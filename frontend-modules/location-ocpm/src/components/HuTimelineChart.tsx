// HU timeline chart of the instance page: the timeline of the selected handling units (or of the whole loaded
// lineage), drawn by the backend's `timeline/object_timeline.py` and shown with Plotly.
// Documented in docs/pages/instances.md, section "HU timeline".
import { Alert, Checkbox, Group, Loader, SegmentedControl, Stack, Text } from "@mantine/core";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { getHuTimeline, type TimelineRequestAxis, type TimelineRequestMovementMarkers } from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import { plotConfig, ThemedPlot } from "./plots";

/** Settings of the HU timeline (kept per log). */
export type TimelineSettings = {
  /** Which handling units: the selected ones, or every handling unit of the loaded lineage. */
  source: "selected" | "lineage";
  axis: TimelineRequestAxis;
  showHighLevel: boolean;
  showActivityLabels: boolean;
  markTies: boolean;
  linkSharedEvents: boolean;
  /** Row order: as selected (lineage: selected first) or by first event. */
  order: "given" | "first event";
  /** Movements: implicit (tick, ▲/▼, ◇ on the band), explicit (open circle on the band) or explicit with label. */
  movements: TimelineRequestMovementMarkers;
};

/** Defaults: selected handling units, event order, everything shown, rows in selection order. */
export const DEFAULT_TIMELINE: TimelineSettings = {
  source: "selected",
  axis: "event order",
  showHighLevel: true,
  showActivityLabels: true,
  markTies: true,
  linkSharedEvents: true,
  order: "given",
  movements: "implicit",
};

/** The legend, in grey above the chart (see the resource "HU Timeline"). */
const Legend = () => (
  <Text fz={11} lh={1.3} c="dimmed">
    Band: upper half the location after each event (loc), lower half its high-level location; hatched: vehicle; empty: not located ·
    ★ processing operation, ● other event, on the band: movement (▲ produced, ▼ consumed, | otherwise; ◇ pickup location differs
    from the previous location; open circle: movement shown explicitly) · colours: green produced, pink consumed, amber both, dark grey neither · dotted line: event shared
    by shown handling units · grey box: same timestamp · line below the band: lifespan
  </Text>
);

/**
 * The settings row of the HU timeline.
 *
 * @param settings Current settings.
 * @param onChange Called with the changed settings.
 * @param lineageCount Handling units of the loaded lineage (0 disables "with lineage").
 * @param hasHighLevel High-level locations are configured (otherwise the high-level band is not offered).
 */
export const TimelineSettingsRow = ({
  settings,
  onChange,
  lineageCount,
  hasHighLevel,
}: {
  settings: TimelineSettings;
  onChange: (s: TimelineSettings) => void;
  lineageCount: number;
  hasHighLevel: boolean;
}) => (
  <Group gap="md" align="flex-end">
    <div>
      <Text size="xs" fw={500}>Handling units</Text>
      <SegmentedControl
        size="xs"
        value={settings.source}
        onChange={(v) => onChange({ ...settings, source: v as TimelineSettings["source"] })}
        data={[
          { value: "selected", label: "selected" },
          { value: "lineage", label: `all in the lineage${lineageCount ? ` (${lineageCount})` : ""}`, disabled: lineageCount === 0 },
        ]}
      />
    </div>
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
          { value: "given", label: "as selected" },
          { value: "first event", label: "by first event" },
        ]}
      />
    </div>
    <div>
      <Text size="xs" fw={500}>Movements</Text>
      <SegmentedControl
        size="xs"
        value={settings.movements}
        onChange={(v) => onChange({ ...settings, movements: v as TimelineRequestMovementMarkers })}
        data={[
          { value: "implicit", label: "implicit" },
          { value: "explicit", label: "explicit" },
          { value: "explicit with label", label: "explicit with label" },
        ]}
      />
    </div>
    {hasHighLevel && (
      <Checkbox size="xs" label="High-level band" checked={settings.showHighLevel} onChange={(e) => onChange({ ...settings, showHighLevel: e.currentTarget.checked })} />
    )}
    <Checkbox size="xs" label="Activity names" checked={settings.showActivityLabels} onChange={(e) => onChange({ ...settings, showActivityLabels: e.currentTarget.checked })} />
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
      movement_markers: settings.movements,
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
