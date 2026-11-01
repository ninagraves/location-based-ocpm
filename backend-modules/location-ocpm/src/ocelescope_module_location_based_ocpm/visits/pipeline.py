"""All visit results in one call: maximal visits, stops, transfers and shifts, waiting times.

Runs the steps of `maximal.py`, `shifts.py` and `waiting.py` in order and joins the per-visit summaries
into one visits table.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass

import polars as pl

from . import columns as v
from .maximal import derive_maximal_visits, visit_relations
from .order import add_waiting_positions
from .shifts import add_stops, shift_summary, transfers
from .waiting import add_processing, add_storage_removals, time_pieces, waiting_summary, waiting_times


@dataclass
class VisitAnalysis:
    """The results of `analyse_visits` (eager frames).

    Attributes:
        relations: One row per hu-event relation with tie_rank, position, waiting_position, high_level,
            kappa, gap, starts_visit and visit_id (the maximal visit at the relation's own high-level location).
        visits: One row per maximal visit: the columns of `maximal.maximal_visits`, then those of
            `shifts.shift_summary` and `waiting.waiting_summary`.
        visit_relations: One row per visit and relation r ∈ R(ν), with at_location, on_vehicle, is_stop,
            is_processing_event, is_processing and is_storage_removal.
        transfers: One row per transfer μ_j (`shifts.transfers`).
        pieces: One row per timed piece of a visit, labelled waiting, storage or remaining
            (`waiting.time_pieces`).
        waiting_times: The waiting pieces, one per processing operation (`waiting.waiting_times`).
    """

    relations: pl.DataFrame
    visits: pl.DataFrame
    visit_relations: pl.DataFrame
    transfers: pl.DataFrame
    pieces: pl.DataFrame
    waiting_times: pl.DataFrame


def analyse_visits(
    relations: pl.DataFrame | pl.LazyFrame,
    location: str = "loc",
    agg: Mapping[str, str] | None = None,
    vehicles: Collection[str] = (),
    kappa: int = 0,
    processing: Collection[str] | None = None,
    ignore_vehicles: bool = False,
    storage_units: Collection[str] = (),
    zero_wait_at_removal: bool = False,
    outside_storage_resets: bool = True,
) -> VisitAnalysis:
    """Maximal visits with their shifts and waiting times, in one call.

    Args:
        relations: One row per hu-event relation with columns hu, event, time, is_movement,
            is_transformation (needed if `processing` is None) and `location`, e.g. a saved level mapping or `Derivation.relations`.
        location: Column of the current location loc (null = ⊥).
        agg: Location mapping L -> HL (partial, completed by identity); None = identity.
        vehicles: The set V.
        kappa: κ_max, the excursion tolerance of every high-level location (κ(⊥) = 0).
        processing: The processing operations P as event ids; None = the transformation events T. Also
            orders events with the same timestamp (AS4: movements, then processing operations, then the
            rest), so trace positions and visits follow AS4; waiting times use the waiting-time order
            (processing operations before movements, `order.add_waiting_positions`).
        ignore_vehicles: True = relations on a vehicle do not count towards the tolerance κ, even if the
            vehicle maps to another high-level location (`maximal.add_gaps`); default False.
        storage_units: The set W; a removal from a storage unit restarts the clock of the waiting times
            (`waiting.add_storage_removals`); empty = no removals.
        zero_wait_at_removal: False (default, concept): a processing operation that is itself a storage
            removal waits from the previous clock event, incl. the storage time; True: its waiting time is
            0 and the time before it is storage time (`waiting.time_pieces`).
        outside_storage_resets: True (default, concept): removals from storage units outside the visit's
            high-level location (during an excursion) also reset the clock; False: only those inside it.

    Returns:
        VisitAnalysis: All frames, collected.
    """
    rel, visits = derive_maximal_visits(
        relations, location, agg, kappa, vehicles, ignore_vehicles, processing
    )
    rel = add_waiting_positions(rel, processing)
    vrel = visit_relations(rel, visits)
    vrel = add_stops(vrel, vehicles, location)
    vrel = add_processing(vrel, processing)
    vrel = add_storage_removals(vrel, storage_units, location, outside_storage_resets)
    transfer_frame = transfers(vrel, location)
    pieces = time_pieces(vrel, visits, zero_wait_at_removal=zero_wait_at_removal)
    summary = visits.join(shift_summary(vrel, transfer_frame, location), on=v.VISIT_ID).join(
        waiting_summary(visits, pieces), on=v.VISIT_ID
    )
    frames = [rel, summary.sort(v.VISIT_ID), vrel, transfer_frame, pieces, waiting_times(pieces)]
    if isinstance(relations, pl.LazyFrame):
        frames = pl.collect_all(frames)
    return VisitAnalysis(*frames)
