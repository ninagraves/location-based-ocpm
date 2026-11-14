"""Step 1: the traces of the objects whose directly-follows relations are shown.

An object's trace is the sequence of its events (via e2o) ordered by time, then the DFG boundary rank
(`boundary_rank`: a transformation event at the object's first timestamp comes first, one at its last
timestamp comes last; Nina, 2026-11-14), then the AS4 tie rank (movements, processing operations, rest;
`visits/order.py`), then event id. Apart from the boundary rank this is the `seq` order used everywhere
else in the module.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable

import polars as pl

from ..derivation import columns as c
from ..visits import columns as v
from ..visits.order import add_tie_rank
from . import columns as d

FrameLike = pl.DataFrame | pl.LazyFrame

#: Column of the DFG boundary rank (`boundary_rank`).
BOUNDARY_RANK = "boundary_rank"


def boundary_rank(by: str = d.OBJECT) -> pl.Expr:
    """Expression for the DFG tie-break at the start and end of an object's trace (Nina, 2026-11-14).

    Among events with the same timestamp, a transformation event at the object's first timestamp gets 0
    (it comes first, as it creates the object), one at the object's last timestamp gets 2 (it comes last,
    as it consumes the object), every other event 1. If all events of an object share one timestamp, the
    first rule applies (rank 0).

    Args:
        by: Column of the object whose trace is ordered.

    Returns:
        pl.Expr: UInt8 named `boundary_rank`; needs the columns `by`, time and is_transformation.
    """
    transformation = pl.col(c.IS_TRANSFORMATION).fill_null(False)
    return (
        pl.when(transformation & (pl.col(c.TIME) == pl.col(c.TIME).min().over(by)))
        .then(pl.lit(0, pl.UInt8))
        .when(transformation & (pl.col(c.TIME) == pl.col(c.TIME).max().over(by)))
        .then(pl.lit(2, pl.UInt8))
        .otherwise(pl.lit(1, pl.UInt8))
        .alias(BOUNDARY_RANK)
    )


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
    """One row per (object, event) of the given objects, sorted by object, time, `boundary_rank`, AS4 tie rank, event.

    Args:
        e2o: Event-to-object relations, columns event and object (further columns are ignored; an object
            linked to an event with several qualifiers counts once).
        events: Events with columns event, time, activity, is_movement and is_transformation.
        objects: The considered objects, columns object and object_type (`considered_objects`).
        processing: The processing operations P as event ids, for the AS4 tie rank; None = the
            transformation events T.

    Returns:
        pl.DataFrame: Columns object, object_type, event, activity, time, position (1-based position in the
        object's trace).
    """
    event_columns = [c.EVENT, c.TIME, c.ACTIVITY, c.IS_MOVEMENT, c.IS_TRANSFORMATION]
    rows = (
        e2o.lazy()
        .select(c.EVENT, d.OBJECT)
        .unique()
        .join(objects.lazy(), on=d.OBJECT)
        .join(events.lazy().select(event_columns), on=c.EVENT)
        .collect()
    )
    return (
        add_tie_rank(rows.with_columns(boundary_rank(d.OBJECT)), processing)
        .sort(d.OBJECT, c.TIME, BOUNDARY_RANK, v.TIE_RANK, c.EVENT)
        .with_columns(pl.int_range(1, pl.len() + 1, dtype=pl.UInt32).over(d.OBJECT).alias(d.POSITION))
        .select(d.OBJECT, c.OBJECT_TYPE, c.EVENT, c.ACTIVITY, c.TIME, d.POSITION)
    )
