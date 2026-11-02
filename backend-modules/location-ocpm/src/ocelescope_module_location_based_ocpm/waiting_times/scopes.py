"""The scopes in which waiting times are measured: visits, or whole traces (DD-W6 in
`overview/concepts/Visit Mappings.md`).

- **With visits** (default of the concept): every visit ν = (hu, hl, σ) with hl ∈ HL is a scope; visits at
  ⊥ get no waiting times (DD-W7). The clock starts at the entry into hl, and only processing operations at
  hl count.
- **Without visits**: the whole trace of a handling unit is one scope, σ = otrace(hu), without a high-level
  location. The clock starts at its first event; only processing operations and (if selected) storage
  removals reset it; every located processing operation counts.

A scope frame has the columns of a visits frame that the waiting functions need: visit_id, hu, high_level
(null for a whole trace), first_position, last_position, first_event, last_event, exit_event, entry_time,
exit_time, ends_trace and duration. `scope_relations` gives one row per scope and relation, like
`visits.maximal.visit_relations`, with at_location = "counts for this scope".
"""

import polars as pl

from ..derivation import columns as c
from ..visits import columns as v
from ..visits.context import Frame
from ..visits.maximal import visit_relations

#: Columns of a scope frame, in this order.
SCOPE_COLUMNS = [
    v.VISIT_ID,
    c.HU,
    v.HIGH_LEVEL,
    v.FIRST_POSITION,
    v.LAST_POSITION,
    v.FIRST_EVENT,
    v.LAST_EVENT,
    v.EXIT_EVENT,
    v.ENTRY_TIME,
    v.EXIT_TIME,
    v.ENDS_TRACE,
    v.DURATION,
]


def visit_scopes(visits: Frame) -> Frame:
    """The visits at hl ∈ HL as scopes (DD-W7: visits at ⊥ get no waiting times).

    Args:
        visits: One row per visit, e.g. `VisitAnalysis.visits` or `maximal.maximal_visits` (any set of
            visits with the columns of `SCOPE_COLUMNS`).

    Returns:
        Frame: The scope columns of the visits with a high-level location, sorted by visit_id.
    """
    return visits.filter(pl.col(v.HIGH_LEVEL).is_not_null()).select(SCOPE_COLUMNS).sort(v.VISIT_ID)


def trace_scopes(relations: Frame) -> Frame:
    """Every whole trace as one scope (DD-W6, no visits): σ = otrace(hu), no high-level location.

    The scope ends with the trace, so its exit event is its last event (ends_trace is true) and its
    duration is the time from the first to the last event. visit_id numbers the handling units 1, 2, ...
    in sorted order.

    Args:
        relations: One row per hu-event relation with columns hu, event, time, position.

    Returns:
        Frame: One row per handling unit with the columns of `SCOPE_COLUMNS`, sorted by visit_id.
    """
    return (
        relations.group_by(c.HU)
        .agg(
            pl.col(v.POSITION).min().alias(v.FIRST_POSITION),
            pl.col(v.POSITION).max().alias(v.LAST_POSITION),
            pl.col(c.EVENT).sort_by(v.POSITION).first().alias(v.FIRST_EVENT),
            pl.col(c.EVENT).sort_by(v.POSITION).last().alias(v.LAST_EVENT),
            pl.col(c.TIME).sort_by(v.POSITION).first().alias(v.ENTRY_TIME),
            pl.col(c.TIME).sort_by(v.POSITION).last().alias(v.EXIT_TIME),
        )
        .with_columns(
            pl.col(c.HU).rank("dense").cast(pl.Int64).alias(v.VISIT_ID),
            pl.lit(None, dtype=pl.String).alias(v.HIGH_LEVEL),
            pl.col(v.LAST_EVENT).alias(v.EXIT_EVENT),
            pl.lit(True).alias(v.ENDS_TRACE),
            (pl.col(v.EXIT_TIME) - pl.col(v.ENTRY_TIME)).alias(v.DURATION),
        )
        .select(SCOPE_COLUMNS)
        .sort(v.VISIT_ID)
    )


def scope_relations(relations: Frame, scopes: Frame, location: str = "loc") -> Frame:
    """One row per scope and relation of its σ, with at_location = the relation counts for the scope.

    For a visit, at_location is hat-hl(r) = hl (as in `visits.maximal.visit_relations`); for a whole trace
    (high_level null), it is loc(r) ≠ ⊥.

    Args:
        relations: One row per hu-event relation with columns hu, event, time, position, `location` (and
            high_level for visits; it is added as null if missing).
        scopes: Output of `visit_scopes` or `trace_scopes`.
        location: Column of loc (null = ⊥).

    Returns:
        Frame: The relation columns plus visit_id, visit_high_level, first_position, last_position and
        at_location, sorted by visit_id and position.
    """
    if v.HIGH_LEVEL not in relations.collect_schema().names():
        relations = relations.with_columns(pl.lit(None, dtype=pl.String).alias(v.HIGH_LEVEL))
    return visit_relations(relations, scopes).with_columns(
        pl.when(pl.col(v.VISIT_HIGH_LEVEL).is_null())
        .then(pl.col(location).is_not_null())
        .otherwise(pl.col(v.AT_LOCATION))
        .alias(v.AT_LOCATION)
    )
