"""Save and load a mapping set V_map as a CSV file.

File format (`visit_mapping_level_{k}_kappa_{κ}_{strategy}.csv`): one row per visit of V_map, sorted by
visit_id; the columns of a maximal visits file (`visits.visit_files.VISIT_SCHEMA`, without kappa) plus
maximal_visit_id. Time in ISO format, booleans as true/false, ⊥ as an empty cell.
"""

from pathlib import Path

import polars as pl

from ..visits import columns as v
from ..visits.visit_files import VISIT_SCHEMA
from .segments import MAXIMAL_VISIT_ID

#: Columns of a mapping file, in this order, with their types.
MAPPING_VISIT_SCHEMA = {
    **{name: dtype for name, dtype in VISIT_SCHEMA.items() if name != v.KAPPA},
    MAXIMAL_VISIT_ID: pl.Int64,
}


def mapping_file_name(level: int, kappa: int, strategy: str) -> str:
    """File name of a mapping set.

    Args:
        level: Location level k.
        kappa: κ_max of the maximal visits.
        strategy: Short strategy key, e.g. "S6" (used as is in the file name).

    Returns:
        str: e.g. "visit_mapping_level_3_kappa_3_S6.csv".
    """
    return f"visit_mapping_level_{level}_kappa_{kappa}_{strategy}.csv"


def save_mapping(mapping: pl.DataFrame, folder: str | Path, level: int, kappa: int, strategy: str) -> Path:
    """Write a mapping set to `folder/visit_mapping_level_{k}_kappa_{κ}_{strategy}.csv`.

    Args:
        mapping: `MappingAnalysis.mapping` (or `segments.mapping_visits`).
        folder: Target folder; created if missing. An existing file is overwritten.
        level: Location level k (file name only).
        kappa: κ_max (file name only).
        strategy: Short strategy key (file name only).

    Returns:
        Path: The written file.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / mapping_file_name(level, kappa, strategy)
    mapping.select(pl.col(name).cast(dtype) for name, dtype in MAPPING_VISIT_SCHEMA.items()).sort(
        v.VISIT_ID
    ).write_csv(path)
    return path


def load_mapping(folder: str | Path, level: int, kappa: int, strategy: str) -> pl.DataFrame:
    """Read a mapping set written by `save_mapping`.

    Args:
        folder: Folder holding the file.
        level: Location level k.
        kappa: κ_max.
        strategy: Short strategy key.

    Returns:
        pl.DataFrame: Columns as in `MAPPING_VISIT_SCHEMA`, plus duration; empty cells are null (⊥).
    """
    mapping = pl.read_csv(Path(folder) / mapping_file_name(level, kappa, strategy), schema=MAPPING_VISIT_SCHEMA)
    return mapping.with_columns((pl.col(v.EXIT_TIME) - pl.col(v.ENTRY_TIME)).alias(v.DURATION))
