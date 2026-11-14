"""Step 5: the whole directly-follows graph, as the response of the page's route.

`directly_follows_graph` runs the steps on plain frames (usable in the notebooks);
`log_frames` reads these frames from an OCEL and its derivation.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass

import polars as pl
from ocelescope import OCEL
from pydantic import BaseModel, Field

from ..derivation import columns as c
from ..derivation.inputs import OCEL_EID, OCEL_OID, OCEL_TYPE
from ..derivation.pipeline import Derivation
from . import columns as d
from .arcs import arc_filter, directly_follows_arcs, objects_per_type
from .nodes import activity_frequencies, involved_object_types, shown_activities
from .traces import considered_objects, object_traces
from .variants import object_variants, path_filter

#: Default path threshold (percent): all paths.
DEFAULT_PATH_THRESHOLD = 100.0
#: Default arc threshold (percent): all arcs.
DEFAULT_ARC_THRESHOLD = 0.0


class TypeSetting(BaseModel):
    """Settings of one selected object type.

    Attributes:
        object_type: The object type.
        path_threshold: Path threshold in percent (`variants.py`); 100 = all paths.
        arc_threshold: Arc threshold in percent (`arcs.py`); 0 = all arcs.
    """

    object_type: str
    path_threshold: float = Field(DEFAULT_PATH_THRESHOLD, ge=0, le=100)
    arc_threshold: float = Field(DEFAULT_ARC_THRESHOLD, ge=0, le=100)


class DfgRequest(BaseModel):
    """Settings of the page.

    Attributes:
        selection: The selected object types with their thresholds; None = the default, every object type
            that contains handling units, with the default thresholds.
    """

    selection: list[TypeSetting] | None = None


class DfgObjectType(BaseModel):
    """An object type of the log, with what the graph shows of it.

    Attributes:
        object_type: The object type.
        objects: Number of objects of the type (for a type with handling units: its handling units).
        handling_units: True if the type contains handling units.
        selected: True if the type's arcs are shown.
        path_threshold: Path threshold used (percent), for selected types.
        arc_threshold: Arc threshold used (percent), for selected types.
        kept_objects: Objects whose path is kept (selected types; 0 otherwise).
        paths: Distinct paths (variants) of the type's objects (selected types; 0 otherwise).
        kept_paths: Paths kept by the path threshold.
        arcs: Arcs after the path filter, before the arc filter (with start and end arcs).
        kept_arcs: Arcs kept by the arc threshold.
    """

    object_type: str
    objects: int
    handling_units: bool
    selected: bool
    path_threshold: float = DEFAULT_PATH_THRESHOLD
    arc_threshold: float = DEFAULT_ARC_THRESHOLD
    kept_objects: int = 0
    paths: int = 0
    kept_paths: int = 0
    arcs: int = 0
    kept_arcs: int = 0


class DfgTypeCount(BaseModel):
    """Events of an activity node that involve an object type.

    Attributes:
        object_type: The object type.
        events: Counted events of the activity that involve at least one object of the type.
        objects: Distinct objects of the type in these events.
    """

    object_type: str
    events: int
    objects: int


class DfgActivity(BaseModel):
    """An activity node.

    Attributes:
        activity: The activity.
        events: Frequency: events of the activity in the traces of the kept objects (`nodes.py`).
        log_events: All events of the activity in the log.
        object_types: Object types involved in the counted events, most events first.
    """

    activity: str
    events: int
    log_events: int
    object_types: list[DfgTypeCount]


class DfgArc(BaseModel):
    """A kept arc.

    Attributes:
        object_type: The object type whose objects traverse it.
        source: Source activity; None = the start node of the object type.
        target: Target activity; None = the end node of the object type.
        count: Traversals.
        objects: Distinct objects traversing it.
    """

    object_type: str
    source: str | None
    target: str | None
    count: int
    objects: int


class DirectlyFollowsGraph(BaseModel):
    """The page's graph.

    Attributes:
        object_types: All object types of the log, most objects first (the order of their colours).
        activities: The shown activity nodes, by name.
        arcs: The kept arcs.
    """

    object_types: list[DfgObjectType]
    activities: list[DfgActivity]
    arcs: list[DfgArc]


@dataclass(frozen=True)
class LogFrames:
    """The frames the graph is computed from.

    Attributes:
        e2o: Columns event, object, object_type (all objects).
        events: Columns event, time, activity, is_movement, is_transformation, is_processing.
        objects: Columns object, object_type (all objects).
        handling_units: The handling units HU (object ids).
        processing: The processing operations P (event ids), for the AS4 tie rank.
    """

    e2o: pl.DataFrame
    events: pl.DataFrame
    objects: pl.DataFrame
    handling_units: pl.Series
    processing: pl.Series


def log_frames(ocel: OCEL, derivation: Derivation) -> LogFrames:
    """Read the frames for the graph from the log and its derivation.

    Args:
        ocel: The log.
        derivation: The derivation of the log (handling units, M, P).

    Returns:
        LogFrames: The frames.
    """
    objects = ocel.objects.pl.select(OCEL_OID, OCEL_TYPE).collect().rename({OCEL_OID: d.OBJECT, OCEL_TYPE: c.OBJECT_TYPE})
    e2o = (
        ocel.e2o.pl.select(OCEL_EID, OCEL_OID)
        .unique()
        .collect()
        .rename({OCEL_EID: c.EVENT, OCEL_OID: d.OBJECT})
        .join(objects, on=d.OBJECT)
    )
    events = derivation.events.select(
        c.EVENT, c.TIME, c.ACTIVITY, c.IS_MOVEMENT, c.IS_TRANSFORMATION, c.IS_PROCESSING
    )
    return LogFrames(
        e2o=e2o,
        events=events,
        objects=objects,
        handling_units=derivation.handling_units[c.HU],
        processing=events.filter(pl.col(c.IS_PROCESSING).fill_null(False))[c.EVENT],
    )


def default_selection(objects: pl.DataFrame, handling_units: Collection[str]) -> list[TypeSetting]:
    """The default selection: every object type that contains handling units, with the default thresholds.

    Args:
        objects: All objects, columns object and object_type.
        handling_units: The handling units HU.

    Returns:
        list[TypeSetting]: One setting per handling-unit type, sorted by type.
    """
    types = objects.filter(pl.col(d.OBJECT).is_in(list(handling_units)))[c.OBJECT_TYPE].unique().sort()
    return [TypeSetting(object_type=t) for t in types]


def type_overview(objects: pl.DataFrame, handling_units: Collection[str]) -> pl.DataFrame:
    """All object types with their number of considered objects and whether they contain handling units.

    Args:
        objects: All objects, columns object and object_type.
        handling_units: The handling units HU.

    Returns:
        pl.DataFrame: Columns object_type, objects, handling_units; most objects first, then by type.
    """
    is_hu = pl.col(d.OBJECT).is_in(list(handling_units))
    return (
        objects.group_by(c.OBJECT_TYPE)
        .agg(
            pl.when(is_hu.any()).then(is_hu.sum()).otherwise(pl.len()).cast(pl.Int64).alias(d.OBJECTS),
            is_hu.any().alias("handling_units"),
        )
        .sort([d.OBJECTS, c.OBJECT_TYPE], descending=[True, False])
    )


def directly_follows_graph(
    frames: LogFrames, selection: Sequence[TypeSetting] | None = None, traces: pl.DataFrame | None = None
) -> DirectlyFollowsGraph:
    """The directly-follows graph of the selected object types.

    Args:
        frames: The log's frames (`log_frames`).
        selection: Selected object types with thresholds; None = `default_selection`.
        traces: Precomputed `object_traces` of the selected types (e.g. from a cache); None = compute them.

    Returns:
        DirectlyFollowsGraph: Object types, activity nodes and kept arcs.
    """
    hu = frames.handling_units.to_list()
    if selection is None:
        selection = default_selection(frames.objects, hu)
    settings = {s.object_type: s for s in selection}
    if traces is None:
        traces = selected_traces(frames, list(settings))
    path_thresholds = {t: s.path_threshold for t, s in settings.items()}
    arc_thresholds = {t: s.arc_threshold for t, s in settings.items()}

    kept_traces = path_filter(traces, path_thresholds)
    n_kept = objects_per_type(kept_traces)
    all_arcs = directly_follows_arcs(kept_traces)
    kept_arcs = arc_filter(all_arcs, n_kept, arc_thresholds)

    activities = shown_activities(kept_arcs)
    frequencies = activity_frequencies(kept_traces, activities)
    involved = involved_object_types(kept_traces, activities, frames.e2o)
    log_counts = frames.events.group_by(c.ACTIVITY).agg(pl.len().alias(d.EVENTS))
    log_events = dict(zip(log_counts[c.ACTIVITY], log_counts[d.EVENTS], strict=True))

    variants = object_variants(traces)
    kept_variants = object_variants(kept_traces)
    paths = _count_per_type(variants.unique([c.OBJECT_TYPE, d.VARIANT]))
    kept_paths = _count_per_type(kept_variants.unique([c.OBJECT_TYPE, d.VARIANT]))
    arcs_before = _count_per_type(all_arcs)
    arcs_after = _count_per_type(kept_arcs)

    object_types = [
        DfgObjectType(
            object_type=row[c.OBJECT_TYPE],
            objects=row[d.OBJECTS],
            handling_units=row["handling_units"],
            selected=row[c.OBJECT_TYPE] in settings,
            **(
                {
                    "path_threshold": settings[row[c.OBJECT_TYPE]].path_threshold,
                    "arc_threshold": settings[row[c.OBJECT_TYPE]].arc_threshold,
                    "kept_objects": n_kept.get(row[c.OBJECT_TYPE], 0),
                    "paths": paths.get(row[c.OBJECT_TYPE], 0),
                    "kept_paths": kept_paths.get(row[c.OBJECT_TYPE], 0),
                    "arcs": arcs_before.get(row[c.OBJECT_TYPE], 0),
                    "kept_arcs": arcs_after.get(row[c.OBJECT_TYPE], 0),
                }
                if row[c.OBJECT_TYPE] in settings
                else {}
            ),
        )
        for row in type_overview(frames.objects, hu).iter_rows(named=True)
    ]
    by_activity: dict[str, list[DfgTypeCount]] = {}
    for row in involved.iter_rows(named=True):
        by_activity.setdefault(row[c.ACTIVITY], []).append(
            DfgTypeCount(object_type=row[c.OBJECT_TYPE], events=row[d.EVENTS], objects=row[d.OBJECTS])
        )
    return DirectlyFollowsGraph(
        object_types=object_types,
        activities=[
            DfgActivity(
                activity=row[c.ACTIVITY],
                events=row[d.EVENTS],
                log_events=log_events.get(row[c.ACTIVITY], 0),
                object_types=by_activity.get(row[c.ACTIVITY], []),
            )
            for row in frequencies.iter_rows(named=True)
        ],
        arcs=[DfgArc(**row) for row in kept_arcs.iter_rows(named=True)],
    )


def selected_traces(frames: LogFrames, object_types: Collection[str]) -> pl.DataFrame:
    """The traces of the considered objects of the given object types (step 1).

    Args:
        frames: The log's frames.
        object_types: The selected object types.

    Returns:
        pl.DataFrame: `traces.object_traces` of these objects.
    """
    objects = considered_objects(frames.objects, object_types, frames.handling_units.to_list())
    return object_traces(frames.e2o, frames.events, objects, processing=frames.processing.to_list())


def _count_per_type(frame: pl.DataFrame) -> dict[str, int]:
    """Number of rows per object type.

    Args:
        frame: Frame with the column object_type.

    Returns:
        dict[str, int]: object type -> rows.
    """
    counts = frame.group_by(c.OBJECT_TYPE).len()
    return dict(zip(counts[c.OBJECT_TYPE], counts["len"], strict=True))
