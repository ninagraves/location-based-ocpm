"""Save and load maximal visits as a CSV file, so later notebooks can load them instead of deriving again.

File format (`maximal_visits_level_{k}_kappa_{κ}.csv`):
- one row per maximal visit, sorted by visit_id;
- columns `VISIT_SCHEMA` (the core columns of `maximal.maximal_visits`; durations and the shift and
  waiting columns are left out, since they are cheap to recompute and CSV has no duration or list type);
- time in ISO format, booleans as true/false, ⊥ as an empty cell.
"""

from pathlib import Path

import polars as pl

from ..derivation import columns as c
from . import columns as v

#: Columns of a visits file, in this order, with their types.
VISIT_SCHEMA = {
    v.VISIT_ID: pl.Int64,
    c.HU: pl.String,
    v.HIGH_LEVEL: pl.String,
    v.KAPPA: pl.Int64,
    v.FIRST_POSITION: pl.Int64,
    v.LAST_POSITION: pl.Int64,
    v.FIRST_EVENT: pl.String,
    v.LAST_EVENT: pl.String,
    v.EXIT_EVENT: pl.String,
    v.ENTRY_TIME: pl.Datetime("us"),
    v.LAST_TIME: pl.Datetime("us"),
    v.EXIT_TIME: pl.Datetime("us"),
    v.ENDS_TRACE: pl.Boolean,
    v.N_RELATIONS: pl.Int64,
    v.N_AT_LOCATION: pl.Int64,
    v.INTERRUPTED: pl.Boolean,
}


def visits_file_name(level: int, kappa: int) -> str:
    """File name of the maximal visits of one level and tolerance.

    Args:
        level: Location level k the visits were derived from.
        kappa: κ_max used.

    Returns:
        str: e.g. "maximal_visits_level_3_kappa_2.csv".
    """
    return f"maximal_visits_level_{level}_kappa_{kappa}.csv"


def save_visits(visits: pl.DataFrame, folder: str | Path, level: int, kappa: int) -> Path:
    """Write the core columns of the maximal visits to `folder/maximal_visits_level_{k}_kappa_{κ}.csv`.

    Args:
        visits: Maximal visits (`maximal.maximal_visits` or `VisitAnalysis.visits`).
        folder: Target folder; created if missing. An existing file is overwritten.
        level: Location level k the visits were derived from (only used in the file name).
        kappa: κ_max used (only used in the file name).

    Returns:
        Path: The written file.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / visits_file_name(level, kappa)
    visits.select(
        pl.col(name).cast(dtype) for name, dtype in VISIT_SCHEMA.items()
    ).sort(v.VISIT_ID).write_csv(path)
    return path


def load_visits(folder: str | Path, level: int, kappa: int) -> pl.DataFrame:
    """Read maximal visits written by `save_visits`.

    Args:
        folder: Folder holding the file.
        level: Location level k.
        kappa: κ_max.

    Returns:
        pl.DataFrame: Columns and types as in `VISIT_SCHEMA`, plus duration (exit_time - entry_time);
        empty cells are null (⊥).
    """
    visits = pl.read_csv(Path(folder) / visits_file_name(level, kappa), schema=VISIT_SCHEMA)
    return visits.with_columns(
        (pl.col(v.EXIT_TIME) - pl.col(v.ENTRY_TIME)).alias(v.DURATION)
    )
