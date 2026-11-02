"""All waiting-time results in one call, with or without visits (DD-W6).

Runs the steps of `scopes.py`, `waiting.py` and (optionally) `durations.py` in order.
"""

from collections.abc import Collection
from dataclasses import dataclass

import polars as pl

from ..visits import columns as v
from ..visits.maximal import add_trace_positions
from .durations import NEGATIVE_WAITING_TIME, add_processing_durations
from .scopes import scope_relations, trace_scopes, visit_scopes
from .waiting import (
    add_processing,
    add_storage_removals,
    simultaneous_processing,
    time_pieces,
    waiting_summary,
    waiting_times,
)


@dataclass
class WaitingAnalysis:
    """The results of `analyse_waiting_times` (eager frames).

    Attributes:
        scopes: One row per scope: the visits at hl ∈ HL, or one whole trace per handling unit
            (`scopes.py`).
        scope_relations: One row per scope and relation, with at_location, is_processing_event,
            is_processing and is_storage_removal.
        pieces: One row per timed piece, labelled waiting, storage or remaining (`waiting.time_pieces`).
        waiting_times: The waiting pieces, one per processing operation; with a processing-duration
            attribute also processing_duration, net_waiting_time and negative_waiting_time.
        summary: Per scope: counts, total waiting, storage and remaining time, is_processing_visit
            (`waiting.waiting_summary`); join it to the visits on visit_id.
        simultaneous_processing: Flag (RQ5): processing operations of one handling unit at the same
            timestamp (`waiting.simultaneous_processing`); empty if RQ5 holds.
        negative_waiting_times: Flag (DD-W3): waiting times that become negative after deducting the
            processing duration; empty without a processing-duration attribute.
    """

    scopes: pl.DataFrame
    scope_relations: pl.DataFrame
    pieces: pl.DataFrame
    waiting_times: pl.DataFrame
    summary: pl.DataFrame
    simultaneous_processing: pl.DataFrame
    negative_waiting_times: pl.DataFrame


def analyse_waiting_times(
    relations: pl.DataFrame | pl.LazyFrame,
    location: str = "loc",
    visits: pl.DataFrame | pl.LazyFrame | None = None,
    processing: Collection[str] | None = None,
    storage_units: Collection[str] = (),
    storage_removals_reset: bool = True,
    outside_storage_resets: bool = True,
    zero_wait_at_removal: bool = False,
    skip_simultaneous_removal: bool = False,
    processing_duration: str | None = None,
    duration_unit: str = "s",
) -> WaitingAnalysis:
    """Waiting, storage and remaining times, measured per visit or per whole trace.

    Args:
        relations: One row per hu-event relation with columns hu, event, time, activity, is_movement,
            is_transformation (if `processing` is None) and `location`. With `visits`, the relations the
            visits were derived from, with position and high_level (`VisitAnalysis.relations`); without,
            e.g. a saved level mapping (positions are added by AS4 if missing).
        location: Column of loc (null = ⊥).
        visits: The visits to measure in (e.g. `VisitAnalysis.visits`); None = every whole trace is one
            scope (DD-W6).
        processing: The processing operations P as event ids; None = the transformation events T.
        storage_units: The set W.
        storage_removals_reset: DD-W5. True (default): removals from storage units are clock events;
            False: they are not (only entry and processing operations reset the clock).
        outside_storage_resets: DD-W2. True (default): removals from storage units outside the visit's hl
            (during an excursion) also reset the clock; False: only those inside hl. No effect without
            visits.
        zero_wait_at_removal: DD-W1. False (default): a processing operation that is itself a storage
            removal waits from the previous clock event, incl. the storage time; True: its waiting time
            is 0 and the time before it is storage time.
        skip_simultaneous_removal: DD-W4. False (default): a removal at the same timestamp as the next
            processing operation resets the clock (waiting time 0); True: that removal is skipped and the
            operation waits from the clock event before.
        processing_duration: DD-W3. Event attribute (column of `relations`) with the processing duration,
            deducted from the waiting time of its own operation; None = not used.
        duration_unit: Unit of a numeric `processing_duration`: "s", "min" or "h".

    Returns:
        WaitingAnalysis: All frames, collected.
    """
    names = relations.collect_schema().names()
    if visits is None:
        rel = relations if v.POSITION in names else add_trace_positions(relations, processing)
        scopes = trace_scopes(rel)
    else:
        missing = {v.POSITION, v.HIGH_LEVEL} - set(names)
        if missing:
            raise ValueError(
                f"With visits, `relations` needs the columns {sorted(missing)} of the visit derivation "
                "(use `VisitAnalysis.relations`)."
            )
        rel = relations
        scopes = visit_scopes(visits)
    srel = scope_relations(rel, scopes, location)
    srel = add_processing(srel, processing)
    units = storage_units if storage_removals_reset else ()
    srel = add_storage_removals(srel, units, location, outside_storage_resets)
    pieces = time_pieces(
        srel,
        scopes,
        zero_wait_at_removal=zero_wait_at_removal,
        skip_simultaneous_removal=skip_simultaneous_removal,
        relations=rel,
    )
    waits = waiting_times(pieces)
    if processing_duration is not None:
        waits = add_processing_durations(waits, rel, processing_duration, duration_unit)
        negative = waits.filter(pl.col(NEGATIVE_WAITING_TIME))
    else:
        negative = waits.head(0)
    frames = [
        scopes,
        srel,
        pieces,
        waits,
        waiting_summary(scopes, pieces),
        simultaneous_processing(rel, processing),
        negative,
    ]
    if isinstance(relations, pl.LazyFrame):
        frames = pl.collect_all(frames)
    return WaitingAnalysis(*frames)
