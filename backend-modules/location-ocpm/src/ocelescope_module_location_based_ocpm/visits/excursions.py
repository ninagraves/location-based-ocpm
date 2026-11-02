"""Excursions of visits (concept note `overview/concepts/Visit Mappings.md`, "Visits", excursion).

An excursion of ν = (hu, hl, σ) is a maximal infix ξ = σ[a:b] of non-conforming relations strictly inside σ
(1 < a ≤ b < |σ|): its neighbours σ[a-1] and σ[b+1] are at hl. Its excursion locations are
{hat-hl(e) | e ∈ set(ξ)} (⊥ written as "⊥").

Works for any set of visits (maximal visits, visits of a mapping set, hand-written ones) given its visit
relations; built on the run helper `sequence.runs`. The sweep of the mapping strategies takes the
excursions of the maximal visits from here (`visit_mapping.traces.split_traces`).
"""

import polars as pl

from ..derivation import columns as c
from . import columns as v
from .context import Frame
from .sequence import LENGTH, runs

#: Columns of the excursion table.
EXCURSION = "excursion"
EXCURSION_LENGTH = "excursion_length"
EXCURSION_LOCATIONS = "excursion_locations"
#: How ⊥ is written in the excursion locations.
BOTTOM = "⊥"


def excursions(visit_relations: Frame) -> Frame:
    """One row per excursion ξ of every visit.

    How it works: the runs of equal at_location per visit (`sequence.runs`) are taken; an excursion is a
    run with at_location false that neither starts at the visit's first nor ends at its last position.

    Args:
        visit_relations: Output of `maximal.visit_relations` (visit_id, hu, position, event, high_level,
            first_position, last_position, at_location).

    Returns:
        Frame: visit_id, hu, excursion (1, 2, ... per visit), first_position, last_position, first_event,
        last_event, excursion_length (number of relations), excursion_locations (sorted list of the
        high-level locations, ⊥ as "⊥"); sorted by visit_id and excursion.
    """
    bounds = visit_relations.group_by(v.VISIT_ID).agg(
        pl.col(v.POSITION).min().alias("_visit_first"),
        pl.col(v.POSITION).max().alias("_visit_last"),
    )
    found = runs(
        visit_relations,
        v.AT_LOCATION,
        group=[v.VISIT_ID, c.HU],
        keep=lambda value: ~value,
        aggregations=[
            pl.col(c.EVENT).sort_by(v.POSITION).first().alias(v.FIRST_EVENT),
            pl.col(c.EVENT).sort_by(v.POSITION).last().alias(v.LAST_EVENT),
            pl.col(v.HIGH_LEVEL)
            .fill_null(BOTTOM)
            .unique()
            .sort()
            .alias(EXCURSION_LOCATIONS),
        ],
    )
    return (
        found.join(bounds, on=v.VISIT_ID)
        .filter(
            (pl.col(v.FIRST_POSITION) > pl.col("_visit_first"))
            & (pl.col(v.LAST_POSITION) < pl.col("_visit_last"))
        )
        .sort(v.VISIT_ID, v.FIRST_POSITION)
        .with_columns(
            (pl.int_range(pl.len()).over(v.VISIT_ID) + 1)
            .cast(pl.Int64)
            .alias(EXCURSION)
        )
        .select(
            v.VISIT_ID,
            c.HU,
            EXCURSION,
            v.FIRST_POSITION,
            v.LAST_POSITION,
            v.FIRST_EVENT,
            v.LAST_EVENT,
            pl.col(LENGTH).alias(EXCURSION_LENGTH),
            EXCURSION_LOCATIONS,
        )
    )


def excursion_counts(visits: Frame, excursions_frame: Frame) -> Frame:
    """Per visit: n_excursions = |Ξ(ν)| (0 for uninterrupted visits).

    Args:
        visits: One row per visit with visit_id.
        excursions_frame: Output of `excursions`.

    Returns:
        Frame: visit_id, n_excursions.
    """
    counts = excursions_frame.group_by(v.VISIT_ID).agg(
        pl.len().cast(pl.Int64).alias("n_excursions")
    )
    return (
        visits.select(v.VISIT_ID)
        .join(counts, on=v.VISIT_ID, how="left")
        .with_columns(pl.col("n_excursions").fill_null(0))
    )
