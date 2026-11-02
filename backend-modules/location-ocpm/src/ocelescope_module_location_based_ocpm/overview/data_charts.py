"""Data overview charts (concept section "Data Overview Charts"; changes from `overview/module/Module Overview.md`,
"Update Overview Page", section 5).

Four small charts: the events sunburst (type, locatedness, agreement), the E2HU chart (first
derivation level at which a relation gets a location), the HU chart (locatedness of the
handling units) and the locations sunburst (location type, high-level location). Under a page filter
they count kept events, passing relations and kept handling units; properties always come from the
whole event or trace.
"""

import polars as pl
from pydantic import BaseModel

from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.derivation.locatedness import FULLY, PARTIALLY, UNLOCATED
from ocelescope_module_location_based_ocpm.derivation.pipeline import Derivation
from ocelescope_module_location_based_ocpm.overview import filters as f
from ocelescope_module_location_based_ocpm.overview.filters import PageFilter, event_table, passing_relations

#: Ring values in display order.
LOCATEDNESS = [FULLY, PARTIALLY, UNLOCATED]
#: Roles of an event; its type is the combination of its roles, joined with " · " ("other" if none).
ROLES = ("movement", "transformation", "processing")
ROLE_SEPARATOR = " · "


def _role_combinations() -> list[str]:
    """All event types in display order: combinations with movement first, then with transformation, then
    processing only, then "other"."""
    combos = []
    for mask in (0b100, 0b110, 0b101, 0b111, 0b010, 0b011, 0b001):
        combos.append(ROLE_SEPARATOR.join(role for i, role in enumerate(ROLES) if mask & (0b100 >> i)))
    return [*combos, "other"]


EVENT_TYPES = _role_combinations()
#: Agreement of an event; "agreeing at high level only" only occurs if high-level locations are configured.
AGREEING_HIGH_ONLY = "agreeing at high level only"
AGREEMENT = ["agreeing", AGREEING_HIGH_ONLY, "not agreeing", "not tested"]
#: Location types (a property of a low-level location) in display order.
VEHICLE, STORAGE, BOTH, OTHER_LOCATION = "vehicle", "storage unit", "vehicle and storage unit", "other"
LOCATION_TYPES = [VEHICLE, STORAGE, BOTH, OTHER_LOCATION]
#: Label of relations without a location at any level.
NEVER = "⊥"

#: Filter value a click on a segment adds, per ring value (None: no filter matches it).
EVENT_FILTERS = {
    FULLY: ("activities", f.FULLY_LOCATED_EVENTS),
    PARTIALLY: ("activities", f.PARTIALLY_LOCATED_EVENTS),
    UNLOCATED: ("activities", f.UNLOCATED_EVENTS),
    "movement": ("activities", f.MOVEMENT_EVENTS),
    "transformation": ("activities", f.TRANSFORMATION_EVENTS),
    "processing": ("activities", f.PROCESSING_OPERATIONS),
    "agreeing": ("activities", f.AGREEING_EVENTS),
    "not agreeing": ("activities", f.DISAGREEING_EVENTS),
}
LOCATION_FILTERS = {
    VEHICLE: ("locations", f.VEHICLES),
    STORAGE: ("locations", f.STORAGE_UNITS),
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
        id: Unique path, e.g. "movement/fully located/agreeing".
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
    """The four data overview charts.

    Attributes:
        events: Sunburst segments; counts are (kept) events.
        relations: First level with a location (0-3, "⊥"); counts are (passing) relations.
        handling_units: Locatedness at the selected level; counts are (kept) handling units.
        locations: Locations sunburst counting the locations of L: inner ring location type, outer ring
            high-level location (only if configured).
        location_relations: The same counting (passing) relations by their loc; relations without a location
            are left out.
        unlocated_relations: Number of (passing) relations without a location (left out of `location_relations`).
        has_context: True if vehicles, storage units or high-level locations are configured.
        level: The selected level.
        filtered: True if a page filter is active.
    """

    events: list[Segment]
    relations: list[Segment]
    handling_units: list[Segment]
    locations: list[Segment] = []
    location_relations: list[Segment] = []
    unlocated_relations: int = 0
    has_context: bool = False
    level: int
    filtered: bool


def _filter(values: dict[str, tuple[str, str]], key: str) -> FilterValue | None:
    """The filter value of a ring value, if any."""
    match = values.get(key)
    return FilterValue(filter=match[0], value=match[1]) if match else None


def event_type_expr() -> pl.Expr:
    """The type of an event: the combination of its roles movement (M), transformation (T) and processing (P),
    joined with " · ", e.g. "transformation · processing"; "other" if it has none.

    Returns:
        pl.Expr: Text expression on a frame with is_movement, is_transformation, is_processing.
    """
    flags = [pl.col(c.IS_MOVEMENT), pl.col(c.IS_TRANSFORMATION), pl.col(c.IS_PROCESSING)]
    parts = [pl.when(flag.fill_null(False)).then(pl.lit(role)).otherwise(None) for flag, role in zip(flags, ROLES)]
    joined = pl.concat_str(parts, separator=ROLE_SEPARATOR, ignore_nulls=True)
    return pl.when(joined == "").then(pl.lit("other")).otherwise(joined)


def event_categories(derivation: Derivation, high: bool = False) -> pl.DataFrame:
    """Locatedness, type and agreement of every event at the selected level.

    Args:
        derivation: The current derivation.
        high: True for the agreement under hat-hl (high-level mode of the Overview section).

    Returns:
        pl.DataFrame: Columns event, located, type, agreement. Agreement is "not tested" if
        fewer than two handling units of the event are located (agreeing by definition); with high-level
        locations, an event that only agrees under hat-hl is "agreeing at high level only" (low-level mode only;
        in high-level mode it is "agreeing").
    """
    base = event_table(derivation, high)
    hl_agreeing = event_table(derivation, derivation.has_high_level).select(
        c.EVENT, pl.col("agreeing").alias("hl_agreeing")
    )
    agreement = (
        pl.when(pl.col("n_located") < 2)
        .then(pl.lit("not tested"))
        .when(pl.col("agreeing"))
        .then(pl.lit("agreeing"))
        .when(pl.col("hl_agreeing"))
        .then(pl.lit(AGREEING_HIGH_ONLY))
        .otherwise(pl.lit("not agreeing"))
    )
    return (
        base.join(hl_agreeing, on=c.EVENT, how="left")
        .join(derivation.events.select(c.EVENT, c.IS_MOVEMENT, c.IS_TRANSFORMATION, c.IS_PROCESSING), on=c.EVENT)
        .select(c.EVENT, "located", event_type_expr().alias("type"), agreement.alias("agreement"))
    )


def event_segments(events: pl.DataFrame) -> list[Segment]:
    """Sunburst segments: inner ring type, middle ring locatedness, outer ring agreement.

    Args:
        events: Rows of `event_categories` to count.

    Returns:
        list[Segment]: Non-empty segments, inner ring first, each ring in display order.
    """
    rings = [("type", EVENT_TYPES), ("located", LOCATEDNESS), ("agreement", AGREEMENT)]
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
    """Lowest level k with loc^k ≠ ⊥ per relation, as text ("0" to "3", "⊥" if none).

    Args:
        relations: Relations frame with the columns loc^0 to loc^3.

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


def location_types(derivation: Derivation) -> pl.DataFrame:
    """Location type and high-level location of every location of L.

    Args:
        derivation: The current derivation.

    Returns:
        pl.DataFrame: Columns location, location_type (vehicle, storage unit, vehicle and storage unit, other),
        high_level (agg completed by the identity).
    """
    context = derivation.context
    rows = []
    for location in derivation.locations:
        vehicle, storage = location in context.vehicles, location in context.storage_units
        kind = BOTH if vehicle and storage else VEHICLE if vehicle else STORAGE if storage else OTHER_LOCATION
        rows.append((location, kind, context.agg.get(location, location)))
    return pl.DataFrame(rows, schema={"location": pl.String, "location_type": pl.String, "high_level": pl.String}, orient="row")


def location_segments(counted: pl.DataFrame, with_high_level: bool) -> list[Segment]:
    """Locations sunburst: inner ring location type, outer ring high-level location.

    Args:
        counted: One row per counted item with columns location_type, high_level.
        with_high_level: False leaves out the outer ring (no high-level locations configured).

    Returns:
        list[Segment]: Non-empty segments, inner ring first; types in display order, high-level locations by
        count (largest first, ties alphabetical).
    """
    segments = []
    per_type = counted.group_by("location_type").agg(pl.len().alias("count"))
    for kind in LOCATION_TYPES:
        row = per_type.filter(pl.col("location_type") == kind)
        if row.height:
            segments.append(
                Segment(id=kind, label=kind, parent="", count=row["count"].item(), filter=_filter(LOCATION_FILTERS, kind))
            )
    if with_high_level:
        outer = (
            counted.group_by("location_type", "high_level")
            .agg(pl.len().alias("count"))
            .sort(["count", "high_level"], descending=[True, False])
        )
        for kind in LOCATION_TYPES:
            for _, high_level, count in outer.filter(pl.col("location_type") == kind).rows():
                segments.append(Segment(id=f"{kind}/{high_level}", label=high_level, parent=kind, count=count))
    return segments


def data_charts(derivation: Derivation, page_filter: PageFilter | None = None) -> DataCharts:
    """The four data overview charts, counted over the kept part of the log.

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
    types = location_types(derivation)
    located = passing.filter(pl.col("loc").is_not_null()).join(types, left_on="loc", right_on="location", how="left")
    config = derivation.config
    return DataCharts(
        events=event_segments(kept_events),
        relations=relation_segments(first_levels(relations)),
        handling_units=hu_segments(passing.unique(c.HU)["hu_located"]),
        locations=location_segments(types, derivation.has_high_level),
        location_relations=location_segments(located, derivation.has_high_level),
        unlocated_relations=passing.filter(pl.col("loc").is_null()).height,
        has_context=any(
            option is not None for option in (config.high_level_locations, config.vehicles, config.storage_units)
        ),
        level=derivation.level,
        filtered=page_filter.active,
    )
