# Object timeline (draft)

Status: draft; the concept is in `claude_notes/Object Timeline (draft).md` (outside this repo) and not approved yet.
Not used by any page yet. Demo: `notebooks/object_timeline.ipynb`.

## What it shows
For selected handling units, one row each (top to bottom; default by first event, then id):
- **Band**: upper half $loc$, lower half $\widehat{hl} = agg(loc)$; one colour per location (shared by both halves), hatched on vehicles ($V$), empty at ⊥.
- **Lifespan line** below the band with a tick at the first and last event.
- **Markers**: processing operations ($P$) stars, other non-movement events circles (both above the band, with the activity name at an angle), movements on the band (▲ produced, ▼ consumed, otherwise a vertical tick); colour by role at transformation events: produced green, consumed pink, consumed and produced amber, none dark grey.
- **Shared events**: dotted lines between the markers of an event shared by several shown handling units.
- **Same timestamp**: light grey box over the whole height behind tied events.

## How it is calculated
Concept draft, sections 3 and 5:
- After $r_j$, the band shows $loc(r_j)$ up to $r_{j+1}$.
- If $r_{j+1}$ has a later timestamp and the location just before that timestamp, $ploc_t(hu)$, is known and differs from $loc(r_j)$, the stretch is split in the middle and the second half shows $ploc_t(hu)$. $ploc_t(hu)$ is $ploc$ of the movement at $t$ (unique by RQ3) if there is one, else $ploc$ of any relation at $t$.
- Lead-in of length $\delta$ with $ploc_{t_1}(hu)$ before the first event, unless unknown or the handling unit is produced at $t_1$.
- After the last event: continuation of length $\delta$, unless the handling unit is consumed there.
- ⊥ stretches are gaps; neighbouring stretches with the same location and vehicle status are merged.
- The high-level band uses $agg(loc)$ and $agg(ploc)$; vehicle status from the low-level location.

## Example
Running example, Level 3, c1 (event order): low-level band A1 [3, 5], A2 [5, 7], B1 [7, 8], T hatched [8, 9], A2 [9, 12], A1 [12, 13] (pickup location of e13), T hatched [13, 14.6]; high-level band A [3, 7], B [7, 8], T [8, 9], A [9, 13], T [13, 14.6].
Edge cases: `data/timeline_example/` (see its README).

## Same timestamp
Every event gets its own x in `seq` order (time, then event id), on both axes: on "event order" it is the rank among all shown events; on "time" the tied events are spread around their timestamp (`trace_figure.add_tie_offsets`, half the smallest gap between timestamps).
Tied events get a grey box (`tie_groups`).
Inside a tie group the band is not split (ploc refers to the time before the timestamp).
At Levels 1 to 3 all tied relations of a handling unit have the same `loc`, so the order inside a box does not change the band.

## Filtering
None (draft outside the tool). The playground timeline ignored global filters.

## Settings
- `axis` ("event order" default, or "time"), `handling_units` (selection and order).
- `processing`: event ids of $P$; None = the transformation events (as in the trace figure).
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
6. `hu_order(relations, handling_units)`: row order; `timeline_relations(...)` runs 1 to 5 and `trace_figure.add_x_positions` (x).
7. `timestamp_before(relations, level)`: $ploc_t(hu)$ per handling unit and timestamp.
8. `band_segments(relations, level, reach)`: the band stretches (`continuation` gives the default reach).
9. `tie_groups`, `shared_events`, `lifespans`.
10. `object_timeline(relations, ...)`: the plotly figure.
Inputs of the running example: `data/running_example/inputs/processing_events.csv`, `transformation_roles.csv`, `locations.csv`. Tests: `tests/test_object_timeline.py`.

## How to change it
- Marker symbols, sizes and role colours: `SYMBOL`, `SIZE`, `ROLE_COLOUR`, `NO_ROLE_COLOUR`.
- Geometry: `BAND_TOP`, `BAND_BOTTOM`, `MARKER_Y`, `ROW_GAP`, `LABELLED_ROW_GAP`; reach: `ORDER_CONTINUATION`, `TIME_CONTINUATION`.
- Split rule: `band_segments` (column `_split`); location before a timestamp: `timestamp_before`.
- Colours: `trace_figure.location_colours` (ranked by the relations' loc and high_level, as in the trace figure).
- In the tool the figure will be drawn in the frontend (Plotly.js); steps 1 to 9 become the backend's data preparation.

## Alternatives
- Playground (`ObjectTimeline.tsx`, `timeline.py` of material_flow_analysis): one x per timestamp with stacked markers, stars for all non-movement events, red flag rings. Changes are listed in section 9 of the concept draft.
- Ties: stacking or one combined marker per tie group (concept draft, section 7).
