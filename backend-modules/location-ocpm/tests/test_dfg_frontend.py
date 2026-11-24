"""Cross-check (Nina, 2026-11-15): the page applies the arc settings in the browser (`lib/dfgArcs.ts`), the notebooks
and tests in Python (`dfg/arcs.py`, `dfg/connectivity.py`). This test runs the TypeScript functions with Node on the
arcs the route sends and checks that they show exactly the arcs of `directly_follows_graph`.
Skipped if Node (22.6 or later, for TypeScript without a build step) is not installed.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from ocelescope_module_location_based_ocpm.dfg.graph import TypeSetting, directly_follows_graph

from test_dfg import _pallet_example, _pallet_example_with_activities_without_handling_units, every_activity, frames  # noqa: F401

DFG_ARCS = Path(__file__).parents[3] / "frontend-modules" / "location-ocpm" / "src" / "lib" / "dfgArcs.ts"
RUNNER = """
const { filterArcs } = await import(process.argv[2]);
const cases = JSON.parse(await new Promise((ok) => { let s = ""; process.stdin.on("data", (d) => (s += d)); process.stdin.on("end", () => ok(s)); }));
const out = cases.map(({ arcs, threshold, count, total, removed, stay }) =>
  filterArcs(arcs, {
    threshold: (t) => threshold[t] ?? 100,
    count: (t) => count[t] ?? null,
    total,
    removed,
    stayConnected: stay,
  }).shown.map((a) => [a.object_type, a.source ?? null, a.target ?? null, a.connecting]),
);
console.log(JSON.stringify(out));
"""

#: (variant threshold, arc threshold, arc count, removed arcs, stay connected[, total]) of the pallets (and, with
#: total, trucks) in the worked example; total = Arcs (display) in "general" mode.
CASES = [
    (60, 100, None, [], True),
    (60, 70, None, [], True),
    (60, 50, None, [], False),
    (60, 50, None, [], True),
    (60, 100, 3, [], False),
    (60, 100, 3, [], True),
    (60, 70, None, [("pallet", "pick", "pack")], True),
    (60, 70, None, [("pallet", "pick", "pack")], False),
    (100, 30, 4, [("pallet", "produce", "inspect")], True),
    (100, 0, None, [], True),
    (100, 12.5, 2, [], True),
    (100, 100, None, [], False, 5),
    (100, 100, None, [], True, 5),
    (100, 50, None, [("pallet", "pick", "pack")], False, 3),
    (100, 100, 2, [], False, 4),
]


def _node() -> str:
    """The Node executable, or skip the test."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    version = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v")
    if tuple(int(x) for x in version.split(".")[:2]) < (22, 6):
        pytest.skip(f"Node {version} cannot run TypeScript without a build step")
    return node


def test_frontend_arc_settings_match_python(tmp_path):
    node = _node()
    frames = _pallet_example()
    every = every_activity(frames, "pallet", "truck")
    inputs, expected = [], []
    for variants, threshold, count, removed, stay, *rest in CASES:
        total = rest[0] if rest else None
        # With total: pallets and trucks, the pallets with their own count (if any), the trucks pooled.
        types = ["pallet", "truck"] if total is not None else ["pallet"]
        # What the route sends: all arcs of the included traces.
        base = directly_follows_graph(frames, [TypeSetting(object_type=t, variant_threshold=variants, arc_threshold=100) for t in types], activities=every, stay=False)
        inputs.append(
            {
                "arcs": [a.model_dump() for a in base.arcs],
                "threshold": {t: threshold for t in types},
                "count": {"pallet": count} if count is not None else {},
                "total": total,
                "removed": [{"object_type": t, "source": s, "target": g} for t, s, g in removed],
                "stay": stay,
            }
        )
        setting = [
            TypeSetting(object_type=t, variant_threshold=variants, arc_threshold=threshold, arc_count=count if t == "pallet" else None)
            for t in types
        ]
        graph = directly_follows_graph(frames, setting, activities=every, stay=stay, removed=removed, arc_total=total)
        expected.append(sorted([a.object_type, a.source or "", a.target or "", a.connecting] for a in graph.arcs))
    runner = tmp_path / "runner.mjs"
    runner.write_text(RUNNER)
    result = subprocess.run(
        [node, str(runner), DFG_ARCS.as_uri()], input=json.dumps(inputs), capture_output=True, text=True, check=True
    )
    shown = [sorted([t, s or "", g or "", c] for t, s, g, c in case) for case in json.loads(result.stdout)]
    for case, (got, want) in enumerate(zip(shown, expected, strict=True)):
        assert got == want, f"case {CASES[case]}"


NEEDED_RUNNER = """
const { neededArcThresholds } = await import(process.argv[2]);
const arcs = JSON.parse(await new Promise((ok) => { let s = ""; process.stdin.on("data", (d) => (s += d)); process.stdin.on("end", () => ok(s)); }));
const out = {};
for (const [t, m] of neededArcThresholds(arcs, Number(process.argv[3] ?? 0))) out[t] = Object.fromEntries(m);
console.log(JSON.stringify(out));
"""


def test_needed_projection_thresholds_match_python(tmp_path):
    """`neededArcThresholds` gives, per activity, the smallest whole Arcs (projection) value at which Python's
    `arc_share_filter` keeps an arc touching it (checked by trying every value from 1 to 100)."""
    node = _node()
    frames = _pallet_example()
    every = every_activity(frames, "pallet")
    base = directly_follows_graph(frames, [TypeSetting(object_type="pallet", variant_threshold=100, arc_threshold=100)], activities=every, stay=False)
    runner = tmp_path / "needed.mjs"
    runner.write_text(NEEDED_RUNNER)
    result = subprocess.run(
        [node, str(runner), DFG_ARCS.as_uri()], input=json.dumps([a.model_dump() for a in base.arcs]), capture_output=True, text=True, check=True
    )
    needed = json.loads(result.stdout)["pallet"]
    expected = {}
    for alpha in range(100, 0, -1):
        setting = [TypeSetting(object_type="pallet", variant_threshold=100, arc_threshold=alpha)]
        graph = directly_follows_graph(frames, setting, activities=every, stay=False)
        for a in graph.arcs:
            for activity in (a.source, a.target):
                if activity is not None:
                    expected[activity] = alpha
    assert needed == expected


def test_exact_projection_thresholds_match_python(tmp_path):
    """With 3 decimals, `neededArcThresholds` gives the value at which Python's `arc_share_filter` keeps an arc of the
    activity, and 0.001 less does not (Nina, 2026-11-18: shown in the unfold)."""
    node = _node()
    frames = _pallet_example()
    every = every_activity(frames, "pallet")
    base = directly_follows_graph(frames, [TypeSetting(object_type="pallet", variant_threshold=100, arc_threshold=100)], activities=every, stay=False)
    runner = tmp_path / "needed.mjs"
    runner.write_text(NEEDED_RUNNER)
    result = subprocess.run(
        [node, str(runner), DFG_ARCS.as_uri(), "3"], input=json.dumps([a.model_dump() for a in base.arcs]), capture_output=True, text=True, check=True
    )
    needed = json.loads(result.stdout)["pallet"]

    def drawn(alpha: float) -> set[str]:
        setting = [TypeSetting(object_type="pallet", variant_threshold=100, arc_threshold=alpha)]
        arcs = directly_follows_graph(frames, setting, activities=every, stay=False).arcs
        return {x for a in arcs for x in (a.source, a.target) if x is not None}

    assert any(round(v) != v for v in needed.values())
    for activity, value in needed.items():
        assert activity in drawn(value)
        if value > 0.001:
            assert activity not in drawn(round(value - 0.001, 3))


DFG_SEARCH = Path(__file__).parents[3] / "frontend-modules" / "location-ocpm" / "src" / "lib" / "dfgActivitySearch.ts"
SEARCH_RUNNER = """
const { activitiesOfType, matchingObjectTypes } = await import(process.argv[2]);
const { options, types } = JSON.parse(await new Promise((ok) => { let s = ""; process.stdin.on("data", (d) => (s += d)); process.stdin.on("end", () => ok(s)); }));
const out = {
  byType: Object.fromEntries(types.map((t) => [t, activitiesOfType(options, t).map((o) => o.activity)])),
  hits: Object.fromEntries(["o", "op", "TRU", "TRUC", " pall ", "truck", "x"].map((q) => [q, matchingObjectTypes(types, q)])),
  short: ["bo", "box", "BOX ", "boxe"].map((q) => matchingObjectTypes(["boxes", "box"], q)),
};
console.log(JSON.stringify(out));
"""


def _run_search(tmp_path, graph) -> dict:
    """Runs `activitiesOfType` and `matchingObjectTypes` of `lib/dfgActivitySearch.ts` on the route's activity list."""
    node = _node()
    runner = tmp_path / "search.mjs"
    runner.write_text(SEARCH_RUNNER)
    payload = {"options": [o.model_dump() for o in graph.activity_options], "types": [t.object_type for t in graph.object_types]}
    result = subprocess.run([node, str(runner), DFG_SEARCH.as_uri()], input=json.dumps(payload), capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_object_type_search_lists_the_activities_of_the_type_by_its_events(tmp_path, frames):
    """Object type search (Nina, 2026-11-24): every activity the type is involved in, most events of the type first
    (ties: events with a handling unit, events in the log, name). Running example, as in the module note."""
    graph = directly_follows_graph(frames)
    by_type = _run_search(tmp_path, graph)["byType"]
    assert by_type["coil"] == ["crane move", "quality check", "load truck", "unload truck", "cut", "label", "roll"]
    assert by_type["slab"] == ["cast slab", "inspect slab", "roll"]


def test_object_type_search_matches_python_ordering(tmp_path):
    """The same on the pallets with trucks and operators (activities without handling units): the order agrees with a
    Python sort of the route's counts. Type names are matched case-insensitively by a part from 4 letters on, below
    only by their full name (Nina, 2026-11-24)."""
    frames = _pallet_example_with_activities_without_handling_units()
    graph = directly_follows_graph(frames)
    out = _run_search(tmp_path, graph)
    types = [t.object_type for t in graph.object_types]
    for t in types:
        events = {o.activity: next((x.events for x in o.object_types if x.object_type == t), 0) for o in graph.activity_options}
        expected = sorted(
            (o for o in graph.activity_options if events[o.activity] > 0),
            key=lambda o: (-events[o.activity], -o.hu_events, -o.log_events, o.activity),
        )
        assert out["byType"][t] == [o.activity for o in expected]
    assert out["byType"]["operator"]
    assert out["hits"]["o"] == []
    assert out["hits"]["op"] == []
    assert out["hits"]["TRU"] == []
    assert out["hits"]["TRUC"] == ["truck"]
    assert out["hits"][" pall "] == ["pallet"]
    assert out["hits"]["truck"] == ["truck"]
    assert out["hits"]["x"] == []
    assert out["short"] == [[], ["box"], ["box"], ["boxes"]]


CHIP_RUNNER = """
const { activitiesOf, chipCount, matchingCategories } = await import(process.argv[2]);
const { options, categories, cases, queries } = JSON.parse(await new Promise((ok) => { let s = ""; process.stdin.on("data", (d) => (s += d)); process.stdin.on("end", () => ok(s)); }));
const out = {
  lists: cases.map(([types, cats]) => activitiesOf(options, types, cats).map((o) => [o.activity, chipCount(o, types, cats)])),
  hits: Object.fromEntries(queries.map((q) => [q, matchingCategories(categories, q).map((c) => c.key)])),
};
console.log(JSON.stringify(out));
"""

#: Picked chips (types, categories) of the running example (Nina, 2026-11-24: chips stack).
CHIP_CASES = [
    (["coil"], ["processing"]),
    ([], ["processing"]),
    ([], ["to_vehicle", "other_movement"]),
    (["coil", "slab"], []),
    (["slab"], ["transformation"]),
    (["coil"], ["to_storage", "processing"]),
]


def _chip_count(option, types, categories) -> int:
    """Python version of `chipCount` (the smallest of the pair counts) for the expectations."""
    entries = {t.object_type: t for t in option.object_types}
    if not types:
        counts = [option.categories.get(c, 0) for c in categories]
    elif not categories:
        counts = [entries[t].events if t in entries else 0 for t in types]
    else:
        counts = [entries[t].categories.get(c, 0) if t in entries else 0 for t in types for c in categories]
    return min(counts)


def test_stacked_chips_list_the_activities_matching_all_of_them(tmp_path, frames):
    """Category chips (from 4 letters of a category word) and stacked chips: only activities matching all picked chips,
    ordered by the smallest pair count, ties by events with a handling unit, events in the log, name."""
    node = _node()
    graph = directly_follows_graph(frames)
    runner = tmp_path / "chips.mjs"
    runner.write_text(CHIP_RUNNER)
    payload = {
        "options": [o.model_dump() for o in graph.activity_options],
        "categories": [c.model_dump() for c in graph.event_categories],
        "cases": CHIP_CASES,
        "queries": ["vehic", "move", "Movements", "proc", "pro", "transforming", "stor", "other"],
    }
    result = subprocess.run([node, str(runner), DFG_SEARCH.as_uri()], input=json.dumps(payload), capture_output=True, text=True, check=True)
    out = json.loads(result.stdout)
    for (types, categories), got in zip(CHIP_CASES, out["lists"], strict=True):
        counted = [(o, _chip_count(o, types, categories)) for o in graph.activity_options]
        expected = sorted(((o, n) for o, n in counted if n > 0), key=lambda p: (-p[1], -p[0].hu_events, -p[0].log_events, p[0].activity))
        assert got == [[o.activity, n] for o, n in expected], (types, categories)
    assert out["lists"][0] == [["cut", 1], ["roll", 1]]  # coil + Processing
    assert out["lists"][1] == [["cast slab", 1], ["cut", 1], ["roll", 1]]  # Processing
    assert out["lists"][2] == []  # no activity moves to a vehicle and elsewhere
    assert out["lists"][3] == [["roll", 1]]  # coil + slab
    assert out["lists"][3] == [["roll", 1]]
    assert out["hits"] == {
        "vehic": ["to_vehicle"],
        "move": ["to_vehicle", "to_storage", "other_movement"],
        "Movements": ["to_vehicle", "to_storage", "other_movement"],
        "proc": ["processing"],
        "pro": [],
        "transforming": ["transformation"],
        "stor": ["to_storage"],
        "other": ["other_movement"],
    }

