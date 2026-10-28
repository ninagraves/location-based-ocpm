"""Page filter bar on the running example (concept section "Filter Effect", example "Location B1, after")."""

from ocelescope_module_location_based_ocpm.overview.filters import (
    DISAGREEING_EVENTS,
    MOVEMENT_EVENTS,
    UNKNOWN,
    UNLOCATED_HUS,
    PageFilter,
    filter_options,
    passing_relations,
)
from ocelescope_module_location_based_ocpm.overview.key_numbers import key_numbers

B1_AFTER = PageFilter(locations=["B1"], location_role="after")


def pairs(derivation, page_filter):
    """Passing relations as sorted (hu, event) pairs."""
    return sorted(passing_relations(derivation, page_filter).select("hu", "event").rows())


def test_concept_example_passing_relations(derivation):
    assert pairs(derivation, B1_AFTER) == sorted(
        [("c1", "e7"), ("c3", "e10"), ("c2", "e12"), ("c3", "e12"), ("c3", "e14"), ("c2", "e15"), ("c4", "e15"), ("c4", "e16")]
    )


def test_concept_example_key_numbers(derivation):
    numbers = key_numbers(derivation, B1_AFTER)
    filtered = numbers.filtered
    assert filtered.handling_units == 4
    assert (filtered.located_relations, filtered.relations) == (8, 8)
    assert filtered.movement_events == 2
    assert filtered.locations == 1
    assert filtered.transformation_events == 1
    # Kept events e7, e10, e12, e14, e15, e16; all but e14 (disagreeing) have an eloc.
    assert filtered.agreed_located_events == 5
    assert numbers.handling_units == 6  # big numbers stay the whole log


def test_no_filter_no_filtered_values(derivation):
    assert key_numbers(derivation, PageFilter()).filtered is None
    assert key_numbers(derivation, PageFilter(location_role="before")).filtered is None


def test_exclude_and_special_values(derivation):
    everything = len(pairs(derivation, PageFilter()))
    movements = pairs(derivation, PageFilter(activities=[MOVEMENT_EVENTS]))
    without = pairs(derivation, PageFilter(exclude_activities=[MOVEMENT_EVENTS]))
    assert len(movements) + len(without) == everything == 28
    assert {e for _, e in pairs(derivation, PageFilter(activities=[DISAGREEING_EVENTS]))} == {"e14"}
    assert {h for h, _ in pairs(derivation, PageFilter(object_types=[UNLOCATED_HUS]))} == {"c5"}
    unknown_after = pairs(derivation, PageFilter(locations=[UNKNOWN], location_role="after"))
    assert len(unknown_after) == 2  # 26 of 28 relations are located at Level 3


def test_filters_combine_with_and(derivation):
    both = pairs(derivation, PageFilter(locations=["B1"], location_role="after", object_types=["coil"], activities=["quality check"]))
    assert both == [("c1", "e7"), ("c3", "e14"), ("c4", "e16")]


def test_filter_options(derivation):
    options = filter_options(derivation)
    activities = {o.value: o.count for o in options.activities}
    assert activities[MOVEMENT_EVENTS] == 8 and activities["quality check"] == 4
    assert options.locations[0].value == UNKNOWN
    assert {o.value: o.count for o in options.object_types}["coil"] == 5
