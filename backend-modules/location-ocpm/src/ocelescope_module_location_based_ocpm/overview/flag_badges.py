"""Flag badges (concept section "Flags (whole log)"): one count per flag, never filtered."""

from pydantic import BaseModel

from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.derivation.pipeline import Derivation


class FlagCount(BaseModel):
    """One flag badge.

    Attributes:
        key: "F1" to "F5".
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
        "Handling units without any event with a provided location (a higher level may still locate them).",
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
}


def flag_counts(derivation: Derivation) -> list[FlagCount]:
    """Count the flags of a derivation at its selected level.

    Args:
        derivation: The current derivation (without blocking errors).

    Returns:
        list[FlagCount]: F1 to F5; F4 is left out if no pickup locations are configured
        (it cannot occur then, and the concept hides it).
    """
    flags = derivation.flags
    counts = {
        "F1": flags.f1.n_unique(),
        "F2": flags.f2.n_unique(),
        "F3": flags.f3.n_unique(),
        "F4": flags.f4.n_unique(),
        "F5": flags.f5[c.EVENT].n_unique(),
    }
    if derivation.config.pickup_locations is None:
        del counts["F4"]
    return [
        FlagCount(key=key, label=FLAGS[key][0], count=count, unit=FLAGS[key][1], definition=FLAGS[key][2])
        for key, count in counts.items()
    ]
