# State and caching

## Where state lives
- Backend: `state.py`, class `ModuleState`, one per backend session, kept in memory in `configuration_routes.STATES` (`SessionStates`, keyed by the session id). States of sessions the backend no longer knows ("Reset session") are dropped on the next access.
  Ocelescope's own module state (`session.module_states`, since 0.13) is not used: it only holds JSON-serialisable pydantic models and serialises them on every update, which does not fit polars frames and cached derivations.
  - `tables`: uploaded CSV tables by file name (every column read as text). Uploading a file with the same name replaces the table.
  - `configs`: the applied `DerivationConfig` per log id (its `level` and `include_transformations` are ignored; the settings bar's values apply).
  - `settings`: the settings bar per log id (`global_settings.GlobalSettings`: level, transformations as processing operations, Locations: low | high); a log without an entry uses the defaults.
  - `cache`: the current derivation per log id (`CachedDerivation(key, derivation)`), i.e. the one of the effective configuration (`global_settings.effective_config`).
  - `recent`: per log id the last `RECENT_PER_LOG` (2) derivations, newest first (`remember`, `recall`), so that switching a setting back does not derive again.
- Lifetime: survives page switches and browser reloads; lost with "Reset session" in Ocelescope or a backend restart.
  The frontend keeps what each page looks like in the browser (section "Page state" below).
- Configuration files: "Download configuration" writes the form as JSON (the `DerivationConfig` schema, tables by file name, not their contents); "Load configuration" fills the form from such a file. Only the form changes; "Apply" is still needed.

## Cache
- Key (`state.fingerprint`): SHA-256 over the effective configuration (incl. level; without high-level locations in Locations: low), the log version and the content hashes of the tables the configuration uses.
- Log version (`configuration_routes.log_version`): which version of the log a request reads: `original`, or `view:<id>` for an Ocelescope view. Ocelescope (since 0.13) never changes an uploaded log; a filter creates a view, whose id is a hash over the log and the filter's operations, and the active view is what requests read by default. Like Ocelescope's `ApiOcel`, `current_derivation` and `POST /{ocel_id}/config` accept `ocel_version=original` and `view_id=<id>`.
- `POST /{ocel_id}/config` derives, and on success stores the configuration and the cache entry.
- Content routes depend on `configuration_routes.current_derivation`: it applies the settings (`effective_config`), recomputes the key on every request (cheap, no data read), takes the current or a recent derivation with that key, and derives again only if there is none. Up to `RECENT_PER_LOG` entries per log; the oldest is dropped.
- `PUT /{ocel_id}/settings` derives with the changed settings right away and caches the result, so pages open without waiting.
- If the applied configuration fails on a changed log (e.g. a filter removed every movement event's target), `current_derivation` answers 409 with the errors; the applied configuration stays until the user changes it.
- Memory: one `Derivation` per log (relation frame with all level columns plus per-level event frames). For a log with n hu-event relations this is roughly 20 columns × n rows.

## Page state
Every page opens again as it was left (Nina, 2026-11-20): switching to another page of the module (or to another Ocelescope page) and back shows the same selections, settings, searches, unfolded rows, graphs (layout, dragged nodes, zoom and pan) and scroll position.
Ocelescope unmounts a page when another one opens, so nothing stays in the React tree; what a page needs is kept outside it, in the browser tab, per log (the log id is part of every key).

| What | Where | Survives a reload? |
|---|---|---|
| Settings, filters, selections, searches, sort, page and page size of tables, unfolded rows, the configuration form's unapplied changes, the editing state of the Configuration page | `usePageState(key, initial)` (`lib/pageState.ts`): like `useState`, shared by all components using the key, in memory and in the tab's sessionStorage (JSON) | yes |
| Graph layouts (ELK) of the DFG, the lineage and the object graph; dragged node positions; zoom and pan | `useKeptLayout`, `useKeptViewport` (`lib/keptView.ts`) and `keep`/`recall` (`lib/pageState.ts`), memory only (layouts hold functions and maps) | no: the graph is laid out and fitted again |
| Scroll position of the page and of the DFG sidebar's lists | `useKeptScroll` (in `ModulePage`), `useKeptScrollOf` (`lib/keptView.ts`), memory and sessionStorage | yes |
| Answers of the backend's requests | React Query's cache in Ocelescope's query client; the module keeps its own answers `KEEP_ANSWERS_MS` (30 min) after no page shows them instead of React Query's 5 min (`useKeptAnswers`, `lib/queries.ts`) | no |

Keys used by the pages (all with the log id, except settings that hold for every log): `filter.<log>`, `profile.*`, `charts.*`, `dfg.v6.<log>` (DFG settings), `dfg.sidebar` (width, hidden), `dfg.height`, `dfg.sidebar.<log>.*` (searches, unfolded rows, scroll positions), `dfg.save.*.<log>`, `dfg.view.<log>.*` (layout, dragged nodes, zoom and pan), `instances.*.<log>` (selection, table, unfolded rows, chart settings), `instances.lineage.view.<log>.*`, `instances.objectGraph.view.<log>.*`, `config.form.<log>`, `config.editing.<log>`, `scroll.<log>.<path>`.

**No stale state.**
- A kept layout is only used for the same inputs (`sameInputs`: identical, or equal maps or JSON; callbacks are not compared), e.g. the same graph and look settings; otherwise the graph is laid out and fitted again and the new layout is kept instead. Dragged positions and zoom and pan belong to one layout (its object or ELK generation) and are dropped with it.
- Answers: React Query refetches a page's requests when the page opens (as before), so a kept answer is shown at once and replaced if the log (e.g. an Ocelescope filter, i.e. a new view), the configuration or the settings changed since. Applying a configuration or changing the settings refetches every request of the log (`ofLog` in `lib/queries.ts`; since 2026-11-20 also the hand-written keys `["locationBasedOcpm", …, <log>, …]` of the DFG and Instances pages, which the old URL-only test missed).
- The configuration form keeps its unapplied changes only for the configuration they started from (`base` in `ConfigForm`); Apply and Cancel drop them.
- Settings, selections and filters are kept as they are when the configuration changes (as before); handling units no longer in the log stay selected until unselected.

**Changing it.**
- Keep a new piece of a page: replace its `useState` by `usePageState` with a key containing the log id (or `useMemoryState` for values that are not JSON); for a layout computed in the browser use `useKeptLayout` with every input it depends on.
- Keep answers longer or shorter: `KEEP_ANSWERS_MS` (memory of the tab grows with every distinct request kept).
- Keep layouts across reloads: they would have to be JSON (positions only) and stored with a content hash of their inputs; not done, since ELK recomputes them in well under a second for typical graphs.
- Not kept: zoom of the Plotly charts (they reset on every redraw, also without a page switch), open popovers and dropdown searches, the save dialogs' messages.

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
