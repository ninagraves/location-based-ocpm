# Overview page

Concept: `overview/Deriving Locations.md`, section "overview" (outside this repo).
Content elements are added one at a time; built so far: key numbers, configuration notices, flag badges.
Still to come: page filter bar (and the filtered values in the key numbers), data overview charts, activity profile, overview charts, flag explore sections.

## Code
- Page: `frontend-modules/location-ocpm/src/routes/Overview.tsx`
- Frame and shared header: `frontend-modules/location-ocpm/src/components/ModulePage.tsx`; the shared header (configuration summary and form) is documented in `configuration.md`.
- Backend: one module per section in `backend-modules/location-ocpm/src/ocelescope_module_location_based_ocpm/overview/`, routes in `overview_routes.py`. Every route reads the cached derivation (`configuration_routes.current_derivation`, see `docs/hosting/state-and-caching.md`).
- Number formatting: `frontend-modules/location-ocpm/src/lib/format.ts` (`num`, `pct`).

## 1. Key numbers
**What it shows:** six tiles, each with a big number and a small grey line.

| Tile | Big number | Small line |
|---|---|---|
| Handling units | \|HU\|, including handling units without events | count per object type, largest first, e.g. "coil 5 · slab 1" |
| Agreed located events | events with eloc(e) ≠ ⊥ at the selected level, "x of \|E\|" | share of all events |
| Relations with a known location | relations with loc ≠ ⊥ at the selected level, "x of \|E2HU\|" | share · "loc at Level k" |
| Movement events | \|M\| | "provided" |
| Locations | \|L\| = distinct locations in uloc ∪ puloc | "target n · pickup m" (pickup "–" if no pickup locations are configured) |
| Transformation events | \|T\|; "–" if none are configured | "no transformation events configured" if none are configured |

**How it is calculated:** `overview/key_numbers.py`, `key_numbers(derivation) -> KeyNumbers`.
eloc and loc come from the derivation at the selected level (`derivation.event_locations[level]["eloc"]`, `derivation.relations[derivation.loc]`); see `docs/resources/location-derivation.md`.
Pickup locations are counted after ignoring pickups of non-movement events (as resolved).
**Example** (running example, Level 3): 6 (coil 5 · slab 1); 15 of 17, 88 % (e14 not agreeing, e17 unlocated); 26 of 28, 93 % · loc at Level 3; 8; 4 (target 4 · pickup 2); 3.
**Filtering:** none yet; with the filter bar, each tile gets the filtered value next to the big number (concept section "Filter Effect").
**Settings:** the selected level (configuration).
**Code:** backend `key_numbers` (route `GET /{ocel_id}/overview/key-numbers`, `getKeyNumbers`); frontend `components/KeyNumbers.tsx` (`KeyNumbers`, `Tile`).
**How to change:** a new tile needs a field in `KeyNumbers`, its computation in `key_numbers`, `pnpm run build:modules`, a `Tile` in `KeyNumbers.tsx`, and an assertion in `tests/test_overview_key_numbers.py`.
**Alternatives:** counting located events by locatedness (fully located) instead of eloc ≠ ⊥; the concept chose agreed located events.

## 2. Configuration notices
**What it shows:** grey lines below the tiles with the notices of the applied configuration, e.g. ignored pickup locations or dropped table rows, each with its ids (first 20, "show all").
**Code:** `Overview.tsx`, `ConfigNotices` (reads `getConfig`), rendering `Notices` from `ConfigForm.tsx`.
**Example:** none for the running example.

## 3. Flags
**What it shows:** one badge per flag, "F1 Partial movement · 2 events"; grey at 0, amber above 0; hovering shows the definition. F4 is hidden if no pickup locations are configured. The explore sections (opened by clicking a badge) follow in later steps.
**How it is calculated:** `overview/flag_badges.py`, `flag_counts(derivation) -> list[FlagCount]`: number of distinct flagged events or handling units in `derivation.flags` (computed at the selected level, see `docs/resources/location-derivation.md`, section "Flags"). Labels, units and hover texts are in `FLAGS`.
**Example** (running example, Level 3): F1 2 events, F2 2 handling units, F3 1 event, F4 1 handling unit, F5 2 events.
**Filtering:** never filtered (whole log).
**Code:** route `GET /{ocel_id}/overview/flags` (`getFlagCounts`); frontend `components/FlagBadges.tsx`.
**How to change:** wording in `FLAGS`; colours in `FlagBadges` (`color` of the `Badge`).
