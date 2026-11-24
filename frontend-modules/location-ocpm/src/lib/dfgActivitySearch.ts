// The activity search of the directly-follows graph sidebar (`components/DfgSettings.tsx`): by activity name, and
// chips for object types and event categories (Nina, 2026-11-24): picked chips stack; the list holds the activities
// that match all of them (the type involved / events in the category), most such events first (`activitiesOf`). Documented in docs/pages/directly-follows-graph.md,
// "Object type and category search".
// Plain TypeScript without imports (structural types only), so that Node can run it in `tests/test_dfg_frontend.py`.

/** What the search needs of an activity of the list (a `DfgActivityOption` of the route). */
export type SearchableActivity = {
  activity: string;
  hu_events: number;
  log_events: number;
  categories?: Record<string, number>;
  object_types: { object_type: string; events: number; categories?: Record<string, number> }[];
};

/** Words that offer the chip of a category in the activity search (Nina, 2026-11-16, as chips since 2026-11-24). */
export const CATEGORY_WORDS: Record<string, string[]> = {
  to_vehicle: ["vehicles", "vehicle", "movements", "movement", "move"],
  to_storage: ["storage", "movements", "movement", "move"],
  other_movement: ["other", "movements", "movement", "move"],
  processing: ["processing", "process"],
  transformation: ["transformations", "transformation", "transforming", "transform"],
};

/**
 * Shortest query (letters, after trimming) that offers object types and categories by a part of their name or word; a
 * shorter query only offers a type whose full name it is (Nina, 2026-11-24: fewer letters are not selective enough).
 */
export const CHIP_QUERY_MIN_LENGTH = 4;

/**
 * True if an activity's name contains the search text (case-insensitive). An empty query matches every activity.
 * (Category words no longer add activities here, they offer a chip instead: `matchingCategories`; Nina, 2026-11-24.)
 *
 * @param option The activity.
 * @param query The search text.
 */
export const activityMatches = (option: SearchableActivity, query: string) =>
  option.activity.toLowerCase().includes(query.trim().toLowerCase());

/**
 * The object types whose name contains the query (case-insensitive), in the order given (the sidebar's order: types
 * with handling units first, then by objects). Below `CHIP_QUERY_MIN_LENGTH` letters only a type whose full name is
 * the query. E.g. in ["slab", "coil", "operator", "box"]: "oper" gives ["operator"], "coi" nothing, "box" ["box"].
 *
 * @param types The object types.
 * @param query The search text.
 */
export const matchingObjectTypes = (types: string[], query: string) => {
  const q = query.trim().toLowerCase();
  if (q === "") return [];
  if (q.length < CHIP_QUERY_MIN_LENGTH) return types.filter((t) => t.toLowerCase() === q);
  return types.filter((t) => t.toLowerCase().includes(q));
};

/**
 * The event categories the query names, in the order given (the toolbar's): from `CHIP_QUERY_MIN_LENGTH` letters on,
 * a category matches if the query starts one of its `CATEGORY_WORDS` or a word of its label, or one of these words
 * starts the query (e.g. "vehicles" for "vehicle"). E.g. "vehic" gives Move to vehicle, "move" all three movement
 * categories, "proc" Processing, "pro" nothing.
 *
 * @param categories The event categories (key and label, e.g. "to_vehicle", "Move to vehicle").
 * @param query The search text.
 */
export const matchingCategories = <C extends { key: string; label: string }>(categories: C[], query: string): C[] => {
  const q = query.trim().toLowerCase();
  if (q.length < CHIP_QUERY_MIN_LENGTH) return [];
  return categories.filter((c) => {
    const words = [...(CATEGORY_WORDS[c.key] ?? []), ...c.label.toLowerCase().split(/\s+/).filter((w) => w.length >= CHIP_QUERY_MIN_LENGTH)];
    return words.some((w) => w.startsWith(q) || q.startsWith(w));
  });
};

/**
 * The events of an activity in an event category, among its events with a handling unit (the badges' numbers,
 * `DfgActivityOption.categories`); 0 if none.
 *
 * @param option The activity.
 * @param category The category key (e.g. "to_vehicle").
 */
export const categoryEvents = (option: SearchableActivity, category: string) => option.categories?.[category] ?? 0;

/**
 * The activities with a positive count, most first; ties by events with a handling unit, then events in the log (both
 * descending), then name.
 *
 * @param options The activities (any order).
 * @param count The count of an activity (e.g. its events of a type).
 */
export const rankedBy = <T extends SearchableActivity>(options: T[], count: (option: T) => number): T[] =>
  options
    .filter((o) => count(o) > 0)
    .sort(
      (x, y) =>
        count(y) - count(x) ||
        y.hu_events - x.hu_events ||
        y.log_events - x.log_events ||
        (x.activity < y.activity ? -1 : x.activity > y.activity ? 1 : 0),
    );

/**
 * All activities with events in an event category (among their events with a handling unit), most such events first
 * (ties as in `rankedBy`). E.g. Processing in the running example (as in the tests): cast slab, cut, roll (1 each).
 *
 * @param options The activities (any order).
 * @param category The category key.
 */
export const activitiesOfCategory = <T extends SearchableActivity>(options: T[], category: string): T[] =>
  rankedBy(options, (o) => categoryEvents(o, category));

/**
 * The events of an activity with at least one considered object of a type (for a handling-unit type only its handling
 * units; the unfold's number, `DfgActivityTypeOption.events`); 0 if the type is not involved.
 *
 * @param option The activity.
 * @param type The object type.
 */
export const typeEvents = (option: SearchableActivity, type: string) =>
  option.object_types.find((t) => t.object_type === type)?.events ?? 0;

/**
 * All activities an object type is involved in (at least one event with a considered object of the type), most events
 * of the type first; ties as in `rankedBy`: events with a handling unit, then events in the log, then name. E.g.
 * coil in the running example: crane move (4), quality check (4), load truck (2), unload truck (2), cut (1), label (1),
 * roll (1); slab: cast slab, inspect slab, roll (1 each).
 *
 * @param options The activities (any order).
 * @param type The object type.
 */
export const activitiesOfType = <T extends SearchableActivity>(options: T[], type: string): T[] =>
  rankedBy(options, (o) => typeEvents(o, type));

/**
 * The count of an activity for picked chips (Nina, 2026-11-24: chips stack): per pair of a picked type and a picked
 * category the events of the type in the category (`DfgActivityTypeOption.categories`), with only types the events of
 * the type, with only categories the events in the category (among those with a handling unit); then the smallest of
 * these numbers. The route has no numbers for events shared by two types or two categories, so for these the smallest
 * one is used (at most that many events can have both). 0 if the activity misses one of the chips. E.g. coil +
 * Processing: coil's processing events; coil + slab: min(coil's, slab's events).
 *
 * @param option The activity.
 * @param types Picked object types.
 * @param categories Picked category keys.
 */
export const chipCount = (option: SearchableActivity, types: string[], categories: string[]) => {
  const counts: number[] = [];
  if (types.length === 0) for (const c of categories) counts.push(categoryEvents(option, c));
  for (const t of types) {
    const entry = option.object_types.find((o) => o.object_type === t);
    if (categories.length === 0) counts.push(entry?.events ?? 0);
    for (const c of categories) counts.push(entry?.categories?.[c] ?? 0);
  }
  return counts.length > 0 ? Math.min(...counts) : option.hu_events;
};

/**
 * The activities that match all picked chips (`chipCount` > 0), most first (ties as in `rankedBy`). Without chips:
 * all activities as given. E.g. running example (as in the tests): coil + Processing: cut, roll (1 each); coil + slab:
 * roll (1).
 *
 * @param options The activities (any order).
 * @param types Picked object types.
 * @param categories Picked category keys.
 */
export const activitiesOf = <T extends SearchableActivity>(options: T[], types: string[], categories: string[]): T[] =>
  types.length === 0 && categories.length === 0 ? options : rankedBy(options, (o) => chipCount(o, types, categories));
