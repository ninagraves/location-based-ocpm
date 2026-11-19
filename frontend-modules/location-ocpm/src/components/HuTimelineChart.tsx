// HU timeline chart of the instance page: the timeline of the selected handling units (or of the whole loaded
// lineage), drawn by the backend's `timeline/object_timeline.py` and shown with Plotly.
// Documented in docs/pages/instances.md, section "HU timeline".
import { Alert, Button, Checkbox, Group, Loader, Pill, SegmentedControl, Stack, Text } from "@mantine/core";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { getHuTimeline, type TimelineRequestAxis } from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import { plotConfig, ThemedPlot } from "./plots";

/** Settings of the HU timeline (kept per log). */
export type TimelineSettings = {
  axis: TimelineRequestAxis;
  showHighLevel: boolean;
  showActivityLabels: boolean;
  markTies: boolean;
  linkSharedEvents: boolean;
  /** Row order: as selected (lineage: selected first) or by first event. */
  order: "given" | "first event";
  /** Also write the activity names of movements, starting exactly above their line on the band. */
  movementLabels: boolean;
};

/** Defaults: event order, everything shown, rows in selection order. */
export const DEFAULT_TIMELINE: TimelineSettings = {
  axis: "event order",
  showHighLevel: true,
  showActivityLabels: true,
  markTies: true,
  linkSharedEvents: true,
  order: "given",
  movementLabels: false,
};

/** The legend, in grey above the chart (see the resource "HU Timeline"). */
const Legend = () => (
  <Text fz={11} lh={1.3} c="dimmed">
    Band: upper half the location after each event (loc), lower half its high-level location; hatched: vehicle; empty: not located ·
    ★ processing operation, ● other event, on the band: movement (▲ produced, ▼ consumed, | otherwise; ◇ pickup location differs
    from the previous location) · colours: green produced, pink consumed, amber both, dark grey neither · dotted line: event shared
    by shown handling units · grey box: same timestamp · line below the band: lifespan
  </Text>
);

/** Handling units shown as pills at most (the rest as "+ n more"). */
const MAX_PILLS = 30;

/**
 * The handling units of the timeline: its own list, reset to the page's selection whenever that changes, with buttons
 * that add the handling units of the lineage chart or of the object graph.
 *
 * @param units The timeline's handling units, top to bottom.
 * @param onChange Called with the new list.
 * @param selected The page's selection (for "Reset to selection").
 * @param lineage Handling units of the loaded lineage chart.
 * @param objectGraph Handling units of the object graph.
 */
export const TimelineUnitsBar = ({
  units,
  onChange,
  selected,
  lineage,
  objectGraph,
}: {
  units: string[];
  onChange: (units: string[]) => void;
  selected: string[];
  lineage: string[];
  objectGraph: string[];
}) => {
  const add = (more: string[]) => onChange([...units, ...more.filter((hu) => !units.includes(hu))]);
  const newLineage = lineage.filter((hu) => !units.includes(hu)).length;
  const newGraph = objectGraph.filter((hu) => !units.includes(hu)).length;
  const same = units.length === selected.length && units.every((hu, i) => hu === selected[i]);
  return (
    <Stack gap={4}>
      <Group gap={6}>
        <Text size="xs" fw={500}>Handling units ({units.length}):</Text>
        {units.slice(0, MAX_PILLS).map((hu) => (
          <Pill key={hu} size="xs" withRemoveButton onRemove={() => onChange(units.filter((x) => x !== hu))}>
            {hu}
          </Pill>
        ))}
        {units.length > MAX_PILLS && <Text size="xs" c="dimmed">+ {units.length - MAX_PILLS} more</Text>}
      </Group>
      <Group gap={6}>
        <Button size="compact-xs" variant="light" disabled={newLineage === 0} onClick={() => add(lineage)}>
          Add all HUs of the lineage (+{newLineage})
        </Button>
        <Button size="compact-xs" variant="light" disabled={newGraph === 0} onClick={() => add(objectGraph)}>
          Add all HUs of the object graph (+{newGraph})
        </Button>
        <Button size="compact-xs" variant="subtle" disabled={same} onClick={() => onChange(selected)}>
          Reset to selection
        </Button>
      </Group>
    </Stack>
  );
};

/**
 * The settings row of the HU timeline.
 *
 * @param settings Current settings.
 * @param onChange Called with the changed settings.
 * @param hasHighLevel High-level locations are configured (otherwise the high-level band is not offered).
 */
export const TimelineSettingsRow = ({
  settings,
  onChange,
  hasHighLevel,
}: {
  settings: TimelineSettings;
  onChange: (s: TimelineSettings) => void;
  hasHighLevel: boolean;
}) => (
  <Group gap="md" align="flex-end">
    <div>
      <Text size="xs" fw={500}>Axis</Text>
      <SegmentedControl
        size="xs"
        value={settings.axis}
        onChange={(v) => onChange({ ...settings, axis: v as TimelineRequestAxis })}
        data={[
          { value: "event order", label: "event order" },
          { value: "time", label: "time" },
        ]}
      />
    </div>
    <div>
      <Text size="xs" fw={500}>Rows</Text>
      <SegmentedControl
        size="xs"
        value={settings.order}
        onChange={(v) => onChange({ ...settings, order: v as TimelineSettings["order"] })}
        data={[
          { value: "given", label: "as listed" },
          { value: "first event", label: "by first event" },
        ]}
      />
    </div>
    {hasHighLevel && (
      <Checkbox size="xs" label="High-level band" checked={settings.showHighLevel} onChange={(e) => onChange({ ...settings, showHighLevel: e.currentTarget.checked })} />
    )}
    <Checkbox size="xs" label="Activity names" checked={settings.showActivityLabels} onChange={(e) => onChange({ ...settings, showActivityLabels: e.currentTarget.checked })} />
    <Checkbox
      size="xs"
      label="Movement names"
      title="Also write the activity names of movements, starting exactly above their line on the band"
      disabled={!settings.showActivityLabels}
      checked={settings.movementLabels}
      onChange={(e) => onChange({ ...settings, movementLabels: e.currentTarget.checked })}
    />
    <Checkbox size="xs" label="Same timestamp" checked={settings.markTies} onChange={(e) => onChange({ ...settings, markTies: e.currentTarget.checked })} />
    <Checkbox size="xs" label="Shared events" checked={settings.linkSharedEvents} onChange={(e) => onChange({ ...settings, linkSharedEvents: e.currentTarget.checked })} />
  </Group>
);

/**
 * The HU timeline of some handling units.
 *
 * @param ocelId The log.
 * @param handlingUnits Handling units, top to bottom (unless ordered by first event).
 * @param settings The settings.
 */
export const HuTimelineChart = ({ ocelId, handlingUnits, settings }: { ocelId: string; handlingUnits: string[]; settings: TimelineSettings }) => {
  const request = useMemo(
    () => ({
      handling_units: handlingUnits,
      axis: settings.axis,
      show_high_level: settings.showHighLevel,
      show_activity_labels: settings.showActivityLabels,
      mark_ties: settings.markTies,
      link_shared_events: settings.linkSharedEvents,
      by_first_event: settings.order === "first event",
      label_movements: settings.movementLabels,
    }),
    [handlingUnits, settings],
  );
  const { data, error, isFetching } = useQuery({
    queryKey: ["locationBasedOcpm", "instances", "timeline", ocelId, request],
    queryFn: ({ signal }) => getHuTimeline(ocelId, request, undefined, undefined, signal),
    enabled: handlingUnits.length > 0,
    placeholderData: keepPreviousData,
  });
  // The figure comes from the backend; its template is dropped so that Ocelescope's theme (light / dark) applies.
  const figure = useMemo(() => {
    if (!data) return null;
    const { template: _template, width: _width, ...layout } = (data.figure.layout ?? {}) as Record<string, unknown>;
    return { data: (data.figure.data ?? []) as object[], layout: { ...layout, autosize: true } as Record<string, unknown> };
  }, [data]);

  if (handlingUnits.length === 0) return <Text size="sm" c="dimmed">No handling units in the timeline; add some with the buttons above.</Text>;
  if (error) return <Alert color="red">{errorText(error)}</Alert>;
  if (!figure || !data) return <Loader size="sm" />;
  return (
    <Stack gap={4} style={{ opacity: isFetching ? 0.6 : 1 }}>
      <Legend />
      {data.notes.length > 0 && <Text size="xs" c="dimmed">{data.notes.join(" ")}</Text>}
      {figure.data.length === 0 ? (
        <Text size="sm" c="dimmed">None of these handling units has events.</Text>
      ) : (
        <ThemedPlot
          data={figure.data as never}
          layout={figure.layout as never}
          config={plotConfig("HU timeline") as never}
          useResizeHandler
          style={{ width: "100%", height: (figure.layout.height as number | undefined) ?? 400 }}
        />
      )}
    </Stack>
  );
};
