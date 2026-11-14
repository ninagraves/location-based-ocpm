"""Directly-follows graph (docs/pages/directly-follows-graph.md): traces, path filter, arc filter, nodes."""

from datetime import datetime

import polars as pl
import pytest

from ocelescope_module_location_based_ocpm.dfg.graph import (
    LogFrames,
    TypeSetting,
    directly_follows_graph,
    log_frames,
    selected_traces,
)


@pytest.fixture(scope="module")
def frames(ocel, derivation) -> LogFrames:
    """The running example's frames."""
    return log_frames(ocel, derivation)


def arcs_of(graph, object_type):
    """The arcs of one object type as {(source, target): (count, objects)}."""
    return {(a.source, a.target): (a.count, a.objects) for a in graph.arcs if a.object_type == object_type}


def test_default_selects_the_handling_unit_types(frames):
    graph = directly_follows_graph(frames)
    assert [(t.object_type, t.selected, t.objects) for t in graph.object_types] == [
        ("coil", True, 5),
        ("slab", True, 1),
    ]


def test_running_example_arcs(frames):
    graph = directly_follows_graph(frames)
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
    graph = directly_follows_graph(frames)
    events = {a.activity: a.events for a in graph.activities}
    assert events == {
        "cast slab": 1, "crane move": 4, "cut": 1, "inspect slab": 1, "label": 1,
        "load truck": 2, "quality check": 4, "roll": 1, "unload truck": 2,
    }
    roll = next(a for a in graph.activities if a.activity == "roll")
    assert [(t.object_type, t.events, t.objects) for t in roll.object_types] == [("coil", 1, 2), ("slab", 1, 1)]


def test_unselected_type_is_only_involved(frames):
    graph = directly_follows_graph(frames, [TypeSetting(object_type="coil")])
    assert arcs_of(graph, "slab") == {}
    assert "cast slab" not in {a.activity for a in graph.activities}
    roll = next(a for a in graph.activities if a.activity == "roll")
    assert {t.object_type for t in roll.object_types} == {"coil", "slab"}


def test_path_threshold_keeps_most_frequent_paths(frames):
    # All five coils have different paths; 50 % of 5 coils keeps paths until 2.5 coils are covered: 3 paths.
    graph = directly_follows_graph(frames, [TypeSetting(object_type="coil", path_threshold=50)])
    coil = next(t for t in graph.object_types if t.object_type == "coil")
    assert (coil.paths, coil.kept_paths, coil.kept_objects) == (5, 3, 3)
    none = directly_follows_graph(frames, [TypeSetting(object_type="coil", path_threshold=0)])
    assert none.arcs == [] and none.activities == []


def test_arc_threshold_is_a_share_of_the_objects(frames):
    graph = directly_follows_graph(frames, [TypeSetting(object_type="coil", arc_threshold=50)])
    # At least 2.5 of 5 coils: the arcs with 3 or 4 coils.
    assert arcs_of(graph, "coil") == {
        ("quality check", None): (4, 4),
        ("load truck", "unload truck"): (3, 3),
        ("unload truck", "crane move"): (3, 3),
    }
    exact = directly_follows_graph(frames, [TypeSetting(object_type="coil", arc_threshold=60)])
    assert ("load truck", "unload truck") in arcs_of(exact, "coil")  # 3 of 5 = exactly 60 %


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
    graph = directly_follows_graph(_synthetic_frames(["p1", "p2"]))
    assert [t.object_type for t in graph.object_types if t.selected] == ["pallet"]
    ship = next(a for a in graph.activities if a.activity == "ship")
    assert [(t.object_type, t.events, t.objects) for t in ship.object_types] == [("pallet", 1, 2), ("truck", 1, 1)]


def test_handling_unit_table_restricts_the_type():
    # Only p1 is a handling unit: p2 (same type) is left out, the truck type is used in full.
    frames = _synthetic_frames(["p1"])
    graph = directly_follows_graph(frames, [TypeSetting(object_type="pallet"), TypeSetting(object_type="truck")])
    pallet = next(t for t in graph.object_types if t.object_type == "pallet")
    assert (pallet.objects, pallet.kept_objects) == (1, 1)
    assert arcs_of(graph, "truck") == {(None, "ship"): (1, 1), ("ship", None): (1, 1)}
