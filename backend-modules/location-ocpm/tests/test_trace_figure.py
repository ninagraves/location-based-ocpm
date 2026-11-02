"""Tests of the trace figure helpers on the running example (draft for the visit concept)."""

import polars as pl
from ocelescope_module_location_based_ocpm.visits.trace_figure import (
    ROW_FILL,
    ROW_TOP,
    TIE_FILL,
    VISIT_DASH,
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


def _tied(rel):
    """Move e6 and e7 to the timestamp of e5."""
    t5 = rel.filter(pl.col("event") == "e5")["time"][0]
    return rel.with_columns(
        pl.when(pl.col("event").is_in(["e6", "e7"]))
        .then(pl.lit(t5))
        .otherwise(pl.col("time"))
        .alias("time")
    )


def _tie_boxes(fig):
    """The background boxes behind tied events."""
    return [s for s in fig.layout.shapes if s.fillcolor == TIE_FILL]


def test_tie_boxes_global_on_event_order_and_time(derivation):
    """e5, e6, e7 at one timestamp: one box over the whole figure height."""
    rel = _tied(derivation.relations)
    for axis in ("event order", "time"):
        out = relations_for_figure(rel, derivation.loc, ["c1", "c2"], AGG, axis=axis)
        boxes = _tie_boxes(trace_figure(out))
        assert len(boxes) == 1
        assert boxes[0].yref == "paper"
    plain = relations_for_figure(
        derivation.relations, derivation.loc, ["c1", "c2"], AGG
    )
    assert _tie_boxes(trace_figure(plain)) == []
    assert _tie_boxes(trace_figure(out, mark_ties=False)) == []


def test_tie_boxes_per_handling_unit_on_trace_position(derivation):
    """Trace position: only c1 has two tied events (e5, e7); c2 has just e6 at that time."""
    rel = _tied(derivation.relations)
    out = relations_for_figure(
        rel, derivation.loc, ["c1", "c2"], AGG, axis="trace position"
    )
    boxes = _tie_boxes(trace_figure(out))
    assert len(boxes) == 1
    assert boxes[0].yref != "paper"
    assert boxes[0].y1 > 0 > boxes[0].y0


def test_maximal_visits_dashed(derivation):
    """Maximal visits get a dashed outline, resolved ones a solid one."""
    rel = relations_for_figure(derivation.relations, derivation.loc, ["c1"], AGG)
    visits = pl.DataFrame(
        {
            "hu": ["c1", "c1"],
            "high_level": ["A", "A"],
            "first_event": ["e3", "e3"],
            "last_event": ["e4", "e4"],
            "group": ["maximal", "resolved"],
        }
    )
    bars = [
        s
        for s in trace_figure(rel, visits).layout.shapes
        if s.type == "rect" and s.line.dash
    ]
    assert sorted(s.line.dash for s in bars) == sorted([VISIT_DASH, "solid"])


def test_bottom_visit_drawn_grey(derivation):
    """A visit at ⊥ (high_level null) is drawn as a grey bar and named ⊥ in the hover."""
    rel = relations_for_figure(derivation.relations, derivation.loc, ["c5"], AGG)
    visits = pl.DataFrame(
        {
            "hu": ["c5"],
            "high_level": [None],
            "first_event": ["e16"],
            "last_event": ["e17"],
            "group": ["maximal"],
        },
        schema_overrides={"high_level": pl.String},
    )
    fig = trace_figure(rel, visits)
    bars = [s for s in fig.layout.shapes if s.type == "rect" and s.line.dash]
    assert len(bars) == 1
    assert bars[0].line.color == "#adb5bd"
    assert any(
        "⊥" in (t.hovertemplate or "") and "visit" in t.hovertemplate for t in fig.data
    )


def test_visit_ids_shown_in_bars(derivation):
    """An optional visit_id is written into the bar; without the column or with show_visit_ids=False, nothing."""
    rel = relations_for_figure(derivation.relations, derivation.loc, ["c1"], AGG)
    visits = pl.DataFrame(
        {
            "visit_id": ["m1", "m2"],
            "hu": ["c1", "c1"],
            "high_level": ["A", "B"],
            "first_event": ["e3", "e7"],
            "last_event": ["e11", "e7"],
            "group": ["maximal", "maximal"],
        }
    )

    def ids(fig):
        return {a.text for a in fig.layout.annotations} & {"<b>m1</b>", "<b>m2</b>"}

    assert ids(trace_figure(rel, visits)) == {"<b>m1</b>", "<b>m2</b>"}
    assert ids(trace_figure(rel, visits, show_visit_ids=False)) == set()
    assert ids(trace_figure(rel, visits.drop("visit_id"))) == set()


def test_processing_defaults_to_transformations_and_takes_given_events(derivation):
    """Without P, the transformation events are processing operations; with P, exactly the given events."""
    default = relations_for_figure(derivation.relations, derivation.loc, ["c2"], AGG)
    assert default.filter("is_processing")["event"].to_list() == ["e3", "e15"]
    given = relations_for_figure(
        derivation.relations, derivation.loc, ["c2"], AGG, processing={"e4", "e15"}
    )
    assert given.filter("is_processing")["event"].to_list() == ["e4", "e15"]
    none = relations_for_figure(
        derivation.relations, derivation.loc, ["c2"], AGG, processing=()
    )
    assert not none["is_processing"].any()


def test_processing_drawn_as_stars_with_legend_entry(derivation):
    """Processing operations are stars in their location colour; the legend gets 'processing operation'."""
    rel = relations_for_figure(
        derivation.relations,
        derivation.loc,
        ["c1"],
        AGG,
        {"T"},
        processing={"e4", "e14"},
    )
    fig = trace_figure(rel)
    stars = {
        (t.marker.symbol, x)
        for t in fig.data
        if t.marker.symbol in ("star", "star-open") and t.name != "processing operation"
        for x in t.x
    }
    x_of = dict(rel.select("event", "x").iter_rows())
    assert stars == {("star", x_of["e4"]), ("star-open", x_of["e14"])}
    assert "processing operation" in {t.name for t in fig.data}
    # The location legend keeps the plain symbols.
    legend = {
        t.name: t.marker.symbol
        for t in fig.data
        if t.showlegend and t.legendgroup == "location"
    }
    assert legend["A1"] == "circle" and legend["T"] == "circle-open"
    plain = trace_figure(
        relations_for_figure(
            derivation.relations, derivation.loc, ["c1"], AGG, processing=()
        )
    )
    assert "processing operation" not in {t.name for t in plain.data}


def test_every_other_handling_unit_shaded(derivation):
    """Rows 1, 3, ... get a full-width band in ROW_FILL; shade_rows=False draws none."""
    rel = relations_for_figure(derivation.relations, derivation.loc, ["c1", "c2", "c3"], AGG, {"T"}, {"B1"})
    bands = [s for s in trace_figure(rel).layout.shapes if s.fillcolor == ROW_FILL]
    assert len(bands) == 2
    assert all(b.xref == "paper" and b.x0 == 0 and b.x1 == 1 for b in bands)
    # The bands do not overlap and the first one starts at the top of the plot.
    top, second = sorted(bands, key=lambda b: -b.y1)
    assert top.y0 > second.y1 and top.y1 == ROW_TOP
    assert not [s for s in trace_figure(rel, shade_rows=False).layout.shapes if s.fillcolor == ROW_FILL]


def test_shape_legend_explains_markers_in_use(derivation):
    """The 'shape' legend group names the shapes that occur: processing (located or not), vehicle, storage unit."""
    rel = relations_for_figure(
        derivation.relations, derivation.loc, ["c1", "c5"], AGG, {"T"}, {"B1"}, processing={"e4", "e16"}
    )
    shapes = {t.name: t.marker.symbol for t in trace_figure(rel).data if t.legendgroup == "shape"}
    assert shapes == {
        "processing operation": "star",
        "processing operation, not located": "asterisk-open",
        "vehicle": "circle-open",
        "storage unit": "diamond",
    }
    plain = relations_for_figure(derivation.relations, derivation.loc, ["c1"], AGG, processing=())
    assert not [t for t in trace_figure(plain).data if t.legendgroup == "shape"]
