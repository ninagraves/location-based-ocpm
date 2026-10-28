"""Current locations loc_0 to loc_3, before_λ and ploc_λ (`overview/Deriving Locations.md`, "Deriving Current locations").

All functions take the relations frame (one row per hu-event relation, see `inputs.ResolvedInputs`)
and return it with one more column. A null value is ⊥.

Time ties: several events of one handling unit can share a timestamp. Level 1 uses ≤ on time,
so all relations of a handling unit at one timestamp get the same loc_1; before_λ uses < on time.
Both are computed on "time steps" (one row per handling unit and timestamp).
"""

import polars as pl

from . import columns as c


def _per_time_step(relations: pl.DataFrame, value: str) -> pl.DataFrame:
    """Collapse relations to one row per handling unit and timestamp.

    Args:
        relations: Relations frame with columns hu, time and `value`.
        value: Column to collapse; the first non-null value of the time step is kept
            (all non-null values of a step agree by RQ1 for uloc, and by construction for loc_1 to loc_3).

    Returns:
        pl.DataFrame: Columns hu, time, `value`, sorted by hu and time.
    """
    return (
        relations.group_by(c.HU, c.TIME)
        .agg(pl.col(value).drop_nulls().first())
        .sort(c.HU, c.TIME)
    )


def add_loc_0(relations: pl.DataFrame) -> pl.DataFrame:
    """Level 0 (provided): loc_0((e, hu)) = uloc(e) if e ∈ dom(uloc), else ⊥.

    Args:
        relations: Relations frame with column uloc.

    Returns:
        pl.DataFrame: With column loc_0.
    """
    return relations.with_columns(pl.col(c.ULOC).alias(c.loc(0)))


def add_loc_1(relations: pl.DataFrame) -> pl.DataFrame:
    """Level 1 (forward fill): the provided location of the latest located event at or before the event.

    Args:
        relations: Relations frame with columns hu, time, uloc.

    Returns:
        pl.DataFrame: With column loc_1.
    """
    steps = _per_time_step(relations, c.ULOC).with_columns(
        pl.col(c.ULOC).forward_fill().over(c.HU, order_by=c.TIME).alias(c.loc(1))
    )
    return relations.join(steps.select(c.HU, c.TIME, c.loc(1)), on=[c.HU, c.TIME], how="left")


def add_before(relations: pl.DataFrame, level: int) -> pl.DataFrame:
    """before_{loc_k}: loc_k at the handling unit's latest strictly earlier event with loc_k ≠ ⊥.

    Args:
        relations: Relations frame with columns hu, time and loc_k.
        level: Level k.

    Returns:
        pl.DataFrame: With column before_k.
    """
    steps = _per_time_step(relations, c.loc(level)).with_columns(
        pl.col(c.loc(level)).forward_fill().shift(1).over(c.HU, order_by=c.TIME).alias(c.before(level))
    )
    return relations.join(steps.select(c.HU, c.TIME, c.before(level)), on=[c.HU, c.TIME], how="left")


def add_ploc(relations: pl.DataFrame, level: int) -> pl.DataFrame:
    """ploc_k: the provided pickup location where there is one, else before_{loc_k}.

    Args:
        relations: Relations frame with columns puloc and before_k (see `add_before`).
        level: Level k.

    Returns:
        pl.DataFrame: With column ploc_k.
    """
    return relations.with_columns(pl.coalesce(c.PULOC, c.before(level)).alias(c.ploc(level)))


def first_location(relations: pl.DataFrame) -> pl.DataFrame:
    """l_0(hu): a handling unit's location before its first movement (Level 2).

    l_0(hu) = uloc(e_f) if the earliest located event e_f lies strictly before the first movement
    (time t_M(hu)); else the pickup location of the first movement, if provided; else ⊥.

    Args:
        relations: Relations frame with columns hu, time, is_movement, uloc, puloc.

    Returns:
        pl.DataFrame: Columns hu, t_m (time of the first movement, null if none), l_0.
    """
    t_m = relations.filter(pl.col(c.IS_MOVEMENT)).group_by(c.HU).agg(pl.col(c.TIME).min().alias("t_m"))
    first_located = (
        relations.filter(pl.col(c.ULOC).is_not_null())
        .sort(c.TIME)
        .group_by(c.HU)
        .agg(pl.col(c.TIME).first().alias("t_f"), pl.col(c.ULOC).first().alias("uloc_f"))
    )
    first_pickup = (
        relations.join(t_m, on=c.HU)
        .filter(pl.col(c.IS_MOVEMENT) & (pl.col(c.TIME) == pl.col("t_m")) & pl.col(c.PULOC).is_not_null())
        .group_by(c.HU)
        .agg(pl.col(c.PULOC).first().alias("puloc_m"))
    )
    hus = relations.select(c.HU).unique()
    return (
        hus.join(t_m, on=c.HU, how="left")
        .join(first_located, on=c.HU, how="left")
        .join(first_pickup, on=c.HU, how="left")
        .with_columns(
            pl.when(pl.col("t_f").is_not_null() & (pl.col("t_m").is_null() | (pl.col("t_f") < pl.col("t_m"))))
            .then(pl.col("uloc_f"))
            .otherwise(pl.col("puloc_m"))
            .alias("l_0")
        )
        .select(c.HU, "t_m", "l_0")
    )


def add_loc_2(relations: pl.DataFrame) -> pl.DataFrame:
    """Level 2 (backward fill): loc_1 where known, else l_0(hu) (see `first_location`).

    Args:
        relations: Relations frame with columns hu, time, is_movement, uloc, puloc, loc_1.

    Returns:
        pl.DataFrame: With column loc_2.
    """
    l_0 = first_location(relations).select(c.HU, "l_0")
    return (
        relations.join(l_0, on=c.HU, how="left")
        .with_columns(pl.coalesce(c.loc(1), "l_0").alias(c.loc(2)))
        .drop("l_0")
    )


def add_loc_3(relations: pl.DataFrame, eloc_2: pl.DataFrame) -> pl.DataFrame:
    """Level 3 (transformation locations): loc_2 where known, else the agreed Level 2 location of the
    handling unit's earliest transformation event t_1(hu) before its first movement with eloc_{loc_2} ≠ ⊥.

    If several transformation events qualify at the same earliest time, the one with the smallest
    event id is taken (the concept says "an earliest"; ties are not specified).

    Args:
        relations: Relations frame with columns hu, time, event, is_transformation, is_movement,
            uloc, puloc, loc_2.
        eloc_2: Agreed event locations under loc_2, columns event, eloc (see `agreement.event_locations`).

    Returns:
        pl.DataFrame: With column loc_3.
    """
    t_m = first_location(relations).select(c.HU, "t_m")
    t_1 = (
        relations.filter(pl.col(c.IS_TRANSFORMATION))
        .join(t_m, on=c.HU, how="left")
        .filter(pl.col("t_m").is_null() | (pl.col(c.TIME) < pl.col("t_m")))
        .join(eloc_2, on=c.EVENT, how="inner")
        .filter(pl.col("eloc").is_not_null())
        .sort(c.TIME, c.EVENT)
        .group_by(c.HU)
        .agg(pl.col("eloc").first().alias("l_t"))
    )
    return (
        relations.join(t_1, on=c.HU, how="left")
        .with_columns(pl.coalesce(c.loc(2), "l_t").alias(c.loc(3)))
        .drop("l_t")
    )
