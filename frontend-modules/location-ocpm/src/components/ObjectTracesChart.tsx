// Object traces of the instance page (Nina, 2026-11-20): one row per selected handling unit, its events as chevrons
// in `seq` order, the other objects of every event as small circles on its chevron in the colour of their object
// type (as on the activity nodes of the directly-follows graph). A chevron gets a thicker border when another
// selected handling unit takes part in the event. The event category chips of the DFG page project the traces (all
// selected by default). Documented in docs/pages/instances.md, section "Object traces".
import { Alert, Box, Group, Loader, ScrollArea, Stack, Text, Tooltip } from "@mantine/core";
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
};

/** Default: every category selected, so the traces are complete. */
export const DEFAULT_OBJECT_TRACES: ObjectTracesSettings = { excluded: [] };

/** Sizes in pixels: chevron height, depth of its point, padding, gap between chevrons, circles. */
const SIZE = { height: 46, point: 11, padX: 8, gap: 2, font: 11, circle: 9, circleGap: 3, minWidth: 54, label: 120 };
/** Circles drawn on a chevron at most (the rest as "+ n"). */
const MAX_CIRCLES = 10;
/** Other objects listed in the hover of a chevron at most. */
const MAX_HOVER_OBJECTS = 20;

/** Hover text of the event categories here (the DFG's mentions its activity selection). */
const CATEGORIES_INFO =
  "Event categories (as on the directly-follows graph page): an event leaves the traces only when all categories it belongs to are deselected; the following events move up. Move to vehicle / storage: movements whose target location is a vehicle / storage unit; such an event is also a movement, so it stays until both Movements and its Move to chip are off. Events in no category always stay. Numbers: events of the selected handling units in the category. Default: all selected.";

/** Format a timestamp of the backend (ISO, UTC) as "YYYY-MM-DD HH:MM:SS". */
const formatTime = (t: string | null | undefined) => (t ? t.replace("T", " ").replace(/(\.\d+)?(Z|[+-]\d\d:\d\d)?$/, "") : "?");

/** Width of a chevron: room for the activity name and the circles, plus the point. */
const chevronWidth = (e: TraceEvent) => {
  const circles = Math.min(e.objects.length, MAX_CIRCLES);
  const circleWidth = circles * (SIZE.circle + SIZE.circleGap) + (e.objects.length > MAX_CIRCLES ? textWidth(`+${e.objects.length - MAX_CIRCLES}`, SIZE.font - 1) : 0);
  return Math.ceil(Math.max(SIZE.minWidth, textWidth(e.activity ?? e.event, SIZE.font, 600), circleWidth) + 2 * SIZE.padX + SIZE.point);
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
      {selected.length > 0 && <Text fz={11}>{`With selected: ${selected.join(", ")} (thick border)`}</Text>}
      <Text fz={11} fw={600} mt={4}>{e.objects.length ? `Other objects (${e.objects.length}):` : "No other objects"}</Text>
      {lines.map((l) => (
        <Text key={l} fz={11} ff="monospace">{l}</Text>
      ))}
    </Stack>
  );
};

/**
 * One event as a chevron: activity name, below it a circle per other object in the colour of its object type.
 *
 * @param event The event.
 * @param first First chevron of its row (flat left side).
 * @param total Events shown in the row (for "position i of n").
 * @param colours Colour per object type.
 * @param labels Category key -> label.
 */
const Chevron = memo(
  ({ event, first, total, colours, labels }: { event: TraceEvent; first: boolean; total: number; colours: Map<string, string>; labels: Map<string, string> }) => {
    const scheme = useScheme();
    const width = chevronWidth(event);
    const withSelected = event.objects.some((o) => o.selected);
    const shown = event.objects.slice(0, MAX_CIRCLES);
    return (
      <Tooltip label={eventHover(event, total, labels)} withinPortal multiline maw={420} openDelay={200}>
        <Box style={{ position: "relative", width, height: SIZE.height, flexShrink: 0, marginLeft: first ? 0 : -SIZE.point + SIZE.gap }}>
          <svg width={width} height={SIZE.height} style={{ position: "absolute", inset: 0 }} aria-hidden="true">
            <path
              d={chevronPath(width, first)}
              fill="var(--mantine-color-body)"
              stroke="var(--mantine-color-gray-6)"
              strokeWidth={withSelected ? 2.2 : 1}
              strokeLinejoin="round"
            />
          </svg>
          <Stack
            gap={3}
            align="center"
            justify="center"
            style={{ position: "absolute", inset: 0, paddingLeft: (first ? 0 : SIZE.point) + SIZE.padX / 2, paddingRight: SIZE.point + SIZE.padX / 2 }}
          >
            <Text fz={SIZE.font} fw={600} lh={1.1} style={{ whiteSpace: "nowrap" }}>
              {event.activity ?? event.event}
            </Text>
            {event.objects.length > 0 && (
              <Group gap={SIZE.circleGap} wrap="nowrap" justify="center">
                {shown.map((o) => (
                  <Tooltip key={o.object} label={`${o.object} (${o.object_type ?? "?"})${o.selected ? ", selected" : ""}`} withinPortal>
                    <Box
                      style={{
                        width: SIZE.circle,
                        height: SIZE.circle,
                        borderRadius: "50%",
                        background: colours.get(o.object_type ?? "") ?? OTHER[scheme],
                        boxShadow: "0 0 0 0.5px var(--mantine-color-gray-6)",
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

/** One row: the handling unit (id, object type, events shown of all) and its chevrons. */
const TraceRow = ({ trace, colours, labels }: { trace: ObjectTrace; colours: Map<string, string>; labels: Map<string, string> }) => (
  <Group gap="sm" wrap="nowrap" align="center">
    <Box style={{ width: SIZE.label, flexShrink: 0, position: "sticky", left: 0, zIndex: 1, background: "var(--mantine-color-body)" }}>
      <Group gap={6} wrap="nowrap">
        <Box style={{ width: 10, height: 10, borderRadius: 5, background: colours.get(trace.object_type ?? ""), flexShrink: 0 }} />
        <Text fz={12} fw={700} truncate>{trace.hu}</Text>
      </Group>
      <Text fz={10} c="dimmed" truncate>
        {`${trace.object_type ?? "?"} · ${trace.events.length === trace.n_events ? `${num(trace.n_events)} events` : `${num(trace.events.length)} of ${num(trace.n_events)} events`}`}
      </Text>
    </Box>
    <Group gap={0} wrap="nowrap">
      {trace.events.length === 0 ? (
        <Text fz={11} c="dimmed">{trace.n_events ? "No events left (all categories of its events deselected)." : "No events in the log."}</Text>
      ) : (
        trace.events.map((e, i) => <Chevron key={e.event} event={e} first={i === 0} total={trace.events.length} colours={colours} labels={labels} />)
      )}
    </Group>
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
 * The object traces card's content: event category chips, legend and one row per selected handling unit.
 *
 * @param ocelId The log.
 * @param handlingUnits The selected handling units.
 * @param colours Colour per object type of the handling units (others get the next palette colours).
 * @param settings The settings.
 * @param onChange Called with the changed settings.
 */
export const ObjectTracesChart = ({
  ocelId,
  handlingUnits,
  colours,
  settings,
  onChange,
}: {
  ocelId: string;
  handlingUnits: string[];
  colours: Map<string, string>;
  settings: ObjectTracesSettings;
  onChange: (s: ObjectTracesSettings) => void;
}) => {
  const scheme = useScheme();
  const query = useObjectTraces(ocelId, handlingUnits, settings.excluded);
  const data = query.data;
  const allColours = useMemo(() => traceColours(colours, data, scheme), [colours, data, scheme]);
  const labels = useMemo(() => new Map((data?.categories ?? []).map((c) => [c.key, c.label])), [data]);
  return (
    <Stack gap="sm">
      {data && (
        <CategoryChips categories={data.categories} excluded={settings.excluded} onChange={(excluded) => onChange({ ...settings, excluded })} info={CATEGORIES_INFO} />
      )}
      <Text fz={11} lh={1.3} c="dimmed">
        One row per selected handling unit, its events from left to right in trace order (time, then the tie order of the HU profile) ·
        chevron: event with its activity · small circle: another object of the event, in the colour of its object type · thick border:
        another selected handling unit takes part · hover a chevron for the event, its timestamp, location, categories and objects, a
        circle for its object
      </Text>
      {query.isError ? (
        <Alert color="red">{errorText(query.error)}</Alert>
      ) : !data ? (
        <Loader size="sm" />
      ) : (
        <>
          {data.notes.length > 0 && <Text size="xs" c="dimmed">{data.notes.join(" ")}</Text>}
          <ScrollArea type="auto" offsetScrollbars style={{ opacity: query.isFetching ? 0.6 : 1 }}>
            <Stack gap={8} pb={4}>
              {data.traces.map((t) => (
                <TraceRow key={t.hu} trace={t} colours={allColours} labels={labels} />
              ))}
            </Stack>
          </ScrollArea>
        </>
      )}
    </Stack>
  );
};
