// Transformation type graph of the transformations page (draft; concept: Lineage (DRAFT).md, "Transformation Type
// Level Model"): object types (ellipses) and recipes (rectangles), arcs object type → recipe (input) and recipe →
// object type (output) labelled with the quantity. A frequency slider hides rare recipes. Laid out with ELK and drawn
// with React Flow, as the lineage chart; downloadable as PDF, SVG, HTML or PNG (`GraphDownloadMenu`, lib/typeGraphDrawing.ts).
// Documented in docs/pages/transformations.md, section "Transformation type graph".
import { Alert, Box, Checkbox, Group, Loader, SegmentedControl, Slider, Stack, Text, Tooltip } from "@mantine/core";
import {
  BaseEdge,
  Controls,
  type Edge,
  type EdgeProps,
  EdgeLabelRenderer,
  Handle,
  type Node,
  type NodeProps,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import ELK, { type ElkNode } from "elkjs/lib/elk.bundled.js";
import { memo, useEffect, useMemo } from "react";
import {
  type GetTransformationTypeGraphQuantities,
  type TypeArc,
  type TypeGraph,
  type TypeNode,
  useGetTransformationTypeGraph,
} from "../api/locationBasedOcpm";
import { ELK_OPTIONS, sectionPath, textWidth } from "../lib/dfgLayout";
import { errorText } from "../lib/errors";
import { num, pct } from "../lib/format";
import { useKeptLayout, useKeptViewport } from "../lib/keptView";
import { usePageState } from "../lib/pageState";
import { useObjectTypeColours } from "../lib/objectTypeColours";
import { emphasisColourMap, OTHER, type Scheme } from "../lib/palette";
import { KIND_LABELS, listRequest, type TransformationFilter } from "../lib/transformations";
import { useDebounced } from "../lib/useDebounced";
import { arcPaths, SIZES as DRAWING_SIZES, type TypeDrawing, typeGraphScene } from "../lib/typeGraphDrawing";
import { duration } from "./HuProfileTable";
import { GraphDownloadMenu } from "./GraphDownloadMenu";
import { useScheme } from "./plots";

/** Settings of the type graph (kept per log). */
type GraphSettings = {
  /** Slider value in percent: share of the transformation events the shown recipes cover. */
  coverage: number;
  quantities: GetTransformationTypeGraphQuantities;
  layout: "RIGHT" | "DOWN";
  /** Show frequency and share in the recipe rectangles (Nina 2026-11-24: optional). */
  frequencies: boolean;
  /** Lifetime in the ellipses: none, the median, or the median and the interval [Q1, Q3] (Nina 2026-11-24). */
  lifetime: Lifetime;
};

type Lifetime = "off" | "median" | "quartiles";
const LIFETIMES: Lifetime[] = ["off", "median", "quartiles"];

const DEFAULTS: GraphSettings = { coverage: 100, quantities: "exact", layout: "RIGHT", frequencies: true, lifetime: "off" };
/** The slider recalculates the graph this long after the last change (ms). */
const SLIDER_DELAY = 400;
/** Sizes of the drawing in pixels. */
const SIZE = { font: 12, small: 10, padX: 10, typeHeight: 36, recipeHeight: 38, recipeHeightSingle: 28, minWidth: 60, minArc: 1.2, maxArc: 8 };
const HEIGHT = 520;

/** `lines`: below the name (full lifecycles, lifetime); `exportColour`: the colour in the light scheme, for the downloads. */
type TypeData = {
  kind: "type";
  objectType: string;
  lines: string[];
  hover: string;
  consumed: number;
  produced: number;
  width: number;
  height: number;
  colour: string;
  exportColour: string;
};
type RecipeData = {
  kind: "recipe";
  id: string;
  recipe: string;
  activity: string;
  frequency: number;
  share: number;
  recipeKind: string;
  showFrequency: boolean;
  /** Faint background of all recipes of the same activity (`activityShades`), on the page and in the light scheme. */
  shade: string;
  exportShade: string;
  width: number;
  height: number;
};
type NodeData = TypeData | RecipeData;
/** `path`: ELK's route (for the downloads); `line` and `arrow`: the drawn line, ending inside its arrow head. */
type EdgeData = {
  path: string;
  line: string;
  arrow: string;
  colour: string;
  exportColour: string;
  width: number;
  label: string;
  hover: string;
  labelPosition: { x: number; y: number } | null;
};

const Handles = () => (
  <>
    <Handle type="target" position={Position.Left} style={{ opacity: 0, pointerEvents: "none" }} />
    <Handle type="source" position={Position.Right} style={{ opacity: 0, pointerEvents: "none" }} />
  </>
);

/** An object type: ellipse in the colour of the type, with its name and lines (full lifecycles, lifetime). */
const TypeNodeView = memo(({ data }: NodeProps<Node<TypeData>>) => (
  <Tooltip label={data.hover} multiline maw={360} withinPortal>
    <Box
      style={{
        width: data.width,
        height: data.height,
        borderRadius: "50%",
        border: `1.5px solid ${data.colour}`,
        background: `${data.colour}26`,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        lineHeight: DRAWING_SIZES.lineHeight,
      }}
    >
      <Handles />
      <Text fz={SIZE.font} fw={600} lh={DRAWING_SIZES.lineHeight}>
        {data.objectType}
      </Text>
      {data.lines.map((line) => (
        <Text key={line} fz={SIZE.small} c="dimmed" lh={DRAWING_SIZES.lineHeight}>
          {line}
        </Text>
      ))}
    </Box>
  </Tooltip>
));

/** A recipe: rectangle with the activity and the frequency. */
const RecipeNodeView = memo(({ data }: NodeProps<Node<RecipeData>>) => (
  <Tooltip label={`${data.id} · ${data.recipe} · ${KIND_LABELS[data.recipeKind] ?? data.recipeKind} · ${num(data.frequency)} events (${pct(data.share, 1)})`} withinPortal>
    <Box
      style={{
        width: data.width,
        height: data.height,
        borderRadius: 3,
        border: "1px solid var(--mantine-color-gray-6)",
        background: `linear-gradient(${data.shade}, ${data.shade}), var(--mantine-color-body)`,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        lineHeight: 1.15,
      }}
    >
      <Handles />
      <Text fz={SIZE.font} fw={600}>
        {data.activity}
      </Text>
      {data.showFrequency && (
        <Text fz={SIZE.small} c="dimmed">
          {num(data.frequency)}× · {pct(data.share)}
        </Text>
      )}
    </Box>
  </Tooltip>
));

/**
 * An arc: ELK's route, width by the handling units that flowed along it, labelled with the quantity. The arrow head
 * grows with the width (`arcArrow`), and the line ends inside it, so thick arcs keep a visible point.
 */
const ArcView = memo(({ id, data }: EdgeProps<Edge<EdgeData>>) => {
  if (!data?.path) return null;
  return (
    <>
      <BaseEdge id={id} path={data.line} style={{ stroke: data.colour, strokeWidth: data.width, strokeOpacity: 0.85 }} />
      {data.arrow && <path d={data.arrow} fill={data.colour} stroke={data.colour} strokeWidth={1} strokeLinejoin="round" />}
      {data.labelPosition && (
        <EdgeLabelRenderer>
          <Box
            title={data.hover}
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${data.labelPosition.x}px, ${data.labelPosition.y}px)`,
              fontSize: SIZE.small,
              fontWeight: 600,
              padding: "0 3px",
              background: "var(--mantine-color-body)",
              borderRadius: 3,
              pointerEvents: "all",
              cursor: "help",
            }}
          >
            {data.label}
          </Box>
        </EdgeLabelRenderer>
      )}
    </>
  );
});

const NODE_TYPES = { type: TypeNodeView, recipe: RecipeNodeView };
const EDGE_TYPES = { arc: ArcView };
const elk = new ELK();

/** The quantity label of an arc: "2", or "2–3" if the merged recipes differ ("as sets"). */
const quantityLabel = (a: TypeArc) => (a.quantity_min === a.quantity_max ? num(a.quantity_min) : `${num(a.quantity_min)}–${num(a.quantity_max)}`);

/**
 * The lines below an object type's name: its handling units with a full lifecycle (produced and finally consumed in
 * the log) and, if chosen, the median lifetime and the interval [Q1, Q3] of the lifetimes of these handling units
 * (Nina 2026-11-24: an interval instead of the IQR).
 * Example (running example, coil, "quartiles"): ["1 full lifecycle", "median 12 h · [12 h, 12 h]"].
 *
 * @param t The object type from the backend (`type_lifecycles`).
 * @param lifetime What to show of the lifetime.
 * @returns The lines.
 */
export const typeLines = (t: TypeNode, lifetime: Lifetime): string[] => {
  const full = t.full_lifecycle ?? 0;
  const lines = [`${num(full)} full ${full === 1 ? "lifecycle" : "lifecycles"}`];
  if (lifetime === "off" || t.lifetime_median == null) return lines;
  lines.push(
    lifetime === "quartiles"
      ? `median ${duration(t.lifetime_median)} · [${duration(t.lifetime_q1)}, ${duration(t.lifetime_q3)}]`
      : `median ${duration(t.lifetime_median)}`,
  );
  return lines;
};

/** Opacity of the activity shades of the recipe rectangles (hex alpha): very slight (Nina 2026-11-24). */
const SHADE_ALPHA: Record<Scheme, string> = { light: "14", dark: "24" };

/**
 * One very slight shade per activity, so that the recipes of the same activity share a background (Nina 2026-11-24).
 * The colours are the categorical colours without the signature colours of the handling-unit types
 * (`emphasisColourMap` with no emphasised values), so a shade is not mistaken for an object type; activities are
 * ranked by the events of their shown recipes (ties by name).
 * Example: recipes roll (5 events), roll (2), cut (3): roll gets #5291cc14, cut the next colour with alpha 14.
 *
 * @param recipes The shown recipes.
 * @param scheme Light or dark.
 * @returns Shade per activity (8-digit hex).
 */
export const activityShades = (recipes: { activity: string; frequency: number }[], scheme: Scheme): Map<string, string> => {
  const events = new Map<string, number>();
  for (const r of recipes) events.set(r.activity, (events.get(r.activity) ?? 0) + r.frequency);
  const ranked = [...events].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([activity]) => activity);
  const colours = emphasisColourMap([], ranked, scheme, false);
  return new Map(ranked.map((a) => [a, `${colours.get(a)}${SHADE_ALPHA[scheme]}`]));
};

/** Hover text of an object type: handling units, full lifecycles, lifetime quartiles, flow in the shown recipes. */
const typeHover = (t: TypeNode) =>
  [
    `${t.object_type}: ${num(t.handling_units ?? 0)} handling units in the log, ${num(t.full_lifecycle ?? 0)} with a full lifecycle (produced and finally consumed in the log)`,
    t.lifetime_median != null
      ? `Lifetime (production to final consumption) of these: median ${duration(t.lifetime_median)}, Q1 ${duration(t.lifetime_q1)}, Q3 ${duration(t.lifetime_q3)}`
      : "",
    `${num(t.consumed)} handling units consumed, ${num(t.produced)} produced by the shown recipes`,
  ]
    .filter(Boolean)
    .join("\n");

/**
 * Lay out the type graph with ELK (layered, Ocelescope's DFG options) and turn it into React Flow nodes and edges.
 *
 * @param graph The graph from the backend.
 * @param direction Layout direction.
 * @param colours Colour per object type on the page (`useObjectTypeColours`: the same on every page).
 * @param exportColours Colour per object type in the light scheme, for the downloads.
 * @param show What the nodes show: recipe frequencies and the lifetime in the ellipses.
 */
const layoutTypeGraph = async (
  graph: TypeGraph,
  direction: "RIGHT" | "DOWN",
  colours: Map<string, string>,
  exportColours: Map<string, string>,
  show: { frequencies: boolean; lifetime: Lifetime },
  scheme: Scheme,
) => {
  const shades = activityShades(graph.recipes, scheme);
  const exportShades = scheme === "light" ? shades : activityShades(graph.recipes, "light");
  const sizes = new Map<string, { width: number; height: number }>();
  const lines = new Map(graph.object_types.map((t) => [t.node, typeLines(t, show.lifetime)]));
  const line = DRAWING_SIZES.lineHeight;
  for (const t of graph.object_types) {
    const own = lines.get(t.node) ?? [];
    const textW = Math.max(textWidth(t.object_type, SIZE.font, 600), ...own.map((l) => textWidth(l, SIZE.small)));
    const textH = SIZE.font * line + own.length * SIZE.small * line;
    // An ellipse fits its text if it is about 1.3 times as wide and 1.35 times as high as the text block.
    sizes.set(t.node, { width: Math.ceil(Math.max(SIZE.minWidth, textW + 2 * SIZE.padX) * 1.3), height: Math.ceil(Math.max(SIZE.typeHeight, (textH + 8) * 1.35)) });
  }
  for (const r of graph.recipes)
    sizes.set(r.node, {
      width: Math.ceil(
        Math.max(SIZE.minWidth, textWidth(r.activity, SIZE.font, 600), show.frequencies ? textWidth(`${r.frequency}× · 100 %`, SIZE.small) : 0) + 2 * SIZE.padX,
      ),
      height: show.frequencies ? SIZE.recipeHeight : SIZE.recipeHeightSingle,
    });
  const maxHus = Math.max(1, ...graph.arcs.map((a) => a.hus));
  const root: ElkNode = {
    id: "root",
    layoutOptions: { ...ELK_OPTIONS, "elk.direction": direction },
    children: [...graph.object_types.map((t) => t.node), ...graph.recipes.map((r) => r.node)].map((id) => ({ id, ...sizes.get(id) })),
    edges: graph.arcs.map((a, i) => {
      const label = quantityLabel(a);
      return { id: `a${i}`, sources: [a.source], targets: [a.target], labels: [{ text: label, width: textWidth(label, SIZE.small, 600) + 8, height: SIZE.small + 4 }] };
    }),
  };
  const result = await elk.layout(root);
  const position = new Map((result.children ?? []).map((n) => [n.id, { x: n.x ?? 0, y: n.y ?? 0 }]));
  const routed = new Map((result.edges ?? []).map((e) => [e.id, e]));
  const recipes = new Map(graph.recipes.map((r) => [r.id, r]));
  const nodes: Node<NodeData>[] = [
    ...graph.object_types.map((t) => ({
      id: t.node,
      type: "type",
      position: position.get(t.node) ?? { x: 0, y: 0 },
      data: {
        kind: "type" as const,
        objectType: t.object_type,
        lines: lines.get(t.node) ?? [],
        hover: typeHover(t),
        consumed: t.consumed,
        produced: t.produced,
        colour: colours.get(t.object_type) ?? OTHER.light,
        exportColour: exportColours.get(t.object_type) ?? OTHER.light,
        ...(sizes.get(t.node) as { width: number; height: number }),
      },
      style: { pointerEvents: "all" as const },
    })),
    ...graph.recipes.map((r) => ({
      id: r.node,
      type: "recipe",
      position: position.get(r.node) ?? { x: 0, y: 0 },
      data: {
        kind: "recipe" as const,
        id: r.id,
        recipe: r.recipe,
        activity: r.activity,
        frequency: r.frequency,
        share: r.share,
        recipeKind: r.kind,
        showFrequency: show.frequencies,
        shade: shades.get(r.activity) ?? "transparent",
        exportShade: exportShades.get(r.activity) ?? "#ffffff",
        ...(sizes.get(r.node) as { width: number; height: number }),
      },
      style: { pointerEvents: "all" as const },
    })),
  ].map((n) => ({ ...n, draggable: false, connectable: false }));
  const edges: Edge<EdgeData>[] = graph.arcs.map((a, i) => {
    const r = routed.get(`a${i}`);
    const section = r?.sections?.[0];
    const label = r?.labels?.[0];
    const colour = colours.get(a.object_type) ?? OTHER.light;
    const recipe = recipes.get(a.recipe);
    const events = recipe?.frequency ?? 0;
    const path = section ? sectionPath(section) : "";
    const width = SIZE.minArc + ((SIZE.maxArc - SIZE.minArc) * a.hus) / maxHus;
    const drawn = path ? arcPaths(path, width) : { line: "", arrow: "" };
    return {
      id: `a${i}`,
      source: a.source,
      target: a.target,
      type: "arc",
      data: {
        path,
        line: drawn.line,
        arrow: drawn.arrow,
        colour,
        exportColour: exportColours.get(a.object_type) ?? OTHER.light,
        width,
        label: quantityLabel(a),
        hover: `${recipe?.recipe ?? a.recipe}: ${quantityLabel(a)} ${a.object_type} per event ${a.role === "consumed" ? "consumed" : "produced"}; ${num(a.hus)} handling units over ${num(events)} events`,
        labelPosition: label?.x != null && label?.y != null ? { x: label.x + (label.width ?? 0) / 2, y: label.y + (label.height ?? 0) / 2 } : null,
      },
    };
  });
  return { nodes, edges };
};

const FitOnChange = ({ token, skip }: { token: unknown; skip: (token: unknown) => boolean }) => {
  const { fitView } = useReactFlow();
  useEffect(() => {
    if (!skip(token)) requestAnimationFrame(() => fitView({ padding: 0.1, maxZoom: 1 }));
  }, [token, fitView, skip]);
  return null;
};

/**
 * The graph as laid out on the page, in light colours, for the download (`typeGraphScene`). The legend lists the
 * object types in the module's colour order (`useObjectTypeColours`).
 *
 * @param nodes The React Flow nodes.
 * @param edges The React Flow edges.
 * @param order The object types in colour order (the keys of the colour map).
 */
export const typeDrawing = (nodes: Node<NodeData>[], edges: Edge<EdgeData>[], order: string[]): TypeDrawing => {
  const types = nodes.filter((n): n is Node<TypeData> => n.data.kind === "type");
  const recipes = nodes.filter((n): n is Node<RecipeData> => n.data.kind === "recipe");
  const rank = (t: string) => (order.indexOf(t) + 1 || Infinity);
  const ranked = [...types].sort((a, b) => rank(a.data.objectType) - rank(b.data.objectType) || a.data.objectType.localeCompare(b.data.objectType));
  return {
    types: types.map(({ position, data: d }) => ({
      ...position,
      width: d.width,
      height: d.height,
      objectType: d.objectType,
      lines: d.lines ?? [],
      hover: d.hover ?? d.objectType,
      colour: d.exportColour ?? d.colour,
    })),
    recipes: recipes.map(({ position, data: d }) => ({
      ...position,
      width: d.width,
      height: d.height,
      id: d.id,
      recipe: d.recipe,
      activity: d.activity,
      frequency: d.frequency,
      share: d.share,
      kind: d.recipeKind,
      showFrequency: d.showFrequency ?? true,
      shade: d.exportShade ?? "#ffffff",
    })),
    arcs: edges.flatMap((e) => (e.data ? [{ path: e.data.path, colour: e.data.exportColour ?? e.data.colour, width: e.data.width, label: e.data.label, labelPosition: e.data.labelPosition, hover: e.data.hover }] : [])),
    colours: new Map(ranked.map((n) => [n.data.objectType, n.data.exportColour ?? n.data.colour])),
    kindLabels: KIND_LABELS,
    keys: types.some((t) => (t.data.lines ?? []).length)
      ? ["number in an ellipse: handling units with a full lifecycle (produced and finally consumed in the log)", "lifetime: from production to final consumption"]
      : [],
  };
};

/** The slider's marks: 0, 50 and 100 %. */
const MARKS = [0, 50, 100].map((value) => ({ value, label: `${value} %` }));

/**
 * The transformation type graph with its settings: frequency slider, quantities (exact | as sets) and layout.
 *
 * @param ocelId Id of the log.
 * @param filter The page filters (select whole transformation events).
 */
export const TransformationTypeGraph = ({ ocelId, filter }: { ocelId: string; filter: TransformationFilter }) => {
  const [kept, setSettings] = usePageState<GraphSettings>(`transformations.graph.${ocelId}`, DEFAULTS);
  // Settings kept before an option existed lack it: fill in its default.
  const merged: GraphSettings = { ...DEFAULTS, ...kept };
  // ... and a value an option no longer has (e.g. "iqr" before [Q1, Q3]) falls back to the default.
  const settings: GraphSettings = LIFETIMES.includes(merged.lifetime) ? merged : { ...merged, lifetime: DEFAULTS.lifetime };
  const [coverage] = useDebounced(settings.coverage, SLIDER_DELAY);
  const scheme = useScheme();
  const typeColours = useObjectTypeColours(ocelId);
  const params = useMemo(
    () => ({ ...filter, coverage: coverage / 100, quantities: settings.quantities }),
    [filter, coverage, settings.quantities],
  );
  const query = useGetTransformationTypeGraph(ocelId, params, { request: listRequest, query: { placeholderData: (previous) => previous } });
  const data = query.data;
  const { layout: flow, error: layoutError } = useKeptLayout(
    `transformations.graph.layout.${ocelId}`,
    [data, settings.layout, scheme, typeColours, settings.frequencies, settings.lifetime],
    () =>
      layoutTypeGraph(
        data!,
        settings.layout,
        typeColours.colours,
        typeColours.exportColours,
        {
          frequencies: settings.frequencies,
          lifetime: settings.lifetime,
        },
        scheme,
      ),
    !!data && typeColours.loaded,
  );
  const { skipFit, ...viewport } = useKeptViewport(`transformations.graph.viewport.${ocelId}`, flow);
  const set = (change: Partial<GraphSettings>) => setSettings((s) => ({ ...DEFAULTS, ...s, ...change }));

  return (
    <Stack gap={6}>
      <Group gap="xl" align="flex-end" wrap="wrap">
        <Box w={320}>
          <Tooltip
            label="Recipes are ranked by frequency; the most frequent ones are shown until they cover this share of the transformation events. Recipes as frequent as the last one shown are shown too, so the slider sets a minimum frequency."
            multiline
            maw={360}
            withArrow
            openDelay={300}
          >
            <Text size="xs" fw={500}>
              Recipes: {settings.coverage} % of the transformation events
            </Text>
          </Tooltip>
          <Slider
            size="sm"
            min={0}
            max={100}
            step={1}
            marks={MARKS}
            value={settings.coverage}
            onChange={(coverage) => set({ coverage })}
            label={(v) => `${v} %`}
            mb="md"
          />
        </Box>
        <div>
          <Tooltip
            label="exact: a recipe is activity, input and output with quantities (as in the concept). as sets: quantities are ignored, so recipes that differ only in quantities are merged; arcs then show the smallest and largest quantity."
            multiline
            maw={360}
            withArrow
            openDelay={300}
          >
            <Text size="xs" fw={500}>
              Quantities
            </Text>
          </Tooltip>
          <SegmentedControl
            size="xs"
            value={settings.quantities}
            onChange={(v) => set({ quantities: v as GetTransformationTypeGraphQuantities })}
            data={[
              { value: "exact", label: "exact" },
              { value: "sets", label: "as sets" },
            ]}
          />
        </div>
        <div>
          <Text size="xs" fw={500}>
            Layout
          </Text>
          <SegmentedControl
            size="xs"
            value={settings.layout}
            onChange={(v) => set({ layout: v as "RIGHT" | "DOWN" })}
            data={[
              { value: "RIGHT", label: "left to right" },
              { value: "DOWN", label: "top to bottom" },
            ]}
          />
        </div>
        <div>
          <Tooltip
            label="Lifetime of the handling units of a type with a full lifecycle (produced and finally consumed in the log): from production to final consumption. Median, and optionally the interval [Q1, Q3] of the first and third quartile. Over the whole log, not only the shown recipes."
            multiline
            maw={360}
            withArrow
            openDelay={300}
          >
            <Text size="xs" fw={500}>
              Lifetime
            </Text>
          </Tooltip>
          <SegmentedControl
            size="xs"
            value={settings.lifetime}
            onChange={(v) => set({ lifetime: v as Lifetime })}
            data={[
              { value: "off", label: "off" },
              { value: "median", label: "median" },
              { value: "quartiles", label: "median + [Q1, Q3]" },
            ]}
          />
        </div>
        <Checkbox
          size="xs"
          mb={6}
          label="Recipe frequencies"
          checked={settings.frequencies}
          onChange={(e) => set({ frequencies: e.currentTarget.checked })}
        />
      </Group>
      {data && (
        <Text size="xs" c="dimmed">
          {num(data.recipes.length)} of {num(data.recipes_total)} recipes (at least {num(data.min_frequency)}{" "}
          {data.min_frequency === 1 ? "event" : "events"} each) · {num(data.events_shown)} of {num(data.events_total)} transformation events (
          {pct(data.events_shown / Math.max(data.events_total, 1))})
        </Text>
      )}
      <Text fz={11} lh={1.3} c="dimmed">
        Ellipse: object type with its handling units with a full lifecycle (produced and finally consumed in the log) ·
        rectangle: recipe (shaded per activity; activity{settings.frequencies ? ", frequency and share of the transformation events" : ""}; hover for
        input and output) · arrow object type → recipe: input, recipe → object type: output, labelled with the handling units per event,
        as wide as the handling units that flowed along it (hover the label)
      </Text>
      {query.isError ? (
        <Alert color="red">{errorText(query.error)}</Alert>
      ) : layoutError ? (
        <Alert color="red">Layout failed: {layoutError}</Alert>
      ) : !data || !flow ? (
        <Loader size="sm" />
      ) : !data.recipes.length ? (
        <Text size="xs" c="dimmed">
          No transformation events to show.
        </Text>
      ) : (
        <Box
          style={{
            height: HEIGHT,
            minHeight: 240,
            resize: "vertical",
            overflow: "hidden",
            border: "1px solid var(--mantine-color-default-border)",
            borderRadius: 8,
            opacity: query.isFetching ? 0.6 : 1,
          }}
        >
          <ReactFlowProvider>
            <ReactFlow
              nodes={flow.nodes}
              edges={flow.edges}
              nodeTypes={NODE_TYPES}
              edgeTypes={EDGE_TYPES}
              nodesConnectable={false}
              nodesDraggable={false}
              elementsSelectable={false}
              zoomOnDoubleClick={false}
              minZoom={0.05}
              maxZoom={3}
              {...viewport}
              fitViewOptions={{ padding: 0.1, maxZoom: 1 }}
            >
              <Controls showInteractive={false} />
              <GraphDownloadMenu
                scene={(legend) => typeGraphScene(typeDrawing(flow.nodes, flow.edges, [...typeColours.exportColours.keys()]), { legend })}
                fileName="transformation-type-graph"
                title="Transformation type graph"
                legendLabel="With legend (object types and symbols)"
              />
              <FitOnChange token={flow} skip={skipFit} />
            </ReactFlow>
          </ReactFlowProvider>
        </Box>
      )}
    </Stack>
  );
};
