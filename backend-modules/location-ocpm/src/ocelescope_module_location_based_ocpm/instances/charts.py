"""Lineage graph and HU timeline of the handling units selected on the instance page.

Documented in `docs/pages/instances.md`, sections "Lineage" and "HU timeline". Both reuse the resource
packages: `lineage/` (concept "Instance Lineage" and "Instance Visualisation") and `timeline/object_timeline.py`
(resource "HU Timeline").
"""

import json
import math
from collections.abc import Collection
from dataclasses import dataclass

import polars as pl

from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.derivation.pipeline import Derivation
from ocelescope_module_location_based_ocpm.lineage.graph import (
    _EDGES,
    _NODES,
    EVENT,
    FOCAL,
    LINEAGE,
    OBJECT,
    lineage_graph,
)
from ocelescope_module_location_based_ocpm.lineage.lineage import Direction
from ocelescope_module_location_based_ocpm.lineage.relations import lineage_relations
from ocelescope_module_location_based_ocpm.timeline.object_timeline import (
    MAX_HANDLING_UNITS,
    TimelineAxis,
    object_timeline,
    timeline_relations,
)

#: At most this many nodes are drawn in the lineage graph (larger lineages are cut, with a note).
MAX_LINEAGE_NODES = 500


@dataclass
class SelectionLineage:
    """The union of the lineage graphs of the selected handling units.

    Attributes:
        nodes: Columns node, kind (`object`/`event`), role (`focal` for selected handling units, `lineage`,
            `sibling`), object_type (objects), activity and time (events).
        edges: Columns source, target, kind (`lineage`/`sibling`), event, directed (see `lineage.graph`) and
            activity (of the event).
        notes: Remarks, e.g. handling units that are not part of the log, or a cut graph.
    """

    nodes: pl.DataFrame
    edges: pl.DataFrame
    notes: list[str]


def selection_lineage(
    derivation: Derivation,
    handling_units: Collection[str],
    direction: Direction = "both",
    gen: float = math.inf,
    with_events: bool = False,
    with_siblings: bool = False,
    max_nodes: int = MAX_LINEAGE_NODES,
) -> SelectionLineage:
    """The lineage graph of several handling units: the union of their graphs (`lineage.graph.lineage_graph`).

    A node that is focal in one graph and part of the lineage in another stays focal: every selected handling
    unit is highlighted.

    Args:
        derivation: The current derivation (roles, handling units, relations for activities and times).
        handling_units: The selected handling units.
        direction: `components`, `products` or `both`.
        gen: Generations per direction, a natural number or `math.inf`.
        with_events: Bipartite graph (handling units and transformation events).
        with_siblings: Add the siblings.
        max_nodes: Nodes drawn at most; beyond it the graph is cut (nodes in the order of the selection).

    Returns:
        SelectionLineage: Nodes, edges and notes.
    """
    roles = derivation.roles
    known = set(derivation.handling_units[c.HU].to_list())
    selected = [hu for hu in dict.fromkeys(handling_units) if hu in known]
    notes = []
    unknown = [hu for hu in handling_units if hu not in known]
    if unknown:
        notes.append(f"Not handling units of this log: {', '.join(unknown)}.")
    relations = lineage_relations(roles) if roles.height else pl.DataFrame(
        schema={"parent": pl.String, "child": pl.String, "event": pl.String}
    )
    graphs = [lineage_graph(relations, roles, hu, direction, gen, with_events, with_siblings) for hu in selected]
    if not graphs:
        return SelectionLineage(_with_attributes(pl.DataFrame(schema=_NODES), derivation), pl.DataFrame(schema={**_EDGES, c.ACTIVITY: pl.String}), notes)
    nodes = (
        pl.concat([g.nodes for g in graphs])
        .with_columns(
            pl.when(pl.col("node").is_in(selected) & (pl.col("kind") == OBJECT))
            .then(pl.lit(FOCAL))
            .when(pl.col("role") == FOCAL)
            .then(pl.lit(LINEAGE))
            .otherwise(pl.col("role"))
            .alias("role")
        )
        # A node is kept once, with its most prominent role (focal, then lineage, then sibling).
        .with_columns(pl.col("role").replace_strict({FOCAL: 0, LINEAGE: 1}, default=2).alias("_rank"))
        .sort("_rank", maintain_order=True)
        .unique(subset="node", keep="first", maintain_order=True)
        .drop("_rank")
    )
    edges = pl.concat([g.edges for g in graphs]).unique(maintain_order=True)
    if nodes.height > max_nodes:
        notes.append(f"The lineage has {nodes.height} nodes; only the first {max_nodes} are drawn.")
        nodes = nodes.head(max_nodes)
        edges = edges.filter(pl.col("source").is_in(nodes["node"].implode()) & pl.col("target").is_in(nodes["node"].implode()))
    activities = derivation.relations.select(c.EVENT, c.ACTIVITY).unique(subset=c.EVENT)
    edges = edges.join(activities, on=c.EVENT, how="left", maintain_order="left")
    return SelectionLineage(_with_attributes(nodes, derivation), edges, notes)


def _with_attributes(nodes: pl.DataFrame, derivation: Derivation) -> pl.DataFrame:
    """Add object_type (object nodes), activity and time (event nodes) to lineage nodes.

    Args:
        nodes: Columns node, kind, role.
        derivation: The current derivation.

    Returns:
        pl.DataFrame: `nodes` with the columns object_type, activity and time (ISO text).
    """
    types = derivation.handling_units.select(pl.col(c.HU).alias("node"), c.OBJECT_TYPE)
    events = derivation.relations.select(
        pl.col(c.EVENT).alias("node"), c.ACTIVITY, pl.col(c.TIME).dt.to_string("%Y-%m-%d %H:%M:%S").alias(c.TIME)
    ).unique(subset="node")
    objects = nodes.filter(pl.col("kind") == OBJECT).join(types, on="node", how="left")
    event_nodes = nodes.filter(pl.col("kind") == EVENT).join(events, on="node", how="left")
    return pl.concat([objects, event_nodes], how="diagonal_relaxed").select(
        "node", "kind", "role", c.OBJECT_TYPE, c.ACTIVITY, c.TIME
    )


def processing_events(derivation: Derivation) -> list[str]:
    """The processing operations P of the derivation as event ids (for the AS4 tie order).

    Args:
        derivation: The current derivation.

    Returns:
        list[str]: Event ids with is_processing, sorted.
    """
    return sorted(derivation.relations.filter(pl.col(c.IS_PROCESSING).fill_null(False))[c.EVENT].unique().to_list())


def timeline_figure(
    derivation: Derivation,
    handling_units: Collection[str],
    axis: TimelineAxis = "event order",
    show_high_level: bool = True,
    show_activity_labels: bool = True,
    mark_ties: bool = True,
    link_shared_events: bool = True,
    by_first_event: bool = False,
    label_movements: bool = False,
    max_handling_units: int = MAX_HANDLING_UNITS,
) -> tuple[dict, list[str]]:
    """The HU timeline (`timeline.object_timeline`) of handling units at the selected level, as Plotly JSON.

    Args:
        derivation: The current derivation (loc and ploc of the selected level, agg, V, P, roles).
        handling_units: Handling units, top to bottom in this order.
        axis: "event order" or "time".
        show_high_level: Draw the lower half of the band (agg(loc)).
        show_activity_labels: Activity names above the markers.
        mark_ties: Grey boxes behind events with the same timestamp.
        link_shared_events: Dotted lines between the markers of an event shared by shown handling units.
        by_first_event: Order the rows by first event (then id) instead of the given order.
        label_movements: Also write the activity names of movements (`object_timeline.object_timeline`).
        max_handling_units: Rows drawn at most.

    Returns:
        tuple[dict, list[str]]: The figure (`data` and `layout`) and notes (e.g. handling units that are cut).
    """
    known = set(derivation.handling_units[c.HU].to_list())
    wanted = [hu for hu in dict.fromkeys(handling_units) if hu in known]
    notes = []
    unknown = [hu for hu in handling_units if hu not in known]
    if unknown:
        notes.append(f"Not handling units of this log: {', '.join(unknown)}.")
    if len(wanted) > max_handling_units:
        notes.append(f"{len(wanted)} handling units selected; only the first {max_handling_units} are drawn.")
    with_events = set(derivation.relations[c.HU].unique().to_list())
    no_events = [hu for hu in wanted if hu not in with_events]
    if no_events:
        notes.append(f"Without events: {', '.join(no_events)}.")
    relations = derivation.relations.filter(pl.col(c.HU).is_in(wanted)).rename(
        {derivation.loc: "loc", derivation.ploc: "ploc"}
    )
    prepared = timeline_relations(
        relations.drop(c.IS_PROCESSING),
        handling_units=None if by_first_event else [hu for hu in wanted if hu in with_events],
        agg=derivation.context.agg,
        vehicles=derivation.context.vehicles,
        processing=processing_events(derivation),
        roles=derivation.roles if derivation.roles.height else None,
        axis=axis,
        max_handling_units=max_handling_units,
    )
    if prepared.height == 0:
        return {"data": [], "layout": {}}, notes
    figure = object_timeline(
        prepared,
        show_high_level=show_high_level and derivation.has_high_level,
        show_activity_labels=show_activity_labels,
        mark_ties=mark_ties,
        link_shared_events=link_shared_events,
        label_movements=label_movements,
    )
    figure.update_layout(width=None, autosize=True)
    return json.loads(figure.to_json()), notes
