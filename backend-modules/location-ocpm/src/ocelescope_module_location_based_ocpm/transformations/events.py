"""Step 1 of the transformations page: one row per transformation event, and the page filters.

Concept: `overview/concepts/Transfromations/Deriving Transformations.md` ($T$, $cons$, $prod$) and
`Lineage (DRAFT).md`, section "Transformation Type Level Model" (inputs, outputs, recipes).
For an event $e \\in T$:
- input $in(e) = [otype(hu) \\mid hu \\in cons(e)]$ and output $out(e) = [otype(hu) \\mid hu \\in prod(e)]$ (multisets),
- transformation type $(in(e), out(e))$, labelled e.g. "1 slab → 2 coil" (per side "count type", types
  alphabetical, joined by " + ", "∅" for an empty side; as in the playground),
- recipe $(act(e), in(e), out(e))$, labelled e.g. "roll: 1 slab → 2 coil",
- kind: "both" ($cons(e) \\neq \\emptyset \\neq prod(e)$), "consumption_only" or "production_only".

The page filters (`TransformationFilter`) select whole events, so a transformation type or recipe is never cut.
"""

from typing import Literal

import polars as pl
from pydantic import BaseModel

from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.lineage.relations import CONSUMED, PRODUCED

#: Label of an empty side of a transformation type (no consumed or no produced handling units).
EMPTY = "∅"
#: Separator of input and output in a transformation type label.
ARROW = " → "
#: Separator of the object types of one side.
PLUS = " + "
#: Separator of activity and transformation type in a recipe label.
RECIPE_SEPARATOR = ": "

Kind = Literal["both", "consumption_only", "production_only"]
KindFilter = Literal["all", "both", "consumption_only", "production_only"]
#: The kinds, in the order they are shown.
KINDS: tuple[Kind, ...] = ("both", "consumption_only", "production_only")
#: Readable names of the kinds (chart segments, profile).
KIND_LABELS: dict[str, str] = {
    "both": "both",
    "consumption_only": "consumption only",
    "production_only": "production only",
}


def typed_roles(roles: pl.DataFrame, handling_units: pl.DataFrame) -> pl.DataFrame:
    """The transformation roles with the object type of each handling unit.

    Args:
        roles: Columns event, hu, role (`consumed` or `produced`), i.e. $cons$ and $prod$ (`Derivation.roles`).
        handling_units: Columns hu, object_type (`Derivation.handling_units`).

    Returns:
        pl.DataFrame: Columns event, hu, role, object_type; roles of unknown handling units are dropped.
    """
    if roles.is_empty():
        return pl.DataFrame(schema={c.EVENT: pl.String, c.HU: pl.String, "role": pl.String, c.OBJECT_TYPE: pl.String})
    return roles.select(c.EVENT, c.HU, "role").join(handling_units.select(c.HU, c.OBJECT_TYPE), on=c.HU, how="inner")


def side_labels(typed: pl.DataFrame) -> pl.DataFrame:
    """Per event and role: the object types with their quantities, and the side's label.

    Args:
        typed: Output of `typed_roles`.

    Returns:
        pl.DataFrame: One row per (event, role) with columns event, role, label (e.g. "1 slab + 2 coil" sorted by
        type: "2 coil + 1 slab"), types (sorted distinct object types), quantities (number of handling units per
        type, in the order of types) and n (number of handling units).

    Example: e3 of the running example consumes s1 and produces c1, c2: (e3, consumed, "1 slab", [slab], [1], 1) and
    (e3, produced, "2 coil", [coil], [2], 2).
    """
    counts = typed.group_by(c.EVENT, "role", c.OBJECT_TYPE).agg(pl.len().alias("quantity"))
    return counts.group_by(c.EVENT, "role").agg(
        pl.format("{} {}", pl.col("quantity"), pl.col(c.OBJECT_TYPE)).sort_by(c.OBJECT_TYPE).str.join(PLUS).alias("label"),
        pl.col(c.OBJECT_TYPE).sort().alias("types"),
        pl.col("quantity").sort_by(c.OBJECT_TYPE).alias("quantities"),
        pl.col("quantity").sum().alias("n"),
    )


def event_locations(relations: pl.DataFrame, location: str) -> pl.DataFrame:
    """The locations of every event: the distinct known locations of its handling units after the event.

    Args:
        relations: hu-event relations with columns event and `location`.
        location: Location column, e.g. "loc^3" (loc at the selected level) or "hl^3" (high-level mode).

    Returns:
        pl.DataFrame: Columns event and locations (sorted list without ⊥; empty if none is known).
    """
    return relations.group_by(c.EVENT).agg(pl.col(location).drop_nulls().unique().sort().alias("locations"))


def transformation_events(
    events: pl.DataFrame,
    roles: pl.DataFrame,
    handling_units: pl.DataFrame,
    relations: pl.DataFrame | None = None,
    location: str | None = None,
) -> pl.DataFrame:
    """One row per transformation event with its input, output, transformation type, recipe and kind.

    Args:
        events: Columns event, activity, is_transformation (`Derivation.events`).
        roles: Transformation roles (`Derivation.roles`).
        handling_units: Columns hu, object_type (`Derivation.handling_units`).
        relations: hu-event relations with the column `location`; None leaves the locations empty.
        location: Location column of `relations` (e.g. `Derivation.loc`).

    Returns:
        pl.DataFrame: Columns event, activity, input, output (side labels, "∅" if empty), consumed_types,
        produced_types (sorted distinct object types), consumed_quantities, produced_quantities (per type),
        n_consumed, n_produced, transformation_type ("input → output"), recipe ("activity: input → output"), kind
        and locations (`event_locations`), sorted by event.
    """
    sides = side_labels(typed_roles(roles, handling_units))

    def side(role: str, prefix: str, label: str) -> pl.DataFrame:
        return sides.filter(pl.col("role") == role).select(
            c.EVENT,
            pl.col("label").alias(label),
            pl.col("types").alias(f"{prefix}_types"),
            pl.col("quantities").alias(f"{prefix}_quantities"),
            pl.col("n").alias(f"n_{prefix}"),
        )

    table = (
        events.filter(pl.col(c.IS_TRANSFORMATION))
        .select(c.EVENT, c.ACTIVITY)
        .join(side(CONSUMED, "consumed", "input"), on=c.EVENT, how="left")
        .join(side(PRODUCED, "produced", "output"), on=c.EVENT, how="left")
        .with_columns(
            pl.col("input").fill_null(EMPTY),
            pl.col("output").fill_null(EMPTY),
            pl.col("n_consumed").fill_null(0).cast(pl.Int64),
            pl.col("n_produced").fill_null(0).cast(pl.Int64),
            *(
                pl.col(f"{prefix}_{part}").fill_null(pl.lit([], dtype=pl.List(dtype)))
                for prefix in ("consumed", "produced")
                for part, dtype in (("types", pl.String), ("quantities", pl.UInt32))
            ),
        )
        .with_columns(
            (pl.col("input") + ARROW + pl.col("output")).alias("transformation_type"),
            pl.when((pl.col("n_consumed") > 0) & (pl.col("n_produced") > 0))
            .then(pl.lit("both"))
            .when(pl.col("n_consumed") > 0)
            .then(pl.lit("consumption_only"))
            .otherwise(pl.lit("production_only"))
            .alias("kind"),
        )
        .with_columns((pl.col(c.ACTIVITY) + RECIPE_SEPARATOR + pl.col("transformation_type")).alias("recipe"))
    )
    if relations is not None and location is not None:
        located = event_locations(relations.join(table.select(c.EVENT), on=c.EVENT, how="semi"), location)
        table = table.join(located, on=c.EVENT, how="left")
    else:
        table = table.with_columns(pl.lit(None, dtype=pl.List(pl.String)).alias("locations"))
    return table.with_columns(pl.col("locations").fill_null(pl.lit([], dtype=pl.List(pl.String)))).sort(c.EVENT)


class TransformationFilter(BaseModel):
    """The page filters of the transformations page; each selects whole transformation events.

    Attributes:
        consumes: Keep events consuming at least one handling unit of one of these object types (empty: any).
        produces: Keep events producing at least one handling unit of one of these object types (empty: any).
        kind: Keep events of this kind ("all": every kind).
    """

    consumes: list[str] = []
    produces: list[str] = []
    kind: KindFilter = "all"

    @property
    def active(self) -> bool:
        """True if any filter is set."""
        return bool(self.consumes or self.produces or self.kind != "all")


def _contains_any(column: str, values: list[str]) -> pl.Expr:
    """True where the list column holds at least one of `values`."""
    return pl.col(column).list.eval(pl.element().is_in(values)).list.any()


def filter_events(table: pl.DataFrame, page_filter: TransformationFilter | None) -> pl.DataFrame:
    """The transformation events kept by the page filters (AND across filters, OR within one filter).

    Args:
        table: Output of `transformation_events`.
        page_filter: The page filters; None keeps everything.

    Returns:
        pl.DataFrame: The kept rows (whole events).

    Example: consumes = [slab] keeps e3 of the running example; kind = production_only keeps e1.
    """
    if page_filter is None or not page_filter.active:
        return table
    condition = pl.lit(True)
    if page_filter.consumes:
        condition &= _contains_any("consumed_types", page_filter.consumes)
    if page_filter.produces:
        condition &= _contains_any("produced_types", page_filter.produces)
    if page_filter.kind != "all":
        condition &= pl.col("kind") == page_filter.kind
    return table.filter(condition)
