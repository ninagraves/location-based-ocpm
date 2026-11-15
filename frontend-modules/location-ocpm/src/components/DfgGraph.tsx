// The drawing of the directly-follows graph: ELK layout (lib/dfgLayout.ts), rendered with React Flow so that
// it can be panned and zoomed, and its nodes dragged (the arcs follow; Nina, 2026-11-15). Documented in docs/pages/directly-follows-graph.md.
import { Alert, Box, Group, Loader, Stack, Text, Tooltip } from "@mantine/core";
import {
  applyNodeChanges,
  BaseEdge,
  Controls,
  type Edge,
  type EdgeProps,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  type Node,
  type NodeChange,
  type NodeProps,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import { memo, useCallback, useEffect, useMemo, useState } from "react";
import type { DirectlyFollowsGraph } from "../api/locationBasedOcpm";
import {
  type ActivityNodeData,
  type ArcLabel,
  type Direction,
  type LaidOutArc,
  type Layout,
  layoutGraph,
  SIZES,
  type TerminalNodeData,
} from "../lib/dfgLayout";
import { num } from "../lib/format";

type NodeData = (ActivityNodeData | TerminalNodeData) & { colours: Map<string, string> };
type ArcData = LaidOutArc & { colour: string; width: number; onRemove?: (arc: LaidOutArc) => void };

/** Invisible handles: React Flow needs them to draw an edge, the path itself comes from ELK. */
const Handles = () => (
  <>
    <Handle type="target" position={Position.Left} style={{ opacity: 0, pointerEvents: "none" }} />
    <Handle type="source" position={Position.Right} style={{ opacity: 0, pointerEvents: "none" }} />
  </>
);

/** Hover text of an activity node: frequency, events in the log, and the object types involved. */
const activityTooltip = (d: ActivityNodeData) => (
  <Stack gap={2}>
    <Text size="xs" fw={600}>{d.activity}</Text>
    <Text size="xs">
      {num(d.events)} events shown{d.logEvents !== d.events ? ` (of ${num(d.logEvents)} in the log)` : ""}
    </Text>
    {d.involved.map((t) => (
      <Text size="xs" key={t.objectType}>
        {t.objectType}{t.selected ? "" : " (not selected)"}: {num(t.events)} events, {num(t.objects)} objects
      </Text>
    ))}
  </Stack>
);

/** Activity node: full name (wrapped, never cut), below it the frequency followed by a circle per involved type that is not selected. */
const ActivityNode = memo(({ data }: NodeProps<Node<NodeData>>) => {
  const d = data as ActivityNodeData & { colours: Map<string, string> };
  const circles = d.involved.filter((t) => !t.selected);
  return (
    <Tooltip label={activityTooltip(d)} withinPortal openDelay={300} multiline>
      <Box
        style={{
          width: d.width,
          height: d.height,
          padding: `${SIZES.padY}px ${SIZES.padX}px`,
          border: "1px solid var(--mantine-color-gray-7)",
          borderRadius: 4,
          background: "var(--mantine-color-body)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 0,
          boxSizing: "border-box",
        }}
      >
        <Handles />
        <Box style={{ fontSize: SIZES.nameFont, lineHeight: `${SIZES.nameLine}px`, fontWeight: d.nameWeight, textAlign: "center" }}>
          {d.lines.map((line) => (
            <div key={line}>{line}</div>
          ))}
        </Box>
        <Group gap={SIZES.circleGap} wrap="nowrap" align="center" justify="center">
          <Box style={{ fontSize: SIZES.frequencyFont, lineHeight: `${SIZES.frequencyFont + 3}px`, opacity: 0.7, marginRight: circles.length ? SIZES.circleGap : 0 }}>
            {num(d.events)}
          </Box>
          {circles.map((t) => (
            <Tooltip key={t.objectType} label={`${t.objectType}: ${num(t.events)} of ${num(d.events)} events, ${num(t.objects)} objects`} withinPortal>
              <Box
                style={{
                  width: SIZES.circle,
                  height: SIZES.circle,
                  borderRadius: "50%",
                  background: d.colours.get(t.objectType),
                  boxShadow: "0 0 0 0.5px var(--mantine-color-gray-6)",
                  flexShrink: 0,
                }}
              />
            </Tooltip>
          ))}
        </Group>
      </Box>
    </Tooltip>
  );
});

/** Start node (triangle) or end node (square) of an object type, filled with its colour, named below. */
const TerminalNode = memo(({ data }: NodeProps<Node<NodeData>>) => {
  const d = data as TerminalNodeData & { colours: Map<string, string> };
  const colour = d.colours.get(d.objectType);
  return (
    <Box style={{ width: d.width, height: d.height, position: "relative" }}>
      <Handles />
      <svg width={d.width} height={d.height} style={{ display: "block" }} role="img" aria-label={`${d.kind} ${d.objectType}`}>
        <circle cx={d.width / 2} cy={d.height / 2} r={d.width / 2 - 1} fill={colour} stroke="var(--mantine-color-text)" strokeWidth={1} />
        {d.kind === "start" ? (
          <path d={`M ${d.width * 0.4} ${d.height * 0.3} L ${d.width * 0.7} ${d.height / 2} L ${d.width * 0.4} ${d.height * 0.7} Z`} fill="white" />
        ) : (
          <rect x={d.width * 0.33} y={d.height * 0.33} width={d.width * 0.34} height={d.height * 0.34} fill="white" />
        )}
      </svg>
      <Box
        style={{
          position: "absolute",
          top: d.height + 1,
          left: "50%",
          transform: "translateX(-50%)",
          fontSize: SIZES.smallFont,
          opacity: 0.8,
          whiteSpace: "nowrap",
        }}
      >
        {d.objectType}
      </Box>
    </Box>
  );
});

/**
 * Arc: ELK's route in the object type's colour (dashed if shown only because of "Stay connected"), with a small
 * plain label (count or objects) that interrupts the line. A right click on the arc or its label removes it.
 */
const ArcEdge = memo(({ id, data, markerEnd }: EdgeProps<Edge<ArcData>>) => {
  if (!data?.path) return null;
  const position = data.labelPosition;
  const hint = `${data.objectType}: ${num(data.count)} traversals, ${num(data.objects)} objects${data.connecting ? " (shown to stay connected)" : ""} · right click to remove`;
  return (
    <>
      <BaseEdge
        id={id}
        path={data.path}
        markerEnd={markerEnd}
        interactionWidth={12}
        style={{ stroke: data.colour, strokeWidth: data.width, strokeDasharray: data.connecting ? "5 3" : undefined }}
      />
      {position && (
        <EdgeLabelRenderer>
          <Tooltip label={hint} withinPortal>
            <Box
              className="nodrag nopan"
              onContextMenu={(e) => {
                e.preventDefault();
                data.onRemove?.(data);
              }}
              style={{
                position: "absolute",
                transform: `translate(-50%, -50%) translate(${position.x}px, ${position.y}px)`,
                fontSize: SIZES.smallFont,
                lineHeight: `${SIZES.smallFont + 2}px`,
                padding: "0 2px",
                borderRadius: 3,
                background: "var(--mantine-color-body)",
                pointerEvents: "all",
              }}
            >
              {data.label}
            </Box>
          </Tooltip>
        </EdgeLabelRenderer>
      )}
    </>
  );
});

/** Grey of start and end arcs. */
const GREY = "#9aa0a6";

/** The legend, in grey above the graph. */
const Legend = () => (
  <Text fz={11} lh={1.3} c="dimmed">
    ▶ / ■ in a circle: start / end of an object type (named below; arcs from and to them are grey) · coloured line:
    directly-follows arc of a selected object type (thicker = more traversals) · number on an arc: traversals or objects ·
    dashed: shown only to stay connected · number in an activity: its events on the included traces · small circle on an
    activity: an unselected object type involved in these events · right click on an arc: remove it · drag a node to
    move it (the arcs follow; positions reset when a setting changes)
  </Text>
);

const NODE_TYPES = { activity: ActivityNode, start: TerminalNode, end: TerminalNode };
const EDGE_TYPES = { arc: ArcEdge };

/** Stroke width of an arc: 1.2 to 4 px, by the square root of its traversals relative to the largest arc of its type. */
const strokeWidth = (count: number, max: number) => 1.2 + 2.8 * Math.sqrt(count / Math.max(max, 1));

/** React Flow nodes and edges of a layout. */
const toFlow = (layout: Layout, colours: Map<string, string>, onRemove?: (arc: LaidOutArc) => void) => {
  const maxCount = new Map<string, number>();
  for (const a of layout.arcs) maxCount.set(a.objectType, Math.max(maxCount.get(a.objectType) ?? 0, a.count));
  const nodes: Node<NodeData>[] = layout.nodes.map((n) => ({
    id: n.id,
    type: n.data.kind,
    position: { x: n.x, y: n.y },
    data: { ...n.data, colours },
    draggable: true,
    connectable: false,
  }));
  const edges: Edge<ArcData>[] = layout.arcs.map((a) => {
    // Start and end arcs are grey (Nina, 2026-11-14); the start and end nodes carry the type's colour.
    const terminal = a.source.startsWith("start:") || a.target.startsWith("end:");
    const colour = terminal ? GREY : (colours.get(a.objectType) ?? GREY);
    return {
      id: a.id,
      source: a.source,
      target: a.target,
      type: "arc",
      data: { ...a, colour, width: strokeWidth(a.count, maxCount.get(a.objectType) ?? 1), onRemove },
      // React Flow draws the arrow in a 20-unit box of which it fills 5: 30 px gives an arrow of about 8 px, whatever the stroke width.
      markerEnd: { type: MarkerType.ArrowClosed, color: colour, width: 30, height: 30, markerUnits: "userSpaceOnUse" },
    };
  });
  return { nodes, edges };
};

type Offset = { x: number; y: number };

/**
 * Bend an ELK path to dragged nodes: its first point moves with the source node, its last point with the target
 * node, and every point in between by the share of both given by its position along the path (so a path of a
 * self-loop, or of two nodes moved together, is simply shifted).
 * Example: "M 0,0 C 10,0 20,0 30,0" with the target moved by (0, 30) gives "M 0,0 C 10,10 20,20 30,30".
 *
 * @param path SVG path of absolute "x,y" points (`sectionPath` in lib/dfgLayout.ts).
 * @param source, target Offsets of the source and target nodes from their laid-out positions.
 * @returns The bent path.
 */
export const bendPath = (path: string, source: Offset, target: Offset) => {
  const points = path.match(/-?[\d.]+(?:e-?\d+)?,-?[\d.]+(?:e-?\d+)?/g) ?? [];
  let i = 0;
  return path.replace(/(-?[\d.]+(?:e-?\d+)?),(-?[\d.]+(?:e-?\d+)?)/g, (_, x: string, y: string) => {
    const t = points.length > 1 ? i / (points.length - 1) : 0;
    i += 1;
    const dx = source.x + (target.x - source.x) * t;
    const dy = source.y + (target.y - source.y) * t;
    return `${Number(x) + dx},${Number(y) + dy}`;
  });
};

/**
 * The edges for the current node positions: an edge whose nodes were not dragged is the laid-out one (same object,
 * so it is not drawn again); the others get a bent path (`bendPath`) and a label moved by the mean of both offsets.
 */
const followNodes = (edges: Edge<ArcData>[], offsets: Map<string, Offset>) =>
  edges.map((e) => {
    const zero = { x: 0, y: 0 };
    const source = offsets.get(e.source) ?? zero;
    const target = offsets.get(e.target) ?? zero;
    if (!e.data || (source.x === 0 && source.y === 0 && target.x === 0 && target.y === 0)) return e;
    const label = e.data.labelPosition;
    return {
      ...e,
      data: {
        ...e.data,
        path: bendPath(e.data.path, source, target),
        labelPosition: label ? { x: label.x + (source.x + target.x) / 2, y: label.y + (source.y + target.y) / 2 } : null,
      },
    };
  });

/** Fit the view whenever a new layout arrives. */
const FitOnChange = ({ layout }: { layout: Layout | null }) => {
  const { fitView } = useReactFlow();
  useEffect(() => {
    if (layout) requestAnimationFrame(() => fitView({ padding: 0.08, maxZoom: 1 }));
  }, [layout, fitView]);
  return null;
};

/**
 * The directly-follows graph, laid out with ELK and drawn with React Flow (pan, zoom, fit).
 *
 * @param graph The graph from the backend.
 * @param colours Colour per object type.
 * @param direction Layout direction (left to right or top to bottom).
 * @param arcLabel What the arc labels show: traversals (`count`) or distinct objects.
 * @param compact Compact layout (little white space, `COMPACT_OPTIONS`).
 * @param height Height of the drawing area in pixels.
 * @param onRemoveArc Called when the user right-clicks an arc (to remove it).
 */
export const DfgGraph = ({
  graph,
  colours,
  direction,
  arcLabel,
  compact,
  height,
  onRemoveArc,
}: {
  graph: DirectlyFollowsGraph;
  colours: Map<string, string>;
  direction: Direction;
  arcLabel: ArcLabel;
  compact: boolean;
  height: number;
  onRemoveArc?: (arc: LaidOutArc) => void;
}) => {
  const [layout, setLayout] = useState<Layout | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    setError(null);
    layoutGraph(graph, direction, arcLabel, compact).then(
      (result) => !cancelled && setLayout(result),
      (err: unknown) => !cancelled && setError(String(err)),
    );
    return () => {
      cancelled = true;
    };
  }, [graph, direction, arcLabel, compact]);
  const flow = useMemo(() => (layout ? toFlow(layout, colours, onRemoveArc) : null), [layout, colours, onRemoveArc]);
  // Dragged node positions, kept with the layout they belong to: a new layout (a setting changed) starts from its own positions.
  const [dragged, setDragged] = useState<{ flow: typeof flow; nodes: Node<NodeData>[] }>({ flow: null, nodes: [] });
  const nodes = useMemo(() => (dragged.flow === flow ? dragged.nodes : (flow?.nodes ?? [])), [dragged, flow]);
  const onNodesChange = useCallback(
    (changes: NodeChange<Node<NodeData>>[]) =>
      setDragged((d) => ({ flow, nodes: applyNodeChanges(changes, d.flow === flow ? d.nodes : (flow?.nodes ?? [])) })),
    [flow],
  );
  const edges = useMemo(() => {
    if (!flow) return [];
    const laidOut = new Map(flow.nodes.map((n) => [n.id, n.position]));
    const offsets = new Map<string, Offset>();
    for (const n of nodes) {
      const p = laidOut.get(n.id);
      if (p && (p.x !== n.position.x || p.y !== n.position.y)) offsets.set(n.id, { x: n.position.x - p.x, y: n.position.y - p.y });
    }
    return followNodes(flow.edges, offsets);
  }, [flow, nodes]);

  if (error) return <Alert color="red">Layout failed: {error}</Alert>;
  if (!flow) return <Loader size="sm" />;
  if (flow.nodes.length === 0)
    return <Alert color="gray">Nothing to show: select an object type, raise its variant or arc threshold, or restore removed arcs.</Alert>;
  return (
    <Stack gap={4}>
      <Legend />
    <Box style={{ height, border: "1px solid var(--mantine-color-default-border)", borderRadius: 8 }}>
      <ReactFlowProvider>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          nodeTypes={NODE_TYPES}
          edgeTypes={EDGE_TYPES}
          nodesConnectable={false}
          nodesDraggable
          elementsSelectable={false}
          minZoom={0.05}
          maxZoom={3}
          fitView
          fitViewOptions={{ padding: 0.08, maxZoom: 1 }}
          // Right click removes an arc (a left click is reserved for later interactions; Nina, 2026-11-15).
          onEdgeContextMenu={(event, edge) => {
            event.preventDefault();
            const data = edge.data as ArcData | undefined;
            if (data) onRemoveArc?.(data);
          }}
        >
          <Controls showInteractive={false} />
          <FitOnChange layout={layout} />
        </ReactFlow>
      </ReactFlowProvider>
    </Box>
    </Stack>
  );
};
