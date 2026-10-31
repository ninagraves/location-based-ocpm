"""Generate the small visits example: five handling units whose traces cover the edge cases of
maximal visits, shifts and waiting times (`overview/Single Level Visit Mappings.md`).

The single source of the files in this folder; never edit the outputs by hand. Run from the repository
root with `uv run python data/visits_example/make_visits_example.py`.

Outputs:
- `relations.csv`: one row per hu-event relation in the format of a saved level mapping
  (`derivation/level_files.py`, `MAPPING_COLUMNS`); loc is given directly (as if derived), ploc is the
  location of the previous relation of the handling unit.
- `locations.csv`: the location context (agg, vehicles), same format as `running_example/inputs/locations.csv`.
- `processing_events.csv`: the processing operations P (column event).

Time t is 2026-01-01 00:00 plus t hours. The example is meant for κ_max = 1.
"""

from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

HERE = Path(__file__).parent
START = datetime(2026, 1, 1)

#: Location context: A1, A2 and the crane C1 lie in hall A, B1 in hall B; the truck T is not mapped
#: (its own high-level location). Vehicles: C1 and T.
LOCATIONS = [
    ("A1", "A", False),
    ("A2", "A", False),
    ("C1", "A", True),
    ("B1", "B", False),
    ("T", None, True),
]

#: Traces: hu -> list of (event, hour, activity, is_movement, is_transformation, is_processing, loc).
#: None as loc is ⊥.
TRACES = {
    # h1: all four transfer categories in one visit to A; T is visited twice (cut, gap 4 > κ).
    "h1": [
        ("e1", 0, "produce", False, True, True, "A1"),
        ("e2", 1, "label", False, False, False, "A1"),
        ("e3", 2, "crane move", True, False, False, "A2"),
        ("e4", 3, "crane pick", True, False, False, "C1"),
        ("e5", 4, "crane drop", True, False, False, "A2"),
        ("e6", 6, "load truck", True, False, False, "T"),
        ("e7", 7, "unload truck", True, False, False, "A1"),
        ("e8", 9, "crane move", True, False, False, "B1"),
        ("e9", 10, "crane move", True, False, False, "A2"),
        ("e10", 12, "grind", False, False, True, "A2"),
        ("e11", 13, "load truck", True, False, False, "T"),
    ],
    # h2: vehicle relations at the start and end of a visit (not counted), vehicle visits.
    "h2": [
        ("e12", 0, "load truck", True, False, False, "T"),
        ("e13", 1, "crane pick", True, False, False, "C1"),
        ("e14", 2, "crane drop", True, False, False, "A1"),
        ("e15", 5, "inspect", False, False, False, "A1"),
        ("e16", 6, "crane pick", True, False, False, "C1"),
        ("e17", 7, "load truck", True, False, False, "T"),
        ("e18", 9, "inspect", False, False, False, "T"),
    ],
    # h3: ⊥ (as at Level 0): ⊥ visits with κ(⊥) = 0, ⊥ inside a transfer.
    "h3": [
        ("e19", 0, "inspect", False, False, False, None),
        ("e20", 1, "inspect", False, False, False, None),
        ("e21", 2, "crane move", True, False, False, "A1"),
        ("e22", 3, "inspect", False, False, False, None),
        ("e23", 4, "inspect", False, False, False, "A1"),
        ("e24", 5, "load truck", True, False, False, "T"),
        ("e25", 6, "unload truck", True, False, False, "A2"),
    ],
    # h4: a transferring visit (T with an excursion to A1, no stops); A cut into two visits.
    "h4": [
        ("e26", 0, "load truck", True, False, False, "T"),
        ("e27", 1, "unload truck", True, False, False, "A1"),
        ("e28", 2, "load truck", True, False, False, "T"),
        ("e29", 4, "inspect", False, False, False, "T"),
        ("e30", 5, "unload truck", True, False, False, "B1"),
        ("e31", 6, "store", False, False, False, "B1"),
        ("e32", 8, "crane move", True, False, False, "A2"),
    ],
    # h5: waiting times: entry without processing, processing on a vehicle in A, processing during an
    # excursion, processing movements (P ∩ M) as exit of one visit and entry of the next.
    "h5": [
        ("e33", 0, "crane move", True, False, False, "A1"),
        ("e34", 1, "inspect", False, False, False, "A1"),
        ("e35", 3, "roll", False, True, True, "A1"),
        ("e36", 4, "weigh on crane", True, False, True, "C1"),
        ("e37", 5, "paint and drop", True, False, True, "B1"),
        ("e38", 7, "crane move", True, False, False, "A2"),
        ("e39", 8, "label", False, False, False, "A2"),
        ("e40", 10, "pack and move", True, False, True, "B1"),
        ("e41", 12, "store", False, False, False, "B1"),
    ],
}


def relations() -> pl.DataFrame:
    """The relations frame of the example, sorted by hu, time, event.

    Returns:
        pl.DataFrame: Columns event, hu, object_type, time, activity, is_movement, is_transformation, loc, ploc.
    """
    rows = []
    for hu, trace in TRACES.items():
        previous = None
        for event, hour, activity, movement, transformation, _, loc in trace:
            rows.append(
                (event, hu, "coil", START + timedelta(hours=hour), activity, movement, transformation, loc, previous)
            )
            previous = loc
    schema = {
        "event": pl.String,
        "hu": pl.String,
        "object_type": pl.String,
        "time": pl.Datetime("us"),
        "activity": pl.String,
        "is_movement": pl.Boolean,
        "is_transformation": pl.Boolean,
        "loc": pl.String,
        "ploc": pl.String,
    }
    return pl.DataFrame(rows, schema=schema, orient="row").sort("hu", "time", "event")


def main() -> None:
    """Write the three files of the example next to this script."""
    relations().write_csv(HERE / "relations.csv")
    pl.DataFrame(LOCATIONS, schema=["location", "high_level", "is_vehicle"], orient="row").write_csv(
        HERE / "locations.csv"
    )
    processing = [e for trace in TRACES.values() for e, *_, p, _ in trace if p]
    pl.DataFrame({"event": processing}).write_csv(HERE / "processing_events.csv")


if __name__ == "__main__":
    main()
