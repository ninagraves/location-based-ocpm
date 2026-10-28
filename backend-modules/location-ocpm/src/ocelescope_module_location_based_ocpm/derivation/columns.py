"""Column names of the frames used throughout the derivation.

One place for the names, so a rename is a single edit.
"""

#: Event id.
EVENT = "event"
#: Handling unit (object id).
HU = "hu"
#: Event timestamp.
TIME = "time"
#: Activity of the event.
ACTIVITY = "activity"
#: Object type of the handling unit.
OBJECT_TYPE = "object_type"
#: True if the event is a movement event (e ∈ M).
IS_MOVEMENT = "is_movement"
#: True if the event is a transformation event (e ∈ T).
IS_TRANSFORMATION = "is_transformation"
#: Provided target location uloc(e); null = not provided (⊥).
ULOC = "uloc"
#: Provided pickup location puloc(e); null = not provided (⊥). Only set for movement events.
PULOC = "puloc"
#: Location column of input tables after resolution.
LOCATION = "location"


def loc(level: int) -> str:
    """Name of the column holding loc_k.

    Args:
        level: Level k (0 to 3).

    Returns:
        str: e.g. "loc_2".
    """
    return f"loc_{level}"


def before(level: int) -> str:
    """Name of the column holding before_{loc_k}.

    Args:
        level: Level k (0 to 3).

    Returns:
        str: e.g. "before_2".
    """
    return f"before_{level}"


def ploc(level: int) -> str:
    """Name of the column holding ploc_k.

    Args:
        level: Level k (0 to 3).

    Returns:
        str: e.g. "ploc_2".
    """
    return f"ploc_{level}"


#: All levels, lowest first.
LEVELS = (0, 1, 2, 3)
