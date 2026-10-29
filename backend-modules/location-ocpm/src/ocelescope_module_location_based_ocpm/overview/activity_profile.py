"""Activity profile (concept section "Activity Profile").

One row per activity with kept events. Events, role, handling units per event, located and agreed
describe the kept events as a whole; typical location counts passing relations only; share at location appears only with a location filter (concept section "Filter Effect").
"""

import polars as pl
from pydantic import BaseModel

from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.derivation.agreement import FULLY, PARTIALLY, UNLOCATED
from ocelescope_module_location_based_ocpm.derivation.pipeline import Derivation
from ocelescope_module_location_based_ocpm.overview.filters import PageFilter, passing_relations
from ocelescope_module_location_based_ocpm.overview.key_numbers import TypeCount

#: Number of locations in an expanded row.
TOP = 5


class Typical(BaseModel):
    """The most frequent value of a column among an activity's relations.

    Attributes:
        value: The most frequent value; ties broken alphabetically.
        count: Relations with that value.
        total: Relations counted (the denominator of the share).
        distinct: Number of distinct values.
        tied: Number of values sharing the highest count (1 if there is no tie).
    """

    value: str
    count: int
    total: int
    distinct: int
    tied: int


class ValueShare(BaseModel):
    """A value with its count (the share is count / total of the list's owner)."""

    value: str
    count: int


class ActivityRow(BaseModel):
    """One row of the activity profile.

    Attributes:
        activity: The activity.
        events: Kept events of the activity.
        share_at_location: events / all kept events; None without a location filter.
        movement_share: Share of the events that are movement events.
        transformation_share: Share that are transformation events; None if no transformation
            events are configured.
        hus_median: Median number of handling units per event (whole event).
        hus_max: Maximum number of handling units per event.
        object_types: Object types of the events' handling units, counted as hu-event relations.
        typical_location: Most frequent loc over the passing relations with loc ≠ ⊥; None if
            there is none ("unknown").
        top_locations: The `TOP` most frequent such locations (expanded row), largest first.
        provided: Events with a location from the input (e ∈ dom(uloc)).
        fully_located: Fully located events.
        partially_located: Partially located events.
        unlocated: Unlocated events.
        agreed: Agreeing events by the definition (incl. events with < 2 located handling units).
        tested: Events with at least two located handling units.
        tested_agreed: Agreeing events among the tested ones.
    """

    activity: str
    events: int
    share_at_location: float | None
    movement_share: float
    transformation_share: float | None
    hus_median: float
    hus_max: int
    object_types: list[TypeCount]
    typical_location: Typical | None
    top_locations: list[ValueShare]
    provided: int
    fully_located: int
    partially_located: int
    unlocated: int
    agreed: int
    tested: int
    tested_agreed: int


class ActivityProfile(BaseModel):
    """The activity profile.

    Attributes:
        rows: One row per activity with kept events, most events first (ties alphabetical).
        level: The selected level.
        kept_events: All kept events (denominator of the share at location).
        location_filter: True if a location filter is set (the share at location is shown).
    """

    rows: list[ActivityRow]
    level: int
    kept_events: int
    location_filter: bool


def ranked(frame: pl.DataFrame, value: str) -> pl.DataFrame:
    """Count values per activity, ranked by count (descending) and value (alphabetical).

    Args:
        frame: Rows with columns activity and `value` (nulls are dropped).
        value: The column to count.

    Returns:
        pl.DataFrame: Columns activity, value, count, total (per activity), distinct, rank
        (0 = typical value), tied (values with the top count).
    """
    return (
        frame.filter(pl.col(value).is_not_null())
        .group_by(c.ACTIVITY, value)
        .agg(pl.len().alias("count"))
        .rename({value: "value"})
        .sort([c.ACTIVITY, "count", "value"], descending=[False, True, False])
        .with_columns(
            pl.col("count").sum().over(c.ACTIVITY).alias("total"),
            pl.len().over(c.ACTIVITY).alias("distinct"),
            pl.int_range(pl.len()).over(c.ACTIVITY).alias("rank"),
            (pl.col("count") == pl.col("count").max()).sum().over(c.ACTIVITY).alias("tied"),
        )
    )


def _typicals(counted: pl.DataFrame) -> dict[str, Typical]:
    """The typical value per activity from the output of `ranked`."""
    top = counted.filter(pl.col("rank") == 0)
    return {
        row[c.ACTIVITY]: Typical(
            value=str(row["value"]), count=row["count"], total=row["total"], distinct=row["distinct"], tied=row["tied"]
        )
        for row in top.iter_rows(named=True)
    }


def _tops(counted: pl.DataFrame) -> dict[str, list[ValueShare]]:
    """The `TOP` most frequent values per activity from the output of `ranked`."""
    tops: dict[str, list[ValueShare]] = {}
    for row in counted.filter(pl.col("rank") < TOP).iter_rows(named=True):
        tops.setdefault(row[c.ACTIVITY], []).append(ValueShare(value=str(row["value"]), count=row["count"]))
    return tops


def activity_profile(derivation: Derivation, page_filter: PageFilter | None = None) -> ActivityProfile:
    """The activity profile at the selected level under the page filter.

    Args:
        derivation: The current derivation.
        page_filter: The filter bar's state; None or inactive uses the whole log.

    Returns:
        ActivityProfile: Rows most events first, ties alphabetical.
    """
    page_filter = page_filter or PageFilter()
    passing = passing_relations(derivation, page_filter)
    kept = passing.select(c.EVENT).unique()
    events = (
        derivation.event_locations[derivation.level]
        .join(kept, on=c.EVENT, how="semi")
        .join(derivation.events.select(c.EVENT, c.ACTIVITY, c.IS_MOVEMENT, c.IS_TRANSFORMATION, c.ULOC), on=c.EVENT)
    )
    per_activity = (
        events.group_by(c.ACTIVITY)
        .agg(
            pl.len().alias("events"),
            pl.col(c.IS_MOVEMENT).mean().alias("movement_share"),
            pl.col(c.IS_TRANSFORMATION).mean().alias("transformation_share"),
            pl.col("n_relations").median().alias("hus_median"),
            pl.col("n_relations").max().alias("hus_max"),
            pl.col(c.ULOC).is_not_null().sum().alias("provided"),
            (pl.col("located") == FULLY).sum().alias("fully_located"),
            (pl.col("located") == PARTIALLY).sum().alias("partially_located"),
            (pl.col("located") == UNLOCATED).sum().alias("unlocated"),
            pl.col("agreeing").sum().alias("agreed"),
            (pl.col("n_located") >= 2).sum().alias("tested"),
            ((pl.col("n_located") >= 2) & pl.col("agreeing")).sum().alias("tested_agreed"),
        )
        .sort(["events", c.ACTIVITY], descending=[True, False])
    )
    types = (
        derivation.relations.join(kept, on=c.EVENT, how="semi")
        .group_by(c.ACTIVITY, c.OBJECT_TYPE)
        .agg(pl.len().alias("count"))
        .sort([c.ACTIVITY, "count", c.OBJECT_TYPE], descending=[False, True, False])
    )
    object_types: dict[str, list[TypeCount]] = {}
    for activity, object_type, count in types.rows():
        object_types.setdefault(activity, []).append(TypeCount(object_type=object_type, count=count))
    locations = ranked(passing, "loc")
    typical_locations, top_locations = _typicals(locations), _tops(locations)

    location_filter = bool(page_filter.locations or page_filter.exclude_locations)
    with_t = derivation.config.transformation_events is not None
    rows = [
        ActivityRow(
            activity=row[c.ACTIVITY],
            events=row["events"],
            share_at_location=row["events"] / kept.height if location_filter else None,
            movement_share=row["movement_share"],
            transformation_share=row["transformation_share"] if with_t else None,
            hus_median=row["hus_median"],
            hus_max=row["hus_max"],
            object_types=object_types.get(row[c.ACTIVITY], []),
            typical_location=typical_locations.get(row[c.ACTIVITY]),
            top_locations=top_locations.get(row[c.ACTIVITY], []),
            provided=row["provided"],
            fully_located=row["fully_located"],
            partially_located=row["partially_located"],
            unlocated=row["unlocated"],
            agreed=row["agreed"],
            tested=row["tested"],
            tested_agreed=row["tested_agreed"],
        )
        for row in per_activity.iter_rows(named=True)
    ]
    return ActivityProfile(rows=rows, level=derivation.level, kept_events=kept.height, location_filter=location_filter)
