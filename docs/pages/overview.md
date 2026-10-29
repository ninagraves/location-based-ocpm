# Overview page

Concept: `overview/Deriving Locations.md`, section "overview" (outside this repo).
Content elements are added one at a time; built so far: page filter bar, key numbers (with filtered values), configuration notices, flag badges, data overview charts, activity profile, overview charts.
Still to come: flag explore sections.

## Page structure (Nina, 2026-10-29)
Two sections, so that it is clear what the filters act on:
- **Configuration** (page title): the configuration bar (`configuration.md`), configuration notices (section 2), input flags (section 3) and the data overview charts (section 4). Never filtered; always the whole log.
- **Overview** (heading): the filter bar (section 0), key numbers (section 1), activity profile (section 5) and overview charts (section 6). Everything here follows the filters.

## Code
- Page: `frontend-modules/location-ocpm/src/routes/Overview.tsx`
- Frame and shared header: `frontend-modules/location-ocpm/src/components/ModulePage.tsx`; the shared header (configuration summary and form) is documented in `configuration.md`.
- Backend: one module per section in `backend-modules/location-ocpm/src/ocelescope_module_location_based_ocpm/overview/`, routes in `overview_routes.py`. Every route reads the cached derivation (`configuration_routes.current_derivation`, see `docs/hosting/state-and-caching.md`).
- Number formatting: `frontend-modules/location-ocpm/src/lib/format.ts` (`num`, `pct`).

## 0. Page filter bar
**What it shows:** a bar that sticks to the top while scrolling, with three columns: Activity, Location and Handling unit type. Each column has an "include" picker and below it an "exclude" picker. Next to the Location heading, the switch "either / pre / post" decides whether a location filter matches ploc (pre, the pickup or previous location), loc (post, the target or current location) or either. "Clear filters" sits next to the Handling unit type heading; it is always shown and disabled while no filter is set. Each option shows its count over the whole log in brackets.
A value is never included and excluded at the same time: choosing it in one picker removes it from the other (`lib/filters.ts`, `withValues`).
- Activity lists: "[movement events]", "[transformation events]", "[fully / partially / unlocated events]", "[agreeing / disagreeing events]", then the activities; counts are events.
- Location lists: "[unknown]" (⊥), then the locations; counts are relations whose loc or ploc is that location ("[unknown]": loc or ploc is ⊥).
- Handling unit type lists: "[fully / partially / unlocated HUs]", then the object types; counts are handling units.

**How it is calculated** (`overview/filters.py`): every filter is evaluated on hu-event relations at the selected level (`relation_properties`, `passes`). A relation passes if it passes every active filter (AND across filters, OR within one filter's values; an exclude filter removes matching relations). Location filters match loc ("post", `after` in the API), ploc ("pre", `before`) or either. Special values match properties of the whole event or the whole trace (locatedness, agreement), never of the passing relations only. Events and handling units are kept if at least one of their relations passes. Filters never change loc or ploc.
**Example** (running example, Level 3, "Location B1, post"): 8 passing relations (c1, e7), (c3, e10), (c2, e12), (c3, e12), (c3, e14), (c2, e15), (c4, e15), (c4, e16); kept events e7, e10, e12, e14, e15, e16; kept handling units c1-c4.
**State:** kept per log across page switches and browser reloads (`lib/filters.ts`, `usePageFilter`, on top of `lib/pageState.ts`); sent to every filtered route as query parameters (lists as repeated parameters, `filterRequest`).
**Code:** backend `PageFilter`, `passing_relations`, `filter_options` (route `GET /{ocel_id}/overview/filter-options`, `getFilterOptions`; filter parameters parsed by `overview_routes.get_page_filter`); frontend `components/FilterBar.tsx`.
**How to change:** a new special value needs a constant and a branch in `_activity_match` / `_location_match` / `_object_type_match`, an entry in `filter_options`, and a test in `tests/test_overview_filters.py`. A new filter needs a field in `PageFilter` (backend and `lib/filters.ts`), a parameter in `get_page_filter`, a branch in `passes`, and a `Column` (or a picker in one) in `FilterBar`.
**Alternatives:** filtering events (instead of relations) would make location filters ambiguous for events whose handling units are at different locations; the concept chose relations.

## 1. Key numbers
**What it shows:** six tiles, each with a big number and a small grey line.

| Tile | Big number | Small line |
|---|---|---|
| Handling units | \|HU\|, including handling units without events | count per object type, largest first, e.g. "coil 5 · slab 1"; beyond five types the first five and "(+n)" for the n further types, hovering it lists all |
| Agreed located events | events with eloc(e) ≠ ⊥ at the selected level, "x of \|E\|" | share of all events |
| Relations with a known location | relations with loc ≠ ⊥ at the selected level, "x of \|E2HU\|" | share · "loc at Level k" |
| Movement events | \|M\| | events per movement activity, largest first, e.g. "crane move 4 · load truck 2 · unload truck 2"; beyond three activities "(+n)", hovering it lists all |
| Locations | \|L\| = distinct locations in uloc ∪ puloc | "target n · pickup m" (pickup "–" if no pickup locations are configured) |
| Transformation events | \|T\|; "–" if none are configured | events per transformation activity, largest first, e.g. "cast slab 1 · cut 1 · roll 1"; beyond three activities "(+n)", hovering it lists all; "no transformation events configured" if none are configured |

With an active filter, each tile shows the filtered value in brackets next to the big number, smaller and in the accent colour: kept handling units; kept events with eloc ≠ ⊥; passing relations with loc ≠ ⊥ "of" passing relations; kept movement events; distinct locations of the passing relations (loc for "after", ploc for "before", both for "either"); kept transformation events.

**How it is calculated:** `overview/key_numbers.py`, `key_numbers(derivation) -> KeyNumbers`.
eloc and loc come from the derivation at the selected level (`derivation.event_locations[level]["eloc"]`, `derivation.relations[derivation.loc]`); see `docs/resources/location-derivation.md`.
Pickup locations are counted after ignoring pickups of non-movement events (as resolved).
**Example** (running example, Level 3): 6 (coil 5 · slab 1); 15 of 17, 88 % (e14 not agreeing, e17 unlocated); 26 of 28, 93 % · loc at Level 3; 8 (crane move 4 · load truck 2 · unload truck 2); 4 (target 4 · pickup 2); 3 (cast slab 1 · cut 1 · roll 1).
**Filtering:** big numbers never; filtered values as above (`filtered_numbers`). Example "Location B1, post": 6 (4); 15 of 17 (5); 26 of 28 (8 of 8); 8 (2); 4 (1); 3 (1). The small grey lines are never filtered.
Implementation choice: the concept's filter line names "kept events with a location from the input" for the second tile, but the tile itself counts agreed located events; the filtered value follows the tile (kept events with eloc ≠ ⊥: 5 in the example; with "location from the input" it would be 3).
**Settings:** the selected level (configuration).
**Code:** backend `key_numbers(derivation, page_filter)` and `filtered_numbers` (route `GET /{ocel_id}/overview/key-numbers`, `getKeyNumbers`); frontend `components/KeyNumbers.tsx` (`KeyNumbers`, `Tile`; the shortened type list is `components/ShortList.tsx`, limit `SHORT_LIST_LIMIT`; accent colour from `lib/palette.ts`, `UI`).
**How to change:** a new tile needs a field in `KeyNumbers`, its computation in `key_numbers`, `pnpm run build:modules`, a `Tile` in `KeyNumbers.tsx`, and an assertion in `tests/test_overview_key_numbers.py`.
**Alternatives:** counting located events by locatedness (fully located) instead of eloc ≠ ⊥; the concept chose agreed located events.

## 2. Configuration notices
**What it shows:** grey lines right below the configuration bar (configuration section) with the notices of the applied configuration, e.g. ignored pickup locations or dropped table rows, each with its ids (first 20, "show all").
**Code:** `Overview.tsx`, `ConfigNotices` (reads `getConfig`), rendering `Notices` from `ConfigForm.tsx`.
**Example:** none for the running example.

## 3. Input flags
**What it shows:** a row headed "Input Flags" with one badge per flag, "F1 Partial movement · 2 events"; grey at 0, amber above 0; hovering shows the definition. F4 is hidden if no pickup locations are configured. The explore sections (opened by clicking a badge) follow in later steps.
**How it is calculated:** `overview/flag_badges.py`, `flag_counts(derivation) -> list[FlagCount]`: number of distinct flagged events or handling units in `derivation.flags` (computed at the selected level, see `docs/resources/location-derivation.md`, section "Flags"). Labels, units and hover texts are in `FLAGS`.
**Example** (running example, Level 3): F1 2 events, F2 2 handling units, F3 1 event, F4 1 handling unit, F5 2 events.
**Filtering:** never filtered (whole log).
**Code:** route `GET /{ocel_id}/overview/flags` (`getFlagCounts`); frontend `components/FlagBadges.tsx`.
**How to change:** wording in `FLAGS`; colours in `FlagBadges` (`color` of the `Badge`).

## 4. Data overview charts
**What it shows:** three small charts in one row, each with its legend to the right (the sunburst's legend grouped by ring); hovering a segment shows its count and share.
- **Events** (sunburst): inner ring type (movement, transformation, movement and transformation, other), middle ring locatedness (fully / partially / unlocated), outer ring agreement (agreeing, not agreeing, not tested). Counts events; subtitle "events · inner-outer: type, located, agreement (lvl k)" (one line, so without "kept").
- **Relations: first level with a location** (donut): for every hu-event relation the lowest level k with loc_k ≠ ⊥, or ⊥ if there is none (shown as "Level k" and "not located" in legend and hover). Always all levels, independent of the selected one (helps to choose a level). Counts relations.
- **Handling units** (donut): locatedness of each handling unit's trace at the selected level. Counts handling units with at least one event.

**How it is calculated:** `overview/data_charts.py`, `data_charts(derivation, page_filter) -> DataCharts`.
- Type: movement if e ∈ M \ T, transformation if e ∈ T \ M, "movement and transformation" if e ∈ M ∩ T, other otherwise (`event_categories`).
- Agreement: "not tested" if fewer than two handling units of the event are located (agreeing by definition, but nothing is compared); otherwise agreeing or not agreeing at the selected level (`derivation.event_locations[level]`).
- First level: `first_levels` over loc_0 … loc_3.
- Locatedness of events and handling units: as in the filter bar (`derivation/agreement.py`).

**Example** (running example, Level 3, no filter): events movement 8 (fully located: 4 agreeing, 4 not tested), transformation 3 (fully located: 2 agreeing, 1 not tested), other 6 (fully located 4: 1 agreeing, 1 not agreeing (e14), 2 not tested; partially located 1 (e16, not tested); unlocated 1 (e17, not tested)); relations Level 0: 15, Level 1: 4, Level 2: 3, Level 3: 4, ⊥: 2; handling units fully 5, unlocated 1 (c5).
**Filtering:** none since 2026-10-29: the charts sit in the configuration section and always show the whole log (the frontend sends no filter). The route still accepts the page filter (`data_charts(derivation, page_filter)`), e.g. "Location B1, post": 6 events; relations Level 0: 4, Level 1: 2, Level 3: 2; handling units 4 fully located. Clicks still set filter values for the overview section below.
**Clicking** a segment adds its filter value to the filter bar, replacing any other value of the same category (e.g. "[transformation events]" replaces "[movement events]") and removing it from the matching exclude filter (`lib/filters.ts`, `withValue`, categories in `CATEGORIES`):

| Segment | Filter value |
|---|---|
| fully / partially / unlocated (events) | Activity "[fully / partially / unlocated events]" |
| movement, transformation | Activity "[movement events]", "[transformation events]" |
| agreeing, not agreeing | Activity "[agreeing events]", "[disagreeing events]" |
| fully / partially / unlocated (handling units) | Handling unit type "[fully / partially / unlocated HUs]" |
| movement and transformation, other, not tested, every segment of the relations chart | nothing (no filter value matches them) |

Values of different categories within the Activity filter are combined with OR, so clicking a type and then a locatedness segment widens the filter instead of narrowing it.
A sunburst click never zooms into the segment.
**Settings:** the selected level (events and handling units; the relations chart shows all levels).
**Code:** route `GET /{ocel_id}/overview/data-charts` (`getDataCharts`); `Segment` carries id, label, parent, count and the click's `filter`; frontend `components/DataCharts.tsx` (`Sunburst`, `Donut`, `Legend`, `useAddFilter`). Colours: `STATUS` in `lib/palette.ts`. Click handling: `ThemedPlot` in `components/plots.tsx` (see `docs/hosting/dependencies.md`).
**How to change:** ring order: `rings` in `event_segments` (backend) and `RINGS` (frontend). A new ring value needs a branch in `event_categories`, an entry in `EVENT_TYPES` / `AGREEMENT` (backend) and `RINGS` (frontend), a colour in `STATUS`, and, if clicking should filter, an entry in `EVENT_FILTERS` and in a category of `CATEGORIES`. Height: `HEIGHT` in `DataCharts.tsx`. Tests: `tests/test_overview_data_charts.py`.
**Alternatives:** bar charts instead of donuts (easier to compare small segments); a click that sets the whole path of a sunburst segment would need an AND between activity values, which the filter bar does not have.

## 5. Activity profile
**What it shows:** a table with one row per activity with kept events, a search box ("Search activity", only hides rows) and sortable columns (click a heading; activity, events, share at location, role, HUs per event by max, located by the share of fully located events, agreed). Default: most events first. Every heading has a hover text. A click anywhere on a row (or its arrow) unfolds it, a second click folds it again; the unfolded row shows its top 5 locations, each with a frequency bar, share and count, plus the number of distinct locations.

| Column | Content | Example (crane move, Level 3) |
|---|---|---|
| events | kept events of the activity | 4 |
| share at location | only with a location filter: events / all kept events | (B1, post: quality check 3/6 = 50 %) |
| role | share of movement events (M) and transformation events (T; "–" if none are configured) | M 100 %, T 0 % |
| HUs per event | median (max) handling units per event; hover: object types counted as hu-event relations | 1.5 (2), hover "coil 6" |
| typical location | most frequent loc over the located relations (count/total = share; "n tied" if tied, alphabetically first shown); "unknown" if none; "provided x/y" = events in dom(uloc) | A2 (4/6 = 67 %); provided 4/4 |
| located | fully (partially, unlocated) located events · share fully located | 4 (0, 0) · 100 % |
| agreed (tested) | agreeing events by the definition / events (in brackets: agreeing among events with ≥ 2 located handling units / such events) | 4/4 (2/2) |

**How it is calculated:** `overview/activity_profile.py`, `activity_profile(derivation, page_filter) -> ActivityProfile`. Event properties come from `derivation.event_locations[level]` (n_relations, n_located, located, agreeing) and `derivation.events` (is_movement, is_transformation, uloc); typical values from `ranked` (count per activity and value, ties alphabetical), top values from `_tops`.
**Example** (running example, Level 3, no filter): as in the concept's table "Step 2"; e.g. quality check: 4 events, B1 (3/4 = 75 %); provided 1/4, 2 (1, 1) · 50 %, 3/4 (0/1). Expanded crane move: A2 67 % (4), B1 33 % (2); 2 distinct.
**Filtering:** one row per activity with kept events; events, role, HUs per event, located and agreed describe the kept events as a whole; typical location and top locations count passing relations only; share at location appears only with a location (or exclude location) filter. Example "Location B1, post": crane move 1, quality check 3 (50 %, B1 3/3, 2/3 (0/1): e14 still disagreeing), unload truck 1, cut 1.
Events without handling units have no relation and therefore never appear.
**Settings:** the selected level; sort order kept across pages and reloads (`profile.sort`, `lib/pageState.ts`); the search box is not kept.
**Code:** route `GET /{ocel_id}/overview/activity-profile` (`getActivityProfile`); frontend `components/ActivityProfile.tsx` (`ActivityProfile`, `Row`, `Heading`; hover texts in `INFO`, sort keys in `sortValue`). Tests: `tests/test_overview_activity_profile.py`.
**How to change:** a new column needs a field in `ActivityRow` and its aggregation in `activity_profile` (backend), `pnpm run build:modules`, a heading and a cell in `ActivityProfile.tsx` (and a `sortValue` entry if sortable). Number of expanded locations: `TOP` in `activity_profile.py`.
**Alternatives:** the typical recipe is struck in the concept until defined. Routes (ploc → loc of moved handling units) were removed on 2026-10-28 as not useful in their current form.

## 6. Overview charts
**What it shows:** a **top 10 / bottom 10** switch, three bar charts in one row (Activities, Locations, Movement activities) and below them the location × activity heatmap (concept section "Overview charts"). Bars are horizontal, largest on top.

| Chart | One bar per | Bar counts | Controls (default first) | "by" options (default) |
|---|---|---|---|---|
| Activities | activity | relations or events | relations / events; most frequent / most locations | none, location (default), object type |
| Locations | location at the selected level ("–" = ⊥) | relations or events | relations / events | none, activity (default), object type |
| Movement activities | activity of movement events, ranked by moved relations | relations | – | none, movement status (default), location, object type |

- **relations:** every passing hu-event relation counts once, under its own values (its loc for locations).
- **events:** only agreeing kept events, each once, under the common value of its handling units: eloc for locations ("–" if no handling unit is located), the object type ("[several types]" if they differ). Not agreeing events are left out; the subtitle gives their number, the hover of an Activities bar the number for that activity.
- **most locations** (Activities): bar = distinct locations ≠ ⊥ of the activity's passing relations (in both measures); the hover lists them; "by object type" is not offered.
- **Movement status:** moved, origin known (ploc ≠ ⊥, ploc ≠ loc) / moved, origin unknown (⊥) (ploc = ⊥) / not moved (ploc = loc). A bar's rank is its number of moved relations; its height all its relations.
- **top 10:** the 10 largest bars, the rest summed into a grey "other" bar (hover: how many bars). **bottom 10:** the 10 smallest, the rest left out. Ties: alphabetical. The switch also sets both heatmap axes.
- **Colours:** each chart ranks its own segment values. Every shown bar gets enough of its largest values that at most 5 % of it stays grey "other"; the chosen values are ordered by their total over the shown bars (first palette colour = largest), at most 50 per chart. "–" segments and the "–" bar are grey or hatched and never get a colour. The legend sits beside the chart (at most ¼ of the card width, long names cut, full name on hover); bar labels are cut to ¼ of the chart width.
- **Heatmap:** rows locations ("–" row grey, last), columns activities, cells counts (relations or events, as above); 10 values per axis by their totals following the top/bottom switch, no "other"; **all / movements / transformations** keeps the relations (events) of all, of movement or of transformation events.
- **Clicks:** a bar or segment adds the bar's value and the segment's value to the include filters (a heatmap cell: its location and activity). "–" adds the location "[unknown]"; "other", "[several types]" and movement status add nothing. Chart locations are loc (post), so adding a location switches the location role "pre" to "post" ("either" stays).

**How it is calculated:** `overview/overview_charts.py`. Step 1: `relation_units` (passing relations with activity, object type, location, movement status, moved) and `event_units` (kept agreeing events with activity, object type, location = eloc; plus the not agreeing ones). Step 2: `bar_chart(units, bar, by, end, count, rank)` is generic for every bar chart (`chosen` picks the top/bottom bars, `colour_values` the coloured segment values); `overview_bar_chart` picks the units and the bar dimension per chart; `heatmap` counts units per (location, activity).
**Example** (running example, Level 3, no filter): as in the concept's "Deriving Overview Charts". Activities, relations, by location: crane move 6 (A2 4, B1 2), quality check 6 (B1 3, T 1, – 2); events: quality check 3 (B1 2, – 1), 1 not agreeing event left out (e14). Most locations: quality check 2 (B1, T). Locations, events: B1 5, A1 4, A2 4, T 2, – 1. Movement activities: load truck 4 (moved, origin known 3, origin unknown 1), crane move 6 (ranked 3: moved 3, not moved 3), unload truck 3. Heatmap, relations: A2 × crane move 4, – × quality check 2.
**Filtering:** all charts count the kept part: passing relations, kept events (with whole-event agreement and eloc). Example "Location B1, post", Locations chart: only the bar B1.
**Settings:** the selected level; per chart measure, mode and "by" (`charts.activities`, `charts.locations`, `charts.movements`), the heatmap switches (`charts.heatmap`) and the top/bottom switch (`charts.end`) are kept across pages and reloads (`lib/pageState.ts`).
**Code:** routes `GET /{ocel_id}/overview/bar-chart` (`getBarChart`, parameters chart, measure, by, mode, end) and `GET /{ocel_id}/overview/heatmap` (`getHeatmap`, parameters measure, end, events); frontend `components/OverviewCharts.tsx` (`OverviewCharts`, `BarChartCard`, `HeatmapCard`, `traces`; chart definitions in `CHARTS`, "by" options in `BY_OPTIONS`, click mapping in `FILTER_OF` and `useAddValues`, hover texts in `INFO`). Tests: `tests/test_overview_charts.py`.
**How to change:** number of bars `SHOWN`, grey share `MAX_OTHER_SHARE`, colour cap `MAX_COLOURS` (all in `overview_charts.py`); a new "by" dimension needs a column in `relation_units`/`event_units`, an entry in `BY_COLUMN` and the `By` literal (backend), `pnpm run build:modules`, then an entry in `BY_OPTIONS` (and `FILTER_OF` if clicks should filter by it). A new chart: a branch in `overview_bar_chart` and an entry in `CHARTS`.
**Alternatives:** the transformation activities chart and the high-level location "by" are struck in the concept. Events mode by object type could instead count an event under each of its object types (then an event counts more than once).
