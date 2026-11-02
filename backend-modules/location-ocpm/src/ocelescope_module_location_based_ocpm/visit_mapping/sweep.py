"""The sweep along one trace with a local rule (working note, sections 3.3 to 3.6 and 5.1).

Per handling unit, start at the first position p. Take the maximal visit m(p) at the relation's own
high-level location and walk along it from p. At each excursion ξ of m(p) that starts after p, a rule
decides: absorb (the visit continues across ξ) or split (the visit ends before ξ). The segment from p to
where the walk stopped (the end of m(p) if everything was absorbed) is one visit of V_map; continue at the
position after it.

The result is always disjoint and covering (the segments partition the trace), and every mapping set can be
produced by some sequence of decisions (working note 4.3). A local strategy is therefore just a rule.

How to add a rule: write a function `rule(step: SweepStep) -> bool` (True = absorb) and pass it to
`sweep_trace`, or register it in `strategies.py`.
"""

from collections.abc import Callable
from dataclasses import dataclass

from .traces import MaximalVisit, Trace


@dataclass(frozen=True)
class Segment:
    """One visit of the mapping set, with 0-based positions.

    Attributes:
        first: Position of its first relation.
        last: Position of its last relation.
        high_level: Its high-level location (None = ⊥).
        maximal_visit_id: Id of the maximal visit m(first) it lies in.
    """

    first: int
    last: int
    high_level: str | None
    maximal_visit_id: int


@dataclass(frozen=True)
class SweepStep:
    """What a rule can look at when the sweep meets an excursion.

    Attributes:
        trace: The trace.
        current: The current visit m(p).
        entry: The position p where the sweep entered the current visit (need not be its first position).
        start: First position of the excursion ξ.
        end: Last position of ξ.
    """

    trace: Trace
    current: MaximalVisit
    entry: int
    start: int
    end: int

    @property
    def positions(self) -> range:
        """Positions of the relations of ξ."""
        return range(self.start, self.end + 1)

    @property
    def inner_visits(self) -> list[MaximalVisit]:
        """The inner visits {m(e) | e ∈ set(ξ)}, in the order of their first position."""
        found = {self.trace.maximal[p].visit_id: self.trace.maximal[p] for p in self.positions}
        return sorted(found.values(), key=lambda m: m.first)


#: A local rule: True = absorb the excursion, False = split before it.
Rule = Callable[[SweepStep], bool]


def excursions(trace: Trace, visit: MaximalVisit, after: int) -> list[tuple[int, int]]:
    """The excursions of a maximal visit that start after a position.

    An excursion is a maximal run of relations not at the visit's high-level location, strictly inside it.

    Args:
        trace: The trace.
        visit: A maximal visit of the trace.
        after: Only excursions starting after this position.

    Returns:
        list[tuple[int, int]]: (first, last) position of each excursion, in trace order.
    """
    out = []
    start = None
    for p in range(after + 1, visit.last + 1):
        if not trace.at(p, visit.high_level):
            start = p if start is None else start
        elif start is not None:
            out.append((start, p - 1))
            start = None
    return out


def sweep_trace(trace: Trace, rule: Rule) -> list[Segment]:
    """Segment one trace with a local rule.

    Args:
        trace: The trace of one handling unit (`traces.split_traces`).
        rule: Decides each excursion the sweep meets (see `SweepStep`).

    Returns:
        list[Segment]: The visits of V_map(hu), in trace order; they partition the trace.
    """
    segments = []
    p = 0
    while p < len(trace):
        current = trace.maximal[p]
        q = current.last
        for start, end in excursions(trace, current, p):
            if not rule(SweepStep(trace, current, p, start, end)):
                q = start - 1
                break
        segments.append(Segment(p, q, current.high_level, current.visit_id))
        p = q + 1
    return segments


def earlier_wins(step: SweepStep) -> bool:
    """S1 earlier wins: absorb every excursion (coarsest result; in an overlap the earlier visit keeps the
    shared part)."""
    return True


def absorb_never(step: SweepStep) -> bool:
    """S2 absorb never: split at every excursion (finest result: the uninterrupted runs, i.e. V_max at
    κ = 0)."""
    return False


def vehicle_only(step: SweepStep) -> bool:
    """S3 vehicle-only: absorb iff all relations of the excursion are on vehicles (loc ∈ V)."""
    return all(step.trace.on_vehicle[p] for p in step.positions)


def later_wins(step: SweepStep) -> bool:
    """S4 later wins: split iff an inner visit overlaps the current one and starts after it (reaches beyond
    its end); otherwise absorb. Contained visits are absorbed as in S1."""
    return not any(
        inner.first > step.current.first and inner.last > step.current.last for inner in step.inner_visits
    )
