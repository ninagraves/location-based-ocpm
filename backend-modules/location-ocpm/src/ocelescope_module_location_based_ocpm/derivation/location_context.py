"""Resolve the location context and the processing operations (`overview/module/Module Overview.md`,
"Update Overview Page", section 1; concepts in `overview/concepts/Visit Mappings.md`, "Specific new notations").

- High-level locations agg: L ⇸ HL from a table, two event attributes, an attribute of the location objects,
  o2o relations of the location objects, or a naming pattern. agg may be partial; unmapped locations are
  their own high-level location (identity).
- Vehicles V ⊆ L and storage units W ⊆ L from a list, a table, an event attribute (the provided target
  locations of the events with the selected values) or the object types of the location objects.
- Processing operations P ⊆ E like the transformation events, by default together with T; without any
  input P = T.

Rules (from the concept):
- Empty values (null, NaN, "", "NA") are never locations; such rows leave a location unmapped.
- Values that are not locations of L (the provided target and pickup locations) are dropped and reported.
- A location with two different high-level locations is a blocking error (agg must be a function).
- Options that need location objects only work if the target or pickup locations come from e2o qualifiers.
"""

import re
from collections.abc import Collection

import polars as pl
from ocelescope import OCEL

from ..visits.context import LocationContext
from . import columns as c
from .config import (
    DerivationConfig,
    HighLevelEventAttributes,
    HighLevelInput,
    HighLevelO2O,
    HighLevelObjectAttribute,
    HighLevelPattern,
    HighLevelTable,
    LocationAttributeValues,
    LocationList,
    LocationObjectTypes,
    LocationQualifiers,
    LocationSetInput,
    LocationSetTable,
    ProcessingOperations,
)
from .messages import BlockingError, Notice

#: Values of a true/false table column that count as true (compared in lower case).
TRUE_VALUES = ("true", "1", "yes", "y", "t", "x")

#: Column names of the frames returned here.
OBJECT = "object"
HIGH_LEVEL = "high_level"


def known_locations(events: pl.DataFrame) -> list[str]:
    """The locations L: all provided target and pickup locations.

    Args:
        events: Events with the columns uloc and puloc.

    Returns:
        list[str]: Sorted distinct locations.
    """
    values = pl.concat([events[c.ULOC], events[c.PULOC]]).drop_nulls().unique().sort()
    return values.to_list()


def _no_objects() -> pl.DataFrame:
    """An empty frame of location objects (columns object, object_type, location)."""
    return pl.DataFrame(schema={OBJECT: pl.String, c.OBJECT_TYPE: pl.String, c.LOCATION: pl.String})


def location_objects(ocel: OCEL, config: DerivationConfig) -> pl.DataFrame:
    """The location objects of the e2o-qualifier location inputs and their location names.

    Args:
        ocel: The log.
        config: The configuration; only target and pickup locations with the qualifier option count.

    Returns:
        pl.DataFrame: Columns object, object_type, location; one row per location object (empty if no
        location input uses qualifiers).
    """
    from .inputs import OCEL_OID, OCEL_QUALIFIER, OCEL_TYPE, location_names

    frames = []
    for option in (config.target_locations, config.pickup_locations):
        if not isinstance(option, LocationQualifiers):
            continue
        objects = (
            ocel.e2o.pl.filter(pl.col(OCEL_QUALIFIER).is_in(option.qualifiers))
            .select(pl.col(OCEL_OID).alias(OBJECT))
            .unique()
            .collect()[OBJECT]
        )
        frames.append(location_names(ocel, objects, option.name_attribute))
    if not frames:
        return _no_objects()
    types = ocel.objects.pl.select(OCEL_OID, OCEL_TYPE).collect().rename({OCEL_OID: OBJECT, OCEL_TYPE: c.OBJECT_TYPE})
    return (
        pl.concat(frames)
        .unique(OBJECT, keep="first")
        .join(types, on=OBJECT, how="left")
        .select(OBJECT, c.OBJECT_TYPE, c.LOCATION)
        .sort(OBJECT)
    )


def _no_location_objects(input_name: str) -> BlockingError:
    """Blocking error for an option that needs location objects when there are none."""
    return BlockingError(
        code="no_location_objects",
        message=f"{input_name}: this option needs location objects, i.e., target or pickup locations from e2o qualifiers.",
        ids=[],
    )


def _dropped(values: Collection[str], locations: Collection[str], input_name: str) -> list[Notice]:
    """Report values that are not locations of L (they are dropped).

    Args:
        values: The provided values.
        locations: L.
        input_name: Name of the input, for the message.

    Returns:
        list[Notice]: One notice if any value is not in L, else none.
    """
    unknown = sorted(set(values) - set(locations))
    if not unknown:
        return []
    return [
        Notice(
            code="unknown_locations_dropped",
            message=f"{input_name}: {len(unknown)} value{' is' if len(unknown) == 1 else 's are'} not a provided target "
            f"or pickup location and {'was' if len(unknown) == 1 else 'were'} dropped.",
            count=len(unknown),
            ids=unknown,
        )
    ]


def _provided_text(column: str) -> pl.Expr:
    """The column as text, null where the value is not provided (null, NaN, "", "NA")."""
    from .inputs import provided

    return pl.when(provided(column)).then(pl.col(column).cast(pl.String)).otherwise(None)


def mapping_pairs(
    ocel: OCEL,
    events: pl.DataFrame,
    option: HighLevelInput,
    tables: dict[str, pl.DataFrame],
    locations: list[str],
    objects: pl.DataFrame,
) -> tuple[pl.DataFrame, list[BlockingError]]:
    """The provided pairs (location, high-level location) of one high-level option.

    Args:
        ocel: The log (object attributes, o2o relations).
        events: Events of the log with all their attributes (see `inputs._log_events`).
        option: The chosen option.
        tables: User tables by name.
        locations: L (only used by the naming pattern).
        objects: Location objects (see `location_objects`).

    Returns:
        tuple[pl.DataFrame, list[BlockingError]]: Columns location, high_level (provided values only, may
        contain duplicates and conflicts); blocking errors (missing location objects, invalid pattern).
    """
    from .inputs import _table, location_names

    empty = pl.DataFrame(schema={c.LOCATION: pl.String, HIGH_LEVEL: pl.String})
    name = "High-level locations"
    if isinstance(option, HighLevelTable):
        table = _table(tables, option.table, [option.location_column, option.high_level_column])
        rows = table.select(
            _provided_text(option.location_column).alias(c.LOCATION),
            _provided_text(option.high_level_column).alias(HIGH_LEVEL),
        )
        return rows.drop_nulls(), []
    if isinstance(option, HighLevelEventAttributes):
        for attribute in (option.low_attribute, option.high_attribute):
            if attribute not in events.columns:
                raise KeyError(f"{name}: the log has no event attribute '{attribute}'.")
        rows = events.select(
            _provided_text(option.low_attribute).alias(c.LOCATION),
            _provided_text(option.high_attribute).alias(HIGH_LEVEL),
        )
        return rows.drop_nulls().unique(), []
    if isinstance(option, HighLevelPattern):
        try:
            compiled = re.compile(option.pattern)
        except re.error as error:
            return empty, [BlockingError(code="invalid_pattern", message=f"{name}: invalid pattern ({error}).", ids=[])]
        if compiled.groups < 1:
            return empty, [
                BlockingError(code="invalid_pattern", message=f"{name}: the pattern needs one group, e.g. ^([A-Z]+).", ids=[])
            ]
        frame = pl.DataFrame({c.LOCATION: locations}, schema={c.LOCATION: pl.String})
        rows = frame.with_columns(pl.col(c.LOCATION).str.extract(option.pattern, 1).alias(HIGH_LEVEL))
        return rows.filter(pl.col(HIGH_LEVEL).is_not_null() & (pl.col(HIGH_LEVEL) != "")), []
    if objects.is_empty():
        return empty, [_no_location_objects(name)]
    if isinstance(option, HighLevelObjectAttribute):
        named = location_names(ocel, objects[OBJECT], option.attribute)
        # location_names falls back to the id; here an object without a value stays unmapped.
        named = named.filter(pl.col(c.LOCATION) != pl.col(OBJECT)).rename({c.LOCATION: HIGH_LEVEL})
        rows = objects.join(named, on=OBJECT, how="inner").select(c.LOCATION, HIGH_LEVEL)
        return rows, []
    assert isinstance(option, HighLevelO2O)
    o2o = (
        ocel.o2o.pl.filter(pl.col("ocel:qualifier").is_in(option.qualifiers))
        .select(pl.col("ocel:oid_1").alias(OBJECT), pl.col("ocel:oid_2").alias("target"))
        .unique()
        .collect()
    )
    targets = location_names(ocel, o2o["target"], option.name_attribute).rename({OBJECT: "target", c.LOCATION: HIGH_LEVEL})
    rows = (
        objects.join(o2o, on=OBJECT, how="inner")
        .join(targets, on="target", how="left")
        .select(c.LOCATION, HIGH_LEVEL)
        .unique()
    )
    return rows.drop_nulls(), []


def resolve_high_level_locations(
    ocel: OCEL,
    events: pl.DataFrame,
    option: HighLevelInput | None,
    tables: dict[str, pl.DataFrame],
    locations: list[str],
    objects: pl.DataFrame,
) -> tuple[dict[str, str], list[Notice], list[BlockingError]]:
    """Resolve agg: L ⇸ HL.

    Args:
        ocel: The log.
        events: Events of the log with all their attributes.
        option: The chosen option; None = no high-level locations (identity).
        tables: User tables by name.
        locations: L.
        objects: Location objects (see `location_objects`).

    Returns:
        tuple[dict[str, str], list[Notice], list[BlockingError]]: agg as a dict (only the mapped locations);
        notices (dropped values, unmapped locations); blocking errors (a location with different high-level
        locations, missing location objects, invalid pattern).
    """
    if option is None:
        return {}, [], []
    pairs, errors = mapping_pairs(ocel, events, option, tables, locations, objects)
    if errors:
        return {}, [], errors
    name = "High-level locations"
    notices = _dropped(pairs[c.LOCATION].unique().to_list(), locations, name)
    pairs = pairs.filter(pl.col(c.LOCATION).is_in(locations)).unique()
    conflicting = pairs.group_by(c.LOCATION).agg(pl.len()).filter(pl.col("len") > 1)[c.LOCATION].sort()
    if conflicting.len():
        errors.append(
            BlockingError(
                code="ambiguous_high_level",
                message=f"{name}: locations with different high-level locations.",
                ids=conflicting.to_list(),
            )
        )
        return {}, notices, errors
    agg = dict(pairs.rows())
    unmapped = [location for location in locations if location not in agg]
    if unmapped:
        notices.append(
            Notice(
                code="unmapped_locations",
                message=f"{name}: {len(unmapped)} location{' is' if len(unmapped) == 1 else 's are'} not mapped and "
                f"keep{'s its' if len(unmapped) == 1 else ' their'} own name.",
                count=len(unmapped),
                ids=unmapped,
            )
        )
    return agg, notices, []


def resolve_location_set(
    events: pl.DataFrame,
    option: LocationSetInput | None,
    tables: dict[str, pl.DataFrame],
    locations: list[str],
    objects: pl.DataFrame,
    input_name: str,
) -> tuple[set[str], list[Notice], list[BlockingError]]:
    """Resolve a set of locations (vehicles V or storage units W).

    Args:
        events: Events of the log with all their attributes and uloc.
        option: The chosen option; None = the empty set.
        tables: User tables by name.
        locations: L.
        objects: Location objects (see `location_objects`).
        input_name: "Vehicles" or "Storage units", for messages.

    Returns:
        tuple[set[str], list[Notice], list[BlockingError]]: The set (∩ L); notices (dropped values); blocking
        errors (missing location objects).
    """
    from .inputs import _table

    if option is None:
        return set(), [], []
    if isinstance(option, LocationList):
        values = {value.strip() for value in option.locations if value.strip() not in ("", "NA")}
    elif isinstance(option, LocationSetTable):
        needed = [option.location_column] + ([option.flag_column] if option.flag_column else [])
        table = _table(tables, option.table, needed)
        rows = table.select(_provided_text(option.location_column).alias(c.LOCATION), *(
            [pl.col(option.flag_column).cast(pl.String).str.strip_chars().str.to_lowercase().is_in(TRUE_VALUES).fill_null(False).alias("flag")]
            if option.flag_column
            else []
        ))
        if option.flag_column:
            rows = rows.filter("flag")
        values = set(rows[c.LOCATION].drop_nulls().to_list())
    elif isinstance(option, LocationAttributeValues):
        if option.attribute not in events.columns:
            raise KeyError(f"{input_name}: the log has no event attribute '{option.attribute}'.")
        marked = events.filter(pl.col(option.attribute).cast(pl.String).is_in(option.values))
        values = set(marked[c.ULOC].drop_nulls().to_list())
    else:
        assert isinstance(option, LocationObjectTypes)
        if objects.is_empty():
            return set(), [], [_no_location_objects(input_name)]
        values = set(objects.filter(pl.col(c.OBJECT_TYPE).is_in(option.object_types))[c.LOCATION].to_list())
    return values & set(locations), _dropped(values, locations, input_name), []


def resolve_processing(
    ocel: OCEL,
    events: pl.DataFrame,
    option: ProcessingOperations | None,
    tables: dict[str, pl.DataFrame],
    transformations: pl.Series,
) -> tuple[pl.Series, list[Notice]]:
    """Resolve the processing operations P.

    Args:
        ocel: The log.
        events: Events of the log with all their attributes.
        option: The input; None = P = T.
        tables: User tables by name.
        transformations: T (event ids).

    Returns:
        tuple[pl.Series, list[Notice]]: P as unique event ids; notices (table rows with unknown events).
    """
    from .inputs import resolve_event_set

    if option is None:
        return transformations.unique(maintain_order=True), []
    selected, notices = pl.Series(c.EVENT, [], dtype=pl.String), []
    if option.selection is not None:
        selected, notices = resolve_event_set(ocel, events, option.selection, tables, "Processing operations")
    if option.include_transformations:
        selected = pl.concat([selected.cast(pl.String), transformations.cast(pl.String)])
    return selected.unique(maintain_order=True).alias(c.EVENT), notices


def resolve_location_context(
    ocel: OCEL,
    config: DerivationConfig,
    events: pl.DataFrame,
    tables: dict[str, pl.DataFrame],
) -> tuple[LocationContext, list[Notice], list[BlockingError]]:
    """Resolve agg, V and W of a configuration.

    Args:
        ocel: The log.
        config: The configuration.
        events: Events of the log with all their attributes and the resolved uloc, puloc.
        tables: User tables by name.

    Returns:
        tuple[LocationContext, list[Notice], list[BlockingError]]: The context; notices; blocking errors.
    """
    locations = known_locations(events)
    needs_objects = any(
        option is not None and option.option in ("object_attribute", "o2o", "object_types")
        for option in (config.high_level_locations, config.vehicles, config.storage_units)
    )
    objects = location_objects(ocel, config) if needs_objects else _no_objects()
    agg, notices, errors = resolve_high_level_locations(
        ocel, events, config.high_level_locations, tables, locations, objects
    )
    vehicles, found, blocking = resolve_location_set(events, config.vehicles, tables, locations, objects, "Vehicles")
    notices += found
    errors += blocking
    storage, found, blocking = resolve_location_set(
        events, config.storage_units, tables, locations, objects, "Storage units"
    )
    notices += found
    errors += blocking
    return LocationContext(agg=agg, vehicles=vehicles, storage_units=storage), notices, errors
