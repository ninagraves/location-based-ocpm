# Properties of visits and of visit sets

Status: implemented in the backend package and demoed in `notebooks/visit_properties.ipynb`; not used by any page yet.
Concept: `overview/concepts/Visit Mappings.md` (outside this repo), sections "Visits" (excursions), "Properties", "Sets of visits" (with "Metrics" and its example) and the RQ4 requirement in "Setting".
Code: `backend-modules/location-ocpm/src/ocelescope_module_location_based_ocpm/visits/` (paths below are relative to it): `sequence.py`, `properties.py`, `excursions.py`.
Tests: `backend-modules/location-ocpm/tests/test_visit_properties.py` (running example of the concept note, `data/mapping_example/`, $\kappa_{max} = 3$).
Input: any set of visits: the maximal visits (`docs/resources/visits.md`), the visits of a mapping set (`docs/resources/visit-mapping.md`) or a hand-written table.

## 1. What it shows

Per visit:
- **trivial**: $|\sigma| = 1$;
- **interrupted**: $R(\nu) \neq R_{hl}(\nu)$;
- **kind**: ⊥ visit, stay (has a stop), vehicle visit ($L_{\neg v}(\nu) = \emptyset$) or transferring visit (no stop, $L_{\neg v}(\nu) \neq \emptyset$);
- counts: relations not at $hl$, relations on a vehicle, processing relations at $hl$, excursions;
- **contained** ($\nu \sqsubseteq \nu'$ for another visit of the set), **contains** (another visit is contained in it), **overlapping** ($\nu \Vert \nu'$), relative to the given set.

Per pair of visits: "contained in" or "overlaps", with the number of shared relations.
Per excursion: its first and last event and position, its length and its excursion locations.
Per handling unit: whether its visit set is **disjoint**, **hl-disjoint**, **covering**.
For the whole set (and per handling unit): $N^{\nu}$, $p^{r}_{cov}$, $N^{\nu}_{int}$ / $p^{\nu}_{int}$, $N^{\nu}_{con}$, $N^{\nu}_{ov}$, $N^{hu}_{dis}$ / $p^{hu}_{dis}$, $N^{r}_{>1}$ / $p^{r}_{>1}$, $N^{r}_{nc}$ / $p^{r}_{nc}$, $p^{r}_{\Vert}$.
Flag: **RQ4** violations, relations of a handling unit with the same timestamp at different (high-level) locations.

## 2. How it is calculated

General helpers (`sequence.py`), used throughout the visit code:

| Helper | What it does | Used by |
|---|---|---|
| `add_positions` | position 1, 2, ... in each sequence | trace positions (`maximal.add_trace_positions`), stop numbers j (`shifts.transfers`), visit sequence index j (`visit_mapping.metrics`), trace figure |
| `run_ids`, `runs` | maximal runs of equal values | excursions, high-level runs of the trace figure |
| `expand_intervals` | one row per position of an interval | visit relations $R(\nu)$, transfer relations |
| `at_positions` | columns at a position (+ offset) of the same sequence | entry, last and exit event/time (`maximal.visit_table`), dwell times |
| `interval_pairs` | contained / overlapping pairs of intervals | `properties.visit_pairs` |
| `python_runs` | runs of a plain Python list | tests of the sweep |

| Step | File, function | Output |
|---|---|---|
| Visits table of any set | `maximal.py`, `visit_table(intervals, relations)` | the columns of the maximal visits for any intervals (also used by `maximal_visits` and `visit_mapping.segments.mapping_visits`) |
| Hand-written sets | `properties.py`, `with_positions(visits, relations)` | first/last position from first/last event, visit_id if missing |
| Pairs | `properties.py`, `visit_pairs(visits)` | hu, visit_id, other_visit_id, relation, n_shared |
| Excursions | `excursions.py`, `excursions(visit_relations)`, `excursion_counts` | one row per excursion; n_excursions per visit |
| Visit properties | `properties.py`, `visit_properties(visits, visit_relations, excursions)` | the visits with kind, is_trivial, interrupted, counts, is_contained, contains, is_overlapping |
| Kinds | `properties.py`, `kind_of` (Python), `kind_expr` (polars) | the same rule; `kind_of` is used by the global strategies, `kind_expr` by the properties and `shifts.shift_summary` |
| Set properties | `properties.py`, `set_properties(visits, visit_relations, relations)` | per hu: is_disjoint, is_hl_disjoint, is_covering |
| Set metrics | `properties.py`, `set_metrics(visits, visit_relations, relations, by_hu)` | one row (or one per hu) |
| RQ4 | `properties.py`, `rq4_violations(relations, column)`, `flag_rq4` | violating (hu, time) with events and values |
| All | `pipeline.py`, `analyse_visit_set` | see `docs/resources/visit-overview.md` |

The visit relations come from `maximal.visit_relations` (with `shifts.add_stops` for on_vehicle and is_stop).
Everything is polars (eager or lazy); `interval_pairs` is a self-join per handling unit, so quadratic only in the number of visits of one handling unit.

Decisions taken in the implementation:
- Identical intervals (only possible in a hand-written set with two rows for the same visit) are contained in each other.
- An excursion must lie strictly inside the visit (as in the note); for maximal visits and mapping sets the first and last relation are at $hl$ anyway.
- Excursion locations write ⊥ as "⊥".
- $N^{hu}_{dis}$ / $p^{hu}_{dis}$: $|HU|$ = all handling units of the relations; a handling unit without visits counts as not disjoint.
- RQ4 compares high_level by default (the note: "theoretically sufficient"); `column="loc"` checks the stricter version. Null (⊥) counts as a value, so a tie between a located and an unlocated relation is a violation.

## 3. Example

Running example of the note ($\vts = \vmax$, $\kappa_{max} = 3$): $N^{\nu} = 24$, $p^{r}_{cov} = 1$, $N^{\nu}_{int} = 12$ ($p^{\nu}_{int} = 1/2$), $N^{\nu}_{con} = 9$, $N^{\nu}_{ov} = 6$, $HU_{dis} = \{s1, b3, b5\}$ ($p^{hu}_{dis} = 3/10$), $N^{r}_{>1} = N^{r}_{nc} = 21$, $p^{r}_{\Vert} = 11/54$; all reproduced by the tests.
Pairs: $m_3 \sqsubseteq m_2$, $m_2 \Vert m_4$, $m_{18} \sqsubseteq m_{17} \sqsubseteq m_{16}$.
Excursions: $m_2$ ⟨e7, e8⟩ with locations {B, T}; $m_{16}$ ⟨e27, e28, e29⟩ of length 3 with {B, T}; $m_{10}$ two excursions ⟨e18⟩ and ⟨e20⟩.
The S6 mapping set has $N^{\nu} = 16$, is disjoint and covering for every handling unit ($p^{hu}_{dis} = 1$, $N^{r}_{>1} = 0$).

## 4. Filtering

None (not on a page yet).

## 5. Settings

- `column` of `rq4_violations`: "high_level" (default) or the loc column.
- `by_hu` of `set_metrics`: one row for the set (default) or one per handling unit.

## 6. Where it lives in the code

See the tables in section 2; every function has a docstring with its parameters and return value.

## 7. How to change it

- **Another kind rule**: change `properties.kind_of` and `properties.kind_expr` together (same rule, Python and polars); the strategies, the metrics and the shift summary follow.
- **Another definition of trivial**: `properties.trivial_expr`; the mapping metrics add "not connecting" on top (`visit_mapping.metrics.visit_metrics`).
- **A further set metric**: add its aggregation in `properties.set_metrics` and its name to `SET_METRIC_COLUMNS`.
- After a change: `uv run pytest`, re-run `notebooks/visit_properties.ipynb`.

## 8. Alternatives

- **Pairs by an interval tree** instead of the self-join per handling unit: faster for handling units with very many visits, but the number of visits per trace is small here.
- **Excursions only inside the sweep** (as before): the sweep now reads them from the shared table, so the maximal visits, the overview and the strategies count the same excursions.
