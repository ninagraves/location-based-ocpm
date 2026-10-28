"""API routes of the configuration: table upload, form options, apply, and the cached derivation.

Every route below works on the module state of the current backend session (see `state.py`).
Routes with `{ocel_id}` read the log as Ocelescope currently shows it, i.e. with Ocelescope's own
filters applied.
"""

from typing import Annotated

import polars as pl
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from ocelescope import OCEL
from ocelescope_backend.app.dependencies import ApiOcel, ApiSession

from ocelescope_module_location_based_ocpm.api_models import (
    ApplyResult,
    ConfigState,
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
from ocelescope_module_location_based_ocpm.state import (
    STATE_KEY,
    CachedDerivation,
    ModuleState,
    UploadedTable,
    fingerprint,
)

router = APIRouter()

#: Number of table rows sent as preview.
PREVIEW_ROWS = 5
#: Maximum number of distinct values the attribute-value picker offers.
MAX_ATTRIBUTE_VALUES = 500


def get_state(session: ApiSession) -> ModuleState:
    """The module's state in the current session (created on first use).

    Args:
        session: The backend session.

    Returns:
        ModuleState: Tables, configurations and cache of this session.
    """
    return session.get_module_state(STATE_KEY, ModuleState)


State = Annotated[ModuleState, Depends(get_state)]


def log_version(session: ApiSession, ocel_id: str) -> str:
    """Identify the current version of a log: its Ocelescope filter pipeline.

    Ocelescope keeps the original log unchanged and applies its filters on top, so the log a
    request sees only changes when the filters change.

    Args:
        session: The backend session.
        ocel_id: Id of the log.

    Returns:
        str: A text that changes whenever the filter pipeline changes.
    """
    return repr([f.model_dump(mode="json") | {"type": type(f).__name__} for f in session.get_filter(ocel_id)])


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


def current_derivation(ocel_id: str, ocel: ApiOcel, session: ApiSession, state: State) -> Derivation:
    """The derivation of a log under its applied configuration, from the cache if still valid.

    Content routes use this as a dependency. The cache holds one derivation per log; it is reused
    while configuration, log version (Ocelescope filters) and used tables are unchanged, and
    recomputed otherwise.

    Args:
        ocel_id: Id of the log.
        ocel: The log (with Ocelescope's filters).
        session: The backend session.
        state: The module state.

    Returns:
        Derivation: The current derivation.

    Raises:
        HTTPException: 409 if no configuration is applied, or if it no longer works on the
            current log (e.g. after an Ocelescope filter change); the detail says why.
    """
    config = state.configs.get(ocel_id)
    if config is None:
        raise HTTPException(status_code=409, detail="No configuration applied for this log yet.")
    key = fingerprint(config, log_version(session, ocel_id), state.tables)
    cached = state.cache.get(ocel_id)
    if cached is not None and cached.key == key:
        return cached.derivation
    result = run_derivation(ocel, config, state)
    if isinstance(result, list) or result.errors:
        errors = result if isinstance(result, list) else [Message.of(e) for e in result.errors]
        raise HTTPException(
            status_code=409,
            detail="The applied configuration does not work on the current log: "
            + " ".join(e.message for e in errors),
        )
    state.cache[ocel_id] = CachedDerivation(key=key, derivation=result)
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
    ocel_id: str, body: DerivationConfig, ocel: ApiOcel, session: ApiSession, state: State
) -> ApplyResult:
    """Derive with a configuration; store and cache it only if there is no blocking error.

    A configuration that cannot be applied leaves the previously applied one in place.
    """
    result = run_derivation(ocel, body, state)
    if isinstance(result, list):
        return ApplyResult(applied=False, errors=result)
    notices = [Message.of(n) for n in result.notices]
    if result.errors:
        return ApplyResult(applied=False, errors=[Message.of(e) for e in result.errors], notices=notices)
    state.configs[ocel_id] = body
    state.cache[ocel_id] = CachedDerivation(
        key=fingerprint(body, log_version(session, ocel_id), state.tables), derivation=result
    )
    return ApplyResult(applied=True, notices=notices)


# endregion
