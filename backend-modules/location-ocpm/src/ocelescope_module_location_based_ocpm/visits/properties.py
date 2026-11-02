"""Properties of visits and of sets of visits, for ANY set of visits (concept note
`overview/concepts/Visit Mappings.md`, "Properties", "Sets of visits" and "identifying shifts").

Every function takes a visits table with at least visit_id, hu, high_level, first_position, last_position
(e.g. the maximal visits, the visits of a mapping set, or a hand-written table, see `with_positions`) and,
where needed, its visit relations (`maximal.visit_relations`, with `shifts.add_stops`). The same functions
are used for V_max and for mapping sets (`visit_mapping.metrics`).

Per visit (`visit_properties`):
- trivial: |σ| = 1;
- interrupted: R(ν) ≠ R_hl(ν);
- kind: "⊥ visit" (hl = ⊥), "stay" (has a stop), "vehicle visit" (L_¬v(ν) = ∅) or "transferring visit"
  (no stop, L_¬v(ν) ≠ ∅); `kind_of` is the same rule for one visit in Python (used by the global strategies);
- counts: relations not at hl, relations on a vehicle, processing relations at hl, excursions;
- contained (ν ⊑ ν' for another ν'), contains (another visit is contained in ν), overlapping (ν ∥ ν'),
  relative to the visit set itself (`visit_pairs`).

Per handling unit and for the whole set (`set_properties`, `set_metrics`): disjoint, hl-disjoint, covering,
and N^ν, p^r_cov, N^ν_int / p^ν_int, N^ν_con, N^ν_ov, N^hu_dis / p^hu_dis, N^r_>1 / p^r_>1, N^r_nc / p^r_nc,
p^r_∥ (N counts, p shares; superscript = counted entity: ν visits, r relations, hu handling units).
"""

from collections.abc import Collection

import polars as pl

from ..derivation import columns as c
from . import columns as v
from .context import Frame
from .sequence import CONTAINED_IN, OTHER, OVERLAPS, RELATION, interval_pairs

#: Kinds of a visit.
STAY = "stay"
VEHICLE_VISIT = "vehicle visit"
TRANSFERRING_VISIT = "transferring visit"
BOTTOM_VISIT = "⊥ visit"
KINDS = (STAY, VEHICLE_VISIT, TRANSFERRING_VISIT, BOTTOM_VISIT)

#: Columns of `visit_properties`.
KIND = "kind"
IS_TRIVIAL = "is_trivial"
N_NOT_AT_LOCATION = "n_not_at_location"
N_VEHICLE_RELATIONS = "n_vehicle_relations"
N_PROCESSING_AT_LOCATION = "n_processing_at_location"
N_EXCURSIONS = "n_excursions"
IS_CONTAINED = "is_contained"
CONTAINS = "contains"
IS_OVERLAPPING = "is_overlapping"
PROPERTY_COLUMNS = [
    KIND,
    IS_TRIVIAL,
    v.INTERRUPTED,
    N_NOT_AT_LOCATION,
    N_VEHICLE_RELATIONS,
    N_PROCESSING_AT_LOCATION,
    N_EXCURSIONS,
    IS_CONTAINED,
    CONTAINS,
    IS_OVERLAPPING,
]

#: Columns of `set_properties` (one row per handling unit).
IS_DISJOINT = "is_disjoint"
IS_HL_DISJOINT = "is_hl_disjoint"
IS_COVERING = "is_covering"


def kind_of(high_level: str | None, has_stop: bool, has_non_vehicle: bool) -> str:
    """The kind of one visit (Python version of `kind_expr`).

    Args:
        high_level: hl of the visit (None = ⊥).
        has_stop: The visit has a stop (a relation at hl not on a vehicle).
        has_non_vehicle: Some located relation of the visit is not on a vehicle (L_¬v(ν) ≠ ∅).

    Returns:
        str: "⊥ visit", "stay", "vehicle visit" or "transferring visit".
    """
    if high_level is None:
        return BOTTOM_VISIT
    if has_stop:
        return STAY
    return TRANSFERRING_VISIT if has_non_vehicle else VEHICLE_VISIT


def kind_expr(
    high_level: pl.Expr, has_stop: pl.Expr, has_non_vehicle: pl.Expr
) -> pl.Expr:
    """The kind of a visit as a polars expression (same rule as `kind_of`).

    Args:
        high_level: hl of the visit (null = ⊥).
        has_stop: Boolean: the visit has a stop.
        has_non_vehicle: Boolean: L_¬v(ν) ≠ ∅.

    Returns:
        pl.Expr: The kind (string).
    """
    return (
        pl.when(high_level.is_null())
        .then(pl.lit(BOTTOM_VISIT))
        .when(has_stop)
        .then(pl.lit(STAY))
        .when(has_non_vehicle)
        .then(pl.lit(TRANSFERRING_VISIT))
        .otherwise(pl.lit(VEHICLE_VISIT))
    )


def trivial_expr(n_relations: str = v.N_RELATIONS) -> pl.Expr:
    """Trivial visit: |σ| = 1 (concept note, "Properties").

    Args:
        n_relations: Column with |σ|.

    Returns:
        pl.Expr: Boolean.
    """
    return pl.col(n_relations) == 1


def with_positions(visits: pl.DataFrame, relations: pl.DataFrame) -> pl.DataFrame:
    """Make sure a visits table has first_position, last_position and visit_id.

    Lets every function here take a hand-written visit set given by its first and last event.

    Args:
        visits: One row per visit with hu, high_level and either first_position, last_position or
            first_event, last_event.
        relations: Relations with hu, event, position.

    Returns:
        pl.DataFrame: `visits` with the positions (looked up from the events if missing) and a visit_id
        (1, 2, ... in hu and position order if missing).
    """
    out = visits
    if v.FIRST_POSITION not in out.columns or v.LAST_POSITION not in out.columns:
        pos = relations.select(c.HU, c.EVENT, pl.col(v.POSITION).cast(pl.Int64))
        out = out.join(
            pos.rename({c.EVENT: v.FIRST_EVENT, v.POSITION: v.FIRST_POSITION}),
            on=[c.HU, v.FIRST_EVENT],
        ).join(
            pos.rename({c.EVENT: v.LAST_EVENT, v.POSITION: v.LAST_POSITION}),
            on=[c.HU, v.LAST_EVENT],
        )
    if v.VISIT_ID not in out.columns:
        out = (
            out.sort(c.HU, v.FIRST_POSITION)
            .with_row_index(v.VISIT_ID, offset=1)
            .with_columns(pl.col(v.VISIT_ID).cast(pl.Int64))
        )
    return out


def visit_pairs(visits: Frame) -> Frame:
    """The contained and overlapping pairs of a visit set (per handling unit).

    ν ⊑ ν' ("contained in") iff σ ⊑ σ' and ν ≠ ν'; ν ∥ ν' ("overlaps") iff they share a relation and neither
    is contained in the other. Built on `sequence.interval_pairs`.

    Args:
        visits: One row per visit with visit_id, hu, first_position, last_position.

    Returns:
        Frame: hu, visit_id, other_visit_id, relation ("contained in" / "overlaps", read: visit relation
        other), n_shared (shared relations); an overlap appears in both directions.
    """
    return interval_pairs(visits, c.HU, v.VISIT_ID, v.FIRST_POSITION, v.LAST_POSITION)


def pair_flags(visits: Frame, pairs: Frame) -> Frame:
    """Per visit: is_contained, contains, is_overlapping (from `visit_pairs`).

    Args:
        visits: One row per visit with visit_id.
        pairs: Output of `visit_pairs` for the same visits.

    Returns:
        Frame: visit_id, is_contained, contains, is_overlapping.
    """
    other = OTHER + v.VISIT_ID
    contained = pairs.filter(pl.col(RELATION) == CONTAINED_IN)
    flags = [
        (contained.select(v.VISIT_ID).unique(), IS_CONTAINED),
        (contained.select(pl.col(other).alias(v.VISIT_ID)).unique(), CONTAINS),
        (
            pairs.filter(pl.col(RELATION) == OVERLAPS).select(v.VISIT_ID).unique(),
            IS_OVERLAPPING,
        ),
    ]
    out = visits.select(v.VISIT_ID)
    for ids, name in flags:
        out = out.join(
            ids.with_columns(pl.lit(True).alias(name)), on=v.VISIT_ID, how="left"
        ).with_columns(pl.col(name).fill_null(False))
    return out


def visit_properties(
    visits: Frame,
    visit_relations: Frame,
    excursions: Frame | None = None,
    location: str = "loc",
) -> Frame:
    """The properties of every visit of any visit set.

    Args:
        visits: One row per visit with visit_id, hu, high_level, first_position, last_position, n_relations,
            n_at_location (e.g. `maximal.visit_table`).
        visit_relations: Its visit relations with on_vehicle and is_stop (`shifts.add_stops`); with the
            column is_processing_event, processing relations at hl are counted (else 0).
        excursions: Output of `excursions.excursions` for the same visits; None = n_excursions is computed
            from `visit_relations`.
        location: Column of loc.

    Returns:
        Frame: `visits` with the columns of `PROPERTY_COLUMNS` (interrupted is recomputed), sorted by
        visit_id.
    """
    from .excursions import excursion_counts
    from .excursions import excursions as find_excursions

    names = visit_relations.collect_schema().names()
    processing = (
        pl.col(v.IS_PROCESSING_EVENT)
        if v.IS_PROCESSING_EVENT in names
        else pl.lit(False)
    )
    at_hl = pl.col(v.AT_LOCATION) & pl.col(v.VISIT_HIGH_LEVEL).is_not_null()
    per_visit = visit_relations.group_by(v.VISIT_ID).agg(
        pl.col(v.ON_VEHICLE).sum().cast(pl.Int64).alias(N_VEHICLE_RELATIONS),
        (processing & at_hl).sum().cast(pl.Int64).alias(N_PROCESSING_AT_LOCATION),
        pl.col(v.IS_STOP).any().alias("_has_stop"),
        (pl.col(location).is_not_null() & ~pl.col(v.ON_VEHICLE))
        .any()
        .alias("_has_non_vehicle"),
    )
    if excursions is None:
        excursions = find_excursions(visit_relations)
    pairs = visit_pairs(visits)
    return (
        visits.drop(
            [col for col in PROPERTY_COLUMNS if col in visits.collect_schema().names()]
        )
        .join(per_visit, on=v.VISIT_ID, how="left")
        .join(excursion_counts(visits, excursions), on=v.VISIT_ID, how="left")
        .join(pair_flags(visits, pairs), on=v.VISIT_ID, how="left")
        .with_columns(
            kind_expr(
                pl.col(v.HIGH_LEVEL), pl.col("_has_stop"), pl.col("_has_non_vehicle")
            ).alias(KIND),
            trivial_expr().alias(IS_TRIVIAL),
            (pl.col(v.N_RELATIONS) > pl.col(v.N_AT_LOCATION)).alias(v.INTERRUPTED),
            (pl.col(v.N_RELATIONS) - pl.col(v.N_AT_LOCATION)).alias(N_NOT_AT_LOCATION),
        )
        .drop("_has_stop", "_has_non_vehicle")
        .sort(v.VISIT_ID)
    )


def relation_counts(visit_relations: Frame) -> Frame:
    """Per relation (hu, position): in how many visits it lies, and whether it is non-conforming in one.

    Args:
        visit_relations: Visit relations (`maximal.visit_relations`) of a visit set.

    Returns:
        Frame: hu, position, n_visits, is_nonconforming (r ∈ R_nc(ν) for some ν).
    """
    return visit_relations.group_by(c.HU, v.POSITION).agg(
        pl.len().cast(pl.Int64).alias("n_visits"),
        (~pl.col(v.AT_LOCATION)).any().alias("is_nonconforming"),
    )


def overlapping_relations(visit_relations: Frame, pairs: Frame) -> Frame:
    """The relations shared by two overlapping visits, RL_∥(V).

    Args:
        visit_relations: Visit relations of the visit set.
        pairs: Output of `visit_pairs`.

    Returns:
        Frame: hu, position (unique).
    """
    overlapping = pairs.filter(pl.col(RELATION) == OVERLAPS).select(
        v.VISIT_ID, pl.col(OTHER + v.VISIT_ID)
    )
    vr = visit_relations.select(v.VISIT_ID, c.HU, v.POSITION)
    return (
        overlapping.join(vr, on=v.VISIT_ID)
        .join(
            vr.rename({v.VISIT_ID: OTHER + v.VISIT_ID}),
            on=[OTHER + v.VISIT_ID, c.HU, v.POSITION],
        )
        .select(c.HU, v.POSITION)
        .unique()
    )


def set_properties(
    visits: Frame,
    visit_relations: Frame,
    relations: Frame,
    pairs: Frame | None = None,
) -> Frame:
    """Per handling unit: is its visit set V(hu) disjoint, hl-disjoint, covering?

    - disjoint: no visit contained or overlapping, i.e. every relation lies in at most one visit;
    - hl-disjoint: every relation lies in R_hl of at most one visit;
    - covering: every relation of hu lies in some visit.
    Handling units of `relations` without any visit get false for covering and null for the others.

    Args:
        visits: The visit set.
        visit_relations: Its visit relations.
        relations: All relations E2HU (hu, position).
        pairs: Output of `visit_pairs`; None = computed.

    Returns:
        Frame: hu, n_visits, is_disjoint, is_hl_disjoint, is_covering; sorted by hu.
    """
    if pairs is None:
        pairs = visit_pairs(visits)
    per_hu_visits = visits.group_by(c.HU).agg(pl.len().cast(pl.Int64).alias("n_visits"))
    not_disjoint = (
        pairs.select(c.HU).unique().with_columns(pl.lit(False).alias(IS_DISJOINT))
    )
    hl_shared = (
        visit_relations.filter(pl.col(v.AT_LOCATION))
        .group_by(c.HU, v.POSITION)
        .agg(pl.len().alias("_n"))
        .filter(pl.col("_n") > 1)
        .select(c.HU)
        .unique()
        .with_columns(pl.lit(False).alias(IS_HL_DISJOINT))
    )
    covered = visit_relations.select(c.HU, v.POSITION).unique()
    uncovered = (
        relations.select(c.HU, pl.col(v.POSITION).cast(pl.Int64))
        .join(
            covered.with_columns(pl.col(v.POSITION).cast(pl.Int64)),
            on=[c.HU, v.POSITION],
            how="anti",
        )
        .select(c.HU)
        .unique()
        .with_columns(pl.lit(False).alias(IS_COVERING))
    )
    all_hus = relations.select(c.HU).unique()
    return (
        all_hus.join(per_hu_visits, on=c.HU, how="left")
        .join(not_disjoint, on=c.HU, how="left")
        .join(hl_shared, on=c.HU, how="left")
        .join(uncovered, on=c.HU, how="left")
        .with_columns(
            pl.col("n_visits").fill_null(0),
            *(
                pl.when(pl.col("n_visits") > 0)
                .then(pl.col(col).fill_null(True))
                .alias(col)
                for col in (IS_DISJOINT, IS_HL_DISJOINT)
            ),
            (pl.col(IS_COVERING).fill_null(True) & (pl.col("n_visits") > 0)).alias(
                IS_COVERING
            ),
        )
        .select(c.HU, "n_visits", IS_DISJOINT, IS_HL_DISJOINT, IS_COVERING)
        .sort(c.HU)
    )


#: Columns of `set_metrics`.
SET_METRIC_COLUMNS = [
    "n_visits",
    "n_relations",
    "n_covered",
    "p_cov",
    "n_interrupted",
    "p_int",
    "n_contained",
    "n_overlapping",
    "n_hus",
    "n_disjoint_hus",
    "p_dis",
    "n_in_several_visits",
    "p_several",
    "n_nonconforming",
    "p_nc",
    "n_overlapping_relations",
    "p_overlap",
]


def _share(numerator: str, denominator: str) -> pl.Expr:
    """numerator / denominator, null if the denominator is 0."""
    return pl.when(pl.col(denominator) > 0).then(
        pl.col(numerator) / pl.col(denominator)
    )


def set_metrics(
    visits: Frame,
    visit_relations: Frame,
    relations: Frame,
    by_hu: bool = False,
) -> pl.DataFrame:
    """The metrics of a set of visits (concept note, "Sets of visits", "Metrics").

    | metric | column | definition |
    |---|---|---|
    | N^ν | n_visits | number of visits |
    | p^r_cov | n_covered / n_relations, p_cov | relations in some visit / all relations E2HU |
    | N^ν_int, p^ν_int | n_interrupted, p_int | interrupted visits, / N^ν |
    | N^ν_con | n_contained | visits contained in another visit |
    | N^ν_ov | n_overlapping | visits overlapping another visit |
    | N^hu_dis, p^hu_dis | n_disjoint_hus / n_hus, p_dis | handling units whose visits are disjoint, / all hus of the relations |
    | N^r_>1, p^r_>1 | n_in_several_visits, p_several | relations in more than one visit, / all relations |
    | N^r_nc, p^r_nc | n_nonconforming, p_nc | relations non-conforming in at least one visit, / all relations |
    | p^r_∥ | n_overlapping_relations, p_overlap | relations shared by two overlapping visits, / all relations |

    Args:
        visits: The visit set (visit_id, hu, first_position, last_position, n_relations, n_at_location).
        visit_relations: Its visit relations (`maximal.visit_relations`).
        relations: All relations E2HU (hu, position).
        by_hu: False = one row for the whole set; True = one row per handling unit.

    Returns:
        pl.DataFrame: `SET_METRIC_COLUMNS` (with hu first if `by_hu`).
    """
    lazy = [
        f.lazy()
        for f in (
            visits,
            visit_relations,
            relations.select(c.HU, pl.col(v.POSITION).cast(pl.Int64)),
        )
    ]
    visits, visit_relations, rel = lazy
    pairs = visit_pairs(visits)
    flags = pair_flags(visits, pairs)
    by = [c.HU] if by_hu else []
    per_visit = visits.select(c.HU, v.VISIT_ID, v.N_RELATIONS, v.N_AT_LOCATION).join(
        flags, on=v.VISIT_ID
    )
    counts = relation_counts(visit_relations)
    overlap = overlapping_relations(visit_relations, pairs).with_columns(
        pl.lit(True).alias("_ov")
    )
    per_relation = (
        rel.join(counts, on=[c.HU, v.POSITION], how="left")
        .join(overlap, on=[c.HU, v.POSITION], how="left")
        .with_columns(
            pl.col("n_visits").fill_null(0),
            pl.col("is_nonconforming").fill_null(False),
            pl.col("_ov").fill_null(False),
        )
    )
    disjoint = set_properties(visits, visit_relations, rel, pairs).select(
        c.HU, IS_DISJOINT
    )

    def grouped(frame: pl.LazyFrame, aggs: list[pl.Expr]) -> pl.LazyFrame:
        return frame.group_by(by).agg(aggs) if by else frame.select(aggs)

    v_part = grouped(
        per_visit,
        [
            pl.len().cast(pl.Int64).alias("n_visits"),
            (pl.col(v.N_RELATIONS) > pl.col(v.N_AT_LOCATION))
            .sum()
            .cast(pl.Int64)
            .alias("n_interrupted"),
            pl.col(IS_CONTAINED).sum().cast(pl.Int64).alias("n_contained"),
            pl.col(IS_OVERLAPPING).sum().cast(pl.Int64).alias("n_overlapping"),
        ],
    )
    r_part = grouped(
        per_relation,
        [
            pl.len().cast(pl.Int64).alias("n_relations"),
            (pl.col("n_visits") > 0).sum().cast(pl.Int64).alias("n_covered"),
            (pl.col("n_visits") > 1).sum().cast(pl.Int64).alias("n_in_several_visits"),
            pl.col("is_nonconforming").sum().cast(pl.Int64).alias("n_nonconforming"),
            pl.col("_ov").sum().cast(pl.Int64).alias("n_overlapping_relations"),
        ],
    )
    d_part = grouped(
        disjoint,
        [
            pl.len().cast(pl.Int64).alias("n_hus"),
            pl.col(IS_DISJOINT)
            .fill_null(False)
            .sum()
            .cast(pl.Int64)
            .alias("n_disjoint_hus"),
        ],
    )
    if by:
        out = r_part.join(v_part, on=by, how="left").join(d_part, on=by, how="left")
    else:
        out = pl.concat([r_part, v_part, d_part], how="horizontal")
    out = out.with_columns(
        pl.col("n_visits", "n_interrupted", "n_contained", "n_overlapping").fill_null(0)
    ).with_columns(
        _share("n_covered", "n_relations").alias("p_cov"),
        _share("n_interrupted", "n_visits").alias("p_int"),
        _share("n_disjoint_hus", "n_hus").alias("p_dis"),
        _share("n_in_several_visits", "n_relations").alias("p_several"),
        _share("n_nonconforming", "n_relations").alias("p_nc"),
        _share("n_overlapping_relations", "n_relations").alias("p_overlap"),
    )
    return (
        out.select(*by, *SET_METRIC_COLUMNS).sort(by).collect()
        if by
        else out.select(SET_METRIC_COLUMNS).collect()
    )


def rq4_violations(
    relations: Frame, column: str = v.HIGH_LEVEL, time: str = c.TIME
) -> Frame:
    """Flag RQ4: relations of a handling unit with the same timestamp but different locations.

    RQ4 (concept note, "Setting"): all relations of a handling unit with the same timestamp have the same
    (high-level) location. It holds at Levels 1 to 3 by construction; at Level 0, tied relations can differ
    in being located or not (null counts as a value of its own here).

    Args:
        relations: Relations with hu, event, `time` and `column`.
        column: The location column to compare, e.g. "high_level" (default) or "loc".
        time: Timestamp column.

    Returns:
        Frame: One row per violating (hu, time): hu, time, events (sorted list), values (sorted distinct
        values of `column`, null included); empty if RQ4 holds.
    """
    return (
        relations.group_by(c.HU, time)
        .agg(
            pl.col(c.EVENT).sort().alias("events"),
            pl.col(column).unique().sort(nulls_last=True).alias("values"),
            pl.col(column).n_unique().alias("_n"),
        )
        .filter(pl.col("_n") > 1)
        .drop("_n")
        .sort(c.HU, time)
    )


def flag_rq4(relations: Frame, column: str = v.HIGH_LEVEL) -> bool:
    """True if RQ4 holds (no violations, `rq4_violations`).

    Args:
        relations: Relations with hu, event, time and `column`.
        column: The location column to compare.

    Returns:
        bool: True if no handling unit has relations with the same timestamp at different locations.
    """
    found = rq4_violations(relations, column)
    if isinstance(found, pl.LazyFrame):
        found = found.collect()
    return found.height == 0


def located_processing(
    relations: Frame, processing: Collection[str] | None = None
) -> Frame:
    """Per handling unit: number of located processing relations (e ∈ P and hat-hl ≠ ⊥).

    Args:
        relations: Relations with hu, event, high_level (and is_transformation if `processing` is None).
        processing: The processing operations P as event ids; None = the transformation events T.

    Returns:
        Frame: hu, n_located_processing.
    """
    from .order import processing_flag

    return relations.group_by(c.HU).agg(
        (processing_flag(processing) & pl.col(v.HIGH_LEVEL).is_not_null())
        .sum()
        .cast(pl.Int64)
        .alias("n_located_processing")
    )
