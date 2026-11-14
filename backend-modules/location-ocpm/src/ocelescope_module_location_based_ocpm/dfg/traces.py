"""Step 1: the traces of the objects whose directly-follows relations are shown.

An object's trace is the sequence of its events (via e2o) in `seq` order: time, then the AS4 tie rank
(movements, processing operations, rest; `visits/order.py`), then event id. This is the same order as
otrace(hu) everywhere else in the module, so the arcs of a handling unit agree with its trace figure.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable

import polars as pl

from ..derivation import columns as c
from ..visits.order import sort_by_seq
from . import columns as d

FrameLike = pl.DataFrame | pl.LazyFrame


def considered_objects(
    objects: FrameLike, object_types: Iterable[str], handling_units: Collection[str] | None = None
) -> pl.LazyFrame:
    """The objects whose traces are used for the selected object types.

    For an object type that contains handling units, only its handling units are used (with handling units
    given as object types this is every object of the type; with a handling-unit table, objects of the type
    that are not in the table are left out). For any other object type, all its objects are used.

    Args:
        objects: All objects, columns object and object_type.
        object_types: The selected object types.
        handling_units: The handling units HU as object ids; None = no restriction.

    Returns:
        pl.LazyFrame: Columns object, object_type.
    """
    selected = objects.lazy().filter(pl.col(c.OBJECT_TYPE).is_in(list(object_types)))
    if handling_units is None:
        return selected.select(d.OBJECT, c.OBJECT_TYPE)
    is_hu = pl.col(d.OBJECT).is_in(list(handling_units))
    hu_types = is_hu.any().over(c.OBJECT_TYPE)
    return selected.filter(~hu_types | is_hu).select(d.OBJECT, c.OBJECT_TYPE)


def object_traces(
    e2o: FrameLike,
    events: FrameLike,
    objects: FrameLike,
    processing: Collection[str] | None = None,
) -> pl.DataFrame:
    """One row per (object, event) of the given objects, sorted by object, then in `seq` order.

    Args:
        e2o: Event-to-object relations, columns event and object (further columns are ignored; an object
            linked to an event with several qualifiers counts once).
        events: Events with columns event, time, activity and is_movement (and is_transformation if
            `processing` is None).
        objects: The considered objects, columns object and object_type (`considered_objects`).
        processing: The processing operations P as event ids, for the AS4 tie rank; None = the
            transformation events T.

    Returns:
        pl.DataFrame: Columns object, object_type, event, activity, time, position (1-based position in the
        object's trace).
    """
    event_columns = [c.EVENT, c.TIME, c.ACTIVITY, c.IS_MOVEMENT]
    if processing is None:
        event_columns.append(c.IS_TRANSFORMATION)
    rows = (
        e2o.lazy()
        .select(c.EVENT, d.OBJECT)
        .unique()
        .join(objects.lazy(), on=d.OBJECT)
        .join(events.lazy().select(event_columns), on=c.EVENT)
        .collect()
    )
    return (
        sort_by_seq(rows, d.OBJECT, processing=processing)
        .with_columns(pl.int_range(1, pl.len() + 1, dtype=pl.UInt32).over(d.OBJECT).alias(d.POSITION))
        .select(d.OBJECT, c.OBJECT_TYPE, c.EVENT, c.ACTIVITY, c.TIME, d.POSITION)
    )
