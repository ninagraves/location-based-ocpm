"""Optional processing durations (DD-W3 in `overview/concepts/Visit Mappings.md`).

Timestamps are completion times, so a waiting time w(σ[c[l]]) also contains the processing time of the
operation σ[c[l]] itself (we do not know when it started). If an event attribute holds the processing
duration, it is deducted from the waiting time of that same operation (not of the previous one):
net waiting time = waiting time - processing duration. A negative result (the duration is longer than the
time since the last clock event) is flagged, not corrected.
"""

import polars as pl

from ..derivation import columns as c
from ..visits.context import Frame
from .waiting import END_EVENT, PIECE_DURATION

#: Columns added to the waiting times.
PROCESSING_DURATION = "processing_duration"
NET_WAITING_TIME = "net_waiting_time"
NEGATIVE_WAITING_TIME = "negative_waiting_time"

#: Units of a numeric duration column.
UNITS = {"s": 1, "min": 60, "h": 3600}


def duration_expression(column: str, unit: str = "s") -> pl.Expr:
    """A numeric processing duration as a polars duration (duration columns are cast directly in
    `add_processing_durations`).

    Args:
        column: Event attribute (column) with the processing duration as a number in `unit`.
        unit: Unit of the column: "s", "min" or "h".

    Returns:
        pl.Expr: Expression named processing_duration.
    """
    if unit not in UNITS:
        raise ValueError(f"Unknown unit {unit!r}; use one of {sorted(UNITS)}.")
    col = pl.col(column)
    return (col.cast(pl.Float64) * UNITS[unit] * 1_000_000).cast(pl.Int64).cast(pl.Duration("us")).alias(
        PROCESSING_DURATION
    )


def add_processing_durations(
    waiting: Frame, events: Frame, column: str, unit: str = "s"
) -> Frame:
    """Deduct the processing duration of each processing operation from its own waiting time.

    Args:
        waiting: Output of `waiting.waiting_times` (end_event = the processing operation).
        events: Frame with the columns event and `column` (one value per event, e.g. the relations or the
            event table).
        column: Event attribute with the processing duration (duration type, or a number in `unit`).
        unit: Unit of a numeric `column`: "s" (default), "min" or "h".

    Returns:
        Frame: `waiting` with the columns processing_duration (null if the event has no value),
        net_waiting_time (waiting time minus processing duration; the waiting time if the duration is
        missing) and negative_waiting_time (true if net_waiting_time < 0).
    """
    schema = events.collect_schema()
    if c.EVENT not in schema.names():
        raise ValueError("`events` needs the column event.")
    if schema[column].is_temporal():
        value = pl.col(column).cast(pl.Duration("us")).alias(PROCESSING_DURATION)
    else:
        value = duration_expression(column, unit)
    durations = events.select(pl.col(c.EVENT).alias(END_EVENT), value).unique(END_EVENT)
    zero = pl.col(PIECE_DURATION) - pl.col(PIECE_DURATION)
    net = pl.col(PIECE_DURATION) - pl.col(PROCESSING_DURATION).fill_null(zero)
    return (
        waiting.join(durations, on=END_EVENT, how="left")
        .with_columns(net.alias(NET_WAITING_TIME))
        .with_columns((pl.col(NET_WAITING_TIME) < zero).alias(NEGATIVE_WAITING_TIME))
    )
