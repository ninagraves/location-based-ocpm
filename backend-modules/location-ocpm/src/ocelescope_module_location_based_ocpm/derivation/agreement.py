"""Agreement, agreed event locations (eloc) and locatedness (`overview/Deriving Locations.md`,
boxes "Location Agreement" and "Locatedness")."""

import polars as pl

from . import columns as c

#: Values of the locatedness columns.
FULLY = "fully located"
PARTIALLY = "partially located"
UNLOCATED = "unlocated"


def _locatedness(n_relations: pl.Expr, n_located: pl.Expr) -> pl.Expr:
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


def event_locations(relations: pl.DataFrame, events: pl.DataFrame, location: str) -> pl.DataFrame:
    """Agreement, eloc and locatedness of every event under a location function λ.

    An event is target-agreeing if no two of its handling units have different locations ≠ ⊥
    (⊥ does not count against agreement). eloc is its unique location ≠ ⊥ if it is agreeing,
    else ⊥.

    Args:
        relations: Relations frame with columns event and `location`.
        events: All events (column event), so that events without handling units are included.
        location: Column holding λ, e.g. "loc_2".

    Returns:
        pl.DataFrame: Columns event, n_relations, n_located, agreeing (bool), eloc, located
        (fully located / partially located / unlocated).
    """
    per_event = relations.group_by(c.EVENT).agg(
        pl.len().alias("n_relations"),
        pl.col(location).is_not_null().sum().alias("n_located"),
        pl.col(location).drop_nulls().n_unique().alias("n_locations"),
        pl.col(location).drop_nulls().first().alias("first_location"),
    )
    return (
        events.select(c.EVENT)
        .join(per_event, on=c.EVENT, how="left")
        .with_columns(
            pl.col("n_relations").fill_null(0).cast(pl.UInt32),
            pl.col("n_located").fill_null(0).cast(pl.UInt32),
            pl.col("n_locations").fill_null(0).cast(pl.UInt32),
        )
        .with_columns(
            (pl.col("n_locations") <= 1).alias("agreeing"),
            pl.when(pl.col("n_locations") == 1).then(pl.col("first_location")).otherwise(None).alias("eloc"),
            _locatedness(pl.col("n_relations"), pl.col("n_located")).alias("located"),
        )
        .select(c.EVENT, "n_relations", "n_located", "agreeing", "eloc", "located")
    )


def hu_locatedness(relations: pl.DataFrame, location: str) -> pl.DataFrame:
    """Locatedness of every handling unit under a location function λ.

    Args:
        relations: Relations frame with columns hu and `location`.
        location: Column holding λ, e.g. "loc_3".

    Returns:
        pl.DataFrame: Columns hu, n_relations, n_located, located.
    """
    return (
        relations.group_by(c.HU)
        .agg(pl.len().alias("n_relations"), pl.col(location).is_not_null().sum().alias("n_located"))
        .with_columns(_locatedness(pl.col("n_relations"), pl.col("n_located")).alias("located"))
    )
