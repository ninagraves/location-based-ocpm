"""Step 2: the path filter, per object type.

A *path* (variant) of an object is the sequence of the activities of its trace.
The path threshold $\\pi_{ot} \\in [0, 100]$ (percent) of an object type $ot$ keeps the most frequent paths of $ot$ until
they cover at least $\\pi_{ot}$ % of its objects: paths are ranked by their number of objects
(descending; ties by the path itself, alphabetically), and a path is kept if the objects of the paths
ranked before it cover less than $\\pi_{ot} / 100 \\cdot |O_{ot}|$.
Ties are not kept together on purpose: in logistics logs most objects often have a path of their own (all paths
have one object), and keeping ties would then keep every path for any threshold.
$\\pi_{ot} = 100$ keeps every path, $\\pi_{ot} = 0$ keeps none. Default: 30 % (Nina, 2026-11-14).
Only the objects of kept paths contribute to the arcs and nodes of the graph.
"""

from __future__ import annotations

from collections.abc import Mapping

import polars as pl

from ..derivation import columns as c
from . import columns as d


def object_variants(traces: pl.DataFrame) -> pl.DataFrame:
    """The path (variant) of every object.

    Args:
        traces: Object traces, sorted by object and position (`traces.object_traces`).

    Returns:
        pl.DataFrame: Columns object, object_type, variant (activities joined by `VARIANT_SEPARATOR`).
    """
    return traces.group_by(d.OBJECT, c.OBJECT_TYPE, maintain_order=True).agg(
        pl.col(c.ACTIVITY).sort_by(d.POSITION).str.join(d.VARIANT_SEPARATOR).alias(d.VARIANT)
    )


def variant_ranking(variants: pl.DataFrame) -> pl.DataFrame:
    """The paths of every object type with their number of objects, most frequent first.

    Args:
        variants: Columns object, object_type, variant (`object_variants`).

    Returns:
        pl.DataFrame: Columns object_type, variant, objects (count), covered_before (objects of the paths
        ranked before it within the object type), sorted by object type and rank.
    """
    return (
        variants.group_by(c.OBJECT_TYPE, d.VARIANT)
        .agg(pl.len().alias(d.OBJECTS))
        .sort([c.OBJECT_TYPE, d.OBJECTS, d.VARIANT], descending=[False, True, False])
        .with_columns(
            (pl.col(d.OBJECTS).cum_sum().over(c.OBJECT_TYPE) - pl.col(d.OBJECTS)).alias("covered_before")
        )
    )


def kept_variants(ranking: pl.DataFrame, thresholds: Mapping[str, float]) -> pl.DataFrame:
    """The paths kept by the path thresholds.

    Args:
        ranking: Ranked paths (`variant_ranking`).
        thresholds: Path threshold per object type in percent (0 to 100); a missing type uses 100 (all paths).

    Returns:
        pl.DataFrame: The rows of `ranking` that are kept.
    """
    threshold = pl.col(c.OBJECT_TYPE).replace_strict(dict(thresholds), default=100.0, return_dtype=pl.Float64)
    total = pl.col(d.OBJECTS).sum().over(c.OBJECT_TYPE)
    # Compared in integers times percent, so that e.g. 7 % of 100 objects is exactly 7 objects.
    return ranking.filter(pl.col("covered_before") * 100 < threshold * total)


def path_filter(traces: pl.DataFrame, thresholds: Mapping[str, float]) -> pl.DataFrame:
    """Keep the traces of the objects whose path is kept by the path threshold of their object type.

    Args:
        traces: Object traces (`traces.object_traces`).
        thresholds: Path threshold per object type in percent (0 to 100); a missing type uses 100 (all paths).

    Returns:
        pl.DataFrame: The rows of `traces` of kept objects, in the same order.
    """
    variants = object_variants(traces)
    kept = kept_variants(variant_ranking(variants), thresholds).select(c.OBJECT_TYPE, d.VARIANT)
    objects = variants.join(kept, on=[c.OBJECT_TYPE, d.VARIANT], how="semi").select(d.OBJECT)
    return traces.join(objects, on=d.OBJECT, how="semi", maintain_order="left")
