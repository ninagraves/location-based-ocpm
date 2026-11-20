"""Object traces of the handling units selected on the instance page (Nina, 2026-11-20).

Documented in `docs/pages/instances.md`, section "Object traces". One row per selected handling unit: its events in
`seq` order (time, AS4 ties, event id; as in the HU profile), each with its activity, timestamp, location and the
other objects it involves (all objects of the log, not only handling units). Above the chart, the event categories
of the directly-follows graph page (`dfg/categories.py`) project the traces: an event is removed when all its
categories are deselected (events in no category always stay); by default all are selected.

Steps (each a function of its own):
1. `trace_events`: the events of the selected handling units in `seq` order.
2. `involved_objects`: per event the objects it involves, with their object type.
3. `object_traces`: both joined, the categories attached, the projection applied and the positions renumbered.
"""

from collections.abc import Collection
from dataclasses import dataclass

import polars as pl

from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.dfg.categories import (
    CATEGORIES,
    removed_events,
)
from ocelescope_module_location_based_ocpm.instances.object_graph import ObjectFrames
from ocelescope_module_location_based_ocpm.instances.profile import ordered_traces

#: At most this many handling units get a row (the first ones of the selection).
MAX_TRACES = 50


@dataclass
class ObjectTraces:
    """The traces of the selected handling units.

    Attributes:
        events: One row per (handling unit, kept event): hu, object_type (of the hu), pos (1-based, after the
            projection), event, time, activity, location (loc^k of the relation, null if unlocated), categories
            (list of `CATEGORIES` keys) and objects (list of structs object, object_type, selected: the other
            objects of the event, sorted by object type and id; `selected` = also one of the selected handling
            units); sorted by the order of the selection, then pos.
        totals: Per selected handling unit (in the order of the selection): hu, object_type, n_events (all its
            events) and n_shown (kept by the projection).
        categories: Per category key the number of distinct events of the selected handling units in it (before
            the projection), for the chips.
        notes: Remarks, e.g. handling units that are not part of the log.
    """

    events: pl.DataFrame
    totals: pl.DataFrame
    categories: dict[str, int]
    notes: list[str]


def trace_events(
    relations: pl.DataFrame | pl.LazyFrame,
    handling_units: Collection[str],
    loc: str,
    hl: str,
    processing: Collection[str] | None = None,
) -> pl.DataFrame:
    """The events of the given handling units in `seq` order (`profile.ordered_traces`).

    Args:
        relations: hu-event relations (`Derivation.relations`).
        handling_units: The handling units.
        loc: Column of loc^k.
        hl: Column of agg(loc^k).
        processing: Event ids of P for the AS4 tie order; None = the transformation events T.

    Returns:
        pl.DataFrame: Columns hu, object_type, pos, event, time, activity, location; sorted by hu and pos.
    """
    selected = relations.lazy().filter(pl.col(c.HU).is_in(list(handling_units)))
    return (
        ordered_traces(selected, loc, hl, processing)
        .select(c.HU, c.OBJECT_TYPE, pl.col("pos").cast(pl.UInt32), c.EVENT, c.TIME, c.ACTIVITY, pl.col("loc").alias("location"))
        .collect()
    )


def involved_objects(frames: ObjectFrames, events: Collection[str]) -> pl.DataFrame:
    """The objects of the given events with their object type.

    Args:
        frames: Tables of the log (`object_graph.object_frames`).
        events: Event ids.

    Returns:
        pl.DataFrame: Columns event, object, object_type; sorted by event, object type and object.
    """
    return (
        frames.e2o.filter(pl.col("event").is_in(list(events)))
        .join(frames.objects, on="object", how="left")
        .sort("event", "object_type", "object", nulls_last=True)
        .collect()
    )


def object_traces(
    relations: pl.DataFrame | pl.LazyFrame,
    frames: ObjectFrames,
    categories: pl.DataFrame,
    handling_units: Collection[str],
    units: pl.DataFrame,
    loc: str,
    hl: str,
    processing: Collection[str] | None = None,
    excluded: Collection[str] = (),
    max_traces: int = MAX_TRACES,
) -> ObjectTraces:
    """The traces of the selected handling units with the other objects of every event, projected on the categories.

    Example (running example, c2 selected, Movements deselected): c2's trace e3 roll, e4 label, e6 move, e8 load
    truck, ... loses e6 (a movement only) but keeps e8 (a movement to the vehicle T, while Move to vehicle is
    still selected); e3 lists s1 and c1 as other objects, c1 marked `selected` if c1 is selected too.

    Args:
        relations: hu-event relations (`Derivation.relations`).
        frames: Tables of the log (`object_graph.object_frames`).
        categories: `dfg.categories.event_categories` of all events.
        handling_units: The selected handling units (order kept).
        units: All handling units of the log, columns hu and object_type (`Derivation.handling_units`).
        loc: Column of loc^k.
        hl: Column of agg(loc^k).
        processing: Event ids of P (AS4 tie order).
        excluded: Deselected category keys.
        max_traces: Rows at most.

    Returns:
        ObjectTraces: Events, totals, category counts and notes.
    """
    known = set(units[c.HU].to_list())
    notes = []
    unknown = [hu for hu in handling_units if hu not in known]
    if unknown:
        notes.append(f"Not handling units of this log: {', '.join(unknown)}.")
    selected = [hu for hu in dict.fromkeys(handling_units) if hu in known]
    if len(selected) > max_traces:
        notes.append(f"{len(selected)} handling units selected; only the first {max_traces} are drawn.")
        selected = selected[:max_traces]
    order = pl.DataFrame({c.HU: selected, "_order": range(len(selected))}, schema={c.HU: pl.String, "_order": pl.Int64})
    events = trace_events(relations, selected, loc, hl, processing)
    ids = events[c.EVENT].unique()
    cats = categories.filter(pl.col(c.EVENT).is_in(ids.implode()))
    counts = {k: int(cats[k].sum() or 0) for k in CATEGORIES}
    category_lists = cats.select(
        c.EVENT,
        pl.concat_list(pl.when(pl.col(k)).then(pl.lit(k)).otherwise(None) for k in CATEGORIES).list.drop_nulls().alias("categories"),
    )
    objects = involved_objects(frames, ids.to_list()).with_columns(pl.col("object").is_in(selected).alias("selected"))
    removed = removed_events(cats, excluded)
    # Other objects per (hu, event): the event's objects without the hu itself.
    others = (
        events.select(c.HU, c.EVENT)
        .join(objects, on=c.EVENT, how="inner")
        .filter(pl.col("object") != pl.col(c.HU))
        .group_by(c.HU, c.EVENT, maintain_order=True)
        .agg(pl.struct("object", "object_type", "selected").alias("objects"))
    )
    empty_objects = pl.lit([], dtype=pl.List(pl.Struct({"object": pl.String, "object_type": pl.String, "selected": pl.Boolean})))
    kept = (
        events.join(removed, on=c.EVENT, how="anti")
        .join(category_lists, on=c.EVENT, how="left")
        .join(others, on=[c.HU, c.EVENT], how="left")
        .join(order, on=c.HU, how="left")
        .sort("_order", "pos")
        .with_columns(
            (pl.int_range(pl.len()).over(c.HU) + 1).cast(pl.UInt32).alias("pos"),
            pl.col("categories").fill_null(pl.lit([], dtype=pl.List(pl.String))),
            pl.col("objects").fill_null(empty_objects),
        )
        .drop("_order")
    )
    totals = (
        order.join(units.select(c.HU, c.OBJECT_TYPE), on=c.HU, how="left")
        .join(events.group_by(c.HU).agg(pl.len().cast(pl.Int64).alias("n_events")), on=c.HU, how="left")
        .join(kept.group_by(c.HU).agg(pl.len().cast(pl.Int64).alias("n_shown")), on=c.HU, how="left")
        .with_columns(pl.col("n_events").fill_null(0), pl.col("n_shown").fill_null(0))
        .sort("_order")
        .drop("_order")
    )
    return ObjectTraces(events=kept, totals=totals, categories=counts, notes=notes)
