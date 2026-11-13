"""Tests of the transformation inputs (T, consumed and produced handling units): options 1 to 6 of
`overview/concepts/Transformations.md` on the running example, and the assumption checks AS-T1 to AS-T4."""

import polars as pl
import pytest
from conftest import example_config
from ocelescope_module_location_based_ocpm.derivation.config import (
    Activities,
    DerivationConfig,
    ObjectTable,
    RolesFromFirstLast,
    RolesFromFrequency,
    RolesFromObjectSets,
    RolesFromQualifiers,
    RolesFromTable,
)
from ocelescope_module_location_based_ocpm.derivation.inputs import resolve_inputs
from ocelescope_module_location_based_ocpm.derivation.transformations import (
    activity_frequencies,
    check_assumptions,
    first_last_events,
    roles_from_parents,
)

#: cons and prod of the running example (= inputs/transformation_roles.csv).
EXAMPLE_ROLES = {
    ("e1", "s1", "produced"),
    ("e3", "s1", "consumed"),
    ("e3", "c1", "produced"),
    ("e3", "c2", "produced"),
    ("e15", "c2", "consumed"),
    ("e15", "c4", "produced"),
}
#: Candidates including the label event e4, which is no transformation event.
WITH_LABEL = Activities(activities=["cast slab", "roll", "label", "cut"])


def _resolve(ocel, tables=None, **changes):
    """resolve_inputs on the running example with configuration changes."""
    return resolve_inputs(ocel, example_config(**changes), tables)


def _roles(resolved) -> set[tuple]:
    """The roles as a set of (event, hu, role)."""
    return set(resolved.roles.iter_rows())


def _t(resolved) -> set[str]:
    """T as a set of event ids."""
    return set(resolved.events.filter(pl.col("is_transformation"))["event"])


def _codes(resolved) -> set[str]:
    """The notice codes."""
    return {n.code for n in resolved.notices}


def test_default_is_first_last(ocel):
    """Only transformation events given: option 5; the example's roles."""
    resolved = _resolve(ocel)
    assert _t(resolved) == {"e1", "e3", "e15"}
    assert _roles(resolved) == EXAMPLE_ROLES


def test_no_transformation_input(ocel):
    """Neither input: T is empty."""
    resolved = _resolve(ocel, transformation_events=None)
    assert _t(resolved) == set() and resolved.roles.is_empty()


def test_option_1_qualifiers(ocel):
    """Option 1: T and roles from the e2o qualifiers; a given T-input is ignored and reported."""
    option = RolesFromQualifiers(consumed_qualifiers=["consumed"], produced_qualifiers=["produced"])
    resolved = _resolve(ocel, transformation_events=None, transformation_roles=option)
    assert _t(resolved) == {"e1", "e3", "e15"}
    assert _roles(resolved) == EXAMPLE_ROLES
    assert "transformation_events_ignored" in _codes(_resolve(ocel, transformation_roles=option))


def test_option_2_table(ocel, input_tables):
    """Option 2: roles from a table; T from the table when no T-input is given."""
    option = RolesFromTable(table="transformation_roles", event_column="event", object_column="hu", role_column="role")
    resolved = _resolve(ocel, input_tables, transformation_events=None, transformation_roles=option)
    assert _t(resolved) == {"e1", "e3", "e15"} and _roles(resolved) == EXAMPLE_ROLES


def test_option_2_table_with_candidates(ocel, input_tables):
    """Option 2 with T given: e4 has no roles in the table and is dropped (AS-T1)."""
    option = RolesFromTable(table="transformation_roles", event_column="event", object_column="hu", role_column="role")
    resolved = _resolve(ocel, input_tables, transformation_events=WITH_LABEL, transformation_roles=option)
    assert _t(resolved) == {"e1", "e3", "e15"}
    notice = next(n for n in resolved.notices if n.code == "AS-T1")
    assert notice.ids == ["e4"]


def test_option_3_parents(ocel, derivation):
    """Option 3 on frames (the example log has no o2o relations): the note's example."""
    e2hu = derivation.relations.select("event", "hu", "time")
    parents = pl.DataFrame({"child": ["c1", "c2", "c4"], "parent": ["s1", "s1", "c2"]})
    candidates = pl.Series(["e1", "e3", "e4", "e15"])
    roles = roles_from_parents(e2hu, parents, candidates, first_last_events(e2hu))
    assert set(roles.iter_rows()) == EXAMPLE_ROLES


def test_option_3_needs_transformation_events():
    """Options 3 to 5 need the transformation-events input."""
    base = example_config().model_dump()
    for option in ({"option": "parents", "qualifiers": ["child of"]}, {"option": "object_sets"}, {"option": "first_last"}):
        with pytest.raises(ValueError):
            DerivationConfig.model_validate({**base, "transformation_events": None, "transformation_roles": option})


@pytest.mark.parametrize(
    "consumption, t, extra",
    [
        ("final", {"e1", "e3", "e15"}, set()),
        ("partial", {"e1", "e3", "e4", "e15"}, {("e1", "s1", "consumed"), ("e3", "c2", "consumed"), ("e4", "c2", "consumed")}),
    ],
)
def test_option_4_object_sets(ocel, consumption, t, extra):
    """Option 4: HU_prod = {s1, c1, c2, c4}, HU_cons = {s1, c2} (the note's example)."""
    tables = {
        "produced": pl.DataFrame({"object": ["s1", "c1", "c2", "c4"]}),
        "consumed": pl.DataFrame({"object": ["s1", "c2"]}),
    }
    option = RolesFromObjectSets(
        produced=ObjectTable(table="produced", object_column="object"),
        consumed=ObjectTable(table="consumed", object_column="object"),
        consumption=consumption,
    )
    resolved = _resolve(ocel, tables, transformation_events=WITH_LABEL, transformation_roles=option)
    assert _t(resolved) == t
    assert _roles(resolved) == EXAMPLE_ROLES | extra


def test_option_5_drops_label(ocel):
    """Option 5 with e4 as candidate: e4 has no first or last event of a hu and is dropped (AS-T1)."""
    resolved = _resolve(ocel, transformation_events=WITH_LABEL, transformation_roles=RolesFromFirstLast())
    assert _t(resolved) == {"e1", "e3", "e15"} and _roles(resolved) == EXAMPLE_ROLES
    assert "AS-T1" in _codes(resolved)


def test_option_6_frequencies(derivation):
    """Option 6: the frequency table of the note."""
    e2hu = derivation.relations.select("event", "hu", "object_type", "time", "activity")
    freq = activity_frequencies(e2hu, first_last_events(e2hu))
    rows = {(t, tt, a): f for t, tt, a, _, f in freq.iter_rows()}
    assert rows[("coil", "prod", "roll")] == pytest.approx(0.4)
    assert rows[("coil", "cons", "quality check")] == pytest.approx(0.8)
    assert rows[("slab", "prod", "cast slab")] == 1


def test_option_6_threshold_03(ocel):
    """τ = 0.3: T = {e1, e3, e14, e16, e17} with the note's cons and prod."""
    resolved = _resolve(ocel, transformation_events=None, transformation_roles=RolesFromFrequency(threshold=0.3))
    assert _t(resolved) == {"e1", "e3", "e14", "e16", "e17"}
    assert _roles(resolved) == {
        ("e1", "s1", "produced"),
        ("e3", "s1", "consumed"),
        ("e3", "c1", "produced"),
        ("e3", "c2", "produced"),
        ("e14", "c1", "consumed"),
        ("e14", "c3", "consumed"),
        ("e16", "c4", "consumed"),
        ("e16", "c5", "produced"),
        ("e17", "c5", "consumed"),
    }


def test_option_6_threshold_09(ocel):
    """τ = 0.9: only the slab activities qualify; T = {e1, e3}."""
    resolved = _resolve(ocel, transformation_events=None, transformation_roles=RolesFromFrequency(threshold=0.9))
    assert _t(resolved) == {"e1", "e3"}


def test_first_last_tie_break():
    """Ties at the first/last timestamp: processing operations first, then the smallest event id."""
    e2hu = pl.DataFrame({"event": ["b", "a", "c"], "hu": ["x", "x", "x"], "time": [1, 1, 2]})
    assert first_last_events(e2hu).row(0) == ("x", "a", "c")
    assert first_last_events(e2hu, pl.Series(["b"])).row(0) == ("x", "b", "c")


def test_assumption_checks():
    """AS-T2, AS-T3 and AS-T4 violations are reported with their events.

    a is produced at t1 but occurs at t0 (AS-T2); c is fully consumed at t3 but occurs at t5 (AS-T3); t6 and t7
    share d at the same timestamp (AS-T4). b is consumed at t1, which produces a, so it is not fully consumed.
    """
    e2hu = pl.DataFrame(
        {
            "event": ["t0", "t1", "t1", "t2", "t3", "t5", "t6", "t7"],
            "hu": ["a", "a", "b", "b", "c", "c", "d", "d"],
            "time": [0, 1, 1, 2, 3, 5, 6, 6],
        }
    )
    roles = pl.DataFrame(
        {
            "event": ["t1", "t1", "t3", "t6", "t7"],
            "hu": ["a", "b", "c", "d", "d"],
            "role": ["produced", "consumed", "consumed", "produced", "consumed"],
        }
    )
    notices = {n.code: sorted(n.ids) for n in check_assumptions(e2hu, roles)}
    assert notices == {"AS-T2": ["t1"], "AS-T3": ["t3"], "AS-T4": ["t6", "t7"]}
