"""The visit overview (concept note `overview/concepts/Visit Mappings.md`, "Visit Overview").

Aggregations over the per-visit results, for any set of visits:
- `transfer_relations`: the relations of every transfer μ_j, with their dwell times;
- `transfer_statistics`: per visit and transfer category: number, total / mean / min / max / median
  duration d(μ_j) and mean / min / max / median length |μ_j|;
- `transfer_targets`: per visit, category and target: for vehicle shifts the vehicles, for external shifts the
  external high-level locations (⊥ as "⊥"): number of transfers going to it, relations at it and time spent
  at it (total, and min / max / median / mean per transfer);
- `processing_statistics`: per visit and processing activity: number of operations and their waiting times
  (total, min / max / median / mean);
- `visit_overview`: one row per visit with the counts, properties, durations, shifts and waiting times of
  the overview list, joined from the frames above.
"""

from collections.abc import Sequence

import polars as pl

from ..derivation import columns as c
from . import columns as v
from .context import Frame
from .dwell import DWELL_TIME
from .excursions import BOTTOM
from .sequence import expand_intervals
from .shifts import (
    CATEGORY,
    EXTERNAL_SHIFT,
    FROM_POSITION,
    TO_POSITION,
    TRANSFER_DURATION,
    TRANSFER_LENGTH,
    VEHICLE_SHIFT,
    J,
)

#: Columns of `transfer_targets`.
TARGET = "target"
N_TRANSFERS = "n_transfers"

#: Statistics used for durations and counts.
STATISTICS = ("total", "mean", "min", "max", "median")


def _stats(
    column: str, prefix: str, which: Sequence[str] = STATISTICS
) -> list[pl.Expr]:
    """Aggregations total / mean / min / max / median of a column, named <prefix>_<statistic>."""
    functions = {
        "total": lambda e: e.sum(),
        "mean": lambda e: e.mean(),
        "min": lambda e: e.min(),
        "max": lambda e: e.max(),
        "median": lambda e: e.median(),
    }
    return [functions[s](pl.col(column)).alias(f"{prefix}_{s}") for s in which]


def transfer_relations(dwell_relations: Frame, transfers_frame: Frame) -> Frame:
    """The relations of every non-empty transfer μ_j (strictly between its two stops).

    Args:
        dwell_relations: Visit relations with dwell times (`dwell.add_dwell_times`, after `shifts.add_stops`).
        transfers_frame: Output of `shifts.transfers`.

    Returns:
        Frame: One row per transfer and relation: visit_id, j, category, position and the relation columns.
    """
    inner = transfers_frame.filter(pl.col(TRANSFER_LENGTH) > 0).select(
        v.VISIT_ID,
        J,
        CATEGORY,
        (pl.col(FROM_POSITION) + 1).alias("_first"),
        (pl.col(TO_POSITION) - 1).alias("_last"),
    )
    return (
        expand_intervals(inner, "_first", "_last")
        .drop("_first", "_last")
        .join(dwell_relations, on=[v.VISIT_ID, v.POSITION])
        .sort(v.VISIT_ID, J, v.POSITION)
    )


def transfer_statistics(transfers_frame: Frame) -> Frame:
    """Per visit and category: number of transfers, their durations and lengths.

    Args:
        transfers_frame: Output of `shifts.transfers`.

    Returns:
        Frame: visit_id, category, n_transfers, duration_total / _mean / _min / _max / _median,
        length_mean / _min / _max / _median.
    """
    return (
        transfers_frame.group_by(v.VISIT_ID, CATEGORY)
        .agg(
            pl.len().cast(pl.Int64).alias(N_TRANSFERS),
            *_stats(TRANSFER_DURATION, "duration"),
            *_stats(TRANSFER_LENGTH, "length", ("mean", "min", "max", "median")),
        )
        .sort(v.VISIT_ID, CATEGORY)
    )


def transfer_targets(
    transfer_relations_frame: Frame,
    location: str = "loc",
    categories: Sequence[str] = (VEHICLE_SHIFT, EXTERNAL_SHIFT),
) -> Frame:
    """Per visit, category and target: transfers going to it, relations at it and time spent at it.

    The target of a relation in a vehicle shift is its vehicle (loc); in an external shift its high-level
    location (⊥ as "⊥"). A transfer goes to a target if it has at least one relation at it.

    Args:
        transfer_relations_frame: Output of `transfer_relations`.
        location: Column of loc.
        categories: Transfer categories to include.

    Returns:
        Frame: visit_id, category, target, n_transfers, relations_total / _min / _max / _median / _mean (per
        transfer), time_total / _min / _max / _median / _mean (per transfer); sorted by visit_id, category,
        target.
    """
    target = (
        pl.when(pl.col(CATEGORY) == VEHICLE_SHIFT)
        .then(pl.col(location))
        .otherwise(pl.col(v.HIGH_LEVEL))
        .fill_null(BOTTOM)
    )
    per_transfer = (
        transfer_relations_frame.filter(pl.col(CATEGORY).is_in(list(categories)))
        .with_columns(target.alias(TARGET))
        .group_by(v.VISIT_ID, CATEGORY, J, TARGET)
        .agg(
            pl.len().cast(pl.Int64).alias("_n"), pl.col(DWELL_TIME).sum().alias("_time")
        )
    )
    return (
        per_transfer.group_by(v.VISIT_ID, CATEGORY, TARGET)
        .agg(
            pl.len().cast(pl.Int64).alias(N_TRANSFERS),
            *_stats("_n", "relations"),
            *_stats("_time", "time"),
        )
        .sort(v.VISIT_ID, CATEGORY, TARGET)
    )


def processing_statistics(
    waiting_times: Frame, activity: str = "end_activity"
) -> Frame:
    """Per visit and processing activity: number of operations and their waiting times.

    Args:
        waiting_times: The waiting pieces (`waiting_times.waiting.waiting_times`), one per processing
            operation, with visit_id, end_activity and piece_duration.
        activity: Column with the activity of the processing operation.

    Returns:
        Frame: visit_id, activity, n_operations, waiting_total / _min / _max / _median / _mean.
    """
    return (
        waiting_times.group_by(v.VISIT_ID, activity)
        .agg(
            pl.len().cast(pl.Int64).alias("n_operations"),
            *_stats("piece_duration", "waiting"),
        )
        .rename({activity: c.ACTIVITY})
        .sort(v.VISIT_ID, c.ACTIVITY)
    )


def _wide_transfer_statistics(
    statistics: Frame, categories: Sequence[str]
) -> list[Frame]:
    """`transfer_statistics` of some categories as columns <category>_<statistic> (spaces as "_")."""
    parts = []
    for category in categories:
        prefix = category.replace(" ", "_")
        part = statistics.filter(pl.col(CATEGORY) == category).drop(CATEGORY)
        names = [n for n in part.collect_schema().names() if n != v.VISIT_ID]
        parts.append(part.rename({n: f"{prefix}_{n}" for n in names}))
    return parts


def visit_overview(
    visits: Frame,
    inside_outside: Frame | None = None,
    statistics: Frame | None = None,
    waiting_summary: Frame | None = None,
    processing: Frame | None = None,
    categories: Sequence[str] = (VEHICLE_SHIFT, EXTERNAL_SHIFT),
) -> Frame:
    """One row per visit with everything of the overview list.

    Args:
        visits: The visits with their properties and shift summary (e.g. `VisitAnalysis.visits`).
        inside_outside: Output of `dwell.time_inside_outside`.
        statistics: Output of `transfer_statistics`; the categories in `categories` become columns.
        waiting_summary: The waiting summary (`waiting_times.waiting.waiting_summary`).
        processing: Output of `processing_statistics` (gives n_processing_activities).
        categories: Transfer categories whose statistics are added as columns.

    Returns:
        Frame: `visits` with the further columns (left joins; missing parts are left out), sorted by visit_id.
    """
    out = visits
    if inside_outside is not None:
        out = out.join(inside_outside, on=v.VISIT_ID, how="left")
    if statistics is not None:
        for part in _wide_transfer_statistics(statistics, categories):
            out = out.join(part, on=v.VISIT_ID, how="left")
    if waiting_summary is not None:
        out = out.join(waiting_summary, on=v.VISIT_ID, how="left")
    if processing is not None:
        activities = processing.group_by(v.VISIT_ID).agg(
            pl.col(c.ACTIVITY)
            .n_unique()
            .cast(pl.Int64)
            .alias("n_processing_activities")
        )
        out = out.join(activities, on=v.VISIT_ID, how="left").with_columns(
            pl.when(pl.col(v.HIGH_LEVEL).is_not_null())
            .then(pl.col("n_processing_activities").fill_null(0))
            .alias("n_processing_activities")
        )
    return out.sort(v.VISIT_ID)
