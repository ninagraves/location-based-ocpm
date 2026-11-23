// Object graph of the instance page: the selected handling units, every object related to them by a shared event or
// an o2o relation, and all arcs between these. The backend returns the whole graph once; object types and arc kinds
// are shown or hidden here. Optionally, the events of the selected handling units are drawn as boxes with an arc from
// every object they involve. Laid out with ELK (stress) and drawn with React Flow.
// Documented in docs/pages/instances.md, section "Object graph".
import { Alert, Box, Checkbox, Chip, Group, Loader, Stack, Text, Tooltip } from "@mantine/core";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  applyNodeChanges,
  Controls,
  type Edge,
  type EdgeProps,
  EdgeLabelRenderer,
  Handle,
  type Node,
  type NodeChange,
  type NodeProps,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import ELK, { type ElkNode } from "elkjs/lib/elk.bundled.js";
import { memo, useCallback, useEffect, useMemo, useState } from "react";
import {
  type EventArc,
  type FocalEvent,
  getObjectGraph,
  type O2oArc,
  type ObjectGraphNode,
  type ObjectGraphResponse,
} from "../api/locationBasedOcpm";
import { textWidth } from "../lib/dfgLayout";
import { errorText } from "../lib/errors";
import { useKeptLayout, useKeptViewport } from "../lib/keptView";
import { keep, recall } from "../lib/pageState";
import { OTHER, type Scheme, UI } from "../lib/palette";
import { useScheme } from "./plots";

/** Settings of the object graph (kept per log). */
export type ObjectGraphSettings = {
  /** Object types switched on or off by the user; types not listed: handling-unit types on, other types off. */
  types: Record<string, boolean>;
  /** Arcs for shared events. */
  eventArcs: boolean;
  /** Arcs for o2o relations. */
  o2oArcs: boolean;
  /** Arcs between two related objects (otherwise only arcs that touch a selected handling unit). */
  relatedArcs: boolean;
  /** Event ids on the event arcs, qualifiers on the o2o arcs. */
  labels: boolean;
  /** The events of the selected handling units as boxes, with an arc from every object they involve (their shared
   * events then leave the event arcs). */
  eventBoxes: boolean;
};

/** Defaults: handling units only, both arc kinds, all arcs, with labels, no event boxes. */
export const DEFAULT_OBJECT_GRAPH: ObjectGraphSettings = {
  types: {},
  eventArcs: true,
  o2oArcs: true,
  relatedArcs: true,
  labels: true,
  eventBoxes: false,
};

/** Sizes of the drawing in pixels. */
const SIZE = { font: 12, small: 10, padX: 10, minWidth: 64, height: 40, eventHeight: 34, arcGap: 44, edgeLength: 190 };
const HEIGHT = 460;
/** Event ids written on an event arc at most (the rest as "+ n"); events listed in the hover at most. */
const MAX_LABEL_EVENTS = 3;
const MAX_HOVER_EVENTS = 25;

/** Id of the node of an event box (prefixed, so that it cannot clash with an object id). */
const eventNodeId = (event: string) => `\u0001event:${event}`;

type ObjectData = { kind: "object" } & { [K in keyof ObjectGraphNode]: ObjectGraphNode[K] } & {
  width: number;
  height: number;
  colour: string;
  /** Set for handling units: called when their name is double-clicked. */
  onToggle?: (hu: string) => void;
};
type EventData = { kind: "event" } & { [K in keyof FocalEvent]: FocalEvent[K] } & { width: number; height: number };
type NodeData = ObjectData | EventData;
/** An arc from an object to the box of an event it is involved in. */
type E2oArc = { source: string; target: string; event: FocalEvent };
type Arc = { kind: "event"; arc: EventArc } | { kind: "o2o"; arc: O2oArc } | { kind: "e2o"; arc: E2oArc };
type EdgeData = { path: string; label: string | null; labelAt: { x: number; y: number }; arc: Arc; colour: string; width: number; arrow: string | null };

/** Is the object type shown? (handling-unit types on, others off, unless the user switched them.) */
const typeShown = (settings: ObjectGraphSettings, type: string, isHu: boolean) => settings.types[type] ?? isHu;

/** An object: id and object type in the colour of its type; handling units rounded, other objects square; selected ones with a thick border. */
const ObjectNode = memo(({ data }: NodeProps<Node<ObjectData>>) => {
  const focal = data.role === "focal";
  return (
    <Tooltip
      label={`${data.node} (${data.object_type ?? "?"}) · ${data.n_events} events${data.n_shared != null ? `, ${data.n_shared} shared with the selection` : ""}${focal ? " · selected, double-click the name to unselect" : data.is_hu ? " · double-click the name to select" : ""} · drag to move`}
      withinPortal
    >
      <Box
        style={{
          width: data.width,
          height: data.height,
          borderRadius: data.is_hu ? data.height / 2 : 4,
          border: `${focal ? 3 : 1.5}px solid ${focal ? "var(--mantine-color-text)" : data.colour}`,
          background: `color-mix(in srgb, ${data.colour} 15%, var(--mantine-color-body))`,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          lineHeight: 1.1,
          cursor: "grab",
        }}
      >
        {/* React Flow needs handles to draw an edge; the arcs are routed by `layoutGraph` and ignore them. */}
        <Handle type="target" position={Position.Left} style={{ opacity: 0, pointerEvents: "none" }} />
        <Handle type="source" position={Position.Right} style={{ opacity: 0, pointerEvents: "none" }} />
        {/* Only the name reacts to a double click (Nina, 2026-11-20); the rest of the box drags the node. */}
        <Text
          fz={SIZE.font}
          fw={focal ? 700 : 500}
          onDoubleClick={(e) => {
            e.stopPropagation();
            data.onToggle?.(data.node);
          }}
          style={data.onToggle ? { cursor: "pointer", textDecoration: "underline dotted", textUnderlineOffset: 2 } : undefined}
        >
          {data.node}
        </Text>
        <Text fz={SIZE.small} c="dimmed">{data.object_type}</Text>
      </Box>
    </Tooltip>
  );
});

/** An event of a selected handling unit (event boxes): event id and activity in a white box. */
const EventNode = memo(({ data }: NodeProps<Node<EventData>>) => (
  <Tooltip label={`${data.event} · ${formatTime(data.time)} · ${data.activity ?? ""} · ${data.objects.length} objects · drag to move`} withinPortal>
    <Box
      style={{
        width: data.width,
        height: data.height,
        borderRadius: 3,
        border: "1px solid var(--mantine-color-default-border)",
        background: "var(--mantine-color-body)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        lineHeight: 1.1,
        cursor: "grab",
      }}
    >
      <Handle type="target" position={Position.Left} style={{ opacity: 0, pointerEvents: "none" }} />
      <Handle type="source" position={Position.Right} style={{ opacity: 0, pointerEvents: "none" }} />
      <Text fz={SIZE.small} fw={600}>{data.event}</Text>
      <Text fz={SIZE.small} c="dimmed">{data.activity}</Text>
    </Box>
  </Tooltip>
));

/** Format a timestamp of the backend (ISO, UTC) as "YYYY-MM-DD HH:MM:SS". */
const formatTime = (t: string | null | undefined) => (t ? t.replace("T", " ").replace(/(\.\d+)?(Z|[+-]\d\d:\d\d)?$/, "") : "?");

/** Hover of an arc: the shared events (id, timestamp, activity) or the o2o relation. */
const arcHover = (arc: Arc) => {
  if (arc.kind === "o2o") return `${arc.arc.source} → ${arc.arc.target}: ${arc.arc.qualifier ?? "(no qualifier)"} (o2o)`;
  if (arc.kind === "e2o") return `${arc.arc.source} in ${arc.arc.event.event} · ${formatTime(arc.arc.event.time)} · ${arc.arc.event.activity ?? ""}`;
  const { events, source, target, n_events } = arc.arc;
  const lines = events.slice(0, MAX_HOVER_EVENTS).map((e) => `${e.event} · ${formatTime(e.time)} · ${e.activity ?? ""}`);
  if (n_events > MAX_HOVER_EVENTS) lines.push(`+ ${n_events - MAX_HOVER_EVENTS} more`);
  return (
    <Stack gap={0}>
      <Text fz={11} fw={600}>{`${source} – ${target}: ${n_events} shared event${n_events === 1 ? "" : "s"}`}</Text>
      {lines.map((l) => (
        <Text key={l} fz={11} ff="monospace">{l}</Text>
      ))}
    </Stack>
  );
};

/** Label of an arc: up to three event ids (event arc) or the qualifier (o2o arc). */
const arcLabel = (arc: Arc) => {
  if (arc.kind === "o2o") return arc.arc.qualifier ?? "";
  if (arc.kind === "e2o") return null;
  const ids = arc.arc.events.map((e) => e.event);
  return ids.length > MAX_LABEL_EVENTS ? `${ids.slice(0, MAX_LABEL_EVENTS).join(", ")} +${ids.length - MAX_LABEL_EVENTS}` : ids.join(", ");
};

/** An arc: a straight line or, for several arcs between the same two objects, a curve; o2o arcs dashed with an arrow. Hovering the label lists the events. */
const ArcView = memo(({ id, data }: EdgeProps<Edge<EdgeData>>) => {
  if (!data?.path) return null;
  const tooltip = arcHover(data.arc);
  return (
    <>
      <path
        id={id}
        d={data.path}
        fill="none"
        stroke={data.colour}
        strokeWidth={data.width}
        strokeDasharray={data.arc.kind === "o2o" ? "6 4" : undefined}
        markerEnd={data.arrow ? `url(#${data.arrow})` : undefined}
      />
      <EdgeLabelRenderer>
        <Tooltip label={tooltip} withinPortal multiline maw={420}>
          <Box
            className="nodrag nopan"
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${data.labelAt.x}px, ${data.labelAt.y}px)`,
              fontSize: SIZE.small,
              padding: data.label ? "0 3px" : 0,
              width: data.label ? undefined : 10,
              height: data.label ? undefined : 10,
              background: data.label ? "var(--mantine-color-body)" : "transparent",
              color: data.arc.kind === "o2o" ? data.colour : undefined,
              fontStyle: data.arc.kind === "o2o" ? "italic" : undefined,
              border: data.label ? `1px solid ${data.colour}55` : undefined,
              borderRadius: 3,
              pointerEvents: "all",
              cursor: "default",
              whiteSpace: "nowrap",
            }}
          >
            {data.label}
          </Box>
        </Tooltip>
      </EdgeLabelRenderer>
    </>
  );
});

const NODE_TYPES = { object: ObjectNode, event: EventNode };
const EDGE_TYPES = { arc: ArcView };
const elk = new ELK();

/** Width and height of an event box: tight around its id and activity. */
const eventSize = (e: FocalEvent) => ({
  width: Math.ceil(Math.max(textWidth(e.event, SIZE.small, 600), textWidth(e.activity ?? "", SIZE.small)) + 2 * SIZE.padX),
  height: SIZE.eventHeight,
});

/** Width and height of a node: tight around its id and object type. */
const nodeSize = (n: ObjectGraphNode) => {
  const width = Math.max(SIZE.minWidth, textWidth(n.node, SIZE.font, 600), textWidth(n.object_type ?? "", SIZE.small)) + 2 * SIZE.padX;
  return { width: Math.ceil(n.is_hu ? width + SIZE.height / 2 : width), height: SIZE.height };
};

/** The point where the line from the centre `c` of a w × h box towards `p` leaves the box. */
const clip = (c: { x: number; y: number }, p: { x: number; y: number }, w: number, h: number) => {
  const dx = p.x - c.x;
  const dy = p.y - c.y;
  const t = Math.min(dx ? w / 2 / Math.abs(dx) : Infinity, dy ? h / 2 / Math.abs(dy) : Infinity, 1);
  return { x: c.x + t * dx, y: c.y + t * dy };
};

/** The visible part of the graph under the settings. */
export const visibleGraph = (graph: ObjectGraphResponse, settings: ObjectGraphSettings) => {
  const nodes = graph.nodes.filter((n) => n.role === "focal" || typeShown(settings, n.object_type ?? "", n.is_hu));
  const ids = new Set(nodes.map((n) => n.node));
  const focal = new Set(nodes.filter((n) => n.role === "focal").map((n) => n.node));
  const keep = (a: { source: string; target: string }) =>
    ids.has(a.source) && ids.has(a.target) && (settings.relatedArcs || focal.has(a.source) || focal.has(a.target));
  // With event boxes, the events of the selection are boxes; event arcs keep only the other shared events.
  const events = settings.eventBoxes ? (graph.events ?? []) : [];
  const boxed = new Set(events.map((e) => e.event));
  const eventArcs = graph.event_arcs
    .filter(keep)
    .map((arc) => {
      if (!boxed.size) return arc;
      const rest = arc.events.filter((e) => !boxed.has(e.event));
      return { ...arc, events: rest, n_events: rest.length };
    })
    .filter((arc) => arc.n_events > 0);
  const arcs: Arc[] = [
    ...(settings.eventArcs ? eventArcs.map((arc) => ({ kind: "event" as const, arc })) : []),
    ...(settings.o2oArcs ? graph.o2o_arcs.filter(keep).map((arc) => ({ kind: "o2o" as const, arc })) : []),
    ...events.flatMap((event) =>
      event.objects.filter((o) => ids.has(o)).map((o) => ({ kind: "e2o" as const, arc: { source: o, target: eventNodeId(event.event), event } })),
    ),
  ];
  return { nodes, events, arcs };
};

/**
 * Lay out the visible graph with ELK (stress) and turn its objects into React Flow nodes (the arcs are routed from
 * the current node positions by `routeArcs`, so that they follow nodes the user drags).
 *
 * @param graph The visible part (`visibleGraph`).
 * @param colours Colour per object type.
 * @param scheme Colour scheme.
 * @param onToggle Given to the handling units, called when their name is double-clicked.
 */
const layoutGraph = async (
  graph: ReturnType<typeof visibleGraph>,
  colours: Map<string, string>,
  scheme: Scheme,
  onToggle?: (hu: string) => void,
) => {
  const sizes = new Map([
    ...graph.nodes.map((n) => [n.node, nodeSize(n)] as const),
    ...graph.events.map((e) => [eventNodeId(e.event), eventSize(e)] as const),
  ]);
  const root: ElkNode = {
    id: "root",
    layoutOptions: {
      "elk.algorithm": "stress",
      "elk.stress.desiredEdgeLength": String(SIZE.edgeLength),
      "elk.separateConnectedComponents": "true",
      "elk.spacing.componentComponent": "60",
    },
    children: [...sizes.entries()].map(([id, size]) => ({ id, ...size })),
    // One layout edge per pair of objects, so that several arcs between two objects do not pull them together.
    edges: [...new Set(graph.arcs.map(({ arc }) => [arc.source, arc.target].sort().join("\u0000")))].map((key, i) => {
      const [s, t] = key.split("\u0000");
      return { id: `l${i}`, sources: [s], targets: [t] };
    }),
  };
  const result = await elk.layout(root);
  const centre = new Map(
    (result.children ?? []).map((n) => [n.id, { x: (n.x ?? 0) + (n.width ?? 0) / 2, y: (n.y ?? 0) + (n.height ?? 0) / 2 }]),
  );
  const at = (id: string) => {
    const size = sizes.get(id) as { width: number; height: number };
    const c = centre.get(id) ?? { x: 0, y: 0 };
    return { size, position: { x: c.x - size.width / 2, y: c.y - size.height / 2 } };
  };
  const nodes: Node<NodeData>[] = [
    ...graph.nodes.map((n): Node<NodeData> => {
      const { size, position } = at(n.node);
      return {
        id: n.node,
        type: "object",
        position,
        data: { kind: "object", ...n, ...size, colour: colours.get(n.object_type ?? "") ?? OTHER[scheme], onToggle: n.is_hu ? onToggle : undefined },
        connectable: false,
      };
    }),
    ...graph.events.map((e): Node<NodeData> => {
      const id = eventNodeId(e.event);
      const { size, position } = at(id);
      return { id, type: "event", position, data: { kind: "event", ...e, ...size }, connectable: false };
    }),
  ];
  return { nodes, arcs: graph.arcs };
};

/**
 * Route the arcs between the current node positions: straight lines, or curves to both sides for several arcs between
 * the same two objects, clipped at the node boxes, with the label in the middle.
 *
 * @param arcs The visible arcs.
 * @param nodes The React Flow nodes (current positions, sizes in `data`).
 * @param labels Write event ids and qualifiers on the arcs.
 * @param scheme Colour scheme.
 */
const routeArcs = (arcs: Arc[], nodes: Node<NodeData>[], labels: boolean, scheme: Scheme): Edge<EdgeData>[] => {
  const centre = new Map(nodes.map((n) => [n.id, { x: n.position.x + n.data.width / 2, y: n.position.y + n.data.height / 2 }]));
  const sizes = new Map(nodes.map((n) => [n.id, { width: n.data.width, height: n.data.height }]));
  const graph = { arcs };
  // Arcs between the same two objects are spread as curves to both sides of the straight line.
  const groups = new Map<string, number[]>();
  graph.arcs.forEach(({ arc }, i) => {
    const key = [arc.source, arc.target].sort().join("\u0000");
    groups.set(key, [...(groups.get(key) ?? []), i]);
  });
  const eventColour = scheme === "dark" ? "#909296" : "#666666";
  const o2oColour = UI[scheme].accent;
  return graph.arcs.map((a, i) => {
    const { source, target } = a.arc;
    const [lo, hi] = [source, target].sort();
    const group = groups.get([lo, hi].join("\u0000")) ?? [i];
    const offset = (group.indexOf(i) - (group.length - 1) / 2) * SIZE.arcGap;
    const p = centre.get(lo) ?? { x: 0, y: 0 };
    const q = centre.get(hi) ?? { x: 0, y: 0 };
    const len = Math.hypot(q.x - p.x, q.y - p.y) || 1;
    const normal = { x: -(q.y - p.y) / len, y: (q.x - p.x) / len };
    // Control point of the quadratic curve (twice the offset, so that the curve's middle lies at the offset).
    const ctrl = { x: (p.x + q.x) / 2 + 2 * offset * normal.x, y: (p.y + q.y) / 2 + 2 * offset * normal.y };
    const [from, to] = source === lo ? [p, q] : [q, p];
    const sizeFrom = sizes.get(source) as { width: number; height: number };
    const sizeTo = sizes.get(target) as { width: number; height: number };
    const start = clip(from, offset ? ctrl : to, sizeFrom.width, sizeFrom.height);
    const end = clip(to, offset ? ctrl : from, sizeTo.width + 4, sizeTo.height + 4);
    const colour = a.kind === "o2o" ? o2oColour : eventColour;
    return {
      id: `a${i}`,
      source,
      target,
      type: "arc",
      data: {
        path: offset ? `M ${start.x} ${start.y} Q ${ctrl.x} ${ctrl.y} ${end.x} ${end.y}` : `M ${start.x} ${start.y} L ${end.x} ${end.y}`,
        label: labels ? arcLabel(a) : null,
        labelAt: { x: (p.x + q.x) / 2 + offset * normal.x, y: (p.y + q.y) / 2 + offset * normal.y },
        arc: a,
        colour,
        width: a.kind === "event" ? Math.min(1.2 + Math.log2(a.arc.n_events), 5) : a.kind === "e2o" ? 1.2 : 1.4,
        arrow: a.kind === "o2o" ? `og-arrow-${scheme}` : null,
      },
    };
  });
};

const FitOnChange = ({ token, skip }: { token: unknown; skip: (token: unknown) => boolean }) => {
  const { fitView } = useReactFlow();
  useEffect(() => {
    // Not for a layout whose zoom and pan were restored as the user left them.
    if (!skip(token)) requestAnimationFrame(() => fitView({ padding: 0.1, maxZoom: 1 }));
  }, [token, fitView, skip]);
  return null;
};

/** The legend, in grey above the graph. */
const Legend = () => (
  <Text fz={11} lh={1.3} c="dimmed">
    Rounded box: handling unit, square box: other object, in the colour of its object type (thick border: selected) · solid
    line: shared events, labelled with their ids (thicker: more events) · dashed arrow: o2o relation, labelled with its
    qualifier · hover a label for the events (id, timestamp, activity) · with "Events as boxes": white box = event of a selected handling
    unit, with a line to every object it involves · drag objects to move them · double-click the name of a handling unit to select or unselect it
  </Text>
);

/**
 * Settings row of the object graph: object types (with their number of objects) and arcs.
 *
 * @param graph The whole graph (for the object types).
 * @param colours Colour per object type.
 * @param settings Current settings.
 * @param onChange Called with the changed settings.
 */
const ObjectGraphSettingsRow = ({
  graph,
  colours,
  settings,
  onChange,
}: {
  graph: ObjectGraphResponse | undefined;
  colours: Map<string, string>;
  settings: ObjectGraphSettings;
  onChange: (s: ObjectGraphSettings) => void;
}) => {
  // Object types of the related objects: handling-unit types first, then by number of objects.
  const types = useMemo(() => {
    const count = new Map<string, { n: number; isHu: boolean }>();
    for (const n of graph?.nodes ?? []) {
      if (n.role === "focal") continue;
      const t = n.object_type ?? "";
      count.set(t, { n: (count.get(t)?.n ?? 0) + 1, isHu: n.is_hu });
    }
    return [...count.entries()].sort((a, b) => Number(b[1].isHu) - Number(a[1].isHu) || b[1].n - a[1].n || a[0].localeCompare(b[0]));
  }, [graph]);
  const shown = types.filter(([t, { isHu }]) => typeShown(settings, t, isHu)).map(([t]) => t);
  return (
    <Group gap="md" align="flex-end">
      <div>
        <Text size="xs" fw={500}>Related objects</Text>
        {types.length === 0 ? (
          <Text size="xs" c="dimmed">none</Text>
        ) : (
          <Chip.Group
            multiple
            value={shown}
            onChange={(v) => onChange({ ...settings, types: Object.fromEntries(types.map(([t]) => [t, v.includes(t)])) })}
          >
            <Group gap={4}>
              {types.map(([t, { n, isHu }]) => (
                <Chip key={t} value={t} size="xs" color={colours.get(t)} variant="filled">
                  {`${t} (${n})`}
                </Chip>
              ))}
            </Group>
          </Chip.Group>
        )}
      </div>
      <Checkbox size="xs" label="Shared events" checked={settings.eventArcs} onChange={(e) => onChange({ ...settings, eventArcs: e.currentTarget.checked })} />
      <Checkbox size="xs" label="O2O relations" checked={settings.o2oArcs} onChange={(e) => onChange({ ...settings, o2oArcs: e.currentTarget.checked })} />
      <Checkbox
        size="xs"
        label="Arcs between related objects"
        checked={settings.relatedArcs}
        onChange={(e) => onChange({ ...settings, relatedArcs: e.currentTarget.checked })}
      />
      <Checkbox size="xs" label="Labels" checked={settings.labels} onChange={(e) => onChange({ ...settings, labels: e.currentTarget.checked })} />
      <Checkbox
        size="xs"
        label="Events as boxes"
        checked={settings.eventBoxes}
        onChange={(e) => onChange({ ...settings, eventBoxes: e.currentTarget.checked })}
      />
    </Group>
  );
};

/** Fetch the object graph of the selected handling units (shared with the HU timeline's "add" button). */
export const useObjectGraph = (ocelId: string, handlingUnits: string[]) => {
  const request = useMemo(() => ({ handling_units: handlingUnits }), [handlingUnits]);
  return useQuery({
    queryKey: ["locationBasedOcpm", "instances", "objectGraph", ocelId, request],
    queryFn: ({ signal }) => getObjectGraph(ocelId, request, undefined, undefined, signal),
    enabled: handlingUnits.length > 0,
    placeholderData: keepPreviousData,
  });
};

/**
 * The object graph card's content: settings row and graph.
 *
 * @param ocelId The log.
 * @param handlingUnits The selected handling units.
 * @param colours Colour per object type (`useObjectTypeColours`, the same on every page).
 * @param settings The settings.
 * @param onChange Called with the changed settings.
 * @param onToggle Called with a handling unit whose name is double-clicked in the graph (selects or unselects it).
 * @param layoutKey Changing it lays the graph out again (drops dragged positions; "Reset settings").
 * @param stateKey Where the layout, the dragged positions and zoom and pan are kept (e.g.
 *   `instances.objectGraph.view.<log id>`), so that the graph looks as it was left when the page opens again with the
 *   same graph (`lib/keptView.ts`).
 */
export const ObjectGraphChart = ({
  layoutKey = 0,
  stateKey,
  ocelId,
  handlingUnits,
  colours,
  settings,
  onChange,
  onToggle,
}: {
  ocelId: string;
  handlingUnits: string[];
  colours: Map<string, string>;
  settings: ObjectGraphSettings;
  onChange: (s: ObjectGraphSettings) => void;
  onToggle: (hu: string) => void;
  layoutKey?: number;
  stateKey: string;
}) => {
  const scheme = useScheme();
  const query = useObjectGraph(ocelId, handlingUnits);
  const data = query.data;
  const visible = useMemo(() => (data ? visibleGraph(data, settings) : null), [data, settings]);
  // layoutKey only triggers a new layout.
  const { layout: flow, error: layoutError } = useKeptLayout(
    `${stateKey}.layout`,
    [visible, colours, scheme, onToggle, layoutKey],
    () => layoutGraph(visible!, colours, scheme, onToggle),
    !!visible,
  );
  // Nodes keep the positions the user dragged them to until the next layout (new selection or visible part), also
  // when the page is left and opened again; positions of another layout are not used.
  type Dragged = { flow: typeof flow; nodes: Node<NodeData>[] };
  const [dragged, setDragged] = useState<Dragged>(() => {
    const kept = recall<Dragged>(`${stateKey}.nodes`);
    return kept && flow && kept.flow === flow ? kept : { flow, nodes: flow?.nodes ?? [] };
  });
  const nodes = useMemo(() => (dragged.flow === flow ? dragged.nodes : (flow?.nodes ?? [])), [dragged, flow]);
  const onNodesChange = useCallback(
    (changes: NodeChange<Node<NodeData>>[]) => setDragged({ flow, nodes: applyNodeChanges(changes, nodes) }),
    [flow, nodes],
  );
  useEffect(() => {
    if (dragged.flow) keep(`${stateKey}.nodes`, dragged);
  }, [stateKey, dragged]);
  const { skipFit, ...viewport } = useKeptViewport(`${stateKey}.viewport`, flow);
  const edges = useMemo(() => (flow ? routeArcs(flow.arcs, nodes, settings.labels, scheme) : []), [flow, nodes, settings.labels, scheme]);
  const o2oColour = UI[scheme].accent;

  return (
    <Stack gap="sm">
      <ObjectGraphSettingsRow graph={data} colours={colours} settings={settings} onChange={onChange} />
      {query.isError ? (
        <Alert color="red">{errorText(query.error)}</Alert>
      ) : layoutError ? (
        <Alert color="red">Layout failed: {layoutError}</Alert>
      ) : !data || !flow ? (
        <Loader size="sm" />
      ) : (
        <Stack gap={4}>
          <Legend />
          {data.notes.length > 0 && <Text size="xs" c="dimmed">{data.notes.join(" ")}</Text>}
          {data.nodes.length === handlingUnits.length && (
            <Text size="xs" c="dimmed">The selected handling units share no events and no o2o relations with other objects.</Text>
          )}
          {/* Resizable at the bottom edge (drag the corner); React Flow follows the new size. */}
      <Box style={{ height: HEIGHT, minHeight: 200, resize: "vertical", overflow: "hidden", border: "1px solid var(--mantine-color-default-border)", borderRadius: 8, opacity: query.isFetching ? 0.6 : 1 }}>
            <svg style={{ position: "absolute", width: 0, height: 0 }} aria-hidden="true">
              <defs>
                <marker id={`og-arrow-${scheme}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" markerUnits="userSpaceOnUse" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" fill={o2oColour} />
                </marker>
              </defs>
            </svg>
            <ReactFlowProvider>
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                zoomOnDoubleClick={false}
                nodeTypes={NODE_TYPES}
                edgeTypes={EDGE_TYPES}
                nodesConnectable={false}
                nodesDraggable
                elementsSelectable={false}
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
        </Stack>
      )}
    </Stack>
  );
};
