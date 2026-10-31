"""Stops, transfers and shifts of visits (`overview/Single Level Visit Mappings.md`, "identifying shifts").

Let ν = (hu, hl, σ) be a visit with hl ∈ HL (visits at ⊥ have no stops, transfers or shifts).
- A **stop** of ν is a relation of ν at hl that is not on a vehicle: hat-hl(r) = hl and loc(r) ∉ V.
- With a_1 < ... < a_m the positions of the stops, the **transfer** μ_j between two consecutive stops is
  the (possibly empty) infix strictly between them, otrace(hu)[a_j + 1 : a_{j+1} - 1], j = 1, ..., m - 1.
- Every transfer has one category:
  - "stay": μ_j = ⟨⟩ and both stops have the same loc;
  - "direct shift": μ_j = ⟨⟩ and the stops have different loc;
  - "vehicle shift": μ_j ≠ ⟨⟩ and every relation of μ_j is on a vehicle (whatever the two stops' loc);
  - "external shift": μ_j ≠ ⟨⟩ and some relation of μ_j is not on a vehicle (⊥ counts as not on a vehicle).
  Direct and vehicle shifts are internal shifts.
Vehicle relations before the first and after the last stop are entry and exit movements, not shifts.

The steps, each a function of its own (eager and lazy polars frames alike):
1. `add_stops`: on_vehicle and is_stop for every row of the visit relations (`maximal.visit_relations`).
2. `transfers`: one row per transfer with its category.
3. `shift_summary`: per visit the counts per category, the stops, and the location sets L(ν), L_hl(ν),
   L_stop(ν), L_¬v(ν) with the properties "vehicle visit" and "transferring visit".
"""

from collections.abc import Collection

import polars as pl

from ..derivation import columns as c
from . import columns as v
from .context import Frame

#: Transfer categories, in the order of the concept.
STAY = "stay"
DIRECT_SHIFT = "direct shift"
VEHICLE_SHIFT = "vehicle shift"
EXTERNAL_SHIFT = "external shift"
CATEGORIES = (STAY, DIRECT_SHIFT, VEHICLE_SHIFT, EXTERNAL_SHIFT)

#: Columns of the transfers frame (one row per transfer μ_j).
J = "j"
FROM_POSITION, TO_POSITION = "from_position", "to_position"
FROM_EVENT, TO_EVENT = "from_event", "to_event"
FROM_LOC, TO_LOC = "from_loc", "to_loc"
#: Events of μ_j in trace order (empty list for ⟨⟩) and their number |μ_j| = a_{j+1} - a_j - 1.
TRANSFER_EVENTS = "transfer_events"
TRANSFER_LENGTH = "transfer_length"
#: True if every relation of μ_j is on a vehicle (true for ⟨⟩).
ALL_ON_VEHICLE = "all_on_vehicle"
CATEGORY = "category"

#: Columns of the shift summary (one row per visit).
N_STOPS = "n_stops"
N_STAYS = "n_stays"
N_DIRECT_SHIFTS = "n_direct_shifts"
N_VEHICLE_SHIFTS = "n_vehicle_shifts"
N_EXTERNAL_SHIFTS = "n_external_shifts"
N_INTERNAL_SHIFTS = "n_internal_shifts"
#: L(ν): low-level locations of the visit (⊥ left out); L_hl(ν): those at hl; L_stop(ν) = L_hl(ν) \ V;
#: L_¬v(ν) = L(ν) \ V. Sorted lists.
LOCATIONS = "locations"
LOCATIONS_AT_HL = "locations_at_hl"
STOP_LOCATIONS = "stop_locations"
NON_VEHICLE_LOCATIONS = "non_vehicle_locations"
#: Vehicle visit: L_¬v(ν) = ∅. Transferring visit: no stops, but L_¬v(ν) ≠ ∅.
IS_VEHICLE_VISIT = "is_vehicle_visit"
IS_TRANSFERRING_VISIT = "is_transferring_visit"

#: Count column of each category.
CATEGORY_COUNTS = {
    STAY: N_STAYS,
    DIRECT_SHIFT: N_DIRECT_SHIFTS,
    VEHICLE_SHIFT: N_VEHICLE_SHIFTS,
    EXTERNAL_SHIFT: N_EXTERNAL_SHIFTS,
}


def add_stops(
    visit_relations: Frame, vehicles: Collection[str] = (), location: str = "loc"
) -> Frame:
    """Add on_vehicle (loc ∈ V) and is_stop (relation at hl, not on a vehicle) to the visit relations.

    A stop is never ⊥ (hat-hl = hl ∈ HL implies loc ≠ ⊥), and visits at ⊥ have no stops.

    Args:
        visit_relations: Output of `maximal.visit_relations` (columns visit_high_level, at_location and
            `location`).
        vehicles: The set V.
        location: Column of the low-level location loc (null = ⊥).

    Returns:
        Frame: `visit_relations` with the columns on_vehicle and is_stop (both false for ⊥).
    """
    on_vehicle = pl.col(location).is_in(list(vehicles)).fill_null(False)
    is_stop = (
        pl.col(v.AT_LOCATION) & pl.col(v.VISIT_HIGH_LEVEL).is_not_null() & ~on_vehicle
    )
    return visit_relations.with_columns(on_vehicle.alias(v.ON_VEHICLE)).with_columns(
        is_stop.alias(v.IS_STOP)
    )


def transfer_category() -> pl.Expr:
    """The category of a transfer from its length, ALL_ON_VEHICLE and the two stops' locations.

    Returns:
        pl.Expr: "stay", "direct shift", "vehicle shift" or "external shift".
    """
    empty = pl.col(TRANSFER_LENGTH) == 0
    return (
        pl.when(empty & (pl.col(FROM_LOC) == pl.col(TO_LOC)))
        .then(pl.lit(STAY))
        .when(empty)
        .then(pl.lit(DIRECT_SHIFT))
        .when(pl.col(ALL_ON_VEHICLE))
        .then(pl.lit(VEHICLE_SHIFT))
        .otherwise(pl.lit(EXTERNAL_SHIFT))
    )


def transfers(visit_relations: Frame, location: str = "loc") -> Frame:
    """One row per transfer μ_j between two consecutive stops of a visit, with its category.

    How it works:
    - the stops of each visit are numbered j = 1, ..., m in trace order; stop j and the next stop j + 1
      give from/to position, event and loc;
    - every other relation gets the number of the stops before it (cumulative sum of is_stop), so the
      relations of μ_j are those with number j that are not stops (relations before the first stop get
      0 and those after the last get m, and neither belongs to a transfer);
    - per (visit, j), μ_j's events and whether all of them are on a vehicle are aggregated;
    - an empty μ_j (adjacent stops, a_{j+1} = a_j + 1) gets an empty event list and length 0.

    Args:
        visit_relations: Output of `add_stops`.
        location: Column of loc.

    Returns:
        Frame: Columns visit_id, hu, visit_high_level, j, from_position, to_position, from_event, to_event,
        from_loc, to_loc, transfer_events (list), transfer_length, all_on_vehicle, category; sorted by
        visit_id and j. Visits with fewer than two stops have no rows.
    """
    ordered = visit_relations.sort(v.VISIT_ID, v.POSITION)
    stops = (
        ordered.filter(pl.col(v.IS_STOP))
        .with_columns((pl.int_range(pl.len()).over(v.VISIT_ID) + 1).cast(pl.Int64).alias(J))
        .select(
            v.VISIT_ID,
            c.HU,
            v.VISIT_HIGH_LEVEL,
            J,
            pl.col(v.POSITION).alias(FROM_POSITION),
            pl.col(v.POSITION).shift(-1).over(v.VISIT_ID).alias(TO_POSITION),
            pl.col(c.EVENT).alias(FROM_EVENT),
            pl.col(c.EVENT).shift(-1).over(v.VISIT_ID).alias(TO_EVENT),
            pl.col(location).alias(FROM_LOC),
            pl.col(location).shift(-1).over(v.VISIT_ID).alias(TO_LOC),
        )
        .filter(pl.col(TO_POSITION).is_not_null())
    )
    between = (
        ordered.with_columns(
            pl.col(v.IS_STOP).cast(pl.Int64).cum_sum().over(v.VISIT_ID).alias(J)
        )
        .filter(~pl.col(v.IS_STOP) & (pl.col(J) > 0))
        .group_by(v.VISIT_ID, J)
        .agg(
            pl.col(c.EVENT).sort_by(v.POSITION).alias(TRANSFER_EVENTS),
            pl.col(v.ON_VEHICLE).all().alias(ALL_ON_VEHICLE),
        )
    )
    return (
        stops.join(between, on=[v.VISIT_ID, J], how="left")
        .with_columns(
            pl.col(TRANSFER_EVENTS).fill_null(pl.lit([], dtype=pl.List(pl.String))),
            pl.col(ALL_ON_VEHICLE).fill_null(True),
            (pl.col(TO_POSITION) - pl.col(FROM_POSITION) - 1).alias(TRANSFER_LENGTH),
        )
        .with_columns(transfer_category().alias(CATEGORY))
        .select(
            v.VISIT_ID,
            c.HU,
            v.VISIT_HIGH_LEVEL,
            J,
            FROM_POSITION,
            TO_POSITION,
            FROM_EVENT,
            TO_EVENT,
            FROM_LOC,
            TO_LOC,
            TRANSFER_EVENTS,
            TRANSFER_LENGTH,
            ALL_ON_VEHICLE,
            CATEGORY,
        )
        .sort(v.VISIT_ID, J)
    )


def shift_summary(
    visit_relations: Frame, transfers_frame: Frame, location: str = "loc"
) -> Frame:
    """Per visit: number of stops, transfers per category, location sets and the vehicle properties.

    For visits at ⊥ all these columns are null (stops and shifts are only defined for hl ∈ HL).
    For a visit at hl ∈ HL without transfers, all counts are 0.
    n_internal_shifts = n_direct_shifts + n_vehicle_shifts, and
    n_stays + n_direct_shifts + n_vehicle_shifts + n_external_shifts = n_stops - 1 (if n_stops ≥ 1).

    Args:
        visit_relations: Output of `add_stops`.
        transfers_frame: Output of `transfers`.
        location: Column of loc.

    Returns:
        Frame: One row per visit: visit_id, n_stops, n_stays, n_direct_shifts, n_vehicle_shifts,
        n_external_shifts, n_internal_shifts, locations, locations_at_hl, stop_locations,
        non_vehicle_locations, is_vehicle_visit, is_transferring_visit; sorted by visit_id.
    """
    loc = pl.col(location)

    def location_set(condition: pl.Expr) -> pl.Expr:
        """Sorted distinct non-null locations of the rows meeting `condition`."""
        return loc.filter(condition & loc.is_not_null()).unique().sort()

    per_visit = visit_relations.group_by(v.VISIT_ID).agg(
        pl.col(v.VISIT_HIGH_LEVEL).first(),
        pl.col(v.IS_STOP).sum().cast(pl.Int64).alias(N_STOPS),
        location_set(pl.lit(True)).alias(LOCATIONS),
        location_set(pl.col(v.AT_LOCATION)).alias(LOCATIONS_AT_HL),
        location_set(pl.col(v.IS_STOP)).alias(STOP_LOCATIONS),
        location_set(~pl.col(v.ON_VEHICLE)).alias(NON_VEHICLE_LOCATIONS),
    )
    counts = transfers_frame.group_by(v.VISIT_ID).agg(
        (pl.col(CATEGORY) == category).sum().cast(pl.Int64).alias(column)
        for category, column in CATEGORY_COUNTS.items()
    )
    count_columns = list(CATEGORY_COUNTS.values())
    has_location = pl.col(v.VISIT_HIGH_LEVEL).is_not_null()
    no_non_vehicle = pl.col(NON_VEHICLE_LOCATIONS).list.len() == 0

    def only_at_location(expr: pl.Expr) -> pl.Expr:
        """`expr` for visits at hl ∈ HL, null for visits at ⊥."""
        return pl.when(has_location).then(expr)

    return (
        per_visit.join(counts, on=v.VISIT_ID, how="left")
        .with_columns(pl.col(count_columns).fill_null(0))
        .with_columns(
            (pl.col(N_DIRECT_SHIFTS) + pl.col(N_VEHICLE_SHIFTS)).alias(N_INTERNAL_SHIFTS),
            no_non_vehicle.alias(IS_VEHICLE_VISIT),
            ((pl.col(N_STOPS) == 0) & ~no_non_vehicle).alias(IS_TRANSFERRING_VISIT),
        )
        .with_columns(
            only_at_location(pl.col(col)).alias(col)
            for col in (
                N_STOPS,
                *count_columns,
                N_INTERNAL_SHIFTS,
                STOP_LOCATIONS,
                IS_VEHICLE_VISIT,
                IS_TRANSFERRING_VISIT,
            )
        )
        .select(
            v.VISIT_ID,
            N_STOPS,
            *count_columns,
            N_INTERNAL_SHIFTS,
            LOCATIONS,
            LOCATIONS_AT_HL,
            STOP_LOCATIONS,
            NON_VEHICLE_LOCATIONS,
            IS_VEHICLE_VISIT,
            IS_TRANSFERRING_VISIT,
        )
        .sort(v.VISIT_ID)
    )
