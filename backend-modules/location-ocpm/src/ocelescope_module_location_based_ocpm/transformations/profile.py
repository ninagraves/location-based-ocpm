"""Transformation profile (as in the playground, agreed 2026-10-19): one row per transformation type.

Each row answers "what is this transformation, how often, and by which activities?". Every activity of a
transformation type is one recipe of it, so the unfolded row lists the type's recipes.
"""

import polars as pl
from pydantic import BaseModel

from ocelescope_module_location_based_ocpm.derivation import columns as c

#: Activities listed in an unfolded row.
TOP_ACTIVITIES = 5


class ActivityShare(BaseModel):
    """An activity of a transformation type with its events and share of the type's events."""

    activity: str
    count: int
    share: float


class TransformationTypeRow(BaseModel):
    """One row of the profile.

    Attributes:
        transformation_type: Label "input → output", e.g. "1 slab → 2 coil".
        input: Input side label ("∅" if empty).
        output: Output side label ("∅" if empty).
        kind: "both", "consumption_only" or "production_only".
        events: Kept transformation events of this type.
        transformations: Consumed handling units, plus handling units produced at events without consumption.
        lineage_relations: Sum of |cons(e)| · |prod(e)| over the type's events.
        activity_count: Distinct activities (= recipes) of the type.
        typical_activity: Most frequent activity (ties alphabetical).
        typical_share: Its share of the type's events.
        activities: The `TOP_ACTIVITIES` most frequent activities with count and share.
    """

    transformation_type: str
    input: str
    output: str
    kind: str
    events: int
    transformations: int
    lineage_relations: int
    activity_count: int
    typical_activity: str
    typical_share: float
    activities: list[ActivityShare]


def type_profile(table: pl.DataFrame, n_activities: int = TOP_ACTIVITIES) -> list[TransformationTypeRow]:
    """The profile rows of the kept transformation events, most events first (ties alphabetical).

    Args:
        table: Kept transformation events (`events.filter_events`).
        n_activities: Activities kept per row.

    Returns:
        list[TransformationTypeRow]: One row per transformation type.

    Example (running example): three rows of 1 event each, e.g. "1 slab → 2 coil", kind both, 1 transformation,
    2 lineage relations, typical activity roll (100 %, 1 activity).
    """
    if table.is_empty():
        return []
    key = "transformation_type"
    base = table.group_by(key).agg(
        pl.col("input").first(),
        pl.col("output").first(),
        pl.col("kind").first(),
        pl.len().alias("events"),
        (pl.col("n_consumed").sum() + pl.col("n_produced").filter(pl.col("n_consumed") == 0).sum()).alias("transformations"),
        (pl.col("n_consumed") * pl.col("n_produced")).sum().alias("lineage_relations"),
        pl.col(c.ACTIVITY).n_unique().alias("activity_count"),
    )
    shares = (
        table.group_by(key, c.ACTIVITY)
        .agg(pl.len().alias("count"))
        .with_columns((pl.col("count") / pl.col("count").sum().over(key)).alias("share"))
        .sort(["count", c.ACTIVITY], descending=[True, False])
        .group_by(key, maintain_order=True)
        .agg(pl.struct(c.ACTIVITY, "count", "share").head(n_activities).alias("activities"))
    )
    rows = base.join(shares, on=key).sort(["events", key], descending=[True, False])
    return [
        TransformationTypeRow(
            **{k: v for k, v in r.items() if k != "activities"},
            typical_activity=r["activities"][0][c.ACTIVITY],
            typical_share=r["activities"][0]["share"],
            activities=[ActivityShare(**a) for a in r["activities"]],
        )
        for r in rows.iter_rows(named=True)
    ]
