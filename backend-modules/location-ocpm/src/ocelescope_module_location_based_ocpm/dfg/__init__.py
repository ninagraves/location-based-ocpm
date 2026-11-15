"""Directly-follows graph (DFG) of the handling units, shown on the page "Directly-follows graph".

Documented in `docs/pages/directly-follows-graph.md`.

Steps (one module each, every step a plain polars function):
1. `traces.object_traces`: the events of every considered object of the selected object types, in `seq`
   order (time, DFG boundary rank, AS4 tie rank, event id).
2. `projection.project_traces`: per object type, remove the events of deselected activities (projection).
3. `variants.variant_filter`: per object type, keep the objects of the most frequent variants.
4. `arcs.directly_follows_arcs`, `arcs.arc_share_filter`, `arcs.arc_count_filter`, `arcs.remove_arcs`: count the
   directly-follows arcs (with start and end arcs) per object type and keep the frequent ones.
5. `connectivity.stay_connected` (optional): add back arcs so that every arc lies on a start-to-end path.
6. `nodes`: the shown activities with their frequency and the object types involved.
7. `graph.directly_follows_graph`: all steps together, as the response of the page's route.
"""
