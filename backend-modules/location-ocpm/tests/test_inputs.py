"""Input options, notices and blocking errors (concept section "input data", RQ1-RQ3)."""

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from conftest import example_config
from ocelescope_module_location_based_ocpm.derivation.config import (
    AttributeValues,
    EventTable,
    LocationTable,
    ObjectTable,
    Qualifiers,
)
from ocelescope_module_location_based_ocpm.derivation.inputs import resolve_inputs
from ocelescope_module_location_based_ocpm.derivation.pipeline import derive

COLUMNS = ["hu", "event", "is_movement", "is_transformation", "uloc", "puloc"]


def relations(ocel, config, tables=None):
    """Resolved relations, sorted, restricted to the input columns."""
    return resolve_inputs(ocel, config, tables).relations.select(COLUMNS).sort("hu", "event")


def test_table_options_equal_attribute_options(ocel, input_tables):
    via_tables = example_config(
        handling_units=ObjectTable(table="handling_units", object_column="object"),
        movement_events=EventTable(table="movement_events", event_column="event"),
        transformation_events=EventTable(table="transformation_events", event_column="event"),
        target_locations=LocationTable(table="target_locations", event_column="event", location_column="location"),
        pickup_locations=LocationTable(table="pickup_locations", event_column="event", location_column="location"),
    )
    assert_frame_equal(relations(ocel, via_tables, input_tables), relations(ocel, example_config()))


def test_attribute_value_and_qualifier_options(ocel):
    other = example_config(
        movement_events=AttributeValues(attribute="event_group", values=["transport"]),
        transformation_events=Qualifiers(qualifiers=["produced", "consumed"]),
    )
    assert_frame_equal(relations(ocel, other), relations(ocel, example_config()))


def test_unknown_table_rows_are_dropped_and_reported(ocel, input_tables):
    tables = dict(input_tables)
    tables["target_locations"] = pl.concat([tables["target_locations"], pl.DataFrame({"event": ["x1"], "location": ["A1"]})])
    config = example_config(target_locations=LocationTable(table="target_locations", event_column="event", location_column="location"))
    resolved = resolve_inputs(ocel, config, tables)
    assert [(n.code, n.count, n.ids) for n in resolved.notices] == [("unknown_ids_dropped", 1, ["x1"])]
    assert resolved.errors == []


def test_empty_values_are_not_locations(ocel, input_tables):
    tables = dict(input_tables)
    tables["target_locations"] = pl.concat(
        [tables["target_locations"], pl.DataFrame({"event": ["e4", "e14", "e16"], "location": ["", "NA", None]})]
    )
    config = example_config(target_locations=LocationTable(table="target_locations", event_column="event", location_column="location"))
    assert_frame_equal(relations(ocel, config, tables), relations(ocel, example_config()))


def test_conflicting_table_locations_block(ocel, input_tables):
    tables = dict(input_tables)
    tables["target_locations"] = pl.concat([tables["target_locations"], pl.DataFrame({"event": ["e5"], "location": ["B1"]})])
    config = example_config(target_locations=LocationTable(table="target_locations", event_column="event", location_column="location"))
    result = derive(ocel, config, tables)
    assert [(e.code, e.ids) for e in result.errors] == [("conflicting_locations", ["e5"])]
    assert result.flags is None


def test_pickups_of_non_movements_are_ignored(ocel, input_tables):
    tables = dict(input_tables)
    tables["pickup_locations"] = pl.concat([tables["pickup_locations"], pl.DataFrame({"event": ["e7"], "location": ["A1"]})])
    config = example_config(pickup_locations=LocationTable(table="pickup_locations", event_column="event", location_column="location"))
    resolved = resolve_inputs(ocel, config, tables)
    assert [(n.code, n.ids) for n in resolved.notices] == [("pickups_of_non_movements_ignored", ["e7"])]
    assert_frame_equal(resolved.relations.select(COLUMNS).sort("hu", "event"), relations(ocel, example_config()))


def test_rq2_movement_without_target(ocel, input_tables):
    tables = dict(input_tables)
    tables["target_locations"] = tables["target_locations"].filter(pl.col("event") != "e5")
    config = example_config(target_locations=LocationTable(table="target_locations", event_column="event", location_column="location"))
    assert [(e.code, e.ids) for e in derive(ocel, config, tables).errors] == [("RQ2", ["e5"])]


def test_requirements_on_frames():
    from ocelescope_module_location_based_ocpm.derivation.requirements import check_rq1, check_rq3

    frame = pl.DataFrame(
        {
            "hu": ["h", "h", "h"],
            "time": [1, 1, 2],
            "event": ["a", "b", "c"],
            "uloc": ["X", "Y", None],
            "is_movement": [True, True, False],
        }
    )
    assert [(e.code, e.ids) for e in check_rq1(frame)] == [("RQ1", ["a", "b"])]
    assert [(e.code, e.ids) for e in check_rq3(frame)] == [("RQ3", ["a", "b"])]


def test_missing_attribute_raises(ocel):
    config = example_config(movement_events=AttributeValues(attribute="nope", values=["x"]))
    with pytest.raises(KeyError):
        resolve_inputs(ocel, config)
