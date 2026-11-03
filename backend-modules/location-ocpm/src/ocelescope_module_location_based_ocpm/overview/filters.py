"""Page filter bar (concept sections "Page Filter Bar" and "Filter Effect").

Every filter is evaluated on hu-event relations at the selected level. A relation passes if it
passes every active filter (AND across filters, OR within the values of one filter; an exclude
filter removes the matching relations). Events and handling units are kept if at least one of
their relations passes; their properties (locatedness, agreement) always come from the whole
event or trace. Filters never change loc or ploc.

Locations: low | high (`PageFilter.location_mode`, concept "Update Overview Page", section 6): filters are always
evaluated on low-level locations; a high-level value ("[high-level] A") stands for its preimage agg⁻¹(A), which is
the same as matching hat-hl (hl, phl). The mode only changes how values are shown and aggregated, and which
agreement "[agreeing / disagreeing events]" use (under hat-hl in high-level mode).
"""

from typing import Literal

import polars as pl
from pydantic import BaseModel

from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.derivation.locatedness import FULLY, PARTIALLY, UNLOCATED, hu_locatedness
from ocelescope_module_location_based_ocpm.derivation.pipeline import Derivation

#: Special values of the activity filters, matched by event properties instead of act(e).
MOVEMENT_EVENTS = "[movement events]"
TRANSFORMATION_EVENTS = "[transformation events]"
PROCESSING_OPERATIONS = "[processing operations]"
FULLY_LOCATED_EVENTS = "[fully located events]"
PARTIALLY_LOCATED_EVENTS = "[partially located events]"
UNLOCATED_EVENTS = "[unlocated events]"
AGREEING_EVENTS = "[agreeing events]"
DISAGREEING_EVENTS = "[disagreeing events]"
#: Special value of the location filters, matching ⊥.
UNKNOWN = "[unknown]"
#: Special values of the location filters, matching locations in V or W (only offered if configured).
VEHICLES = "[vehicles]"
STORAGE_UNITS = "[storage units]"
#: Special values of the object-type filters, matched by the locatedness of the whole trace.
FULLY_LOCATED_HUS = "[fully located HUs]"
PARTIALLY_LOCATED_HUS = "[partially located HUs]"
UNLOCATED_HUS = "[unlocated HUs]"

EVENT_LOCATEDNESS = {FULLY_LOCATED_EVENTS: FULLY, PARTIALLY_LOCATED_EVENTS: PARTIALLY, UNLOCATED_EVENTS: UNLOCATED}
#: Prefixes of single ids and of high-level locations in the filter values (section 7 of the concept).
HIGH_LEVEL_PREFIX = "[high-level] "
HU_PREFIX = "[hu] "
EVENT_PREFIX = "[event] "
#: Most ids returned by a search.
MAX_SEARCH = 20

HU_LOCATEDNESS = {FULLY_LOCATED_HUS: FULLY, PARTIALLY_LOCATED_HUS: PARTIALLY, UNLOCATED_HUS: UNLOCATED}

LocationRole = Literal["either", "before", "after"]
LocationMode = Literal["low", "high"]


def prefixed(values: list[str], prefix: str) -> list[str]:
    """The values starting with `prefix`, without it (e.g. the HU ids of "[hu] s1")."""
    return [v[len(prefix) :] for v in values if v.startswith(prefix)]


class PageFilter(BaseModel):
    """The filter bar's state.

    Attributes:
        activities: Keep relations of events with one of these activities, special values or single events
            ("[event] e5").
        exclude_activities: Remove relations of events with one of these.
        locations: Keep relations at one of these locations ("[unknown]" = ⊥, "[high-level] A" = a location
            of agg⁻¹(A)).
        exclude_locations: Remove relations at one of these.
        location_role: Which location a location filter matches: "after" (target) = loc,
            "before" (pickup) = ploc, "either" = one of them.
        object_types: Keep relations of handling units with one of these object types, special values or
            single handling units ("[hu] s1").
        exclude_object_types: Remove relations of handling units with one of these.
        location_mode: "low" or "high" (Locations: low | high); not a filter, it only changes the display and
            the agreement of "[agreeing / disagreeing events]".
    """

    activities: list[str] = []
    exclude_activities: list[str] = []
    locations: list[str] = []
    exclude_locations: list[str] = []
    location_role: LocationRole = "either"
    object_types: list[str] = []
    exclude_object_types: list[str] = []
    location_mode: LocationMode = "low"

    @property
    def active(self) -> bool:
        """True if any filter value is set (the role switch alone filters nothing)."""
        return bool(
            self.activities
            or self.exclude_activities
            or self.locations
            or self.exclude_locations
            or self.object_types
            or self.exclude_object_types
        )

    @property
    def high(self) -> bool:
        """True in high-level mode."""
        return self.location_mode == "high"


def event_table(derivation: Derivation, high: bool = False) -> pl.DataFrame:
    """Locatedness, agreement and eloc of every event at the selected level, under loc or (high) under hat-hl.

    Args:
        derivation: The current derivation.
        high: True for agreement and eloc under hat-hl (falls back to loc without high-level locations).

    Returns:
        pl.DataFrame: Columns of `agreement.event_locations` (event, n_relations, n_located, agreeing, eloc, located).
    """
    if high and derivation.has_high_level:
        return derivation.hl_event_locations
    return derivation.event_locations[derivation.level]


def relation_properties(derivation: Derivation, high: bool = False) -> pl.DataFrame:
    """The relations with every property a filter can match, at the selected level.

    Args:
        derivation: The current derivation.
        high: True for the agreement under hat-hl (high-level mode).

    Returns:
        pl.DataFrame: One row per hu-event relation with columns event, hu, activity,
        object_type, is_movement, is_transformation, is_processing, loc, ploc, hl, phl (the selected level's
        columns, renamed), event_located, event_agreeing, hu_located.
    """
    events = event_table(derivation, high).select(
        c.EVENT, pl.col("located").alias("event_located"), pl.col("agreeing").alias("event_agreeing")
    )
    hus = hu_locatedness(derivation.relations, derivation.loc).select(c.HU, pl.col("located").alias("hu_located"))
    return (
        derivation.relations.select(
            c.EVENT,
            c.HU,
            c.ACTIVITY,
            c.OBJECT_TYPE,
            c.IS_MOVEMENT,
            c.IS_TRANSFORMATION,
            c.IS_PROCESSING,
            pl.col(derivation.loc).alias("loc"),
            pl.col(derivation.ploc).alias("ploc"),
            pl.col(derivation.hl).alias("hl"),
            pl.col(derivation.phl).alias("phl"),
        )
        .join(events, on=c.EVENT, how="left")
        .join(hus, on=c.HU, how="left")
    )


def _activity_match(values: list[str]) -> pl.Expr:
    """Relations whose event matches one of the activity filter values (OR)."""
    expr = pl.col(c.ACTIVITY).is_in(values) | pl.col(c.EVENT).is_in(prefixed(values, EVENT_PREFIX))
    if MOVEMENT_EVENTS in values:
        expr |= pl.col(c.IS_MOVEMENT)
    if TRANSFORMATION_EVENTS in values:
        expr |= pl.col(c.IS_TRANSFORMATION)
    if PROCESSING_OPERATIONS in values:
        expr |= pl.col(c.IS_PROCESSING)
    located = [EVENT_LOCATEDNESS[v] for v in values if v in EVENT_LOCATEDNESS]
    if located:
        expr |= pl.col("event_located").is_in(located)
    if AGREEING_EVENTS in values:
        expr |= pl.col("event_agreeing")
    if DISAGREEING_EVENTS in values:
        expr |= ~pl.col("event_agreeing")
    return expr


def _location_match(
    values: list[str], role: LocationRole, vehicles: set[str] = frozenset(), storage_units: set[str] = frozenset()
) -> pl.Expr:
    """Relations whose location (by role) is one of the values; "[unknown]" matches ⊥, "[vehicles]" a location
    in V, "[storage units]" a location in W, "[high-level] A" a location of agg⁻¹(A) (matched on hl / phl)."""
    locations = set(values)
    high_level = prefixed(values, HIGH_LEVEL_PREFIX)
    if VEHICLES in values:
        locations |= set(vehicles)
    if STORAGE_UNITS in values:
        locations |= set(storage_units)

    def matches(column: str, high_column: str) -> pl.Expr:
        expr = pl.col(column).is_in(sorted(locations)).fill_null(False)
        if high_level:
            expr |= pl.col(high_column).is_in(high_level).fill_null(False)
        if UNKNOWN in values:
            expr |= pl.col(column).is_null()
        return expr

    if role == "after":
        return matches("loc", "hl")
    if role == "before":
        return matches("ploc", "phl")
    return matches("loc", "hl") | matches("ploc", "phl")


def _object_type_match(values: list[str]) -> pl.Expr:
    """Relations whose handling unit matches one of the object-type filter values (OR)."""
    expr = pl.col(c.OBJECT_TYPE).is_in(values) | pl.col(c.HU).is_in(prefixed(values, HU_PREFIX))
    located = [HU_LOCATEDNESS[v] for v in values if v in HU_LOCATEDNESS]
    if located:
        expr |= pl.col("hu_located").is_in(located)
    return expr


def passes(page_filter: PageFilter, derivation: Derivation | None = None) -> pl.Expr:
    """Boolean expression on `relation_properties`: does a relation pass all active filters?

    Args:
        page_filter: The filter bar's state.
        derivation: The current derivation, for V and W of "[vehicles]" and "[storage units]"; None = empty.

    Returns:
        pl.Expr: True for passing relations.
    """
    vehicles = derivation.context.vehicles if derivation else set()
    storage = derivation.context.storage_units if derivation else set()
    expr = pl.lit(True)
    if page_filter.activities:
        expr &= _activity_match(page_filter.activities)
    if page_filter.exclude_activities:
        expr &= ~_activity_match(page_filter.exclude_activities)
    if page_filter.locations:
        expr &= _location_match(page_filter.locations, page_filter.location_role, vehicles, storage)
    if page_filter.exclude_locations:
        expr &= ~_location_match(page_filter.exclude_locations, page_filter.location_role, vehicles, storage)
    if page_filter.object_types:
        expr &= _object_type_match(page_filter.object_types)
    if page_filter.exclude_object_types:
        expr &= ~_object_type_match(page_filter.exclude_object_types)
    return expr


def passing_relations(derivation: Derivation, page_filter: PageFilter) -> pl.DataFrame:
    """The relations that pass the filters, with their properties.

    Args:
        derivation: The current derivation.
        page_filter: The filter bar's state.

    Returns:
        pl.DataFrame: Rows of `relation_properties` that pass.
    """
    return relation_properties(derivation, page_filter.high).filter(passes(page_filter, derivation))


class FilterOption(BaseModel):
    """One value a filter offers, with its count over the whole log."""

    value: str
    count: int


class LocationGroup(BaseModel):
    """A high-level location in the grouped location picker.

    Attributes:
        value: The filter value ("[high-level] A").
        label: The high-level location (A).
        count: Relations whose loc or ploc lies in agg⁻¹(A).
        members: Its locations with their counts (as in `FilterOptions.locations`), largest first.
    """

    value: str
    label: str
    count: int
    members: list[FilterOption]


class FilterOptions(BaseModel):
    """Values the filter bar offers.

    Attributes:
        activities: Special event values first, then activities; counts are events.
        locations: "[unknown]" first, then "[vehicles]" and "[storage units]" (if configured), then locations;
            counts are relations whose loc or ploc
            is that location (the "either" role).
        high_level_locations: The grouped picker: one entry per high-level location with its locations, largest
            first; a location that is its own only member (e.g. an unmapped T) is left out, it appears once
            as a location. Empty without high-level locations.
        object_types: Special handling-unit values first, then object types; counts are
            handling units with at least one relation.
    """

    activities: list[FilterOption]
    locations: list[FilterOption]
    high_level_locations: list[LocationGroup] = []
    object_types: list[FilterOption]


def _either_counts(rel: pl.DataFrame, low: str, high: str) -> pl.DataFrame:
    """Relations per value of `low` / `high` taken from loc or ploc (resp. hl or phl), largest first."""
    either = pl.concat(
        [
            rel.select(c.EVENT, c.HU, pl.col(low).alias("location")),
            rel.select(c.EVENT, c.HU, pl.col(high).alias("location")),
        ]
    ).unique()
    return (
        either.filter(pl.col("location").is_not_null())
        .group_by("location")
        .agg(pl.struct(c.EVENT, c.HU).n_unique().alias("count"))
        .sort(["count", "location"], descending=[True, False])
    )


def location_groups(derivation: Derivation, rel: pl.DataFrame, per_location: dict[str, int]) -> list[LocationGroup]:
    """The high-level entries of the grouped location picker.

    Args:
        derivation: The current derivation.
        rel: `relation_properties` of the derivation.
        per_location: Relations per location (the "either" role).

    Returns:
        list[LocationGroup]: One entry per high-level location with at least one other member than itself,
        largest first (ties alphabetical); empty without high-level locations.
    """
    if not derivation.has_high_level:
        return []
    agg = derivation.context.agg
    members: dict[str, list[str]] = {}
    for location in derivation.locations:
        members.setdefault(agg.get(location, location), []).append(location)
    counts = _either_counts(rel, "hl", "phl")
    groups = []
    for label, count in counts.rows():
        own = members.get(label, [])
        if own == [label]:
            continue
        ordered = sorted(own, key=lambda m: (-per_location.get(m, 0), m))
        groups.append(
            LocationGroup(
                value=HIGH_LEVEL_PREFIX + label,
                label=label,
                count=count,
                members=[FilterOption(value=m, count=per_location.get(m, 0)) for m in ordered],
            )
        )
    return groups


def _counted(frame: pl.DataFrame, column: str, unique: str) -> list[FilterOption]:
    """Count distinct `unique` per value of `column`, largest first (ties alphabetical)."""
    counted = (
        frame.filter(pl.col(column).is_not_null())
        .group_by(column)
        .agg(pl.col(unique).n_unique().alias("count"))
        .sort(["count", column], descending=[True, False])
    )
    return [FilterOption(value=str(v), count=n) for v, n in counted.rows()]


def filter_options(derivation: Derivation) -> FilterOptions:
    """The filter bar's values with their counts over the whole log at the selected level.

    Args:
        derivation: The current derivation.

    Returns:
        FilterOptions: Options per filter.
    """
    rel = relation_properties(derivation)
    events = rel.unique(c.EVENT)
    hus = rel.unique(c.HU)

    def special(frame: pl.DataFrame, values: dict[str, pl.Expr]) -> list[FilterOption]:
        return [FilterOption(value=v, count=int(frame.filter(e).height)) for v, e in values.items()]

    event_specials = special(
        events,
        {
            MOVEMENT_EVENTS: pl.col(c.IS_MOVEMENT),
            TRANSFORMATION_EVENTS: pl.col(c.IS_TRANSFORMATION),
            PROCESSING_OPERATIONS: pl.col(c.IS_PROCESSING),
            **{v: pl.col("event_located") == loc for v, loc in EVENT_LOCATEDNESS.items()},
            AGREEING_EVENTS: pl.col("event_agreeing"),
            DISAGREEING_EVENTS: ~pl.col("event_agreeing"),
        },
    )
    hu_specials = special(hus, {v: pl.col("hu_located") == loc for v, loc in HU_LOCATEDNESS.items()})
    per_location = _either_counts(rel, "loc", "ploc")
    unknown = rel.filter(pl.col("loc").is_null() | pl.col("ploc").is_null()).height
    location_specials = [
        FilterOption(
            value=value,
            count=rel.filter(pl.col("loc").is_in(sorted(members)) | pl.col("ploc").is_in(sorted(members))).height,
        )
        for value, members in ((VEHICLES, derivation.context.vehicles), (STORAGE_UNITS, derivation.context.storage_units))
        if members
    ]
    return FilterOptions(
        activities=event_specials + _counted(rel, c.ACTIVITY, c.EVENT),
        locations=[FilterOption(value=UNKNOWN, count=unknown), *location_specials]
        + [FilterOption(value=v, count=n) for v, n in per_location.rows()],
        high_level_locations=location_groups(derivation, rel, dict(per_location.rows())),
        object_types=hu_specials + _counted(rel, c.OBJECT_TYPE, c.HU),
    )


IdKind = Literal["hu", "event"]


def search_ids(derivation: Derivation, kind: IdKind, query: str, limit: int = MAX_SEARCH) -> list[FilterOption]:
    """Single handling units or events whose id contains `query` (ignoring case), for the filter bar.

    Ids are not listed in the options (logs have up to 10^5 of them) but found by typing.

    Args:
        derivation: The current derivation.
        kind: "hu" (count = events of the handling unit) or "event" (count = handling units of the event).
        query: Part of the id; fewer than two characters return nothing.
        limit: Most ids returned.

    Returns:
        list[FilterOption]: Values with prefix ("[hu] s1", "[event] e5"), ids starting with the query first,
        then alphabetical.
    """
    if len(query.strip()) < 2:
        return []
    column, other, prefix = (c.HU, c.EVENT, HU_PREFIX) if kind == "hu" else (c.EVENT, c.HU, EVENT_PREFIX)
    needle = query.strip().lower()
    found = (
        derivation.relations.group_by(column)
        .agg(pl.col(other).n_unique().alias("count"))
        .filter(pl.col(column).str.to_lowercase().str.contains(needle, literal=True))
        .with_columns((~pl.col(column).str.to_lowercase().str.starts_with(needle)).alias("_later"))
        .sort("_later", column)
        .head(limit)
    )
    return [FilterOption(value=prefix + value, count=count) for value, count in found.select(column, "count").rows()]
