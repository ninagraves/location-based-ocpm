"""Resolve the user's input choices on an OCEL (`overview/Deriving Locations.md`, section "input data").

The result is one frame of hu-event relations (`ResolvedInputs.relations`) carrying everything the
derivation needs per relation, plus a frame of all events (for events without handling units),
notices and blocking errors.

Rules implemented here (from the concept):
- Empty values (null, NaN, the empty string and "NA") are never locations.
- Table rows whose event id is not in the log are dropped and reported.
- An event with several different locations in a location table is a blocking error.
- Pickup locations of events that are not movement events are ignored and reported.
- e2o-qualifier locations: an event related to more than one distinct object via the selected
  qualifiers is a blocking error, and so is a location object that is also a handling unit.
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
    LocationQualifiers,
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


def location_names(ocel: OCEL, objects: pl.Series, name_attribute: str | None) -> pl.DataFrame:
    """Name of each location object: its id, or the value of a static object attribute.

    Args:
        ocel: The log.
        objects: Ids of the location objects.
        name_attribute: Object attribute holding the name; None means the object id. Objects
            without a provided value keep their id. If the attribute changes over time, the
            last provided value is used (the configuration form only offers static attributes).

    Returns:
        pl.DataFrame: Columns object (id) and location (name), one row per object.
    """
    names = pl.DataFrame({"object": objects.unique()}, schema={"object": pl.String})
    if name_attribute is None:
        return names.with_columns(pl.col("object").alias(c.LOCATION))
    if name_attribute not in ocel.objects.attribute_names:
        raise KeyError(f"The log has no object attribute '{name_attribute}'.")
    states = (
        ocel.objects.attribute_states(None, [name_attribute])
        .pl()
        .filter(provided(name_attribute))
        .sort(OCEL_TIMESTAMP)
        .group_by(OCEL_OID)
        .agg(pl.col(name_attribute).last().cast(pl.String).alias(c.LOCATION))
        .rename({OCEL_OID: "object"})
    )
    return names.join(states, on="object", how="left").with_columns(
        pl.col(c.LOCATION).fill_null(pl.col("object"))
    )


def _qualifier_locations(
    ocel: OCEL, option: LocationQualifiers, input_name: str, handling_units: pl.Series | None
) -> tuple[pl.DataFrame, list[BlockingError]]:
    """Locations from e2o relations with the selected qualifiers.

    Args:
        ocel: The log.
        option: Qualifiers and the optional name attribute.
        input_name: Name of the input, for messages.
        handling_units: Ids of the handling units, to check that no location object is one.

    Returns:
        tuple[pl.DataFrame, list[BlockingError]]: Frame with columns event, location (one row per
        event with exactly one related object); blocking errors (events with more than one
        object, location objects that are handling units).
    """
    related = (
        ocel.e2o.pl.filter(pl.col(OCEL_QUALIFIER).is_in(option.qualifiers))
        .select(pl.col(OCEL_EID).alias(c.EVENT), pl.col(OCEL_OID).alias("object"))
        .unique()
        .collect()
    )
    errors = []
    objects_per_event = related.group_by(c.EVENT).agg(pl.col("object").sort())
    several = objects_per_event.filter(pl.col("object").list.len() > 1).sort(c.EVENT)
    if several.height:
        event, objects = several.row(0)
        errors.append(
            BlockingError(
                code="several_location_objects",
                message=f"{input_name}: {several.height} events are related to more than one object via the "
                f"selected qualifiers, e.g. {event}: more than one location ({', '.join(objects)}).",
                ids=several[c.EVENT].to_list(),
            )
        )
        related = related.filter(~pl.col(c.EVENT).is_in(several[c.EVENT].implode()))
    if handling_units is not None:
        both = related["object"].unique().filter(related["object"].unique().is_in(handling_units.implode())).sort()
        if both.len():
            errors.append(
                BlockingError(
                    code="location_object_is_handling_unit",
                    message=f"{input_name}: {both.len()} location objects are also handling units.",
                    ids=both.to_list(),
                )
            )
    names = location_names(ocel, related["object"], option.name_attribute)
    return related.join(names, on="object", how="left").select(c.EVENT, c.LOCATION), errors


def resolve_locations(
    events: pl.DataFrame,
    option: LocationsInput,
    tables: dict[str, pl.DataFrame],
    input_name: str,
    ocel: OCEL | None = None,
    handling_units: pl.Series | None = None,
) -> tuple[pl.DataFrame, list[Notice], list[BlockingError]]:
    """Resolve a partial location function (uloc or puloc) as a table event → location.

    Args:
        events: Events of the log, as returned by `_log_events`.
        option: Event attribute, e2o qualifiers, or a table with event and location columns.
        tables: User tables by name.
        input_name: Name of the input, for messages ("Target locations", ...).
        ocel: The log; only needed for the e2o-qualifier option.
        handling_units: Ids of the handling units; only used by the e2o-qualifier option.

    Returns:
        tuple[pl.DataFrame, list[Notice], list[BlockingError]]: Frame with columns event, location
        (only events with a provided location, one row each); notices; blocking errors
        (an event with different locations in the table, or with several location objects).
    """
    if isinstance(option, LocationQualifiers):
        if ocel is None:
            raise ValueError("The e2o-qualifier option needs the log.")
        located, errors = _qualifier_locations(ocel, option, input_name, handling_units)
        return located, [], errors
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
    uloc, found, blocking = resolve_locations(
        events, config.target_locations, tables, "Target locations", ocel, hus[c.HU]
    )
    notices += found
    errors += blocking
    if config.pickup_locations is None:
        puloc = pl.DataFrame(schema={c.EVENT: pl.String, c.LOCATION: pl.String})
    else:
        puloc, found, blocking = resolve_locations(
            events, config.pickup_locations, tables, "Pickup locations", ocel, hus[c.HU]
        )
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
