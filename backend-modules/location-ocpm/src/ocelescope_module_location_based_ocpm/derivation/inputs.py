"""Resolve the user's input choices on an OCEL (`overview/Deriving Locations.md`, section "input data").

The result is one frame of hu-event relations (`ResolvedInputs.relations`) carrying everything the
derivation needs per relation, plus a frame of all events (for events without handling units),
notices and blocking errors.

Rules implemented here (from the concept):
- Empty values (null, NaN, the empty string and "NA") are never locations.
- Table rows whose event id is not in the log are dropped and reported.
- An event with several different locations in a location table is a blocking error.
- Pickup locations of events that are not movement events are ignored and reported.
"""

from dataclasses import dataclass, field

import polars as pl
from ocelescope import OCEL

from . import columns as c
from .config import (
    Activities,
    AttributeValues,
    DerivationConfig,
    EventTable,
    LocationAttribute,
    LocationsInput,
    ObjectTable,
    ObjectTypes,
    Qualifiers,
)
from .messages import BlockingError, Notice

#: String values that count as "not provided" (besides null and NaN).
EMPTY_STRINGS = ("", "NA")

#: Column names of Ocelescope's OCEL tables.
OCEL_EID = "ocel:eid"
OCEL_OID = "ocel:oid"
OCEL_TYPE = "ocel:type"
OCEL_ACTIVITY = "ocel:activity"
OCEL_TIMESTAMP = "ocel:timestamp"
OCEL_QUALIFIER = "ocel:qualifier"


@dataclass
class ResolvedInputs:
    """All inputs resolved on one OCEL.

    Attributes:
        relations: One row per hu-event relation (e, hu) ∈ E2HU, with columns
            event, hu, object_type, time, activity, is_movement, is_transformation, uloc, puloc.
        events: One row per event of the log, with columns event, time, activity,
            is_movement, is_transformation, uloc, puloc.
        notices: Non-blocking reports (dropped rows, ignored pickups, ...).
        errors: Blocking errors; if not empty, the configuration cannot be applied.
    """

    relations: pl.DataFrame
    events: pl.DataFrame
    notices: list[Notice] = field(default_factory=list)
    errors: list[BlockingError] = field(default_factory=list)


def provided(column: str) -> pl.Expr:
    """Expression that is true where a value counts as provided.

    A value is not provided if it is null, NaN (for float columns), the empty string or "NA".

    Args:
        column: Name of the column to test.

    Returns:
        pl.Expr: Boolean expression.
    """
    as_text = pl.col(column).cast(pl.String)
    return (
        pl.col(column).is_not_null()
        & ~as_text.str.to_lowercase().eq("nan").fill_null(False)
        & ~as_text.is_in(EMPTY_STRINGS).fill_null(False)
    )


def _log_events(ocel: OCEL) -> pl.DataFrame:
    """Read the events of the log with all their attributes.

    Args:
        ocel: The log.

    Returns:
        pl.DataFrame: Events, renamed to the derivation's column names (event, time, activity)
        plus the event attributes under their own names.
    """
    return ocel.events.pl.collect().rename(
        {OCEL_EID: c.EVENT, OCEL_TIMESTAMP: c.TIME, OCEL_ACTIVITY: c.ACTIVITY}
    )


def _known_ids(ids: pl.Series, known: pl.Series, what: str, input_name: str) -> tuple[pl.Series, list[Notice]]:
    """Drop ids that are not in the log and report how many were dropped.

    Args:
        ids: Ids from a user table.
        known: All ids of that kind in the log.
        what: "event" or "object", for the message.
        input_name: Name of the input, for the message.

    Returns:
        tuple[pl.Series, list[Notice]]: The known ids and, if any were dropped, one notice.
    """
    ids = ids.cast(pl.String)
    unknown = ids.filter(~ids.is_in(known.implode()))
    notices = []
    if unknown.len():
        notices.append(
            Notice(
                code="unknown_ids_dropped",
                message=f"{input_name}: {unknown.len()} table rows refer to {what}s that are not in the log and were dropped.",
                count=unknown.len(),
                ids=unknown.unique(maintain_order=True).to_list(),
            )
        )
    return ids.filter(ids.is_in(known.implode())), notices


def _table(tables: dict[str, pl.DataFrame], name: str, needed: list[str]) -> pl.DataFrame:
    """Look up a user table and check that it has the needed columns.

    Args:
        tables: Tables passed by the caller, by name.
        name: Name of the table in the configuration.
        needed: Columns the configuration refers to.

    Returns:
        pl.DataFrame: The table.

    Raises:
        KeyError: If the table or a column is missing.
    """
    if name not in tables:
        raise KeyError(f"Table '{name}' is not available.")
    table = tables[name]
    missing = [col for col in needed if col not in table.columns]
    if missing:
        raise KeyError(f"Table '{name}' has no column(s) {', '.join(missing)}.")
    return table


def resolve_handling_units(
    ocel: OCEL, option: ObjectTypes | ObjectTable, tables: dict[str, pl.DataFrame]
) -> tuple[pl.DataFrame, list[Notice]]:
    """Resolve the handling units HU.

    Args:
        ocel: The log.
        option: Object types (all objects of these types) or a table with an object column.
        tables: User tables by name.

    Returns:
        tuple[pl.DataFrame, list[Notice]]: Frame with columns hu, object_type; and notices
        (table rows with unknown objects are dropped and reported).
    """
    objects = ocel.objects.pl.select(OCEL_OID, OCEL_TYPE).collect().rename({OCEL_OID: c.HU, OCEL_TYPE: c.OBJECT_TYPE})
    if isinstance(option, ObjectTypes):
        return objects.filter(pl.col(c.OBJECT_TYPE).is_in(option.object_types)), []
    table = _table(tables, option.table, [option.object_column])
    ids, notices = _known_ids(table[option.object_column], objects[c.HU], "object", "Handling units")
    return objects.filter(pl.col(c.HU).is_in(ids.implode())), notices


def resolve_event_set(
    ocel: OCEL,
    events: pl.DataFrame,
    option: Activities | AttributeValues | Qualifiers | EventTable,
    tables: dict[str, pl.DataFrame],
    input_name: str,
) -> tuple[pl.Series, list[Notice]]:
    """Resolve a set of events (movement events M or transformation events T).

    Args:
        ocel: The log (needed for the qualifier option).
        events: Events of the log, as returned by `_log_events`.
        option: Activities, attribute values, e2o qualifiers or a table with an event column.
        tables: User tables by name.
        input_name: Name of the input, for messages ("Movement events", ...).

    Returns:
        tuple[pl.Series, list[Notice]]: The selected event ids (unique); notices.
    """
    if isinstance(option, Activities):
        return events.filter(pl.col(c.ACTIVITY).is_in(option.activities))[c.EVENT], []
    if isinstance(option, AttributeValues):
        if option.attribute not in events.columns:
            raise KeyError(f"{input_name}: the log has no event attribute '{option.attribute}'.")
        return events.filter(pl.col(option.attribute).cast(pl.String).is_in(option.values))[c.EVENT], []
    if isinstance(option, Qualifiers):
        e2o = ocel.e2o.pl.select(OCEL_EID, OCEL_QUALIFIER).collect()
        return e2o.filter(pl.col(OCEL_QUALIFIER).is_in(option.qualifiers))[OCEL_EID].unique(maintain_order=True), []
    table = _table(tables, option.table, [option.event_column])
    ids, notices = _known_ids(table[option.event_column], events[c.EVENT], "event", input_name)
    return ids.unique(maintain_order=True), notices


def resolve_locations(
    events: pl.DataFrame, option: LocationsInput, tables: dict[str, pl.DataFrame], input_name: str
) -> tuple[pl.DataFrame, list[Notice], list[BlockingError]]:
    """Resolve a partial location function (uloc or puloc) as a table event → location.

    Args:
        events: Events of the log, as returned by `_log_events`.
        option: Event attribute, or a table with event and location columns.
        tables: User tables by name.
        input_name: Name of the input, for messages ("Target locations", ...).

    Returns:
        tuple[pl.DataFrame, list[Notice], list[BlockingError]]: Frame with columns event, location
        (only events with a provided location, one row each); notices; blocking errors
        (an event with different locations in the table).
    """
    if isinstance(option, LocationAttribute):
        if option.attribute not in events.columns:
            raise KeyError(f"{input_name}: the log has no event attribute '{option.attribute}'.")
        located = events.filter(provided(option.attribute)).select(
            c.EVENT, pl.col(option.attribute).cast(pl.String).alias(c.LOCATION)
        )
        return located, [], []
    table = _table(tables, option.table, [option.event_column, option.location_column])
    rows = table.select(
        pl.col(option.event_column).cast(pl.String).alias(c.EVENT),
        pl.col(option.location_column).alias(c.LOCATION),
    )
    rows = rows.filter(provided(c.LOCATION)).with_columns(pl.col(c.LOCATION).cast(pl.String))
    known, notices = _known_ids(rows[c.EVENT], events[c.EVENT], "event", input_name)
    rows = rows.filter(pl.col(c.EVENT).is_in(known.implode())).unique()
    conflicting = rows.group_by(c.EVENT).agg(pl.len()).filter(pl.col("len") > 1)[c.EVENT].sort()
    errors = []
    if conflicting.len():
        errors.append(
            BlockingError(
                code="conflicting_locations",
                message=f"{input_name}: events with different locations in the table.",
                ids=conflicting.to_list(),
            )
        )
        rows = rows.filter(~pl.col(c.EVENT).is_in(conflicting.implode()))
    return rows, notices, errors


def resolve_inputs(ocel: OCEL, config: DerivationConfig, tables: dict[str, pl.DataFrame] | None = None) -> ResolvedInputs:
    """Resolve all inputs of a configuration on an OCEL.

    Args:
        ocel: The log.
        config: The user's choices.
        tables: User tables by name (from the table resource or CSV); only needed for table options.

    Returns:
        ResolvedInputs: Relations and events frames with M, T, uloc and puloc, plus notices and
        blocking errors of the resolution (the requirements RQ1-RQ3 are checked separately,
        see `requirements.check_requirements`).
    """
    tables = tables or {}
    notices: list[Notice] = []
    errors: list[BlockingError] = []
    events = _log_events(ocel)

    hus, found = resolve_handling_units(ocel, config.handling_units, tables)
    notices += found
    movements, found = resolve_event_set(ocel, events, config.movement_events, tables, "Movement events")
    notices += found
    if config.transformation_events is None:
        transformations = pl.Series(c.EVENT, [], dtype=pl.String)
    else:
        transformations, found = resolve_event_set(
            ocel, events, config.transformation_events, tables, "Transformation events"
        )
        notices += found
    uloc, found, blocking = resolve_locations(events, config.target_locations, tables, "Target locations")
    notices += found
    errors += blocking
    if config.pickup_locations is None:
        puloc = pl.DataFrame(schema={c.EVENT: pl.String, c.LOCATION: pl.String})
    else:
        puloc, found, blocking = resolve_locations(events, config.pickup_locations, tables, "Pickup locations")
        notices += found
        errors += blocking
        ignored = puloc.filter(~pl.col(c.EVENT).is_in(movements.implode()))
        if ignored.height:
            notices.append(
                Notice(
                    code="pickups_of_non_movements_ignored",
                    message=f"Pickup locations: {ignored.height} events with a pickup location are not movement events; their pickup locations are ignored.",
                    count=ignored.height,
                    ids=ignored[c.EVENT].to_list(),
                )
            )
        puloc = puloc.filter(pl.col(c.EVENT).is_in(movements.implode()))

    events = events.select(c.EVENT, c.TIME, c.ACTIVITY).with_columns(
        pl.col(c.EVENT).is_in(movements.implode()).alias(c.IS_MOVEMENT),
        pl.col(c.EVENT).is_in(transformations.implode()).alias(c.IS_TRANSFORMATION),
    )
    events = events.join(uloc.rename({c.LOCATION: c.ULOC}), on=c.EVENT, how="left").join(
        puloc.rename({c.LOCATION: c.PULOC}), on=c.EVENT, how="left"
    )
    e2hu = (
        ocel.e2o.pl.select(OCEL_EID, OCEL_OID)
        .collect()
        .rename({OCEL_EID: c.EVENT, OCEL_OID: c.HU})
        .unique()
        .join(hus, on=c.HU, how="inner")
    )
    relations = e2hu.join(events, on=c.EVENT, how="inner").sort(c.HU, c.TIME, c.EVENT)
    return ResolvedInputs(relations=relations, events=events.sort(c.TIME, c.EVENT), notices=notices, errors=errors)
