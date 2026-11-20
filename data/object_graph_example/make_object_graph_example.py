"""Generate the object graph example: the running example plus objects that are not handling units and o2o relations.

The running example (`data/running_example`) has handling units only and no o2o relations, so it cannot show the
object graph of the instance page (`docs/pages/instances.md`, section "Object graph"). This example adds a crane,
the truck as an object, two operators, two customer orders and a customer, their e2o relations and o2o relations
(see `README.md`). Events, locations and handling units are those of the running example, so its
`configuration.json` and `inputs/*.csv` apply unchanged. Never edit the generated files by hand; change the data
below and run the script again:

    uv run python data/object_graph_example/make_object_graph_example.py

Output (next to this script): `object_graph_example.sqlite`, an OCEL 2.0 log uploadable in Ocelescope.
"""

import sys
from pathlib import Path

import polars as pl
from ocelescope import OCEL

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "running_example"))

import make_running_example as running

#: Object id -> object type of the objects that are not handling units.
EXTRA_OBJECTS = {
    "crane1": "crane",
    "truck1": "truck",
    "op1": "operator",
    "op2": "operator",
    "o1": "customer order",
    "o2": "customer order",
    "k1": "customer",
}

#: (event, object, qualifier) of the added e2o relations.
EXTRA_RELATIONS = [
    ("e5", "crane1", "crane"),
    ("e6", "crane1", "crane"),
    ("e11", "crane1", "crane"),
    ("e12", "crane1", "crane"),
    ("e5", "op1", "operator"),
    ("e6", "op1", "operator"),
    ("e11", "op1", "operator"),
    ("e12", "op1", "operator"),
    ("e8", "truck1", "vehicle"),
    ("e9", "truck1", "vehicle"),
    ("e10", "truck1", "vehicle"),
    ("e13", "truck1", "vehicle"),
    ("e8", "op2", "driver"),
    ("e9", "op2", "driver"),
    ("e10", "op2", "driver"),
    ("e13", "op2", "driver"),
    ("e14", "op2", "inspector"),
    ("e16", "op1", "inspector"),
]

#: (source object, target object, qualifier) of the o2o relations.
O2O = [
    ("c1", "o1", "part of"),
    ("c2", "o1", "part of"),
    ("c4", "o2", "part of"),
    ("c5", "o2", "part of"),
    ("c4", "c2", "cut from"),
    ("o1", "k1", "ordered by"),
    ("o2", "k1", "ordered by"),
    ("op1", "crane1", "operates"),
    ("op2", "truck1", "drives"),
]


def build_frames() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Build the OCEL tables of the object graph example.

    Returns:
        tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]: Events, objects, e2o relations and o2o
        relations, in Ocelescope's column naming (events and handling units as in the running example).
    """
    events, objects, relations = running.build_frames()
    types = {**running.OBJECTS, **EXTRA_OBJECTS}
    objects = pl.concat([objects, pl.DataFrame({"ocel:oid": list(EXTRA_OBJECTS), "ocel:type": list(EXTRA_OBJECTS.values())})])
    extra = pl.DataFrame(
        [
            {
                "ocel:eid": eid,
                "ocel:oid": oid,
                "ocel:qualifier": qualifier,
                "ocel:activity": running.EVENTS[eid][1],
                "ocel:type": types[oid],
            }
            for eid, oid, qualifier in EXTRA_RELATIONS
        ]
    )
    o2o = pl.DataFrame(O2O, schema=["ocel:oid_1", "ocel:oid_2", "ocel:qualifier"], orient="row")
    return events, objects, pl.concat([relations, extra]), o2o


def build_ocel() -> OCEL:
    """The object graph example as an in-memory OCEL (used by the tests).

    Returns:
        OCEL: The log.
    """
    events, objects, relations, o2o = build_frames()
    return OCEL.from_frames(events=events, objects=objects, relations=relations, o2o=o2o)


def main() -> None:
    """Write the log next to this script."""
    path = HERE / "object_graph_example.sqlite"
    path.unlink(missing_ok=True)
    build_ocel().write(path)


if __name__ == "__main__":
    main()
