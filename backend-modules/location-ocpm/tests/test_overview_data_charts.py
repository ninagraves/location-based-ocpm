"""Data overview charts on the running example (concept section "Data Overview Charts", example calculation)."""

from ocelescope_module_location_based_ocpm.overview.data_charts import data_charts
from ocelescope_module_location_based_ocpm.overview.filters import PageFilter


def counts(segments, depth=None):
    """Segment counts by id, optionally only for one ring (depth 1 = inner ring)."""
    return {s.id: s.count for s in segments if depth is None or s.id.count("/") == depth - 1}


def test_events_sunburst(derivation):
    outer = counts(data_charts(derivation).events, depth=3)
    assert outer == {
        "movement/fully located/agreeing": 4,
        "movement/fully located/not tested": 4,
        "transformation/fully located/agreeing": 2,
        "transformation/fully located/not tested": 1,
        "other/fully located/agreeing": 1,
        "other/fully located/not agreeing": 1,
        "other/fully located/not tested": 2,
        "other/partially located/not tested": 1,
        "other/unlocated/not tested": 1,
    }
    inner = counts(data_charts(derivation).events, depth=1)
    assert inner == {"movement": 8, "transformation": 3, "other": 6}
    middle = counts(data_charts(derivation).events, depth=2)
    assert middle["other/fully located"] == 4


def test_click_filters(derivation):
    segments = {s.id: s for s in data_charts(derivation).events}
    assert segments["other/partially located"].filter.value == "[partially located events]"
    assert segments["other"].filter is None
    assert segments["other/fully located/not tested"].filter is None
    assert data_charts(derivation).handling_units[0].filter.filter == "object_types"


def test_relations_and_handling_units(derivation):
    charts = data_charts(derivation)
    assert counts(charts.relations) == {"0": 15, "1": 4, "2": 3, "3": 4, "⊥": 2}
    assert counts(charts.handling_units) == {"fully located": 5, "partially located": 0, "unlocated": 1}


def test_filter_b1_after(derivation):
    """Concept example "Location B1, after (target)"."""
    charts = data_charts(derivation, PageFilter(locations=["B1"], location_role="after"))
    assert charts.filtered
    assert sum(counts(charts.events, depth=1).values()) == 6
    assert counts(charts.events, depth=3)["other/fully located/not agreeing"] == 1  # e14
    assert counts(charts.relations) == {"0": 4, "1": 2, "2": 0, "3": 2, "⊥": 0}
    assert counts(charts.handling_units) == {"fully located": 4, "partially located": 0, "unlocated": 0}
