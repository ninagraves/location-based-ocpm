// The directly-follows graph as a scene of plain shapes (rectangles, circles, paths, texts), drawn from the layout as
// it is on the page (dragged nodes and arcs removed by hand included), with a legend of the object types below it.
// The same scene is written as SVG, PDF (vector, jsPDF), PNG (the SVG rasterised) and a standalone interactive HTML page
// (`lib/dfgDownload.ts`). Documented in docs/pages/directly-follows-graph.md, section "Download".
//
// Example: `graphScene(drawing, { legend: true })` for a graph with the arc load truck → unload truck gives a scene
// with two activity boxes, one coloured path with an arrow head, its label and, below, the legend
// "Object types: ━ truck ● operator".

import { num } from "./format";
import { type ActivityNodeData, type ArcLabel, SIZES, type TerminalNodeData, textWidth } from "./dfgLayout";

/** Colours of the export (always light, whatever the page's colour scheme: the files are meant for print and papers). */
export const EXPORT_COLOURS = {
  background: "#ffffff",
  text: "#212529",
  /** Frequency in an activity, object-type name below a start or end node. */
  secondaryText: "#5c5f66",
  /** Border of an activity node (Mantine gray 7, as on the page). */
  border: "#495057",
  /** Outline of an object-type circle (Mantine gray 6). */
  circleOutline: "#868e96",
  /** Legend explanations. */
  dimmed: "#868e96",
} as const;

/**
 * A colour without transparency: an 8-digit hex colour (e.g. the paler colours of unselected object types,
 * `emphasisColourMap`) blended onto white, since PDF drawing commands have no alpha. Other colours are returned as given.
 *
 * @param colour E.g. "#0098a18c".
 * @returns E.g. "#5ec0c6".
 */
export const solid = (colour: string): string => {
  const m = /^#([0-9a-f]{6})([0-9a-f]{2})$/i.exec(colour);
  if (!m) return colour;
  const alpha = parseInt(m[2], 16) / 255;
  const channels = [0, 2, 4].map((i) => Math.round(parseInt(m[1].slice(i, i + 2), 16) * alpha + 255 * (1 - alpha)));
  return `#${channels.map((c) => c.toString(16).padStart(2, "0")).join("")}`;
};

/** Length and half width of an arc's arrow head, in pixels. */
export const ARROW = { length: 8, halfWidth: 4 };
/** White space around the drawing, in pixels. */
export const MARGIN = 12;

/** A point. */
type Point = { x: number; y: number };

/** One step of a path, in absolute coordinates. */
export type Segment =
  | { op: "M" | "L"; p: Point }
  | { op: "C"; c1: Point; c2: Point; p: Point }
  | { op: "Z" };

/** A plain shape of the scene. Text positions are baselines; `width` is the text's width as measured on the page. */
export type Shape =
  | { kind: "rect"; x: number; y: number; w: number; h: number; r: number; fill: string; stroke?: string; strokeWidth?: number }
  | { kind: "circle"; cx: number; cy: number; r: number; fill: string; stroke?: string; strokeWidth?: number }
  | { kind: "path"; d: Segment[]; stroke?: string; strokeWidth?: number; fill?: string; hit?: boolean }
  | { kind: "text"; x: number; y: number; text: string; size: number; weight: number; fill: string; anchor: "start" | "middle"; width: number };

/** A group of shapes with an optional hover text (lines separated by "\n"); groups can be nested (a circle on a node). */
export type Group = { shapes: (Shape | Group)[]; hover?: string; className?: string };

/** A scene: groups in drawing order and the size of the whole drawing (origin at 0, 0). */
export type Scene = { width: number; height: number; groups: Group[]; fontFamily: string };

/** An activity or start / end node as drawn (position = top left corner). */
export type DrawnNode = { x: number; y: number; data: ActivityNodeData | TerminalNodeData };

/** An arc as drawn: its path (`M x,y C …`), colour, stroke width, label and hover numbers. */
export type DrawnArc = {
  path: string;
  colour: string;
  width: number;
  label: string;
  labelPosition: Point | null;
  objectType: string;
  count: number;
  objects: number;
  connecting: boolean;
};

/** Everything needed to draw the graph: nodes and arcs as on the page, colours per object type, the arc labels' meaning. */
export type Drawing = { nodes: DrawnNode[]; arcs: DrawnArc[]; colours: Map<string, string>; arcLabel: ArcLabel };

/** Options of the scene. */
export type SceneOptions = { legend: boolean; fontFamily?: string };

/** Distance from the vertical centre of a line of text to its baseline, as a share of the font size. */
const BASELINE = 0.35;

/**
 * Parse a path of absolute "x,y" points with the commands M, L and C (as written by `sectionPath` and `bendPath`).
 *
 * @param path E.g. "M 0,0 C 10,0 20,0 30,0".
 * @returns The segments, e.g. [{op: "M", p: {x: 0, y: 0}}, {op: "C", c1: …, c2: …, p: {x: 30, y: 0}}].
 */
export const parsePath = (path: string): Segment[] => {
  const segments: Segment[] = [];
  const tokens = path.match(/[MLC]|-?[\d.]+(?:e-?\d+)?,-?[\d.]+(?:e-?\d+)?/g) ?? [];
  let op = "M";
  const points: Point[] = [];
  const flush = () => {
    if (op === "C") {
      for (let i = 0; i + 2 < points.length; i += 3) segments.push({ op: "C", c1: points[i], c2: points[i + 1], p: points[i + 2] });
    } else for (const [i, p] of points.entries()) segments.push({ op: op === "M" && i === 0 ? "M" : "L", p });
    points.length = 0;
  };
  for (const token of tokens) {
    if (token === "M" || token === "L" || token === "C") {
      flush();
      op = token;
    } else {
      const [x, y] = token.split(",").map(Number);
      points.push({ x, y });
    }
  }
  flush();
  return segments;
};

/**
 * Shorten a path at its end by `by` pixels along its last direction (so that the line ends under the arrow head
 * instead of at its tip) and return the arrow head: a triangle with its tip at the original end point.
 *
 * @param d The path.
 * @param by How far to pull the end back (default: 70 % of the arrow's length).
 * @param size Length and half width of the arrow (default `ARROW`; larger for thick arcs, e.g. `arcArrow` in
 *   lib/typeGraphDrawing.ts).
 * @returns The shortened path and the arrow triangle (null for a path without direction).
 */
export const arrowHead = (
  d: Segment[],
  by?: number,
  size: { length: number; halfWidth: number } = ARROW,
): { path: Segment[]; arrow: Segment[] | null } => {
  const pull = by ?? size.length * 0.7;
  const drawn = d.filter((s): s is Exclude<Segment, { op: "Z" }> => s.op !== "Z");
  if (drawn.length < 2) return { path: d, arrow: null };
  const last = drawn[drawn.length - 1];
  const before = last.op === "C" ? (Math.hypot(last.c2.x - last.p.x, last.c2.y - last.p.y) > 0.01 ? last.c2 : last.c1) : drawn[drawn.length - 2].p;
  const length = Math.hypot(last.p.x - before.x, last.p.y - before.y);
  if (length < 0.01) return { path: d, arrow: null };
  const ux = (last.p.x - before.x) / length;
  const uy = (last.p.y - before.y) / length;
  const tip = last.p;
  const base = { x: tip.x - ux * size.length, y: tip.y - uy * size.length };
  const arrow: Segment[] = [
    { op: "M", p: tip },
    { op: "L", p: { x: base.x - uy * size.halfWidth, y: base.y + ux * size.halfWidth } },
    { op: "L", p: { x: base.x + uy * size.halfWidth, y: base.y - ux * size.halfWidth } },
    { op: "Z" },
  ];
  const back = (p: Point) => ({ x: p.x - ux * pull, y: p.y - uy * pull });
  const path = d.map((s) => (s === last ? (s.op === "C" ? { ...s, c2: back(s.c2), p: back(s.p) } : { ...s, p: back(s.p) }) : s));
  return { path, arrow };
};

/** Text shape helper: measured width, baseline from the vertical centre (also used by lib/typeGraphDrawing.ts). */
export const text = (
  value: string,
  x: number,
  centreY: number,
  size: number,
  options: { weight?: number; fill?: string; anchor?: "start" | "middle" } = {},
): Shape => ({
  kind: "text",
  x,
  y: centreY + BASELINE * size,
  text: value,
  size,
  weight: options.weight ?? 400,
  fill: options.fill ?? EXPORT_COLOURS.text,
  anchor: options.anchor ?? "middle",
  width: textWidth(value, size, options.weight ?? 400),
});

/** Hover text of an activity node (as on the page, without the hints on mouse actions). */
export const activityHover = (d: ActivityNodeData) =>
  [
    d.activity,
    `${num(d.events)} events shown${d.logEvents !== d.events ? ` (of ${num(d.logEvents)} in the log)` : ""}`,
    ...d.involved.map((t) => `${t.objectType}${t.selected ? "" : " (not selected)"}: ${num(t.events)} events, ${num(t.objects)} objects`),
  ].join("\n");

/** Hover text of an arc (as on the page, without the hint on removing it). */
export const arcHover = (a: DrawnArc) =>
  `${a.objectType}: ${num(a.count)} traversals, ${num(a.objects)} objects${a.connecting ? "\nOnly kept to stay connected (Arcs (projection) or Arcs (display) would hide it)" : ""}`;

/**
 * The shapes of an activity node, laid out as on the page (`ActivityNode` in components/DfgGraph.tsx): border box,
 * centred name lines, below them the frequency followed by a circle per unselected object type.
 */
const activityGroup = (n: DrawnNode, d: ActivityNodeData, colours: Map<string, string>): Group => {
  const circles = d.involved.filter((t) => !t.selected);
  const nameHeight = d.lines.length * SIZES.nameLine;
  const rowHeight = Math.max(SIZES.frequencyFont + 3, SIZES.circle);
  const inner = d.height - 2 - 2 * SIZES.padY;
  const top = n.y + 1 + SIZES.padY + (inner - nameHeight - rowHeight) / 2;
  const centreX = n.x + d.width / 2;
  const shapes: (Shape | Group)[] = [
    { kind: "rect", x: n.x + 0.5, y: n.y + 0.5, w: d.width - 1, h: d.height - 1, r: 4, fill: EXPORT_COLOURS.background, stroke: EXPORT_COLOURS.border, strokeWidth: 1 },
    ...d.lines.map((line, i) => text(line, centreX, top + (i + 0.5) * SIZES.nameLine, SIZES.nameFont, { weight: d.nameWeight })),
  ];
  const frequency = num(d.events);
  const frequencyWidth = textWidth(frequency, SIZES.frequencyFont);
  const circlesWidth = circles.length ? 2 * SIZES.circleGap + circles.length * SIZES.circle + (circles.length - 1) * SIZES.circleGap : 0;
  const rowY = top + nameHeight + rowHeight / 2;
  let x = centreX - (frequencyWidth + circlesWidth) / 2;
  shapes.push(text(frequency, x, rowY, SIZES.frequencyFont, { fill: EXPORT_COLOURS.secondaryText, anchor: "start" }));
  x += frequencyWidth + 2 * SIZES.circleGap;
  for (const t of circles) {
    shapes.push({
      shapes: [{ kind: "circle", cx: x + SIZES.circle / 2, cy: rowY, r: SIZES.circle / 2, fill: colours.get(t.objectType) ?? EXPORT_COLOURS.dimmed, stroke: EXPORT_COLOURS.circleOutline, strokeWidth: 0.5 }],
      hover: `${t.objectType}: ${num(t.events)} of ${num(d.events)} events, ${num(t.objects)} objects`,
    });
    x += SIZES.circle + SIZES.circleGap;
  }
  return { shapes, hover: activityHover(d), className: "node" };
};

/** The symbol of a start (triangle) or end (square) node: a circle in `fill` with a white mark. */
const terminalSymbol = (kind: "start" | "end", x: number, y: number, size: number, fill: string): Shape[] => {
  const mark: Shape =
    kind === "start"
      ? { kind: "path", fill: "#ffffff", d: [{ op: "M", p: { x: x + size * 0.4, y: y + size * 0.3 } }, { op: "L", p: { x: x + size * 0.7, y: y + size / 2 } }, { op: "L", p: { x: x + size * 0.4, y: y + size * 0.7 } }, { op: "Z" }] }
      : { kind: "rect", x: x + size * 0.33, y: y + size * 0.33, w: size * 0.34, h: size * 0.34, r: 0, fill: "#ffffff" };
  return [{ kind: "circle", cx: x + size / 2, cy: y + size / 2, r: size / 2 - 1, fill, stroke: EXPORT_COLOURS.text, strokeWidth: 1 }, mark];
};

/** The shapes of a start or end node: the symbol in the type's colour and the type's name below. */
const terminalGroup = (n: DrawnNode, d: TerminalNodeData, colours: Map<string, string>): Group => ({
  shapes: [
    ...terminalSymbol(d.kind, n.x, n.y, d.width, colours.get(d.objectType) ?? EXPORT_COLOURS.dimmed),
    text(d.objectType, n.x + d.width / 2, n.y + d.height + 1 + SIZES.smallFont * 0.6, SIZES.smallFont, { fill: EXPORT_COLOURS.secondaryText }),
  ],
  hover: `${d.kind === "start" ? "Start" : "End"} of ${d.objectType}`,
  className: "node",
});

/** The shapes of an arc: an invisible wide line for hovering, the line, its arrow head and its label on a white box. */
const arcGroup = (a: DrawnArc): Group => {
  const { path, arrow } = arrowHead(parsePath(a.path));
  const shapes: Shape[] = [
    { kind: "path", d: path, stroke: a.colour, strokeWidth: 12, hit: true },
    { kind: "path", d: path, stroke: a.colour, strokeWidth: a.width },
  ];
  if (arrow) shapes.push({ kind: "path", d: arrow, fill: a.colour, stroke: a.colour, strokeWidth: 1 });
  if (a.labelPosition) {
    const w = textWidth(a.label, SIZES.smallFont) + 4;
    const h = SIZES.smallFont + 2;
    shapes.push({ kind: "rect", x: a.labelPosition.x - w / 2, y: a.labelPosition.y - h / 2, w, h, r: 3, fill: EXPORT_COLOURS.background });
    shapes.push(text(a.label, a.labelPosition.x, a.labelPosition.y, SIZES.smallFont));
  }
  return { shapes, hover: arcHover(a), className: "arc" };
};

/** Bounding box of shapes (texts by their measured width, curves by their control points). */
export const bounds = (items: (Shape | Group)[]) => {
  let box = { left: Infinity, top: Infinity, right: -Infinity, bottom: -Infinity };
  const add = (x: number, y: number) => {
    box = { left: Math.min(box.left, x), top: Math.min(box.top, y), right: Math.max(box.right, x), bottom: Math.max(box.bottom, y) };
  };
  const visit = (item: Shape | Group) => {
    if ("shapes" in item) return item.shapes.forEach(visit);
    if (item.kind === "rect") (add(item.x, item.y), add(item.x + item.w, item.y + item.h));
    else if (item.kind === "circle") (add(item.cx - item.r, item.cy - item.r), add(item.cx + item.r, item.cy + item.r));
    else if (item.kind === "text") {
      const left = item.anchor === "middle" ? item.x - item.width / 2 : item.x;
      add(left, item.y - item.size);
      add(left + item.width, item.y + item.size * 0.3);
    } else if (!item.hit)
      for (const s of item.d) {
        if (s.op === "Z") continue;
        add(s.p.x, s.p.y);
        if (s.op === "C") (add(s.c1.x, s.c1.y), add(s.c2.x, s.c2.y));
      }
  };
  items.forEach(visit);
  return box;
};

/** Move shapes by (dx, dy). */
export const shift = (item: Shape | Group, dx: number, dy: number): Shape | Group => {
  if ("shapes" in item) return { ...item, shapes: item.shapes.map((s) => shift(s, dx, dy)) };
  const p = (q: Point) => ({ x: q.x + dx, y: q.y + dy });
  switch (item.kind) {
    case "rect":
      return { ...item, x: item.x + dx, y: item.y + dy };
    case "circle":
      return { ...item, cx: item.cx + dx, cy: item.cy + dy };
    case "text":
      return { ...item, x: item.x + dx, y: item.y + dy };
    case "path":
      return { ...item, d: item.d.map((s) => (s.op === "Z" ? s : s.op === "C" ? { ...s, c1: p(s.c1), c2: p(s.c2), p: p(s.p) } : { ...s, p: p(s.p) })) };
  }
};

/** Legend entry of an object type: its colour as a line with an arrow (selected, drawn as arcs) or as a circle (not selected). */
type LegendEntry = { objectType: string; colour: string; selected: boolean };

/**
 * The object types to explain: selected ones (with arcs or start / end nodes) first, then the unselected ones shown as
 * circles, each in the order of the colour map (the page's order of object types).
 */
export const legendEntries = (drawing: Drawing): LegendEntry[] => {
  const selected = new Set(drawing.arcs.map((a) => a.objectType));
  const circles = new Set<string>();
  for (const n of drawing.nodes) {
    if (n.data.kind === "activity") {
      for (const t of n.data.involved) (t.selected ? selected : circles).add(t.objectType);
    } else selected.add(n.data.objectType);
  }
  const order = [...drawing.colours.keys()];
  const sorted = (types: Set<string>) => [...types].sort((a, b) => (order.indexOf(a) + 1 || Infinity) - (order.indexOf(b) + 1 || Infinity));
  return [
    ...sorted(selected).map((objectType) => ({ objectType, colour: drawing.colours.get(objectType) ?? EXPORT_COLOURS.dimmed, selected: true })),
    ...sorted(circles)
      .filter((t) => !selected.has(t))
      .map((objectType) => ({ objectType, colour: drawing.colours.get(objectType) ?? EXPORT_COLOURS.dimmed, selected: false })),
  ];
};

/**
 * The legend below the graph, wrapped to `width`: first row "Object types:" with one entry per type (line with arrow
 * = selected, circle = only shown on activities), then the key of the symbols in grey.
 *
 * @param drawing The drawing (types, arc label meaning).
 * @param width Width available (the graph's width, at least 360 px).
 * @returns The groups, starting at y = 0.
 */
const legendGroups = (drawing: Drawing, width: number): Group[] => {
  const size = SIZES.smallFont + 1;
  const rowHeight = 16;
  const groups: Group[] = [];
  let x = 0;
  let y = rowHeight / 2;
  const place = (itemWidth: number) => {
    if (x > 0 && x + itemWidth > width) {
      x = 0;
      y += rowHeight;
    }
    const at = x;
    x += itemWidth + 14;
    return at;
  };
  const title = "Object types:";
  const titleWidth = textWidth(title, size, 600);
  groups.push({ shapes: [text(title, place(titleWidth), y, size, { weight: 600, anchor: "start" })] });
  for (const e of legendEntries(drawing)) {
    const nameWidth = textWidth(e.objectType, size);
    const swatch = e.selected ? 22 : SIZES.circle + 2;
    const at = place(swatch + 4 + nameWidth);
    const shapes: Shape[] = e.selected
      ? (() => {
          const { path, arrow } = arrowHead([{ op: "M", p: { x: at, y } }, { op: "L", p: { x: at + swatch, y } }]);
          return [{ kind: "path", d: path, stroke: e.colour, strokeWidth: 2.5 }, { kind: "path", d: arrow ?? [], fill: e.colour, stroke: e.colour, strokeWidth: 1 }] as Shape[];
        })()
      : [{ kind: "circle", cx: at + SIZES.circle / 2 + 1, cy: y, r: SIZES.circle / 2, fill: e.colour, stroke: EXPORT_COLOURS.circleOutline, strokeWidth: 0.5 }];
    shapes.push(text(e.objectType, at + swatch + 4, y, size, { anchor: "start" }));
    groups.push({
      shapes,
      hover: e.selected
        ? `${e.objectType}: directly-follows arcs, start and end nodes in this colour`
        : `${e.objectType}: not selected, shown as a circle on the activities whose events involve it`,
    });
  }
  // Key of the symbols, on a new row, in grey.
  x = 0;
  y += rowHeight;
  const key = (symbol: Shape[], symbolWidth: number, label: string) => {
    const labelWidth = textWidth(label, SIZES.smallFont);
    const at = place(symbolWidth + (symbolWidth ? 4 : 0) + labelWidth);
    groups.push({
      shapes: [
        ...symbol.map((s) => shift(s, at, y) as Shape),
        text(label, at + symbolWidth + (symbolWidth ? 4 : 0), y, SIZES.smallFont, { fill: EXPORT_COLOURS.dimmed, anchor: "start" }),
      ],
    });
  };
  const s = 12;
  key(terminalSymbol("start", 0, -s / 2, s, EXPORT_COLOURS.dimmed), s, "start of an object type");
  key(terminalSymbol("end", 0, -s / 2, s, EXPORT_COLOURS.dimmed), s, "end of an object type (grey arcs: from a start / to an end)");
  key([], 0, "number in an activity: its events");
  key([], 0, `number on an arc: ${drawing.arcLabel === "count" ? "traversals" : "objects"}`);
  key([], 0, "thicker arc: more traversals");
  return groups;
};

/**
 * The scene of a drawing: arcs first (below), then nodes, then (option) the legend below the graph; everything moved
 * so that the drawing starts at (MARGIN, MARGIN).
 *
 * @param drawing Nodes and arcs as on the page.
 * @param options `legend`: add the legend; `fontFamily`: font of the texts (default: the page's font).
 * @returns The scene, in pixels.
 */
export const graphScene = (input: Drawing, options: SceneOptions): Scene => {
  const drawing: Drawing = {
    ...input,
    colours: new Map([...input.colours].map(([t, c]) => [t, solid(c)])),
    arcs: input.arcs.map((a) => ({ ...a, colour: solid(a.colour) })),
  };
  const graph: Group[] = [
    ...drawing.arcs.filter((a) => a.path).map(arcGroup),
    ...drawing.nodes.map((n) => (n.data.kind === "activity" ? activityGroup(n, n.data, drawing.colours) : terminalGroup(n, n.data, drawing.colours))),
  ];
  const box = bounds(graph);
  if (!Number.isFinite(box.left)) throw new Error("Nothing to download: the graph is empty.");
  const graphWidth = box.right - box.left;
  let groups = graph.map((g) => shift(g, MARGIN - box.left, MARGIN - box.top) as Group);
  let width = graphWidth;
  let height = box.bottom - box.top;
  if (options.legend) {
    const legendWidth = Math.max(graphWidth, 360);
    const legend = legendGroups(drawing, legendWidth);
    const legendBox = bounds(legend);
    const top = MARGIN + height + 18;
    groups = [...groups, ...legend.map((g) => shift(g, MARGIN - Math.min(0, legendBox.left), top - legendBox.top) as Group)];
    width = Math.max(width, legendBox.right - Math.min(0, legendBox.left));
    height += 18 + (legendBox.bottom - legendBox.top);
  }
  const fontFamily =
    options.fontFamily ?? (typeof document !== "undefined" ? getComputedStyle(document.body).fontFamily : "") ?? "";
  return { width: Math.ceil(width + 2 * MARGIN), height: Math.ceil(height + 2 * MARGIN), groups, fontFamily: fontFamily || "Helvetica, Arial, sans-serif" };
};

/** Escape a text for XML. */
const xml = (value: string) => value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** Round to two decimals (smaller files). */
const r2 = (v: number) => Math.round(v * 100) / 100;

/** SVG path data of segments (also the arcs of the transformation type graph on the page). */
export const pathData = (d: Segment[]) =>
  d.map((s) => (s.op === "Z" ? "Z" : s.op === "C" ? `C${r2(s.c1.x)},${r2(s.c1.y)} ${r2(s.c2.x)},${r2(s.c2.y)} ${r2(s.p.x)},${r2(s.p.y)}` : `${s.op}${r2(s.p.x)},${r2(s.p.y)}`)).join(" ");

/** SVG of one shape. */
const shapeSvg = (s: Shape): string => {
  switch (s.kind) {
    case "rect":
      return `<rect x="${r2(s.x)}" y="${r2(s.y)}" width="${r2(s.w)}" height="${r2(s.h)}"${s.r ? ` rx="${s.r}"` : ""} fill="${s.fill}"${s.stroke ? ` stroke="${s.stroke}" stroke-width="${s.strokeWidth ?? 1}"` : ""}/>`;
    case "circle":
      return `<circle cx="${r2(s.cx)}" cy="${r2(s.cy)}" r="${r2(s.r)}" fill="${s.fill}"${s.stroke ? ` stroke="${s.stroke}" stroke-width="${s.strokeWidth ?? 1}"` : ""}/>`;
    case "path":
      if (s.hit) return `<path d="${pathData(s.d)}" fill="none" stroke="${s.stroke}" stroke-opacity="0" stroke-width="${s.strokeWidth}" class="hit"/>`;
      return `<path d="${pathData(s.d)}" fill="${s.fill ?? "none"}"${s.stroke ? ` stroke="${s.stroke}" stroke-width="${r2(s.strokeWidth ?? 1)}" stroke-linecap="round" stroke-linejoin="round"` : ""}/>`;
    case "text":
      return `<text x="${r2(s.x)}" y="${r2(s.y)}" font-size="${s.size}"${s.weight !== 400 ? ` font-weight="${s.weight}"` : ""}${s.anchor === "middle" ? ' text-anchor="middle"' : ""} fill="${s.fill}">${xml(s.text)}</text>`;
  }
};

/**
 * The scene as an SVG document: plain SVG 1.1 shapes and texts (no HTML inside), so editors such as Inkscape,
 * Illustrator and LaTeX (via Inkscape or rsvg) show it too.
 *
 * @param scene The scene.
 * @param hover "title": hover texts as `<title>` elements (the browser shows them when the file is opened);
 *   "data": as `data-hover` attributes (for the interactive HTML page, which shows its own tooltip).
 * @returns The SVG text.
 */
export const sceneSvg = (scene: Scene, hover: "title" | "data" = "title"): string => {
  const group = (g: Group): string => {
    const attributes = `${g.className ? ` class="${g.className}"` : ""}${g.hover && hover === "data" ? ` data-hover="${xml(g.hover)}"` : ""}`;
    const title = g.hover && hover === "title" ? `<title>${xml(g.hover)}</title>` : "";
    return `<g${attributes}>${title}${g.shapes.map((s) => ("shapes" in s ? group(s) : shapeSvg(s))).join("")}</g>`;
  };
  return [
    `<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="${scene.width}" height="${scene.height}" viewBox="0 0 ${scene.width} ${scene.height}" font-family="${xml(scene.fontFamily)}">`,
    `<rect width="100%" height="100%" fill="${EXPORT_COLOURS.background}"/>`,
    ...scene.groups.map(group),
    "</svg>",
  ].join("\n");
};
