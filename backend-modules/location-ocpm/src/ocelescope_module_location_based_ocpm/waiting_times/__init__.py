"""Waiting times (`overview/Single Level Visit Mappings.md`, "Waiting Times", DD-W1 to DD-W7). Not used by any
page yet.

Measured per visit (the visits come from `visits`) or, without visits, per whole trace (DD-W6).
- `scopes.py`: the scopes (visits at hl ∈ HL, or whole traces) and their relations.
- `waiting.py`: processing operations, storage removals, the timed pieces (waiting, storage, remaining),
  the per-scope summary and the RQ5 flag.
- `durations.py`: optional processing durations deducted from the waiting times (DD-W3).
- `pipeline.py`: everything in one call (`analyse_waiting_times`).
Documented in `docs/resources/waiting-times.md`; demo in `notebooks/waiting_times.ipynb`.
"""
