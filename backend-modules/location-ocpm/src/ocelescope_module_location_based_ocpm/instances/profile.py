"""HU profile: one row per handling unit with general information on its instance.

Documented in `docs/pages/instances.md`, section "HU profile".
All values use the low-level location loc = loc^k of the selected level only (no visits); high-level
locations are hat-hl = agg(loc).

The profile is built in small steps, each a function of its own (lazy polars in, lazy polars out):
1. `ordered_traces`: the relations of every handling unit in `seq` order (time, AS4, event id) with their position.
2. `lifecycle_basics`: object type, events, first and last timestamp, lifespan, movements, processing operations.
3. `location_profile`: distinct low- and high-level locations, first and last location, location changes,
   locatedness.
4. `time_per_location_kind`: time spent on vehicles (V), in storage units (W), at other locations and unlocated.
5. `transformation_profile`: creation event, final consumption, partial consumptions, parents, children,
   siblings and the lifecycle class.
6. `connectedness`: non-transformation events shared with other handling units, their share, and the number of
   handling units they are shared with.
7. `linked_handling_units`: handling units sharing any event (transformation events included, so the lineage counts).
`hu_profile` joins them (also handling units without events); `query_profile` searches, filters by column, sorts
and pages it (`ColumnFilter`, `column_info`); `export_frame` gives the folded table with the shown columns.
`hu_details` gives what an unfolded row of the table shows for one handling unit (names, events, location path).
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Literal

import polars as pl

from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.lineage.relations import (
    consumption_events,
    creation_events,
    lineage_relations,
    siblings,
)
from ocelescope_module_location_based_ocpm.visits.context import LocationContext
from ocelescope_module_location_based_ocpm.visits.order import sort_by_seq

#: Column names of the traces used by the profile (loc and hl of the selected level, renamed).
LOC, HL, POS = "loc", "hl", "pos"
#: Location kinds of `time_per_location_kind`, in this order of precedence (V before W, see F10).
KINDS = ("vehicle", "storage", "other", "unlocated")
#: Lifecycle classes of `transformation_profile`.
LifecycleClass = Literal["both", "produced", "consumed", "open"]
#: Columns of the profile that `query_profile` can sort by (all scalar columns).
SORTABLE = (
    "hu",
    "object_type",
    "lifecycle",
    "n_events",
    "first",
    "last",
    "lifespan",
    "creation_activity",
    "final_consumption_activity",
    "n_partial_consumptions",
    "n_parents",
    "n_children",
    "n_siblings",
    "n_locations",
    "n_high_level_locations",
    "first_location",
    "last_location",
    "n_location_changes",
    "locatedness",
    "n_movements",
    "n_processing",
    "n_shared_events",
    "connectedness",
    "n_co_handled",
    "n_linked",
    *(f"time_{kind}" for kind in KINDS),
)

#: Columns of the profile that can be filtered and exported (the sortable ones).
FILTERABLE = SORTABLE

#: A string column with at most this many distinct values is filtered by picking values, otherwise by text.
MAX_CATEGORIES = 100


def ordered_traces(
    relations: pl.DataFrame | pl.LazyFrame,
    loc: str,
    hl: str,
    processing: Collection[str] | None = None,
) -> pl.LazyFrame:
    """The relations of every handling unit in `seq` order with their trace position.

    Args:
        relations: One row per hu-event relation with the columns event, hu, object_type, time, activity,
            is_movement, is_transformation, is_processing, `loc` and `hl` (e.g. `Derivation.relations`).
        loc: Column of the selected low-level location loc^k.
        hl: Column of the selected high-level location agg(loc^k).
        processing: Event ids of P for the AS4 tie order; None = the transformation events T.

    Returns:
        pl.LazyFrame: Columns hu, event, time, activity, object_type, is_movement, is_transformation,
        is_processing, loc, hl and pos (1-based position in the trace of the hu), sorted by hu, then seq.
    """
    frame = relations.lazy().select(
        c.HU,
        c.EVENT,
        c.TIME,
        c.ACTIVITY,
        c.OBJECT_TYPE,
        pl.col(c.IS_MOVEMENT).fill_null(False),
        pl.col(c.IS_TRANSFORMATION).fill_null(False),
        pl.col(c.IS_PROCESSING).fill_null(False),
        pl.col(loc).alias(LOC),
        pl.col(hl).alias(HL),
    )
    return sort_by_seq(frame, c.HU, processing=processing).with_columns(
        (pl.int_range(pl.len()).over(c.HU) + 1).alias(POS)
    )


def lifecycle_basics(traces: pl.LazyFrame) -> pl.LazyFrame:
    """Object type, number of events, first and last timestamp, lifespan, movements and processing operations.

    Args:
        traces: Output of `ordered_traces`.

    Returns:
        pl.LazyFrame: One row per hu with the columns hu, object_type, n_events, first, last, lifespan
        (seconds from first to last timestamp), n_movements (events in M), n_processing (events in P) and
        processing_activities (distinct activities of its processing operations, in trace order).
    """
    return traces.group_by(c.HU).agg(
        pl.col(c.OBJECT_TYPE).first(),
        pl.col(c.EVENT).n_unique().alias("n_events"),
        pl.col(c.TIME).min().alias("first"),
        pl.col(c.TIME).max().alias("last"),
        ((pl.col(c.TIME).max() - pl.col(c.TIME).min()).dt.total_milliseconds() / 1000).alias("lifespan"),
        pl.col(c.EVENT).filter(pl.col(c.IS_MOVEMENT)).n_unique().alias("n_movements"),
        pl.col(c.EVENT).filter(pl.col(c.IS_PROCESSING)).n_unique().alias("n_processing"),
        pl.col(c.ACTIVITY).filter(pl.col(c.IS_PROCESSING)).unique(maintain_order=True).alias("processing_activities"),
    )


def location_profile(traces: pl.LazyFrame) -> pl.LazyFrame:
    """Distinct locations, first and last location, location changes and locatedness of every handling unit.

    A location change is a relation with loc ≠ ⊥ whose loc differs from the last loc ≠ ⊥ before it in the
    trace (⊥ stretches in between are skipped, so A, ⊥, A is no change and A, ⊥, B one).

    Args:
        traces: Output of `ordered_traces`.

    Returns:
        pl.LazyFrame: One row per hu with the columns hu, n_locations (distinct loc ≠ ⊥),
        n_high_level_locations (distinct hl ≠ ⊥), first_location and last_location (first and last loc ≠ ⊥),
        n_location_changes and locatedness (`fully located`, `partially located`, `unlocated`).
    """
    previous = pl.col(LOC).shift(1).forward_fill().over(c.HU)
    change = pl.col(LOC).is_not_null() & previous.is_not_null() & (pl.col(LOC) != previous)
    located = pl.col(LOC).is_not_null()
    return (
        traces.with_columns(change.alias("_change"))
        .group_by(c.HU)
        .agg(
            pl.col(LOC).drop_nulls().n_unique().alias("n_locations"),
            pl.col(HL).drop_nulls().n_unique().alias("n_high_level_locations"),
            pl.col(LOC).drop_nulls().first().alias("first_location"),
            pl.col(LOC).drop_nulls().last().alias("last_location"),
            pl.col("_change").sum().cast(pl.UInt32).alias("n_location_changes"),
            pl.when(located.all())
            .then(pl.lit("fully located"))
            .when(located.any())
            .then(pl.lit("partially located"))
            .otherwise(pl.lit("unlocated"))
            .alias("locatedness"),
        )
    )


def location_kind(context: LocationContext) -> pl.Expr:
    """Expression for the kind of the location loc of a relation: vehicle, storage, other or unlocated.

    A location that is both a vehicle and a storage unit (flag F10) counts as a vehicle.

    Args:
        context: The location context (V and W).

    Returns:
        pl.Expr: String named `kind`.
    """
    return (
        pl.when(pl.col(LOC).is_null())
        .then(pl.lit("unlocated"))
        .when(pl.col(LOC).is_in(sorted(context.vehicles)))
        .then(pl.lit("vehicle"))
        .when(pl.col(LOC).is_in(sorted(context.storage_units)))
        .then(pl.lit("storage"))
        .otherwise(pl.lit("other"))
        .alias("kind")
    )


def time_per_location_kind(traces: pl.LazyFrame, context: LocationContext) -> pl.LazyFrame:
    """Time a handling unit spends on vehicles, in storage units, at other locations and unlocated.

    After its j-th relation $r_j$ the handling unit is at $loc(r_j)$ until its next relation $r_{j+1}$, so
    $r_j$ contributes $time(r_{j+1}) - time(r_j)$ to the kind of $loc(r_j)$; the last relation contributes
    nothing. The four times add up to the lifespan.

    Args:
        traces: Output of `ordered_traces`.
        context: The location context (V and W).

    Returns:
        pl.LazyFrame: One row per hu with the columns time_vehicle, time_storage, time_other and
        time_unlocated (seconds).
    """
    duration = (pl.col(c.TIME).shift(-1).over(c.HU) - pl.col(c.TIME)).dt.total_milliseconds() / 1000
    return (
        traces.with_columns(location_kind(context), duration.fill_null(0).alias("_duration"))
        .group_by(c.HU)
        .agg(pl.col("_duration").filter(pl.col("kind") == kind).sum().alias(f"time_{kind}") for kind in KINDS)
    )


def transformation_profile(roles: pl.DataFrame, traces: pl.LazyFrame) -> pl.LazyFrame:
    """Creation event, final consumption, partial consumptions, parents, children, siblings and lifecycle class.

    - Creation event $ev_{prod}(hu)$ and its activity (null if the hu is not produced in the log).
    - Final consumption: a consumption event $e \\in E_{cons}(hu)$ at the hu's last timestamp.
    - Partial consumptions: the other consumption events $E_{cons}(hu)$, i.e. consumptions after which the
      hu still has events (by AS-T3 only in events that also produce something).
    - Lifecycle: `both` (produced and finally consumed in the log), `produced` (only produced), `consumed`
      (only finally consumed) or `open` (neither).

    Args:
        roles: Transformation roles with the columns event, hu and role (`Derivation.roles`).
        traces: Output of `ordered_traces`.

    Returns:
        pl.LazyFrame: One row per hu of `traces` with the columns creation_event, creation_activity,
        final_consumption_event, final_consumption_activity, partial_consumptions (list of event ids, in
        time order), n_partial_consumptions, parents, children, siblings (lists, sorted), n_parents,
        n_children, n_siblings and lifecycle.
    """
    activity = traces.select(c.EVENT, c.ACTIVITY, c.TIME).unique(subset=c.EVENT)
    last = traces.group_by(c.HU).agg(pl.col(c.TIME).max().alias("_last"))
    created = (
        creation_events(roles)
        .lazy()
        .join(activity, on=c.EVENT, how="left")
        .group_by(c.HU)
        .agg(pl.col(c.EVENT).first().alias("creation_event"), pl.col(c.ACTIVITY).first().alias("creation_activity"))
    )
    consumed = (
        consumption_events(roles)
        .lazy()
        .join(activity, on=c.EVENT, how="left")
        .join(last, on=c.HU, how="left")
        .sort(c.HU, c.TIME, c.EVENT)
        .with_columns((pl.col(c.TIME) == pl.col("_last")).alias("_final"))
        .group_by(c.HU)
        .agg(
            pl.col(c.EVENT).filter(pl.col("_final")).first().alias("final_consumption_event"),
            pl.col(c.ACTIVITY).filter(pl.col("_final")).first().alias("final_consumption_activity"),
            pl.col(c.EVENT).filter(~pl.col("_final")).alias("partial_consumptions"),
        )
    )
    relations = lineage_relations(roles)
    parents = relations.lazy().group_by("child").agg(pl.col("parent").unique().sort().alias("parents"))
    children = relations.lazy().group_by("parent").agg(pl.col("child").unique().sort().alias("children"))
    sibs = siblings(roles).lazy().group_by(c.HU).agg(pl.col("sibling").unique().sort().alias("siblings"))
    empty = pl.lit([], dtype=pl.List(pl.String))
    produced = pl.col("creation_event").is_not_null()
    final = pl.col("final_consumption_event").is_not_null()
    return (
        traces.select(c.HU)
        .unique()
        .join(created, on=c.HU, how="left")
        .join(consumed, on=c.HU, how="left")
        .join(parents, left_on=c.HU, right_on="child", how="left")
        .join(children, left_on=c.HU, right_on="parent", how="left")
        .join(sibs, on=c.HU, how="left")
        .with_columns(pl.col(name).fill_null(empty) for name in ("partial_consumptions", "parents", "children", "siblings"))
        .with_columns(
            pl.col("partial_consumptions").list.len().alias("n_partial_consumptions"),
            pl.col("parents").list.len().alias("n_parents"),
            pl.col("children").list.len().alias("n_children"),
            pl.col("siblings").list.len().alias("n_siblings"),
            pl.when(produced & final)
            .then(pl.lit("both"))
            .when(produced)
            .then(pl.lit("produced"))
            .when(final)
            .then(pl.lit("consumed"))
            .otherwise(pl.lit("open"))
            .alias("lifecycle"),
        )
    )


def connectedness(traces: pl.LazyFrame) -> pl.LazyFrame:
    """How strongly a handling unit is handled together with others, outside transformations.

    Only events that are not transformation events count (shared transformation events are lineage, see
    `transformation_profile`). For hu with non-transformation events E'(hu):
    - n_shared_events: events of E'(hu) that involve at least one other handling unit;
    - connectedness: n_shared_events / |E'(hu)| (null if E'(hu) is empty);
    - n_co_handled: distinct other handling units in these events.

    Args:
        traces: Output of `ordered_traces`.

    Returns:
        pl.LazyFrame: One row per hu of `traces` with the columns n_shared_events, connectedness, n_co_handled.
    """
    pairs = traces.filter(~pl.col(c.IS_TRANSFORMATION)).select(c.EVENT, c.HU).unique()
    others = pairs.join(pairs.rename({c.HU: "_other"}), on=c.EVENT, how="inner").filter(pl.col(c.HU) != pl.col("_other"))
    shared = others.group_by(c.HU).agg(
        pl.col(c.EVENT).n_unique().alias("n_shared_events"), pl.col("_other").n_unique().alias("n_co_handled")
    )
    totals = pairs.group_by(c.HU).agg(pl.len().alias("_n"))
    return (
        traces.select(c.HU)
        .unique()
        .join(totals, on=c.HU, how="left")
        .join(shared, on=c.HU, how="left")
        .with_columns(
            pl.col("n_shared_events").fill_null(0).cast(pl.UInt32),
            pl.col("n_co_handled").fill_null(0).cast(pl.UInt32),
        )
        .with_columns(
            pl.when(pl.col("_n") > 0).then(pl.col("n_shared_events") / pl.col("_n")).otherwise(None).alias("connectedness")
        )
        .drop("_n")
    )


def linked_handling_units(traces: pl.LazyFrame) -> pl.LazyFrame:
    """How many other handling units share at least one event with a handling unit, transformation events included.

    Unlike `connectedness`, transformation events count, so parents, children and siblings are among them
    (n_linked >= n_co_handled).

    Args:
        traces: Output of `ordered_traces`.

    Returns:
        pl.LazyFrame: One row per hu of `traces` with the column n_linked.
    """
    pairs = traces.select(c.EVENT, c.HU).unique()
    linked = (
        pairs.join(pairs.rename({c.HU: "_other"}), on=c.EVENT, how="inner")
        .filter(pl.col(c.HU) != pl.col("_other"))
        .group_by(c.HU)
        .agg(pl.col("_other").n_unique().alias("n_linked"))
    )
    return (
        traces.select(c.HU)
        .unique()
        .join(linked, on=c.HU, how="left")
        .with_columns(pl.col("n_linked").fill_null(0).cast(pl.UInt32))
    )


def hu_profile(
    relations: pl.DataFrame | pl.LazyFrame,
    handling_units: pl.DataFrame,
    roles: pl.DataFrame,
    context: LocationContext,
    loc: str,
    hl: str,
    processing: Collection[str] | None = None,
) -> pl.DataFrame:
    """The HU profile: one row per handling unit (steps 1 to 6), sorted by hu.

    Args:
        relations: See `ordered_traces`.
        handling_units: All handling units with the columns hu and object_type; those without events get
            0 events and nulls elsewhere.
        roles: Transformation roles (see `transformation_profile`).
        context: The location context (V and W).
        loc: Column of loc^k.
        hl: Column of agg(loc^k).
        processing: Event ids of P (AS4 tie order); None = the transformation events T.

    Returns:
        pl.DataFrame: The columns of `lifecycle_basics`, `location_profile`, `time_per_location_kind`,
        `transformation_profile`, `connectedness` and `linked_handling_units`.
    """
    traces = ordered_traces(relations, loc, hl, processing).cache()
    profile = (
        lifecycle_basics(traces)
        .join(location_profile(traces), on=c.HU, how="left")
        .join(time_per_location_kind(traces, context), on=c.HU, how="left")
        .join(transformation_profile(roles, traces), on=c.HU, how="left")
        .join(connectedness(traces), on=c.HU, how="left")
        .join(linked_handling_units(traces), on=c.HU, how="left")
        .collect()
    )
    missing = handling_units.select(c.HU, c.OBJECT_TYPE).filter(~pl.col(c.HU).is_in(profile[c.HU].implode()))
    return (
        pl.concat([profile, missing], how="diagonal_relaxed")
        .with_columns(pl.col("n_events").fill_null(0), pl.col("lifecycle").fill_null("open"))
        .sort(c.HU)
    )


def search_text() -> pl.Expr:
    """Expression for the text a search matches: id, object type, first and last location, creation and final
    consumption activity, parents, children and processing activities, lower case.

    Returns:
        pl.Expr: String named `_search`.
    """
    def joined(name: str) -> pl.Expr:
        return pl.col(name).list.join(" ").fill_null("")

    return (
        pl.concat_str(
            [
                pl.col(c.HU),
                pl.col(c.OBJECT_TYPE).fill_null(""),
                pl.col("first_location").fill_null(""),
                pl.col("last_location").fill_null(""),
                pl.col("creation_activity").fill_null(""),
                pl.col("final_consumption_activity").fill_null(""),
                joined("parents"),
                joined("children"),
                joined("processing_activities"),
            ],
            separator=" ",
        )
        .str.to_lowercase()
        .alias("_search")
    )


@dataclass
class ColumnFilter:
    """A filter on one column of the profile; a row is kept if it satisfies every filter.

    Set one of:
    - values: keep rows whose value is one of these (None in the list = missing value);
    - min and/or max: keep rows whose value is in [min, max] (rows without a value are dropped); for timestamp
      columns both are milliseconds since 1970-01-01 (UTC), for durations seconds, for connectedness a share 0..1;
    - text: keep rows whose value contains the text (case-insensitive).

    Example: `ColumnFilter("n_children", min=1)` keeps handling units with at least one child;
    `ColumnFilter("object_type", values=["coil"])` keeps the coils.
    """

    column: str
    values: list[str | None] | None = None
    min: float | None = None
    max: float | None = None
    text: str | None = None


def filter_expression(schema: pl.Schema, flt: ColumnFilter) -> pl.Expr | None:
    """The polars expression of one column filter (None if the filter sets nothing).

    Args:
        schema: Schema of the profile (to treat timestamp columns as milliseconds).
        flt: The filter.

    Returns:
        pl.Expr | None: Boolean expression.

    Raises:
        ValueError: If the column cannot be filtered.
    """
    if flt.column not in FILTERABLE or flt.column not in schema:
        raise ValueError(f"cannot filter by {flt.column!r}")
    col = pl.col(flt.column)
    parts: list[pl.Expr] = []
    if flt.values is not None:
        known = [v for v in flt.values if v is not None]
        expr = col.cast(pl.String).is_in(known)
        parts.append(expr | col.is_null() if None in flt.values else expr.fill_null(False))
    if flt.min is not None or flt.max is not None:
        value = col.dt.epoch("ms") if schema[flt.column].is_temporal() else col.cast(pl.Float64)
        if flt.min is not None:
            parts.append(value >= flt.min)
        if flt.max is not None:
            parts.append(value <= flt.max)
    if flt.text:
        parts.append(col.cast(pl.String).str.to_lowercase().str.contains(flt.text.lower(), literal=True).fill_null(False))
    return pl.all_horizontal(parts) if parts else None


def query_rows(profile: pl.DataFrame, search: str = "", filters: Sequence[ColumnFilter] = ()) -> pl.DataFrame:
    """The rows of the profile matching the search and all column filters (unsorted).

    Args:
        profile: Output of `hu_profile`.
        search: Words that must all occur (case-insensitive substrings) in the `search_text` of a row; empty =
            every row.
        filters: Column filters (see `ColumnFilter`).

    Returns:
        pl.DataFrame: The matching rows.
    """
    frame = profile.lazy()
    for flt in filters:
        expr = filter_expression(profile.schema, flt)
        if expr is not None:
            frame = frame.filter(expr)
    words = search.lower().split()
    if words:
        frame = frame.with_columns(search_text()).filter(
            pl.all_horizontal(pl.col("_search").str.contains(word, literal=True) for word in words)
        ).drop("_search")
    return frame.collect()


def sort_rows(rows: pl.DataFrame, sort_by: str = "hu", descending: bool = False) -> pl.DataFrame:
    """Sort rows of the profile by one column, nulls last, ties by hu.

    Args:
        rows: Rows of the profile.
        sort_by: A column of `SORTABLE`.
        descending: Sort descending.

    Returns:
        pl.DataFrame: The sorted rows.

    Raises:
        ValueError: If `sort_by` is not sortable.
    """
    if sort_by not in SORTABLE:
        raise ValueError(f"cannot sort by {sort_by!r}")
    by = [sort_by] if sort_by == c.HU else [sort_by, c.HU]
    return rows.sort(by, descending=[descending] + [False] * (len(by) - 1), nulls_last=True)


def query_profile(
    profile: pl.DataFrame,
    search: str = "",
    object_types: Collection[str] = (),
    sort_by: str = "hu",
    descending: bool = False,
    offset: int = 0,
    limit: int = 25,
    filters: Sequence[ColumnFilter] = (),
) -> tuple[pl.DataFrame, int]:
    """Search, filter, sort and page the profile.

    Args:
        profile: Output of `hu_profile`.
        search: See `query_rows`.
        object_types: Keep only these object types; empty = all (same as a values filter on object_type).
        sort_by: A column of `SORTABLE`; nulls last, ties by hu.
        descending: Sort descending.
        offset: First row of the page (0-based).
        limit: Rows per page.
        filters: Column filters (see `ColumnFilter`).

    Returns:
        tuple[pl.DataFrame, int]: The rows of the page and the number of matching rows.

    Raises:
        ValueError: If `sort_by` is not sortable or a filter's column cannot be filtered.
    """
    if sort_by not in SORTABLE:
        raise ValueError(f"cannot sort by {sort_by!r}")
    if object_types:
        filters = [*filters, ColumnFilter(c.OBJECT_TYPE, values=list(object_types))]
    matching = query_rows(profile, search, filters)
    return sort_rows(matching, sort_by, descending).slice(offset, limit), matching.height


def column_info(profile: pl.DataFrame) -> list[dict]:
    """What the column filters of the table offer: per filterable column its kind and its values or range.

    Kinds: `category` (string column with at most `MAX_CATEGORIES` distinct values: values with their number of
    rows, most frequent first, missing value as None), `text` (other string columns), `number` and `time`
    (min and max; time in milliseconds since 1970-01-01 UTC).

    Args:
        profile: Output of `hu_profile`.

    Returns:
        list[dict]: Entries with column, kind, values (list of (value, count) or None), min and max (or None).
    """
    info = []
    for name in FILTERABLE:
        if name not in profile.columns:
            continue
        dtype = profile.schema[name]
        series = profile[name]
        entry = {"column": name, "kind": "number", "values": None, "min": None, "max": None}
        if dtype == pl.String or dtype == pl.Categorical:
            counts = series.value_counts(sort=True)
            if counts.height <= MAX_CATEGORIES and name != c.HU:
                pairs = sorted(counts.iter_rows(), key=lambda r: (-r[1], r[0] is None, r[0] or ""))
                entry.update(kind="category", values=[(v, int(n)) for v, n in pairs])
            else:
                entry["kind"] = "text"
        else:
            values = series.dt.epoch("ms") if dtype.is_temporal() else series.cast(pl.Float64)
            entry.update(
                kind="time" if dtype.is_temporal() else "number",
                min=values.min(),
                max=values.max(),
            )
        info.append(entry)
    return info


def export_frame(rows: pl.DataFrame, columns: Sequence[str]) -> pl.DataFrame:
    """The folded table for an export: the given columns (hu always first) of the given rows, in their order.

    Values stay as stored: counts as integers, durations in seconds, connectedness as a share 0..1, timestamps
    as datetimes.

    Args:
        rows: Rows of the profile (e.g. `sort_rows(query_rows(...))`).
        columns: Columns to export, in table order; unknown or list columns are refused.

    Returns:
        pl.DataFrame: The export.

    Raises:
        ValueError: If a column cannot be exported.
    """
    wrong = [col for col in columns if col not in FILTERABLE]
    if wrong:
        raise ValueError(f"cannot export {', '.join(map(repr, wrong))}")
    ordered = [c.HU, *(col for col in dict.fromkeys(columns) if col != c.HU)]
    return rows.select(ordered)


def location_path(trace: pl.DataFrame) -> list[dict]:
    """The locations of one handling unit in trace order, each with the time it is reached.

    A new entry starts at every location change (as in `location_profile`: loc != ⊥ and different from the last
    loc != ⊥ before), so ⊥ in between is skipped and A, ⊥, A is one entry.

    Args:
        trace: The rows of one hu of `ordered_traces` (columns event, time, loc), in trace order.

    Returns:
        list[dict]: Entries with location, event (the event that reached it) and time.
    """
    located = trace.filter(pl.col(LOC).is_not_null())
    changes = located.filter(pl.col(LOC) != pl.col(LOC).shift(1).fill_null(""))
    return changes.select(pl.col(LOC).alias("location"), c.EVENT, c.TIME).to_dicts()


def _events(trace: pl.DataFrame, ids: Collection[str]) -> list[dict]:
    """Event id, activity and time of the given events of a trace, in trace order."""
    return trace.filter(pl.col(c.EVENT).is_in(list(ids))).select(c.EVENT, c.ACTIVITY, c.TIME).unique(c.EVENT, maintain_order=True).to_dicts()


def hu_details(
    relations: pl.DataFrame | pl.LazyFrame,
    profile_row: dict,
    loc: str,
    hl: str,
    processing: Collection[str] | None = None,
) -> dict:
    """What an unfolded row of the HU profile shows for one handling unit.

    Args:
        relations: See `ordered_traces` (all handling units; the co-handled ones are looked up there).
        profile_row: The handling unit's row of `hu_profile`.
        loc: Column of loc^k.
        hl: Column of agg(loc^k).
        processing: Event ids of P (AS4 tie order); None = the transformation events T.

    Returns:
        dict: first_event and last_event (event, activity, time; None without events), creation and
        final_consumption (the same, None if missing), partial_consumptions (list), parents, children,
        siblings (lists of ids), location_path (see `location_path`), processing (activity and count, by
        count), co_handled (other handling unit, its number of shared non-transformation events and their ids,
        by count).
    """
    hu = profile_row[c.HU]
    frame = relations.lazy()
    trace = ordered_traces(frame.filter(pl.col(c.HU) == hu), loc, hl, processing).collect()
    first = trace.head(1).select(c.EVENT, c.ACTIVITY, c.TIME).to_dicts()
    last = trace.tail(1).select(c.EVENT, c.ACTIVITY, c.TIME).to_dicts()

    def one(event: str | None) -> dict | None:
        rows = _events(trace, [event]) if event else []
        return rows[0] if rows else None

    processing_counts = (
        trace.filter(pl.col(c.IS_PROCESSING))
        .group_by(c.ACTIVITY)
        .len()
        .sort(["len", c.ACTIVITY], descending=[True, False])
        .rename({"len": "count"})
        .to_dicts()
    )
    events = trace.filter(~pl.col(c.IS_TRANSFORMATION))[c.EVENT].to_list()
    co_handled = (
        frame.filter(pl.col(c.EVENT).is_in(events) & (pl.col(c.HU) != hu))
        .select(c.HU, c.EVENT, c.TIME)
        .unique()
        .sort(c.TIME, c.EVENT)
        .group_by(c.HU, maintain_order=True)
        .agg(pl.col(c.EVENT).alias("events"))
        .with_columns(pl.col("events").list.len().alias("count"))
        .sort(["count", c.HU], descending=[True, False])
        .collect()
        .to_dicts()
    )
    return {
        "first_event": first[0] if first else None,
        "last_event": last[0] if last else None,
        "creation": one(profile_row.get("creation_event")),
        "final_consumption": one(profile_row.get("final_consumption_event")),
        "partial_consumptions": _events(trace, profile_row.get("partial_consumptions") or []),
        "parents": profile_row.get("parents") or [],
        "children": profile_row.get("children") or [],
        "siblings": profile_row.get("siblings") or [],
        "location_path": location_path(trace),
        "processing": processing_counts,
        "co_handled": co_handled,
    }
