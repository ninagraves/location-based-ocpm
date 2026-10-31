"""Processing operations and waiting times of visits (working doc `claude_notes/excursions-and-visit-sequences.md`,
Part C, decided by Nina on 2026-10-31; section "Waiting Times" of `overview/Single Level Visit Mappings.md`).

Input: a set of processing operations P ⊆ E (in the concept a separate input; here the transformation events
T are used if no P is given). Processing operations may be movements (P ∩ M ≠ ∅ is allowed).

Let ν = (hu, hl, σ) be a visit with hl ∈ HL and σ = otrace(hu)[i:k] (visits at ⊥ have no waiting times).
- The **processing positions** q_1 < ... < q_r of ν are the positions j of σ with e_j ∈ P and hat-hl((e_j, hu)) = hl,
  i.e. only processing operations at hl count (one during an excursion counts for the visit to its own location).
  Since loc is the location after the event, a processing movement from hl to hl' is at hl': it is the
  entry of the visit to hl' (w_1 = 0 there) and the exit event of the visit to hl.
  A processing operation on a vehicle mapped into hl counts (it is at hl).
- With q_0 = i (the entry), the **waiting time** before the j-th processing operation is
  w_j = time(e_{q_j}) - time(e_{q_{j-1}}), j = 1, ..., r; all of them are kept.
  If the entry event itself is a processing operation, q_1 = q_0 = i and w_1 = 0.
- The **remaining time** is w_rem = time(e_out) - time(e_{q_r}) (q_r = i if r = 0).
- Σ_j w_j + w_rem = d, the visit duration.

The steps, each a function of its own (eager and lazy polars frames alike):
1. `add_processing`: is_processing_event (e ∈ P) and is_processing (e ∈ P at the visit's hl).
2. `waiting_times`: one row per processing position with its waiting time.
3. `waiting_summary`: per visit r, Σ_j w_j and w_rem.
"""

from collections.abc import Collection

import polars as pl

from ..derivation import columns as c
from . import columns as v
from .context import Frame

#: Columns of the waiting times frame (one row per processing position q_j of a visit).
J = "j"
#: Event and time of the start of the waiting time: e_{q_{j-1}} (the entry, or the previous processing).
START_EVENT = "start_event"
START_TIME = "start_time"
WAITING_TIME = "waiting_time"

#: Columns of the waiting summary (one row per visit).
N_PROCESSING = "n_processing"
TOTAL_WAITING_TIME = "total_waiting_time"
#: Event and time of e_{q_r} (the last processing operation, or the entry if r = 0).
LAST_PROCESSING_EVENT = "last_processing_event"
REMAINING_TIME = "remaining_time"


def add_processing(
    visit_relations: Frame, processing: Collection[str] | None = None
) -> Frame:
    """Add is_processing_event (e ∈ P) and is_processing (e ∈ P and at the visit's high-level location).

    Args:
        visit_relations: Output of `maximal.visit_relations` (columns event, visit_high_level, at_location;
            and is_transformation if `processing` is None).
        processing: The processing operations P as event ids; None = the transformation events T (column
            is_transformation), the implementation default decided by Nina (2026-10-31).

    Returns:
        Frame: `visit_relations` with the columns is_processing_event and is_processing (false at ⊥ visits).
    """
    if processing is None:
        in_p = pl.col(c.IS_TRANSFORMATION).fill_null(False)
    else:
        in_p = pl.col(c.EVENT).is_in(list(processing))
    return visit_relations.with_columns(in_p.alias(v.IS_PROCESSING_EVENT)).with_columns(
        (
            pl.col(v.IS_PROCESSING_EVENT)
            & pl.col(v.AT_LOCATION)
            & pl.col(v.VISIT_HIGH_LEVEL).is_not_null()
        ).alias(v.IS_PROCESSING)
    )


def waiting_times(visit_relations: Frame) -> Frame:
    """One row per processing position q_j of a visit, with its waiting time w_j.

    How it works: the "marks" of a visit are its entry (position = first_position) and its processing
    positions, in trace order. The waiting time of a processing position starts at the previous mark,
    i.e. at the entry or at the previous processing operation; if the entry is itself a processing
    operation, it starts at itself (w_1 = 0).

    Args:
        visit_relations: Output of `add_processing` (columns visit_id, hu, visit_high_level, position,
            first_position, event, time, is_processing).

    Returns:
        Frame: Columns visit_id, hu, visit_high_level, j, position, event, time, start_event, start_time,
        waiting_time; sorted by visit_id and j. Visits without processing operations have no rows.
    """
    is_entry = pl.col(v.POSITION) == pl.col(v.FIRST_POSITION)
    marks = visit_relations.filter(is_entry | pl.col(v.IS_PROCESSING)).sort(
        v.VISIT_ID, v.POSITION
    )

    def previous(column: str) -> pl.Expr:
        """`column` of the previous mark of the same visit."""
        return pl.col(column).shift(1).over(v.VISIT_ID)

    return (
        marks.with_columns(
            pl.when(is_entry).then(pl.col(c.EVENT)).otherwise(previous(c.EVENT)).alias(START_EVENT),
            pl.when(is_entry).then(pl.col(c.TIME)).otherwise(previous(c.TIME)).alias(START_TIME),
        )
        .filter(pl.col(v.IS_PROCESSING))
        .with_columns(
            (pl.int_range(pl.len()).over(v.VISIT_ID) + 1).cast(pl.Int64).alias(J),
            (pl.col(c.TIME) - pl.col(START_TIME)).alias(WAITING_TIME),
        )
        .select(
            v.VISIT_ID,
            c.HU,
            v.VISIT_HIGH_LEVEL,
            J,
            v.POSITION,
            c.EVENT,
            c.TIME,
            START_EVENT,
            START_TIME,
            WAITING_TIME,
        )
        .sort(v.VISIT_ID, J)
    )


def waiting_summary(visits: Frame, waiting: Frame) -> Frame:
    """Per visit: number of processing operations r, total waiting time Σ_j w_j and remaining time w_rem.

    w_rem = time(e_out) - time(e_{q_r}), with e_{q_r} the last processing operation of the visit, or its
    entry event if it has none (then the whole duration is remaining time).
    All three are null for visits at ⊥ (waiting times are only defined for hl ∈ HL).

    Args:
        visits: One row per visit with columns visit_id, high_level, first_event, entry_time, exit_time
            (e.g. `maximal.maximal_visits`).
        waiting: Output of `waiting_times`.

    Returns:
        Frame: Columns visit_id, n_processing, total_waiting_time, last_processing_event, remaining_time;
        sorted by visit_id.
    """
    per_visit = waiting.group_by(v.VISIT_ID).agg(
        pl.len().cast(pl.Int64).alias(N_PROCESSING),
        pl.col(WAITING_TIME).sum().alias(TOTAL_WAITING_TIME),
        pl.col(c.EVENT).sort_by(J).last().alias(LAST_PROCESSING_EVENT),
        pl.col(c.TIME).sort_by(J).last().alias("_last_time"),
    )
    has_location = pl.col(v.HIGH_LEVEL).is_not_null()
    no_processing = pl.col(N_PROCESSING).is_null()
    return (
        visits.select(v.VISIT_ID, v.HIGH_LEVEL, v.FIRST_EVENT, v.ENTRY_TIME, v.EXIT_TIME)
        .join(per_visit, on=v.VISIT_ID, how="left")
        .with_columns(
            pl.col(N_PROCESSING).fill_null(0),
            # Zero duration in the time unit of the frame for visits without processing operations.
            pl.when(no_processing)
            .then(pl.col(v.EXIT_TIME) - pl.col(v.EXIT_TIME))
            .otherwise(pl.col(TOTAL_WAITING_TIME))
            .alias(TOTAL_WAITING_TIME),
            pl.col(LAST_PROCESSING_EVENT).fill_null(pl.col(v.FIRST_EVENT)),
            (pl.col(v.EXIT_TIME) - pl.col("_last_time").fill_null(pl.col(v.ENTRY_TIME))).alias(
                REMAINING_TIME
            ),
        )
        .with_columns(
            pl.when(has_location).then(pl.col(col)).alias(col)
            for col in (N_PROCESSING, TOTAL_WAITING_TIME, LAST_PROCESSING_EVENT, REMAINING_TIME)
        )
        .select(
            v.VISIT_ID, N_PROCESSING, TOTAL_WAITING_TIME, LAST_PROCESSING_EVENT, REMAINING_TIME
        )
        .sort(v.VISIT_ID)
    )
