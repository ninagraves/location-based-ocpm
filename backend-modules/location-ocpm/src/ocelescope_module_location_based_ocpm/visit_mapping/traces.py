"""The input of the mapping strategies for one handling unit: its trace and its maximal visits.

The strategies work on one trace at a time (`otrace(hu)` in AS4 order), so the relations and the maximal
visits are split into one `Trace` per handling unit. Positions inside a `Trace` start at 0 (Python lists);
the frames use positions starting at 1, as the visit functions do.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime

import polars as pl

from ..derivation import columns as c
from ..visits import columns as v
from ..visits.order import processing_flag

#: Column of the relations: loc ∈ V (false for ⊥).
ON_VEHICLE = v.ON_VEHICLE
#: Column of the relations: e ∈ P, wherever it happens.
IS_PROCESSING_EVENT = v.IS_PROCESSING_EVENT


@dataclass(frozen=True)
class MaximalVisit:
    """A maximal visit of the trace, with 0-based positions.

    Attributes:
        visit_id: Its id in the maximal visits frame.
        high_level: Its high-level location hl (None = ⊥).
        first: Position of its first relation.
        last: Position of its last relation.
    """

    visit_id: int
    high_level: str | None
    first: int
    last: int


@dataclass
class Trace:
    """The trace of one handling unit, as lists indexed by the 0-based position.

    Attributes:
        hu: The handling unit.
        events: Event ids.
        times: Timestamps.
        locations: Low-level locations loc (None = ⊥).
        high_levels: High-level locations hat-hl (None = ⊥).
        on_vehicle: loc ∈ V.
        is_processing: e ∈ P (wherever it happens).
        maximal: The maximal visit m(p) at the relation's own high-level location, per position.
        visits: All maximal visits of the trace, by visit id.
        storage_high_levels: High-level locations that contain a storage unit, {agg(w) | w ∈ W} (for the
            storage tie-break of S6).
    """

    hu: str
    events: list[str]
    times: list[datetime]
    locations: list[str | None]
    high_levels: list[str | None]
    on_vehicle: list[bool]
    is_processing: list[bool]
    maximal: list[MaximalVisit]
    visits: dict[int, MaximalVisit]
    storage_high_levels: frozenset[str] = frozenset()

    def __len__(self) -> int:
        """Number of relations n of the trace."""
        return len(self.events)

    def at(self, position: int, high_level: str | None) -> bool:
        """True if the relation at `position` is at `high_level` (⊥ = ⊥ counts as true)."""
        return self.high_levels[position] == high_level

    def located(self, position: int) -> bool:
        """True if the relation at `position` has a location (loc ≠ ⊥)."""
        return self.locations[position] is not None


def add_mapping_inputs(
    relations: pl.DataFrame | pl.LazyFrame,
    vehicles: Collection[str] = (),
    processing: Collection[str] | None = None,
    location: str = "loc",
) -> pl.DataFrame | pl.LazyFrame:
    """Add the columns on_vehicle (loc ∈ V) and is_processing_event (e ∈ P) to the relations.

    Args:
        relations: Relations with the columns event and `location` (and is_transformation if `processing`
            is None), e.g. the relations of `visits.maximal.derive_maximal_visits`.
        vehicles: The set V.
        processing: The processing operations P as event ids; None = the transformation events T.
        location: Column of loc (null = ⊥).

    Returns:
        Frame: `relations` with the two columns (both false for ⊥ / missing values).
    """
    return relations.with_columns(
        pl.col(location).is_in(list(vehicles)).fill_null(False).alias(ON_VEHICLE),
        processing_flag(processing).alias(IS_PROCESSING_EVENT),
    )


def storage_high_levels(storage_units: Collection[str], agg: Mapping[str, str] | None = None) -> set[str]:
    """The high-level locations that contain a storage unit: {agg(w) | w ∈ W} (agg completed by identity).

    Args:
        storage_units: The set W.
        agg: Location mapping L -> HL (partial); None = identity.

    Returns:
        set[str]: The high-level locations.
    """
    agg = agg or {}
    return {agg.get(w, w) for w in storage_units}


def split_traces(
    relations: pl.DataFrame,
    visits: pl.DataFrame,
    location: str = "loc",
    handling_units: Collection[str] | None = None,
    storage_high_levels: Collection[str] = (),
) -> list[Trace]:
    """One `Trace` per handling unit.

    Args:
        relations: Output of `add_mapping_inputs` on the relations of `derive_maximal_visits` (columns hu,
            event, time, position, high_level, visit_id, on_vehicle, is_processing_event and `location`).
        visits: The maximal visits (columns visit_id, high_level, first_position, last_position).
        location: Column of loc.
        handling_units: Only these handling units; None = all.
        storage_high_levels: High-level locations containing a storage unit (`storage_high_levels`).

    Returns:
        list[Trace]: Sorted by handling unit.
    """
    if handling_units is not None:
        relations = relations.filter(pl.col(c.HU).is_in(list(handling_units)))
    by_id = {
        row[v.VISIT_ID]: row
        for row in visits.select(v.VISIT_ID, v.HIGH_LEVEL, v.FIRST_POSITION, v.LAST_POSITION).iter_rows(named=True)
    }
    traces = []
    for (hu,), part in relations.sort(c.HU, v.POSITION).group_by(c.HU, maintain_order=True):
        ids = part[v.VISIT_ID].to_list()
        own = {
            i: MaximalVisit(
                i, by_id[i][v.HIGH_LEVEL], by_id[i][v.FIRST_POSITION] - 1, by_id[i][v.LAST_POSITION] - 1
            )
            for i in set(ids)
        }
        traces.append(
            Trace(
                hu=hu,
                events=part[c.EVENT].to_list(),
                times=part[c.TIME].to_list(),
                locations=part[location].to_list(),
                high_levels=part[v.HIGH_LEVEL].to_list(),
                on_vehicle=part[ON_VEHICLE].to_list(),
                is_processing=part[IS_PROCESSING_EVENT].to_list(),
                maximal=[own[i] for i in ids],
                visits=own,
                storage_high_levels=frozenset(storage_high_levels),
            )
        )
    return traces
