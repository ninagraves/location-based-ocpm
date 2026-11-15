// The graph the page draws: the backend's graph (all arcs of the included traces) with the arc settings applied in
// the browser (lib/dfgArcs.ts). Documented in docs/pages/directly-follows-graph.md.
import type { DfgArc, DirectlyFollowsGraph } from "../api/locationBasedOcpm";
import { type ArcSettings, arcKey, filterArcs } from "./dfgArcs";

/** Number of arcs per object type. */
const perType = (arcs: { object_type: string }[]) => {
  const counts = new Map<string, number>();
  for (const a of arcs) counts.set(a.object_type, (counts.get(a.object_type) ?? 0) + 1);
  return counts;
};

/**
 * Apply the arc settings to the backend's graph: the shown arcs (with `connecting`), the activities they touch, and
 * per selected object type the arc threshold and count used and the numbers of arcs (all, left by the threshold,
 * shown); `arc_count_max` (most arcs of one type left by the threshold) and `removed_arcs` (with their counts).
 *
 * @param graph The backend's graph (`arcs` = all arcs of the included traces, with `rank`).
 * @param settings The arc settings (`arcSettings` of the page state).
 * @returns A graph of the same shape, as drawn.
 */
export const applyArcSettings = (graph: DirectlyFollowsGraph, settings: ArcSettings): DirectlyFollowsGraph => {
  const { shown, threshold } = filterArcs(graph.arcs, settings);
  const used = new Set(shown.flatMap((a) => [a.source, a.target]).filter((x): x is string => x != null));
  const all = perType(graph.arcs);
  const left = perType(threshold);
  const drawn = perType(shown);
  const removed = new Set(settings.removed.map(arcKey));
  return {
    ...graph,
    arcs: shown as DfgArc[],
    activities: graph.activities.filter((a) => used.has(a.activity)),
    object_types: graph.object_types.map((t) =>
      t.selected
        ? {
            ...t,
            arc_threshold: settings.threshold(t.object_type),
            arc_count: settings.count(t.object_type),
            arcs: all.get(t.object_type) ?? 0,
            threshold_arcs: left.get(t.object_type) ?? 0,
            shown_arcs: drawn.get(t.object_type) ?? 0,
          }
        : t,
    ),
    arc_count_max: Math.max(0, ...left.values()),
    removed_arcs: graph.arcs.filter((a) => removed.has(arcKey(a))),
  };
};
