"""The global settings of the settings bar (Nina, 2026-11-20): choices that apply to every page of the module.

Initial version, three settings, all stored per log in `GlobalSettings` (Nina, 2026-11-20: level and
"transformation events are processing operations" are not part of the configuration; a new log starts with the
defaults):
- **Location function** loc^k: the selected level k (0..3), default 3.
- **Transformation events count as processing operations**: P = selection ∪ T (default) or P = selection.
- **Locations: low | high**: high uses the provided high-level locations (agg); low uses the identity as the
  high-level function (every location is its own high-level location). Default: high if high-level locations are
  provided; without them, low is forced and high cannot be chosen.

Every content route reads the derivation of the *effective* configuration (`effective_config`): the applied
configuration with the bar's level and processing choice, and without high-level locations in low mode. So all
pages follow the bar without further parameters. The `level` and `include_transformations` fields of a stored or
uploaded `DerivationConfig` are ignored by the module (the package functions still take them).
A new setting adds a field to `GlobalSettings`, `SettingsState` and `SettingsUpdate`, and is applied in
`effective_config` (or read from `ModuleState.settings` by the routes that need it).
Documented in docs/pages/settings-bar.md.
"""

from typing import Literal

from pydantic import BaseModel

from ocelescope_module_location_based_ocpm.derivation.config import DerivationConfig, ProcessingOperations

#: Locations: low (identity as the high-level function) or high (the provided high-level locations).
LocationMode = Literal["low", "high"]


class GlobalSettings(BaseModel):
    """The settings bar of a log (not part of its configuration).

    Attributes:
        level: Selected level k of the location function loc^k.
        include_transformations: True if the transformation events count as processing operations (P ⊇ T).
        location_mode: The user's choice of Locations: low | high. It only takes effect while high-level locations
            are configured (see `effective_location_mode`).
    """

    level: Literal[0, 1, 2, 3] = 3
    include_transformations: bool = True
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
    """The configuration every page derives with: the bar's level and processing choice, and in low mode no
    high-level locations (agg = identity).

    Example: the running example configuration with high-level locations from "locations.csv" and processing
    operations "label", under `GlobalSettings(level=1, include_transformations=False, location_mode="low")`, gives
    the same configuration with `level=1`, `processing_operations=ProcessingOperations(selection=label,
    include_transformations=False)` (P = events of label) and `high_level_locations=None` (hl^k = loc^k).

    Args:
        config: The applied configuration.
        settings: The log's settings; None means the defaults.

    Returns:
        DerivationConfig: A copy of `config` with the settings applied.
    """
    settings = settings or GlobalSettings()
    changes: dict = {"level": settings.level}
    processing = config.processing_operations
    if processing is not None or not settings.include_transformations:
        # Without a processing input and with the default (P = T), None stays None ("default" in the key numbers).
        changes["processing_operations"] = (processing or ProcessingOperations()).model_copy(
            update={"include_transformations": settings.include_transformations}
        )
    if effective_location_mode(config, settings) == "low":
        changes["high_level_locations"] = None
    return config.model_copy(update=changes)


def updated(settings: GlobalSettings | None, update: SettingsUpdate) -> GlobalSettings:
    """The settings after a change in the bar.

    Example: `updated(None, SettingsUpdate(level=1))` gives Level 1 with the other defaults.

    Args:
        settings: The log's settings; None means the defaults.
        update: The change; fields left out keep their value.

    Returns:
        GlobalSettings: A new settings object.
    """
    changes = {key: value for key, value in update.model_dump().items() if value is not None}
    return (settings or GlobalSettings()).model_copy(update=changes)


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
    settings = settings or GlobalSettings()
    return SettingsState(
        configured=True,
        level=settings.level,
        include_transformations=settings.include_transformations,
        location_mode=effective_location_mode(config, settings),
        high_level_available=config.high_level_locations is not None,
    )
