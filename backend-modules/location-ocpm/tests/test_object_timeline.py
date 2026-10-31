"""Tests of the object timeline on the running example (Level 3) and the edge-case example."""

from datetime import datetime
from pathlib import Path

import plotly.graph_objects as go
import polars as pl
import pytest
from ocelescope_module_location_based_ocpm.derivation.level_files import (
    load_level_mapping,
)
from ocelescope_module_location_based_ocpm.timeline.object_timeline import (
    band_segments,
    hu_order,
    lifespans,
    object_timeline,
    shared_events,
    tie_groups,
    timeline_relations,
    timestamp_before,
)
from ocelescope_module_location_based_ocpm.visits.context import location_context

DATA = Path(__file__).parents[3] / "data"
EXAMPLE = DATA / "running_example"
EDGE = DATA / "timeline_example"


def _inputs(
    folder: Path, mapping: pl.DataFrame, locations: Path, axis="event order", **kwargs
):
    """timeline_relations on a mapping with the processing events, roles and location context in `folder`."""
    ctx = location_context(pl.read_csv(locations))
    return timeline_relations(
        mapping,
        agg=ctx.agg,
        vehicles=ctx.vehicles,
        processing=pl.read_csv(folder / "processing_events.csv")["event"].to_list(),
        roles=pl.read_csv(folder / "transformation_roles.csv"),
        axis=axis,
        **kwargs,
    )


@pytest.fixture(scope="module")
def mapping() -> pl.DataFrame:
    """Saved Level 3 mapping of the running example."""
    return load_level_mapping(EXAMPLE / "derived", 3)


@pytest.fixture(scope="module")
def relations(mapping) -> pl.DataFrame:
    """The running example prepared for the timeline (event order)."""
    return _inputs(EXAMPLE / "inputs", mapping, EXAMPLE / "inputs" / "locations.csv")


@pytest.fixture(scope="module")
def edge() -> pl.DataFrame:
    """The edge-case example prepared for the timeline (event order)."""
    mapping = pl.read_csv(EDGE / "relations.csv", try_parse_dates=True)
    return _inputs(EDGE, mapping, EDGE / "locations.csv")


def _segments(frame: pl.DataFrame, hu: str, level="low") -> list[tuple]:
    """(location, is_vehicle, x0, x1) of one handling unit's band."""
    return (
        band_segments(frame, level)
        .filter(pl.col("hu") == hu)
        .select("location", "is_vehicle", "x0", "x1")
        .rows()
    )


def test_order_by_first_event_or_as_given(mapping):
    """Default order by first event, then id; a given order is kept and unknown ids are dropped."""
    assert list(hu_order(mapping)) == ["s1", "c1", "c2", "c3", "c4", "c5"]
    assert hu_order(mapping, ["c3", "zz", "c1"]) == {"c3": 0, "c1": 1}


def test_markers_and_roles(relations):
    """Processing operations are stars; roles only at transformation events."""
    c2 = relations.filter(pl.col("hu") == "c2").select("event", "marker", "role").rows()
    assert c2 == [
        ("e3", "processing", "produced"),
        ("e4", "processing", None),
        ("e6", "movement", None),
        ("e8", "movement", None),
        ("e9", "movement", None),
        ("e11", "movement", None),
        ("e12", "movement", None),
        ("e15", "processing", "consumed"),
    ]


def test_low_band_c1_shows_pickup_location_halfway(relations):
    """c1 after e11 is at A2, but e13 picks it up at A1: A2 up to the middle, then A1; continuation after e14."""
    assert _segments(relations, "c1") == [
        ("A1", False, 3.0, 5.0),
        ("A2", False, 5.0, 7.0),
        ("B1", False, 7.0, 8.0),
        ("T", True, 8.0, 9.0),
        ("A2", False, 9.0, 12.0),
        ("A1", False, 12.0, 13.0),
        ("T", True, 13.0, 14.6),
    ]


def test_high_band_merges_and_band_ends_at_consumption(relations):
    """High-level stretches merge; s1 and c2 are consumed at their last event, c5 is never located."""
    assert _segments(relations, "c1", "high") == [
        ("A", False, 3.0, 7.0),
        ("B", False, 7.0, 8.0),
        ("T", True, 8.0, 9.0),
        ("A", False, 9.0, 13.0),
        ("T", True, 13.0, 14.6),
    ]
    assert _segments(relations, "s1") == [("A1", False, 1.0, 3.0)]
    assert _segments(relations, "c2")[-1] == ("B1", False, 12.0, 15.0)
    assert _segments(relations, "c5") == []


def test_shared_events_and_lifespans(relations):
    """e8 is shared by c1, c2, c3; c3 lives from e8 to e14."""
    shared = shared_events(relations)
    assert shared.filter(pl.col("event") == "e8")["hus"].to_list() == [
        ["c1", "c2", "c3"]
    ]
    assert shared.height == 9
    assert lifespans(relations).filter(pl.col("hu") == "c3").select("x0", "x1").row(
        0
    ) == (8, 14)


def test_no_ties_in_running_example(relations):
    """The running example has no events with the same timestamp."""
    assert tie_groups(relations).is_empty()


def test_ties_get_own_positions_and_boxes(mapping):
    """With e4 at 3:00, e3 and e4 share a timestamp: own x each (event id order), one tie group."""
    tied = mapping.with_columns(
        pl.when(pl.col("event") == "e4")
        .then(pl.lit(datetime(2026, 1, 1, 3)))
        .otherwise(pl.col("time"))
        .alias("time")
    )
    rel = _inputs(EXAMPLE / "inputs", tied, EXAMPLE / "inputs" / "locations.csv")
    c1 = rel.filter(pl.col("hu") == "c1")
    assert c1.filter(pl.col("event").is_in(["e3", "e4"]))["x"].to_list() == [3, 4]
    assert tie_groups(rel).select("events", "x0", "x1").rows() == [("e3, e4", 3, 4)]
    timed = _inputs(
        EXAMPLE / "inputs", tied, EXAMPLE / "inputs" / "locations.csv", axis="time"
    )
    xs = timed.filter((pl.col("hu") == "c1") & pl.col("event").is_in(["e3", "e4"]))[
        "x"
    ].to_list()
    assert xs[0] < datetime(2026, 1, 1, 3) < xs[1]


def test_edge_lead_in_consumption_and_production(edge):
    """h1: lead-in at X1, band ends at x3 (consumed); h2 produced at x4: no lead-in."""
    assert _segments(edge, "h1") == [("X1", False, 0.4, 1.0), ("Y1", False, 1.0, 5.0)]
    assert _segments(edge, "h2")[0] == ("Y2", False, 7.0, 9.5)
    roles = dict(edge.select("event", "role").rows())
    assert (
        roles["x3"] == "consumed"
        and roles["x4"] == "produced"
        and roles["x5"] == "consumed and produced"
    )


def test_edge_location_before_a_timestamp_comes_from_the_movement(edge):
    """At 6:00, h2 has the movement x7 (ploc Y3) and the scan x8 (ploc Y2): the location before is Y3."""
    before = (
        timestamp_before(edge)
        .filter(pl.col("hu") == "h2")
        .sort("time")["before"]
        .to_list()
    )
    assert before == [None, "Y2", "Y3"]
    assert _segments(edge, "h2") == [
        ("Y2", False, 7.0, 9.5),
        ("Y3", False, 9.5, 10.0),
        ("Y1", False, 10.0, 11.6),
    ]
    assert _segments(edge, "h2", "high") == [("Y", False, 7.0, 11.6)]


def test_edge_unknown_location_then_known_before_next_event(edge):
    """h3 is not located at x9, but the location before x10 is Y1: second half Y1, then the crane C (hatched)."""
    assert _segments(edge, "h3") == [
        ("Y1", False, 3.5, 4.0),
        ("C", True, 4.0, 6.0),
        ("Y2", False, 6.0, 6.6),
    ]


@pytest.mark.parametrize("axis", ["event order", "time"])
def test_figure_draws_bands_markers_and_tie_boxes(edge, axis):
    """The figure has one bar trace per location, the role markers and a box per tie group."""
    mapping = pl.read_csv(EDGE / "relations.csv", try_parse_dates=True)
    rel = _inputs(EDGE, mapping, EDGE / "locations.csv", axis=axis)
    fig = object_timeline(rel)
    assert isinstance(fig, go.Figure)
    names = {t.name for t in fig.data if t.name}
    assert {"Y1", "Y", "C", "vehicle (hatched)", "same timestamp"} <= names
    assert {
        "movement: consumed",
        "movement: produced",
        "processing: consumed and produced",
    } <= names
    assert (
        sum(1 for s in fig.layout.shapes if s.fillcolor) == tie_groups(rel).height == 5
    )
    without = object_timeline(rel, show_high_level=False, mark_ties=False)
    assert "Y" not in {t.name for t in without.data} and not without.layout.shapes
