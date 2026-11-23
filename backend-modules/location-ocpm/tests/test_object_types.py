"""Module-wide object type order that fixes the colours of object types (docs/resources/object-type-colours.md)."""

import polars as pl

from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.dfg.graph import log_frames
from ocelescope_module_location_based_ocpm.object_type_routes import object_type_order


def test_order_of_the_docstring_example():
    """Most objects first, handling units counted for handling-unit types."""
    objects = pl.DataFrame(
        {
            "object": ["p1", "p2", "p3", "b1", "b2", "o1", "o2", "o3", "o4"],
            "object_type": ["pallet"] * 3 + ["box"] * 2 + ["order"] * 4,
        }
    )
    order = object_type_order(objects, pl.Series(["p1", "p2", "p3", "b1"]))
    assert [(t.object_type, t.objects, t.handling_units) for t in order] == [
        ("order", 4, False),
        ("pallet", 3, True),
        ("box", 1, True),
    ]


def test_ties_by_name():
    """Types with as many objects are ordered by name."""
    objects = pl.DataFrame({"object": ["a", "b"], "object_type": ["zeta", "alpha"]})
    assert [t.object_type for t in object_type_order(objects, pl.Series([], dtype=pl.String))] == ["alpha", "zeta"]


def test_running_example_matches_the_dfg_order(ocel, derivation):
    """The order is the one the directly-follows graph used for its colours, with every object type of the log."""
    frames = log_frames(ocel, derivation)
    order = object_type_order(frames.objects, derivation.handling_units[c.HU])
    assert {t.object_type for t in order} == set(frames.objects["object_type"].unique())
    hu_types = [t.object_type for t in order if t.handling_units]
    assert hu_types, "the running example has handling-unit types"
    counts = [t.objects for t in order]
    assert counts == sorted(counts, reverse=True)
