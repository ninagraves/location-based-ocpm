"""Visit mapping vl_V and event agreement under it (concept note `overview/concepts/Visit Mappings.md`,
sections "Visit-based location function" and "Metrics for mapping sets").

For a disjoint and covering set of visits V (a mapping set), every relation r lies in exactly one visit, so
vl_V(r) = hl of that visit is a location function E2HU -> HL ∪ {⊥}:
- vl_V(r) = \\hat{hl}(r) iff r is conforming in its visit;
- a ⊥ relation inside an excursion gets the visit's hl; the relations of a ⊥ visit get ⊥.
The maximal visits V_max are in general neither (e.g. (e8, b1) lies in m2 (A) and m4 (T)), so `visit_location`
refuses them.

Agreement under vl_V is the agreement of `derivation.agreement.event_agreement` with ℓ = vl_V (no copy of the
definition): an event agrees iff no two of its handling units have different locations ≠ ⊥. The metrics
compare it with the agreement under the high-level location function \\hat{hl}:

| metric | column | definition | better |
|---|---|---|---|
| p^e_agr | n_agreeing, n_events, p_agr | \\|E_t^+(vl_V)\\| / \\|E\\| | ↑ |
| N^e_agr,lost | n_agr_lost | \\|E_t^+(\\hat{hl}) \\ E_t^+(vl_V)\\|, events the mapping breaks | ↓ |
| N^e_agr,gain | n_agr_gain | \\|E_t^+(vl_V) \\ E_t^+(\\hat{hl})\\|, events the mapping repairs | ↑ |

E = the events with at least one hu relation (in the given relations).
"""

import polars as pl

from ..derivation import columns as c
from ..derivation.agreement import event_agreement
from . import columns as v
from .sequence import expand_intervals

#: Column of vl_V in the relations.
VISIT_LOCATION = "vl"
#: Columns of `agreement_changes`.
AGREEING_HIGH_LEVEL = "agreeing_high_level"
AGREEING_VISIT_LOCATION = "agreeing_vl"
CHANGE = "change"
LOST = "lost"
GAINED = "gained"
#: Columns of `agreement_metrics`.
AGREEMENT_METRIC_COLUMNS = [
    "n_events",
    "n_agreeing",
    "p_agr",
    "n_agr_lost",
    "n_agr_gain",
]


def visit_location(
    relations: pl.DataFrame,
    visits: pl.DataFrame,
    name: str = VISIT_LOCATION,
) -> pl.DataFrame:
    """The visit mapping vl_V: every relation gets the high-level location of the unique visit containing it.

    Args:
        relations: The relations with hu and position (further columns are kept).
        visits: A disjoint and covering set of visits with hu, high_level, first_position, last_position
            (e.g. `MappingAnalysis.mapping`, or `properties.with_positions` of a hand-written set).
        name: Name of the new column.

    Returns:
        pl.DataFrame: `relations` with the column `name` (null = ⊥, for the relations of ⊥ visits), in the
        order of `relations`.

    Raises:
        ValueError: If a relation lies in several visits (V not disjoint, e.g. V_max) or in none (V not
            covering); the message names up to five such relations.
    """
    expanded = expand_intervals(
        visits.select(c.HU, v.HIGH_LEVEL, v.FIRST_POSITION, v.LAST_POSITION)
    ).select(c.HU, v.POSITION, pl.col(v.HIGH_LEVEL).alias(name))
    counts = expanded.group_by(c.HU, v.POSITION).len()
    several = counts.filter(pl.col("len") > 1)
    if several.height:
        raise ValueError(
            "vl_V needs a disjoint set of visits; relations in several visits (hu, position): "
            f"{several.sort(c.HU, v.POSITION).head(5).select(c.HU, v.POSITION).rows()}"
        )
    out = relations.join(
        expanded, on=[c.HU, v.POSITION], how="left", maintain_order="left"
    )
    covered = relations.join(counts, on=[c.HU, v.POSITION], how="anti")
    if covered.height:
        raise ValueError(
            "vl_V needs a covering set of visits; relations in no visit (hu, event): "
            f"{covered.head(5).select(c.HU, c.EVENT).rows()}"
        )
    return out


def agreement_changes(
    relations: pl.DataFrame,
    visits: pl.DataFrame,
    high_level: str = v.HIGH_LEVEL,
) -> pl.DataFrame:
    """Agreement of every event under \\hat{hl} and under vl_V, and whether the mapping breaks or repairs it.

    Args:
        relations: The relations with hu, event, time, position and `high_level`.
        visits: A disjoint and covering set of visits (see `visit_location`).
        high_level: Column of \\hat{hl}.

    Returns:
        pl.DataFrame: One row per event of E (events with at least one relation), in the order of time: event,
        agreeing_high_level, agreeing_vl, change ("lost" = agreeing under \\hat{hl} only, "gained" =
        under vl_V only, null = unchanged).
    """
    located = visit_location(relations, visits)
    events = relations.sort(c.TIME, c.EVENT).select(c.EVENT).unique(maintain_order=True)
    before = event_agreement(relations, events, high_level).select(
        c.EVENT, pl.col("agreeing").alias(AGREEING_HIGH_LEVEL)
    )
    after = event_agreement(located, events, VISIT_LOCATION).select(
        c.EVENT, pl.col("agreeing").alias(AGREEING_VISIT_LOCATION)
    )
    a, b = pl.col(AGREEING_HIGH_LEVEL), pl.col(AGREEING_VISIT_LOCATION)
    return before.join(after, on=c.EVENT, maintain_order="left").with_columns(
        pl.when(a & ~b)
        .then(pl.lit(LOST))
        .when(~a & b)
        .then(pl.lit(GAINED))
        .alias(CHANGE)
    )


def agreement_metrics(changes: pl.DataFrame) -> pl.DataFrame:
    """p^e_agr, N^e_agr,lost and N^e_agr,gain of `agreement_changes` (pooled over its events).

    Args:
        changes: Output of `agreement_changes` (possibly filtered to some events).

    Returns:
        pl.DataFrame: One row with `AGREEMENT_METRIC_COLUMNS`; p_agr is null without events.
    """
    return (
        changes.select(
            pl.len().cast(pl.Int64).alias("n_events"),
            pl.col(AGREEING_VISIT_LOCATION).sum().cast(pl.Int64).alias("n_agreeing"),
            (pl.col(CHANGE) == LOST).sum().cast(pl.Int64).alias("n_agr_lost"),
            (pl.col(CHANGE) == GAINED).sum().cast(pl.Int64).alias("n_agr_gain"),
        )
        .with_columns(
            pl.when(pl.col("n_events") > 0)
            .then(pl.col("n_agreeing") / pl.col("n_events"))
            .alias("p_agr")
        )
        .select(AGREEMENT_METRIC_COLUMNS)
    )


def changed_events(changes: pl.DataFrame, change: str) -> list[str]:
    """The event ids with the given change ("lost" or "gained"), in the order of `changes` (time).

    Args:
        changes: Output of `agreement_changes`.
        change: `LOST` or `GAINED`.

    Returns:
        list[str]: e.g. ["e8"].
    """
    return changes.filter(pl.col(CHANGE) == change)[c.EVENT].to_list()
