"""Reports and blocking errors produced while resolving inputs and checking requirements."""

from pydantic import BaseModel


class Notice(BaseModel):
    """Something the user should know, which does not block the configuration.

    Attributes:
        code: Stable identifier, e.g. "unknown_events_dropped".
        message: Text shown to the user.
        count: Number of affected rows or items.
        ids: Affected ids (events or objects), possibly truncated by the caller.
    """

    code: str
    message: str
    count: int
    ids: list[str] = []


class BlockingError(BaseModel):
    """A problem that prevents applying the configuration until the data is fixed.

    Attributes:
        code: Stable identifier, e.g. "RQ1".
        message: Text shown to the user.
        ids: Conflicting or affected ids (events or objects).
    """

    code: str
    message: str
    ids: list[str]
