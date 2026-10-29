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
    """c1's trace at Level 3: positions, high-level locations and kinds."""
    rel = relations_for_figure(
        derivation.relations,
        derivation.loc,
        ["c1"],
        AGG,
        {"T"},
        {"B1"},
        axis="trace position",
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
    rel = relations_for_figure(
        derivation.relations,
        derivation.loc,
        ["s1", "c1", "c2"],
        AGG,
        axis="event order",
    )
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
    rel = relations_for_figure(
        derivation.relations, derivation.loc, None, AGG, {"T"}, {"B1"}
    )
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


def test_high_level_runs_c1(derivation):
    """c1's runs of equal high-level locations: A, B, T, A, T (event order axis)."""
    from ocelescope_module_location_based_ocpm.visits.trace_figure import (
        high_level_runs,
    )

    rel = relations_for_figure(
        derivation.relations, derivation.loc, ["c1"], AGG, axis="trace position"
    )
    runs = high_level_runs(rel)
    assert runs["high_level"].to_list() == ["A", "B", "T", "A", "T"]
    assert list(zip(runs["x0"], runs["x1"])) == [(1, 3), (4, 4), (5, 5), (6, 7), (8, 9)]


def test_all_high_level_styles_build(derivation):
    """Every high-level style builds."""
    rel = relations_for_figure(
        derivation.relations, derivation.loc, None, AGG, {"T"}, {"B1"}
    )
    for style in ("squares", "ribbon", "shading", "outline"):
        assert trace_figure(rel, high_level_style=style).layout.annotations


def test_ribbon_labels_only_where_they_fit(derivation):
    """A long name is shown on c2's four-event run of B (e12 to e15) but not on c1's one-event run (e7)."""
    rel = relations_for_figure(
        derivation.relations,
        derivation.loc,
        ["c1", "c2"],
        {**AGG, "B1": "Storage hall north"},
    )
    fig = trace_figure(rel, high_level_style="ribbon", show_event_labels=False)
    labels = [a.text for a in fig.layout.annotations]
    assert labels.count("<b>Storage hall north</b>") == 1
    assert labels.count("<b>T</b>") == 3


def test_location_context_from_running_example_table(input_tables):
    """inputs/locations.csv: A1, A2 -> A, B1 -> B, T unmapped; V = {T}, W = {B1}."""
    from ocelescope_module_location_based_ocpm.visits.context import location_context

    context = location_context(input_tables["locations"])
    assert context.agg == AGG
    assert context.vehicles == {"T"}
    assert context.storage_units == {"B1"}


def test_time_axis_spreads_tied_events(derivation):
    """Events at the same timestamp get distinct x values around it; a shared event keeps one x."""
    from datetime import timedelta

    rel = derivation.relations
    t5 = rel.filter(pl.col("event") == "e5")["time"][0]
    rel = rel.with_columns(
        pl.when(pl.col("event").is_in(["e6", "e7"]))
        .then(pl.lit(t5))
        .otherwise(pl.col("time"))
        .alias("time")
    )
    out = relations_for_figure(rel, derivation.loc, ["c1", "c2"], AGG, axis="time")
    xs = dict(
        out.filter(pl.col("event").is_in(["e5", "e6", "e7"]))
        .select("event", "x")
        .unique()
        .iter_rows()
    )
    assert xs["e5"] < xs["e6"] < xs["e7"]
    assert xs["e6"] == t5
    assert xs["e7"] - xs["e5"] <= timedelta(hours=1) * 0.5
    assert out.filter(pl.col("event") == "e3")["x"].n_unique() == 1
