"""Object traces of the handling units selected on the instance page (Nina, 2026-11-20).

Documented in `docs/pages/instances.md`, section "Object traces". One row per selected handling unit: its events in
`seq` order (time, AS4 ties, event id; as in the HU profile), each with its activity, timestamp, location and the
other objects it involves (all objects of the log, not only handling units). Above the chart, the event categories
of the directly-follows graph page (`dfg/categories.py`) project the traces: an event is removed when all its
categories are deselected (events in no category always stay); by default all are selected.

Steps (each a function of its own):
1. `trace_events`: the events of the selected handling units in `seq` order.
2. `involved_objects`: per event the objects it involves, with their object type.
3. `object_traces`: both joined, the categories attached, the projection applied and the positions renumbered.
For notebooks, `align_columns` and `traces_figure` draw the result with plotly, like the page's chart
(`ObjectTracesChart.tsx`, which has its own TypeScript copy of `align_columns`).
"""

from collections.abc import Collection
from dataclasses import dataclass

import plotly.graph_objects as go
import polars as pl

from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.dfg.categories import (
    CATEGORIES,
    removed_events,
)
from ocelescope_module_location_based_ocpm.instances.object_graph import ObjectFrames
from ocelescope_module_location_based_ocpm.instances.profile import ordered_traces
from ocelescope_module_location_based_ocpm.visits.trace_figure import CATEGORICAL

#: At most this many handling units get a row (the first ones of the selection).
MAX_TRACES = 50


@dataclass
class ObjectTraces:
    """The traces of the selected handling units.

    Attributes:
        events: One row per (handling unit, kept event): hu, object_type (of the hu), pos (1-based, after the
            projection), event, time, activity, location (loc^k of the relation, null if unlocated), categories
            (list of `CATEGORIES` keys) and objects (list of structs object, object_type, is_hu, selected: the
            other objects of the event, sorted by object type and id; `is_hu` = a handling unit of the log,
            `selected` = also one of the selected handling units); sorted by the order of the selection, then pos.
        totals: Per selected handling unit (in the order of the selection): hu, object_type, n_events (all its
            events) and n_shown (kept by the projection).
        categories: Per category key the number of distinct events of the selected handling units in it (before
            the projection), for the chips.
        notes: Remarks, e.g. handling units that are not part of the log.
    """

    events: pl.DataFrame
    totals: pl.DataFrame
    categories: dict[str, int]
    notes: list[str]


def trace_events(
    relations: pl.DataFrame | pl.LazyFrame,
    handling_units: Collection[str],
    loc: str,
    hl: str,
    processing: Collection[str] | None = None,
) -> pl.DataFrame:
    """The events of the given handling units in `seq` order (`profile.ordered_traces`).

    Args:
        relations: hu-event relations (`Derivation.relations`).
        handling_units: The handling units.
        loc: Column of loc^k.
        hl: Column of agg(loc^k).
        processing: Event ids of P for the AS4 tie order; None = the transformation events T.

    Returns:
        pl.DataFrame: Columns hu, object_type, pos, event, time, activity, location; sorted by hu and pos.
    """
    selected = relations.lazy().filter(pl.col(c.HU).is_in(list(handling_units)))
    return (
        ordered_traces(selected, loc, hl, processing)
        .select(c.HU, c.OBJECT_TYPE, pl.col("pos").cast(pl.UInt32), c.EVENT, c.TIME, c.ACTIVITY, pl.col("loc").alias("location"))
        .collect()
    )


def involved_objects(frames: ObjectFrames, events: Collection[str]) -> pl.DataFrame:
    """The objects of the given events with their object type.

    Args:
        frames: Tables of the log (`object_graph.object_frames`).
        events: Event ids.

    Returns:
        pl.DataFrame: Columns event, object, object_type; sorted by event, object type and object.
    """
    return (
        frames.e2o.filter(pl.col("event").is_in(list(events)))
        .join(frames.objects, on="object", how="left")
        .sort("event", "object_type", "object", nulls_last=True)
        .collect()
    )


def object_traces(
    relations: pl.DataFrame | pl.LazyFrame,
    frames: ObjectFrames,
    categories: pl.DataFrame,
    handling_units: Collection[str],
    units: pl.DataFrame,
    loc: str,
    hl: str,
    processing: Collection[str] | None = None,
    excluded: Collection[str] = (),
    max_traces: int = MAX_TRACES,
) -> ObjectTraces:
    """The traces of the selected handling units with the other objects of every event, projected on the categories.

    Example (running example, c2 selected, Other movements deselected): c2's trace e3 roll, e4 label, e6 move, e8
    load truck, ... loses e6 (a movement to A2, neither vehicle nor storage unit) but keeps e8 (a movement to the
    vehicle T, while Move to vehicle is still selected); e3 lists s1 and c1 as other objects, c1 marked `selected` if c1 is selected too.

    Args:
        relations: hu-event relations (`Derivation.relations`).
        frames: Tables of the log (`object_graph.object_frames`).
        categories: `dfg.categories.event_categories` of all events.
        handling_units: The selected handling units (order kept).
        units: All handling units of the log, columns hu and object_type (`Derivation.handling_units`).
        loc: Column of loc^k.
        hl: Column of agg(loc^k).
        processing: Event ids of P (AS4 tie order).
        excluded: Deselected category keys.
        max_traces: Rows at most.

    Returns:
        ObjectTraces: Events, totals, category counts and notes.
    """
    known = set(units[c.HU].to_list())
    notes = []
    unknown = [hu for hu in handling_units if hu not in known]
    if unknown:
        notes.append(f"Not handling units of this log: {', '.join(unknown)}.")
    selected = [hu for hu in dict.fromkeys(handling_units) if hu in known]
    if len(selected) > max_traces:
        notes.append(f"{len(selected)} handling units selected; only the first {max_traces} are drawn.")
        selected = selected[:max_traces]
    order = pl.DataFrame({c.HU: selected, "_order": range(len(selected))}, schema={c.HU: pl.String, "_order": pl.Int64})
    events = trace_events(relations, selected, loc, hl, processing)
    ids = events[c.EVENT].unique()
    cats = categories.filter(pl.col(c.EVENT).is_in(ids.implode()))
    counts = {k: int(cats[k].sum() or 0) for k in CATEGORIES}
    category_lists = cats.select(
        c.EVENT,
        pl.concat_list(pl.when(pl.col(k)).then(pl.lit(k)).otherwise(None) for k in CATEGORIES).list.drop_nulls().alias("categories"),
    )
    objects = involved_objects(frames, ids.to_list()).with_columns(
        pl.col("object").is_in(list(known)).alias("is_hu"), pl.col("object").is_in(selected).alias("selected")
    )
    removed = removed_events(cats, excluded)
    # Other objects per (hu, event): the event's objects without the hu itself.
    others = (
        events.select(c.HU, c.EVENT)
        .join(objects, on=c.EVENT, how="inner")
        .filter(pl.col("object") != pl.col(c.HU))
        .group_by(c.HU, c.EVENT, maintain_order=True)
        .agg(pl.struct("object", "object_type", "is_hu", "selected").alias("objects"))
    )
    empty_objects = pl.lit([], dtype=pl.List(pl.Struct({"object": pl.String, "object_type": pl.String, "is_hu": pl.Boolean, "selected": pl.Boolean})))
    kept = (
        events.join(removed, on=c.EVENT, how="anti")
        .join(category_lists, on=c.EVENT, how="left")
        .join(others, on=[c.HU, c.EVENT], how="left")
        .join(order, on=c.HU, how="left")
        .sort("_order", "pos")
        .with_columns(
            (pl.int_range(pl.len()).over(c.HU) + 1).cast(pl.UInt32).alias("pos"),
            pl.col("categories").fill_null(pl.lit([], dtype=pl.List(pl.String))),
            pl.col("objects").fill_null(empty_objects),
        )
        .drop("_order")
    )
    totals = (
        order.join(units.select(c.HU, c.OBJECT_TYPE), on=c.HU, how="left")
        .join(events.group_by(c.HU).agg(pl.len().cast(pl.Int64).alias("n_events")), on=c.HU, how="left")
        .join(kept.group_by(c.HU).agg(pl.len().cast(pl.Int64).alias("n_shown")), on=c.HU, how="left")
        .with_columns(pl.col("n_events").fill_null(0), pl.col("n_shown").fill_null(0))
        .sort("_order")
        .drop("_order")
    )
    return ObjectTraces(events=kept, totals=totals, categories=counts, notes=notes)


def align_columns(events: pl.DataFrame) -> dict[str, int] | None:
    """One column per event, the same in every row it appears in, each row keeping its order (option "Align shared events").

    The column of an event is the length of the longest chain of events before it over all rows: longest path in the
    graph with an arc from each event to the next one of the same row (Kahn's algorithm by rounds).

    Example: c2 = e3, e4, e6, e8 and c1 = e3, e4, e5, e7, e8 give e3 → 0, e4 → 1, e5 and e6 → 2, e7 → 3, e8 → 4.

    Args:
        events: `ObjectTraces.events` (columns hu, pos, event).

    Returns:
        dict[str, int] | None: Event -> column, or None if two rows order shared events differently (a cycle).
    """
    rows = events.sort("hu", "pos").group_by("hu", maintain_order=True).agg(pl.col(c.EVENT))
    following: dict[str, set[str]] = {}
    indegree: dict[str, int] = {}
    for sequence in rows[c.EVENT].to_list():
        for i, event in enumerate(sequence):
            indegree.setdefault(event, 0)
            if i + 1 < len(sequence) and sequence[i + 1] not in following.setdefault(event, set()):
                following[event].add(sequence[i + 1])
                indegree[sequence[i + 1]] = indegree.get(sequence[i + 1], 0) + 1
    column: dict[str, int] = {}
    current = [e for e, d in indegree.items() if d == 0]
    depth = 0
    while current:
        upcoming = []
        for event in current:
            column[event] = depth
            for nxt in following.get(event, ()):
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    upcoming.append(nxt)
        current = upcoming
        depth += 1
    return column if len(column) == len(indegree) else None


def traces_figure(traces: ObjectTraces, align: bool = False, colours: dict[str, str] | None = None) -> go.Figure:
    """The object traces as a plotly figure (for notebooks; the page draws them in `ObjectTracesChart.tsx`).

    One row per handling unit (top to bottom in the order of the selection), its events as chevrons labelled with
    event id and activity, the other objects of an event as small circles below in the colour of their object type;
    circles of selected handling units have a thick black border. Hover a chevron's centre for the event (timestamp,
    location, categories, objects), a circle for its object.

    Args:
        traces: Output of `object_traces`.
        align: Shared events in one column (`align_columns`); otherwise every row packed from the left.
        colours: Object type -> colour; missing types get the module's palette in alphabetical order.

    Returns:
        go.Figure: The figure.
    """
    colours = dict(colours or {})
    types = sorted({o["object_type"] or "" for objects in traces.events["objects"].to_list() for o in objects})
    for t in [t for t in traces.totals["object_type"].to_list() if t] + types:
        colours.setdefault(t, CATEGORICAL[len(colours) % len(CATEGORICAL)])
    columns = align_columns(traces.events) if align else None
    rows = {hu: i for i, hu in enumerate(traces.totals[c.HU].to_list())}
    fig = go.Figure()
    centres = {"x": [], "y": [], "text": []}
    circles: dict[str, dict[str, list]] = {}
    width, point = 0.94, 0.14
    for row in traces.events.iter_rows(named=True):
        x = columns[row[c.EVENT]] if columns else row["pos"] - 1
        y = -rows[row[c.HU]]
        left, right = x - width / 2, x + width / 2
        notch = "" if row["pos"] == 1 else f" L {left + point} {y}"
        fig.add_shape(
            type="path",
            path=f"M {left} {y + 0.3} L {right - point} {y + 0.3} L {right} {y} L {right - point} {y - 0.3} L {left} {y - 0.3}{notch} Z",
            line={"color": "#868e96", "width": 1},
            fillcolor="white",
            layer="below",
        )
        fig.add_annotation(x=x, y=y + 0.17, text=row[c.EVENT], showarrow=False, font={"size": 9, "color": "#868e96"})
        fig.add_annotation(x=x, y=y + 0.04, text=f"<b>{row[c.ACTIVITY] or ''}</b>", showarrow=False, font={"size": 11})
        others = row["objects"]
        listed = "<br>".join(f"{o['object']} ({o['object_type']}){', selected' if o['selected'] else ''}" for o in others[:20])
        centres["x"].append(x)
        centres["y"].append(y)
        centres["text"].append(
            f"<b>{row[c.EVENT]} · {row[c.ACTIVITY]}</b><br>{row[c.TIME]} · at {row['location'] or '⊥'} · position {row['pos']}"
            f"<br>Categories: {', '.join(row['categories']) or 'none'}<br>{listed or 'no other objects'}"
        )
        step = 0.09
        start = x - step * (len(others) - 1) / 2
        for i, o in enumerate(others):
            group = circles.setdefault(o["object_type"] or "", {"x": [], "y": [], "text": [], "line": []})
            group["x"].append(start + i * step)
            group["y"].append(y - 0.15)
            group["text"].append(f"{o['object']} ({o['object_type']}){', selected' if o['selected'] else ''}")
            group["line"].append(2.5 if o["selected"] else 0.5)
    fig.add_trace(go.Scatter(**centres, mode="markers", marker={"size": 18, "opacity": 0}, hovertemplate="%{text}<extra></extra>", showlegend=False))
    for t, group in sorted(circles.items()):
        fig.add_trace(
            go.Scatter(
                x=group["x"],
                y=group["y"],
                text=group["text"],
                mode="markers",
                name=t,
                marker={"size": 9, "color": colours.get(t), "line": {"color": "#343a40", "width": group["line"]}},
                hovertemplate="%{text}<extra></extra>",
            )
        )
    labels = [f"<b>{r[c.HU]}</b><br>{r[c.OBJECT_TYPE]} · {r['n_shown']} of {r['n_events']}" for r in traces.totals.iter_rows(named=True)]
    fig.update_yaxes(tickvals=[-i for i in range(len(rows))], ticktext=labels, showgrid=False, zeroline=False, range=[-len(rows) + 0.5, 0.5])
    fig.update_xaxes(visible=False)
    fig.update_layout(
        height=120 + 90 * len(rows),
        plot_bgcolor="white",
        legend={"title": {"text": "Object types"}, "orientation": "h", "y": 1.08},
        margin={"l": 10, "r": 10, "t": 40, "b": 10},
    )
    return fig
