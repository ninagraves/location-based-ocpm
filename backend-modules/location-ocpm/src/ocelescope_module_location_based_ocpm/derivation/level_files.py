"""Save and load the derived location mapping of each level as one CSV file per level.

Used by the notebooks: `notebooks/location_derivation.ipynb` writes the files of the running example,
other notebooks (e.g. `notebooks/trace_figure.ipynb`) load them instead of deriving again.

File format (one file per level k, `locations_level_{k}.csv`):
- one row per hu-event relation, sorted by hu, time, event;
- columns `MAPPING_COLUMNS`: event, hu, object_type, time, activity, is_movement, is_transformation, loc, ploc;
- `loc` = loc_k and `ploc` = ploc_k, so every file has the same columns and the level is in the file name;
- time in ISO format, booleans as true/false, ⊥ as an empty cell.
"""

from collections.abc import Iterable
from pathlib import Path

import polars as pl

from . import columns as c
from .pipeline import Derivation

#: Column of the current location loc_k in a level file.
LOC = "loc"
#: Column of the previous location ploc_k in a level file.
PLOC = "ploc"

#: Columns of a level file, in this order, with their types.
MAPPING_SCHEMA = {
    c.EVENT: pl.String,
    c.HU: pl.String,
    c.OBJECT_TYPE: pl.String,
    c.TIME: pl.Datetime("us"),
    c.ACTIVITY: pl.String,
    c.IS_MOVEMENT: pl.Boolean,
    c.IS_TRANSFORMATION: pl.Boolean,
    LOC: pl.String,
    PLOC: pl.String,
}
MAPPING_COLUMNS = list(MAPPING_SCHEMA)


def level_file_name(level: int) -> str:
    """File name of the mapping of one level.

    Args:
        level: Level k (0 to 3).

    Returns:
        str: e.g. "locations_level_2.csv".
    """
    return f"locations_level_{level}.csv"


def level_mapping(derivation: Derivation, level: int) -> pl.DataFrame:
    """The location mapping of one level: loc_k and ploc_k per hu-event relation.

    Args:
        derivation: Result of `pipeline.derive` without blocking errors.
        level: Level k (0 to 3); independent of the level selected in the configuration.

    Returns:
        pl.DataFrame: Columns `MAPPING_COLUMNS`, sorted by hu, time, event.
    """
    if derivation.errors:
        raise ValueError(f"The derivation has blocking errors: {[e.code for e in derivation.errors]}")
    return (
        derivation.relations.select(
            *MAPPING_COLUMNS[:-2],
            pl.col(c.loc(level)).alias(LOC),
            pl.col(c.ploc(level)).alias(PLOC),
        )
        .sort(c.HU, c.TIME, c.EVENT)
    )


def save_level_mappings(
    derivation: Derivation, folder: str | Path, levels: Iterable[int] = c.LEVELS
) -> list[Path]:
    """Write the location mapping of each level to `folder/locations_level_{k}.csv`.

    Args:
        derivation: Result of `pipeline.derive` without blocking errors.
        folder: Target folder; created if missing. Existing files are overwritten.
        levels: Levels to write (default: all, 0 to 3).

    Returns:
        list[Path]: The written files, one per level.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for level in levels:
        path = folder / level_file_name(level)
        level_mapping(derivation, level).write_csv(path)
        paths.append(path)
    return paths


def load_level_mapping(folder: str | Path, level: int) -> pl.DataFrame:
    """Read the location mapping of one level written by `save_level_mappings`.

    Args:
        folder: Folder holding the level files.
        level: Level k (0 to 3).

    Returns:
        pl.DataFrame: Columns and types as in `MAPPING_SCHEMA`; empty cells are null (⊥).
    """
    return pl.read_csv(Path(folder) / level_file_name(level), schema=MAPPING_SCHEMA)
