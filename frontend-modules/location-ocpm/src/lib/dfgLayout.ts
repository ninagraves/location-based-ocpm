// Layout of the directly-follows graph with ELK (layered). Documented in
// docs/pages/directly-follows-graph.md, section "Layout".
import ELK, { type ElkExtendedEdge, type ElkNode } from "elkjs/lib/elk.bundled.js";
import type { DirectlyFollowsGraph } from "../api/locationBasedOcpm";

export type Direction = "RIGHT" | "DOWN";
export type ArcLabel = "count" | "objects";
type Point = { x: number; y: number };

/** Sizes of the drawing, in pixels. */
export const SIZES = {
  /** Font size of activity names. */
  nameFont: 12,
  /** Line height of activity names. */
  nameLine: 14,
  /** Activity names wrap at this width (never cut). */
  maxNameWidth: 150,
  /** Font size of the frequency in an activity node. */
  frequencyFont: 10,
  /** Diameter of an object-type circle on an activity node. */
  circle: 7,
  /** Gap between object-type circles. */
  circleGap: 2,
  /** Horizontal and vertical padding inside an activity node (tight, Nina 2026-11-14). */
  padX: 5,
  padY: 2,
  /** Diameter of start and end nodes. */
  terminal: 18,
  /** Font size of the object-type name below start and end nodes, and of arc labels. */
  smallFont: 10,
} as const;

/** ELK options: Ocelescope's DIRECTED_ELK_GRAPH_LAYOUT (ocelescope/visualization/default/graph/layouting.py), with the direction as a setting. */
export const ELK_OPTIONS: Record<string, string> = {
  "elk.algorithm": "layered",
  "elk.edgeRouting": "SPLINES",
  "elk.separateConnectedComponents": "true",
  "elk.spacing.nodeNode": "48",
  "elk.spacing.edgeNode": "24",
  "elk.spacing.edgeEdge": "16",
  "elk.spacing.componentComponent": "96",
  "elk.layered.cycleBreaking.strategy": "GREEDY",
  "elk.layered.layering.strategy": "NETWORK_SIMPLEX",
  "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
  "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
  "elk.layered.nodePlacement.favorStraightEdges": "true",
  "elk.layered.spacing.nodeNodeBetweenLayers": "90",
  "elk.layered.spacing.edgeNodeBetweenLayers": "30",
  "elk.layered.spacing.edgeEdgeBetweenLayers": "14",
  "elk.layered.thoroughness": "15",
  "elk.edgeLabels.placement": "CENTER",
};

/**
 * Spacing of the compact layout (setting "Compact layout"): little white space, e.g. to export the whole graph
 * as a figure for a paper. Replaces the spacing options of `ELK_OPTIONS`.
 */
export const COMPACT_OPTIONS: Record<string, string> = {
  "elk.spacing.nodeNode": "12",
  "elk.spacing.edgeNode": "8",
  "elk.spacing.edgeEdge": "5",
  "elk.spacing.componentComponent": "24",
  "elk.layered.spacing.nodeNodeBetweenLayers": "28",
  "elk.layered.spacing.edgeNodeBetweenLayers": "10",
  "elk.layered.spacing.edgeEdgeBetweenLayers": "5",
};

let probe: HTMLSpanElement | null = null;

/**
 * Width of a text in pixels as the browser renders it (an invisible span in the page, so the same font as the
 * nodes; a canvas measurement can differ from the rendered text). Outside the browser: approximated by the
 * number of characters.
 */
export const textWidth = (text: string, fontSize: number, weight = 400): number => {
  if (typeof document === "undefined") return text.length * fontSize * 0.6;
  if (!probe) {
    probe = document.createElement("span");
    Object.assign(probe.style, { position: "absolute", visibility: "hidden", whiteSpace: "pre", left: "-9999px", top: "0" });
    document.body.appendChild(probe);
  }
  probe.style.fontSize = `${fontSize}px`;
  probe.style.fontWeight = String(weight);
  probe.textContent = text;
  return probe.getBoundingClientRect().width;
};

/**
 * Break an activity name into lines of at most `maxWidth` pixels, at spaces (a single word longer than
 * that gets a line of its own). The name is never cut.
 */
export const wrapName = (name: string, maxWidth: number = SIZES.maxNameWidth): string[] => {
  const lines: string[] = [];
  let line = "";
  for (const word of name.split(/\s+/)) {
    const candidate = line ? `${line} ${word}` : word;
    if (line && textWidth(candidate, SIZES.nameFont, 600) > maxWidth) {
      lines.push(line);
      line = word;
    } else line = candidate;
  }
  if (line) lines.push(line);
  return lines.length ? lines : [name];
};

/** Id of the start / end node of an object type. */
export const startId = (objectType: string) => `start:${objectType}`;
export const endId = (objectType: string) => `end:${objectType}`;
const activityId = (activity: string) => `activity:${activity}`;

/** What an activity node shows, with its size. */
export type ActivityNodeData = {
  kind: "activity";
  activity: string;
  lines: string[];
  events: number;
  logEvents: number;
  /** Object types involved in the counted events: selected ones (drawn as arcs) and the others (circles). */
  involved: { objectType: string; events: number; objects: number; selected: boolean }[];
  width: number;
  height: number;
};

/** A start or end node of an object type. */
export type TerminalNodeData = { kind: "start" | "end"; objectType: string; width: number; height: number };

export type LaidOutNode = { id: string; x: number; y: number; data: ActivityNodeData | TerminalNodeData };
export type LaidOutArc = {
  id: string;
  source: string;
  target: string;
  objectType: string;
  count: number;
  objects: number;
  label: string;
  path: string;
  labelPosition: Point | null;
};
export type Layout = { nodes: LaidOutNode[]; arcs: LaidOutArc[] };

/** Size of an activity node: wrapped name, frequency line, and a row of circles for the unselected types. */
const activitySize = (lines: string[], events: number, circles: number) => {
  const nameWidth = Math.max(...lines.map((l) => textWidth(l, SIZES.nameFont, 600)));
  const frequencyWidth = textWidth(events.toLocaleString("en-GB"), SIZES.frequencyFont, 600);
  const circlesWidth = circles * SIZES.circle + Math.max(0, circles - 1) * SIZES.circleGap;
  // + 4: the node's border (1.5 px each side) and rounding.
  const width = Math.ceil(Math.max(nameWidth, frequencyWidth, circlesWidth, 24) + 2 * SIZES.padX + 4);
  const height = Math.ceil(
    2 * SIZES.padY + 3 + lines.length * SIZES.nameLine + SIZES.frequencyFont + 3 + (circles ? SIZES.circle + 3 : 0),
  );
  return { width, height };
};

/** SVG path of an ELK edge section; with spline routing, ELK's bend points are cubic Bézier control points. */
const sectionPath = (section: NonNullable<ElkExtendedEdge["sections"]>[number]): string => {
  const points: Point[] = [section.startPoint, ...(section.bendPoints ?? []), section.endPoint];
  const control = [section.startPoint, ...(section.bendPoints ?? [])];
  if ((control.length - 1) % 3 === 2) control.push(section.endPoint);
  if (control.length >= 4 && (control.length - 1) % 3 === 0) {
    let path = `M ${control[0].x},${control[0].y}`;
    for (let i = 1; i + 2 < control.length; i += 3)
      path += ` C ${control[i].x},${control[i].y} ${control[i + 1].x},${control[i + 1].y} ${control[i + 2].x},${control[i + 2].y}`;
    return path;
  }
  return points.map((p, i) => `${i ? "L" : "M"} ${p.x},${p.y}`).join(" ");
};

const elk = new ELK();

/**
 * Lay out the graph with ELK: one node per shown activity, a start and an end node per selected object type
 * that has a kept start / end arc, one edge per kept arc (labelled with its count or its objects).
 * Start and end nodes get no layer constraint, so ELK places them next to their first / last activities
 * instead of all in the first / last layer.
 * `compact` replaces the spacing by `COMPACT_OPTIONS`.
 */
export const layoutGraph = async (
  graph: DirectlyFollowsGraph,
  direction: Direction,
  arcLabel: ArcLabel,
  compact = false,
): Promise<Layout> => {
  const selected = new Set(graph.object_types.filter((t) => t.selected).map((t) => t.object_type));
  const data = new Map<string, ActivityNodeData | TerminalNodeData>();

  for (const a of graph.activities) {
    const lines = wrapName(a.activity);
    const involved = a.object_types.map((t) => ({
      objectType: t.object_type,
      events: t.events,
      objects: t.objects,
      selected: selected.has(t.object_type),
    }));
    const circles = involved.filter((t) => !t.selected).length;
    data.set(activityId(a.activity), { kind: "activity", activity: a.activity, lines, events: a.events, logEvents: a.log_events, involved, ...activitySize(lines, a.events, circles) });
  }
  const terminal = (kind: "start" | "end", objectType: string) => {
    const id = kind === "start" ? startId(objectType) : endId(objectType);
    if (!data.has(id)) data.set(id, { kind, objectType, width: SIZES.terminal, height: SIZES.terminal });
    return id;
  };

  const arcs = graph.arcs.map((arc, index) => {
    const source = arc.source == null ? terminal("start", arc.object_type) : activityId(arc.source);
    const target = arc.target == null ? terminal("end", arc.object_type) : activityId(arc.target);
    const label = (arcLabel === "count" ? arc.count : arc.objects).toLocaleString("en-GB");
    return { id: `arc:${index}`, source, target, arc, label };
  });

  const root: ElkNode = {
    id: "root",
    layoutOptions: { ...ELK_OPTIONS, ...(compact ? COMPACT_OPTIONS : {}), "elk.direction": direction },
    children: [...data.entries()].map(([id, d]) => ({
      id,
      width: d.width,
      height: d.height,
      ...(d.kind === "activity"
        ? {}
        : {
            labels: [{ text: d.objectType, width: textWidth(d.objectType, SIZES.smallFont, 600) + 4, height: SIZES.smallFont + 4 }],
            layoutOptions: { "elk.nodeLabels.placement": "OUTSIDE V_BOTTOM H_CENTER" },
          }),
    })),
    edges: arcs.map((a) => ({
      id: a.id,
      sources: [a.source],
      targets: [a.target],
      labels: [{ text: a.label, width: textWidth(a.label, SIZES.smallFont, 600) + 8, height: SIZES.smallFont + 4 }],
    })),
  };
  const result = await elk.layout(root);

  const nodes: LaidOutNode[] = (result.children ?? []).map((n) => ({
    id: n.id,
    x: n.x ?? 0,
    y: n.y ?? 0,
    data: data.get(n.id) as ActivityNodeData | TerminalNodeData,
  }));
  const routed = new Map((result.edges ?? []).map((e) => [e.id, e]));
  return {
    nodes,
    arcs: arcs.map((a) => {
      const edge = routed.get(a.id);
      const section = edge?.sections?.[0];
      const label = edge?.labels?.[0];
      return {
        id: a.id,
        source: a.source,
        target: a.target,
        objectType: a.arc.object_type,
        count: a.arc.count,
        objects: a.arc.objects,
        label: a.label,
        path: section ? sectionPath(section) : "",
        labelPosition:
          label?.x != null && label?.y != null
            ? { x: label.x + (label.width ?? 0) / 2, y: label.y + (label.height ?? 0) / 2 }
            : null,
      };
    }),
  };
};
