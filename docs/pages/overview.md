# Overview page

Concept: `overview/Deriving Locations.md`, section "overview", and for the location context (high-level locations, vehicles, storage units, processing operations) `overview/module/Module Overview.md`, "Update Overview Page", sections 6-10 (outside this repo).
Content elements are added one at a time; built so far: page filter bar, key numbers (with filtered values), configuration notices, flag badges, data overview charts, activity profile, overview charts.
Still to come: flag explore sections.

## Page structure (Nina, 2026-10-29)
Two sections, so that it is clear what the filters act on:
- **Configuration** (page title): the configuration bar (`configuration.md`), configuration notices (section 2), input flags (section 3) and the data overview charts (section 4). Never filtered; always the whole log.
- **Overview** (heading): the filter bar (section 0), key numbers (section 1), activity profile (section 5) and overview charts (section 6). Everything here follows the filters and uses the selected level, which the configuration bar shows; the section itself does not repeat the level.

## Code
- Page: `frontend-modules/location-ocpm/src/routes/Overview.tsx`
- Frame and shared header: `frontend-modules/location-ocpm/src/components/ModulePage.tsx`; the shared header (configuration summary and form) is documented in `configuration.md`.
- Backend: one module per section in `backend-modules/location-ocpm/src/ocelescope_module_location_based_ocpm/overview/`, routes in `overview_routes.py`. Every route reads the cached derivation (`configuration_routes.current_derivation`, see `docs/hosting/state-and-caching.md`).
- Number formatting: `frontend-modules/location-ocpm/src/lib/format.ts` (`num`, `pct`).

## 0. Page filter bar
**What it shows:** a bar that sticks to the top while scrolling, with three columns: Activity, Location and Handling unit. Each column has an "include" picker and below it an "exclude" picker. Next to the Location heading, the switch "either / pre / post" decides whether a location filter matches ploc (pre, the pickup or previous location), loc (post, the target or current location) or either. "Clear filters" sits next to the Handling unit heading; it is always shown and disabled while no filter is set; it keeps the location mode. With high-level locations, the switch **Locations: low | high** sits left of it (section 0a). Each option shows its count over the whole log in brackets.
A value is never included and excluded at the same time: choosing it in one picker removes it from the other (`lib/filters.ts`, `withValues`).
- Activity lists: "[movement events]", "[transformation events]", "[processing operations]", "[fully / partially / unlocated events]", "[agreeing / disagreeing events]", then the activities; counts are events. Single events are found by typing (below).
- Location lists: "[unknown]" (⊥), "[vehicles]" and "[storage units]" (only if configured; a location in V or W), then the locations; counts are relations whose loc or ploc is that location ("[unknown]": loc or ploc is ⊥). With high-level locations, the list is **grouped**: each high-level location as an entry "A, all locations (17)" with its locations indented below it ("A1 (10)"; in high-level mode "A1 (in A) (10)"), then the locations that are their own only member (e.g. the unmapped T) once. Picking the entry ("[high-level] A") picks all of its locations.
- Handling unit lists: "[fully / partially / unlocated HUs]", then the object types; counts are handling units. Single handling units are found by typing.
- **Single ids:** typing at least two characters in an Activity or Handling unit picker lists up to 20 matching event ids (heading "Events", count = handling units of the event) or handling unit ids (heading "Handling units", count = events of the handling unit), ids starting with the typed text first. Ids are not listed otherwise (logs have up to 10^5 of them). The filter values are "[event] e5" and "[hu] s1"; the chips show the id only. Example: "coil" + "s1" = all coils and s1.

**How it is calculated** (`overview/filters.py`): every filter is evaluated on hu-event relations at the selected level (`relation_properties`, `passes`). A relation passes if it passes every active filter (AND across filters, OR within one filter's values; an exclude filter removes matching relations). Location filters match loc ("post", `after` in the API), ploc ("pre", `before`) or either. Special values match properties of the whole event or the whole trace (locatedness, agreement), never of the passing relations only. Events and handling units are kept if at least one of their relations passes. Filters never change loc or ploc. A single event matches all its relations, a single handling unit its whole trace. A high-level value "[high-level] A" matches relations whose hl (phl) is A, which is the same as loc (ploc) ∈ agg⁻¹(A).
**Example** (running example, Level 3, "Location B1, post"): 8 passing relations (c1, e7), (c3, e10), (c2, e12), (c3, e12), (c3, e14), (c2, e15), (c4, e15), (c4, e16); kept events e7, e10, e12, e14, e15, e16; kept handling units c1-c4.
**State:** kept per log across page switches and browser reloads (`lib/filters.ts`, `usePageFilter`, on top of `lib/pageState.ts`); sent to every filtered route as query parameters (lists as repeated parameters, `filterRequest`).
**Code:** backend `PageFilter`, `passing_relations`, `filter_options` and `location_groups` (route `GET /{ocel_id}/overview/filter-options`, `getFilterOptions`; filter parameters parsed by `overview_routes.get_page_filter`), `search_ids` (route `GET /{ocel_id}/overview/search-ids`, `searchIds`, parameters kind = hu / event and query; limit `MAX_SEARCH`), prefixes `HIGH_LEVEL_PREFIX`, `HU_PREFIX`, `EVENT_PREFIX`; frontend `components/FilterBar.tsx` (`locationItems` for the grouped list, `useIdItems` and `IdPickers` for the id search; `SEARCH_FROM` characters) and `lib/filters.ts` (`shown` strips the prefix). Tests: `tests/test_overview_filters.py`, `tests/test_overview_high_level.py`.
**How to change:** a new special value needs a constant and a branch in `_activity_match` / `_location_match` / `_object_type_match`, an entry in `filter_options`, and a test in `tests/test_overview_filters.py`. A new filter needs a field in `PageFilter` (backend and `lib/filters.ts`), a parameter in `get_page_filter`, a branch in `passes`, and a `Column` (or a picker in one) in `FilterBar`.
**Alternatives:** filtering events (instead of relations) would make location filters ambiguous for events whose handling units are at different locations; the concept chose relations.

## 0a. Locations: low | high
**What it shows:** a switch "Locations: low | high" in the filter bar (left of "Clear filters"), only if high-level locations are configured. Default low. It applies to the whole Overview section (key numbers, activity profile, overview charts); the Configuration section shows both levels where it matters and is not affected. Kept per log with the filters (`PageFilter.location_mode`, sent as the query parameter `location_mode` to every filtered route).
**Principle:** filters are always evaluated on low-level locations, a high-level value stands for its preimage; switching never changes which relations pass and never changes or clears a filter. Only the display and aggregation change: the location dimension becomes ĥl = agg(loc) (hl^k, phl^k in the derivation), and agreement and eloc are taken under ĥl (`derivation.hl_event_locations`), also for "[agreeing / disagreeing events]".

| Part | In high-level mode |
|---|---|
| Key numbers | Locations tile becomes "High-level locations": \|HL\|, target and pickup counted as high-level locations, the small line names the low-level count; agreed located events under ĥl |
| Activity profile | "typical high-level location" and the unfolded top locations are high-level locations; hovering a cell or entry lists its locations with counts; agreed (tested) under ĥl |
| Overview charts | bars, segments and heatmap rows are ĥl; events: agreeing under ĥl, under eloc_ĥl; "# locations" counts high-level locations; Handling unit types by location: single high-level location over the trace; Locations chart: new "by low-level location" |

**Example** (running example with the location context, `data/running_example/inputs/locations.csv`): Locations chart, relations by low-level location: A 13 (A1 7, A2 6), B 8 (B1 8), T 5, – 2; events: A 8, B 5, T 2, – 1 (e14 left out, it still disagrees: c1 at T, c3 at B). crane move: typical high-level location A (4/6 = 67 %, hover "A2 4"), unfolded A 4, B 2.
**Code:** backend `overview/filters.py` (`LocationMode`, `PageFilter.high`, `event_table(derivation, high)`); each section reads `page_filter.high` and falls back to low-level without high-level locations. Frontend `FilterBar.tsx` (the switch) and `lib/filters.ts` (`useLocationContext`, `isHigh`). Tests: `tests/test_overview_high_level.py`.
**Alternatives:** filtering on ĥl directly would give the same relations (ĥl ∈ X ⟺ loc ∈ agg⁻¹(X)) but would lose single low-level locations in high-level mode; the label avoids "level", which already means the derivation level.

## 1. Key numbers
**What it shows:** seven tiles, each with a big number and a small grey line.

| Tile | Big number | Small line |
|---|---|---|
| Handling units | \|HU\|, including handling units without events | count per object type, largest first, e.g. "coil 5 · slab 1"; beyond five types the first five and "(+n)" for the n further types, hovering it lists all |
| Agreed located events | events with eloc(e) ≠ ⊥ at the selected level (under ĥl in high-level mode), "x of \|E\|" | share of all events; hover in low-level mode "+n agreeing at high level only" if there are such events |
| Relations with a known location | relations with loc ≠ ⊥ at the selected level, "x of \|E2HU\|" | share |
| Movement events | \|M\| | events per movement activity, largest first, e.g. "crane move 4 · load truck 2 · unload truck 2"; beyond three activities "(+n)", hovering it lists all |
| Locations | \|L\| = distinct locations in uloc ∪ puloc; in high-level mode "High-level locations" \|HL\| | "target n · pickup m" in the mode (pickup "–" if no pickup locations are configured), then the count of the other level ("high-level n" / "low-level n"), "vehicles n", "storage units n" for what is configured |
| Transformation events | \|T\|; "–" if none are configured | events per transformation activity, largest first, e.g. "cast slab 1 · cut 1 · roll 1"; beyond three activities "(+n)", hovering it lists all; "no transformation events configured" if none are configured |
| Processing operations | \|P\| | events per activity of P, largest first, beyond three "(+n)"; hover "default: the transformation events" if P is not configured |

With an active filter, each tile shows the filtered value in brackets next to the big number, smaller and in the accent colour: kept handling units; kept events with eloc ≠ ⊥; passing relations with loc ≠ ⊥ "of" passing relations; kept movement events; distinct locations of the passing relations (loc for "after", ploc for "before", both for "either"; hl / phl in high-level mode); kept transformation events; kept processing operations.

**How it is calculated:** `overview/key_numbers.py`, `key_numbers(derivation) -> KeyNumbers`.
eloc and loc come from the derivation at the selected level (`derivation.event_locations[level]["eloc"]`, `derivation.relations[derivation.loc]`); see `docs/resources/location-derivation.md`.
Pickup locations are counted after ignoring pickups of non-movement events (as resolved).
**Example** (running example, Level 3): 6 (coil 5 · slab 1); 15 of 17, 88 % (e14 not agreeing, e17 unlocated); 26 of 28, 93 %; 8 (crane move 4 · load truck 2 · unload truck 2); 4 (target 4 · pickup 2); 3 (cast slab 1 · cut 1 · roll 1); 3 processing operations (P = T). With the location context: Locations 4 (target 4 · pickup 2 · high-level 3 · vehicles 1 · storage units 1), high-level mode 3 (target 3 · pickup 2 · low-level 4 · vehicles 1 · storage units 1); processing operations 4 (cast slab 1 · cut 1 · label 1 (+1)).
**Filtering:** big numbers never; filtered values as above (`filtered_numbers`). Example "Location B1, post": 6 (4); 15 of 17 (5); 26 of 28 (8 of 8); 8 (2); 4 (1); 3 (1). The small grey lines are never filtered.
Implementation choice: the concept's filter line names "kept events with a location from the input" for the second tile, but the tile itself counts agreed located events; the filtered value follows the tile (kept events with eloc ≠ ⊥: 5 in the example; with "location from the input" it would be 3).
**Settings:** the selected level (configuration).
**Code:** backend `key_numbers(derivation, page_filter)` (location counts per mode, `agreed_high_level_only`, `processing_*`) and `filtered_numbers` (route `GET /{ocel_id}/overview/key-numbers`, `getKeyNumbers`); frontend `components/KeyNumbers.tsx` (`KeyNumbers`, `Tile`; the shortened type list is `components/ShortList.tsx`, limit `SHORT_LIST_LIMIT`; accent colour from `lib/palette.ts`, `UI`).
**How to change:** a new tile needs a field in `KeyNumbers`, its computation in `key_numbers`, `pnpm run build:modules`, a `Tile` in `KeyNumbers.tsx`, and an assertion in `tests/test_overview_key_numbers.py`.
**Alternatives:** counting located events by locatedness (fully located) instead of eloc ≠ ⊥; the concept chose agreed located events.

## 2. Configuration notices
**What it shows:** grey lines right below the configuration bar (configuration section) with the notices of the applied configuration, e.g. ignored pickup locations or dropped table rows, each with its ids (first 20, "show all").
**Code:** `Overview.tsx`, `ConfigNotices` (reads `getConfig`), rendering `Notices` from `ConfigForm.tsx`.
**Example:** none for the running example.

## 3. Input flags
**What it shows:** a row headed "Input Flags" with one badge per flag, "F1 Partial movement · 2 events"; grey at 0, amber above 0; hovering shows the definition. F4 is hidden if no pickup locations are configured, F6 without high-level locations, F8 at Levels 1-3, F10 without vehicles and storage units. The explore sections (opened by clicking a badge) follow in later steps.
**How it is calculated:** `overview/flag_badges.py`, `flag_counts(derivation) -> list[FlagCount]`: number of distinct flagged events or handling units in `derivation.flags` (computed at the selected level, see `docs/resources/location-derivation.md`, section "Flags"). Labels, units and hover texts are in `FLAGS`.
**Example** (running example, Level 3): F1 2 events, F2 2 handling units, F3 1 event, F4 1 handling unit, F5 2 events, F7 0, F9 0; with the location table of `data/running_example/inputs/locations.csv` also F6 0 and F10 0.
**Filtering:** never filtered (whole log).
**Code:** route `GET /{ocel_id}/overview/flags` (`getFlagCounts`); frontend `components/FlagBadges.tsx`.
**How to change:** wording in `FLAGS`; colours in `FlagBadges` (`color` of the `Badge`).

## 4. Data overview charts
**What it shows:** four small charts in a 2×2 grid (one column on narrow screens), each with its legend to the right (the sunburst's legend grouped by ring); hovering a segment shows its count and share.
- **Events** (sunburst): inner ring type (the combination of the roles movement, transformation, processing, e.g. "transformation · processing"; "other" if none; only occurring combinations), middle ring locatedness (fully / partially / unlocated), outer ring agreement (agreeing, agreeing at high level only, not agreeing, not tested). Counts events; subtitle "events · inner-outer: type, located, agreement (lvl k)" (one line, so without "kept").
- **Relations: first level with a location** (donut): for every hu-event relation the lowest level k with loc^k ≠ ⊥, or ⊥ if there is none (shown as "Level k" and "not located" in legend and hover). Always all levels, independent of the selected one (helps to choose a level). Counts relations.
- **Handling units** (donut): locatedness of each handling unit's trace at the selected level. Counts handling units with at least one event.
- **Locations** (sunburst): inner ring location type (vehicle, storage unit, vehicle and storage unit, other), outer ring high-level location (only if configured). Switch "# locations / # relations" in the title line: counts the locations of L, or relations by their loc at the selected level (relations without a location are left out; the subtitle gives their number). Without any location context the card says "no location context configured".

**How it is calculated:** `overview/data_charts.py`, `data_charts(derivation, page_filter) -> DataCharts`.
- Type: the roles of the event (e ∈ M, e ∈ T, e ∈ P) joined with " · ", "other" if none (`event_type_expr`; display order `EVENT_TYPES`). Without the processing input P = T, so transformation events show as "transformation · processing".
- Agreement: "not tested" if fewer than two handling units of the event are located (agreeing by definition, but nothing is compared); otherwise agreeing or not agreeing at the selected level (`derivation.event_locations[level]`); with high-level locations, a not agreeing event that agrees under hat-hl is "agreeing at high level only" (`derivation.hl_event_locations`).
- Location type and high-level location of each location: `location_types`; segments `location_segments`.
- First level: `first_levels` over loc^0 … loc^3.
- Locatedness of events and handling units: as in the filter bar (`derivation/locatedness.py`).

**Example** (running example, Level 3, no filter): events movement 8 (fully located: 4 agreeing, 4 not tested), transformation · processing 3 (fully located: 2 agreeing, 1 not tested), other 6 (fully located 4: 1 agreeing, 1 not agreeing (e14), 2 not tested; partially located 1 (e16, not tested); unlocated 1 (e17, not tested)); relations Level 0: 15, Level 1: 4, Level 2: 3, Level 3: 4, ⊥: 2; handling units fully 5, unlocated 1 (c5).
With the location context of `data/running_example/inputs/locations.csv` and processing "label": types movement 8, transformation · processing 3, processing 1 (e4), other 5; no event agrees at high level only (e14: T vs B); locations vehicle 1 (T), storage unit 1 (B), other 2 (A); relations vehicle 5, storage unit 8, other 13, 2 left out.
**Filtering:** none since 2026-10-29: the charts sit in the configuration section and always show the whole log (the frontend sends no filter). The route still accepts the page filter (`data_charts(derivation, page_filter)`), e.g. "Location B1, post": 6 events; relations Level 0: 4, Level 1: 2, Level 3: 2; handling units 4 fully located. Clicks still set filter values for the overview section below.
**Clicking** a segment adds its filter value to the filter bar, replacing any other value of the same category (e.g. "[transformation events]" replaces "[movement events]") and removing it from the matching exclude filter (`lib/filters.ts`, `withValue`, categories in `CATEGORIES`):

| Segment | Filter value |
|---|---|
| fully / partially / unlocated (events) | Activity "[fully / partially / unlocated events]" |
| movement, transformation, processing | Activity "[movement events]", "[transformation events]", "[processing operations]" |
| agreeing, not agreeing | Activity "[agreeing events]", "[disagreeing events]" |
| fully / partially / unlocated (handling units) | Handling unit type "[fully / partially / unlocated HUs]" |
| vehicle, storage unit (locations chart) | Location "[vehicles]", "[storage units]" |
| combinations of roles, other, agreeing at high level only, not tested, vehicle and storage unit, high-level segments, every segment of the relations chart | nothing (no filter value matches them; high-level filter values follow with the high-level switch) |

Values of different categories within the Activity filter are combined with OR, so clicking a type and then a locatedness segment widens the filter instead of narrowing it.
A sunburst click never zooms into the segment.
**Settings:** the selected level (events and handling units; the relations chart shows all levels).
**Code:** route `GET /{ocel_id}/overview/data-charts` (`getDataCharts`); `Segment` carries id, label, parent, count and the click's `filter`; frontend `components/DataCharts.tsx` (`Sunburst`, `Donut`, `LocationsChart`, `Legend`, `useAddFilter`; high-level colours ranked by total in `highLevelColours`). Colours: `STATUS` in `lib/palette.ts`. Click handling: `ThemedPlot` in `components/plots.tsx` (see `docs/hosting/dependencies.md`).
**How to change:** ring order: `rings` in `event_segments` (backend) and `RINGS` (frontend). A new ring value needs a branch in `event_categories`, an entry in `EVENT_TYPES` / `AGREEMENT` (backend) and `RINGS` (frontend), a colour in `STATUS`, and, if clicking should filter, an entry in `EVENT_FILTERS` and in a category of `CATEGORIES`. Height: `HEIGHT` in `DataCharts.tsx`. Tests: `tests/test_overview_data_charts.py`.
**Alternatives:** bar charts instead of donuts (easier to compare small segments); a click that sets the whole path of a sunburst segment would need an AND between activity values, which the filter bar does not have.

## 5. Activity profile
**What it shows:** a table with one row per activity with kept events, a search box ("Search activity", only hides rows) and sortable columns (click a heading; activity, events, share at location, role, HUs per event by max, located by the share of fully located events, agreed). Default: most events first. Every heading has a hover text. A click anywhere on a row (or its arrow) unfolds it, a second click folds it again; the unfolded row shows its top 5 locations, each with a frequency bar, share and count, plus the number of distinct locations.

| Column | Content | Example (crane move, Level 3) |
|---|---|---|
| events | kept events of the activity | 4 |
| share at location | only with a location filter: events / all kept events | (B1, post: quality check 3/6 = 50 %) |
| role | share of movement events (M), transformation events (T; "–" if none are configured) and processing operations (P; "–" if P is empty) | M 100 %, T 0 %, P 0 % |
| HUs per event | median (max) handling units per event; hover: object types counted as hu-event relations | 1.5 (2), hover "coil 6" |
| typical location ("typical high-level location" in high-level mode, hover: its locations with counts) | most frequent loc (ĥl) over the located relations (count/total = share; "n tied" if tied, alphabetically first shown); "unknown" if none; "provided x/y" = events in dom(uloc) | A2 (4/6 = 67 %); provided 4/4 |
| located | fully (partially, unlocated) located events · share fully located | 4 (0, 0) · 100 % |
| agreed (tested) | agreeing events by the definition / events (in brackets: agreeing among events with ≥ 2 located handling units / such events) | 4/4 (2/2) |

**How it is calculated:** `overview/activity_profile.py`, `activity_profile(derivation, page_filter) -> ActivityProfile`. Event properties come from `derivation.event_locations[level]` (n_relations, n_located, located, agreeing) and `derivation.events` (is_movement, is_transformation, uloc); typical values from `ranked` (count per activity and value, ties alphabetical), top values from `_tops`.
**Example** (running example, Level 3, no filter): as in the concept's table "Step 2"; e.g. quality check: 4 events, B1 (3/4 = 75 %); provided 1/4, 2 (1, 1) · 50 %, 3/4 (0/1). Expanded crane move: A2 67 % (4), B1 33 % (2); 2 distinct.
**Filtering:** one row per activity with kept events; events, role, HUs per event, located and agreed describe the kept events as a whole; typical location and top locations count passing relations only; share at location appears only with a location (or exclude location) filter. Example "Location B1, post": crane move 1, quality check 3 (50 %, B1 3/3, 2/3 (0/1): e14 still disagreeing), unload truck 1, cut 1.
Events without handling units have no relation and therefore never appear.
**Settings:** the selected level; sort order kept across pages and reloads (`profile.sort`, `lib/pageState.ts`); the search box is not kept.
**High-level mode:** typical and top locations count hl; each carries its `members` (locations with counts, `members_of`) for the hover; located/agreed come from `event_table(derivation, high)`.
**Code:** route `GET /{ocel_id}/overview/activity-profile` (`getActivityProfile`); frontend `components/ActivityProfile.tsx` (`ActivityProfile`, `Row`, `Heading`; hover texts in `INFO`, sort keys in `sortValue`, `membersText`). Tests: `tests/test_overview_activity_profile.py`, `tests/test_overview_high_level.py`.
**How to change:** a new column needs a field in `ActivityRow` and its aggregation in `activity_profile` (backend), `pnpm run build:modules`, a heading and a cell in `ActivityProfile.tsx` (and a `sortValue` entry if sortable). Number of expanded locations: `TOP` in `activity_profile.py`.
**Alternatives:** the typical recipe is struck in the concept until defined. Routes (ploc → loc of moved handling units) were removed on 2026-10-28 as not useful in their current form.

## 6. Overview charts
**What it shows:** a **top 10 / bottom 10** switch, bar charts in a 2×2 grid (row 1: Activities, Handling unit types; row 2: Relations per activity · handling unit type, Locations; layout and the two new charts agreed by Nina on 2026-11-02) and below them the location × activity heatmap (concept section "Overview charts"). Bars are horizontal, largest on top. Each chart's controls sit in its title line. The Movement activities chart was dropped on 2026-10-29.

| Chart | One bar per | Bar counts | Controls (default first) | "by" options (default) |
|---|---|---|---|---|
| Activities | activity | relations or events | relations / events; # relations (# events) / # locations | none, location (default), object type, locatedness, agreement, location type |
| Handling unit types | object type | kept handling units | # handling units / # locations | locatedness (default), location, none |
| Relations per activity · handling unit type | (activity, object type) pair, labelled "activity · type" | relations | # relations / # locations | location (default), locatedness, location type, none |
| Locations | location at the selected level ("–" = ⊥; ĥl in high-level mode) | relations or events | relations / events | none, activity (default), object type, location type, low-level location (high-level mode) |

- **by location type** (only if vehicles or storage units are configured, relations only): vehicle / storage unit / vehicle and storage unit / other of the relation's low-level location, "–" for ⊥; status colours from `palette.ts` (`STATUS`), "other" grey. Relations only, since a type belongs to a low-level location and an agreed high-level location can contain several types. Example (Locations, low-level): B1 8 (storage unit), A1 7 and A2 6 (other), T 5 (vehicle).
- **by low-level location** (Locations chart, high-level mode, relations only): each high-level bar split into its locations, e.g. A 13 (A1 7, A2 6).

- **relations:** every passing hu-event relation counts once, under its own values (its loc for locations).
- **events:** only agreeing kept events, each once, under the common value of its handling units: eloc for locations ("–" if no handling unit is located), the object type ("[several types]" if they differ). Not agreeing events are left out; the subtitle gives their number, the hover of an Activities bar the number for that activity.
- **# locations** (all but Locations): bar = distinct locations ≠ ⊥ of the bar's passing relations (in both measures); the hover lists them; only "by" none, location and activity are offered (their segments add up to the bar).
- **Handling unit types:** a handling unit is kept if at least one of its relations passes. *by locatedness*: its locatedness over the whole trace (fully / partially / unlocated, as in the data overview's handling unit chart). *by location*: its only known location over the whole trace; "[several locations]" (grey) if it has two or more, "–" (hatched) if it has none; ⊥ never counts. Both are judged on the whole trace, not on the passing relations, so a location filter does not turn a multi-location handling unit into a single-location one (Nina, 2026-11-02). Example: coil 5 (fully 4, unlocated 1; by location B1 1 (c4), [several locations] 3 (c1, c2, c3), – 1 (c5)), slab 1 (A1). # locations: coil 4 (A1, A2, B1, T).
- **Relations per activity · handling unit type:** every passing relation counts under its activity and its handling unit's object type; by location = its loc, by locatedness = its event's locatedness. Relations only, no events measure (Nina, 2026-11-02). Example: crane move · coil 6 (A2 4, B1 2), roll · coil 2 (A1), roll · slab 1 (A1): roll splits into its consumed slab and its produced coils.
- **by locatedness / agreement** (Activities): the event's locatedness (fully / partially / unlocated) or agreement (agreeing / not agreeing / not tested, as in the data overview sunburst), in the sunburst's status colours. Both are properties of the whole event, so in events mode *all* kept events count, including the not agreeing ones. Example quality check: relations by locatedness fully 3, partially 2, unlocated 1; events by agreement not tested 3, not agreeing 1 (e14).
- **top 10:** the 10 largest bars, the rest summed into a grey "other" bar (hover: how many bars). **bottom 10:** the 10 smallest, the rest left out. Ties: alphabetical. The switch also sets both heatmap axes.
- **Colours:** each chart ranks its own segment values. Every shown bar gets enough of its largest values that at most 5 % of it stays grey "other"; the chosen values are ordered by their total over the shown bars (first palette colour = largest), at most 50 per chart. "–" segments and the "–" bar are hatched grey, "[several locations]" segments plain grey; neither ever gets a colour (`GREY` in `overview_charts.py`). The legend sits beside the chart (at most ¼ of the card width, long names cut, full name on hover); bar labels are cut to ¼ of the chart width.
- **Heatmap:** rows locations ("–" row grey, last), columns activities, cells counts (relations or events, as above); 10 values per axis by their totals following the top/bottom switch, no "other"; **all / movements / transformations / processing operations** keeps the relations (events) of all, of movement, of transformation events or of processing operations (example: only cast slab, roll, cut, label stay with P = T ∪ {label}).
- **Clicks:** a bar or segment adds the bar's value and the segment's value to the include filters (a heatmap cell: its location and activity). "–" adds the location "[unknown]"; locatedness and agreement add "[fully / partially / unlocated events]", "[agreeing events]" or "[disagreeing events]" to the Activity filter, but in the Handling unit types chart locatedness adds "[fully / partially / unlocated HUs]" to the Handling unit filter; an activity · type bar adds both its activity and its type; "other", "[several types]", "[several locations]" and "not tested" add nothing. Chart locations are loc (post), so adding a location switches the location role "pre" to "post" ("either" stays). In high-level mode a high-level bar, segment or heatmap row adds its entry "[high-level] A" (a location that is its own only member adds itself); a low-level location segment adds its location; a location-type segment adds "[vehicles]" or "[storage units]" ("other" and "vehicle and storage unit" add nothing).

**How it is calculated:** `overview/overview_charts.py`. Step 1: `relation_units` (passing relations with activity, object type, location, and the event's locatedness and agreement from `data_charts.event_categories`) `event_units` (kept agreeing events with activity, object type, location = eloc; plus the not agreeing ones) and `hu_units` (kept handling units with object type, whole-trace locatedness and single location). Step 2: `bar_chart(units, bar, by, end, count, rank)` is generic for every bar chart (`chosen` picks the top/bottom bars, `colour_values` the coloured segment values); `overview_bar_chart` picks the units and the bar dimension per chart (`BAR_COLUMN`; the activity · type chart also returns each bar's `parts`, activity and type, for clicks); `heatmap` counts units per (location, activity).
**Example** (running example, Level 3, no filter): as in the concept's "Deriving Overview Charts". Activities, relations, by location: crane move 6 (A2 4, B1 2), quality check 6 (B1 3, T 1, – 2); events: quality check 3 (B1 2, – 1), 1 not agreeing event left out (e14). # locations: quality check 2 (B1, T). Locations, events: B1 5, A1 4, A2 4, T 2, – 1. Heatmap, relations: A2 × crane move 4, – × quality check 2.
**Filtering:** all charts count the kept part: passing relations, kept events (with whole-event agreement and eloc). Example "Location B1, post", Locations chart: only the bar B1.
**Settings:** the selected level; per chart measure, mode and "by" (`charts.activities`, `charts.hu_types`, `charts.activity_types`, `charts.locations`), the heatmap switches (`charts.heatmap`) and the top/bottom switch (`charts.end`) are kept across pages and reloads (`lib/pageState.ts`).
**High-level mode:** `relation_units` takes the location from hl, `event_units` eloc and agreement from `event_table(derivation, high)`, `hu_units` the single location from hl; `low_location` and `location_type` columns always come from loc (`RELATION_ONLY`).
**Code:** routes `GET /{ocel_id}/overview/bar-chart` (`getBarChart`, parameters chart, measure, by, mode, end) and `GET /{ocel_id}/overview/heatmap` (`getHeatmap`, parameters measure, end, events); frontend `components/OverviewCharts.tsx` (`OverviewCharts`, `BarChartCard`, `HeatmapCard`, `traces`; chart definitions in `CHARTS`, "by" options in `BY_OPTIONS`, click mapping in `FILTER_OF` and `useAddValues`, hover texts in `INFO`). Tests: `tests/test_overview_charts.py`.
**How to change:** number of bars `SHOWN`, grey share `MAX_OTHER_SHARE`, colour cap `MAX_COLOURS` (all in `overview_charts.py`); a new "by" dimension needs a column in `relation_units`/`event_units`, an entry in `BY_COLUMN` and the `By` literal (backend), `pnpm run build:modules`, then an entry in `BY_OPTIONS` (and `FILTER_OF` if clicks should filter by it). A new chart: a branch in `overview_bar_chart` and an entry in `CHARTS`.
**Alternatives:** the transformation activities chart is struck in the concept; the high-level location "by" is replaced by the switch (section 0a). Events mode by object type could instead count an event under each of its object types (then an event counts more than once).
