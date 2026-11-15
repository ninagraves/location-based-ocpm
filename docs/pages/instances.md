# Instance page

Status: suggestion (Nina 2026-11-14: "an instance page with HU overviews on the instance level, very similar to the playground"); not yet agreed.
User-facing description with a step-by-step example: `overview/module/Instance Page.md` (outside this repo).
Demo: `notebooks/instances.ipynb`.

The page has no sidebar: four cards one below the other (HU profile, Lineage, Object graph, HU timeline), every chart with its own settings row above it.
It ignores the filter bar of the overview page.
The graph canvases (lineage, object graph) can be made taller by dragging their bottom-right corner (CSS `resize: vertical`; Nina 2026-11-15).
All values use the low-level location $loc = loc^k$ of the selected level (and $\widehat{hl} = agg(loc)$); visits are not used.

## HU profile

### What it shows
One row per handling unit (also those without events): object type, lifecycle class, events, first and last timestamp, lifespan, number of partial consumptions, numbers of parents, children and siblings, distinct low- and high-level locations, first and last location, location changes, locatedness, time on vehicles / in storage / at other locations / unlocated (with a bar of the shares), movements, processing operations, shared events, connectedness, co-handled handling units.
The overview shows counts, so that every column sorts (Nina 2026-11-15, "like in the activity profile").
Columns come in groups (Lifecycle, Lineage, Locations, Time, Activities, Connectedness) that can be hidden.

Clicking a row unfolds it (several rows can be open) with the names behind the counts, loaded per handling unit:
- start and end: first and last event, creation event, final consumption, partial consumptions (activity, id, timestamp);
- lineage: parents, children, siblings (clicking one adds it to the selection);
- locations: the location path, one entry per location change with the event that reached it and its timestamp;
- activities and connectedness: processing activities with counts, co-handled handling units with their shared events (clickable).

### How it is calculated
- Traces: the relations of a handling unit in `seq` order (time, AS4 via `visits/order.sort_by_seq`, event id).
- Creation event $ev_{prod}$, consumption events $E_{cons}$, parents, children, siblings: `lineage/relations.py` (concept: Transformations, "Instance Lineage").
- Final consumption: an $e \in E_{cons}(hu)$ with $time(e) = last(hu)$; partial consumptions: the other $E_{cons}(hu)$.
- Lifecycle: `both` (produced and finally consumed; Nina 2026-11-15, previously `full`), `produced`, `consumed`, `open`.
- Location change: $loc(r_j) \neq \bot$ and different from the last $loc \neq \bot$ before $r_j$.
- Locatedness: General Concepts, "Locatedness" (handling-unit version).
- Time per location kind: $r_j$ contributes $time(r_{j+1}) - time(r_j)$ to the kind of $loc(r_j)$ (vehicle if in $V$, else storage if in $W$, else other; unlocated if $\bot$); the last relation contributes nothing, so the four times add up to the lifespan.
- Connectedness (Nina 2026-11-15): with $E'(hu)$ the events of $hu$ that are not transformation events, shared events $= |\{e \in E'(hu) \mid e$ involves another handling unit$\}|$, connectedness = shared events $/ |E'(hu)|$ (– if $E'(hu) = \emptyset$), co-handled = distinct other handling units in the shared events. Shared transformation events are left out, as they are lineage.
- Location path (unfolded row): a new entry at every location change (as above), so A, ⊥, A is one entry.

### Example
Running example, `data/running_example/configuration.json` (Level 3): c1 has 9 events, lifespan 11 h, lifecycle `produced` (roll e3), 4 locations, 3 high-level locations, 5 location changes, 2 h on vehicles, 1 h in storage, 8 h at other locations; c2 is `both` (roll e3, cut e15), shares 5 of its 6 non-transformation events (e4, e8, e9, e11, e12; not e6) with c1 and c3 (connectedness 83 %), location path A1 (e3), A2 (e6), T (e8), A2 (e9), B1 (e12); c5 is unlocated for 1 h.
Tests: `backend-modules/location-ocpm/tests/test_instances.py`.

### Filtering
Own search and object-type filter only. Search: every word must occur in the lower-case concatenation of id, object type, first and last location, creation and final consumption activity, parents, children and processing activities (`profile.search_text`).

### Settings and defaults
Sort by any scalar column (`profile.SORTABLE`; nulls last, ties by id), 10/25/50/100 rows per page (default 25), all column groups shown. Kept per log in the page state (`instances.table.<ocel>`), as is the selection (`instances.selected.<ocel>`).

### Where it lives in the code
- `backend-modules/.../instances/profile.py`: `ordered_traces`, `lifecycle_basics`, `location_profile`, `location_kind`, `time_per_location_kind`, `transformation_profile`, `connectedness`, `hu_profile` (joins them), `search_text`, `query_profile(profile, search, object_types, sort_by, descending, offset, limit) -> (page, total)`; `location_path`, `hu_details(relations, profile_row, loc, hl, processing)` for an unfolded row.
- `backend-modules/.../instance_routes.py`: `GET /{ocel_id}/instances/profile` (`getHuProfile`); the profile is cached per derivation key (`cached_profile`, LRU of 4), so paging and sorting only rerun `query_profile`; `GET /{ocel_id}/instances/details?hu=` (`getHuDetails`) for an unfolded row.
- `frontend-modules/.../components/HuProfileTable.tsx` (mantine-datatable, server-side paging and sorting, `rowExpansion` with `HuDetailsPanel`, kept in view when the table scrolls sideways; `duration` formats seconds), `routes/Instances.tsx` (selection pills, cards).

### How to change it
- New column: add it to the matching step function in `profile.py`, to `SORTABLE` if scalar, to `HuProfileRow` in `instance_routes.py`, rebuild the API client (`pnpm run build:modules`) and add it to `columns` in `HuProfileTable.tsx`; extend the test.
- Other notion of final consumption or lifecycle: `transformation_profile`; counting transformation events in the connectedness: drop the filter in `connectedness` (and in `hu_details`).
- More in the unfolded row: add it to `hu_details`, `HuDetails` in `instance_routes.py` and `HuDetailsPanel`.
- Precedence of vehicle over storage: `location_kind`.

### Alternatives
- Client-side paging (all rows to the browser): rejected for logs with hundreds of thousands of handling units.
- Times per visit or per high-level location: not used, the brief asks for low-level locations only.

## Lineage

### What it shows
The union of the lineage graphs (`lineage/graph.lineage_graph`) of all selected handling units, object graph or bipartite graph, with or without siblings (concept: Transformations, "Instance Visualisation"). Selected handling units are `focal` (thick border) even if they lie in another one's lineage. Edges carry the event's activity for their labels.

### Settings and defaults
Direction `both`, generations 2 (1–10 or all), transformation events off, siblings off, layout left to right; at most `MAX_LINEAGE_NODES` = 500 nodes (cut with a note).

### Where it lives in the code
- `instances/charts.py`: `selection_lineage(derivation, handling_units, direction, gen, with_events, with_siblings, max_nodes) -> SelectionLineage(nodes, edges, notes)`.
- Route `POST /{ocel_id}/instances/lineage` (`getSelectionLineage`).
- `components/LineageChart.tsx`: ELK layout (options of `lib/dfgLayout.ts`) and React Flow drawing; clicking a handling unit adds it to the selection.

### Alternatives
- Ocelescope's graph viewer (as in the playground): its first fit zooms in too far; React Flow + ELK as on the DFG page instead.
- One graph per selected handling unit: harder to read when lineages overlap.

## Object graph

### What it shows
Requested by Nina 2026-11-15.
Nodes: the selected handling units (`focal`, thick border) and every object related to one of them by a shared event or by an o2o relation in either direction (`related`), handling units and other objects alike (handling units rounded, other objects square, in the colour of their object type).
Arcs: one undirected arc per pair of nodes sharing at least one event, labelled with the event ids (at most three, then "+ n"; thicker for more events), and one dashed arrow per o2o relation (source → target), labelled with its qualifier.
The arcs are all arcs between the nodes, also between two related objects.
Hovering an arc's label lists its events (id, timestamp, activity) or the o2o relation; hovering a node gives its number of events and of events shared with the selection; clicking a handling unit adds it to the selection.
Objects can be dragged (Nina 2026-11-15); the arcs follow, and positions are kept until the graph is laid out again (other selection or other visible part).

### How it is calculated
For the selected handling units $S$, with $E(o)$ the events of object $o$ (e2o) and $O2O$ the o2o relations:
- related objects $R = \{o \notin S \mid E(o) \cap E(S) \neq \emptyset\} \cup \{o \notin S \mid (s, o) \in O2O \lor (o, s) \in O2O, s \in S\}$ (one hop);
- event arcs: pairs $\{o, o'\} \subseteq S \cup R$ with $E(o) \cap E(o') \neq \emptyset$, carrying $E(o) \cap E(o')$ ordered by time and id;
- o2o arcs: $(o, o') \in O2O$ with $o, o' \in S \cup R$.
The backend returns the whole graph once; object types and arc kinds are hidden in the browser, so changing them needs no new request (only a new layout).
Unlike the rest of the page it reads the log's e2o and o2o tables directly (all objects, not only handling units).

### Example
`data/object_graph_example` (the running example plus crane1, truck1, op1, op2, customer orders o1, o2, customer k1 and nine o2o relations; same configuration).
Selecting c2: related objects c1, c3, c4, s1 (shared events), crane1, op1, op2, truck1 (shared events) and o1 (o2o only); c5, o2 and k1 are two hops away and not part of the graph.
Arcs: c1–c2 with e3, e4, e8, e9, e11; crane1–op1 with e5, e6, e11, e12 (between two related objects); o2o c4 → c2 "cut from", c2 → o1 "part of".
Tests: `test_object_graph` in `tests/test_instances.py`.

### Settings and defaults
- Related objects: one chip per object type of the related objects with its number of objects; handling-unit types on, other types off (selected handling units are always shown).
- Shared events, O2O relations: arc kinds, both on.
- Arcs between related objects: on (off: only arcs touching a selected handling unit, a star around the selection).
- Labels: on.
- At most `MAX_OBJECT_NODES` = 500 nodes (selected first, then handling units, then other objects, each by shared events; cut with a note).
Kept per log in the page state (`instances.objectGraph.<ocel>`).

### Where it lives in the code
- `instances/object_graph.py`: `object_frames(ocel)` (e2o, o2o, objects, events renamed), `related_objects(frames, selected)`, `graph_nodes(frames, selected, related, handling_units)`, `event_arcs(frames, nodes)`, `o2o_arcs(frames, nodes)`, `object_graph(frames, selected, handling_units, max_nodes) -> ObjectGraph(nodes, event_arcs, o2o_arcs, notes)`.
- Route `POST /{ocel_id}/instances/object-graph` (`getObjectGraph`).
- `components/ObjectGraphChart.tsx`: settings row, `visibleGraph` (hiding), `layoutGraph` (ELK `stress`, one layout edge per pair), `routeArcs` (from the current node positions, so arcs follow dragged nodes: straight lines or, several between two objects, curves to both sides, clipped at the node boxes), React Flow drawing, label tooltips.

### How to change it
- More hops (objects related to related objects): repeat `related_objects` with $S \cup R$ in `object_graph`.
- Label length: `MAX_LABEL_EVENTS`; events listed in the hover: `MAX_HOVER_EVENTS`; default types: `typeShown`.
- Layout: ELK options in `layoutGraph` (`elk.stress.desiredEdgeLength`); `layered` would suit directed graphs, but most arcs here are undirected.

### Alternatives
- Arcs only between a selected handling unit and its related objects: available as a setting ("Arcs between related objects" off), not the default, since arcs between related objects show who works together (operator and crane, coils on the same truck).
- One arc per shared event: unreadable for objects sharing many events; one arc per pair with the list in the hover instead.
- Filtering in the backend per object type: every change would need a request; the graph of a selection is small, so it is sent whole.

## HU timeline

### What it shows
The resource `docs/resources/object-timeline.md` for the timeline's own list of handling units (Nina 2026-11-15).
The list is reset to the selection whenever the selection changes; pills remove single handling units, *Add all HUs of the lineage* and *Add all HUs of the object graph* append the handling units of the loaded lineage chart (with its current settings) or of the object graph (all its handling units, also hidden ones) that are not in the list yet, *Reset to selection* goes back.

### Settings and defaults
List = selection, axis `event order`, rows `as listed` (or by first event), movements `implicit` (or `explicit`: open circle on the band; `explicit with label`: also the activity name above the band; Nina 2026-11-15), high-level band, activity names, same-timestamp boxes and shared-event lines on. At most 50 rows (`MAX_HANDLING_UNITS`).

### Where it lives in the code
- `instances/charts.py`: `timeline_figure(derivation, handling_units, axis, ..., by_first_event, movement_markers) -> (plotly JSON, notes)`; it renames $loc^k$, $ploc^k$ to `loc`, `ploc` and runs `timeline.object_timeline.timeline_relations` and `object_timeline`.
- Route `POST /{ocel_id}/instances/timeline` (`getHuTimeline`).
- `components/HuTimelineChart.tsx`: shows the figure with `ThemedPlot` (the figure's template is dropped so Ocelescope's theme applies).

### Alternatives
- Drawing the timeline in the frontend from prepared tables (planned in the resource doc): more work; the backend figure keeps one implementation of the drawing.
