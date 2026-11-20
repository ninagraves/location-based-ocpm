# Settings bar

Shown on every page of the module, below the title (on the Configuration page below the configuration summary and its notices), once a configuration is applied (Nina, 2026-11-20).
Every change applies to **all pages**: the backend stores the settings per log and every content route derives with them, so no page has its own copy.
The bar will get more settings; how to add one is under "How to change".

## What it shows
`Settings · Location function [Level 3: + transformation locations (default)] · Transformation events are processing operations [on] · Locations: [low | high]`

| Setting | Values | Default | Effect on every page |
|---|---|---|---|
| Location function | Level 0-3, i.e. the low-level location function $loc^k$ (labels as in the form: "Level 0: provided locations only" … "Level 3: + transformation locations") | the level of the applied configuration (3 for a new form) | current location $loc^k$, previous location $ploc^k$, $eloc$, agreement, locatedness and flags at Level $k$ |
| Transformation events are processing operations | on / off | on (P = selection ∪ T) | on: $P$ = selected processing events ∪ $T$; off: $P$ = selected processing events only (without a selection: $P = \emptyset$) |
| Locations: low \| high | low, high | high if high-level locations are configured; else low, and high is disabled (hover says why) | high: $\widehat{hl} = agg(loc^k)$ with the provided high-level locations; low: $\widehat{hl} = loc^k$ (the identity as high-level function) |

Hovering a label explains the setting. While a change is computed, the controls are disabled and a small spinner shows; afterwards every page reloads its content.
If deriving with the change gives blocking errors, they are listed in red below the bar and nothing changes.

## How it is calculated
- Level and "Transformation events are processing operations" are inputs of the derivation and are **stored in the applied configuration** (`DerivationConfig.level`, `ProcessingOperations.include_transformations`). So the configuration summary ("Level 1"), the form (section "Location level", switch "and all transformation events") and "Download configuration" always show the bar's values; changing them in the form and applying changes the bar too.
- Locations: low | high is not an input of the derivation. It is stored per log next to the configuration (`GlobalSettings.location_mode`). Low mode derives with the **effective configuration** = the applied configuration without its high-level locations (`effective_config`), so on every page every location is its own high-level location ($agg = id$). The configuration itself keeps its high-level input; switching back to high uses it again.
- Applying a configuration that adds high-level locations to one without them sets the mode to high (the default). Removing them forces low.
- Every content route reads the derivation through `current_derivation`, which uses the effective configuration; the cache keeps the current and the previous derivation per log, so switching back and forth (e.g. low → high → low) does not derive again.

## Example
Running example with `data/running_example/configuration.json` (high-level locations A1, A2 → A, B1 → B, T unmapped; P = label ∪ T; upload `inputs/locations.csv` first).
Step by step, with the functions involved:
1. Apply the configuration (`apply_config`). `get_settings` → Level 3, transformations on, Locations high (high-level locations are configured).
   Overview page, key numbers: Locations tile "High-level locations 3" (A, B, T); processing operations 4 (cast slab, cut, label, roll). Instances: c1's events e3, e4, e5 have $\widehat{hl}$ = A.
2. Switch Locations to low (`update_settings` with `location_mode="low"`). `effective_config` drops the high-level locations, `current_derivation` derives with it, every page reloads.
   Key numbers: "Locations 4" (A1, A2, B1, T); the Locations chart on the Configuration page has no high-level ring, flag F6 is hidden; Instances: c1's e3, e4 have $\widehat{hl}$ = A1, e5 has A2; the overview filter's location list is no longer grouped.
   The configuration summary still says "high-level locations from table "locations.csv"".
3. Switch back to high: the cached derivation of step 1 is used again (`ModuleState.recall`), nothing is derived.
4. Turn "Transformation events are processing operations" off (`update_settings` with `include_transformations=False`; `with_update` writes it into the configuration). Processing operations: 1 (label only); in the DFG the category chip "Processing" counts 1 event instead of 4.
5. Choose "Level 1: + forward fill" (`with_update` sets `level=1`). Agreed located events: 12 of 17 instead of 15; c1's e3 and e4 become unlocated; the summary line says "Level 1".

## Filtering
The settings are not filters. The overview filter bar keeps its values when a setting changes; it is evaluated on low-level locations in both modes (a high-level filter value stands for its preimage, see `overview.md`, section 0).

## Code
- Backend `backend-modules/location-ocpm/src/ocelescope_module_location_based_ocpm/`:
  - `global_settings.py`: `LocationMode`; `GlobalSettings(location_mode)` (stored part); `SettingsState(configured, level, include_transformations, location_mode, high_level_available)` (what the bar shows); `SettingsUpdate(level, include_transformations, location_mode)` (a change, fields left out stay); `includes_transformations(config)`; `effective_location_mode(config, settings)` ("low" without high-level locations); `effective_config(config, settings)` (drops the high-level locations in low mode); `with_update(config, update)` (writes level and transformations into a copy of the configuration); `settings_state(config, settings)`.
  - `settings_routes.py`: `GET /{ocel_id}/settings` (`getSettings`, `get_settings`), `PUT /{ocel_id}/settings` (`updateSettings`, `update_settings` → `SettingsResult(applied, settings, errors, notices)`; 409 without configuration, 422 for high without high-level locations). It derives right away (or recalls a cached derivation), so errors show at the bar and pages open without waiting.
  - `state.py`: `ModuleState.settings` (per log), `ModuleState.recent`, `remember`, `recall`, `RECENT_PER_LOG`.
  - `configuration_routes.py`: `current_derivation` (effective configuration, recent cache), `apply_config` (sets high when high-level locations are added).
  - `overview_routes.get_page_filter`: fills `PageFilter.location_mode` from the settings (no query parameter any more).
- Frontend `frontend-modules/location-ocpm/src/`: `components/SettingsBar.tsx` (`SettingsBar`, `Setting`, hover texts `INFO`), `lib/settings.ts` (`useGlobalSettings`, `useChangeSettings`: refetches every query of the log after a change), `components/ModulePage.tsx` (places the bar on every page), `lib/filters.ts` (`useLocationContext` reads the mode from the settings). Level labels: `LEVELS` in `components/ConfigForm.tsx`.
- Tests: `backend-modules/location-ocpm/tests/test_global_settings.py` (the example above).

## How to change
- **A new setting that is an input of the derivation** (like the level): a field in `SettingsState` and `SettingsUpdate`, write it in `with_update`, read it in `settings_state`; `pnpm run build:modules`; a control in `SettingsBar`; a test in `test_global_settings.py`. The cache key already covers the whole configuration.
- **A new setting that only changes how pages compute or show things** (like Locations): a field in `GlobalSettings`, `SettingsState` and `SettingsUpdate`; set it in `update_settings`; either apply it in `effective_config` (if it can be expressed as a configuration change) or read `state.settings[ocel_id]` in the routes that need it (as `get_page_filter` does). If it changes the derivation, include it in the cache key (`fingerprint` is computed over the effective configuration).
- Other default for Locations: `GlobalSettings.location_mode` and the reset in `apply_config`.
- More derivations kept per log (instant switching between more combinations): `RECENT_PER_LOG` in `state.py` (each one holds all level columns of the log).

## Alternatives considered
- Keeping the settings in the browser and sending them as query parameters to every route (as the filter was): every route and every new setting would need the parameters, and the backend's precomputations (e.g. the default DFG) could not know them.
- Removing the level and the transformations switch from the form: the downloaded configuration would no longer say which level an analysis used; storing them in the configuration keeps one source.
- Low mode by keeping the high-level columns and only ignoring them in the pages: every page would need its own fallback; dropping agg in the effective configuration gives the identity everywhere at once.
