"""Tests of waiting times (`waiting_times` package): with visits on the running example (values of the
concept note and the working doc) and the edge-case example in data/visits_example/, and without visits."""

from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest
from ocelescope_module_location_based_ocpm.derivation.level_files import MAPPING_SCHEMA
from ocelescope_module_location_based_ocpm.visits.context import location_context
from ocelescope_module_location_based_ocpm.visits.pipeline import analyse_visits
from ocelescope_module_location_based_ocpm.waiting_times.pipeline import analyse_waiting_times

DATA = Path(__file__).parents[3] / "data"
EXAMPLE = DATA / "running_example"
EDGE = DATA / "visits_example"
CONTEXT = location_context(pl.read_csv(EXAMPLE / "inputs" / "locations.csv"))
EDGE_CONTEXT = location_context(pl.read_csv(EDGE / "locations.csv"))
EDGE_P = pl.read_csv(EDGE / "processing_events.csv")["event"].to_list()
FRAMES = (
    "scopes", "scope_relations", "pieces", "waiting_times", "summary", "simultaneous_processing",
    "negative_waiting_times",
)


def hours(frame: pl.DataFrame, column: str) -> list[float | None]:
    """A duration column in hours."""
    return (frame[column].dt.total_seconds() / 3600).to_list()


def analyse(relations, location, agg, vehicles, kappa, processing=None, **options) -> SimpleNamespace:
    """Maximal visits, then waiting times per visit; visits carry the waiting summary (null at ⊥)."""
    visits = analyse_visits(relations, location, agg, vehicles, kappa=kappa, processing=processing)
    waiting = analyse_waiting_times(
        visits.relations, location, visits.visits, processing=processing, **options
    )
    return SimpleNamespace(
        relations=visits.relations,
        visits=visits.visits.join(waiting.summary, on="visit_id", how="left"),
        pieces=waiting.pieces,
        waiting_times=waiting.waiting_times,
        simultaneous_processing=waiting.simultaneous_processing,
        waiting=waiting,
    )


def visit(analysis, hu: str, high_level: str | None, first_event: str) -> dict:
    """The visits row of one visit, as a dict."""
    rows = analysis.visits.filter(
        (pl.col("hu") == hu)
        & pl.col("high_level").eq_missing(high_level)
        & (pl.col("first_event") == first_event)
    )
    assert rows.height == 1
    return rows.row(0, named=True)


def edge_relations() -> pl.DataFrame:
    """The relations of the edge-case example."""
    return pl.read_csv(EDGE / "relations.csv", schema=MAPPING_SCHEMA)


@pytest.fixture(scope="module")
def running(derivation) -> SimpleNamespace:
    """Running example, Level 3, κ = 2, P = T, W = {B1}."""
    return analyse(
        derivation.relations, derivation.loc, CONTEXT.agg, CONTEXT.vehicles, kappa=2,
        storage_units=CONTEXT.storage_units,
    )


@pytest.fixture(scope="module")
def edge() -> SimpleNamespace:
    """Edge-case example, κ = 1, explicit P, storage units S1, S2, B2."""
    return analyse(
        edge_relations(), "loc", EDGE_CONTEXT.agg, EDGE_CONTEXT.vehicles, kappa=1, processing=EDGE_P,
        storage_units=EDGE_CONTEXT.storage_units,
    )


def test_waiting_times_of_the_working_doc(derivation):
    """Part C.2 with P = {e1, e3, e4, e15} and no storage units."""
    analysis = analyse(
        derivation.relations, derivation.loc, CONTEXT.agg, CONTEXT.vehicles, kappa=2, processing=["e1", "e3", "e4", "e15"]
    )
    expected = {  # (hu, hl, first event): (waiting times, remaining time) in hours
        ("c2", "A", "e3"): ([0, 1], 8),
        ("s1", "A", "e1"): ([0, 2], 0),
        ("c2", "B", "e12"): ([3], 0),
        ("c1", "A", "e3"): ([0, 1], 9),
        ("c3", "B", "e10"): ([], 4),
    }
    for key, (waits, remaining) in expected.items():
        row = visit(analysis, *key)
        got = analysis.waiting_times.filter(pl.col("visit_id") == row["visit_id"])
        assert hours(got, "piece_duration") == waits, key
        assert row["remaining_time"].total_seconds() / 3600 == remaining, key


def test_default_processing_is_t(running):
    """Without P, the transformation events are used: c2's A visit has only e3 (roll)."""
    m5 = visit(running, "c2", "A", "e3")
    assert (m5["n_processing"], m5["remaining_time"].total_seconds() / 3600) == (1, 9)


@pytest.mark.parametrize("name", ["running", "edge"])
def test_pieces_add_up_to_duration(name, request):
    """Waiting + storage + remaining time = d for every visit at hl ∈ HL."""
    visits = request.getfixturevalue(name).visits.filter(pl.col("high_level").is_not_null())
    total = visits["total_waiting_time"] + visits["total_storage_time"] + visits["remaining_time"]
    assert total.equals(visits["duration"], check_names=False)


def test_storage_example_of_the_working_doc(derivation):
    """C.6: m2 with W = {B1} and P = {e1, e3, e4, e15}: waiting 0, 1, storage 4 (removal e8 outside A), remaining 5."""
    analysis = analyse(
        derivation.relations, derivation.loc, CONTEXT.agg, CONTEXT.vehicles, kappa=2,
        processing=["e1", "e3", "e4", "e15"], storage_units={"B1"},
    )
    m2 = visit(analysis, "c1", "A", "e3")
    pieces = analysis.pieces.filter(pl.col("visit_id") == m2["visit_id"])
    assert pieces["label"].to_list() == ["waiting", "waiting", "storage", "remaining"]
    assert hours(pieces, "piece_duration") == [0, 1, 4, 5]
    assert pieces["end_event"].to_list() == ["e3", "e4", "e8", "e13"]


def test_edge_storage(edge):
    """h6: S1 -> S2 is no removal; removal e44; processing removal e48 waits 4 h incl. storage (concept
    since 2026-11-01); removal e50 outside A."""
    a = visit(edge, "h6", "A", "e42")
    pieces = edge.pieces.filter(pl.col("visit_id") == a["visit_id"])
    assert pieces.select("label", "end_event").rows() == [
        ("storage", "e44"), ("waiting", "e46"), ("waiting", "e48"),
        ("storage", "e50"), ("waiting", "e51"), ("remaining", "e52"),
    ]
    assert hours(pieces, "piece_duration") == [5, 3, 4, 3, 1, 2]
    assert (a["n_processing"], a["n_storage_removals"]) == (3, 2)


def test_edge_storage_zero_wait_at_removal():
    """zero_wait_at_removal=True: e48 ends a storage piece (4 h) and gets a waiting time of 0."""
    relations = edge_relations()
    analysis = analyse(
        relations, "loc", EDGE_CONTEXT.agg, EDGE_CONTEXT.vehicles, kappa=1, processing=EDGE_P,
        storage_units=EDGE_CONTEXT.storage_units, zero_wait_at_removal=True,
    )
    a = visit(analysis, "h6", "A", "e42")
    pieces = analysis.pieces.filter(pl.col("visit_id") == a["visit_id"])
    assert pieces.select("label", "end_event").rows() == [
        ("storage", "e44"), ("waiting", "e46"), ("storage", "e48"), ("waiting", "e48"),
        ("storage", "e50"), ("waiting", "e51"), ("remaining", "e52"),
    ]
    assert hours(pieces, "piece_duration") == [5, 3, 4, 0, 3, 1, 2]
    assert (a["n_processing"], a["n_storage_removals"]) == (3, 3)
    total = a["total_waiting_time"] + a["total_storage_time"] + a["remaining_time"]
    assert total == a["duration"]


def test_no_storage_units_is_the_earlier_version(derivation, running):
    """Without W, every piece is waiting or remaining, and Σ w + w_rem = d (C.1)."""
    analysis = analyse(derivation.relations, derivation.loc, CONTEXT.agg, CONTEXT.vehicles, kappa=2)
    assert set(analysis.pieces["label"]) <= {"waiting", "remaining"}
    assert analysis.visits["n_storage_removals"].drop_nulls().sum() == 0


def test_edge_waiting_times(edge):
    """h5: processing on C1 counts for A, paint at B (excursion) counts for B, processing movements."""
    a = visit(edge, "h5", "A", "e33")
    got = edge.waiting_times.filter(pl.col("visit_id") == a["visit_id"])
    assert got["end_event"].to_list() == ["e35", "e36"] and hours(got, "piece_duration") == [3, 1]
    assert (a["exit_event"], a["remaining_time"].total_seconds() / 3600) == ("e40", 6)
    for first in ("e37", "e40"):  # processing movements into B: entry by processing, w_1 = 0
        b = visit(edge, "h5", "B", first)
        got = edge.waiting_times.filter(pl.col("visit_id") == b["visit_id"])
        assert got["end_event"].to_list() == [first] and hours(got, "piece_duration") == [0]
    h1 = visit(edge, "h1", "A", "e1")
    assert hours(edge.waiting_times.filter(pl.col("visit_id") == h1["visit_id"]), "piece_duration") == [0, 12]


def test_waiting_times_carry_activities(edge):
    """Every piece has the activities of its start and end event; waiting times group by the processing activity."""
    assert edge.pieces["end_activity"].null_count() == 0 and edge.pieces["start_activity"].null_count() == 0
    roll = edge.waiting_times.filter(pl.col("end_activity") == "roll")
    assert roll.select("hu", "end_event", "start_activity").rows() == [
        ("h5", "e35", "crane move"), ("h6", "e46", "crane pick"), ("h7", "e57", "grind"), ("h8", "e61", "grind")
    ]
    assert hours(roll, "piece_duration") == [3, 3, 2, 0]


def test_outside_storage_resets_option(derivation):
    """C.6 example m2: by default the removal e8 from B1 (outside A) resets the clock; with
    outside_storage_resets=False it does not, so after e4 only remaining time follows (9 h)."""
    kwargs = dict(kappa=2, processing=["e1", "e3", "e4", "e15"], storage_units={"B1"})
    for outside, labels, durations in (
        (True, ["waiting", "waiting", "storage", "remaining"], [0, 1, 4, 5]),
        (False, ["waiting", "waiting", "remaining"], [0, 1, 9]),
    ):
        analysis = analyse(
            derivation.relations, derivation.loc, CONTEXT.agg, CONTEXT.vehicles,
            outside_storage_resets=outside, **kwargs,
        )
        m2 = visit(analysis, "c1", "A", "e3")
        pieces = analysis.pieces.filter(pl.col("visit_id") == m2["visit_id"])
        assert pieces["label"].to_list() == labels
        assert hours(pieces, "piece_duration") == durations


def test_outside_storage_resets_edge():
    """h6 with outside_storage_resets=False: the removal e50 from B2 (in B) no longer resets the clock,
    so the grind e51 waits 4 h from e48; the inside removal e44 still counts."""
    relations = edge_relations()
    analysis = analyse(
        relations, "loc", EDGE_CONTEXT.agg, EDGE_CONTEXT.vehicles, kappa=1, processing=EDGE_P,
        storage_units=EDGE_CONTEXT.storage_units, outside_storage_resets=False,
    )
    a = visit(analysis, "h6", "A", "e42")
    pieces = analysis.pieces.filter(pl.col("visit_id") == a["visit_id"])
    assert pieces.select("label", "end_event").rows() == [
        ("storage", "e44"), ("waiting", "e46"), ("waiting", "e48"), ("waiting", "e51"), ("remaining", "e52"),
    ]
    assert hours(pieces, "piece_duration") == [5, 3, 4, 4, 2]


def test_skip_simultaneous_removal(edge):
    """h7: by default (DD-W4) the grind e54 waits 0 after the removal e55 at the same time; with
    skip_simultaneous_removal the removal is skipped and the grind waits 3 h from the entry."""
    a = visit(edge, "h7", "A", "e53")
    default = edge.pieces.filter(pl.col("visit_id") == a["visit_id"])
    assert hours(default.filter(pl.col("end_event") == "e54"), "piece_duration") == [0]
    relations = edge_relations()
    skip = analyse(
        relations, "loc", EDGE_CONTEXT.agg, EDGE_CONTEXT.vehicles, kappa=1, processing=EDGE_P,
        storage_units=EDGE_CONTEXT.storage_units, skip_simultaneous_removal=True,
    )
    pieces = skip.pieces.filter(pl.col("visit_id") == a["visit_id"])
    assert pieces.select("start_event", "end_event", "label").rows() == [
        ("e53", "e54", "waiting"), ("e54", "e57", "waiting"), ("e57", "e58", "remaining")
    ]
    assert hours(pieces, "piece_duration") == [3, 2, 1]
    # Only h7 has such a removal: all other pieces are unchanged.
    others = pl.col("hu") != "h7"
    assert skip.pieces.filter(others).equals(edge.pieces.filter(others))


def test_simultaneous_processing_flag(edge):
    """RQ5 flag: h8 has two processing operations at the same timestamp; AS4 orders them by id."""
    flag = edge.simultaneous_processing
    assert flag.select("hu", "events", "n_events").rows() == [("h8", ["e60", "e61"], 2)]
    h8 = edge.waiting_times.filter(pl.col("hu") == "h8")
    assert h8.select("start_event", "end_event").rows() == [("e59", "e60"), ("e60", "e61")]
    assert hours(h8, "piece_duration") == [2, 0]


def test_bottom_visits_have_no_waiting_times(running):
    """DD-W7: the ⊥ visit of c5 is no scope, its summary columns are null."""
    bottom = visit(running, "c5", None, "e16")
    assert bottom["remaining_time"] is None and bottom["n_processing"] is None
    assert running.waiting.scopes["high_level"].null_count() == 0


def test_processing_visit(running):
    """A visit with Q(ν) ≠ ∅ is a processing visit: c2's A visit (roll e3), not c3's B visit."""
    assert visit(running, "c2", "A", "e3")["is_processing_visit"] is True
    assert visit(running, "c3", "B", "e10")["is_processing_visit"] is False


def test_storage_removals_reset_option(derivation):
    """DD-W5: storage_removals_reset=False ignores W: m2 has waiting 0, 1 and remaining 9 h."""
    analysis = analyse(
        derivation.relations, derivation.loc, CONTEXT.agg, CONTEXT.vehicles, kappa=2,
        processing=["e1", "e3", "e4", "e15"], storage_units={"B1"}, storage_removals_reset=False,
    )
    m2 = visit(analysis, "c1", "A", "e3")
    pieces = analysis.pieces.filter(pl.col("visit_id") == m2["visit_id"])
    assert pieces["label"].to_list() == ["waiting", "waiting", "remaining"]
    assert hours(pieces, "piece_duration") == [0, 1, 9]


def test_edge_ties_waiting_times(edge):
    """h7 (AS4): the removal e55 comes before the grind e54 at t = 3: storage 3 h, grind waits 0 (DD-W4)."""
    a = visit(edge, "h7", "A", "e53")
    pieces = edge.pieces.filter(pl.col("visit_id") == a["visit_id"])
    assert pieces.select("start_event", "end_event", "label").rows() == [
        ("e53", "e55", "storage"), ("e55", "e54", "waiting"), ("e54", "e57", "waiting"), ("e57", "e58", "remaining"),
    ]
    assert hours(pieces, "piece_duration") == [3, 0, 2, 1]


def test_without_visits_running_example(derivation):
    """DD-W6 without visits: c1's whole trace e3 ... e14 is one scope (P = {e1, e3, e4, e15}, W = {B1}):
    waiting 0 (roll e3, first event), 1 h (label e4), storage until the removal e8 (4 h), remaining until
    the trace end e14 (6 h)."""
    waiting = analyse_waiting_times(
        derivation.relations, derivation.loc, processing=["e1", "e3", "e4", "e15"], storage_units={"B1"}
    )
    c1 = waiting.pieces.filter(pl.col("hu") == "c1")
    assert c1.select("label", "end_event").rows() == [
        ("waiting", "e3"), ("waiting", "e4"), ("storage", "e8"), ("remaining", "e14"),
    ]
    assert hours(c1, "piece_duration") == [0, 1, 4, 6]
    assert waiting.scopes["high_level"].null_count() == waiting.scopes.height
    totals = waiting.summary.join(waiting.scopes.select("visit_id", "duration"), on="visit_id")
    total = totals["total_waiting_time"] + totals["total_storage_time"] + totals["remaining_time"]
    assert total.equals(totals["duration"], check_names=False)


def test_without_visits_counts_processing_everywhere(derivation):
    """Without visits, processing during an excursion resets the clock too: c2's cut e15 (in B) waits from
    the previous clock event of the whole trace, not from the entry into B."""
    with_visits = analyse(
        derivation.relations, derivation.loc, CONTEXT.agg, CONTEXT.vehicles, kappa=2,
        processing=["e1", "e3", "e4", "e15"],
    )
    without = analyse_waiting_times(derivation.relations, derivation.loc, processing=["e1", "e3", "e4", "e15"])
    cut_with = with_visits.waiting_times.filter((pl.col("hu") == "c2") & (pl.col("end_event") == "e15"))
    cut_without = without.waiting_times.filter((pl.col("hu") == "c2") & (pl.col("end_event") == "e15"))
    assert hours(cut_with, "piece_duration") == [3]
    assert cut_without["start_event"].to_list() == ["e4"]
    assert hours(cut_without, "piece_duration") == [11]


def test_without_visits_lazy_and_positions(derivation):
    """Without visits, raw relations (no position) work eagerly and lazily alike."""
    eager = analyse_waiting_times(derivation.relations, derivation.loc)
    lazy = analyse_waiting_times(derivation.relations.lazy(), derivation.loc)
    for name in FRAMES:
        assert getattr(lazy, name).equals(getattr(eager, name)), name


def test_with_visits_lazy(derivation, running):
    """With visits, lazy frames give the same results."""
    visits = analyse_visits(derivation.relations.lazy(), derivation.loc, CONTEXT.agg, CONTEXT.vehicles, kappa=2)
    lazy = analyse_waiting_times(
        visits.relations.lazy(), derivation.loc, visits.visits.lazy(), storage_units=CONTEXT.storage_units
    )
    for name in FRAMES:
        assert getattr(lazy, name).equals(getattr(running.waiting, name)), name


def test_visits_need_positions(derivation):
    """With visits, the relations must come from the visit derivation."""
    visits = analyse_visits(derivation.relations, derivation.loc, CONTEXT.agg, CONTEXT.vehicles, kappa=2)
    with pytest.raises(ValueError, match="position"):
        analyse_waiting_times(derivation.relations, derivation.loc, visits.visits)


def test_processing_durations():
    """DD-W3: the duration of the operation itself is deducted from its waiting time; negative ones are
    flagged. h5: roll e35 waits 3 h and weigh e36 1 h; durations of 1 h and 4 h give 2 h and -3 h."""
    relations = edge_relations().with_columns(
        pl.when(pl.col("event") == "e35").then(1.0)
        .when(pl.col("event") == "e36").then(4.0)
        .otherwise(None)
        .alias("duration_h")
    )
    analysis = analyse(
        relations, "loc", EDGE_CONTEXT.agg, EDGE_CONTEXT.vehicles, kappa=1, processing=EDGE_P,
        storage_units=EDGE_CONTEXT.storage_units, processing_duration="duration_h", duration_unit="h",
    )
    h5 = analysis.waiting_times.filter(pl.col("end_event").is_in(["e35", "e36"])).sort("end_event")
    assert hours(h5, "piece_duration") == [3, 1]
    assert hours(h5, "net_waiting_time") == [2, -3]
    assert h5["negative_waiting_time"].to_list() == [False, True]
    assert analysis.waiting.negative_waiting_times["end_event"].to_list() == ["e36"]
    others = analysis.waiting_times.filter(~pl.col("end_event").is_in(["e35", "e36"]))
    assert others["net_waiting_time"].equals(others["piece_duration"], check_names=False)


def test_processing_durations_as_duration_column():
    """A duration-typed attribute works without a unit."""
    relations = edge_relations().with_columns(
        pl.when(pl.col("event") == "e35").then(pl.duration(hours=1)).otherwise(None).alias("duration")
    )
    waiting = analyse_waiting_times(
        relations, "loc", processing=EDGE_P, processing_duration="duration"
    )
    roll = waiting.waiting_times.filter(pl.col("end_event") == "e35")
    assert (roll["piece_duration"] - roll["net_waiting_time"]).to_list() == [timedelta(hours=1)]
