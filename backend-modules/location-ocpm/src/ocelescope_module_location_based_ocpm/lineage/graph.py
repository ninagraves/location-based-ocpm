"""Instance visualisation: the lineage of a handling unit as a graph, with or without events and siblings.

Concept: `overview/concepts/Transformations.md`, section "Instance Visualisation".
Two options give four graphs:
- `with_events`: False = object graph (every node is a handling unit, arcs $x \\to y$ for $(x, y, e) \\in R'$);
  True = bipartite graph of handling units and transformation events (arcs $x \\to e \\to y$).
- `with_siblings`: also show the siblings $S$ of the lineage's handling units (greyed), connected by an
  undirected sibling edge (object graph) or by arcs from the shared creation event (bipartite graph).

`lineage_graph` returns plain node and edge tables; `to_dot` turns them into Graphviz DOT source for rendering.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import polars as pl

from ocelescope_module_location_based_ocpm.lineage.lineage import Direction, lineage
from ocelescope_module_location_based_ocpm.lineage.relations import FrameLike, creation_events, siblings
from ocelescope_module_location_based_ocpm.visits.trace_figure import CATEGORICAL

#: Node kinds.
OBJECT, EVENT = "object", "event"
#: Node roles: the selected handling unit, a node of the lineage, a sibling (or its creation event).
FOCAL, LINEAGE, SIBLING = "focal", "lineage", "sibling"
#: Edge kinds.
LINEAGE_EDGE, SIBLING_EDGE = "lineage", "sibling"

_NODES = {"node": pl.String, "kind": pl.String, "role": pl.String}
_EDGES = {"source": pl.String, "target": pl.String, "kind": pl.String, "event": pl.String, "directed": pl.Boolean}


@dataclass(frozen=True)
class LineageGraph:
    """Nodes and edges of a lineage graph.

    Attributes:
        nodes: Columns node (hu or event id), kind (`object`/`event`) and role (`focal`/`lineage`/`sibling`).
        edges: Columns source, target, kind (`lineage`/`sibling`), event (the transformation event the edge
            stands for) and directed (False only for sibling edges of the object graph).
    """

    nodes: pl.DataFrame
    edges: pl.DataFrame


def lineage_graph(
    relations: pl.DataFrame,
    roles: FrameLike,
    hu: str,
    direction: Direction = "both",
    gen: float = math.inf,
    with_events: bool = False,
    with_siblings: bool = False,
) -> LineageGraph:
    """The graph of the lineage $R' = R(hu, dir, gen)$ for one of the four visualisation options.

    Nodes: the handling units $O' = \\set{hu} \\cup \\set{x, y \\mid (x, y, e) \\in R'}$, with events also
    $T' = \\set{e \\mid (x, y, e) \\in R'}$, with siblings also $S = \\bigcup_{x \\in O'} siblings(x) \\setminus O'$
    (and, with events, the creation events $ev_{prod}(x)$ of the hus that have siblings in $S$).

    Args:
        relations: The lineage relations R (`relations.lineage_relations`).
        roles: Transformation roles with the columns event, hu, role (for siblings and creation events).
        hu: The selected handling unit.
        direction: `components`, `products` or `both` (default).
        gen: Generations per direction, a natural number or `math.inf` (default).
        with_events: Bipartite graph with the transformation events as nodes (default: object graph).
        with_siblings: Add the siblings (default: direct lineage only).

    Returns:
        LineageGraph with unique nodes and edges.
    """
    lin = lineage(relations, hu, direction, gen)
    objects = sorted({hu} | set(lin["parent"]) | set(lin["child"]))
    nodes = [(o, OBJECT, FOCAL if o == hu else LINEAGE) for o in objects]
    if with_events:
        nodes += [(e, EVENT, LINEAGE) for e in sorted(set(lin["event"]))]
        edges = [(x, e, LINEAGE_EDGE, e, True) for x, e in lin.select("parent", "event").iter_rows()]
        edges += [(e, y, LINEAGE_EDGE, e, True) for e, y in lin.select("event", "child").iter_rows()]
    else:
        edges = [(x, y, LINEAGE_EDGE, e, True) for x, y, e in lin.select("parent", "child", "event").iter_rows()]

    if with_siblings:
        sib = siblings(roles).filter(pl.col("hu").is_in(objects) & ~pl.col("sibling").is_in(objects))
        nodes += [(s, OBJECT, SIBLING) for s in sorted(set(sib["sibling"]))]
        if with_events:
            known = {n for n, _, _ in nodes}
            nodes += [(e, EVENT, SIBLING) for e in sorted(set(sib["event"]) - known)]
            for x, s, e in sib.iter_rows():
                edges += [(e, x, LINEAGE_EDGE, e, True), (e, s, SIBLING_EDGE, e, True)]
        else:
            edges += [(x, s, SIBLING_EDGE, e, False) for x, s, e in sib.iter_rows()]

    node_frame = pl.DataFrame(nodes, schema=_NODES, orient="row").unique(subset="node", keep="first", maintain_order=True)
    edge_frame = pl.DataFrame(edges, schema=_EDGES, orient="row").unique(maintain_order=True)
    if not with_events:  # an undirected sibling edge between two siblings in S would appear twice
        edge_frame = edge_frame.with_columns(
            pl.when(pl.col("directed")).then(pl.col("source")).otherwise(pl.min_horizontal("source", "target")).alias("source"),
            pl.when(pl.col("directed")).then(pl.col("target")).otherwise(pl.max_horizontal("source", "target")).alias("target"),
        ).unique(maintain_order=True)
    return LineageGraph(node_frame, edge_frame)


def type_colours(object_types: dict[str, str]) -> dict[str, str]:
    """One palette colour per object type, in order of first appearance of the sorted types.

    Args:
        object_types: Mapping hu → object type.

    Returns:
        Mapping object type → colour from the module's categorical palette.
    """
    types = sorted(set(object_types.values()))
    return {t: CATEGORICAL[i % len(CATEGORICAL)] for i, t in enumerate(types)}


def _quote(text: str) -> str:
    """Quote `text` as a DOT string (line breaks become DOT `\\n`)."""
    escaped = str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return '"' + escaped + '"'


def to_dot(
    graph: LineageGraph,
    object_types: dict[str, str] | None = None,
    activities: dict[str, str] | None = None,
    rankdir: str = "LR",
) -> str:
    """Graphviz DOT source of a lineage graph.

    Handling units are ellipses filled in the colour of their object type, events are small white boxes
    (labelled with the activity if given), the selected hu has a thick border, siblings and their edges are
    grey and dashed. In the object graph the lineage arcs are labelled with their event.

    Args:
        graph: The graph (`lineage_graph`).
        object_types: Mapping hu → object type, for colours and labels (default: all one colour, no type).
        activities: Mapping event → activity, for event labels (default: event id only).
        rankdir: Graphviz layout direction (default `LR`, components left, products right).

    Returns:
        DOT source; render it with Graphviz, e.g. `dot -Tpng`.
    """
    object_types = object_types or {}
    activities = activities or {}
    colours = type_colours(object_types)
    lines = [
        "digraph lineage {",
        f"  rankdir={rankdir};",
        '  node [fontname="Helvetica", fontsize=11];',
        '  edge [fontname="Helvetica", fontsize=9, color="#555555"];',
    ]
    for node, kind, role in graph.nodes.iter_rows():
        if kind == OBJECT:
            otype = object_types.get(node)
            label = f"{node}\n{otype}" if otype else node
            fill = "#e0e0e0" if role == SIBLING else colours.get(otype, CATEGORICAL[0])
            font = "#555555" if role == SIBLING else "white"
            style = '"filled,dashed"' if role == SIBLING else "filled"
            pen = 3 if role == FOCAL else 1
            border = "#000000" if role == FOCAL else ("#999999" if role == SIBLING else fill)
            lines.append(
                f"  {_quote(node)} [shape=ellipse, style={style}, fillcolor={_quote(fill)}, color={_quote(border)}, "
                f"penwidth={pen}, fontcolor={_quote(font)}, label={_quote(label)}];"
            )
        else:
            act = activities.get(node)
            label = f"{node}\n{act}" if act else node
            colour = "#999999" if role == SIBLING else "#333333"
            style = "dashed" if role == SIBLING else "solid"
            lines.append(
                f"  {_quote(node)} [shape=box, style={style}, color={_quote(colour)}, fontcolor={_quote(colour)}, "
                f"fontsize=9, height=0.3, label={_quote(label)}];"
            )
    for source, target, kind, event, directed in graph.edges.iter_rows():
        attrs = []
        if kind == SIBLING_EDGE:
            attrs += ['style=dashed', 'color="#999999"']
        if not directed:
            attrs += ["dir=none", "constraint=false"]
        elif not graph.nodes.filter(pl.col("kind") == EVENT).height:
            attrs.append(f"label={_quote(event)}")
        lines.append(f"  {_quote(source)} -> {_quote(target)} [{', '.join(attrs)}];")
    lines.append("}")
    return "\n".join(lines)
