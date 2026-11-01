# Maximal visits

Status: implemented in the backend package and demoed in `notebooks/visits.ipynb`; not used by any page yet.
Concept: `overview/Single Level Visit Mappings.md` (outside this repo), sections "Visits", "Deriving maximal Visits" (with DD-V1 to DD-V4), "Visit duration" and "implementation".
Code: `backend-modules/location-ocpm/src/ocelescope_module_location_based_ocpm/visits/` (paths below are relative to it).
Tests: `backend-modules/location-ocpm/tests/test_visits.py` (running example and the edge-case example).
Built on the visits: stops, transfers and shifts (`docs/resources/shifts.md`) and, optionally, waiting times (`docs/resources/waiting-times.md`).

Not implemented (benched or discarded in the concept): cutting visits and excursions (Part B), the general marker/segment version (Part D), visit sequences, the characteristics "contained" and "overlapping", and the conditions on the visit itself of DD-V4 (maximum visit duration, maximum number of deviating infixes, maximum time outside, maximum number of other high-level locations; open question to Nina, since cutting by them changes maximality).

## 1. What it shows

Per handling unit, its **maximal visits**: the stays at one high-level location $hl \in HL_\bot$, allowing excursions (deviating infixes) of at most $\kappa(hl)$ events ($\kappa(\bot) = 0$, DD-V3), optionally also limited in their number of distinct timestamps and in their duration (DD-V1).
Each visit has its first, last and exit event, entry and exit time, duration, number of events and relations, and whether it was interrupted (has an excursion).
Plus a flag: auto-completed locations whose name clashes with a provided high-level location.

## 2. How it is calculated

| Step | File, function | Output |
|---|---|---|
| Event order | `order.py`, `tie_rank`, `sort_by_seq` | AS4 group of each event for equal timestamps: 0 movement, 1 processing operation, 2 other |
| Trace positions | `maximal.py`, `add_trace_positions` | position in $otrace(hu)$: time, then AS4 group, then event id |
| High-level locations | `context.py`, `add_high_level_locations` | $\widehat{hl}$ ($agg$ completed by identity) |
| Tolerance | `maximal.py`, `add_kappa` | $\kappa(\widehat{hl})$: $\kappa_{max}$ (null = no limit), 0 for ⊥ |
| Gaps | `maximal.py`, `add_gaps` | $g_j = p_j - p_{j-1} - 1$ per (hu, $hl$); with `ignore_vehicles` without relations on vehicles (DD-V2) |
| Further gap measures | `maximal.py`, `add_gap_measures` | per gap: number of distinct timestamps of the deviating infix (`gap_timestamps`) and its duration $time(\sigma[p_j]) - time(\sigma[p_{j-1}+1])$ (`gap_duration`); both 0 for an empty infix |
| Visit ids | `maximal.py`, `add_visit_ids` | new visit iff gap null, gap $> \kappa$, or (if set) gap_timestamps $>$ max_timestamps or gap_duration $>$ max_excursion_duration; cumulative sum numbers the visits |
| Visits | `maximal.py`, `maximal_visits` | one row per visit: first, last and exit event, times, duration, counts, interrupted |
| All visit steps | `maximal.py`, `derive_maximal_visits` | relations with visit ids, and the visits |
| Visit relations | `maximal.py`, `visit_relations` | one row per visit and $r \in R(\nu)$ (incl. excursions), at_location |
| Flag naming clash | `context.py`, `naming_clashes` | unmapped locations whose name is a high-level location of $agg$ (e.g. B unmapped and B1 → B) |
| All | `pipeline.py`, `analyse_visits` | `VisitAnalysis` (relations, visits incl. the shift summary, visit_relations, transfers, naming_clashes) |

Column names are in `columns.py`.
All functions take and return polars frames, eager or lazy alike; nothing iterates over rows.
Complexity: sorting is $O(N \log N)$ for $N$ relations, every other step is linear; `visit_relations` is linear in the size of its result ($\sum_\nu \lvert\sigma\rvert$).

Decisions taken in the implementation (from the concept, listed for reference):
- Events with the same timestamp are ordered by AS4 (Nina, 2026-11-01): movements, then processing operations, then the rest, each group by event id; an event in $M \cap P$ counts as a movement. Timestamps are completion times.
- If no $P$ is given, $P = T$ (column `is_transformation`); $P$ is only used here for the AS4 order. Use the same $P$ for the waiting times.
- DD-V1: the three limits (κ, timestamps, duration) can be combined; an excursion has to satisfy all that are set. They are only checked for located gaps; a ⊥ relation always cuts ($\kappa(\bot) = 0$).
- DD-V2: with `ignore_vehicles`, relations on a vehicle are left out of the gaps, so a vehicle trip does not use up the tolerance; visits to ⊥ are not affected.
- $agg$ may be partial and is completed by the identity (note, section "implementation"); a resulting name clash is a flag, not a blocking error.

## 3. Example

Running example (Level 3, $\kappa_{max} = 2$, $V = \{T\}$): the maximal visits are $m_1$ to $m_{11}$ of the note (14, 13, 11 visits for κ = 0, 1, 2, including the ⊥ visit of c5).
With `ignore_vehicles=True` and κ = 1, c1's visit to A stays e3–e11 (the excursion ⟨e7 at B1, e8 on T⟩ counts 1), while by default it is cut into e3–e5 and e9–e11.

Edge-case example `data/visits_example/` (generated by `make_visits_example.py`, $\kappa_{max} = 1$, crane C1 mapped into A, truck T unmapped, both vehicles, storage units S1, S2 in A and B2 in B): eight handling units h1 to h8; for the visits, ⊥ visits (h3), cuts by κ (h4, h1), vehicles and the tolerance (h1) and events with the same timestamp ordered by AS4 (h7) matter.
`notebooks/visits.ipynb`, section 5, goes through these cases.

## 4. Filtering

None (not on a page yet).

## 5. Settings

- `kappa`: $\kappa_{max} \geq 0$, the tolerance of every high-level location (default 0); `None` = no limit on the number of events (DD-V1, e.g. to limit excursions only by duration).
- `max_timestamps` (DD-V1, default `None` = off): maximum number of distinct timestamps of a deviating infix.
- `max_excursion_duration` (DD-V1, a `timedelta`, default `None` = off): maximum duration of a deviating infix, from its first event until the first event back at $hl$.
- `ignore_vehicles` (DD-V2, default `False`): see section 2.
- `agg`, `vehicles`: the location context; until they are inputs of the tool, read with `context.location_context` from a table (e.g. `data/running_example/inputs/locations.csv`).
- `processing`: $P$ as event ids; default $T$; only for the AS4 order.
- `vehicles_outside_external`: a shift option, see `docs/resources/shifts.md`.

## 6. Where it lives in the code

See the table in section 2; every function has a docstring with its parameters and return value.
`visit_files.py`: `save_visits(visits, folder, level, kappa)` and `load_visits(folder, level, kappa)` write and read the core visit columns as `maximal_visits_level_{k}_kappa_{κ}.csv`; the notebook writes `data/running_example/derived/maximal_visits_level_3_kappa_2.csv`.

## 7. How to change it

- **A tolerance per high-level location**: change `maximal.add_kappa` only (e.g. join κ from a table with one row per $hl$); everything after it reads the column `kappa`.
- **Another rule for new visits** (e.g. another limit on excursions): add its measure in `maximal.add_gap_measures` and its condition to the `starts` expression in `maximal.add_visit_ids`.
- **Conditions on the visit itself** (DD-V4): would need a cutting rule (e.g. greedy from the start of the visit) applied after `maximal_visits`; the result is no longer maximal in the sense of the note.
- **Another tie-break for equal timestamps** (e.g. processing operations before movements): change `order.tie_rank` only; trace positions, visits, shifts, waiting times and the trace figure follow.
- After a change: run `uv run pytest`, re-run `notebooks/visits.ipynb`, `notebooks/shifts.ipynb` and `notebooks/waiting_times.ipynb`, and adapt `tests/test_visits.py` where expected values change.

## 8. Alternatives

- **Enumerating infixes** and checking the visit conditions: at least quadratic per trace; the gap rule gives the same visits in one pass (note, "Why this always gives us maximal visits").
- **Joining visits and relations on hu and filtering by position** for `visit_relations`: simpler but quadratic for long traces; expanding the positions is linear.
- **Excursion duration from the last event at $hl$** (instead of from the first event of the infix): would also count the time before leaving; the note defines it from the first deviating event.
