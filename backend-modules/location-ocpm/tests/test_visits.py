"""Tests of maximal visits and shifts on the running example (values of the concept note and
the working doc) and on the small edge-case example in data/visits_example/."""

from pathlib import Path

import polars as pl
import pytest
from ocelescope_module_location_based_ocpm.derivation.level_files import MAPPING_SCHEMA
from ocelescope_module_location_based_ocpm.visits.context import location_context
from ocelescope_module_location_based_ocpm.visits.maximal import add_trace_positions, derive_maximal_visits
from ocelescope_module_location_based_ocpm.visits.order import add_tie_rank
from ocelescope_module_location_based_ocpm.visits.pipeline import VisitAnalysis, analyse_visits
from ocelescope_module_location_based_ocpm.visits.visit_files import load_visits, save_visits

DATA = Path(__file__).parents[3] / "data"
EXAMPLE = DATA / "running_example"
EDGE = DATA / "visits_example"
CONTEXT = location_context(pl.read_csv(EXAMPLE / "inputs" / "locations.csv"))
EDGE_CONTEXT = location_context(pl.read_csv(EDGE / "locations.csv"))
EDGE_P = pl.read_csv(EDGE / "processing_events.csv")["event"].to_list()
FRAMES = ("relations", "visits", "visit_relations", "transfers", "naming_clashes")


def hours(frame: pl.DataFrame, column: str) -> list[float | None]:
    """A duration column in hours."""
    return (frame[column].dt.total_seconds() / 3600).to_list()


def visit(analysis: VisitAnalysis, hu: str, high_level: str | None, first_event: str) -> dict:
    """The visits row of one visit, as a dict."""
    rows = analysis.visits.filter(
        (pl.col("hu") == hu)
        & pl.col("high_level").eq_missing(high_level)
        & (pl.col("first_event") == first_event)
    )
    assert rows.height == 1
    return rows.row(0, named=True)


def categories(analysis: VisitAnalysis, visit_id: int) -> list[str]:
    """Transfer categories of one visit in order."""
    return analysis.transfers.filter(pl.col("visit_id") == visit_id)["category"].to_list()


@pytest.fixture(scope="module")
def running(derivation) -> VisitAnalysis:
    """Running example, Level 3, κ = 2, P = T, W = {B1}."""
    return analyse_visits(
        derivation.relations, derivation.loc, CONTEXT.agg, CONTEXT.vehicles, kappa=2,
    )


@pytest.fixture(scope="module")
def edge() -> VisitAnalysis:
    """Edge-case example, κ = 1, explicit P, storage units S1, S2, B2."""
    relations = pl.read_csv(EDGE / "relations.csv", schema=MAPPING_SCHEMA)
    return analyse_visits(
        relations, "loc", EDGE_CONTEXT.agg, EDGE_CONTEXT.vehicles, kappa=1, processing=EDGE_P,
    )


def test_maximal_visits_match_the_note(running):
    """m1 to m11 of the note (κ = 2), including the ⊥ visit of c5."""
    got = running.visits.select("hu", "high_level", "first_event", "last_event").rows()
    assert sorted(got, key=str) == sorted(
        [
            ("s1", "A", "e1", "e3"),
            ("c1", "A", "e3", "e11"),
            ("c1", "B", "e7", "e7"),
            ("c1", "T", "e8", "e14"),
            ("c2", "A", "e3", "e11"),
            ("c2", "T", "e8", "e8"),
            ("c2", "B", "e12", "e15"),
            ("c3", "T", "e8", "e8"),
            ("c3", "B", "e10", "e14"),
            ("c4", "B", "e15", "e16"),
            ("c5", None, "e16", "e17"),
        ],
        key=str,
    )


@pytest.mark.parametrize("kappa, count", [(0, 14), (1, 13), (2, 11)])
def test_number_of_maximal_visits_per_kappa(derivation, kappa, count):
    """Review 1: 13, 12, 10 visits at hl ∈ HL for κ = 0, 1, 2, plus the ⊥ visit of c5."""
    _, visits = derive_maximal_visits(derivation.relations, derivation.loc, CONTEXT.agg, kappa)
    assert visits.height == count


def test_kappa_one_cuts_like_the_note(derivation):
    """Note, table for κ = 1: c1 at A is cut into e3-e5 and e9-e11, at T into e8 and e13-e14."""
    _, visits = derive_maximal_visits(derivation.relations, derivation.loc, CONTEXT.agg, 1)
    c1 = visits.filter(pl.col("hu") == "c1").select("high_level", "first_event", "last_event").rows()
    assert c1 == [("A", "e3", "e5"), ("B", "e7", "e7"), ("T", "e8", "e8"), ("A", "e9", "e11"), ("T", "e13", "e14")]


def test_exit_event_duration_and_interrupted(running):
    """m2: exit e13, d = 10 h, interrupted; m1 ends with the trace (exit = last event)."""
    m2 = visit(running, "c1", "A", "e3")
    assert (m2["exit_event"], m2["ends_trace"], m2["interrupted"]) == ("e13", False, True)
    assert m2["duration"].total_seconds() == 10 * 3600
    m1 = visit(running, "s1", "A", "e1")
    assert (m1["exit_event"], m1["ends_trace"], m1["interrupted"]) == ("e3", True, False)


def test_shifts_of_the_note(running):
    """Part A: m5 = stay, direct, vehicle, stay; m2 = stay, direct, external, stay; m9 only stays."""
    m5 = visit(running, "c2", "A", "e3")
    assert categories(running, m5["visit_id"]) == ["stay", "direct shift", "vehicle shift", "stay"]
    assert (m5["n_internal_shifts"], m5["n_external_shifts"]) == (2, 0)
    m2 = visit(running, "c1", "A", "e3")
    assert categories(running, m2["visit_id"]) == ["stay", "direct shift", "external shift", "stay"]
    assert (m2["n_internal_shifts"], m2["n_external_shifts"]) == (1, 1)
    assert m2["locations"] == ["A1", "A2", "B1", "T"] and m2["stop_locations"] == ["A1", "A2"]
    m9 = visit(running, "c3", "B", "e10")
    assert categories(running, m9["visit_id"]) == ["stay", "stay"]


def test_vehicle_and_transferring_visits_of_the_note(running):
    """Vehicle visits m6 and m8; m4 (c1 at T) is transferring; ⊥ visits get null."""
    vehicle = running.visits.filter(pl.col("is_vehicle_visit")).select("hu", "first_event").rows()
    assert sorted(vehicle) == [("c2", "e8"), ("c3", "e8")]
    transferring = running.visits.filter(pl.col("is_transferring_visit")).select("hu", "first_event").rows()
    assert transferring == [("c1", "e8")]
    bottom = visit(running, "c5", None, "e16")
    assert bottom["n_stops"] is None and bottom["is_vehicle_visit"] is None


@pytest.mark.parametrize("name", ["running", "edge"])
def test_transfers_add_up_to_stops_minus_one(name, request):
    """stays + direct + vehicle + external = m - 1 for every visit with at least one stop."""
    visits = request.getfixturevalue(name).visits.filter(pl.col("n_stops") > 0)
    total = visits["n_stays"] + visits["n_direct_shifts"] + visits["n_vehicle_shifts"] + visits["n_external_shifts"]
    assert total.to_list() == (visits["n_stops"] - 1).to_list()


def test_lazy_gives_the_same_frames(derivation, running):
    """The functions work on lazy frames with the same results."""
    lazy = analyse_visits(
        derivation.relations.lazy(), derivation.loc, CONTEXT.agg, CONTEXT.vehicles, kappa=2,
    )
    for name in FRAMES:
        assert getattr(lazy, name).equals(getattr(running, name)), name


def test_edge_all_four_categories_and_vehicles_inside_and_outside(edge):
    """h1 at A: stay, direct, vehicle shift via C1 (in A), vehicle shift via T (outside A, uses κ), external, stay."""
    h1 = visit(edge, "h1", "A", "e1")
    assert categories(edge, h1["visit_id"]) == [
        "stay", "direct shift", "vehicle shift", "vehicle shift", "external shift", "stay"
    ]
    assert h1["n_relations"] == 10 and h1["n_stops"] == 7


def test_edge_kappa_cuts_visits(edge):
    """Gaps longer than κ = 1 cut: h1 visits T twice, h4 visits A twice."""
    t = edge.visits.filter((pl.col("hu") == "h1") & (pl.col("high_level") == "T"))
    assert t["first_event"].to_list() == ["e6", "e11"]
    a = edge.visits.filter((pl.col("hu") == "h4") & (pl.col("high_level") == "A"))
    assert a["first_event"].to_list() == ["e27", "e32"]


def test_edge_vehicles_at_start_and_end_are_not_shifts(edge):
    """h2 at A starts and ends on the crane C1 (in A): two stops, one stay, no shifts."""
    h2 = visit(edge, "h2", "A", "e13")
    assert (h2["first_event"], h2["last_event"], h2["n_stops"]) == ("e13", "e16", 2)
    assert categories(edge, h2["visit_id"]) == ["stay"]
    assert edge.visits.filter(pl.col("hu") == "h2")["is_vehicle_visit"].to_list() == [True, False, True]


def test_edge_bottom(edge):
    """h3: ⊥ visits e19-e20 and e22 (κ(⊥) = 0), ⊥ inside a transfer is external."""
    bottom = edge.visits.filter((pl.col("hu") == "h3") & pl.col("high_level").is_null())
    assert bottom.select("first_event", "last_event").rows() == [("e19", "e20"), ("e22", "e22")]
    h3 = visit(edge, "h3", "A", "e21")
    assert categories(edge, h3["visit_id"]) == ["external shift", "vehicle shift"]


def test_edge_transferring_visit(edge):
    """h4 at T (e26-e29) has an excursion to A1 but no stops: transferring, not a vehicle visit."""
    h4 = visit(edge, "h4", "T", "e26")
    assert (h4["n_stops"], h4["is_vehicle_visit"], h4["is_transferring_visit"]) == (0, False, True)


def test_visit_files_round_trip(running, tmp_path):
    """save_visits / load_visits keep the core columns."""
    save_visits(running.visits, tmp_path, 3, 2)
    loaded = load_visits(tmp_path, 3, 2)
    assert loaded.drop("duration").equals(running.visits.select(loaded.drop("duration").columns))
    assert loaded["duration"].equals(running.visits["duration"])


def test_ignore_vehicles_running_example(derivation):
    """κ = 1 with ignore_vehicles: c1's A visit is no longer cut at ⟨e7 B1, e8 T⟩ (only B1 counts), T still is."""
    _, visits = derive_maximal_visits(
        derivation.relations, derivation.loc, CONTEXT.agg, 1, CONTEXT.vehicles, ignore_vehicles=True
    )
    c1 = visits.filter(pl.col("hu") == "c1").select("high_level", "first_event", "last_event").rows()
    assert c1 == [("A", "e3", "e11"), ("B", "e7", "e7"), ("T", "e8", "e8"), ("T", "e13", "e14")]
    assert visits.height == 12


def test_ignore_vehicles_edge_example():
    """κ = 0 with ignore_vehicles: h1 at A runs on across ⟨e6 on T⟩ and is cut only at e8 (B1)."""
    relations = pl.read_csv(EDGE / "relations.csv", schema=MAPPING_SCHEMA)
    _, default = derive_maximal_visits(relations, "loc", EDGE_CONTEXT.agg, 0, EDGE_CONTEXT.vehicles)
    _, ignoring = derive_maximal_visits(relations, "loc", EDGE_CONTEXT.agg, 0, EDGE_CONTEXT.vehicles, True)

    def h1_a(visits: pl.DataFrame) -> list[tuple]:
        """h1's visits to A as (first, last event)."""
        return visits.filter((pl.col("hu") == "h1") & (pl.col("high_level") == "A")).select(
            "first_event", "last_event"
        ).rows()

    assert h1_a(default) == [("e1", "e5"), ("e7", "e7"), ("e9", "e10")]
    assert h1_a(ignoring) == [("e1", "e7"), ("e9", "e10")]


def test_ignore_vehicles_keeps_bottom_strict():
    """⊥ visits allow no excursions, also with ignore_vehicles: ⊥, T, ⊥ gives two ⊥ visits."""
    import datetime as dt

    relations = pl.DataFrame(
        {
            "hu": ["x"] * 3,
            "event": ["a", "b", "c"],
            "time": [dt.datetime(2026, 1, 1, h) for h in (1, 2, 3)],
            "is_movement": [False, True, False],
            "is_transformation": [False] * 3,
            "loc": [None, "T", None],
        }
    )
    _, visits = derive_maximal_visits(relations, "loc", None, 2, {"T"}, ignore_vehicles=True)
    assert visits.filter(pl.col("high_level").is_null()).height == 2


def test_tie_rank_as4():
    """AS4 groups: movements (also if processing) 0, processing operations 1, others 2; lazy alike."""
    frame = pl.DataFrame(
        {
            "event": ["a", "b", "c", "d"],
            "is_movement": [True, True, False, None],
            "is_transformation": [False, True, True, False],
        }
    )
    assert add_tie_rank(frame)["tie_rank"].to_list() == [0, 0, 1, 2]
    assert add_tie_rank(frame, processing={"d"})["tie_rank"].to_list() == [0, 0, 2, 1]
    assert add_tie_rank(frame.lazy()).collect().equals(add_tie_rank(frame))


def test_edge_ties_follow_as4(edge):
    """h7: equal timestamps are ordered movements, processing operations, rest (against the event ids)."""
    h7 = edge.relations.filter(pl.col("hu") == "h7").sort("position")
    assert h7["event"].to_list() == ["e53", "e55", "e54", "e57", "e56", "e58"]


def test_trace_order_uses_processing_input():
    """The tie-break uses the given P, not T: with P = {b}, b comes before the other event a."""
    import datetime as dt

    t = dt.datetime(2026, 1, 1)
    relations = pl.DataFrame(
        {
            "hu": ["x", "x"],
            "event": ["a", "b"],
            "time": [t, t],
            "is_movement": [False, False],
            "is_transformation": [False, False],
        }
    )
    assert add_trace_positions(relations)["event"].to_list() == ["a", "b"]
    assert add_trace_positions(relations, processing={"b"})["event"].to_list() == ["b", "a"]





def test_excursion_measures_and_further_conditions(derivation):
    """DD-V1: c1's A visit has the deviating infix ⟨e7, e8⟩ (2 events, 2 timestamps, 2 h from e7 to e9).
    Without a limit on events (kappa=None), it is cut by max_timestamps=1 or max_excursion_duration=1 h,
    but not by max_excursion_duration=2 h; conditions combine (any violation cuts)."""
    from datetime import timedelta

    rel, _ = derive_maximal_visits(derivation.relations, derivation.loc, CONTEXT.agg, None)
    e9 = rel.filter((pl.col("hu") == "c1") & (pl.col("event") == "e9")).row(0, named=True)
    assert (e9["gap"], e9["gap_timestamps"], e9["gap_duration"]) == (2, 2, timedelta(hours=2))

    def c1_a(**kwargs) -> list[tuple]:
        """c1's visits to A as (first, last event)."""
        _, visits = derive_maximal_visits(derivation.relations, derivation.loc, CONTEXT.agg, **kwargs)
        return visits.filter((pl.col("hu") == "c1") & (pl.col("high_level") == "A")).select(
            "first_event", "last_event"
        ).rows()

    cut, whole = [("e3", "e5"), ("e9", "e11")], [("e3", "e11")]
    assert c1_a(kappa=None) == whole
    assert c1_a(kappa=None, max_timestamps=1) == cut
    assert c1_a(kappa=None, max_timestamps=2) == whole
    assert c1_a(kappa=None, max_excursion_duration=timedelta(hours=1)) == cut
    assert c1_a(kappa=None, max_excursion_duration=timedelta(hours=2)) == whole
    assert c1_a(kappa=2, max_excursion_duration=timedelta(hours=1)) == cut


def test_bottom_tolerance_stays_zero_without_kappa():
    """DD-V3: with kappa=None, ⊥ still allows no excursions (⊥, A1, ⊥ gives two ⊥ visits)."""
    import datetime as dt

    relations = pl.DataFrame(
        {
            "hu": ["x"] * 3,
            "event": ["a", "b", "c"],
            "time": [dt.datetime(2026, 1, 1, h) for h in (1, 2, 3)],
            "is_movement": [False] * 3,
            "is_transformation": [False] * 3,
            "loc": [None, "A1", None],
        }
    )
    _, visits = derive_maximal_visits(relations, "loc", None, None)
    assert visits.filter(pl.col("high_level").is_null()).height == 2


def test_naming_clashes():
    """An unmapped location named like a provided high-level location is flagged."""
    from ocelescope_module_location_based_ocpm.visits.context import naming_clashes

    clashes = naming_clashes(["A1", "B", "B1", "T"], {"A1": "A", "B1": "B"})
    assert clashes.rows() == [("B", ["B1"])]
    assert naming_clashes(["A1", "T"], {"A1": "A"}).height == 0


def test_no_naming_clashes_in_the_examples(running, edge):
    """Neither example has a naming clash."""
    assert running.naming_clashes.height == 0 and edge.naming_clashes.height == 0


def test_transfer_durations(running):
    """d(μ): m5's vehicle shift via ⟨e8⟩ takes 1 h (e8 to e9), m2's external shift via ⟨e7, e8⟩ 2 h; empty
    transfers take 0."""
    m5 = visit(running, "c2", "A", "e3")
    t5 = running.transfers.filter(pl.col("visit_id") == m5["visit_id"])
    assert hours(t5, "transfer_duration") == [0, 0, 1, 0]
    m2 = visit(running, "c1", "A", "e3")
    t2 = running.transfers.filter(pl.col("visit_id") == m2["visit_id"])
    assert hours(t2, "transfer_duration") == [0, 0, 2, 0]
    assert m2["external_shift_time"].total_seconds() == 2 * 3600 and m2["internal_shift_time"].total_seconds() == 0
    assert m5["internal_shift_time"].total_seconds() == 3600


def test_vehicles_outside_external(derivation):
    """DD-S1: with vehicles_outside_external, m5's trip on the truck T (outside A) is an external shift;
    on the edge example, h1's trip via the crane C1 (in A) stays a vehicle shift, the one via T does not."""
    analysis = analyse_visits(
        derivation.relations, derivation.loc, CONTEXT.agg, CONTEXT.vehicles, kappa=2,
        vehicles_outside_external=True,
    )
    m5 = visit(analysis, "c2", "A", "e3")
    assert categories(analysis, m5["visit_id"]) == ["stay", "direct shift", "external shift", "stay"]
    relations = pl.read_csv(EDGE / "relations.csv", schema=MAPPING_SCHEMA)
    edge_option = analyse_visits(
        relations, "loc", EDGE_CONTEXT.agg, EDGE_CONTEXT.vehicles, kappa=1, processing=EDGE_P,
        vehicles_outside_external=True,
    )
    h1 = visit(edge_option, "h1", "A", "e1")
    assert categories(edge_option, h1["visit_id"]) == [
        "stay", "direct shift", "vehicle shift", "external shift", "external shift", "stay"
    ]
