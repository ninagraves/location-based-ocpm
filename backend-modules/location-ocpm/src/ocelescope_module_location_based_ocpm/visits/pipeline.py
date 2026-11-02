"""All visit results in one call, for the maximal visits or for ANY set of visits (e.g. a mapping set).

- `analyse_visit_set(relations, visits, ...)`: everything that is defined for a set of visits: properties
  (kinds, trivial, contained, overlapping, excursions), the set properties and metrics, stops, transfers and
  shifts, dwell times and time spent at locations, the transfer and processing aggregations, optionally the
  waiting times, and one overview row per visit.
- `analyse_visits(relations, ...)`: derives the maximal visits V_max first and then runs
  `analyse_visit_set` on them.
For a mapping set use `visit_mapping.pipeline.analyse_mapping`, which passes the mapping to
`analyse_visit_set`.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import timedelta

import polars as pl

from ..waiting_times.pipeline import WaitingAnalysis, analyse_waiting_times
from . import columns as v
from .context import naming_clashes
from .dwell import add_dwell_times, time_inside_outside, time_spent
from .excursions import excursions
from .maximal import derive_maximal_visits, visit_relations, visit_table
from .order import processing_flag
from .overview import (
    processing_statistics,
    transfer_relations,
    transfer_statistics,
    transfer_targets,
    visit_overview,
)
from .properties import (
    rq4_violations,
    set_metrics,
    set_properties,
    visit_pairs,
    visit_properties,
    with_positions,
)
from .shifts import add_stops, shift_summary, transfers
from .visit_location import agreement_changes, agreement_metrics


@dataclass
class VisitAnalysis:
    """The results of `analyse_visits` / `analyse_visit_set` (eager frames).

    Attributes:
        relations: One row per hu-event relation with position and high_level (for `analyse_visits` also
            tie_rank, kappa, gap, gap_timestamps, gap_duration, starts_visit and visit_id, the maximal visit at
            the relation's own high-level location).
        visits: One row per visit: the columns of `maximal.visit_table`, the properties
            (`properties.visit_properties`) and the shift summary (`shifts.shift_summary`).
        visit_relations: One row per visit and relation r ∈ R(ν), with at_location, on_vehicle, is_stop,
            is_processing_event and dwell_time.
        transfers: One row per transfer μ_j (`shifts.transfers`).
        naming_clashes: Flag: unmapped locations whose name is also a provided high-level location
            (`context.naming_clashes`); empty if there are none.
        excursions: One row per excursion (`excursions.excursions`).
        pairs: Contained and overlapping pairs of visits (`properties.visit_pairs`).
        set_properties: Per handling unit: disjoint, hl-disjoint, covering (`properties.set_properties`).
        set_metrics: One row with the set metrics (`properties.set_metrics`).
        set_metrics_per_hu: The same per handling unit.
        time_at_locations: Per visit and low-level location: time spent there (`dwell.time_spent`).
        time_at_high_levels: Per visit and high-level location: time spent there.
        transfer_statistics: Per visit and transfer category (`overview.transfer_statistics`).
        transfer_targets: Per visit, category and vehicle / external hl (`overview.transfer_targets`).
        waiting: The waiting-time results on these visits (`waiting_times.pipeline.analyse_waiting_times`);
            None if not computed.
        processing_statistics: Per visit and processing activity (`overview.processing_statistics`); empty
            without waiting times.
        overview: One row per visit with all overview columns (`overview.visit_overview`).
        rq4_violations: Flag (RQ4): relations of a handling unit with the same timestamp at different
            high-level locations (`properties.rq4_violations`); empty if RQ4 holds.
        agreement: One row per event: agreement under \\hat{hl} and under the visit mapping vl_V, and its
            change (`visit_location.agreement_changes`); None if the set is not disjoint and covering (e.g. V_max).
        agreement_metrics: One row with p^e_agr, N^e_agr,lost, N^e_agr,gain (`visit_location.agreement_metrics`);
            None like `agreement`.
    """

    relations: pl.DataFrame
    visits: pl.DataFrame
    visit_relations: pl.DataFrame
    transfers: pl.DataFrame
    naming_clashes: pl.DataFrame
    excursions: pl.DataFrame
    pairs: pl.DataFrame
    set_properties: pl.DataFrame
    set_metrics: pl.DataFrame
    set_metrics_per_hu: pl.DataFrame
    time_at_locations: pl.DataFrame
    time_at_high_levels: pl.DataFrame
    transfer_statistics: pl.DataFrame
    transfer_targets: pl.DataFrame
    waiting: WaitingAnalysis | None
    processing_statistics: pl.DataFrame
    overview: pl.DataFrame
    rq4_violations: pl.DataFrame
    agreement: pl.DataFrame | None = None
    agreement_metrics: pl.DataFrame | None = None


def analyse_visit_set(
    relations: pl.DataFrame | pl.LazyFrame,
    visits: pl.DataFrame | pl.LazyFrame,
    location: str = "loc",
    vehicles: Collection[str] = (),
    processing: Collection[str] | None = None,
    storage_units: Collection[str] = (),
    vehicles_outside_external: bool = False,
    with_waiting_times: bool = True,
    agg: Mapping[str, str] | None = None,
    **waiting_options,
) -> VisitAnalysis:
    """Everything defined for a set of visits, for any set: V_max, a mapping set or a hand-written one.

    Args:
        relations: The relations with position and high_level, e.g. `VisitAnalysis.relations` or
            `visit_mapping.pipeline.MappingAnalysis.relations` (columns hu, event, time, activity,
            `location`, and is_transformation if `processing` is None).
        visits: The visits: hu, high_level and first/last position or first/last event, optionally
            visit_id (further columns are kept); e.g. `MappingAnalysis.mapping`.
        location: Column of loc.
        vehicles: The set V.
        processing: The processing operations P as event ids; None = the transformation events T.
        storage_units: The set W (for the waiting times).
        vehicles_outside_external: DD-S1 (`shifts.transfer_category`); default False.
        with_waiting_times: Also compute the waiting times on these visits (default True).
        agg: Location mapping, only for the naming-clash flag.
        **waiting_options: Further options of `waiting_times.pipeline.analyse_waiting_times` (e.g.
            storage_removals_reset, zero_wait_at_removal, processing_duration).

    Returns:
        VisitAnalysis: All frames, collected.
    """
    rel = relations.collect() if isinstance(relations, pl.LazyFrame) else relations
    given = visits.collect() if isinstance(visits, pl.LazyFrame) else visits
    given = with_positions(given, rel)
    extra = [
        col
        for col in given.columns
        if col
        not in (v.VISIT_ID, "hu", v.HIGH_LEVEL, v.FIRST_POSITION, v.LAST_POSITION)
    ]
    keep = [col for col in extra if col in ("kappa", "maximal_visit_id")]
    table = visit_table(
        given.select(
            v.VISIT_ID, "hu", v.HIGH_LEVEL, *keep, v.FIRST_POSITION, v.LAST_POSITION
        ),
        rel,
    )
    rel_p = rel.with_columns(processing_flag(processing).alias(v.IS_PROCESSING_EVENT))
    vrel = add_stops(visit_relations(rel_p, table), vehicles, location)
    vrel = add_dwell_times(vrel, table)
    found = excursions(vrel)
    pairs = visit_pairs(table)
    props = visit_properties(table, vrel, found, location)
    transfer_frame = transfers(vrel, location, vehicles_outside_external)
    with_shifts = props.join(
        shift_summary(vrel, transfer_frame, location), on=v.VISIT_ID, how="left"
    )
    statistics = transfer_statistics(transfer_frame)
    targets = transfer_targets(transfer_relations(vrel, transfer_frame), location)
    inside = time_inside_outside(vrel, table)
    waiting = None
    if with_waiting_times:
        waiting = analyse_waiting_times(
            rel,
            location,
            table,
            processing=processing,
            storage_units=storage_units,
            **waiting_options,
        )
        per_activity = processing_statistics(waiting.waiting_times)
    else:
        per_activity = pl.DataFrame(
            schema={
                v.VISIT_ID: pl.Int64,
                "activity": pl.String,
                "n_operations": pl.Int64,
            }
        )
    overview = visit_overview(
        with_shifts,
        inside,
        statistics,
        waiting.summary if waiting is not None else None,
        per_activity if waiting is not None else None,
    )
    try:
        agreement = agreement_changes(rel, table)
    except ValueError:  # vl_V is only defined for disjoint and covering sets
        agreement = None
    locations = rel.select(pl.col(location).drop_nulls().unique()).to_series().to_list()
    return VisitAnalysis(
        relations=rel,
        visits=with_shifts.sort(v.VISIT_ID),
        visit_relations=vrel,
        transfers=transfer_frame,
        naming_clashes=naming_clashes(locations, agg),
        excursions=found,
        pairs=pairs,
        set_properties=set_properties(table, vrel, rel, pairs),
        set_metrics=set_metrics(table, vrel, rel),
        set_metrics_per_hu=set_metrics(table, vrel, rel, by_hu=True),
        time_at_locations=time_spent(vrel, location),
        time_at_high_levels=time_spent(vrel, v.HIGH_LEVEL),
        transfer_statistics=statistics,
        transfer_targets=targets,
        waiting=waiting,
        processing_statistics=per_activity,
        overview=overview,
        rq4_violations=rq4_violations(rel),
        agreement=agreement,
        agreement_metrics=agreement_metrics(agreement)
        if agreement is not None
        else None,
    )


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
    storage_units: Collection[str] = (),
    with_waiting_times: bool = True,
    **waiting_options,
) -> VisitAnalysis:
    """Maximal visits V_max with everything of `analyse_visit_set`, in one call.

    Args:
        relations: One row per hu-event relation with columns hu, event, time, activity, is_movement,
            is_transformation (needed if `processing` is None) and `location`, e.g. a saved level mapping
            or `Derivation.relations`.
        location: Column of the current location loc (null = ⊥).
        agg: Location mapping L -> HL (partial, completed by identity); None = identity.
        vehicles: The set V.
        kappa: κ_max, the maximum number of events of a deviating infix (κ(⊥) = 0); None = no limit (DD-V1).
        processing: The processing operations P as event ids, used for the AS4 order of equal timestamps,
            the processing counts and the waiting times; None = the transformation events T.
        ignore_vehicles: DD-V2. True = relations on a vehicle do not count towards κ, even if the vehicle
            maps to another high-level location (`maximal.add_gaps`); default False.
        max_timestamps: DD-V1. Maximum number of distinct timestamps of a deviating infix; None = off.
        max_excursion_duration: DD-V1. Maximum duration of a deviating infix (its first event until the first
            event back at hl); None = off.
        vehicles_outside_external: DD-S1. True = a transfer with a relation outside hl is an external shift,
            also if it is only on vehicles; default False (`shifts.transfer_category`).
        storage_units: The set W (for the waiting times).
        with_waiting_times: Also compute the waiting times (default True).
        **waiting_options: Further options of `waiting_times.pipeline.analyse_waiting_times`.

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
    if isinstance(rel, pl.LazyFrame):
        rel, visits = pl.collect_all([rel, visits])
    return analyse_visit_set(
        rel,
        visits,
        location,
        vehicles,
        processing,
        storage_units,
        vehicles_outside_external,
        with_waiting_times,
        agg,
        **waiting_options,
    )
