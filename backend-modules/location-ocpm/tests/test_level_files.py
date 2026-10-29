"""Saving and loading the per-level location mappings (`derivation.level_files`)."""

import polars as pl
from polars.testing import assert_frame_equal

from conftest import EXAMPLE, expected
from ocelescope_module_location_based_ocpm.derivation.level_files import (
    MAPPING_COLUMNS,
    level_mapping,
    load_level_mapping,
    save_level_mappings,
)


def test_round_trip(derivation, tmp_path):
    paths = save_level_mappings(derivation, tmp_path)
    assert [p.name for p in paths] == [f"locations_level_{k}.csv" for k in range(4)]
    for level in range(4):
        assert_frame_equal(load_level_mapping(tmp_path, level), level_mapping(derivation, level))


def test_mapping_matches_expected_levels(derivation):
    for level in range(4):
        mapping = level_mapping(derivation, level)
        assert mapping.columns == MAPPING_COLUMNS
        actual = mapping.select("hu", "event", pl.col("loc").alias(f"loc_{level}")).sort("hu", "event")
        assert_frame_equal(actual, expected("levels").select("hu", "event", f"loc_{level}").sort("hu", "event"))


def test_committed_files_are_up_to_date(derivation):
    """The files in data/running_example/derived/ match the current derivation (rerun the notebook if not)."""
    for level in range(4):
        assert_frame_equal(load_level_mapping(EXAMPLE / "derived", level), level_mapping(derivation, level))
