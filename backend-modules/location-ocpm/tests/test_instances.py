"""Tests of the instance page (HU profile, lineage of a selection, HU timeline, object graph).

The running example (Level 3); the object graph uses `data/object_graph_example`.
"""

import json
import sys

import polars as pl
import pytest
from conftest import EXAMPLE

from ocelescope_module_location_based_ocpm.derivation.config import DerivationConfig
from ocelescope_module_location_based_ocpm.derivation.pipeline import derive
from ocelescope_module_location_based_ocpm.instances.charts import (
    selection_lineage,
    timeline_figure,
)
from ocelescope_module_location_based_ocpm.instances.object_graph import (
    object_frames,
    object_graph,
)
from ocelescope_module_location_based_ocpm.instances.profile import (
    ColumnFilter,
    column_info,
    export_frame,
    hu_details,
    hu_profile,
    query_profile,
    query_rows,
    sort_rows,
)

HOUR = 3600.0


@pytest.fixture(scope="module")
def full(ocel):
    """The running example with its full configuration (location context, processing operations)."""
    config = DerivationConfig.model_validate(json.loads((EXAMPLE / "configuration.json").read_text()))
    tables = {path.name: pl.read_csv(path, infer_schema=False) for path in (EXAMPLE / "inputs").glob("*.csv")}
    return derive(ocel, config, tables)


@pytest.fixture(scope="module")
def profile(full) -> pl.DataFrame:
    """The HU profile of the running example."""
    processing = full.relations.filter("is_processing")["event"].unique().to_list()
    return hu_profile(full.relations, full.handling_units, full.roles, full.context, full.loc, full.hl, processing)


def row(profile: pl.DataFrame, hu: str) -> dict:
    """The profile row of one handling unit."""
    return profile.filter(pl.col("hu") == hu).to_dicts()[0]


def test_lifecycle(profile):
    """Creation, final consumption and lifecycle class follow the transformation roles."""
    assert profile["hu"].to_list() == ["c1", "c2", "c3", "c4", "c5", "s1"]
    expected = {"s1": "both", "c1": "produced", "c2": "both", "c3": "open", "c4": "produced", "c5": "open"}
    assert dict(profile.select("hu", "lifecycle").iter_rows()) == expected
    c2 = row(profile, "c2")
    assert (c2["creation_event"], c2["creation_activity"]) == ("e3", "roll")
    assert (c2["final_consumption_event"], c2["final_consumption_activity"]) == ("e15", "cut")
    assert c2["n_partial_consumptions"] == 0
    assert row(profile, "c1")["lifespan"] == 11 * HOUR


def test_lineage_columns(profile):
    """Parents, children and siblings of the concept's table."""
    assert row(profile, "s1")["children"] == ["c1", "c2"]
    assert row(profile, "c4")["parents"] == ["c2"]
    assert row(profile, "c1")["siblings"] == ["c2"]
    assert row(profile, "c3")["n_parents"] == 0


def test_locations(profile):
    """Distinct locations, location changes and locatedness at Level 3."""
    c1 = row(profile, "c1")
    assert (c1["n_locations"], c1["n_high_level_locations"]) == (4, 3)  # A1, A2, B1, T; A, B, T
    assert (c1["first_location"], c1["last_location"], c1["n_location_changes"]) == ("A1", "T", 5)
    assert row(profile, "c5")["locatedness"] == "unlocated"


def test_time_per_location_kind(profile):
    """c1: A1 3-5, A2 5-7, B1 (storage) 7-8, T (vehicle) 8-9, A2 9-13, T 13-14; the four times add up to the lifespan."""
    c1 = row(profile, "c1")
    assert (c1["time_vehicle"], c1["time_storage"], c1["time_other"], c1["time_unlocated"]) == (2 * HOUR, HOUR, 8 * HOUR, 0)
    total = profile.select(pl.sum_horizontal("time_vehicle", "time_storage", "time_other", "time_unlocated"))
    assert total.to_series().to_list() == profile["lifespan"].to_list()
    assert row(profile, "c5")["time_unlocated"] == HOUR


def test_activities(profile):
    """Movements, processing operations (transformation events and label) and co-handled handling units."""
    c2 = row(profile, "c2")
    assert (c2["n_movements"], c2["n_processing"]) == (5, 3)
    assert c2["processing_activities"] == ["roll", "label", "cut"]



def test_connectedness(profile):
    """Non-transformation events of c2: e4, e6, e8, e9, e11, e12; shared: all but e6 (with c1 and c3)."""
    c2 = row(profile, "c2")
    assert (c2["n_shared_events"], c2["connectedness"], c2["n_co_handled"]) == (5, 5 / 6, 2)
    assert (row(profile, "s1")["n_shared_events"], row(profile, "s1")["n_co_handled"]) == (0, 0)  # only e1, e2, e3


def test_linked_handling_units(profile):
    """Linked HUs count transformation events too: c2 shares e3 with s1 and c1, e15 with c4, others with c1 and c3."""
    linked = dict(profile.select("hu", "n_linked").iter_rows())
    assert linked["c2"] == 4  # s1, c1 (also roll e3), c3, c4
    assert linked["s1"] == 2  # c1 and c2 via roll e3
    assert all(linked[hu] >= row(profile, hu)["n_co_handled"] for hu in linked)


def test_column_filters(profile):
    """Values, ranges (also on timestamps, in ms) and text filters; all filters must hold."""
    page, total = query_profile(profile, filters=[ColumnFilter("object_type", values=["coil"]), ColumnFilter("n_children", min=1)])
    assert (total, page["hu"].to_list()) == (1, ["c2"])
    _, total = query_profile(profile, filters=[ColumnFilter("lifecycle", values=["both", "open"])])
    assert total == 4
    first_c2 = row(profile, "c2")["first"].timestamp() * 1000
    rows = query_rows(profile, filters=[ColumnFilter("first", max=first_c2)])
    assert sorted(rows["hu"].to_list()) == ["c1", "c2", "s1"]
    assert query_rows(profile, filters=[ColumnFilter("hu", text="C")]).height == 5
    with pytest.raises(ValueError):
        query_rows(profile, filters=[ColumnFilter("parents", values=["s1"])])


def test_column_info(profile):
    """Category columns list their values (most frequent first), number and time columns their range."""
    info = {i["column"]: i for i in column_info(profile)}
    assert info["object_type"]["kind"] == "category" and info["object_type"]["values"][0] == ("coil", 5)
    assert info["hu"]["kind"] == "text"
    assert (info["n_events"]["kind"], info["n_events"]["min"], info["n_events"]["max"]) == ("number", 2, 9)
    assert info["first"]["kind"] == "time"


def test_export_frame(profile):
    """The folded table: matching rows in table order, hu first, then the shown columns."""
    rows = sort_rows(query_rows(profile, filters=[ColumnFilter("object_type", values=["coil"])]), "n_events", True)
    frame = export_frame(rows, ["n_events", "connectedness"])
    assert frame.columns == ["hu", "n_events", "connectedness"]
    assert frame["hu"].to_list()[:2] == ["c1", "c2"]
    with pytest.raises(ValueError):
        export_frame(rows, ["children"])


def test_hu_details(full, profile):
    """Unfolded row of c2: start and end, lineage names, location path, processing, co-handled with shared events."""
    processing = full.relations.filter("is_processing")["event"].unique().to_list()
    details = hu_details(full.relations, row(profile, "c2"), full.loc, full.hl, processing)
    assert (details["first_event"]["activity"], details["last_event"]["event"]) == ("roll", "e15")
    assert (details["creation"]["event"], details["final_consumption"]["activity"]) == ("e3", "cut")
    assert (details["parents"], details["children"], details["siblings"]) == (["s1"], ["c4"], ["c1"])
    assert [(p["location"], p["event"]) for p in details["location_path"]] == [("A1", "e3"), ("A2", "e6"), ("T", "e8"), ("A2", "e9"), ("B1", "e12")]
    assert [(h["hu"], h["events"]) for h in details["co_handled"]] == [("c1", ["e4", "e8", "e9", "e11"]), ("c3", ["e8", "e12"])]


def test_query(profile):
    """Search (all words), object-type filter, sorting with nulls last, paging."""
    page, total = query_profile(profile, search="roll coil")
    assert total == 2 and page["hu"].to_list() == ["c1", "c2"]
    page, total = query_profile(profile, object_types=["slab"])
    assert (total, page["hu"].to_list()) == (1, ["s1"])
    page, _ = query_profile(profile, sort_by="time_storage", descending=True, limit=2)
    assert page["hu"].to_list() == ["c3", "c2"]
    page, total = query_profile(profile, offset=4, limit=25)
    assert (total, page["hu"].to_list()) == (6, ["c5", "s1"])
    with pytest.raises(ValueError):
        query_profile(profile, sort_by="nonsense")


def test_selection_lineage(full):
    """Union of the lineages of c2 and c3; both selected handling units are focal."""
    lineage = selection_lineage(full, ["c2", "c3", "x9"], "both", 2)
    roles = dict(lineage.nodes.select("node", "role").iter_rows())
    assert roles == {"c2": "focal", "c3": "focal", "c4": "lineage", "s1": "lineage"}
    assert sorted(lineage.edges.select("source", "target", "activity").iter_rows()) == [("c2", "c4", "cut"), ("s1", "c2", "roll")]
    assert lineage.notes == ["Not handling units of this log: x9."]
    with_siblings = selection_lineage(full, ["c2"], "both", 2, with_events=True, with_siblings=True)
    assert dict(with_siblings.nodes.select("node", "role").iter_rows())["c1"] == "sibling"


def test_timeline_figure(full):
    """The timeline is Plotly JSON; unknown and event-less handling units are named in the notes."""
    figure, notes = timeline_figure(full, ["c2", "zz"])
    assert figure["data"] and "layout" in figure
    assert notes == ["Not handling units of this log: zz."]


def test_timeline_movement_markers(full):
    """Explicit movements: one open circle per movement of c2 (5) on the band; with labels also their activity names."""
    implicit, _ = timeline_figure(full, ["c2"])
    explicit, _ = timeline_figure(full, ["c2"], movement_markers="explicit")
    labelled, _ = timeline_figure(full, ["c2"], movement_markers="explicit with label")
    circles = [t for t in explicit["data"] if t.get("name", "").startswith("movement (explicit)")]
    assert sum(len(t["customdata"]) for t in circles) == 5
    assert not any(t.get("name", "").startswith("movement (explicit)") for t in implicit["data"])
    texts = lambda figure: [a["text"] for a in figure["layout"].get("annotations", [])]
    assert texts(explicit) == texts(implicit)
    assert sorted(set(texts(labelled)) - set(texts(implicit))) == ["crane move", "load truck", "unload truck"]


@pytest.fixture(scope="module")
def object_example():
    """The object graph example (running example plus crane, truck, operators, orders, customer and o2o relations)."""
    sys.path.insert(0, str(EXAMPLE.parent / "object_graph_example"))
    import make_object_graph_example

    return object_frames(make_object_graph_example.build_ocel())


def test_object_graph(object_example):
    """c2: related by events (c1, c3, c4, s1, crane1, op1, op2, truck1) and by o2o (o1, c4); arcs among all of them."""
    graph = object_graph(object_example, ["c2", "zz"], ["s1", "c1", "c2", "c3", "c4", "c5"])
    assert graph.nodes["node"].to_list() == ["c2", "c1", "c3", "c4", "s1", "crane1", "op1", "op2", "truck1", "o1"]
    assert dict(graph.nodes.select("node", "role").iter_rows())["c2"] == "focal"
    assert dict(graph.nodes.select("node", "n_shared").iter_rows())["o1"] == 0
    arcs = {(s, t): [e["event"] for e in events] for s, t, events in graph.event_arcs.select("source", "target", "events").iter_rows()}
    assert arcs[("c1", "c2")] == ["e3", "e4", "e8", "e9", "e11"]
    assert arcs[("crane1", "op1")] == ["e5", "e6", "e11", "e12"]  # between two related objects
    assert ("c2", "c5") not in arcs and "c5" not in graph.nodes["node"].to_list()
    first = graph.event_arcs.filter(pl.col("source") == "c1", pl.col("target") == "c2")["events"][0][0]
    assert (first["activity"], first["time"].hour) == ("roll", 3)
    assert sorted(graph.o2o_arcs.iter_rows()) == [
        ("c1", "o1", "part of"),
        ("c2", "o1", "part of"),
        ("c4", "c2", "cut from"),
        ("op1", "crane1", "operates"),
        ("op2", "truck1", "drives"),
    ]
    assert graph.notes == ["Not handling units of this log: zz."]
    cut = object_graph(object_example, ["c2"], ["s1", "c1", "c2", "c3", "c4", "c5"], max_nodes=3)
    assert cut.nodes["node"].to_list() == ["c2", "c1", "c3"] and cut.notes == ["10 objects; only the first 3 are drawn."]
