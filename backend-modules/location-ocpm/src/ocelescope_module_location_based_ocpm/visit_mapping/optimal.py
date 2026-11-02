"""Global strategies: the best segmentation of a whole trace (working note, sections 5.1 S5 and 6.2 S7, called S6 in Nina's note).

Among all mapping sets of a handling unit (all segmentations of its trace into visits), take the best one by
criteria that are sums over the visits. Because they are sums, a dynamic programme over the positions finds
the optimum: g(i) = best over valid segments [i, q] of c([i, q]) ⊕ g(q + 1), g(n) = 0.

Valid segment [i, q] at h = hat-hl(i): it lies inside the maximal visit m(i), hat-hl(q) = h, and its
neighbours are not at h (i = 0 or hat-hl(i - 1) ≠ h; q = n - 1 or hat-hl(q + 1) ≠ h). Its deviating
infixes are those of m(i), so they respect the tolerance.

Combination of the criteria:
- lexicographic: an ordered list of criteria; the cost is the vector of their (signed) sums, compared in order;
- weighted: one number, the sum of weight × criterion, signed by the criterion's direction (so a positive
  weight always means "good in the criterion's direction").
Ties are broken like S1: the segmentation whose first visit is longest (then the next, and so on).

Optional hard rule `no_sacrifice_to_vehicles` (R1 of the note): a visit at hl ∈ HL without stops must be a
vehicle visit, i.e. it may not take relations at non-vehicle locations; such segments are infeasible. The
uninterrupted runs are always feasible, so there is always a solution.

How to add a criterion: add a `Criterion` to `CRITERIA` (a function of `SegmentStats` and a direction).

Complexity: for every start i all ends q inside m(i) are tried, so O(Σ_i |m(i)|) segment evaluations per
trace, each linear in the segment (straightforward version; prefix sums would make it linear overall).
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

# The kinds are defined once for all visit sets (`visits.properties`); re-exported here for the criteria.
from ..visits.properties import (  # noqa: F401
    BOTTOM_VISIT,
    STAY,
    TRANSFERRING_VISIT,
    VEHICLE_VISIT,
    kind_of,
)
from .sweep import Segment
from .traces import Trace

Direction = Literal["min", "max"]


@dataclass(frozen=True)
class SegmentStats:
    """What a criterion can look at: the counts of one segment.

    Attributes:
        n_relations: |σ|.
        n_at_location: Relations at its hl (conforming).
        n_conforming_processing: Processing relations at its hl (0 for ⊥ visits).
        kind: stay, vehicle visit, transferring visit or ⊥ visit.
        duration_hours: d = time(exit event) - time(first event), in hours (exit event = the next relation of
            the handling unit, or the last relation if the trace ends).
        at_storage_location: True if its hl contains a storage unit (`Trace.storage_high_levels`).
    """

    n_relations: int
    n_at_location: int
    n_conforming_processing: int
    kind: str
    duration_hours: float
    at_storage_location: bool = False


@dataclass(frozen=True)
class Criterion:
    """An additive criterion: a value per segment and the direction in which it is better.

    Attributes:
        value: Function of the segment's `SegmentStats`.
        direction: "min" or "max".
        description: One line for docs and tables.
    """

    value: Callable[[SegmentStats], float]
    direction: Direction
    description: str


#: The available criteria (working note 6.2 and the implementation brief).
CRITERIA: dict[str, Criterion] = {
    "n_visits": Criterion(lambda s: 1, "min", "number of visits"),
    "n_stays": Criterion(
        lambda s: int(s.kind == STAY), "min", "number of stays (visits with a stop)"
    ),
    "n_vehicle_visits": Criterion(
        lambda s: int(s.kind in (VEHICLE_VISIT, TRANSFERRING_VISIT)),
        "min",
        "number of vehicle and transferring visits",
    ),
    "n_nonconforming": Criterion(
        lambda s: s.n_relations - s.n_at_location,
        "min",
        "relations not at their visit's hl",
    ),
    "n_conforming_processing": Criterion(
        lambda s: s.n_conforming_processing,
        "max",
        "processing relations at their visit's hl",
    ),
    "n_storage_stay_relations": Criterion(
        lambda s: s.n_relations if s.kind == STAY and s.at_storage_location else 0,
        "max",
        "relations in stays at a high-level location with a storage unit (storage tie-break)",
    ),
    "duration_sq": Criterion(
        lambda s: s.duration_hours**2,
        "max",
        "squared visit duration in hours (prefers longer visits)",
    ),
}


@dataclass(frozen=True)
class GlobalStrategy:
    """A global strategy: criteria, how they are combined, and the hard rule.

    Attributes:
        criteria: Criterion keys (of `CRITERIA`) in order; a pair (key, direction) overrides the direction.
        mode: "lexicographic" or "weighted".
        weights: Weight per criterion key (only for "weighted"; missing keys weigh 1).
        no_sacrifice_to_vehicles: The hard rule R1.
        name: Shown in tables.
    """

    criteria: Sequence[str | tuple[str, Direction]]
    mode: Literal["lexicographic", "weighted"] = "lexicographic"
    weights: Mapping[str, float] = field(default_factory=dict)
    no_sacrifice_to_vehicles: bool = False
    name: str = "custom"

    def resolved(self) -> list[tuple[str, Criterion, float]]:
        """The criteria as (key, criterion with the effective direction, sign), sign = +1 for min, -1 for max."""
        out = []
        for entry in self.criteria:
            key, direction = (entry, None) if isinstance(entry, str) else entry
            if key not in CRITERIA:
                raise ValueError(
                    f"Unknown criterion {key!r}; use one of {sorted(CRITERIA)}."
                )
            base = CRITERIA[key]
            crit = (
                base
                if direction is None
                else Criterion(base.value, direction, base.description)
            )
            out.append((key, crit, 1.0 if crit.direction == "min" else -1.0))
        return out


def lexicographic(
    criteria: Sequence[str | tuple[str, Direction]],
    no_sacrifice_to_vehicles: bool = False,
    name: str = "custom (lexicographic)",
) -> GlobalStrategy:
    """A custom strategy that compares the criteria in the given order.

    Args:
        criteria: Criterion keys of `CRITERIA` in order of importance, e.g. ["n_stays", "n_nonconforming"];
            a pair ("duration_sq", "min") overrides a direction.
        no_sacrifice_to_vehicles: Hard rule R1 on or off.
        name: Name shown in tables.

    Returns:
        GlobalStrategy: The strategy.
    """
    return GlobalStrategy(
        tuple(criteria), "lexicographic", {}, no_sacrifice_to_vehicles, name
    )


def weighted(
    weights: Mapping[str, float],
    no_sacrifice_to_vehicles: bool = False,
    name: str = "custom (weighted)",
) -> GlobalStrategy:
    """A custom strategy that minimises the weighted sum of the criteria (signed by their directions).

    Args:
        weights: Criterion key -> weight, e.g. {"n_visits": 1, "n_nonconforming": 1.25} (S5).
        no_sacrifice_to_vehicles: Hard rule R1 on or off.
        name: Name shown in tables.

    Returns:
        GlobalStrategy: The strategy.
    """
    return GlobalStrategy(
        tuple(weights), "weighted", dict(weights), no_sacrifice_to_vehicles, name
    )


def segment_stats(trace: Trace, first: int, last: int) -> SegmentStats:
    """The counts of the segment [first, last] of a trace (0-based positions).

    Args:
        trace: The trace.
        first: First position.
        last: Last position.

    Returns:
        SegmentStats: Its counts, kind and duration.
    """
    h = trace.high_levels[first]
    positions = range(first, last + 1)
    at = [p for p in positions if trace.at(p, h)]
    kind = kind_of(
        h,
        has_stop=any(not trace.on_vehicle[p] for p in at),
        has_non_vehicle=any(
            trace.located(p) and not trace.on_vehicle[p] for p in positions
        ),
    )
    exit_position = last + 1 if last + 1 < len(trace) else last
    duration = (trace.times[exit_position] - trace.times[first]).total_seconds() / 3600
    return SegmentStats(
        n_relations=len(positions),
        n_at_location=len(at),
        n_conforming_processing=0
        if h is None
        else sum(trace.is_processing[p] for p in at),
        kind=kind,
        duration_hours=duration,
        at_storage_location=h in trace.storage_high_levels,
    )


def segment_cost(
    stats: SegmentStats, strategy: GlobalStrategy
) -> tuple[float, ...] | None:
    """The cost of one segment under a strategy (lower is better).

    Args:
        stats: The segment's counts (`segment_stats`).
        strategy: The strategy.

    Returns:
        tuple[float, ...] | None: The signed criterion values (lexicographic) or a one-element tuple with the
        weighted sum; None if the hard rule makes the segment infeasible.
    """
    if strategy.no_sacrifice_to_vehicles and stats.kind == TRANSFERRING_VISIT:
        return None
    signed = [
        (key, sign * crit.value(stats)) for key, crit, sign in strategy.resolved()
    ]
    if strategy.mode == "weighted":
        return (sum(strategy.weights.get(key, 1.0) * value for key, value in signed),)
    return tuple(value for _, value in signed)


def _add(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, ...]:
    """Element-wise sum of two cost vectors."""
    return tuple(x + y for x, y in zip(a, b, strict=True))


def _key(cost: tuple[float, ...]) -> tuple[float, ...]:
    """Cost vector rounded for comparisons, so that float sums of equal costs count as ties."""
    return tuple(round(x, 9) for x in cost)


def valid_ends(trace: Trace, first: int) -> list[int]:
    """All q such that [first, q] is a valid segment (see the module docstring); empty if `first` cannot
    start a visit.

    Args:
        trace: The trace.
        first: Candidate first position p.

    Returns:
        list[int]: The valid last positions, ascending.
    """
    h = trace.high_levels[first]
    if first > 0 and trace.at(first - 1, h):
        return []
    visit = trace.maximal[first]
    n = len(trace)
    return [
        q
        for q in range(first, visit.last + 1)
        if trace.at(q, h) and (q == n - 1 or not trace.at(q + 1, h))
    ]


def optimal_segmentation(
    trace: Trace, strategy: GlobalStrategy
) -> tuple[list[Segment], tuple[float, ...]]:
    """The best segmentation of one trace under a global strategy (dynamic programme over the positions).

    Args:
        trace: The trace of one handling unit.
        strategy: The strategy.

    Returns:
        tuple[list[Segment], tuple[float, ...]]: The visits of V_map(hu) in trace order, and the total cost.
    """
    n = len(trace)
    width = 1 if strategy.mode == "weighted" else len(strategy.criteria)
    best: list[tuple[tuple[float, ...], int] | None] = [None] * (n + 1)
    best[n] = (tuple(0.0 for _ in range(width)), n)
    for i in range(n - 1, -1, -1):
        for q in reversed(
            valid_ends(trace, i)
        ):  # longest first: ties keep the longer segment (S1)
            rest = best[q + 1]
            cost = segment_cost(segment_stats(trace, i, q), strategy)
            if rest is None or cost is None:
                continue
            total = _add(cost, rest[0])
            if best[i] is None or _key(total) < _key(best[i][0]):
                best[i] = (total, q)
    if best[0] is None:  # cannot happen: the uninterrupted runs are always feasible
        raise RuntimeError(f"No feasible segmentation for {trace.hu}.")
    segments, i = [], 0
    while i < n:
        q = best[i][1]
        segments.append(Segment(i, q, trace.high_levels[i], trace.maximal[i].visit_id))
        i = q + 1
    return segments, best[0][0]
