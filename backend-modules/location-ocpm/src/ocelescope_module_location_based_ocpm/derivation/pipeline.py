"""Run the whole location derivation on an OCEL."""

from dataclasses import dataclass, field

import polars as pl
from ocelescope import OCEL

from . import columns as c
from .agreement import event_locations
from .config import DerivationConfig
from .flags import (
    f1_partial_movement,
    f2_never_located,
    f3_mixed_pickup,
    f4_location_gap,
    f5_movement_disagreement,
)
from .inputs import resolve_inputs
from .levels import add_before, add_loc_0, add_loc_1, add_loc_2, add_loc_3, add_ploc
from .messages import BlockingError, Notice
from .requirements import check_requirements


@dataclass
class Flags:
    """Flags F1-F5 at the selected level, on the whole log.

    Attributes:
        f1: Partial movement (event ids).
        f2: Never located (handling units).
        f3: Mixed pickup (event ids).
        f4: Location gap (handling units).
        f5: Movement disagreement (columns event, kind).
    """

    f1: pl.Series
    f2: pl.Series
    f3: pl.Series
    f4: pl.Series
    f5: pl.DataFrame


@dataclass
class Derivation:
    """Result of `derive`.

    Attributes:
        config: The configuration used.
        relations: One row per hu-event relation with the inputs (see `inputs.ResolvedInputs`) and,
            for every level k, loc_k, before_k and ploc_k. Empty if there are blocking errors.
        events: All events with M, T, uloc, puloc.
        event_locations: For every level k, agreement, eloc and locatedness per event
            (see `agreement.event_locations`).
        flags: Flags at the selected level; None if there are blocking errors.
        notices: Non-blocking reports of the input resolution.
        errors: Blocking errors (input resolution and RQ1-RQ3); if not empty, nothing is derived.
        handling_units: All handling units with columns hu, object_type (also those without events).
    """

    config: DerivationConfig
    relations: pl.DataFrame
    events: pl.DataFrame
    event_locations: dict[int, pl.DataFrame] = field(default_factory=dict)
    flags: Flags | None = None
    notices: list[Notice] = field(default_factory=list)
    errors: list[BlockingError] = field(default_factory=list)
    handling_units: pl.DataFrame = field(default_factory=pl.DataFrame)

    @property
    def level(self) -> int:
        """The selected level k."""
        return self.config.level

    @property
    def loc(self) -> str:
        """Column of the selected current location loc = loc_k."""
        return c.loc(self.level)

    @property
    def ploc(self) -> str:
        """Column of the selected previous location ploc = ploc_k."""
        return c.ploc(self.level)


def derive_levels(relations: pl.DataFrame, events: pl.DataFrame) -> tuple[pl.DataFrame, dict[int, pl.DataFrame]]:
    """Add loc_k, before_k and ploc_k for all levels, and compute the event locations per level.

    Args:
        relations: Resolved relations (requirements must hold).
        events: All events.

    Returns:
        tuple[pl.DataFrame, dict[int, pl.DataFrame]]: The relations with all level columns;
        agreement, eloc and locatedness per event for every level.
    """
    relations = add_loc_2(add_loc_1(add_loc_0(relations)))
    eloc = {level: event_locations(relations, events, c.loc(level)) for level in (0, 1, 2)}
    relations = add_loc_3(relations, eloc[2].select(c.EVENT, "eloc"))
    eloc[3] = event_locations(relations, events, c.loc(3))
    for level in c.LEVELS:
        relations = add_ploc(add_before(relations, level), level)
    return relations, eloc


def compute_flags(relations: pl.DataFrame, level: int) -> Flags:
    """Compute F1-F5 at one level.

    Args:
        relations: Relations with the level columns (see `derive_levels`).
        level: Selected level k.

    Returns:
        Flags: The flagged events and handling units.
    """
    return Flags(
        f1=f1_partial_movement(relations, level),
        f2=f2_never_located(relations),
        f3=f3_mixed_pickup(relations, level),
        f4=f4_location_gap(relations, level),
        f5=f5_movement_disagreement(relations, level),
    )


def derive(ocel: OCEL, config: DerivationConfig, tables: dict[str, pl.DataFrame] | None = None) -> Derivation:
    """Resolve the inputs, check RQ1-RQ3 and derive locations, agreement and flags.

    Args:
        ocel: The log.
        config: The user's choices, including the selected level.
        tables: User tables by name (only needed for table options).

    Returns:
        Derivation: The result. If there are blocking errors, only `errors`, `notices`
        and the resolved inputs are filled.
    """
    resolved = resolve_inputs(ocel, config, tables)
    # Requirements are only checked on clean inputs: e.g. an event with conflicting table
    # locations has no target and would also show up as an RQ2 violation.
    errors = resolved.errors or check_requirements(resolved.relations, resolved.events)
    result = Derivation(
        config=config,
        relations=resolved.relations,
        events=resolved.events,
        notices=resolved.notices,
        errors=errors,
        handling_units=resolved.handling_units,
    )
    if errors:
        return result
    result.relations, result.event_locations = derive_levels(resolved.relations, resolved.events)
    result.flags = compute_flags(result.relations, config.level)
    return result
