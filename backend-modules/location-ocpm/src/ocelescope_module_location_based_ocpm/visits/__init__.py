"""Visits (`overview/Single Level Visit Mappings.md`). Not used by any page yet.

- `context.py`: location context (agg, V, W), the high-level location of every relation, the naming-clash flag.
- `order.py`: the order of events with the same timestamp (AS4).
- `maximal.py`: maximal visits.
- `shifts.py`: stops, transfers and shifts of visits.
- `pipeline.py`: everything in one call (`analyse_visits`).
- `visit_files.py`: save and load maximal visits.
- `trace_figure.py`: draft figure of object traces with visits.
Waiting times are in the package `waiting_times` (with or without visits).
Documented in `docs/resources/visits.md`, `docs/resources/shifts.md` and `docs/resources/trace-figure.md`.
"""
