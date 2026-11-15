# Directly-follows graph page

Status: **suggestion** (2026-11-14), built from Nina's brief in the project thread "Build directly-follows graph page"; to be reviewed by Nina before it counts as conceptualised.
User-facing description: module note `overview/module/Directly-Follows Graph Page.md` (outside this repo).
The page will be extended (more interaction) later; the code is split into one step per module so that steps can be replaced one at a time.

## Brief (Nina, 2026-11-14)
- Replaces Ocelescope's default DFG module. Disliked there: the layout (all start nodes on the same height at the top), the two places for settings (discovery form and viewer), activity names that are cut off, too large frequency labels on the arcs.
- All settings in a sidebar of the page.
- Only the directly-follows relations of the handling units are shown by default; other object types involved appear only as circles on the activity nodes (as in TOTeM's discovery view, https://totem-tool.com/#discovery), unless they are selected.
- Arc and path filter thresholds per object type.
- Round 6 (Nina, 2026-11-15): "paths" renamed "variants"; activity selection as in Ocelescope (projection before everything else), per object type, default 40 % of a type's activities (3 to 10); arc threshold as Ocelescope's DFG filter, default 100 %; optional "Stay connected" (default on); an arc count slider like Ocelescope's DFG viewer; default variant threshold: one value for all types keeping at least the top 3 variants of each; arcs removable by right click.
- Object types named in the model; activity frequencies in the nodes.
- Layout and look of Ocelescope's earlier graph view of DFGs (ELK, `DirectlyFollowsGraph._visualize_graph` in `ocelescope/resource/default/dfg.py`), with smaller arc labels and complete activity names.

## Page structure
Configuration bar (shared header, `configuration.md`), then two columns: the **graph** (left, 760 px high, pan and zoom with the mouse; buttons zoom in, zoom out, fit) with the **legend** in grey above it, and the **settings sidebar** (right, sticks to the top; Nina, 2026-11-14). The sidebar is 300 px wide by default; dragging its left edge changes the width (220–640 px; a thin line appears on hover), the panel button in its header hides it, and a button in the graph's top right corner brings it back. Width and visibility are kept for the browser tab (`usePageState`, key `dfg.sidebar`, the same for all logs).
The view is fitted to the graph when it changes, but never enlarged beyond 100 %, so a small graph is not blown up.
The page ignores the overview page's filter bar and has no filters beyond its own settings (Nina, 2026-11-14: not for now). It uses the configuration for the handling units HU, the movement events M and the processing operations P (tie order); it does not use locations yet.

## 1. What the graph shows
For a log with object types $OT$, the user selects $OT_{sel} \subseteq OT$ (default: the object types that contain handling units).
**Considered objects** $O_{ot}$ of a selected type $ot$: its handling units if $ot$ contains handling units (with HU given as object types: all objects of $ot$; with a HU table: only the listed objects of $ot$), otherwise all objects of $ot$.
**Trace** of an object: its events (e2o, an object linked twice to an event counts once) ordered by time, then the **DFG boundary rank** (`dfg/traces.py`, `boundary_rank`; Nina, 2026-11-14): among events at the object's first timestamp a transformation event comes first (it creates the object), among events at its last timestamp a transformation event comes last (it consumes the object); if all its events share one timestamp, the first rule applies. Then the AS4 tie rank (movements, processing operations, rest; `visits/order.py`), then event id. Apart from the boundary rank this is the `seq` order of otrace(hu) on the other pages.

| Element | Shows | Calculated by |
|---|---|---|
| Activity node | full activity name (12 px, regular, **bold only in the compact layout**; wrapped at 150 px, never cut), below it one row with its **frequency** (events of the activity in the included traces) followed by one small circle per **unselected** object type involved in these events (same row, so nodes stay flat; Nina, 2026-11-14) | `dfg/nodes.py` |
| Start node ▶ / end node ■ | one per selected type with a kept start / end arc; filled with the type's colour, the type's **name** below; arcs from start nodes and to end nodes are **grey** (Nina, 2026-11-14) | `dfg/arcs.py` (null source / target) |
| Arc | directly-follows arc $(a, b)$ between two activities of a selected type in its colour; thickness 1.2–4 px by $\sqrt{count / \max count}$ of the type; small label (10 px) with the traversals or the objects, plain text sitting on the arc (the arc runs through it, as in Ocelescope's earlier view) | `dfg/arcs.py` |
| Hover activity | name, events shown (and in the log if different), per involved type: events and objects | `components/DfgGraph.tsx`, `activityTooltip` |
| Hover circle | "truck: 2 of 2 events, 1 objects" | `DfgGraph.tsx`, `ActivityNode` |
| Hover arc label | traversals and objects of the arc | `DfgGraph.tsx`, `ArcEdge` |

Definitions (`dfg/arcs.py`): for an object $o$ of type $ot$ with trace $\langle e_1, \dots, e_n \rangle$, the arcs are $(\triangleright_{ot}, act(e_1))$, $(act(e_i), act(e_{i+1}))$ and $(act(e_n), \square_{ot})$. $count(arc)$ = traversals (an object repeating an arc counts once per traversal), $objects(arc)$ = distinct objects.
**Order of the steps** (Nina, 2026-11-15): 1. traces, 2. **projection** on the selected activities, 3. **variant filter**, 4. arcs, **arc threshold**, **arc count**, **arcs removed by hand**, 5. **Stay connected** (optional), 6. nodes.
**Where they run** (Nina, 2026-11-15, for speed): steps 1–3, the arcs of the included traces and the nodes in the backend (route); the arc settings of steps 4–5 in the browser (`lib/dfgArcs.ts`, `lib/dfgView.ts`), so the arc sliders, Stay connected and the right click react without a request. The Python functions of steps 4–5 (`dfg/arcs.py`, `dfg/connectivity.py`) stay for the notebook, the tests and analyses outside the page; `tests/test_dfg_frontend.py` runs the TypeScript version with Node and checks that both give the same arcs (Nina chose to keep both).
**Included traces**: the projected traces of the objects whose variant is kept by the variant filter. They are the baseline of everything after the variant filter: arcs, frequencies and involved types only use events on included traces.
Shown activities: every activity that is the source or target of a shown arc. Frequency of activity $a$: $|\{e \mid act(e) = a,\ e$ on an included trace$\}|$.
Involved types of $a$: for every object type (selected or not), the frequency events of $a$ that involve at least one object of that type, and its distinct objects there.

## 2. Settings (sidebar, top to bottom)
| Setting | Values | Default | Effect |
|---|---|---|---|
| **Compact** (header, next to Reset) | on / off | off | smaller spacing between nodes, arcs and layers (`COMPACT_OPTIONS`) |
| **Reset** (header) | button | – | every setting back to its default (selection, general and own values, activities, Stay connected, arcs removed by hand, display); not the sidebar's width |
| **General: Variants** | 0–100 %, slider or typed (decimals allowed) | **default** (None): `variants.default_variant_threshold`, one value for all selected types (see below) | variant threshold $\pi_{ot}$ of every selected type without own value; *auto* returns to the default |
| **General: Arcs** | 0–100 %, slider or typed | **100 %** (`DEFAULT_ARC_THRESHOLD`) | arc threshold $\alpha_{ot}$ of every selected type without own value |
| **General: Arc count** | 0 to the most arcs of one type, slider or typed (empty = all) | all (None) | arc count $N$ per type for every selected type without own value; the line shows "shown of total arcs" (shown after everything, total = left by the arc threshold) |
| **Stay connected** | on / off | **on** (`DEFAULT_STAY_CONNECTED`) | every shown arc lies on a start-to-end path; arcs added for this are dashed |
| **Arcs removed by hand** (only while there are any) | list with × per arc, "Restore all" | none | right click on an arc (or its label) in the graph adds it; the General divider is marked **manual** while the list is not empty, as the sliders then no longer describe the graph on their own (Nina, 2026-11-15) |
| **Object types** (searchable list; types with handling units first, then by number of objects) | any subset of $OT$ | the types with handling units | checked: arcs, start and end nodes drawn; unchecked: only circles on the activity nodes |
| **Own values** (unfold of a type) | Variants, Arcs, Arc count | the general values | own $\pi_{ot}$, $\alpha_{ot}$, $N_{ot}$; marked in the list, e.g. "V 100 % · A 50 % · N 4"; "Use the general values" removes them |
| **Activities** (searchable list, by events with at least one handling unit, then events in the log, then name) | per selected type any subset | per type: its most frequent 40 % of activities, at least 3, at most 10 | see "Activity selection" below |
| **Arc labels** | Traversals / Objects | Traversals | the number on every arc |
| **Direction** | Left to right / Top to bottom | Left to right | ELK's `elk.direction` |

**Activity selection (projection)** (`dfg/projection.py`; Nina, 2026-11-15): as in Ocelescope's DFG discovery (`ocelescope.discovery.algorithms.dfg_miner`, which removes excluded activities before the directly-follows relations). For every selected type the events of its deselected activities are removed from its traces before anything else: a trace $\langle a, b, c \rangle$ with $b$ deselected becomes $\langle a, c \rangle$, so variants, arcs and frequencies are computed on the projected traces. An object whose projected trace is empty is left out.
The list shows per activity its events with at least one handling unit (`handling_unit_event_counts`); its checkbox (de)selects it for every selected type with events of it (indeterminate if selected for some of them). The unfold lists every object type with events of the activity (`type_activity_counts`: events with at least one considered object of the type); only selected types can be (de)selected. Default per type (`default_activities`, `default_activity_count`): the $\min(n, \max(3, \min(10, \lceil 0.4\,n \rceil)))$ most frequent of its $n$ activities (by events of its considered objects; ties by first occurrence, then name). E.g. $n$ = 7 → 3, 12 → 5, 30 → 10. Once the user changes a type, its full list is stored (`DfgState.activities`), so it no longer follows the default; "Default" in the list header clears all.

**Variant threshold** $\pi_{ot}$ (`dfg/variants.py`): the variant of an object is the sequence of the activities of its projected trace. Variants of $ot$ are ranked by their number of objects (descending; ties by first occurrence in the log, then alphabetically), and a variant is kept if the objects of the variants ranked before it cover less than $\pi_{ot}/100 \cdot |O_{ot}|$. 0 % keeps none; ties are deliberately not kept together.
**Default** (`default_variant_threshold`, Nina 2026-11-15): one threshold for all selected types, the smallest whole percentage that keeps at least the 3 top-ranked variants of every type. A type's third variant is kept by every threshold above the share $s_2$ of its first two variants, so the type needs $\lfloor s_2 \rfloor + 1$ % (`needed_variant_thresholds`; with fewer than 3 variants: above the share of all but its last; 1 variant: 1 %); the default is the largest of these. E.g. running example: 5 coils with a variant each need 41 %, the slab 1 % → 41 % for both.

**Arc threshold** $\alpha_{ot}$ (`arcs.arc_share_filter`, as `DirectlyFollowsGraph.filter_edges` of Ocelescope without its repair): all $n$ arcs of $ot$, **start and end arcs included**, are ranked by objects, then traversals; the first $\lceil \alpha_{ot}/100 \cdot n \rceil$ are kept, plus every arc tied with the last kept one. 0 % keeps none.
**Arc count** $N_{ot}$ (`arcs.arc_count_filter`, like the slider of Ocelescope's DFG viewer `OCDFGViewer` in `@r4pm/components`): of the arcs left by the arc threshold, the first $N_{ot}$ in the order objects, traversals (descending), first occurrence (time of the first traversal), source, target; exactly $N_{ot}$ (ties broken by this order; Nina, 2026-11-15).
**Arcs removed by hand** (`arcs.remove_arcs`): removed after the arc count.
**Stay connected** (`dfg/connectivity.py`, `stay_connected`; as the repair in Ocelescope's `filter_edges`): per type, base graph = the arcs of the included traces without the arcs removed by hand, reduced to the arcs on a start-to-end path (`on_start_end_paths`); required activities = the endpoints of the arcs left after the hand removals; every other base arc is then taken out, least frequent first, unless this cuts a required activity off from the start or the end node. It overrides the arc threshold and the arc count, nothing else: it never adds arcs of removed variants, of deselected activities or removed by hand (Nina, 2026-11-15). Added arcs have `connecting` = true and are drawn dashed.
All percentage comparisons are done in whole numbers times 100 (rounded to 6 decimals), so e.g. 60 % of 5 objects is exactly 3.

**Independence of settings**: changing one setting leaves all others as they are. Settings are kept per log across page switches and reloads (`lib/pageState.ts`, key `dfg.v4.<log id>`; settings saved by an older version are completed with the defaults). A slider sends its value when released.

**Example** (running example, Level 3, default selection coil and slab): defaults: coil activities crane move, quality check, load truck (3 of 7); slab: cast slab, inspect slab, roll (3 of 3); variants 41 % (coil: 3 of 5 variants, 3 coils); arcs 100 %: coil 10 arcs, slab 4.
coil with all activities, Variants 100 %, Arcs 20 %: 18 arcs, $\lceil 3.6 \rceil = 4$, the fourth (2 objects) is tied with four more → 8 arcs. Arc count 2 instead: quality check → ■ (4) and load truck → unload truck (3). slab with Arc count 1: ▶ → cast slab, and Stay connected adds the other three (dashed).

## 3. Layout
ELK layered (`lib/dfgLayout.ts`, `layoutGraph`, options `ELK_OPTIONS`; with "Compact layout" `COMPACT_OPTIONS`): the options of Ocelescope's `DIRECTED_ELK_GRAPH_LAYOUT` (network-simplex layering and node placement, layer-sweep crossing minimisation, spline edges), with somewhat smaller spacing between layers.
- Start and end nodes get **no** layer constraint: network-simplex layering places them right before their first (after their last) activity instead of all at the top.
- Activity nodes are tight around their text (`SIZES`: name 12 px, frequency 10 px, padding 2 × 5 px) and sized from the rendered text (`textWidth` measures with an invisible span in the page), so names are never cut; names wrap at spaces beyond 150 px (`wrapName`).
- Arc labels are ELK edge labels (centre placement, `elk.edgeLabels.inline`: the arc is routed through its label), so ELK reserves room for them; the object-type name below start and end nodes is an outside node label (`OUTSIDE V_BOTTOM H_CENTER`).
- Arrowheads have a fixed size (about 8 px), independent of the arc's thickness.
- Colours: `emphasisColourMap` (`lib/palette.ts`): handling-unit types get the signature colours `SIGNATURE` (petrol, pink, turquoise, blue, orange) first, all other types further categorical colours with opacity `FADED_ALPHA` (0.55), each group in the order of all object types (most objects first), so a type keeps its colour (Nina, 2026-11-15).
- Rendering: React Flow (`@xyflow/react`), nodes not draggable; the edge paths come from ELK (`sectionPath`; spline bend points are cubic Bézier control points).

## 4. Code
- Backend (`backend-modules/location-ocpm/src/ocelescope_module_location_based_ocpm/`):
  - `dfg/traces.py`: `considered_objects(objects, object_types, handling_units)`, `object_traces(e2o, events, objects, processing)`, `boundary_rank`.
  - `dfg/projection.py`: `type_activity_counts`, `handling_unit_event_counts`, `default_activity_count`, `default_activities(counts, object_types)`, `project_traces(traces, included)`; constants `DEFAULT_ACTIVITY_SHARE` (40), `MIN_ACTIVITIES` (3), `MAX_ACTIVITIES` (10).
  - `dfg/variants.py`: `object_variants`, `variant_ranking`, `needed_variant_thresholds`, `default_variant_threshold(ranking, object_types)`, `kept_variants(ranking, thresholds)`, `variant_filter(traces, thresholds)`; `TOP_VARIANTS` (3).
  - `dfg/arcs.py`: `directly_follows_arcs(traces)` (with `first_time`), `arc_order`, `arc_share_filter(arcs, thresholds)`, `arc_count_filter(arcs, counts)`, `remove_arcs(arcs, removed)`, `objects_per_type`, `arcs_per_type`.
  - `dfg/connectivity.py`: `on_start_end_paths(arcs)`, `stay_connected(base, kept)` (networkx).
  - `dfg/nodes.py`: `shown_activities`, `activity_frequencies`, `involved_object_types(traces, activities, typed_e2o)`.
  - `dfg/graph.py`: `DEFAULT_ARC_THRESHOLD` (100), `DEFAULT_STAY_CONNECTED` (True); models `TypeSetting`, `TypeThresholds`, `ArcKey`, `DfgRequest`, `DirectlyFollowsGraph` (with `variant_default`, `arc_count_max`, `removed_arcs`), `DfgObjectType`, `DfgArc` (with `connecting`), `DfgActivityOption`, `DfgActivityTypeOption`; `log_frames(ocel, derivation)`, `default_selection`, `resolve_selection(request, objects, handling_units)`, `type_overview`, `selected_traces`, `directly_follows_graph(frames, selection, traces, activities, stay, removed)`.
  - `dfg_routes.py`: `POST /{ocel_id}/dfg` (`getDirectlyFollowsGraph`), body `DfgRequest` (`object_types`, `variant_threshold`, `type_thresholds` (variant only), `activities`; the arc fields are ignored), answers with **all arcs of the included traces** (each with its `rank` in `arcs.arc_order`) and every activity on them; caches the log's frames and the traces per selection (LRU, `CACHE_SIZE`), keyed by the derivation's cache key.
- Frontend (`frontend-modules/location-ocpm/src/`): `lib/dfgArcs.ts` (`arcShareFilter`, `arcCountFilter`, `removeArcs`, `onStartEndPaths`, `stayConnected`, `filterArcs`: the TypeScript mirror of steps 4–5), `lib/dfgView.ts` (`applyArcSettings`: the drawn graph from the route's graph), `routes/DirectlyFollowsGraph.tsx` (page, state, query, right click handler), `components/DfgSettings.tsx` (sidebar, `DEFAULT_STATE`, `toRequest`, `removeArc`, `PercentSlider`, `CountSlider`, `ActivityRow`; hover texts `INFO`), `components/DfgGraph.tsx` (drawing, legend, `onEdgeContextMenu`), `lib/dfgLayout.ts` (layout, sizes `SIZES`, `ELK_OPTIONS`, `COMPACT_OPTIONS`).
- Tests: `tests/test_dfg.py` (`test_worked_example_of_the_module_note` checks the worked example of the module note; update both together); `tests/test_dfg_frontend.py` (Python and TypeScript arc steps agree; skipped without Node 22.6+). Demo notebook: `notebooks/directly_follows_graph.ipynb`.

## 5. How to change
- Default activities: `DEFAULT_ACTIVITY_SHARE`, `MIN_ACTIVITIES`, `MAX_ACTIVITIES` in `dfg/projection.py`.
- Number of variants of the default threshold: `TOP_VARIANTS` in `dfg/variants.py`.
- Other defaults: `DEFAULT_ARC_THRESHOLD` / `DEFAULT_STAY_CONNECTED` in `dfg/graph.py` **and** `DEFAULT_STATE` in `DfgSettings.tsx`.
- Other tie order of traces: `visits/order.py`, `tie_rank` (changes all pages).
- Other variant filter: `variants.kept_variants`; other arc ranking: `arcs.arc_order` (arc count, sent as `rank`) and the key in `arcs.arc_share_filter` (arc threshold). Any change to steps 4–5 must be made in **both** `dfg/arcs.py` / `dfg/connectivity.py` and `lib/dfgArcs.ts`; `test_dfg_frontend.py` fails otherwise.
- Stay connected overriding hand removals too: pass `all_arcs` instead of `remove_arcs(all_arcs, removed)` as the base in `graph.directly_follows_graph`.
- Other frequency in the nodes: `nodes.activity_frequencies` or the frontend `ActivityNode`.
- A new setting: field in `DfgRequest` (backend), `pnpm run build:modules`, a field in `DfgState`/`DEFAULT_STATE`/`toRequest` and a control in `DfgSettings.tsx`, a row in section 2 here and in the module note.
- Look: `SIZES`, `ELK_OPTIONS` and `COMPACT_OPTIONS` in `lib/dfgLayout.ts`; arc thickness `strokeWidth`, start/end grey `GREY`, dashes of connecting arcs and arrow size in `DfgGraph.tsx`.

## 6. Alternatives considered
- **Ocelescope's `Graph` visualisation** (`<Visualization>` of `@ocelescope/resources`): same layout engine, but no circles on nodes, fixed node width (cut names) and no room for later interaction. Own React Flow rendering instead.
- **Activity deselection without projection** (rounds 1–4: removing the node and its arcs, no arc between its neighbours): replaced by the projection, as in Ocelescope (Nina, 2026-11-15).
- **Arc threshold on arcs between activities only, start and end arcs always kept, no ties** (rounds 2–5): replaced by Ocelescope's ranking (Nina, 2026-11-15).
- **Automatic variant threshold per type** (round 4: the top 3 of each type in full): replaced by one default value for all types (Nina, 2026-11-15).
- **Default variant threshold = share of the top 3, rounded up** (e.g. 60 % for 5 equally frequent coils): keeps the same variants here, but forces 100 % whenever a type has at most 3 variants, although these need much less; the smallest threshold that keeps the top 3 avoids this.
- **Path filter keeping ties**: degenerates when every object has its own variant.
- **Start nodes in the first layer** (as in the current Ocelescope viewer): what Nina disliked.

## 7. Open points (for Nina)
- Should circles be shown for all involved unselected types, or only some (e.g. resources, vehicles)? Should they carry a letter or the count?
- Locations are not used yet (e.g. activity × location nodes, or location-based colouring).
