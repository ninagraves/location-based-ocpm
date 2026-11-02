"""Mapping sets in one call: maximal visits, then one strategy per trace, then the visits table and the
evaluation metrics (`derive_mapping_set`); a comparison of several strategies (`compare_strategies`); and
shifts, waiting times and the visit overview on a mapping set (`analyse_mapping`)."""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

import polars as pl

from ..visits.maximal import derive_maximal_visits
from ..visits.pipeline import VisitAnalysis, analyse_visit_set
from .metrics import MappingMetrics, mapping_metrics
from .segments import mapping_visits, segments_frame
from .strategies import StrategyLike, segment_trace, strategy_name
from .traces import add_mapping_inputs, split_traces, storage_high_levels

#: Column of the comparison table: the strategy's name.
STRATEGY = "strategy"


@dataclass
class MappingAnalysis:
    """The results of `derive_mapping_set` (eager frames).

    Attributes:
        relations: The relations of the maximal visits (`derive_maximal_visits`) with on_vehicle and
            is_processing_event.
        maximal_visits: V_max.
        mapping: V_map: one row per visit with the columns of the maximal visits plus maximal_visit_id.
        metrics: Evaluation metrics of V_map (`metrics.mapping_metrics`).
        strategy: Name of the strategy.
    """

    relations: pl.DataFrame
    maximal_visits: pl.DataFrame
    mapping: pl.DataFrame
    metrics: MappingMetrics
    strategy: str


def map_traces(
    relations: pl.DataFrame,
    maximal_visits: pl.DataFrame,
    strategy: StrategyLike = "S6",
    location: str = "loc",
    handling_units: Collection[str] | None = None,
    storage_high_levels: Collection[str] = (),
) -> pl.DataFrame:
    """Apply a strategy to every trace and return the segments.

    Args:
        relations: Output of `traces.add_mapping_inputs` on the relations of `derive_maximal_visits`.
        maximal_visits: The maximal visits.
        strategy: A key of `strategies.STRATEGIES`, a local rule, or a strategy object.
        location: Column of loc.
        handling_units: Only these handling units; None = all.
        storage_high_levels: High-level locations containing a storage unit (for the storage tie-break).

    Returns:
        pl.DataFrame: `segments.segments_frame` (hu, high_level, first_position, last_position,
        maximal_visit_id).
    """
    traces = split_traces(
        relations, maximal_visits, location, handling_units, storage_high_levels
    )
    return segments_frame((t.hu, s) for t in traces for s in segment_trace(t, strategy))


def derive_mapping_set(
    relations: pl.DataFrame | pl.LazyFrame,
    location: str = "loc",
    agg: Mapping[str, str] | None = None,
    vehicles: Collection[str] = (),
    kappa: int | None = 0,
    processing: Collection[str] | None = None,
    strategy: StrategyLike = "S6",
    storage_units: Collection[str] = (),
    ignore_vehicles: bool = False,
    trivial_excludes_connecting: bool = True,
) -> MappingAnalysis:
    """V_max and V_map with its evaluation metrics, in one call.

    Args:
        relations: One row per hu-event relation (as for `visits.pipeline.analyse_visits`).
        location: Column of loc (null = ⊥).
        agg: Location mapping L -> HL (partial, completed by identity); None = identity.
        vehicles: The set V.
        kappa: κ_max (see `derive_maximal_visits`).
        processing: The processing operations P as event ids (AS4 order, strategies, metrics); None = T.
        strategy: A key of `strategies.STRATEGIES` ("S1" to "S6"; default "S6"), a local rule, or a
            strategy object (custom: `optimal.lexicographic`, `optimal.weighted`).
        storage_units: The set W; only used by the storage tie-break of S6 (criterion n_storage_stay_relations).
        ignore_vehicles: DD-V2 for the maximal visits.
        trivial_excludes_connecting: See `metrics.visit_metrics`.

    Returns:
        MappingAnalysis: All frames, collected.
    """
    rel, visits = derive_maximal_visits(
        relations, location, agg, kappa, vehicles, ignore_vehicles, processing
    )
    rel = add_mapping_inputs(rel, vehicles, processing, location)
    if isinstance(rel, pl.LazyFrame):
        rel, visits = pl.collect_all([rel, visits])
    segments = map_traces(
        rel,
        visits,
        strategy,
        location,
        storage_high_levels=storage_high_levels(storage_units, agg),
    )
    mapping = mapping_visits(rel, segments)
    metrics = mapping_metrics(
        rel,
        mapping,
        vehicles,
        processing,
        location,
        trivial_excludes_connecting=trivial_excludes_connecting,
    )
    return MappingAnalysis(rel, visits, mapping, metrics, strategy_name(strategy))


def compare_strategies(
    relations: pl.DataFrame | pl.LazyFrame,
    strategies: Sequence[StrategyLike] = ("S1", "S2", "S3", "S4", "S5", "S6"),
    **kwargs,
) -> tuple[pl.DataFrame, dict[str, MappingAnalysis]]:
    """Pooled metrics of several strategies side by side.

    Args:
        relations: As for `derive_mapping_set`.
        strategies: The strategies to compare.
        **kwargs: Further arguments of `derive_mapping_set` (location, agg, vehicles, kappa, processing, ...).

    Returns:
        tuple[pl.DataFrame, dict[str, MappingAnalysis]]: One row per strategy (column strategy, then the
        pooled metrics), and the analyses by strategy name.
    """
    analyses = {}
    for strategy in strategies:
        analysis = derive_mapping_set(relations, strategy=strategy, **kwargs)
        analyses[analysis.strategy] = analysis
    table = pl.concat(
        [
            a.metrics.pooled.with_columns(pl.lit(name).alias(STRATEGY))
            for name, a in analyses.items()
        ]
    )
    return table.select(STRATEGY, pl.exclude(STRATEGY)), analyses


def analyse_mapping(
    analysis: MappingAnalysis,
    location: str = "loc",
    vehicles: Collection[str] = (),
    processing: Collection[str] | None = None,
    storage_units: Collection[str] = (),
    vehicles_outside_external: bool = False,
    with_waiting_times: bool = True,
    agg: Mapping[str, str] | None = None,
    **waiting_options,
) -> VisitAnalysis:
    """Shifts, waiting times, dwell times, properties and the overview of a mapping set, in one call.

    The same as for the maximal visits (`visits.pipeline.analyse_visit_set`), run on V_map.

    Args:
        analysis: Output of `derive_mapping_set`.
        location: Column of loc.
        vehicles: The set V.
        processing: The processing operations P as event ids; None = T.
        storage_units: The set W.
        vehicles_outside_external: DD-S1.
        with_waiting_times: Also compute the waiting times (default True).
        agg: Location mapping, only for the naming-clash flag.
        **waiting_options: Further options of `waiting_times.pipeline.analyse_waiting_times`.

    Returns:
        VisitAnalysis: All frames for the visits of the mapping set.
    """
    return analyse_visit_set(
        analysis.relations,
        analysis.mapping,
        location,
        vehicles,
        processing,
        storage_units,
        vehicles_outside_external,
        with_waiting_times,
        agg,
        **waiting_options,
    )
