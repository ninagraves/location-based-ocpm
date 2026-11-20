# State and caching

## Where state lives
- Backend: `state.py`, class `ModuleState`, one per backend session, kept in memory in `configuration_routes.STATES` (`SessionStates`, keyed by the session id). States of sessions the backend no longer knows ("Reset session") are dropped on the next access.
  Ocelescope's own module state (`session.module_states`, since 0.13) is not used: it only holds JSON-serialisable pydantic models and serialises them on every update, which does not fit polars frames and cached derivations.
  - `tables`: uploaded CSV tables by file name (every column read as text). Uploading a file with the same name replaces the table.
  - `configs`: the applied `DerivationConfig` per log id (also holds the settings bar's level and "transformation events are processing operations").
  - `settings`: the settings bar's other values per log id (`global_settings.GlobalSettings`, so far Locations: low | high).
  - `cache`: the current derivation per log id (`CachedDerivation(key, derivation)`), i.e. the one of the effective configuration (`global_settings.effective_config`).
  - `recent`: per log id the last `RECENT_PER_LOG` (2) derivations, newest first (`remember`, `recall`), so that switching a setting back does not derive again.
- Lifetime: survives page switches and browser reloads; lost with "Reset session" in Ocelescope or a backend restart.
  The frontend keeps the page filter per log (since 2026-11-20 without the location mode, which moved to the settings bar) (`lib/pageState.ts`, `usePageState`: in memory, shared by all components with the same key, and in the tab's sessionStorage, so it survives page switches and reloads), plus React Query's request cache.
- Configuration files: "Download configuration" writes the form as JSON (the `DerivationConfig` schema, tables by file name, not their contents); "Load configuration" fills the form from such a file. Only the form changes; "Apply" is still needed.

## Cache
- Key (`state.fingerprint`): SHA-256 over the effective configuration (incl. level; without high-level locations in Locations: low), the log version and the content hashes of the tables the configuration uses.
- Log version (`configuration_routes.log_version`): which version of the log a request reads: `original`, or `view:<id>` for an Ocelescope view. Ocelescope (since 0.13) never changes an uploaded log; a filter creates a view, whose id is a hash over the log and the filter's operations, and the active view is what requests read by default. Like Ocelescope's `ApiOcel`, `current_derivation` and `POST /{ocel_id}/config` accept `ocel_version=original` and `view_id=<id>`.
- `POST /{ocel_id}/config` derives, and on success stores the configuration and the cache entry.
- Content routes depend on `configuration_routes.current_derivation`: it applies the settings (`effective_config`), recomputes the key on every request (cheap, no data read), takes the current or a recent derivation with that key, and derives again only if there is none. Up to `RECENT_PER_LOG` entries per log; the oldest is dropped.
- `PUT /{ocel_id}/settings` derives with the changed settings right away and caches the result, so pages open without waiting.
- If the applied configuration fails on a changed log (e.g. a filter removed every movement event's target), `current_derivation` answers 409 with the errors; the applied configuration stays until the user changes it.
- Memory: one `Derivation` per log (relation frame with all level columns plus per-level event frames). For a log with n hu-event relations this is roughly 20 columns × n rows.

## API (all under `/modules/locationBasedOcpm/v1`)
| Route | Operation id | Purpose |
|---|---|---|
| `POST /tables` | `uploadTable` | upload a CSV table |
| `GET /tables` | `listTables` | uploaded tables with columns and first rows |
| `GET /{ocel_id}/options` | `getOptions` | object types, activities, qualifiers (with counts), event attributes, static object attributes |
| `GET /{ocel_id}/attribute-values?attribute=` | `getAttributeValues` | values of an event attribute with counts (at most 500) |
| `GET /{ocel_id}/config` | `getConfig` | applied configuration and its notices |
| `POST /{ocel_id}/config` | `applyConfig` | derive; store only without blocking errors |
| `GET /{ocel_id}/settings` | `getSettings` | the settings bar's values |
| `PUT /{ocel_id}/settings` | `updateSettings` | change settings (derives; keeps the previous ones on blocking errors) |

Messages carry at most 500 ids (`api_models.MAX_IDS`); `count` gives the total.

## Changing it
- Keep tables across sessions or share them between users: replace `ModuleState.tables` by Ocelescope resources (typed `TabularResource`s), as discussed in the iteration 3 proposal (option C1, `claude_notes/` outside this repo).
- More cache entries per log (e.g. to switch levels instantly): raise `RECENT_PER_LOG` (memory: each entry holds all level columns of the log).
- Persist configurations on disk: serialise `configs` (pydantic) on change; nothing else depends on where they live.

## Tests
`tests/test_configuration_api.py` calls the route functions directly with a stand-in session (`FakeSession`, with an id and an active view): apply, cache reuse, invalidation by level, views and tables, errors keeping the previous configuration, log versions, and dropping states of closed sessions.
