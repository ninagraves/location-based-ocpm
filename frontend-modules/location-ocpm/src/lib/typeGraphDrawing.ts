// The transformation type graph (gozinto graph) as a scene of plain shapes, for its download as PDF, SVG, HTML or PNG
// (`downloadScene`, lib/dfgDownload.ts). Same approach as the DFG download (lib/dfgDrawing.ts): the graph is drawn
// again from the layout on the page, always light, optionally with a legend below it.
// Documented in docs/pages/transformations.md, section "Transformation type graph".
//
// Example: `typeGraphScene(drawing, { legend: true })` for the running example gives two ellipses (slab, coil), three
// recipe rectangles (cast slab, cut, roll), five coloured arcs with arrow heads and quantity labels and, below, the
// legend "Object types: ⬭ coil ⬭ slab" with the key of the symbols.

import { num, pct } from "./format";
import { arrowHead, bounds, EXPORT_COLOURS, type Group, MARGIN, parsePath, type Scene, type Segment, type Shape, shift, solid, text } from "./dfgDrawing";
import { textWidth } from "./dfgLayout";

/** An object type as drawn (position = top left corner). */
export type DrawnType = { x: number; y: number; width: number; height: number; objectType: string; consumed: number; produced: number; colour: string };

/** A recipe as drawn (position = top left corner). */
export type DrawnRecipe = {
  x: number;
  y: number;
  width: number;
  height: number;
  id: string;
  recipe: string;
  activity: string;
  frequency: number;
  share: number;
  kind: string;
};

/** An arc as drawn: its path (`M x,y C …`), colour, stroke width, quantity label and hover text. */
export type DrawnTypeArc = { path: string; colour: string; width: number; label: string; labelPosition: { x: number; y: number } | null; hover: string };

/** Everything needed to draw the type graph; `colours` per object type in the order of the legend. */
export type TypeDrawing = { types: DrawnType[]; recipes: DrawnRecipe[]; arcs: DrawnTypeArc[]; colours: Map<string, string>; kindLabels: Record<string, string> };

/** Font sizes and fill opacity of the ellipses, as on the page (`SIZE` in components/TransformationTypeGraph.tsx). */
const SIZES = { font: 12, small: 10, ellipseFill: "26" };

/** Bézier constant for a quarter ellipse. */
const KAPPA = 0.5523;

/**
 * An ellipse as a closed path of four cubic Bézier curves (the scene has no ellipse shape; PDF, SVG and the bounding
 * box all handle paths).
 *
 * @param cx Centre x.
 * @param cy Centre y.
 * @param rx Horizontal radius.
 * @param ry Vertical radius.
 * @returns The path, starting at the leftmost point.
 */
export const ellipsePath = (cx: number, cy: number, rx: number, ry: number): Segment[] => {
  const kx = rx * KAPPA;
  const ky = ry * KAPPA;
  return [
    { op: "M", p: { x: cx - rx, y: cy } },
    { op: "C", c1: { x: cx - rx, y: cy - ky }, c2: { x: cx - kx, y: cy - ry }, p: { x: cx, y: cy - ry } },
    { op: "C", c1: { x: cx + kx, y: cy - ry }, c2: { x: cx + rx, y: cy - ky }, p: { x: cx + rx, y: cy } },
    { op: "C", c1: { x: cx + rx, y: cy + ky }, c2: { x: cx + kx, y: cy + ry }, p: { x: cx, y: cy + ry } },
    { op: "C", c1: { x: cx - kx, y: cy + ry }, c2: { x: cx - rx, y: cy + ky }, p: { x: cx - rx, y: cy } },
    { op: "Z" },
  ];
};

/** The shapes of an object type: ellipse in a pale fill of its colour with a border in its colour, the name centred. */
const typeGroup = (t: DrawnType): Group => ({
  shapes: [
    { kind: "path", d: ellipsePath(t.x + t.width / 2, t.y + t.height / 2, t.width / 2 - 0.75, t.height / 2 - 0.75), fill: solid(`${t.colour}${SIZES.ellipseFill}`), stroke: t.colour, strokeWidth: 1.5 },
    text(t.objectType, t.x + t.width / 2, t.y + t.height / 2, SIZES.font, { weight: 600 }),
  ],
  hover: `${t.objectType}: ${num(t.consumed)} handling units consumed, ${num(t.produced)} produced by the shown recipes`,
  className: "node",
});

/** The shapes of a recipe: rectangle, activity in bold, below it the frequency and share. */
const recipeGroup = (r: DrawnRecipe, kindLabels: Record<string, string>): Group => {
  const line = SIZES.font * 1.15;
  const top = r.y + (r.height - line - SIZES.small * 1.15) / 2;
  return {
    shapes: [
      { kind: "rect", x: r.x + 0.5, y: r.y + 0.5, w: r.width - 1, h: r.height - 1, r: 3, fill: EXPORT_COLOURS.background, stroke: EXPORT_COLOURS.circleOutline, strokeWidth: 1 },
      text(r.activity, r.x + r.width / 2, top + line / 2, SIZES.font, { weight: 600 }),
      text(`${num(r.frequency)}× · ${pct(r.share)}`, r.x + r.width / 2, top + line + (SIZES.small * 1.15) / 2, SIZES.small, { fill: EXPORT_COLOURS.secondaryText }),
    ],
    hover: `${r.id} · ${r.recipe} · ${kindLabels[r.kind] ?? r.kind} · ${num(r.frequency)} events (${pct(r.share, 1)})`,
    className: "node",
  };
};

/** The shapes of an arc: an invisible wide line for hovering, the line, its arrow head and the quantity on a white box. */
const arcGroup = (a: DrawnTypeArc): Group => {
  const colour = solid(a.colour);
  const { path, arrow } = arrowHead(parsePath(a.path));
  const shapes: Shape[] = [
    { kind: "path", d: path, stroke: colour, strokeWidth: 12, hit: true },
    { kind: "path", d: path, stroke: colour, strokeWidth: a.width },
  ];
  if (arrow) shapes.push({ kind: "path", d: arrow, fill: colour, stroke: colour, strokeWidth: 1 });
  if (a.labelPosition) {
    const w = textWidth(a.label, SIZES.small, 600) + 6;
    const h = SIZES.small + 2;
    shapes.push({ kind: "rect", x: a.labelPosition.x - w / 2, y: a.labelPosition.y - h / 2, w, h, r: 3, fill: EXPORT_COLOURS.background });
    shapes.push(text(a.label, a.labelPosition.x, a.labelPosition.y, SIZES.small, { weight: 600 }));
  }
  return { shapes, hover: a.hover, className: "arc" };
};

/**
 * The legend below the graph, wrapped to `width`: "Object types:" with a small ellipse per type, then the key of the
 * symbols in grey.
 *
 * @param colours Colour per object type, in the order of the legend.
 * @param width Width available.
 * @returns The groups, starting at y = 0.
 */
const legendGroups = (colours: Map<string, string>, width: number): Group[] => {
  const size = SIZES.small + 1;
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
  groups.push({ shapes: [text(title, place(textWidth(title, size, 600)), y, size, { weight: 600, anchor: "start" })] });
  const swatch = { w: 20, h: 11 };
  for (const [objectType, colour] of colours) {
    const at = place(swatch.w + 4 + textWidth(objectType, size));
    groups.push({
      shapes: [
        { kind: "path", d: ellipsePath(at + swatch.w / 2, y, swatch.w / 2, swatch.h / 2), fill: solid(`${colour}${SIZES.ellipseFill}`), stroke: colour, strokeWidth: 1.2 },
        text(objectType, at + swatch.w + 4, y, size, { anchor: "start" }),
      ],
      hover: `${objectType}: ellipse and arcs in this colour`,
    });
  }
  x = 0;
  y += rowHeight;
  const key = (label: string) => groups.push({ shapes: [text(label, place(textWidth(label, SIZES.small)), y, SIZES.small, { fill: EXPORT_COLOURS.dimmed, anchor: "start" })] });
  key("ellipse: object type");
  key("rectangle: recipe (activity, events × · share of the transformation events)");
  // No "→" here: the PDF's Helvetica has no arrow glyph.
  key("arrow into a recipe: input, arrow out of a recipe: output");
  key("number on an arc: handling units per event");
  key("thicker arc: more handling units over all events");
  return groups;
};

/**
 * The scene of the type graph: arcs first (below), then object types and recipes, then (option) the legend; moved so
 * that the drawing starts at (MARGIN, MARGIN).
 *
 * @param drawing Object types, recipes and arcs as laid out on the page, with light colours.
 * @param options `legend`: add the legend; `fontFamily`: font of the texts (default: the page's font).
 * @returns The scene, in pixels; throws if the graph is empty.
 */
export const typeGraphScene = (drawing: TypeDrawing, options: { legend: boolean; fontFamily?: string }): Scene => {
  const colours = new Map([...drawing.colours].map(([t, c]) => [t, solid(c)]));
  const graph: Group[] = [
    ...drawing.arcs.filter((a) => a.path).map(arcGroup),
    ...drawing.types.map((t) => typeGroup({ ...t, colour: solid(t.colour) })),
    ...drawing.recipes.map((r) => recipeGroup(r, drawing.kindLabels)),
  ];
  const box = bounds(graph);
  if (!Number.isFinite(box.left)) throw new Error("Nothing to download: the graph is empty.");
  const graphWidth = box.right - box.left;
  let groups = graph.map((g) => shift(g, MARGIN - box.left, MARGIN - box.top) as Group);
  let width = graphWidth;
  let height = box.bottom - box.top;
  if (options.legend) {
    const legend = legendGroups(colours, Math.max(graphWidth, 360));
    const legendBox = bounds(legend);
    const top = MARGIN + height + 18;
    groups = [...groups, ...legend.map((g) => shift(g, MARGIN - Math.min(0, legendBox.left), top - legendBox.top) as Group)];
    width = Math.max(width, legendBox.right - Math.min(0, legendBox.left));
    height += 18 + (legendBox.bottom - legendBox.top);
  }
  const fontFamily = options.fontFamily ?? (typeof document !== "undefined" ? getComputedStyle(document.body).fontFamily : "");
  return { width: Math.ceil(width + 2 * MARGIN), height: Math.ceil(height + 2 * MARGIN), groups, fontFamily: fontFamily || "Helvetica, Arial, sans-serif" };
};
