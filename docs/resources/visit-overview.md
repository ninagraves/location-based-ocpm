# Visit overview: dwell times, aggregations and one call for any visit set

Status: implemented in the backend package and demoed in `notebooks/visit_overview.ipynb`; not used by any page yet.
Concept: `overview/concepts/Visit Mappings.md` (outside this repo), sections "identifying shifts" (dwell time, time spent at, inside and outside, transfers going to a location) and "Visit Overview".
Code: `backend-modules/location-ocpm/src/ocelescope_module_location_based_ocpm/visits/` (paths below are relative to it): `dwell.py`, `overview.py`, `pipeline.py`; for mapping sets `visit_mapping/pipeline.py`, `analyse_mapping`.
Tests: `backend-modules/location-ocpm/tests/test_visit_properties.py`.
Input: any set of visits and its relations; the shifts (`docs/resources/shifts.md`) and the waiting times (`docs/resources/waiting-times.md`).

## 1. What it shows

- **Dwell time** of every relation of a visit, $\delta_\nu(i) = time(\sigma[i+1]) - time(\sigma[i])$, and for the last one $time(e_{out}(\nu)) - time(\sigma[n])$; they add up to $d(\nu)$.
- **Time spent** per visit at every low-level location $x$ ($d_x(\nu)$) and at every high-level location $hl'$ ($d_{hl'}(\nu)$), with the number of relations there.
- **Time inside** $hl$, $d_{hl}(\nu)$, and **outside**, $d(\nu) - d_{hl}(\nu)$ (⊥ counts as outside).
- **Transfer statistics** per visit and category: number, total / mean / min / max / median duration $d(\mu_j)$, mean / min / max / median length $|\mu_j|$.
- **Transfer targets** per visit, category and target (the vehicles of vehicle shifts, the external high-level locations of external shifts): number of transfers going to it, relations at it and time spent at it (total, and min / max / median / mean per transfer).
- **Processing statistics** per visit and processing activity: number of operations, waiting time total / min / max / median / mean.
- **Overview**: one row per visit with the counts, properties, durations, shifts (including the statistics of vehicle and external shifts as columns) and waiting times.

## 2. How it is calculated

| Step | File, function | Output |
|---|---|---|
| Dwell times | `dwell.py`, `add_dwell_times(visit_relations, visits)` | visit relations + dwell_time |
| Time at locations | `dwell.py`, `time_spent(dwell_relations, by)` | visit_id, hu, location, n_relations_at, time_at |
| Inside / outside | `dwell.py`, `time_inside_outside(dwell_relations, visits)` | visit_id, time_inside, time_outside |
| Relations of transfers | `overview.py`, `transfer_relations(dwell_relations, transfers)` | one row per transfer and relation |
| Transfer statistics | `overview.py`, `transfer_statistics(transfers)` | per visit and category |
| Transfer targets | `overview.py`, `transfer_targets(transfer_relations, location)` | per visit, category and target |
| Processing statistics | `overview.py`, `processing_statistics(waiting_times)` | per visit and activity |
| Overview | `overview.py`, `visit_overview(visits, inside_outside, statistics, waiting_summary, processing)` | one row per visit |
| Visit mapping, agreement | `visit_location.py`, `agreement_changes`, `agreement_metrics` | per event: agreeing under $\hat{hl}$ and $vl_{\mathcal{V}}$, change; one row of metrics (`docs/resources/visit-mapping.md`) |
| Any visit set | `pipeline.py`, `analyse_visit_set(relations, visits, ...)` | `VisitAnalysis` with all frames, incl. waiting times (`waiting`) |
| Maximal visits | `pipeline.py`, `analyse_visits(relations, ...)` | derives $\vmax$, then `analyse_visit_set` |
| Mapping set | `visit_mapping/pipeline.py`, `analyse_mapping(mapping_analysis, ...)` | `analyse_visit_set` on $\vts_{map}$ |

`VisitAnalysis` holds: relations, visits (table, properties, shift summary), visit_relations (with stops and dwell times), transfers, naming_clashes, excursions, pairs, set_properties, set_metrics, set_metrics_per_hu, time_at_locations, time_at_high_levels, transfer_statistics, transfer_targets, waiting (`WaitingAnalysis` or None), processing_statistics, overview, rq4_violations, agreement and agreement_metrics (both None if the set is not disjoint and covering, e.g. $\mathcal{V}_{max}$).

Decisions taken in the implementation:
- The target of a relation in a vehicle shift is its vehicle ($loc$); in an external shift its high-level location (a truck that is its own high-level location appears as such).
- The statistics of the categories "vehicle shift" and "external shift" are columns of the overview (`vehicle_shift_...`, `external_shift_...`); the per-target and per-activity tables stay long, one row per target or activity.
- `n_processing_activities` is the number of distinct processing activities with a waiting time in the visit (0 for visits at $hl \in HL$ without, null at ⊥).
- Waiting times are computed by default (`with_waiting_times=True`); their options are passed through (`**waiting_options`).

## 3. Example

Running example ($\kappa_{max} = 3$): b2's visit to A (e3–e11) is 8 h inside A and 1 h outside (on T at e8), with one vehicle shift via T of 1 h; b6's visit to A (e26–e30) is 3 h outside A, its external shift goes to B (1 relation) and T (2 relations).
On the S6 mapping set, `analyse_mapping` gives the same frames for the 16 visits of $\vts_{map}$.

## 4. Filtering

None (not on a page yet).

## 5. Settings

- `location`, `vehicles`, `processing`, `storage_units`: as for the visits and waiting times.
- `vehicles_outside_external` (DD-S1).
- `with_waiting_times` (default True) and the waiting-time options (DD-W1 to DD-W5, processing duration).

## 6. Where it lives in the code

See the table in section 2; every function has a docstring with its parameters and return value.

## 7. How to change it

- **Other statistics**: `overview._stats` (the list `STATISTICS`).
- **Other targets** (e.g. low-level locations also for external shifts): the `target` expression in `overview.transfer_targets`.
- **Further overview columns**: add the frame to `visit_overview` and pass it from `pipeline.analyse_visit_set`.
- After a change: `uv run pytest`, re-run `notebooks/visit_overview.ipynb`.

## 8. Alternatives

- **One very wide overview table** with a column per target and activity: the number of columns would depend on the log; long tables are joined on demand instead.
- **Dwell time until the next relation at hl**: would mix the time outside into the stop; the note defines it until the next relation of the visit.
