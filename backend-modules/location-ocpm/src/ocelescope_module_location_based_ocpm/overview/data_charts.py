"""Data overview charts (concept section "Data Overview Charts").

Three small charts: the events sunburst (locatedness, type, agreement), the E2HU chart (first
derivation level at which a relation gets a location) and the HU chart (locatedness of the
handling units). Under a page filter they count kept events, passing relations and kept
handling units; properties always come from the whole event or trace.
"""

import polars as pl
from pydantic import BaseModel

from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.derivation.agreement import FULLY, PARTIALLY, UNLOCATED
from ocelescope_module_location_based_ocpm.derivation.pipeline import Derivation
from ocelescope_module_location_based_ocpm.overview import filters as f
from ocelescope_module_location_based_ocpm.overview.filters import PageFilter, passing_relations

#: Ring values in display order.
LOCATEDNESS = [FULLY, PARTIALLY, UNLOCATED]
EVENT_TYPES = ["movement", "transformation", "movement and transformation", "other"]
AGREEMENT = ["agreeing", "not agreeing", "not tested"]
#: Label of relations without a location at any level.
NEVER = "⊥"

#: Filter value a click on a segment adds, per ring value (None: no filter matches it).
EVENT_FILTERS = {
    FULLY: ("activities", f.FULLY_LOCATED_EVENTS),
    PARTIALLY: ("activities", f.PARTIALLY_LOCATED_EVENTS),
    UNLOCATED: ("activities", f.UNLOCATED_EVENTS),
    "movement": ("activities", f.MOVEMENT_EVENTS),
    "transformation": ("activities", f.TRANSFORMATION_EVENTS),
    "agreeing": ("activities", f.AGREEING_EVENTS),
    "not agreeing": ("activities", f.DISAGREEING_EVENTS),
}
HU_FILTERS = {
    FULLY: ("object_types", f.FULLY_LOCATED_HUS),
    PARTIALLY: ("object_types", f.PARTIALLY_LOCATED_HUS),
    UNLOCATED: ("object_types", f.UNLOCATED_HUS),
}


class FilterValue(BaseModel):
    """A filter value: which filter of the bar (e.g. "activities") and the value to add."""

    filter: str
    value: str


class Segment(BaseModel):
    """One segment of a chart.

    Attributes:
        id: Unique path, e.g. "fully/movement/agreeing".
        label: Shown text, e.g. "agreeing".
        parent: Id of the parent segment ("" for the inner ring and for flat charts).
        count: Events, relations or handling units in the segment.
        filter: Filter value a click adds; None if no filter matches the segment.
    """

    id: str
    label: str
    parent: str
    count: int
    filter: FilterValue | None = None


class DataCharts(BaseModel):
    """The three data overview charts.

    Attributes:
        events: Sunburst segments; counts are (kept) events.
        relations: First level with a location (0-3, "⊥"); counts are (passing) relations.
        handling_units: Locatedness at the selected level; counts are (kept) handling units.
        level: The selected level.
        filtered: True if a page filter is active.
    """

    events: list[Segment]
    relations: list[Segment]
    handling_units: list[Segment]
    level: int
    filtered: bool


def _filter(values: dict[str, tuple[str, str]], key: str) -> FilterValue | None:
    """The filter value of a ring value, if any."""
    match = values.get(key)
    return FilterValue(filter=match[0], value=match[1]) if match else None


def event_categories(derivation: Derivation) -> pl.DataFrame:
    """Locatedness, type and agreement of every event at the selected level.

    Args:
        derivation: The current derivation.

    Returns:
        pl.DataFrame: Columns event, located, type, agreement. Agreement is "not tested" if
        fewer than two handling units of the event are located (agreeing by definition).
    """
    movement, transformation = pl.col(c.IS_MOVEMENT), pl.col(c.IS_TRANSFORMATION)
    kind = (
        pl.when(movement & transformation)
        .then(pl.lit("movement and transformation"))
        .when(movement)
        .then(pl.lit("movement"))
        .when(transformation)
        .then(pl.lit("transformation"))
        .otherwise(pl.lit("other"))
    )
    agreement = (
        pl.when(pl.col("n_located") < 2)
        .then(pl.lit("not tested"))
        .when(pl.col("agreeing"))
        .then(pl.lit("agreeing"))
        .otherwise(pl.lit("not agreeing"))
    )
    return (
        derivation.event_locations[derivation.level]
        .join(derivation.events.select(c.EVENT, c.IS_MOVEMENT, c.IS_TRANSFORMATION), on=c.EVENT)
        .select(c.EVENT, "located", kind.alias("type"), agreement.alias("agreement"))
    )


def event_segments(events: pl.DataFrame) -> list[Segment]:
    """Sunburst segments: inner ring locatedness, middle ring type, outer ring agreement.

    Args:
        events: Rows of `event_categories` to count.

    Returns:
        list[Segment]: Non-empty segments, inner ring first, each ring in display order.
    """
    rings = [("located", LOCATEDNESS), ("type", EVENT_TYPES), ("agreement", AGREEMENT)]
    segments = []
    for depth in range(1, 4):
        keys = [name for name, _ in rings[:depth]]
        counted = events.group_by(keys).agg(pl.len().alias("count"))
        order = [pl.col(name).replace_strict(values, list(range(len(values)))) for name, values in rings[:depth]]
        for row in counted.sort(order).iter_rows(named=True):
            path = [row[name] for name in keys]
            segments.append(
                Segment(
                    id="/".join(path),
                    label=path[-1],
                    parent="/".join(path[:-1]),
                    count=row["count"],
                    filter=_filter(EVENT_FILTERS, path[-1]),
                )
            )
    return segments


def first_levels(relations: pl.DataFrame) -> pl.Series:
    """Lowest level k with loc_k ≠ ⊥ per relation, as text ("0" to "3", "⊥" if none).

    Args:
        relations: Relations frame with the columns loc_0 to loc_3.

    Returns:
        pl.Series: Named "first_level", one value per relation.
    """
    expr = pl.lit(NEVER)
    for k in reversed(c.LEVELS):
        expr = pl.when(pl.col(c.loc(k)).is_not_null()).then(pl.lit(str(k))).otherwise(expr)
    return relations.select(expr.alias("first_level")).to_series()


def relation_segments(first: pl.Series) -> list[Segment]:
    """E2HU segments, one per level (all levels, also empty ones) and ⊥.

    Args:
        first: Output of `first_levels` for the relations to count.

    Returns:
        list[Segment]: Levels 0 to 3, then ⊥.
    """
    counts = dict(first.value_counts().rows())
    labels = [*(str(k) for k in c.LEVELS), NEVER]
    return [Segment(id=label, label=label, parent="", count=counts.get(label, 0)) for label in labels]


def hu_segments(located: pl.Series) -> list[Segment]:
    """HU segments: fully, partially, unlocated (also empty ones).

    Args:
        located: Locatedness of the handling units to count.

    Returns:
        list[Segment]: In display order.
    """
    counts = dict(located.value_counts().rows())
    return [
        Segment(id=v, label=v, parent="", count=counts.get(v, 0), filter=_filter(HU_FILTERS, v)) for v in LOCATEDNESS
    ]


def data_charts(derivation: Derivation, page_filter: PageFilter | None = None) -> DataCharts:
    """The three data overview charts, counted over the kept part of the log.

    Args:
        derivation: The current derivation.
        page_filter: The filter bar's state; None or inactive counts the whole log.

    Returns:
        DataCharts: Segments of the three charts.
    """
    page_filter = page_filter or PageFilter()
    passing = passing_relations(derivation, page_filter)
    kept_events = event_categories(derivation).join(passing.select(c.EVENT).unique(), on=c.EVENT, how="semi")
    relations = derivation.relations.join(passing.select(c.EVENT, c.HU), on=[c.EVENT, c.HU], how="semi")
    return DataCharts(
        events=event_segments(kept_events),
        relations=relation_segments(first_levels(relations)),
        handling_units=hu_segments(passing.unique(c.HU)["hu_located"]),
        level=derivation.level,
        filtered=page_filter.active,
    )
