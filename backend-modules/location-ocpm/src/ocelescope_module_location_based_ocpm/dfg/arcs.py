"""Step 3: the directly-follows arcs per object type, and the arc filter.

For an object $o$ of type $ot$ with trace $\\langle e_1, \\dots, e_n \\rangle$, the arcs are
$(\\triangleright_{ot}, act(e_1))$, $(act(e_i), act(e_{i+1}))$ for $i < n$, and $(act(e_n), \\square_{ot})$,
where $\\triangleright_{ot}$ and $\\square_{ot}$ are the start and end node of $ot$ (null source / target).
Every arc has a count (traversals: an object repeating the arc counts once per traversal) and a number of
distinct objects.

The arc threshold $\\alpha_{ot} \\in [0, 100]$ (percent) keeps an arc of $ot$ if at least $\\alpha_{ot}$ % of the
(path-filtered) objects of $ot$ traverse it: $objects(arc) \\ge \\alpha_{ot} / 100 \\cdot |O'_{ot}|$.
$\\alpha_{ot} = 0$ keeps every arc (the default). Start and end arcs are filtered in the same way.
"""

from __future__ import annotations

from collections.abc import Mapping

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


def arc_filter(arcs: pl.DataFrame, n_objects: Mapping[str, int], thresholds: Mapping[str, float]) -> pl.DataFrame:
    """Keep the arcs traversed by at least `thresholds[ot]` % of the objects of their type.

    Args:
        arcs: Arcs (`directly_follows_arcs`).
        n_objects: Number of (path-filtered) objects per object type, the reference of the share.
        thresholds: Arc threshold per object type in percent (0 to 100); a missing type uses 0 (all arcs).

    Returns:
        pl.DataFrame: The kept rows of `arcs`, in the same order.
    """
    threshold = pl.col(c.OBJECT_TYPE).replace_strict(dict(thresholds), default=0.0, return_dtype=pl.Float64)
    total = pl.col(c.OBJECT_TYPE).replace_strict(dict(n_objects), default=0, return_dtype=pl.Int64)
    # Compared times 100, so that e.g. 7 % of 100 objects is exactly 7 objects.
    return arcs.filter(pl.col(d.OBJECTS) * 100 >= threshold * total)
