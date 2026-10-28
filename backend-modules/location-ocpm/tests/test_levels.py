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
