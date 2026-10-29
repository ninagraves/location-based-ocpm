# Location derivation

Derives, for every hu-event relation, where the handling unit is (current location) and where it was before (previous location), plus agreement, locatedness and flags.
Concept: `overview/Deriving Locations.md` (outside this repo); section names below refer to it.
Code: package `backend-modules/location-ocpm/src/ocelescope_module_location_based_ocpm/derivation/` (paths below are relative to it).
Tests: `backend-modules/location-ocpm/tests/` against `data/running_example/` (run `uv run pytest`).

Status: used by the configuration (iteration 3, `docs/pages/configuration.md`); no page shows its results yet.

## Overview of the data flow

| Step | File, function | Output |
|---|---|---|
| 1. User choices | `config.py`, `DerivationConfig` | one option per input, selected level |
| 2. Resolve inputs | `inputs.py`, `resolve_inputs` | `relations` (one row per hu-event relation), `events`, notices, blocking errors |
| 3. Requirements | `requirements.py`, `check_requirements` | blocking errors RQ1-RQ3 |
| 4. Levels | `levels.py`, `add_loc_0` … `add_loc_3`, `add_before`, `add_ploc` | columns `loc_k`, `before_k`, `ploc_k` for k = 0..3 |
| 5. Agreement | `agreement.py`, `event_locations`, `hu_locatedness` | per event: agreeing, eloc, located; per HU: located |
| 6. Flags | `flags.py`, `f1_…` to `f5_…` | flagged events / HUs |
| All | `pipeline.py`, `derive` | `Derivation` |

Conventions in all frames: column names are in `columns.py`; a null value is ⊥.
All levels are always computed (they build on each other and are cheap); the selected level only decides which columns `loc` and `ploc` refer to (`Derivation.loc`, `Derivation.ploc`) and which level the flags use.

**Filtering:** nothing in this resource is filtered. Page filters act later, on the results (see the page docs). Flags always cover the whole log.

**Settings:** `DerivationConfig.level` (0 to 3, default 3), as in the concept box "Current Locations".

## 1. Inputs (concept section "input data")

What it does: turns the user's choice per input into the sets HU, M, T and the partial functions uloc, puloc.

| Input | Options (`config.py`) | Resolved by |
|---|---|---|
| Handling units (required) | `ObjectTypes`, `ObjectTable` | `resolve_handling_units` |
| Movement events M (required) | `Activities`, `AttributeValues`, `EventTable` | `resolve_event_set` |
| Transformation events T (optional) | `Activities`, `AttributeValues`, `Qualifiers`, `EventTable` | `resolve_event_set` |
| Target locations uloc (required) | `LocationAttribute`, `LocationQualifiers`, `LocationTable` | `resolve_locations` |
| Pickup locations puloc (optional) | `LocationAttribute`, `LocationQualifiers`, `LocationTable` | `resolve_locations`, then restricted to M |

Calculation and rules:
- Empty values (null, NaN, `""`, `"NA"`) are never locations: `inputs.provided`. NaN is recognised as a float NaN or the text "nan"/"NaN".
- Table rows with event ids that are not in the log are dropped and reported (`Notice` "unknown_ids_dropped"): `_known_ids`.
- An event with different locations in a location table is a blocking error ("conflicting_locations"); identical duplicate rows are fine.
- Pickup locations of non-movement events are ignored and reported ("pickups_of_non_movements_ignored").
- E2o-qualifier locations (`LocationQualifiers`, `_qualifier_locations`): the object related to an event via one of the selected qualifiers is its location.
  An event related to more than one distinct object is a blocking error ("several_location_objects"; the message names the first such event and its objects, e.g. "e5: more than one location (A2, B1)").
  A location object that is also a handling unit is a blocking error ("location_object_is_handling_unit"), reported per input.
  The location name is the object id, or the value of `name_attribute` (`location_names`); objects without a value keep their id.
  If the attribute changes over time, the last provided value is used; the form only offers static object attributes, so this case only arises from a hand-written configuration.
- Tables are passed to `resolve_inputs` as a dict name → polars frame; the configuration names the table and its columns. In the app they are CSV uploads keyed by file name (`state.py`); Ocelescope's table resource can be added later.
- E2O relations are made unique per (event, object) before building the relations, so an object related to an event via two qualifiers counts once.

Output `ResolvedInputs.relations`: columns `event, hu, object_type, time, activity, is_movement, is_transformation, uloc, puloc`, sorted by hu, time, event. `ResolvedInputs.events` has the event columns for all events, including events without handling units.

Example (running example, `data/running_example/README.md`): object types slab, coil; movement activities crane move, load truck, unload truck; transformation activities cast slab, roll, cut; attributes `to_loc`, `from_loc` → 28 relations, no notices. The same result via the CSV tables, via `event_group = transport`, via the qualifiers `produced`/`consumed` for T (tests in `test_inputs.py`), or via location objects A1, A2, B1, T related with the qualifiers `to`/`from` (`test_qualifier_locations.py`, which builds that log variant in the test).

How to change:
- New option for an input: add a model to `config.py`, add it to the input's union type, handle it in the matching `resolve_…` function, add a test with the running example.
- What counts as empty: `EMPTY_STRINGS` and `provided` in `inputs.py`.

Implementation choices (not in the concept):
- Handling-unit tables: rows with unknown object ids are dropped and reported, like event tables (approved by Nina, 2026-10-28).
- A missing event attribute or table column raises an error (a configuration mistake, not a data problem).

Alternatives considered: keeping M, T, uloc, puloc as separate frames instead of columns of one relations frame; rejected because every later step needs them per relation and one frame avoids repeated joins.

## 2. Requirements RQ1-RQ3 (concept section "Setting")

| Requirement | Function | Blocking error lists |
|---|---|---|
| RQ1: no handling unit with different provided locations at the same time | `check_rq1` | all events of the conflicting (hu, time) pairs that have a uloc |
| RQ2: M ⊆ dom(uloc) | `check_rq2` | movement events without target |
| RQ3: no handling unit in two movement events at the same time | `check_rq3` | the movement events of the conflicting (hu, time) pairs |

`pipeline.derive` checks the requirements only if the input resolution had no blocking errors (otherwise one data problem would be reported twice, e.g. a conflicting table location also as RQ2).
If there are blocking errors, nothing is derived (`Derivation.flags` is None).
Example: the running example satisfies all three; `test_requirements_on_frames` shows a violation of RQ1 and RQ3.

## 3. Current locations, Levels 0-3 (concept "Deriving Current locations")

| Level | Function | Calculation |
|---|---|---|
| loc_0 (provided) | `add_loc_0` | uloc(e) |
| loc_1 (forward fill) | `add_loc_1` | per handling unit, the provided location of the latest located event at or before the event's time (≤) |
| loc_2 (backward fill) | `add_loc_2`, `first_location` | loc_1, else l_0(hu): the uloc of the earliest located event if strictly before the first movement t_M, else the puloc of the first movement |
| loc_3 (transformation locations) | `add_loc_3` | loc_2, else eloc_{loc_2} of the earliest transformation event before t_M with eloc ≠ ⊥ |

How it is computed: Level 1 and before_λ work on "time steps" (`_per_time_step`: one row per handling unit and timestamp, holding the first non-null value). All relations of a handling unit at one timestamp therefore get the same loc_1, which implements the ≤ of the concept; before_λ shifts by one time step, which implements the <.
Example: `data/running_example/expected/levels.csv` (the concept's table "Overview of all levels"); the level at which relations are first located: 15, 4, 3, 4, never 2 (`test_levels.py`).

How to change: each level is one function; a new level k needs a function `add_loc_k`, an entry in `columns.LEVELS`, a call in `pipeline.derive_levels`, the `level` literal in `DerivationConfig`, and expected values in `levels.csv`.

Choice of t_1(hu) when several transformation events qualify (decided by Nina, 2026-10-28): 1. earliest time, 2. with an agreed location (eloc_{loc_2} ≠ ⊥; applied as a filter, as in the concept), 3. smallest event id.

Alternatives considered: a row-by-row loop per handling unit (closer to the formulas, but far too slow on 2 GB logs); DuckDB SQL window functions (similar speed, harder to read and test step by step).

## 4. Location before an event and previous location (concept box "Location before an event")

- `add_before(relations, k)`: before_{loc_k}((e, hu)) = loc_k at the latest strictly earlier time step of hu with loc_k ≠ ⊥ (forward fill, shifted by one time step).
- `add_ploc(relations, k)`: ploc_k = puloc(e) where provided, else before_{loc_k}.
Example: `data/running_example/expected/ploc_1.csv`; e.g. (c1, e13): before_1 = A2, puloc = A1, so ploc_1 = A1.

## 5. Agreement, eloc and locatedness (concept boxes "Location Agreement", "Locatedness")

- `event_locations(relations, events, "loc_k")`: per event the number of relations and located relations, `agreeing` (at most one distinct location ≠ ⊥), `eloc` (that location if exactly one, else ⊥) and `located` (fully located / partially located / unlocated). Events without handling units are included and unlocated.
- `hu_locatedness(relations, "loc_k")`: the same locatedness per handling unit.
- `Derivation.event_locations[k]` holds the result for every level.
Example: `data/running_example/expected/agreement.csv`; e.g. e14 at Level 1: c1 T, c3 B1 → fully located, disagreeing, eloc ⊥.

## 6. Flags (concept section "Flags (whole log)")

All at the selected level; the whole log.

| Flag | Function | Counted unit | Running example (Level 3) |
|---|---|---|---|
| F1 Partial movement | `f1_partial_movement` | events | e11, e12 |
| F2 Never located | `f2_never_located` | handling units | c4, c5 |
| F3 Mixed pickup | `f3_mixed_pickup` | events | e8 |
| F4 Location gap | `f4_location_gap` (`f4_location_gaps` lists the gaps) | handling units | c1 (e13: A2 ⇢ A1) |
| F5 Movement disagreement | `f5_movement_disagreement` | events, with kind a / b | e7 (a), e11 (b) |

"Already at the target" (F1, F3, F5 b) is ploc_k = uloc(e); ⊥ counts as a change (`flags._unchanged`).
Explore sections are not built yet.

## 7. Saved level mappings and the demo notebook

`notebooks/location_derivation.ipynb` walks through steps 1 to 5 on the running example, showing every input and output frame, and explains each function and its parameters.
It ends by saving the mapping of every level with `level_files.save_level_mappings` to `data/running_example/derived/locations_level_{k}.csv` (k = 0..3).

File format: one row per hu-event relation, sorted by hu, time, event; columns event, hu, object_type, time, activity, is_movement, is_transformation, `loc` (= loc_k), `ploc` (= ploc_k); time in ISO format, ⊥ as an empty cell.
Other notebooks read a level with `level_files.load_level_mapping(folder, k)`, which restores the column types.
`test_level_files.py` checks that the committed files match the current derivation: after a change to the derivation or the running example, rerun the notebook and commit the files.
