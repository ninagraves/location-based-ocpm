# Object timeline (draft)

Status: package function, not used by any page yet; the user-facing description (concept and display) is `overview/module/Resources/HU Timeline.md` (outside this repo); filtering is still open.
Demo: `notebooks/object_timeline.ipynb`.

## What it shows
For selected handling units, one row each (top to bottom; default by first event, then id):
- **Band**: upper half $loc$, lower half $\widehat{hl} = agg(loc)$; one colour per location (shared by both halves), hatched on vehicles ($V$), empty at ⊥.
- **Lifespan line** below the band with a tick at the first and last event.
- **Markers**: processing operations ($P$) stars, other non-movement events circles (both above the band, with the activity name at an angle), movements on the band (▲ produced, ▼ consumed, otherwise a vertical tick; a small open diamond instead of the tick if the pickup location differs from the location after the previous event, details in the hover); colour by role at transformation events: produced green, consumed pink, consumed and produced amber, none dark grey.
- Legend entry for hatching: "vehicle".
- **Shared events**: dotted lines between the markers of an event shared by several shown handling units.
- **Same timestamp**: light grey box over the whole height behind tied events.

## How it is calculated
Concept draft, sections 3 and 5:
- After $r_j$, the band shows $loc(r_j)$ up to $r_{j+1}$ (only $loc$, Nina 2026-10-31).
- Lead-in of length $\delta$ before the first event with the location just before its timestamp ($ploc$ of the movement at it if there is one, else of any relation there; `timestamp_before`), unless unknown or the handling unit is produced there.
- After the last event: continuation of length $\delta$, unless the handling unit is consumed there.
- ⊥ stretches are gaps; neighbouring stretches with the same location and vehicle status are merged.
- The high-level band uses $agg(loc)$ (and $agg(ploc)$ for the lead-in); vehicle status from the low-level location, so it is hatched where the handling unit is on a vehicle (Nina 2026-10-31).
- Pickup disagreement: a movement with $ploc \ne \bot$, previous $loc \ne \bot$ and $ploc \ne$ previous $loc$ (`add_pickup_differs`).
- $\delta$: 0.3 positions, or 1 % of the time span (at least 30 s) (halved, Nina 2026-10-31).

## Example
Running example, Level 3, c1 (event order): low-level band A1 [3, 5], A2 [5, 7], B1 [7, 8], T hatched [8, 9], A2 [9, 13], T hatched [13, 14.3]; high-level band A [3, 7], B [7, 8], T [8, 9], A [9, 13], T [13, 14.3]. e13 picks c1 up at A1 although it was at A2: open diamond at e13.
Edge cases: `data/timeline_example/` (see its README).

## Same timestamp
Every event gets its own x, in the order seq: by time; among events with the same timestamp by AS4 (`visits/order.py`: `tie_rank`, `sort_by_seq`, shared with visits, shifts, waiting times, mapping sets and the trace figure): movements, then processing operations, then the rest, each by event id (`add_positions`).
On "event order" x is the rank among all shown events; on "time" the tied events are spread around their timestamp (half the smallest gap between timestamps).
Tied events get a grey box (`tie_groups`).
At Levels 1 to 3 all tied relations of a handling unit have the same `loc`, so the band does not change inside a box.

## Filtering
None (draft outside the tool). The playground timeline ignored global filters; to be decided once the timeline's place in the tool is known (Nina 2026-10-31).

## Settings
- `axis` ("event order" default, or "time"), `handling_units` (selection and order), `max_handling_units` (default 50, Nina 2026-10-31; selection by typed ids as in the playground).
- `processing`: event ids of $P$; None = only the transformation events $T$ (Nina 2026-10-31).
- `roles`: table event, hu, role ("consumed"/"produced"); only rows of transformation events count.
- `agg`, `vehicles`: from a location table via `visits.context.location_context`.
- Figure: `show_high_level`, `show_activity_labels`, `mark_ties`, `link_shared_events`, `reach` ($\delta$), `title`, `width`.

## Where it lives in the code
`backend-modules/location-ocpm/src/ocelescope_module_location_based_ocpm/timeline/object_timeline.py`:
1. `add_high_level_locations(relations, agg)`: high_level, prev_high_level.
2. `add_vehicles(relations, vehicles)`: is_vehicle, prev_is_vehicle.
3. `add_processing(relations, processing)`: is_processing.
4. `add_transformation_roles(relations, roles)`: is_consumed, is_produced.
5. `add_markers(relations)`: marker (processing/movement/other), role.
6. `hu_order(relations, handling_units, max_handling_units)`: row order (at most 50).
7. `add_positions(relations, axis, processing)`: tie_rank, position and x (ties by AS4 via `visits.order.sort_by_seq`).
8. `add_pickup_differs(relations)`: prev_loc, pickup_differs. `timeline_relations(...)` runs 1 to 8.
9. `timestamp_before(relations, level)`: location just before each timestamp (for the lead-in).
10. `band_segments(relations, level, reach)`: the band stretches (`continuation` gives the default reach).
11. `tie_groups`, `shared_events`, `lifespans`.
12. `object_timeline(relations, ...)`: the plotly figure.
Inputs of the running example: `data/running_example/inputs/processing_events.csv`, `transformation_roles.csv`, `locations.csv`. Tests: `tests/test_object_timeline.py`.

## How to change it
- Marker symbols, sizes and role colours: `SYMBOL`, `SIZE`, `ROLE_COLOUR`, `NO_ROLE_COLOUR`; pickup disagreement: `PICKUP_DIFFERS_SYMBOL`, `PICKUP_DIFFERS_SIZE`; limit: `MAX_HANDLING_UNITS`.
- Geometry: `BAND_TOP`, `BAND_BOTTOM`, `MARKER_Y`, `ROW_GAP`, `LABELLED_ROW_GAP`; reach: `ORDER_CONTINUATION`, `TIME_CONTINUATION`, `MIN_TIME_CONTINUATION`.
- Tie order: `visits.order.tie_rank` (changes it everywhere); pickup disagreement rule: `add_pickup_differs`.
- Colours: `trace_figure.location_colours` (ranked by the relations' loc and high_level, as in the trace figure).
- In the tool the figure will be drawn in the frontend (Plotly.js); steps 1 to 11 become the backend's data preparation.

## Alternatives
- Playground (`ObjectTimeline.tsx`, `timeline.py` of material_flow_analysis): one x per timestamp with stacked markers, stars for all non-movement events, red flag rings. Changes are listed in section 9 of the concept draft.
- Ties: stacking or one combined marker per tie group (concept draft, section 7).
- Pickup disagreement: splitting the band stretch before the movement in the middle and showing $ploc$ in the second half (first draft; Nina chose to show $loc$ only and mark the movement instead).
