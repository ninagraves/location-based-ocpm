"""From segments (hu, first and last position) to a visits table with the columns of the maximal visits.

So the mapping set can be passed to everything that takes visits: `visits.maximal.visit_relations`,
`visits.shifts`, `waiting_times.analyse_waiting_times` and the trace figure.
"""

from collections.abc import Iterable

import polars as pl

from ..derivation import columns as c
from ..visits import columns as v
from .sweep import Segment

#: Column of a mapping visit: id of the maximal visit m(p) it lies in.
MAXIMAL_VISIT_ID = "maximal_visit_id"


def segments_frame(segments: Iterable[tuple[str, Segment]]) -> pl.DataFrame:
    """One row per segment, with positions starting at 1.

    Args:
        segments: Pairs (hu, segment).

    Returns:
        pl.DataFrame: Columns hu, high_level, first_position, last_position, maximal_visit_id.
    """
    rows = [
        (hu, s.high_level, s.first + 1, s.last + 1, s.maximal_visit_id) for hu, s in segments
    ]
    return pl.DataFrame(
        rows,
        schema={
            c.HU: pl.String,
            v.HIGH_LEVEL: pl.String,
            v.FIRST_POSITION: pl.Int64,
            v.LAST_POSITION: pl.Int64,
            MAXIMAL_VISIT_ID: pl.Int64,
        },
        orient="row",
    )


def mapping_visits(relations: pl.DataFrame, segments: pl.DataFrame) -> pl.DataFrame:
    """The visits table of a mapping set: one row per segment with the columns of `maximal.maximal_visits`.

    Args:
        relations: Relations with columns hu, event, time, position, high_level (e.g. of
            `derive_maximal_visits`).
        segments: Columns hu, high_level, first_position, last_position (further columns are kept),
            e.g. `segments_frame`.

    Returns:
        pl.DataFrame: visit_id (1, 2, ... in hu and position order), the segment columns, first_event,
        last_event, exit_event, entry_time, last_time, exit_time, ends_trace, duration, n_relations,
        n_at_location, interrupted; sorted by visit_id.
    """
    rel = relations.select(
        c.HU, pl.col(v.POSITION).cast(pl.Int64), c.EVENT, c.TIME, pl.col(v.HIGH_LEVEL).alias("_hl")
    )
    first = rel.select(
        c.HU,
        pl.col(v.POSITION).alias(v.FIRST_POSITION),
        pl.col(c.EVENT).alias(v.FIRST_EVENT),
        pl.col(c.TIME).alias(v.ENTRY_TIME),
    )
    last = rel.select(
        c.HU,
        pl.col(v.POSITION).alias(v.LAST_POSITION),
        pl.col(c.EVENT).alias(v.LAST_EVENT),
        pl.col(c.TIME).alias(v.LAST_TIME),
    )
    after = rel.select(
        c.HU,
        (pl.col(v.POSITION) - 1).alias(v.LAST_POSITION),
        pl.col(c.EVENT).alias("_next_event"),
        pl.col(c.TIME).alias("_next_time"),
    )
    expanded = (
        segments.select(
            c.HU,
            v.FIRST_POSITION,
            v.LAST_POSITION,
            pl.col(v.HIGH_LEVEL).alias("_visit_hl"),
            pl.int_ranges(v.FIRST_POSITION, pl.col(v.LAST_POSITION) + 1).alias(v.POSITION),
        )
        .explode(v.POSITION)
        .with_columns(pl.col(v.POSITION).cast(pl.Int64))
        .join(rel.select(c.HU, v.POSITION, "_hl"), on=[c.HU, v.POSITION])
        .group_by(c.HU, v.FIRST_POSITION)
        .agg(
            pl.len().cast(pl.Int64).alias(v.N_RELATIONS),
            pl.col("_hl").eq_missing(pl.col("_visit_hl")).sum().cast(pl.Int64).alias(v.N_AT_LOCATION),
        )
    )
    return (
        segments.sort(c.HU, v.FIRST_POSITION)
        .with_row_index(v.VISIT_ID, offset=1)
        .with_columns(pl.col(v.VISIT_ID).cast(pl.Int64))
        .join(first, on=[c.HU, v.FIRST_POSITION], how="left")
        .join(last, on=[c.HU, v.LAST_POSITION], how="left")
        .join(after, on=[c.HU, v.LAST_POSITION], how="left")
        .join(expanded, on=[c.HU, v.FIRST_POSITION], how="left")
        .with_columns(
            pl.col("_next_event").is_null().alias(v.ENDS_TRACE),
            pl.col("_next_event").fill_null(pl.col(v.LAST_EVENT)).alias(v.EXIT_EVENT),
            pl.col("_next_time").fill_null(pl.col(v.LAST_TIME)).alias(v.EXIT_TIME),
        )
        .with_columns(
            (pl.col(v.EXIT_TIME) - pl.col(v.ENTRY_TIME)).alias(v.DURATION),
            (pl.col(v.N_RELATIONS) > pl.col(v.N_AT_LOCATION)).alias(v.INTERRUPTED),
        )
        .drop("_next_event", "_next_time")
        .sort(v.VISIT_ID)
    )


#: Column of `visit_sequences`.
SEQUENCE = "sequence"


def visit_sequences(mapping: pl.DataFrame, bottom: str = "⊥") -> pl.DataFrame:
    """The visit sequence of every handling unit as one text, to compare mapping sets at a glance.

    Args:
        mapping: Visits with hu, high_level, first_position, first_event, last_event.
        bottom: Text for ⊥.

    Returns:
        pl.DataFrame: Columns hu, sequence (e.g. "(A e3–e11) (T e13–e14)"), sorted by hu.
    """
    text = pl.format("({} {}–{})", pl.col(v.HIGH_LEVEL).fill_null(bottom), v.FIRST_EVENT, v.LAST_EVENT)
    return (
        mapping.sort(c.HU, v.FIRST_POSITION)
        .group_by(c.HU, maintain_order=True)
        .agg(text.str.join(" ").alias(SEQUENCE))
    )
