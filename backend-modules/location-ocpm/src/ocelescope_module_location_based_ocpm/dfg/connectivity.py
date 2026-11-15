"""Step 3b: "Stay connected", the optional connectivity repair of the arcs (default on; Nina, 2026-11-15).

As the repair in `filter_edges` of Ocelescope's `DirectlyFollowsGraph`: every shown arc lies on a path from the
start to the end node of its object type. It overrides the arc threshold, the arc count and nothing else: it may
add back arcs that these two removed, but never arcs of removed variants, of deselected activities, or arcs the
user removed by hand.

Per object type:
1. Base graph: the arcs of the kept (projected, variant-filtered) traces, without the arcs removed by hand,
   reduced to the arcs that still lie on a start-to-end path (removing arcs by hand can cut others off).
2. Required activities: the endpoints of the arcs left by the arc threshold and arc count (and in the base graph).
3. Every base arc that the sliders removed is taken out again, least frequent first (reverse `arcs.arc_order`),
   unless this would cut a required activity off from the start or the end node; then it stays.

Example: the sliders keep produce -> pick and pick -> pack of the pallets, but no arc into the end node.
pack -> load, load -> ship and ship -> end stay as well, because without them pack could not reach the end node.
"""

from __future__ import annotations

import networkx as nx
import polars as pl

from ..derivation import columns as c
from . import columns as d
from .arcs import KEY, arc_order

#: Column: True if an arc is shown only because of the connectivity repair.
CONNECTING = "connecting"
_START, _END = object(), object()


def _endpoints(source: str | None, target: str | None) -> tuple[object, object]:
    """The graph nodes of an arc: the start / end sentinel for a null source / target."""
    return (_START if source is None else source, _END if target is None else target)


def on_start_end_paths(arcs: pl.DataFrame) -> pl.DataFrame:
    """The arcs that lie on a path from the start to the end node of their object type.

    Args:
        arcs: Arcs (`arcs.directly_follows_arcs`, possibly filtered).

    Returns:
        pl.DataFrame: These rows of `arcs`, in the same order.
    """
    keep = []
    for (_,), group in arcs.group_by([c.OBJECT_TYPE], maintain_order=True):
        edges = [_endpoints(s, t) for s, t in group.select(d.SOURCE, d.TARGET).iter_rows()]
        graph = nx.DiGraph(edges)
        graph.add_nodes_from((_START, _END))
        reachable = nx.descendants(graph, _START) | {_START}
        reaching = nx.ancestors(graph, _END) | {_END}
        keep.append(group.filter(pl.Series([u in reachable and v in reaching for u, v in edges], dtype=pl.Boolean)))
    return pl.concat(keep) if keep else arcs.clear()


def stay_connected(base: pl.DataFrame, kept: pl.DataFrame) -> pl.DataFrame:
    """Add back the fewest, most frequent arcs of `base` so that every arc lies on a start-to-end path.

    Args:
        base: Arcs of the kept traces without the hand-removed arcs (`arcs.remove_arcs`).
        kept: Arcs left by the arc threshold, the arc count and the hand removals (a subset of `base`).

    Returns:
        pl.DataFrame: The shown arcs (columns of `base` plus `connecting`), sorted by `arcs.arc_order`.
    """
    base = on_start_end_paths(base)
    kept_keys = kept.select(KEY).join(base.select(KEY), on=KEY, how="semi", nulls_equal=True)
    marked = base.join(kept_keys.with_columns(pl.lit(False).alias(CONNECTING)), on=KEY, how="left", nulls_equal=True).with_columns(
        pl.col(CONNECTING).fill_null(True)
    )
    result = []
    for (_,), group in arc_order(marked).group_by([c.OBJECT_TYPE], maintain_order=True):
        rows = group.select(d.SOURCE, d.TARGET, CONNECTING).rows()
        required = {node for s, t, extra in rows if not extra for node in _endpoints(s, t)}
        graph = nx.DiGraph()
        graph.add_nodes_from((_START, _END))
        graph.add_edges_from(_endpoints(s, t) for s, t, _ in rows)
        for s, t, extra in reversed(rows):  # least frequent first
            if not extra:
                continue
            edge = _endpoints(s, t)
            graph.remove_edge(*edge)
            if not required <= (nx.descendants(graph, _START) | {_START}) & (nx.ancestors(graph, _END) | {_END}):
                graph.add_edge(*edge)
        result.append(group.filter(pl.Series([graph.has_edge(*_endpoints(s, t)) for s, t, _ in rows], dtype=pl.Boolean)))
    return arc_order(pl.concat(result)) if result else marked.clear()
