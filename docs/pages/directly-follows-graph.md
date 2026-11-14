# Directly-follows graph page

Status: **suggestion** (2026-11-14), built from Nina's brief in the project thread "Build directly-follows graph page"; to be reviewed by Nina before it counts as conceptualised.
User-facing description: module note `overview/module/Directly-Follows Graph Page.md` (outside this repo).
The page will be extended (more interaction) later; the code is split into one step per module so that steps can be replaced one at a time.

## Brief (Nina, 2026-11-14)
- Replaces Ocelescope's default DFG module. Disliked there: the layout (all start nodes on the same height at the top), the two places for settings (discovery form and viewer), activity names that are cut off, too large frequency labels on the arcs.
- All settings in a sidebar of the page.
- Only the directly-follows relations of the handling units are shown by default; other object types involved appear only as circles on the activity nodes (as in TOTeM's discovery view, https://totem-tool.com/#discovery), unless they are selected.
- Arc and path filter thresholds per object type.
- Object types named in the model; activity frequencies in the nodes.
- Layout and look of Ocelescope's earlier graph view of DFGs (ELK, `DirectlyFollowsGraph._visualize_graph` in `ocelescope/resource/default/dfg.py`), with smaller arc labels and complete activity names.

## Page structure
Configuration bar (shared header, `configuration.md`), then two columns: the **graph** (left, 760 px high, pan and zoom with the mouse; buttons zoom in, zoom out, fit) with the **legend** in grey above it, and the **settings sidebar** (right, 340 px, sticks to the top; Nina, 2026-11-14).
The view is fitted to the graph when it changes, but never enlarged beyond 100 %, so a small graph is not blown up.
The page ignores the overview page's filter bar (it has no filter bar of its own yet). It uses the configuration for the handling units HU, the movement events M and the processing operations P (tie order); it does not use locations yet.

## 1. What the graph shows
For a log with object types $OT$, the user selects $OT_{sel} \subseteq OT$ (default: the object types that contain handling units).
**Considered objects** $O_{ot}$ of a selected type $ot$: its handling units if $ot$ contains handling units (with HU given as object types: all objects of $ot$; with a HU table: only the listed objects of $ot$), otherwise all objects of $ot$.
**Trace** of an object: its events (e2o, an object linked twice to an event counts once) in `seq` order: time, AS4 tie rank (movements, processing operations, rest), event id (`visits/order.py`), so the arcs agree with otrace(hu) on all other pages.

| Element | Shows | Calculated by |
|---|---|---|
| Activity node | full activity name (12 px, wrapped at 150 px, never cut), its **frequency** below (events of the activity in the included traces), one small circle per **unselected** object type involved in these events | `dfg/nodes.py` |
| Start node ▶ / end node ■ | one per selected type with a kept start / end arc; filled with the type's colour, the type's **name** below; arcs from start nodes and to end nodes are **grey** (Nina, 2026-11-14) | `dfg/arcs.py` (null source / target) |
| Arc | directly-follows arc $(a, b)$ between two activities of a selected type in its colour; thickness 1.2–4 px by $\sqrt{count / \max count}$ of the type; small label (10 px) with the traversals or the objects | `dfg/arcs.py` |
| Hover activity | name, events shown (and in the log if different), per involved type: events and objects | `components/DfgGraph.tsx`, `activityTooltip` |
| Hover circle | "truck: 2 of 2 events, 1 objects" | `DfgGraph.tsx`, `ActivityNode` |
| Hover arc label | traversals and objects of the arc | `DfgGraph.tsx`, `ArcEdge` |

Definitions (`dfg/arcs.py`): for an object $o$ of type $ot$ with trace $\langle e_1, \dots, e_n \rangle$, the arcs are $(\triangleright_{ot}, act(e_1))$, $(act(e_i), act(e_{i+1}))$ and $(act(e_n), \square_{ot})$. $count(arc)$ = traversals (an object repeating an arc counts once per traversal), $objects(arc)$ = distinct objects.
**Included traces**: the traces of the objects whose path is kept by the path filter. They are the baseline of everything else: arcs, frequencies, involved types and the activity list only use events on included traces (Nina, 2026-11-14).
Shown activities: every activity that is the source or target of a kept arc and is not deselected. Frequency of activity $a$: $|\{e \mid act(e) = a,\ e$ on an included trace$\}|$.
Involved types of $a$: for every object type (selected or not), the frequency events of $a$ that involve at least one object of that type, and its distinct objects there.

## 2. Settings (sidebar, top to bottom)
| Setting | Values | Default | Effect |
|---|---|---|---|
| **Reset to defaults** (top) | button | – | every setting of the page back to its default (selection, general and own thresholds, activities, display) |
| **General thresholds: Paths** | 0–100 %, step 1 | 30 % | path threshold $\pi_{ot}$ of every selected type **without own value** |
| **General thresholds: Arcs** | 0–100 %, step 1 | 10 % | arc threshold $\alpha_{ot}$ of every selected type without own value |
| **Object types** (searchable, scrollable list; checkbox, colour swatch, number of considered objects, badge "HU") | any subset of $OT$ | the types with handling units | checked: arcs, start and end nodes of the type are drawn; unchecked: the type only appears as circles on the activity nodes whose events involve it. Unchecking all types leaves an empty graph. |
| **Own thresholds** (unfold with the arrow of a type) | Paths and Arcs, 0–100 % | the general values | own $\pi_{ot}$ / $\alpha_{ot}$ of this type; the general sliders no longer change it. A type with an own value is marked in the list, e.g. "P 100 % · A 100 %"; "Use the general thresholds" removes the own values. The line next to a slider says "x of y paths · a objects" / "x of y arcs" kept. |
| **Activities** (searchable, scrollable list, by number of events in the log, descending; ties alphabetically) | any subset | all | see "Activity selection" below |
| **Arc labels** | Traversals / Objects | Traversals | the number on every arc: $count$ or $objects$ |
| **Direction** | Left to right / Top to bottom | Left to right | ELK's `elk.direction` (RIGHT / DOWN) |
| **Compact layout** | on / off | off | smaller spacing between nodes, arcs and layers (`COMPACT_OPTIONS`), e.g. to export the whole graph as a figure for a paper |

For both thresholds, **100 % keeps everything** and lower values keep less (Nina, 2026-11-14).

**Path threshold** $\pi_{ot}$ (`dfg/variants.py`): the path (variant) of an object is the sequence of its activities. Paths of $ot$ are ranked by their number of objects (descending; ties alphabetically by the path), and a path is kept if the objects of the paths ranked before it cover less than $\pi_{ot}/100 \cdot |O_{ot}|$. So the most frequent paths are kept until they cover at least $\pi_{ot}$ % of the objects. 0 % keeps none.
Ties are deliberately not kept together: in logistics logs most objects often have a path of their own, and keeping ties would then keep everything at any threshold.

**Arc threshold** $\alpha_{ot}$ (`dfg/arcs.py`, `arc_filter`): of the $n$ arcs of $ot$ **between two activities** on the included traces, the $\lceil \alpha_{ot}/100 \cdot n \rceil$ most frequent are kept (ranked by traversals, then objects, then source and target alphabetically). Start and end arcs are **always** kept. 0 % keeps only start and end arcs. The path filter is applied first.
Both comparisons are done in whole numbers times 100, so e.g. 60 % of 5 objects is exactly 3.
An arc filter can leave an activity without outgoing (or incoming) arc; it is still shown, as long as one kept arc touches it.

**Activity selection** (`arcs.remove_activities`): an activity is shown as checked when it lies on an included trace, whether or not it is drawn; activities on no included trace are greyed out (checking them could not add anything). Unchecking an activity removes its node and every arc touching it; no new arc is drawn between its neighbours (no projection). Unchecking an activity that is not drawn changes nothing. The arc counts in the type unfolds are taken after this removal.

**Independence of settings**: changing one setting leaves all others as they are (e.g. a deselected activity stays deselected when a threshold changes; a general slider does not touch own values).
Settings are kept per log across page switches and reloads (`lib/pageState.ts`, key `dfg.v2.<log id>`; settings saved by an older version are completed with the defaults). A slider sends its value when released.

**Example** (running example, Level 3, default selection coil and slab): with 100 % / 100 %: 9 activities; slab: ▶ → cast slab → inspect slab → roll → ■ (1 each); coil: 18 arcs (6 start/end, 12 between activities), e.g. load truck → unload truck 3 traversals (3 coils), ▶ → roll 2, quality check → ■ 4; frequencies crane move 4, quality check 4, load truck 2, roll 1.
Defaults (30 % / 10 %): all 5 coils have different paths, so 2 paths (2 coils) are kept, and 10 % of their arcs between activities, rounded up.
coil with Paths 50 %: 3 paths (3 coils). coil with Paths 100 % and Arcs 20 %: $\lceil 0.2 \cdot 12 \rceil = 3$ arcs between activities (load truck → unload truck 3, unload truck → crane move 3, crane move → load truck 2) plus the 6 start and end arcs.

## 3. Layout
ELK layered (`lib/dfgLayout.ts`, `layoutGraph`, options `ELK_OPTIONS`; with "Compact layout" `COMPACT_OPTIONS`): the options of Ocelescope's `DIRECTED_ELK_GRAPH_LAYOUT` (network-simplex layering and node placement, layer-sweep crossing minimisation, spline edges), with somewhat smaller spacing between layers.
- Start and end nodes get **no** layer constraint: network-simplex layering places them right before their first (after their last) activity instead of all at the top.
- Activity nodes are tight around their text (`SIZES`: name 12 px, frequency 10 px, padding 2 × 5 px) and sized from the rendered text (`textWidth` measures with an invisible span in the page), so names are never cut; names wrap at spaces beyond 150 px (`wrapName`).
- Arc labels are ELK edge labels (centre placement), so ELK reserves room for them; the object-type name below start and end nodes is an outside node label (`OUTSIDE V_BOTTOM H_CENTER`).
- Arrowheads have a fixed size (about 8 px), independent of the arc's thickness.
- Colours: `colourMap` (`lib/palette.ts`) over all object types of the log, most objects first, so a type keeps its colour when the selection changes.
- Rendering: React Flow (`@xyflow/react`), nodes not draggable; the edge paths come from ELK (`sectionPath`; spline bend points are cubic Bézier control points).

## 4. Code
- Backend (`backend-modules/location-ocpm/src/ocelescope_module_location_based_ocpm/`):
  - `dfg/traces.py`: `considered_objects(objects, object_types, handling_units)`, `object_traces(e2o, events, objects, processing)`.
  - `dfg/variants.py`: `object_variants`, `variant_ranking`, `kept_variants(ranking, thresholds)`, `path_filter(traces, thresholds)`.
  - `dfg/arcs.py`: `directly_follows_arcs(traces)`, `objects_per_type`, `arc_filter(arcs, thresholds)`, `remove_activities(arcs, activities)`.
  - `dfg/nodes.py`: `shown_activities`, `activity_frequencies`, `involved_object_types(traces, activities, typed_e2o)`.
  - `dfg/graph.py`: defaults `DEFAULT_PATH_THRESHOLD` (30) and `DEFAULT_ARC_THRESHOLD` (10); request and response models (`TypeSetting`, `TypeThresholds`, `DfgRequest`, `DirectlyFollowsGraph`, `DfgActivityOption`, …), `log_frames(ocel, derivation)`, `default_selection`, `resolve_selection(request, objects, handling_units)`, `type_overview`, `selected_traces`, `directly_follows_graph(frames, selection, traces, excluded_activities)`.
  - `dfg_routes.py`: `POST /{ocel_id}/dfg` (`getDirectlyFollowsGraph`), body `{"object_types": [...] | null, "path_threshold", "arc_threshold", "type_thresholds": [{"object_type", "path_threshold"?, "arc_threshold"?}], "excluded_activities": [...]}`; caches the log's frames and the traces per selection (LRU, `CACHE_SIZE`), keyed by the derivation's cache key, so a slider only reruns the filters.
- Frontend (`frontend-modules/location-ocpm/src/`): `routes/DirectlyFollowsGraph.tsx` (page, state, query), `components/DfgSettings.tsx` (sidebar, `DEFAULT_STATE`, `toRequest`; hover texts `INFO`), `components/DfgGraph.tsx` (drawing, legend), `lib/dfgLayout.ts` (layout, sizes `SIZES`, `ELK_OPTIONS`, `COMPACT_OPTIONS`).
- Tests: `tests/test_dfg.py`. Demo notebook: `notebooks/directly_follows_graph.ipynb`.

## 5. How to change
- Other defaults: `DEFAULT_PATH_THRESHOLD` / `DEFAULT_ARC_THRESHOLD` in `dfg/graph.py` **and** `DEFAULT_STATE` in `DfgSettings.tsx`.
- Other tie order of traces: `visits/order.py`, `tie_rank` (changes all pages).
- Other path filter (e.g. keep ties, rank by other criteria): `variants.kept_variants`; adapt `test_path_threshold_keeps_most_frequent_paths`.
- Other arc filter (e.g. a minimum share of objects per arc, or Ocelescope's connectivity-preserving filter): `arcs.arc_filter`; adapt `test_arc_threshold_keeps_most_frequent_relations_and_all_start_and_end_arcs`.
- Activity deselection with projection (connect the neighbours): `arcs.remove_activities` would have to work on the traces instead of the arcs.
- Other frequency in the nodes (e.g. all events of the activity in the log, `log_events`, already sent): `nodes.activity_frequencies` or the frontend `ActivityNode`.
- A new setting: field in `DfgRequest` (backend), `pnpm run build:modules`, a field in `DfgState`/`DEFAULT_STATE`/`toRequest` and a control in `DfgSettings.tsx`, a row in section 2 here and in the module note.
- Look: `SIZES`, `ELK_OPTIONS` and `COMPACT_OPTIONS` in `lib/dfgLayout.ts`; arc thickness `strokeWidth`, start/end grey `GREY` and arrow size in `DfgGraph.tsx`.

## 6. Alternatives considered
- **Ocelescope's `Graph` visualisation** (`<Visualization>` of `@ocelescope/resources`): same layout engine, but no circles on nodes, fixed node width (cut names) and no room for later interaction. Own React Flow rendering instead.
- **Arc threshold as a minimum share of objects per arc** (round 1): replaced so that both sliders read the same way, 100 % = all (Nina, 2026-11-14).
- **Path filter keeping ties**: degenerates when every object has its own path (see section 2).
- **Frequency = all events of the activity in the log**: does not change with the selection and the path filter; kept as hover information and as the order of the activity list.
- **Start nodes in the first layer** (as in the current Ocelescope viewer): what Nina disliked.

## 7. Open points (for Nina)
- Default path threshold: the brief says "30 % of paths (i.e. ... cover at least 10 % of objects)"; implemented as 30 % of the objects.
- Should the page follow the overview filter bar (or get its own filters)?
- Should circles be shown for all involved unselected types, or only some (e.g. resources, vehicles)? Should they carry a letter or the count?
- Locations are not used yet (e.g. activity × location nodes, or location-based colouring).
