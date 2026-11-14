"""Step 3: the directly-follows arcs per object type, and the arc filter.

For an object $o$ of type $ot$ with trace $\\langle e_1, \\dots, e_n \\rangle$, the arcs are
$(\\triangleright_{ot}, act(e_1))$, $(act(e_i), act(e_{i+1}))$ for $i < n$, and $(act(e_n), \\square_{ot})$,
where $\\triangleright_{ot}$ and $\\square_{ot}$ are the start and end node of $ot$ (null source / target).
Every arc has a count (traversals: an object repeating the arc counts once per traversal) and a number of
distinct objects.

The arc threshold $\\alpha_{ot} \\in [0, 100]$ (percent; Nina, 2026-11-14) keeps the most frequent $\\alpha_{ot}$ % of
the directly-follows relations of $ot$ (the arcs between two activities, computed on the path-filtered traces):
the $n_{ot}$ arcs are ranked by count (traversals), then objects (both descending), then source and target
(alphabetically), and the first $\\lceil \\alpha_{ot} / 100 \\cdot n_{ot} \\rceil$ are kept.
Start and end arcs are always kept. $\\alpha_{ot} = 100$ keeps every arc, $\\alpha_{ot} = 0$ only the start and end
arcs. Default: 10 %.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

import polars as pl

from ..derivation import columns as c
from . import columns as d


def directly_follows_arcs(traces: pl.DataFrame) -> pl.DataFrame:
    """All arcs of the given traces, including start and end arcs.

    Args:
        traces: Object traces, sorted by object and position (`traces.object_traces` or `path_filter`).

    Returns:
        pl.DataFrame: Columns object_type, source, target (null = start / end node), count, objects; sorted by
        object type, then objects descending, count descending, source, target.
    """
    steps = traces.lazy().select(
        d.OBJECT,
        c.OBJECT_TYPE,
        pl.col(c.ACTIVITY).shift(1).over(d.OBJECT, order_by=d.POSITION).alias(d.SOURCE),
        pl.col(c.ACTIVITY).alias(d.TARGET),
    )
    ends = (
        traces.lazy()
        .group_by(d.OBJECT, c.OBJECT_TYPE)
        .agg(pl.col(c.ACTIVITY).sort_by(d.POSITION).last().alias(d.SOURCE))
        .with_columns(pl.lit(None, pl.String).alias(d.TARGET))
    )
    return (
        pl.concat([steps, ends.select(steps.collect_schema().names())])
        .group_by(c.OBJECT_TYPE, d.SOURCE, d.TARGET)
        .agg(pl.len().alias(d.COUNT), pl.col(d.OBJECT).n_unique().alias(d.OBJECTS))
        .sort(
            [c.OBJECT_TYPE, d.OBJECTS, d.COUNT, d.SOURCE, d.TARGET],
            descending=[False, True, True, False, False],
            nulls_last=False,
        )
        .collect()
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


def arc_filter(arcs: pl.DataFrame, thresholds: Mapping[str, float]) -> pl.DataFrame:
    """Keep the most frequent `thresholds[ot]` % of the arcs between activities of every object type, and all start
    and end arcs.

    Args:
        arcs: Arcs (`directly_follows_arcs`).
        thresholds: Arc threshold per object type in percent (0 to 100); a missing type uses 100 (all arcs).

    Returns:
        pl.DataFrame: The kept rows of `arcs`, in the same order.
    """
    threshold = pl.col(c.OBJECT_TYPE).replace_strict(dict(thresholds), default=100.0, return_dtype=pl.Float64)
    inner = pl.col(d.SOURCE).is_not_null() & pl.col(d.TARGET).is_not_null()
    ranked = (
        arcs.with_row_index("_order")
        .sort(
            [c.OBJECT_TYPE, d.COUNT, d.OBJECTS, d.SOURCE, d.TARGET],
            descending=[False, True, True, False, False],
            nulls_last=True,
        )
        .with_columns(
            # 1-based rank among the arcs between activities of the type; n = their number.
            pl.when(inner).then(pl.int_range(1, pl.len() + 1).over(c.OBJECT_TYPE, inner)).alias("_rank"),
            inner.sum().over(c.OBJECT_TYPE).alias("_n"),
        )
    )
    # rank <= ceil(alpha / 100 * n)  <=>  (rank - 1) * 100 < alpha * n  (exact in whole numbers for whole percents).
    keep = ~inner | ((pl.col("_rank") - 1) * 100 < threshold * pl.col("_n"))
    return ranked.filter(keep).sort("_order").drop("_order", "_rank", "_n")


def remove_activities(arcs: pl.DataFrame, activities: Collection[str]) -> pl.DataFrame:
    """Remove the arcs that start or end at one of the given (deselected) activities.

    Deselecting an activity removes its node and every arc touching it (including start and end arcs); the traces
    are not projected, so no new arcs between its neighbours appear.

    Args:
        arcs: Kept arcs (`arc_filter`).
        activities: Deselected activities.

    Returns:
        pl.DataFrame: The remaining rows of `arcs`, in the same order.
    """
    excluded = list(activities)
    if not excluded:
        return arcs
    return arcs.filter(~pl.col(d.SOURCE).is_in(excluded).fill_null(False) & ~pl.col(d.TARGET).is_in(excluded).fill_null(False))
