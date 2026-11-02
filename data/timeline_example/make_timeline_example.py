"""Generate the small edge-case example of the object timeline.

The running example has no events with the same timestamp, no production or consumption at a movement and no
location known only from a pickup location; this example has all of them (see `README.md`). It is given directly
as a location mapping (the format of `data/running_example/derived/locations_level_{k}.csv`), not as a log.
Never edit the generated files by hand; change the data below and run the script again:

    uv run python data/timeline_example/make_timeline_example.py
"""

from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

HERE = Path(__file__).parent

#: Time 0 of the example; example time t is START + t hours.
START = datetime(2026, 1, 1, 0, 0)

#: One row per hu-event relation: event, hu, time t, activity, e ∈ M, e ∈ T, loc, ploc (None = ⊥).
RELATIONS = [
    ("x1", "h1", 1, "unload truck", True, False, "Y1", "X1"),
    ("x2", "h1", 2, "quality check", False, False, "Y1", "Y1"),
    ("x3", "h1", 3, "charge furnace", True, True, "F", "Y1"),
    ("x4", "h2", 4, "discharge furnace", True, True, "Y2", None),
    ("x5", "h2", 5, "rework", False, True, "Y2", "Y2"),
    ("x6", "h2", 5, "label", False, False, "Y2", "Y2"),
    ("x7", "h2", 6, "scan", False, False, "Y1", "Y2"),
    ("x8", "h2", 6, "crane move", True, False, "Y1", "Y3"),
    ("x9", "h3", 2, "inspect", False, False, None, None),
    ("x10", "h3", 3, "crane pick", True, False, "C", "Y1"),
    ("x11", "h3", 4, "crane drop", True, False, "Y2", "C"),
]

#: Location context: location -> (agg(l) or None = unmapped, l ∈ V).
LOCATIONS = {
    "X1": ("X", False),
    "Y1": ("Y", False),
    "Y2": ("Y", False),
    "Y3": ("Y", False),
    "C": ("Y", True),
    "F": (None, False),
}

#: Processing operations P.
PROCESSING = ["x5", "x6"]

#: Consumed/produced handling units at the transformation events.
ROLES = [
    ("x3", "h1", "consumed"),
    ("x4", "h2", "produced"),
    ("x5", "h2", "consumed"),
    ("x5", "h2", "produced"),
]


def build_tables() -> dict[str, pl.DataFrame]:
    """Build the tables of the example.

    Returns:
        dict[str, pl.DataFrame]: File name (without `.csv`) -> table: relations (location mapping), locations,
        processing_events, transformation_roles.
    """
    relations = pl.DataFrame(
        [
            (e, hu, "coil", START + timedelta(hours=t), a, m, tr, loc, ploc)
            for e, hu, t, a, m, tr, loc, ploc in RELATIONS
        ],
        schema={
            "event": pl.String,
            "hu": pl.String,
            "object_type": pl.String,
            "time": pl.Datetime("us"),
            "activity": pl.String,
            "is_movement": pl.Boolean,
            "is_transformation": pl.Boolean,
            "loc": pl.String,
            "ploc": pl.String,
        },
        orient="row",
    ).sort("hu", "time", "event")
    locations = pl.DataFrame(
        [(loc, high, vehicle) for loc, (high, vehicle) in LOCATIONS.items()],
        schema={
            "location": pl.String,
            "high_level": pl.String,
            "is_vehicle": pl.Boolean,
        },
        orient="row",
    )
    return {
        "relations": relations,
        "locations": locations,
        "processing_events": pl.DataFrame({"event": PROCESSING}),
        "transformation_roles": pl.DataFrame(
            ROLES, schema=["event", "hu", "role"], orient="row"
        ),
    }


def main() -> None:
    """Write the tables next to this script."""
    for name, table in build_tables().items():
        table.write_csv(HERE / f"{name}.csv")


if __name__ == "__main__":
    main()
