"""Directly-follows graph (docs/pages/directly-follows-graph.md): traces, path filter, arc filter, nodes."""

from datetime import datetime, timedelta

import polars as pl
import pytest

from ocelescope_module_location_based_ocpm.dfg.graph import (
    DfgRequest,
    LogFrames,
    TypeSetting,
    directly_follows_graph,
    TypeThresholds,
    log_frames,
    resolve_selection,
    selected_traces,
)


@pytest.fixture(scope="module")
def frames(ocel, derivation) -> LogFrames:
    """The running example's frames."""
    return log_frames(ocel, derivation)


def arcs_of(graph, object_type):
    """The arcs of one object type as {(source, target): (count, objects)}."""
    return {(a.source, a.target): (a.count, a.objects) for a in graph.arcs if a.object_type == object_type}


ALL = {"path_threshold": 100, "arc_threshold": 100}


def full(*types):
    """Selection of the given types with all paths and all arcs."""
    return [TypeSetting(object_type=t, **ALL) for t in types]


def test_default_selects_the_handling_unit_types(frames):
    graph = directly_follows_graph(frames)
    assert [(t.object_type, t.selected, t.objects) for t in graph.object_types] == [
        ("coil", True, 5),
        ("slab", True, 1),
    ]


def test_default_thresholds(frames):
    graph = directly_follows_graph(frames)
    coil = next(t for t in graph.object_types if t.object_type == "coil")
    # 30 % of 5 coils with 5 different paths: 2 paths; 10 % of their arcs between activities, rounded up.
    assert (coil.path_threshold, coil.arc_threshold, coil.kept_paths, coil.kept_objects) == (30, 10, 2, 2)


def test_running_example_arcs(frames):
    graph = directly_follows_graph(frames, full("coil", "slab"))
    assert arcs_of(graph, "slab") == {
        (None, "cast slab"): (1, 1),
        ("cast slab", "inspect slab"): (1, 1),
        ("inspect slab", "roll"): (1, 1),
        ("roll", None): (1, 1),
    }
    coil = arcs_of(graph, "coil")
    assert len(coil) == 18
    assert coil[("load truck", "unload truck")] == (3, 3)
    assert coil[(None, "roll")] == (2, 2)
    assert coil[("quality check", None)] == (4, 4)
    # Every coil has exactly one start and one end arc.
    assert sum(n for (s, _), (n, _) in coil.items() if s is None) == 5
    assert sum(n for (_, t), (n, _) in coil.items() if t is None) == 5


def test_activity_frequencies(frames):
    graph = directly_follows_graph(frames, full("coil", "slab"))
    events = {a.activity: a.events for a in graph.activities}
    assert events == {
        "cast slab": 1, "crane move": 4, "cut": 1, "inspect slab": 1, "label": 1,
        "load truck": 2, "quality check": 4, "roll": 1, "unload truck": 2,
    }
    roll = next(a for a in graph.activities if a.activity == "roll")
    assert [(t.object_type, t.events, t.objects) for t in roll.object_types] == [("coil", 1, 2), ("slab", 1, 1)]


def test_unselected_type_is_only_involved(frames):
    graph = directly_follows_graph(frames, full("coil"))
    assert arcs_of(graph, "slab") == {}
    assert "cast slab" not in {a.activity for a in graph.activities}
    roll = next(a for a in graph.activities if a.activity == "roll")
    assert {t.object_type for t in roll.object_types} == {"coil", "slab"}


def test_path_threshold_keeps_most_frequent_paths(frames):
    # All five coils have different paths; 50 % of 5 coils keeps paths until 2.5 coils are covered: 3 paths.
    graph = directly_follows_graph(frames, [TypeSetting(object_type="coil", path_threshold=50, arc_threshold=100)])
    coil = next(t for t in graph.object_types if t.object_type == "coil")
    assert (coil.paths, coil.kept_paths, coil.kept_objects) == (5, 3, 3)
    none = directly_follows_graph(frames, [TypeSetting(object_type="coil", path_threshold=0, arc_threshold=100)])
    assert none.arcs == [] and none.activities == []


def test_arc_threshold_keeps_most_frequent_relations_and_all_start_and_end_arcs(frames):
    # coil has 18 arcs: 6 start/end arcs and 12 between activities; 20 % of 12 = 2.4, rounded up 3 most frequent.
    graph = directly_follows_graph(frames, [TypeSetting(object_type="coil", path_threshold=100, arc_threshold=20)])
    coil = arcs_of(graph, "coil")
    inner = {k: v for k, v in coil.items() if None not in k}
    assert inner == {
        ("load truck", "unload truck"): (3, 3),
        ("unload truck", "crane move"): (3, 3),
        ("crane move", "load truck"): (2, 2),
    }
    assert len(coil) - len(inner) == 6
    only_ends = directly_follows_graph(frames, [TypeSetting(object_type="coil", path_threshold=100, arc_threshold=0)])
    assert all(None in k for k in arcs_of(only_ends, "coil"))


def test_deselected_activity_removes_node_and_arcs_only(frames):
    graph = directly_follows_graph(frames, full("coil", "slab"), excluded_activities=["label"])
    assert "label" not in {a.activity for a in graph.activities}
    coil = arcs_of(graph, "coil")
    assert ("roll", "label") not in coil and ("label", "crane move") not in coil
    assert ("roll", "crane move") not in coil  # no projection: no new arc between the neighbours
    options = {o.activity: o for o in graph.activity_options}
    assert options["label"].on_included_trace
    assert [o.activity for o in graph.activity_options][:2] == ["crane move", "quality check"]


def test_unknown_or_unshown_activity_changes_nothing(frames):
    base = directly_follows_graph(frames, full("coil"))
    same = directly_follows_graph(frames, full("coil"), excluded_activities=["cast slab"])
    assert base.arcs == same.arcs and base.activities == same.activities


def _synthetic_frames(handling_units: list[str]) -> LogFrames:
    """Two pallets and a truck; e2 and e3 share a timestamp (e3 is a movement, so it comes first by AS4)."""
    t = [datetime(2026, 1, 1, h) for h in (1, 2, 2, 3)]
    events = pl.DataFrame(
        {
            "event": ["e1", "e2", "e3", "e4"],
            "time": t,
            "activity": ["pick", "pack", "move", "ship"],
            "is_movement": [False, False, True, True],
            "is_transformation": [False, False, False, False],
            "is_processing": [False, False, False, False],
        }
    )
    objects = pl.DataFrame({"object": ["p1", "p2", "t1"], "object_type": ["pallet", "pallet", "truck"]})
    e2o = pl.DataFrame(
        {"event": ["e1", "e2", "e3", "e4", "e4", "e4", "e1"], "object": ["p1", "p1", "p1", "p1", "p2", "t1", "p1"]}
    ).join(objects, on="object")
    return LogFrames(
        e2o=e2o,
        events=events,
        objects=objects,
        handling_units=pl.Series("hu", handling_units),
        processing=pl.Series("event", [], dtype=pl.String),
    )


def test_ties_follow_as4_and_duplicate_links_count_once():
    traces = selected_traces(_synthetic_frames(["p1", "p2"]), ["pallet"])
    assert traces.filter(pl.col("object") == "p1")["activity"].to_list() == ["pick", "move", "pack", "ship"]


def test_unselected_types_are_circles_on_the_nodes():
    graph = directly_follows_graph(_synthetic_frames(["p1", "p2"]), full("pallet"))
    assert [t.object_type for t in graph.object_types if t.selected] == ["pallet"]
    ship = next(a for a in graph.activities if a.activity == "ship")
    assert [(t.object_type, t.events, t.objects) for t in ship.object_types] == [("pallet", 1, 2), ("truck", 1, 1)]


def test_handling_unit_table_restricts_the_type():
    # Only p1 is a handling unit: p2 (same type) is left out, the truck type is used in full.
    frames = _synthetic_frames(["p1"])
    graph = directly_follows_graph(frames, full("pallet", "truck"))
    pallet = next(t for t in graph.object_types if t.object_type == "pallet")
    assert (pallet.objects, pallet.kept_objects) == (1, 1)
    assert arcs_of(graph, "truck") == {(None, "ship"): (1, 1), ("ship", None): (1, 1)}


def test_request_resolves_general_and_own_thresholds(frames):
    request = DfgRequest(
        path_threshold=50,
        type_thresholds=[TypeThresholds(object_type="slab", arc_threshold=100), TypeThresholds(object_type="truck", path_threshold=1)],
    )
    settings = resolve_selection(request, frames.objects, frames.handling_units.to_list())
    assert [(s.object_type, s.path_threshold, s.arc_threshold) for s in settings] == [
        ("coil", 50, 10),
        ("slab", 50, 100),
    ]


def test_transformation_first_at_first_and_last_at_last_timestamp():
    """DFG boundary tie-break (Nina, 2026-11-14): at an object's first timestamp a transformation event comes
    first, at its last timestamp last, ahead of / after movements (which AS4 would put first)."""
    t1, t2 = datetime(2026, 1, 1, 1), datetime(2026, 1, 1, 2)
    events = pl.DataFrame(
        {
            "event": ["a", "b", "c", "d"],
            "time": [t1, t1, t2, t2],
            "activity": ["create", "move in", "move out", "consume"],
            "is_movement": [False, True, True, False],
            "is_transformation": [True, False, False, True],
            "is_processing": [False, False, False, False],
        }
    )
    objects = pl.DataFrame({"object": ["p1"], "object_type": ["pallet"]})
    e2o = pl.DataFrame({"event": ["a", "b", "c", "d"], "object": ["p1"] * 4}).join(objects, on="object")
    frames = LogFrames(
        e2o=e2o,
        events=events,
        objects=objects,
        handling_units=pl.Series("hu", ["p1"]),
        processing=pl.Series("event", [], dtype=pl.String),
    )
    traces = selected_traces(frames, ["pallet"])
    assert traces["activity"].to_list() == ["create", "move in", "move out", "consume"]


def _pallet_example() -> LogFrames:
    """The worked example of the module note "Directly-Follows Graph Page": ten pallets, a truck and an operator."""
    paths = {
        **{f"p{i}": ["produce", "pick", "pack", "load", "ship"] for i in range(1, 6)},
        **{f"p{i}": ["produce", "pick", "inspect", "pack", "load", "ship"] for i in range(6, 9)},
        "p9": ["produce", "inspect", "inspect", "scrap"],
        "p10": ["produce", "pick", "pack", "inspect", "pack", "load", "ship"],
    }
    rows, links, n = [], [], 0
    for i, (pallet, activities) in enumerate(paths.items()):
        for k, activity in enumerate(activities):
            n += 1
            hour = 10 * i + (0 if k < 2 else 1) if pallet == "p9" else 10 * i + k
            # p9: produce and inspect share the first timestamp, inspect and scrap the last; ids against the rule.
            event = ["e902", "e901", "e904", "e903"][k] if pallet == "p9" else f"e{n:03d}"
            rows.append((event, datetime(2026, 1, 1) + timedelta(hours=hour), activity, activity in ("load", "ship"), activity in ("produce", "scrap")))
            links.append((event, pallet))
            if activity in ("load", "ship"):
                links.append((event, "t1"))
            if activity == "inspect":
                links.append((event, "o1"))
    events = pl.DataFrame(rows, schema=["event", "time", "activity", "is_movement", "is_transformation"], orient="row")
    objects = pl.DataFrame({"object": [*paths, "t1", "o1"], "object_type": ["pallet"] * 10 + ["truck", "operator"]})
    return LogFrames(
        e2o=pl.DataFrame(links, schema=["event", "object"], orient="row").join(objects, on="object"),
        events=events.with_columns(is_processing=pl.lit(False)),
        objects=objects,
        handling_units=pl.Series("hu", list(paths)),
        processing=pl.Series("event", [], dtype=pl.String),
    )


def test_worked_example_of_the_module_note():
    frames = _pallet_example()
    p9 = selected_traces(frames, ["pallet"]).filter(pl.col("object") == "p9")
    assert p9["activity"].to_list() == ["produce", "inspect", "inspect", "scrap"]
    setting = [TypeSetting(object_type="pallet", path_threshold=60, arc_threshold=70)]
    graph = directly_follows_graph(frames, setting)
    pallet = next(t for t in graph.object_types if t.object_type == "pallet")
    assert (pallet.kept_paths, pallet.kept_objects) == (2, 8)
    assert set(arcs_of(graph, "pallet")) == {
        (None, "produce"), ("produce", "pick"), ("pack", "load"), ("load", "ship"), ("ship", None), ("pick", "pack"), ("inspect", "pack"),
    }
    assert {a.activity: a.events for a in graph.activities}["inspect"] == 3
    assert not next(o for o in graph.activity_options if o.activity == "scrap").on_included_trace
    without = directly_follows_graph(frames, setting, excluded_activities=["inspect"])
    assert arcs_of(without, "pallet")[("pick", "pack")] == (5, 5)
    truck = directly_follows_graph(frames, [*setting, TypeSetting(object_type="truck", path_threshold=100, arc_threshold=100)])
    assert {a.activity: a.events for a in truck.activities}["load"] == 9
    default = directly_follows_graph(frames)
    assert set(arcs_of(default, "pallet")) == {(None, "produce"), ("load", "ship"), ("ship", None)}
