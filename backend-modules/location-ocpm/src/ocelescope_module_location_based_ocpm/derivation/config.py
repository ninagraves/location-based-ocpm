"""The user's choices for each input (`overview/Deriving Locations.md`, section "input data"; the location
context from `overview/concepts/Visit Mappings.md`, "Specific new notations", and `overview/module/Module Overview.md`).

Each input has several options; the user picks exactly one per input. Tables are referred to
by name: the caller passes the actual tables (from Ocelescope's table resource or a CSV) to
`inputs.resolve_inputs` in a dict keyed by these names.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator


class ObjectTypes(BaseModel):
    """Handling units = all objects of the selected object types."""

    option: Literal["object_types"] = "object_types"
    object_types: list[str]


class ObjectTable(BaseModel):
    """Handling units = the objects listed in a table."""

    option: Literal["table"] = "table"
    table: str
    object_column: str


class Activities(BaseModel):
    """Events = all events of the selected activities."""

    option: Literal["activities"] = "activities"
    activities: list[str]


class AttributeValues(BaseModel):
    """Events = all events whose event attribute has one of the selected values."""

    option: Literal["attribute_values"] = "attribute_values"
    attribute: str
    values: list[str]


class Qualifiers(BaseModel):
    """Events = all events with at least one e2o relation carrying one of the selected qualifiers."""

    option: Literal["qualifiers"] = "qualifiers"
    qualifiers: list[str]


class EventTable(BaseModel):
    """Events = the events listed in a table."""

    option: Literal["table"] = "table"
    table: str
    event_column: str


class LocationAttribute(BaseModel):
    """Locations from an event attribute."""

    option: Literal["attribute"] = "attribute"
    attribute: str


class LocationQualifiers(BaseModel):
    """Locations from e2o relations: the object related to an event via one of the qualifiers.

    Attributes:
        qualifiers: The e2o qualifiers (e.g. "to" for targets, "from" for pickups).
        name_attribute: Static object attribute used as the location name; None means the
            object id. Objects with an empty value fall back to their id.
    """

    option: Literal["qualifiers"] = "qualifiers"
    qualifiers: list[str]
    name_attribute: str | None = None


class LocationTable(BaseModel):
    """Locations from a table with an event column and a location column."""

    option: Literal["table"] = "table"
    table: str
    event_column: str
    location_column: str


class HighLevelTable(BaseModel):
    """High-level locations from a table with a location column and a high-level location column."""

    option: Literal["table"] = "table"
    table: str
    location_column: str
    high_level_column: str


class HighLevelEventAttributes(BaseModel):
    """High-level locations from two event attributes: every event with values in both gives a pair
    (low-level location, high-level location)."""

    option: Literal["event_attributes"] = "event_attributes"
    low_attribute: str
    high_attribute: str


class HighLevelObjectAttribute(BaseModel):
    """High-level locations from a static attribute of the location objects (e2o-qualifier locations only)."""

    option: Literal["object_attribute"] = "object_attribute"
    attribute: str


class HighLevelO2O(BaseModel):
    """High-level locations from o2o relations: a location object's related object via one of the
    qualifiers is its high-level location (e2o-qualifier locations only).

    Attributes:
        qualifiers: The o2o qualifiers (e.g. "part of").
        name_attribute: Static object attribute naming the high-level location; None means the object id.
    """

    option: Literal["o2o"] = "o2o"
    qualifiers: list[str]
    name_attribute: str | None = None


class HighLevelPattern(BaseModel):
    """High-level locations from the location names: a regular expression with one group, e.g. `^([A-Z]+)`;
    the group is the high-level location, locations the pattern does not match stay unmapped."""

    option: Literal["pattern"] = "pattern"
    pattern: str


class LocationList(BaseModel):
    """A set of locations, picked or typed in."""

    option: Literal["locations"] = "locations"
    locations: list[str]


class LocationSetTable(BaseModel):
    """A set of locations from a table: the locations of a column, optionally only rows whose
    true/false column is true ("true", "1", "yes", case-insensitive)."""

    option: Literal["table"] = "table"
    table: str
    location_column: str
    flag_column: str | None = None


class LocationAttributeValues(BaseModel):
    """A set of locations: the provided target locations of the events whose event attribute has one of the values."""

    option: Literal["attribute_values"] = "attribute_values"
    attribute: str
    values: list[str]


class LocationObjectTypes(BaseModel):
    """A set of locations: the location objects of the selected object types (e2o-qualifier locations only)."""

    option: Literal["object_types"] = "object_types"
    object_types: list[str]



class RolesFromQualifiers(BaseModel):
    """Option 1 of `overview/concepts/Transformations.md`: consumed and produced handling units from e2o qualifiers.

    T is derived: every event with at least one handling unit related via one of the qualifiers (the
    transformation-events input is not used).

    Attributes:
        consumed_qualifiers: e2o qualifiers meaning "consumed".
        produced_qualifiers: e2o qualifiers meaning "produced".
    """

    option: Literal["qualifiers"] = "qualifiers"
    consumed_qualifiers: list[str] = []
    produced_qualifiers: list[str] = []


class RolesFromTable(BaseModel):
    """Option 2: consumed and produced handling units from a table with one row per (event, handling unit, role).

    T = the transformation-events input if given, otherwise the events of the table.

    Attributes:
        table: Name of the table.
        event_column: Column of the event ids.
        object_column: Column of the handling unit ids.
        role_column: Column of the role.
        consumed_values: Values of the role column meaning "consumed".
        produced_values: Values of the role column meaning "produced".
    """

    option: Literal["table"] = "table"
    table: str
    event_column: str
    object_column: str
    role_column: str
    consumed_values: list[str] = ["consumed"]
    produced_values: list[str] = ["produced"]


class RolesFromParents(BaseModel):
    """Option 3: consumed and produced handling units from parent o2o relations (needs the transformation events).

    Attributes:
        qualifiers: o2o qualifiers of the parent-child relations.
        direction: `child_of`: the source object of the o2o relation is a child of the target object;
            `parent_of`: the source is a parent of the target.
    """

    option: Literal["parents"] = "parents"
    qualifiers: list[str]
    direction: Literal["child_of", "parent_of"] = "child_of"


class ObjectAttributeValues(BaseModel):
    """A set of objects: those whose (static) object attribute has one of the values."""

    option: Literal["attribute_values"] = "attribute_values"
    attribute: str
    values: list[str]


ObjectSetInput = Annotated[ObjectAttributeValues | ObjectTable, Field(discriminator="option")]


class RolesFromObjectSets(BaseModel):
    """Option 4: the handling units produced and consumed in the log are given (needs the transformation events).

    Attributes:
        produced: The handling units created in the log ($HU_{prod}$); None = none.
        consumed: The handling units consumed in the log ($HU_{cons}$); None = none.
        consumption: `final`: a consumed hu is consumed at its last event only; `partial`: at every
            transformation event it is involved in.
    """

    option: Literal["object_sets"] = "object_sets"
    produced: ObjectSetInput | None = None
    consumed: ObjectSetInput | None = None
    consumption: Literal["final", "partial"] = "final"


class RolesFromFirstLast(BaseModel):
    """Option 5: produced = hus whose first event is the transformation event, consumed = hus whose last event
    it is (needs the transformation events). Default if only transformation events are given."""

    option: Literal["first_last"] = "first_last"


class RolesFromFrequency(BaseModel):
    """Option 6: T, consumed and produced derived from the first and last events of the handling units.

    An activity qualifies if its share among the first (last) events of the hus of a handling unit type is at
    least `threshold`; T are the first (last) events of those activities; produced (consumed) are all hus whose
    first (last) event is in T. The transformation-events input is not used.

    Attributes:
        threshold: $\\tau$ in [0, 1].
    """

    option: Literal["frequency"] = "frequency"
    threshold: float = Field(0.5, ge=0, le=1)


class ProcessingOperations(BaseModel):
    """The processing operations P.

    Attributes:
        selection: Events selected like the transformation events; None selects no further events.
        include_transformations: True: P = selection ∪ T (default).
    """

    selection: Annotated[
        Activities | AttributeValues | Qualifiers | EventTable, Field(discriminator="option")
    ] | None = None
    include_transformations: bool = True


HandlingUnitsInput = Annotated[ObjectTypes | ObjectTable, Field(discriminator="option")]
MovementEventsInput = Annotated[Activities | AttributeValues | EventTable, Field(discriminator="option")]
TransformationEventsInput = Annotated[
    Activities | AttributeValues | Qualifiers | EventTable, Field(discriminator="option")
]
TransformationRolesInput = Annotated[
    RolesFromQualifiers
    | RolesFromTable
    | RolesFromParents
    | RolesFromObjectSets
    | RolesFromFirstLast
    | RolesFromFrequency,
    Field(discriminator="option"),
]
#: Options that take T from the transformation-events input (as candidates) and need it.
NEEDS_TRANSFORMATION_EVENTS = ("parents", "object_sets", "first_last")
#: Options that derive T themselves and ignore the transformation-events input.
DERIVES_TRANSFORMATION_EVENTS = ("qualifiers", "frequency")
LocationsInput = Annotated[
    LocationAttribute | LocationQualifiers | LocationTable, Field(discriminator="option")
]

HighLevelInput = Annotated[
    HighLevelTable | HighLevelEventAttributes | HighLevelObjectAttribute | HighLevelO2O | HighLevelPattern,
    Field(discriminator="option"),
]
LocationSetInput = Annotated[
    LocationList | LocationSetTable | LocationAttributeValues | LocationObjectTypes,
    Field(discriminator="option"),
]


class DerivationConfig(BaseModel):
    """All inputs of the location derivation, plus the selected level.

    Attributes:
        handling_units: Required.
        movement_events: Required (M).
        transformation_events: Optional (T, or the candidates for T); None means T = ∅ unless
            `transformation_roles` derives T (options `qualifiers`, `table`, `frequency`).
        transformation_roles: Optional ($cons$ and $prod$, `overview/concepts/Transformations.md`, "Deriving
            Starting Points"); None means option 5 (first/last timestamps) if transformation events are given.
        target_locations: Required (uloc).
        pickup_locations: Optional (puloc); None means no pickup locations.
        level: Selected location level k in 0..3 (default: the highest).
        high_level_locations: Optional (agg); None means every location is its own high-level location.
        vehicles: Optional (V); None means V = ∅.
        storage_units: Optional (W); None means W = ∅.
        processing_operations: Optional (P); None means P = T (∅ if there are no transformation events).
    """

    handling_units: HandlingUnitsInput
    movement_events: MovementEventsInput
    transformation_events: TransformationEventsInput | None = None
    transformation_roles: TransformationRolesInput | None = None
    target_locations: LocationsInput
    pickup_locations: LocationsInput | None = None
    level: Literal[0, 1, 2, 3] = 3
    high_level_locations: HighLevelInput | None = None
    vehicles: LocationSetInput | None = None
    storage_units: LocationSetInput | None = None
    processing_operations: ProcessingOperations | None = None

    @model_validator(mode="after")
    def _transformation_events_needed(self) -> "DerivationConfig":
        """Options 3 to 5 derive $cons$ and $prod$ for given transformation events, so they need them."""
        roles = self.transformation_roles
        if roles is not None and roles.option in NEEDS_TRANSFORMATION_EVENTS and self.transformation_events is None:
            raise ValueError(f"Consumed and produced handling units: option '{roles.option}' needs the transformation events.")
        return self
