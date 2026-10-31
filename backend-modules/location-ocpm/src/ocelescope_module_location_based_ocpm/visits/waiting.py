"""Processing operations, storage removals and the timed pieces of visits: waiting, storage and remaining time
(working doc `claude_notes/excursions-and-visit-sequences.md`, Part C with C.6, decided by Nina on 2026-10-31;
section "Waiting Times" of `overview/Single Level Visit Mappings.md`).

Inputs: processing operations P ⊆ E (a separate input in the concept; here the transformation events T are
used if no P is given; P ∩ M ≠ ∅ is allowed) and storage units W ⊆ L (optional; none = no storage removals).

Let ν = (hu, hl, σ) be a visit with hl ∈ HL, σ = otrace(hu)[i:k], x the position of e_out(ν) (x = k + 1, or
x = k if the trace ends with σ), and loc_j = loc((e_j, hu)). Visits at ⊥ have no pieces.
- **Processing positions** Q(ν) = {j ∈ {i, ..., k} | e_j ∈ P and hat-hl((e_j, hu)) = hl}: only processing at hl
  counts (one during an excursion counts for the visit to its own location). Since loc is the location
  after the event, a processing movement from hl to hl' is at hl'. Processing on a vehicle mapped into hl
  counts.
- **Storage removals** X_W(ν) = {j ∈ {i+1, ..., k} | loc_{j-1} ∈ W and loc_j ∉ W}: the events that take hu
  out of a storage unit, anywhere (also outside hl, during an excursion; Nina 2026-10-31). A move between
  two storage units is no removal; ⊥ after a storage unit counts as a removal (loc_j ∉ W).
- **Clock events** c_0 = i < c_1 < ... < c_s: the positions in {i} ∪ Q(ν) ∪ X_W(ν), followed by c_{s+1} = x.
- The **piece** ending at c_l (l = 1, ..., s + 1) lasts time(e_{c_l}) - time(e_{c_{l-1}}) and is labelled by its
  end: "storage" if c_l ∈ X_W(ν), "waiting" if c_l ∈ Q(ν) \\ X_W(ν), "remaining" if l = s + 1.
  Every processing operation gets one waiting time: a processing operation at the entry or one that is
  itself a storage removal gets a waiting time of 0 (an extra piece of length 0).
- waiting + storage + remaining time = d, the visit duration. With W = ∅ this is the earlier version (C.1).

The steps, each a function of its own (eager and lazy polars frames alike):
1. `add_processing`: is_processing_event (e ∈ P) and is_processing (e ∈ P at the visit's hl).
2. `add_storage_removals`: is_storage_removal.
3. `time_pieces`: one row per piece with its label and duration.
4. `waiting_times`: the waiting pieces only (one per processing operation).
5. `waiting_summary`: per visit the number of processing operations and storage removals, and the total
   waiting, storage and remaining time.
"""

from collections.abc import Collection

import polars as pl

from ..derivation import columns as c
from . import columns as v
from .context import Frame

#: Piece labels.
WAITING = "waiting"
STORAGE = "storage"
REMAINING = "remaining"

#: Columns of the pieces frame (one row per piece).
#: Number of the piece within its visit (1, 2, ...).
PIECE = "piece"
START_POSITION, END_POSITION = "start_position", "end_position"
START_EVENT, END_EVENT = "start_event", "end_event"
START_TIME, END_TIME = "start_time", "end_time"
LABEL = "label"
PIECE_DURATION = "piece_duration"

#: Columns of the waiting summary (one row per visit).
N_PROCESSING = "n_processing"
N_STORAGE_REMOVALS = "n_storage_removals"
TOTAL_WAITING_TIME = "total_waiting_time"
TOTAL_STORAGE_TIME = "total_storage_time"
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


def add_storage_removals(
    visit_relations: Frame, storage_units: Collection[str] = (), location: str = "loc"
) -> Frame:
    """Add is_storage_removal: the relation takes the handling unit out of a storage unit.

    A relation at position j > i (not the first one of the visit) is a storage removal iff the previous
    relation of the handling unit is in a storage unit and this one is not: loc_{j-1} ∈ W and loc_j ∉ W.
    The storage unit may lie outside the visit's high-level location (during an excursion). False at ⊥ visits.

    Args:
        visit_relations: Output of `maximal.visit_relations` (columns visit_id, position, first_position,
            visit_high_level and `location`).
        storage_units: The set W; empty = no removals.
        location: Column of loc (null = ⊥, which is not a storage unit).

    Returns:
        Frame: `visit_relations` with the column is_storage_removal.
    """
    in_w = pl.col(location).is_in(list(storage_units)).fill_null(False)
    previous_in_w = in_w.shift(1).over(v.VISIT_ID, order_by=v.POSITION)
    removal = (
        (pl.col(v.POSITION) > pl.col(v.FIRST_POSITION))
        & previous_in_w.fill_null(False)
        & ~in_w
        & pl.col(v.VISIT_HIGH_LEVEL).is_not_null()
    )
    return visit_relations.with_columns(removal.alias(v.IS_STORAGE_REMOVAL))


def time_pieces(visit_relations: Frame, visits: Frame) -> Frame:
    """One row per piece of a visit between two consecutive clock events, labelled by the event ending it.

    How it works:
    - the clock events of a visit are its entry, its processing positions and its storage removals (rows of
      `visit_relations`), followed by its exit e_out (a row from `visits`), in trace order;
    - each clock event after the entry ends a piece from the previous clock event; the label is "storage"
      for a removal, "waiting" for a processing operation, "remaining" for the exit;
    - a processing operation at the entry, or one that is itself a removal, also gets a waiting piece of
      length 0 (so every processing operation has exactly one waiting time).

    Args:
        visit_relations: Output of `add_processing` and `add_storage_removals`.
        visits: One row per visit with columns visit_id, hu, high_level, last_position, exit_event,
            exit_time, ends_trace (e.g. `maximal.maximal_visits`).

    Returns:
        Frame: Columns visit_id, hu, visit_high_level, piece, start_position, end_position, start_event,
        end_event, start_time, end_time, label, piece_duration; sorted by visit_id and piece. Visits at ⊥
        have no rows.
    """
    is_entry = pl.col(v.POSITION) == pl.col(v.FIRST_POSITION)
    clock = visit_relations.filter(
        pl.col(v.VISIT_HIGH_LEVEL).is_not_null()
        & (is_entry | pl.col(v.IS_PROCESSING) | pl.col(v.IS_STORAGE_REMOVAL))
    ).select(
        v.VISIT_ID,
        c.HU,
        v.VISIT_HIGH_LEVEL,
        v.POSITION,
        c.EVENT,
        c.TIME,
        is_entry.alias("_entry"),
        pl.col(v.IS_PROCESSING).alias("_processing"),
        pl.col(v.IS_STORAGE_REMOVAL).alias("_removal"),
        pl.lit(0, dtype=pl.Int64).alias("_order"),
    )
    exits = visits.filter(pl.col(v.HIGH_LEVEL).is_not_null()).select(
        v.VISIT_ID,
        c.HU,
        pl.col(v.HIGH_LEVEL).alias(v.VISIT_HIGH_LEVEL),
        (pl.col(v.LAST_POSITION) + (~pl.col(v.ENDS_TRACE)).cast(pl.Int64)).alias(v.POSITION),
        pl.col(v.EXIT_EVENT).alias(c.EVENT),
        pl.col(v.EXIT_TIME).alias(c.TIME),
        pl.lit(False).alias("_entry"),
        pl.lit(False).alias("_processing"),
        pl.lit(False).alias("_removal"),
        # The exit comes after a clock event at the same position (trace ends with the visit).
        pl.lit(1, dtype=pl.Int64).alias("_order"),
    )
    marks = pl.concat([clock, exits.with_columns(pl.col(v.POSITION).cast(pl.Int64))], how="vertical_relaxed")
    marks = marks.sort(v.VISIT_ID, v.POSITION, "_order").with_columns(
        pl.col(v.POSITION).shift(1).over(v.VISIT_ID).alias(START_POSITION),
        pl.col(c.EVENT).shift(1).over(v.VISIT_ID).alias(START_EVENT),
        pl.col(c.TIME).shift(1).over(v.VISIT_ID).alias(START_TIME),
    )
    label = (
        pl.when(pl.col("_order") == 1)
        .then(pl.lit(REMAINING))
        .when(pl.col("_removal"))
        .then(pl.lit(STORAGE))
        .otherwise(pl.lit(WAITING))
    )
    # Pieces ending at a clock event after the entry.
    ending = marks.filter(~pl.col("_entry") | (pl.col("_order") == 1)).with_columns(
        label.alias(LABEL)
    )
    # Zero waiting pieces for processing at the entry or at a removal.
    zero = marks.filter(
        (pl.col("_order") == 0) & pl.col("_processing") & (pl.col("_entry") | pl.col("_removal"))
    ).with_columns(
        pl.col(v.POSITION).alias(START_POSITION),
        pl.col(c.EVENT).alias(START_EVENT),
        pl.col(c.TIME).alias(START_TIME),
        pl.lit(WAITING).alias(LABEL),
        # A zero piece comes after the storage piece ending at the same removal.
        pl.lit(0.5).alias("_sub"),
    )
    pieces = pl.concat(
        [ending.with_columns(pl.lit(0.0).alias("_sub")), zero], how="vertical_relaxed"
    )
    return (
        pieces.sort(v.VISIT_ID, v.POSITION, "_order", "_sub")
        .with_columns(
            (pl.int_range(pl.len()).over(v.VISIT_ID) + 1).cast(pl.Int64).alias(PIECE),
            (pl.col(c.TIME) - pl.col(START_TIME)).alias(PIECE_DURATION),
        )
        .select(
            v.VISIT_ID,
            c.HU,
            v.VISIT_HIGH_LEVEL,
            PIECE,
            START_POSITION,
            pl.col(v.POSITION).alias(END_POSITION),
            START_EVENT,
            pl.col(c.EVENT).alias(END_EVENT),
            START_TIME,
            pl.col(c.TIME).alias(END_TIME),
            LABEL,
            PIECE_DURATION,
        )
        .sort(v.VISIT_ID, PIECE)
    )


def waiting_times(pieces: Frame) -> Frame:
    """The waiting times: the pieces labelled "waiting", one per processing operation of a visit.

    Args:
        pieces: Output of `time_pieces`.

    Returns:
        Frame: The waiting pieces; end_event is the processing operation, start_event the clock event its
        waiting time starts at (entry, previous processing operation or storage removal).
    """
    return pieces.filter(pl.col(LABEL) == WAITING)


def waiting_summary(visits: Frame, pieces: Frame) -> Frame:
    """Per visit: number of processing operations and storage removals, total waiting time, total storage
    time and remaining time; they add up to the visit duration. All null for visits at ⊥.

    Args:
        visits: One row per visit with columns visit_id, high_level, entry_time, exit_time.
        pieces: Output of `time_pieces`.

    Returns:
        Frame: Columns visit_id, n_processing, n_storage_removals, total_waiting_time, total_storage_time,
        remaining_time; sorted by visit_id.
    """
    zero = pl.col(v.EXIT_TIME) - pl.col(v.EXIT_TIME)  # zero duration in the frame's time unit

    def total(label: str) -> pl.Expr:
        """Sum of the piece durations with this label."""
        return pl.col(PIECE_DURATION).filter(pl.col(LABEL) == label).sum()

    per_visit = pieces.group_by(v.VISIT_ID).agg(
        (pl.col(LABEL) == WAITING).sum().cast(pl.Int64).alias(N_PROCESSING),
        (pl.col(LABEL) == STORAGE).sum().cast(pl.Int64).alias(N_STORAGE_REMOVALS),
        total(WAITING).alias(TOTAL_WAITING_TIME),
        total(STORAGE).alias(TOTAL_STORAGE_TIME),
        total(REMAINING).alias(REMAINING_TIME),
    )
    columns = (N_PROCESSING, N_STORAGE_REMOVALS, TOTAL_WAITING_TIME, TOTAL_STORAGE_TIME, REMAINING_TIME)
    return (
        visits.select(v.VISIT_ID, v.HIGH_LEVEL, v.EXIT_TIME)
        .join(per_visit, on=v.VISIT_ID, how="left")
        .with_columns(
            pl.when(pl.col(v.HIGH_LEVEL).is_not_null())
            .then(pl.col(col).fill_null(0) if col.startswith("n_") else pl.col(col).fill_null(zero))
            .alias(col)
            for col in columns
        )
        .select(v.VISIT_ID, *columns)
        .sort(v.VISIT_ID)
    )
