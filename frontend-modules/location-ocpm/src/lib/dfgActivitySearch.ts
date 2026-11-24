// The activity search of the directly-follows graph sidebar (`components/DfgSettings.tsx`): by activity name, by
// category words (Nina, 2026-11-16) and by object type (Nina, 2026-11-24: all activities an object type is involved
// in, most events of the type first). Documented in docs/pages/directly-follows-graph.md, "Activity search".
// Plain TypeScript without imports (structural types only), so that Node can run it in `tests/test_dfg_frontend.py`.

/** What the search needs of an activity of the list (a `DfgActivityOption` of the route). */
export type SearchableActivity = {
  activity: string;
  hu_events: number;
  log_events: number;
  categories?: Record<string, number>;
  object_types: { object_type: string; events: number; categories?: Record<string, number> }[];
};

/** Words that find the activities with events of a category in the activity search (Nina, 2026-11-16). */
export const CATEGORY_WORDS: Record<string, string[]> = {
  to_vehicle: ["vehicles", "vehicle", "movements", "movement", "move"],
  to_storage: ["storage", "movements", "movement", "move"],
  other_movement: ["other", "movements", "movement", "move"],
  processing: ["processing", "process"],
  transformation: ["transformations", "transformation", "transforming", "transform"],
};

/** Shortest query (letters, after trimming) that suggests object types (one letter would match nearly every type). */
export const TYPE_QUERY_MIN_LENGTH = 2;

/**
 * True if an activity matches the search: its name contains the query, or the query (at least 3 letters) starts one of
 * the words of a category the activity has events of (or one of these words starts the query). E.g. "vehic" finds
 * "load truck" when loads go to a vehicle. An empty query matches every activity.
 *
 * @param option The activity.
 * @param query The search text.
 */
export const activityMatches = (option: SearchableActivity, query: string) => {
  const q = query.trim().toLowerCase();
  if (option.activity.toLowerCase().includes(q)) return true;
  if (q.length < 3) return false;
  return Object.entries(CATEGORY_WORDS).some(
    ([k, words]) => (option.categories?.[k] ?? 0) > 0 && words.some((w) => w.startsWith(q) || q.startsWith(w)),
  );
};

/**
 * The object types whose name contains the query (case-insensitive), in the order given (the sidebar's order: types
 * with handling units first, then by objects). Nothing below `TYPE_QUERY_MIN_LENGTH` letters. E.g. "co" in
 * ["slab", "coil", "operator"] gives ["coil"].
 *
 * @param types The object types.
 * @param query The search text.
 */
export const matchingObjectTypes = (types: string[], query: string) => {
  const q = query.trim().toLowerCase();
  if (q.length < TYPE_QUERY_MIN_LENGTH) return [];
  return types.filter((t) => t.toLowerCase().includes(q));
};

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
 * of the type first; ties by events with a handling unit, then events in the log (both descending), then name. E.g.
 * coil in the running example: crane move (4), quality check (4), load truck (2), unload truck (2), cut (1), label (1),
 * roll (1); slab: cast slab, inspect slab, roll (1 each).
 *
 * @param options The activities (any order).
 * @param type The object type.
 */
export const activitiesOfType = <T extends SearchableActivity>(options: T[], type: string): T[] =>
  options
    .filter((o) => typeEvents(o, type) > 0)
    .sort(
      (x, y) =>
        typeEvents(y, type) - typeEvents(x, type) ||
        y.hu_events - x.hu_events ||
        y.log_events - x.log_events ||
        (x.activity < y.activity ? -1 : x.activity > y.activity ? 1 : 0),
    );
