"""Levels 0-3, before and ploc against the tables of the concept's running example."""

import polars as pl
from polars.testing import assert_frame_equal

from conftest import expected


def test_no_errors(derivation):
    assert derivation.errors == []
    assert derivation.notices == []
    assert derivation.relations.height == 28


def test_levels(derivation):
    columns = ["hu", "event", "loc_0", "loc_1", "loc_2", "loc_3"]
    actual = derivation.relations.select(columns).sort("hu", "event")
    assert_frame_equal(actual, expected("levels").sort("hu", "event"))


def test_before_and_ploc_level_1(derivation):
    actual = derivation.relations.select("hu", "event", "puloc", "before_1", "ploc_1").sort("hu", "event")
    assert_frame_equal(actual, expected("ploc_1").sort("hu", "event"))


def test_level_at_which_a_relation_is_first_located(derivation):
    """Concept: Level 0: 15, Level 1: 4, Level 2: 3, Level 3: 4, never: 2."""
    first = derivation.relations.select(
        pl.when(pl.col("loc_0").is_not_null()).then(pl.lit("0"))
        .when(pl.col("loc_1").is_not_null()).then(pl.lit("1"))
        .when(pl.col("loc_2").is_not_null()).then(pl.lit("2"))
        .when(pl.col("loc_3").is_not_null()).then(pl.lit("3"))
        .otherwise(pl.lit("never"))
        .alias("first")
    )["first"].value_counts()
    assert dict(first.iter_rows()) == {"0": 15, "1": 4, "2": 3, "3": 4, "never": 2}


def test_t1_tie_rule():
    """t_1(hu) at equal times: only transformations with eloc ≠ ⊥ qualify, then the smaller event id.

    h has no movement and no provided location. At time 1, t2 disagrees (x at A, y at B) and
    t3 is at C; at time 1 also t1 is at D. t1 and t3 qualify, t2 does not; t1 has the smaller id.
    """
    from ocelescope_module_location_based_ocpm.derivation.agreement import event_locations
    from ocelescope_module_location_based_ocpm.derivation.levels import add_loc_3

    relations = pl.DataFrame(
        {
            "event": ["t1", "t2", "t3", "t1", "t2", "t2", "t3"],
            "hu": ["h", "h", "h", "a", "x", "y", "c"],
            "time": [1] * 7,
            "is_transformation": [True] * 7,
            "is_movement": [False] * 7,
            "uloc": [None] * 7,
            "puloc": [None] * 7,
            "loc_2": [None, None, None, "D", "A", "B", "C"],
        },
        schema_overrides={"uloc": pl.String, "puloc": pl.String, "loc_2": pl.String},
    )
    events = relations.select("event").unique()
    eloc_2 = event_locations(relations, events, "loc_2").select("event", "eloc")
    loc_3 = add_loc_3(relations, eloc_2).filter(pl.col("hu") == "h")["loc_3"].unique().to_list()
    assert loc_3 == ["D"]
