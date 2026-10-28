"""The e2o-qualifier option for target and pickup locations.

The running example has its locations in the event attributes to_loc and from_loc. Here the same
information is turned into location objects (type "location") related to the events via the
qualifiers "to" and "from", so the derivation must give the same result as with the attributes.
"""

import polars as pl
import pytest
from ocelescope import OCEL

from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.derivation.config import LocationQualifiers, ObjectTypes
from ocelescope_module_location_based_ocpm.derivation.pipeline import derive

from conftest import example_config


def _with_location_objects(ocel: OCEL, extra_relations: list[tuple[str, str, str]] = ()) -> OCEL:
    """Copy of the log with one location object per location, related via "to" and "from".

    Args:
        ocel: The running example.
        extra_relations: Additional (event, object, qualifier) relations.

    Returns:
        OCEL: The new log; location objects have the static attribute "name" ("bay A1", ...),
        except T, which has none.
    """
    events = ocel.events.pl.collect()
    objects = ocel.objects.pl.collect()
    e2o = ocel.e2o.pl.collect()
    locations = sorted(set(events["to_loc"].drop_nulls()) | set(events["from_loc"].drop_nulls()))
    location_objects = pl.DataFrame(
        {
            "ocel:oid": locations,
            "ocel:type": ["location"] * len(locations),
            "name": [None if loc == "T" else f"bay {loc}" for loc in locations],
        }
    )
    objects = pl.concat([objects.with_columns(pl.lit(None, pl.String).alias("name")), location_objects])
    rows = [
        (event, location, qualifier)
        for attribute, qualifier in (("to_loc", "to"), ("from_loc", "from"))
        for event, location in events.select("ocel:eid", attribute).drop_nulls().rows()
    ] + list(extra_relations)
    lookup = events.select("ocel:eid", "ocel:activity", "ocel:timestamp")
    added = (
        pl.DataFrame(rows, schema=["ocel:eid", "ocel:oid", "ocel:qualifier"], orient="row")
        .join(lookup, on="ocel:eid")
        .with_columns(pl.lit("location").alias("ocel:type"))
        .select(e2o.columns)
    )
    return OCEL.from_frames(events, objects, pl.concat([e2o, added]))


QUALIFIER_CONFIG = dict(
    target_locations=LocationQualifiers(qualifiers=["to"]),
    pickup_locations=LocationQualifiers(qualifiers=["from"]),
)


def test_qualifiers_reproduce_the_attribute_option(ocel, derivation):
    """Locations from qualifiers give the same levels as locations from the attributes."""
    result = derive(_with_location_objects(ocel), example_config(**QUALIFIER_CONFIG))
    assert result.errors == []
    columns = [c.EVENT, c.HU, *(c.loc(k) for k in c.LEVELS), *(c.ploc(k) for k in c.LEVELS)]
    assert result.relations.select(columns).sort(c.HU, c.EVENT).equals(
        derivation.relations.select(columns).sort(c.HU, c.EVENT)
    )


def test_name_attribute_with_fallback_to_id(ocel):
    """With a name attribute, locations are named by it; objects without a value keep their id."""
    config = example_config(
        target_locations=LocationQualifiers(qualifiers=["to"], name_attribute="name"),
        pickup_locations=LocationQualifiers(qualifiers=["from"], name_attribute="name"),
    )
    result = derive(_with_location_objects(ocel), config)
    targets = set(result.events[c.ULOC].drop_nulls())
    assert targets == {"bay A1", "bay A2", "bay B1", "T"}


def test_several_location_objects_block(ocel):
    """An event related to two location objects via the selected qualifiers is a blocking error."""
    log = _with_location_objects(ocel, extra_relations=[("e5", "B1", "to")])
    result = derive(log, example_config(**QUALIFIER_CONFIG))
    codes = {error.code: error for error in result.errors}
    assert codes["several_location_objects"].ids == ["e5"]
    assert "e5: more than one location (A2, B1)" in codes["several_location_objects"].message


def test_location_object_that_is_a_handling_unit_blocks(ocel):
    """A location object whose type is selected as handling unit type is a blocking error."""
    config = example_config(
        handling_units=ObjectTypes(object_types=["slab", "coil", "location"]), **QUALIFIER_CONFIG
    )
    result = derive(_with_location_objects(ocel), config)
    errors = [error for error in result.errors if error.code == "location_object_is_handling_unit"]
    assert len(errors) == 2  # once for target, once for pickup locations
    assert errors[0].ids == ["A1", "A2", "B1", "T"]


def test_unknown_name_attribute(ocel):
    """An unknown name attribute is reported as a KeyError (shown to the user as an error)."""
    config = example_config(target_locations=LocationQualifiers(qualifiers=["to"], name_attribute="no_such_attribute"))
    with pytest.raises(KeyError):
        derive(_with_location_objects(ocel), config)
