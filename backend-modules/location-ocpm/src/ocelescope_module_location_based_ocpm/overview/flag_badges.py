"""Flag badges (concept section "Flags (whole log)"; F6-F10 from `overview/module/Module Overview.md`): one count
per flag, never filtered."""

from pydantic import BaseModel

from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.derivation.pipeline import Derivation


class FlagCount(BaseModel):
    """One flag badge.

    Attributes:
        key: "F1" to "F10".
        label: Short name, e.g. "Partial movement".
        count: Number of flagged items.
        unit: What is counted ("events" or "handling units").
        definition: Text shown when hovering over the badge.
    """

    key: str
    label: str
    count: int
    unit: str
    definition: str


#: Label, counted unit and hover text per flag, from the concept's flag table.
FLAGS = {
    "F1": (
        "Partial movement",
        "events",
        "Movement events at which at least one handling unit was already at the target.",
    ),
    "F2": (
        "Never located",
        "handling units",
        "Handling units without any event with a provided location. Derived levels may still locate them, "
        "e.g. Level 3 via transformations.",
    ),
    "F3": (
        "Mixed pickup",
        "events",
        "Movement events whose moved handling units came from different previous locations (unknown counts as one). "
        "Handling units already at the target are left out; events with a provided pickup location are never flagged.",
    ),
    "F4": (
        "Location gap",
        "handling units",
        "Handling units picked up somewhere other than their last known location, i.e., they moved without a recorded "
        "movement. A first known location is not a gap.",
    ),
    "F5": (
        "Movement disagreement",
        "events",
        "Located non-movement events at which a handling unit changes location (change without movement), and "
        "movement events at which none does (movement without change; these are also F1).",
    ),
    "F6": (
        "Naming clash",
        "locations",
        "Locations without a high-level location whose name is the high-level location of other locations: both end "
        "up at the same high-level location, one intentionally and one not.",
    ),
    "F7": (
        "Simultaneous processing",
        "handling units",
        "Handling units with two processing operations at the same timestamp. Their order then only follows the event "
        "id, and the waiting time of the second one is 0.",
    ),
    "F8": (
        "Tied high-level locations",
        "handling units",
        "Handling units with two events at the same timestamp at different high-level locations (unknown counts as one; "
        "RQ4). Only possible at Level 0.",
    ),
    "F9": (
        "Unlocated processing",
        "events",
        "Processing operations with a handling unit without a location. Location-based analyses (waiting times, "
        "visit strategies) only use located processing operations.",
    ),
    "F10": (
        "Vehicle and storage unit",
        "locations",
        "Locations that are both a vehicle and a storage unit: they give no stops, but taking a handling unit out of "
        "them resets the waiting clock.",
    ),
}


def flag_counts(derivation: Derivation) -> list[FlagCount]:
    """Count the flags of a derivation at its selected level.

    Args:
        derivation: The current derivation (without blocking errors).

    Returns:
        list[FlagCount]: F1 to F10, leaving out flags whose input is not configured (F4: pickup locations,
        F6: high-level locations, F10: vehicles and storage units) and F8 at Levels 1-3 (it holds there by
        construction).
    """
    flags = derivation.flags
    counts = {
        "F1": flags.f1.n_unique(),
        "F2": flags.f2.n_unique(),
        "F3": flags.f3.n_unique(),
        "F4": flags.f4.n_unique(),
        "F5": flags.f5[c.EVENT].n_unique(),
        "F6": flags.f6.height,
        "F7": flags.f7[c.HU].n_unique() if flags.f7.height else 0,
        "F8": flags.f8[c.HU].n_unique() if flags.f8.height else 0,
        "F9": flags.f9.n_unique(),
        "F10": flags.f10.n_unique(),
    }
    config = derivation.config
    hidden = {
        "F4": config.pickup_locations is None,
        "F6": config.high_level_locations is None,
        "F8": derivation.level != 0,
        "F10": config.vehicles is None or config.storage_units is None,
    }
    counts = {key: count for key, count in counts.items() if not hidden.get(key, False)}
    return [
        FlagCount(key=key, label=FLAGS[key][0], count=count, unit=FLAGS[key][1], definition=FLAGS[key][2])
        for key, count in counts.items()
    ]
