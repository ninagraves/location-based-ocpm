"""Page filter bar (concept sections "Page Filter Bar" and "Filter Effect").

Every filter is evaluated on hu-event relations at the selected level. A relation passes if it
passes every active filter (AND across filters, OR within the values of one filter; an exclude
filter removes the matching relations). Events and handling units are kept if at least one of
their relations passes; their properties (locatedness, agreement) always come from the whole
event or trace. Filters never change loc or ploc.
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
FULLY_LOCATED_EVENTS = "[fully located events]"
PARTIALLY_LOCATED_EVENTS = "[partially located events]"
UNLOCATED_EVENTS = "[unlocated events]"
AGREEING_EVENTS = "[agreeing events]"
DISAGREEING_EVENTS = "[disagreeing events]"
#: Special value of the location filters, matching ⊥.
UNKNOWN = "[unknown]"
#: Special values of the object-type filters, matched by the locatedness of the whole trace.
FULLY_LOCATED_HUS = "[fully located HUs]"
PARTIALLY_LOCATED_HUS = "[partially located HUs]"
UNLOCATED_HUS = "[unlocated HUs]"

EVENT_LOCATEDNESS = {FULLY_LOCATED_EVENTS: FULLY, PARTIALLY_LOCATED_EVENTS: PARTIALLY, UNLOCATED_EVENTS: UNLOCATED}
HU_LOCATEDNESS = {FULLY_LOCATED_HUS: FULLY, PARTIALLY_LOCATED_HUS: PARTIALLY, UNLOCATED_HUS: UNLOCATED}

LocationRole = Literal["either", "before", "after"]


class PageFilter(BaseModel):
    """The filter bar's state.

    Attributes:
        activities: Keep relations of events with one of these activities or special values.
        exclude_activities: Remove relations of events with one of these.
        locations: Keep relations at one of these locations ("[unknown]" = ⊥).
        exclude_locations: Remove relations at one of these.
        location_role: Which location a location filter matches: "after" (target) = loc,
            "before" (pickup) = ploc, "either" = one of them.
        object_types: Keep relations of handling units with one of these object types or
            special values.
        exclude_object_types: Remove relations of handling units with one of these.
    """

    activities: list[str] = []
    exclude_activities: list[str] = []
    locations: list[str] = []
    exclude_locations: list[str] = []
    location_role: LocationRole = "either"
    object_types: list[str] = []
    exclude_object_types: list[str] = []

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


def relation_properties(derivation: Derivation) -> pl.DataFrame:
    """The relations with every property a filter can match, at the selected level.

    Args:
        derivation: The current derivation.

    Returns:
        pl.DataFrame: One row per hu-event relation with columns event, hu, activity,
        object_type, is_movement, is_transformation, loc, ploc (the selected level's
        columns, renamed), event_located, event_agreeing, hu_located.
    """
    level = derivation.level
    events = derivation.event_locations[level].select(
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
            pl.col(derivation.loc).alias("loc"),
            pl.col(derivation.ploc).alias("ploc"),
        )
        .join(events, on=c.EVENT, how="left")
        .join(hus, on=c.HU, how="left")
    )


def _activity_match(values: list[str]) -> pl.Expr:
    """Relations whose event matches one of the activity filter values (OR)."""
    expr = pl.col(c.ACTIVITY).is_in(values)
    if MOVEMENT_EVENTS in values:
        expr |= pl.col(c.IS_MOVEMENT)
    if TRANSFORMATION_EVENTS in values:
        expr |= pl.col(c.IS_TRANSFORMATION)
    located = [EVENT_LOCATEDNESS[v] for v in values if v in EVENT_LOCATEDNESS]
    if located:
        expr |= pl.col("event_located").is_in(located)
    if AGREEING_EVENTS in values:
        expr |= pl.col("event_agreeing")
    if DISAGREEING_EVENTS in values:
        expr |= ~pl.col("event_agreeing")
    return expr


def _location_match(values: list[str], role: LocationRole) -> pl.Expr:
    """Relations whose location (by role) is one of the values; "[unknown]" matches ⊥."""

    def matches(column: str) -> pl.Expr:
        expr = pl.col(column).is_in(values).fill_null(False)
        if UNKNOWN in values:
            expr |= pl.col(column).is_null()
        return expr

    if role == "after":
        return matches("loc")
    if role == "before":
        return matches("ploc")
    return matches("loc") | matches("ploc")


def _object_type_match(values: list[str]) -> pl.Expr:
    """Relations whose handling unit matches one of the object-type filter values (OR)."""
    expr = pl.col(c.OBJECT_TYPE).is_in(values)
    located = [HU_LOCATEDNESS[v] for v in values if v in HU_LOCATEDNESS]
    if located:
        expr |= pl.col("hu_located").is_in(located)
    return expr


def passes(page_filter: PageFilter) -> pl.Expr:
    """Boolean expression on `relation_properties`: does a relation pass all active filters?

    Args:
        page_filter: The filter bar's state.

    Returns:
        pl.Expr: True for passing relations.
    """
    expr = pl.lit(True)
    if page_filter.activities:
        expr &= _activity_match(page_filter.activities)
    if page_filter.exclude_activities:
        expr &= ~_activity_match(page_filter.exclude_activities)
    if page_filter.locations:
        expr &= _location_match(page_filter.locations, page_filter.location_role)
    if page_filter.exclude_locations:
        expr &= ~_location_match(page_filter.exclude_locations, page_filter.location_role)
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
    return relation_properties(derivation).filter(passes(page_filter))


class FilterOption(BaseModel):
    """One value a filter offers, with its count over the whole log."""

    value: str
    count: int


class FilterOptions(BaseModel):
    """Values the filter bar offers.

    Attributes:
        activities: Special event values first, then activities; counts are events.
        locations: "[unknown]" first, then locations; counts are relations whose loc or ploc
            is that location (the "either" role).
        object_types: Special handling-unit values first, then object types; counts are
            handling units with at least one relation.
    """

    activities: list[FilterOption]
    locations: list[FilterOption]
    object_types: list[FilterOption]


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
            **{v: pl.col("event_located") == loc for v, loc in EVENT_LOCATEDNESS.items()},
            AGREEING_EVENTS: pl.col("event_agreeing"),
            DISAGREEING_EVENTS: ~pl.col("event_agreeing"),
        },
    )
    hu_specials = special(hus, {v: pl.col("hu_located") == loc for v, loc in HU_LOCATEDNESS.items()})
    either = pl.concat(
        [
            rel.select(c.EVENT, c.HU, pl.col("loc").alias("location")),
            rel.select(c.EVENT, c.HU, pl.col("ploc").alias("location")),
        ]
    ).unique()
    per_location = (
        either.filter(pl.col("location").is_not_null())
        .group_by("location")
        .agg(pl.struct(c.EVENT, c.HU).n_unique().alias("count"))
        .sort(["count", "location"], descending=[True, False])
    )
    unknown = rel.filter(pl.col("loc").is_null() | pl.col("ploc").is_null()).height
    return FilterOptions(
        activities=event_specials + _counted(rel, c.ACTIVITY, c.EVENT),
        locations=[FilterOption(value=UNKNOWN, count=unknown)]
        + [FilterOption(value=v, count=n) for v, n in per_location.rows()],
        object_types=hu_specials + _counted(rel, c.OBJECT_TYPE, c.HU),
    )
