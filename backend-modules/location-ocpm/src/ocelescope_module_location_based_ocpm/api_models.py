"""Response models of the configuration API (what the frontend receives)."""

from pydantic import BaseModel

from ocelescope_module_location_based_ocpm.derivation.config import DerivationConfig, LocationsInput
from ocelescope_module_location_based_ocpm.derivation.messages import BlockingError, Notice

#: At most this many ids are sent per message; `count` still gives the total.
MAX_IDS = 500


class TableInfo(BaseModel):
    """An uploaded table as the form shows it.

    Attributes:
        name: File name, by which the configuration refers to the table.
        columns: Column names.
        row_count: Number of rows.
        preview: The first rows.
    """

    name: str
    columns: list[str]
    row_count: int
    preview: list[dict[str, str | None]]


class ValueCount(BaseModel):
    """A value of the log (activity, object type, qualifier, attribute value) and how often it occurs."""

    value: str
    count: int


class LogOptions(BaseModel):
    """What the pickers of the configuration form offer, with counts.

    Attributes:
        object_types: Object types with their number of objects.
        activities: Activities with their number of events.
        qualifiers: E2o qualifiers with their number of relations.
        event_attributes: Names of the event attributes.
        object_attributes: Names of the static object attributes (for location names).
        o2o_qualifiers: O2o qualifiers with their number of relations (for high-level locations).
    """

    object_types: list[ValueCount]
    activities: list[ValueCount]
    qualifiers: list[ValueCount]
    event_attributes: list[str]
    object_attributes: list[str]
    o2o_qualifiers: list[ValueCount] = []


class LocationRequest(BaseModel):
    """The location inputs of the form, to list the locations L before the configuration is applied.

    Attributes:
        target_locations: The target location input.
        pickup_locations: The pickup location input (optional).
    """

    target_locations: LocationsInput
    pickup_locations: LocationsInput | None = None


class LocationOptions(BaseModel):
    """The locations L of the current location inputs, for the location-context pickers and the template.

    Attributes:
        locations: Every location with its number of events (as target or pickup), most frequent first.
        location_object_types: Object types of the location objects (only with e2o-qualifier locations).
        problems: Why the locations could not be listed (e.g. a missing table); empty if they could.
    """

    locations: list[ValueCount] = []
    location_object_types: list[ValueCount] = []
    problems: list[str] = []


class Message(BaseModel):
    """A notice or a blocking error, with at most `MAX_IDS` ids.

    Attributes:
        code: Stable identifier, e.g. "RQ1".
        message: Text shown to the user.
        count: Total number of affected items.
        ids: Affected ids (the first `MAX_IDS`).
    """

    code: str
    message: str
    count: int
    ids: list[str]

    @classmethod
    def of(cls, item: Notice | BlockingError) -> "Message":
        """Convert a notice or blocking error, cutting its ids to `MAX_IDS`.

        Args:
            item: The notice or blocking error.

        Returns:
            Message: The message for the frontend.
        """
        count = item.count if isinstance(item, Notice) else len(item.ids)
        return cls(code=item.code, message=item.message, count=count, ids=item.ids[:MAX_IDS])


class ConfigState(BaseModel):
    """The applied configuration of a log.

    Attributes:
        config: The configuration; None if none is applied yet.
        notices: Notices of its last derivation.
    """

    config: DerivationConfig | None = None
    notices: list[Message] = []


class ApplyResult(BaseModel):
    """Outcome of applying a configuration.

    Attributes:
        applied: True if there was no blocking error and the configuration is now in use.
        errors: Blocking errors (input resolution, missing tables or attributes, RQ1-RQ3).
        notices: Non-blocking notices.
    """

    applied: bool
    errors: list[Message] = []
    notices: list[Message] = []
