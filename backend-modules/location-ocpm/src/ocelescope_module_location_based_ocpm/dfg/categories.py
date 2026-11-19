"""Step 1a: the event categories of the page's toolbar (Nina, 2026-11-15).

Five categories of events, all selected by default; deselecting one removes the events of that category from the
traces (projection, as the activity selection in `projection.py`), before anything else:

| Key | Label | Events |
|---|---|---|
| `movement` | Movements | $M$ |
| `to_vehicle` | Move to vehicle | $e \\in M$ with target location $uloc(e) \\in V$ |
| `to_storage` | Move to storage | $e \\in M$ with $uloc(e) \\in W$ |
| `processing` | Processing | $P$ |
| `transformation` | Transforming | $T$ |

The categories overlap ("Move to vehicle" and "Move to storage" are movements; $P$ may contain transformation events):
an event is removed only if **all** its categories are deselected (Nina, 2026-11-15). Events in no category are
always kept.
Example: a "load truck" event (uloc = truck, a vehicle) is in Movements and Move to vehicle. Deselecting only one of
them keeps it; deselecting both removes it. A "crane move" to a gate is only in Movements: deselecting Movements
removes it.
"""

from __future__ import annotations

from collections.abc import Collection

import polars as pl

from ..derivation import columns as c
from . import columns as d

MOVEMENT = "movement"
TO_VEHICLE = "to_vehicle"
TO_STORAGE = "to_storage"
PROCESSING = "processing"
TRANSFORMATION = "transformation"
#: Category key -> label, in the order of the toolbar.
CATEGORIES: dict[str, str] = {
    MOVEMENT: "Movements",
    TO_VEHICLE: "Move to vehicle",
    TO_STORAGE: "Move to storage",
    PROCESSING: "Processing",
    TRANSFORMATION: "Transforming",
}
#: Categories deselected by default (Nina, 2026-11-16: Move to vehicle / storage; 2026-11-19: all movements). As an
#: event stays while any of its categories is selected, this removes the movements that are not also processing
#: operations or transformations.
DEFAULT_EXCLUDED: tuple[str, ...] = (MOVEMENT, TO_VEHICLE, TO_STORAGE)


def event_categories(events: pl.DataFrame, vehicles: Collection[str], storage_units: Collection[str]) -> pl.DataFrame:
    """The categories of every event.

    Args:
        events: Events with columns event, is_movement, is_transformation, is_processing and uloc (target location;
            null = not provided).
        vehicles: The vehicles V (locations).
        storage_units: The storage units W (locations).

    Returns:
        pl.DataFrame: Column event and one boolean column per key of `CATEGORIES`.
    """
    movement = pl.col(c.IS_MOVEMENT).fill_null(False)
    return events.select(
        c.EVENT,
        movement.alias(MOVEMENT),
        (movement & pl.col(c.ULOC).is_in(list(vehicles)).fill_null(False)).alias(TO_VEHICLE),
        (movement & pl.col(c.ULOC).is_in(list(storage_units)).fill_null(False)).alias(TO_STORAGE),
        pl.col(c.IS_PROCESSING).fill_null(False).alias(PROCESSING),
        pl.col(c.IS_TRANSFORMATION).fill_null(False).alias(TRANSFORMATION),
    )


def category_counts(categories: pl.DataFrame) -> dict[str, int]:
    """Number of events per category.

    Args:
        categories: `event_categories`.

    Returns:
        dict[str, int]: Category key -> events of the log in it.
    """
    row = categories.select(pl.col(k).sum() for k in CATEGORIES).row(0, named=True)
    return {k: int(v or 0) for k, v in row.items()}


def remove_categories(traces: pl.DataFrame, categories: pl.DataFrame, excluded: Collection[str]) -> pl.DataFrame:
    """Remove the events whose categories are all deselected from the traces (projection).

    Args:
        traces: Object traces (`traces.object_traces`), sorted by object and position.
        categories: `event_categories`.
        excluded: Deselected category keys.

    Returns:
        pl.DataFrame: The kept rows, same columns and order, with `position` renumbered from 1 per object.
    """
    excluded = [k for k in excluded if k in CATEGORIES]
    if not excluded:
        return traces
    selected = [k for k in CATEGORIES if k not in excluded]
    in_any = pl.any_horizontal(pl.col(k) for k in CATEGORIES)
    in_selected = pl.any_horizontal(pl.col(k) for k in selected) if selected else pl.lit(False)
    removed = categories.filter(in_any & ~in_selected).select(c.EVENT)
    return (
        traces.join(removed, on=c.EVENT, how="anti", maintain_order="left")
        .with_columns(pl.int_range(1, pl.len() + 1, dtype=pl.UInt32).over(d.OBJECT).alias(d.POSITION))
    )


def grouped_category_counts(categories: pl.DataFrame, rows: pl.DataFrame, by: Collection[str]) -> pl.DataFrame:
    """Number of events per category within groups, e.g. per activity or per object type and activity.

    Args:
        categories: `event_categories`.
        rows: Column event and the columns `by`; each event at most once per group.
        by: The group columns.

    Returns:
        pl.DataFrame: The columns `by` and one count column per key of `CATEGORIES` (groups without any categorised
        event are left out).
    """
    return (
        rows.lazy()
        .join(categories.lazy(), on=c.EVENT)
        .group_by(list(by))
        .agg(pl.col(k).sum().cast(pl.Int64) for k in CATEGORIES)
        .filter(pl.any_horizontal(pl.col(k) > 0 for k in CATEGORIES))
        .collect()
    )


def counts_by_group(counts: pl.DataFrame, by: Collection[str]) -> dict[tuple, dict[str, int]]:
    """`grouped_category_counts` as a dictionary, with only the non-zero categories.

    Args:
        counts: `grouped_category_counts`.
        by: Its group columns.

    Returns:
        dict[tuple, dict[str, int]]: Group values -> category key -> events, e.g. {("load",): {"movement": 9}}.
    """
    return {
        tuple(row[b] for b in by): {k: row[k] for k in CATEGORIES if row[k]} for row in counts.iter_rows(named=True)
    }
