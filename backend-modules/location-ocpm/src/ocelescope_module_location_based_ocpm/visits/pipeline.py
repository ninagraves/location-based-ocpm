"""All visit results in one call: maximal visits, stops, transfers and shifts, waiting times.

Runs the steps of `maximal.py`, `shifts.py` and `waiting.py` in order and joins the per-visit summaries
into one visits table.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass

import polars as pl

from . import columns as v
from .maximal import derive_maximal_visits, visit_relations
from .shifts import add_stops, shift_summary, transfers
from .waiting import add_processing, waiting_summary, waiting_times


@dataclass
class VisitAnalysis:
    """The results of `analyse_visits` (eager frames).

    Attributes:
        relations: One row per hu-event relation with high_level, position, kappa, gap, starts_visit and
            visit_id (the maximal visit at the relation's own high-level location).
        visits: One row per maximal visit: the columns of `maximal.maximal_visits`, then those of
            `shifts.shift_summary` and `waiting.waiting_summary`.
        visit_relations: One row per visit and relation r ∈ R(ν), with at_location, on_vehicle, is_stop,
            is_processing_event and is_processing.
        transfers: One row per transfer μ_j (`shifts.transfers`).
        waiting_times: One row per processing position q_j (`waiting.waiting_times`).
    """

    relations: pl.DataFrame
    visits: pl.DataFrame
    visit_relations: pl.DataFrame
    transfers: pl.DataFrame
    waiting_times: pl.DataFrame


def analyse_visits(
    relations: pl.DataFrame | pl.LazyFrame,
    location: str = "loc",
    agg: Mapping[str, str] | None = None,
    vehicles: Collection[str] = (),
    kappa: int = 0,
    processing: Collection[str] | None = None,
    ignore_vehicles: bool = False,
) -> VisitAnalysis:
    """Maximal visits with their shifts and waiting times, in one call.

    Args:
        relations: One row per hu-event relation with columns hu, event, time, is_transformation (needed
            if `processing` is None) and `location`, e.g. a saved level mapping or `Derivation.relations`.
        location: Column of the current location loc (null = ⊥).
        agg: Location mapping L -> HL (partial, completed by identity); None = identity.
        vehicles: The set V.
        kappa: κ_max, the excursion tolerance of every high-level location (κ(⊥) = 0).
        processing: The processing operations P as event ids; None = the transformation events T.
        ignore_vehicles: True = relations on a vehicle do not count towards the tolerance κ, even if the
            vehicle maps to another high-level location (`maximal.add_gaps`); default False.

    Returns:
        VisitAnalysis: All frames, collected.
    """
    rel, visits = derive_maximal_visits(relations, location, agg, kappa, vehicles, ignore_vehicles)
    vrel = visit_relations(rel, visits)
    vrel = add_stops(vrel, vehicles, location)
    vrel = add_processing(vrel, processing)
    transfer_frame = transfers(vrel, location)
    waiting = waiting_times(vrel)
    summary = visits.join(shift_summary(vrel, transfer_frame, location), on=v.VISIT_ID).join(
        waiting_summary(visits, waiting), on=v.VISIT_ID
    )
    frames = [rel, summary.sort(v.VISIT_ID), vrel, transfer_frame, waiting]
    if isinstance(relations, pl.LazyFrame):
        frames = pl.collect_all(frames)
    return VisitAnalysis(*frames)
