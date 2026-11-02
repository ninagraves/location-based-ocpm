"""Evaluation metrics of a mapping set (working note, section 7), for one or several handling units.

For a handling unit, its visits in V_map form a visit sequence ⟨ν_1, ..., ν_r⟩. A visit is a **stay** if
it has a stop, otherwise a vehicle visit (all located relations on vehicles), a transferring visit, or a
⊥ visit. Per visit, per handling unit and pooled over the given handling units:

| metric | column | definition |
|---|---|---|
| N_vis | n_visits | number of visits |
| N_proc, p_proc | n_conforming_processing, n_located_processing, p_proc | processing relations at their visit's hl / all located processing relations |
| N_loop | n_loops | stays whose hl occurred in an earlier stay, with a stay at another hl in between (vehicle and transferring visits ignored, so A, T, A is no loop) |
| N_triv | n_trivial | visits with one relation (Nina, concept note, "Properties"), not connecting (default, Nina 2026-11-02) |
| N_triv^np | n_trivial_without_processing | trivial visits without a processing operation at their hl (Nina, 2026-11-02) |
| N_veh, N_trans | n_vehicle_visits, n_transferring_visits | vehicle and transferring visits |
| p_vr | n_vehicle_relations_on_the_way, n_vehicle_relations, p_vr | relations at vehicles (loc ∈ V) in a vehicle or transferring visit / all relations at vehicles (Nina, 2026-11-02) |
| N_conn, p_conn | n_connecting, p_conn | vehicle or transferring visits whose two neighbours are stays at different hl / (N_veh + N_trans) |
| relations per visit | mean_relations, median_relations | |
| duration | mean_duration, median_duration | d = time(exit event) - time(first event) |
| p_conf | n_conforming, n_relations, p_conf | relations at their visit's hl / all relations |

All steps are polars expressions (no loop over rows); the frames can be eager or lazy until `collect`.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import timedelta

import polars as pl

from ..derivation import columns as c
from ..visits import columns as v
from ..visits.maximal import visit_relations, visit_table
from ..visits.order import processing_flag
from ..visits.properties import (
    KIND,
    N_PROCESSING_AT_LOCATION,
    N_VEHICLE_RELATIONS,
    STAY,
    TRANSFERRING_VISIT,
    VEHICLE_VISIT,
    located_processing,
    trivial_expr,
    visit_properties,
    with_positions,
)
from ..visits.sequence import add_positions
from ..visits.shifts import add_stops

#: Columns of the per-visit metrics.
SEQUENCE_INDEX = "j"
N_CONFORMING_PROCESSING = "n_conforming_processing"
IS_LOOP = "is_loop"
IS_CONNECTING = "is_connecting"
IS_TRIVIAL = "is_trivial"
IS_TRIVIAL_WITHOUT_PROCESSING = "is_trivial_without_processing"

#: Columns of the summaries (per handling unit and pooled).
SUMMARY_COLUMNS = [
    "n_visits",
    "n_stays",
    "n_conforming_processing",
    "n_located_processing",
    "p_proc",
    "n_loops",
    "n_trivial",
    "n_trivial_without_processing",
    "n_vehicle_visits",
    "n_transferring_visits",
    "n_connecting",
    "p_conn",
    "n_vehicle_relations_on_the_way",
    "n_vehicle_relations",
    "p_vr",
    "mean_relations",
    "median_relations",
    "mean_duration",
    "median_duration",
    "n_conforming",
    "n_relations",
    "p_conf",
]


@dataclass
class MappingMetrics:
    """The evaluation metrics of a mapping set.

    Attributes:
        visits: One row per visit: hu, visit_id, high_level, j (index in the visit sequence), kind,
            n_relations, n_at_location, n_conforming_processing, n_vehicle_relations (loc ∈ V), duration, is_loop, is_connecting, is_trivial.
        per_hu: One row per handling unit with `SUMMARY_COLUMNS`.
        pooled: One row with `SUMMARY_COLUMNS`, pooled over the handling units.
    """

    visits: pl.DataFrame
    per_hu: pl.DataFrame
    pooled: pl.DataFrame


def visit_metrics(
    relations: pl.DataFrame,
    mapping: pl.DataFrame,
    vehicles: Collection[str] = (),
    processing: Collection[str] | None = None,
    location: str = "loc",
    trivial_excludes_connecting: bool = True,
) -> pl.DataFrame:
    """Per-visit metrics of a mapping set.

    Args:
        relations: Relations with hu, event, time, position, high_level, `location` (and is_transformation if
            `processing` is None), e.g. of `derive_maximal_visits`.
        mapping: The visits of the mapping set (see `with_positions`).
        vehicles: The set V.
        processing: The processing operations P as event ids; None = the transformation events T.
        location: Column of loc.
        trivial_excludes_connecting: True (default; Nina, 2026-11-02) = connecting vehicle or transferring
            visits are never trivial; False = they count like any other visit. Applies to both is_trivial
            (|σ| = 1) and is_trivial_without_processing (also no processing operation at its hl).

    Returns:
        pl.DataFrame: One row per visit (see `MappingMetrics.visits`), sorted by hu and j.
    """
    mapping = with_positions(mapping, relations)
    rel = relations.with_columns(
        processing_flag(processing).alias(v.IS_PROCESSING_EVENT)
    )
    intervals = mapping.select(
        c.HU, v.VISIT_ID, v.HIGH_LEVEL, v.FIRST_POSITION, v.LAST_POSITION
    )
    table = visit_table(intervals, rel)
    vrel = add_stops(visit_relations(rel, table), vehicles, location)
    out = add_positions(
        visit_properties(table, vrel, location=location).rename(
            {N_PROCESSING_AT_LOCATION: N_CONFORMING_PROCESSING}
        ),
        c.HU,
        v.FIRST_POSITION,
        SEQUENCE_INDEX,
    )
    is_stay = pl.col(KIND) == STAY
    # loops: among the stays of a handling unit, hl seen before and the previous stay at another hl
    stays = (
        out.filter(is_stay)
        .with_columns(
            (pl.int_range(pl.len()).over(c.HU, v.HIGH_LEVEL) > 0).alias("_seen"),
            pl.col(v.HIGH_LEVEL).shift(1).over(c.HU).alias("_prev_stay_hl"),
        )
        .select(
            v.VISIT_ID,
            (pl.col("_seen") & (pl.col("_prev_stay_hl") != pl.col(v.HIGH_LEVEL))).alias(
                IS_LOOP
            ),
        )
    )
    prev_kind = pl.col(KIND).shift(1).over(c.HU)
    next_kind = pl.col(KIND).shift(-1).over(c.HU)
    prev_hl = pl.col(v.HIGH_LEVEL).shift(1).over(c.HU)
    next_hl = pl.col(v.HIGH_LEVEL).shift(-1).over(c.HU)
    connecting = (
        pl.col(KIND).is_in([VEHICLE_VISIT, TRANSFERRING_VISIT])
        & (prev_kind == STAY)
        & (next_kind == STAY)
        & (prev_hl != next_hl)
    ).fill_null(False)
    out = out.join(stays, on=v.VISIT_ID, how="left").with_columns(
        pl.col(IS_LOOP).fill_null(False), connecting.alias(IS_CONNECTING)
    )
    trivial = trivial_expr()
    if trivial_excludes_connecting:
        trivial = trivial & ~pl.col(IS_CONNECTING)
    without_processing = trivial & (pl.col(N_CONFORMING_PROCESSING) == 0)
    return out.with_columns(
        trivial.alias(IS_TRIVIAL),
        without_processing.alias(IS_TRIVIAL_WITHOUT_PROCESSING),
    ).select(
        c.HU,
        v.VISIT_ID,
        v.HIGH_LEVEL,
        SEQUENCE_INDEX,
        v.FIRST_POSITION,
        v.LAST_POSITION,
        KIND,
        v.N_RELATIONS,
        v.N_AT_LOCATION,
        N_CONFORMING_PROCESSING,
        N_VEHICLE_RELATIONS,
        v.DURATION,
        IS_LOOP,
        IS_CONNECTING,
        IS_TRIVIAL,
        IS_TRIVIAL_WITHOUT_PROCESSING,
    )


def _share(numerator: str, denominator: str) -> pl.Expr:
    """numerator / denominator, null if the denominator is 0."""
    return pl.when(pl.col(denominator) > 0).then(
        pl.col(numerator) / pl.col(denominator)
    )


def summarise(
    visits: pl.DataFrame, located_processing: pl.DataFrame, by: list[str]
) -> pl.DataFrame:
    """Summary metrics of per-visit metrics (`SUMMARY_COLUMNS`).

    Args:
        visits: Output of `visit_metrics`.
        located_processing: Columns hu, n_located_processing (located processing relations per hu).
        by: Group columns, e.g. ["hu"]; empty = pooled over all rows.

    Returns:
        pl.DataFrame: One row per group.
    """
    vehicle_like = pl.col(KIND).is_in([VEHICLE_VISIT, TRANSFERRING_VISIT])
    aggs = [
        pl.len().cast(pl.Int64).alias("n_visits"),
        (pl.col(KIND) == STAY).sum().cast(pl.Int64).alias("n_stays"),
        pl.col(N_CONFORMING_PROCESSING)
        .sum()
        .cast(pl.Int64)
        .alias("n_conforming_processing"),
        pl.col(IS_LOOP).sum().cast(pl.Int64).alias("n_loops"),
        pl.col(IS_TRIVIAL).sum().cast(pl.Int64).alias("n_trivial"),
        pl.col(IS_TRIVIAL_WITHOUT_PROCESSING)
        .sum()
        .cast(pl.Int64)
        .alias("n_trivial_without_processing"),
        (pl.col(KIND) == VEHICLE_VISIT).sum().cast(pl.Int64).alias("n_vehicle_visits"),
        (pl.col(KIND) == TRANSFERRING_VISIT)
        .sum()
        .cast(pl.Int64)
        .alias("n_transferring_visits"),
        pl.col(IS_CONNECTING).sum().cast(pl.Int64).alias("n_connecting"),
        vehicle_like.sum().cast(pl.Int64).alias("_n_vehicle_like"),
        pl.col(N_VEHICLE_RELATIONS)
        .filter(vehicle_like)
        .sum()
        .cast(pl.Int64)
        .alias("n_vehicle_relations_on_the_way"),
        pl.col(N_VEHICLE_RELATIONS).sum().cast(pl.Int64).alias("n_vehicle_relations"),
        pl.col(v.N_RELATIONS).mean().alias("mean_relations"),
        pl.col(v.N_RELATIONS).median().alias("median_relations"),
        pl.col(v.DURATION).mean().alias("mean_duration"),
        pl.col(v.DURATION).median().alias("median_duration"),
        pl.col(v.N_AT_LOCATION).sum().cast(pl.Int64).alias("n_conforming"),
        pl.col(v.N_RELATIONS).sum().cast(pl.Int64).alias("n_relations"),
    ]
    if by:
        out = (
            visits.group_by(by)
            .agg(aggs)
            .join(located_processing, on=by, how="left")
            .sort(by)
        )
    else:
        out = visits.select(aggs).with_columns(
            pl.lit(located_processing["n_located_processing"].sum())
            .cast(pl.Int64)
            .alias("n_located_processing")
        )
    out = out.with_columns(pl.col("n_located_processing").fill_null(0)).with_columns(
        _share("n_conforming_processing", "n_located_processing").alias("p_proc"),
        _share("n_connecting", "_n_vehicle_like").alias("p_conn"),
        _share("n_conforming", "n_relations").alias("p_conf"),
        _share("n_vehicle_relations_on_the_way", "n_vehicle_relations").alias("p_vr"),
    )
    return out.select(*by, *SUMMARY_COLUMNS)


def mapping_metrics(
    relations: pl.DataFrame,
    mapping: pl.DataFrame,
    vehicles: Collection[str] = (),
    processing: Collection[str] | None = None,
    location: str = "loc",
    handling_units: Collection[str] | None = None,
    trivial_excludes_connecting: bool = True,
) -> MappingMetrics:
    """Evaluation metrics of a mapping set for one or several handling units.

    Args:
        relations: Relations with hu, event, time, position, high_level, `location` (and is_transformation if
            `processing` is None), e.g. `MappingAnalysis.relations` or the relations of `derive_maximal_visits`.
        mapping: The visits of the mapping set: hu, high_level and first/last position or first/last event
            (e.g. `MappingAnalysis.mapping`, or a hand-written table for one handling unit).
        vehicles: The set V.
        processing: The processing operations P as event ids; None = the transformation events T.
        location: Column of loc.
        handling_units: Evaluate only these handling units; None = all handling units of `mapping`.
        trivial_excludes_connecting: See `visit_metrics`.

    Returns:
        MappingMetrics: Per visit, per handling unit and pooled. Shares are null if their denominator is 0.
    """
    hus = (
        handling_units
        if handling_units is not None
        else mapping[c.HU].unique().to_list()
    )
    mapping = mapping.filter(pl.col(c.HU).is_in(list(hus)))
    relations = relations.filter(pl.col(c.HU).is_in(list(hus)))
    visits = visit_metrics(
        relations, mapping, vehicles, processing, location, trivial_excludes_connecting
    )
    located = located_processing(relations, processing)
    return MappingMetrics(
        visits, summarise(visits, located, [c.HU]), summarise(visits, located, [])
    )


#: How each summary metric is shown in a figure: label, and for shares the numerator and denominator columns.
METRIC_LABELS: dict[str, tuple[str, tuple[str, str] | None]] = {
    "n_visits": ("N_vis", None),
    "n_stays": ("N_stay", None),
    "p_proc": ("p_proc", ("n_conforming_processing", "n_located_processing")),
    "n_loops": ("N_loop", None),
    "n_trivial": ("N_triv", None),
    "n_trivial_without_processing": ("N_triv^np", None),
    "n_vehicle_visits": ("N_veh", None),
    "n_transferring_visits": ("N_trans", None),
    "p_conn": ("p_conn", ("n_connecting", "n_vehicle_like")),
    "p_vr": ("p_vr", ("n_vehicle_relations_on_the_way", "n_vehicle_relations")),
    "mean_relations": ("mean |R|", None),
    "median_relations": ("median |R|", None),
    "mean_duration": ("mean d", None),
    "median_duration": ("median d", None),
    "p_conf": ("p_conf", ("n_conforming", "n_relations")),
}

#: Explanation of each metric, shown on mouse-over in the trace figure (Nina's note, "Evaluating mapping
#: sets": definition, then what it says).
METRIC_EXPLANATIONS: dict[str, str] = {
    "n_visits": "number of visits, Σ_hu r(hu)<br>size of the mapping; per hu: r(hu)",
    "n_stays": "number of stays: visits with at least one stop<br>(a relation at the visit's hl, not on a vehicle)",
    "p_proc": (
        "located processing relations that are conforming in their visit,<br>divided by all located "
        "processing relations<br>correctly mapped processing operations"
    ),
    "n_loops": (
        "number of stays whose hl already occurred in an earlier stay<br>of the sequence (vehicle and "
        'transferring visits ignored)<br>"went back to a place it had already left"'
    ),
    "n_trivial": (
        "number of trivial visits: one relation only (|σ| = 1),<br>not connecting<br>visits that hardly "
        "carry information"
    ),
    "n_trivial_without_processing": (
        "number of trivial visits (|σ| = 1, not connecting)<br>without a processing operation at their hl"
        "<br>visits that hardly carry information and are not a processing step"
    ),
    "n_vehicle_visits": 'number of vehicle visits (all located relations on vehicles)<br>how much of the mapping is "on the way"',
    "n_transferring_visits": (
        "number of transferring visits (no stop, but relations not on vehicles)<br>how much of the mapping is "
        '"on the way"'
    ),
    "p_conn": (
        "vehicle or transferring visits ν_j (1 < j < r) whose neighbours<br>ν_j-1, ν_j+1 are stays at different "
        'high-level locations,<br>divided by N_veh + N_trans<br>share of vehicle visits that separate "before" '
        'and "after"'
    ),
    "p_vr": (
        "relations at vehicles (loc ∈ V) that lie in a vehicle or transferring visit,<br>divided by all relations "
        'at vehicles<br>how many vehicle relations are kept "on the way" instead of being absorbed into a stay'
    ),
    "mean_relations": "mean number of relations per visit, |R(ν)|<br>granularity",
    "median_relations": "median number of relations per visit, |R(ν)|<br>granularity",
    "mean_duration": "mean visit duration d(ν) = time(exit event) - time(entry event)",
    "median_duration": "median visit duration d(ν) = time(exit event) - time(entry event)",
    "p_conf": (
        "relations conforming in their visit, Σ_ν |R_hl(ν)| / |E2HU|, i.e. 1 - p_nc<br>"
        "events agreeing on the high-level location"
    ),
}

#: Metrics shown for the whole set, and per trace, by default (N_triv; pass keys with
#: "n_trivial_without_processing" to show N_triv^np instead).
LEGEND_METRICS = (
    "n_visits",
    "p_proc",
    "n_loops",
    "n_trivial",
    "n_vehicle_visits",
    "n_transferring_visits",
    "p_conn",
    "p_vr",
    "mean_relations",
    "mean_duration",
    "p_conf",
)
TRACE_METRICS = ("n_visits", "n_loops", "n_trivial", "p_conf")


def _format_value(row: dict, key: str) -> str:
    """One metric of a summary row as text: shares as numerator/denominator, durations in hours."""
    label, share = METRIC_LABELS[key]
    if share is not None:
        numerator, denominator = share
        if denominator == "n_vehicle_like":
            value = f"{row[numerator]}/{row['n_vehicle_visits'] + row['n_transferring_visits']}"
        else:
            value = f"{row[numerator]}/{row[denominator]}"
    elif isinstance(row[key], timedelta):
        value = f"{row[key].total_seconds() / 3600:.3g} h"
    elif isinstance(row[key], float):
        value = f"{row[key]:.3g}"
    else:
        value = str(row[key])
    return f"{label} = {value}"


def metric_lines(
    pooled: pl.DataFrame, keys: Sequence[str] = LEGEND_METRICS
) -> list[tuple[str, str]]:
    """The pooled metrics as (text, explanation) pairs, e.g. for the trace figure (`legend_metrics`).

    Args:
        pooled: `MappingMetrics.pooled` (one row).
        keys: Metrics to show, keys of `METRIC_LABELS`.

    Returns:
        list[tuple[str, str]]: e.g. [("N_vis = 16", "number of visits, ..."), ("p_proc = 13/13", ...), ...].
    """
    row = pooled.row(0, named=True)
    return [(_format_value(row, key), METRIC_EXPLANATIONS[key]) for key in keys]


def trace_metric_lines(
    per_hu: pl.DataFrame, keys: Sequence[str] = TRACE_METRICS
) -> dict[str, list[tuple[str, str]]]:
    """The metrics of each handling unit as (text, explanation) pairs, e.g. for the trace figure
    (`trace_metrics`).

    Args:
        per_hu: `MappingMetrics.per_hu`.
        keys: Metrics to show, keys of `METRIC_LABELS`.

    Returns:
        dict[str, list[tuple[str, str]]]: hu -> e.g. [("N_vis = 3", "number of visits, ..."), ...].
    """
    return {
        row[c.HU]: [(_format_value(row, key), METRIC_EXPLANATIONS[key]) for key in keys]
        for row in per_hu.iter_rows(named=True)
    }
