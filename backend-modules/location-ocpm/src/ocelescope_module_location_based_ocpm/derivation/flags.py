"""Flags F1-F5 (`overview/Deriving Locations.md`, section "Flags (whole log)").

All flags use the selected level k: loc = loc_k, ploc = ploc_k, before = before_{loc_k}.
They are always computed on the whole log (never filtered).
"""

import polars as pl

from . import columns as c


def at_target(level: int) -> pl.Expr:
    """True where the handling unit was already at the target: ploc_k((e, hu)) = uloc(e).

    ⊥ counts as a change: if ploc_k or uloc is ⊥, the expression is False.

    Args:
        level: Selected level k.

    Returns:
        pl.Expr: Boolean expression on a relations frame with columns uloc and ploc_k.
    """
    return (pl.col(c.ploc(level)) == pl.col(c.ULOC)).fill_null(False)


def f1_partial_movement(relations: pl.DataFrame, level: int) -> pl.Series:
    """F1: movement events at which at least one handling unit was already at the target.

    Args:
        relations: Relations frame with columns event, is_movement, uloc, ploc_k.
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
        relations: Relations frame with columns event, is_movement, uloc, puloc, ploc_k.
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
    unit's last known location before_{loc_k} (a first known location, ⊥, is not a gap).

    Args:
        relations: Relations frame with columns hu, event, puloc, before_k.
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
        relations: Relations frame with columns hu, event, puloc, before_k.
        level: Selected level k.

    Returns:
        pl.Series: Flagged handling units, sorted.
    """
    return f4_location_gaps(relations, level)[c.HU].unique().sort()


def f5_movement_disagreement(relations: pl.DataFrame, level: int) -> pl.DataFrame:
    """F5: events whose movement classification disagrees with the locations.

    (a) location change without movement: e ∈ dom(uloc) \\ M where some handling unit's
        before_{loc_k} is neither ⊥ nor uloc(e);
    (b) movement without location change: e ∈ M where every handling unit has ploc_k = uloc(e).

    Args:
        relations: Relations frame with columns event, is_movement, uloc, before_k, ploc_k.
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
