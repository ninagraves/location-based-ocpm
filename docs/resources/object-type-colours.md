# Object type colours

Every object type, above all every handling-unit type, has one colour on all pages, charts and downloads of the module (Nina, 2026-11-23).
Before, the directly-follows graph, the instance page and the overview bar charts each ranked their own colours, so the same type could be petrol on one page and turquoise on another.

## What it shows
One colour per object type of the log:
- **Handling-unit types** get Nina's signature colours (`SIGNATURE` in `lib/palette.ts`: petrol, pink, turquoise, blue, orange), then further categorical colours.
- **All other object types** get the remaining categorical colours (never a signature colour, nor the categorical orange, which is too close to the signature orange).
- On the **directly-follows graph** the other types are paler (opacity `FADED_ALPHA` = 0.55), so the handling-unit types stand out (Nina, 2026-11-15); everywhere else they are opaque, in the same hue.
- **Downloads** (always on white) use the light-scheme colours, whatever the page's scheme.

## How it is calculated
1. Backend, `object_type_order(objects, handling_units)` in `object_type_routes.py` (route `GET /{ocel_id}/object-types`, `getObjectTypes`): every object type of the log with its number of objects (for a type with handling units: its handling units) and whether it contains handling units, most first, ties by name. It reuses `dfg.graph.type_overview`, the order the directly-follows graph already used. Cached per derivation key (`CACHE_SIZE` = 4).
2. Frontend, `objectTypeColourMap(types, scheme, fadeOther)` in `lib/objectTypeColours.ts`: splits the order into handling-unit types and other types (each keeps its order) and calls `emphasisColourMap(huTypes, otherTypes, scheme, fade)` in `lib/palette.ts`.
3. Frontend, `useObjectTypeColours(ocelId, fadeOther)`: fetches the order and returns `colours` (page scheme), `exportColours` (light scheme), `huTypes` and `loaded`. Every component that colours object types gets its colours from this hook or from its page, which calls it once.

The order belongs to the log and its current derivation, not to a page or a chart, so a type keeps its colour when a page's selection, filter or chart setting changes.
It can only change when the derivation changes (a new configuration, the settings bar's level, or an Ocelescope filter that changes the handling units), and then on every page at once.

## Example
Running example (Level 3): order coil (5 handling units), slab (1 handling unit), both handling-unit types.
Every page draws coil petrol (#006165) and slab pink (#CE108A): the directly-follows graph, the lineage, object graph and object traces of the instance page, and the overview bar charts "by object type".
Before, the instance page drew coil turquoise (#0098A1) and slab orange (#d98b09).

Worked example with another type: handling-unit types pallet (3 handling units) and box (1), other type order (4 objects).
1. `object_type_order` gives order (4), pallet (3), box (1); handling-unit types pallet, box.
2. `objectTypeColourMap` calls `emphasisColourMap(["pallet", "box"], ["order"], "light", fade)`.
3. pallet #006165 (petrol), box #CE108A (pink); order #5291cc (the first categorical colour that is no signature colour, #d98b09 skipped), on the directly-follows graph #5291cc8c (paler).

## Where it is used
| Page | Element | Colours |
|---|---|---|
| Overview | bar charts with "by object type" (Activities, Locations) | segments of an object type in its colour; "other", "–" and "[several …]" stay grey |
| Overview | "Handling unit types" with "by none" | each bar in its type's colour ("–" grey) |
| Directly-follows graph | arcs, start and end nodes, circles, object-type legend, downloads | `useObjectTypeColours(ocelId, true)` (other types paler) |
| Instances | lineage, object graph, object traces (chevron circles, legend) | `useObjectTypeColours(ocelId)`, handed to the charts by `routes/Instances.tsx` |

Not coloured by object type (status colours): the data overview charts, the HU profile table, the timeline (produced / consumed).
Notebook figures (`visits/trace_figure.py`, `lineage` `to_dot`) use the Python copy of the palette and are not covered yet.

## Filtering and settings
Page filters do not change the colours (the order is log-wide). No settings.

## How to change it
- Other colours for the handling-unit types: `SIGNATURE` in `lib/palette.ts`.
- Other order (e.g. by events instead of objects): `object_type_order` (backend); every page follows.
- Other types opaque on the directly-follows graph too: `useObjectTypeColours(ocelId, true)` in `routes/DirectlyFollowsGraph.tsx` → `false`.
- A new chart that colours object types: call `useObjectTypeColours(ocelId)` (or take `colours` from its page) and look types up in `colours`; never rank object types per chart.

## Alternatives
- **Rank per chart** (as before): best use of the first colours in each chart, but a type changed colour between pages and with filters.
- **Order alphabetically**: stable across derivations, but the most important type need not get petrol.
- **Colours computed in the backend**: would duplicate `palette.ts` in Python; the backend only sends the order.
