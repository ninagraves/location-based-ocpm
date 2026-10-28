"""Key numbers and flag badges on the running example (concept sections "Key Numbers" and "Flags")."""

from ocelescope_module_location_based_ocpm.derivation.pipeline import derive
from ocelescope_module_location_based_ocpm.overview.flag_badges import flag_counts
from ocelescope_module_location_based_ocpm.overview.key_numbers import key_numbers

from conftest import example_config


def test_key_numbers_level_3(derivation):
    numbers = key_numbers(derivation)
    assert numbers.handling_units == 6
    assert [(t.object_type, t.count) for t in numbers.handling_units_per_type] == [("coil", 5), ("slab", 1)]
    assert (numbers.agreed_located_events, numbers.events) == (15, 17)  # e14 not agreeing, e17 unlocated
    assert (numbers.located_relations, numbers.relations, numbers.level) == (26, 28, 3)
    assert numbers.movement_events == 8
    assert [(a.activity, a.count) for a in numbers.movement_activities][0][0] == "crane move"
    assert sum(a.count for a in numbers.movement_activities) == 8
    assert numbers.locations == 4
    assert numbers.target_locations == 4
    assert numbers.pickup_locations == 2
    assert numbers.transformation_events == 3
    assert [(a.activity, a.count) for a in numbers.transformation_activities] == [("cast slab", 1), ("cut", 1), ("roll", 1)]


def test_key_numbers_without_optional_inputs(ocel):
    numbers = key_numbers(derive(ocel, example_config(transformation_events=None, pickup_locations=None, level=0)))
    assert numbers.transformation_events is None
    assert numbers.transformation_activities == []
    assert numbers.pickup_locations is None
    assert numbers.level == 0
    assert numbers.located_relations < 26


def test_flag_counts_level_3(derivation):
    counts = {f.key: f.count for f in flag_counts(derivation)}
    assert counts == {"F1": 2, "F2": 2, "F3": 1, "F4": 1, "F5": 2}


def test_f4_hidden_without_pickup_locations(ocel):
    keys = [f.key for f in flag_counts(derive(ocel, example_config(pickup_locations=None)))]
    assert keys == ["F1", "F2", "F3", "F5"]
