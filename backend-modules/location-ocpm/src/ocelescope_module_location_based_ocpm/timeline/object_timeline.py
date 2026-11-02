"""Object timeline: one row per handling unit with its location band and its events.

Concept draft: `claude_notes/Object Timeline (draft).md`; documented in `docs/resources/object-timeline.md`.
A variation of the playground's object timeline (material_flow_analysis, `ObjectTimeline.tsx`): the bands show
loc (and agg(loc)), processing operations are stars, other events circles, consumption/production at
transformation events colours the event markers, and a movement whose pickup location differs from the location
after the previous event gets a different tick. Flags are not shown.

The data is prepared in small steps, each a function of its own (all take and return polars frames):
1. `add_high_level_locations`: hl = agg(loc) and the high-level previous location agg(ploc).
2. `add_vehicles`: whether loc and ploc are vehicles (V).
3. `add_processing`: whether the event is a processing operation (P; default: the transformation events T).
4. `add_transformation_roles`: whether the handling unit is consumed and/or produced at the event (only e ∈ T).
5. `add_markers`: marker shape (processing, movement, other) and role colour of every relation.
6. `add_positions`: trace position and x per relation on the "event order" or "time" axis; events with the
   same timestamp get their own x, movements first, then by event id.
7. `add_pickup_differs`: movements whose pickup location differs from the location after the previous event.
`timeline_relations` runs steps 1 to 7 on a relations frame (a saved level mapping or `Derivation.relations`).
From its output:
8. `band_segments`: the coloured stretches of the low-level or high-level band.
9. `tie_groups`, `shared_events`, `lifespans`: same-timestamp boxes, shared-event links, lifespan lines.
10. `object_timeline`: draws the plotly figure.
"""

import warnings
from collections.abc import Collection, Mapping
from datetime import timedelta
from typing import Literal

import plotly.graph_objects as go
import polars as pl

from ..derivation import columns as c
from ..visits.trace_figure import (
    CATEGORICAL,
    GREY,
    HU_ORDER,
    POSITION,
    TIE_FILL,
    TIE_SPREAD,
    X,
    location_colours,
)

#: x axis options: every event its own position in the order of all shown events, or real time.
TimelineAxis = Literal["event order", "time"]
#: Band options: the low-level band (loc) or the high-level band (agg(loc)).
BandLevel = Literal["low", "high"]

# Input columns (the columns of a saved level mapping).
#: Current location loc((e, hu)); null = ⊥.
LOC = "loc"
#: Previous location ploc((e, hu)); null = ⊥.
PLOC = "ploc"

# Columns added by the steps.
#: High-level location agg(loc((e, hu))); null = ⊥.
HIGH_LEVEL = "high_level"
#: High-level previous location agg(ploc((e, hu))); null = ⊥.
PREV_HIGH_LEVEL = "prev_high_level"
#: loc((e, hu)) ∈ V.
IS_VEHICLE = "is_vehicle"
#: ploc((e, hu)) ∈ V.
PREV_IS_VEHICLE = "prev_is_vehicle"
#: e ∈ P.
IS_PROCESSING = "is_processing"
#: hu ∈ cons(e) (only for e ∈ T).
IS_CONSUMED = "is_consumed"
#: hu ∈ prod(e) (only for e ∈ T).
IS_PRODUCED = "is_produced"
#: Marker shape of the relation: "processing", "movement" or "other" (see `add_markers`).
MARKER = "marker"
#: Role of the handling unit at the event: "produced", "consumed", "consumed and produced", or null.
ROLE = "role"
#: loc of the previous relation of the handling unit (null for its first relation or ⊥).
PREV_LOC = "prev_loc"
#: True for a movement whose ploc (pickup location) is known and differs from PREV_LOC (also known).
PICKUP_DIFFERS = "pickup_differs"

#: Values of the column `ROLE`.
PRODUCED, CONSUMED, BOTH = "produced", "consumed", "consumed and produced"
#: Colour of each role (module palette: green, pink, amber); events without a role are dark grey.
ROLE_COLOUR = {PRODUCED: "#007e56", CONSUMED: "#CE108A", BOTH: "#F6A800"}
NO_ROLE_COLOUR = "#495057"
#: Colour of the lifespan line, the shared-event links and the movement ticks.
LINE = "#868e96"
TICK = "#343a40"

#: Marker symbols by marker shape (plotly names); movements without a role are a vertical tick on the band.
SYMBOL = {"processing": "star", "other": "circle", "movement": "line-ns-open"}
#: Marker sizes by marker shape (a star looks smaller than a circle of the same size).
SIZE = {"processing": 17, "other": 10, "movement": 16}
#: Movement tick whose pickup location differs from the previous location (Nina 2026-10-31: visible, not
#: dominant; details in the hover): a small open diamond instead of the tick.
PICKUP_DIFFERS_SYMBOL = "diamond-tall-open"
PICKUP_DIFFERS_SIZE = 13
#: Most handling units shown in one timeline (Nina 2026-10-31).
MAX_HANDLING_UNITS = 50

# Geometry in y units: one handling unit per row; offsets from the row's centre.
#: Top and bottom of the band; with a high-level band, the low-level band is the upper half.
BAND_TOP = 0.12
BAND_BOTTOM = -0.32
#: Height of the markers of events that are not movements, above the band.
MARKER_Y = 0.4
#: Distance of the lifespan line below the band, and overhang of its end ticks.
LIFESPAN_OFFSET = 0.07
#: Distance between the rows of two handling units (more if activity names are written).
ROW_GAP = 1.0
LABELLED_ROW_GAP = 1.4
#: Room above the top row for activity names.
LABEL_ROOM = 0.45
#: Angle of the activity names.
LABEL_ANGLE = -35
#: Pixels per y unit.
PX_PER_UNIT = 90
#: Default figure width in pixels.
WIDTH = 1200
#: How far a band reaches beyond the first or last event (lead-in, continuation): event-order axis in
#: positions; time axis as a share of the time span (at least `MIN_TIME_CONTINUATION`). Halved on
#: Nina's request (2026-10-31).
ORDER_CONTINUATION = 0.3
TIME_CONTINUATION = 0.01
MIN_TIME_CONTINUATION = timedelta(seconds=30)
#: Half the width of a same-timestamp box beyond its first and last event, in positions (event order)
#: or as a share of the smallest gap between timestamps (time).
TIE_PAD = 0.4
#: Pattern of the band stretches on vehicles.
VEHICLE_PATTERN = {
    "shape": "/",
    "fillmode": "overlay",
    "fgcolor": "#ffffff",
    "solidity": 0.3,
}
#: Label of ⊥.
NOT_LOCATED = "⊥ (not located)"


def add_high_level_locations(
    relations: pl.DataFrame, agg: Mapping[str, str] | None = None
) -> pl.DataFrame:
    """Add the high-level location of loc and of ploc of every relation.

    hl((e, hu)) = agg(loc((e, hu))) and agg(ploc((e, hu))), ⊥ where the location is ⊥ (hat-hl in
    `overview/Single Level Visit Mappings.md`). `agg` may be partial: unmapped locations are their own
    high-level location (identity).

    Args:
        relations: One row per hu-event relation with the columns loc and ploc (null = ⊥).
        agg: Low-level location -> high-level location; None = identity for all.

    Returns:
        pl.DataFrame: `relations` with the columns high_level and prev_high_level.
    """
    mapping = dict(agg or {})
    return relations.with_columns(
        pl.col(LOC).replace(mapping).alias(HIGH_LEVEL),
        pl.col(PLOC).replace(mapping).alias(PREV_HIGH_LEVEL),
    )


def add_vehicles(
    relations: pl.DataFrame, vehicles: Collection[str] = ()
) -> pl.DataFrame:
    """Add whether loc and ploc of every relation are vehicles (in V).

    Args:
        relations: Relations frame with the columns loc and ploc.
        vehicles: The set V of vehicle locations.

    Returns:
        pl.DataFrame: `relations` with the boolean columns is_vehicle and prev_is_vehicle (false for ⊥).
    """
    v = list(vehicles)
    return relations.with_columns(
        pl.col(LOC).is_in(v).fill_null(False).alias(IS_VEHICLE),
        pl.col(PLOC).is_in(v).fill_null(False).alias(PREV_IS_VEHICLE),
    )


def add_processing(
    relations: pl.DataFrame, processing: Collection[str] | None = None
) -> pl.DataFrame:
    """Add whether the event of every relation is a processing operation (e ∈ P).

    As for the trace figure (decision 2026-10-31): without P, the transformation events T are used.

    Args:
        relations: Relations frame with the columns event and is_transformation.
        processing: Event ids of P; None = the transformation events; an empty collection = none.

    Returns:
        pl.DataFrame: `relations` with the boolean column is_processing.
    """
    flag = (
        pl.col(c.IS_TRANSFORMATION).fill_null(False)
        if processing is None
        else pl.col(c.EVENT).is_in(list(processing))
    )
    return relations.with_columns(flag.alias(IS_PROCESSING))


def add_transformation_roles(
    relations: pl.DataFrame, roles: pl.DataFrame | None = None
) -> pl.DataFrame:
    """Add whether the handling unit is consumed (hu ∈ cons(e)) and/or produced (hu ∈ prod(e)) at the event.

    Roles only count at transformation events (e ∈ T): a role given for any other event is ignored, as
    cons and prod are only defined on T.

    Args:
        relations: Relations frame with the columns event, hu and is_transformation.
        roles: One row per (event, hu, role) with role "consumed" or "produced" (a relation may have both,
            in two rows); e.g. `data/running_example/inputs/transformation_roles.csv`. None = no roles.

    Returns:
        pl.DataFrame: `relations` with the boolean columns is_consumed and is_produced.
    """
    if roles is None:
        roles = pl.DataFrame(
            schema={c.EVENT: pl.String, c.HU: pl.String, "role": pl.String}
        )
    flags = roles.group_by(c.EVENT, c.HU).agg(
        (pl.col("role") == CONSUMED).any().alias(IS_CONSUMED),
        (pl.col("role") == PRODUCED).any().alias(IS_PRODUCED),
    )
    in_t = pl.col(c.IS_TRANSFORMATION).fill_null(False)
    return (
        relations.drop(IS_CONSUMED, IS_PRODUCED, strict=False)
        .join(flags, on=[c.EVENT, c.HU], how="left", maintain_order="left")
        .with_columns(
            (pl.col(IS_CONSUMED).fill_null(False) & in_t).alias(IS_CONSUMED),
            (pl.col(IS_PRODUCED).fill_null(False) & in_t).alias(IS_PRODUCED),
        )
    )


def add_markers(relations: pl.DataFrame) -> pl.DataFrame:
    """Add the marker shape and the role of every relation.

    Shape: "processing" (star) if e ∈ P, else "movement" (on the band) if e ∈ M, else "other" (circle).
    A processing operation that is also a movement stays a star, drawn on the band.
    Role (colour): "consumed and produced", "produced", "consumed" or null.

    Args:
        relations: Relations frame with the columns is_processing, is_movement, is_consumed, is_produced.

    Returns:
        pl.DataFrame: `relations` with the columns marker and role.
    """
    cons, prod = pl.col(IS_CONSUMED), pl.col(IS_PRODUCED)
    return relations.with_columns(
        pl.when(pl.col(IS_PROCESSING))
        .then(pl.lit("processing"))
        .when(pl.col(c.IS_MOVEMENT).fill_null(False))
        .then(pl.lit("movement"))
        .otherwise(pl.lit("other"))
        .alias(MARKER),
        pl.when(cons & prod)
        .then(pl.lit(BOTH))
        .when(prod)
        .then(pl.lit(PRODUCED))
        .when(cons)
        .then(pl.lit(CONSUMED))
        .otherwise(None)
        .alias(ROLE),
    )


def hu_order(
    relations: pl.DataFrame,
    handling_units: Collection[str] | None = None,
    max_handling_units: int | None = MAX_HANDLING_UNITS,
) -> dict[str, int]:
    """Order of the handling units in the timeline (top to bottom).

    Args:
        relations: Relations frame with the columns hu and time.
        handling_units: Handling units to show, in this order; None = all, ordered by their first
            event's time, then by id (as in the playground).
        max_handling_units: Show at most this many (the first ones); a warning names how many were cut.
            None = no limit.

    Returns:
        dict[str, int]: Handling unit -> row index (0 = top); handling units without relations are left out.
    """
    present = set(relations[c.HU].unique().to_list())
    if handling_units is not None:
        shown = [hu for hu in dict.fromkeys(handling_units) if hu in present]
    else:
        shown = (
            relations.group_by(c.HU)
            .agg(pl.col(c.TIME).min().alias("_first"))
            .sort("_first", c.HU)[c.HU]
            .to_list()
        )
    if max_handling_units is not None and len(shown) > max_handling_units:
        warnings.warn(
            f"Only the first {max_handling_units} of {len(shown)} handling units are shown.",
            stacklevel=2,
        )
        shown = shown[:max_handling_units]
    return {hu: i for i, hu in enumerate(shown)}


def add_positions(
    relations: pl.DataFrame,
    axis: TimelineAxis = "event order",
    spread: float = TIE_SPREAD,
) -> pl.DataFrame:
    """Add the trace position of every relation and its x value on the chosen axis.

    Order of the relations (the order of seq, with one tie rule; Nina 2026-10-31): by time; among events with
    the same timestamp, movements first (an event at the same timestamp as a movement counts as after it, as
    in Level 1 of `overview/Deriving Locations.md`), then by event id.

    Args:
        relations: Relations frame with columns hu, hu_order, event, time, is_movement.
        axis: "event order": x = rank of the event among all shown events in this order, so every event has
            its own x and a shared event one x; "time": x = the timestamp, with the tied events of a timestamp
            placed side by side in this order, centred on it and together spanning at most `spread` times the
            smallest gap between two distinct timestamps.
        spread: See `axis` ("time" only).

    Returns:
        pl.DataFrame: `relations` sorted by hu_order and this order, with columns position (index in the
        handling unit's trace, from 1) and x.
    """
    later = pl.col(c.IS_MOVEMENT).fill_null(False).not_().alias("_later")
    out = (
        relations.with_columns(later)
        .sort(HU_ORDER, c.TIME, "_later", c.EVENT)
        .with_columns((pl.int_range(pl.len()).over(c.HU) + 1).alias(POSITION))
    )
    if axis == "event order":
        return out.with_columns(
            pl.struct(c.TIME, "_later", c.EVENT).rank("dense").alias(X)
        ).drop("_later")
    times = out[c.TIME].unique().sort()
    gaps = times.diff().drop_nulls()
    gap = gaps.min() if len(gaps) else timedelta(hours=1)
    ties = (
        out.select(c.TIME, "_later", c.EVENT)
        .unique()
        .with_columns(
            (pl.struct("_later", c.EVENT).rank("dense").over(c.TIME) - 1).alias("_i"),
            pl.col(c.EVENT).n_unique().over(c.TIME).alias("_n"),
        )
    )
    max_n = ties["_n"].max() if ties.height else 1
    step = gap * spread / max(max_n - 1, 1)
    ties = ties.select(
        c.EVENT,
        (pl.col(c.TIME) + (pl.col("_i") - (pl.col("_n") - 1) / 2) * pl.lit(step)).alias(
            X
        ),
    )
    return out.join(ties, on=c.EVENT, how="left", maintain_order="left").drop("_later")


def add_pickup_differs(relations: pl.DataFrame) -> pl.DataFrame:
    """Add the previous location and whether a movement's pickup location differs from it.

    prev_loc = loc of the handling unit's previous relation (in the order of `add_positions`; for a movement
    that is a relation at an earlier timestamp, since movements come first among tied events and RQ3 allows
    one movement per handling unit and timestamp). pickup_differs is true for a movement (e ∈ M) with
    ploc ≠ ⊥, prev_loc ≠ ⊥ and ploc ≠ prev_loc, i.e. a provided pickup location that disagrees.
    The band shows loc only; this is marked on the movement (Nina 2026-10-31).

    Args:
        relations: Output of `add_positions` (sorted by handling unit and trace position) with loc, ploc.

    Returns:
        pl.DataFrame: `relations` with the columns prev_loc and pickup_differs.
    """
    out = relations.with_columns(pl.col(LOC).shift(1).over(c.HU).alias(PREV_LOC))
    return out.with_columns(
        (
            pl.col(c.IS_MOVEMENT).fill_null(False)
            & pl.col(PLOC).is_not_null()
            & pl.col(PREV_LOC).is_not_null()
            & (pl.col(PLOC) != pl.col(PREV_LOC))
        ).alias(PICKUP_DIFFERS)
    )


def timeline_relations(
    relations: pl.DataFrame,
    handling_units: Collection[str] | None = None,
    agg: Mapping[str, str] | None = None,
    vehicles: Collection[str] = (),
    processing: Collection[str] | None = None,
    roles: pl.DataFrame | None = None,
    axis: TimelineAxis = "event order",
    max_handling_units: int | None = MAX_HANDLING_UNITS,
) -> pl.DataFrame:
    """Prepare the relations of some handling units for the timeline (steps 1 to 7).

    Args:
        relations: One row per hu-event relation with columns event, hu, object_type, time, activity,
            is_movement, is_transformation, loc and ploc (e.g. a saved level mapping).
        handling_units: Handling units to show, top to bottom in this order; None = all, by first event.
        agg: Location mapping (partial, completed by identity).
        vehicles: The set V.
        processing: Event ids of P (None = the transformation events).
        roles: Consumed/produced roles (see `add_transformation_roles`).
        axis: "event order" or "time", see `add_positions`.
        max_handling_units: See `hu_order` (default 50).

    Returns:
        pl.DataFrame: The columns of `relations` (only the shown handling units) plus hu_order,
        high_level, prev_high_level, is_vehicle, prev_is_vehicle, is_processing, is_consumed, is_produced,
        marker, role, position, x, prev_loc and pickup_differs; sorted by hu_order and trace position.
    """
    order = hu_order(relations, handling_units, max_handling_units)
    out = relations.filter(pl.col(c.HU).is_in(list(order))).with_columns(
        pl.col(c.HU).replace_strict(order, return_dtype=pl.Int64).alias(HU_ORDER)
    )
    out = add_high_level_locations(out, agg)
    out = add_vehicles(out, vehicles)
    out = add_processing(out, processing)
    out = add_transformation_roles(out, roles)
    out = add_markers(out)
    return add_pickup_differs(add_positions(out, axis))


def continuation(relations: pl.DataFrame):
    """Default length of the lead-in and the continuation of a band.

    Args:
        relations: Output of `timeline_relations`.

    Returns:
        float | timedelta: `ORDER_CONTINUATION` positions on the event-order axis; on the time axis
        `TIME_CONTINUATION` of the shown time span, at least `MIN_TIME_CONTINUATION`.
    """
    if not relations.schema[X].is_temporal():
        return ORDER_CONTINUATION
    span = relations[X].max() - relations[X].min()
    return max(span * TIME_CONTINUATION, MIN_TIME_CONTINUATION)


def timestamp_before(relations: pl.DataFrame, level: BandLevel = "low") -> pl.DataFrame:
    """The location of each handling unit just before each of its timestamps.

    For hu and a timestamp t of its trace: ploc((m, hu)) of the movement m at t if there is one (unique by
    RQ3; it carries the provided pickup location), else ploc((e, hu)) of any relation at t (all equal:
    without a pickup location, ploc is before_loc, which only depends on the timestamp).

    Args:
        relations: Output of `timeline_relations`.
        level: "low" (ploc) or "high" (agg(ploc)).

    Returns:
        pl.DataFrame: One row per (hu, time) with the columns before (location, null = ⊥) and before_vehicle.
    """
    prev = PLOC if level == "low" else PREV_HIGH_LEVEL
    return (
        relations.sort(
            c.HU, c.TIME, pl.col(c.IS_MOVEMENT).fill_null(False).not_(), c.EVENT
        )
        .group_by(c.HU, c.TIME, maintain_order=True)
        .agg(
            pl.col(prev).first().alias("before"),
            pl.col(PREV_IS_VEHICLE).first().alias("before_vehicle"),
        )
    )


def band_segments(
    relations: pl.DataFrame, level: BandLevel = "low", reach=None
) -> pl.DataFrame:
    """The coloured stretches of the low-level or high-level band of every handling unit.

    Per handling unit with relations r_1, ..., r_n in trace order (x increasing):
    - after r_j, the band shows loc(r_j) up to r_{j+1} (only loc, Nina 2026-10-31: a pickup location that
      disagrees is marked on the movement instead, see `add_pickup_differs`);
    - lead-in: if the location before the first timestamp is known and the handling unit is not produced at
      it, the band starts `reach` before r_1 with that location;
    - continuation: after r_n, the band goes on for `reach` with loc(r_n), unless the handling unit is
      consumed at r_n (then it ends there);
    - stretches at ⊥ are left out (gaps), neighbouring stretches with the same location and vehicle status
      are merged.
    On the high-level band, agg(loc) (and agg(ploc) for the lead-in) is used instead; vehicle status is that of the
    underlying low-level location, so a high-level stretch is hatched where the handling unit is on a vehicle.

    Args:
        relations: Output of `timeline_relations`.
        level: "low" (loc) or "high" (agg(loc)).
        reach: Length of lead-in and continuation, in x units (positions or a timedelta); None = `continuation`.

    Returns:
        pl.DataFrame: One row per stretch: hu, hu_order, level, location, is_vehicle, x0, x1, sorted by hu_order, x0.
    """
    if reach is None:
        reach = continuation(relations)
    now = LOC if level == "low" else HIGH_LEVEL
    if not relations.schema[X].is_temporal():
        relations = relations.with_columns(pl.col(X).cast(pl.Float64))
    rel = relations.sort(HU_ORDER, POSITION).join(
        timestamp_before(relations, level),
        on=[c.HU, c.TIME],
        how="left",
        maintain_order="left",
    )
    rel = rel.with_columns(
        pl.col(X).shift(-1).over(c.HU).alias("_x_next"),
        (pl.int_range(pl.len()).over(c.HU) == 0).alias("_first"),
        pl.col(IS_PRODUCED).any().over(c.HU, c.TIME).alias("_produced_at_t"),
    )
    keys = [c.HU, HU_ORDER]
    after = rel.select(
        *keys,
        pl.col(now).alias("location"),
        pl.col(IS_VEHICLE).alias("is_vehicle"),
        pl.col(X).alias("x0"),
        pl.when(pl.col("_x_next").is_null())
        .then(pl.when(pl.col(IS_CONSUMED)).then(pl.col(X)).otherwise(pl.col(X) + reach))
        .otherwise(pl.col("_x_next"))
        .alias("x1"),
    )
    lead_in = rel.filter(
        pl.col("_first") & pl.col("before").is_not_null() & ~pl.col("_produced_at_t")
    ).select(
        *keys,
        pl.col("before").alias("location"),
        pl.col("before_vehicle").alias("is_vehicle"),
        (pl.col(X) - reach).alias("x0"),
        pl.col(X).alias("x1"),
    )
    pieces = (
        pl.concat([lead_in, after])
        .filter(pl.col("location").is_not_null() & (pl.col("x1") > pl.col("x0")))
        .sort(HU_ORDER, "x0")
    )
    # Merge touching stretches of one handling unit with the same location and vehicle status.
    new = (
        pl.col("location").ne_missing(pl.col("location").shift(1))
        | pl.col("is_vehicle").ne_missing(pl.col("is_vehicle").shift(1))
        | (pl.col("x0") != pl.col("x1").shift(1))
    ).fill_null(True)
    return (
        pieces.with_columns(new.over(c.HU).cum_sum().over(c.HU).alias("_run"))
        .group_by(*keys, "_run", maintain_order=True)
        .agg(
            pl.col("location").first(),
            pl.col("is_vehicle").first(),
            pl.col("x0").first(),
            pl.col("x1").last(),
        )
        .drop("_run")
        .with_columns(pl.lit(level).alias("level"))
        .select(*keys, "level", "location", "is_vehicle", "x0", "x1")
    )


def tie_groups(relations: pl.DataFrame) -> pl.DataFrame:
    """Timestamps shared by several shown events (over all shown handling units).

    Args:
        relations: Output of `timeline_relations`.

    Returns:
        pl.DataFrame: One row per such timestamp: time, x0 and x1 (x of its first and last event),
        events (the tied event ids in x order, comma-separated), n (number of events); sorted by time.
    """
    return (
        relations.select(c.TIME, c.EVENT, X)
        .unique()
        .sort(X, c.EVENT)
        .group_by(c.TIME, maintain_order=True)
        .agg(
            pl.col(X).min().alias("x0"),
            pl.col(X).max().alias("x1"),
            pl.col(c.EVENT).str.join(", ").alias("events"),
            pl.len().alias("n"),
        )
        .filter(pl.col("n") > 1)
        .sort(c.TIME)
    )


def shared_events(relations: pl.DataFrame) -> pl.DataFrame:
    """Events shared by several shown handling units.

    Args:
        relations: Output of `timeline_relations`.

    Returns:
        pl.DataFrame: One row per shared event: event, x, hus (list, in row order), n; sorted by x.
    """
    return (
        relations.sort(HU_ORDER)
        .group_by(c.EVENT)
        .agg(pl.col(X).first(), pl.col(c.HU).alias("hus"), pl.len().alias("n"))
        .filter(pl.col("n") > 1)
        .sort(X, c.EVENT)
    )


def lifespans(relations: pl.DataFrame) -> pl.DataFrame:
    """First and last x of every shown handling unit (its lifespan line).

    Args:
        relations: Output of `timeline_relations`.

    Returns:
        pl.DataFrame: One row per handling unit: hu, hu_order, object_type, x0, x1; sorted by hu_order.
    """
    return (
        relations.group_by(c.HU, HU_ORDER)
        .agg(
            pl.col(c.OBJECT_TYPE).first(),
            pl.col(X).min().alias("x0"),
            pl.col(X).max().alias("x1"),
        )
        .sort(HU_ORDER)
    )


def _relation_hover(row: dict) -> str:
    """Hover text of one event marker.

    Args:
        row: A row of `timeline_relations`.

    Returns:
        str: HTML hover text.
    """
    kinds = [
        name
        for name, flag in (
            ("movement", row[c.IS_MOVEMENT]),
            ("processing", row[IS_PROCESSING]),
            ("transformation", row[c.IS_TRANSFORMATION]),
        )
        if flag
    ]
    role = f": {row[ROLE]}" if row[ROLE] else ""
    vehicle = " (vehicle)" if row[IS_VEHICLE] else ""
    differs = (
        f"<br><i>pickup location {row[PLOC]} ≠ location after the previous event {row[PREV_LOC]}</i>"
        if row.get(PICKUP_DIFFERS)
        else ""
    )
    return (
        f"<b>{row[c.ACTIVITY]}</b> ({row[c.EVENT]}){' · ' + ', '.join(kinds) if kinds else ''}<br>"
        f"{row[c.HU]}{role}<br>{row[c.TIME]:%Y-%m-%d %H:%M:%S}<br>"
        f"ploc: {row[PLOC] or NOT_LOCATED} → loc: {row[LOC] or NOT_LOCATED}{vehicle}<br>"
        f"high-level: {row[PREV_HIGH_LEVEL] or NOT_LOCATED} → {row[HIGH_LEVEL] or NOT_LOCATED}"
        f"{differs}"
    )


def _span(x0, x1) -> float:
    """Length of a stretch as a bar length: positions, or milliseconds on a time axis.

    Args:
        x0: Start (number or datetime).
        x1: End (number or datetime).

    Returns:
        float: x1 - x0 in positions or milliseconds.
    """
    d = x1 - x0
    return d.total_seconds() * 1000 if isinstance(d, timedelta) else float(d)


def object_timeline(
    relations: pl.DataFrame,
    show_high_level: bool = True,
    show_activity_labels: bool = True,
    mark_ties: bool = True,
    link_shared_events: bool = True,
    reach=None,
    title: str | None = None,
    width: int = WIDTH,
) -> go.Figure:
    """Draw the object timeline of the prepared relations.

    Per handling unit (one row, top to bottom by hu_order; y label: id and object type):
    - the band: upper half loc, lower half agg(loc) (whole height if `show_high_level` is False), see
      `band_segments`; one colour per location (low and high level share the colour map), hatched on vehicles;
    - the lifespan line just below the band, with a tick at the first and the last event;
    - markers: processing operations are stars, other events that are not movements circles, both above
      the band with the activity name written at an angle; movements sit on the band: a vertical tick (a
      small open diamond if the pickup location differs from the previous location, see
      `add_pickup_differs`; details in the hover), or ▲/▼ if the handling unit is produced/consumed there;
      a processing movement is a star on the band;
      colour by role: produced green, consumed pink, consumed and produced amber, none dark grey.
    Dotted lines join the markers of an event shared by several handling units (`link_shared_events`), and
    events with the same timestamp get a light grey box over the whole height (`mark_ties`).

    Args:
        relations: Output of `timeline_relations`.
        show_high_level: Draw the high-level band (lower half of the band).
        show_activity_labels: Write the activity name above every marker that is not on the band.
        mark_ties: Grey boxes behind events with the same timestamp.
        link_shared_events: Dotted lines joining shared events.
        reach: Length of band lead-ins and continuations (see `band_segments`); None = default.
        title: Figure title.
        width: Figure width in pixels.

    Returns:
        go.Figure: The figure.
    """
    is_time = relations.schema[X].is_temporal()
    if reach is None:
        reach = continuation(relations)
    lives = lifespans(relations)
    labelled = show_activity_labels and (relations[MARKER] != "movement").any()
    gap = LABELLED_ROW_GAP if labelled else ROW_GAP
    n = lives.height
    row_y = {
        hu: (n - 1 - i) * gap for hu, i in lives.select(c.HU, HU_ORDER).iter_rows()
    }
    split = (BAND_TOP + BAND_BOTTOM) / 2
    band = {
        "low": ((BAND_TOP + split) / 2, BAND_TOP - split)
        if show_high_level
        else ((BAND_TOP + BAND_BOTTOM) / 2, BAND_TOP - BAND_BOTTOM),
        "high": ((split + BAND_BOTTOM) / 2, split - BAND_BOTTOM),
    }
    on_band_y = split if show_high_level else (BAND_TOP + BAND_BOTTOM) / 2

    segments = [band_segments(relations, "low", reach)]
    if show_high_level:
        segments.append(band_segments(relations, "high", reach))
    segments = pl.concat(segments)
    # Colours ranked by the relations, as in the trace figure, so both figures colour a log alike.
    # (locations only seen as ploc are added at the end).
    names = relations[LOC].to_list() + relations[HIGH_LEVEL].to_list()
    colours = location_colours(names, CATEGORICAL)
    for name in segments["location"].unique().sort().to_list():
        colours.setdefault(name, CATEGORICAL[len(colours) % len(CATEGORICAL)])

    fig = go.Figure()
    shapes: list[dict] = []
    annotations: list[dict] = []

    # Lifespan lines with end ticks.
    life_x, life_y, tick_x, tick_y = [], [], [], []
    for r in lives.iter_rows(named=True):
        y = row_y[r[c.HU]]
        life_x += [r["x0"], r["x1"], None]
        life_y += [y + BAND_BOTTOM - LIFESPAN_OFFSET] * 2 + [None]
        for x in (r["x0"], r["x1"]):
            tick_x += [x, x, None]
            tick_y += [
                y + BAND_BOTTOM - 2 * LIFESPAN_OFFSET,
                y + BAND_TOP + LIFESPAN_OFFSET,
                None,
            ]
    for xs, ys, colour in ((life_x, life_y, GREY), (tick_x, tick_y, TICK)):
        fig.add_trace(
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines",
                line={"color": colour, "width": 2},
                hoverinfo="skip",
                showlegend=False,
            )
        )

    # Bands: one bar trace per location name, low and high level together.
    for name in dict.fromkeys(
        segments.sort("level", descending=True)["location"].to_list()
    ):
        items = segments.filter(pl.col("location") == name)
        fig.add_trace(
            go.Bar(
                orientation="h",
                name=name,
                legendgroup="location",
                legendgrouptitle_text="location",
                y=[
                    row_y[hu] + band[lvl][0]
                    for hu, lvl in items.select(c.HU, "level").iter_rows()
                ],
                base=items["x0"].to_list(),
                x=[_span(a, b) for a, b in items.select("x0", "x1").iter_rows()],
                width=[band[lvl][1] for lvl in items["level"].to_list()],
                text=[name] * items.height,
                textposition="inside",
                insidetextanchor="middle",
                textfont={"size": 10, "color": "white"},
                marker={
                    "color": colours[name],
                    "line": {"width": 0},
                    "pattern": VEHICLE_PATTERN
                    | {
                        "shape": [
                            "/" if v else "" for v in items["is_vehicle"].to_list()
                        ]
                    },
                },
                customdata=[
                    f"<b>{name}</b>{' (high-level)' if lvl == 'high' else ''}{' · vehicle' if v else ''}<br>{hu}"
                    for hu, lvl, v in items.select(
                        c.HU, "level", "is_vehicle"
                    ).iter_rows()
                ],
                hovertemplate="%{customdata}<extra></extra>",
            )
        )
    if segments["is_vehicle"].any():
        fig.add_trace(
            go.Bar(
                orientation="h",
                name="vehicle",
                x=[None],
                y=[None],
                marker={"color": GREY, "pattern": VEHICLE_PATTERN},
                hoverinfo="skip",
            )
        )

    # Event markers.
    rel = relations.with_columns(
        pl.Series(
            "_hover",
            [_relation_hover(r) for r in relations.iter_rows(named=True)],
            dtype=pl.String,
        ),
        pl.col(c.HU).replace_strict(row_y, return_dtype=pl.Float64).alias("_row"),
    ).with_columns(
        (
            pl.col("_row")
            + pl.when(pl.col(c.IS_MOVEMENT).fill_null(False))
            .then(on_band_y)
            .otherwise(MARKER_Y)
        ).alias("_y")
    )
    if PICKUP_DIFFERS not in rel.columns:
        rel = rel.with_columns(pl.lit(False).alias(PICKUP_DIFFERS))
    # A plain movement tick whose pickup location differs gets its own (subtle) symbol.
    differs = (
        (pl.col(MARKER) == "movement") & pl.col(ROLE).is_null() & pl.col(PICKUP_DIFFERS)
    )
    for (marker, role), part in (
        rel.filter(~differs)
        .sort(MARKER, ROLE, nulls_last=True)
        .group_by(MARKER, ROLE, maintain_order=True)
    ):
        colour = ROLE_COLOUR.get(role, NO_ROLE_COLOUR)
        label = f"{marker}{': ' + role if role else ''}"
        if marker == "movement" and role:
            # Production ▲ above, consumption ▼ below the band's middle; both: one of each.
            for kind, symbol, dy in (
                (PRODUCED, "triangle-up", 0.07),
                (CONSUMED, "triangle-down", -0.07),
            ):
                if role not in (kind, BOTH):
                    continue
                fig.add_trace(
                    go.Scatter(
                        x=part[X],
                        y=part["_y"] + (dy if role == BOTH else 0),
                        mode="markers",
                        name=f"movement: {kind}",
                        legendgroup="event",
                        legendgrouptitle_text="event",
                        marker={
                            "symbol": symbol,
                            "size": 14,
                            "color": ROLE_COLOUR[kind],
                            "line": {"width": 1, "color": "white"},
                        },
                        customdata=part["_hover"],
                        hovertemplate="%{customdata}<extra></extra>",
                    )
                )
            continue
        line = (
            {"width": 2.5, "color": TICK}
            if marker == "movement"
            else {"width": 0.5, "color": "white"}
        )
        fig.add_trace(
            go.Scatter(
                x=part[X],
                y=part["_y"],
                mode="markers",
                name=label,
                legendgroup="event",
                legendgrouptitle_text="event",
                marker={
                    "symbol": SYMBOL[marker],
                    "size": SIZE[marker],
                    "color": colour,
                    "line": line,
                },
                customdata=part["_hover"],
                hovertemplate="%{customdata}<extra></extra>",
            )
        )
    flagged = rel.filter(differs)
    if flagged.height:
        fig.add_trace(
            go.Scatter(
                x=flagged[X],
                y=flagged["_y"],
                mode="markers",
                name="movement: pickup ≠ previous location",
                legendgroup="event",
                legendgrouptitle_text="event",
                marker={
                    "symbol": PICKUP_DIFFERS_SYMBOL,
                    "size": PICKUP_DIFFERS_SIZE,
                    "color": TICK,
                    "line": {"width": 1.5, "color": TICK},
                },
                customdata=flagged["_hover"],
                hovertemplate="%{customdata}<extra></extra>",
            )
        )
    if labelled:
        for x, y, activity in (
            rel.filter(~pl.col(c.IS_MOVEMENT).fill_null(False))
            .select(X, "_y", c.ACTIVITY)
            .iter_rows()
        ):
            annotations.append(
                {
                    "x": x,
                    "y": y,
                    "text": activity,
                    "textangle": LABEL_ANGLE,
                    "showarrow": False,
                    "xanchor": "left",
                    "yanchor": "bottom",
                    "xshift": 2,
                    "yshift": 7,
                    "font": {"size": 9, "color": "#495057"},
                }
            )

    # Shared events: dotted lines between the markers of the same event.
    if link_shared_events:
        links = (
            rel.group_by(c.EVENT)
            .agg(
                pl.col(X).first(),
                pl.col("_y").min().alias("y0"),
                pl.col("_y").max().alias("y1"),
                pl.len().alias("n"),
            )
            .filter(pl.col("n") > 1)
        )
        xs, ys = [], []
        for x, y0, y1 in links.select(X, "y0", "y1").iter_rows():
            xs += [x, x, None]
            ys += [y0, y1, None]
        if xs:
            fig.add_trace(
                go.Scatter(
                    x=xs,
                    y=ys,
                    mode="lines",
                    line={"color": LINE, "width": 1, "dash": "dot"},
                    hoverinfo="skip",
                    showlegend=False,
                )
            )

    # Same timestamp: light grey boxes over the whole height.
    ties = tie_groups(relations)
    if mark_ties and ties.height:
        if is_time:
            times = relations[X].unique().sort()
            step = (
                times.diff().drop_nulls().min()
                if times.len() > 1
                else timedelta(hours=1)
            )
            pad = max(step, timedelta(seconds=1)) * TIE_PAD
        else:
            pad = TIE_PAD
        for r in ties.iter_rows(named=True):
            shapes.append(
                {
                    "type": "rect",
                    "x0": r["x0"] - pad,
                    "x1": r["x1"] + pad,
                    "yref": "paper",
                    "y0": 0,
                    "y1": 1,
                    "line": {"width": 0},
                    "fillcolor": TIE_FILL,
                    "layer": "below",
                }
            )
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                name="same timestamp",
                marker={"symbol": "square", "size": 14, "color": TIE_FILL},
                hoverinfo="skip",
            )
        )

    top = (n - 1) * gap + MARKER_Y + 0.3 + (LABEL_ROOM if labelled else 0)
    bottom = BAND_BOTTOM - 0.35
    fig.update_layout(
        title=title,
        width=width,
        height=int(170 + (top - bottom) * PX_PER_UNIT),
        barmode="overlay",
        hovermode="closest",
        template="plotly_white",
        uniformtext={"minsize": 8, "mode": "hide"},
        shapes=shapes,
        annotations=annotations,
        legend={"groupclick": "toggleitem", "tracegroupgap": 12},
        margin={"l": 10, "r": 10, "t": 70 if title else 30, "b": 10},
        hoverlabel={"align": "left"},
    )
    fig.update_yaxes(
        tickvals=list(row_y.values()),
        ticktext=[
            f"<b>{hu}</b><br>({t})"
            for hu, t in lives.select(c.HU, c.OBJECT_TYPE).iter_rows()
        ],
        range=[bottom, top],
        showgrid=False,
        zeroline=False,
        automargin=True,
    )
    x_lo, x_hi = segments["x0"].min(), segments["x1"].max()
    x_lo = min(x_lo, relations[X].min()) if x_lo is not None else relations[X].min()
    x_hi = max(x_hi, relations[X].max()) if x_hi is not None else relations[X].max()
    margin = reach * 0.5
    if is_time:
        fig.update_xaxes(
            type="date",
            title="time",
            range=[x_lo - margin, x_hi + margin],
            automargin=True,
        )
    else:
        # One tick per timestamp, at the middle of its (tied) events, labelled with the timestamp.
        ticks = relations.group_by(c.TIME).agg(pl.col(X).mean()).sort(c.TIME)
        fig.update_xaxes(
            title="event order (ticks: timestamps)",
            tickvals=ticks[X].to_list(),
            ticktext=[f"{t:%Y-%m-%d %H:%M}" for t in ticks[c.TIME].to_list()],
            tickangle=-90,
            tickfont={"size": 10},
            range=[x_lo - margin, x_hi + margin],
            showgrid=True,
            zeroline=False,
            automargin=True,
        )
    return fig
