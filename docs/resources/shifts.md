# Stops, transfers and shifts

Status: implemented in the backend package and demoed in `notebooks/shifts.ipynb`; not used by any page yet.
Concept: `overview/concepts/Visit Mappings.md` (outside this repo), section "identifying shifts" (with DD-S1) and the shift times of "Visit Metrics" (work in progress); categories as in Part A of `claude_notes/excursions-and-visit-sequences.md`.
Code: `backend-modules/location-ocpm/src/ocelescope_module_location_based_ocpm/visits/shifts.py`; run together with the visits by `visits/pipeline.analyse_visits` (or `analyse_visit_set` for any visit set, e.g. a mapping set).
Tests: `backend-modules/location-ocpm/tests/test_visits.py`.
Input: maximal visits and their relations (`docs/resources/visits.md`).

## 1. What it shows

Per visit at $hl \in HL$:
- its **stops**: relations at $hl$ (low-level location mapped to $hl$) not on a vehicle;
- the **transfers** $\mu_j$ between consecutive stops, each a **stay** (same location, nothing in between), **direct shift** (other location, nothing in between), **vehicle shift** (only vehicles in between) or **external shift** (something not on a vehicle outside $hl$, or ⊥, in between); stays and direct and vehicle shifts are internal shifts;
- each transfer's **duration** $d(\mu_j) = time(\sigma[a_{j+1}]) - time(\sigma[a_j + 1])$, from the first event after the stop until the next stop (0 for an empty transfer);
- per visit: counts per category, the internal and external **shift time** (sums of the durations), the locations $L(\nu)$, $L_{hl}(\nu)$, $L_{stop}(\nu)$, $L_{\neg v}(\nu)$, and whether it is a **vehicle visit** (only on vehicles, $L_{\neg v}(\nu) = \emptyset$) or a **transferring visit** (no stops, but $L_{\neg v}(\nu) \neq \emptyset$).

## 2. How it is calculated

| Step | Function | Output |
|---|---|---|
| Stops | `add_stops(visit_relations, vehicles, location)` | on_vehicle, is_stop per visit relation |
| Transfers | `transfers(visit_relations, location, vehicles_outside_external)` | one row per $\mu_j$: j, from/to stop, transfer_events, transfer_length, all_on_vehicle, all_at_location, transfer_duration, category |
| Category | `transfer_category(vehicles_outside_external)` | the expression used by `transfers` |
| Per visit | `shift_summary(visit_relations, transfers, location)` (vehicle / transferring visit from the shared kind rule `properties.kind_expr`) | counts (`CATEGORY_COUNTS`), internal_shift_time, external_shift_time, location sets, is_vehicle_visit, is_transferring_visit |

Column names are at the top of `shifts.py`.
All functions are linear after the sort of the visit relations and work eager or lazy.

Decisions taken in the implementation:
- ⊥ visits get null in all stop and shift columns (only defined for $hl \in HL$); the location sets leave ⊥ out.
- ⊥ inside a transfer counts as not on a vehicle, so the transfer is an external shift.
- Vehicle relations at the start or end of a visit (before the first or after the last stop) are no transfer.
- DD-S1 (concept note, "identifying shifts"): by default a transfer that is only on vehicles is a vehicle shift, also if a vehicle lies outside $hl$ (e.g. the truck T); with `vehicles_outside_external=True` it is a vehicle shift only if all its relations are at $hl$, otherwise an external shift.
- Shift times are 0 for a visit without transfers of that kind and null at ⊥.

## 3. Example

Running example (Level 3, $\kappa_{max} = 2$, $V = \{T\}$): c2's A visit ($m_5$, e3–e11) has the transfers stay, direct shift, vehicle shift (⟨e8⟩ on T, 1 h), stay, so internal shift time 1 h; c1's ($m_2$) has stay, direct, external (⟨e7, e8⟩, 2 h), stay, so external shift time 2 h; $m_6$ and $m_8$ are vehicle visits, $m_4$ is transferring.
With `vehicles_outside_external=True`, c2's transfer via T becomes an external shift (T is not mapped into A).

Edge-case example `data/visits_example/`: h1 (all four categories, vehicle shift via C1 inside and T outside A), h2 (vehicles at the start and end, vehicle visits), h3 (⊥ in a transfer), h4 (transferring visit); `notebooks/shifts.ipynb`, section 5.

## 4. Filtering

None (not on a page yet).

## 5. Settings

- `vehicles`: the set $V$ (from `context.location_context`).
- `vehicles_outside_external` (DD-S1, default `False`): see section 2; also a parameter of `analyse_visits`.

## 6. Where it lives in the code

`visits/shifts.py` (functions in section 2); `visits/pipeline.analyse_visits` joins `shift_summary` into `VisitAnalysis.visits` and returns the transfers as `VisitAnalysis.transfers`.

## 7. How to change it

- **Other transfer categories**: change `transfer_category` and `CATEGORIES` / `CATEGORY_COUNTS`; the summary counts follow `CATEGORY_COUNTS`.
- **Another transfer duration** (e.g. from the stop itself): change the `_leave_time` expression in `transfers`.
- **Other visits** (e.g. later a visit sequence): `add_stops`, `transfers` and `shift_summary` work for any visit relations with visit_id, hu, high_level, position, time, at_location.
- After a change: `uv run pytest`, re-run `notebooks/shifts.ipynb`.

## 8. Alternatives

- **Counting shifts between consecutive relations at $hl$** or along excursions: depends on whether vehicles are mapped into $hl$ (one physical move would count twice via a crane in $hl$); counting between stops does not (working doc, A.0).
- **Transfer duration from stop to stop**: would include the time spent at the first stop, which is waiting rather than transfer time.
