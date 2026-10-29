"""Agreement and agreed event locations eloc (`overview/Deriving Locations.md`, box "Location Agreement").

Locatedness lives in `locatedness.py`; `event_locations` combines both per event.
"""

import polars as pl

from . import columns as c
from .locatedness import event_locatedness
# Re-exported so that older imports from `agreement` (e.g. on open branches) keep working.
from .locatedness import FULLY, PARTIALLY, UNLOCATED, hu_locatedness  # noqa: F401


def event_agreement(relations: pl.DataFrame, events: pl.DataFrame, location: str) -> pl.DataFrame:
    """Agreement and eloc of every event under a location function λ.

    An event is agreeing if no two of its handling units have different locations ≠ ⊥
    (⊥ does not count against agreement). eloc is its unique location ≠ ⊥ if there is exactly
    one, else ⊥ (disagreeing events and events without any located relation).

    Args:
        relations: Relations frame with columns event and `location`.
        events: All events (column event), so that events without handling units are included
            (as agreeing, eloc ⊥).
        location: Column holding λ, e.g. "loc_2".

    Returns:
        pl.DataFrame: Columns event, n_locations (distinct locations ≠ ⊥), agreeing (bool), eloc,
        in the order of `events`.
    """
    per_event = relations.group_by(c.EVENT).agg(
        pl.col(location).drop_nulls().n_unique().alias("n_locations"),
        pl.col(location).drop_nulls().first().alias("first_location"),
    )
    return (
        events.select(c.EVENT)
        .join(per_event, on=c.EVENT, how="left", maintain_order="left")
        .with_columns(pl.col("n_locations").fill_null(0).cast(pl.UInt32))
        .with_columns(
            (pl.col("n_locations") <= 1).alias("agreeing"),
            pl.when(pl.col("n_locations") == 1).then(pl.col("first_location")).otherwise(None).alias("eloc"),
        )
        .select(c.EVENT, "n_locations", "agreeing", "eloc")
    )


def event_locations(relations: pl.DataFrame, events: pl.DataFrame, location: str) -> pl.DataFrame:
    """Locatedness, agreement and eloc of every event under λ (`event_locatedness` + `event_agreement`).

    Args:
        relations: Relations frame with columns event and `location`.
        events: All events (column event).
        location: Column holding λ, e.g. "loc_2".

    Returns:
        pl.DataFrame: Columns event, n_relations, n_located, agreeing (bool), eloc, located.
    """
    return (
        event_locatedness(relations, events, location)
        .join(event_agreement(relations, events, location), on=c.EVENT, how="left", maintain_order="left")
        .select(c.EVENT, "n_relations", "n_located", "agreeing", "eloc", "located")
    )
