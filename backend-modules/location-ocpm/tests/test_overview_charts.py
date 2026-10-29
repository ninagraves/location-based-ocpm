"""Overview charts on the running example (concept section "Overview charts", "Deriving Overview Charts")."""

import polars as pl

from ocelescope_module_location_based_ocpm.overview.filters import PageFilter
from ocelescope_module_location_based_ocpm.overview.overview_charts import (
    MISSING,
    OTHER,
    colour_values,
    heatmap,
    overview_bar_chart,
)


def bars(chart):
    """Bars as {label: (count, {segment: count})}."""
    return {b.label: (b.count, {s.value: s.count for s in b.segments}) for b in chart.bars}


def test_activities_by_location(derivation):
    events = overview_bar_chart(derivation, chart="activities", measure="events", by="location")
    assert bars(events)["crane move"] == (4, {"A2": 3, "B1": 1})
    assert bars(events)["quality check"] == (3, {"B1": 2, MISSING: 1})
    assert events.left_out == 1 and events.bars[1].left_out == 1  # e14
    relations = overview_bar_chart(derivation, chart="activities", measure="relations", by="location")
    assert bars(relations)["quality check"] == (6, {"B1": 3, "T": 1, MISSING: 2})
    assert [b.label for b in relations.bars][:3] == ["crane move", "quality check", "load truck"]
    assert relations.other is None  # at most 10 bars


def test_most_locations(derivation):
    chart = overview_bar_chart(derivation, chart="activities", mode="locations", measure="events")
    quality = next(b for b in chart.bars if b.label == "quality check")
    assert (quality.count, quality.locations) == (2, ["B1", "T"])  # counted over relations in both measures


def test_locations_by_activity(derivation):
    events = bars(overview_bar_chart(derivation, chart="locations", measure="events", by="activity"))
    assert {k: v[0] for k, v in events.items()} == {"B1": 5, "A1": 4, "A2": 4, "T": 2, MISSING: 1}
    relations = bars(overview_bar_chart(derivation, chart="locations", by="activity"))
    assert relations["T"] == (5, {"load truck": 4, "quality check": 1})
    assert relations[MISSING][0] == 2


def test_activities_by_event_properties(derivation):
    """Locatedness and agreement are event properties: events mode counts all kept events."""
    relations = bars(overview_bar_chart(derivation, chart="activities", by="locatedness"))
    assert relations["quality check"] == (6, {"fully located": 3, "partially located": 2, "unlocated": 1})
    agreement = bars(overview_bar_chart(derivation, chart="activities", by="agreement"))
    assert agreement["quality check"] == (6, {"not tested": 4, "not agreeing": 2})
    events = overview_bar_chart(derivation, chart="activities", measure="events", by="agreement")
    assert bars(events)["quality check"] == (4, {"not tested": 3, "not agreeing": 1})  # e14 counts
    assert events.left_out == 0
    located = bars(overview_bar_chart(derivation, chart="activities", measure="events", by="locatedness"))
    assert located["quality check"] == (4, {"fully located": 2, "partially located": 1, "unlocated": 1})


def test_filtered(derivation):
    chart = overview_bar_chart(derivation, PageFilter(locations=["B1"], location_role="after"), chart="locations")
    assert [b.label for b in chart.bars] == ["B1"]


def test_heatmap(derivation):
    relations = heatmap(derivation)
    assert relations.rows == ["B1", "A1", "A2", "T", MISSING]
    cell = dict(zip(relations.columns, relations.cells[relations.rows.index("A2")]))
    assert (cell["crane move"], cell["unload truck"]) == (4, 2)
    events = heatmap(derivation, measure="events")
    assert dict(zip(events.columns, events.cells[0]))["quality check"] == 2 and events.left_out == 1
    assert set(heatmap(derivation, events="movements").columns) == {"crane move", "load truck", "unload truck"}
    assert set(heatmap(derivation, events="transformations").columns) == {"cast slab", "roll", "cut"}


def test_top_bottom_and_other():
    """Top 10 sums the rest into "other"; bottom 10 leaves the rest out (synthetic units)."""
    from ocelescope_module_location_based_ocpm.overview.overview_charts import bar_chart

    units = pl.DataFrame({"a": [f"x{i:02d}" for i in range(12) for _ in range(i + 1)]})
    shown, other, _ = bar_chart(units, "a", None, "top")
    assert shown[0].label == "x11" and (other.label, other.count, other.bars) == (OTHER, 1 + 2, 2)
    shown, other, _ = bar_chart(units, "a", None, "bottom")
    assert shown[-1].label == "x00" and other is None


def test_colour_values():
    """Enough colours per bar that at most 5 % stays grey; missing values get none."""
    segments = pl.DataFrame(
        {
            "label": ["b1"] * 4 + ["b2"] * 2,
            "value": ["p", "q", "r", MISSING, "s", "p"],
            "count": [90, 6, 4, 50, 50, 50],
        }
    )
    # b1: p (90) leaves 10 % > 5 %, so q too; r (4 %) is "other". b2 needs s and p.
    assert colour_values(segments) == ["p", "s", "q"]
