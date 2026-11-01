"""Order of events with the same timestamp (AS4 in `overview/Single Level Visit Mappings.md`).

`seq(E')` orders a set of events by time; ties (events with the same timestamp) are broken by AS4:
1. movement events (e ∈ M) first,
2. then processing operations (e ∈ P),
3. then all other events;
within each group by event id.
An event that is both a movement and a processing operation counts as a movement (group 1).

Every function that orders the events of a handling unit (`otrace(hu)`) or of several handling units
(event order of the trace figure) sorts by time, `tie_rank`, event id via `sort_by_seq`, so trace
positions, visits, transfers and waiting times all follow AS4.

How to change the tie-break (e.g. processing before movements): change `tie_rank` only.
"""

from collections.abc import Collection

import polars as pl

from ..derivation import columns as c
from . import columns as v
from .context import Frame


def processing_flag(processing: Collection[str] | None = None) -> pl.Expr:
    """Expression for e ∈ P per row.

    Args:
        processing: The processing operations P as event ids; None = the transformation events T (column
            is_transformation), the implementation default decided by Nina (2026-10-31).

    Returns:
        pl.Expr: Boolean, never null.
    """
    if processing is None:
        return pl.col(c.IS_TRANSFORMATION).fill_null(False)
    return pl.col(c.EVENT).is_in(list(processing))


def tie_rank(
    processing: Collection[str] | None = None, movement: str = c.IS_MOVEMENT
) -> pl.Expr:
    """Expression for the AS4 group of an event: 0 = movement, 1 = processing operation, 2 = other.

    Args:
        processing: The processing operations P as event ids; None = the transformation events T.
        movement: Boolean column marking the movement events M (null counts as no movement).

    Returns:
        pl.Expr: UInt8 named `tie_rank`.
    """
    return (
        pl.when(pl.col(movement).fill_null(False))
        .then(pl.lit(0, pl.UInt8))
        .when(processing_flag(processing))
        .then(pl.lit(1, pl.UInt8))
        .otherwise(pl.lit(2, pl.UInt8))
        .alias(v.TIE_RANK)
    )


def add_tie_rank(
    relations: Frame, processing: Collection[str] | None = None, movement: str = c.IS_MOVEMENT
) -> Frame:
    """Add the column tie_rank (see `tie_rank`).

    Args:
        relations: Frame with columns event, `movement` (and is_transformation if `processing` is None).
        processing: The processing operations P as event ids; None = the transformation events T.
        movement: Boolean column marking the movement events M.

    Returns:
        Frame: `relations` with the column tie_rank.
    """
    return relations.with_columns(tie_rank(processing, movement))


def sort_by_seq(
    relations: Frame,
    *by: str,
    processing: Collection[str] | None = None,
    movement: str = c.IS_MOVEMENT,
) -> Frame:
    """Sort by the columns `by`, then in `seq` order: time, tie_rank (AS4), event id.

    Args:
        relations: Frame with columns event, time, `movement` (and is_transformation if `processing` is
            None).
        by: Columns sorted by first, e.g. hu for object traces; none for the order of all events.
        processing: The processing operations P as event ids; None = the transformation events T.
        movement: Boolean column marking the movement events M.

    Returns:
        Frame: `relations` with the column tie_rank, sorted.
    """
    return add_tie_rank(relations, processing, movement).sort(*by, c.TIME, v.TIE_RANK, c.EVENT)
