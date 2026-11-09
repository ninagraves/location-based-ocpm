"""The lineage $R(hu, dir, gen)$ of a handling unit: its components and/or products over a number of generations.

Concept: `overview/concepts/Transformations.md`, section "Instance Lineage".
"""

from __future__ import annotations

import math
from typing import Literal

import polars as pl

Direction = Literal["components", "products", "both"]

_SCHEMA = {"parent": pl.String, "child": pl.String, "event": pl.String, "direction": pl.String, "generation": pl.Int64}


def generations(
    relations: pl.DataFrame, hu: str, direction: Literal["components", "products"], gen: float = math.inf
) -> pl.DataFrame:
    """The generations $R^i_{comp}(hu)$ or $R^i_{prod}(hu)$ for $i = 1, \\dots, gen$, one join per generation.

    Components: $R^1_{comp}(hu)$ are the relations with child $hu$, $R^{i+1}_{comp}(hu)$ those whose child is a
    parent in $R^i_{comp}(hu)$. Products: $R^1_{prod}(hu)$ are the relations with parent $hu$, $R^{i+1}_{prod}(hu)$
    those whose parent is a child in $R^i_{prod}(hu)$. The loop stops after `gen` generations or when a
    generation is empty (it always stops, as R is finite and, by AS-T2, acyclic).

    Args:
        relations: The lineage relations R with the columns parent, child, event (`lineage_relations`).
        hu: The handling unit.
        direction: `components` or `products`.
        gen: Number of generations, a natural number or `math.inf` (all); 0 gives no relation.

    Returns:
        DataFrame with the columns parent, child, event, direction and generation ($i$); a relation reached in
        several generations keeps its smallest $i$.
    """
    if direction not in ("components", "products"):
        raise ValueError(f"direction must be 'components' or 'products', not {direction!r}")
    near, far = ("child", "parent") if direction == "components" else ("parent", "child")
    frames: list[pl.DataFrame] = []
    frontier = [hu]
    i = 0
    while frontier and i < gen:
        i += 1
        step = relations.select("parent", "child", "event").filter(pl.col(near).is_in(frontier))
        for earlier in frames:  # a relation reached again (diamond-shaped lineage) keeps its first generation
            step = step.join(earlier, on=["parent", "child", "event"], how="anti")
        if step.is_empty():
            break
        frames.append(step)
        frontier = step[far].unique().to_list()
    if not frames:
        return pl.DataFrame(schema=_SCHEMA)
    return pl.concat(
        [f.with_columns(pl.lit(direction).alias("direction"), pl.lit(k).alias("generation")) for k, f in enumerate(frames, 1)]
    ).cast(_SCHEMA)


def lineage(relations: pl.DataFrame, hu: str, direction: Direction = "both", gen: float = math.inf) -> pl.DataFrame:
    """The lineage $R(hu, dir, gen) \\subseteq R$.

    $R(hu, components, gen) = \\bigcup_{i=1}^{gen} R^i_{comp}(hu)$, $R(hu, products, gen)$ analogously and
    $R(hu, both, gen)$ their union. Paths only go in one direction, so siblings are never part of a lineage
    (see `graph.lineage_graph` for showing them).

    Args:
        relations: The lineage relations R (`lineage_relations`).
        hu: The handling unit.
        direction: `components`, `products` or `both` (default).
        gen: Number of generations per direction, a natural number or `math.inf` (default: all).

    Returns:
        DataFrame with the columns parent, child, event, direction and generation, sorted by direction,
        generation, event, parent, child.
    """
    if direction not in ("components", "products", "both"):
        raise ValueError(f"direction must be 'components', 'products' or 'both', not {direction!r}")
    parts = ["components", "products"] if direction == "both" else [direction]
    out = pl.concat([generations(relations, hu, d, gen) for d in parts])
    return out.sort("direction", "generation", "event", "parent", "child")
