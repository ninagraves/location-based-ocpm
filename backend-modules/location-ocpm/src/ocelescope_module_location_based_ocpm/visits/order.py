"""Order of events with the same timestamp (AS4 in `overview/Single Level Visit Mappings.md`).

`seq(E')` orders a set of events by time; ties (events with the same timestamp) are broken by AS4:
1. movement events (e ∈ M) first,
2. then processing operations (e ∈ P),
3. then all other events;
within each group by event id.
An event that is both a movement and a processing operation counts as a movement (group 1).

Every function that orders the events of a handling unit (`otrace(hu)`) or of several handling units
(event order of the trace figure) sorts by time, `tie_rank`, event id via `sort_by_seq`, so trace
positions, visits, transfers and the trace figure follow AS4.

**Waiting times use another order** (Nina, 2026-11-01): processing operations before movements, then the
rest (`tie_rank(..., processing_first=True)`). A removal from storage is usually a movement; with AS4 it
would come before a processing operation at the same timestamp and give that operation a waiting time of
0. In the waiting order, the processing operation comes first, so it is itself the removal and waits from
the previous clock event, including the storage time (DD-W1). `add_waiting_positions` adds this order as
the column waiting_position; `waiting.add_storage_removals` and `waiting.time_pieces` use it.
The set of relations of a visit is still the AS4 infix; only the order inside it changes.

How to change a tie-break: change `tie_rank` only.
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
    processing: Collection[str] | None = None,
    movement: str = c.IS_MOVEMENT,
    processing_first: bool = False,
) -> pl.Expr:
    """Expression for the group of an event among events with the same timestamp.

    AS4 (default): 0 = movement, 1 = processing operation, 2 = other; an event in M ∩ P is a movement.
    Waiting order (`processing_first=True`): 0 = processing operation, 1 = movement, 2 = other; an event in
    M ∩ P is a processing operation.

    Args:
        processing: The processing operations P as event ids; None = the transformation events T.
        movement: Boolean column marking the movement events M (null counts as no movement).
        processing_first: False = AS4; True = the waiting-time order (processing before movements).

    Returns:
        pl.Expr: UInt8 named `tie_rank`.
    """
    is_movement = pl.col(movement).fill_null(False)
    is_processing = processing_flag(processing)
    first, second = (is_processing, is_movement) if processing_first else (is_movement, is_processing)
    return (
        pl.when(first)
        .then(pl.lit(0, pl.UInt8))
        .when(second)
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


def add_waiting_positions(
    relations: Frame, processing: Collection[str] | None = None, movement: str = c.IS_MOVEMENT
) -> Frame:
    """Add waiting_position: the position of every relation in otrace(hu) in the waiting-time order.

    Like `position` (AS4), but at equal timestamps processing operations come before movements
    (`tie_rank(..., processing_first=True)`). Both are permutations of 1..n per handling unit that differ
    only inside groups of events with the same timestamp. The rows keep their order.
    Works on the relations frame and on visit relations alike (a relation that appears in several visits
    gets the same waiting position in each): the positions are computed once per (hu, event) and joined.

    Args:
        relations: Frame with columns hu, time, event, `movement` (and is_transformation if `processing`
            is None), e.g. the relations or the output of `maximal.visit_relations`.
        processing: The processing operations P as event ids; None = the transformation events T. Use the
            same P as for the waiting times.
        movement: Boolean column marking the movement events M.

    Returns:
        Frame: `relations` with the column waiting_position (Int64, starting at 1).
    """
    key = pl.struct(
        pl.col(c.TIME), tie_rank(processing, movement, processing_first=True), pl.col(c.EVENT)
    )
    needed = [c.HU, c.TIME, c.EVENT, movement] + ([c.IS_TRANSFORMATION] if processing is None else [])
    positions = (
        relations.select(needed)
        .unique([c.HU, c.EVENT])
        .select(c.HU, c.EVENT, key.rank("ordinal").over(c.HU).cast(pl.Int64).alias(v.WAITING_POSITION))
    )
    names = relations.collect_schema().names()
    base = relations.drop(v.WAITING_POSITION) if v.WAITING_POSITION in names else relations
    return base.join(positions, on=[c.HU, c.EVENT], how="left", maintain_order="left")
