"""Movement routes (`overview/Deriving Locations.md`, box "Movement Route")."""

import polars as pl

from . import columns as c


def event_routes(relations: pl.DataFrame, level: int) -> pl.DataFrame:
    """move(e) for every movement event e: the (previous, current) location pairs of its handling
    units whose location changed, with their frequency. An unknown previous location (⊥) counts
    as a change.

    Args:
        relations: Relations frame with columns event, activity, is_movement, loc_k and ploc_k.
        level: Level k.

    Returns:
        pl.DataFrame: Columns event, activity, previous (null = ⊥), current, count;
        one row per event and route.
    """
    current, previous = pl.col(c.loc(level)), pl.col(c.ploc(level))
    return (
        relations.filter(pl.col(c.IS_MOVEMENT) & (previous.is_null() | (previous != current)))
        .group_by(c.EVENT, c.ACTIVITY, previous.alias("previous"), current.alias("current"))
        .agg(pl.len().cast(pl.UInt32).alias("count"))
        .sort(c.EVENT, "previous", "current", nulls_last=True)
    )


def activity_routes(routes: pl.DataFrame) -> pl.DataFrame:
    """route(a): multiset sum of move(e) over the events of each activity.

    Args:
        routes: Output of `event_routes`.

    Returns:
        pl.DataFrame: Columns activity, previous, current, count.
    """
    return (
        routes.group_by(c.ACTIVITY, "previous", "current")
        .agg(pl.col("count").sum())
        .sort(c.ACTIVITY, "count", descending=[False, True])
    )
