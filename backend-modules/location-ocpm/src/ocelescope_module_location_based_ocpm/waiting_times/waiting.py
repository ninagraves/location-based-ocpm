"""Processing operations, storage removals and the timed pieces of a scope: waiting, storage and remaining time
(section "Waiting Times" of `overview/Single Level Visit Mappings.md`, design decisions DD-W1 to DD-W7).

Inputs: processing operations P ⊆ E (a separate input in the concept; here the transformation events T are
used if no P is given; P ∩ M ≠ ∅ is allowed) and storage units W ⊆ L (optional; none = no storage removals).

The **scope** ν = (hu, hl, σ) the waiting times are measured in is either a visit with hl ∈ HL, or, if no
visits are given (DD-W6), the whole trace of a handling unit (σ = otrace(hu), no hl; `scopes.py`).
Let σ = otrace(hu)[i:k] (ordered by seq, AS4), x the position of e_out(ν) (x = k + 1, or x = k if the trace
ends with σ; for a whole trace x = k), and loc_j = loc((e_j, hu)). Visits at ⊥ are no scopes (DD-W7).
- **Processing positions** Q(ν) = {j ∈ {i, ..., k} | e_j ∈ P and hat-hl((e_j, hu)) = hl}: only processing at hl
  counts (one during an excursion counts for the visit to its own location). Since loc is the location
  after the event, a processing movement from hl to hl' is at hl'. Processing on a vehicle mapped into hl
  counts. For a whole trace, every located processing operation counts (loc_j ≠ ⊥, as DD-W7).
- **Storage removals** X_W(ν) = {j ∈ {i+1, ..., k} | loc_{j-1} ∈ W and loc_j ∉ W}: the events that take hu
  out of a storage unit, anywhere (also outside hl, during an excursion; Nina 2026-10-31). Option
  `outside_storage_resets=False` counts only storage units inside hl (agg(loc_{j-1}) = hl). A move between
  two storage units is no removal; ⊥ after a storage unit counts as a removal (loc_j ∉ W).
- **Clock events** c_0 = i < c_1 < ... < c_s: the positions in {i} ∪ Q(ν) ∪ X_W(ν), followed by c_{s+1} = x.
- The **piece** ending at c_l (l = 1, ..., s + 1) lasts time(e_{c_l}) - time(e_{c_{l-1}}) and is labelled by its
  end: "waiting" if c_l ∈ Q(ν), "storage" if c_l ∈ X_W(ν) \\ Q(ν), "remaining" if l = s + 1.
  Every processing operation gets one waiting time; one at the entry gets 0 (an extra piece of length 0).
- **Processing operations that are themselves storage removals** (c_l ∈ Q(ν) ∩ X_W(ν)): by the concept
  (Nina, 2026-11-01) the piece before them is their waiting time, so it includes the time until and in
  storage. Option `zero_wait_at_removal=True` gives the earlier behaviour instead: that piece is storage
  time and the operation gets a waiting time of 0. Removals by other events reset the clock in both modes.
- **Removal at the same timestamp as a processing operation** (DD-W4, Nina 2026-11-01): by AS4 the
  removing movement comes first, so the processing operation waits 0. Option
  `skip_simultaneous_removal=True` skips such a removal instead (it is no clock event), so the processing
  operation waits from the clock event before it, including the storage time.
- **Timestamps are completion times** (DD-W3, Nina 2026-11-01): a waiting time contains the processing time
  of its own operation. A later processing-duration attribute would deduct the duration of that operation
  (not of the previous one) and flag negative waiting times.
- waiting + storage + remaining time = d, the duration of the scope. With W = ∅ (or without removals as clock
  events, DD-W5) there are only waiting and remaining pieces.

The steps, each a function of its own (eager and lazy polars frames alike):
0. `scopes.py`: the scopes and their relations (`visit_scopes` or `trace_scopes`, then `scope_relations`).
1. `add_processing`: is_processing_event (e ∈ P) and is_processing (e ∈ P at the visit's hl).
2. `add_storage_removals`: is_storage_removal.
3. `time_pieces`: one row per piece with its label and duration.
4. `waiting_times`: the waiting pieces only (one per processing operation).
5. `waiting_summary`: per visit the number of processing operations and storage removals, and the total
   waiting, storage and remaining time.
6. `simultaneous_processing`: flag (RQ5) for two processing operations of one handling unit at the same
   timestamp.
"""

from collections.abc import Collection

import polars as pl

from ..derivation import columns as c
from ..visits import columns as v
from ..visits.context import Frame
from ..visits.order import processing_flag

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
#: Activities of the start and end event of a piece (for a waiting piece, end_activity is the activity of
#: the processing operation the waiting time belongs to).
START_ACTIVITY, END_ACTIVITY = "start_activity", "end_activity"
LABEL = "label"
PIECE_DURATION = "piece_duration"

#: Columns of the waiting summary (one row per visit).
N_PROCESSING = "n_processing"
N_STORAGE_REMOVALS = "n_storage_removals"
TOTAL_WAITING_TIME = "total_waiting_time"
TOTAL_STORAGE_TIME = "total_storage_time"
REMAINING_TIME = "remaining_time"
#: Processing visit: Q(ν) ≠ ∅.
IS_PROCESSING_VISIT = "is_processing_visit"

#: Columns of the flag frame of `simultaneous_processing`.
EVENTS = "events"
N_EVENTS = "n_events"


def add_processing(
    visit_relations: Frame, processing: Collection[str] | None = None
) -> Frame:
    """Add is_processing_event (e ∈ P) and is_processing (e ∈ P and at the visit's high-level location).

    Args:
        visit_relations: Output of `scopes.scope_relations` (columns event, at_location; and
            is_transformation if `processing` is None).
        processing: The processing operations P as event ids; None = the transformation events T (column
            is_transformation), the implementation default decided by Nina (2026-10-31).

    Returns:
        Frame: `visit_relations` with the columns is_processing_event and is_processing (e ∈ P and the
        relation at the scope's hl; for a whole trace: located).
    """
    return visit_relations.with_columns(processing_flag(processing).alias(v.IS_PROCESSING_EVENT)).with_columns(
        (pl.col(v.IS_PROCESSING_EVENT) & pl.col(v.AT_LOCATION)).alias(v.IS_PROCESSING)
    )


def add_storage_removals(
    visit_relations: Frame,
    storage_units: Collection[str] = (),
    location: str = "loc",
    outside_storage_resets: bool = True,
) -> Frame:
    """Add is_storage_removal: the relation takes the handling unit out of a storage unit.

    A relation at position j > i (not the first one of the visit) is a storage removal iff the previous
    relation of the handling unit is in a storage unit and this one is not: loc_{j-1} ∈ W and loc_j ∉ W.
    By default (Nina's concept, 2026-10-31) the storage unit may lie outside the visit's high-level location
    (during an excursion). With `outside_storage_resets=False`, only storage units inside hl count, i.e.
    additionally agg(loc_{j-1}) = hl (DD-W2); for a whole trace (no hl) this option has no effect.

    Args:
        visit_relations: Output of `scopes.scope_relations` (columns visit_id, position, first_position,
            visit_high_level and `location`).
        storage_units: The set W; empty = no removals.
        location: Column of loc (null = ⊥, which is not a storage unit).
        outside_storage_resets: True (default, concept): removals from any storage unit count; False: only
            removals from storage units at the visit's high-level location (needs the column high_level).

    Returns:
        Frame: `visit_relations` with the column is_storage_removal.
    """
    in_w = pl.col(location).is_in(list(storage_units)).fill_null(False)
    previous_in_w = in_w.shift(1).over(v.VISIT_ID, order_by=v.POSITION)
    removal = (
        (pl.col(v.POSITION) > pl.col(v.FIRST_POSITION))
        & previous_in_w.fill_null(False)
        & ~in_w
    )
    if not outside_storage_resets:
        previous_hl = pl.col(v.HIGH_LEVEL).shift(1).over(v.VISIT_ID, order_by=v.POSITION)
        inside = pl.col(v.VISIT_HIGH_LEVEL).is_null() | (previous_hl == pl.col(v.VISIT_HIGH_LEVEL)).fill_null(False)
        removal = removal & inside
    return visit_relations.with_columns(removal.alias(v.IS_STORAGE_REMOVAL))


def time_pieces(
    visit_relations: Frame,
    visits: Frame,
    activity: str = c.ACTIVITY,
    zero_wait_at_removal: bool = False,
    skip_simultaneous_removal: bool = False,
    relations: Frame | None = None,
) -> Frame:
    """One row per piece of a visit between two consecutive clock events, labelled by the event ending it.

    How it works:
    - the clock events of a visit are its entry, its processing positions and its storage removals (rows of
      `visit_relations`), followed by its exit e_out (a row from `visits`), in trace order;
    - each clock event after the entry ends a piece from the previous clock event; the label is "waiting"
      for a processing operation, "storage" for a removal that is no processing operation, "remaining"
      for the exit;
    - a processing operation at the entry gets a waiting piece of length 0 (so every processing operation
      has exactly one waiting time);
    - with `zero_wait_at_removal`, a processing operation that is itself a removal ends a "storage" piece
      and gets an extra waiting piece of length 0 (the earlier behaviour);
    - the activities of the start and end event are looked up by (hu, event) in `relations` (or, if not
      given, in `visit_relations`, where an exit event outside every scope, e.g. into ⊥, has no activity),
      so waiting times can be grouped by the activity of their processing operation (Nina, 2026-10-31).

    Args:
        visit_relations: Output of `add_processing` and `add_storage_removals`.
        visits: The scopes: one row per visit with columns visit_id, hu, high_level, last_position,
            exit_event, exit_time, ends_trace (`scopes.visit_scopes` or `scopes.trace_scopes`).
        relations: All relations (one row per hu-event relation) to look up the activities; None = use
            `visit_relations`.
        activity: Column of the activity in `visit_relations`; if the column is missing, the activity
            columns are left out.
        zero_wait_at_removal: False (default, the concept since 2026-11-01): a processing operation that
            takes the handling unit out of a storage unit waits from the previous clock event, including
            the storage time. True: the time before it is storage time and its waiting time is 0.
        skip_simultaneous_removal: False (default, DD-W4, Nina 2026-11-01): a removal by another event at
            the same timestamp as the next processing operation resets the clock, so that operation waits
            0 (by AS4 the removing movement comes first). True: such a removal is skipped, i.e. it is no
            clock event, and the processing operation waits from the clock event before it (the time in
            storage becomes part of its waiting time).

    Returns:
        Frame: Columns visit_id, hu, visit_high_level, piece, start_position, end_position, start_event,
        end_event, start_activity, end_activity, start_time, end_time, label, piece_duration; sorted by visit_id
        and piece.
    """
    is_entry = pl.col(v.POSITION) == pl.col(v.FIRST_POSITION)
    clock = visit_relations.filter(is_entry | pl.col(v.IS_PROCESSING) | pl.col(v.IS_STORAGE_REMOVAL)).select(
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
    exits = visits.select(
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
    marks = marks.sort(v.VISIT_ID, v.POSITION, "_order")
    if skip_simultaneous_removal:
        # A removal (not itself processing, not the entry) directly followed by a processing operation at the
        # same timestamp is no clock event.
        next_processing = pl.col("_processing").shift(-1).over(v.VISIT_ID).fill_null(False)
        same_time = (pl.col(c.TIME).shift(-1).over(v.VISIT_ID) == pl.col(c.TIME)).fill_null(False)
        skipped = pl.col("_removal") & ~pl.col("_processing") & ~pl.col("_entry") & next_processing & same_time
        marks = marks.filter(~skipped)
    marks = marks.with_columns(
        pl.col(v.POSITION).shift(1).over(v.VISIT_ID).alias(START_POSITION),
        pl.col(c.EVENT).shift(1).over(v.VISIT_ID).alias(START_EVENT),
        pl.col(c.TIME).shift(1).over(v.VISIT_ID).alias(START_TIME),
    )
    label = (
        pl.when(pl.col("_order") == 1)
        .then(pl.lit(REMAINING))
        .when(pl.col("_removal") & (~pl.col("_processing") | pl.lit(zero_wait_at_removal)))
        .then(pl.lit(STORAGE))
        .otherwise(pl.lit(WAITING))
    )
    # Pieces ending at a clock event after the entry.
    ending = marks.filter(~pl.col("_entry") | (pl.col("_order") == 1)).with_columns(
        label.alias(LABEL)
    )
    # Zero waiting pieces for processing at the entry (and at a removal with `zero_wait_at_removal`).
    zero_at = pl.col("_entry") | (pl.col("_removal") & pl.lit(zero_wait_at_removal))
    zero = marks.filter((pl.col("_order") == 0) & pl.col("_processing") & zero_at).with_columns(
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
    out = (
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
    )
    lookup = visit_relations if relations is None else relations
    if activity in lookup.collect_schema().names():
        activities = lookup.select(c.HU, c.EVENT, activity).unique()
        for event_column, activity_column in ((START_EVENT, START_ACTIVITY), (END_EVENT, END_ACTIVITY)):
            out = out.join(
                activities.rename({c.EVENT: event_column, activity: activity_column}),
                on=[c.HU, event_column],
                how="left",
            )
        order = [v.VISIT_ID, c.HU, v.VISIT_HIGH_LEVEL, PIECE, START_POSITION, END_POSITION, START_EVENT,
                 END_EVENT, START_ACTIVITY, END_ACTIVITY, START_TIME, END_TIME, LABEL, PIECE_DURATION]
        out = out.select(order)
    return out.sort(v.VISIT_ID, PIECE)


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
    """Per scope: number of processing operations and storage removals, total waiting time, total storage
    time and remaining time (they add up to the duration), and whether it is a processing visit (Q(ν) ≠ ∅).

    Joined to all maximal visits (`visits.join(summary, on="visit_id", how="left")`), visits at ⊥ get null.

    Args:
        visits: The scopes, with columns visit_id and exit_time.
        pieces: Output of `time_pieces`.

    Returns:
        Frame: Columns visit_id, n_processing, n_storage_removals (removals that end a storage piece),
        total_waiting_time, total_storage_time, remaining_time, is_processing_visit; sorted by visit_id.
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
        visits.select(v.VISIT_ID, v.EXIT_TIME)
        .join(per_visit, on=v.VISIT_ID, how="left")
        .with_columns(
            (pl.col(col).fill_null(0) if col.startswith("n_") else pl.col(col).fill_null(zero)).alias(col)
            for col in columns
        )
        .with_columns((pl.col(N_PROCESSING) > 0).alias(IS_PROCESSING_VISIT))
        .select(v.VISIT_ID, *columns, IS_PROCESSING_VISIT)
        .sort(v.VISIT_ID)
    )


def simultaneous_processing(
    relations: Frame, processing: Collection[str] | None = None
) -> Frame:
    """Flag (RQ5, not a blocking error): two or more processing operations of one handling unit at the same
    timestamp.

    RQ5 assumes there are none; if there are, AS4 orders them by event id, so the later one waits 0 after
    the earlier one. The flag lists them so they can be checked.

    Args:
        relations: One row per hu-event relation with columns hu, event, time (and is_transformation if
            `processing` is None).
        processing: The processing operations P as event ids; None = the transformation events T.

    Returns:
        Frame: Columns hu, time, events (list of the processing operations, sorted), n_events; one row per
        handling unit and timestamp with at least two processing operations; sorted by hu and time.
    """
    return (
        relations.filter(processing_flag(processing))
        .group_by(c.HU, c.TIME)
        .agg(pl.col(c.EVENT).unique().sort().alias(EVENTS))
        .with_columns(pl.col(EVENTS).list.len().cast(pl.Int64).alias(N_EVENTS))
        .filter(pl.col(N_EVENTS) > 1)
        .sort(c.HU, c.TIME)
    )
