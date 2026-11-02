"""Generate the visit-mapping example: the running example extended by sheets (Level 3, b1 to b8 and the
slabs s1, s2) and the extra traces x1 to x5 and y1 to y5 of the working note `claude_notes/visit-mapping-sets.md`
(sections 3 to 7), used to derive mapping sets from maximal visits (`docs/resources/visit-mapping.md`).

The single source of the files in this folder; never edit the outputs by hand. Run from the repository
root with `uv run python data/mapping_example/make_mapping_example.py`.

Outputs:
- `relations.csv`: the extended running example (10 handling units, 41 events, 54 relations) in the format of
  a saved level mapping (`derivation/level_files.py`, `MAPPING_COLUMNS`); loc is given directly.
- `extra_relations.csv`: the extra traces x1 to x5 (events f1 to f28) and y1 to y5 (events g1 to g28),
  same format.
- `locations.csv`: the location context: A1, A2 -> A, B1 -> B, the truck T unmapped; V = {T}, W = {B1}.
- `processing_events.csv`: the processing operations P of both files (column event).

Event eK, fK, gK happens at 2026-01-01 00:00 plus K hours. The example is meant for κ_max = 3.
"""

from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

HERE = Path(__file__).parent
START = datetime(2026, 1, 1)

#: Location context. Columns: location, high-level location, vehicle, storage unit.
LOCATIONS = [
    ("A1", "A", False, False),
    ("A2", "A", False, False),
    ("B1", "B", False, True),
    ("T", None, True, False),
]

#: Object type per handling unit (default "sheet").
OBJECT_TYPES = {"s1": "slab", "s2": "slab"}

#: Traces: hu -> list of (event, hour, activity, is_movement, is_transformation, is_processing, loc, ploc).
#: None as loc or ploc is ⊥.
RUNNING = {
    'b1': [
        ('e3', 3, 'roll', False, True, True, 'A1', None),
        ('e4', 4, 'label', False, False, True, 'A1', 'A1'),
        ('e5', 5, 'crane move', True, False, False, 'A2', 'A1'),
        ('e7', 7, 'quality check', False, False, False, 'B1', 'A2'),
        ('e8', 8, 'load truck', True, False, False, 'T', 'B1'),
        ('e9', 9, 'unload truck', True, False, False, 'A2', 'T'),
        ('e11', 11, 'crane move', True, False, False, 'A2', 'A2'),
        ('e13', 13, 'load truck', True, False, False, 'T', 'A1'),
        ('e14', 14, 'quality check', False, False, False, 'T', 'T'),
    ],
    'b2': [
        ('e3', 3, 'roll', False, True, True, 'A1', None),
        ('e4', 4, 'label', False, False, True, 'A1', 'A1'),
        ('e6', 6, 'crane move', True, False, False, 'A2', 'A1'),
        ('e8', 8, 'load truck', True, False, False, 'T', 'A2'),
        ('e9', 9, 'unload truck', True, False, False, 'A2', 'T'),
        ('e11', 11, 'crane move', True, False, False, 'A2', 'A2'),
        ('e12', 12, 'crane move', True, False, False, 'B1', 'A2'),
        ('e15', 15, 'cut', False, True, True, 'B1', 'B1'),
    ],
    'b3': [
        ('e8', 8, 'load truck', True, False, False, 'T', None),
        ('e10', 10, 'unload truck', True, False, False, 'B1', 'T'),
        ('e12', 12, 'crane move', True, False, False, 'B1', 'B1'),
        ('e14', 14, 'quality check', False, False, False, 'B1', 'B1'),
    ],
    'b4': [
        ('e15', 15, 'cut', False, True, True, 'B1', None),
        ('e16', 16, 'quality check', False, False, False, 'B1', 'B1'),
        ('e18', 18, 'crane move', True, False, False, 'A2', None),
        ('e19', 19, 'crane move', True, False, False, 'B1', None),
        ('e20', 20, 'crane move', True, False, False, 'A2', None),
        ('e21', 21, 'crane move', True, False, False, 'B1', None),
    ],
    'b5': [
        ('e16', 16, 'quality check', False, False, False, None, None),
        ('e17', 17, 'quality check', False, False, False, None, None),
    ],
    's1': [
        ('e1', 1, 'cast slab', False, True, True, 'A1', None),
        ('e2', 2, 'inspect slab', False, False, False, 'A1', 'A1'),
        ('e3', 3, 'roll', False, True, True, 'A1', 'A1'),
    ],
    's2': [
        ('e22', 22, 'cast slab', False, True, True, 'A1', None),
        ('e23', 23, 'crane move', True, False, False, 'B1', None),
        ('e24', 24, 'load truck', True, False, False, 'T', None),
        ('e25', 25, 'unload truck', True, False, False, 'A2', None),
        ('e26', 26, 'roll', False, True, True, 'A2', None),
    ],
    'b6': [
        ('e26', 26, 'roll', False, True, True, 'A2', None),
        ('e27', 27, 'load truck', True, False, False, 'T', None),
        ('e28', 28, 'unload truck', True, False, False, 'B1', None),
        ('e29', 29, 'load truck', True, False, False, 'T', None),
        ('e30', 30, 'unload truck', True, False, False, 'A2', None),
    ],
    'b7': [
        ('e26', 26, 'roll', False, True, True, 'A2', None),
        ('e31', 31, 'crane move', True, False, False, 'B1', None),
        ('e32', 32, 'load truck', True, False, False, 'T', None),
        ('e33', 33, 'unload truck', True, False, False, 'A2', None),
        ('e34', 34, 'crane move', True, False, False, 'B1', None),
    ],
    'b8': [
        ('e35', 35, 'cut sheet', False, True, True, 'A1', None),
        ('e36', 36, 'crane move', True, False, False, 'B1', None),
        ('e37', 37, 'crane move', True, False, False, 'A2', None),
        ('e38', 38, 'load truck', True, False, False, 'T', None),
        ('e39', 39, 'unload truck', True, False, False, 'B1', None),
        ('e40', 40, 'crane move', True, False, False, 'A1', None),
        ('e41', 41, 'crane move', True, False, False, 'B1', None),
    ],
}

EXTRA = {
    'x1': [
        ('f1', 1, 'process', False, True, True, 'A1', None),
        ('f2', 2, 'load truck', True, False, False, 'T', None),
        ('f3', 3, 'process', False, True, True, 'B1', None),
        ('f4', 4, 'load truck', True, False, False, 'T', None),
        ('f5', 5, 'process', False, True, True, 'A2', None),
    ],
    'x2': [
        ('f6', 6, 'process', False, True, True, 'A1', None),
        ('f7', 7, 'crane move', True, False, False, 'B1', None),
        ('f8', 8, 'crane move', True, False, False, 'A2', None),
        ('f9', 9, 'crane move', True, False, False, 'B1', None),
        ('f10', 10, 'crane move', True, False, False, 'A2', None),
        ('f11', 11, 'crane move', True, False, False, 'B1', None),
    ],
    'x3': [
        ('f12', 12, 'process', False, True, True, 'A1', None),
        ('f13', 13, 'load truck', True, False, False, 'T', None),
        ('f14', 14, 'crane move', True, False, False, 'A2', None),
        ('f15', 15, 'load truck', True, False, False, 'T', None),
        ('f16', 16, 'process', False, True, True, 'B1', None),
        ('f17', 17, 'crane move', True, False, False, 'B1', None),
    ],
    'x4': [
        ('f18', 18, 'process', False, True, True, 'A1', None),
        ('f19', 19, 'crane move', True, False, False, 'B1', None),
        ('f20', 20, 'process', False, True, True, 'A2', None),
        ('f21', 21, 'crane move', True, False, False, 'B1', None),
        ('f22', 22, 'crane move', True, False, False, 'B1', None),
    ],
    'x5': [
        ('f23', 23, 'process', False, True, True, 'A1', None),
        ('f24', 24, 'crane move', True, False, False, 'B1', None),
        ('f25', 25, 'load truck', True, False, False, 'T', None),
        ('f26', 26, 'crane move', True, False, False, 'A2', None),
        ('f27', 27, 'load truck', True, False, False, 'T', None),
        ('f28', 28, 'process', False, True, True, 'B1', None),
    ],
    'y1': [
        ('g1', 1, 'process', False, True, True, 'A1', None),
        ('g2', 2, 'crane move', True, False, False, None, None),
        ('g3', 3, 'crane move', True, False, False, 'A2', None),
        ('g4', 4, 'crane move', True, False, False, 'B1', None),
        ('g5', 5, 'crane move', True, False, False, 'B1', None),
    ],
    'y2': [
        ('g6', 6, 'process', False, True, True, 'A1', None),
        ('g7', 7, 'process', False, True, True, 'B1', None),
        ('g8', 8, 'crane move', True, False, False, 'A2', None),
        ('g9', 9, 'crane move', True, False, False, 'B1', None),
    ],
    'y3': [
        ('g10', 10, 'process', False, True, True, 'A1', None),
        ('g11', 11, 'load truck', True, False, False, 'T', None),
        ('g12', 12, 'load truck', True, False, False, 'T', None),
        ('g13', 13, 'load truck', True, False, False, 'T', None),
        ('g14', 14, 'process', False, True, True, 'A2', None),
        ('g15', 15, 'crane move', True, False, False, 'B1', None),
    ],
    'y4': [
        ('g16', 16, 'process', False, True, True, 'A1', None),
        ('g17', 17, 'process', False, True, True, 'B1', None),
        ('g18', 18, 'crane move', True, False, False, 'A2', None),
        ('g19', 19, 'crane move', True, False, False, 'A2', None),
        ('g20', 20, 'crane move', True, False, False, 'B1', None),
        ('g21', 21, 'crane move', True, False, False, 'B1', None),
    ],
    'y5': [
        ('g22', 22, 'process', False, True, True, 'A1', None),
        ('g23', 23, 'load truck', True, False, False, 'T', None),
        ('g24', 24, 'crane move', True, False, False, 'A2', None),
        ('g25', 25, 'load truck', True, False, False, 'T', None),
        ('g26', 26, 'crane move', True, False, False, 'A1', None),
        ('g27', 27, 'load truck', True, False, False, 'T', None),
        ('g28', 28, 'process', False, True, True, 'B1', None),
    ],
}


def relations(traces: dict[str, list[tuple]]) -> pl.DataFrame:
    """Relations frame of some traces in the format of a saved level mapping.

    Args:
        traces: hu -> list of (event, hour, activity, is_movement, is_transformation, is_processing, loc, ploc).

    Returns:
        pl.DataFrame: Columns event, hu, object_type, time, activity, is_movement, is_transformation, loc, ploc;
        sorted by hu, time, event.
    """
    rows = [
        {
            "event": event,
            "hu": hu,
            "object_type": OBJECT_TYPES.get(hu, "sheet"),
            "time": START + timedelta(hours=hour),
            "activity": activity,
            "is_movement": movement,
            "is_transformation": transformation,
            "loc": loc,
            "ploc": ploc,
        }
        for hu, trace in traces.items()
        for event, hour, activity, movement, transformation, _, loc, ploc in trace
    ]
    return pl.DataFrame(rows).sort("hu", "time", "event")


def processing_events() -> list[str]:
    """The processing operations P of all traces, sorted by event id."""
    return sorted(
        {row[0] for traces in (RUNNING, EXTRA) for trace in traces.values() for row in trace if row[5]},
        key=lambda e: (e[0], int(e[1:])),
    )


def main() -> None:
    """Write all files of the example."""
    relations(RUNNING).write_csv(HERE / "relations.csv")
    relations(EXTRA).write_csv(HERE / "extra_relations.csv")
    pl.DataFrame(
        LOCATIONS, schema=["location", "high_level", "is_vehicle", "is_storage"], orient="row"
    ).write_csv(HERE / "locations.csv")
    pl.DataFrame({"event": processing_events()}).write_csv(HERE / "processing_events.csv")


if __name__ == "__main__":
    main()
