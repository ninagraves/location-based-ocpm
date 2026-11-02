"""Visits (`overview/concepts/Visit Mappings.md`). Not used by any page yet.

- `context.py`: location context (agg, V, W), the high-level location of every relation, the naming-clash flag.
- `order.py`: the order of events with the same timestamp (AS4).
- `sequence.py`: general helpers for positions, runs and intervals in sequences (used everywhere below).
- `maximal.py`: maximal visits, the visits table of any visit set (`visit_table`), visit relations.
- `excursions.py`: excursions of any visits.
- `properties.py`: properties of visits and of visit sets (kinds, trivial, contained, overlapping, disjoint,
  covering, set metrics) and the RQ4 check.
- `dwell.py`: dwell times, time spent at locations, inside and outside hl.
- `overview.py`: transfer, target and processing statistics and the overview row per visit.
- `shifts.py`: stops, transfers and shifts of visits.
- `pipeline.py`: everything in one call, for any visit set (`analyse_visit_set`) or V_max (`analyse_visits`).
- `visit_files.py`: save and load maximal visits.
- `trace_figure.py`: draft figure of object traces with visits.
Waiting times are in the package `waiting_times` (with or without visits), disjoint mapping sets in `visit_mapping`.
Documented in `docs/resources/visits.md`, `visit-properties.md`, `shifts.md`, `visit-overview.md` and
`trace-figure.md`.
"""
