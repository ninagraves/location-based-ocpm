"""Charts of the transformations page (as in the playground): transformation activities, transformation types,
transformation locations and unique counts.

Every chart counts kept transformation events (`events.filter_events`) and uses the generic step 2 of the overview
charts (`overview.overview_charts.bar_chart`): top or bottom 10 bars, segments by a second dimension, colours per
chart. Bars beyond the shown ones are not drawn (the subtitle says how many).
Locations: the distinct known locations of an event's handling units after the event (loc at the selected level,
hat-hl in high-level mode); an event at several locations counts once at each, an event without any under "–".
"""

from typing import Literal

import polars as pl

from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.overview.overview_charts import MISSING, BarChart, End, bar_chart
from ocelescope_module_location_based_ocpm.transformations.events import KIND_LABELS

TransformationChart = Literal["activities", "transformation_types", "locations", "diversity"]
TransformationBy = Literal["none", "kind", "activity", "transformation_type", "location"]
DiversityPer = Literal["activity", "transformation_type"]

#: Column giving the bar of each chart (the diversity chart takes `per`).
BAR_COLUMN: dict[str, str] = {
    "activities": c.ACTIVITY,
    "transformation_types": "transformation_type",
    "locations": "location",
}
#: Column of each "by" value.
BY_COLUMN: dict[str, str | None] = {
    "none": None,
    "kind": "kind_label",
    "activity": c.ACTIVITY,
    "transformation_type": "transformation_type",
    "location": "location",
}


def chart_units(table: pl.DataFrame, with_locations: bool) -> pl.DataFrame:
    """The units of a chart: one row per kept event, or per (event, location) if a location is involved.

    Args:
        table: Kept transformation events (`events.filter_events`).
        with_locations: True if the bar or the segments are locations.

    Returns:
        pl.DataFrame: The events with the column kind_label (readable kind) and, with locations, one row per
        location in a column location ("–" for an event without a known location).
    """
    units = table.with_columns(pl.col("kind").replace_strict(KIND_LABELS).alias("kind_label"))
    if not with_locations:
        return units
    return units.explode("locations").with_columns(pl.col("locations").fill_null(MISSING).alias("location"))


def transformation_bar_chart(
    table: pl.DataFrame,
    chart: TransformationChart = "activities",
    by: TransformationBy = "none",
    per: DiversityPer = "activity",
    end: End = "top",
    level: int = 0,
) -> BarChart:
    """One bar chart of the transformations page.

    Args:
        table: Kept transformation events (`events.filter_events`, with locations).
        chart: "activities" (events per activity), "transformation_types" (events per transformation type),
            "locations" (events per location) or "diversity" (distinct transformation types per activity, or
            distinct activities per transformation type, see `per`).
        by: Segments of the bars (ignored by the diversity chart); a value equal to the bar's dimension draws
            plain bars.
        per: Bars of the diversity chart.
        end: Top or bottom 10 bars.
        level: The selected level (passed through for the frontend).

    Returns:
        BarChart: The chart (bars, the summed rest as `other`, colour order of the segments).

    Example (running example): activities by kind gives three bars of 1 event each, "cast slab" with the segment
    "production only", "cut" and "roll" with "both".
    """
    if chart == "diversity":
        bar = per
        counted = "transformation_type" if per == c.ACTIVITY else c.ACTIVITY
        units = chart_units(table, with_locations=False)
        bars, other, colours = bar_chart(units, bar, None, end, count=pl.col(counted).n_unique())
    else:
        bar = BAR_COLUMN[chart]
        column = BY_COLUMN[by]
        column = None if column == bar else column
        units = chart_units(table, with_locations="location" in (bar, column))
        bars, other, colours = bar_chart(units, bar, column, end, count=pl.col(c.EVENT).n_unique())
    return BarChart(bars=bars, other=other, colours=colours, left_out=0, level=level)
