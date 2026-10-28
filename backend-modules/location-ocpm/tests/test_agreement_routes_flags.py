"""Agreement, locatedness, routes and flags against the concept's running example."""

import polars as pl
from polars.testing import assert_frame_equal

from conftest import example_config, expected
from ocelescope_module_location_based_ocpm.derivation.agreement import hu_locatedness
from ocelescope_module_location_based_ocpm.derivation.pipeline import derive
from ocelescope_module_location_based_ocpm.derivation.routes import activity_routes, event_routes


def test_agreement_examples(derivation):
    for row in expected("agreement").iter_rows(named=True):
        actual = derivation.event_locations[int(row["level"])].filter(pl.col("event") == row["event"]).row(0, named=True)
        assert actual["located"] == row["located"], row
        assert actual["agreeing"] == (row["agreement"] == "agreeing"), row
        assert actual["eloc"] == row["eloc"], row


def test_events_without_handling_units_are_unlocated(derivation):
    assert derivation.event_locations[3].height == 17


def test_hu_locatedness_level_3(derivation):
    located = dict(hu_locatedness(derivation.relations, "loc_3").select("hu", "located").iter_rows())
    assert located == {
        "s1": "fully located", "c1": "fully located", "c2": "fully located",
        "c3": "fully located", "c4": "fully located", "c5": "unlocated",
    }


def test_routes_level_3(derivation):
    actual = event_routes(derivation.relations, 3).select("event", "activity", "previous", "current", "count")
    want = expected("routes").with_columns(pl.col("count").cast(pl.UInt32))
    assert_frame_equal(actual.sort("event", "previous", nulls_last=True), want.sort("event", "previous", nulls_last=True))


def test_route_of_e5_below_level_3(derivation):
    for level in (0, 1, 2):
        e5 = event_routes(derivation.relations, level).filter(pl.col("event") == "e5")
        assert e5.select("previous", "current").rows() == [(None, "A2")]


def test_activity_routes_level_3(derivation):
    routes = activity_routes(event_routes(derivation.relations, 3))
    crane = routes.filter(pl.col("activity") == "crane move").select("previous", "current", "count").rows()
    assert sorted(crane) == [("A1", "A2", 2), ("A2", "B1", 1)]


def test_flags_level_3(derivation):
    flags = derivation.flags
    want = expected("flags")
    ids = lambda flag: want.filter(pl.col("flag") == flag)["id"].to_list()
    assert flags.f1.to_list() == ids("F1")
    assert flags.f2.to_list() == ids("F2")
    assert flags.f3.to_list() == ids("F3")
    assert flags.f4.to_list() == ids("F4")
    assert flags.f5["event"].to_list() == sorted(ids("F5"))
    assert dict(flags.f5.iter_rows()) == {"e7": "a", "e11": "b"}


def test_flags_use_the_selected_level(ocel):
    """At Level 1, e5 has no previous location for c1, so F5 (b) and F1 do not change, but the
    selected columns do."""
    level_1 = derive(ocel, example_config(level=1))
    assert (level_1.loc, level_1.ploc) == ("loc_1", "ploc_1")
    assert level_1.flags.f1.to_list() == ["e11", "e12"]
