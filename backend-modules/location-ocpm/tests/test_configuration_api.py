"""Configuration routes and caching, called as plain functions with a stand-in session."""

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from ocelescope_module_location_based_ocpm import configuration_routes as routes
from ocelescope_module_location_based_ocpm.derivation.config import DerivationConfig, LocationTable
from ocelescope_module_location_based_ocpm.state import ModuleState

from conftest import EXAMPLE, example_config


class FakeSession:
    """The two things the routes use from Ocelescope's session: module state and filters."""

    def __init__(self):
        self.states = {}
        self.filters = []

    def get_module_state(self, key, state_cls):
        return self.states.setdefault(key, state_cls())

    def get_filter(self, ocel_id):
        return self.filters


@pytest.fixture
def session() -> FakeSession:
    """A fresh session per test."""
    return FakeSession()


@pytest.fixture
def state(session) -> ModuleState:
    """The module state of the session."""
    return routes.get_state(session)


def upload(state: ModuleState, path: Path) -> None:
    """Upload a CSV file as the form does."""
    state.add_table(path.name, path.read_bytes())


def test_options_list_values_with_counts(ocel):
    options = routes.get_options(ocel)
    assert {v.value: v.count for v in options.object_types} == {"coil": 5, "slab": 1}
    assert options.activities[0].value == "crane move"
    assert {"to_loc", "from_loc", "event_group"} <= set(options.event_attributes)
    values = routes.get_attribute_values(ocel, "to_loc")
    assert sum(v.count for v in values) == 10


def test_apply_stores_config_and_cache(ocel, session, state):
    result = routes.apply_config("log", example_config(), ocel, session, state)
    assert result.applied and result.errors == []
    assert routes.get_config("log", state).config == example_config()
    cached = state.cache["log"]
    assert routes.current_derivation("log", ocel, session, state) is cached.derivation


def test_cache_invalidated_by_level_filters_and_tables(ocel, session, state):
    config = example_config(target_locations=LocationTable(table="target_locations.csv", event_column="event", location_column="location"))
    upload(state, EXAMPLE / "inputs" / "target_locations.csv")
    assert routes.apply_config("log", config, ocel, session, state).applied
    first = routes.current_derivation("log", ocel, session, state)

    session.filters = [example_config()]  # any pydantic model stands in for a filter
    second = routes.current_derivation("log", ocel, session, state)
    assert second is not first

    upload(state, EXAMPLE / "inputs" / "target_locations.csv")  # same content: same key
    assert routes.current_derivation("log", ocel, session, state) is second

    assert routes.apply_config("log", config.model_copy(update={"level": 1}), ocel, session, state).applied
    assert routes.current_derivation("log", ocel, session, state).level == 1


def test_blocking_errors_keep_previous_config(ocel, session, state, tmp_path):
    assert routes.apply_config("log", example_config(), ocel, session, state).applied
    conflicting = tmp_path / "conflicting.csv"
    conflicting.write_text("event,location\ne5,A2\ne5,B1\n")
    upload(state, conflicting)
    bad = example_config(target_locations=LocationTable(table="conflicting.csv", event_column="event", location_column="location"))
    result = routes.apply_config("log", bad, ocel, session, state)
    assert not result.applied
    assert result.errors[0].code == "conflicting_locations" and result.errors[0].ids == ["e5"]
    assert routes.get_config("log", state).config == example_config()


def test_missing_table_is_an_error(ocel, session, state):
    bad = example_config(target_locations=LocationTable(table="nothing.csv", event_column="event", location_column="location"))
    result = routes.apply_config("log", bad, ocel, session, state)
    assert not result.applied and result.errors[0].code == "missing_input"


def test_no_config_gives_409(ocel, session, state):
    with pytest.raises(HTTPException) as raised:
        routes.current_derivation("log", ocel, session, state)
    assert raised.value.status_code == 409


def test_example_configuration_file_matches_the_tests():
    """data/running_example/configuration.json loads into the running example's configuration."""
    loaded = DerivationConfig.model_validate(json.loads((EXAMPLE / "configuration.json").read_text()))
    assert loaded == example_config()
