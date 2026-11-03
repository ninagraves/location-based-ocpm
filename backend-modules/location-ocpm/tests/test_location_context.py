"""Location context inputs (agg, V, W), processing operations P, high-level columns, flags F6-F10 and the AS4
order of Level 3 (`overview/module/Module Overview.md`, "Update Overview Page").

Running example additions: A1, A2 -> A; B1 -> B; T unmapped; V = {T}; W = {B1}; P = T plus label (e4).
"""

from datetime import datetime

import polars as pl
import pytest

from ocelescope_module_location_based_ocpm.derivation import columns as c
from ocelescope_module_location_based_ocpm.derivation.config import (
    Activities,
    EventTable,
    HighLevelEventAttributes,
    HighLevelPattern,
    HighLevelTable,
    LocationAttributeValues,
    LocationList,
    LocationSetTable,
    ProcessingOperations,
)
from ocelescope_module_location_based_ocpm.derivation.levels import add_loc_3
from ocelescope_module_location_based_ocpm.derivation.pipeline import derive

from conftest import example_config

CONTEXT = dict(
    high_level_locations=HighLevelTable(table="locations", location_column="location", high_level_column="high_level"),
    vehicles=LocationSetTable(table="locations", location_column="location", flag_column="is_vehicle"),
    storage_units=LocationSetTable(table="locations", location_column="location", flag_column="is_storage"),
    processing_operations=ProcessingOperations(selection=Activities(activities=["label"])),
)


@pytest.fixture(scope="module")
def tables(input_tables):
    """The input tables, every column as text (as uploaded in the form)."""
    return {name: frame.cast(pl.String) for name, frame in input_tables.items()}


@pytest.fixture(scope="module")
def with_context(ocel, tables):
    """The running example with the location context at Level 3."""
    return derive(ocel, example_config(**CONTEXT), tables)


def test_context_from_the_location_table(with_context):
    """agg, V and W as in the concept's running example; T is unmapped and reported."""
    assert with_context.errors == []
    assert with_context.context.agg == {"A1": "A", "A2": "A", "B1": "B"}
    assert with_context.context.vehicles == {"T"}
    assert with_context.context.storage_units == {"B1"}
    assert with_context.high_level_locations == ["A", "B", "T"]
    unmapped = [n for n in with_context.notices if n.code == "unmapped_locations"]
    assert unmapped and unmapped[0].ids == ["T"]


def test_processing_operations_are_t_plus_selection(with_context, ocel):
    """P = T ∪ {label}; without the input, P = T; without T and input, P = ∅."""
    processing = with_context.events.filter(c.IS_PROCESSING)[c.EVENT].sort().to_list()
    assert processing == ["e1", "e15", "e3", "e4"]
    default = derive(ocel, example_config())
    assert default.events.filter(c.IS_PROCESSING)[c.EVENT].sort().to_list() == ["e1", "e15", "e3"]
    none = derive(ocel, example_config(transformation_events=None))
    assert none.events.filter(c.IS_PROCESSING).height == 0


def test_processing_from_a_table_without_transformations(ocel, tables):
    """A table of processing operations with "and all transformation events" switched off."""
    option = ProcessingOperations(
        selection=EventTable(table="processing_events", event_column="event"), include_transformations=False
    )
    result = derive(ocel, example_config(processing_operations=option), tables)
    assert result.events.filter(c.IS_PROCESSING)[c.EVENT].sort().to_list() == ["e1", "e15", "e3", "e4"]


def test_high_level_columns(with_context):
    """hl^k = agg(loc^k), phl^k = agg(ploc^k); ⊥ stays ⊥."""
    rel = with_context.relations.select(c.EVENT, c.HU, c.loc(3), c.hl(3), c.ploc(3), c.phl(3))
    row = rel.filter((pl.col(c.EVENT) == "e13") & (pl.col(c.HU) == "c1")).row(0, named=True)
    assert (row[c.loc(3)], row[c.hl(3)], row[c.ploc(3)], row[c.phl(3)]) == ("T", "T", "A1", "A")
    unlocated = rel.filter(pl.col(c.loc(3)).is_null())
    assert unlocated[c.hl(3)].null_count() == unlocated.height == 2


def test_high_level_agreement(with_context):
    """Agreement under hat-hl: e14 (c1 at T, c3 at B1) still disagrees; eloc of e5 is A."""
    hl = with_context.hl_event_locations
    assert hl.filter(~pl.col("agreeing"))[c.EVENT].to_list() == ["e14"]
    assert hl.filter(pl.col(c.EVENT) == "e5")["eloc"].item() == "A"


def test_flags_of_the_context(with_context, ocel, tables):
    """F6-F10 are 0 on the running example; at Level 0 F9 flags the unlocated processing operations."""
    flags = with_context.flags
    assert flags.f6.height == flags.f7.height == flags.f8.height == 0
    assert flags.f9.len() == flags.f10.len() == 0
    level_0 = derive(ocel, example_config(level=0, **CONTEXT), tables)
    assert level_0.flags.f9.to_list() == ["e1", "e15", "e3", "e4"]


def test_naming_clash_and_vehicle_storage(ocel):
    """A naming pattern maps only matching locations; F10 flags a location in V and W."""
    config = example_config(
        high_level_locations=HighLevelPattern(pattern="^(B)1$"),
        vehicles=LocationList(locations=["T", "B1"]),
        storage_units=LocationList(locations=["B1", "unknown"]),
    )
    result = derive(ocel, config)
    assert result.context.agg == {"B1": "B"}
    assert result.flags.f6.height == 0
    assert result.flags.f10.to_list() == ["B1"]
    assert any(n.code == "unknown_locations_dropped" and n.ids == ["unknown"] for n in result.notices)


def test_naming_clash(ocel, tables):
    """A table row (B1, T): B1 and the unmapped truck T both become T."""
    tables = tables | {"clash": pl.DataFrame({"location": ["B1"], "high_level": ["T"]})}
    config = example_config(
        high_level_locations=HighLevelTable(table="clash", location_column="location", high_level_column="high_level")
    )
    result = derive(ocel, config, tables)
    assert result.flags.f6["location"].to_list() == ["T"]


def test_ambiguous_high_level_location_blocks(ocel, tables):
    """A location with two high-level locations is a blocking error."""
    tables = tables | {"ambiguous": pl.DataFrame({"location": ["B1", "B1"], "high_level": ["B", "C"]})}
    config = example_config(
        high_level_locations=HighLevelTable(table="ambiguous", location_column="location", high_level_column="high_level")
    )
    result = derive(ocel, config, tables)
    assert [e.code for e in result.errors] == ["ambiguous_high_level"]
    assert result.errors[0].ids == ["B1"]


def test_options_from_event_attributes(ocel):
    """High-level locations from two event attributes; vehicles from the targets of events with a value."""
    config = example_config(
        high_level_locations=HighLevelEventAttributes(low_attribute="to_loc", high_attribute="to_loc"),
        vehicles=LocationAttributeValues(attribute="event_group", values=["transport"]),
    )
    result = derive(ocel, config)
    assert result.errors == []
    assert result.context.agg == {loc: loc for loc in ["A1", "A2", "B1", "T"]}
    assert result.context.vehicles == {"A2", "B1", "T"}


def test_invalid_pattern_blocks(ocel):
    """A pattern without a group cannot map anything."""
    result = derive(ocel, example_config(high_level_locations=HighLevelPattern(pattern="^[A-Z]")))
    assert [e.code for e in result.errors] == ["invalid_pattern"]


def test_level_3_breaks_ties_by_as4():
    """Two transformation events of h at the same time before its first movement: the processing operation
    (larger id e9) comes first in seq, so its location wins over e1's."""
    t = datetime(2026, 1, 1)
    relations = pl.DataFrame(
        {
            c.HU: ["h", "h"],
            c.EVENT: ["e1", "e9"],
            c.TIME: [t, t],
            c.IS_TRANSFORMATION: [True, True],
            c.IS_PROCESSING: [False, True],
            c.IS_MOVEMENT: [False, False],
            c.ULOC: [None, None],
            c.PULOC: [None, None],
            c.loc(2): [None, None],
        },
        schema_overrides={c.ULOC: pl.String, c.PULOC: pl.String, c.loc(2): pl.String},
    )
    eloc_2 = pl.DataFrame({c.EVENT: ["e1", "e9"], "eloc": ["X", "Y"]})
    assert add_loc_3(relations, eloc_2)[c.loc(3)].to_list() == ["Y", "Y"]
    # Without P (P = T), both are processing operations and the event id decides.
    assert add_loc_3(relations.drop(c.IS_PROCESSING), eloc_2)[c.loc(3)].to_list() == ["X", "X"]


def test_options_with_location_objects(ocel):
    """With e2o-qualifier locations: high-level locations from an object attribute and from o2o relations,
    vehicles from the object types of the location objects."""
    from ocelescope import OCEL

    from ocelescope_module_location_based_ocpm.derivation.config import (
        HighLevelO2O,
        HighLevelObjectAttribute,
        LocationObjectTypes,
        LocationQualifiers,
    )

    from test_qualifier_locations import _with_location_objects

    base = _with_location_objects(ocel)
    objects = base.objects.pl.collect().with_columns(
        pl.when(pl.col("ocel:oid") == "T").then(pl.lit("truck")).otherwise(pl.col("ocel:type")).alias("ocel:type"),
        pl.when(pl.col("ocel:oid").is_in(["A1", "A2"])).then(pl.lit("A")).otherwise(None).alias("area"),
    )
    areas = pl.DataFrame({"ocel:oid": ["area A", "area B"], "ocel:type": ["area"] * 2, "name": ["A", "B"], "area": [None, None]})
    objects = pl.concat([objects, areas.cast(objects.schema)])
    e2o = base.e2o.pl.collect().with_columns(
        pl.when(pl.col("ocel:oid") == "T").then(pl.lit("truck")).otherwise(pl.col("ocel:type")).alias("ocel:type")
    )
    o2o = pl.DataFrame(
        {"ocel:oid_1": ["A1", "A2", "B1"], "ocel:oid_2": ["area A", "area A", "area B"], "ocel:qualifier": ["part of"] * 3}
    )
    log = OCEL.from_frames(base.events.pl.collect(), objects, e2o, o2o=o2o)
    qualifiers = dict(
        target_locations=LocationQualifiers(qualifiers=["to"]), pickup_locations=LocationQualifiers(qualifiers=["from"])
    )
    by_attribute = derive(log, example_config(high_level_locations=HighLevelObjectAttribute(attribute="area"), **qualifiers))
    assert by_attribute.errors == [] and by_attribute.context.agg == {"A1": "A", "A2": "A"}
    by_o2o = derive(
        log,
        example_config(
            high_level_locations=HighLevelO2O(qualifiers=["part of"], name_attribute="name"),
            vehicles=LocationObjectTypes(object_types=["truck"]),
            **qualifiers,
        ),
    )
    assert by_o2o.errors == []
    assert by_o2o.context.agg == {"A1": "A", "A2": "A", "B1": "B"}
    assert by_o2o.context.vehicles == {"T"}
    without_objects = derive(ocel, example_config(vehicles=LocationObjectTypes(object_types=["truck"])))
    assert [e.code for e in without_objects.errors] == ["no_location_objects"]
