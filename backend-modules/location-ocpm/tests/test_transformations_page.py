"""Tests of the transformations page (draft): events, filters, key numbers, charts, profile and type graph.

The running example (T = {e1, e3, e15}) and a small extended example with a second roll (3 coils instead of 2),
a weld (2 coils into 1) and a scrap (consumption only), which make the quantities and kinds differ.
"""

import polars as pl
import pytest

from ocelescope_module_location_based_ocpm.transformations.charts import transformation_bar_chart
from ocelescope_module_location_based_ocpm.transformations.events import (
    TransformationFilter,
    filter_events,
    transformation_events,
)
from ocelescope_module_location_based_ocpm.transformations.key_numbers import key_numbers, transformation_count
from ocelescope_module_location_based_ocpm.transformations.profile import type_profile
from ocelescope_module_location_based_ocpm.transformations.type_graph import min_frequency, type_graph


@pytest.fixture(scope="module")
def running(derivation) -> pl.DataFrame:
    """Transformation events of the running example, with loc at Level 3."""
    return transformation_events(
        derivation.events, derivation.roles, derivation.handling_units, derivation.relations, derivation.loc
    )


@pytest.fixture(scope="module")
def extended() -> pl.DataFrame:
    """Transformation events of the extended example (no locations)."""
    events = pl.DataFrame(
        {
            "event": ["e1", "e3", "e15", "e30", "e31", "e32", "e40"],
            "activity": ["cast slab", "roll", "cut", "roll", "weld", "scrap", "label"],
            "is_transformation": [True, True, True, True, True, True, False],
        }
    )
    roles = pl.DataFrame(
        [
            ("e1", "s1", "produced"),
            ("e3", "s1", "consumed"),
            ("e3", "c1", "produced"),
            ("e3", "c2", "produced"),
            ("e15", "c2", "consumed"),
            ("e15", "c4", "produced"),
            ("e30", "s2", "consumed"),
            ("e30", "c6", "produced"),
            ("e30", "c7", "produced"),
            ("e30", "c8", "produced"),
            ("e31", "c6", "consumed"),
            ("e31", "c7", "consumed"),
            ("e31", "c9", "produced"),
            ("e32", "c8", "consumed"),
        ],
        schema=["event", "hu", "role"],
        orient="row",
    )
    hus = pl.DataFrame(
        {
            "hu": ["s1", "s2", "c1", "c2", "c4", "c6", "c7", "c8", "c9"],
            "object_type": ["slab", "slab"] + ["coil"] * 7,
        }
    )
    return transformation_events(events, roles, hus)


def test_events_of_the_running_example(running):
    rows = {r["event"]: r for r in running.to_dicts()}
    assert set(rows) == {"e1", "e3", "e15"}
    assert rows["e3"]["transformation_type"] == "1 slab → 2 coil"
    assert rows["e3"]["recipe"] == "roll: 1 slab → 2 coil"
    assert rows["e1"]["transformation_type"] == "∅ → 1 slab"
    assert rows["e1"]["kind"] == "production_only"
    assert rows["e15"]["locations"] == ["B1"]


def test_events_of_the_extended_example(extended):
    rows = {r["event"]: r for r in extended.to_dicts()}
    assert "e40" not in rows
    assert rows["e30"]["output"] == "3 coil"
    assert rows["e31"]["transformation_type"] == "2 coil → 1 coil"
    assert rows["e32"]["transformation_type"] == "1 coil → ∅"
    assert rows["e32"]["kind"] == "consumption_only"
    assert rows["e31"]["locations"] == []


def test_filters_keep_whole_events(running, extended):
    assert filter_events(running, TransformationFilter(consumes=["slab"]))["event"].to_list() == ["e3"]
    assert filter_events(running, TransformationFilter(kind="production_only"))["event"].to_list() == ["e1"]
    kept = filter_events(extended, TransformationFilter(produces=["coil"], consumes=["coil"]))
    assert sorted(kept["event"].to_list()) == ["e15", "e31"]
    assert filter_events(extended, TransformationFilter()).height == extended.height


def test_key_numbers_of_the_running_example(running, derivation):
    numbers = key_numbers(running, derivation.roles, derivation.relations["hu"].n_unique())
    assert numbers.transformation_events == 3
    assert numbers.transformations == 3
    assert numbers.activities == 3
    assert numbers.transformation_types == 3
    assert numbers.recipes == 3
    assert numbers.lineage_relations == 3
    assert {k.name: k.count for k in numbers.kinds} == {"both": 2, "consumption_only": 0, "production_only": 1}
    assert (numbers.handling_units, numbers.produced_handling_units, numbers.consumed_handling_units) == (6, 4, 2)


def test_transformations_count_welds_per_consumed_unit(extended):
    # 1 (e3) + 1 (e15) + 1 (e30) + 2 (e31) + 1 (e32) consumed, plus 1 produced at e1 without consumption.
    assert transformation_count(extended) == 7


def test_activities_chart_by_kind(running):
    chart = transformation_bar_chart(running, "activities", "kind")
    assert [b.label for b in chart.bars] == ["cast slab", "cut", "roll"]
    assert chart.bars[0].segments[0].value == "production only"
    assert chart.other is None


def test_locations_chart_counts_events_per_location(running):
    chart = transformation_bar_chart(running, "locations", "activity")
    assert {b.label: b.count for b in chart.bars} == {"A1": 2, "B1": 1}


def test_diversity_chart(extended):
    chart = transformation_bar_chart(extended, "diversity", per="activity")
    assert {b.label: b.count for b in chart.bars}["roll"] == 2
    chart = transformation_bar_chart(extended, "diversity", per="transformation_type")
    assert max(b.count for b in chart.bars) == 1


def test_profile_rows(extended):
    rows = {r.transformation_type: r for r in type_profile(extended)}
    weld = rows["2 coil → 1 coil"]
    assert (weld.events, weld.transformations, weld.lineage_relations) == (1, 2, 2)
    assert weld.typical_activity == "weld"
    assert rows["1 coil → ∅"].lineage_relations == 0


def test_type_graph_of_the_running_example(running):
    graph = type_graph(running)
    assert [r.recipe for r in graph.recipes] == ["cast slab: ∅ → 1 slab", "cut: 1 coil → 1 coil", "roll: 1 slab → 2 coil"]
    arcs = {(a.source, a.target): a.quantity_min for a in graph.arcs}
    assert arcs == {
        ("recipe:r1", "type:slab"): 1,
        ("type:coil", "recipe:r2"): 1,
        ("recipe:r2", "type:coil"): 1,
        ("type:slab", "recipe:r3"): 1,
        ("recipe:r3", "type:coil"): 2,
    }
    assert [t.object_type for t in graph.object_types] == ["coil", "slab"]


def test_type_graph_quantities(extended):
    exact = type_graph(extended, quantities="exact")
    assert sum(r.activity == "roll" for r in exact.recipes) == 2
    sets = type_graph(extended, quantities="sets")
    roll = next(r for r in sets.recipes if r.activity == "roll")
    assert (roll.recipe, roll.frequency) == ("roll: slab → coil", 2)
    output = next(a for a in sets.arcs if a.recipe == roll.id and a.role == "produced")
    assert (output.quantity_min, output.quantity_max, output.hus) == (2, 3, 5)


def test_min_frequency():
    frequencies = pl.Series([5, 3, 1, 1])
    assert min_frequency(frequencies, 0.8) == 3
    assert min_frequency(frequencies, 0.81) == 1
    assert min_frequency(frequencies, 0.0) == 5
    assert min_frequency(frequencies, 1.0) == 1
    assert min_frequency(pl.Series([], dtype=pl.Int64), 0.5) == 0


def test_slider_hides_rare_recipes(extended):
    # Sets: roll 2 events, the other four recipes 1 event each (6 events); 1/3 coverage keeps roll only.
    graph = type_graph(extended, coverage=0.3, quantities="sets")
    assert [r.activity for r in graph.recipes] == ["roll"]
    assert (graph.recipes_total, graph.events_shown, graph.events_total, graph.min_frequency) == (5, 2, 6, 2)
    assert {a.object_type for a in graph.arcs} == {"slab", "coil"}


def test_routes(ocel):
    """The routes, called as plain functions (as in test_configuration_api.py)."""
    from test_configuration_api import FakeSession

    from conftest import example_config
    from ocelescope_module_location_based_ocpm import configuration_routes as config_routes
    from ocelescope_module_location_based_ocpm import transformation_routes as routes

    session = FakeSession("transformations")
    state = config_routes.get_state(session)
    assert config_routes.apply_config("log", example_config(), ocel, session, state).applied
    derivation = config_routes.current_derivation("log", ocel, session, state)
    overview = routes.get_transformation_overview("log", derivation, state, TransformationFilter())
    assert overview.configured and overview.key_numbers.recipes == 3
    assert [t.name for t in overview.consumed_types] == ["coil", "slab"]
    kept = TransformationFilter(kind="both")
    assert len(routes.get_transformation_profile("log", derivation, state, kept)) == 2
    chart = routes.get_transformation_bar_chart("log", derivation, state, kept, chart="transformation_types", by="activity")
    assert len(chart.bars) == 2
    graph = routes.get_transformation_type_graph("log", derivation, state, TransformationFilter(), coverage=1.0)
    assert len(graph.recipes) == 3
