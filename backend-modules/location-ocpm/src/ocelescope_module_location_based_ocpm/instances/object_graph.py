"""Object graph of the handling units selected on the instance page.

Documented in `docs/pages/instances.md`, section "Object graph". Nodes are the selected handling units and every
object related to one of them, by a shared event or by an o2o relation (in either direction); arcs are the shared
events (one undirected arc per pair of objects, listing its events) and the o2o relations (directed, with their
qualifier). The graph is complete for these nodes: arcs between two related objects are included as well, so the
frontend only shows or hides object types and arc kinds without asking the backend again.
"""

from collections.abc import Collection
from dataclasses import dataclass

import polars as pl
from ocelescope import OCEL

from ocelescope_module_location_based_ocpm.derivation.inputs import (
    OCEL_ACTIVITY,
    OCEL_EID,
    OCEL_OID,
    OCEL_QUALIFIER,
    OCEL_TIMESTAMP,
    OCEL_TYPE,
)

#: At most this many nodes are returned (selected handling units first, then handling units, then other objects,
#: each by the number of events shared with the selected handling units).
MAX_OBJECT_NODES = 500

#: Roles of the nodes.
FOCAL = "focal"
RELATED = "related"


@dataclass
class ObjectFrames:
    """The tables of a log the object graph is built from.

    Attributes:
        e2o: Columns event, object (unique pairs).
        o2o: Columns source, target, qualifier.
        objects: Columns object, object_type.
        events: Columns event, time, activity.
    """

    e2o: pl.LazyFrame
    o2o: pl.LazyFrame
    objects: pl.LazyFrame
    events: pl.LazyFrame


@dataclass
class ObjectGraph:
    """The object graph of some handling units.

    Attributes:
        nodes: Columns node, object_type, is_hu, role (`focal` for the selected handling units, `related`),
            n_events (events of the object in the log), n_shared (events shared with a selected handling unit).
        event_arcs: Columns source, target (source < target), events (list of structs event, time, activity,
            ordered by time and event id), n_events.
        o2o_arcs: Columns source, target, qualifier.
        notes: Remarks, e.g. handling units that are not part of the log, or a cut graph.
    """

    nodes: pl.DataFrame
    event_arcs: pl.DataFrame
    o2o_arcs: pl.DataFrame
    notes: list[str]


def object_frames(ocel: OCEL) -> ObjectFrames:
    """Read the e2o, o2o, object and event tables of a log, renamed to the module's column names.

    Args:
        ocel: The log.

    Returns:
        ObjectFrames: The tables (lazy).
    """
    return ObjectFrames(
        e2o=ocel.e2o.pl.select(pl.col(OCEL_EID).alias("event"), pl.col(OCEL_OID).alias("object")).unique(),
        o2o=ocel.o2o.pl.select(
            pl.col("ocel:oid_1").alias("source"), pl.col("ocel:oid_2").alias("target"), pl.col(OCEL_QUALIFIER).alias("qualifier")
        ).unique(),
        objects=ocel.objects.pl.select(pl.col(OCEL_OID).alias("object"), pl.col(OCEL_TYPE).alias("object_type")),
        events=ocel.events.pl.select(
            pl.col(OCEL_EID).alias("event"), pl.col(OCEL_TIMESTAMP).alias("time"), pl.col(OCEL_ACTIVITY).alias("activity")
        ),
    )


def related_objects(frames: ObjectFrames, selected: Collection[str]) -> pl.DataFrame:
    """The objects related to the selected ones, by a shared event or an o2o relation, with their shared events.

    Args:
        frames: Tables of the log.
        selected: The selected objects.

    Returns:
        pl.DataFrame: Columns object, n_shared (events shared with a selected object; 0 if only o2o-related), for
        every related object that is not selected.
    """
    selected = list(selected)
    events = frames.e2o.filter(pl.col("object").is_in(selected)).select("event").unique()
    by_event = (
        frames.e2o.join(events, on="event", how="semi")
        .filter(~pl.col("object").is_in(selected))
        .group_by("object")
        .agg(pl.len().cast(pl.Int64).alias("n_shared"))
    )
    o2o = frames.o2o.filter(pl.col("source").is_in(selected) | pl.col("target").is_in(selected))
    by_o2o = (
        pl.concat([o2o.select(pl.col("source").alias("object")), o2o.select(pl.col("target").alias("object"))])
        .filter(~pl.col("object").is_in(selected))
        .unique()
        .with_columns(pl.lit(0, pl.Int64).alias("n_shared"))
    )
    return (
        pl.concat([by_event, by_o2o])
        .group_by("object")
        .agg(pl.col("n_shared").max())
        .sort("object")
        .collect()
    )


def graph_nodes(
    frames: ObjectFrames, selected: Collection[str], related: pl.DataFrame, handling_units: Collection[str]
) -> pl.DataFrame:
    """The nodes of the object graph: the selected objects and the related ones.

    Args:
        frames: Tables of the log.
        selected: The selected handling units (all part of the log).
        related: Output of `related_objects`.
        handling_units: All handling units of the log.

    Returns:
        pl.DataFrame: Columns node, object_type, is_hu, role, n_events, n_shared (null for selected nodes); selected
        nodes first (in the given order), then handling units, then other objects, each by n_shared (descending)
        and id.
    """
    focal = pl.DataFrame(
        {"object": list(selected), "n_shared": None, "order": range(len(selected))},
        schema={"object": pl.String, "n_shared": pl.Int64, "order": pl.Int64},
    )
    nodes = pl.concat([focal, related.with_columns(pl.lit(None, pl.Int64).alias("order"))])
    ids = nodes["object"].to_list()
    counts = frames.e2o.filter(pl.col("object").is_in(ids)).group_by("object").agg(pl.len().cast(pl.Int64).alias("n_events"))
    types = frames.objects.filter(pl.col("object").is_in(ids))
    return (
        nodes.lazy()
        .join(types, on="object", how="left")
        .join(counts, on="object", how="left")
        .with_columns(
            pl.col("object").is_in(list(handling_units)).alias("is_hu"),
            pl.when(pl.col("order").is_not_null()).then(pl.lit(FOCAL)).otherwise(pl.lit(RELATED)).alias("role"),
            pl.col("n_events").fill_null(0),
        )
        .sort(
            [pl.col("order").is_null(), "order", ~pl.col("is_hu"), "n_shared", "object"],
            descending=[False, False, False, True, False],
            nulls_last=True,
        )
        .select(pl.col("object").alias("node"), "object_type", "is_hu", "role", "n_events", "n_shared")
        .collect()
    )


def event_arcs(frames: ObjectFrames, nodes: Collection[str]) -> pl.DataFrame:
    """One undirected arc per pair of nodes that share at least one event, with the shared events.

    Args:
        frames: Tables of the log.
        nodes: Ids of the nodes.

    Returns:
        pl.DataFrame: Columns source, target (source < target), events (list of structs event, time, activity,
        ordered by time and event id), n_events; ordered by source and target.
    """
    e2o = frames.e2o.filter(pl.col("object").is_in(list(nodes)))
    pairs = (
        e2o.join(e2o, on="event", suffix="_2")
        .filter(pl.col("object") < pl.col("object_2"))
        .join(frames.events, on="event", how="left")
        .sort("time", "event")
    )
    return (
        pairs.group_by(pl.col("object").alias("source"), pl.col("object_2").alias("target"), maintain_order=True)
        .agg(pl.struct("event", "time", "activity").alias("events"))
        .with_columns(pl.col("events").list.len().cast(pl.Int64).alias("n_events"))
        .sort("source", "target")
        .collect()
    )


def o2o_arcs(frames: ObjectFrames, nodes: Collection[str]) -> pl.DataFrame:
    """The o2o relations between nodes, as directed arcs.

    Args:
        frames: Tables of the log.
        nodes: Ids of the nodes.

    Returns:
        pl.DataFrame: Columns source, target, qualifier; ordered by source, target and qualifier.
    """
    nodes = list(nodes)
    return (
        frames.o2o.filter(pl.col("source").is_in(nodes) & pl.col("target").is_in(nodes))
        .sort("source", "target", "qualifier")
        .collect()
    )


def object_graph(
    frames: ObjectFrames,
    selected: Collection[str],
    handling_units: Collection[str],
    max_nodes: int = MAX_OBJECT_NODES,
) -> ObjectGraph:
    """The object graph of the selected handling units: they, their related objects and all arcs between these.

    Args:
        frames: Tables of the log (`object_frames`).
        selected: The selected handling units.
        handling_units: All handling units of the log.
        max_nodes: Nodes returned at most; beyond it the graph is cut (order of `graph_nodes`).

    Returns:
        ObjectGraph: Nodes, event arcs, o2o arcs and notes.
    """
    known = set(handling_units)
    focal = [hu for hu in dict.fromkeys(selected) if hu in known]
    notes = []
    unknown = [hu for hu in selected if hu not in known]
    if unknown:
        notes.append(f"Not handling units of this log: {', '.join(unknown)}.")
    nodes = graph_nodes(frames, focal, related_objects(frames, focal), known)
    if nodes.height > max_nodes:
        notes.append(f"{nodes.height} objects; only the first {max_nodes} are drawn.")
        nodes = nodes.head(max_nodes)
    ids = nodes["node"].to_list()
    return ObjectGraph(nodes=nodes, event_arcs=event_arcs(frames, ids), o2o_arcs=o2o_arcs(frames, ids), notes=notes)
