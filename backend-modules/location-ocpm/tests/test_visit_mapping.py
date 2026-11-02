"""Tests of visit mapping sets (`visit_mapping` package) on the extended running example and the extra
traces in data/mapping_example/ (κ_max = 3, V = {T}, W = {B1}): the results of the working note
`claude_notes/visit-mapping-sets.md` (sections 5.2, 6.6, 6.8, 7.3) and Nina's target resolutions (4.1)."""

from datetime import timedelta
from itertools import pairwise
from pathlib import Path

import polars as pl
import pytest

from ocelescope_module_location_based_ocpm.derivation.level_files import MAPPING_SCHEMA
from ocelescope_module_location_based_ocpm.visit_mapping.metrics import mapping_metrics
from ocelescope_module_location_based_ocpm.visit_mapping.optimal import (
    lexicographic,
    optimal_segmentation,
    segment_cost,
    segment_stats,
    valid_ends,
    weighted,
)
from ocelescope_module_location_based_ocpm.visit_mapping.pipeline import (
    compare_strategies,
    derive_mapping_set,
)
from ocelescope_module_location_based_ocpm.visit_mapping.strategies import (
    DEFAULT_LAMBDA,
    STRATEGIES,
    cost_optimal,
    domain_knowledge,
)
from ocelescope_module_location_based_ocpm.visit_mapping.traces import split_traces
from ocelescope_module_location_based_ocpm.visits.context import location_context

DATA = Path(__file__).parents[3] / "data" / "mapping_example"
RELATIONS = pl.read_csv(DATA / "relations.csv", schema=MAPPING_SCHEMA)
EXTRA = pl.read_csv(DATA / "extra_relations.csv", schema=MAPPING_SCHEMA)
CONTEXT = location_context(pl.read_csv(DATA / "locations.csv"))
P = pl.read_csv(DATA / "processing_events.csv")["event"].to_list()
KAPPA = 3
OPTIONS = {
    "location": "loc",
    "agg": CONTEXT.agg,
    "vehicles": CONTEXT.vehicles,
    "kappa": KAPPA,
    "processing": P,
    "storage_units": CONTEXT.storage_units,
}

#: Nina's targets (working note 4.1); s1, b3, b5 keep their maximal visits.
TARGETS = {
    "s1": "(A e1-e3)",
    "b1": "(A e3-e11) (T e13-e14)",
    "b2": "(A e3-e11) (B e12-e15)",
    "b3": "(T e8-e8) (B e10-e14)",
    "b4": "(B e15-e21)",
    "b5": "(⊥ e16-e17)",
    "s2": "(A e22-e26)",
    "b6": "(A e26-e30)",
    "b7": "(A e26-e33) (B e34-e34)",  # option 1; option 2 (A e26-e26) (B e31-e34) is fine too
    "b8": "(A e35-e37) (T e38-e38) (B e39-e41)",
}
B7_OPTION_2 = "(A e26-e26) (B e31-e34)"


def sequences(mapping: pl.DataFrame) -> dict[str, str]:
    """hu -> its visit sequence as text, e.g. "(A e3-e11) (T e13-e14)"."""
    text = pl.format(
        "({} {}-{})", pl.col("high_level").fill_null("⊥"), "first_event", "last_event"
    )
    rows = (
        mapping.sort("hu", "first_position")
        .group_by("hu", maintain_order=True)
        .agg(text.str.join(" "))
    )
    return dict(rows.rows())


def letters(analysis) -> dict[str, str]:
    """hu -> the high-level location of every relation in V_map, e.g. "ATBTA"."""
    expanded = analysis.mapping.join(
        analysis.relations.select("hu", "position"), on="hu"
    ).filter(pl.col("position").is_between("first_position", "last_position"))
    rows = expanded.group_by("hu").agg(
        pl.col("high_level").fill_null("⊥").sort_by("position").str.join("")
    )
    return dict(rows.rows())


@pytest.fixture(scope="module")
def analyses():
    """All six predefined strategies on the running example."""
    return compare_strategies(RELATIONS, tuple(STRATEGIES), **OPTIONS)[1]


def by_key(analyses, key: str):
    """The analysis of a strategy key ("S1", ...)."""
    name = STRATEGIES[key]().name
    return analyses[name]


def test_s6_hits_all_targets(analyses):
    # the storage tie-break (default) takes option 2 of b7: the stay at B, which has the storage unit B1
    assert sequences(by_key(analyses, "S6").mapping) == {**TARGETS, "b7": B7_OPTION_2}


def test_s6_without_storage_tie_break_takes_the_longer_visit():
    result = derive_mapping_set(
        RELATIONS, **OPTIONS, strategy=domain_knowledge(storage_tie_break=False)
    )
    assert sequences(result.mapping) == TARGETS
    extra = derive_mapping_set(
        EXTRA, **OPTIONS, strategy=domain_knowledge(storage_tie_break=False)
    )
    assert letters(extra)["x2"] == "AAAAAB"


def test_s5_default_equals_s1(analyses):
    """Default λ = 0.5 (Nina, 2026-11-02) gives the same optima as λ = 0, i.e. S1 on the running example."""
    assert DEFAULT_LAMBDA == 0.5
    assert cost_optimal().name == "S5 cost-optimal (λ = 0.5)"
    assert sequences(by_key(analyses, "S5").mapping) == sequences(
        by_key(analyses, "S1").mapping
    )


def test_s1_misses_only_b8(analyses):
    result = sequences(by_key(analyses, "S1").mapping)
    assert {hu for hu in TARGETS if result[hu] != TARGETS[hu]} == {"b8"}
    assert result["b8"] == "(A e35-e40) (B e41-e41)"


def test_s4_later_wins(analyses):
    result = sequences(by_key(analyses, "S4").mapping)
    assert result["b1"] == "(A e3-e5) (B e7-e7) (T e8-e14)"
    assert result["b8"] == "(A e35-e35) (B e36-e41)"
    assert result["b7"] == B7_OPTION_2
    assert {hu for hu in TARGETS if result[hu] != TARGETS[hu]} == {"b1", "b7", "b8"}


def test_s3_hits_only_b2_and_s2_none(analyses):
    s3 = sequences(by_key(analyses, "S3").mapping)
    s2 = sequences(by_key(analyses, "S2").mapping)
    changed = {
        "b1",
        "b2",
        "b4",
        "s2",
        "b6",
        "b7",
        "b8",
    }  # the hus with non-disjoint maximal visits
    assert {hu for hu in changed if s3[hu] == TARGETS[hu]} == {"b2"}
    assert {hu for hu in changed if s2[hu] == TARGETS[hu]} == set()
    assert s2["b8"].count("(") == 7


def test_s2_gives_the_uninterrupted_runs(analyses):
    s2 = by_key(analyses, "S2").mapping
    assert not s2["interrupted"].any()
    kappa0 = derive_mapping_set(
        RELATIONS, **{**OPTIONS, "kappa": 0}, strategy="S1"
    ).mapping
    assert sequences(s2) == sequences(kappa0)


@pytest.mark.parametrize(
    ("lam", "misses"),
    [(0.9, {"b8"}), (1.0, {"b8"}), (1.1, {"b6"}), (1.25, {"b6"}), (1.4, {"b6"})],
)
def test_s5_trade_off(lam, misses):
    result = sequences(
        derive_mapping_set(RELATIONS, **OPTIONS, strategy=cost_optimal(lam)).mapping
    )
    assert {
        hu for hu in TARGETS if result[hu] not in (TARGETS[hu], B7_OPTION_2)
    } == misses
    if lam > 1:
        assert result["b6"] == "(A e26-e26) (T e27-e29) (A e30-e30)"


def test_every_result_is_disjoint_and_covering(analyses):
    positions = RELATIONS.group_by("hu").len()
    for analysis in analyses.values():
        mapping = analysis.mapping.sort("hu", "first_position")
        for _, part in mapping.group_by("hu"):
            firsts, lasts = (
                part["first_position"].to_list(),
                part["last_position"].to_list(),
            )
            assert firsts[0] == 1
            assert all(
                last + 1 == first
                for last, first in zip(lasts, firsts[1:], strict=False)
            )
            assert all(
                a != b for a, b in pairwise(part["high_level"].fill_null("⊥").to_list())
            )
        ends = (
            mapping.group_by("hu")
            .agg(pl.col("last_position").max())
            .join(positions, on="hu")
        )
        assert (ends["last_position"] == ends["len"]).all()


def all_segmentations(trace, p=0):
    """Brute force: every segmentation of a trace into valid segments, as lists of (first, last)."""
    if p == len(trace):
        yield []
        return
    for q in valid_ends(trace, p):
        for rest in all_segmentations(trace, q + 1):
            yield [(p, q), *rest]


@pytest.mark.parametrize(
    "strategy",
    [
        domain_knowledge(),
        domain_knowledge(storage_tie_break=False),
        cost_optimal(),
        cost_optimal(1.25),
    ],
)
@pytest.mark.parametrize("relations", [RELATIONS, EXTRA], ids=["running", "extra"])
def test_dynamic_programme_finds_the_brute_force_optimum(strategy, relations):
    analysis = derive_mapping_set(relations, **OPTIONS, strategy="S1")
    for trace in split_traces(
        analysis.relations, analysis.maximal_visits, storage_high_levels={"B"}
    ):
        costs = []
        for segmentation in all_segmentations(trace):
            parts = [
                segment_cost(segment_stats(trace, p, q), strategy)
                for p, q in segmentation
            ]
            if all(part is not None for part in parts):
                costs.append(tuple(round(sum(x), 9) for x in zip(*parts, strict=True)))
        _, cost = optimal_segmentation(trace, strategy)
        assert tuple(round(x, 9) for x in cost) == min(costs)


def test_s6_on_the_extra_traces():
    result = letters(derive_mapping_set(EXTRA, **OPTIONS, strategy="S6"))
    assert (
        result
        == {
            "x1": "ATBTA",
            "x2": "ABBBBB",  # a tie up to criterion 4; the storage tie-break gives Nina's lean (working note 6.6)
            "x3": "AAATBB",
            "x4": "AAABB",
            "x5": "AAAATB",
            "y1": "AAABB",
            "y2": "ABBB",
            "y3": "AAAAAB",
            "y4": "ABBBBB",
            "y5": "AAAAATB",  # (A g22-g26) (T g27) (B g28), working note 6.8
        }
    )


def test_custom_strategies_equal_the_presets():
    s6 = sequences(derive_mapping_set(RELATIONS, **OPTIONS, strategy="S6").mapping)
    custom = lexicographic(
        [
            "n_conforming_processing",
            "n_stays",
            "n_nonconforming",
            "n_vehicle_visits",
            "n_storage_stay_relations",
            "duration_sq",
        ],
        no_sacrifice_to_vehicles=True,
    )
    assert (
        sequences(derive_mapping_set(RELATIONS, **OPTIONS, strategy=custom).mapping)
        == s6
    )
    s5 = sequences(derive_mapping_set(RELATIONS, **OPTIONS, strategy="S5").mapping)
    custom = weighted({"n_visits": 1, "n_nonconforming": 0.5})
    assert (
        sequences(derive_mapping_set(RELATIONS, **OPTIONS, strategy=custom).mapping)
        == s5
    )


def test_custom_order_and_direction_change_the_result():
    # without the hard rule and with fewest visits first, b8 is absorbed as in S1
    fewest = lexicographic(["n_visits", "n_nonconforming"])
    result = sequences(
        derive_mapping_set(RELATIONS, **OPTIONS, strategy=fewest).mapping
    )
    assert result["b8"] == "(A e35-e40) (B e41-e41)"
    # preferring short visits (duration_sq minimised) on its own gives the uninterrupted runs
    short = lexicographic([("duration_sq", "min")])
    s2 = sequences(derive_mapping_set(RELATIONS, **OPTIONS, strategy="S2").mapping)
    assert (
        sequences(derive_mapping_set(RELATIONS, **OPTIONS, strategy=short).mapping)
        == s2
    )


def test_custom_local_rule():
    def never_into_vehicles(step):
        """Absorb unless the current visit is at the truck."""
        return step.current.high_level != "T"

    result = sequences(
        derive_mapping_set(RELATIONS, **OPTIONS, strategy=never_into_vehicles).mapping
    )
    assert result["b1"] == TARGETS["b1"]


def test_s7_is_an_alias_of_s6():
    s6 = derive_mapping_set(RELATIONS, **OPTIONS, strategy="S6")
    s7 = derive_mapping_set(RELATIONS, **OPTIONS, strategy="S7")
    assert s7.strategy == s6.strategy
    assert s7.mapping.equals(s6.mapping)


def test_unknown_strategy_and_criterion():
    with pytest.raises(ValueError, match="Unknown strategy"):
        derive_mapping_set(RELATIONS, **OPTIONS, strategy="S8")
    with pytest.raises(ValueError, match="Unknown criterion"):
        derive_mapping_set(RELATIONS, **OPTIONS, strategy=lexicographic(["n_loops"]))


#: Pooled metrics of the working note 7.3 and Nina's concept note, "Evaluating mapping sets" (S6 without the storage tie-break; trivial =
#: one relation without processing, connecting visits included).
METRICS = {
    "S1": (15, 13, 0, 3, 2, 0, 0, 2, 3.6, 3, 4, 4, 39),
    "S6": (16, 13, 0, 3, 3, 0, 1, 3, 3.375, 3, 3.75, 3, 40),
    "S2": (39, 13, 12, 24, 9, 0, 6, 9, 54 / 39, 1, 60 / 39, 1, 54),
}


@pytest.mark.parametrize("key", list(METRICS))
def test_pooled_metrics(key):
    strategy = domain_knowledge(storage_tie_break=False) if key == "S6" else key
    analysis = derive_mapping_set(
        RELATIONS, **OPTIONS, strategy=strategy, trivial_excludes_connecting=False
    )
    m = analysis.metrics.pooled.row(0, named=True)
    (
        n_vis,
        n_proc,
        loops,
        trivial,
        veh,
        trans,
        conn,
        veh_like,
        mean_rel,
        med_rel,
        mean_d,
        med_d,
        conf,
    ) = METRICS[key]
    assert (m["n_visits"], m["n_conforming_processing"], m["n_located_processing"]) == (
        n_vis,
        n_proc,
        13,
    )
    assert (
        m["n_loops"],
        m["n_trivial_without_processing"],
        m["n_vehicle_visits"],
        m["n_transferring_visits"],
    ) == (loops, trivial, veh, trans)
    assert m["n_connecting"] == conn
    assert m["p_conn"] == pytest.approx(conn / veh_like)
    assert m["mean_relations"] == pytest.approx(mean_rel)
    assert m["median_relations"] == med_rel
    assert m["mean_duration"].total_seconds() / 3600 == pytest.approx(mean_d)
    assert m["median_duration"] == timedelta(hours=med_d)
    assert (m["n_conforming"], m["n_relations"]) == (conf, 54)
    assert m["p_proc"] == 1.0


def test_trivial_options():
    analysis = derive_mapping_set(
        RELATIONS, **OPTIONS, strategy=domain_knowledge(storage_tie_break=False)
    )
    # default: |σ| = 1 (concept note, "Properties"), connecting visits excluded: (T e8) of b3 and (B e34) of b7, not the
    # connecting (T e38) of b8
    trivial = analysis.metrics.visits.filter("is_trivial")
    assert sorted(trivial["hu"].to_list()) == ["b3", "b7"]
    with_connecting = mapping_metrics(
        analysis.relations,
        analysis.mapping,
        CONTEXT.vehicles,
        P,
        trivial_excludes_connecting=False,
    )
    assert with_connecting.pooled["n_trivial"].item() == 3
    # S2: 28 with |σ| = 1, 24 of them without processing at their hl (both with connecting visits)
    s2 = derive_mapping_set(RELATIONS, **OPTIONS, strategy="S2")
    pooled = mapping_metrics(
        s2.relations, s2.mapping, CONTEXT.vehicles, P, trivial_excludes_connecting=False
    ).pooled
    assert (
        pooled["n_trivial"].item(),
        pooled["n_trivial_without_processing"].item(),
    ) == (28, 24)


def test_trivial_counts_with_sigma_one():
    # values of the concept thread (|σ| = 1, connecting included): S1 3, S2 28, S3 27, S4 4, S5 (λ = 0.5) 3
    expected = {"S1": 3, "S2": 28, "S3": 27, "S4": 4, "S5": 3}
    for key, n in expected.items():
        analysis = derive_mapping_set(
            RELATIONS, **OPTIONS, strategy=key, trivial_excludes_connecting=False
        )
        assert analysis.metrics.pooled["n_trivial"].item() == n, key


def test_both_trivial_metrics_with_defaults():
    """Nina's note (2026-11-02): N_triv and N_triv^np, connecting visits excluded, S6 with the storage tie-break."""
    expected = {
        "S1": (3, 3),
        "S2": (22, 18),
        "S3": (21, 17),
        "S4": (4, 2),
        "S5": (3, 3),
        "S6": (2, 1),
    }
    table, _ = compare_strategies(RELATIONS, **OPTIONS)
    got = {
        row["strategy"].split()[0]: (
            row["n_trivial"],
            row["n_trivial_without_processing"],
        )
        for row in table.iter_rows(named=True)
    }
    assert got == expected


def test_metrics_for_one_handling_unit_from_events():
    analysis = derive_mapping_set(RELATIONS, **OPTIONS, strategy="S6")
    hand = pl.DataFrame(
        {
            "hu": ["b8"] * 3,
            "high_level": ["A", "T", "B"],
            "first_event": ["e35", "e38", "e39"],
            "last_event": ["e37", "e38", "e41"],
        }
    )
    m = mapping_metrics(analysis.relations, hand, CONTEXT.vehicles, P)
    assert m.per_hu["hu"].to_list() == ["b8"]
    row = m.pooled.row(0, named=True)
    assert (
        row["n_visits"],
        row["n_connecting"],
        row["n_vehicle_visits"],
        row["n_conforming"],
    ) == (3, 1, 1, 5)
    assert m.visits["kind"].to_list() == ["stay", "vehicle visit", "stay"]
    several = mapping_metrics(
        analysis.relations,
        analysis.mapping,
        CONTEXT.vehicles,
        P,
        handling_units=["b1", "b8"],
    )
    assert several.per_hu["hu"].to_list() == ["b1", "b8"]
    assert several.pooled["n_visits"].item() == 5


def test_lazy_input_gives_the_same_mapping():
    eager = derive_mapping_set(RELATIONS, **OPTIONS, strategy="S6")
    lazy = derive_mapping_set(RELATIONS.lazy(), **OPTIONS, strategy="S6")
    assert lazy.mapping.equals(eager.mapping)
    assert lazy.metrics.pooled.equals(eager.metrics.pooled)


def test_mapping_visits_have_the_maximal_visit_columns():
    analysis = derive_mapping_set(RELATIONS, **OPTIONS, strategy="S6")
    assert set(analysis.maximal_visits.columns) - {"kappa"} <= set(
        analysis.mapping.columns
    )
    b8 = analysis.mapping.filter(pl.col("hu") == "b8").row(0, named=True)  # (A e35-e37)
    assert (
        b8["exit_event"],
        b8["n_relations"],
        b8["n_at_location"],
        b8["interrupted"],
    ) == ("e38", 3, 2, True)
    assert b8["duration"] == timedelta(hours=3)


def test_save_and_load_mapping(tmp_path):
    from ocelescope_module_location_based_ocpm.visit_mapping.mapping_files import (
        load_mapping,
        save_mapping,
    )

    mapping = derive_mapping_set(RELATIONS, **OPTIONS, strategy="S6").mapping
    path = save_mapping(mapping, tmp_path, 3, KAPPA, "S6")
    assert path.name == "visit_mapping_level_3_kappa_3_S6.csv"
    loaded = load_mapping(tmp_path, 3, KAPPA, "S6")
    assert loaded.select(mapping.columns).equals(
        mapping.select(loaded.columns).select(mapping.columns)
    )


def test_share_of_vehicle_relations_on_the_way():
    # Nina 2026-11-02: relations at vehicles in vehicle or transferring visits / all relations at vehicles
    expected = {"S1": 3, "S2": 10, "S3": 9, "S4": 4, "S5": 3}
    for key, n in expected.items():
        pooled = derive_mapping_set(
            RELATIONS, **OPTIONS, strategy=key
        ).metrics.pooled.row(0, named=True)
        assert (
            pooled["n_vehicle_relations_on_the_way"],
            pooled["n_vehicle_relations"],
        ) == (n, 10), key
        assert pooled["p_vr"] == pytest.approx(n / 10)
    for strategy in (domain_knowledge(), domain_knowledge(storage_tie_break=False)):
        pooled = derive_mapping_set(
            RELATIONS, **OPTIONS, strategy=strategy
        ).metrics.pooled
        assert pooled["n_vehicle_relations_on_the_way"].item() == 4
