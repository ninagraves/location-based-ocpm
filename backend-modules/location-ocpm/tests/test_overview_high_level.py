"""Overview section with the location context: Locations low | high, grouped location filter, single ids,
location types, processing operations (`overview/module/Module Overview.md`, "Update Overview Page",
sections 6-10). Running example with A1, A2 -> A; B1 -> B; T unmapped; V = {T}; W = {B1}; P = T plus label.
"""

import polars as pl
import pytest

from ocelescope_module_location_based_ocpm.derivation.pipeline import derive
from ocelescope_module_location_based_ocpm.overview.activity_profile import activity_profile
from ocelescope_module_location_based_ocpm.overview.filters import (
    PageFilter,
    filter_options,
    passing_relations,
    search_ids,
)
from ocelescope_module_location_based_ocpm.overview.key_numbers import key_numbers
from ocelescope_module_location_based_ocpm.overview.overview_charts import heatmap, overview_bar_chart

from conftest import example_config
from test_location_context import CONTEXT

HIGH = PageFilter(location_mode="high")


@pytest.fixture(scope="module")
def context(ocel, input_tables):
    """The running example with the location context at Level 3."""
    tables = {name: frame.cast(pl.String) for name, frame in input_tables.items()}
    return derive(ocel, example_config(**CONTEXT), tables)


def _bars(chart):
    """(label, count, [(segment, count)]) of every shown bar."""
    return [(b.label, b.count, [(s.value, s.count) for s in b.segments]) for b in chart.bars]


def test_locations_chart_by_low_level_location(context):
    """High-level mode, relations by low-level location: A 13 (A1 7, A2 6), B 8, T 5, – 2."""
    chart = overview_bar_chart(context, HIGH, chart="locations", by="low_location")
    assert _bars(chart) == [
        ("A", 13, [("A1", 7), ("A2", 6)]),
        ("B", 8, [("B1", 8)]),
        ("T", 5, [("T", 5)]),
        ("–", 2, [("–", 2)]),
    ]


def test_events_by_high_level_eloc(context):
    """High-level mode, events by eloc under hat-hl: A 8, B 5, T 2, – 1; e14 left out (still disagreeing)."""
    chart = overview_bar_chart(context, HIGH, chart="locations", measure="events")
    assert [(b.label, b.count) for b in chart.bars] == [("A", 8), ("B", 5), ("T", 2), ("–", 1)]
    assert chart.left_out == 1


def test_location_type_segments(context):
    """Low-level mode, Locations chart by location type: B1 storage unit, T vehicle, A1 and A2 other."""
    chart = overview_bar_chart(context, PageFilter(), chart="locations", by="location_type")
    assert dict((label, segments) for label, _, segments in _bars(chart)) == {
        "B1": [("storage unit", 8)],
        "A1": [("other", 7)],
        "A2": [("other", 6)],
        "T": [("vehicle", 5)],
        "–": [("–", 2)],
    }


def test_activity_profile_high_level(context):
    """crane move: typical A (4 of 6, from A2), top A 4, B 2; label is a processing operation."""
    rows = {r.activity: r for r in activity_profile(context, HIGH).rows}
    crane = rows["crane move"]
    assert (crane.typical_location.value, crane.typical_location.count, crane.typical_location.total) == ("A", 4, 6)
    assert [(t.value, t.count) for t in crane.top_locations] == [("A", 4), ("B", 2)]
    assert [(m.value, m.count) for m in crane.typical_location.members] == [("A2", 4)]
    assert rows["label"].processing_share == 1.0 and rows["crane move"].processing_share == 0.0
    assert activity_profile(context).rows[0].typical_location.members == []


def test_key_numbers_by_mode(context):
    """Locations tile per mode; agreed located events 15 of 17; processing operations 4."""
    low, high = key_numbers(context, PageFilter()), key_numbers(context, HIGH)
    assert (low.locations, low.target_locations, low.pickup_locations, low.other_level_locations) == (4, 4, 2, 3)
    assert (low.vehicles, low.storage_units) == (1, 1)
    assert (high.locations, high.target_locations, high.pickup_locations, high.other_level_locations) == (3, 3, 2, 4)
    assert low.agreed_located_events == high.agreed_located_events == 15
    assert low.processing_operations == 4 and not low.processing_default
    assert [a.activity for a in low.processing_activities] == ["cast slab", "cut", "label", "roll"]
    filtered = key_numbers(context, PageFilter(locations=["B1"], location_role="after", location_mode="high")).filtered
    assert (filtered.locations, filtered.agreed_located_events, filtered.processing_operations) == (1, 5, 1)


def test_high_level_value_stands_for_its_locations(context):
    """"[high-level] A" filters like A1 + A2; switching the mode never changes which relations pass."""
    by_group = passing_relations(context, PageFilter(locations=["[high-level] A"]))
    by_members = passing_relations(context, PageFilter(locations=["A1", "A2"]))
    assert by_group.equals(by_members)
    high = passing_relations(context, PageFilter(locations=["A1"], location_mode="high"))
    assert high.select("event", "hu").equals(passing_relations(context, PageFilter(locations=["A1"])).select("event", "hu"))


def test_grouped_location_options(context):
    """A with A1, A2 and B with B1; the unmapped T appears once, as a location."""
    groups = filter_options(context).high_level_locations
    assert [(g.value, g.count, [m.value for m in g.members]) for g in groups] == [
        ("[high-level] A", 17, ["A1", "A2"]),
        ("[high-level] B", 9, ["B1"]),
    ]


def test_single_handling_units_and_events(derivation):
    """"coil" + "[hu] s1" = all coils and s1; "[event] e5" + "roll" = e5 and the roll events."""
    coils = passing_relations(derivation, PageFilter(object_types=["coil"])).height
    with_s1 = passing_relations(derivation, PageFilter(object_types=["coil", "[hu] s1"])).height
    assert with_s1 == coils + 3
    events = passing_relations(derivation, PageFilter(activities=["[event] e5", "roll"]))["event"].unique().sort()
    assert events.to_list() == ["e3", "e5"]


def test_search_ids(derivation):
    """From two characters; ignoring case; counts are events of the HU / HUs of the event."""
    assert search_ids(derivation, "hu", "c") == []
    assert [(o.value, o.count) for o in search_ids(derivation, "hu", "C1")] == [("[hu] c1", 9)]
    assert [o.value for o in search_ids(derivation, "event", "e1")][:3] == ["[event] e1", "[event] e10", "[event] e11"]


def test_heatmap_of_processing_operations(context):
    """Only the processing operations' activities stay."""
    assert sorted(heatmap(context, PageFilter(), events="processing").columns) == ["cast slab", "cut", "label", "roll"]


def test_sunburst_high_level_clicks(context):
    """A high-level segment of the Locations sunburst sets its entry; the unmapped T sets itself."""
    from ocelescope_module_location_based_ocpm.overview.data_charts import data_charts

    filters = {s.id: s.filter.value for s in data_charts(context).locations if s.parent and s.filter}
    assert filters == {"other/A": "[high-level] A", "storage unit/B": "[high-level] B", "vehicle/T": "T"}
