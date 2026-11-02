"""From segments (hu, first and last position) to a visits table with the columns of the maximal visits.

So the mapping set can be passed to everything that takes visits: `visits.maximal.visit_relations`,
`visits.shifts`, `waiting_times.analyse_waiting_times` and the trace figure.
"""

from collections.abc import Iterable

import polars as pl

from ..derivation import columns as c
from ..visits import columns as v
from ..visits.maximal import visit_table
from .sweep import Segment

#: Column of a mapping visit: id of the maximal visit m(i) it lies in.
MAXIMAL_VISIT_ID = "maximal_visit_id"


def segments_frame(segments: Iterable[tuple[str, Segment]]) -> pl.DataFrame:
    """One row per segment, with positions starting at 1.

    Args:
        segments: Pairs (hu, segment).

    Returns:
        pl.DataFrame: Columns hu, high_level, first_position, last_position, maximal_visit_id.
    """
    rows = [
        (hu, s.high_level, s.first + 1, s.last + 1, s.maximal_visit_id)
        for hu, s in segments
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
    """The visits table of a mapping set: one row per segment with the columns of `maximal.maximal_visits`
    (built by the same `maximal.visit_table`).

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
    return visit_table(segments, relations)


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
    text = pl.format(
        "({} {}–{})",
        pl.col(v.HIGH_LEVEL).fill_null(bottom),
        v.FIRST_EVENT,
        v.LAST_EVENT,
    )
    return (
        mapping.sort(c.HU, v.FIRST_POSITION)
        .group_by(c.HU, maintain_order=True)
        .agg(text.str.join(" ").alias(SEQUENCE))
    )
