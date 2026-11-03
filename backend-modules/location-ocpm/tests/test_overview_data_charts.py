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
        # Without the processing input, P = T: transformation events are processing operations too.
        "transformation · processing/fully located/agreeing": 2,
        "transformation · processing/fully located/not tested": 1,
        "other/fully located/agreeing": 1,
        "other/fully located/not agreeing": 1,
        "other/fully located/not tested": 2,
        "other/partially located/not tested": 1,
        "other/unlocated/not tested": 1,
    }
    inner = counts(data_charts(derivation).events, depth=1)
    assert inner == {"movement": 8, "transformation · processing": 3, "other": 6}
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


def test_charts_with_location_context(ocel, input_tables):
    """With the location context (P = T plus label): e4 is "processing"; the locations sunburst counts
    locations and relations by type and high-level location (concept example in section 5)."""
    import polars as pl

    from ocelescope_module_location_based_ocpm.derivation.pipeline import derive

    from conftest import example_config
    from test_location_context import CONTEXT

    tables = {name: frame.cast(pl.String) for name, frame in input_tables.items()}
    charts = data_charts(derive(ocel, example_config(**CONTEXT), tables))
    inner = counts(charts.events, depth=1)
    assert inner == {"movement": 8, "transformation · processing": 3, "processing": 1, "other": 5}
    assert "not agreeing" in {s.label for s in charts.events}  # e14 stays not agreeing at high level
    assert not any(s.label == "agreeing at high level only" for s in charts.events)
    assert counts(charts.locations) == {
        "vehicle": 1, "storage unit": 1, "other": 2, "vehicle/T": 1, "storage unit/B": 1, "other/A": 2,
    }
    assert counts(charts.location_relations, depth=1) == {"vehicle": 5, "storage unit": 8, "other": 13}
    assert charts.unlocated_relations == 2 and charts.has_context
    segments = {s.id: s for s in charts.locations}
    assert segments["vehicle"].filter.value == "[vehicles]"
    assert segments["other"].filter is None


def test_high_level_locations_repair_disagreement(ocel):
    """Mapping T and B1 to one high-level location makes e14 (c1 at T, c3 at B1) agree at high level only."""
    import polars as pl

    from ocelescope_module_location_based_ocpm.derivation.config import HighLevelTable
    from ocelescope_module_location_based_ocpm.derivation.pipeline import derive

    from conftest import example_config

    tables = {"yard": pl.DataFrame({"location": ["T", "B1"], "high_level": ["yard", "yard"]})}
    config = example_config(
        high_level_locations=HighLevelTable(table="yard", location_column="location", high_level_column="high_level")
    )
    outer = counts(data_charts(derive(ocel, config, tables)).events, depth=3)
    assert outer["other/fully located/agreeing at high level only"] == 1
    assert "other/fully located/not agreeing" not in outer


def test_vehicle_and_storage_filters(ocel, input_tables):
    """"[vehicles]" and "[storage units]" match relations at locations of V and W."""
    import polars as pl

    from ocelescope_module_location_based_ocpm.derivation.pipeline import derive
    from ocelescope_module_location_based_ocpm.overview.filters import filter_options, passing_relations

    from conftest import example_config
    from test_location_context import CONTEXT

    tables = {name: frame.cast(pl.String) for name, frame in input_tables.items()}
    result = derive(ocel, example_config(**CONTEXT), tables)
    after = passing_relations(result, PageFilter(locations=["[vehicles]"], location_role="after"))
    assert set(after["loc"]) == {"T"} and after.height == 5
    options = {o.value: o.count for o in filter_options(result).locations}
    assert "[storage units]" in options and "[vehicles]" in options
    processing = passing_relations(result, PageFilter(activities=["[processing operations]"]))
    assert sorted(processing["event"].unique()) == ["e1", "e15", "e3", "e4"]
