"""API routes of the instance page (documented in `docs/pages/instances.md`).

The HU profile of a log is cached (small LRU per process), keyed by the cache key of the current derivation,
so that paging, sorting and searching the table only rerun the cheap query step.
"""

import math
from collections import OrderedDict
from datetime import datetime
from typing import Literal

import polars as pl
from fastapi import APIRouter, HTTPException
from ocelescope.resource.default.ocel_mapping import OCELMapping
from ocelescope_backend.app.dependencies import ApiOcel, ApiSession
from pydantic import BaseModel, Field, field_validator

from ocelescope_module_location_based_ocpm.configuration_routes import (
    CurrentDerivation,
    State,
)
from ocelescope_module_location_based_ocpm.derivation.pipeline import Derivation
from ocelescope_module_location_based_ocpm.instances.charts import (
    processing_events,
    selection_lineage,
    timeline_figure,
)
from ocelescope_module_location_based_ocpm.instances.object_graph import (
    object_frames,
    object_graph,
)
from ocelescope_module_location_based_ocpm.instances.profile import (
    FILTERABLE,
    SORTABLE,
    ColumnFilter,
    column_info,
    export_frame,
    hu_details,
    hu_profile,
    query_profile,
    query_rows,
    sort_rows,
)
from ocelescope_module_location_based_ocpm.lineage.lineage import Direction
from ocelescope_module_location_based_ocpm.timeline.object_timeline import (
    MAX_HANDLING_UNITS,
    TimelineAxis,
)

router = APIRouter()

#: Number of cached profiles (one per derivation key).
CACHE_SIZE = 4
_profiles: OrderedDict[str, pl.DataFrame] = OrderedDict()
_column_infos: dict[str, list[dict]] = {}

SortColumn = Literal[SORTABLE]  # type: ignore[valid-type]
FilterColumn = Literal[FILTERABLE]  # type: ignore[valid-type]


def cached_profile(key: str, derivation: Derivation) -> pl.DataFrame:
    """The HU profile of the derivation, computed once per derivation key.

    Args:
        key: Cache key of the derivation (`state.cache[ocel_id].key`).
        derivation: The derivation.

    Returns:
        pl.DataFrame: Output of `instances.profile.hu_profile`.
    """
    if key in _profiles:
        _profiles.move_to_end(key)
        return _profiles[key]
    profile = _profiles[key] = hu_profile(
        derivation.relations,
        derivation.handling_units,
        derivation.roles,
        derivation.context,
        derivation.loc,
        derivation.hl,
        processing_events(derivation),
    )
    while len(_profiles) > CACHE_SIZE:
        old, _ = _profiles.popitem(last=False)
        _column_infos.pop(old, None)
    return profile


def cached_column_info(key: str, profile: pl.DataFrame) -> list[dict]:
    """`instances.profile.column_info` of the cached profile of a derivation key, computed once.

    Args:
        key: Cache key of the derivation.
        profile: Its profile (`cached_profile`).

    Returns:
        list[dict]: The column infos.
    """
    if key not in _column_infos:
        _column_infos[key] = column_info(profile)
    return _column_infos[key]


class HuProfileRow(BaseModel):
    """One row of the HU profile (see `instances.profile.hu_profile` for every column)."""

    hu: str
    object_type: str | None
    lifecycle: str
    n_events: int
    first: datetime | None = None
    last: datetime | None = None
    lifespan: float | None = None
    creation_event: str | None = None
    creation_activity: str | None = None
    final_consumption_event: str | None = None
    final_consumption_activity: str | None = None
    partial_consumptions: list[str] = Field(default_factory=list)
    n_partial_consumptions: int = 0
    parents: list[str] = Field(default_factory=list)
    children: list[str] = Field(default_factory=list)
    siblings: list[str] = Field(default_factory=list)
    n_parents: int = 0
    n_children: int = 0
    n_siblings: int = 0
    n_locations: int = 0
    n_high_level_locations: int = 0
    first_location: str | None = None
    last_location: str | None = None
    n_location_changes: int = 0
    locatedness: str | None = None
    n_movements: int = 0
    n_processing: int = 0
    processing_activities: list[str] = Field(default_factory=list)
    n_shared_events: int = 0
    connectedness: float | None = None
    n_co_handled: int = 0
    n_linked: int = 0
    #: Longest chain of parents above / children below; None = unbounded (a lineage loop, inf in the profile).
    generations_up: float | None = 0
    generations_down: float | None = 0
    time_vehicle: float = 0
    time_storage: float = 0
    time_other: float = 0
    time_unlocated: float = 0

    @field_validator("generations_up", "generations_down", mode="before")
    @classmethod
    def _unbounded(cls, value: float | None) -> float | None:
        """inf (a loop) as None, since JSON has no infinity."""
        return None if value is not None and math.isinf(value) else value


class ColumnInfo(BaseModel):
    """What the filter of one column offers (see `instances.profile.column_info`)."""

    column: FilterColumn
    kind: Literal["category", "text", "number", "time"]
    values: list[tuple[str | None, int]] | None = None
    min: float | None = None
    max: float | None = None


class HuProfilePage(BaseModel):
    """A page of the HU profile.

    Attributes:
        rows: The rows of the page.
        total: Rows matching search and filters.
        object_types: Object types of all handling units with their number of handling units.
        columns: Filter options per column (values or range over all handling units).
        has_high_level: True if high-level locations are configured.
        has_vehicles: True if vehicles are configured.
        has_storage: True if storage units are configured.
    """

    rows: list[HuProfileRow]
    total: int
    object_types: list[tuple[str, int]]
    columns: list[ColumnInfo]
    has_high_level: bool
    has_vehicles: bool
    has_storage: bool


class ProfileFilter(BaseModel):
    """A column filter of the table (see `instances.profile.ColumnFilter`)."""

    column: FilterColumn
    values: list[str | None] | None = None
    min: float | None = None
    max: float | None = None
    text: str | None = None


class ProfileQuery(BaseModel):
    """Search, column filters, sorting and page of the HU profile table."""

    search: str = ""
    filters: list[ProfileFilter] = Field(default_factory=list)
    sort_by: SortColumn = "hu"
    descending: bool = False
    offset: int = 0
    limit: int = 25


class ProfileExportRequest(ProfileQuery):
    """The table as shown, for an export: all matching rows (not only the page), the shown columns.

    Attributes:
        columns: Shown columns in table order (hu is always included).
        name: Name of the saved resource (save to session only).
    """

    columns: list[FilterColumn]
    name: str = "HU profile"


class ProfileCsv(BaseModel):
    """A CSV export of the table."""

    file_name: str
    content: str
    rows: int


class SavedResource(BaseModel):
    """A resource saved to the session."""

    id: str
    name: str
    rows: int


def _filters(query: ProfileQuery) -> list[ColumnFilter]:
    """The column filters of a query as `ColumnFilter`s.

    Args:
        query: The query.

    Returns:
        list[ColumnFilter]: Its filters.
    """
    return [ColumnFilter(**f.model_dump()) for f in query.filters]


def _shown_rows(key: str, derivation: Derivation, request: ProfileExportRequest) -> pl.DataFrame:
    """All rows matching the request, sorted, with the shown columns (the folded table as shown).

    Args:
        key: Cache key of the derivation.
        derivation: The derivation.
        request: Search, filters, sorting and shown columns.

    Returns:
        pl.DataFrame: Output of `instances.profile.export_frame`.

    Raises:
        HTTPException: 422 if a column cannot be filtered, sorted or exported.
    """
    profile = cached_profile(key, derivation)
    try:
        rows = sort_rows(query_rows(profile, request.search, _filters(request)), request.sort_by, request.descending)
        return export_frame(rows, request.columns)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/{ocel_id}/instances/profile", operation_id="getHuProfile")
def get_hu_profile(ocel_id: str, derivation: CurrentDerivation, state: State, query: ProfileQuery) -> HuProfilePage:
    """A page of the HU profile, searched, filtered by column and sorted."""
    key = state.cache[ocel_id].key
    profile = cached_profile(key, derivation)
    try:
        page, total = query_profile(
            profile, query.search, (), query.sort_by, query.descending, query.offset, query.limit, _filters(query)
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    counts = profile.group_by("object_type").len().sort("len", "object_type", descending=[True, False])
    return HuProfilePage(
        rows=[HuProfileRow(**row) for row in page.to_dicts()],
        total=total,
        object_types=[(t or "", n) for t, n in counts.iter_rows()],
        columns=[ColumnInfo(**info) for info in cached_column_info(key, profile)],
        has_high_level=derivation.has_high_level,
        has_vehicles=bool(derivation.context.vehicles),
        has_storage=bool(derivation.context.storage_units),
    )


@router.post("/{ocel_id}/instances/profile/csv", operation_id="exportHuProfileCsv")
def export_hu_profile_csv(
    ocel_id: str, derivation: CurrentDerivation, state: State, request: ProfileExportRequest
) -> ProfileCsv:
    """The table as shown (all matching rows, shown columns, folded) as CSV text."""
    frame = _shown_rows(state.cache[ocel_id].key, derivation, request)
    return ProfileCsv(file_name="hu_profile.csv", content=frame.write_csv(), rows=frame.height)


@router.post("/{ocel_id}/instances/profile/save", operation_id="saveHuProfile")
def save_hu_profile(
    ocel_id: str, derivation: CurrentDerivation, state: State, session: ApiSession, request: ProfileExportRequest
) -> SavedResource:
    """Save the table as shown to the session as an Ocelescope "OCEL Mapping" resource.

    The handling units are its objects (column ocel:oid), the shown columns its values; events, e2o and o2o stay
    empty.
    """
    frame = _shown_rows(state.cache[ocel_id].key, derivation, request).rename({"hu": "ocel:oid"})
    mapping = OCELMapping()
    mapping.objects = frame
    name = request.name.strip() or "HU profile"
    return SavedResource(id=session.add_resource(mapping, name), name=name, rows=frame.height)


class DetailEvent(BaseModel):
    """An event in the details of a handling unit."""

    event: str
    activity: str | None = None
    time: datetime | None = None


class PathEntry(BaseModel):
    """A location of the location path: the location and the event that reached it."""

    location: str
    event: str
    time: datetime | None = None


class ActivityCount(BaseModel):
    """An activity with its number of events."""

    activity: str | None = None
    count: int


class CoHandled(BaseModel):
    """Another handling unit sharing non-transformation events with the handling unit."""

    hu: str
    count: int
    events: list[str]


class HuDetails(BaseModel):
    """What an unfolded row of the HU profile shows (see `instances.profile.hu_details`)."""

    hu: str
    first_event: DetailEvent | None = None
    last_event: DetailEvent | None = None
    creation: DetailEvent | None = None
    final_consumption: DetailEvent | None = None
    partial_consumptions: list[DetailEvent]
    parents: list[str]
    children: list[str]
    siblings: list[str]
    location_path: list[PathEntry]
    processing: list[ActivityCount]
    co_handled: list[CoHandled]


@router.get("/{ocel_id}/instances/details", operation_id="getHuDetails")
def get_hu_details(ocel_id: str, derivation: CurrentDerivation, state: State, hu: str) -> HuDetails:
    """Details of one handling unit for its unfolded row in the HU profile."""
    profile = cached_profile(state.cache[ocel_id].key, derivation)
    rows = profile.filter(pl.col("hu") == hu).to_dicts()
    if not rows:
        raise HTTPException(status_code=404, detail=f"Not a handling unit of this log: {hu}.")
    details = hu_details(derivation.relations, rows[0], derivation.loc, derivation.hl, processing_events(derivation))
    return HuDetails(hu=hu, **details)


class LineageRequest(BaseModel):
    """Settings of the lineage chart.

    Attributes:
        handling_units: The selected handling units.
        direction: `components`, `products` or `both`.
        generations: Generations per direction; None = all.
        with_events: Bipartite graph.
        with_siblings: Add the siblings.
    """

    handling_units: list[str]
    direction: Direction = "both"
    generations: int | None = 2
    with_events: bool = False
    with_siblings: bool = False


class LineageNode(BaseModel):
    """A node of the lineage graph (see `instances.charts.SelectionLineage`)."""

    node: str
    kind: str
    role: str
    object_type: str | None = None
    activity: str | None = None
    time: str | None = None


class LineageEdge(BaseModel):
    """An edge of the lineage graph."""

    source: str
    target: str
    kind: str
    event: str | None = None
    directed: bool = True
    activity: str | None = None


class LineageResponse(BaseModel):
    """The lineage graph of the selected handling units."""

    nodes: list[LineageNode]
    edges: list[LineageEdge]
    notes: list[str]


@router.post("/{ocel_id}/instances/lineage", operation_id="getSelectionLineage")
def get_selection_lineage(derivation: CurrentDerivation, request: LineageRequest) -> LineageResponse:
    """The union of the lineage graphs of the selected handling units."""
    gen = math.inf if request.generations is None else request.generations
    lineage = selection_lineage(
        derivation, request.handling_units, request.direction, gen, request.with_events, request.with_siblings
    )
    return LineageResponse(
        nodes=[LineageNode(**row) for row in lineage.nodes.to_dicts()],
        edges=[LineageEdge(**row) for row in lineage.edges.to_dicts()],
        notes=lineage.notes,
    )


class TimelineRequest(BaseModel):
    """Settings of the HU timeline.

    Attributes:
        handling_units: Handling units, top to bottom.
        axis: "event order" or "time".
        show_high_level: Lower half of the band (agg(loc)).
        show_activity_labels: Activity names above the markers.
        mark_ties: Grey boxes behind events with the same timestamp.
        link_shared_events: Dotted lines between markers of shared events.
        by_first_event: Rows ordered by first event instead of the given order.
        label_movements: Also write the activity names of movements, starting exactly above their line.
    """

    handling_units: list[str]
    axis: TimelineAxis = "event order"
    show_high_level: bool = True
    show_activity_labels: bool = True
    mark_ties: bool = True
    link_shared_events: bool = True
    by_first_event: bool = False
    label_movements: bool = False


class TimelineResponse(BaseModel):
    """The HU timeline as a Plotly figure (`data`, `layout`) and notes."""

    figure: dict
    notes: list[str]
    max_handling_units: int = MAX_HANDLING_UNITS


@router.post("/{ocel_id}/instances/timeline", operation_id="getHuTimeline")
def get_hu_timeline(derivation: CurrentDerivation, request: TimelineRequest) -> TimelineResponse:
    """The HU timeline of the given handling units at the selected level."""
    if not request.handling_units:
        raise HTTPException(status_code=422, detail="No handling units given.")
    figure, notes = timeline_figure(
        derivation,
        request.handling_units,
        request.axis,
        request.show_high_level,
        request.show_activity_labels,
        request.mark_ties,
        request.link_shared_events,
        request.by_first_event,
        request.label_movements,
    )
    return TimelineResponse(figure=figure, notes=notes)


class ObjectGraphRequest(BaseModel):
    """The selected handling units of the object graph."""

    handling_units: list[str]


class ObjectGraphNode(BaseModel):
    """A node of the object graph (see `instances.object_graph.ObjectGraph`)."""

    node: str
    object_type: str | None = None
    is_hu: bool
    role: str
    n_events: int
    n_shared: int | None = None


class ArcEvent(BaseModel):
    """An event shared by the two objects of an event arc."""

    event: str
    time: datetime | None = None
    activity: str | None = None


class EventArc(BaseModel):
    """Undirected arc between two objects that share events."""

    source: str
    target: str
    events: list[ArcEvent]
    n_events: int


class O2oArc(BaseModel):
    """Directed o2o relation."""

    source: str
    target: str
    qualifier: str | None = None


class FocalEvent(BaseModel):
    """An event of a selected handling unit with the objects of the graph it involves."""

    event: str
    time: datetime | None = None
    activity: str | None = None
    objects: list[str]


class ObjectGraphResponse(BaseModel):
    """The object graph of the selected handling units.

    Attributes:
        nodes: Selected handling units first, then related handling units, then related other objects.
        event_arcs: Shared events.
        o2o_arcs: O2O relations.
        events: Events of the selected handling units (drawn as boxes if the user switches it on).
        notes: Remarks.
    """

    nodes: list[ObjectGraphNode]
    event_arcs: list[EventArc]
    o2o_arcs: list[O2oArc]
    events: list[FocalEvent]
    notes: list[str]


@router.post("/{ocel_id}/instances/object-graph", operation_id="getObjectGraph")
def get_object_graph(ocel: ApiOcel, derivation: CurrentDerivation, request: ObjectGraphRequest) -> ObjectGraphResponse:
    """The object graph of the selected handling units: they, every object related to them and all arcs between these."""
    graph = object_graph(object_frames(ocel), request.handling_units, derivation.handling_units["hu"].to_list())
    return ObjectGraphResponse(
        nodes=[ObjectGraphNode(**row) for row in graph.nodes.to_dicts()],
        event_arcs=[EventArc(**row) for row in graph.event_arcs.to_dicts()],
        o2o_arcs=[O2oArc(**row) for row in graph.o2o_arcs.to_dicts()],
        events=[FocalEvent(**row) for row in graph.events.to_dicts()],
        notes=graph.notes,
    )
