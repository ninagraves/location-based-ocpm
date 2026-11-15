"""Step 2: the path filter, per object type.

A *path* (variant) of an object is the sequence of the activities of its trace.
The path threshold $\\pi_{ot} \\in [0, 100]$ (percent) of an object type $ot$ keeps the most frequent paths of $ot$ until
they cover at least $\\pi_{ot}$ % of its objects: paths are ranked by their number of objects
(descending; equally frequent paths by their first occurrence in the log, i.e. the earliest first event of
their objects, Nina 2026-11-15; then by the path itself), and a path is kept if the objects of the paths
ranked before it cover less than $\\pi_{ot} / 100 \\cdot |O_{ot}|$.
Ties are not kept together on purpose: in logistics logs most objects often have a path of their own (all paths
have one object), and keeping ties would then keep every path for any threshold.
$\\pi_{ot} = 100$ keeps every path, $\\pi_{ot} = 0$ keeps none.
Default ("automatic", $\\pi_{ot}$ = None): the `AUTO_PATHS` = 3 most frequent paths in full, i.e. the threshold
depends on the data: $\\pi_{ot}$ = share of the objects of the three top-ranked paths (Nina, 2026-11-15).
Only the objects of kept paths contribute to the arcs and nodes of the graph.
"""

from __future__ import annotations

from collections.abc import Mapping

import polars as pl

from ..derivation import columns as c
from . import columns as d

#: Number of top-ranked paths kept by the automatic (default) path threshold (Nina, 2026-11-15).
AUTO_PATHS = 3
#: Column: time of the first event of an object (and the earliest of a path's objects).
FIRST_TIME = "first_time"
#: Column: rank of a path within its object type (1 = most frequent).
RANK = "rank"


def object_variants(traces: pl.DataFrame) -> pl.DataFrame:
    """The path (variant) of every object.

    Args:
        traces: Object traces, sorted by object and position (`traces.object_traces`).

    Returns:
        pl.DataFrame: Columns object, object_type, variant (activities joined by `VARIANT_SEPARATOR`),
        first_time (time of the object's first event).
    """
    return traces.group_by(d.OBJECT, c.OBJECT_TYPE, maintain_order=True).agg(
        pl.col(c.ACTIVITY).sort_by(d.POSITION).str.join(d.VARIANT_SEPARATOR).alias(d.VARIANT),
        pl.col(c.TIME).min().alias(FIRST_TIME),
    )


def variant_ranking(variants: pl.DataFrame) -> pl.DataFrame:
    """The paths of every object type with their number of objects, most frequent first.

    Equally frequent paths are ranked by their first occurrence in the log (the earliest first event of
    their objects; Nina, 2026-11-15), then by the path itself.

    Args:
        variants: Columns object, object_type, variant, first_time (`object_variants`).

    Returns:
        pl.DataFrame: Columns object_type, variant, objects (count), first_time, rank (1 = most frequent,
        within the object type), covered_before (objects of the paths ranked before it within the object
        type), sorted by object type and rank.
    """
    return (
        variants.group_by(c.OBJECT_TYPE, d.VARIANT)
        .agg(pl.len().alias(d.OBJECTS), pl.col(FIRST_TIME).min())
        .sort([c.OBJECT_TYPE, d.OBJECTS, FIRST_TIME, d.VARIANT], descending=[False, True, False, False])
        .with_columns(
            pl.int_range(1, pl.len() + 1, dtype=pl.UInt32).over(c.OBJECT_TYPE).alias(RANK),
            (pl.col(d.OBJECTS).cum_sum().over(c.OBJECT_TYPE) - pl.col(d.OBJECTS)).alias("covered_before"),
        )
    )


def auto_path_thresholds(ranking: pl.DataFrame) -> dict[str, float]:
    """The automatic (default) path threshold per object type: the share of objects of its `AUTO_PATHS` top paths.

    With this threshold exactly the `AUTO_PATHS` top-ranked paths are kept (all paths if there are fewer).

    Args:
        ranking: Ranked paths (`variant_ranking`).

    Returns:
        dict[str, float]: Object type -> threshold in percent (100 if the type has at most `AUTO_PATHS` paths).
    """
    shares = ranking.group_by(c.OBJECT_TYPE).agg(
        (pl.col(d.OBJECTS).filter(pl.col(RANK) <= AUTO_PATHS).sum() * 100 / pl.col(d.OBJECTS).sum()).alias("share")
    )
    return dict(zip(shares[c.OBJECT_TYPE], shares["share"], strict=True))


def kept_variants(ranking: pl.DataFrame, thresholds: Mapping[str, float | None]) -> pl.DataFrame:
    """The paths kept by the path thresholds.

    Args:
        ranking: Ranked paths (`variant_ranking`).
        thresholds: Path threshold per object type in percent (0 to 100, decimals allowed); None = automatic
            (the `AUTO_PATHS` top-ranked paths); a missing type uses 100 (all paths).

    Returns:
        pl.DataFrame: The rows of `ranking` that are kept.
    """
    auto = [t for t, v in thresholds.items() if v is None]
    fixed = {t: v for t, v in thresholds.items() if v is not None}
    threshold = pl.col(c.OBJECT_TYPE).replace_strict(fixed, default=100.0, return_dtype=pl.Float64)
    total = pl.col(d.OBJECTS).sum().over(c.OBJECT_TYPE)
    # Compared in objects times percent (rounded against floating-point noise), so that e.g. 7 % of 100 objects
    # is exactly 7 objects.
    by_share = pl.col("covered_before") * 100 < (threshold * total).round(6)
    by_rank = pl.col(RANK) <= AUTO_PATHS
    return ranking.filter(pl.when(pl.col(c.OBJECT_TYPE).is_in(auto)).then(by_rank).otherwise(by_share))


def path_filter(traces: pl.DataFrame, thresholds: Mapping[str, float | None]) -> pl.DataFrame:
    """Keep the traces of the objects whose path is kept by the path threshold of their object type.

    Args:
        traces: Object traces (`traces.object_traces`).
        thresholds: Path threshold per object type in percent; None = automatic (`kept_variants`); a missing
            type uses 100 (all paths).

    Returns:
        pl.DataFrame: The rows of `traces` of kept objects, in the same order.
    """
    variants = object_variants(traces)
    kept = kept_variants(variant_ranking(variants), thresholds).select(c.OBJECT_TYPE, d.VARIANT)
    objects = variants.join(kept, on=[c.OBJECT_TYPE, d.VARIANT], how="semi").select(d.OBJECT)
    return traces.join(objects, on=d.OBJECT, how="semi", maintain_order="left")
