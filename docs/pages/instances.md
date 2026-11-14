# Instance page

Status: suggestion (Nina 2026-11-14: "an instance page with HU overviews on the instance level, very similar to the playground"); not yet agreed.
User-facing description with a step-by-step example: `overview/module/Instance Page.md` (outside this repo).
Demo: `notebooks/instances.ipynb`.

The page has no sidebar: three cards one below the other (HU profile, Lineage, HU timeline), every chart with its own settings row above it.
It ignores the filter bar of the overview page.
All values use the low-level location $loc = loc^k$ of the selected level (and $\widehat{hl} = agg(loc)$); visits are not used.

## HU profile

### What it shows
One row per handling unit (also those without events): object type, lifecycle class, events, first and last timestamp, lifespan, creation event, final consumption, partial consumptions, parents, children, siblings, distinct low- and high-level locations, first and last location, location changes, locatedness, time on vehicles / in storage / at other locations / unlocated (with a bar of the shares), movements, processing operations, processing activities, co-handled handling units.
Columns come in groups (Lifecycle, Lineage, Locations, Time, Activities) that can be hidden.

### How it is calculated
- Traces: the relations of a handling unit in `seq` order (time, AS4 via `visits/order.sort_by_seq`, event id).
- Creation event $ev_{prod}$, consumption events $E_{cons}$, parents, children, siblings: `lineage/relations.py` (concept: Transformations, "Instance Lineage").
- Final consumption: an $e \in E_{cons}(hu)$ with $time(e) = last(hu)$; partial consumptions: the other $E_{cons}(hu)$.
- Lifecycle: `full` (produced and finally consumed), `produced`, `consumed`, `open`.
- Location change: $loc(r_j) \neq \bot$ and different from the last $loc \neq \bot$ before $r_j$.
- Locatedness: General Concepts, "Locatedness" (handling-unit version).
- Time per location kind: $r_j$ contributes $time(r_{j+1}) - time(r_j)$ to the kind of $loc(r_j)$ (vehicle if in $V$, else storage if in $W$, else other; unlocated if $\bot$); the last relation contributes nothing, so the four times add up to the lifespan.
- Co-handled: distinct other handling units sharing at least one event.

### Example
Running example, `data/running_example/configuration.json` (Level 3): c1 has 9 events, lifespan 11 h, lifecycle `produced` (roll e3), 4 locations, 3 high-level locations, 5 location changes, 2 h on vehicles, 1 h in storage, 8 h at other locations; c2 is `full` (roll e3, cut e15) and co-handled with 4 handling units; c5 is unlocated for 1 h.
Tests: `backend-modules/location-ocpm/tests/test_instances.py`.

### Filtering
Own search and object-type filter only. Search: every word must occur in the lower-case concatenation of id, object type, first and last location, creation and final consumption activity, parents, children and processing activities (`profile.search_text`).

### Settings and defaults
Sort by any scalar column (`profile.SORTABLE`; nulls last, ties by id), 10/25/50/100 rows per page (default 25), all column groups shown. Kept per log in the page state (`instances.table.<ocel>`), as is the selection (`instances.selected.<ocel>`).

### Where it lives in the code
- `backend-modules/.../instances/profile.py`: `ordered_traces`, `lifecycle_basics`, `location_profile`, `location_kind`, `time_per_location_kind`, `transformation_profile`, `co_handled`, `hu_profile` (joins them), `search_text`, `query_profile(profile, search, object_types, sort_by, descending, offset, limit) -> (page, total)`.
- `backend-modules/.../instance_routes.py`: `GET /{ocel_id}/instances/profile` (`getHuProfile`); the profile is cached per derivation key (`cached_profile`, LRU of 4), so paging and sorting only rerun `query_profile`.
- `frontend-modules/.../components/HuProfileTable.tsx` (mantine-datatable, server-side paging and sorting; `duration` formats seconds), `routes/Instances.tsx` (selection pills, cards).

### How to change it
- New column: add it to the matching step function in `profile.py`, to `SORTABLE` if scalar, to `HuProfileRow` in `instance_routes.py`, rebuild the API client (`pnpm run build:modules`) and add it to `columns` in `HuProfileTable.tsx`; extend the test.
- Other notion of final consumption or lifecycle: `transformation_profile`.
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

## HU timeline

### What it shows
The resource `docs/resources/object-timeline.md` for the selected handling units, or for all handling units of the loaded lineage (selected first).

### Settings and defaults
Handling units `selected`, axis `event order`, rows `as selected` (or by first event), high-level band, activity names, same-timestamp boxes and shared-event lines on. At most 50 rows (`MAX_HANDLING_UNITS`).

### Where it lives in the code
- `instances/charts.py`: `timeline_figure(derivation, handling_units, axis, ..., by_first_event) -> (plotly JSON, notes)`; it renames $loc^k$, $ploc^k$ to `loc`, `ploc` and runs `timeline.object_timeline.timeline_relations` and `object_timeline`.
- Route `POST /{ocel_id}/instances/timeline` (`getHuTimeline`).
- `components/HuTimelineChart.tsx`: shows the figure with `ThemedPlot` (the figure's template is dropped so Ocelescope's theme applies).

### Alternatives
- Drawing the timeline in the frontend from prepared tables (planned in the resource doc): more work; the backend figure keeps one implementation of the drawing.
