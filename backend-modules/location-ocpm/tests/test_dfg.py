"""Directly-follows graph (docs/pages/directly-follows-graph.md): traces, projection, variants, arcs, nodes."""

from datetime import datetime, timedelta

import polars as pl
import pytest

from ocelescope_module_location_based_ocpm.dfg.projection import default_activity_count
from ocelescope_module_location_based_ocpm.dfg.variants import object_variants, variant_ranking
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


ALL = {"variant_threshold": 100, "arc_threshold": 100}


def full(*types):
    """Selection of the given types with all variants and all arcs."""
    return [TypeSetting(object_type=t, **ALL) for t in types]


def every_activity(frames, *types):
    """Activity selection that keeps every activity of the log for the given types (no projection)."""
    activities = frames.events["activity"].unique().to_list()
    return {t: activities for t in types}


def test_default_selects_the_handling_unit_types(frames):
    graph = directly_follows_graph(frames)
    assert [(t.object_type, t.selected, t.objects) for t in graph.object_types] == [
        ("coil", True, 5),
        ("slab", True, 1),
    ]


def test_default_thresholds(frames):
    graph = directly_follows_graph(frames)
    coil = next(t for t in graph.object_types if t.object_type == "coil")
    # Default variant threshold: the 5 coils have a variant each, the first two cover 40 %, so 41 % keeps the top 3;
    # the slab (1 variant) needs 1 %: 41 % for both. Arcs: 100 %, no arc count.
    assert graph.variant_default == 41.0
    assert (coil.variant_threshold, coil.arc_threshold, coil.arc_count, coil.kept_variants, coil.kept_objects) == (41.0, 100, None, 3, 3)
    slab = next(t for t in graph.object_types if t.object_type == "slab")
    assert (slab.variant_threshold, slab.kept_variants) == (41.0, 1)


def test_equally_frequent_paths_are_ranked_by_first_occurrence(frames):
    # All coils have their own path: ranked by the first event of the coil (c1 and c2 both start at 3:00, then
    # alphabetically by the path: "roll, label, crane move, load truck" < "roll, label, crane move, quality check").
    ranking = variant_ranking(object_variants(selected_traces(frames, ["coil"])))
    first = {v: o for o, v in object_variants(selected_traces(frames, ["coil"])).select("object", "variant").iter_rows()}
    assert [first[v] for v in ranking["variant"]] == ["c2", "c1", "c3", "c4", "c5"]


def test_running_example_arcs(frames):
    graph = directly_follows_graph(frames, full("coil", "slab"), activities=every_activity(frames, "coil", "slab"))
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
    graph = directly_follows_graph(frames, full("coil", "slab"), activities=every_activity(frames, "coil", "slab"))
    events = {a.activity: a.events for a in graph.activities}
    assert events == {
        "cast slab": 1, "crane move": 4, "cut": 1, "inspect slab": 1, "label": 1,
        "load truck": 2, "quality check": 4, "roll": 1, "unload truck": 2,
    }
    roll = next(a for a in graph.activities if a.activity == "roll")
    assert [(t.object_type, t.events, t.objects) for t in roll.object_types] == [("coil", 1, 2), ("slab", 1, 1)]


def test_unselected_type_is_only_involved(frames):
    graph = directly_follows_graph(frames, full("coil"), activities=every_activity(frames, "coil"))
    assert arcs_of(graph, "slab") == {}
    assert "cast slab" not in {a.activity for a in graph.activities}
    roll = next(a for a in graph.activities if a.activity == "roll")
    assert {t.object_type for t in roll.object_types} == {"coil", "slab"}


def test_variant_threshold_keeps_most_frequent_variants(frames):
    # All five coils have different variants; 50 % of 5 coils keeps variants until 2.5 coils are covered: 3.
    graph = directly_follows_graph(frames, [TypeSetting(object_type="coil", variant_threshold=50, arc_threshold=100)])
    coil = next(t for t in graph.object_types if t.object_type == "coil")
    assert (coil.variants, coil.kept_variants, coil.kept_objects) == (5, 3, 3)
    none = directly_follows_graph(frames, [TypeSetting(object_type="coil", variant_threshold=0, arc_threshold=100)])
    assert none.arcs == [] and none.activities == []


def test_arc_threshold_ranks_all_arcs_by_objects_and_keeps_ties(frames):
    # coil has 18 arcs (start and end arcs included); 20 % of 18 = 3.6 -> 4, and the fourth, (2, 2), is tied with
    # four more: 8 arcs (as Ocelescope's DFG filter).
    every = every_activity(frames, "coil")
    setting = [TypeSetting(object_type="coil", variant_threshold=100, arc_threshold=20)]
    coil = arcs_of(directly_follows_graph(frames, setting, activities=every, stay=False), "coil")
    assert coil == {
        ("quality check", None): (4, 4),
        ("load truck", "unload truck"): (3, 3),
        ("unload truck", "crane move"): (3, 3),
        (None, "roll"): (2, 2),
        ("roll", "label"): (2, 2),
        ("label", "crane move"): (2, 2),
        ("crane move", "quality check"): (2, 2),
        ("crane move", "load truck"): (2, 2),
    }
    none = directly_follows_graph(frames, [TypeSetting(object_type="coil", variant_threshold=100, arc_threshold=0)], activities=every)
    assert arcs_of(none, "coil") == {}


def test_arc_count_keeps_exactly_n_arcs_per_type_by_the_tie_break(frames):
    every = every_activity(frames, "coil", "slab")
    selection = [TypeSetting(object_type=t, variant_threshold=100, arc_count=2) for t in ("coil", "slab")]
    graph = directly_follows_graph(frames, selection, activities=every, stay=False)
    assert set(arcs_of(graph, "coil")) == {("quality check", None), ("load truck", "unload truck")}
    # The slab's arcs are all (1, 1): first occurrence decides (start arc, then cast slab -> inspect slab).
    assert set(arcs_of(graph, "slab")) == {(None, "cast slab"), ("cast slab", "inspect slab")}
    assert graph.arc_count_max == 18


def test_stay_connected_adds_back_the_arcs_needed_for_start_to_end_paths(frames):
    every = every_activity(frames, "slab")
    selection = [TypeSetting(object_type="slab", variant_threshold=100, arc_count=1)]
    graph = directly_follows_graph(frames, selection, activities=every)
    assert [(a.source, a.target, a.connecting) for a in graph.arcs] == [
        (None, "cast slab", False),
        ("cast slab", "inspect slab", True),
        ("inspect slab", "roll", True),
        ("roll", None, True),
    ]
    assert [(a.source, a.target) for a in directly_follows_graph(frames, selection, activities=every, stay=False).arcs] == [(None, "cast slab")]


def test_arcs_removed_by_hand_stay_removed(frames):
    # Removing inspect slab -> roll cuts the slab's only path: with "Stay connected" no arc is left (no arc lies on a
    # start-to-end path), without it the other three arcs stay.
    every = every_activity(frames, "slab")
    selection = full("slab")
    removed = [("slab", "inspect slab", "roll")]
    assert directly_follows_graph(frames, selection, activities=every, removed=removed).arcs == []
    graph = directly_follows_graph(frames, selection, activities=every, stay=False, removed=removed)
    assert len(graph.arcs) == 3
    assert [(a.source, a.target, a.count) for a in graph.removed_arcs] == [("inspect slab", "roll", 1)]


def test_deselected_activity_is_projected_out_first(frames):
    # Projection (Nina, 2026-11-15): without label, the coils' traces roll, label, crane move become roll, crane move.
    activities = every_activity(frames, "coil", "slab")
    activities["coil"] = [a for a in activities["coil"] if a != "label"]
    graph = directly_follows_graph(frames, full("coil", "slab"), activities=activities)
    coil = arcs_of(graph, "coil")
    assert ("roll", "label") not in coil and ("label", "crane move") not in coil
    assert coil[("roll", "crane move")] == (2, 2)
    assert "label" not in {a.activity for a in graph.activities}
    options = {o.activity: o for o in graph.activity_options}
    assert [(t.object_type, t.events, t.included) for t in options["label"].object_types] == [("coil", 1, False)]


def test_default_activities_are_the_most_frequent_40_percent_between_3_and_10(frames):
    assert [default_activity_count(n) for n in (2, 4, 7, 12, 30)] == [2, 3, 3, 5, 10]
    # coil has 7 activities -> 3: crane move 4, quality check 4, load truck 2 (before unload truck 2 by first occurrence).
    graph = directly_follows_graph(frames)
    options = {o.activity: o for o in graph.activity_options}
    coil = {a for a, o in options.items() for t in o.object_types if t.object_type == "coil" and t.included}
    assert coil == {"crane move", "quality check", "load truck"}
    # The list is ordered by events with handling units.
    assert [o.activity for o in graph.activity_options][:2] == ["crane move", "quality check"]
    assert options["crane move"].hu_events == 4


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
    frames = _synthetic_frames(["p1", "p2"])
    graph = directly_follows_graph(frames, full("pallet"), activities=every_activity(frames, "pallet"))
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
        variant_threshold=50,
        arc_count=4,
        type_thresholds=[TypeThresholds(object_type="slab", arc_threshold=30, arc_count=2), TypeThresholds(object_type="truck", variant_threshold=1)],
    )
    settings = resolve_selection(request, frames.objects, frames.handling_units.to_list())
    assert [(s.object_type, s.variant_threshold, s.arc_threshold, s.arc_count) for s in settings] == [
        ("coil", 50, 100, 4),
        ("slab", 50, 30, 2),
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
    every = every_activity(frames, "pallet", "truck")

    def pallet(**settings):
        return [TypeSetting(object_type="pallet", variant_threshold=60, **settings)]

    # Variants 60 %: 2 of 4 variants, p1-p8.
    graph = directly_follows_graph(frames, pallet(), activities=every)
    t = next(t for t in graph.object_types if t.object_type == "pallet")
    assert (t.kept_variants, t.kept_objects, t.arcs) == (2, 8, 8)
    assert graph.variant_default == 81.0
    # Arcs 70 %: ceil(5.6) = 6 arcs; PI -> IN and IN -> PA are dropped, so IN disappears.
    graph = directly_follows_graph(frames, pallet(arc_threshold=70), activities=every)
    assert ("pick", "pack") in arcs_of(graph, "pallet") and "inspect" not in {a.activity for a in graph.activities}
    assert len(graph.arcs) == 6
    # Arcs 50 %: the five arcs with 8 pallets (tied); Stay connected adds PI -> PA back.
    loose = directly_follows_graph(frames, pallet(arc_threshold=50), activities=every, stay=False)
    assert ("pick", "pack") not in arcs_of(loose, "pallet") and len(loose.arcs) == 5
    graph = directly_follows_graph(frames, pallet(arc_threshold=50), activities=every)
    assert [(a.source, a.target) for a in graph.arcs if a.connecting] == [("pick", "pack")]
    # Arc count 3: start -> PR, PR -> PI, PA -> LO (first occurrence); Stay connected adds PI -> PA, LO -> SH, SH -> end.
    graph = directly_follows_graph(frames, pallet(arc_count=3), activities=every, stay=False)
    assert set(arcs_of(graph, "pallet")) == {(None, "produce"), ("produce", "pick"), ("pack", "load")}
    graph = directly_follows_graph(frames, pallet(arc_count=3), activities=every)
    assert {(a.source, a.target) for a in graph.arcs if a.connecting} == {("pick", "pack"), ("load", "ship"), ("ship", None)}
    # Arcs 70 % and PI -> PA removed by hand: Stay connected adds PI -> IN and IN -> PA back instead.
    removed = [("pallet", "pick", "pack")]
    graph = directly_follows_graph(frames, pallet(arc_threshold=70), activities=every, removed=removed)
    assert {(a.source, a.target) for a in graph.arcs if a.connecting} == {("pick", "inspect"), ("inspect", "pack")}
    assert ("pick", "pack") not in arcs_of(graph, "pallet")
    # IN deselected: projected out before the variants, so p6-p8 have the variant of p1-p5 (8 pallets).
    no_inspect = {"pallet": [a for a in every["pallet"] if a != "inspect"]}
    graph = directly_follows_graph(frames, pallet(), activities=no_inspect)
    t = next(t for t in graph.object_types if t.object_type == "pallet")
    assert (t.variants, t.kept_variants, t.kept_objects) == (3, 1, 8)
    assert arcs_of(graph, "pallet")[("pick", "pack")] == (8, 8)
    # truck selected as well: LO and SH count p10's events with t1 too.
    truck = directly_follows_graph(frames, [*pallet(), TypeSetting(object_type="truck", variant_threshold=100)], activities=every)
    assert {a.activity: a.events for a in truck.activities}["load"] == 9
    # Defaults: activities PR, PA, PI (40 % of 7 -> 3); variants 91 % (3 variants after the projection); arcs 100 %.
    default = directly_follows_graph(frames)
    t = next(t for t in default.object_types if t.object_type == "pallet")
    assert default.variant_default == 91.0
    assert (t.variants, t.kept_variants, t.kept_objects, t.shown_arcs) == (3, 3, 10, 6)


def test_thresholds_with_decimals(frames):
    # 33.3 % of 5 coils = 1.665 coils: two variants.
    graph = directly_follows_graph(frames, [TypeSetting(object_type="coil", variant_threshold=33.3)], activities=every_activity(frames, "coil"))
    assert next(t for t in graph.object_types if t.object_type == "coil").kept_variants == 2
    # 18 arcs: 5.5 % -> ceil(0.99) = 1 arc; 5.6 % -> ceil(1.008) = 2, and the second, (3, 3), is tied with a third.
    every = every_activity(frames, "coil")
    counts = [
        len(directly_follows_graph(frames, [TypeSetting(object_type="coil", variant_threshold=100, arc_threshold=x)], activities=every, stay=False).arcs)
        for x in (5.5, 5.6)
    ]
    assert counts == [1, 3]
