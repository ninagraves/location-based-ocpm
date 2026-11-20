# Configuration (summary and form)

Shown only on the Configuration page (before 2026-11-20 on top of every page; the other pages now show the settings bar, `settings-bar.md`). While no configuration is applied for the current log, opening Overview, Directly-follows graph or Instances opens the Configuration page instead (section 3). Concept: `overview/Deriving Locations.md`, sections "input data" and "shared header", and for the location context `overview/module/Module Overview.md`, "Update Overview Page", section 1 (outside this repo).
How the inputs are resolved and checked: `docs/resources/location-derivation.md`, section 1 and 2. Storage and caching: `docs/hosting/state-and-caching.md`.

## 1. Configuration summary
**What it shows:** one line, e.g. `Configuration: handling units slab, coil; locations from "to_loc".`, and the buttons "Download configuration" (saves the applied configuration as JSON, like the button in the form) and "Edit configuration". The notices of the current derivation appear right below this card (`overview.md`, section 2), then the settings bar.
The level and whether the transformation events are processing operations are not part of the configuration; they are set in the settings bar (`settings-bar.md`).
Locations read `from qualifier "to"` for the e2o-qualifier option and `from table "target_locations.csv"` for a table.
Configured location-context inputs are appended, e.g. `; high-level locations from table "locations.csv"; vehicles from table "locations.csv"; storage units from table "locations.csv"; processing operations label` (only the selection; `contextParts`, `sourceOf`).
More than five selected object types show the first five (in the order selected) and "(+n)", n being the number of further types; hovering it lists all (`components/ShortList.tsx`).
**Example:** running example configuration (see `data/running_example/README.md`) gives the line above.
**Filtering:** not affected by filters.
**Code:** `ModulePage.tsx`, `SummaryLine` (the text) and `locationSource(locations)` (the locations part); the card is built in `ModulePage`.
**How to change:** add a part (e.g. movement activities) in `SummaryLine`; keep it one line. The number of entries before "(+n)" is `SHORT_LIST_LIMIT` in `ShortList.tsx`.
**Alternatives:** listing every input in the line was too long for logs with many activities; the full configuration is one click away.

## 2. Configuration form
**What it shows:** shown instead of the summary while no configuration is applied, and after "Edit configuration" (with "Cancel").
One section per input, each with an option switch, the matching pickers and an ⓘ text, in three groups (Nina, 2026-11-20): the required inputs (handling units, target locations below them; movement events, pickup locations on the right), then "Location context (optional)", then "Transformations (optional)":

| Section | Options | Pickers |
|---|---|---|
| Handling units (required) | object types, table | object types with number of objects; table + object column |
| Target locations (required) | event attribute, e2o qualifier, table | attribute; qualifiers + location name (object id or a static object attribute); table + event and location columns |
| Movement events (required) | activities, event attribute, table | activities with number of events; attribute + values with number of events; table + event column |
| Pickup locations (optional) | none, event attribute, e2o qualifier, table | as for target locations |
| High-level locations (optional, group "Location context") | none, table, event attributes, object attribute, o2o relation, naming pattern | table + location and high-level columns; low-level and high-level event attributes; attribute of the location objects; o2o qualifiers + name (id or attribute); regular expression with one group |
| Processing operations (optional) | none, activities, event attribute, e2o qualifiers, table; whether the transformation events count too is set in the settings bar | as for transformation events; "none" with the switch on = P = T (default) |
| Vehicles, storage units (optional) | none, locations, table, event attribute, object types | locations picked from L or typed in; table + location column + optional true/false column; attribute + values (their events' targets); object types of the location objects |
| Transformation events (optional, group "Transformations") | none, activities, event attribute, e2o qualifiers, table | as for movement events; qualifiers with number of relations |
| Consumed and produced handling units (optional, group "Transformations") | default (first/last timestamps), e2o qualifiers, table, parent relations (o2o), produced/consumed objects, first/last timestamps, frequency of first/last activities | consumed and produced qualifiers; table + event, object, role columns + role values; o2o qualifiers + direction; produced and consumed objects (object attribute values or table) + final/partial; threshold τ. Options deriving T replace the transformation-events pickers; details in `docs/resources/transformation-inputs.md` |

The object-attribute, o2o and object-type options only appear if target or pickup locations use e2o qualifiers.
**Location template** (button next to "Location context"): downloads `locations.csv` with one row per location of L and the empty columns `high_level`, `is_vehicle`, `is_storage`; fill it in, upload it once and pick it in the three location inputs. The locations come from `POST /{ocel_id}/locations` (`get_locations`), which resolves the current target and pickup inputs before "Apply" (only complete inputs are sent).

- Table options: select an uploaded table or "Upload CSV" right there; "Show first rows" shows the first 5 rows. A CSV file can also be dragged onto the table option (the table field, its column fields or "Upload CSV"); a dashed outline shows the drop area, other file types are refused with a red note. Re-uploading a file with the name of the selected table keeps the chosen columns.
- "Apply" is disabled while entries are missing; hovering lists them (`missingEntries`).
- "Apply" derives everything in the backend. Blocking errors appear in a red box, each with its affected ids (first 20, "show all" for the rest, at most 500 sent); notices appear as grey lines. With blocking errors, the previously applied configuration stays in use.
- "Download configuration" saves the form as JSON (also an incomplete one); "Load configuration" fills the form from such a file, chosen in the dialog or dragged onto the button (only .json files). Tables are referred to by file name, so after loading in a new session, upload the same files again.

**Example:** loading the running example configuration and applying it gives the summary line of section 1. Replacing the target locations by a table with the rows (e5, A2), (e5, B1) gives the blocking error "Target locations: events with different locations in the table." with id e5.
**Filtering:** the pickers count over the log as Ocelescope currently shows it (with Ocelescope's own filters); the module's page filters do not apply.
**Settings:** new forms start with object types, activities and event attribute selected as options, transformation and pickup locations "none".

**Code** (`frontend-modules/location-ocpm/src/components/ConfigForm.tsx`):
- Form state `ConfigDraft`: keeps the entries of every option of an input, so switching the option and back loses nothing. `emptyDraft()` is the empty form.
- The form keeps its unapplied changes and the last Apply result when another page is opened, and across reloads, as long as the applied configuration is the one the changes started from (`config.form.<log>`, `usePageState`); "Edit configuration" stays open too (`config.editing.<log>`). "Apply" and "Cancel" drop the kept changes (since 2026-11-20; `docs/hosting/state-and-caching.md`, section "Page state").
- `toConfig(draft)` → `DerivationConfig` sent to the backend; `fromConfig(config)` the reverse (applied or loaded configuration).
- Sections: `EventSetFields` (movement, transformation events, processing operations), `RolesFields` and `ObjectSetFields` (consumed and produced handling units), `LocationFields` (target and pickup locations), `HighLevelFields`, `LocationSetFields` (vehicles, storage units), `TableColumns` (table, columns, upload, preview), `CountPicker`, `AttributeValuePicker`; `useFormLocations` (L for pickers and template), `downloadTemplate`.
- Texts: `INFO` (ⓘ texts) and `LEVELS` (level labels).
- Errors and notices: `MessageLine`, `Notices` (also used for the notices below the summary, in `ModulePage`, and for errors of the settings bar). `LEVELS` is also used by the settings bar.
- Backend: `configuration_routes.py` (`get_options`, `get_attribute_values`, `get_locations`, `apply_config`, `upload_table`), resolution in `derivation/inputs.py` and `derivation/location_context.py`.

**How to change:**
- New option for an input: backend first (model in `derivation/config.py`, resolution in `inputs.py`, test), then `pnpm run build:modules` to regenerate the API client, then add the option to `EventSetDraft`/`LocationsDraft`, to `toConfig`/`fromConfig`, to `missingEntries` and to the section's switch.
- Different defaults: `emptyDraft`.
- Order of the sections: the JSX at the end of `ConfigForm` (three `SimpleGrid`s of two columns, filled row by row: the required inputs, "Location context", "Transformations").
- Wording: `INFO`, `LEVELS`, the `hint` texts in `ConfigForm`.
- More ids per error: `api_models.MAX_IDS` (backend) and the 20 in `MessageLine`.

**Alternatives considered:**
- Ocelescope's table resource instead of CSV upload: it is a typed resource class, not a generic table, so it needs one resource type per input; postponed until a plugin should produce inputs.
- Applying on every change: deriving can take seconds on large logs, so the user applies explicitly.
- Storing the configuration in the browser: the backend session already holds tables and cache, and keeping all three together avoids a configuration that refers to tables the backend no longer has.

## Loading files by drag and drop
`components/DropTarget.tsx` (`DropTarget`) wraps a button or field: a file dropped on it is handled like one chosen in the file dialog (`onFile`); files not ending in one of `accept` go to `onReject`. While a file is dragged over, the area gets a dashed outline in the primary colour. Used for "Load configuration" (`accept=[".json"]`) and for each table option of the form (`TableColumns` in `ConfigForm.tsx`, `accept=[".csv"]`). To add it elsewhere, wrap the element in `<DropTarget accept={[...]} onFile={...}>`.

## 3. Redirect while no configuration is applied
**What it does:** while no configuration is applied for the current log, Overview, Directly-follows graph and Instances open the Configuration page instead (Nina, 2026-11-20). The sidebar still lists all four pages: Ocelescope 0.13 only greys out routes while no log is loaded (`requiresOcel`) and has no way for a module to hide or disable routes itself.
**Example:** upload the running example, open "Directly-follows graph": the address changes to `/locationBasedOcpm/configuration` and the form shows. After "Apply", "Directly-follows graph" opens normally.
**Code:** `ModulePage.tsx`: `unconfigured` (not the Configuration page, a log is selected, `getConfig` has answered without error and has no configuration) and a `useEffect` calling `router.replace(CONFIGURATION_ROUTE)` (`next/router`; `CONFIGURATION_ROUTE` from `getModuleRoute` of `@ocelescope/core`). `replace` instead of `push`, so "back" skips the page that could not be shown. `next` is a peer dependency of the module for this.
**How to change:** another target page: `routeName` in `CONFIGURATION_ROUTE`. A page that should open without a configuration: render it without `ModulePage`, or pass `configuration`.
**Alternatives considered:** hiding the entries in the sidebar needs a change in Ocelescope (`NavbarGroup` in `@ocelescope/core`, e.g. a per-route `isAvailable` hook); a module cannot do it. Showing a note with a link on each page instead of redirecting (the version before) leaves the pages reachable but empty.
