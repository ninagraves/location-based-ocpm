"""Generate the running example log and its input tables.

The running example is the example of `overview/Deriving Locations.md` (section "Setting"):
bays A1, A2, storage B1, truck T; handling units slab s1 and coils c1 to c5; events e1 to e17.
This script is its single source in the repo. Never edit the generated files by hand;
change the data below and run the script again:

    uv run python data/running_example/make_running_example.py

Outputs (next to this script):
- `running_example.sqlite`: OCEL 2.0 log, uploadable in Ocelescope.
- `inputs/*.csv`: the same configuration inputs as tables, to test the table options.
"""

from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
from ocelescope import OCEL

HERE = Path(__file__).parent

#: Time 0 of the example; example time t is START + t hours.
START = datetime(2026, 1, 1, 0, 0)

#: Object id -> object type.
OBJECTS = {
    "s1": "slab",
    "c1": "coil",
    "c2": "coil",
    "c3": "coil",
    "c4": "coil",
    "c5": "coil",
}

#: Event id -> (time, activity, target location (uloc), pickup location (puloc)); None = not provided.
EVENTS = {
    "e1": (1, "cast slab", None, None),
    "e2": (2, "inspect slab", "A1", None),
    "e3": (3, "roll", None, None),
    "e4": (4, "label", None, None),
    "e5": (5, "crane move", "A2", None),
    "e6": (6, "crane move", "A2", "A1"),
    "e7": (7, "quality check", "B1", None),
    "e8": (8, "load truck", "T", None),
    "e9": (9, "unload truck", "A2", "T"),
    "e10": (10, "unload truck", "B1", "T"),
    "e11": (11, "crane move", "A2", None),
    "e12": (12, "crane move", "B1", None),
    "e13": (13, "load truck", "T", "A1"),
    "e14": (14, "quality check", None, None),
    "e15": (15, "cut", None, None),
    "e16": (16, "quality check", None, None),
    "e17": (17, "quality check", None, None),
}

#: Event id -> handling units involved (the e2o relations of the example).
RELATIONS = {
    "e1": ["s1"],
    "e2": ["s1"],
    "e3": ["s1", "c1", "c2"],
    "e4": ["c1", "c2"],
    "e5": ["c1"],
    "e6": ["c2"],
    "e7": ["c1"],
    "e8": ["c1", "c2", "c3"],
    "e9": ["c1", "c2"],
    "e10": ["c3"],
    "e11": ["c1", "c2"],
    "e12": ["c2", "c3"],
    "e13": ["c1"],
    "e14": ["c1", "c3"],
    "e15": ["c2", "c4"],
    "e16": ["c4", "c5"],
    "e17": ["c5"],
}

#: E2O qualifiers at transformation events (all other relations get "handled").
#: Data only: the concept does not use consumed/produced yet.
QUALIFIERS = {
    ("e1", "s1"): "produced",
    ("e3", "s1"): "consumed",
    ("e3", "c1"): "produced",
    ("e3", "c2"): "produced",
    ("e15", "c2"): "consumed",
    ("e15", "c4"): "produced",
}

#: Location context (draft for the visit concept; input format not decided yet):
#: location -> (high-level location agg(l) or None = not mapped (identity), vehicle (l ∈ V), storage unit (l ∈ W)).
LOCATIONS = {
    "A1": ("A", False, False),
    "A2": ("A", False, False),
    "B1": ("B", False, True),
    "T": (None, True, False),
}

#: Movement events M and transformation events T, by activity.
MOVEMENT_ACTIVITIES = ["crane move", "load truck", "unload truck"]
TRANSFORMATION_ACTIVITIES = ["cast slab", "roll", "cut"]


def event_group(activity: str) -> str:
    """Value of the event attribute `event_group`, to test the attribute-value input options.

    Args:
        activity: Activity of the event.

    Returns:
        str: "transport" for movement activities, "transformation" for transformation
        activities, "other" otherwise.
    """
    if activity in MOVEMENT_ACTIVITIES:
        return "transport"
    if activity in TRANSFORMATION_ACTIVITIES:
        return "transformation"
    return "other"


def build_frames() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Build the OCEL tables of the running example.

    Returns:
        tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]: Events (with the attributes
        `to_loc`, `from_loc` and `event_group`), objects and e2o relations, in Ocelescope's
        column naming.
    """
    events = pl.DataFrame(
        [
            {
                "ocel:eid": eid,
                "ocel:timestamp": START + timedelta(hours=time),
                "ocel:activity": activity,
                "to_loc": uloc,
                "from_loc": puloc,
                "event_group": event_group(activity),
            }
            for eid, (time, activity, uloc, puloc) in EVENTS.items()
        ],
        schema_overrides={"to_loc": pl.String, "from_loc": pl.String},
    )
    objects = pl.DataFrame(
        {"ocel:oid": list(OBJECTS), "ocel:type": list(OBJECTS.values())}
    )
    relations = pl.DataFrame(
        [
            {
                "ocel:eid": eid,
                "ocel:oid": oid,
                "ocel:qualifier": QUALIFIERS.get((eid, oid), "handled"),
                "ocel:activity": EVENTS[eid][1],
                "ocel:type": OBJECTS[oid],
            }
            for eid, oids in RELATIONS.items()
            for oid in oids
        ]
    )
    return events, objects, relations


def build_input_tables() -> dict[str, pl.DataFrame]:
    """Build the configuration inputs of the running example as tables.

    Returns:
        dict[str, pl.DataFrame]: File name (without `.csv`) -> table: handling units,
        movement events, transformation events, target locations, pickup locations, and the
        location context (columns location, high_level, is_vehicle, is_storage; draft).
    """
    rows = [
        (eid, activity, uloc, puloc)
        for eid, (_, activity, uloc, puloc) in EVENTS.items()
    ]
    return {
        "handling_units": pl.DataFrame({"object": list(OBJECTS)}),
        "movement_events": pl.DataFrame(
            {"event": [e for e, a, _, _ in rows if a in MOVEMENT_ACTIVITIES]}
        ),
        "transformation_events": pl.DataFrame(
            {"event": [e for e, a, _, _ in rows if a in TRANSFORMATION_ACTIVITIES]}
        ),
        "target_locations": pl.DataFrame(
            {
                "event": [e for e, _, u, _ in rows if u],
                "location": [u for _, _, u, _ in rows if u],
            }
        ),
        "pickup_locations": pl.DataFrame(
            {
                "event": [e for e, _, _, p in rows if p],
                "location": [p for _, _, _, p in rows if p],
            }
        ),
        "locations": pl.DataFrame(
            [
                (loc, high, vehicle, storage)
                for loc, (high, vehicle, storage) in LOCATIONS.items()
            ],
            schema={
                "location": pl.String,
                "high_level": pl.String,
                "is_vehicle": pl.Boolean,
                "is_storage": pl.Boolean,
            },
            orient="row",
        ),
    }


def main() -> None:
    """Write the log and the input tables next to this script."""
    events, objects, relations = build_frames()
    log_path = HERE / "running_example.sqlite"
    log_path.unlink(missing_ok=True)
    OCEL.from_frames(events=events, objects=objects, relations=relations).write(
        log_path
    )
    (HERE / "inputs").mkdir(exist_ok=True)
    for name, table in build_input_tables().items():
        table.write_csv(HERE / "inputs" / f"{name}.csv")


if __name__ == "__main__":
    main()
