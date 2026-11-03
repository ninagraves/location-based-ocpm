"""Run the whole location derivation on an OCEL."""

from dataclasses import dataclass, field

import polars as pl
from ocelescope import OCEL

from . import columns as c
from .agreement import event_locations
from .config import DerivationConfig
from ..visits.context import LocationContext
from .flags import (
    f1_partial_movement,
    f2_never_located,
    f3_mixed_pickup,
    f4_location_gap,
    f5_movement_disagreement,
    f6_naming_clashes,
    f7_simultaneous_processing,
    f8_tied_high_level_locations,
    f9_unlocated_processing,
    f10_vehicle_and_storage,
)
from .location_context import known_locations
from .inputs import resolve_inputs
from .levels import add_before, add_loc_0, add_loc_1, add_loc_2, add_loc_3, add_ploc
from .messages import BlockingError, Notice
from .requirements import check_requirements


@dataclass
class Flags:
    """Flags F1-F10 at the selected level, on the whole log.

    Attributes:
        f1: Partial movement (event ids).
        f2: Never located (handling units).
        f3: Mixed pickup (event ids).
        f4: Location gap (handling units).
        f5: Movement disagreement (columns event, kind).
        f6: Naming clash (columns location, mapped_locations).
        f7: Simultaneous processing (columns hu, time, events, n_events).
        f8: Tied high-level locations, RQ4 (columns hu, time, events, values).
        f9: Unlocated processing (event ids).
        f10: Vehicle and storage unit (locations).
    """

    f1: pl.Series
    f2: pl.Series
    f3: pl.Series
    f4: pl.Series
    f5: pl.DataFrame
    f6: pl.DataFrame = field(default_factory=pl.DataFrame)
    f7: pl.DataFrame = field(default_factory=pl.DataFrame)
    f8: pl.DataFrame = field(default_factory=pl.DataFrame)
    f9: pl.Series = field(default_factory=lambda: pl.Series(c.EVENT, [], dtype=pl.String))
    f10: pl.Series = field(default_factory=lambda: pl.Series(c.LOCATION, [], dtype=pl.String))


@dataclass
class Derivation:
    """Result of `derive`.

    Attributes:
        config: The configuration used.
        relations: One row per hu-event relation with the inputs (see `inputs.ResolvedInputs`) and,
            for every level k, loc^k, before^k, ploc^k and the high-level locations hl^k = agg(loc^k),
            phl^k = agg(ploc^k). Empty if there are blocking errors.
        events: All events with M, T, P, uloc, puloc.
        event_locations: For every level k, agreement, eloc and locatedness per event
            (see `agreement.event_locations`).
        hl_event_locations: The same under hat-hl at the selected level (agreement on high-level locations).
        context: The location context agg, V, W.
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
    hl_event_locations: pl.DataFrame = field(default_factory=pl.DataFrame)
    context: LocationContext = field(default_factory=LocationContext)

    @property
    def level(self) -> int:
        """The selected level k."""
        return self.config.level

    @property
    def loc(self) -> str:
        """Column of the selected current location loc = loc^k."""
        return c.loc(self.level)

    @property
    def ploc(self) -> str:
        """Column of the selected previous location ploc = ploc^k."""
        return c.ploc(self.level)

    @property
    def hl(self) -> str:
        """Column of the selected high-level location hat-hl = agg(loc^k)."""
        return c.hl(self.level)

    @property
    def phl(self) -> str:
        """Column of the selected previous high-level location agg(ploc^k)."""
        return c.phl(self.level)

    @property
    def has_high_level(self) -> bool:
        """True if high-level locations are configured (otherwise hat-hl = loc)."""
        return self.config.high_level_locations is not None

    @property
    def locations(self) -> list[str]:
        """L: all provided target and pickup locations, sorted."""
        return known_locations(self.events)

    @property
    def high_level_locations(self) -> list[str]:
        """HL = agg(L), sorted."""
        return sorted({self.context.agg.get(location, location) for location in self.locations})


def derive_levels(relations: pl.DataFrame, events: pl.DataFrame) -> tuple[pl.DataFrame, dict[int, pl.DataFrame]]:
    """Add loc^k, before^k and ploc^k for all levels, and compute the event locations per level.

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


def add_high_level_columns(relations: pl.DataFrame, agg: dict[str, str]) -> pl.DataFrame:
    """Add hl^k = agg(loc^k) and phl^k = agg(ploc^k) for every level (⊥ stays ⊥; unmapped locations map
    to themselves).

    Args:
        relations: Relations with the level columns.
        agg: The (partial) mapping.

    Returns:
        pl.DataFrame: `relations` with the columns hl^k and phl^k.
    """
    from ..visits.context import add_high_level_locations

    for level in c.LEVELS:
        relations = add_high_level_locations(relations, c.loc(level), agg, c.hl(level))
        relations = add_high_level_locations(relations, c.ploc(level), agg, c.phl(level))
    return relations


def compute_flags(
    relations: pl.DataFrame, level: int, context: LocationContext | None = None, locations: list[str] | None = None
) -> Flags:
    """Compute F1-F10 at one level.

    Args:
        relations: Relations with the level columns (see `derive_levels`) and, for F7-F9, is_processing and
            hl^k (see `add_high_level_columns`).
        level: Selected level k.
        context: The location context (F6, F10); None = empty.
        locations: L (F6); None = no naming clashes.

    Returns:
        Flags: The flagged events, handling units and locations.
    """
    context = context or LocationContext()
    flags = Flags(
        f1=f1_partial_movement(relations, level),
        f2=f2_never_located(relations),
        f3=f3_mixed_pickup(relations, level),
        f4=f4_location_gap(relations, level),
        f5=f5_movement_disagreement(relations, level),
        f6=f6_naming_clashes(locations or [], context.agg),
        f10=f10_vehicle_and_storage(context.vehicles, context.storage_units),
    )
    if c.IS_PROCESSING in relations.columns:
        flags.f7 = f7_simultaneous_processing(relations)
        flags.f9 = f9_unlocated_processing(relations, level)
    if c.hl(level) in relations.columns:
        flags.f8 = f8_tied_high_level_locations(relations, level)
    return flags


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
        context=resolved.context,
    )
    if errors:
        return result
    relations, result.event_locations = derive_levels(resolved.relations, resolved.events)
    result.relations = add_high_level_columns(relations, resolved.context.agg)
    result.hl_event_locations = event_locations(result.relations, resolved.events, c.hl(config.level))
    result.flags = compute_flags(result.relations, config.level, resolved.context, result.locations)
    return result
