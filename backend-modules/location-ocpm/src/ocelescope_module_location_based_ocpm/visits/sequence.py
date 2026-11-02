"""General helpers for positions, runs and intervals in sequences (one sequence per group, e.g. per hu).

Every visit-related step works on sequences: otrace(hu) is a sequence of relations, a visit is an interval
[first_position, last_position] of it, an excursion is a run of non-conforming relations inside a visit,
and a visit sequence is a sequence of visits. These helpers do the recurring operations once, as polars
expressions or frame functions (eager and lazy alike), so the maximal visits, excursions, the sweep, the
properties of visit sets, the dwell times and the metrics all use the same code:

| helper | what it does | used by |
|---|---|---|
| `add_positions` | position 1, 2, ... of every row in its sequence | trace positions, visit sequences (j) |
| `run_ids`, `runs` | maximal runs of equal values (or of true flags) | excursions, high-level runs of the figure |
| `expand_intervals` | one row per position of each interval | visit relations R(ν) |
| `at_positions` | look up columns at a position (+ offset) of the same sequence | entry, last and exit event/time of visits |
| `interval_pairs` | contained / overlapping pairs of intervals of one sequence | properties of visit sets |
| `python_runs` | the same runs for a plain Python list | sweep checks, tests |
"""

from collections.abc import Callable, Sequence
from typing import Any

import polars as pl

from ..derivation import columns as c
from . import columns as v
from .context import Frame

#: Relation of two intervals a, b of one sequence (`interval_pairs`).
CONTAINED_IN = "contained in"
OVERLAPS = "overlaps"
#: Columns of `interval_pairs`.
OTHER = "other_"
RELATION = "relation"
N_SHARED = "n_shared"
#: Columns of `runs`.
RUN = "run"
LENGTH = "length"


def add_positions(
    frame: Frame,
    group: str | Sequence[str] = c.HU,
    order_by: str | Sequence[str] = v.POSITION,
    name: str = v.POSITION,
) -> Frame:
    """Number the rows of every sequence 1, 2, ... in the given order.

    Args:
        frame: Any frame with the group and order columns.
        group: Column(s) identifying the sequence, e.g. "hu".
        order_by: Column(s) giving the order inside a sequence.
        name: Name of the new column.

    Returns:
        Frame: `frame` with the column `name` (Int64), sorted by group and order.
    """
    group = [group] if isinstance(group, str) else list(group)
    order_by = [order_by] if isinstance(order_by, str) else list(order_by)
    return frame.sort(*group, *order_by).with_columns(
        (pl.int_range(pl.len()).over(group) + 1).cast(pl.Int64).alias(name)
    )


def run_ids(
    value: str | pl.Expr,
    group: str | Sequence[str] = c.HU,
    order_by: str = v.POSITION,
) -> pl.Expr:
    """Expression: number of the maximal run of equal consecutive values each row belongs to.

    Runs are counted per sequence (1, 2, ...); null counts as a value of its own (⊥ = ⊥), so a run of
    nulls is one run. For a boolean `value`, the runs alternate between true and false.

    Args:
        value: Column name or expression whose runs are wanted (e.g. high_level, or at_location).
        group: Column(s) identifying the sequence.
        order_by: Column giving the order.

    Returns:
        pl.Expr: Int64 run number per row.
    """
    expr = pl.col(value) if isinstance(value, str) else value
    group = [group] if isinstance(group, str) else list(group)
    changed = expr.ne_missing(expr.shift(1)).fill_null(True)
    return changed.cast(pl.Int64).cum_sum().over(group, order_by=order_by)


def runs(
    frame: Frame,
    value: str | pl.Expr,
    group: str | Sequence[str] = c.HU,
    position: str = v.POSITION,
    keep: Callable[[pl.Expr], pl.Expr] | None = None,
    aggregations: Sequence[pl.Expr] = (),
) -> Frame:
    """One row per maximal run of equal consecutive values.

    Args:
        frame: One row per sequence element with the group columns and `position`.
        value: Column or expression whose runs are wanted; its value is kept in the column "value".
        group: Column(s) identifying the sequence.
        position: Column giving the order.
        keep: Optional filter on the run's value, e.g. `lambda x: ~x` for runs of false only.
        aggregations: Further aggregations per run (e.g. `pl.col("event").first()`).

    Returns:
        Frame: Group columns, run, value, first_position, last_position, length (number of elements), and the
        further aggregations; sorted by group and run.
    """
    group = [group] if isinstance(group, str) else list(group)
    expr = pl.col(value) if isinstance(value, str) else value
    out = (
        frame.with_columns(expr.alias("value"))
        .with_columns(run_ids("value", group, position).alias(RUN))
        .group_by(*group, RUN)
        .agg(
            pl.col("value").first(),
            pl.col(position).min().cast(pl.Int64).alias(v.FIRST_POSITION),
            pl.col(position).max().cast(pl.Int64).alias(v.LAST_POSITION),
            pl.len().cast(pl.Int64).alias(LENGTH),
            *aggregations,
        )
    )
    if keep is not None:
        out = out.filter(keep(pl.col("value")))
    return out.sort(*group, RUN)


def expand_intervals(
    frame: Frame,
    first: str = v.FIRST_POSITION,
    last: str = v.LAST_POSITION,
    name: str = v.POSITION,
) -> Frame:
    """One row per position of every interval [first, last] (linear in the size of the result).

    Args:
        frame: One row per interval with the columns `first` and `last`.
        first: Column of the first position.
        last: Column of the last position.
        name: Name of the new position column.

    Returns:
        Frame: The rows of `frame`, repeated once per position, with the column `name` (Int64).
    """
    return (
        frame.with_columns(pl.int_ranges(pl.col(first), pl.col(last) + 1).alias(name))
        .explode(name)
        .with_columns(pl.col(name).cast(pl.Int64))
    )


def at_positions(
    frame: Frame,
    sequence: Frame,
    position: str,
    columns: dict[str, str],
    group: str | Sequence[str] = c.HU,
    offset: int = 0,
    sequence_position: str = v.POSITION,
) -> Frame:
    """Look up columns of a sequence at a position (+ offset) of every row (left join).

    Example: the exit event of a visit is the event at last_position + 1 of its trace:
    `at_positions(visits, relations, "last_position", {"event": "exit_event"}, offset=1)`.

    Args:
        frame: Rows with the group columns and the column `position`.
        sequence: The sequence elements with the group columns, `sequence_position` and the looked-up columns.
        position: Column of `frame` with the position to look up.
        columns: Column of `sequence` -> new column name in the result.
        group: Column(s) identifying the sequence.
        offset: Added to `position` (e.g. 1 = the next element, -1 = the previous one).
        sequence_position: Position column of `sequence`.

    Returns:
        Frame: `frame` with the new columns (null where the position does not exist).
    """
    group = [group] if isinstance(group, str) else list(group)
    looked_up = sequence.select(
        *group,
        (pl.col(sequence_position).cast(pl.Int64) - offset).alias("_at"),
        *(pl.col(src).alias(dst) for src, dst in columns.items()),
    )
    return (
        frame.with_columns(pl.col(position).cast(pl.Int64).alias("_at"))
        .join(looked_up, on=[*group, "_at"], how="left")
        .drop("_at")
    )


def interval_pairs(
    intervals: Frame,
    group: str | Sequence[str] = c.HU,
    key: str = v.VISIT_ID,
    first: str = v.FIRST_POSITION,
    last: str = v.LAST_POSITION,
) -> Frame:
    """The contained and overlapping pairs among the intervals of each sequence.

    For two different intervals a = [a1, a2] and b = [b1, b2] of the same sequence:
    - a is **contained in** b iff b1 ≤ a1 and a2 ≤ b2 (identical intervals are contained in each other);
    - a **overlaps** b iff they share a position and neither is contained in the other (symmetric).
    Disjoint pairs are left out. The work is a self-join per sequence, i.e. quadratic in the number of
    intervals of one sequence only.

    Args:
        intervals: One row per interval with the group columns, `key`, `first` and `last`.
        group: Column(s) identifying the sequence (e.g. "hu").
        key: Id column of the intervals (e.g. "visit_id").
        first: Column of the first position.
        last: Column of the last position.

    Returns:
        Frame: Columns group, key, other_<key>, relation ("contained in" / "overlaps"; read: key relation
        other), n_shared (number of shared positions); one row per ordered pair, so an overlap appears
        twice; sorted by group, key and other.
    """
    group = [group] if isinstance(group, str) else list(group)
    base = intervals.select(*group, key, first, last)
    other = base.rename({key: OTHER + key, first: "_b1", last: "_b2"})
    a1, a2, b1, b2 = pl.col(first), pl.col(last), pl.col("_b1"), pl.col("_b2")
    contained = (b1 <= a1) & (a2 <= b2)
    contains = (a1 <= b1) & (b2 <= a2)
    shared = pl.min_horizontal(a2, b2) - pl.max_horizontal(a1, b1) + 1
    return (
        base.join(other, on=group)
        .filter((pl.col(key) != pl.col(OTHER + key)) & (shared > 0))
        .with_columns(
            pl.when(contained)
            .then(pl.lit(CONTAINED_IN))
            .when(~contains)
            .then(pl.lit(OVERLAPS))
            .alias(RELATION),
            shared.cast(pl.Int64).alias(N_SHARED),
        )
        .filter(pl.col(RELATION).is_not_null())
        .select(*group, key, OTHER + key, RELATION, N_SHARED)
        .sort(*group, key, OTHER + key)
    )


def python_runs(
    values: Sequence[Any], start: int = 0, keep: Callable[[Any], bool] | None = None
) -> list[tuple[int, int, Any]]:
    """Maximal runs of equal consecutive values of a plain Python list (positions as list indices).

    Args:
        values: The sequence.
        start: Index of the first element to consider.
        keep: Optional filter on the run's value.

    Returns:
        list[tuple[int, int, Any]]: (first index, last index, value) of every run, in order.
    """
    out = []
    i = start
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[j + 1] == values[i]:
            j += 1
        if keep is None or keep(values[i]):
            out.append((i, j, values[i]))
        i = j + 1
    return out
