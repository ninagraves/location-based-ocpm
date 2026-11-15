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

from test_dfg import _pallet_example, every_activity

DFG_ARCS = Path(__file__).parents[3] / "frontend-modules" / "location-ocpm" / "src" / "lib" / "dfgArcs.ts"
RUNNER = """
const { filterArcs } = await import(process.argv[2]);
const cases = JSON.parse(await new Promise((ok) => { let s = ""; process.stdin.on("data", (d) => (s += d)); process.stdin.on("end", () => ok(s)); }));
const out = cases.map(({ arcs, threshold, count, removed, stay }) =>
  filterArcs(arcs, {
    threshold: (t) => threshold[t] ?? 100,
    count: (t) => count[t] ?? null,
    removed,
    stayConnected: stay,
  }).shown.map((a) => [a.object_type, a.source ?? null, a.target ?? null, a.connecting]),
);
console.log(JSON.stringify(out));
"""

#: (variant threshold, arc threshold, arc count, removed arcs, stay connected) of the pallets in the worked example.
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
    every = every_activity(frames, "pallet")
    inputs, expected = [], []
    for variants, threshold, count, removed, stay in CASES:
        # What the route sends: all arcs of the included traces.
        base = directly_follows_graph(frames, [TypeSetting(object_type="pallet", variant_threshold=variants)], activities=every, stay=False)
        inputs.append(
            {
                "arcs": [a.model_dump() for a in base.arcs],
                "threshold": {"pallet": threshold},
                "count": {"pallet": count} if count is not None else {},
                "removed": [{"object_type": t, "source": s, "target": g} for t, s, g in removed],
                "stay": stay,
            }
        )
        setting = [TypeSetting(object_type="pallet", variant_threshold=variants, arc_threshold=threshold, arc_count=count)]
        graph = directly_follows_graph(frames, setting, activities=every, stay=stay, removed=removed)
        expected.append(sorted([a.object_type, a.source or "", a.target or "", a.connecting] for a in graph.arcs))
    runner = tmp_path / "runner.mjs"
    runner.write_text(RUNNER)
    result = subprocess.run(
        [node, str(runner), DFG_ARCS.as_uri()], input=json.dumps(inputs), capture_output=True, text=True, check=True
    )
    shown = [sorted([t, s or "", g or "", c] for t, s, g, c in case) for case in json.loads(result.stdout)]
    for case, (got, want) in enumerate(zip(shown, expected, strict=True)):
        assert got == want, f"case {CASES[case]}"
