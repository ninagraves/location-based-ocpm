# State and caching

## Where state lives
- Backend: `state.py`, class `ModuleState`, kept in Ocelescope's backend session under the key `locationBasedOcpm` (`session.get_module_state`).
  - `tables`: uploaded CSV tables by file name (every column read as text). Uploading a file with the same name replaces the table.
  - `configs`: the applied `DerivationConfig` per log id.
  - `cache`: the latest derivation per log id (`CachedDerivation(key, derivation)`).
- Lifetime: survives page switches and browser reloads; lost with "Reset session" in Ocelescope or a backend restart.
  The frontend keeps the page filter per log (`lib/pageState.ts`, `usePageState`: in memory, shared by all components with the same key, and in the tab's sessionStorage, so it survives page switches and reloads), plus React Query's request cache.
- Configuration files: "Download configuration" writes the form as JSON (the `DerivationConfig` schema, tables by file name, not their contents); "Load configuration" fills the form from such a file. Only the form changes; "Apply" is still needed.

## Cache
- Key (`state.fingerprint`): SHA-256 over the configuration (incl. level), the log version and the content hashes of the tables the configuration uses.
- Log version (`configuration_routes.log_version`): the log's Ocelescope filter pipeline. Ocelescope never changes an uploaded log; it only applies filters, so the filters identify what a request sees.
- `POST /{ocel_id}/config` derives, and on success stores the configuration and the cache entry.
- Content routes depend on `configuration_routes.current_derivation`: it recomputes the key on every request (cheap, no data read) and derives again only if the key changed. One entry per log; a new key replaces the old entry.
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

Messages carry at most 500 ids (`api_models.MAX_IDS`); `count` gives the total.

## Changing it
- Keep tables across sessions or share them between users: replace `ModuleState.tables` by Ocelescope resources (typed `TabularResource`s), as discussed in the iteration 3 proposal (option C1, `claude_notes/` outside this repo).
- More cache entries per log (e.g. to switch levels instantly): make `cache` a small LRU keyed by fingerprint instead of by log id.
- Persist configurations on disk: serialise `configs` (pydantic) on change; nothing else depends on where they live.

## Tests
`tests/test_configuration_api.py` calls the route functions directly with a stand-in session (`FakeSession`): apply, cache reuse, invalidation by level, filters and tables, errors keeping the previous configuration.
