"""Location context for visits: the location mapping agg, the vehicles V and the storage units W
(`overview/Single Level Visit Mappings.md`, "Specific new notations").

Draft: the input format is not decided yet. Until then, the context is read from a table with one row per
location (e.g. `data/running_example/inputs/locations.csv`).
"""

from dataclasses import dataclass, field

import polars as pl


@dataclass
class LocationContext:
    """The location context.

    Attributes:
        agg: Low-level location -> high-level location (partial; unmapped locations are their own
            high-level location).
        vehicles: The set V.
        storage_units: The set W.
    """

    agg: dict[str, str] = field(default_factory=dict)
    vehicles: set[str] = field(default_factory=set)
    storage_units: set[str] = field(default_factory=set)


def location_context(
    table: pl.DataFrame,
    location: str = "location",
    high_level: str = "high_level",
    is_vehicle: str = "is_vehicle",
    is_storage: str = "is_storage",
) -> LocationContext:
    """Read the location context from a table with one row per location.

    Args:
        table: The table; an empty high-level cell leaves the location unmapped, and the vehicle and
            storage columns are optional (missing = no vehicles / no storage units).
        location: Column of the low-level location.
        high_level: Column of its high-level location agg(l).
        is_vehicle: Boolean column: l ∈ V.
        is_storage: Boolean column: l ∈ W.

    Returns:
        LocationContext: agg, V and W.
    """

    def flagged(column: str) -> set[str]:
        """Locations whose boolean `column` is true (empty set if the column is missing)."""
        if column not in table.columns:
            return set()
        return set(table.filter(pl.col(column).fill_null(False))[location].to_list())

    agg = {}
    if high_level in table.columns:
        mapped = table.filter(pl.col(high_level).is_not_null())
        agg = dict(
            zip(mapped[location].to_list(), mapped[high_level].to_list(), strict=True)
        )
    return LocationContext(
        agg=agg, vehicles=flagged(is_vehicle), storage_units=flagged(is_storage)
    )
