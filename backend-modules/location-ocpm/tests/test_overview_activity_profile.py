"""Activity profile on the running example (concept section "Activity Profile", "Deriving the profile")."""

from ocelescope_module_location_based_ocpm.derivation.pipeline import derive
from ocelescope_module_location_based_ocpm.overview.activity_profile import activity_profile
from ocelescope_module_location_based_ocpm.overview.filters import PageFilter

from conftest import example_config


def typical(t):
    """A typical value as (value, count, total, distinct, tied), or None."""
    return None if t is None else (t.value, t.count, t.total, t.distinct, t.tied)


def rows(profile):
    """Rows by activity."""
    return {r.activity: r for r in profile.rows}


def test_profile_level_3(derivation):
    profile = activity_profile(derivation)
    assert [r.activity for r in profile.rows][:2] == ["crane move", "quality check"]  # most events, then alphabetical
    r = rows(profile)
    crane = r["crane move"]
    assert (crane.events, crane.movement_share, crane.transformation_share) == (4, 1.0, 0.0)
    assert (crane.hus_median, crane.hus_max) == (1.5, 2)
    assert typical(crane.typical_location) == ("A2", 4, 6, 2, 1)
    assert [(v.value, v.count) for v in crane.top_locations] == [("A2", 4), ("B1", 2)]
    assert crane.provided == 4
    assert typical(crane.typical_route) == ("A1 → A2", 2, 3, 2, 1)  # e11 moves nothing, c3 already at B1 in e12
    check = r["quality check"]
    assert typical(check.typical_location) == ("B1", 3, 4, 2, 1)
    assert check.provided == 1
    assert (check.fully_located, check.partially_located, check.unlocated) == (2, 1, 1)
    assert (check.agreed, check.tested_agreed, check.tested) == (3, 0, 1)
    assert check.typical_route is None
    assert typical(r["load truck"].typical_route) == ("A1 → T", 1, 4, 4, 4)
    assert [(t.object_type, t.count) for t in r["roll"].object_types] == [("coil", 2), ("slab", 1)]
    assert profile.rows[0].share_at_location is None


def test_profile_filter_b1_post(derivation):
    """Concept example with the location filter "B1, post"."""
    profile = activity_profile(derivation, PageFilter(locations=["B1"], location_role="after"))
    r = rows(profile)
    assert profile.kept_events == 6 and profile.location_filter
    assert set(r) == {"crane move", "quality check", "unload truck", "cut"}
    check = r["quality check"]
    assert (check.events, check.share_at_location) == (3, 0.5)
    assert (check.hus_median, check.hus_max) == (2, 2)
    assert typical(check.typical_location) == ("B1", 3, 3, 1, 1)
    assert (check.agreed, check.tested_agreed, check.tested) == (2, 0, 1)  # e14 still disagreeing
    assert typical(r["crane move"].typical_route) == ("A2 → B1", 1, 1, 1, 1)
    assert typical(r["unload truck"].typical_route) == ("T → B1", 1, 1, 1, 1)


def test_without_transformations(ocel):
    profile = activity_profile(derive(ocel, example_config(transformation_events=None)))
    assert all(r.transformation_share is None for r in profile.rows)
