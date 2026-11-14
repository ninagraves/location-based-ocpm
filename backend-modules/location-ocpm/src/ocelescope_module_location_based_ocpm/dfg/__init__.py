"""Directly-follows graph (DFG) of the handling units, shown on the page "Directly-follows graph".

Documented in `docs/pages/directly-follows-graph.md`.

Steps (one module each, every step a plain polars function):
1. `traces.object_traces`: the events of every considered object of the selected object types, in `seq`
   order (time, AS4 tie rank, event id).
2. `variants.path_filter`: per object type, keep the objects of the most frequent variants (paths).
3. `arcs.directly_follows_arcs` and `arcs.arc_filter`: count the directly-follows arcs (with start and end
   arcs) per object type and keep the frequent ones.
4. `nodes.activity_nodes`: the shown activities with their frequency and the object types involved.
5. `graph.directly_follows_graph`: all steps together, as the response of the page's route.
"""
