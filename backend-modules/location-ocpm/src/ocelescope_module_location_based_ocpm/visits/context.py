"""Location context for visits: the location mapping agg, the vehicles V and the storage units W
(`overview/concepts/Visit Mappings.md`, "Specific new notations").

Also `add_high_level_locations`, which applies agg to the relations (hat-hl), and `naming_clashes`, the flag
for auto-completed locations whose name is also a provided high-level location.

Draft: the input format is not decided yet. Until then, the context is read from a table with one row per
location (e.g. `data/running_example/inputs/locations.csv`).
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import TypeVar

import polars as pl

from .columns import HIGH_LEVEL

#: A polars frame, eager or lazy; the functions return the same kind they get.
Frame = TypeVar("Frame", pl.DataFrame, pl.LazyFrame)


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


def add_high_level_locations(
    relations: Frame,
    location: str,
    agg: Mapping[str, str] | None = None,
    high_level: str = HIGH_LEVEL,
) -> Frame:
    """Add hat-hl((e, hu)) = agg(loc((e, hu))) if loc((e, hu)) ≠ ⊥, else ⊥.

    `agg` may be partial: locations it does not map are their own high-level location (identity),
    as in the note's todo "auto-complete via identity function".

    Args:
        relations: One row per hu-event relation with the column `location` (null = ⊥).
        location: Column of the low-level location, e.g. "loc^3".
        agg: Low-level location -> high-level location; None = identity for all.
        high_level: Name of the new column.

    Returns:
        Frame: `relations` with the column `high_level` (null where `location` is null).
    """
    expr = pl.col(location)
    if agg:
        expr = expr.replace(dict(agg))
    return relations.with_columns(expr.alias(high_level))


def naming_clashes(locations: Collection[str], agg: Mapping[str, str] | None = None) -> pl.DataFrame:
    """Flag (concept, section "implementation"): auto-completed locations whose name clashes with a
    provided high-level location.

    agg may be partial and is completed by the identity. If an unmapped low-level location has the same
    name as a high-level location that other locations are mapped to (e.g. B unmapped and B1 -> B), both
    end up at B, one intentionally and one not. Not a blocking error.

    Args:
        locations: All low-level locations L that occur (e.g. the distinct non-null values of loc).
        agg: The provided (partial) mapping; None = identity, which has no clashes.

    Returns:
        pl.DataFrame: Columns location (the unmapped location), mapped_locations (sorted list of the
        locations agg maps to the same name); one row per clash, sorted by location.
    """
    agg = dict(agg or {})
    targets: dict[str, list[str]] = {}
    for low, high in agg.items():
        targets.setdefault(high, []).append(low)
    rows = [
        (name, sorted(targets[name]))
        for name in sorted(set(locations))
        if name not in agg and name in targets
    ]
    return pl.DataFrame(
        rows,
        schema={"location": pl.String, "mapped_locations": pl.List(pl.String)},
        orient="row",
    )
