"""Key numbers tiles (concept section "Key Numbers").

The big numbers describe the whole log at the selected level. With an active page filter,
each tile also gets the filtered value (concept section "Filter Effect", "Key numbers").
"""

import polars as pl
from pydantic import BaseModel

from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.derivation.pipeline import Derivation
from ocelescope_module_location_based_ocpm.overview.filters import PageFilter, event_table, passing_relations


class TypeCount(BaseModel):
    """Number of handling units of one object type."""

    object_type: str
    count: int


class ActivityCount(BaseModel):
    """Number of events of one activity."""

    activity: str
    count: int


class FilteredNumbers(BaseModel):
    """The tiles' values under the page filter.

    Attributes:
        handling_units: Kept handling units.
        agreed_located_events: Kept events with eloc(e) ≠ ⊥ (eloc of the whole event; under hat-hl in
            high-level mode).
        relations: Passing relations.
        located_relations: Passing relations with loc ≠ ⊥.
        movement_events: Kept movement events.
        locations: Distinct locations in the passing relations, by the location role: loc
            for "after", ploc for "before", both for "either" (hl / phl in high-level mode).
        transformation_events: Kept transformation events.
        processing_operations: Kept processing operations.
    """

    handling_units: int
    agreed_located_events: int
    relations: int
    located_relations: int
    movement_events: int
    locations: int
    transformation_events: int
    processing_operations: int = 0


class KeyNumbers(BaseModel):
    """The seven key number tiles.

    Attributes:
        handling_units: |HU|, including handling units without any event.
        handling_units_per_type: |HU| per object type, largest first (ties alphabetical).
        events: Number of events in the log.
        agreed_located_events: Events with eloc(e) ≠ ⊥ at the selected level (under hat-hl in high-level mode).
        agreed_high_level_only: Located events that agree under hat-hl but not under loc (hover of the tile);
            0 without high-level locations.
        relations: Number of hu-event relations |E2HU|.
        located_relations: Relations with loc ≠ ⊥ at the selected level.
        level: The selected level k.
        movement_events: |M|.
        location_mode: "low" or "high": the level the location counts refer to.
        locations: |L|, the distinct locations in uloc ∪ puloc; |HL| = |agg(L)| in high-level mode.
        target_locations: Distinct locations in uloc (agg(uloc) in high-level mode).
        pickup_locations: Distinct locations in puloc (after ignoring pickups of non-movement
            events; agg(puloc) in high-level mode); None if no pickup locations are configured.
        other_level_locations: |HL| in low-level mode, |L| in high-level mode; None without high-level locations.
        vehicles: |V|; None if not configured.
        storage_units: |W|; None if not configured.
        transformation_events: |T|; None if no transformation events are configured.
        transformation_activities: Events of T per activity, largest first (ties alphabetical);
            empty if there are none.
        movement_activities: Events of M per activity, largest first (ties alphabetical).
        processing_operations: |P|.
        processing_activities: Events of P per activity, largest first (ties alphabetical).
        processing_default: True if P is not configured (P = T).
        filtered: The values under the page filter; None if no filter is active.
    """

    handling_units: int
    handling_units_per_type: list[TypeCount]
    events: int
    agreed_located_events: int
    agreed_high_level_only: int = 0
    relations: int
    located_relations: int
    level: int
    movement_events: int
    location_mode: str = "low"
    locations: int
    target_locations: int
    pickup_locations: int | None
    other_level_locations: int | None = None
    vehicles: int | None = None
    storage_units: int | None = None
    transformation_events: int | None
    transformation_activities: list[ActivityCount]
    movement_activities: list[ActivityCount]
    processing_operations: int = 0
    processing_activities: list[ActivityCount] = []
    processing_default: bool = True
    filtered: FilteredNumbers | None = None


def _distinct(column: pl.Series) -> set[str]:
    """Distinct provided values of a column (null is ⊥ and not counted)."""
    return set(column.drop_nulls().to_list())


def _per_activity(events: pl.DataFrame, flag: str) -> list[ActivityCount]:
    """Events with `flag` set, counted per activity, largest first (ties alphabetical).

    Args:
        events: The derivation's events frame.
        flag: Boolean column selecting the events, e.g. is_movement.

    Returns:
        list[ActivityCount]: One entry per activity; empty if no event has the flag.
    """
    counted = (
        events.filter(pl.col(flag))
        .group_by(c.ACTIVITY)
        .agg(pl.len().alias("count"))
        .sort(["count", c.ACTIVITY], descending=[True, False])
    )
    return [ActivityCount(activity=a, count=n) for a, n in counted.rows()]


def filtered_numbers(derivation: Derivation, page_filter: PageFilter) -> FilteredNumbers:
    """The tiles' values under the page filter.

    Args:
        derivation: The current derivation.
        page_filter: The filter bar's state.

    Returns:
        FilteredNumbers: Values counted over kept events, kept handling units and passing relations.
    """
    passing = passing_relations(derivation, page_filter)
    kept = passing.unique(c.EVENT)
    eloc = event_table(derivation, page_filter.high).select(c.EVENT, "eloc")
    role = page_filter.location_role
    low, pickup = ("hl", "phl") if page_filter.high else ("loc", "ploc")
    columns = {"after": [low], "before": [pickup], "either": [low, pickup]}[role]
    locations = set().union(*(_distinct(passing[column]) for column in columns))
    return FilteredNumbers(
        handling_units=passing[c.HU].n_unique(),
        agreed_located_events=kept.join(eloc, on=c.EVENT)["eloc"].is_not_null().sum(),
        relations=passing.height,
        located_relations=int(passing["loc"].is_not_null().sum()),
        movement_events=int(kept[c.IS_MOVEMENT].sum()),
        locations=len(locations),
        transformation_events=int(kept[c.IS_TRANSFORMATION].sum()),
        processing_operations=int(kept[c.IS_PROCESSING].sum()),
    )


def key_numbers(derivation: Derivation, page_filter: PageFilter | None = None) -> KeyNumbers:
    """Compute the key numbers of a derivation.

    Args:
        derivation: The current derivation (without blocking errors).
        page_filter: The filter bar's state; the filtered values are only computed if a
            filter is active.

    Returns:
        KeyNumbers: The tiles' numbers at `derivation.level`.
    """
    hus = derivation.handling_units
    per_type = (
        hus.group_by(c.OBJECT_TYPE)
        .agg(pl.len().alias("count"))
        .sort(["count", c.OBJECT_TYPE], descending=[True, False])
    )
    page_filter = page_filter or PageFilter()
    high = page_filter.high and derivation.has_high_level
    events = derivation.events
    low_agreed = derivation.event_locations[derivation.level]["eloc"].is_not_null().sum()
    high_agreed = derivation.hl_event_locations["eloc"].is_not_null().sum() if derivation.has_high_level else low_agreed
    targets = _distinct(events[c.ULOC])
    pickups = _distinct(events[c.PULOC])
    agg = derivation.context.agg
    high_level = {agg.get(loc, loc) for loc in targets | pickups}
    if high:
        targets, pickups = {agg.get(loc, loc) for loc in targets}, {agg.get(loc, loc) for loc in pickups}
    other_level = (len(derivation.locations) if high else len(high_level)) if derivation.has_high_level else None
    config = derivation.config
    context = derivation.context
    return KeyNumbers(
        handling_units=hus.height,
        handling_units_per_type=[TypeCount(object_type=t, count=n) for t, n in per_type.rows()],
        events=events.height,
        agreed_located_events=int(high_agreed if high else low_agreed),
        agreed_high_level_only=int(high_agreed - low_agreed),
        relations=derivation.relations.height,
        located_relations=int(derivation.relations[derivation.loc].is_not_null().sum()),
        level=derivation.level,
        movement_events=int(events[c.IS_MOVEMENT].sum()),
        location_mode="high" if high else "low",
        locations=len(targets | pickups),
        target_locations=len(targets),
        pickup_locations=None if config.pickup_locations is None else len(pickups),
        other_level_locations=other_level,
        vehicles=None if config.vehicles is None else len(context.vehicles),
        storage_units=None if config.storage_units is None else len(context.storage_units),
        transformation_events=None if config.transformation_events is None else int(events[c.IS_TRANSFORMATION].sum()),
        transformation_activities=_per_activity(events, c.IS_TRANSFORMATION),
        movement_activities=_per_activity(events, c.IS_MOVEMENT),
        processing_operations=int(events[c.IS_PROCESSING].sum()),
        processing_activities=_per_activity(events, c.IS_PROCESSING),
        processing_default=config.processing_operations is None,
        filtered=filtered_numbers(derivation, page_filter) if page_filter.active else None,
    )
