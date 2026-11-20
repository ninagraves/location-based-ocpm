// Steps 4 and 5 of the directly-follows graph, in the browser so that the arc sliders, the arc removal (double click) and
// "Stay connected" react without a request (Nina, 2026-11-15): arc threshold, arc count, arcs removed by hand and the
// connectivity repair. The backend sends all arcs of the included traces (projected, variant-filtered), each with its
// `rank` in the arc ranking of its type; these functions mirror `dfg/arcs.py` and `dfg/connectivity.py` exactly (the
// Python versions stay for the notebook and the tests; `tests/test_dfg_frontend.py` checks that both agree).
// Documented in docs/pages/directly-follows-graph.md. Plain TypeScript without imports, so that Node can run it.

/** An arc as sent by the backend (null source / target = start / end node of the object type). */
export type BaseArc = {
  object_type: string;
  source?: string | null;
  target?: string | null;
  count: number;
  objects: number;
  /** 1-based position in the ranking of its type: objects, traversals (descending), first occurrence, source, target. */
  rank?: number;
  connecting?: boolean;
};

/** An arc, identified by its object type and endpoints. */
export type ArcId = { object_type: string; source: string | null; target: string | null };

/** The arc settings of the page. */
export type ArcSettings = {
  /** Arc threshold in percent (0 to 100) of an object type. */
  threshold: (objectType: string) => number;
  /** Arcs (display) of an object type on its own; null = no limit of its own (the type then belongs to `total`). */
  count: (objectType: string) => number | null;
  /** Arcs (display) in "general" mode: one limit for the arcs of all types without an own count together; null = none. */
  total?: number | null;
  /** Arcs removed by hand. */
  removed: ArcId[];
  /** Every shown arc lies on a start-to-end path. */
  stayConnected: boolean;
};

/** Key of an arc, e.g. "pallet␞pick␞pack" (start / end node: empty). */
export const arcKey = (a: { object_type: string; source?: string | null; target?: string | null }) =>
  `${a.object_type}␞${a.source ?? ""}␞${a.target ?? ""}`;

/** The arcs grouped by object type, each group in the order of `rank`. */
const byType = <T extends BaseArc>(arcs: T[]): Map<string, T[]> => {
  const groups = new Map<string, T[]>();
  for (const a of arcs) {
    const group = groups.get(a.object_type) ?? [];
    group.push(a);
    groups.set(a.object_type, group);
  }
  for (const group of groups.values()) group.sort((x, y) => (x.rank ?? 0) - (y.rank ?? 0));
  return groups;
};

/**
 * Arc threshold (`arcs.arc_share_filter`, as Ocelescope's DFG filter): per type, all arcs (start and end arcs included)
 * ranked by objects, then traversals; the first ceil(alpha / 100 * n) are kept, with every arc tied with the last one.
 * Example: 8 arcs (8, 8, 8, 8, 8, 5, 3, 3 objects) at 50 %: ceil(4) = 4, the fifth is tied with the fourth: 5 arcs.
 *
 * @param arcs All arcs of the included traces.
 * @param threshold Arc threshold in percent per object type.
 * @returns The kept arcs, in the order of `arcs`.
 */
export const arcShareFilter = <T extends BaseArc>(arcs: T[], threshold: (objectType: string) => number): T[] => {
  const kept = new Set<T>();
  for (const [type, group] of byType(arcs)) {
    const sorted = [...group].sort((x, y) => y.objects - x.objects || y.count - x.count);
    const limit = Math.round(threshold(type) * sorted.length * 1e6) / 1e6;
    let minRank = 1;
    sorted.forEach((a, i) => {
      // Ties share the smallest rank ("min"); (rank - 1) * 100 < alpha * n  <=>  rank <= ceil(alpha / 100 * n).
      if (i > 0 && (a.objects !== sorted[i - 1].objects || a.count !== sorted[i - 1].count)) minRank = i + 1;
      if ((minRank - 1) * 100 < limit) kept.add(a);
    });
  }
  return arcs.filter((a) => kept.has(a));
};

/**
 * Arcs (display) (`arcs.arc_count_filter`, like the slider of Ocelescope's DFG viewer): per type the first N arcs by
 * `rank` (exactly N; ties are broken by the ranking). With `total` ("general" mode, Nina 2026-11-16), the types without
 * an own count share one limit: the first `total` of their arcs together, by objects, traversals (both descending),
 * position in the ranking of their type, then object type.
 * Example: coil arcs with 4, 3, 2 objects and slab arcs with 1, 1 object, total 3: the three coil arcs.
 *
 * @param arcs Arcs (after the arc threshold).
 * @param count Arc count per object type; null = no limit of its own.
 * @param total Limit shared by the types without a count; null or undefined = all their arcs.
 * @returns The kept arcs, in the order of `arcs`.
 */
export const arcCountFilter = <T extends BaseArc>(
  arcs: T[],
  count: (objectType: string) => number | null,
  total?: number | null,
): T[] => {
  const kept = new Set<T>();
  const pooled: { arc: T; position: number }[] = [];
  for (const [type, group] of byType(arcs)) {
    const n = count(type);
    if (n != null) for (const a of group.slice(0, Math.max(0, n))) kept.add(a);
    else group.forEach((a, i) => pooled.push({ arc: a, position: i + 1 }));
  }
  pooled.sort(
    (x, y) =>
      y.arc.objects - x.arc.objects ||
      y.arc.count - x.arc.count ||
      x.position - y.position ||
      (x.arc.object_type < y.arc.object_type ? -1 : x.arc.object_type > y.arc.object_type ? 1 : 0),
  );
  for (const p of total == null ? pooled : pooled.slice(0, Math.max(0, total))) kept.add(p.arc);
  return arcs.filter((a) => kept.has(a));
};

/**
 * The smallest whole Arcs (projection) value at which the arc threshold keeps at least one arc of a type that touches an
 * activity (Nina, 2026-11-16: shown for the activities on the included traces that are not in the graph): for the
 * best-ranked such arc with tie rank r ("min") among n arcs, floor(100 (r - 1) / n) + 1, at most 100.
 * Example: 8 arcs, the activity's best arc has tie rank 7: floor(75) + 1 = 76 %.
 * With `decimals` (Nina, 2026-11-18: 3 in the unfold of the activity list) the smallest value with that many decimals:
 * the share rounded down to them plus one step, e.g. 3 arcs, tie rank 3: 66.666… -> 66.667 % (whole: 67 %).
 *
 * @param arcs All arcs of the included traces.
 * @param decimals Decimals of the values (0 = whole percentages, as the summary shows them).
 * @returns Object type -> activity -> needed percentage.
 */
export const neededArcThresholds = (arcs: BaseArc[], decimals = 0): Map<string, Map<string, number>> => {
  const step = 10 ** decimals;
  const result = new Map<string, Map<string, number>>();
  for (const [type, group] of byType(arcs)) {
    const sorted = [...group].sort((x, y) => y.objects - x.objects || y.count - x.count);
    const needed = new Map<string, number>();
    let minRank = 1;
    sorted.forEach((a, i) => {
      if (i > 0 && (a.objects !== sorted[i - 1].objects || a.count !== sorted[i - 1].count)) minRank = i + 1;
      const share = ((minRank - 1) * 100 * step) / sorted.length;
      const value = Math.min(100, Math.round(((Math.floor(Math.round(share * 1e6) / 1e6) + 1) / step) * step) / step);
      for (const activity of [a.source, a.target]) {
        if (activity != null && !needed.has(activity)) needed.set(activity, value);
      }
    });
    result.set(type, needed);
  }
  return result;
};

/** Removes the arcs removed by hand (`arcs.remove_arcs`). */
export const removeArcs = <T extends BaseArc>(arcs: T[], removed: ArcId[]): T[] => {
  const keys = new Set(removed.map(arcKey));
  return arcs.filter((a) => !keys.has(arcKey(a)));
};

const START = "\u0000start";
const END = "\u0000end";
/** Graph nodes of an arc: the start / end sentinel for a null source / target. */
const endpoints = (a: BaseArc): [string, string] => [a.source ?? START, a.target ?? END];

/** Nodes reachable from `from` along the edges (forward), or reaching it (backward). */
const reach = (edges: [string, string][], from: string, backward = false): Set<string> => {
  const next = new Map<string, string[]>();
  for (const [u, v] of edges) {
    const [a, b] = backward ? [v, u] : [u, v];
    next.set(a, [...(next.get(a) ?? []), b]);
  }
  const seen = new Set([from]);
  const stack = [from];
  while (stack.length) {
    for (const n of next.get(stack.pop() as string) ?? []) {
      if (!seen.has(n)) {
        seen.add(n);
        stack.push(n);
      }
    }
  }
  return seen;
};

/** The arcs that lie on a path from the start to the end node of their type (`connectivity.on_start_end_paths`). */
export const onStartEndPaths = <T extends BaseArc>(arcs: T[]): T[] => {
  const kept = new Set<T>();
  for (const group of byType(arcs).values()) {
    const edges = group.map(endpoints);
    const reachable = reach(edges, START);
    const reaching = reach(edges, END, true);
    group.forEach((a, i) => reachable.has(edges[i][0]) && reaching.has(edges[i][1]) && kept.add(a));
  }
  return arcs.filter((a) => kept.has(a));
};

/**
 * "Stay connected" (`connectivity.stay_connected`, the repair of Ocelescope's DFG filter): per type, starting from the
 * base arcs that lie on a start-to-end path, every arc not in `kept` is taken out, least frequent first (highest rank
 * first), unless this cuts an activity of the kept arcs off from the start or the end node.
 *
 * @param base All arcs of the included traces without the arcs removed by hand.
 * @param kept The arcs left by the arc threshold, the arc count and the hand removals.
 * @returns The shown arcs, ordered by type and rank, with `connecting` = true for the added ones.
 */
export const stayConnected = <T extends BaseArc>(base: T[], kept: T[]): (T & { connecting: boolean })[] => {
  const keptKeys = new Set(kept.map(arcKey));
  const result: (T & { connecting: boolean })[] = [];
  for (const group of byType(onStartEndPaths(base)).values()) {
    const rows = group.map((a) => ({ ...a, connecting: !keptKeys.has(arcKey(a)) }));
    const required = new Set(rows.filter((a) => !a.connecting).flatMap(endpoints));
    const present = new Set(rows.map(arcKey));
    for (const a of [...rows].reverse()) {
      if (!a.connecting) continue;
      present.delete(arcKey(a));
      const edges = rows.filter((r) => present.has(arcKey(r))).map(endpoints);
      const reachable = reach(edges, START);
      const reaching = reach(edges, END, true);
      if (![...required].every((n) => reachable.has(n) && reaching.has(n))) present.add(arcKey(a));
    }
    result.push(...rows.filter((r) => present.has(arcKey(r))));
  }
  return result;
};

/**
 * Steps 4 and 5 together: arc threshold, arc count, hand removals, then (if on) "Stay connected".
 *
 * @param arcs All arcs of the included traces (from the backend, with `rank`).
 * @param settings The arc settings.
 * @returns `shown` (with `connecting`) and `threshold`, the arcs left by the arc threshold (what the arc count counts).
 */
export const filterArcs = <T extends BaseArc>(arcs: T[], settings: ArcSettings) => {
  const threshold = arcShareFilter(arcs, settings.threshold);
  const kept = removeArcs(arcCountFilter(threshold, settings.count, settings.total), settings.removed);
  const shown = settings.stayConnected
    ? stayConnected(removeArcs(arcs, settings.removed), kept)
    : kept.map((a) => ({ ...a, connecting: false }));
  return { shown, threshold };
};
