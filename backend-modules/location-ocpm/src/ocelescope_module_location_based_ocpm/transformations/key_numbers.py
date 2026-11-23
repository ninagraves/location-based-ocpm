"""Key numbers of the transformations page (as in the playground, agreed 2026-10-19), plus the number of recipes.

All numbers count the transformation events kept by the page filters (`events.filter_events`).
"""

import polars as pl
from pydantic import BaseModel

from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.lineage.relations import CONSUMED, PRODUCED
from ocelescope_module_location_based_ocpm.transformations.events import KINDS


class Count(BaseModel):
    """A value with a count (kind split, filter options)."""

    name: str
    count: int


class TransformationKeyNumbers(BaseModel):
    """The key number tiles.

    Attributes:
        transformation_events: |T_f|, the kept transformation events.
        transformations: Consumed handling units, plus handling units produced at events without consumption
            (welding two coils into one counts 2).
        activities: Distinct activities of the kept events.
        transformation_types: Distinct transformation types (input → output).
        recipes: Distinct recipes (activity, input, output).
        lineage_relations: Sum over the kept events of |cons(e)| · |prod(e)|.
        kinds: Kept events per kind, in the order both, consumption only, production only.
        handling_units: Handling units with at least one event.
        produced_handling_units: Of those, handling units produced at a kept event.
        consumed_handling_units: Of those, handling units consumed at a kept event.
    """

    transformation_events: int
    transformations: int
    activities: int
    transformation_types: int
    recipes: int
    lineage_relations: int
    kinds: list[Count]
    handling_units: int
    produced_handling_units: int
    consumed_handling_units: int


def transformation_count(table: pl.DataFrame) -> int:
    """Consumed handling units plus handling units produced at events without consumption.

    Args:
        table: Transformation events (`events.transformation_events`, possibly filtered).

    Returns:
        int: The number of transformations; running example: 2 consumed (s1 at e3, c2 at e15) + 1 (s1 at e1) = 3.
    """
    return int(table["n_consumed"].sum() + table.filter(pl.col("n_consumed") == 0)["n_produced"].sum())


def key_numbers(table: pl.DataFrame, roles: pl.DataFrame, handling_units: int) -> TransformationKeyNumbers:
    """The key numbers of a set of transformation events.

    Args:
        table: The kept transformation events (`events.filter_events`).
        roles: Transformation roles (columns event, hu, role).
        handling_units: Number of handling units with at least one event (the denominator of the shares).

    Returns:
        TransformationKeyNumbers: The tiles' values.
    """
    kept_roles = roles.join(table.select(c.EVENT), on=c.EVENT, how="semi")
    per_kind = dict(table.group_by("kind").len().rows())
    return TransformationKeyNumbers(
        transformation_events=table.height,
        transformations=transformation_count(table),
        activities=table[c.ACTIVITY].n_unique(),
        transformation_types=table["transformation_type"].n_unique(),
        recipes=table["recipe"].n_unique(),
        lineage_relations=int((table["n_consumed"] * table["n_produced"]).sum()),
        kinds=[Count(name=kind, count=per_kind.get(kind, 0)) for kind in KINDS],
        handling_units=handling_units,
        produced_handling_units=kept_roles.filter(pl.col("role") == PRODUCED)[c.HU].n_unique(),
        consumed_handling_units=kept_roles.filter(pl.col("role") == CONSUMED)[c.HU].n_unique(),
    )


def type_counts(table: pl.DataFrame, column: str) -> list[Count]:
    """Number of events per object type of a list column, most frequent first (filter options).

    Args:
        table: Transformation events.
        column: "consumed_types" or "produced_types".

    Returns:
        list[Count]: One entry per object type (ties alphabetical).
    """
    counted = (
        table.select(pl.col(column).explode().alias("name"))
        .drop_nulls()
        .group_by("name")
        .agg(pl.len().alias("count"))
        .sort(["count", "name"], descending=[True, False])
    )
    return [Count(name=n, count=k) for n, k in counted.rows()]
