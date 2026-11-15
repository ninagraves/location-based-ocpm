// Lineage chart of the instance page: the lineage graph of the selected handling units, laid out with ELK and drawn
// with React Flow (as the directly-follows graph). Documented in docs/pages/instances.md, section "Lineage".
import { Alert, Box, Checkbox, Group, Loader, SegmentedControl, Select, Stack, Text, Tooltip } from "@mantine/core";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
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
import { memo, useEffect, useMemo, useState } from "react";
import {
  getSelectionLineage,
  type LineageEdge,
  type LineageNode,
  type LineageRequestDirection,
  type LineageResponse,
} from "../api/locationBasedOcpm";
import { ELK_OPTIONS, sectionPath, textWidth } from "../lib/dfgLayout";
import { errorText } from "../lib/errors";
import { OTHER } from "../lib/palette";
import { useScheme } from "./plots";

/** Settings of the lineage chart (kept per log). */
export type LineageSettings = {
  direction: LineageRequestDirection;
  /** Generations per direction; "all" = no limit. */
  generations: string;
  withEvents: boolean;
  withSiblings: boolean;
  layout: "RIGHT" | "DOWN";
};

/** Defaults: both directions, two generations, object graph without siblings, left to right. */
export const DEFAULT_LINEAGE: LineageSettings = {
  direction: "both",
  generations: "2",
  withEvents: false,
  withSiblings: false,
  layout: "RIGHT",
};

const GENERATIONS = [...Array.from({ length: 10 }, (_, i) => String(i + 1)), "all"];
/** Sizes of the drawing in pixels. */
const SIZE = { font: 12, small: 10, padX: 10, padY: 6, minWidth: 64, height: 40, eventHeight: 36 };
const HEIGHT = 420;

// A mapped copy of LineageNode (an interface has no index signature, which React Flow's node data needs).
type NodeData = { [K in keyof LineageNode]: LineageNode[K] } & { width: number; height: number; colour: string; onPick?: (hu: string) => void };
type EdgeData = { path: string; dashed: boolean; label: string | null; labelPosition: { x: number; y: number } | null; colour: string };

const Handles = () => (
  <>
    <Handle type="target" position={Position.Left} style={{ opacity: 0, pointerEvents: "none" }} />
    <Handle type="source" position={Position.Right} style={{ opacity: 0, pointerEvents: "none" }} />
  </>
);

/** A handling unit: id and object type, filled in the colour of its type; selected ones with a thick border, siblings grey and dashed. */
const ObjectNode = memo(({ data }: NodeProps<Node<NodeData>>) => {
  const sibling = data.role === "sibling";
  const focal = data.role === "focal";
  return (
    <Tooltip
      label={`${data.node} (${data.object_type ?? "?"})${focal ? ", selected" : sibling ? ", sibling" : ""}${data.onPick && !focal ? " · click to select" : ""}`}
      withinPortal
    >
      <Box
        onClick={() => data.onPick?.(data.node)}
        style={{
          width: data.width,
          height: data.height,
          borderRadius: data.height / 2,
          border: `${focal ? 3 : 1.5}px ${sibling ? "dashed" : "solid"} ${focal ? "var(--mantine-color-text)" : data.colour}`,
          background: `${data.colour}26`,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          lineHeight: 1.1,
          cursor: data.onPick && !focal ? "pointer" : "default",
          opacity: sibling ? 0.7 : 1,
        }}
      >
        <Handles />
        <Text fz={SIZE.font} fw={focal ? 700 : 500}>{data.node}</Text>
        <Text fz={SIZE.small} c="dimmed">{data.object_type}</Text>
      </Box>
    </Tooltip>
  );
});

/** A transformation event (bipartite graph): event id and activity in a white box. */
const EventNode = memo(({ data }: NodeProps<Node<NodeData>>) => (
  <Tooltip label={`${data.node}: ${data.activity ?? ""}, ${data.time ?? ""}`} withinPortal>
    <Box
      style={{
        width: data.width,
        height: data.height,
        borderRadius: 3,
        border: `1px ${data.role === "sibling" ? "dashed" : "solid"} var(--mantine-color-gray-6)`,
        background: "var(--mantine-color-body)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        lineHeight: 1.1,
      }}
    >
      <Handles />
      <Text fz={SIZE.small} fw={600}>{data.node}</Text>
      <Text fz={SIZE.small}>{data.activity}</Text>
    </Box>
  </Tooltip>
));

/** An edge: ELK's route, solid with an arrow (lineage) or dashed (sibling edge of the object graph), labelled with its event in the object graph. */
const LineageEdgeView = memo(({ id, data, markerEnd }: EdgeProps<Edge<EdgeData>>) => {
  if (!data?.path) return null;
  return (
    <>
      <BaseEdge
        id={id}
        path={data.path}
        markerEnd={markerEnd}
        style={{ stroke: data.colour, strokeWidth: 1.4, strokeDasharray: data.dashed ? "5 4" : undefined }}
      />
      {data.label && data.labelPosition && (
        <EdgeLabelRenderer>
          <Box
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${data.labelPosition.x}px, ${data.labelPosition.y}px)`,
              fontSize: SIZE.small,
              padding: "0 2px",
              background: "var(--mantine-color-body)",
              borderRadius: 3,
            }}
          >
            {data.label}
          </Box>
        </EdgeLabelRenderer>
      )}
    </>
  );
});

const NODE_TYPES = { object: ObjectNode, event: EventNode };
const EDGE_TYPES = { lineage: LineageEdgeView };
const elk = new ELK();

/** Width and height of a node: tight around its two lines of text. */
const nodeSize = (n: LineageNode) => {
  const lines = n.kind === "event" ? [n.node, n.activity ?? ""] : [n.node, n.object_type ?? ""];
  const width = Math.max(SIZE.minWidth, ...lines.map((l, i) => textWidth(l, i === 0 && n.kind === "object" ? SIZE.font : SIZE.small, 600))) + 2 * SIZE.padX;
  return { width: Math.ceil(n.kind === "object" ? width + SIZE.height / 2 : width), height: n.kind === "event" ? SIZE.eventHeight : SIZE.height };
};

/** Edge label: the transformation event of a lineage edge in the object graph, with its activity. */
const edgeLabel = (e: LineageEdge, withEvents: boolean) =>
  !withEvents && e.kind === "lineage" && e.event ? `${e.event} ${e.activity ?? ""}`.trim() : null;

/**
 * Lay out a lineage with ELK (layered, Ocelescope's DFG options) and turn it into React Flow nodes and edges.
 *
 * @param lineage The lineage from the backend.
 * @param colours Colour per object type.
 * @param withEvents Bipartite graph (edge labels only in the object graph).
 * @param direction Layout direction.
 * @param edgeColour Colour of the edges.
 * @param grey Colour of siblings and sibling edges.
 * @param onPick Called with a handling unit when its node is clicked.
 */
const layoutLineage = async (
  lineage: LineageResponse,
  colours: Map<string, string>,
  withEvents: boolean,
  direction: "RIGHT" | "DOWN",
  edgeColour: string,
  grey: string,
  onPick?: (hu: string) => void,
) => {
  const sizes = new Map(lineage.nodes.map((n) => [n.node, nodeSize(n)]));
  const root: ElkNode = {
    id: "root",
    layoutOptions: { ...ELK_OPTIONS, "elk.direction": direction },
    children: lineage.nodes.map((n) => ({ id: n.node, ...sizes.get(n.node) })),
    edges: lineage.edges.map((e, i) => {
      const label = edgeLabel(e, withEvents);
      return {
        id: `e${i}`,
        sources: [e.source],
        targets: [e.target],
        labels: label ? [{ text: label, width: textWidth(label, SIZE.small) + 6, height: SIZE.small + 2 }] : [],
      };
    }),
  };
  const result = await elk.layout(root);
  const position = new Map((result.children ?? []).map((n) => [n.id, { x: n.x ?? 0, y: n.y ?? 0 }]));
  const routed = new Map((result.edges ?? []).map((e) => [e.id, e]));
  const nodes: Node<NodeData>[] = lineage.nodes.map((n) => {
    const colour = n.role === "sibling" ? grey : (colours.get(n.object_type ?? "") ?? grey);
    return {
      id: n.node,
      type: n.kind,
      position: position.get(n.node) ?? { x: 0, y: 0 },
      data: { ...n, ...(sizes.get(n.node) as { width: number; height: number }), colour, onPick: n.kind === "object" ? onPick : undefined },
      draggable: false,
      connectable: false,
    };
  });
  const edges: Edge<EdgeData>[] = lineage.edges.map((e, i) => {
    const r = routed.get(`e${i}`);
    const section = r?.sections?.[0];
    const label = r?.labels?.[0];
    const dashed = e.kind === "sibling";
    return {
      id: `e${i}`,
      source: e.source,
      target: e.target,
      type: "lineage",
      data: {
        path: section ? sectionPath(section) : "",
        dashed,
        colour: dashed ? grey : edgeColour,
        label: edgeLabel(e, withEvents),
        labelPosition:
          label?.x != null && label?.y != null ? { x: label.x + (label.width ?? 0) / 2, y: label.y + (label.height ?? 0) / 2 } : null,
      },
      markerEnd: e.directed
        ? { type: MarkerType.ArrowClosed, color: dashed ? grey : edgeColour, width: 24, height: 24, markerUnits: "userSpaceOnUse" }
        : undefined,
    };
  });
  return { nodes, edges };
};

const FitOnChange = ({ token }: { token: unknown }) => {
  const { fitView } = useReactFlow();
  useEffect(() => {
    requestAnimationFrame(() => fitView({ padding: 0.1, maxZoom: 1 }));
  }, [token, fitView]);
  return null;
};

/** The legend, in grey above the graph. */
const Legend = ({ withEvents }: { withEvents: boolean }) => (
  <Text fz={11} lh={1.3} c="dimmed">
    Rounded box: handling unit in the colour of its object type (thick border: selected; grey and dashed: sibling, i.e. produced
    together with a handling unit of the lineage) · arrow: component → product
    {withEvents ? " via the transformation event (white box)" : ", labelled with the transformation event"}
    {withEvents ? "" : " · dashed line: siblings"} · click a handling unit to add it to the selection
  </Text>
);

/**
 * The settings row of the lineage chart.
 *
 * @param settings Current settings.
 * @param onChange Called with the changed settings.
 */
export const LineageSettingsRow = ({ settings, onChange }: { settings: LineageSettings; onChange: (s: LineageSettings) => void }) => (
  <Group gap="md" align="flex-end">
    <div>
      <Text size="xs" fw={500}>Direction</Text>
      <SegmentedControl
        size="xs"
        value={settings.direction}
        onChange={(v) => onChange({ ...settings, direction: v as LineageRequestDirection })}
        data={[
          { value: "components", label: "components" },
          { value: "products", label: "products" },
          { value: "both", label: "both" },
        ]}
      />
    </div>
    <Select
      size="xs"
      label="Generations"
      data={GENERATIONS}
      value={settings.generations}
      onChange={(v) => onChange({ ...settings, generations: v ?? "2" })}
      allowDeselect={false}
      w={80}
    />
    <Checkbox size="xs" label="Transformation events" checked={settings.withEvents} onChange={(e) => onChange({ ...settings, withEvents: e.currentTarget.checked })} />
    <Checkbox size="xs" label="Siblings" checked={settings.withSiblings} onChange={(e) => onChange({ ...settings, withSiblings: e.currentTarget.checked })} />
    <div>
      <Text size="xs" fw={500}>Layout</Text>
      <SegmentedControl
        size="xs"
        value={settings.layout}
        onChange={(v) => onChange({ ...settings, layout: v as "RIGHT" | "DOWN" })}
        data={[
          { value: "RIGHT", label: "left to right" },
          { value: "DOWN", label: "top to bottom" },
        ]}
      />
    </div>
  </Group>
);

/** Request of the lineage chart. */
const toRequest = (handlingUnits: string[], s: LineageSettings) => ({
  handling_units: handlingUnits,
  direction: s.direction,
  generations: s.generations === "all" ? null : Number(s.generations),
  with_events: s.withEvents,
  with_siblings: s.withSiblings,
});

/** Fetch the lineage of the selected handling units with the given settings (shared with the HU timeline). */
export const useSelectionLineage = (ocelId: string, handlingUnits: string[], settings: LineageSettings) => {
  const request = useMemo(() => toRequest(handlingUnits, settings), [handlingUnits, settings]);
  return useQuery({
    queryKey: ["locationBasedOcpm", "instances", "lineage", ocelId, request],
    queryFn: ({ signal }) => getSelectionLineage(ocelId, request, undefined, undefined, signal),
    enabled: handlingUnits.length > 0,
    placeholderData: keepPreviousData,
  });
};

/**
 * The lineage chart: graph of the loaded lineage (settings in the row above, see `LineageSettingsRow`).
 *
 * @param query The query of the lineage (`useSelectionLineage`).
 * @param colours Colour per object type (all object types of the log, so colours stay fixed).
 * @param settings The settings (for the shape of the graph).
 * @param onPick Called with a handling unit clicked in the graph.
 */
export const LineageChart = ({
  query,
  colours,
  settings,
  onPick,
}: {
  query: ReturnType<typeof useSelectionLineage>;
  colours: Map<string, string>;
  settings: LineageSettings;
  onPick: (hu: string) => void;
}) => {
  const scheme = useScheme();
  const [flow, setFlow] = useState<Awaited<ReturnType<typeof layoutLineage>> | null>(null);
  const [layoutError, setLayoutError] = useState<string | null>(null);
  const data = query.data;
  useEffect(() => {
    if (!data) return;
    let cancelled = false;
    layoutLineage(data, colours, settings.withEvents, settings.layout, scheme === "dark" ? "#909296" : "#666666", OTHER[scheme], onPick).then(
      (f) => !cancelled && setFlow(f),
      (e: unknown) => !cancelled && setLayoutError(String(e)),
    );
    return () => {
      cancelled = true;
    };
  }, [data, colours, settings.withEvents, settings.layout, scheme, onPick]);

  if (query.isError) return <Alert color="red">{errorText(query.error)}</Alert>;
  if (layoutError) return <Alert color="red">Layout failed: {layoutError}</Alert>;
  if (!data || !flow) return <Loader size="sm" />;
  const lonely = data.edges.length === 0;
  return (
    <Stack gap={4}>
      <Legend withEvents={settings.withEvents} />
      {data.notes.length > 0 && <Text size="xs" c="dimmed">{data.notes.join(" ")}</Text>}
      {lonely && (
        <Text size="xs" c="dimmed">
          The selected handling units have no {settings.direction === "both" ? "components or products" : settings.direction} in the log.
        </Text>
      )}
      {/* Resizable at the bottom edge (drag the corner); React Flow follows the new size. */}
      <Box style={{ height: HEIGHT, minHeight: 200, resize: "vertical", overflow: "hidden", border: "1px solid var(--mantine-color-default-border)", borderRadius: 8, opacity: query.isFetching ? 0.6 : 1 }}>
        <ReactFlowProvider>
          <ReactFlow
            nodes={flow.nodes}
            edges={flow.edges}
            nodeTypes={NODE_TYPES}
            edgeTypes={EDGE_TYPES}
            nodesConnectable={false}
            nodesDraggable={false}
            elementsSelectable={false}
            minZoom={0.05}
            maxZoom={3}
            fitView
            fitViewOptions={{ padding: 0.1, maxZoom: 1 }}
          >
            <Controls showInteractive={false} />
            <FitOnChange token={flow} />
          </ReactFlow>
        </ReactFlowProvider>
      </Box>
    </Stack>
  );
};
