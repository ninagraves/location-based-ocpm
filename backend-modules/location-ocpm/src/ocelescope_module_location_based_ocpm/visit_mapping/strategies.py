"""The predefined strategies (working note, sections 5.1 and 6.2) and how a strategy is chosen.

| key | name | kind |
|---|---|---|
| S1 | earlier wins (absorb always) | local rule `sweep.earlier_wins` |
| S2 | absorb never | local rule `sweep.absorb_never` |
| S3 | vehicle-only absorb | local rule `sweep.vehicle_only` |
| S4 | later wins | local rule `sweep.later_wins` |
| S5 | cost-optimal: n_visits + λ · n_nonconforming | global, weighted (`cost_optimal(lam)`) |
| S6 | integrating domain knowledge (S7 in the working note) | global, lexicographic with the hard rule (`domain_knowledge(storage_tie_break)`) |

"S7" is accepted as an alias of "S6" (the working note numbered it S7; Nina's note calls it S6).
A strategy argument can be one of these keys, a local rule (a function `SweepStep -> bool`), or a
`optimal.GlobalStrategy` (e.g. from `optimal.lexicographic` or `optimal.weighted`: the custom strategies).
"""

from collections.abc import Callable
from dataclasses import dataclass

from .optimal import GlobalStrategy, lexicographic, optimal_segmentation, weighted
from .sweep import (
    Rule,
    Segment,
    absorb_never,
    earlier_wins,
    later_wins,
    sweep_trace,
    vehicle_only,
)
from .traces import Trace

#: Default λ of S5 (Nina, 2026-11-02): 0.5, with ties broken in favour of longer earlier visits; on the running
#: example this gives the same optima as λ = 0, i.e. exactly S1 (ties in b7, b8). λ ∈ [1.1, 1.4] hits all targets
#: except b6, λ < 1 all except b8 (working note 5.2).
DEFAULT_LAMBDA = 0.5

#: The criteria of S6 in order (working note 6.2, there called S7), with the hard rule R1. The storage
#: tie-break (Nina, 2026-11-02) comes before the durations and can be switched off (`domain_knowledge`).
S6_CRITERIA = (
    "n_conforming_processing",
    "n_stays",
    "n_nonconforming",
    "n_vehicle_visits",
    "n_storage_stay_relations",
    "duration_sq",
)


def cost_optimal(lam: float = DEFAULT_LAMBDA) -> GlobalStrategy:
    """S5 cost-optimal segmentation: minimise number of visits + λ · number of non-conforming relations.

    Args:
        lam: λ ≥ 0, the cost of an absorbed (non-conforming) relation relative to one more visit.

    Returns:
        GlobalStrategy: The weighted strategy.
    """
    return weighted(
        {"n_visits": 1.0, "n_nonconforming": lam}, name=f"S5 cost-optimal (λ = {lam:g})"
    )


def domain_knowledge(storage_tie_break: bool = True) -> GlobalStrategy:
    """S6 integrating domain knowledge: hard rule R1, then lexicographically max conforming processing,
    min stays, min non-conforming relations, min vehicle visits, (storage tie-break) max relations in stays
    at high-level locations with a storage unit, max Σ d².

    Args:
        storage_tie_break: Use the storage tie-break (Nina, 2026-11-02; default True). It decides ties such
            as b7 (then (A e26) (B e31–e34)) and x2 (then A B B B B B) in favour of the stay at the high-level
            location with storage units; without it, the longer visit wins.

    Returns:
        GlobalStrategy: The lexicographic strategy.
    """
    criteria = (
        S6_CRITERIA
        if storage_tie_break
        else tuple(k for k in S6_CRITERIA if k != "n_storage_stay_relations")
    )
    name = (
        "S6 domain knowledge"
        if storage_tie_break
        else "S6 domain knowledge (no storage tie-break)"
    )
    return lexicographic(criteria, no_sacrifice_to_vehicles=True, name=name)


@dataclass(frozen=True)
class LocalStrategy:
    """A local strategy: a named rule for the sweep.

    Attributes:
        rule: The rule (True = absorb).
        name: Shown in tables.
    """

    rule: Rule
    name: str


#: The predefined strategies by key.
STRATEGIES: dict[str, Callable[[], LocalStrategy | GlobalStrategy]] = {
    "S1": lambda: LocalStrategy(earlier_wins, "S1 earlier wins"),
    "S2": lambda: LocalStrategy(absorb_never, "S2 absorb never"),
    "S3": lambda: LocalStrategy(vehicle_only, "S3 vehicle-only"),
    "S4": lambda: LocalStrategy(later_wins, "S4 later wins"),
    "S5": cost_optimal,
    "S6": domain_knowledge,
}

#: Other names of strategy keys.
ALIASES = {"S7": "S6"}

#: A strategy argument: a key of STRATEGIES, a rule, a LocalStrategy or a GlobalStrategy.
StrategyLike = str | Rule | LocalStrategy | GlobalStrategy


def resolve_strategy(strategy: StrategyLike) -> LocalStrategy | GlobalStrategy:
    """Turn a strategy argument into a strategy object.

    Args:
        strategy: A key of `STRATEGIES` ("S1" to "S6", or the alias "S7"), a local rule, or a strategy object.

    Returns:
        LocalStrategy | GlobalStrategy: The strategy.
    """
    if isinstance(strategy, LocalStrategy | GlobalStrategy):
        return strategy
    if isinstance(strategy, str):
        strategy = ALIASES.get(strategy, strategy)
        if strategy not in STRATEGIES:
            raise ValueError(
                f"Unknown strategy {strategy!r}; use one of {sorted(STRATEGIES)}."
            )
        return STRATEGIES[strategy]()
    if callable(strategy):
        return LocalStrategy(strategy, getattr(strategy, "__name__", "custom rule"))
    raise TypeError(f"Not a strategy: {strategy!r}")


def strategy_name(strategy: StrategyLike) -> str:
    """The display name of a strategy argument."""
    return resolve_strategy(strategy).name


def segment_trace(trace: Trace, strategy: StrategyLike) -> list[Segment]:
    """Segment one trace with any strategy.

    Args:
        trace: The trace of one handling unit.
        strategy: See `resolve_strategy`.

    Returns:
        list[Segment]: The visits of V_map(hu), in trace order.
    """
    resolved = resolve_strategy(strategy)
    if isinstance(resolved, LocalStrategy):
        return sweep_trace(trace, resolved.rule)
    return optimal_segmentation(trace, resolved)[0]
