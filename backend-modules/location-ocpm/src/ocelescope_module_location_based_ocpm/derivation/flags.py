"""Flags F1-F5 (`overview/Deriving Locations.md`, section "Flags (whole log)") and F6-F10 of the location
context (`overview/module/Module Overview.md`, "Update Overview Page", section 4).

All flags use the selected level k: loc = loc^k, ploc = ploc^k, before = before_{loc^k}.
They are always computed on the whole log (never filtered).
"""

import polars as pl

from . import columns as c


def at_target(level: int) -> pl.Expr:
    """True where the handling unit was already at the target: ploc^k((e, hu)) = uloc(e).

    ⊥ counts as a change: if ploc^k or uloc is ⊥, the expression is False.

    Args:
        level: Selected level k.

    Returns:
        pl.Expr: Boolean expression on a relations frame with columns uloc and ploc^k.
    """
    return (pl.col(c.ploc(level)) == pl.col(c.ULOC)).fill_null(False)


def f1_partial_movement(relations: pl.DataFrame, level: int) -> pl.Series:
    """F1: movement events at which at least one handling unit was already at the target.

    Args:
        relations: Relations frame with columns event, is_movement, uloc, ploc^k.
        level: Selected level k.

    Returns:
        pl.Series: Flagged event ids, sorted.
    """
    return (
        relations.filter(pl.col(c.IS_MOVEMENT))
        .group_by(c.EVENT)
        .agg(at_target(level).any().alias("flag"))
        .filter("flag")[c.EVENT]
        .sort()
    )


def f2_never_located(relations: pl.DataFrame) -> pl.Series:
    """F2: handling units without any event with a provided location (level-independent).

    Args:
        relations: Relations frame with columns hu, uloc.

    Returns:
        pl.Series: Flagged handling units, sorted.
    """
    return (
        relations.group_by(c.HU)
        .agg(pl.col(c.ULOC).is_not_null().any().alias("located"))
        .filter(~pl.col("located"))[c.HU]
        .sort()
    )


def f3_mixed_pickup(relations: pl.DataFrame, level: int) -> pl.Series:
    """F3: movement events whose moved handling units had different previous locations
    (⊥ counts as one previous location). Handling units already at the target are left out;
    events with a provided pickup location are never flagged.

    Args:
        relations: Relations frame with columns event, is_movement, uloc, puloc, ploc^k.
        level: Selected level k.

    Returns:
        pl.Series: Flagged event ids, sorted.
    """
    moved = relations.filter(pl.col(c.IS_MOVEMENT) & pl.col(c.PULOC).is_null() & ~at_target(level))
    return (
        moved.group_by(c.EVENT)
        .agg(pl.col(c.ploc(level)).n_unique().alias("n_previous"))
        .filter(pl.col("n_previous") > 1)[c.EVENT]
        .sort()
    )


def f4_location_gaps(relations: pl.DataFrame, level: int) -> pl.DataFrame:
    """F4 gaps: hu-event relations where the provided pickup location differs from the handling
    unit's last known location before_{loc^k} (a first known location, ⊥, is not a gap).

    Args:
        relations: Relations frame with columns hu, event, puloc, before^k.
        level: Selected level k.

    Returns:
        pl.DataFrame: Columns hu, event, last_known, pickup; one row per gap.
    """
    before = pl.col(c.before(level))
    return (
        relations.filter(pl.col(c.PULOC).is_not_null() & before.is_not_null() & (before != pl.col(c.PULOC)))
        .select(c.HU, c.EVENT, before.alias("last_known"), pl.col(c.PULOC).alias("pickup"))
        .sort(c.HU, c.EVENT)
    )


def f4_location_gap(relations: pl.DataFrame, level: int) -> pl.Series:
    """F4: handling units with at least one location gap (see `f4_location_gaps`).

    Args:
        relations: Relations frame with columns hu, event, puloc, before^k.
        level: Selected level k.

    Returns:
        pl.Series: Flagged handling units, sorted.
    """
    return f4_location_gaps(relations, level)[c.HU].unique().sort()


def f5_movement_disagreement(relations: pl.DataFrame, level: int) -> pl.DataFrame:
    """F5: events whose movement classification disagrees with the locations.

    (a) location change without movement: e ∈ dom(uloc) \\ M where some handling unit's
        before_{loc^k} is neither ⊥ nor uloc(e);
    (b) movement without location change: e ∈ M where every handling unit has ploc^k = uloc(e).

    Args:
        relations: Relations frame with columns event, is_movement, uloc, before^k, ploc^k.
        level: Selected level k.

    Returns:
        pl.DataFrame: Columns event, kind ("a" or "b"), sorted by event.
    """
    before = pl.col(c.before(level))
    kind_a = (
        relations.filter(pl.col(c.ULOC).is_not_null() & ~pl.col(c.IS_MOVEMENT))
        .group_by(c.EVENT)
        .agg((before.is_not_null() & (before != pl.col(c.ULOC))).fill_null(False).any().alias("flag"))
        .filter("flag")
        .select(c.EVENT, pl.lit("a").alias("kind"))
    )
    kind_b = (
        relations.filter(pl.col(c.IS_MOVEMENT))
        .group_by(c.EVENT)
        .agg(at_target(level).all().alias("flag"))
        .filter("flag")
        .select(c.EVENT, pl.lit("b").alias("kind"))
    )
    return pl.concat([kind_a, kind_b]).sort(c.EVENT)


# region Flags of the location context (F6-F10, `overview/module/Module Overview.md`, section 4)


def f6_naming_clashes(locations: list[str], agg: dict[str, str]) -> pl.DataFrame:
    """F6 naming clash: unmapped locations whose name is a high-level location other locations are mapped to.

    Uses `visits.context.naming_clashes` (a location mapped to itself on purpose is no clash).

    Args:
        locations: L.
        agg: The provided (partial) mapping.

    Returns:
        pl.DataFrame: Columns location, mapped_locations; one row per flagged location.
    """
    from ..visits.context import naming_clashes

    return naming_clashes(locations, agg)


def f7_simultaneous_processing(relations: pl.DataFrame) -> pl.DataFrame:
    """F7 simultaneous processing: handling units with two processing operations at the same timestamp
    (DD-W4; `waiting_times.waiting.simultaneous_processing`).

    Args:
        relations: Relations frame with columns hu, event, time, is_processing.

    Returns:
        pl.DataFrame: Columns hu, time, events, n_events; one row per handling unit and timestamp.
    """
    from ..waiting_times.waiting import simultaneous_processing

    processing = relations.filter(pl.col(c.IS_PROCESSING))[c.EVENT].unique().to_list()
    return simultaneous_processing(relations, processing)


def f8_tied_high_level_locations(relations: pl.DataFrame, level: int) -> pl.DataFrame:
    """F8 tied high-level locations (RQ4): relations of one handling unit at the same timestamp with different
    high-level locations (⊥ counts as a value; `visits.properties.rq4_violations`). Holds at Levels 1-3 by
    construction, so the badge is only shown at Level 0.

    Args:
        relations: Relations frame with columns hu, event, time, hl^k.
        level: Selected level k.

    Returns:
        pl.DataFrame: Columns hu, time, events, values; one row per violating handling unit and timestamp.
    """
    from ..visits.properties import rq4_violations

    return rq4_violations(relations, column=c.hl(level))


def f9_unlocated_processing(relations: pl.DataFrame, level: int) -> pl.Series:
    """F9 unlocated processing: processing operations with a handling unit without a location
    (hat-hl((e, hu)) = ⊥, equivalently loc^k((e, hu)) = ⊥).

    Args:
        relations: Relations frame with columns event, is_processing, loc^k.
        level: Selected level k.

    Returns:
        pl.Series: Flagged event ids, sorted.
    """
    return (
        relations.filter(pl.col(c.IS_PROCESSING) & pl.col(c.loc(level)).is_null())[c.EVENT].unique().sort()
    )


def f10_vehicle_and_storage(vehicles: set[str], storage_units: set[str]) -> pl.Series:
    """F10 vehicle and storage unit: locations in V ∩ W.

    Args:
        vehicles: V.
        storage_units: W.

    Returns:
        pl.Series: Flagged locations, sorted.
    """
    return pl.Series(c.LOCATION, sorted(vehicles & storage_units), dtype=pl.String)


# endregion
