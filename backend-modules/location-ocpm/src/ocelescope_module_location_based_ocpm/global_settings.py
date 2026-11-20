"""The global settings of the settings bar (Nina, 2026-11-20): choices that apply to every page of the module.

Initial version, three settings:
- **Location function** loc^k: the selected level k (0..3). Stored in the applied configuration
  (`DerivationConfig.level`), so the configuration form, the downloaded configuration and the bar always agree.
- **Transformation events count as processing operations**: P = selection ∪ T or P = selection. Also stored in
  the applied configuration (`ProcessingOperations.include_transformations`).
- **Locations: low | high**: high uses the provided high-level locations (agg); low uses the identity as the
  high-level function (every location is its own high-level location). Stored per log in `GlobalSettings`, since it
  is not an input of the derivation. Default: high if high-level locations are provided; without them, low is
  forced and high cannot be chosen.

Every content route reads the derivation of the *effective* configuration (`effective_config`): the applied
configuration, without high-level locations in low mode. So all pages follow the bar without further parameters.
A new setting adds a field to `GlobalSettings` (if it is not an input of the derivation) or writes into the
configuration (`with_update`), plus a field in `SettingsState` and `SettingsUpdate`.
Documented in docs/pages/settings-bar.md.
"""

from typing import Literal

from pydantic import BaseModel

from ocelescope_module_location_based_ocpm.derivation.config import DerivationConfig, ProcessingOperations

#: Locations: low (identity as the high-level function) or high (the provided high-level locations).
LocationMode = Literal["low", "high"]


class GlobalSettings(BaseModel):
    """The settings of a log that are not part of its configuration.

    Attributes:
        location_mode: The user's choice of Locations: low | high. It only takes effect while high-level locations
            are configured (see `effective_location_mode`).
    """

    location_mode: LocationMode = "high"


class SettingsState(BaseModel):
    """The settings bar of a log as the frontend shows it.

    Attributes:
        configured: False while no configuration is applied (the other values are then the defaults).
        level: Selected level k of the location function loc^k.
        include_transformations: True if the transformation events count as processing operations.
        location_mode: Effective Locations: low | high ("low" whenever no high-level locations are configured).
        high_level_available: True if high-level locations are configured, i.e. "high" can be chosen.
    """

    configured: bool
    level: int = 3
    include_transformations: bool = True
    location_mode: LocationMode = "low"
    high_level_available: bool = False


class SettingsUpdate(BaseModel):
    """A change in the settings bar; fields left out keep their value.

    Attributes:
        level: New level k (0..3).
        include_transformations: New value of "transformation events count as processing operations".
        location_mode: New Locations: low | high.
    """

    level: Literal[0, 1, 2, 3] | None = None
    include_transformations: bool | None = None
    location_mode: LocationMode | None = None


def includes_transformations(config: DerivationConfig) -> bool:
    """Whether the transformation events count as processing operations under a configuration.

    Example: without a processing-operations input, P = T, so the result is True.

    Args:
        config: The applied configuration.

    Returns:
        bool: `ProcessingOperations.include_transformations`, True if processing operations are not configured.
    """
    processing = config.processing_operations
    return processing is None or processing.include_transformations


def effective_location_mode(config: DerivationConfig, settings: GlobalSettings | None) -> LocationMode:
    """The Locations: low | high mode that is in effect.

    Example: with high-level locations from "locations.csv" and no choice yet, "high"; without high-level
    locations always "low", whatever was chosen before.

    Args:
        config: The applied configuration.
        settings: The log's settings; None means the defaults.

    Returns:
        LocationMode: "high" only if high-level locations are configured and the user did not choose "low".
    """
    if config.high_level_locations is None:
        return "low"
    return (settings or GlobalSettings()).location_mode


def effective_config(config: DerivationConfig, settings: GlobalSettings | None) -> DerivationConfig:
    """The configuration every page derives with: in low mode without high-level locations (agg = identity).

    Example: the running example configuration with high-level locations from "locations.csv" in low mode gives the
    same configuration with `high_level_locations=None`, so hl^k = loc^k and A1, A2 stay apart on every page.

    Args:
        config: The applied configuration.
        settings: The log's settings; None means the defaults.

    Returns:
        DerivationConfig: `config` itself in high mode (or without high-level locations), else a copy without them.
    """
    if effective_location_mode(config, settings) == "low" and config.high_level_locations is not None:
        return config.model_copy(update={"high_level_locations": None})
    return config


def with_update(config: DerivationConfig, update: SettingsUpdate) -> DerivationConfig:
    """Write the configuration-stored settings (level, transformations as processing) into a configuration.

    Example: `with_update(config, SettingsUpdate(include_transformations=False))` on a configuration without
    processing operations gives `processing_operations=ProcessingOperations(include_transformations=False)`, i.e.
    P = ∅; with a selection "label" it keeps the selection, so P = {events of label}.

    Args:
        config: The applied configuration.
        update: The change; `location_mode` is ignored here (see `GlobalSettings`).

    Returns:
        DerivationConfig: A copy of `config` with the new values; `config` itself if nothing it stores changes.
    """
    changes: dict = {}
    if update.level is not None and update.level != config.level:
        changes["level"] = update.level
    if update.include_transformations is not None and update.include_transformations != includes_transformations(config):
        processing = config.processing_operations or ProcessingOperations()
        changes["processing_operations"] = processing.model_copy(
            update={"include_transformations": update.include_transformations}
        )
    return config.model_copy(update=changes) if changes else config


def settings_state(config: DerivationConfig | None, settings: GlobalSettings | None) -> SettingsState:
    """The settings bar's values for a log.

    Args:
        config: The applied configuration; None if none is applied yet.
        settings: The log's settings; None means the defaults.

    Returns:
        SettingsState: Level, transformations as processing and the effective location mode.
    """
    if config is None:
        return SettingsState(configured=False)
    return SettingsState(
        configured=True,
        level=config.level,
        include_transformations=includes_transformations(config),
        location_mode=effective_location_mode(config, settings),
        high_level_available=config.high_level_locations is not None,
    )
