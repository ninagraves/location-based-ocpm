"""Tests of the trace figure helpers on the running example (draft for the visit concept)."""

import polars as pl
from ocelescope_module_location_based_ocpm.visits.trace_figure import (
    add_high_level_locations,
    location_colours,
    relations_for_figure,
    trace_figure,
    visit_lanes,
)

AGG = {"A1": "A", "A2": "A", "B1": "B"}


def test_high_level_locations_complete_agg_by_identity_and_keep_bottom():
    """Unmapped locations map to themselves; ⊥ stays ⊥."""
    frame = pl.DataFrame({"loc": ["A1", "A2", "B1", "T", None]})
    out = add_high_level_locations(frame, "loc", AGG)
    assert out["high_level"].to_list() == ["A", "A", "B", "T", None]


def test_relations_for_figure_c1(derivation):
    """c1's trace at Level 3: positions, high-level locations and kinds (review-1-visits.md, section 3)."""
    rel = relations_for_figure(
        derivation, ["c1"], AGG, {"T"}, {"B1"}, axis="trace position"
    )
    assert rel["event"].to_list() == [
        "e3",
        "e4",
        "e5",
        "e7",
        "e8",
        "e9",
        "e11",
        "e13",
        "e14",
    ]
    assert rel["position"].to_list() == list(range(1, 10))
    assert rel["high_level"].to_list() == ["A", "A", "A", "B", "T", "A", "A", "T", "T"]
    assert rel["location_kind"].to_list() == ["other"] * 3 + [
        "storage",
        "vehicle",
        "other",
        "other",
        "vehicle",
        "vehicle",
    ]


def test_event_order_aligns_shared_events(derivation):
    """With the event order axis, the shared event e3 has one x for s1, c1 and c2; HU order is kept."""
    rel = relations_for_figure(derivation, ["s1", "c1", "c2"], AGG, axis="event order")
    assert rel["hu"].unique(maintain_order=True).to_list() == ["s1", "c1", "c2"]
    assert rel.filter(pl.col("event") == "e3")["x"].n_unique() == 1


def test_visit_lanes_contained_visit_below_containing_one():
    """A contained visit gets a second lane; a disjoint later visit reuses the first."""
    visits = pl.DataFrame(
        {
            "hu": ["c2"] * 3,
            "group": ["maximal"] * 3,
            "first_position": [1, 4, 7],
            "last_position": [6, 4, 8],
        }
    )
    assert visit_lanes(visits)["lane"].to_list() == [0, 1, 0]


def test_location_colours_ranked_by_frequency():
    """The most frequent location gets the first palette colour; ⊥ is ignored."""
    colours = location_colours(["B", "A", "A", None], palette=("first", "second"))
    assert colours == {"A": "first", "B": "second"}


def test_trace_figure_builds(derivation):
    """The figure builds with visits for all handling units."""
    rel = relations_for_figure(derivation, None, AGG, {"T"}, {"B1"})
    visits = pl.DataFrame(
        {
            "hu": ["c2", "c2"],
            "high_level": ["A", "T"],
            "first_event": ["e3", "e8"],
            "last_event": ["e11", "e8"],
            "group": ["maximal"] * 2,
        }
    )
    fig = trace_figure(rel, visits)
    assert len(fig.layout.shapes) > 0
