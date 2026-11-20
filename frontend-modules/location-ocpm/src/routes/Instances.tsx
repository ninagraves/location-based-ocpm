// The instance page: the HU profile (one row per handling unit; rows can be selected), then, for the selected
// handling units, the lineage chart, the object graph, the object traces and the HU timeline, each with its own
// settings row.
// Documented in docs/pages/instances.md.
import { Box, Button, Card, Group, Pill, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { getHuProfile } from "../api/locationBasedOcpm";
import { HuProfileTable } from "../components/HuProfileTable";
import { DEFAULT_TIMELINE, HuTimelineChart, type TimelineSettings, TimelineSettingsRow, TimelineUnitsBar } from "../components/HuTimelineChart";
import {
  DEFAULT_LINEAGE,
  LineageChart,
  type LineageSettings,
  LineageSettingsRow,
  useSelectionLineage,
} from "../components/LineageChart";
import { DEFAULT_OBJECT_GRAPH, ObjectGraphChart, type ObjectGraphSettings, useObjectGraph } from "../components/ObjectGraphChart";
import { ModulePage } from "../components/ModulePage";
import { DEFAULT_OBJECT_TRACES, ObjectTracesChart, type ObjectTracesSettings } from "../components/ObjectTracesChart";
import { useScheme } from "../components/plots";
import { usePageState } from "../lib/pageState";
import { colourMap } from "../lib/palette";

/** Selected handling units shown at most as pills (the rest as "+ n more"). */
const MAX_PILLS = 30;

/**
 * The selected handling units as removable pills, with "Clear". It sticks to the top of the window once scrolled to,
 * so that the selection stays visible and editable next to the charts below.
 *
 * @param selected The selection.
 * @param onChange Called with the new selection.
 */
const SelectionBar = ({ selected, onChange }: { selected: string[]; onChange: (ids: string[]) => void }) => (
  <Box
    style={{
      position: "sticky",
      top: "var(--app-shell-header-offset, 0px)",
      zIndex: 5,
      background: "var(--mantine-color-body)",
      borderBottom: "1px solid var(--mantine-color-default-border)",
      padding: "6px 0",
    }}
  >
  <Group gap={6}>
    <Text size="sm" fw={500}>Selected ({selected.length}):</Text>
    {selected.slice(0, MAX_PILLS).map((hu) => (
      <Pill key={hu} withRemoveButton onRemove={() => onChange(selected.filter((x) => x !== hu))}>
        {hu}
      </Pill>
    ))}
    {selected.length > MAX_PILLS && <Text size="xs" c="dimmed">+ {selected.length - MAX_PILLS} more</Text>}
    <Button size="compact-xs" variant="subtle" onClick={() => onChange([])}>
      Clear
    </Button>
  </Group>
  </Box>
);

/** A card with a title, an optional reset button, settings and content. */
const ChartCard = ({ title, onReset, children }: { title: string; onReset?: () => void; children: React.ReactNode }) => (
  <Card withBorder padding="md">
    <Stack gap="sm">
      <Group justify="space-between">
        <Title order={4}>{title}</Title>
        {onReset && (
          <Button size="compact-xs" variant="subtle" onClick={onReset}>
            Reset settings
          </Button>
        )}
      </Group>
      {children}
    </Stack>
  </Card>
);

/** The content of the page for one log. */
const InstancesContent = ({ ocelId }: { ocelId: string }) => {
  const scheme = useScheme();
  const [selected, setSelected] = usePageState<string[]>(`instances.selected.${ocelId}`, []);
  const [lineageStored, setLineage] = usePageState<LineageSettings>(`instances.lineage.${ocelId}`, DEFAULT_LINEAGE);
  const [timelineStored, setTimeline] = usePageState<TimelineSettings>(`instances.timeline.${ocelId}`, DEFAULT_TIMELINE);
  const [objectGraphStored, setObjectGraph] = usePageState<ObjectGraphSettings>(`instances.objectGraph.${ocelId}`, DEFAULT_OBJECT_GRAPH);
  const lineageSettings = { ...DEFAULT_LINEAGE, ...lineageStored };
  // Raised by "Reset settings" so that the graphs are laid out again (drops dragged positions, zoom and pan).
  const [lineageLayout, setLineageLayout] = useState(0);
  const [objectGraphLayout, setObjectGraphLayout] = useState(0);
  const objectGraphSettings = useMemo(() => ({ ...DEFAULT_OBJECT_GRAPH, ...objectGraphStored }), [objectGraphStored]);
  const timelineSettings = { ...DEFAULT_TIMELINE, ...timelineStored };
  const [tracesStored, setTraces] = usePageState<ObjectTracesSettings>(`instances.traces.${ocelId}`, DEFAULT_OBJECT_TRACES);
  const tracesSettings = useMemo(() => ({ ...DEFAULT_OBJECT_TRACES, ...tracesStored }), [tracesStored]);
  const lineage = useSelectionLineage(ocelId, selected, lineageSettings);
  // Object types of the log (most handling units first) for fixed colours; the first profile page carries them.
  const { data: profile } = useQuery({
    queryKey: ["locationBasedOcpm", "instances", "profile", ocelId, { limit: 1 }],
    queryFn: ({ signal }) => getHuProfile(ocelId, { limit: 1 }, undefined, undefined, signal),
  });
  const colours = useMemo(() => colourMap((profile?.object_types ?? []).map(([t]) => t), scheme), [profile, scheme]);
  // Double-clicking a handling unit in the lineage or object graph selects it, or unselects it if it is selected.
  const toggle = useCallback((hu: string) => setSelected((s) => (s.includes(hu) ? s.filter((x) => x !== hu) : [...s, hu])), [setSelected]);

  // Handling units of the loaded lineage, selected ones first (siblings only if shown).
  const lineageUnits = useMemo(() => {
    const objects = (lineage.data?.nodes ?? []).filter((n) => n.kind === "object").map((n) => n.node);
    return [...selected, ...objects.filter((o) => !selected.includes(o))];
  }, [lineage.data, selected]);
  const objectGraph = useObjectGraph(ocelId, selected);
  const objectGraphUnits = useMemo(() => (objectGraph.data?.nodes ?? []).filter((n) => n.is_hu).map((n) => n.node), [objectGraph.data]);

  // The timeline has its own list of handling units; it is reset to the selection whenever the selection changes
  // (`basis` is the selection it was last reset to, so a reload keeps the list).
  const [timelineStoredUnits, setTimelineStoredUnits] = usePageState<{ units: string[]; basis: string[] }>(
    `instances.timelineUnits.${ocelId}`,
    { units: [], basis: [] },
  );
  const selectionKey = selected.join("\u0000");
  useEffect(() => {
    if (timelineStoredUnits.basis.join("\u0000") !== selectionKey) setTimelineStoredUnits({ units: selected, basis: selected });
  }, [selectionKey, selected, timelineStoredUnits.basis, setTimelineStoredUnits]);
  const timelineUnits = timelineStoredUnits.units;
  const setTimelineUnits = useCallback((units: string[]) => setTimelineStoredUnits({ units, basis: selected }), [selected, setTimelineStoredUnits]);

  return (
    <Stack gap="md">
      <ChartCard title="HU profile">
        <Text size="xs" c="dimmed">
          One row per handling unit; values use the low-level locations of the selected level (no visits). Tick rows to
          show their lineage, object graph and timeline below; the selection is kept when paging, searching and sorting.
        </Text>
        <HuProfileTable ocelId={ocelId} selected={selected} onSelected={setSelected} />
      </ChartCard>
      {selected.length === 0 ? (
        <Text size="sm" c="dimmed">Select one or more handling units in the HU profile to see their lineage, object graph and timeline.</Text>
      ) : (
        <>
          <SelectionBar selected={selected} onChange={setSelected} />
          <ChartCard title="Lineage" onReset={() => {
              setLineage(DEFAULT_LINEAGE);
              setLineageLayout((k) => k + 1);
            }}>
            <LineageSettingsRow settings={lineageSettings} onChange={setLineage} />
            <LineageChart layoutKey={lineageLayout} query={lineage} colours={colours} settings={lineageSettings} onToggle={toggle} />
          </ChartCard>
          <ChartCard title="Object graph" onReset={() => {
              setObjectGraph(DEFAULT_OBJECT_GRAPH);
              setObjectGraphLayout((k) => k + 1);
            }}>
            <ObjectGraphChart
              layoutKey={objectGraphLayout}
              ocelId={ocelId}
              handlingUnits={selected}
              colours={colours}
              settings={objectGraphSettings}
              onChange={setObjectGraph}
              onToggle={toggle}
            />
          </ChartCard>
          <ChartCard title="Object traces" onReset={() => setTraces(DEFAULT_OBJECT_TRACES)}>
            <ObjectTracesChart ocelId={ocelId} handlingUnits={selected} colours={colours} settings={tracesSettings} onChange={setTraces} />
          </ChartCard>
          <ChartCard title="HU timeline" onReset={() => setTimeline(DEFAULT_TIMELINE)}>
            <TimelineUnitsBar
              units={timelineUnits}
              onChange={setTimelineUnits}
              selected={selected}
              lineage={lineageUnits}
              objectGraph={objectGraphUnits}
            />
            <TimelineSettingsRow settings={timelineSettings} onChange={setTimeline} hasHighLevel={profile?.has_high_level ?? false} />
            <HuTimelineChart ocelId={ocelId} handlingUnits={timelineUnits} settings={timelineSettings} />
          </ChartCard>
        </>
      )}
    </Stack>
  );
};

/** The page. */
export default function Instances() {
  return <ModulePage title="Instances">{({ ocelId }) => <InstancesContent ocelId={ocelId} />}</ModulePage>;
}
