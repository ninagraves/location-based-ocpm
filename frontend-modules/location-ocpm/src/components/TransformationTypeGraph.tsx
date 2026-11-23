// Transformation type graph of the transformations page (draft; concept: Lineage (DRAFT).md, "Transformation Type
// Level Model"): object types (ellipses) and recipes (rectangles), arcs object type → recipe (input) and recipe →
// object type (output) labelled with the quantity. A frequency slider hides rare recipes. Laid out with ELK and drawn
// with React Flow, as the lineage chart. Documented in docs/pages/transformations.md, section "Transformation type graph".
import { Alert, Box, Group, Loader, SegmentedControl, Slider, Stack, Text, Tooltip } from "@mantine/core";
import {
  BaseEdge,
  Controls,
  type Edge,
  type EdgeProps,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
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
  useGetTransformationTypeGraph,
} from "../api/locationBasedOcpm";
import { ELK_OPTIONS, sectionPath, textWidth } from "../lib/dfgLayout";
import { errorText } from "../lib/errors";
import { num, pct } from "../lib/format";
import { useKeptLayout, useKeptViewport } from "../lib/keptView";
import { usePageState } from "../lib/pageState";
import { colourMap, OTHER, type Scheme } from "../lib/palette";
import { KIND_LABELS, listRequest, type TransformationFilter } from "../lib/transformations";
import { useDebounced } from "../lib/useDebounced";
import { useScheme } from "./plots";

/** Settings of the type graph (kept per log). */
type GraphSettings = {
  /** Slider value in percent: share of the transformation events the shown recipes cover. */
  coverage: number;
  quantities: GetTransformationTypeGraphQuantities;
  layout: "RIGHT" | "DOWN";
};

const DEFAULTS: GraphSettings = { coverage: 100, quantities: "exact", layout: "RIGHT" };
/** The slider recalculates the graph this long after the last change (ms). */
const SLIDER_DELAY = 400;
/** Sizes of the drawing in pixels. */
const SIZE = { font: 12, small: 10, padX: 10, typeHeight: 36, recipeHeight: 38, minWidth: 60, minArc: 1.2, maxArc: 8 };
const HEIGHT = 520;

type TypeData = { kind: "type"; objectType: string; consumed: number; produced: number; width: number; height: number; colour: string };
type RecipeData = {
  kind: "recipe";
  id: string;
  recipe: string;
  activity: string;
  frequency: number;
  share: number;
  recipeKind: string;
  width: number;
  height: number;
};
type NodeData = TypeData | RecipeData;
type EdgeData = {
  path: string;
  colour: string;
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

/** An object type: ellipse in the colour of the type. */
const TypeNodeView = memo(({ data }: NodeProps<Node<TypeData>>) => (
  <Tooltip label={`${data.objectType}: ${num(data.consumed)} handling units consumed, ${num(data.produced)} produced by the shown recipes`} withinPortal>
    <Box
      style={{
        width: data.width,
        height: data.height,
        borderRadius: "50%",
        border: `1.5px solid ${data.colour}`,
        background: `${data.colour}26`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Handles />
      <Text fz={SIZE.font} fw={600}>
        {data.objectType}
      </Text>
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
        background: "var(--mantine-color-body)",
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
      <Text fz={SIZE.small} c="dimmed">
        {num(data.frequency)}× · {pct(data.share)}
      </Text>
    </Box>
  </Tooltip>
));

/** An arc: ELK's route, width by the handling units that flowed along it, labelled with the quantity. */
const ArcView = memo(({ id, data, markerEnd }: EdgeProps<Edge<EdgeData>>) => {
  if (!data?.path) return null;
  return (
    <>
      <BaseEdge id={id} path={data.path} markerEnd={markerEnd} style={{ stroke: data.colour, strokeWidth: data.width, strokeOpacity: 0.85 }} />
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
 * Lay out the type graph with ELK (layered, Ocelescope's DFG options) and turn it into React Flow nodes and edges.
 *
 * @param graph The graph from the backend.
 * @param direction Layout direction.
 * @param scheme Colour scheme (object type colours, ranked by the handling units of the type in the graph).
 */
const layoutTypeGraph = async (graph: TypeGraph, direction: "RIGHT" | "DOWN", scheme: Scheme) => {
  const ranked = [...graph.object_types].sort((a, b) => b.consumed + b.produced - (a.consumed + a.produced) || a.object_type.localeCompare(b.object_type));
  const colours = colourMap(
    ranked.map((t) => t.object_type),
    scheme,
  );
  const sizes = new Map<string, { width: number; height: number }>();
  for (const t of graph.object_types)
    sizes.set(t.node, { width: Math.ceil(Math.max(SIZE.minWidth, textWidth(t.object_type, SIZE.font, 600) + 2 * SIZE.padX) * 1.3), height: SIZE.typeHeight });
  for (const r of graph.recipes)
    sizes.set(r.node, {
      width: Math.ceil(Math.max(SIZE.minWidth, textWidth(r.activity, SIZE.font, 600), textWidth(`${r.frequency}× · 100 %`, SIZE.small)) + 2 * SIZE.padX),
      height: SIZE.recipeHeight,
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
        consumed: t.consumed,
        produced: t.produced,
        colour: colours.get(t.object_type) ?? OTHER[scheme],
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
        ...(sizes.get(r.node) as { width: number; height: number }),
      },
      style: { pointerEvents: "all" as const },
    })),
  ].map((n) => ({ ...n, draggable: false, connectable: false }));
  const edges: Edge<EdgeData>[] = graph.arcs.map((a, i) => {
    const r = routed.get(`a${i}`);
    const section = r?.sections?.[0];
    const label = r?.labels?.[0];
    const colour = colours.get(a.object_type) ?? OTHER[scheme];
    const recipe = recipes.get(a.recipe);
    const events = recipe?.frequency ?? 0;
    return {
      id: `a${i}`,
      source: a.source,
      target: a.target,
      type: "arc",
      data: {
        path: section ? sectionPath(section) : "",
        colour,
        width: SIZE.minArc + ((SIZE.maxArc - SIZE.minArc) * a.hus) / maxHus,
        label: quantityLabel(a),
        hover: `${recipe?.recipe ?? a.recipe}: ${quantityLabel(a)} ${a.object_type} per event ${a.role === "consumed" ? "consumed" : "produced"}; ${num(a.hus)} handling units over ${num(events)} events`,
        labelPosition: label?.x != null && label?.y != null ? { x: label.x + (label.width ?? 0) / 2, y: label.y + (label.height ?? 0) / 2 } : null,
      },
      markerEnd: { type: MarkerType.ArrowClosed, color: colour, width: 18, height: 18, markerUnits: "userSpaceOnUse" },
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

/** The slider's marks: 0, 50 and 100 %. */
const MARKS = [0, 50, 100].map((value) => ({ value, label: `${value} %` }));

/**
 * The transformation type graph with its settings: frequency slider, quantities (exact | as sets) and layout.
 *
 * @param ocelId Id of the log.
 * @param filter The page filters (select whole transformation events).
 */
export const TransformationTypeGraph = ({ ocelId, filter }: { ocelId: string; filter: TransformationFilter }) => {
  const [settings, setSettings] = usePageState<GraphSettings>(`transformations.graph.${ocelId}`, DEFAULTS);
  const [coverage] = useDebounced(settings.coverage, SLIDER_DELAY);
  const scheme = useScheme();
  const params = useMemo(
    () => ({ ...filter, coverage: coverage / 100, quantities: settings.quantities }),
    [filter, coverage, settings.quantities],
  );
  const query = useGetTransformationTypeGraph(ocelId, params, { request: listRequest, query: { placeholderData: (previous) => previous } });
  const data = query.data;
  const { layout: flow, error: layoutError } = useKeptLayout(
    `transformations.graph.layout.${ocelId}`,
    [data, settings.layout, scheme],
    () => layoutTypeGraph(data!, settings.layout, scheme),
    !!data,
  );
  const { skipFit, ...viewport } = useKeptViewport(`transformations.graph.viewport.${ocelId}`, flow);
  const set = (change: Partial<GraphSettings>) => setSettings((s) => ({ ...s, ...change }));

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
      </Group>
      {data && (
        <Text size="xs" c="dimmed">
          {num(data.recipes.length)} of {num(data.recipes_total)} recipes (at least {num(data.min_frequency)}{" "}
          {data.min_frequency === 1 ? "event" : "events"} each) · {num(data.events_shown)} of {num(data.events_total)} transformation events (
          {pct(data.events_shown / Math.max(data.events_total, 1))})
        </Text>
      )}
      <Text fz={11} lh={1.3} c="dimmed">
        Ellipse: object type · rectangle: recipe (activity, frequency and share of the transformation events; hover for input
        and output) · arrow object type → recipe: input, recipe → object type: output, labelled with the handling units per event,
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
              <FitOnChange token={flow} skip={skipFit} />
            </ReactFlow>
          </ReactFlowProvider>
        </Box>
      )}
    </Stack>
  );
};
