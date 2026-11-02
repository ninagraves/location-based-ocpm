"""Dwell times and the time spent at locations during a visit (concept note
`overview/concepts/Visit Mappings.md`, "identifying shifts", related notations).

For a visit ν = (hu, hl, σ) with n = |σ|:
- dwell time δ_ν(i) = time(σ[i+1]) - time(σ[i]) for i < n, and δ_ν(n) = time(e_out(ν)) - time(σ[n]); the
  handling unit is at loc(σ[i]) for δ_ν(i) (loc is the location after an event). Σ_i δ_ν(i) = d(ν).
- time spent at a low-level location x: d_x(ν) = Σ of δ_ν(i) over the relations at x; at a high-level
  location hl': d_hl'(ν) likewise over the relations with hat-hl = hl'.
- time inside hl: d_hl(ν); time outside: d(ν) - d_hl(ν) (time at ⊥ counts as outside).
Restricted to a transfer μ_j, the same sums give the time at a vehicle or an external high-level location
per transfer (`overview.transfer_targets`).

Works for any set of visits (maximal, mapping set, hand-written) given its visit relations.
"""

import polars as pl

from ..derivation import columns as c
from . import columns as v
from .context import Frame
from .sequence import at_positions

#: Column of the visit relations: dwell time δ_ν(i).
DWELL_TIME = "dwell_time"
#: Columns of `time_spent` and `time_inside_outside`.
TIME_AT = "time_at"
N_RELATIONS_AT = "n_relations_at"
TIME_INSIDE = "time_inside"
TIME_OUTSIDE = "time_outside"


def add_dwell_times(visit_relations: Frame, visits: Frame) -> Frame:
    """Add δ_ν(i) to every row of the visit relations.

    How it works: the time of the next row of the same visit (`sequence.at_positions` with offset 1); for
    the last row the exit time of the visit.

    Args:
        visit_relations: Output of `maximal.visit_relations` (visit_id, position, time, ...).
        visits: The visits with visit_id and exit_time (e.g. `maximal.visit_table`).

    Returns:
        Frame: `visit_relations` with the column dwell_time (duration), sorted by visit_id and position.
    """
    nxt = at_positions(
        visit_relations,
        visit_relations,
        v.POSITION,
        {c.TIME: "_next_time"},
        group=v.VISIT_ID,
        offset=1,
    )
    return (
        nxt.join(
            visits.select(v.VISIT_ID, pl.col(v.EXIT_TIME).alias("_exit")),
            on=v.VISIT_ID,
            how="left",
        )
        .with_columns(
            (pl.col("_next_time").fill_null(pl.col("_exit")) - pl.col(c.TIME)).alias(
                DWELL_TIME
            )
        )
        .drop("_next_time", "_exit")
        .sort(v.VISIT_ID, v.POSITION)
    )


def time_spent(dwell_relations: Frame, by: str = "loc") -> Frame:
    """Time spent per visit and location: d_x(ν) (by loc) or d_hl'(ν) (by high_level).

    Args:
        dwell_relations: Output of `add_dwell_times`.
        by: Location column, e.g. the loc column (low-level) or "high_level"; null = ⊥.

    Returns:
        Frame: visit_id, hu, `by`, n_relations_at, time_at; sorted by visit_id and time_at (largest first).
    """
    return (
        dwell_relations.group_by(v.VISIT_ID, c.HU, by)
        .agg(
            pl.len().cast(pl.Int64).alias(N_RELATIONS_AT),
            pl.col(DWELL_TIME).sum().alias(TIME_AT),
        )
        .sort(v.VISIT_ID, TIME_AT, descending=[False, True])
    )


def time_inside_outside(dwell_relations: Frame, visits: Frame) -> Frame:
    """Per visit: time inside hl, d_hl(ν), and time outside, d(ν) - d_hl(ν).

    Args:
        dwell_relations: Output of `add_dwell_times` (with at_location).
        visits: The visits with visit_id and duration.

    Returns:
        Frame: visit_id, time_inside, time_outside.
    """
    inside = dwell_relations.group_by(v.VISIT_ID).agg(
        pl.col(DWELL_TIME).filter(pl.col(v.AT_LOCATION)).sum().alias(TIME_INSIDE)
    )
    return (
        visits.select(v.VISIT_ID, v.DURATION)
        .join(inside, on=v.VISIT_ID, how="left")
        .with_columns(
            pl.col(TIME_INSIDE).fill_null(pl.col(v.DURATION) - pl.col(v.DURATION))
        )
        .with_columns((pl.col(v.DURATION) - pl.col(TIME_INSIDE)).alias(TIME_OUTSIDE))
        .select(v.VISIT_ID, TIME_INSIDE, TIME_OUTSIDE)
        .sort(v.VISIT_ID)
    )
