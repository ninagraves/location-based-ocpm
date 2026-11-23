# Instance page

Status: suggestion (Nina 2026-11-14: "an instance page with HU overviews on the instance level, very similar to the playground"); not yet agreed.
User-facing description with a step-by-step example: `overview/module/Instance Page.md` (outside this repo).
Demo: `notebooks/instances.ipynb`.

The page has no sidebar: five cards one below the other (HU profile, Object traces, Lineage, Object graph, HU timeline; the object traces right below the HU profile, Nina 2026-11-20), every chart with its own settings row above it.
It ignores the filter bar of the overview page.
Between the HU profile and the charts, the selection bar ("Selected (n):", one removable pill per selected handling unit, "Clear") sticks to the top of the window once scrolled to (CSS `position: sticky` below the app header; Nina 2026-11-20), so the selection stays visible and editable while looking at the charts.
In the lineage and the object graph, double-clicking the **name** of a handling unit (its id, dotted underline) selects it, or unselects it if it is selected; double-clicking an event, another object or the rest of a box does nothing, so the object graph's boxes are dragged by any point as before (Nina 2026-11-20; `onDoubleClick` on the name, `toggle` in `routes/Instances.tsx`). A single click does nothing, and double-clicking does not zoom.
The graph canvases (lineage, object graph) can be made taller by dragging their bottom-right corner (CSS `resize: vertical`; Nina 2026-11-15).
All values use the low-level location $loc = loc^k$ of the level chosen in the settings bar (and $\widehat{hl} = agg(loc)$, the identity in Locations: low, so the high-level columns and band then repeat the locations); visits are not used (`settings-bar.md`).

## HU profile

### What it shows
One row per handling unit (also those without events): object type, lifecycle class, events, first and last timestamp, lifespan with a bar of the shares of time on vehicles / in storage / at other locations / unlocated, number of partial consumptions, linked handling units, numbers of parents, children and siblings, generations up and down, distinct low- and high-level locations, first and last location, location changes, locatedness, movements, processing operations, shared events, connectedness, co-handled handling units.
The overview shows counts, so that every column sorts (Nina 2026-11-15, "like in the activity profile").
Columns come in groups, in this order: Lifecycle, Lineage, Locations, MF Profile (material flow: movements, processing operations, shared events, connectedness, co-handled HUs); each group can be hidden (Nina 2026-11-18). The time split bar sits in Lifecycle next to the lifespan; the four times per location kind are only shown in the unfolded row (Nina 2026-11-18, evening), so they cannot be sorted, filtered or exported from the table.
A header row above the column titles names the groups (no colours; Nina 2026-11-18).
Columns with a dotted underline explain themselves on hover (e.g. Connectedness, Linked HUs).

Clicking a row unfolds it (several rows can be open; kept with the page, `instances.expanded.<log>`) with the names behind the counts, loaded per handling unit:
- start and end: first and last event, creation event, final consumption, partial consumptions (activity, id, timestamp);
- lineage: parents, children, siblings (clicking one adds it to the selection);
- locations: the location path, one entry per location change with the event that reached it and its timestamp;
- MF Profile: processing activities with counts, co-handled handling units with their shared events (clickable).
- time: on vehicles, in storage (only if configured), at other locations and unlocated, each with its share of the lifespan.

### How it is calculated
- Traces: the relations of a handling unit in `seq` order (time, AS4 via `visits/order.sort_by_seq`, event id).
- Creation event $ev_{prod}$, consumption events $E_{cons}$, parents, children, siblings: `lineage/relations.py` (concept: Transformations, "Instance Lineage").
- Final consumption: an $e \in E_{cons}(hu)$ with $time(e) = last(hu)$; partial consumptions: the other $E_{cons}(hu)$.
- Lifecycle: `both` (produced and finally consumed; Nina 2026-11-15, previously `full`), `produced`, `consumed`, `open`.
- Location change: $loc(r_j) \neq \bot$ and different from the last $loc \neq \bot$ before $r_j$.
- Locatedness: General Concepts, "Locatedness" (handling-unit version).
- Time per location kind: $r_j$ contributes $time(r_{j+1}) - time(r_j)$ to the kind of $loc(r_j)$ (vehicle if in $V$, else storage if in $W$, else other; unlocated if $\bot$); the last relation contributes nothing, so the four times add up to the lifespan.
- Connectedness (Nina 2026-11-15): with $E'(hu)$ the events of $hu$ that are not transformation events, shared events $= |\{e \in E'(hu) \mid e$ involves another handling unit$\}|$, connectedness = shared events $/ |E'(hu)|$ (– if $E'(hu) = \emptyset$), co-handled = distinct other handling units in the shared events. Shared transformation events are left out, as they are lineage.
- Linked HUs (Nina 2026-11-18): distinct other handling units sharing at least one event with $hu$, transformation events included, so parents, children and siblings count too ($\geq$ co-handled).
- Generations up / down (Nina 2026-11-19): on the lineage graph (edges parent → child of `lineage_relations`), the longest chain of parents above $hu$ up to a handling unit without parents, and the longest chain of children below $hu$ down to one without children (0 if there is none). If a loop (cycle) of the lineage lies on such a chain, the value is ∞. Computed in `profile.generation_depths` with `profile.longest_path_rounds` (Kahn's algorithm by rounds: a node removed in round $r$ has a longest incoming path of $r$ edges; nodes never removed lie on or behind a cycle and get `inf`). The API sends ∞ as null (JSON has no infinity), the table shows "∞", the CSV export writes `inf`. Longest, not shortest: with s1 → c1 → p1 and s1 → p1, p1 is 2 generations below s1. The range filter's slider covers the finite values only; ∞ rows are kept unless "To" is set below the maximum.
- Location path (unfolded row): a new entry at every location change (as above), so A, ⊥, A is one entry.

### Example
Running example, `data/running_example/configuration.json` (Level 3): c1 has 9 events, lifespan 11 h, lifecycle `produced` (roll e3), 4 locations, 3 high-level locations, 5 location changes, 2 h on vehicles, 1 h in storage, 8 h at other locations; c2 is `both` (roll e3, cut e15), shares 5 of its 6 non-transformation events (e4, e8, e9, e11, e12; not e6) with c1 and c3 (connectedness 83 %), has 4 linked HUs (s1 and c1 via roll e3, c3, c4 via cut e15), 1 generation up (s1) and 1 down (c4) while c4 has 2 up (c2, s1) and s1 2 down, location path A1 (e3), A2 (e6), T (e8), A2 (e9), B1 (e12); c5 is unlocated for 1 h.
Tests: `backend-modules/location-ocpm/tests/test_instances.py`.

### Filtering
Own search and column filters only (no page filter bar).
- Search: every word must occur in the lower-case concatenation of id, object type, first and last location, creation and final consumption activity, parents, children and processing activities (`profile.search_text`).
- Column filters (Nina 2026-11-18): every column except the time split has a filter icon in its header; a row is kept if it satisfies all active filters and the search. The kind of filter depends on the column (`profile.column_info`):
  - categories (string columns with at most 100 distinct values, e.g. object type, lifecycle, locations, locatedness): checkboxes with the number of handling units per value, "(none)" for a missing value; the old object-type field above the table is gone, this filter replaces it;
  - text (the handling unit id): "contains", case-insensitive;
  - numbers, durations, connectedness, timestamps: a range slider over all values plus From/To fields (durations typed in hours, connectedness in %; timestamps by the slider only). A bound left at the column's minimum or maximum is not applied; a range drops rows without a value.
- Above the table, a line counts the listed handling units: "6 handling units listed", or "1 of 6 handling units listed (search and filters)" when search or filters hide some (Nina 2026-11-19).
- Active filters are listed as pills above the table (× removes one, "Clear all" removes all); a filtered column's icon is filled.

Example: Object type = coil and Children ≥ 1 leaves c2.

### Export
"CSV" and "Save to session" export the table as shown, folded: all handling units matching search and filters (all pages, not only the current one), in the current order, with the shown columns (hidden groups and the time split left out; no unfolded names). Values are as stored: counts, durations in seconds, connectedness as a share 0..1, timestamps in ISO format.
- CSV: downloads `hu_profile.csv`, one column per shown column, named by its id (e.g. `n_linked`).
- Save to session: an Ocelescope "OCEL Mapping" resource (the standard resource for values per object) with the given name (default "HU profile"); its objects table holds the handling units as `ocel:oid` and the shown columns as values; events, e2o and o2o are empty. It appears under Resources.

### Settings and defaults
Sort by any scalar column (`profile.SORTABLE`; nulls last, ties by id), 10/25/50/100 rows per page (default 25), all column groups shown. Kept per log in the page state (`instances.table.v2.<ocel>`, with the column filters), as is the selection (`instances.selected.<ocel>`).

### Where it lives in the code
- `backend-modules/.../instances/profile.py`: `ordered_traces`, `lifecycle_basics`, `location_profile`, `location_kind`, `time_per_location_kind`, `transformation_profile`, `connectedness`, `linked_handling_units`, `hu_profile` (joins them), `search_text`, `ColumnFilter(column, values, min, max, text)`, `filter_expression`, `query_rows(profile, search, filters)`, `sort_rows`, `query_profile(profile, search, object_types, sort_by, descending, offset, limit, filters) -> (page, total)`, `column_info(profile)` (filter options), `export_frame(rows, columns)`; `location_path`, `hu_details(relations, profile_row, loc, hl, processing)` for an unfolded row.
- `backend-modules/.../instance_routes.py`: `POST /{ocel_id}/instances/profile` (`getHuProfile`, body `ProfileQuery`: search, filters, sorting, page; the response carries `columns`, the filter options); `POST /{ocel_id}/instances/profile/csv` (`exportHuProfileCsv`) and `POST /{ocel_id}/instances/profile/save` (`saveHuProfile`, `session.add_resource(OCELMapping)`), both with `ProfileExportRequest` (query plus shown columns and name); the profile and its column options are cached per derivation key (`cached_profile`, `cached_column_info`, LRU of 4), so paging, sorting and filtering only rerun the query; `GET /{ocel_id}/instances/details?hu=` (`getHuDetails`) for an unfolded row.
- `frontend-modules/.../components/HuProfileTable.tsx` (mantine-datatable with column `groups`, `COLUMNS` lists every column with group, format and hover text; server-side paging, sorting and filtering; `ExportButtons`; `rowExpansion` with `HuDetailsPanel`, kept in view when the table scrolls sideways; `duration` formats seconds), `components/ProfileColumnFilter.tsx` (filter popovers: checkboxes, text, range), `routes/Instances.tsx` (selection pills, cards).

### How to change it
- New column: add it to the matching step function in `profile.py`, to `SORTABLE` if scalar, to `HuProfileRow` in `instance_routes.py`, rebuild the API client (`pnpm run build:modules`) and add it to `COLUMNS` in `HuProfileTable.tsx` (group, format, optional hover text); it is then filterable and exportable as well; extend the test.
- Another kind of filter for a column: `column_info` (kind) and `ProfileColumnFilter.tsx`; more values per category: `MAX_CATEGORIES`.
- Another export format or resource type: `export_hu_profile_csv` / `save_hu_profile` in `instance_routes.py`.
- Other notion of final consumption or lifecycle: `transformation_profile`; counting transformation events in the connectedness: drop the filter in `connectedness` (and in `hu_details`).
- More in the unfolded row: add it to `hu_details`, `HuDetails` in `instance_routes.py` and `HuDetailsPanel`.
- Precedence of vehicle over storage: `location_kind`.

### Alternatives
- Client-side paging (all rows to the browser): rejected for logs with hundreds of thousands of handling units.
- A module-specific table resource for "save to session": not used, Ocelescope's OCEL Mapping already holds values per object and other plugins can read it.
- Times per visit or per high-level location: not used, the brief asks for low-level locations only.

## Lineage

### What it shows
The union of the lineage graphs (`lineage/graph.lineage_graph`) of all selected handling units, object graph or bipartite graph, with or without siblings (concept: Transformations, "Instance Visualisation"). Selected handling units are `focal` (thick border) even if they lie in another one's lineage. Edges carry the event's activity for their labels.

### Settings and defaults
Direction `both`, generations 2 (1–10 or all), transformation events off, siblings off, layout left to right; at most `MAX_LINEAGE_NODES` = 500 nodes (cut with a note).

### Where it lives in the code
- `instances/charts.py`: `selection_lineage(derivation, handling_units, direction, gen, with_events, with_siblings, max_nodes) -> SelectionLineage(nodes, edges, notes)`.
- Route `POST /{ocel_id}/instances/lineage` (`getSelectionLineage`).
- `components/LineageChart.tsx`: ELK layout (options of `lib/dfgLayout.ts`) and React Flow drawing; double-clicking a handling unit's name selects or unselects it (`onDoubleClick` on the name; handling-unit nodes get `pointerEvents: "all"`, since React Flow gives none to nodes that can be neither dragged nor selected).

### Alternatives
- Ocelescope's graph viewer (as in the playground): its first fit zooms in too far; React Flow + ELK as on the DFG page instead.
- One graph per selected handling unit: harder to read when lineages overlap.

## Object graph

### What it shows
Requested by Nina 2026-11-15.
Nodes: the selected handling units (`focal`, thick border) and every object related to one of them by a shared event or by an o2o relation in either direction (`related`), handling units and other objects alike (handling units rounded, other objects square, in the colour of their object type).
Arcs: one undirected arc per pair of nodes sharing at least one event, labelled with the event ids (at most three, then "+ n"; thicker for more events), and one dashed arrow per o2o relation (source → target), labelled with its qualifier.
The arcs are all arcs between the nodes, also between two related objects.
Hovering an arc's label lists its events (id, timestamp, activity) or the o2o relation; hovering a node gives its number of events and of events shared with the selection; double-clicking a handling unit's name selects or unselects it (the rest of the box drags it).
Option *Events as boxes* (Nina 2026-11-20, default off): every event of a selected handling unit becomes a white box (event id, activity; hover: timestamp and number of objects), with a thin line to every shown object it involves; these events then leave the event arcs, so an event arc only remains for events between related objects that involve no selected handling unit (e.g. c1–c3 with e14). Hidden object types get no line.
Objects (and event boxes) can be dragged (Nina 2026-11-15); the arcs follow, and positions are kept until the graph is laid out again (other selection or other visible part), also when the page is left and opened again (since 2026-11-20, with zoom and pan; the lineage keeps its zoom and pan the same way; `docs/hosting/state-and-caching.md`, section "Page state").

### How it is calculated
For the selected handling units $S$, with $E(o)$ the events of object $o$ (e2o) and $O2O$ the o2o relations:
- related objects $R = \{o \notin S \mid E(o) \cap E(S) \neq \emptyset\} \cup \{o \notin S \mid (s, o) \in O2O \lor (o, s) \in O2O, s \in S\}$ (one hop);
- event arcs: pairs $\{o, o'\} \subseteq S \cup R$ with $E(o) \cap E(o') \neq \emptyset$, carrying $E(o) \cap E(o')$ ordered by time and id;
- o2o arcs: $(o, o') \in O2O$ with $o, o' \in S \cup R$;
- event boxes: every $e \in E(S)$ with the nodes it involves, $\{o \in S \cup R \mid e \in E(o)\}$ (`focal_events`).
The backend returns the whole graph once; object types and arc kinds are hidden in the browser, so changing them needs no new request (only a new layout).
Unlike the rest of the page it reads the log's e2o and o2o tables directly (all objects, not only handling units).

### Example
`data/object_graph_example` (the running example plus crane1, truck1, op1, op2, customer orders o1, o2, customer k1 and nine o2o relations; same configuration).
Selecting c2: related objects c1, c3, c4, s1 (shared events), crane1, op1, op2, truck1 (shared events) and o1 (o2o only); c5, o2 and k1 are two hops away and not part of the graph.
Arcs: c1–c2 with e3, e4, e8, e9, e11; crane1–op1 with e5, e6, e11, e12 (between two related objects); o2o c4 → c2 "cut from", c2 → o1 "part of".
Event boxes: c2's eight events e3, e4, e6, e8, e9, e11, e12, e15; e3 (roll) has lines to c1, c2 and s1, e6 (crane move) to c2, crane1 and op1 (if crane and operator are switched on); left as event arcs: c1–c3 with e14, c1–crane1 with e5.
Tests: `test_object_graph` in `tests/test_instances.py`.

### Settings and defaults
- Related objects: one chip per object type of the related objects with its number of objects; handling-unit types on, other types off (selected handling units are always shown).
- Shared events, O2O relations: arc kinds, both on.
- Arcs between related objects: on (off: only arcs touching a selected handling unit, a star around the selection).
- Labels: on.
- Events as boxes: off.
- At most `MAX_OBJECT_NODES` = 500 nodes (selected first, then handling units, then other objects, each by shared events; cut with a note).
Kept per log in the page state (`instances.objectGraph.<ocel>`).

### Where it lives in the code
- `instances/object_graph.py`: `object_frames(ocel)` (e2o, o2o, objects, events renamed), `related_objects(frames, selected)`, `graph_nodes(frames, selected, related, handling_units)`, `event_arcs(frames, nodes)`, `o2o_arcs(frames, nodes)`, `focal_events(frames, selected, nodes)`, `object_graph(frames, selected, handling_units, max_nodes) -> ObjectGraph(nodes, event_arcs, o2o_arcs, events, notes)`.
- Route `POST /{ocel_id}/instances/object-graph` (`getObjectGraph`).
- `components/ObjectGraphChart.tsx`: settings row, `visibleGraph` (hiding; with event boxes it adds the event nodes and e2o arcs and removes the boxed events from the event arcs), `layoutGraph` (ELK `stress`, one layout edge per pair), `routeArcs` (from the current node positions, so arcs follow dragged nodes: straight lines or, several between two objects, curves to both sides, clipped at the node boxes), React Flow drawing, label tooltips.

### How to change it
- More hops (objects related to related objects): repeat `related_objects` with $S \cup R$ in `object_graph`.
- Label length: `MAX_LABEL_EVENTS`; events listed in the hover: `MAX_HOVER_EVENTS`; default types: `typeShown`.
- Layout: ELK options in `layoutGraph` (`elk.stress.desiredEdgeLength`); `layered` would suit directed graphs, but most arcs here are undirected.

### Alternatives
- Arcs only between a selected handling unit and its related objects: available as a setting ("Arcs between related objects" off), not the default, since arcs between related objects show who works together (operator and crane, coils on the same truck).
- One arc per shared event: unreadable for objects sharing many events; one arc per pair with the list in the hover instead.
- Filtering in the backend per object type: every change would need a request; the graph of a selection is small, so it is sent whole.

## Object traces

### What it shows
Requested by Nina 2026-11-20.
One row per selected handling unit (in the order of the selection; at most `MAX_TRACES` = 50), left its id, object type and "n of m events" (when the categories removed some).
Its events from left to right in trace order, each as a chevron with its event id (small, dimmed) above its activity (Nina 2026-11-20): $seq$ order as in the HU profile (time, then the AS4 tie order, then event id).
On every chevron one small circle per other object of the event (all objects of the log, the row's handling unit itself left out), in the colour of its object type (handling-unit types as in the rest of the page, other types continue the palette alphabetically), sorted by object type and id; at most `MAX_CIRCLES` = 10, then "+ n".
If another selected handling unit takes part in the event, its **circle** gets a wider border (1.75 instead of 0.5 px, dark grey; Nina 2026-11-20: the circle, not the chevron); there is no other mark.
Double-clicking a circle of a handling unit selects it, or unselects it if it is selected (as in the lineage and the object graph); double-clicking the name of a row unselects it. Circles of other objects do nothing.
Below the chart a legend of the object types with circles (types of the rows first), each with its number of distinct objects.
Option "Align shared events" (default off; Nina 2026-11-20): an event shared by several rows is drawn in the same column in all of them, so shared events stand beneath each other. Columns by longest path (`align_columns` in `traces.py`, mirrored by `alignColumns` in the chart): the events are the nodes, consecutive events of a row the arcs; an event's column is the longest chain of events before it in any row (Kahn's algorithm). Off, every row is packed from the left.
Hover on a chevron: event id, activity, timestamp, location $loc^k$ of the relation (⊥ if unlocated), position, categories, the selected handling units involved, and the other objects (id, type; at most 20). Hover on a circle: the object, its type, and "selected" if it is a selected handling unit.

### Event categories (projection)
Above the chart the event category chips of the directly-follows graph page (`CategoryChips` of `DfgToolbar.tsx`, categories of `dfg/categories.py`): Move to vehicle, Move to storage, Other movements, Processing, Transforming (the three movement chips split the movements; Nina 2026-11-20, PR #43), each with the number of distinct events of the selected handling units in it.
Same rule as on the DFG page: an event leaves the traces only when **all** its categories are deselected (`categories.removed_events`); events in no category always stay; the following events move up (projection, positions renumbered).
Default here: all selected (Nina 2026-11-20), so the traces are complete (unlike the DFG page, where the movements are off by default).
Kept per log in the page state (`instances.traces.<ocel>`); "Reset settings" selects all again.

### Example
Running example (Level 3), c2 and c1 selected: c2 has e3 roll (other objects c1, selected, so its circle has the wide border, and s1), e4 label (c1), e6 move, e8 load truck, e9 unload truck, e11 move, e12 move, e15 cut (c4).
Other movements off: c2 keeps e3, e4, e8 (Move to vehicle), e12 (Move to storage), e15, "5 of 8 events"; c1 keeps its quality checks e7 and e14 (no category).
Aligned: e3 (column 0), e4 (1), e6 and e5 (2), e7 (3), e8 (4): e8 of c2 waits for c1's e7, so c2 has a gap at column 3.
Tests: `test_object_traces` in `tests/test_instances.py`; notebook demo: section 6 of `notebooks/instances.ipynb` (`object_traces`, `traces_figure`, aligned and projected).

### Where it lives in the code
- `instances/traces.py`: `trace_events(relations, handling_units, loc, hl, processing)` (`profile.ordered_traces` of the selection), `involved_objects(frames, events)` (e2o with object types), `object_traces(relations, frames, categories, handling_units, units, loc, hl, processing, excluded, max_traces) -> ObjectTraces(events, totals, categories, notes)` (each object with `is_hu`, `selected`), `align_columns(events)` (aligned columns), `traces_figure(traces, align, colours)` (plotly version of the chart for notebooks).
- `dfg/categories.py`: `removed_events(categories, excluded)` (also used by `remove_categories`).
- Route `POST /{ocel_id}/instances/traces` (`getObjectTraces`, body `ObjectTracesRequest`: handling_units, excluded_categories), answer `ObjectTracesResponse` (traces with events and their objects, categories, notes).
- `components/ObjectTracesChart.tsx`: `Chevron` (SVG outline `chevronPath`, width `chevronWidth`), `TraceRow`, `alignColumns`, `TypeLegend`, `useObjectTraces`, `traceColours`; sizes `SIZE`.

### How to change it
- Circles per chevron: `MAX_CIRCLES`; objects in the hover: `MAX_HOVER_OBJECTS`; rows: `MAX_TRACES` (backend).
- Border of circles of selected handling units: `boxShadow` of the circles in `Chevron`.
- Defaults (categories, alignment): `DEFAULT_OBJECT_TRACES`.

### Alternatives
- Aligning the rows by time (a column per timestamp): shows simultaneity, but long gaps; the HU timeline already does this.
- Marking selected objects by colour: Nina wanted only the wider circle border.

## HU timeline

### What it shows
The resource `docs/resources/object-timeline.md` for the timeline's own list of handling units (Nina 2026-11-15).
The list is reset to the selection whenever the selection changes; pills remove single handling units, *Add all HUs of the lineage* and *Add all HUs of the object graph* append the handling units of the loaded lineage chart (with its current settings) or of the object graph (all its handling units, also hidden ones) that are not in the list yet, *Reset to selection* goes back.

### Settings and defaults
List = selection, axis `event order`, rows `as listed` (or by first event), high-level band, activity names, movement names off (Nina 2026-11-19: the movement option is now only this switch; labels start exactly above the line, at the height of the other events' markers since Nina 2026-11-23), cut long names on (Nina 2026-11-23: off writes activity names in full instead of cutting them after 16 characters with "…"), same-timestamp boxes and shared-event lines on. At most 50 rows (`MAX_HANDLING_UNITS`).

### Where it lives in the code
- `instances/charts.py`: `timeline_figure(derivation, handling_units, axis, ..., by_first_event, label_movements, cut_activity_labels) -> (plotly JSON, notes)`; it renames $loc^k$, $ploc^k$ to `loc`, `ploc` and runs `timeline.object_timeline.timeline_relations` and `object_timeline`.
- Route `POST /{ocel_id}/instances/timeline` (`getHuTimeline`).
- `components/HuTimelineChart.tsx`: shows the figure with `ThemedPlot` (the figure's template is dropped so Ocelescope's theme applies).

### Alternatives
- Drawing the timeline in the frontend from prepared tables (planned in the resource doc): more work; the backend figure keeps one implementation of the drawing.
