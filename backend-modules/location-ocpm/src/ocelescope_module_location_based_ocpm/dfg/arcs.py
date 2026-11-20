"""Step 3: the directly-follows arcs per object type, and the two arc sliders.

For an object $o$ of type $ot$ with (projected, variant-filtered) trace $\\langle e_1, \\dots, e_n \\rangle$, the arcs
are $(\\triangleright_{ot}, act(e_1))$, $(act(e_i), act(e_{i+1}))$ for $i < n$, and $(act(e_n), \\square_{ot})$, where
$\\triangleright_{ot}$ and $\\square_{ot}$ are the start and end node of $ot$ (null source / target).
Every arc has a count (traversals: an object repeating the arc counts once per traversal), a number of
distinct objects and a first occurrence (the time of its first traversal).

Arc threshold $\\alpha_{ot} \\in [0, 100]$ (percent; `arc_share_filter`, as Ocelescope's DFG filter, Nina
2026-11-15): all arcs of $ot$, start and end arcs included, are ranked by objects, then traversals (both
descending); the first $\\lceil \\alpha_{ot} / 100 \\cdot n_{ot} \\rceil$ are kept, together with every arc tied with the
last kept one. Default: 100 % (all arcs).

Arc count $N$ (`arc_count_filter`, like the slider in Ocelescope's DFG viewer, Nina 2026-11-15): of the arcs left
by the arc threshold, the first $N$ of every object type (same $N$ for all types unless a type has its own) in
the ranking objects, traversals, first occurrence, source, target; ties are broken by this order, so exactly
$N$ arcs per type are kept (all if the type has fewer). Default: None = all.

Removed arcs (`remove_arcs`): arcs the user removed by hand (right click on the arc).
The stay-connected repair (`connectivity.stay_connected`) runs after all three.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

import polars as pl

from ..derivation import columns as c
from . import columns as d

#: Column: time of the first traversal of an arc (time of its second event; for an end arc of its last event).
FIRST_TIME = "first_time"
#: Arc key columns.
KEY = [c.OBJECT_TYPE, d.SOURCE, d.TARGET]


def directly_follows_arcs(traces: pl.DataFrame) -> pl.DataFrame:
    """All arcs of the given traces, including start and end arcs.

    Args:
        traces: Object traces, sorted by object and position (`traces.object_traces` or `variants.variant_filter`).

    Returns:
        pl.DataFrame: Columns object_type, source, target (null = start / end node), count, objects, first_time;
        sorted by `arc_order` (most objects first).
    """
    steps = traces.lazy().select(
        d.OBJECT,
        c.OBJECT_TYPE,
        pl.col(c.ACTIVITY).shift(1).over(d.OBJECT, order_by=d.POSITION).alias(d.SOURCE),
        pl.col(c.ACTIVITY).alias(d.TARGET),
        pl.col(c.TIME),
    )
    ends = (
        traces.lazy()
        .group_by(d.OBJECT, c.OBJECT_TYPE)
        .agg(pl.col(c.ACTIVITY).sort_by(d.POSITION).last().alias(d.SOURCE), pl.col(c.TIME).max())
        .with_columns(pl.lit(None, pl.String).alias(d.TARGET))
    )
    arcs = (
        pl.concat([steps, ends.select(steps.collect_schema().names())])
        .group_by(KEY)
        .agg(pl.len().alias(d.COUNT), pl.col(d.OBJECT).n_unique().alias(d.OBJECTS), pl.col(c.TIME).min().alias(FIRST_TIME))
        .collect()
    )
    return arc_order(arcs)


def arc_order(arcs: pl.DataFrame) -> pl.DataFrame:
    """Sort arcs per object type by the arc ranking: objects, traversals (both descending), first occurrence, source,
    target (start node first, end node last).

    Args:
        arcs: Arcs with the columns of `directly_follows_arcs`.

    Returns:
        pl.DataFrame: The same rows, sorted by object type, then the ranking.
    """
    return arcs.sort(
        [c.OBJECT_TYPE, d.OBJECTS, d.COUNT, FIRST_TIME, d.SOURCE, d.TARGET],
        descending=[False, True, True, False, False, False],
        nulls_last=[False, False, False, False, False, True],
    )


def objects_per_type(traces: pl.DataFrame) -> dict[str, int]:
    """Number of distinct objects per object type in the given traces.

    Args:
        traces: Object traces.

    Returns:
        dict[str, int]: object type -> number of objects.
    """
    counts = traces.group_by(c.OBJECT_TYPE).agg(pl.col(d.OBJECT).n_unique())
    return dict(zip(counts[c.OBJECT_TYPE], counts[d.OBJECT], strict=True))


def arc_share_filter(arcs: pl.DataFrame, thresholds: Mapping[str, float]) -> pl.DataFrame:
    """Keep the most frequent `thresholds[ot]` % of the arcs of every object type, ties with the last one included.

    As `filter_edges` of Ocelescope's `DirectlyFollowsGraph` without its connectivity repair (that is
    `connectivity.stay_connected`, optional here). Example: 7 arcs with (objects, traversals) (8, 8), (8, 8), (5, 6),
    (5, 5), (5, 5), (2, 2), (1, 1) at 50 %: ceil(3.5) = 4 arcs, and the fifth is tied with the fourth -> 5 arcs.

    Args:
        arcs: Arcs (`directly_follows_arcs`), start and end arcs included.
        thresholds: Arc threshold per object type in percent (0 to 100); a missing type uses 100 (all arcs).

    Returns:
        pl.DataFrame: The kept rows of `arcs`, in the same order.
    """
    threshold = pl.col(c.OBJECT_TYPE).replace_strict(dict(thresholds), default=100.0, return_dtype=pl.Float64)
    # Rank with ties sharing the smallest rank ("min"), by objects, then traversals: an arc is kept if its rank is at
    # most ceil(alpha / 100 * n), i.e. (rank - 1) * 100 < alpha * n (rounded against floating-point noise).
    key = pl.col(d.OBJECTS).cast(pl.Int64) * (pl.col(d.COUNT).max() + 1).cast(pl.Int64) + pl.col(d.COUNT).cast(pl.Int64)
    rank = key.rank("min", descending=True).over(c.OBJECT_TYPE)
    keep = (rank - 1) * 100 < (threshold * pl.len().over(c.OBJECT_TYPE)).round(6)
    return arcs.filter(keep)


def arc_count_filter(
    arcs: pl.DataFrame, counts: Mapping[str, int | None], total: int | None = None
) -> pl.DataFrame:
    """Arcs (display): keep the first `counts[ot]` arcs of every object type in the arc ranking (`arc_order`); ties
    are broken by it. With `total` ("general" mode, Nina 2026-11-16), the types without a count share one limit: the
    first `total` of their arcs together, ranked by objects, traversals (both descending), position in the ranking of
    their type, then object type.
    Example: coil arcs with 4, 3, 2 objects and slab arcs with 1, 1 object, total 3: the three coil arcs.

    Args:
        arcs: Arcs (after `arc_share_filter`).
        counts: Arc count per object type; None or a missing type = no limit of its own.
        total: Limit shared by the types without a count; None = all their arcs.

    Returns:
        pl.DataFrame: The kept rows of `arcs`, sorted by `arc_order`.
    """
    limits = {t: n for t, n in counts.items() if n is not None}
    ordered = arc_order(arcs).with_columns(pl.int_range(1, pl.len() + 1).over(c.OBJECT_TYPE).alias("_position"))
    limit = pl.col(c.OBJECT_TYPE).replace_strict(limits, default=None, return_dtype=pl.Int64)
    kept = ordered.filter(limit.is_null() | (pl.col("_position") <= limit))
    if total is not None:
        pooled = kept.filter(limit.is_null()).sort(
            [d.OBJECTS, d.COUNT, "_position", c.OBJECT_TYPE], descending=[True, True, False, False]
        )
        dropped = pooled.slice(max(total, 0)).select(c.OBJECT_TYPE, "_position")
        kept = kept.join(dropped, on=[c.OBJECT_TYPE, "_position"], how="anti", maintain_order="left")
    return kept.drop("_position")


def remove_arcs(arcs: pl.DataFrame, removed: Collection[tuple[str, str | None, str | None]]) -> pl.DataFrame:
    """Remove the arcs the user removed by hand.

    Args:
        arcs: Arcs.
        removed: (object type, source, target) of every removed arc; None = start / end node.

    Returns:
        pl.DataFrame: The other rows of `arcs`, in the same order.
    """
    if not removed:
        return arcs
    keys = pl.DataFrame(list(removed), schema={c.OBJECT_TYPE: pl.String, d.SOURCE: pl.String, d.TARGET: pl.String}, orient="row")
    return arcs.join(keys, on=KEY, how="anti", nulls_equal=True, maintain_order="left")


def arcs_per_type(arcs: pl.DataFrame) -> dict[str, int]:
    """Number of arcs per object type.

    Args:
        arcs: Arcs.

    Returns:
        dict[str, int]: object type -> number of arcs.
    """
    counts = arcs.group_by(c.OBJECT_TYPE).len()
    return dict(zip(counts[c.OBJECT_TYPE], counts["len"], strict=True))
