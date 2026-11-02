"""Tests of the general helpers (sequences), the properties of visits and visit sets, excursions, dwell
times, the visit overview and the analysis of any visit set, on the running example of the concept note
(data/mapping_example/, κ_max = 3, V = {T}, W = {B1}): "Properties", "Sets of visits" (Example) and
"identifying shifts"."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from ocelescope_module_location_based_ocpm.derivation.level_files import MAPPING_SCHEMA
from ocelescope_module_location_based_ocpm.visit_mapping.pipeline import (
    analyse_mapping,
    derive_mapping_set,
)
from ocelescope_module_location_based_ocpm.visit_mapping.traces import (
    add_mapping_inputs,
    split_traces,
)
from ocelescope_module_location_based_ocpm.visits.context import location_context
from ocelescope_module_location_based_ocpm.visits.pipeline import (
    VisitAnalysis,
    analyse_visit_set,
    analyse_visits,
)
from ocelescope_module_location_based_ocpm.visits.properties import (
    flag_rq4,
    rq4_violations,
)
from ocelescope_module_location_based_ocpm.visits.sequence import (
    interval_pairs,
    python_runs,
    run_ids,
    runs,
)

DATA = Path(__file__).parents[3] / "data" / "mapping_example"
RELATIONS = pl.read_csv(DATA / "relations.csv", schema=MAPPING_SCHEMA)
CONTEXT = location_context(pl.read_csv(DATA / "locations.csv"))
P = pl.read_csv(DATA / "processing_events.csv")["event"].to_list()


@pytest.fixture(scope="module")
def vmax() -> VisitAnalysis:
    """V_max of the running example, κ_max = 3."""
    return analyse_visits(
        RELATIONS,
        "loc",
        CONTEXT.agg,
        CONTEXT.vehicles,
        3,
        P,
        storage_units=CONTEXT.storage_units,
    )


def visit_id(
    analysis: VisitAnalysis, hu: str, high_level: str | None, first: str, last: str
) -> int:
    """The visit id of the visit (hu, hl, first–last)."""
    rows = analysis.visits.filter(
        (pl.col("hu") == hu)
        & pl.col("high_level").eq_missing(high_level)
        & (pl.col("first_event") == first)
        & (pl.col("last_event") == last)
    )
    assert rows.height == 1, (hu, high_level, first, last)
    return rows["visit_id"].item()


# --- sequence helpers ---


def test_runs_and_run_ids():
    frame = pl.DataFrame(
        {
            "hu": ["a"] * 6 + ["b"] * 2,
            "position": [1, 2, 3, 4, 5, 6, 1, 2],
            "hl": ["A", "A", None, None, "B", "A", "B", "B"],
        }
    )
    ids = frame.with_columns(run_ids("hl").alias("run"))["run"].to_list()
    assert ids == [1, 1, 2, 2, 3, 4, 1, 1]
    found = runs(frame, "hl", keep=lambda x: x.is_not_null())
    assert found.select(
        "hu", "value", "first_position", "last_position", "length"
    ).rows() == [
        ("a", "A", 1, 2, 2),
        ("a", "B", 5, 5, 1),
        ("a", "A", 6, 6, 1),
        ("b", "B", 1, 2, 2),
    ]
    assert python_runs(["A", "A", None, "B"], keep=lambda x: x is not None) == [
        (0, 1, "A"),
        (3, 3, "B"),
    ]


def test_interval_pairs():
    intervals = pl.DataFrame(
        {
            "hu": ["a"] * 4,
            "visit_id": [1, 2, 3, 4],
            "first_position": [1, 2, 4, 8],
            "last_position": [5, 3, 7, 9],
        }
    )
    pairs = interval_pairs(intervals)
    assert pairs.select(
        "visit_id", "other_visit_id", "relation", "n_shared"
    ).rows() == [
        (1, 3, "overlaps", 2),
        (2, 1, "contained in", 2),
        (3, 1, "overlaps", 2),
    ]


# --- properties of visits and of the set V_max (concept note, Example) ---


def test_set_metrics_of_vmax(vmax):
    m = vmax.set_metrics.row(0, named=True)
    assert (m["n_visits"], m["n_relations"], m["p_cov"]) == (24, 54, 1.0)
    assert (m["n_interrupted"], m["p_int"]) == (12, 0.5)
    assert (m["n_contained"], m["n_overlapping"]) == (9, 6)
    assert (m["n_disjoint_hus"], m["n_hus"], m["p_dis"]) == (3, 10, 0.3)
    assert m["n_in_several_visits"] == m["n_nonconforming"] == 21
    assert m["n_overlapping_relations"] == 11
    assert m["p_overlap"] == pytest.approx(11 / 54)


def test_set_properties_of_vmax(vmax):
    props = vmax.set_properties
    assert sorted(props.filter("is_disjoint")["hu"].to_list()) == ["b3", "b5", "s1"]
    assert props["is_hl_disjoint"].all() and props["is_covering"].all()


def test_contained_and_overlapping(vmax):
    m2 = visit_id(vmax, "b1", "A", "e3", "e11")
    m3 = visit_id(vmax, "b1", "B", "e7", "e7")
    m4 = visit_id(vmax, "b1", "T", "e8", "e14")
    m16 = visit_id(vmax, "b6", "A", "e26", "e30")
    m17 = visit_id(vmax, "b6", "T", "e27", "e29")
    m18 = visit_id(vmax, "b6", "B", "e28", "e28")
    pairs = {
        (a, b): r
        for a, b, r in vmax.pairs.select(
            "visit_id", "other_visit_id", "relation"
        ).rows()
    }
    assert pairs[(m3, m2)] == "contained in"
    assert pairs[(m2, m4)] == pairs[(m4, m2)] == "overlaps"
    assert pairs[(m18, m17)] == pairs[(m17, m16)] == "contained in"
    v = vmax.visits.filter(pl.col("visit_id").is_in([m2, m3, m17])).sort("visit_id")
    assert v.select("is_contained", "contains", "is_overlapping").rows() == [
        (False, True, True),
        (True, False, False),
        (True, True, False),
    ]


def test_kinds_and_trivial(vmax):
    kinds = dict(vmax.visits.select("visit_id", "kind").rows())
    vehicle = [
        visit_id(vmax, *k)
        for k in [
            ("b2", "T", "e8", "e8"),
            ("b3", "T", "e8", "e8"),
            ("s2", "T", "e24", "e24"),
            ("b7", "T", "e32", "e32"),
            ("b8", "T", "e38", "e38"),
        ]
    ]
    assert {kinds[i] for i in vehicle} == {"vehicle visit"}
    assert kinds[visit_id(vmax, "b1", "T", "e8", "e14")] == "transferring visit"
    assert kinds[visit_id(vmax, "b6", "T", "e27", "e29")] == "transferring visit"
    assert kinds[visit_id(vmax, "b5", None, "e16", "e17")] == "⊥ visit"
    trivial = vmax.visits.filter("is_trivial")
    assert (trivial["n_relations"] == 1).all() and trivial.height == 8


def test_excursions(vmax):
    ex = vmax.excursions
    m2 = visit_id(vmax, "b1", "A", "e3", "e11")
    row = ex.filter(pl.col("visit_id") == m2).row(0, named=True)
    assert (row["first_event"], row["last_event"], row["excursion_locations"]) == (
        "e7",
        "e8",
        ["B", "T"],
    )
    m16 = ex.filter(pl.col("visit_id") == visit_id(vmax, "b6", "A", "e26", "e30")).row(
        0, named=True
    )
    assert (m16["excursion_length"], m16["excursion_locations"]) == (3, ["B", "T"])
    m10 = visit_id(vmax, "b4", "B", "e15", "e21")
    assert ex.filter(pl.col("visit_id") == m10)["first_event"].to_list() == [
        "e18",
        "e20",
    ]
    counts = dict(vmax.visits.select("visit_id", "n_excursions").rows())
    assert counts[m10] == 2 and counts[visit_id(vmax, "b1", "B", "e7", "e7")] == 0
    # n_excursions = 0 iff uninterrupted
    assert ((vmax.visits["n_excursions"] == 0) == ~vmax.visits["interrupted"]).all()


def test_sweep_uses_the_excursion_table(vmax):
    """The excursions stored per maximal visit equal the runs of relations not at hl strictly inside it."""
    rel = add_mapping_inputs(vmax.relations, CONTEXT.vehicles, P)
    for trace in split_traces(rel, vmax.visits):
        for visit in trace.visits.values():
            inside = trace.high_levels[visit.first : visit.last + 1]
            expected = [
                (visit.first + a, visit.first + b)
                for a, b, at in python_runs(
                    [h == visit.high_level for h in inside], keep=lambda x: not x
                )
            ]
            assert list(visit.excursions) == expected


def test_rq4():
    tied = pl.DataFrame(
        {
            "hu": ["a", "a", "a"],
            "event": ["e1", "e2", "e3"],
            "time": [
                datetime(2026, 1, 1, 8, tzinfo=UTC),
                datetime(2026, 1, 1, 8, tzinfo=UTC),
                datetime(2026, 1, 1, 9, tzinfo=UTC),
            ],
            "high_level": ["A", None, "A"],
        }
    )
    found = rq4_violations(tied)
    assert found.select("hu", "events").rows() == [("a", ["e1", "e2"])]
    assert not flag_rq4(tied)
    assert flag_rq4(tied.filter(pl.col("event") != "e2"))


# --- dwell times, time inside / outside, overview ---


def test_dwell_times_add_up(vmax):
    per_visit = vmax.visit_relations.group_by("visit_id").agg(
        pl.col("dwell_time").sum()
    )
    joined = vmax.visits.select("visit_id", "duration").join(per_visit, on="visit_id")
    assert (joined["duration"] == joined["dwell_time"]).all()
    inside = vmax.overview.select("time_inside", "time_outside", "duration")
    assert (inside["time_inside"] + inside["time_outside"] == inside["duration"]).all()


def test_time_outside_and_transfer_targets(vmax):
    m16 = visit_id(vmax, "b6", "A", "e26", "e30")
    row = vmax.overview.filter(pl.col("visit_id") == m16).row(0, named=True)
    # external shift via ⟨e27, e28, e29⟩: time(e30) - time(e27) = 3 h outside A
    assert row["time_outside"] == timedelta(hours=3)
    assert row["external_shift_n_transfers"] == 1
    assert row["external_shift_duration_total"] == timedelta(hours=3)
    targets = vmax.transfer_targets.filter(pl.col("visit_id") == m16)
    assert dict(targets.select("target", "relations_total").rows()) == {"B": 1, "T": 2}
    m5 = visit_id(vmax, "b2", "A", "e3", "e11")
    t = vmax.transfer_targets.filter(pl.col("visit_id") == m5).row(0, named=True)
    assert (t["category"], t["target"], t["time_total"]) == (
        "vehicle shift",
        "T",
        timedelta(hours=1),
    )


def test_processing_statistics(vmax):
    stats = vmax.processing_statistics
    waits = vmax.waiting.waiting_times
    assert stats["n_operations"].sum() == waits.height
    assert stats["waiting_total"].sum() == waits["piece_duration"].sum()


# --- any visit set: a mapping set and a hand-written one ---


def test_analyse_mapping_is_disjoint_and_covering():
    mapping = derive_mapping_set(
        RELATIONS,
        "loc",
        CONTEXT.agg,
        CONTEXT.vehicles,
        3,
        P,
        "S6",
        CONTEXT.storage_units,
    )
    analysis = analyse_mapping(
        mapping, "loc", CONTEXT.vehicles, P, CONTEXT.storage_units
    )
    m = analysis.set_metrics.row(0, named=True)
    assert (m["n_visits"], m["p_cov"], m["p_dis"], m["n_in_several_visits"]) == (
        16,
        1.0,
        1.0,
        0,
    )
    assert (
        analysis.set_properties["is_disjoint"].all()
        and analysis.set_properties["is_covering"].all()
    )
    assert analysis.waiting is not None and analysis.overview.height == 16


def test_hand_written_visit_set(vmax):
    hand = pl.DataFrame(
        {
            "hu": ["b1", "b1"],
            "high_level": ["A", "T"],
            "first_event": ["e3", "e13"],
            "last_event": ["e5", "e14"],
        }
    )
    analysis = analyse_visit_set(
        vmax.relations, hand, "loc", CONTEXT.vehicles, P, with_waiting_times=False
    )
    props = analysis.set_properties.filter(pl.col("hu") == "b1").row(0, named=True)
    assert props["is_disjoint"] and not props["is_covering"]
    assert analysis.waiting is None
    assert analysis.visits["n_relations"].to_list() == [3, 2]
