# Transformations page (draft)

Status: **draft page** (Nina 2026-11-23: "make sure this page is a draft page for now"). Sidebar label "Transformations (draft)", yellow notice at the top.
Upper part as in the playground (page filters, key numbers, charts, transformation profile; agreed 2026-10-19 in the playground thread), lower part the transformation type graph of `overview/concepts/Transfromations/Lineage (DRAFT).md`, section "Transformation Type Level Model" (outside this repo).
User-facing description with a step-by-step example: `overview/module/Transformations Page (Draft).md` (outside this repo).
Demo: `notebooks/transformations_page.ipynb`.

The page reads $T$, $cons$ and $prod$ as configured (`docs/resources/transformation-inputs.md`); it ignores the filter bar of the overview page.
Without transformation events in the configuration it only shows a notice.
Locations are only used by the locations chart and the "by location" segments: $loc$ at the level of the settings bar, $\widehat{hl}$ in Locations: high.

## Definitions
For a transformation event $e \in T$ (`transformations/events.py`):
- input $in(e) = [otype(hu) \mid hu \in cons(e)]$, output $out(e) = [otype(hu) \mid hu \in prod(e)]$ (multisets);
- **transformation type** $(in(e), out(e))$, label "1 slab → 2 coil": per side "count type", types alphabetical, joined by " + ", "∅" for an empty side (the playground's "recipe");
- **recipe** $(act(e), in(e), out(e))$ (concept note), label "roll: 1 slab → 2 coil";
- **kind**: both, consumption only ($prod(e) = \emptyset$), production only ($cons(e) = \emptyset$).

Running example ($T = \set{e1, e3, e15}$):

| event | activity | input | output | transformation type | kind |
| --- | --- | --- | --- | --- | --- |
| e1 | cast slab | ∅ | 1 slab | ∅ → 1 slab | production only |
| e15 | cut | 1 coil | 1 coil | 1 coil → 1 coil | both |
| e3 | roll | 1 slab | 2 coil | 1 slab → 2 coil | both |

## Page filters
### What it shows
"Consumes" and "Produces" (object types, with their number of transformation events) and "Kind" (all, both, consumption only, production only).
### How it is calculated
`events.filter_events`: an event is kept if it consumes one of the selected "consumes" types AND produces one of the selected "produces" types AND has the selected kind; empty pickers set no condition. Filters keep whole events, so a type or recipe is never cut.
### Example
Consumes slab keeps e3; kind production only keeps e1.
### Where it lives in the code
`transformations/events.py` (`TransformationFilter`, `filter_events`); query parameters `consumes`, `produces`, `kind` (`transformation_routes.get_transformation_filter`); frontend `components/TransformationOverview.tsx` (`TransformationFilterBar`), state `lib/transformations.ts` (`useTransformationFilter`, kept across page switches).
### How to change it
New filter: field in `TransformationFilter`, condition in `filter_events`, query parameter in `get_transformation_filter`, control in `TransformationFilterBar`, regenerate the API client.

## Key numbers
### What it shows
Transformation events, transformations, transformation activities, transformation types, recipes, lineage relations, HUs produced at least once, HUs consumed at least once; below them the split by kind.
### How it is calculated
`key_numbers.key_numbers` over the kept events: transformations = consumed HUs + HUs produced at events without consumption (`transformation_count`); lineage relations = $\sum_e \lvert cons(e) \rvert \cdot \lvert prod(e) \rvert$; the shares divide by the HUs with at least one event.
### Example
Running example: 3 events, 3 transformations (s1 at e3, c2 at e15, s1 at e1), 3 activities, 3 types, 3 recipes, 3 lineage relations, produced 4 of 6, consumed 2 of 6; both 2 · consumption only 0 · production only 1.
### Filtering
All numbers follow the page filters; the shares' denominator does not.
### Where it lives in the code
`transformations/key_numbers.py`; route `GET /{ocel_id}/transformations/overview` (`TransformationOverview`, with the filter options `type_counts`); frontend `TransformationKeyNumberTiles`.
### Alternatives
"Recipes" is new compared to the playground (which had only the transformation types, called recipes there), because the type graph shows recipes.

## Charts
### What it shows
Four bar charts (2×2), each with 10 bars (top or bottom 10, one switch for all; the rest is left out, the subtitle says how many):
- Transformation activities: events per activity, by kind (default), transformation type, location or none;
- Transformation types: events per type, by activity (default), kind, location or none;
- Transformation locations: events per location, by activity (default), kind, transformation type or none;
- Unique counts: distinct transformation types per activity, or distinct activities per transformation type.
### How it is calculated
`charts.transformation_bar_chart`: units are the kept events (`chart_units`), one row per (event, location) if locations are involved; bar and segment heights count distinct events, so an event at two locations counts once at each. Step 2 is the generic `overview.overview_charts.bar_chart` (colours per chart, segments beyond 95 % of a bar grey "other", "–" hatched).
### Example
Activities by kind: cast slab (production only), cut (both), roll (both), 1 event each. Locations by activity: A1 2 (cast slab, roll), B1 1 (cut).
### Where it lives in the code
`transformations/charts.py`; route `GET /{ocel_id}/transformations/bar-chart`; frontend `components/TransformationCharts.tsx` (draws with `traces` and `Legend` of `OverviewCharts.tsx`).
### Alternatives
The playground summed the bars beyond the 10th into an "other" bar; left out here (Nina 2026-11-13: no aggregated "other" bar). Clicking a bar adds no filter (the page has no global filter bar).

## Transformation profile
### What it shows
One row per transformation type: type, kind, events, transformations, lineage relations, typical activity (share, number of activities); a click unfolds its top 5 activities (each one a recipe of the type). Sortable, searchable (type or activity), paged.
### How it is calculated
`profile.type_profile` groups the kept events by transformation type.
### Example
"1 slab → 2 coil": both, 1 event, 1 transformation, 2 lineage relations, roll 100 % · 1 activity.
### Where it lives in the code
`transformations/profile.py`; route `GET /{ocel_id}/transformations/profile` (all rows; sorting, search and pages in the browser); frontend `components/TransformationProfile.tsx`.

## Transformation type graph
### What it shows
Bipartite graph: object types (ellipses, each in its colour of the whole module, `useObjectTypeColours`, `docs/resources/object-type-colours.md`; legend of the download in that order) and recipes (rectangles: activity, frequency, share of the transformation events; hover: id, recipe, kind). Arcs object type → recipe (input) and recipe → object type (output), labelled with the handling units of the type per event of the recipe, coloured by object type, as wide as the handling units that flowed along them (hover the label).
Object types also show the handling units of the type with a **full lifecycle** (produced and finally consumed in the log, lifecycle class "both" of the HU profile) and, optionally, the **median lifetime** (and the **IQR**, Q3 − Q1) of these handling units, their lifespan $last(hu) - first(hu)$ = production to final consumption (Nina 2026-11-24). Both are over the whole log, independent of the page filters and the slider; hover an ellipse for Q1, Q3 and the number of handling units.
Arrow heads grow with the arc width (`arcArrow`: length $8 + 1.5w$, half width $4 + 0.75w$), and the line ends inside the head, so thick arcs keep a visible point (Nina 2026-11-24).
Settings: frequency slider, quantities (exact | as sets), layout (left to right | top to bottom), lifetime (off | median | median + IQR), recipe frequencies (on | off).
Download (Nina 2026-11-23: "export button for the gozinto graph"): button at the top right of the graph, as on the DFG page: PDF (vector), SVG (vector), HTML (interactive), PNG; option "With legend" (object types and the key of the symbols, on by default). The file shows the whole graph in light colours, whatever part is zoomed in on. File name `transformation-type-graph.<ext>`.
### How it is calculated
`type_graph.py`, one function per step:
1. `event_sides`: one row per (event, side, object type) with the quantity.
2. `recipe_keys`: the recipe of every event; "exact" (concept) or "sets" (sets of object types only, so recipes that differ only in quantities merge).
3. `recipe_table` (frequency, stable ids r1, r2, … by frequency, then label) and `recipe_arcs` (per recipe, side and object type: smallest and largest quantity, handling units over all events).
4. `min_frequency`: the slider value $p$ is a share of the kept transformation events; recipes are ranked by frequency and taken until they cover $p$; every recipe at least as frequent as the last one taken is shown, so the slider sets a minimum frequency.
5. `type_graph`: the recipes with at least that frequency, their object types and arcs (node ids "recipe:r1", "type:coil").
6. `type_lifecycles` (of `instance_routes.cached_profile`, the HU profile of the instance page, cached per derivation): per object type the handling units, those with a full lifecycle and the quartiles (linear interpolation) of their lifetimes; `type_graph(..., lifecycles=...)` adds them to the object types.
### Example
Running example, 100 %: r1 "cast slab: ∅ → 1 slab", r2 "cut: 1 coil → 1 coil", r3 "roll: 1 slab → 2 coil"; arcs r1 → slab (1), coil → r2 (1), r2 → coil (1), slab → r3 (1), r3 → coil (2).
Full lifecycles (test `test_type_lifecycles_of_the_running_example`): coil 1 of 5 (c2, 12 h; c1 and c4 are not finally consumed, c3 and c5 not produced), slab 1 of 1 (s1, 2 h); so coil shows "1 full lifecycle" and, with median + IQR, "median 12 h · IQR 0".
With a second roll producing 3 coils (test `test_type_graph_quantities`): exact gives two roll recipes; as sets gives one, "roll: slab → coil", frequency 2, output arc "2–3", 5 handling units.
Slider: frequencies 5, 3, 1, 1 and 80 % give minimum frequency 3 (two recipes, 8 of 10 events); 81 % gives 1 (all).
### Filtering
Follows the page filters (the share and the slider refer to the kept events).
### Settings and defaults
Slider 100 % (all recipes), quantities exact, left to right, lifetime off, recipe frequencies on; kept per log (`transformations.graph.<log>`); the slider recalculates 0.4 s after the last move (`SLIDER_DELAY`).
### Where it lives in the code
`transformations/type_graph.py`; route `GET /{ocel_id}/transformations/type-graph` (`coverage` in [0, 1], `quantities`); frontend `components/TransformationTypeGraph.tsx` (ELK layered with `ELK_OPTIONS` of `lib/dfgLayout.ts`, React Flow, layout and zoom kept with `lib/keptView.ts`).
Download: `typeDrawing` (in `TransformationTypeGraph.tsx`: the laid-out nodes and arcs with their light colours) → `typeGraphScene` (`lib/typeGraphDrawing.ts`: plain shapes, ellipses as four Bézier curves, legend) → `downloadScene` (`lib/dfgDownload.ts`, shared with the DFG); menu `components/GraphDownloadMenu.tsx`.
### How to change it
- Other slider semantics (e.g. a plain minimum frequency or share of recipes): `min_frequency`, and the slider text in `TransformationTypeGraph`.
- Arc width: `SIZE.minArc`/`SIZE.maxArc` and the formula in `layoutTypeGraph` (linear in handling units); arrow size `arcArrow` (`lib/typeGraphDrawing.ts`, page and downloads).
- Lifetime over all handling units of a type (not only those with a full lifecycle): drop the `full` filter in `type_lifecycles`; lines of the ellipses: `typeLines` in `TransformationTypeGraph.tsx`.
- Other recipe definitions: `recipe_keys`.
- Download: look of the file in `lib/typeGraphDrawing.ts` (sizes `SIZES`, legend texts in `legendGroups`); formats and the PDF, PNG and HTML writers are shared with the DFG (`lib/dfgDownload.ts`). The PDF uses Helvetica, which has no "→" or "∅", so texts drawn into the file avoid them (hover texts may use them).
### Alternatives
- One rectangle per activity (all recipes of an activity merged): fewer nodes, but recipes with different input types are no longer distinguishable (discussion note `claude_notes/transformations-page-discussion.md`, R3); not built.
- A transformation Sankey (playground): unreadable on the real log (self-loops, dozens of activities); handled in the Sankey discussion.

## Caching
`transformation_routes.cached_events` keeps the transformation event table per derivation key and location column (LRU of 4); filters, charts, profile and graph are computed per request from it.
