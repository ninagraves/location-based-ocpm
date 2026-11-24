"""Transformation type graph (concept: `Lineage (DRAFT).md`, section "Transformation Type Level Model").

For every transformation event $e$ we know its activity, its input $in(e)$ and its output $out(e)$ (multisets of
object types). A recipe is $\\rho = (act(e), in(e), out(e))$ and $freq(\\rho)$ the number of events with it.
The graph is bipartite: object types (ellipses) and recipes (rectangles), an arc object type → recipe for every
type of the input and recipe → object type for every type of the output, weighted with the quantity.

Steps:
1. `event_sides`: one row per (event, side, object type) with the quantity.
2. `recipe_keys`: the recipe of every event, "exact" (quantities are part of the recipe, as in the concept) or
   "sets" (quantities ignored: recipes that differ only in quantities are merged; arcs then carry min and max).
3. `recipe_table` and `recipe_arcs`: frequency per recipe, and per arc the quantity (min, max) and the handling units
   that flowed along it over all events of the recipe (frequency · quantity in exact mode).
4. `min_frequency`: the frequency slider. Recipes are ranked by frequency; the slider value is the share of
   transformation events the shown recipes must cover. The most frequent recipes are taken until they cover it, and
   every recipe as frequent as the last one taken is shown too, so the slider amounts to a minimum frequency.
5. `type_graph`: the graph of the shown recipes.

Additionally, `type_lifecycles` gives per object type the handling units with a full lifecycle (produced and finally
consumed in the log, lifecycle class "both" of the HU profile) and the quartiles of their lifespans
$last(hu) - first(hu)$ (the lifetime from production to final consumption); the ellipses show them (Nina 2026-11-24).
"""

from typing import Literal

import polars as pl
from pydantic import BaseModel

from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.lineage.relations import CONSUMED, PRODUCED
from ocelescope_module_location_based_ocpm.transformations.events import ARROW, EMPTY, PLUS, RECIPE_SEPARATOR

Quantities = Literal["exact", "sets"]

#: Default share of transformation events covered by the shown recipes.
DEFAULT_COVERAGE = 0.8
#: Prefixes of the node ids, so that an object type and a recipe never share an id.
TYPE_NODE = "type:"
RECIPE_NODE = "recipe:"


def event_sides(table: pl.DataFrame) -> pl.DataFrame:
    """Step 1: one row per (event, side, object type) with the number of handling units.

    Args:
        table: Kept transformation events (`events.filter_events`).

    Returns:
        pl.DataFrame: Columns event, role (`consumed` or `produced`), object_type, quantity.

    Example: e3 of the running example gives (e3, consumed, slab, 1) and (e3, produced, coil, 2).
    """
    parts = []
    for role in (CONSUMED, PRODUCED):
        parts.append(
            table.select(
                c.EVENT,
                pl.lit(role).alias("role"),
                pl.col(f"{role}_types").alias(c.OBJECT_TYPE),
                pl.col(f"{role}_quantities").alias("quantity"),
            )
            .explode(c.OBJECT_TYPE, "quantity")
            .drop_nulls(c.OBJECT_TYPE)
        )
    return pl.concat(parts).with_columns(pl.col("quantity").cast(pl.Int64))


def _set_label(column: str) -> pl.Expr:
    """Side label without quantities ("coil + slab"; "∅" if empty)."""
    return pl.when(pl.col(column).list.len() > 0).then(pl.col(column).list.join(PLUS)).otherwise(pl.lit(EMPTY))


def recipe_keys(table: pl.DataFrame, quantities: Quantities = "exact") -> pl.DataFrame:
    """Step 2: the recipe of every event.

    Args:
        table: Kept transformation events.
        quantities: "exact": $\\rho = (act(e), in(e), out(e))$ with multisets (label e.g. "roll: 1 slab → 2 coil");
            "sets": the sets of object types only (label "roll: slab → coil"), so recipes that differ only in
            quantities are merged.

    Returns:
        pl.DataFrame: Columns event, activity, recipe (label, the key), input, output (side labels), kind.
    """
    if quantities == "exact":
        frame = table.select(c.EVENT, c.ACTIVITY, "input", "output", "kind")
    else:
        frame = table.select(
            c.EVENT,
            c.ACTIVITY,
            _set_label("consumed_types").alias("input"),
            _set_label("produced_types").alias("output"),
            "kind",
        )
    return frame.with_columns(
        (pl.col(c.ACTIVITY) + RECIPE_SEPARATOR + pl.col("input") + ARROW + pl.col("output")).alias("recipe")
    )


def recipe_table(keys: pl.DataFrame) -> pl.DataFrame:
    """Step 3a: one row per recipe with its frequency and a stable id.

    Args:
        keys: Output of `recipe_keys`.

    Returns:
        pl.DataFrame: Columns id ("r1", "r2", … by frequency, then label), recipe, activity, input, output, kind,
        frequency (events), sorted by id.
    """
    return (
        keys.group_by("recipe")
        .agg(pl.col(c.ACTIVITY).first(), pl.col("input").first(), pl.col("output").first(), pl.col("kind").first(), pl.len().alias("frequency"))
        .sort(["frequency", "recipe"], descending=[True, False])
        .with_row_index("rank", offset=1)
        .with_columns(pl.format("r{}", pl.col("rank")).alias("id"))
        .select("id", "recipe", c.ACTIVITY, "input", "output", "kind", "frequency")
    )


def recipe_arcs(sides: pl.DataFrame, keys: pl.DataFrame) -> pl.DataFrame:
    """Step 3b: the arcs of every recipe.

    Args:
        sides: Output of `event_sides`.
        keys: Output of `recipe_keys`.

    Returns:
        pl.DataFrame: One row per (recipe, role, object type) with quantity_min, quantity_max (equal in "exact"
        mode) and hus (handling units that flowed along the arc over all events of the recipe), sorted.

    Example (running example): (roll: 1 slab → 2 coil, produced, coil, 2, 2, 2).
    """
    return (
        sides.join(keys.select(c.EVENT, "recipe"), on=c.EVENT)
        .group_by("recipe", "role", c.OBJECT_TYPE)
        .agg(
            pl.col("quantity").min().alias("quantity_min"),
            pl.col("quantity").max().alias("quantity_max"),
            pl.col("quantity").sum().alias("hus"),
        )
        .sort("recipe", "role", c.OBJECT_TYPE)
    )


def min_frequency(frequencies: pl.Series, coverage: float) -> int:
    """Step 4: the smallest frequency of the shown recipes for a slider value.

    Recipes are ranked by frequency (largest first); the most frequent ones are taken until their events make up at
    least `coverage` of all events. The frequency of the last recipe taken is the minimum frequency: all recipes at
    least as frequent are shown (so recipes with equal frequency are never split).

    Args:
        frequencies: Frequency of every recipe.
        coverage: Share of the events to cover, in [0, 1]; 0 shows only the most frequent recipe(s), 1 all.

    Returns:
        int: The minimum frequency; 0 if there are no recipes.

    Example: frequencies 5, 3, 1, 1 (10 events) and coverage 0.8 give 3 (5 + 3 = 8 events); 0.81 gives 1.
    """
    if frequencies.is_empty():
        return 0
    ranked = frequencies.sort(descending=True)
    needed = coverage * ranked.sum()
    covered = ranked.cum_sum()
    reached = (covered >= needed - 1e-9).arg_max()
    return int(ranked[reached if reached is not None else len(ranked) - 1])


class RecipeNode(BaseModel):
    """A recipe (rectangle).

    Attributes:
        node: Node id ("recipe:" + id).
        id: Stable id ("r1" is the most frequent recipe of the kept events).
        recipe: Label, e.g. "roll: 1 slab → 2 coil".
        activity: Its activity.
        input: Input side label.
        output: Output side label.
        kind: "both", "consumption_only" or "production_only".
        frequency: Number of events with this recipe.
        share: Share of the kept transformation events.
    """

    node: str
    id: str
    recipe: str
    activity: str
    input: str
    output: str
    kind: str
    frequency: int
    share: float


class TypeNode(BaseModel):
    """An object type (ellipse).

    Attributes:
        node: Node id ("type:" + object type).
        object_type: The object type.
        consumed: Handling units of this type consumed by the shown recipes.
        produced: Handling units of this type produced by the shown recipes.
        handling_units: Handling units of this type in the log (`type_lifecycles`; 0 without lifecycles).
        full_lifecycle: Of them, those with a full lifecycle (produced and finally consumed in the log).
        lifetime_q1: First quartile of their lifetimes in seconds (null without a full lifecycle).
        lifetime_median: Median of their lifetimes in seconds.
        lifetime_q3: Third quartile of their lifetimes in seconds.
    """

    node: str
    object_type: str
    consumed: int
    produced: int
    handling_units: int = 0
    full_lifecycle: int = 0
    lifetime_q1: float | None = None
    lifetime_median: float | None = None
    lifetime_q3: float | None = None


class TypeArc(BaseModel):
    """An arc: object type → recipe (input) or recipe → object type (output).

    Attributes:
        source: Node id (`TypeNode.node` or `RecipeNode.node`).
        target: Node id.
        role: "consumed" (input arc) or "produced" (output arc).
        object_type: The arc's object type.
        recipe: Id of the arc's recipe.
        quantity_min: Handling units of the type per event of the recipe (smallest).
        quantity_max: The same, largest (equal to quantity_min with exact quantities).
        hus: Handling units that flowed along the arc over all events of the recipe.
    """

    source: str
    target: str
    role: str
    object_type: str
    recipe: str
    quantity_min: int
    quantity_max: int
    hus: int


class TypeGraph(BaseModel):
    """The transformation type graph of the shown recipes.

    Attributes:
        recipes: Shown recipes, most frequent first.
        object_types: Object types with an arc, alphabetical.
        arcs: Arcs of the shown recipes.
        quantities: "exact" or "sets".
        coverage: The slider value.
        min_frequency: Smallest frequency of a shown recipe.
        recipes_total: Recipes of the kept transformation events.
        events_total: Kept transformation events.
        events_shown: Events of the shown recipes.
        frequencies: Frequency of every recipe, largest first (for the slider's marks).
    """

    recipes: list[RecipeNode]
    object_types: list[TypeNode]
    arcs: list[TypeArc]
    quantities: Quantities
    coverage: float
    min_frequency: int
    recipes_total: int
    events_total: int
    events_shown: int
    frequencies: list[int]


def type_lifecycles(profile: pl.DataFrame) -> pl.DataFrame:
    """Handling units with a full lifecycle and the quartiles of their lifetimes, per object type.

    A handling unit has a full lifecycle if it is produced and finally consumed in the log (lifecycle class "both"
    of the HU profile, `instances.profile.transformation_profile`); its lifetime is its lifespan
    $last(hu) - first(hu)$, which then runs from its production to its final consumption. Handling units without a
    full lifecycle are left out of the quartiles, since their lifespan is cut off by the log.
    Quartiles are linearly interpolated (as numpy's default).

    Args:
        profile: The HU profile (`instances.profile.hu_profile`) with the columns object_type, lifecycle and lifespan
            (seconds).

    Returns:
        pl.DataFrame: One row per object type with the columns object_type, handling_units, full_lifecycle,
        lifetime_q1, lifetime_median and lifetime_q3 (null if no handling unit of the type has a full lifecycle).

    Example (running example): coil 5 handling units, 1 with a full lifecycle (c2, 12 h: median, Q1 and Q3 43200 s);
    slab 1 handling unit, 1 with a full lifecycle (s1, 2 h).
    """
    full = pl.col("lifecycle") == "both"
    lifetime = pl.col("lifespan").filter(full)
    return (
        profile.group_by(c.OBJECT_TYPE)
        .agg(
            pl.len().alias("handling_units"),
            full.sum().alias("full_lifecycle"),
            lifetime.quantile(0.25, interpolation="linear").alias("lifetime_q1"),
            lifetime.median().alias("lifetime_median"),
            lifetime.quantile(0.75, interpolation="linear").alias("lifetime_q3"),
        )
        .with_columns(pl.col("handling_units", "full_lifecycle").cast(pl.Int64))
        .sort(c.OBJECT_TYPE)
    )


def type_graph(
    table: pl.DataFrame,
    coverage: float = DEFAULT_COVERAGE,
    quantities: Quantities = "exact",
    lifecycles: pl.DataFrame | None = None,
) -> TypeGraph:
    """Step 5: the transformation type graph of the kept transformation events.

    Args:
        table: Kept transformation events (`events.filter_events`).
        coverage: Slider value, share of the events the shown recipes cover (`min_frequency`).
        quantities: "exact" or "sets" (`recipe_keys`).
        lifecycles: Optional output of `type_lifecycles` (of the whole log, so independent of the page filters and
            the slider); adds the full lifecycles and lifetimes to the object types.

    Returns:
        TypeGraph: Nodes and arcs of the recipes with at least `min_frequency` events.

    Example (running example, coverage 1): recipes r1 "cast slab: ∅ → 1 slab", r2 "cut: 1 coil → 1 coil",
    r3 "roll: 1 slab → 2 coil" (1 event each), object types coil and slab, arcs r1 → slab (1), coil → r2 (1),
    r2 → coil (1), slab → r3 (1), r3 → coil (2) (node ids with the prefixes "recipe:" and "type:").
    """
    coverage = min(max(coverage, 0.0), 1.0)
    keys = recipe_keys(table, quantities)
    recipes = recipe_table(keys)
    threshold = min_frequency(recipes["frequency"], coverage)
    shown = recipes.filter(pl.col("frequency") >= threshold)
    arcs = recipe_arcs(event_sides(table), keys).join(shown.select("recipe", "id"), on="recipe")
    types = (
        arcs.group_by(c.OBJECT_TYPE)
        .agg(
            pl.col("hus").filter(pl.col("role") == CONSUMED).sum().alias("consumed"),
            pl.col("hus").filter(pl.col("role") == PRODUCED).sum().alias("produced"),
        )
        .sort(c.OBJECT_TYPE)
    )
    if lifecycles is not None:
        types = types.join(lifecycles, on=c.OBJECT_TYPE, how="left").with_columns(
            pl.col("handling_units", "full_lifecycle").fill_null(0)
        )
    total = table.height
    return TypeGraph(
        recipes=[
            RecipeNode(**r, node=RECIPE_NODE + r["id"], share=r["frequency"] / total) for r in shown.iter_rows(named=True)
        ],
        object_types=[TypeNode(**t, node=TYPE_NODE + t[c.OBJECT_TYPE]) for t in types.iter_rows(named=True)],
        arcs=[
            TypeArc(
                source=TYPE_NODE + a[c.OBJECT_TYPE] if a["role"] == CONSUMED else RECIPE_NODE + a["id"],
                target=RECIPE_NODE + a["id"] if a["role"] == CONSUMED else TYPE_NODE + a[c.OBJECT_TYPE],
                role=a["role"],
                object_type=a[c.OBJECT_TYPE],
                recipe=a["id"],
                quantity_min=a["quantity_min"],
                quantity_max=a["quantity_max"],
                hus=a["hus"],
            )
            for a in arcs.sort("id", "role", c.OBJECT_TYPE).iter_rows(named=True)
        ],
        quantities=quantities,
        coverage=coverage,
        min_frequency=threshold,
        recipes_total=recipes.height,
        events_total=total,
        events_shown=int(shown["frequency"].sum()),
        frequencies=recipes["frequency"].to_list(),
    )
