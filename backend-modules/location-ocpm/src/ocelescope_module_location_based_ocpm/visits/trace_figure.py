"""Trace figure: object traces of several handling units with their low-level and high-level locations,
and optionally visits drawn as bars below each trace.

Draft for the visit conceptualisation (`overview/Single Level Visit Mappings.md`); not used by any page yet.
Documented in `docs/resources/trace-figure.md`.

The figure is built in small steps, each a function of its own:
1. `add_high_level_locations`: hat-hl, the high-level location of every relation (agg, completed by identity).
2. `add_location_kinds`: whether a relation's location is a vehicle (V), a storage unit (W) or neither.
3. `add_x_positions`: trace position (position in otrace(hu)) and the x value for the chosen axis.
4. `location_colours`: one colour per location name, ranked by frequency in the figure.
5. `visit_lanes`: places visits in lanes so that visits sharing relations do not overlap.
6. `trace_figure`: draws everything.
`relations_for_figure` runs steps 1 to 3 on a relations frame (a saved location mapping or `Derivation.relations`).
"""

from collections.abc import Collection, Mapping
from datetime import timedelta
from typing import Literal

import plotly.graph_objects as go
import polars as pl

from ..derivation import columns as c

#: Axis options: position in the handling unit's own trace (as in the visit definition), order of all
#: shown events (shared events line up vertically), or real time.
Axis = Literal["trace position", "event order", "time"]

#: Column of the high-level location hat-hl((e, hu)); null = ⊥.
HIGH_LEVEL = "high_level"
#: Column of the location kind: "vehicle", "storage" or "other"; null if the location is ⊥.
KIND = "location_kind"
#: Column of the position of the relation in otrace(hu), starting at 1.
POSITION = "position"
#: Optional column giving the order of the handling units in the figure (top to bottom).
HU_ORDER = "hu_order"
#: Column of the x value of the relation in the figure.
X = "x"

#: Categorical colours of the module palette (light scheme, `frontend-modules/.../lib/palette.ts`, CATEGORICAL).
CATEGORICAL = (
    "#0098A1",
    "#d98b09",
    "#CE108A",
    "#5291cc",
    "#88375e",
    "#00549F",
    "#007e56",
    "#cd00cd",
    "#f897e5",
    "#7bd591",
    "#1e4729",
    "#73c9fb",
    "#b8758d",
    "#595dec",
    "#8602a8",
    "#fe579d",
    "#2d11a7",
    "#ea5efe",
    "#deb58f",
    "#572069",
    "#9953ab",
    "#977d3c",
    "#55af6d",
    "#616c98",
)
#: Colour of ⊥ (palette OTHER).
GREY = "#adb5bd"
#: Colour of guide lines.
GUIDE = "#ced4da"
#: Label of ⊥ in legends and hovers.
NOT_LOCATED = "⊥ (not located)"

#: Marker symbol of a low-level location by kind (vehicles open, storage units diamonds).
LOW_SYMBOL = {"vehicle": "circle-open", "storage": "diamond", "other": "circle"}
#: Marker symbol of a high-level location.
HIGH_SYMBOL = "square"
#: Marker symbol of ⊥ (both levels).
BOTTOM_SYMBOL = "x-thin-open"

# Vertical layout, in y units: the low-level row of a handling unit is at its row y, the high-level
# row HIGH_OFFSET below it, the visit lanes below that, LANE apart; GAP separates handling units.
HIGH_OFFSET = 0.32
LANE = 0.42
BAR = 0.3
GAP = 0.75
#: Height of the event labels above the low-level row.
LABEL_OFFSET = 0.1
#: Height of a high-level ribbon ("ribbon" style) and of a high-level shading box ("shading" style).
RIBBON = 0.14
SHADE = 0.34
#: Colour and width of the trace line.
TRACE = "#adb5bd"
TRACE_WIDTH = 2
#: Default figure width in pixels; also used to decide whether a run label fits its ribbon or box.
WIDTH = 1200
#: Horizontal space taken by the y labels, margins and legend, in pixels (estimate).
NON_PLOT_WIDTH = 110 + 20 + 160
#: Estimated width of one character of a run label (bold, size 10) and the padding around it, in pixels.
CHAR_PX = 7
LABEL_PADDING_PX = 6
#: Time axis: share of the smallest gap between timestamps over which events with the same timestamp are spread.
TIE_SPREAD = 0.5
#: Pixels per y unit.
PX_PER_UNIT = 70
#: Fill of the background box behind events with the same timestamp (very light, very transparent grey).
TIE_FILL = "rgba(134, 142, 150, 0.12)"


def add_high_level_locations(
    relations: pl.DataFrame,
    location: str,
    agg: Mapping[str, str] | None = None,
    high_level: str = HIGH_LEVEL,
) -> pl.DataFrame:
    """Add hat-hl((e, hu)) = agg(loc((e, hu))) if loc((e, hu)) ≠ ⊥, else ⊥.

    `agg` may be partial: locations it does not map are their own high-level location (identity),
    as in the note's todo "auto-complete via identity function".

    Args:
        relations: One row per hu-event relation with the column `location` (null = ⊥).
        location: Column of the low-level location, e.g. "loc_3".
        agg: Low-level location -> high-level location; None = identity for all.
        high_level: Name of the new column.

    Returns:
        pl.DataFrame: `relations` with the column `high_level` (null where `location` is null).
    """
    expr = pl.col(location)
    if agg:
        expr = expr.replace(dict(agg))
    return relations.with_columns(expr.alias(high_level))


def add_location_kinds(
    relations: pl.DataFrame,
    location: str,
    vehicles: Collection[str] = (),
    storage_units: Collection[str] = (),
    kind: str = KIND,
) -> pl.DataFrame:
    """Add whether the low-level location of a relation is a vehicle (V), a storage unit (W) or neither.

    A location in both V and W (violating RQ4) counts as a vehicle, as in the note.

    Args:
        relations: Relations frame with the column `location`.
        location: Column of the low-level location.
        vehicles: The set V.
        storage_units: The set W.
        kind: Name of the new column.

    Returns:
        pl.DataFrame: `relations` with the column `kind` ("vehicle", "storage", "other"; null for ⊥).
    """
    loc = pl.col(location)
    return relations.with_columns(
        pl.when(loc.is_null())
        .then(None)
        .when(loc.is_in(list(vehicles)))
        .then(pl.lit("vehicle"))
        .when(loc.is_in(list(storage_units)))
        .then(pl.lit("storage"))
        .otherwise(pl.lit("other"))
        .alias(kind)
    )


def add_x_positions(
    relations: pl.DataFrame, axis: Axis = "event order"
) -> pl.DataFrame:
    """Add the trace position of every relation and its x value for the chosen axis.

    The trace position is the index in otrace(hu), ordered by time and then event id (as `seq`).

    Args:
        relations: Relations frame with columns hu, event, time (only the handling units to show), and
            optionally hu_order (order of the handling units; else they are sorted by id).
        axis: "trace position" (x = trace position), "event order" (x = rank of the event among all
            shown events, so an event shared by several handling units has one x), or "time".

    Returns:
        pl.DataFrame: `relations` sorted by handling unit, time, event, with columns position and x.
    """
    order = HU_ORDER if HU_ORDER in relations.columns else c.HU
    out = relations.sort(order, c.TIME, c.EVENT).with_columns(
        (pl.int_range(pl.len()).over(c.HU) + 1).alias(POSITION)
    )
    if axis == "trace position":
        x = pl.col(POSITION)
    elif axis == "event order":
        x = pl.struct(c.TIME, c.EVENT).rank("dense")
    else:
        return add_tie_offsets(out)
    return out.with_columns(x.alias(X))


def add_tie_offsets(
    relations: pl.DataFrame, spread: float = TIE_SPREAD
) -> pl.DataFrame:
    """Time axis: x = time, with events that share a timestamp spread slightly around it.

    Without the spread, events at the same timestamp would be drawn on top of each other.
    The tied events of a timestamp (all shown events, so a shared event keeps one x) are placed side
    by side in event id order (as `seq`), centred on the timestamp, together spanning at most `spread`
    times the smallest gap between two distinct timestamps.

    Args:
        relations: Relations frame with columns event and time.
        spread: Share of the smallest gap between timestamps that the tied events of one timestamp span.

    Returns:
        pl.DataFrame: `relations` with column x (datetime).
    """
    times = relations[c.TIME].unique().sort()
    gaps = times.diff().drop_nulls()
    gap = gaps.min() if len(gaps) else timedelta(hours=1)
    ties = (
        relations.select(c.TIME, c.EVENT)
        .unique()
        .with_columns(
            (pl.col(c.EVENT).rank("dense").over(c.TIME) - 1).alias("_i"),
            pl.col(c.EVENT).n_unique().over(c.TIME).alias("_n"),
        )
    )
    max_n = ties["_n"].max() if ties.height else 1
    step = gap * spread / max(max_n - 1, 1)
    ties = ties.with_columns(
        (pl.col(c.TIME) + (pl.col("_i") - (pl.col("_n") - 1) / 2) * pl.lit(step)).alias(
            X
        )
    ).select(c.TIME, c.EVENT, X)
    return relations.join(ties, on=[c.TIME, c.EVENT], how="left", maintain_order="left")


def relations_for_figure(
    relations: pl.DataFrame,
    location: str = "loc",
    handling_units: Collection[str] | None = None,
    agg: Mapping[str, str] | None = None,
    vehicles: Collection[str] = (),
    storage_units: Collection[str] = (),
    axis: Axis = "event order",
) -> pl.DataFrame:
    """Prepare the relations of some handling units for `trace_figure` (steps 1 to 3).

    Args:
        relations: One row per hu-event relation with columns hu, object_type, event, time, activity,
            is_movement, is_transformation and `location`, e.g. a saved location mapping of one level, or
            `Derivation.relations`.
        location: Column of the current location loc (e.g. "loc", or `Derivation.loc`).
        handling_units: Handling units to show, in this order; None = all.
        agg: Location mapping (see `add_high_level_locations`).
        vehicles: The set V.
        storage_units: The set W.
        axis: See `add_x_positions`.

    Returns:
        pl.DataFrame: Columns hu, hu_order, object_type, event, time, activity, is_movement, is_transformation, loc,
        high_level, location_kind, position, x.
    """
    if handling_units is not None:
        order = {hu: i for i, hu in enumerate(handling_units)}
        relations = relations.filter(pl.col(c.HU).is_in(list(order))).with_columns(
            pl.col(c.HU).replace_strict(order, return_dtype=pl.Int64).alias(HU_ORDER)
        )
    else:
        relations = relations.with_columns(
            pl.col(c.HU).rank("dense").cast(pl.Int64).alias(HU_ORDER)
        )
    relations = relations.select(
        c.HU,
        HU_ORDER,
        c.OBJECT_TYPE,
        c.EVENT,
        c.TIME,
        c.ACTIVITY,
        c.IS_MOVEMENT,
        c.IS_TRANSFORMATION,
        pl.col(location).alias("loc"),
    )
    relations = add_high_level_locations(relations, "loc", agg)
    relations = add_location_kinds(relations, "loc", vehicles, storage_units)
    return add_x_positions(relations, axis)


def location_colours(
    names: list[str | None], palette: tuple[str, ...] = CATEGORICAL
) -> dict[str, str]:
    """One colour per location name, the most frequent name first (ties alphabetically).

    Low-level and high-level locations share one colour map, so a high-level location that is
    its own low-level location (identity) gets the same colour on both rows.

    Args:
        names: All location names shown (with repetitions; None = ⊥ is ignored).
        palette: Colours in rank order; repeated cyclically if there are more names.

    Returns:
        dict[str, str]: Location name -> colour.
    """
    counts = pl.Series(
        "name", [n for n in names if n is not None], dtype=pl.String
    ).value_counts()
    ranked = counts.sort(["count", "name"], descending=[True, False])["name"].to_list()
    return {name: palette[i % len(palette)] for i, name in enumerate(ranked)}


def visit_lanes(visits: pl.DataFrame) -> pl.DataFrame:
    """Place visits in lanes (greedy interval packing), so that visits in one lane share no relation.

    Done per handling unit and visit group; visits are taken by first position, then by length
    (longer first, so a containing visit lies above the visits it contains).

    Args:
        visits: Columns hu, group, first_position, last_position.

    Returns:
        pl.DataFrame: `visits` with the column lane (0 = closest to the trace).
    """
    rows = visits.with_row_index("_row").sort(
        "hu",
        "group",
        "first_position",
        "last_position",
        descending=[False, False, False, True],
    )
    lanes: list[int] = []
    ends: dict[tuple[str, str], list[int]] = {}
    for hu, group, first, last in rows.select(
        "hu", "group", "first_position", "last_position"
    ).iter_rows():
        lane_ends = ends.setdefault((hu, group), [])
        lane = next(
            (i for i, end in enumerate(lane_ends) if end < first), len(lane_ends)
        )
        if lane == len(lane_ends):
            lane_ends.append(last)
        else:
            lane_ends[lane] = last
        lanes.append(lane)
    return rows.with_columns(pl.Series("lane", lanes)).sort("_row").drop("_row")


def _visit_positions(visits: pl.DataFrame, relations: pl.DataFrame) -> pl.DataFrame:
    """Add first/last trace position and x of each visit from its first and last event.

    Args:
        visits: Columns hu, high_level, first_event, last_event, group.
        relations: Output of `relations_for_figure`.

    Returns:
        pl.DataFrame: `visits` with first_position, last_position, x0, x1 (visits of hidden handling units dropped).
    """
    ends = relations.select(c.HU, c.EVENT, POSITION, X)
    return visits.join(
        ends.rename({c.EVENT: "first_event", POSITION: "first_position", X: "x0"}),
        on=[c.HU, "first_event"],
    ).join(
        ends.rename({c.EVENT: "last_event", POSITION: "last_position", X: "x1"}),
        on=[c.HU, "last_event"],
    )


def _relation_hover(row: dict) -> str:
    """Hover text of one relation.

    Args:
        row: A row of `relations_for_figure`.

    Returns:
        str: HTML hover text.
    """
    roles = [
        name
        for name, flag in (
            ("movement", row[c.IS_MOVEMENT]),
            ("transformation", row[c.IS_TRANSFORMATION]),
        )
        if flag
    ]
    kind = f" ({row[KIND]})" if row[KIND] in ("vehicle", "storage") else ""
    return (
        f"<b>{row[c.EVENT]}</b> · {row[c.ACTIVITY]}{' · ' + ', '.join(roles) if roles else ''}<br>"
        f"{row[c.HU]}, trace position {row[POSITION]}, {row[c.TIME]:%Y-%m-%d %H:%M}<br>"
        f"location: {row['loc'] or NOT_LOCATED}{kind}<br>high-level location: {row[HIGH_LEVEL] or NOT_LOCATED}"
    )


def high_level_runs(relations: pl.DataFrame) -> pl.DataFrame:
    """Runs of consecutive relations of a handling unit with the same high-level location (⊥ runs left out).

    Args:
        relations: Output of `relations_for_figure` (sorted by handling unit and trace position).

    Returns:
        pl.DataFrame: One row per run: hu, high_level, x0 (x of its first relation), x1 (x of its last relation).
    """
    return (
        relations.with_columns(
            (
                pl.col(HIGH_LEVEL)
                .ne_missing(pl.col(HIGH_LEVEL).shift(1))
                .over(c.HU)
                .fill_null(True)
            )
            .cum_sum()
            .over(c.HU)
            .alias("_run")
        )
        .group_by(c.HU, "_run", maintain_order=True)
        .agg(
            pl.col(HIGH_LEVEL).first(),
            pl.col(X).first().alias("x0"),
            pl.col(X).last().alias("x1"),
        )
        .filter(pl.col(HIGH_LEVEL).is_not_null())
        .drop("_run")
    )


def _x_units(span) -> float:
    """A span on the x axis as a number: itself, or hours for a time span.

    Args:
        span: A number or a timedelta.

    Returns:
        float: The span in x units (hours on a time axis).
    """
    return span.total_seconds() / 3600 if isinstance(span, timedelta) else float(span)


def _tint(colour: str, alpha: float) -> str:
    """A hex colour as rgba with the given opacity.

    Args:
        colour: "#rrggbb".
        alpha: Opacity from 0 to 1.

    Returns:
        str: "rgba(r,g,b,alpha)".
    """
    r, g, b = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


#: How the high-level locations are drawn (see `trace_figure`).
HighLevelStyle = Literal["squares", "ribbon", "shading", "outline"]


def trace_figure(
    relations: pl.DataFrame,
    visits: pl.DataFrame | None = None,
    filled_groups: Collection[str] = ("resolved",),
    dashed_groups: Collection[str] = ("maximal",),
    high_level_style: HighLevelStyle = "ribbon",
    show_event_labels: bool = True,
    link_shared_events: bool = True,
    mark_ties: bool = True,
    title: str | None = None,
    width: int = WIDTH,
) -> go.Figure:
    """Draw the object traces of several handling units with their locations, and optionally visits.

    Per handling unit (top to bottom, in the order of first appearance in `relations`; y label: the
    handling unit and, below it, its object type in brackets):
    - the low-level row: one marker per relation at its x, coloured by loc (circle; open circle for
      vehicles, diamond for storage units; grey × for ⊥), joined by a line (the trace); the event id
      is written at an angle above each marker;
    - the high-level locations, drawn as chosen by `high_level_style`:
      "squares": a row of squares below, one per relation;
      "ribbon": a row below with one thick bar per run of relations with the same high-level location,
      labelled with its name;
      "shading": a tinted box behind the low-level row per run, labelled with its name (no extra row);
      "outline": the low-level markers get a thick ring in the high-level colour (no extra row);
    - below that, each visit group (e.g. "maximal", "resolved") in its own lanes: one bar per visit
      from its first to its last relation, outlined (or filled for `filled_groups`; outline dashed for
      `dashed_groups`), coloured by its location.
    Dashed vertical lines join the relations of an event shared by several shown handling units.
    Events with the same timestamp get a light grey background box (`mark_ties`): across the whole figure
    on the "event order" and "time" axes; per handling unit on the "trace position" axis, where the tied
    events of one handling unit sit next to each other but those of different units do not line up.

    Args:
        relations: Output of `relations_for_figure`.
        visits: Optional, one row per visit: hu, high_level, first_event, last_event, group.
        filled_groups: Visit groups drawn as filled bars; all others outlined.
        dashed_groups: Visit groups whose outline is dashed (e.g. maximal visits, to tell them apart
            from resolved ones); all others solid.
        high_level_style: See above.
        show_event_labels: Write the event id above every low-level marker.
        link_shared_events: Draw the lines joining shared events (not for the "trace position" axis,
            where a shared event has different x values).
        mark_ties: Draw the background boxes behind events with the same timestamp (needs column time).
        title: Figure title.
        width: Figure width in pixels. A run label ("ribbon", "shading") is only shown if it fits
            into its ribbon or box at this width; otherwise the legend and the hover name the location.

    Returns:
        go.Figure: The figure.
    """
    is_time = relations.schema[X].is_temporal()
    is_trace_position = not is_time and relations[X].equals(relations[POSITION])
    hus = relations[c.HU].unique(maintain_order=True).to_list()
    types = (
        dict(relations.select(c.HU, c.OBJECT_TYPE).unique().iter_rows())
        if c.OBJECT_TYPE in relations.columns
        else {}
    )
    names = relations["loc"].to_list() + relations[HIGH_LEVEL].to_list()
    if visits is not None:
        visits = visit_lanes(_visit_positions(visits, relations))
        names += visits[HIGH_LEVEL].to_list()
    colours = location_colours(names)
    runs = high_level_runs(relations)
    has_high_row = high_level_style in ("squares", "ribbon")

    # Half the width of a visit bar (and of a ribbon or shading) beyond its first and last relation, in x units.
    if is_time:
        times = relations[X].unique().sort()
        step = times.diff().drop_nulls().min() if len(times) > 1 else None
        pad = step * 0.4 if step else timedelta(hours=1)
    else:
        pad = 0.4
    x_min, x_max = relations[X].min() - 2 * pad, relations[X].max() + 2 * pad
    px_per_x = (width - NON_PLOT_WIDTH) / _x_units(x_max - x_min)

    def fits(text: str, x0, x1) -> bool:
        """Whether `text` fits into a ribbon or box from x0 - pad to x1 + pad."""
        return (
            len(text) * CHAR_PX + LABEL_PADDING_PX
            <= _x_units(x1 - x0 + 2 * pad) * px_per_x
        )

    fig = go.Figure()
    shapes: list[dict] = []
    annotations: list[dict] = []
    tickvals, ticktext = [], []
    row_y: dict[str, float] = {}
    row_bottom: dict[str, float] = {}
    y = 0.0
    shown_legend: set[str] = set()
    for hu in hus:
        rows = relations.filter(pl.col(c.HU) == hu)
        row_y[hu] = y
        tickvals.append(y)
        ticktext.append(
            f"<b>{hu}</b><br>({types[hu]})" if hu in types else f"<b>{hu}</b>"
        )
        high_y = y - HIGH_OFFSET
        bottom = high_y if has_high_row else y - HIGH_OFFSET / 2

        # High-level runs as ribbons (own row) or shading (behind the low-level row).
        for r in runs.filter(pl.col(c.HU) == hu).iter_rows(named=True):
            colour = colours[r[HIGH_LEVEL]]
            if high_level_style == "ribbon":
                shapes.append(
                    {
                        "type": "rect",
                        "x0": r["x0"] - pad,
                        "x1": r["x1"] + pad,
                        "y0": high_y - RIBBON / 2,
                        "y1": high_y + RIBBON / 2,
                        "line": {"width": 0},
                        "fillcolor": colour,
                        "layer": "below",
                    }
                )
                if fits(r[HIGH_LEVEL], r["x0"], r["x1"]):
                    annotations.append(
                        {
                            "x": r["x0"] - pad,
                            "y": high_y,
                            "xanchor": "left",
                            "text": f"<b>{r[HIGH_LEVEL]}</b>",
                            "showarrow": False,
                            "font": {"size": 10, "color": "white"},
                        }
                    )
            elif high_level_style == "shading":
                shapes.append(
                    {
                        "type": "rect",
                        "x0": r["x0"] - pad,
                        "x1": r["x1"] + pad,
                        "y0": y - SHADE / 2,
                        "y1": y + SHADE / 2,
                        "line": {"color": colour, "width": 1.5},
                        "fillcolor": _tint(colour, 0.18),
                        "layer": "below",
                    }
                )
                if fits(r[HIGH_LEVEL], r["x0"], r["x1"]):
                    annotations.append(
                        {
                            "x": r["x0"] - pad,
                            "y": y - SHADE / 2,
                            "xanchor": "left",
                            "yanchor": "bottom",
                            "text": f"<b>{r[HIGH_LEVEL]}</b>",
                            "showarrow": False,
                            "font": {"size": 10, "color": colour},
                        }
                    )

        # Visit bars, one block of lanes per group.
        if visits is not None:
            lane_top = bottom - LANE
            for group in (
                visits[["group"]].unique(maintain_order=True)["group"].to_list()
            ):
                own = visits.filter((pl.col(c.HU) == hu) & (pl.col("group") == group))
                if own.is_empty():
                    continue
                filled = group in filled_groups
                dash = "dash" if group in dashed_groups else "solid"
                for v in own.iter_rows(named=True):
                    centre = lane_top - v["lane"] * LANE
                    colour = colours.get(v[HIGH_LEVEL], GREY)
                    shapes.append(
                        {
                            "type": "rect",
                            "x0": v["x0"] - pad,
                            "x1": v["x1"] + pad,
                            "y0": centre - BAR / 2,
                            "y1": centre + BAR / 2,
                            "line": {"color": colour, "width": 2, "dash": dash},
                            "fillcolor": colour if filled else "rgba(0,0,0,0)",
                            "opacity": 0.8 if filled else 1,
                            "layer": "below",
                        }
                    )
                    fig.add_trace(
                        go.Scatter(
                            x=[v["x0"], v["x1"]],
                            y=[centre, centre],
                            mode="markers",
                            marker={"size": 12, "opacity": 0},
                            showlegend=False,
                            hovertemplate=(
                                f"<b>{hu}</b> at {v[HIGH_LEVEL]} ({group} visit)<br>"
                                f"{v['first_event']} to {v['last_event']}, trace positions "
                                f"{v['first_position']} to {v['last_position']}<extra></extra>"
                            ),
                        )
                    )
                n_lanes = own["lane"].max() + 1
                annotations.append(
                    {
                        "x": 0,
                        "xref": "paper",
                        "xanchor": "right",
                        "y": lane_top - (n_lanes - 1) * LANE / 2,
                        "text": f"<i>{group}</i>",
                        "showarrow": False,
                        "font": {"size": 10, "color": "#868e96"},
                    }
                )
                bottom = lane_top - (n_lanes - 1) * LANE
                lane_top = bottom - LANE

        # Guide lines from each relation down to the lowest lane.
        for x in rows[X].to_list():
            shapes.append(
                {
                    "type": "line",
                    "x0": x,
                    "x1": x,
                    "y0": y,
                    "y1": bottom,
                    "line": {"color": GUIDE, "width": 1, "dash": "dot"},
                    "layer": "below",
                }
            )

        # The trace line.
        fig.add_trace(
            go.Scatter(
                x=rows[X],
                y=[y] * rows.height,
                mode="lines",
                line={"color": TRACE, "width": TRACE_WIDTH},
                showlegend=False,
                hoverinfo="skip",
            )
        )
        # Markers: low-level row (and high-level row for "squares"); one trace per location, kind and level.
        hover = [_relation_hover(r) for r in rows.iter_rows(named=True)]
        rows = rows.with_columns(pl.Series("_hover", hover))
        for (name, kind, high), part in rows.group_by(
            "loc", KIND, HIGH_LEVEL, maintain_order=True
        ):
            if name is None:
                symbol, colour, label = BOTTOM_SYMBOL, GREY, NOT_LOCATED
            else:
                symbol, colour, label = LOW_SYMBOL[kind], colours[name], name
            ring = (
                colours.get(high, GREY)
                if high_level_style == "outline" and high is not None
                else colour
            )
            ring_width = (
                3.5 if high_level_style == "outline" and high is not None else 2
            )
            key = f"location|{label}"
            fig.add_trace(
                go.Scatter(
                    x=part[X],
                    y=[y] * part.height,
                    mode="markers",
                    marker={
                        "symbol": symbol,
                        "size": 13,
                        "color": colour,
                        "line": {"width": ring_width, "color": ring},
                    },
                    name=label,
                    legendgroup="location",
                    legendgrouptitle_text="location",
                    showlegend=key not in shown_legend,
                    customdata=part["_hover"],
                    hovertemplate="%{customdata}<extra></extra>",
                )
            )
            shown_legend.add(key)
        if high_level_style == "squares":
            for high, part in rows.group_by(HIGH_LEVEL, maintain_order=True):
                high = high[0]
                fig.add_trace(
                    go.Scatter(
                        x=part[X],
                        y=[high_y] * part.height,
                        mode="markers",
                        marker={
                            "symbol": BOTTOM_SYMBOL if high is None else HIGH_SYMBOL,
                            "size": 13,
                            "color": GREY if high is None else colours[high],
                            "line": {
                                "width": 2,
                                "color": GREY if high is None else colours[high],
                            },
                        },
                        showlegend=False,
                        customdata=part["_hover"],
                        hovertemplate="%{customdata}<extra></extra>",
                    )
                )
        elif high_level_style == "ribbon":
            fig.add_trace(
                go.Scatter(
                    x=rows[X],
                    y=[high_y] * rows.height,
                    mode="markers",
                    marker={"size": 12, "opacity": 0},
                    showlegend=False,
                    customdata=rows["_hover"],
                    hovertemplate="%{customdata}<extra></extra>",
                )
            )
        if show_event_labels:
            for x, event in rows.select(X, c.EVENT).iter_rows():
                annotations.append(
                    {
                        "x": x,
                        "y": y + LABEL_OFFSET,
                        "text": event,
                        "textangle": -40,
                        "showarrow": False,
                        "font": {"size": 10, "color": "#495057"},
                        "xanchor": "left",
                        "yanchor": "bottom",
                    }
                )
        row_bottom[hu] = bottom
        y = bottom - GAP

    # Legend entries of the high-level locations (one per name).
    high_symbol = {
        "squares": "square",
        "ribbon": "line-ew-open",
        "shading": "square",
        "outline": "circle-open",
    }[high_level_style]
    for name in runs[HIGH_LEVEL].unique(maintain_order=True).to_list():
        colour = colours[name]
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                name=name,
                marker={
                    "symbol": high_symbol,
                    "size": 12,
                    "line": {
                        "width": 4 if high_level_style == "ribbon" else 2.5,
                        "color": colour,
                    },
                    "color": _tint(colour, 0.25)
                    if high_level_style == "shading"
                    else colour,
                },
                legendgroup="high-level location",
                legendgrouptitle_text="high-level location",
            )
        )

    # Shared events: dashed lines between the low-level rows of their handling units.
    if link_shared_events and not is_trace_position:
        shared = (
            relations.with_columns(
                pl.col(c.HU).replace_strict(row_y, return_dtype=pl.Float64).alias("_y")
            )
            .group_by(c.EVENT)
            .agg(
                pl.col(X).first(),
                pl.col("_y").min().alias("y0"),
                pl.col("_y").max().alias("y1"),
                pl.len().alias("n"),
            )
            .filter(pl.col("n") > 1)
        )
        for r in shared.iter_rows(named=True):
            shapes.append(
                {
                    "type": "line",
                    "x0": r[X],
                    "x1": r[X],
                    "y0": r["y0"],
                    "y1": r["y1"],
                    "line": {"color": "#868e96", "width": 1, "dash": "dash"},
                    "layer": "below",
                }
            )

    # Same timestamp: a light background box around the tied events.
    if mark_ties and c.TIME in relations.columns:
        keys = [c.HU, c.TIME] if is_trace_position else [c.TIME]
        ties = (
            relations.group_by(keys)
            .agg(
                pl.col(X).min().alias("x0"),
                pl.col(X).max().alias("x1"),
                pl.col(c.EVENT).n_unique().alias("n"),
            )
            .filter(pl.col("n") > 1)
            .sort(keys)
        )
        for r in ties.iter_rows(named=True):
            box = {
                "type": "rect",
                "x0": r["x0"] - pad,
                "x1": r["x1"] + pad,
                "line": {"width": 0},
                "fillcolor": TIE_FILL,
                "layer": "below",
            }
            if is_trace_position:
                box |= {
                    "y0": row_bottom[r[c.HU]] - BAR / 2 - 0.05,
                    "y1": row_y[r[c.HU]] + 0.45,
                }
            else:
                box |= {"yref": "paper", "y0": 0, "y1": 1}
            shapes.append(box)
        if ties.height:
            fig.add_trace(
                go.Scatter(
                    x=[None],
                    y=[None],
                    mode="markers",
                    marker={"symbol": "square", "size": 14, "color": TIE_FILL},
                    name="same timestamp",
                    hoverinfo="skip",
                )
            )

    span = -y
    fig.update_layout(
        title=title,
        width=width,
        shapes=shapes,
        annotations=annotations,
        height=int(160 + span * PX_PER_UNIT),
        template="plotly_white",
        legend={"groupclick": "toggleitem", "tracegroupgap": 12},
        margin={"l": 110, "r": 20, "t": 70 if title else 40, "b": 40},
        hoverlabel={"align": "left"},
    )
    fig.update_yaxes(
        tickvals=tickvals,
        ticktext=ticktext,
        showgrid=False,
        zeroline=False,
        range=[y + GAP / 2, 0.6],
    )
    x_title = (
        "time" if is_time else "trace position" if is_trace_position else "event order"
    )
    fig.update_xaxes(
        title=x_title,
        showgrid=False,
        zeroline=False,
        dtick=None if is_time else 1,
        range=[x_min, x_max],
    )
    return fig
