# Configuration (shared header)

Shown on top of every page. Concept: `overview/Deriving Locations.md`, sections "input data" and "shared header" (outside this repo).
How the inputs are resolved and checked: `docs/resources/location-derivation.md`, section 1 and 2. Storage and caching: `docs/hosting/state-and-caching.md`.

## 1. Configuration summary
**What it shows:** one line, e.g. `Configuration: handling units slab, coil; locations from "to_loc"; Level 3.`, and the button "Edit configuration". The notices of the applied configuration appear on the page below the key numbers (`overview.md`, section 2).
Locations read `from qualifier "to"` for the e2o-qualifier option and `from table "target_locations.csv"` for a table.
More than five selected object types show the first five (in the order selected) and "(+n)", n being the number of further types; hovering it lists all (`components/ShortList.tsx`).
**Example:** running example configuration (see `data/running_example/README.md`) gives the line above.
**Filtering:** not affected by filters.
**Code:** `ModulePage.tsx`, `SummaryLine` (the text) and `locationSource(locations)` (the locations part); the card is built in `ModulePage`.
**How to change:** add a part (e.g. movement activities) in `SummaryLine`; keep it one line. The number of entries before "(+n)" is `SHORT_LIST_LIMIT` in `ShortList.tsx`.
**Alternatives:** listing every input in the line was too long for logs with many activities; the full configuration is one click away.

## 2. Configuration form
**What it shows:** shown instead of the summary while no configuration is applied, and after "Edit configuration" (with "Cancel").
One section per input, each with an option switch, the matching pickers and an ⓘ text:

| Section | Options | Pickers |
|---|---|---|
| Handling units (required) | object types, table | object types with number of objects; table + object column |
| Location level | Level 0-3 (default 3) | one line per level in the ⓘ text |
| Movement events (required) | activities, event attribute, table | activities with number of events; attribute + values with number of events; table + event column |
| Transformation events (optional) | none, activities, event attribute, e2o qualifiers, table | as above; qualifiers with number of relations |
| Target locations (required) | event attribute, e2o qualifier, table | attribute; qualifiers + location name (object id or a static object attribute); table + event and location columns |
| Pickup locations (optional) | none, event attribute, e2o qualifier, table | as for target locations |

- Table options: select an uploaded table or "Upload CSV" right there; "Show first rows" shows the first 5 rows. A CSV file can also be dragged onto the table option (the table field, its column fields or "Upload CSV"); a dashed outline shows the drop area, other file types are refused with a red note. Re-uploading a file with the name of the selected table keeps the chosen columns.
- "Apply" is disabled while entries are missing; hovering lists them (`missingEntries`).
- "Apply" derives everything in the backend. Blocking errors appear in a red box, each with its affected ids (first 20, "show all" for the rest, at most 500 sent); notices appear as grey lines. With blocking errors, the previously applied configuration stays in use.
- "Download configuration" saves the form as JSON (also an incomplete one); "Load configuration" fills the form from such a file, chosen in the dialog or dragged onto the button (only .json files). Tables are referred to by file name, so after loading in a new session, upload the same files again.

**Example:** loading the running example configuration and applying it gives the summary line of section 1. Replacing the target locations by a table with the rows (e5, A2), (e5, B1) gives the blocking error "Target locations: events with different locations in the table." with id e5.
**Filtering:** the pickers count over the log as Ocelescope currently shows it (with Ocelescope's own filters); the module's page filters do not apply.
**Settings:** level default 3; new forms start with object types, activities and event attribute selected as options, transformation and pickup locations "none".

**Code** (`frontend-modules/location-ocpm/src/components/ConfigForm.tsx`):
- Form state `ConfigDraft`: keeps the entries of every option of an input, so switching the option and back loses nothing. `emptyDraft()` is the empty form.
- `toConfig(draft)` → `DerivationConfig` sent to the backend; `fromConfig(config)` the reverse (applied or loaded configuration).
- Sections: `EventSetFields` (movement and transformation events), `LocationFields` (target and pickup locations), `TableColumns` (table, columns, upload, preview), `CountPicker`, `AttributeValuePicker`.
- Texts: `INFO` (ⓘ texts) and `LEVELS` (level labels).
- Errors and notices: `MessageLine`, `Notices` (also used for the configuration notices on the overview page).
- Backend: `configuration_routes.py` (`get_options`, `get_attribute_values`, `apply_config`, `upload_table`), resolution in `derivation/inputs.py`.

**How to change:**
- New option for an input: backend first (model in `derivation/config.py`, resolution in `inputs.py`, test), then `pnpm run build:modules` to regenerate the API client, then add the option to `EventSetDraft`/`LocationsDraft`, to `toConfig`/`fromConfig`, to `missingEntries` and to the section's switch.
- Different defaults: `emptyDraft`.
- Wording: `INFO`, `LEVELS`, the `hint` texts in `ConfigForm`.
- More ids per error: `api_models.MAX_IDS` (backend) and the 20 in `MessageLine`.

**Alternatives considered:**
- Ocelescope's table resource instead of CSV upload: it is a typed resource class, not a generic table, so it needs one resource type per input; postponed until a plugin should produce inputs.
- Applying on every change: deriving can take seconds on large logs, so the user applies explicitly.
- Storing the configuration in the browser: the backend session already holds tables and cache, and keeping all three together avoids a configuration that refers to tables the backend no longer has.

## Loading files by drag and drop
`components/DropTarget.tsx` (`DropTarget`) wraps a button or field: a file dropped on it is handled like one chosen in the file dialog (`onFile`); files not ending in one of `accept` go to `onReject`. While a file is dragged over, the area gets a dashed outline in the primary colour. Used for "Load configuration" (`accept=[".json"]`) and for each table option of the form (`TableColumns` in `ConfigForm.tsx`, `accept=[".csv"]`). To add it elsewhere, wrap the element in `<DropTarget accept={[...]} onFile={...}>`.
