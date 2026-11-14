// The instance page: the HU profile (one row per handling unit; rows can be selected), then, for the selected
// handling units, the lineage chart and the HU timeline, each with its own settings row.
// Documented in docs/pages/instances.md.
import { Button, Card, CloseButton, Group, Pill, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import { getHuProfile } from "../api/locationBasedOcpm";
import { HuProfileTable } from "../components/HuProfileTable";
import { DEFAULT_TIMELINE, HuTimelineChart, type TimelineSettings, TimelineSettingsRow } from "../components/HuTimelineChart";
import {
  DEFAULT_LINEAGE,
  LineageChart,
  type LineageSettings,
  LineageSettingsRow,
  useSelectionLineage,
} from "../components/LineageChart";
import { ModulePage } from "../components/ModulePage";
import { useScheme } from "../components/plots";
import { usePageState } from "../lib/pageState";
import { colourMap } from "../lib/palette";

/** Selected handling units shown at most as pills (the rest as "+ n more"). */
const MAX_PILLS = 30;

/**
 * The selected handling units as removable pills, with "Clear".
 *
 * @param selected The selection.
 * @param onChange Called with the new selection.
 */
const SelectionBar = ({ selected, onChange }: { selected: string[]; onChange: (ids: string[]) => void }) => (
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
  const lineageSettings = { ...DEFAULT_LINEAGE, ...lineageStored };
  const timelineSettings = { ...DEFAULT_TIMELINE, ...timelineStored };
  const lineage = useSelectionLineage(ocelId, selected, lineageSettings);
  // Object types of the log (most handling units first) for fixed colours; the first profile page carries them.
  const { data: profile } = useQuery({
    queryKey: ["locationBasedOcpm", "instances", "profile", ocelId, { limit: 1 }],
    queryFn: ({ signal }) => getHuProfile(ocelId, { limit: 1 }, undefined, signal),
  });
  const colours = useMemo(() => colourMap((profile?.object_types ?? []).map(([t]) => t), scheme), [profile, scheme]);
  const pick = useCallback((hu: string) => setSelected((s) => (s.includes(hu) ? s : [...s, hu])), [setSelected]);

  // Handling units of the loaded lineage, selected ones first (siblings only if shown).
  const lineageUnits = useMemo(() => {
    const objects = (lineage.data?.nodes ?? []).filter((n) => n.kind === "object").map((n) => n.node);
    return [...selected, ...objects.filter((o) => !selected.includes(o))];
  }, [lineage.data, selected]);
  const timelineUnits = timelineSettings.source === "lineage" && lineage.data ? lineageUnits : selected;

  return (
    <Stack gap="md">
      <ChartCard title="HU profile">
        <Text size="xs" c="dimmed">
          One row per handling unit; values use the low-level locations of the selected level (no visits). Tick rows to
          show their lineage and timeline below; the selection is kept when paging, searching and sorting.
        </Text>
        <HuProfileTable ocelId={ocelId} selected={selected} onSelected={setSelected} />
      </ChartCard>
      {selected.length === 0 ? (
        <Text size="sm" c="dimmed">Select one or more handling units in the HU profile to see their lineage and timeline.</Text>
      ) : (
        <>
          <SelectionBar selected={selected} onChange={setSelected} />
          <ChartCard title="Lineage" onReset={() => setLineage(DEFAULT_LINEAGE)}>
            <LineageSettingsRow settings={lineageSettings} onChange={setLineage} />
            <LineageChart query={lineage} colours={colours} settings={lineageSettings} onPick={pick} />
          </ChartCard>
          <ChartCard title="HU timeline" onReset={() => setTimeline(DEFAULT_TIMELINE)}>
            <TimelineSettingsRow
              settings={timelineSettings}
              onChange={setTimeline}
              lineageCount={lineageUnits.length}
              hasHighLevel={profile?.has_high_level ?? false}
            />
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
