"""The user's choices for each input (`overview/Deriving Locations.md`, section "input data").

Each input has several options; the user picks exactly one per input. Tables are referred to
by name: the caller passes the actual tables (from Ocelescope's table resource or a CSV) to
`inputs.resolve_inputs` in a dict keyed by these names.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field


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


HandlingUnitsInput = Annotated[ObjectTypes | ObjectTable, Field(discriminator="option")]
MovementEventsInput = Annotated[Activities | AttributeValues | EventTable, Field(discriminator="option")]
TransformationEventsInput = Annotated[
    Activities | AttributeValues | Qualifiers | EventTable, Field(discriminator="option")
]
LocationsInput = Annotated[
    LocationAttribute | LocationQualifiers | LocationTable, Field(discriminator="option")
]


class DerivationConfig(BaseModel):
    """All inputs of the location derivation, plus the selected level.

    Attributes:
        handling_units: Required.
        movement_events: Required (M).
        transformation_events: Optional (T); None means T = ∅, so Level 3 equals Level 2.
        target_locations: Required (uloc).
        pickup_locations: Optional (puloc); None means no pickup locations.
        level: Selected location level k in 0..3 (default: the highest).
    """

    handling_units: HandlingUnitsInput
    movement_events: MovementEventsInput
    transformation_events: TransformationEventsInput | None = None
    target_locations: LocationsInput
    pickup_locations: LocationsInput | None = None
    level: Literal[0, 1, 2, 3] = 3
