"""Locatedness of hu-event relations, events and handling units (`overview/Deriving Locations.md`, box "Locatedness").

All functions take a location column λ (e.g. "loc_3"), so they work on every level.
"""

import polars as pl

from . import columns as c

#: Values of the locatedness columns of events and handling units.
FULLY = "fully located"
PARTIALLY = "partially located"
UNLOCATED = "unlocated"


def locatedness(n_relations: pl.Expr, n_located: pl.Expr) -> pl.Expr:
    """Locatedness from the number of hu-event relations and of located ones.

    Args:
        n_relations: Number of hu-event relations.
        n_located: Number of those with a location ≠ ⊥.

    Returns:
        pl.Expr: "fully located" if all of at least one relation are located, "unlocated" if
        none is (including no relation at all), else "partially located".
    """
    return (
        pl.when((n_relations > 0) & (n_located == n_relations))
        .then(pl.lit(FULLY))
        .when(n_located == 0)
        .then(pl.lit(UNLOCATED))
        .otherwise(pl.lit(PARTIALLY))
    )


def relation_locatedness(relations: pl.DataFrame, location: str) -> pl.DataFrame:
    """Locatedness of every hu-event relation: (e, hu) is located under λ if λ((e, hu)) ≠ ⊥.

    Args:
        relations: Relations frame with columns event, hu and `location`.
        location: Column holding λ, e.g. "loc_3".

    Returns:
        pl.DataFrame: Columns event, hu, `location`, located (bool), in the order of `relations`.
    """
    return relations.select(c.EVENT, c.HU, location, pl.col(location).is_not_null().alias("located"))


def event_locatedness(relations: pl.DataFrame, events: pl.DataFrame, location: str) -> pl.DataFrame:
    """Locatedness of every event under λ, from the locatedness of its hu-event relations.

    Args:
        relations: Relations frame with columns event and `location`.
        events: All events (column event), so that events without handling units are included
            (as unlocated).
        location: Column holding λ, e.g. "loc_3".

    Returns:
        pl.DataFrame: Columns event, n_relations, n_located, located
        (fully located / partially located / unlocated), in the order of `events`.
    """
    per_event = relations.group_by(c.EVENT).agg(
        pl.len().alias("n_relations"),
        pl.col(location).is_not_null().sum().alias("n_located"),
    )
    return (
        events.select(c.EVENT)
        .join(per_event, on=c.EVENT, how="left", maintain_order="left")
        .with_columns(
            pl.col("n_relations").fill_null(0).cast(pl.UInt32),
            pl.col("n_located").fill_null(0).cast(pl.UInt32),
        )
        .with_columns(locatedness(pl.col("n_relations"), pl.col("n_located")).alias("located"))
    )


def hu_locatedness(relations: pl.DataFrame, location: str) -> pl.DataFrame:
    """Locatedness of every handling unit under λ, from the locatedness of its hu-event relations.

    Args:
        relations: Relations frame with columns hu and `location`.
        location: Column holding λ, e.g. "loc_3".

    Returns:
        pl.DataFrame: Columns hu, n_relations, n_located, located, sorted by hu. Handling units
        without events are not in `relations` and therefore not in the result.
    """
    return (
        relations.group_by(c.HU)
        .agg(pl.len().alias("n_relations"), pl.col(location).is_not_null().sum().alias("n_located"))
        .with_columns(locatedness(pl.col("n_relations"), pl.col("n_located")).alias("located"))
        .sort(c.HU)
    )
