"""Key numbers tiles (concept section "Key Numbers").

All numbers describe the whole log at the selected level. The filtered values shown next to
them follow with the page filter bar.
"""

import polars as pl
from pydantic import BaseModel

from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.derivation.pipeline import Derivation


class TypeCount(BaseModel):
    """Number of handling units of one object type."""

    object_type: str
    count: int


class KeyNumbers(BaseModel):
    """The six key number tiles.

    Attributes:
        handling_units: |HU|, including handling units without any event.
        handling_units_per_type: |HU| per object type, largest first (ties alphabetical).
        events: Number of events in the log.
        agreed_located_events: Events with eloc(e) ≠ ⊥ at the selected level.
        relations: Number of hu-event relations |E2HU|.
        located_relations: Relations with loc ≠ ⊥ at the selected level.
        level: The selected level k.
        movement_events: |M|.
        locations: |L|, the distinct locations in uloc ∪ puloc.
        target_locations: Distinct locations in uloc.
        pickup_locations: Distinct locations in puloc (after ignoring pickups of non-movement
            events); None if no pickup locations are configured.
        transformation_events: |T|; None if no transformation events are configured.
    """

    handling_units: int
    handling_units_per_type: list[TypeCount]
    events: int
    agreed_located_events: int
    relations: int
    located_relations: int
    level: int
    movement_events: int
    locations: int
    target_locations: int
    pickup_locations: int | None
    transformation_events: int | None


def _distinct(column: pl.Series) -> set[str]:
    """Distinct provided values of a column (null is ⊥ and not counted)."""
    return set(column.drop_nulls().to_list())


def key_numbers(derivation: Derivation) -> KeyNumbers:
    """Compute the key numbers of a derivation.

    Args:
        derivation: The current derivation (without blocking errors).

    Returns:
        KeyNumbers: The tiles' numbers at `derivation.level`.
    """
    hus = derivation.handling_units
    per_type = (
        hus.group_by(c.OBJECT_TYPE)
        .agg(pl.len().alias("count"))
        .sort(["count", c.OBJECT_TYPE], descending=[True, False])
    )
    events = derivation.events
    agreed = derivation.event_locations[derivation.level]["eloc"].is_not_null().sum()
    targets = _distinct(events[c.ULOC])
    pickups = _distinct(events[c.PULOC])
    config = derivation.config
    return KeyNumbers(
        handling_units=hus.height,
        handling_units_per_type=[TypeCount(object_type=t, count=n) for t, n in per_type.rows()],
        events=events.height,
        agreed_located_events=int(agreed),
        relations=derivation.relations.height,
        located_relations=int(derivation.relations[derivation.loc].is_not_null().sum()),
        level=derivation.level,
        movement_events=int(events[c.IS_MOVEMENT].sum()),
        locations=len(targets | pickups),
        target_locations=len(targets),
        pickup_locations=None if config.pickup_locations is None else len(pickups),
        transformation_events=None if config.transformation_events is None else int(events[c.IS_TRANSFORMATION].sum()),
    )
