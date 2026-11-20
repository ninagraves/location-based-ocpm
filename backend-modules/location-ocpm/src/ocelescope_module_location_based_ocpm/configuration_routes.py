"""API routes of the configuration: table upload, form options, apply, and the cached derivation.

Every route below works on the module state of the current backend session (see `state.py`).
Routes with `{ocel_id}` read the log as Ocelescope currently shows it, i.e. its active view (the
log with Ocelescope's own filters applied), unless the request names another view (`view_id`) or
the original log (`ocel_version=original`).
"""

import threading
from collections.abc import Callable
from typing import Annotated, Literal

import polars as pl
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from ocelescope import OCEL
from ocelescope_backend.app.dependencies import ApiOcel, ApiSession
from ocelescope_backend.app.internal.session import Session

from ocelescope_module_location_based_ocpm.api_models import (
    ApplyResult,
    ConfigState,
    LocationOptions,
    LocationRequest,
    LogOptions,
    Message,
    TableInfo,
    ValueCount,
)
from ocelescope_module_location_based_ocpm.derivation.config import DerivationConfig
from ocelescope_module_location_based_ocpm.derivation.inputs import (
    OCEL_ACTIVITY,
    OCEL_QUALIFIER,
    OCEL_TYPE,
    provided,
)
from ocelescope_module_location_based_ocpm.derivation.pipeline import Derivation, derive
from ocelescope_module_location_based_ocpm.global_settings import GlobalSettings, effective_config
from ocelescope_module_location_based_ocpm.state import (
    CachedDerivation,
    ModuleState,
    SessionStates,
    UploadedTable,
    fingerprint,
)

router = APIRouter()

#: Number of table rows sent as preview.
PREVIEW_ROWS = 5
#: Maximum number of distinct values the attribute-value picker offers.
MAX_ATTRIBUTE_VALUES = 500
#: Which log a request reads, as in Ocelescope's `ApiOcel` dependency.
OcelVersion = Literal["original", "filtered"]

#: Module states of all backend sessions.
STATES = SessionStates()


#: Called in a background thread whenever a new derivation is cached, e.g. to precompute the directly-follows graph
#: before the user opens its page (`dfg_routes`; Nina, 2026-11-16). Arguments: log id, a function that opens the log
#: (the request's log is closed when the request ends, so a hook opens and closes its own), the cached derivation.
ON_DERIVED: list[Callable[[str, Callable[[], OCEL], CachedDerivation], None]] = []


def open_log(session: Session, ocel_id: str, ocel_version: OcelVersion = "filtered", view_id: str | None = None) -> OCEL:
    """Open the log a request reads, outside the request (as Ocelescope's `ApiOcel` does; the caller closes it).

    Example: `open_log(session, ocel_id)` opens the active view, i.e. the log with Ocelescope's filters.

    Args:
        session: The backend session.
        ocel_id: Id of the log.
        ocel_version: "original" for the unfiltered log, "filtered" for the active view.
        view_id: A specific view instead of the active one.

    Returns:
        OCEL: The opened log.

    Raises:
        HTTPException: 404 if the log or the view does not exist (any more).
    """
    handle = session.get_ocel(ocel_id)
    if view_id is None:
        return handle.open(use_original=ocel_version == "original")
    view = handle.get_view(view_id)
    if view is None:
        raise HTTPException(status_code=404, detail=f"View {view_id} not found")
    return view.open()


def _cache_derivation(
    state: ModuleState,
    session: Session,
    ocel_id: str,
    cached: CachedDerivation,
    ocel_version: OcelVersion = "filtered",
    view_id: str | None = None,
) -> None:
    """Make a derivation the current one of a log (`ModuleState.remember`) and start the `ON_DERIVED` hooks in the
    background.

    Args:
        state: The module state.
        session: The backend session (to open the log again in the background).
        ocel_id: Id of the log.
        cached: The derivation and its cache key.
        ocel_version: Which log the derivation was computed on (see `log_version`).
        view_id: A specific Ocelescope view (see `log_version`).
    """
    state.remember(ocel_id, cached)

    def opener() -> OCEL:
        """Open the same log version as the request (in the hook's thread)."""
        return open_log(session, ocel_id, ocel_version, view_id)

    for hook in ON_DERIVED:
        threading.Thread(target=hook, args=(ocel_id, opener, cached), daemon=True).start()


def get_state(session: ApiSession) -> ModuleState:
    """The module's state in the current session (created on first use).

    Args:
        session: The backend session.

    Returns:
        ModuleState: Tables, configurations and cache of this session.
    """
    return STATES.get(session.id, Session.sessions.keys())


State = Annotated[ModuleState, Depends(get_state)]


def log_version(
    session: ApiSession, ocel_id: str, ocel_version: OcelVersion = "filtered", view_id: str | None = None
) -> str:
    """Identify the version of a log a request reads: the original log or one of its views.

    Ocelescope (since 0.13) keeps the original log unchanged and shows its filters as views. A
    view's id is a hash over the log and the view's operations, so the log a request sees only
    changes when the view changes. The arguments mirror those of Ocelescope's `ApiOcel`.

    Args:
        session: The backend session.
        ocel_id: Id of the log.
        ocel_version: "original" for the unfiltered log, "filtered" for the active view.
        view_id: A specific view instead of the active one.

    Returns:
        str: "original" or "view:<id>"; it changes whenever the log the request reads changes.
    """
    if view_id is not None:
        return f"view:{view_id}"
    if ocel_version == "original":
        return "original"
    active = session.get_ocel(ocel_id).active_view_id
    return "original" if active is None else f"view:{active}"


def _table_info(table: UploadedTable) -> TableInfo:
    """Describe an uploaded table for the form.

    Args:
        table: The table.

    Returns:
        TableInfo: Name, columns, row count and preview.
    """
    return TableInfo(
        name=table.name,
        columns=table.frame.columns,
        row_count=table.frame.height,
        preview=table.frame.head(PREVIEW_ROWS).to_dicts(),
    )


def _counts(frame: pl.LazyFrame, column: str) -> list[ValueCount]:
    """Count the values of a column, most frequent first (ties alphabetical).

    Args:
        frame: The table.
        column: The column to count.

    Returns:
        list[ValueCount]: One entry per non-empty value.
    """
    counted = (
        frame.filter(pl.col(column).is_not_null())
        .group_by(pl.col(column).cast(pl.String).alias("value"))
        .agg(pl.len().alias("count"))
        .sort(["count", "value"], descending=[True, False])
        .collect()
    )
    return [ValueCount(value=value, count=count) for value, count in counted.rows()]


def run_derivation(ocel: OCEL, config: DerivationConfig, state: ModuleState) -> Derivation | list[Message]:
    """Derive with the session's tables, turning missing tables or attributes into errors.

    Args:
        ocel: The log.
        config: The configuration.
        state: The module state (for the uploaded tables).

    Returns:
        Derivation | list[Message]: The derivation, or the errors if a table, a column or an
        attribute the configuration refers to does not exist.
    """
    try:
        return derive(ocel, config, state.frames())
    except KeyError as error:
        return [Message(code="missing_input", message=str(error.args[0]), count=0, ids=[])]


def current_derivation(
    ocel_id: str,
    ocel: ApiOcel,
    session: ApiSession,
    state: State,
    ocel_version: OcelVersion = "filtered",
    view_id: str | None = None,
) -> Derivation:
    """The derivation of a log under its effective configuration, from the cache if still valid.

    Content routes use this as a dependency. The effective configuration is the applied one with the settings
    bar applied (`global_settings.effective_config`: without high-level locations in low mode), so every page
    follows the bar. The cache keeps the current and the previous derivation per log (`ModuleState.recent`); one
    is reused while configuration, settings, log version (Ocelescope view) and used tables are unchanged, else the
    log is derived again.

    Args:
        ocel_id: Id of the log.
        ocel: The log (with Ocelescope's filters).
        session: The backend session.
        state: The module state.
        ocel_version: Which log the request reads (see `log_version`).
        view_id: A specific Ocelescope view (see `log_version`).

    Returns:
        Derivation: The current derivation.

    Raises:
        HTTPException: 409 if no configuration is applied, or if it no longer works on the
            current log (e.g. after an Ocelescope filter change); the detail says why.
    """
    config = state.configs.get(ocel_id)
    if config is None:
        raise HTTPException(status_code=409, detail="No configuration applied for this log yet.")
    config = effective_config(config, state.settings.get(ocel_id))
    key = fingerprint(config, log_version(session, ocel_id, ocel_version, view_id), state.tables)
    cached = state.cache.get(ocel_id)
    if cached is not None and cached.key == key:
        return cached.derivation
    recalled = state.recall(ocel_id, key)
    if recalled is not None:
        return recalled.derivation
    result = run_derivation(ocel, config, state)
    if isinstance(result, list) or result.errors:
        errors = result if isinstance(result, list) else [Message.of(e) for e in result.errors]
        raise HTTPException(
            status_code=409,
            detail="The applied configuration does not work on the current log: "
            + " ".join(e.message for e in errors),
        )
    _cache_derivation(state, session, ocel_id, CachedDerivation(key=key, derivation=result), ocel_version, view_id)
    return result


CurrentDerivation = Annotated[Derivation, Depends(current_derivation)]


# region Tables


@router.post("/tables", operation_id="uploadTable")
async def upload_table(file: UploadFile, state: State) -> TableInfo:
    """Upload a CSV table that table options of the configuration can refer to.

    Every column is read as text. A table with the same file name is replaced.
    """
    try:
        table = state.add_table(file.filename or "table.csv", await file.read())
    except Exception as error:
        raise HTTPException(status_code=422, detail=f"Could not read the CSV file: {error}") from error
    return _table_info(table)


@router.get("/tables", operation_id="listTables")
def list_tables(state: State) -> list[TableInfo]:
    """All uploaded tables of the session."""
    return [_table_info(table) for table in state.tables.values()]


# endregion
# region Configuration


@router.get("/{ocel_id}/options", operation_id="getOptions")
def get_options(ocel: ApiOcel) -> LogOptions:
    """Object types, activities, qualifiers and attribute names offered by the form, with counts."""
    events = ocel.events.pl
    return LogOptions(
        object_types=_counts(ocel.objects.pl, OCEL_TYPE),
        activities=_counts(events, OCEL_ACTIVITY),
        qualifiers=_counts(ocel.e2o.pl, OCEL_QUALIFIER),
        event_attributes=[name for name in events.collect_schema().names() if not name.startswith("ocel:")],
        object_attributes=ocel.objects.static_attribute_names,
        o2o_qualifiers=_counts(ocel.o2o.pl, OCEL_QUALIFIER),
    )


@router.post("/{ocel_id}/locations", operation_id="getLocations")
def get_locations(ocel: ApiOcel, body: LocationRequest, state: State) -> LocationOptions:
    """The locations L of the given target and pickup inputs, with their number of events, and the object types
    of the location objects; used by the location-context pickers and the location template."""
    from ocelescope_module_location_based_ocpm.derivation.inputs import _log_events, resolve_locations
    from ocelescope_module_location_based_ocpm.derivation.location_context import location_objects

    events = _log_events(ocel)
    frames, problems = [], []
    for option, name in ((body.target_locations, "Target locations"), (body.pickup_locations, "Pickup locations")):
        if option is None:
            continue
        try:
            located, _, errors = resolve_locations(events, option, state.frames(), name, ocel)
        except KeyError as error:
            problems.append(str(error.args[0]))
            continue
        problems += [e.message for e in errors]
        frames.append(located)
    if not frames:
        return LocationOptions(problems=problems)
    located = pl.concat(frames).unique()
    config = DerivationConfig.model_construct(target_locations=body.target_locations, pickup_locations=body.pickup_locations)
    objects = location_objects(ocel, config)
    return LocationOptions(
        locations=_counts(located.lazy(), "location"),
        location_object_types=_counts(objects.lazy(), "object_type") if objects.height else [],
        problems=problems,
    )


@router.get("/{ocel_id}/attribute-values", operation_id="getAttributeValues")
def get_attribute_values(ocel: ApiOcel, attribute: str) -> list[ValueCount]:
    """Provided values of an event attribute with their number of events (most frequent first)."""
    events = ocel.events.pl
    if attribute.startswith("ocel:") or attribute not in events.collect_schema().names():
        raise HTTPException(status_code=404, detail=f"The log has no event attribute '{attribute}'.")
    return _counts(events.filter(provided(attribute)), attribute)[:MAX_ATTRIBUTE_VALUES]


@router.get("/{ocel_id}/config", operation_id="getConfig")
def get_config(ocel_id: str, state: State) -> ConfigState:
    """The applied configuration of a log, if any, with the notices of its derivation."""
    cached = state.cache.get(ocel_id)
    notices = [Message.of(n) for n in cached.derivation.notices] if cached else []
    return ConfigState(config=state.configs.get(ocel_id), notices=notices)


@router.post("/{ocel_id}/config", operation_id="applyConfig")
def apply_config(
    ocel_id: str,
    body: DerivationConfig,
    ocel: ApiOcel,
    session: ApiSession,
    state: State,
    ocel_version: OcelVersion = "filtered",
    view_id: str | None = None,
) -> ApplyResult:
    """Derive with a configuration; store and cache it only if there is no blocking error.

    A configuration that cannot be applied leaves the previously applied one in place. If it adds high-level
    locations to a configuration without them, the settings bar switches to Locations: high (the default).
    """
    result = run_derivation(ocel, body, state)
    if isinstance(result, list):
        return ApplyResult(applied=False, errors=result)
    notices = [Message.of(n) for n in result.notices]
    if result.errors:
        return ApplyResult(applied=False, errors=[Message.of(e) for e in result.errors], notices=notices)
    previous = state.configs.get(ocel_id)
    if body.high_level_locations is not None and (previous is None or previous.high_level_locations is None):
        state.settings[ocel_id] = GlobalSettings(location_mode="high")
    state.configs[ocel_id] = body
    key = fingerprint(body, log_version(session, ocel_id, ocel_version, view_id), state.tables)
    _cache_derivation(state, session, ocel_id, CachedDerivation(key=key, derivation=result), ocel_version, view_id)
    return ApplyResult(applied=True, notices=notices)


# endregion
