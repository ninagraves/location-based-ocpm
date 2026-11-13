# Transformation inputs (T, cons, prod)

Concept: `overview/concepts/Transformations.md`, options 1-6 for deriving the transformation events T and the consumed and produced handling units cons(e), prod(e), plus AS-T1 to AS-T4 (outside this repo).
Demo: `notebooks/transformations.ipynb`. Used by: the lineage (`lineage.md`, not yet integrated in the module) and loc^3 (`location-derivation.md`, through T).

## What it does
Two configuration inputs work together:
- "Transformation events" (`DerivationConfig.transformation_events`, optional): the candidates, as before (activities, event attribute, e2o qualifiers, table).
- "Consumed and produced handling units" (`DerivationConfig.transformation_roles`, optional): one of the six options below.

| Option (`option`) | Config model | T | Needs |
|---|---|---|---|
| 1 `qualifiers` | `RolesFromQualifiers` | derived from the roles; the candidates are ignored (notice "transformation_events_ignored") | `consumed_qualifiers`, `produced_qualifiers` (e2o) |
| 2 `table` | `RolesFromTable` | the candidates, or the table's events if none are given | `table`, `event_column`, `object_column`, `role_column`, `consumed_values` (default `["consumed"]`), `produced_values` (default `["produced"]`) |
| 3 `parents` | `RolesFromParents` | the candidates (required) | o2o `qualifiers`, `direction` `child_of` (oid_1 is the child) or `parent_of` |
| 4 `object_sets` | `RolesFromObjectSets` | the candidates (required) | `produced`, `consumed`: object attribute values (`ObjectAttributeValues`) or a table (`ObjectTable`); `consumption` `final` or `partial` |
| 5 `first_last` | `RolesFromFirstLast` | the candidates (required) | nothing; the default when only candidates are given |
| 6 `frequency` | `RolesFromFrequency` | derived; the candidates are ignored | `threshold` τ in [0, 1], default 0.5 |

Neither input: T = ∅ and no roles.
An option that needs the candidates without them is a validation error of the configuration (`DerivationConfig._transformation_events_needed`); the form does not allow it ("Apply" lists the missing entry).

## How it is calculated
`inputs.resolve_transformation_inputs` reads what the option needs from the log (e2o qualifiers, o2o relations restricted to handling units, object attribute values, tables) and calls `transformations.resolve_transformations`:
1. `first_last_events(e2hu, processing)`: e^first(hu) and e^last(hu); ties at one timestamp prefer processing operations, then the smaller event id (≺ of the concept).
   Only the explicitly selected processing operations count, not "+ all transformation events", because option 6 would otherwise depend on its own result (agreed with Nina, 2026-11-13).
2. The option's function: `roles_from_qualifiers`, `roles_from_table`, `roles_from_parents`, `roles_from_object_sets`, `roles_from_first_last`, `roles_from_frequency` (with `activity_frequencies`).
3. `apply_as_t1`: candidates without any role are dropped (notice "AS-T1"), roles of non-candidates are dropped.
4. `check_assumptions`: violations of AS-T2, AS-T3, AS-T4 are notices (non-blocking), each with the events concerned (first `MAX_IDS` = 50).

Table rules (option 2): rows with unknown events or objects are dropped (notice "unknown_ids_dropped"); other role values are ignored (notice "other_role_values_ignored"); a value listed as both consumed and produced, or missing columns, raise an error.

Output: `ResolvedInputs.roles` and `Derivation.roles`, columns event, hu, role (`consumed`/`produced`); a hu consumed and produced at one event has two rows. T is the column `is_transformation` of the relations.

## Example (running example)
The running example configuration has only candidates (activities cast slab, roll, cut), so option 5 applies: T = {e1, e3, e15}, roles (e1, s1, produced), (e3, s1, consumed), (e3, c1, produced), (e3, c2, produced), (e15, c2, consumed), (e15, c4, produced); no notices.
Options 1 (qualifiers `consumed`/`produced`), 2 (`inputs/transformation_roles.csv`), 3 (parents c1, c2 → s1; c4 → c2) and 4 (produced s1, c1, c2, c4; consumed s1, c2) give the same.
Option 2 with e4 as additional candidate drops e4 (AS-T1).
Option 6 with τ = 0.5 also makes "quality check" consuming (last event of 4 of 5 coils), so T = {e1, e3, e14, e16, e17}.
Tests: `tests/test_transformations.py`.

## Filtering and settings
Resolved once per configuration, before any page filter. Defaults: option 5 if only candidates are given, τ = 0.5, consumption `final`, role values `consumed`/`produced`.

## Configuration form
`ConfigForm.tsx`: sub-section "Consumed and produced handling units" inside "Transformation events" (`RolesFields`, `ObjectSetFields`, draft `RolesDraft`, `rolesToConfig`, `INFO.roles`).
If the option derives T (`DERIVES_T`), the transformation-events pickers are replaced by "Determined by the consumed and produced handling units below." and `toConfig` sends `transformation_events: null`.
`NEEDS_T` options add "Transformation events" to the missing entries when no candidates are chosen.

## How to change
- New option: model in `config.py`, add it to `TransformationRolesInput` and to `NEEDS_TRANSFORMATION_EVENTS` or `DERIVES_TRANSFORMATION_EVENTS`; function in `transformations.py`, branch in `resolve_transformations`; what it reads from the log in `resolve_transformation_inputs`; test; regenerate the API client; then `RolesDraft`, `rolesToConfig`, `fromConfig`, `missingEntries` and the select in `RolesFields`.
- Tie-break: `first_last_events` (sort order) and which processing operations are passed in `resolve_transformation_inputs`.
- AS-T2 to AS-T4 as blocking errors instead of notices: return them as errors in `resolve_inputs`.

## Alternatives considered
- Using P including "+ all transformation events" for the tie-break: circular for option 6, and inconsistent between options; rejected.
- AS-T2 to AS-T4 violations as flags of the overview page: postponed; notices first.
