"""Tests of the instance lineage (relations, lineage R(hu, dir, gen), graphs) on the running example and a
small example with a merge, a diamond and siblings."""

import math
from pathlib import Path

import polars as pl
import pytest
from ocelescope_module_location_based_ocpm.lineage.graph import (
    EVENT,
    SIBLING,
    lineage_graph,
    to_dot,
)
from ocelescope_module_location_based_ocpm.lineage.lineage import lineage
from ocelescope_module_location_based_ocpm.lineage.relations import (
    children,
    consumption_events,
    creation_events,
    lineage_relations,
    parents,
    siblings,
)

ROLES = Path(__file__).parents[3] / "data" / "running_example" / "inputs" / "transformation_roles.csv"


@pytest.fixture
def roles() -> pl.DataFrame:
    """Transformation roles of the running example."""
    return pl.read_csv(ROLES)


@pytest.fixture
def relations(roles) -> pl.DataFrame:
    """Lineage relations R of the running example."""
    return lineage_relations(roles)


def _rows(frame: pl.DataFrame, *cols) -> set[tuple]:
    """The rows of `frame` (restricted to `cols`) as a set of tuples."""
    return set(frame.select(cols).iter_rows()) if cols else set(frame.iter_rows())


def test_relations(relations):
    """R = {(s1, c1, e3), (s1, c2, e3), (c2, c4, e15)}; e1 produces s1 from nothing and gives no relation."""
    assert _rows(relations) == {("s1", "c1", "e3"), ("s1", "c2", "e3"), ("c2", "c4", "e15")}


def test_functions(roles, relations):
    """Examples of the Transformations note (section Instance Lineage)."""
    assert _rows(parents(relations)) == {("c1", "s1"), ("c2", "s1"), ("c4", "c2")}
    assert _rows(children(relations)) == {("s1", "c1"), ("s1", "c2"), ("c2", "c4")}
    assert _rows(creation_events(roles)) == {("s1", "e1"), ("c1", "e3"), ("c2", "e3"), ("c4", "e15")}
    assert _rows(consumption_events(roles)) == {("s1", "e3"), ("c2", "e15")}
    assert _rows(siblings(roles)) == {("c1", "c2", "e3"), ("c2", "c1", "e3")}


@pytest.mark.parametrize(
    "hu, direction, gen, expected",
    [
        ("c2", "components", 1, {("s1", "c2", "e3")}),
        ("c2", "products", 1, {("c2", "c4", "e15")}),
        ("c2", "both", 1, {("s1", "c2", "e3"), ("c2", "c4", "e15")}),
        ("s1", "products", 1, {("s1", "c1", "e3"), ("s1", "c2", "e3")}),
        ("s1", "products", math.inf, {("s1", "c1", "e3"), ("s1", "c2", "e3"), ("c2", "c4", "e15")}),
        ("c4", "components", math.inf, {("c2", "c4", "e15"), ("s1", "c2", "e3")}),
        ("c1", "both", math.inf, {("s1", "c1", "e3")}),
        ("c2", "both", 0, set()),
        ("c3", "both", math.inf, set()),
    ],
)
def test_lineage(relations, hu, direction, gen, expected):
    """The lineage examples of the Transformations note."""
    assert _rows(lineage(relations, hu, direction, gen), "parent", "child", "event") == expected


def test_generations(relations):
    """Generations count per direction from 1."""
    out = lineage(relations, "c4", "components")
    assert _rows(out, "parent", "generation") == {("c2", 1), ("s1", 2)}


def test_diamond_keeps_first_generation():
    """A relation reached twice (diamond) appears once, with its smallest generation.

    x is reached from a via c (generation 2) and via b, d (generation 3), so (x, y) is reached in generations
    3 and 4 and kept as generation 3.
    """
    roles = pl.DataFrame(
        {
            "event": ["t1", "t1", "t1", "t2", "t2", "t3", "t3", "t3", "t4", "t4"],
            "hu": ["a", "b", "c", "b", "d", "c", "d", "x", "x", "y"],
            "role": ["consumed", "produced", "produced", "consumed", "produced", "consumed", "consumed", "produced",
                     "consumed", "produced"],
        }
    )
    out = lineage(lineage_relations(roles), "a", "products")
    assert out.height == 6
    assert _rows(out, "parent", "child", "generation") == {
        ("a", "b", 1), ("a", "c", 1), ("b", "d", 2), ("c", "x", 2), ("d", "x", 3), ("x", "y", 3)
    }


def test_invalid_direction(relations):
    """Unknown directions are rejected."""
    with pytest.raises(ValueError):
        lineage(relations, "c2", "up")


@pytest.mark.parametrize(
    "with_events, with_siblings, nodes, edges",
    [
        (False, False, {"s1", "c2", "c4"}, {("s1", "c2"), ("c2", "c4")}),
        (False, True, {"s1", "c1", "c2", "c4"}, {("s1", "c2"), ("c2", "c4"), ("c1", "c2")}),
        (True, False, {"s1", "c2", "c4", "e3", "e15"}, {("s1", "e3"), ("e3", "c2"), ("c2", "e15"), ("e15", "c4")}),
        (
            True,
            True,
            {"s1", "c1", "c2", "c4", "e3", "e15"},
            {("s1", "e3"), ("e3", "c2"), ("c2", "e15"), ("e15", "c4"), ("e3", "c1")},
        ),
    ],
)
def test_graphs(roles, relations, with_events, with_siblings, nodes, edges):
    """The four graphs of c2 (both, all generations) of the Transformations note."""
    graph = lineage_graph(relations, roles, "c2", with_events=with_events, with_siblings=with_siblings)
    assert set(graph.nodes["node"]) == nodes
    assert _rows(graph.edges, "source", "target") == edges
    assert set(graph.nodes.filter(pl.col("role") == SIBLING)["node"]) == ({"c1"} if with_siblings else set())
    assert (graph.nodes["kind"] == EVENT).any() == with_events


def test_sibling_creation_event_added(roles, relations):
    """For dir = products the creation event of c2 is not in the lineage; with siblings it is added (greyed)."""
    graph = lineage_graph(relations, roles, "c2", "products", with_events=True, with_siblings=True)
    assert _rows(graph.nodes.filter(pl.col("kind") == EVENT), "node", "role") == {("e15", "lineage"), ("e3", SIBLING)}
    assert {("e3", "c2"), ("e3", "c1")} <= _rows(graph.edges, "source", "target")


def test_dot(roles, relations):
    """DOT source has one statement per node and edge and multi-line labels."""
    graph = lineage_graph(relations, roles, "c2", with_events=True, with_siblings=True)
    dot = to_dot(graph, {"s1": "slab", "c1": "coil", "c2": "coil", "c4": "coil"}, {"e3": "roll"})
    assert dot.startswith("digraph lineage {") and dot.endswith("}")
    assert dot.count(" -> ") == graph.edges.height
    assert 'label="c2\\ncoil"' in dot and 'label="e3\\nroll"' in dot
