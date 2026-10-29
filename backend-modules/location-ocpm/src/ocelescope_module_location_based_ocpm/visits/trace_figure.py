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
`relations_for_figure` runs steps 1 to 3 on a `Derivation`.
"""

from collections.abc import Collection, Mapping
from datetime import timedelta
from typing import Literal

import plotly.graph_objects as go
import polars as pl

from ..derivation import columns as c
from ..derivation.pipeline import Derivation

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
LABEL_OFFSET = 0.2
#: Pixels per y unit.
PX_PER_UNIT = 70


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
        x = pl.col(c.TIME)
    return out.with_columns(x.alias(X))


def relations_for_figure(
    derivation: Derivation,
    handling_units: Collection[str] | None = None,
    agg: Mapping[str, str] | None = None,
    vehicles: Collection[str] = (),
    storage_units: Collection[str] = (),
    axis: Axis = "event order",
) -> pl.DataFrame:
    """Prepare the relations of some handling units for `trace_figure` (steps 1 to 3).

    Args:
        derivation: Result of `derive`; its selected level gives loc.
        handling_units: Handling units to show, in this order; None = all.
        agg: Location mapping (see `add_high_level_locations`).
        vehicles: The set V.
        storage_units: The set W.
        axis: See `add_x_positions`.

    Returns:
        pl.DataFrame: Columns hu, hu_order, event, time, activity, is_movement, is_transformation, loc,
        high_level, location_kind, position, x.
    """
    relations = derivation.relations
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
        c.EVENT,
        c.TIME,
        c.ACTIVITY,
        c.IS_MOVEMENT,
        c.IS_TRANSFORMATION,
        pl.col(derivation.loc).alias("loc"),
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


def trace_figure(
    relations: pl.DataFrame,
    visits: pl.DataFrame | None = None,
    filled_groups: Collection[str] = ("resolved",),
    show_event_labels: bool = True,
    link_shared_events: bool = True,
    title: str | None = None,
) -> go.Figure:
    """Draw the object traces of several handling units with their locations, and optionally visits.

    Per handling unit (top to bottom, in the order of first appearance in `relations`):
    - the low-level row: one marker per relation at its x, coloured by loc (circle; open circle for
      vehicles, diamond for storage units; grey × for ⊥), joined by a thin line (the trace);
    - the high-level row just below: one square per relation, coloured by hat-hl;
    - below that, each visit group (e.g. "maximal", "resolved") in its own lanes: one bar per visit
      from its first to its last relation, outlined (or filled for `filled_groups`), coloured by its location.
    Dotted vertical lines join the relations of an event shared by several shown handling units.

    Args:
        relations: Output of `relations_for_figure`.
        visits: Optional, one row per visit: hu, high_level, first_event, last_event, group.
        filled_groups: Visit groups drawn as filled bars; all others outlined.
        show_event_labels: Write the event id above every low-level marker.
        link_shared_events: Draw the lines joining shared events (not for the "trace position" axis,
            where a shared event has different x values).
        title: Figure title.

    Returns:
        go.Figure: The figure.
    """
    is_time = relations.schema[X].is_temporal()
    is_trace_position = not is_time and relations[X].equals(relations[POSITION])
    hus = relations[c.HU].unique(maintain_order=True).to_list()
    names = relations["loc"].to_list() + relations[HIGH_LEVEL].to_list()
    if visits is not None:
        visits = visit_lanes(_visit_positions(visits, relations))
        names += visits[HIGH_LEVEL].to_list()
    colours = location_colours(names)

    # Half the width of a visit bar beyond its first and last relation, in x units.
    if is_time:
        times = relations[X].unique().sort()
        step = times.diff().drop_nulls().min() if len(times) > 1 else None
        pad = step * 0.4 if step else timedelta(hours=1)
    else:
        pad = 0.4

    fig = go.Figure()
    shapes: list[dict] = []
    tickvals, ticktext = [], []
    row_y: dict[str, float] = {}
    y = 0.0
    shown_legend: set[str] = set()
    for hu in hus:
        rows = relations.filter(pl.col(c.HU) == hu)
        row_y[hu] = y
        tickvals.append(y)
        ticktext.append(f"<b>{hu}</b>")
        high_y = y - HIGH_OFFSET
        bottom = high_y

        # Visit bars, one block of lanes per group.
        if visits is not None:
            lane_top = high_y - LANE
            for group in (
                visits[["group"]].unique(maintain_order=True)["group"].to_list()
            ):
                own = visits.filter((pl.col(c.HU) == hu) & (pl.col("group") == group))
                if own.is_empty():
                    continue
                filled = group in filled_groups
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
                            "line": {"color": colour, "width": 2},
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
                fig.add_annotation(
                    x=0,
                    xref="paper",
                    xanchor="right",
                    y=lane_top - (n_lanes - 1) * LANE / 2,
                    text=f"<i>{group}</i>",
                    showarrow=False,
                    font={"size": 10, "color": "#868e96"},
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
                line={"color": GUIDE, "width": 1},
                showlegend=False,
                hoverinfo="skip",
            )
        )
        # Markers: low-level row and high-level row, one trace per location, kind and level.
        hover = [_relation_hover(r) for r in rows.iter_rows(named=True)]
        rows = rows.with_columns(pl.Series("_hover", hover))
        for level, column, row_level_y in (
            ("location", "loc", y),
            ("high-level location", HIGH_LEVEL, high_y),
        ):
            for (name, kind), part in rows.group_by(column, KIND, maintain_order=True):
                if name is None:
                    symbol, colour, label = BOTTOM_SYMBOL, GREY, NOT_LOCATED
                else:
                    symbol = LOW_SYMBOL[kind] if column == "loc" else HIGH_SYMBOL
                    colour, label = colours[name], name
                key = f"{level}|{label}"
                fig.add_trace(
                    go.Scatter(
                        x=part[X],
                        y=[row_level_y] * part.height,
                        mode="markers",
                        marker={
                            "symbol": symbol,
                            "size": 13 if column == "loc" else 9,
                            "color": colour,
                            "line": {"width": 2, "color": colour},
                        },
                        name=label,
                        legendgroup=level,
                        legendgrouptitle_text=level,
                        showlegend=key not in shown_legend,
                        customdata=part["_hover"],
                        hovertemplate="%{customdata}<extra></extra>",
                    )
                )
                shown_legend.add(key)
        if show_event_labels:
            fig.add_trace(
                go.Scatter(
                    x=rows[X],
                    y=[y + LABEL_OFFSET] * rows.height,
                    mode="text",
                    text=rows[c.EVENT],
                    textposition="middle center",
                    textfont={"size": 10, "color": "#495057"},
                    showlegend=False,
                    hoverinfo="skip",
                )
            )
        y = bottom - GAP

    # Shared events: dotted lines between the low-level rows of their handling units.
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

    span = -y
    fig.update_layout(
        title=title,
        shapes=shapes,
        height=int(140 + span * PX_PER_UNIT),
        template="plotly_white",
        legend={"groupclick": "toggleitem", "tracegroupgap": 12},
        margin={"l": 110, "r": 20, "t": 60 if title else 30, "b": 40},
        hoverlabel={"align": "left"},
    )
    fig.update_yaxes(
        tickvals=tickvals,
        ticktext=ticktext,
        showgrid=False,
        zeroline=False,
        range=[y + GAP / 2, 0.4],
    )
    x_title = (
        "time" if is_time else "trace position" if is_trace_position else "event order"
    )
    fig.update_xaxes(
        title=x_title, showgrid=False, zeroline=False, dtick=None if is_time else 1
    )
    return fig
