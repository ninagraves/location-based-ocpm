// Object traces of the instance page (Nina, 2026-11-20): one row per selected handling unit, its events as chevrons
// in `seq` order, the other objects of every event as small circles on its chevron in the colour of their object
// type (as on the activity nodes of the directly-follows graph); the circle of another selected handling unit has a
// thicker border. Optionally, events shared by several rows are aligned in one column. The event category chips of
// the DFG page project the traces (all selected by default). Documented in docs/pages/instances.md, section "Object traces".
import { Alert, Box, Checkbox, Group, Loader, ScrollArea, Stack, Text, Tooltip } from "@mantine/core";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { memo, useMemo } from "react";
import { getObjectTraces, type ObjectTrace, type ObjectTracesResponse, type TraceEvent } from "../api/locationBasedOcpm";
import { textWidth } from "../lib/dfgLayout";
import { errorText } from "../lib/errors";
import { num } from "../lib/format";
import { categoricalColour, OTHER } from "../lib/palette";
import { CategoryChips } from "./DfgToolbar";
import { useScheme } from "./plots";

/** Settings of the object traces (kept per log). */
export type ObjectTracesSettings = {
  /** Deselected event categories (keys of `dfg/categories.py`); their events leave the traces. */
  excluded: string[];
  /** Shared events in one column across the rows (`alignColumns`); off: every row packed from the left. */
  alignShared: boolean;
};

/** Default: every category selected, so the traces are complete; rows packed from the left. */
export const DEFAULT_OBJECT_TRACES: ObjectTracesSettings = { excluded: [], alignShared: false };

/** Sizes in pixels: chevron height, depth of its point, padding, gap between chevrons, circles. */
const SIZE = { height: 56, point: 11, padX: 8, gap: 2, font: 11, circle: 9, circleGap: 3, minWidth: 54, label: 120 };
/** Circles drawn on a chevron at most (the rest as "+ n"). */
const MAX_CIRCLES = 10;
/** Other objects listed in the hover of a chevron at most. */
const MAX_HOVER_OBJECTS = 20;

/** Hover text of the event categories here (the DFG's mentions its activity selection). */
const CATEGORIES_INFO =
  "Event categories (as on the directly-follows graph page): an event leaves the traces only when all categories it belongs to are deselected; the following events move up. Move to vehicle / storage: movements whose target location is a vehicle / storage unit; such an event is also a movement, so it stays until both Movements and its Move to chip are off. Events in no category always stay. Numbers: events of the selected handling units in the category. Default: all selected.";

/** Format a timestamp of the backend (ISO, UTC) as "YYYY-MM-DD HH:MM:SS". */
const formatTime = (t: string | null | undefined) => (t ? t.replace("T", " ").replace(/(\.\d+)?(Z|[+-]\d\d:\d\d)?$/, "") : "?");

/** Width of a chevron: room for the event id, the activity name and the circles, plus the point. */
const chevronWidth = (e: TraceEvent) => {
  const circles = Math.min(e.objects.length, MAX_CIRCLES);
  const circleWidth = circles * (SIZE.circle + SIZE.circleGap) + (e.objects.length > MAX_CIRCLES ? textWidth(`+${e.objects.length - MAX_CIRCLES}`, SIZE.font - 1) : 0);
  const names = Math.max(textWidth(e.activity ?? e.event, SIZE.font, 600), textWidth(e.event, SIZE.font - 2));
  return Math.ceil(Math.max(SIZE.minWidth, names, circleWidth) + 2 * SIZE.padX + SIZE.point);
};

/** Outline of a chevron of width w: notched on the left (except the first one of a row), pointed on the right. */
const chevronPath = (w: number, first: boolean) => {
  const h = SIZE.height;
  const p = SIZE.point;
  return `M 1 1 L ${w - p} 1 L ${w - 1} ${h / 2} L ${w - p} ${h - 1} L 1 ${h - 1} ${first ? "" : `L ${p} ${h / 2}`} Z`;
};

/** Hover of a chevron: event, activity, timestamp, location, categories, position and the other objects. */
const eventHover = (e: TraceEvent, total: number, labels: Map<string, string>) => {
  const selected = e.objects.filter((o) => o.selected).map((o) => o.object);
  const lines = e.objects.slice(0, MAX_HOVER_OBJECTS).map((o) => `${o.object} (${o.object_type ?? "?"})${o.selected ? ", selected" : ""}`);
  if (e.objects.length > MAX_HOVER_OBJECTS) lines.push(`+ ${e.objects.length - MAX_HOVER_OBJECTS} more`);
  return (
    <Stack gap={0}>
      <Text fz={11} fw={600}>{`${e.event} · ${e.activity ?? ""}`}</Text>
      <Text fz={11}>{`${formatTime(e.time)} · at ${e.location ?? "⊥ (unlocated)"} · position ${e.pos} of ${total}`}</Text>
      <Text fz={11}>{`Categories: ${e.categories.length ? e.categories.map((k) => labels.get(k) ?? k).join(", ") : "none"}`}</Text>
      {selected.length > 0 && <Text fz={11}>{`With selected: ${selected.join(", ")} (circles with a thick border)`}</Text>}
      <Text fz={11} fw={600} mt={4}>{e.objects.length ? `Other objects (${e.objects.length}):` : "No other objects"}</Text>
      {lines.map((l) => (
        <Text key={l} fz={11} ff="monospace">{l}</Text>
      ))}
    </Stack>
  );
};

/**
 * One event as a chevron: event id (small, grey), activity name, below them a circle per other object in the colour
 * of its object type.
 *
 * @param event The event.
 * @param first First chevron of its row (flat left side).
 * @param total Events shown in the row (for "position i of n").
 * @param colours Colour per object type.
 * @param labels Category key -> label.
 * @param at Aligned mode: left edge and width of the chevron's column (`alignColumns`); otherwise packed in a row.
 * @param onToggle Called with a handling unit whose circle is double-clicked (selects or unselects it).
 */
const Chevron = memo(
  ({
    event,
    first,
    total,
    colours,
    labels,
    at,
    onToggle,
  }: {
    event: TraceEvent;
    first: boolean;
    total: number;
    colours: Map<string, string>;
    labels: Map<string, string>;
    at?: { x: number; width: number };
    onToggle?: (hu: string) => void;
  }) => {
    const scheme = useScheme();
    const width = at?.width ?? chevronWidth(event);
    const shown = event.objects.slice(0, MAX_CIRCLES);
    const place: React.CSSProperties = at
      ? { position: "absolute", left: at.x, top: 0 }
      : { position: "relative", marginLeft: first ? 0 : -SIZE.point + SIZE.gap };
    return (
      <Tooltip label={eventHover(event, total, labels)} withinPortal multiline maw={420} openDelay={200}>
        <Box style={{ ...place, width, height: SIZE.height, flexShrink: 0 }}>
          <svg width={width} height={SIZE.height} style={{ position: "absolute", inset: 0 }} aria-hidden="true">
            <path
              d={chevronPath(width, first)}
              fill="var(--mantine-color-body)"
              stroke="var(--mantine-color-gray-6)"
              strokeWidth={1}
              strokeLinejoin="round"
            />
          </svg>
          <Stack
            gap={3}
            align="center"
            justify="center"
            style={{ position: "absolute", inset: 0, paddingLeft: (first ? 0 : SIZE.point) + SIZE.padX / 2, paddingRight: SIZE.point + SIZE.padX / 2 }}
          >
            <Stack gap={0} align="center">
              <Text fz={SIZE.font - 2} c="dimmed" lh={1.1} style={{ whiteSpace: "nowrap" }}>
                {event.event}
              </Text>
              <Text fz={SIZE.font} fw={600} lh={1.1} style={{ whiteSpace: "nowrap" }}>
                {event.activity ?? event.event}
              </Text>
            </Stack>
            {event.objects.length > 0 && (
              <Group gap={SIZE.circleGap} wrap="nowrap" justify="center">
                {shown.map((o) => (
                  <Tooltip
                    key={o.object}
                    label={`${o.object} (${o.object_type ?? "?"})${o.selected ? ", selected · double-click to unselect" : o.is_hu ? " · double-click to select" : ""}`}
                    withinPortal
                  >
                    <Box
                      onDoubleClick={o.is_hu && onToggle ? () => onToggle(o.object) : undefined}
                      style={{
                        cursor: o.is_hu && onToggle ? "pointer" : undefined,
                        width: SIZE.circle,
                        height: SIZE.circle,
                        borderRadius: "50%",
                        background: colours.get(o.object_type ?? "") ?? OTHER[scheme],
                        // A selected handling unit: thicker border (Nina, 2026-11-20), no other mark.
                        boxShadow: o.selected ? "0 0 0 1.75px var(--mantine-color-gray-8)" : "0 0 0 0.5px var(--mantine-color-gray-6)",
                        flexShrink: 0,
                      }}
                    />
                  </Tooltip>
                ))}
                {event.objects.length > MAX_CIRCLES && (
                  <Text fz={SIZE.font - 1} c="dimmed" lh={1}>{`+${event.objects.length - MAX_CIRCLES}`}</Text>
                )}
              </Group>
            )}
          </Stack>
        </Box>
      </Tooltip>
    );
  },
);

/** Column layout of the aligned mode: column per event, left edge and width per column, total width. */
type Columns = { column: Map<string, number>; xs: number[]; widths: number[]; total: number };

/**
 * Align shared events: every event gets one column, the same in every row it appears in, and each row keeps its order.
 * The column of an event is the length of the longest chain of events before it over all rows (longest path in the
 * graph with an arc from each event to the next one of the same row; Kahn's algorithm by rounds). A column is as wide
 * as its widest chevron. Rows skip the columns of events they are not part of, which leaves gaps.
 *
 * Example: c2 = e3, e4, e6, e8 and c1 = e3, e4, e5, e7, e8 give e3 → 0, e4 → 1, e5 and e6 → 2, e7 → 3, e8 → 4; c2's
 * row has a gap at column 3.
 *
 * @param traces The traces.
 * @returns The layout, or null if the rows order shared events differently (a cycle; cannot happen with one global
 *   order, but then the rows are packed instead).
 */
export const alignColumns = (traces: ObjectTrace[]): Columns | null => {
  const next = new Map<string, Set<string>>();
  const indegree = new Map<string, number>();
  const width = new Map<string, number>();
  for (const t of traces) {
    t.events.forEach((e, i) => {
      if (!indegree.has(e.event)) indegree.set(e.event, 0);
      width.set(e.event, Math.max(width.get(e.event) ?? 0, chevronWidth(e)));
      const following = t.events[i + 1]?.event;
      if (following && following !== e.event) {
        const out = next.get(e.event) ?? new Set<string>();
        if (!out.has(following)) {
          out.add(following);
          next.set(e.event, out);
          indegree.set(following, (indegree.get(following) ?? 0) + 1);
        }
      }
    });
  }
  const column = new Map<string, number>();
  let round = [...indegree.entries()].filter(([, d]) => d === 0).map(([e]) => e);
  let depth = 0;
  while (round.length) {
    const upcoming: string[] = [];
    for (const e of round) {
      column.set(e, depth);
      for (const f of next.get(e) ?? []) {
        const d = (indegree.get(f) ?? 0) - 1;
        indegree.set(f, d);
        if (d === 0) upcoming.push(f);
      }
    }
    round = upcoming;
    depth += 1;
  }
  if (column.size < indegree.size) return null;
  const widths = Array.from({ length: depth }, () => SIZE.minWidth);
  for (const [e, c] of column) widths[c] = Math.max(widths[c], width.get(e) ?? 0);
  const xs: number[] = [];
  let x = 0;
  for (const w of widths) {
    xs.push(x);
    x += w - SIZE.point + SIZE.gap;
  }
  return { column, xs, widths, total: x + SIZE.point - SIZE.gap };
};

/**
 * One row: the handling unit (id, object type, events shown of all) and its chevrons, packed or in the aligned
 * columns. Double-clicking the id unselects the handling unit, double-clicking a handling unit's circle (un)selects it.
 */
const TraceRow = ({
  trace,
  colours,
  labels,
  columns,
  onToggle,
}: {
  trace: ObjectTrace;
  colours: Map<string, string>;
  labels: Map<string, string>;
  columns: Columns | null;
  onToggle?: (hu: string) => void;
}) => (
  <Group gap="sm" wrap="nowrap" align="center">
    <Box style={{ width: SIZE.label, flexShrink: 0, position: "sticky", left: 0, zIndex: 1, background: "var(--mantine-color-body)" }}>
      <Group gap={6} wrap="nowrap">
        <Box style={{ width: 10, height: 10, borderRadius: 5, background: colours.get(trace.object_type ?? ""), flexShrink: 0 }} />
        <Tooltip label="Double-click to unselect" withinPortal openDelay={400}>
          <Text fz={12} fw={700} truncate onDoubleClick={() => onToggle?.(trace.hu)} style={{ cursor: onToggle ? "pointer" : undefined }}>
            {trace.hu}
          </Text>
        </Tooltip>
      </Group>
      <Text fz={10} c="dimmed" truncate>
        {`${trace.object_type ?? "?"} · ${trace.events.length === trace.n_events ? `${num(trace.n_events)} events` : `${num(trace.events.length)} of ${num(trace.n_events)} events`}`}
      </Text>
    </Box>
    {trace.events.length === 0 ? (
      <Text fz={11} c="dimmed">{trace.n_events ? "No events left (all categories of its events deselected)." : "No events in the log."}</Text>
    ) : columns ? (
      <Box style={{ position: "relative", width: columns.total, height: SIZE.height, flexShrink: 0 }}>
        {trace.events.map((e, i) => {
          const c = columns.column.get(e.event) ?? 0;
          return (
            <Chevron
              key={e.event}
              event={e}
              first={i === 0}
              total={trace.events.length}
              colours={colours}
              labels={labels}
              at={{ x: columns.xs[c], width: columns.widths[c] }}
              onToggle={onToggle}
            />
          );
        })}
      </Box>
    ) : (
      <Group gap={0} wrap="nowrap">
        {trace.events.map((e, i) => (
          <Chevron key={e.event} event={e} first={i === 0} total={trace.events.length} colours={colours} labels={labels} onToggle={onToggle} />
        ))}
      </Group>
    )}
  </Group>
);

/** Fetch the traces of the selected handling units for the deselected categories. */
export const useObjectTraces = (ocelId: string, handlingUnits: string[], excluded: string[]) => {
  const request = useMemo(() => ({ handling_units: handlingUnits, excluded_categories: excluded }), [handlingUnits, excluded]);
  return useQuery({
    queryKey: ["locationBasedOcpm", "instances", "traces", ocelId, request],
    queryFn: ({ signal }) => getObjectTraces(ocelId, request, undefined, undefined, signal),
    enabled: handlingUnits.length > 0,
    placeholderData: keepPreviousData,
  });
};

/**
 * Colours of all object types in the traces: the given ones (handling-unit types of the log), the others continue
 * the palette in alphabetical order.
 */
const traceColours = (colours: Map<string, string>, data: ObjectTracesResponse | undefined, scheme: "light" | "dark") => {
  const map = new Map(colours);
  const types = new Set<string>();
  for (const t of data?.traces ?? []) for (const e of t.events) for (const o of e.objects) types.add(o.object_type ?? "");
  for (const t of [...types].sort()) if (!map.has(t)) map.set(t, categoricalColour(map.size, scheme));
  return map;
};

/**
 * Legend of the object types: a circle in the type's colour and its name, for every type in the traces (the rows'
 * types and the types of the other objects), with its number of distinct objects; the rows' types first, then by name.
 *
 * @param traces The traces.
 * @param colours Colour per object type.
 */
const TypeLegend = ({ traces, colours }: { traces: ObjectTrace[]; colours: Map<string, string> }) => {
  const scheme = useScheme();
  const objects = new Map<string, Set<string>>();
  const add = (type: string, id: string) => objects.set(type, (objects.get(type) ?? new Set<string>()).add(id));
  for (const t of traces) {
    add(t.object_type ?? "", t.hu);
    for (const e of t.events) for (const o of e.objects) add(o.object_type ?? "", o.object);
  }
  const rows = new Set(traces.map((t) => t.object_type ?? ""));
  const types = [...objects.keys()].sort((a, b) => Number(rows.has(b)) - Number(rows.has(a)) || a.localeCompare(b));
  return (
    <Group gap="md" wrap="wrap">
      <Text fz={11} fw={500}>Object types:</Text>
      {types.map((t) => (
        <Group key={t} gap={5} wrap="nowrap">
          <Box style={{ width: SIZE.circle, height: SIZE.circle, borderRadius: "50%", background: colours.get(t) ?? OTHER[scheme], boxShadow: "0 0 0 0.5px var(--mantine-color-gray-6)" }} />
          <Text fz={11}>{`${t || "?"} (${num(objects.get(t)?.size ?? 0)})`}</Text>
        </Group>
      ))}
    </Group>
  );
};

/**
 * The object traces card's content: event category chips, legend and one row per selected handling unit.
 *
 * @param ocelId The log.
 * @param handlingUnits The selected handling units.
 * @param colours Colour per object type of the handling units (others get the next palette colours).
 * @param settings The settings.
 * @param onChange Called with the changed settings.
 * @param onToggle Called with a handling unit double-clicked in the chart (selects or unselects it).
 */
export const ObjectTracesChart = ({
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
  settings: ObjectTracesSettings;
  onChange: (s: ObjectTracesSettings) => void;
  onToggle?: (hu: string) => void;
}) => {
  const scheme = useScheme();
  const query = useObjectTraces(ocelId, handlingUnits, settings.excluded);
  const data = query.data;
  const allColours = useMemo(() => traceColours(colours, data, scheme), [colours, data, scheme]);
  const labels = useMemo(() => new Map((data?.categories ?? []).map((c) => [c.key, c.label])), [data]);
  const columns = useMemo(() => (settings.alignShared && data ? alignColumns(data.traces) : null), [settings.alignShared, data]);
  return (
    <Stack gap="sm">
      <Group gap="md" align="center">
        {data && (
          <CategoryChips categories={data.categories} excluded={settings.excluded} onChange={(excluded) => onChange({ ...settings, excluded })} info={CATEGORIES_INFO} />
        )}
        <Tooltip
          label="Every event in one column across the rows, so an event shared by several selected handling units sits directly beneath itself; rows keep their order and get gaps where they skip events. Off: every row packed from the left."
          multiline
          w={320}
          withinPortal
        >
          <Checkbox size="xs" label="Align shared events" checked={settings.alignShared} onChange={(e) => onChange({ ...settings, alignShared: e.currentTarget.checked })} />
        </Tooltip>
      </Group>
      <Text fz={11} lh={1.3} c="dimmed">
        One row per selected handling unit, its events from left to right in trace order (time, then the tie order of the HU profile) ·
        chevron: event with its id and activity · small circle: another object of the event, in the colour of its object type (thick border:
        a selected handling unit) · hover a chevron for the event, its timestamp, location, categories and objects, a
        circle for its object · double-click a handling unit's circle to select or unselect it, a row's name to unselect it
      </Text>
      {query.isError ? (
        <Alert color="red">{errorText(query.error)}</Alert>
      ) : !data ? (
        <Loader size="sm" />
      ) : (
        <>
          {data.notes.length > 0 && <Text size="xs" c="dimmed">{data.notes.join(" ")}</Text>}
          <TypeLegend traces={data.traces} colours={allColours} />
          <ScrollArea type="auto" offsetScrollbars style={{ opacity: query.isFetching ? 0.6 : 1 }}>
            <Stack gap={8} pb={4}>
              {data.traces.map((t) => (
                <TraceRow key={t.hu} trace={t} colours={allColours} labels={labels} columns={columns} onToggle={onToggle} />
              ))}
            </Stack>
          </ScrollArea>
        </>
      )}
    </Stack>
  );
};
