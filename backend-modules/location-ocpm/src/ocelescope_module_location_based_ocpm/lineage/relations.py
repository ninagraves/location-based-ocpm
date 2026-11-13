"""Lineage relations R and the per-handling-unit functions of the concept (parents, children, siblings, ...).

Concept: `overview/concepts/Transformations.md`, section "Instance Lineage".
All functions take the transformation roles, i.e. $cons$ and $prod$ as one frame with the columns
`event`, `hu` and `role` (`consumed` or `produced`; e.g. `data/running_example/inputs/transformation_roles.csv`).
A handling unit consumed and produced at the same event has two rows.
"""

from __future__ import annotations

import polars as pl

CONSUMED = "consumed"
PRODUCED = "produced"

FrameLike = pl.DataFrame | pl.LazyFrame


def _lazy(frame: FrameLike) -> pl.LazyFrame:
    """Return `frame` as a LazyFrame."""
    return frame.lazy() if isinstance(frame, pl.DataFrame) else frame


def roles_of(roles: FrameLike, role: str) -> pl.LazyFrame:
    """The (event, hu) pairs with the given role, i.e. $cons$ or $prod$ as relations.

    Args:
        roles: Transformation roles with the columns event, hu and role.
        role: `consumed` (gives $\\set{(e, hu) \\mid hu \\in cons(e)}$) or `produced` ($prod$).

    Returns:
        LazyFrame with the columns event and hu, without duplicates.
    """
    return (
        _lazy(roles)
        .filter(pl.col("role") == role)
        .select(pl.col("event").cast(pl.String), pl.col("hu").cast(pl.String))
        .unique()
    )


def lineage_relations(roles: FrameLike) -> pl.DataFrame:
    """The lineage relations $R = \\set{(hu, hu', e) \\mid e \\in T: hu \\in cons(e), hu' \\in prod(e)}$.

    Every consumed handling unit of an event is paired with every produced handling unit of the same event
    (a join on the event); events with only consumed or only produced handling units give no relation.

    Args:
        roles: Transformation roles with the columns event, hu and role.

    Returns:
        DataFrame with the columns parent ($hu$), child ($hu'$) and event ($e$), sorted by event, parent, child.
    """
    consumed = roles_of(roles, CONSUMED).rename({"hu": "parent"})
    produced = roles_of(roles, PRODUCED).rename({"hu": "child"})
    return (
        consumed.join(produced, on="event", how="inner")
        .select("parent", "child", "event")
        .sort("event", "parent", "child")
        .collect()
    )


def creation_events(roles: FrameLike) -> pl.DataFrame:
    """The creation event $ev_{prod}(hu)$ of every produced handling unit.

    $ev_{prod}$ is a (partial) function under AS-T2 and AS-T4 (every hu is produced in at most one event);
    if the input violates them, a handling unit appears in several rows.

    Args:
        roles: Transformation roles with the columns event, hu and role.

    Returns:
        DataFrame with the columns hu and event, one row per $hu \\in dom(ev_{prod})$, sorted by hu.
    """
    return roles_of(roles, PRODUCED).select("hu", "event").sort("hu", "event").collect()


def consumption_events(roles: FrameLike) -> pl.DataFrame:
    """The consumption events $E_{cons}(hu) = \\set{e \\in T \\mid hu \\in cons(e)}$ as relations.

    Args:
        roles: Transformation roles with the columns event, hu and role.

    Returns:
        DataFrame with the columns hu and event, one row per $e \\in E_{cons}(hu)$, sorted by hu, event;
        handling units that are never consumed have no row ($E_{cons}(hu) = \\emptyset$).
    """
    return roles_of(roles, CONSUMED).select("hu", "event").sort("hu", "event").collect()


def parents(relations: pl.DataFrame) -> pl.DataFrame:
    """The parents $parents(hu) = \\set{hu' \\mid \\exists e: (hu', hu, e) \\in R}$ as relations.

    Args:
        relations: The lineage relations R (`lineage_relations`).

    Returns:
        DataFrame with the columns hu and parent, sorted; hus without parents have no row.
    """
    return relations.select(pl.col("child").alias("hu"), "parent").unique().sort("hu", "parent")


def children(relations: pl.DataFrame) -> pl.DataFrame:
    """The children $children(hu) = \\set{hu' \\mid \\exists e: (hu, hu', e) \\in R}$ as relations.

    Args:
        relations: The lineage relations R (`lineage_relations`).

    Returns:
        DataFrame with the columns hu and child, sorted; hus without children have no row.
    """
    return relations.select(pl.col("parent").alias("hu"), "child").unique().sort("hu", "child")


def siblings(roles: FrameLike) -> pl.DataFrame:
    """The siblings $siblings(hu) = prod(ev_{prod}(hu)) \\setminus \\set{hu}$ as relations.

    Siblings are the handling units produced in the same event (Nina 2026-11-09: not all hus sharing a
    parent); a hu produced alone, or never produced, has no siblings.

    Args:
        roles: Transformation roles with the columns event, hu and role.

    Returns:
        DataFrame with the columns hu, sibling and event (the shared creation event), sorted by hu, sibling.
    """
    produced = roles_of(roles, PRODUCED)
    return (
        produced.join(produced.rename({"hu": "sibling"}), on="event", how="inner")
        .filter(pl.col("hu") != pl.col("sibling"))
        .select("hu", "sibling", "event")
        .sort("hu", "sibling")
        .collect()
    )
