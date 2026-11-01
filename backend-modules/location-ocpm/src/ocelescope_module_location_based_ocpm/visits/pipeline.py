"""All visit results in one call: maximal visits, stops, transfers and shifts.

Runs the steps of `maximal.py` and `shifts.py` in order and joins the per-visit shift summary into one
visits table. Waiting times are computed separately (`waiting_times.pipeline.analyse_waiting_times`, with
these visits or without visits).
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import timedelta

import polars as pl

from . import columns as v
from .context import naming_clashes
from .maximal import derive_maximal_visits, visit_relations
from .shifts import add_stops, shift_summary, transfers


@dataclass
class VisitAnalysis:
    """The results of `analyse_visits` (eager frames).

    Attributes:
        relations: One row per hu-event relation with tie_rank, position, high_level, kappa, gap,
            gap_timestamps, gap_duration, starts_visit and visit_id (the maximal visit at the relation's
            own high-level location).
        visits: One row per maximal visit: the columns of `maximal.maximal_visits`, then those of
            `shifts.shift_summary`.
        visit_relations: One row per visit and relation r ∈ R(ν), with at_location, on_vehicle and is_stop.
        transfers: One row per transfer μ_j (`shifts.transfers`).
        naming_clashes: Flag: unmapped locations whose name is also a provided high-level location
            (`context.naming_clashes`); empty if there are none.
    """

    relations: pl.DataFrame
    visits: pl.DataFrame
    visit_relations: pl.DataFrame
    transfers: pl.DataFrame
    naming_clashes: pl.DataFrame


def analyse_visits(
    relations: pl.DataFrame | pl.LazyFrame,
    location: str = "loc",
    agg: Mapping[str, str] | None = None,
    vehicles: Collection[str] = (),
    kappa: int | None = 0,
    processing: Collection[str] | None = None,
    ignore_vehicles: bool = False,
    max_timestamps: int | None = None,
    max_excursion_duration: timedelta | None = None,
    vehicles_outside_external: bool = False,
) -> VisitAnalysis:
    """Maximal visits with their stops, transfers and shifts, in one call.

    Args:
        relations: One row per hu-event relation with columns hu, event, time, is_movement,
            is_transformation (needed if `processing` is None) and `location`, e.g. a saved level mapping
            or `Derivation.relations`.
        location: Column of the current location loc (null = ⊥).
        agg: Location mapping L -> HL (partial, completed by identity); None = identity.
        vehicles: The set V.
        kappa: κ_max, the maximum number of events of a deviating infix (κ(⊥) = 0); None = no limit (DD-V1).
        processing: The processing operations P as event ids, only used to order events with the same
            timestamp (AS4: movements, then processing operations, then the rest); None = the
            transformation events T. Use the same P for the waiting times.
        ignore_vehicles: DD-V2. True = relations on a vehicle do not count towards κ, even if the vehicle
            maps to another high-level location (`maximal.add_gaps`); default False.
        max_timestamps: DD-V1. Maximum number of distinct timestamps of a deviating infix; None = off.
        max_excursion_duration: DD-V1. Maximum duration of a deviating infix (its first event until the first
            event back at hl); None = off.
        vehicles_outside_external: DD-S1. True = a transfer with a relation outside hl is an external shift,
            also if it is only on vehicles; default False (`shifts.transfer_category`).

    Returns:
        VisitAnalysis: All frames, collected.
    """
    rel, visits = derive_maximal_visits(
        relations,
        location,
        agg,
        kappa,
        vehicles,
        ignore_vehicles,
        processing,
        max_timestamps=max_timestamps,
        max_excursion_duration=max_excursion_duration,
    )
    vrel = add_stops(visit_relations(rel, visits), vehicles, location)
    transfer_frame = transfers(vrel, location, vehicles_outside_external)
    summary = visits.join(shift_summary(vrel, transfer_frame, location), on=v.VISIT_ID)
    frames = [rel, summary.sort(v.VISIT_ID), vrel, transfer_frame]
    if isinstance(relations, pl.LazyFrame):
        frames = pl.collect_all(frames)
        locations = relations.select(pl.col(location).drop_nulls().unique()).collect()
    else:
        locations = relations.select(pl.col(location).drop_nulls().unique())
    clashes = naming_clashes(locations.to_series().to_list(), agg)
    return VisitAnalysis(*frames, clashes)
