"""API routes of the settings bar (`global_settings.py`): read and change the settings of a log.

Documented in docs/pages/settings-bar.md.
"""

from fastapi import APIRouter, HTTPException
from ocelescope_backend.app.dependencies import ApiOcel, ApiSession
from pydantic import BaseModel

from ocelescope_module_location_based_ocpm.api_models import Message
from ocelescope_module_location_based_ocpm.configuration_routes import (
    OcelVersion,
    State,
    _cache_derivation,
    log_version,
    run_derivation,
)
from ocelescope_module_location_based_ocpm.global_settings import (
    GlobalSettings,
    SettingsState,
    SettingsUpdate,
    effective_config,
    settings_state,
    with_update,
)
from ocelescope_module_location_based_ocpm.state import CachedDerivation, fingerprint

router = APIRouter()


class SettingsResult(BaseModel):
    """Outcome of a change in the settings bar.

    Attributes:
        applied: True if the change is in effect; False if deriving with it gave blocking errors (the previous
            settings stay).
        settings: The settings now in effect.
        errors: Blocking errors of the derivation with the change.
        notices: Notices of the derivation with the change.
    """

    applied: bool
    settings: SettingsState
    errors: list[Message] = []
    notices: list[Message] = []


@router.get("/{ocel_id}/settings", operation_id="getSettings")
def get_settings(ocel_id: str, state: State) -> SettingsState:
    """The settings bar of a log: level, transformations as processing operations, Locations: low | high."""
    return settings_state(state.configs.get(ocel_id), state.settings.get(ocel_id))


@router.put("/{ocel_id}/settings", operation_id="updateSettings")
def update_settings(
    ocel_id: str,
    body: SettingsUpdate,
    ocel: ApiOcel,
    session: ApiSession,
    state: State,
    ocel_version: OcelVersion = "filtered",
    view_id: str | None = None,
) -> SettingsResult:
    """Change settings of the settings bar; they apply to every page.

    The level and "transformation events count as processing operations" are written into the applied
    configuration, Locations: low | high into the log's settings. The log is derived with the change right away
    (or taken from the cache), so blocking errors show at the bar and the pages open without waiting; with
    errors nothing changes.

    Raises:
        HTTPException: 409 if no configuration is applied; 422 for Locations: high without high-level locations.
    """
    config = state.configs.get(ocel_id)
    if config is None:
        raise HTTPException(status_code=409, detail="No configuration applied for this log yet.")
    if body.location_mode == "high" and config.high_level_locations is None:
        raise HTTPException(status_code=422, detail="No high-level locations are configured.")
    new_config = with_update(config, body)
    previous = state.settings.get(ocel_id) or GlobalSettings()
    new_settings = previous if body.location_mode is None else previous.model_copy(update={"location_mode": body.location_mode})
    effective = effective_config(new_config, new_settings)
    key = fingerprint(effective, log_version(session, ocel_id, ocel_version, view_id), state.tables)
    notices: list[Message] = []
    cached = state.cache.get(ocel_id)
    if (cached is None or cached.key != key) and state.recall(ocel_id, key) is None:
        result = run_derivation(ocel, effective, state)
        if isinstance(result, list) or result.errors:
            errors = result if isinstance(result, list) else [Message.of(e) for e in result.errors]
            return SettingsResult(applied=False, settings=settings_state(config, previous), errors=errors)
        notices = [Message.of(n) for n in result.notices]
        _cache_derivation(state, session, ocel_id, CachedDerivation(key=key, derivation=result), ocel_version, view_id)
    state.configs[ocel_id] = new_config
    state.settings[ocel_id] = new_settings
    return SettingsResult(applied=True, settings=settings_state(new_config, new_settings), notices=notices)
