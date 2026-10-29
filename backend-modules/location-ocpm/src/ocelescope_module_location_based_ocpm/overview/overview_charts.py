"""Overview charts (concept section "Overview charts"): three bar charts and a heatmap.

Every chart counts units: hu-event relations ("relations") or agreeing events ("events").
Step 1 (`relation_units`, `event_units`) gives every unit its values (activity, object type,
location, movement status); step 2 (`bar_chart`, `heatmap`) aggregates the units of one chart.
Under a page filter, relations are the passing ones and events the kept ones; event properties
(agreement, eloc) always come from the whole event.
"""

from typing import Literal

import polars as pl
from pydantic import BaseModel

from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.derivation.pipeline import Derivation
from ocelescope_module_location_based_ocpm.overview.filters import PageFilter, passing_relations

#: Label of a missing value (e.g. loc = ⊥): a grey "–" bar, segment or row.
MISSING = "–"
#: Label of the segment that sums the values without a colour of their own, and of the bar
#: that sums the bars beyond the top 10.
OTHER = "other"
#: Object type of an event whose handling units have several object types (events mode).
SEVERAL_TYPES = "[several types]"
#: Movement status values, in display order.
MOVED_KNOWN = "moved, origin known"
MOVED_UNKNOWN = "moved, origin unknown (⊥)"
NOT_MOVED = "not moved"

#: Bars per chart and values per heatmap axis.
SHOWN = 10
#: Largest share of a shown bar that may be grey "other".
MAX_OTHER_SHARE = 0.05
#: Most colours per chart.
MAX_COLOURS = 50

Measure = Literal["events", "relations"]
End = Literal["top", "bottom"]
ChartName = Literal["activities", "locations", "movements"]
By = Literal["none", "activity", "object_type", "location", "movement_status"]
Mode = Literal["frequent", "locations"]
EventSet = Literal["all", "movements", "transformations"]


def relation_units(derivation: Derivation, page_filter: PageFilter) -> pl.DataFrame:
    """Step 1 for relations: every passing hu-event relation with its values.

    Args:
        derivation: The current derivation.
        page_filter: The filter bar's state.

    Returns:
        pl.DataFrame: Columns event, activity, object_type, location (loc at the selected
        level, "–" if ⊥), movement_status (movement events only, else "–"), moved (bool),
        is_movement, is_transformation.
    """
    moved = pl.col("ploc").is_null() | (pl.col("ploc") != pl.col("loc"))
    status = (
        pl.when(~pl.col(c.IS_MOVEMENT) | pl.col("loc").is_null())
        .then(pl.lit(MISSING))
        .when(pl.col("ploc").is_null())
        .then(pl.lit(MOVED_UNKNOWN))
        .when(pl.col("ploc") != pl.col("loc"))
        .then(pl.lit(MOVED_KNOWN))
        .otherwise(pl.lit(NOT_MOVED))
    )
    return passing_relations(derivation, page_filter).select(
        c.EVENT,
        c.ACTIVITY,
        c.OBJECT_TYPE,
        pl.col("loc").fill_null(MISSING).alias("location"),
        status.alias("movement_status"),
        (pl.col(c.IS_MOVEMENT) & pl.col("loc").is_not_null() & moved).alias("moved"),
        c.IS_MOVEMENT,
        c.IS_TRANSFORMATION,
    )


def event_units(derivation: Derivation, page_filter: PageFilter) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Step 1 for events: every kept agreeing event with its values, and the left-out ones.

    An agreeing event counts once, under the common value of its handling units: its agreed
    location eloc ("–" if no handling unit is located) and its object type ("[several types]"
    if its handling units have different object types).

    Args:
        derivation: The current derivation.
        page_filter: The filter bar's state.

    Returns:
        tuple[pl.DataFrame, pl.DataFrame]: The agreeing events (columns event, activity,
        object_type, location, is_movement, is_transformation) and the not agreeing kept
        events (same columns, location "–").
    """
    kept = passing_relations(derivation, page_filter).select(c.EVENT).unique()
    types = derivation.relations.group_by(c.EVENT).agg(
        pl.when(pl.col(c.OBJECT_TYPE).n_unique() == 1)
        .then(pl.col(c.OBJECT_TYPE).first())
        .otherwise(pl.lit(SEVERAL_TYPES))
        .alias(c.OBJECT_TYPE)
    )
    events = (
        derivation.event_locations[derivation.level]
        .join(kept, on=c.EVENT, how="semi")
        .join(derivation.events.select(c.EVENT, c.ACTIVITY, c.IS_MOVEMENT, c.IS_TRANSFORMATION), on=c.EVENT)
        .join(types, on=c.EVENT, how="left")
        .select(
            c.EVENT,
            c.ACTIVITY,
            c.OBJECT_TYPE,
            pl.col("eloc").fill_null(MISSING).alias("location"),
            c.IS_MOVEMENT,
            c.IS_TRANSFORMATION,
            "agreeing",
        )
    )
    return events.filter(pl.col("agreeing")).drop("agreeing"), events.filter(~pl.col("agreeing")).drop("agreeing")


class BarSegment(BaseModel):
    """One coloured segment of a bar: a value of the "by" dimension and its count."""

    value: str
    count: int


class Bar(BaseModel):
    """One bar.

    Attributes:
        label: The bar's value (e.g. the activity); "–" for a missing value.
        count: Bar height (units, or distinct locations in "most locations" mode).
        rank: The number the bar is ranked by (equals count except for movement activities,
            ranked by moved relations).
        segments: Segments by the "by" dimension: coloured values in colour order, then
            "other", then "–"; empty for by = none.
        left_out: Not agreeing events of the bar's activity (events mode, Activities chart).
        locations: Distinct locations ("most locations" mode), for the hover.
        bars: Number of summed bars (only for the "other" bar).
    """

    label: str
    count: int
    rank: int
    segments: list[BarSegment] = []
    left_out: int = 0
    locations: list[str] = []
    bars: int = 1


class BarChart(BaseModel):
    """One bar chart, ready to draw.

    Attributes:
        bars: Shown bars, largest first.
        other: Sum of the bars beyond the shown ones (top 10 only); None if there are none.
        colours: Segment values with a colour of their own, in colour order (largest first).
        left_out: Not agreeing kept events left out of the whole chart (events mode).
        level: The selected level.
    """

    bars: list[Bar]
    other: Bar | None
    colours: list[str]
    left_out: int
    level: int


def chosen(totals: pl.DataFrame, end: End, n: int = SHOWN) -> pl.DataFrame:
    """The top or bottom `n` rows by rank, largest first (ties alphabetical by label).

    Args:
        totals: Columns label and rank.
        end: "top" (largest) or "bottom" (smallest).
        n: Number of rows.

    Returns:
        pl.DataFrame: The chosen rows, largest first.
    """
    ascending = end == "bottom"
    picked = totals.sort(["rank", "label"], descending=[not ascending, False]).head(n)
    return picked.sort(["rank", "label"], descending=[True, False])


def colour_values(segments: pl.DataFrame, max_share: float = MAX_OTHER_SHARE, cap: int = MAX_COLOURS) -> list[str]:
    """Segment values that get a colour of their own, in colour order.

    Each shown bar gets enough of its largest values that at most `max_share` of it remains for
    grey "other"; missing values ("–") get no colour and do not count. The chosen values are
    ranked by their total over the shown bars (largest first, ties alphabetical) and capped.

    Args:
        segments: Columns label (bar), value, count; only shown bars.
        max_share: Largest share of a bar that may be "other".
        cap: Most colours.

    Returns:
        list[str]: The values, largest total first.
    """
    present = segments.filter(pl.col("value") != MISSING)
    if present.is_empty():
        return []
    needed = (
        present.sort(["label", "count", "value"], descending=[False, True, False])
        .with_columns(
            (pl.col("count").sum().over("label") - pl.col("count").cum_sum().over("label")).alias("after"),
            pl.col("count").sum().over("label").alias("bar"),
        )
        # A value is needed if the remainder before it is still above the allowed share.
        .filter((pl.col("after") + pl.col("count")) > max_share * pl.col("bar"))
        .select("value")
        .unique()
    )
    ranked = (
        present.join(needed, on="value", how="semi")
        .group_by("value")
        .agg(pl.col("count").sum())
        .sort(["count", "value"], descending=[True, False])
    )
    return ranked["value"].head(cap).to_list()


def _segments(segments: pl.DataFrame, colours: list[str]) -> dict[str, list[BarSegment]]:
    """Segments per bar: coloured values in colour order, then "other", then "–"."""
    order = {v: i for i, v in enumerate(colours)} | {OTHER: len(colours), MISSING: len(colours) + 1}
    folded = (
        segments.with_columns(
            pl.when(pl.col("value").is_in(colours) | (pl.col("value") == MISSING))
            .then(pl.col("value"))
            .otherwise(pl.lit(OTHER))
            .alias("value")
        )
        .group_by("label", "value")
        .agg(pl.col("count").sum())
    )
    result: dict[str, list[BarSegment]] = {}
    for label, value, count in sorted(folded.rows(), key=lambda r: (r[0], order[r[1]])):
        result.setdefault(label, []).append(BarSegment(value=value, count=count))
    return result


def bar_chart(
    units: pl.DataFrame,
    bar: str,
    by: str | None,
    end: End,
    count: pl.Expr | None = None,
    rank: pl.Expr | None = None,
) -> tuple[list[Bar], Bar | None, list[str]]:
    """Step 2: aggregate units into bars, segments and colours (generic for every bar chart).

    Args:
        units: One row per unit, with the columns `bar` and `by`.
        bar: Column giving the bar.
        by: Column giving the segment; None for plain bars.
        end: Top or bottom `SHOWN` bars; with top, the rest is summed into an "other" bar.
        count: Aggregation giving a bar's (and segment's) height; default: number of units.
        rank: Aggregation the bars are ranked by; default: their height.

    Returns:
        tuple[list[Bar], Bar | None, list[str]]: Shown bars (largest first, with segments), the
        "other" bar and the colour order of the segment values.
    """
    count = pl.len() if count is None else count
    rank = count if rank is None else rank
    units = units.with_columns(pl.col(bar).alias("label"))
    totals = units.group_by("label").agg(count.alias("count"), rank.alias("rank"))
    shown = chosen(totals, end)
    rest = totals.join(shown, on="label", how="anti")
    other = (
        Bar(label=OTHER, count=int(rest["count"].sum()), rank=int(rest["rank"].sum()), bars=rest.height)
        if end == "top" and rest.height
        else None
    )
    colours: list[str] = []
    per_bar: dict[str, list[BarSegment]] = {}
    if by is not None:
        segments = (
            units.join(shown.select("label"), on="label", how="semi")
            .group_by("label", pl.col(by).alias("value"))
            .agg(count.alias("count"))
        )
        colours = colour_values(segments)
        per_bar = _segments(segments, colours)
    bars = [
        Bar(label=label, count=n, rank=r, segments=per_bar.get(label, []))
        for label, n, r in shown.select("label", "count", "rank").rows()
    ]
    return bars, other, colours


#: Column of each "by" value.
BY_COLUMN: dict[str, str | None] = {
    "none": None,
    "activity": c.ACTIVITY,
    "object_type": c.OBJECT_TYPE,
    "location": "location",
    "movement_status": "movement_status",
}


def overview_bar_chart(
    derivation: Derivation,
    page_filter: PageFilter | None = None,
    chart: ChartName = "activities",
    measure: Measure = "relations",
    by: By = "none",
    mode: Mode = "frequent",
    end: End = "top",
) -> BarChart:
    """One of the three overview bar charts.

    Args:
        derivation: The current derivation.
        page_filter: The filter bar's state; None counts the whole log.
        chart: "activities", "locations" or "movements" (movement activities).
        measure: Count hu-event relations or agreeing events (Activities and Locations only;
            Movement activities always count relations).
        by: Secondary dimension splitting each bar.
        mode: Activities only: "frequent" (bar = units) or "locations" (bar = distinct
            locations ≠ ⊥ of the activity, counted over the relations in both measures).
        end: Top or bottom 10 bars.

    Returns:
        BarChart: The chart.
    """
    page_filter = page_filter or PageFilter()
    column = BY_COLUMN[by]
    left_out = pl.DataFrame()
    if chart == "movements":
        units = relation_units(derivation, page_filter).filter(pl.col(c.IS_MOVEMENT))
        bars, other, colours = bar_chart(units, c.ACTIVITY, column, end, rank=pl.col("moved").sum())
    elif chart == "activities" and mode == "locations":
        units = relation_units(derivation, page_filter).filter(pl.col("location") != MISSING)
        bars, other, colours = bar_chart(units, c.ACTIVITY, column, end, count=pl.col("location").n_unique())
        located = units.group_by(c.ACTIVITY).agg(pl.col("location").unique().sort())
        names = dict(located.rows())
        for b in bars:
            b.locations = names.get(b.label, [])
    else:
        if measure == "events":
            units, left_out = event_units(derivation, page_filter)
        else:
            units = relation_units(derivation, page_filter)
        bar = c.ACTIVITY if chart == "activities" else "location"
        bars, other, colours = bar_chart(units, bar, column, end)
    if chart == "activities" and not left_out.is_empty():
        per_activity = dict(left_out.group_by(c.ACTIVITY).len().rows())
        for b in bars:
            b.left_out = per_activity.get(b.label, 0)
    return BarChart(bars=bars, other=other, colours=colours, left_out=left_out.height, level=derivation.level)


class Heatmap(BaseModel):
    """The location × activity heatmap.

    Attributes:
        rows: Locations (largest first; "–" last if shown).
        columns: Activities (largest first).
        cells: cells[i][j] = units at rows[i] and columns[j] (0 if none).
        left_out: Not agreeing kept events left out (events mode).
        level: The selected level.
    """

    rows: list[str]
    columns: list[str]
    cells: list[list[int]]
    left_out: int
    level: int


def heatmap(
    derivation: Derivation,
    page_filter: PageFilter | None = None,
    measure: Measure = "relations",
    end: End = "top",
    events: EventSet = "all",
) -> Heatmap:
    """The location × activity heatmap: 10 values per axis, no "other" row or column.

    Args:
        derivation: The current derivation.
        page_filter: The filter bar's state; None counts the whole log.
        measure: Count hu-event relations or agreeing events.
        end: Top or bottom 10 locations and activities (each ranked by its total).
        events: Keep all units, only those of movement events or of transformation events.

    Returns:
        Heatmap: The heatmap.
    """
    page_filter = page_filter or PageFilter()
    if measure == "events":
        units, left_out = event_units(derivation, page_filter)
    else:
        units, left_out = relation_units(derivation, page_filter), pl.DataFrame()
    if events != "all":
        keep = pl.col(c.IS_MOVEMENT if events == "movements" else c.IS_TRANSFORMATION)
        units = units.filter(keep)
        left_out = left_out.filter(keep) if not left_out.is_empty() else left_out

    def axis(column: str) -> list[str]:
        totals = units.group_by(pl.col(column).alias("label")).agg(pl.len().alias("rank"))
        labels = chosen(totals, end)["label"].to_list()
        return [v for v in labels if v != MISSING] + [v for v in labels if v == MISSING]

    rows, columns = axis("location"), axis(c.ACTIVITY)
    counts = {(loc, act): n for loc, act, n in units.group_by("location", c.ACTIVITY).len().rows()}
    cells = [[counts.get((r, col), 0) for col in columns] for r in rows]
    return Heatmap(rows=rows, columns=columns, cells=cells, left_out=left_out.height, level=derivation.level)
