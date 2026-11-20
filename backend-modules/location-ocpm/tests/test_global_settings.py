"""Settings bar (`global_settings.py`, `settings_routes.py`): level, transformations as processing operations and
Locations: low | high, applied to every page through the effective configuration.

Running example with its configuration file (`data/running_example/configuration.json`): A1, A2 -> A; B1 -> B;
T unmapped; P = T plus label.
"""

import json

import pytest
from fastapi import HTTPException

from ocelescope_module_location_based_ocpm import configuration_routes as routes
from ocelescope_module_location_based_ocpm import overview_routes
from ocelescope_module_location_based_ocpm.derivation.config import DerivationConfig, ProcessingOperations
from ocelescope_module_location_based_ocpm.global_settings import (
    GlobalSettings,
    SettingsUpdate,
    effective_config,
    effective_location_mode,
    updated,
)
from ocelescope_module_location_based_ocpm.overview.key_numbers import key_numbers
from ocelescope_module_location_based_ocpm.settings_routes import get_settings, update_settings
from ocelescope_module_location_based_ocpm.state import RECENT_PER_LOG

from conftest import EXAMPLE, example_config
from test_configuration_api import FakeSession


@pytest.fixture
def session(request) -> FakeSession:
    """A fresh session per test."""
    return FakeSession(request.node.name)


@pytest.fixture
def state(session):
    """The module state of the session, with the running example's location table uploaded."""
    state = routes.get_state(session)
    path = EXAMPLE / "inputs" / "locations.csv"
    state.add_table(path.name, path.read_bytes())
    return state


@pytest.fixture
def context_config() -> DerivationConfig:
    """The running example's configuration file (with high-level locations, vehicles, storage units, P = T + label)."""
    return DerivationConfig.model_validate(json.loads((EXAMPLE / "configuration.json").read_text()))


def test_defaults_without_and_with_high_level_locations(context_config):
    plain = example_config()
    assert effective_location_mode(plain, None) == "low"
    assert effective_location_mode(plain, GlobalSettings(location_mode="high")) == "low"
    assert effective_location_mode(context_config, None) == "high"
    assert effective_config(plain, None).level == 3
    assert effective_config(plain, None).processing_operations is None  # P = T, shown as the default


def test_low_mode_uses_the_identity(context_config):
    """Low mode: the effective configuration has no high-level locations, so hl^k = loc^k."""
    low = effective_config(context_config, GlobalSettings(location_mode="low"))
    assert low.high_level_locations is None and low.vehicles == context_config.vehicles
    assert effective_config(context_config, None).high_level_locations == context_config.high_level_locations


def test_settings_override_level_and_processing(context_config):
    """The configuration's own level and processing choice are ignored; the bar's apply."""
    settings = updated(None, SettingsUpdate(level=1, include_transformations=False))
    assert settings == GlobalSettings(level=1, include_transformations=False)
    effective = effective_config(context_config.model_copy(update={"level": 0}), settings)
    assert effective.level == 1
    processing = effective.processing_operations
    assert processing.selection == context_config.processing_operations.selection and not processing.include_transformations
    assert effective_config(example_config(), settings).processing_operations == ProcessingOperations(include_transformations=False)


def test_new_log_uses_the_defaults(ocel, session, state, context_config):
    """A configuration file with level 0 is applied at Level 3, the default of the bar."""
    assert routes.apply_config("log", context_config.model_copy(update={"level": 0}), ocel, session, state).applied
    assert get_settings("log", state).level == 3
    assert routes.current_derivation("log", ocel, session, state).level == 3


def test_routes_apply_settings_to_every_page(ocel, session, state, context_config):
    assert not get_settings("log", state).configured
    assert routes.apply_config("log", context_config, ocel, session, state).applied
    settings = get_settings("log", state)
    assert settings.location_mode == "high" and settings.high_level_available and settings.level == 3

    # Overview: the filter takes its location mode from the settings bar.
    page_filter = overview_routes.get_page_filter("log", state)
    derivation = routes.current_derivation("log", ocel, session, state)
    assert page_filter.high and derivation.has_high_level
    assert key_numbers(derivation, page_filter).locations == 3  # A, B, T

    result = update_settings("log", SettingsUpdate(location_mode="low"), ocel, session, state)
    assert result.applied and result.settings.location_mode == "low"
    derivation = routes.current_derivation("log", ocel, session, state)
    assert not derivation.has_high_level
    page_filter = overview_routes.get_page_filter("log", state)
    assert not page_filter.high and key_numbers(derivation, page_filter).locations == 4  # A1, A2, B1, T
    assert routes.get_config("log", state).config == context_config  # the configuration keeps its input

    result = update_settings("log", SettingsUpdate(level=1, include_transformations=False), ocel, session, state)
    assert result.applied and result.settings.level == 1 and not result.settings.include_transformations
    derivation = routes.current_derivation("log", ocel, session, state)
    assert derivation.level == 1
    assert routes.get_config("log", state).config == context_config  # the configuration is unchanged
    assert routes.apply_config("log", context_config, ocel, session, state).applied  # re-applying keeps the bar
    assert get_settings("log", state).level == 1 and routes.current_derivation("log", ocel, session, state).level == 1


def test_switching_back_reuses_the_cached_derivation(ocel, session, state, context_config):
    assert routes.apply_config("log", context_config, ocel, session, state).applied
    high = routes.current_derivation("log", ocel, session, state)
    update_settings("log", SettingsUpdate(location_mode="low"), ocel, session, state)
    update_settings("log", SettingsUpdate(location_mode="high"), ocel, session, state)
    assert routes.current_derivation("log", ocel, session, state) is high
    assert len(state.recent["log"]) == RECENT_PER_LOG


def test_high_without_high_level_locations_is_refused(ocel, session, state):
    with pytest.raises(HTTPException) as raised:
        update_settings("log", SettingsUpdate(level=2), ocel, session, state)
    assert raised.value.status_code == 409
    assert routes.apply_config("log", example_config(), ocel, session, state).applied
    with pytest.raises(HTTPException) as raised:
        update_settings("log", SettingsUpdate(location_mode="high"), ocel, session, state)
    assert raised.value.status_code == 422


def test_adding_high_level_locations_switches_to_high(ocel, session, state, context_config):
    assert routes.apply_config("log", context_config, ocel, session, state).applied
    update_settings("log", SettingsUpdate(location_mode="low"), ocel, session, state)
    assert routes.apply_config("log", context_config, ocel, session, state).applied  # unchanged input: stays low
    assert get_settings("log", state).location_mode == "low"
    assert routes.apply_config("log", example_config(), ocel, session, state).applied
    assert get_settings("log", state).location_mode == "low" and not get_settings("log", state).high_level_available
    assert routes.apply_config("log", context_config, ocel, session, state).applied  # added again: default high
    assert get_settings("log", state).location_mode == "high"
