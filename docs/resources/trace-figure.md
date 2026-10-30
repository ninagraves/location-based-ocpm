# Trace figure (draft)

Status: draft for the visit conceptualisation (`overview/Single Level Visit Mappings.md`).
Not used by any page yet; it will be discussed with Nina and changed before it goes into the tool.

## What it shows
The object traces of several handling units, one block per handling unit (top to bottom in the given order; y label: the handling unit and, below it, its object type in brackets):
- **Low-level row**: one marker per hu-event relation, coloured by its current location $loc$ at the selected level.
  Circles for ordinary locations, open circles for vehicles ($V$), diamonds for storage units ($W$), a grey × for ⊥.
  A line joins the relations of the trace; the event id is written at an angle above each marker.
- **High-level locations** $\widehat{hl}$, in one of four styles (`high_level_style`; under discussion):
  - "squares": a row of squares below the low-level row, one per relation (grey × for ⊥);
  - "ribbon" (default; Nina's choice, 2026-10-29): a row below with one thick bar per run of consecutive relations with the same high-level location, labelled with its name;
  - "shading": a tinted, outlined box behind the low-level row per run, labelled with its name (no extra row);
  - "outline": the low-level markers get a thick ring in the high-level colour (no extra row).
  - Run labels ("ribbon", "shading") are only shown where they fit (Nina, 2026-10-29); otherwise the legend and the hover name the location.
    Whether a label fits is estimated from `width` (figure width, default 1200 px), `NON_PLOT_WIDTH`, `CHAR_PX` and `LABEL_PADDING_PX`, since plotly in Python does not know the rendered text width; the x range is fixed accordingly.
    In the tool (Plotly.js), the rendered width can be measured instead.
- **Visits** (optional): below the high-level row, one block of lanes per visit group (e.g. "maximal", "resolved").
  The group name is written left of its lanes (κ belongs in the title, not in the group name).
  One bar per visit from its first to its last relation, outlined (filled for the groups in `filled_groups`; dashed outline for the groups in `dashed_groups`, default "maximal", Nina 2026-10-30), coloured by its high-level location; a visit at ⊥ (high_level null; ⊥ visits have κ(⊥) = 0, Nina 2026-10-30) is grey.
  Visits sharing relations are put in different lanes, so contained and overlapping visits are visible.
- Dashed vertical lines join the relations of an event shared by several shown handling units (not for the "trace position" axis).
- Events with the same timestamp get a very light, transparent grey background box (`mark_ties`, colour `TIE_FILL`; Nina 2026-10-30): over the whole figure height on the "event order" and "time" axes; on the "trace position" axis per handling unit only (around the tied relations of that unit, its rows and visit lanes), since tied events of different units do not line up there. A legend entry "same timestamp" explains it.
- Hover on a relation: event, activity, movement/transformation, handling unit, trace position, time, both locations; on a visit bar: location, group, first and last event and positions.

Low-level and high-level locations share one colour map (ranked by frequency in the figure), so a location mapped to itself has one colour on both rows.

## How it is calculated
$\widehat{hl}((e,hu)) = agg(loc((e,hu)))$, ⊥ if $loc((e,hu)) = \bot$; $agg$ may be partial and is completed by the identity.
The trace position is the index in $otrace(hu)$ (time, then event id).

## Settings
- `axis`: "event order" (default; rank of the event among all shown events, so shared events line up), "trace position" (index in $otrace(hu)$, as in the visit definition), or "time" (events with the same timestamp are spread side by side around it in event id order, over at most `TIE_SPREAD` = half the smallest gap between timestamps; `add_tie_offsets`).
- `agg`, `vehicles` ($V$), `storage_units` ($W$): until they are inputs of the tool, passed as arguments (in the notebook read from `data/running_example/inputs/locations.csv` with `location_context`).
- `visits`: a table with columns hu, high_level (null = ⊥), first_event, last_event, group, and optionally visit_id (Nina 2026-10-30: shown in the middle of the bar and in the hover, to talk about single visits; `show_visit_ids=False` hides it). Visits are not computed yet; `notebooks/trace_figure.ipynb` passes a hand-written table (maximal visits at κ = 2), for illustration only.

## Example
`notebooks/trace_figure.ipynb` (start with `uv run --with jupyter jupyter lab notebooks/trace_figure.ipynb`) demos every function and parameter on the running example (Level 3, $agg$: A1, A2 → A; B1 → B; T unmapped; $V$ = {T}, $W$ = {B1}): the preparation steps, the three axes, visits (outlined and filled), the four high-level styles, label fitting and `width`, and switching labels and links off.

## Filtering
None (draft outside the tool).

## Where it lives in the code
`backend-modules/location-ocpm/src/ocelescope_module_location_based_ocpm/visits/trace_figure.py`, one function per step:
1. `add_high_level_locations(relations, location, agg)`: column high_level.
2. `add_location_kinds(relations, location, vehicles, storage_units)`: column location_kind (vehicle wins if a location is in both).
3. `add_x_positions(relations, axis)`: columns position and x.
4. `location_colours(names)`: location → colour (module palette, light scheme).
5. `high_level_runs(relations)`: runs of equal high-level location per handling unit (for "ribbon" and "shading").
6. `visit_lanes(visits)`: column lane (greedy interval packing per handling unit and group; containing visits above contained ones).
7. `trace_figure(relations, visits, filled_groups, dashed_groups, high_level_style, show_event_labels, link_shared_events, mark_ties, show_visit_ids, title)`: the plotly figure.
`relations_for_figure(relations, location, handling_units, agg, vehicles, storage_units, axis)` runs steps 1 to 3 on a relations frame (a saved level mapping or `Derivation.relations`).
`visits/context.py`: `location_context(table)` reads $agg$, $V$, $W$ from a table with one row per location (columns location, high_level, is_vehicle, is_storage; draft format), e.g. `data/running_example/inputs/locations.csv`.
Tests: `tests/test_trace_figure.py`.

## How to change it
- Marker shapes: `LOW_SYMBOL`, `HIGH_SYMBOL`, `BOTTOM_SYMBOL`; vertical spacing: `HIGH_OFFSET`, `LANE`, `BAR`, `GAP`, `LABEL_OFFSET`, `RIBBON`, `SHADE`; trace line: `TRACE`, `TRACE_WIDTH`.
- Colours: `CATEGORICAL` is a copy of the light slots of `frontend-modules/location-ocpm/src/lib/palette.ts`.
- In the tool, the figure will be drawn in the frontend (Plotly.js, like the other charts); the Python steps 1 to 5 then become the backend's data preparation.

## Alternatives
- Playground figure (`VisitFigure.tsx` of material_flow_analysis): same idea (dots for locations, squares for high-level locations, visit bars in lanes, guides), x axis per-HU position or time only. Added here: event-order axis with shared-event lines, vehicle/storage symbols, ⊥ markers, visit groups as parameters.
