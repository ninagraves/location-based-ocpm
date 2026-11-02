"""Visit mapping sets V_map: a disjoint and covering set of visits derived from the maximal visits V_max
(working note `claude_notes/visit-mapping-sets.md`, sections 3 to 7). Not used by any page yet.

Per handling unit, a mapping set is a segmentation of its trace into consecutive visits (a visit sequence).

- `traces.py`: the per-trace input of the strategies (relations and maximal visits of one handling unit).
- `sweep.py`: the sweep along the trace with a local rule (absorb or split each excursion): S1 to S4.
- `optimal.py`: the best segmentation of a whole trace by additive criteria (lexicographic or weighted):
  S5, S6 and custom strategies.
- `strategies.py`: the predefined strategies and how to choose one.
- `segments.py`: from segments (hu, first and last position) to a visits table.
- `metrics.py`: evaluation metrics of a mapping set, for one or several handling units.
- `pipeline.py`: everything in one call (`derive_mapping_set`, `compare_strategies`).
- `mapping_files.py`: save and load a mapping set.
Documented in `docs/resources/visit-mapping.md`.
"""
