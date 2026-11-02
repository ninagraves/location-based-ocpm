# Waiting times

Status: implemented in the backend package and demoed in `notebooks/waiting_times.ipynb`; not used by any page yet.
Concept: `overview/concepts/Visit Mappings.md` (outside this repo), section "Waiting Times" with DD-W1 to DD-W7; storage units as decided in C.6 of `claude_notes/excursions-and-visit-sequences.md`.
Code: `backend-modules/location-ocpm/src/ocelescope_module_location_based_ocpm/waiting_times/` (paths below are relative to it).
Tests: `backend-modules/location-ocpm/tests/test_waiting_times.py`.

## 1. What it shows

Per **scope**, either a visit at $hl \in HL$ (`docs/resources/visits.md`) or, without visits, the whole trace of a handling unit (DD-W6), its **timed pieces**: the scope is cut at its clock events (entry, processing operations, removals from a storage unit) and each piece is labelled by the event ending it:
- **waiting** time (ends at a processing operation),
- **storage** time (ends at a removal from a storage unit),
- **remaining** time (ends at the exit, or the end of the trace).

They add up to the scope's duration, so the waiting time before a processing operation counts from the latest of entry, previous processing operation and storage removal.
Per scope: number of processing operations and removals, total waiting, storage and remaining time, and whether it is a processing visit.
Flags: two processing operations of one handling unit at one timestamp (RQ5), and waiting times that become negative after deducting a processing duration (DD-W3).

## 2. How it is calculated

| Step | File, function | Output |
|---|---|---|
| Scopes with visits | `scopes.py`, `visit_scopes` | the visits with $hl \in HL$ (DD-W7: no ⊥ visits) |
| Scopes without visits | `scopes.py`, `trace_scopes` | one scope per handling unit: its whole trace, high_level null, exit = its last event |
| Scope relations | `scopes.py`, `scope_relations` | one row per scope and relation; at_location = at $hl$ (with visits) or located (without) |
| Processing | `waiting.py`, `add_processing` | $e \in P$; $e \in P$ and at_location |
| Storage removals | `waiting.py`, `add_storage_removals` | $loc_{j-1} \in W$, $loc_j \notin W$ (not at the first relation of the scope) |
| Pieces | `waiting.py`, `time_pieces` | one row per piece between two clock events, labelled waiting / storage / remaining, with start and end event and activity |
| Waiting times | `waiting.py`, `waiting_times` | the waiting pieces, one per processing operation |
| Processing durations | `durations.py`, `add_processing_durations` | processing_duration, net_waiting_time, negative_waiting_time (DD-W3, optional) |
| Summary | `waiting.py`, `waiting_summary` | counts, totals, is_processing_visit per scope |
| Flag RQ5 | `waiting.py`, `simultaneous_processing` | handling units with two or more processing operations at one timestamp |
| All | `pipeline.py`, `analyse_waiting_times` | `WaitingAnalysis` (scopes, scope_relations, pieces, waiting_times, summary, simultaneous_processing, negative_waiting_times) |
| With visits, shifts and overview | `visits/pipeline.py`, `analyse_visit_set` / `analyse_visits`; `visit_mapping/pipeline.py`, `analyse_mapping` | the `WaitingAnalysis` as `VisitAnalysis.waiting`, per-activity statistics and the overview (`docs/resources/visit-overview.md`) |

Column names are at the top of `waiting.py`, `scopes.py` and `durations.py`.
All functions take and return polars frames, eager or lazy alike; nothing iterates over rows.

Decisions taken in the implementation (concept and Nina's decisions, listed for reference):
- Order: AS4 (movements, then processing operations, then the rest, each by event id), the same order as for the visits; use the same $P$ for both. If no $P$ is given, $P = T$.
- A processing movement counts at the location after the event ($loc$): it is the exit event of the visit it leaves and the entry ($w_1 = 0$) of the visit it enters.
- Processing operations on a vehicle mapped into $hl$ count; those during an excursion count for the visit to their own high-level location.
- A processing operation at the entry gets a waiting time of 0 (an extra piece of length 0).
- DD-W1: a processing operation that is itself a storage removal waits from the previous clock event, so its waiting time includes the time until and in storage; `zero_wait_at_removal=True` instead makes the time before it a storage piece and its waiting time 0.
- DD-W2: storage removals count anywhere in the visit, also outside $hl$ during an excursion; `outside_storage_resets=False` counts only storage units inside $hl$. A move between two storage units is no removal; a removal at the exit event does not count for that visit.
- DD-W3: timestamps are completion times, so a waiting time contains the processing time of its own operation. An optional processing-duration attribute is deducted from the waiting time of that same operation; negative results are flagged, not corrected.
- DD-W4: a removal by a movement at the same timestamp as a processing operation comes first (AS4), so the operation waits 0 (h7). `skip_simultaneous_removal=True` skips such a removal, and the operation waits from the clock event before it.
- DD-W5: removals from storage units are clock events by default; `storage_removals_reset=False` turns that off (only entry and processing operations reset the clock, storage time becomes part of waiting time).
- DD-W6: waiting times can be measured without visits; then the whole trace is one scope, the clock starts at its first event, every located processing operation counts, and the exit is the last event of the trace (`ends_trace`).
- DD-W7: no waiting times for visits at ⊥.
- RQ5 violated (two processing operations at one timestamp) is a flag, not a blocking error; AS4 orders them by event id, so the second waits 0 (h8).

## 3. Example

Running example (Level 3, $\kappa_{max} = 2$, $P = \{e1, e3, e4, e15\}$): with visits, the waiting times of the working doc (C.2) come out, e.g. $m_5$: $w = (0, 1)$ h, $w_{rem} = 8$ h; with $W = \{B1\}$ (C.6), $m_2$ is cut into waiting 0, waiting 1 h, storage 4 h (removal e8, outside A), remaining 5 h.
Without visits, c1's whole trace is cut into waiting 0, waiting 1 h, storage 4 h, remaining 6 h; c2's processing operation e15 waits 11 h from e4 (in A) instead of 3 h from its entry into B.

Edge-case example `data/visits_example/`: h5 (entry without processing, processing on a vehicle, during an excursion, as movements, trace end), h6 (storage units, DD-W1, DD-W2), h7 (ties, DD-W4), h8 (RQ5 flag), h3 (⊥); `notebooks/waiting_times.ipynb`, section 5, also compares with and without visits.

## 4. Filtering

None (not on a page yet).

## 5. Settings

All are parameters of `analyse_waiting_times`:
- `visits`: the visits to measure in (e.g. `VisitAnalysis.visits`, with `VisitAnalysis.relations` as `relations`); `None` (default) = whole traces (DD-W6).
- `processing`: $P$ as event ids; default $T$.
- `storage_units`: the set $W$ (read with `visits.context.location_context`, column is_storage); default empty, which gives waiting and remaining time only.
- `storage_removals_reset` (DD-W5, default `True`).
- `outside_storage_resets` (DD-W2, default `True`; no effect without visits).
- `zero_wait_at_removal` (DD-W1, default `False`).
- `skip_simultaneous_removal` (DD-W4, default `False`).
- `processing_duration` (DD-W3, default `None`): event attribute with the duration (duration type, or a number in `duration_unit`: "s", "min" or "h").

## 6. Where it lives in the code

See the table in section 2; every function has a docstring with its parameters and return value.
With visits, `relations` needs the columns position and high_level of the visit derivation, otherwise `analyse_waiting_times` raises a `ValueError`; without visits the positions are added (AS4) if missing.

## 7. How to change it

- **Counting processing movements where they start** (at $ploc$ instead of $loc$): change the `is_processing` condition in `waiting.add_processing` (needs the high-level location of `ploc`).
- **Other scopes** (e.g. later a visit sequence): any frame with the columns `scopes.SCOPE_COLUMNS` works as scopes for `scope_relations`, `time_pieces` and `waiting_summary`.
- **Time in storage on its own** (C.6 note): add storage entries ($loc_{j-1} \notin W$, $loc_j \in W$) as clock events in `time_pieces` with their own label.
- **Another tie-break** for equal timestamps: `visits.order.tie_rank` only (shared with the visits).
- After a change: `uv run pytest`, re-run `notebooks/waiting_times.ipynb`, adapt `tests/test_waiting_times.py`.

## 8. Alternatives

- **Separate order for waiting times** (processing before movements at equal timestamps): built and reverted on 2026-11-01; one order everywhere plus `skip_simultaneous_removal` covers the case.
- **Deducting the processing duration from the next waiting time** (start timestamps): does not fit completion timestamps (DD-W3).
- **Scopes as a mandatory visit step**: waiting times without visits (whole traces) are useful when no location context is given, so scopes are separate from visits.
