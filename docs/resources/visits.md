# Maximal visits, shifts and waiting times

Status: implemented in the backend package and demoed in `notebooks/visits.ipynb`; not used by any page yet.
Concept: `overview/Single Level Visit Mappings.md` (outside this repo), sections "Visits", "Deriving maximal Visits", "Visit duration", "identifying shifts" and "Waiting Times"; waiting times as decided in Part C with C.6 (storage units) of `claude_notes/excursions-and-visit-sequences.md` (2026-10-31).
Code: `backend-modules/location-ocpm/src/ocelescope_module_location_based_ocpm/visits/` (paths below are relative to it).
Tests: `backend-modules/location-ocpm/tests/test_visits.py` (running example and the edge-case example).

Not implemented (benched or discarded in the concept): cutting visits and excursions (Part B), the general marker/segment version (Part D), visit sequences, and the characteristics "contained" and "overlapping".

## 1. What it shows

Per handling unit, its **maximal visits**: the stays at one high-level location $hl \in HL_\bot$, allowing excursions of at most $\kappa(hl)$ events ($\kappa(\bot) = 0$).
Per visit at $hl \in HL$:
- its **stops** (relations at $hl$ not on a vehicle) and the **transfers** between consecutive stops, each a stay, direct shift, vehicle shift or external shift;
- its **timed pieces**: the visit is cut at its clock events (entry, processing operations at $hl$, removals from a storage unit) and each piece is labelled by the event ending it: **waiting** time (ends at a processing operation), **storage** time (ends at a removal from a storage unit), **remaining** time (ends at the exit); they add up to the visit duration. So the waiting time before a processing operation counts from the latest of entry, previous processing operation and storage removal.

## 2. How it is calculated

| Step | File, function | Output |
|---|---|---|
| Event order | `order.py`, `tie_rank`, `sort_by_seq` | AS4 group of each event for equal timestamps: 0 movement, 1 processing operation, 2 other |
| Trace positions | `maximal.py`, `add_trace_positions` | position in $otrace(hu)$: time, then AS4 group, then event id |
| High-level locations | `context.py`, `add_high_level_locations` | $\widehat{hl}$ ($agg$ completed by identity) |
| Tolerance | `maximal.py`, `add_kappa` | $\kappa(\widehat{hl})$: $\kappa_{max}$, 0 for ⊥ |
| Gaps | `maximal.py`, `add_gaps` | $g_j = p_j - p_{j-1} - 1$ per (hu, $hl$); with `ignore_vehicles` without relations on vehicles |
| Visit ids | `maximal.py`, `add_visit_ids` | new visit iff gap null or gap $> \kappa$; cumulative sum numbers the visits |
| Visits | `maximal.py`, `maximal_visits` | one row per visit: first, last and exit event, times, duration, counts, interrupted |
| Visit relations | `maximal.py`, `visit_relations` | one row per visit and $r \in R(\nu)$ (incl. excursions), at_location |
| Stops | `shifts.py`, `add_stops` | on_vehicle, is_stop |
| Transfers | `shifts.py`, `transfers` | one row per $\mu_j$ with its category |
| Shift summary | `shifts.py`, `shift_summary` | counts per category, $L(\nu)$, $L_{hl}(\nu)$, $L_{stop}(\nu)$, $L_{\neg v}(\nu)$, vehicle / transferring visit |
| Processing | `waiting.py`, `add_processing` | $e \in P$; $e \in P$ at the visit's $hl$ |
| Storage removals | `waiting.py`, `add_storage_removals` | $loc_{j-1} \in W$, $loc_j \notin W$ (not at the first relation of the visit) |
| Pieces | `waiting.py`, `time_pieces` | one row per piece between two clock events, labelled waiting / storage / remaining, with the activities of its start and end event (`start_activity`, `end_activity`; for a waiting time, `end_activity` is the processing activity, so waiting times group by activity directly) |
| Waiting times | `waiting.py`, `waiting_times` | the waiting pieces, one per processing operation |
| Flag RQ5 | `waiting.py`, `simultaneous_processing` | handling units with two or more processing operations at one timestamp |
| Waiting summary | `waiting.py`, `waiting_summary` | number of processing operations and removals, total waiting, storage and remaining time |
| All | `pipeline.py`, `analyse_visits` | `VisitAnalysis` (relations, visits, visit_relations, transfers, pieces, waiting_times, simultaneous_processing) |

Column names are in `columns.py` (relations, visits and visit relations) and at the top of `shifts.py` and `waiting.py` (their own frames).
All functions take and return polars frames, eager or lazy alike; nothing iterates over rows.
Complexity: sorting is $O(N \log N)$ for $N$ relations, every other step is linear; `visit_relations` is linear in the size of its result ($\sum_\nu \lvert\sigma\rvert$).

Decisions taken in the implementation (all from the concept, listed for reference):
- ⊥ visits get null in all stop, shift and waiting columns (these are only defined for $hl \in HL$); `locations` leaves ⊥ out.
- ⊥ inside a transfer counts as not on a vehicle, so the transfer is an external shift.
- A processing movement counts at the location after the event ($loc$): it is the exit event of the visit it leaves and the entry ($w_1 = 0$) of the visit it enters.
- Processing operations on a vehicle mapped into $hl$ count; those during an excursion count for the visit to their own high-level location.
- Storage removals count anywhere in the visit, also outside $hl$ during an excursion (Nina, 2026-10-31; option `outside_storage_resets=False` counts only storage units inside $hl$); a move between two storage units is no removal; a removal at the exit event (outside the visit) does not count for that visit.
- A processing operation at the entry gets a waiting time of 0 (an extra piece of length 0).
- A processing operation that is itself a storage removal: by the concept (Nina, 2026-11-01) its waiting time counts from the previous clock event and so includes the time until and in storage. Option `zero_wait_at_removal=True` (in `time_pieces` and `analyse_visits`) gives the earlier behaviour: the time before it is a storage piece and its waiting time is 0. Removals by other events reset the clock in both modes.
- If no $P$ is given, $P = T$ (column `is_transformation`).
- Events with the same timestamp are ordered by AS4 (Nina, 2026-11-01): movements, then processing operations, then the rest, each group by event id; an event in $M \cap P$ counts as a movement. The same $P$ is used for the order and for the waiting times. So a removal from storage by a movement and a processing operation at the same timestamp give a storage piece ending at the removal and a waiting time of 0 for the processing operation (DD-W4, accepted by Nina 2026-11-01; h7 of the edge-case example). Option `skip_simultaneous_removal=True` (in `time_pieces` and `analyse_visits`) skips such a removal: the processing operation then waits from the clock event before it, including the storage time.
- Two processing operations of one handling unit at the same timestamp (excluded by RQ5) are a flag, not a blocking error: `simultaneous_processing` (in `VisitAnalysis.simultaneous_processing`); AS4 orders them by event id, so the second waits 0 (h8). The trace figure uses the same order on every axis.

## 3. Example

Running example (Level 3, $\kappa_{max} = 2$, $V = \{T\}$): the maximal visits are $m_1$ to $m_{11}$ of the note (14, 13, 11 visits for κ = 0, 1, 2, including the ⊥ visit of c5); c2's A visit ($m_5$) has the transfers stay, direct shift, vehicle shift, stay; c1's ($m_2$) stay, direct, external, stay; $m_6$ and $m_8$ are vehicle visits, $m_4$ is transferring.
With $P = \{e1, e3, e4, e15\}$ the waiting times of the working doc (C.2) come out, e.g. $m_5$: $w = (0, 1)$ h, $w_{rem} = 8$ h; with $W = \{B1\}$ (C.6), $m_2$ is cut into waiting 0, waiting 1 h, storage 4 h (removal e8, outside A), remaining 5 h.

Edge-case example `data/visits_example/` (generated by `make_visits_example.py`, $\kappa_{max} = 1$, crane C1 mapped into A, truck T unmapped, both vehicles, storage units S1, S2 in A and B2 in B, explicit $P$ incl. three processing movements): eight handling units covering all transfer categories, vehicles inside and outside $hl$, vehicle relations at the start and end of a visit, vehicle and transferring visits, ⊥ visits and ⊥ in a transfer, cuts by κ, processing on a vehicle, during an excursion and as movements, entry by processing, trace end, and storage units (move between storage units, removal, processing that removes from storage, removal outside $hl$), events with the same timestamp ordered by AS4 (h7), and two processing operations at one timestamp (h8, flagged).
`notebooks/visits.ipynb`, section 6, goes through each case.

## 4. Filtering

None (not on a page yet).

## 5. Settings

- `kappa`: $\kappa_{max} \geq 0$, the tolerance of every high-level location (default 0).
- `ignore_vehicles` (Nina, 2026-10-31; default `False`): if `True`, relations on a vehicle ($loc \in V$) do not count as part of deviating infixes, even if the vehicle maps to another high-level location, so a vehicle trip does not use up the tolerance. Visits to ⊥ are not affected. Example: κ = 1, c1's visit to A stays e3–e11 (the excursion ⟨e7 at B1, e8 on T⟩ counts 1), while by default it is cut into e3–e5 and e9–e11.
- `agg`, `vehicles`: the location context; until they are inputs of the tool, read with `context.location_context` from a table (e.g. `data/running_example/inputs/locations.csv`).
- `processing`: $P$ as event ids; default $T$. Also used for the AS4 order of events with the same timestamp.
- `outside_storage_resets` (default `True`, concept): removals from storage units outside $hl$ also reset the clock; `False`: only storage units with $agg(loc_{j-1}) = hl$.
- `skip_simultaneous_removal` (default `False`, DD-W4): with `True`, a removal by another event at the same timestamp as the next processing operation is no clock event.
- `zero_wait_at_removal` (default `False`): see section 2; with `True`, processing operations that take the handling unit out of storage get a waiting time of 0.
- `storage_units`: the set $W$ (read with `context.location_context`, column is_storage); default empty, which gives waiting and remaining time only.

## 6. Where it lives in the code

See the table in section 2; every function has a docstring with its parameters and return value.
`visit_files.py`: `save_visits(visits, folder, level, kappa)` and `load_visits(folder, level, kappa)` write and read the core visit columns as `maximal_visits_level_{k}_kappa_{κ}.csv`; the notebook writes `data/running_example/derived/maximal_visits_level_3_kappa_2.csv`.

## 7. How to change it

- **A tolerance per high-level location**: change `maximal.add_kappa` only (e.g. join κ from a table with one row per $hl$); everything after it reads the column `kappa`.
- **Another rule for new visits** (e.g. a time limit on excursions): change the `starts` expression in `maximal.add_visit_ids`.
- **Other transfer categories**: change `shifts.transfer_category` and `CATEGORIES` / `CATEGORY_COUNTS`; the summary counts follow `CATEGORY_COUNTS`.
- **Counting processing movements where they start** (at $ploc$ instead of $loc$): change the `is_processing` condition in `waiting.add_processing` (needs the high-level location of `ploc`).
- **Visits other than the maximal ones** (e.g. later a visit sequence): `visit_relations`, `add_stops`, `transfers`, `shift_summary`, `add_processing`, `add_storage_removals`, `time_pieces`, `waiting_times` and `waiting_summary` work for any visits table with visit_id, hu, high_level, first_position, last_position (plus exit_event, exit_time, ends_trace for `time_pieces`).
- **Another tie-break for equal timestamps** (e.g. processing operations before movements): change `order.tie_rank` only; trace positions, visits, pieces and the trace figure follow.
- **Time in storage on its own** (C.6 note): add storage entries ($loc_{j-1} \notin W$, $loc_j \in W$) as clock events in `time_pieces` with their own label.
- After a change: run `uv run pytest`, re-run `notebooks/visits.ipynb`, and adapt `tests/test_visits.py` where expected values change.

## 8. Alternatives

- **Enumerating infixes** and checking the visit conditions: at least quadratic per trace; the gap rule gives the same visits in one pass (note, "Why this always gives us maximal visits").
- **Counting shifts between consecutive relations at $hl$** or along excursions: depends on whether vehicles are mapped into $hl$ (one physical move would count twice via a crane in $hl$); counting between stops does not (working doc, A.0).
- **Joining visits and relations on hu and filtering by position** for `visit_relations`: simpler but quadratic for long traces; expanding the positions is linear.
