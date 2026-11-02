# Visit mapping sets

Status: implemented in the backend package and demoed in `notebooks/visit_mapping.ipynb`; not used by any page yet.
Concept: `overview/Single Level Visit Mappings.md` (outside this repo), sections on mapping sets, the strategies S1 to S6 and "Evaluating mapping sets" (l. 701–731); reasoning in the working note `claude_notes/visit-mapping-sets.md`, sections 3 to 7 (there the lexicographic strategy is called S7).
Code: `backend-modules/location-ocpm/src/ocelescope_module_location_based_ocpm/visit_mapping/` (paths below are relative to it).
Tests: `backend-modules/location-ocpm/tests/test_visit_mapping.py` (extended running example and extra traces, `data/mapping_example/`).
Input: the maximal visits (`docs/resources/visits.md`).

## 1. What it shows

A **mapping set** $\mathcal{V}_{map}$: visits that are disjoint and covering, i.e. every hu-event relation lies in exactly one visit.
Per handling unit it is a segmentation of its trace into consecutive visits, a **visit sequence**; consecutive visits have different high-level locations.
A **strategy** decides which segmentation is taken (six predefined ones, or your own).
**Evaluation metrics** describe a mapping set, per visit, per handling unit and pooled: number of visits, conforming processing, loops, trivial visits, vehicle and transferring visits, connecting visits, relations per visit, durations, conforming relations.
The trace figure can show the metrics of the whole set and of each trace, with their definitions on mouse-over (`docs/resources/trace-figure.md`).

## 2. How it is calculated

| Step | File, function | Output |
|---|---|---|
| Maximal visits | `visits/maximal.py`, `derive_maximal_visits` | relations with position, high_level, visit_id; $\mathcal{V}_{max}$ |
| Inputs of the strategies | `traces.py`, `add_mapping_inputs` | on_vehicle ($loc \in V$), is_processing_event ($e \in P$) |
| One trace per hu | `traces.py`, `split_traces`, `storage_high_levels` | `Trace` (lists by 0-based position, $m(p)$ per position) |
| Local strategies | `sweep.py`, `sweep_trace(trace, rule)` | segments; the rule decides absorb/split per excursion |
| Global strategies | `optimal.py`, `optimal_segmentation(trace, strategy)` | the best segmentation by criteria (dynamic programme) |
| Choosing a strategy | `strategies.py`, `resolve_strategy`, `segment_trace` | key, rule or strategy object → segments |
| Segments frame | `segments.py`, `segments_frame` | hu, high_level, first/last position (from 1), maximal_visit_id |
| Visits table | `segments.py`, `mapping_visits` | the columns of the maximal visits (events, times, duration, counts, interrupted) |
| Metrics | `metrics.py`, `visit_metrics`, `summarise`, `mapping_metrics` | per visit, per hu, pooled |
| Figure texts | `metrics.py`, `metric_lines`, `trace_metric_lines` | (text, explanation) pairs for the trace figure |
| All | `pipeline.py`, `derive_mapping_set`, `map_traces`, `compare_strategies` | `MappingAnalysis`; comparison table |
| Files | `mapping_files.py`, `save_mapping`, `load_mapping` | `visit_mapping_level_{k}_kappa_{κ}_{strategy}.csv` |

**The sweep** (local strategies; working note 3.3): start at $p = 1$; take the maximal visit $m(p)$ at the relation's own high-level location and walk along it from $p$; at each excursion $\xi$ of $m(p)$ after $p$, the rule decides absorb (continue) or split (stop before $\xi$); output the segment and continue after it.
Every result is disjoint and covering, and every mapping set is the result of some decision sequence (working note 4.3).
A rule gets a `SweepStep`: trace, current visit $m(p)$, entry $p$, start and end of $\xi$, its positions and its inner visits $\{m(e) \mid e \in \xi\}$.

| key | strategy | rule / criteria |
|---|---|---|
| S1 | earlier wins | absorb always (`earlier_wins`) |
| S2 | absorb never | split always (`absorb_never`): the uninterrupted runs, $\mathcal{V}_{max}$ at κ = 0 |
| S3 | vehicle-only | absorb iff all relations of $\xi$ are on vehicles (`vehicle_only`) |
| S4 | later wins | split iff an inner visit overlaps the current one and reaches beyond its end (`later_wins`) |
| S5 | cost-optimal | weighted: n_visits + λ · n_nonconforming (`cost_optimal(lam=1.0)`) |
| S6 | integrating domain knowledge | hard rule, then lexicographic: max n_conforming_processing, min n_stays, min n_nonconforming, min n_vehicle_visits, max n_storage_stay_relations (storage tie-break), max duration_sq (`nina_strategy(storage_tie_break=True)`) |

**Global strategies** (`optimal.py`): among all segmentations, the best one by criteria that are sums over the visits, so a dynamic programme over the positions finds it: $g(p) = \text{best}_{q}\,(c([p, q]) \oplus g(q + 1))$ over valid segments $[p, q]$ (inside $m(p)$, ending at its $hl$, neighbours not at its $hl$).
Criteria (`CRITERIA`; per segment, with a direction):

| key | per segment | direction |
|---|---|---|
| n_visits | 1 | min |
| n_stays | 1 if it is a stay (has a stop) | min |
| n_vehicle_visits | 1 if vehicle or transferring visit | min |
| n_nonconforming | relations not at its $hl$ | min |
| n_conforming_processing | processing relations at its $hl$ | max |
| n_storage_stay_relations | its relations, if it is a stay at a high-level location with a storage unit ($\{agg(w) \mid w \in W\}$) | max |
| duration_sq | $d^2$ in hours² ($d$ = time(exit event) − time(first event)) | max |

Combined lexicographically (`lexicographic(criteria, no_sacrifice_to_vehicles)`: compared in order) or weighted (`weighted(weights, no_sacrifice_to_vehicles)`: sum of weight × criterion, signed by its direction).
Hard rule `no_sacrifice_to_vehicles`: a visit at $hl \in HL$ without stops must be a vehicle visit (a transferring visit is infeasible); the uninterrupted runs are always feasible.
Ties: the segmentation whose first visit is longest, then the next (S1-like, "longer earlier visits first").

**Kinds of a visit**: ⊥ visit ($hl = \bot$); stay (a relation at $hl$ not on a vehicle); vehicle visit (all located relations on vehicles); transferring visit (otherwise). Same as `visits/shifts.py`.

**Metrics** (`metrics.py`; Nina's note l. 705–718):

| metric | column(s) | definition |
|---|---|---|
| $N_{vis}$ | n_visits | number of visits |
| $sh_{proc}$ | n_conforming_processing / n_located_processing | processing relations at their visit's $hl$ / located processing relations |
| $N_{loop}$ | n_loops | stays whose $hl$ occurred in an earlier stay, with the previous stay elsewhere (vehicle and transferring visits ignored, so A, T, A is no loop) |
| $N_{triv}$ | n_trivial | visits with one relation; by default not connecting ones; optionally only without processing at their $hl$ |
| $N_{veh}$, $N_{trans}$ | n_vehicle_visits, n_transferring_visits | |
| $sh_{conn}$ | n_connecting / ($N_{veh} + N_{trans}$) | vehicle or transferring visits $\nu_j$ ($1 < j < r$) whose neighbours are stays at different $hl$ |
| relations per visit | mean_relations, median_relations | |
| duration | mean_duration, median_duration | |
| $sh_{conf}$ | n_conforming / n_relations | relations at their visit's $hl$ |

Complexity: the sweep is linear per trace; the dynamic programme tries all ends inside $m(p)$ for every start, each segment counted in linear time (straightforward version, Nina's rule: modular first; with prefix sums it becomes linear). Both loop over the traces in Python; the metrics are polars expressions.

Decisions taken in the implementation:
- Strategy names follow Nina's note (S6 = the lexicographic strategy); `"S7"` (its number in the working note) is an alias.
- S5: λ = 1 by default (Nina, 2026-11-02); with the S1-like tie-break it gives exactly S1 on the running example.
- S6: the storage tie-break is on by default (Nina, 2026-11-02): it picks (A e26) (B e31–e34) for b7 (Nina was indifferent) and A, B, B, B, B, B for x2 (her lean); `storage_tie_break=False` gives the longer visit (b7: (A e26–e33) (B e34); x2: A, A, A, A, A, B).
- Trivial: one relation ($|\sigma| = 1$, note l. 143), connecting visits excluded by default (Nina, 2026-11-02, `trivial_excludes_connecting`). Whether trivial also requires "no processing at its $hl$" (note l. 709) is still open with Nina; `trivial_without_processing=True` gives it.
- ⊥ relations do not make a visit a transferring visit (they are not located); a ⊥ visit is its own kind and never infeasible.
- $sh_{proc}$ counts processing relations only at $hl \in HL$ (⊥ visits have none).
- Durations of criteria are in hours (`duration_sq`); for weighted strategies the weights have to take this unit into account.

## 3. Example

Extended running example (`data/mapping_example/`, κ = 3, $V = \{T\}$, $W = \{B1\}$, $P = \{e1, e3, e4, e15, e22, e26, e35\}$):
- S6 hits all of Nina's targets: b1 (A e3–e11) (T e13–e14); b2 (A e3–e11) (B e12–e15); b4 (B e15–e21); s2 (A e22–e26); b6 (A e26–e30); b7 (A e26) (B e31–e34); b8 (A e35–e37) (T e38) (B e39–e41).
- S1 (= S5 with λ = 1) misses only b8: (A e35–e40) (B e41); S4 misses b1 ((A e3–e5) (B e7) (T e8–e14)) and b8 ((A e35) (B e36–e41)); S3 hits only b2; S2 none.
- Metrics (Nina's note l. 720–731; S6 without the storage tie-break, trivial without processing, connecting included): S1 15 visits, $sh_{proc}$ 13/13, 0 loops, 3 trivial, 2/0 vehicle/transferring visits, $sh_{conn}$ 0/2, 3.6/3 relations per visit, 4/4 h, $sh_{conf}$ 39/54; S6 16, 13/13, 0, 3, 3/0, 1/3, 3.38/3, 3.75/3 h, 40/54; S2 39, 13/13, 12, 24, 9/0, 6/9, 1.38/1, 1.54/1 h, 54/54.
- Extra traces with S6: x1 A T B T A, x2 A B B B B B, x3 A A A T B B, x4 A A A B B, x5 A A A A T B, y1 A A A B B, y2 A B B B, y3 A A A A A B, y4 A B B B B B, y5 (A g22–g26) (T g27) (B g28); all as Nina resolved them.

## 4. Filtering

None (not on a page yet).

## 5. Settings

Parameters of `derive_mapping_set`:
- `strategy` (default `"S6"`): `"S1"` to `"S6"` (`"S7"` = `"S6"`), a rule (a function `SweepStep -> bool`), or a `GlobalStrategy` (`lexicographic`, `weighted`, `cost_optimal(lam)`, `nina_strategy(storage_tie_break)`).
- `kappa`, `agg`, `vehicles`, `processing`, `ignore_vehicles`: as for the maximal visits.
- `storage_units` ($W$): only for the storage tie-break of S6.
- `trivial_without_processing` (default `False`), `trivial_excludes_connecting` (default `True`): the definition of trivial visits.

`mapping_metrics(relations, mapping, vehicles, processing, location, handling_units, ...)` takes any mapping (with first/last position or first/last event) for one or several handling units.

## 6. Where it lives in the code

See the table in section 2; every function has a docstring with its parameters and return value.
`MappingAnalysis` holds relations, maximal_visits, mapping, metrics (`MappingMetrics`: visits, per_hu, pooled) and the strategy's name.
The mapping visits have the columns of the maximal visits, so `visits.maximal.visit_relations`, `visits.shifts` and `waiting_times.analyse_waiting_times` work on them.

## 7. How to change it

- **A new local strategy**: write a rule `def rule(step: SweepStep) -> bool` and pass it as `strategy`, or add it to `strategies.STRATEGIES`.
- **A new criterion**: add a `Criterion` to `optimal.CRITERIA` (a function of `SegmentStats`, a direction, a description); if it needs more counts, add them to `SegmentStats` and `segment_stats`.
- **Another order or weights for S6 / S5**: `strategies.S6_CRITERIA`, `strategies.DEFAULT_LAMBDA`, or a custom strategy.
- **Another tie-break**: the comparison in `optimal.optimal_segmentation` (ends are tried longest first, only a strictly better cost replaces).
- **Another definition of a metric**: the expressions in `metrics.visit_metrics` (kinds, loops, connecting, trivial) and `metrics.summarise`; texts and mouse-over explanations in `METRIC_LABELS` and `METRIC_EXPLANATIONS`.
- **Faster global strategies**: prefix counts per maximal visit in `segment_stats`, so each segment costs O(1).
- After a change: `uv run pytest`, re-run `notebooks/visit_mapping.ipynb`, adapt `tests/test_visit_mapping.py`.

## 8. Alternatives

- **Iterating drop and cut operations on visit sets**: hard to define after a cut and no argument that it terminates (working note 3.1); the sweep needs neither.
- **S6 second tolerance κ' < κ** (dropped 2026-11-02): the same as S1 on the maximal visits for κ'.
- **Only weighted strategies** (S5): no λ hits all of Nina's targets (b6 needs λ < 1, b8 λ > 1, also with separate weights for vehicles); what separates b6 from b8 is the structure, which the lexicographic S6 captures.
- **Enumerating all segmentations**: exponential; the dynamic programme gives the same optimum (tested against brute force on all example traces).
