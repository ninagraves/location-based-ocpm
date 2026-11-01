"""Maximal visits (`overview/Single Level Visit Mappings.md`, "Visits" and "Deriving maximal Visits").

A visit ν = (hu, hl, σ) is a stay of a handling unit at one high-level location hl ∈ HL_⊥: an infix σ of
otrace(hu) that starts when hu enters hl, ends with its last event there, and contains no deviating
infix longer than the excursion tolerance κ(hl) (κ(⊥) = 0).
The maximal visits of hu at hl are found without enumerating infixes: take the positions of hu at hl in
order and cut wherever the gap between two consecutive ones is longer than κ(hl); every piece is one
maximal visit.

The steps, each a function of its own (all work on eager and lazy polars frames alike):
1. `add_trace_positions`: position of every relation in otrace(hu).
2. `context.add_high_level_locations`: hat-hl of every relation (agg, completed by identity).
3. `add_kappa`: κ(hat-hl) of every relation.
4. `add_gaps`: the gap g_j to the previous relation of hu at the same high-level location (optionally
   without relations on vehicles), and `add_gap_measures`: the number of distinct timestamps and the
   duration of the deviating infix in between (DD-V1, for the optional further conditions).
5. `add_visit_ids`: whether a relation starts a new maximal visit, and the visit it belongs to at its
   own high-level location.
6. `maximal_visits`: one row per maximal visit (first, last and exit event, duration, ...).
7. `visit_relations`: one row per visit and relation r ∈ R(ν), i.e. including the relations of excursions.
`derive_maximal_visits` runs steps 1 to 6 in one call.
"""

from collections.abc import Collection, Mapping
from datetime import timedelta

import polars as pl

from ..derivation import columns as c
from . import columns as v
from .context import Frame, add_high_level_locations
from .order import sort_by_seq


def add_trace_positions(
    relations: Frame, processing: Collection[str] | None = None, movement: str = c.IS_MOVEMENT
) -> Frame:
    """Add the position of every relation in otrace(hu), starting at 1.

    otrace(hu) orders the events of hu by time (`seq` in the concept); events with the same timestamp
    are ordered by AS4 (`order.py`): movements first, then processing operations, then the others, each
    group by event id.

    Args:
        relations: One row per hu-event relation with columns hu, time, event, `movement` (and
            is_transformation if `processing` is None).
        processing: The processing operations P as event ids, used for the tie-break; None = the
            transformation events T. Use the same P as for the waiting times.
        movement: Boolean column marking the movement events M.

    Returns:
        Frame: `relations` sorted by hu, time, tie_rank, event, with the columns tie_rank and position.
    """
    return sort_by_seq(relations, c.HU, processing=processing, movement=movement).with_columns(
        (pl.int_range(pl.len()).over(c.HU) + 1).alias(v.POSITION)
    )


def add_kappa(relations: Frame, kappa: int | None, high_level: str = v.HIGH_LEVEL) -> Frame:
    """Add κ(hat-hl), the excursion tolerance of the relation's own high-level location.

    The concept defines one tolerance κ_max for every hl ∈ HL and κ(⊥) = 0.
    To allow one tolerance per high-level location later, only this function has to change (e.g. join
    κ from a small table with one row per high-level location).

    Args:
        relations: Relations frame with the column `high_level` (null = ⊥).
        kappa: κ_max ≥ 0, the tolerance of every high-level location; ⊥ always gets 0 (DD-V3). None = no
            limit on the number of events of a deviating infix (DD-V1: only the other selected conditions
            apply); κ(⊥) stays 0.
        high_level: Column of hat-hl.

    Returns:
        Frame: `relations` with the column kappa (Int64; null at hl ∈ HL if `kappa` is None).
    """
    if kappa is not None and kappa < 0:
        raise ValueError(f"The excursion tolerance must be at least 0, got {kappa}.")
    return relations.with_columns(
        pl.when(pl.col(high_level).is_null())
        .then(0)
        .otherwise(pl.lit(kappa, dtype=pl.Int64))
        .cast(pl.Int64)
        .alias(v.KAPPA)
    )


def add_gaps(
    relations: Frame,
    high_level: str = v.HIGH_LEVEL,
    location: str = "loc",
    vehicles: Collection[str] = (),
    ignore_vehicles: bool = False,
) -> Frame:
    """Add the gap before every relation: the number of events since the previous relation of the
    handling unit at the same high-level location that count towards the tolerance κ.

    By default every event in between counts, so the gap is g_j = p_j - p_{j-1} - 1, with p_{j-1} the
    position of the previous relation of the same handling unit at the same high-level location (⊥ counts
    as one location here).
    With `ignore_vehicles` (Nina, 2026-10-31), relations on a vehicle (loc ∈ V) in between do not count,
    even if the vehicle maps to another high-level location; so a trip on a truck that is not part of hl
    does not use up the tolerance. Gaps before ⊥ relations always count every event, since visits to ⊥
    allow no excursions.
    The first relation of a handling unit at a high-level location has no gap (null).

    How it works: w = 0 for relations that do not count, 1 otherwise; with C the cumulative sum of w per
    handling unit, the counted events strictly between p_{j-1} and p_j are C(p_j) - w(p_j) - C(p_{j-1}).
    With w = 1 everywhere this is p_j - p_{j-1} - 1.

    Args:
        relations: Output of `add_trace_positions` with the columns `high_level` and `location`.
        high_level: Column of hat-hl.
        location: Column of loc (only used with `ignore_vehicles`).
        vehicles: The set V (only used with `ignore_vehicles`).
        ignore_vehicles: True = relations on a vehicle do not count towards the gap (default False:
            they count).

    Returns:
        Frame: `relations` with the column gap (null for the first relation at a high-level location).
    """
    if ignore_vehicles:
        weight = (~pl.col(location).is_in(list(vehicles)).fill_null(False)).cast(pl.Int64)
    else:
        weight = pl.repeat(1, pl.len(), dtype=pl.Int64)
    out = relations.with_columns(weight.alias("_w")).with_columns(
        (pl.col("_w").cum_sum().over(c.HU, order_by=v.POSITION) - pl.col("_w")).alias("_c")
    )
    # `over` puts all nulls (⊥) of a handling unit into one group, so ⊥ needs no stand-in value.
    group = (c.HU, high_level)
    previous_c = (pl.col("_c") + pl.col("_w")).shift(1).over(*group, order_by=v.POSITION)
    previous_p = pl.col(v.POSITION).shift(1).over(*group, order_by=v.POSITION)
    gap = (
        pl.when(pl.col(high_level).is_null())
        .then(pl.col(v.POSITION) - previous_p - 1)
        .otherwise(pl.col("_c") - previous_c)
    )
    return out.with_columns(gap.alias(v.GAP)).drop("_w", "_c")


def add_gap_measures(relations: Frame, high_level: str = v.HIGH_LEVEL) -> Frame:
    """Add the number of distinct timestamps and the duration of the deviating infix before every relation.

    The deviating infix before p_j is otrace(hu)[p_{j-1} + 1 : p_j - 1] (all its events are not at hl).
    - gap_timestamps: its number of distinct timestamps (0 if it is empty);
    - gap_duration: time(e_{p_j}) - time(e_{p_{j-1}+1}), from its first event until the first event back at
      hl (DD-V1: "time of first event until first event back in the visit"); 0 if it is empty.
    Both are null for the first relation of a handling unit at a high-level location. Relations on
    vehicles always count here (`ignore_vehicles` only concerns the number of events).

    How it works: with t the dense rank of the timestamps per handling unit (the trace is sorted by time),
    the distinct timestamps of positions a..b are t(b) - t(a) + 1; t and time of the next relation in the
    trace are taken at p_{j-1} and shifted per (hu, hl), those of the previous relation at p_j directly.

    Args:
        relations: Output of `add_trace_positions` with the column `high_level`.
        high_level: Column of hat-hl.

    Returns:
        Frame: `relations` with the columns gap_timestamps (Int64) and gap_duration (duration).
    """
    trace = (c.HU,)
    group = (c.HU, high_level)
    out = relations.with_columns(
        pl.col(c.TIME).rank("dense").over(*trace).cast(pl.Int64).alias("_t")
    ).with_columns(
        pl.col("_t").shift(1).over(*trace, order_by=v.POSITION).alias("_t_before"),
        pl.col("_t").shift(-1).over(*trace, order_by=v.POSITION).alias("_t_after"),
        pl.col(c.TIME).shift(-1).over(*trace, order_by=v.POSITION).alias("_time_after"),
    )
    previous_p = pl.col(v.POSITION).shift(1).over(*group, order_by=v.POSITION)
    first_t = pl.col("_t_after").shift(1).over(*group, order_by=v.POSITION)
    first_time = pl.col("_time_after").shift(1).over(*group, order_by=v.POSITION)
    empty = (pl.col(v.POSITION) - previous_p - 1) == 0
    zero = pl.col(c.TIME) - pl.col(c.TIME)
    return out.with_columns(
        pl.when(empty).then(0).otherwise(pl.col("_t_before") - first_t + 1).cast(pl.Int64).alias(v.GAP_TIMESTAMPS),
        pl.when(empty).then(zero).otherwise(pl.col(c.TIME) - first_time).alias(v.GAP_DURATION),
    ).drop("_t", "_t_before", "_t_after", "_time_after")


def add_visit_ids(
    relations: Frame,
    high_level: str = v.HIGH_LEVEL,
    max_timestamps: int | None = None,
    max_excursion_duration: timedelta | None = None,
) -> Frame:
    """Number the maximal visits and assign every relation to the one at its own high-level location.

    A relation starts a new maximal visit iff it is the first one of its handling unit at its high-level
    location (gap null) or the deviating infix before it violates one of the selected conditions (DD-V1;
    all selected conditions must hold, so violating one is enough to cut):
    - more counted events than κ (gap > kappa; no limit if kappa is null);
    - more distinct timestamps than `max_timestamps` (gap_timestamps, `add_gap_measures`);
    - longer than `max_excursion_duration` (gap_duration, `add_gap_measures`).
    At ⊥ the tolerance is always 0 (DD-V3): any relation in between cuts.
    Counting these starts per handling unit and high-level location numbers the visits; the visit ids
    are then numbered 1, 2, ... over all visits, ordered by handling unit and first position.

    Every relation lies in exactly one maximal visit at its own high-level location (the one with this
    id); it can lie in further maximal visits at other high-level locations as part of their excursions
    (see `visit_relations`).

    Args:
        relations: Output of `add_gaps` with the columns kappa and `high_level` (and of `add_gap_measures`
            if `max_timestamps` or `max_excursion_duration` is given).
        high_level: Column of hat-hl.
        max_timestamps: Maximum number of distinct timestamps of a deviating infix at hl ∈ HL; None = no
            limit.
        max_excursion_duration: Maximum duration of a deviating infix at hl ∈ HL; None = no limit.

    Returns:
        Frame: `relations` with the columns starts_visit (bool) and visit_id (Int64).
    """
    located = pl.col(high_level).is_not_null()
    starts = pl.col(v.GAP).is_null() | (pl.col(v.GAP) > pl.col(v.KAPPA)).fill_null(False)
    if max_timestamps is not None:
        starts = starts | (located & (pl.col(v.GAP_TIMESTAMPS) > max_timestamps)).fill_null(False)
    if max_excursion_duration is not None:
        starts = starts | (located & (pl.col(v.GAP_DURATION) > max_excursion_duration)).fill_null(False)
    number = starts.cum_sum().over(c.HU, high_level, order_by=v.POSITION)
    # First position of the visit of each relation, then a dense rank over (hu, first position).
    first = pl.col(v.POSITION).min().over(c.HU, high_level, number)
    visit_id = pl.struct(pl.col(c.HU), first).rank("dense").cast(pl.Int64)
    return relations.with_columns(starts.alias(v.STARTS_VISIT)).with_columns(
        visit_id.alias(v.VISIT_ID)
    )


def maximal_visits(relations: Frame, high_level: str = v.HIGH_LEVEL) -> Frame:
    """One row per maximal visit ν = (hu, hl, otrace(hu)[i:k]).

    Columns:
    - visit_id, hu, high_level (null = ⊥ visit), kappa;
    - first_position i, last_position k, first_event e_i (= entry event e_in), last_event e_k;
    - exit_event e_out = otrace(hu)[k+1], or e_k if the trace ends with the visit (then ends_trace is true);
    - entry_time, last_time, exit_time, and duration d = time(e_out) - time(e_in);
    - n_relations = |σ| = k - i + 1, n_at_location = number of relations at hl, and interrupted
      (true iff some relation of σ is not at hl).

    Bounds of the duration (concept, "Visit duration"): if the visit ends with the trace, d is a lower
    bound; if the exit event is not a movement, the departure lies between e_k and e_out, so d is an
    upper bound. Both are left to the reader of the table (columns ends_trace and the exit event).

    Args:
        relations: Output of `add_visit_ids` (all relations of every handling unit, not only some).
        high_level: Column of hat-hl.

    Returns:
        Frame: One row per maximal visit, sorted by visit_id.
    """
    visits = relations.group_by(v.VISIT_ID).agg(
        pl.col(c.HU).first(),
        pl.col(high_level).first().alias(v.HIGH_LEVEL),
        pl.col(v.KAPPA).first(),
        pl.col(v.POSITION).min().alias(v.FIRST_POSITION),
        pl.col(v.POSITION).max().alias(v.LAST_POSITION),
        pl.col(c.EVENT).sort_by(v.POSITION).first().alias(v.FIRST_EVENT),
        pl.col(c.EVENT).sort_by(v.POSITION).last().alias(v.LAST_EVENT),
        pl.col(c.TIME).sort_by(v.POSITION).first().alias(v.ENTRY_TIME),
        pl.col(c.TIME).sort_by(v.POSITION).last().alias(v.LAST_TIME),
        pl.len().cast(pl.Int64).alias(v.N_AT_LOCATION),
    )
    # The exit event is the relation right after the last one, if the trace goes on.
    successors = relations.select(
        c.HU,
        (pl.col(v.POSITION) - 1).alias(v.LAST_POSITION),
        pl.col(c.EVENT).alias("_next_event"),
        pl.col(c.TIME).alias("_next_time"),
    )
    visits = visits.join(successors, on=[c.HU, v.LAST_POSITION], how="left")
    n_relations = pl.col(v.LAST_POSITION) - pl.col(v.FIRST_POSITION) + 1
    return (
        visits.with_columns(
            pl.col("_next_event").is_null().alias(v.ENDS_TRACE),
            pl.col("_next_event").fill_null(pl.col(v.LAST_EVENT)).alias(v.EXIT_EVENT),
            pl.col("_next_time").fill_null(pl.col(v.LAST_TIME)).alias(v.EXIT_TIME),
            n_relations.cast(pl.Int64).alias(v.N_RELATIONS),
        )
        .with_columns(
            (pl.col(v.EXIT_TIME) - pl.col(v.ENTRY_TIME)).alias(v.DURATION),
            (pl.col(v.N_RELATIONS) > pl.col(v.N_AT_LOCATION)).alias(v.INTERRUPTED),
        )
        .select(
            v.VISIT_ID,
            c.HU,
            v.HIGH_LEVEL,
            v.KAPPA,
            v.FIRST_POSITION,
            v.LAST_POSITION,
            v.FIRST_EVENT,
            v.LAST_EVENT,
            v.EXIT_EVENT,
            v.ENTRY_TIME,
            v.LAST_TIME,
            v.EXIT_TIME,
            v.ENDS_TRACE,
            v.DURATION,
            v.N_RELATIONS,
            v.N_AT_LOCATION,
            v.INTERRUPTED,
        )
        .sort(v.VISIT_ID)
    )


def visit_relations(
    relations: Frame, visits: Frame, high_level: str = v.HIGH_LEVEL
) -> Frame:
    """One row per visit and relation r ∈ R(ν), i.e. every relation of the visit's infix σ.

    Relations of excursions appear once for every visit they lie in, so a relation can appear several
    times (once with its own maximal visit, and once per visit at another location around it).
    Works for any set of visits given by hu, first and last position (not only maximal ones).

    How it works: each visit is expanded to the positions first_position, ..., last_position and joined
    with the relations on (hu, position); the cost is linear in the size of the result.

    Args:
        relations: Relations frame with columns hu, position, `high_level` and any further columns
            (event, time, loc, ...), which are kept; a visit_id column of the relations is dropped, since
            the visit id of the row is the one of `visits`.
        visits: One row per visit with columns visit_id, hu, high_level, first_position, last_position.
        high_level: Column of hat-hl in `relations`.

    Returns:
        Frame: The relation columns plus visit_id, visit_high_level, first_position, last_position and
        at_location (hat-hl(r) = hl, where ⊥ = ⊥ counts as true), sorted by visit_id and position.
    """
    expanded = visits.select(
        v.VISIT_ID,
        c.HU,
        pl.col(v.HIGH_LEVEL).alias(v.VISIT_HIGH_LEVEL),
        v.FIRST_POSITION,
        v.LAST_POSITION,
        pl.int_ranges(pl.col(v.FIRST_POSITION), pl.col(v.LAST_POSITION) + 1).alias(
            v.POSITION
        ),
    ).explode(v.POSITION)
    names = relations.collect_schema().names()
    rel = relations.drop(v.VISIT_ID) if v.VISIT_ID in names else relations
    return (
        expanded.with_columns(pl.col(v.POSITION).cast(pl.Int64))
        .join(rel.with_columns(pl.col(v.POSITION).cast(pl.Int64)), on=[c.HU, v.POSITION])
        .with_columns(
            pl.col(high_level).eq_missing(pl.col(v.VISIT_HIGH_LEVEL)).alias(v.AT_LOCATION)
        )
        .sort(v.VISIT_ID, v.POSITION)
    )


def derive_maximal_visits(
    relations: Frame,
    location: str = "loc",
    agg: Mapping[str, str] | None = None,
    kappa: int | None = 0,
    vehicles: Collection[str] = (),
    ignore_vehicles: bool = False,
    processing: Collection[str] | None = None,
    max_timestamps: int | None = None,
    max_excursion_duration: timedelta | None = None,
) -> tuple[Frame, Frame]:
    """All maximal visits V_max in one call (steps 1 to 6).

    Args:
        relations: One row per hu-event relation with columns hu, event, time, is_movement and `location`
            (and is_transformation if `processing` is None), e.g. a saved
            level mapping (`derivation.level_files.load_level_mapping`) or `Derivation.relations`.
        location: Column of the current location loc (null = ⊥), e.g. "loc" or "loc_3".
        agg: Location mapping L -> HL (partial, completed by identity); None = identity.
        kappa: κ_max, the maximum number of events of a deviating infix at every high-level location
            (κ(⊥) = 0); None = no limit on the number of events (DD-V1).
        vehicles: The set V (only used with `ignore_vehicles`).
        ignore_vehicles: True = relations on a vehicle do not count towards the tolerance (see
            `add_gaps`); default False.
        processing: The processing operations P as event ids, only used to order events with the same
            timestamp (AS4, `add_trace_positions`); None = the transformation events T.
        max_timestamps: Optional further condition (DD-V1): maximum number of distinct timestamps of a
            deviating infix; None = off.
        max_excursion_duration: Optional further condition (DD-V1): maximum duration of a deviating infix
            (first event of the infix until the first event back at hl); None = off.

    Returns:
        tuple[Frame, Frame]: The relations with the columns tie_rank, high_level, position, kappa, gap,
        starts_visit and visit_id; and the maximal visits (see `maximal_visits`).
    """
    rel = add_trace_positions(relations, processing)
    rel = add_high_level_locations(rel, location, agg)
    rel = add_kappa(rel, kappa)
    rel = add_gaps(rel, location=location, vehicles=vehicles, ignore_vehicles=ignore_vehicles)
    rel = add_gap_measures(rel)
    rel = add_visit_ids(rel, max_timestamps=max_timestamps, max_excursion_duration=max_excursion_duration)
    return rel, maximal_visits(rel)
