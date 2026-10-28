// Data overview charts: events sunburst, E2HU chart, HU chart. Clicking a segment adds the
// matching page filter value. Documented in docs/pages/overview.md, section "Data overview charts".
import type { ReactNode } from "react";
import { Alert, Box, Card, ColorSwatch, Group, Loader, SimpleGrid, Stack, Text } from "@mantine/core";
import type { Segment } from "../api/locationBasedOcpm";
import { useGetDataCharts } from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import { filterParams, filterRequest, type PageFilter, usePageFilter } from "../lib/filters";
import { num, pct } from "../lib/format";
import { OTHER, STATUS } from "../lib/palette";
import { plotConfig, ThemedPlot, useScheme } from "./plots";

/** Height of each chart in pixels ("rather small"). */
const HEIGHT = 220;

/** Hover texts of segments that need an explanation. */
const NOTES: Record<string, string> = {
  "not tested": "fewer than two located handling units: agreeing by definition, but nothing is compared",
  "⊥": "no location at any level",
};

type Add = (segment: Segment) => void;

/** Adds the segment's filter value to the page filter (once). */
const useAddFilter = (ocelId: string): Add => {
  const [, setFilter] = usePageFilter(ocelId);
  return (segment) => {
    const target = segment.filter;
    if (!target) return;
    const key = target.filter as keyof PageFilter;
    setFilter((f) => {
      const values = f[key] as string[];
      return values.includes(target.value) ? f : { ...f, [key]: [...values, target.value] };
    });
  };
};

/** Hover text of a segment: label, count and share, note, and what a click does. */
const hover = (s: Segment, total: number, unit: string) =>
  [
    `<b>${s.label}</b>`,
    `${num(s.count)} ${unit} (${pct(s.count / total)})`,
    NOTES[s.label],
    s.filter ? `click: add filter "${s.filter.value}"` : undefined,
  ]
    .filter(Boolean)
    .join("<br>");

/** Values of the sunburst's rings in display order (as in `overview/data_charts.py`). */
const RINGS: [string, string[]][] = [
  ["located", ["fully located", "partially located", "unlocated"]],
  ["type", ["movement", "transformation", "movement and transformation", "other"]],
  ["agreement", ["agreeing", "not agreeing", "not tested"]],
];

/** Legend beneath a chart: one swatch per value, in display order, optionally with a title. */
const Legend = ({ items, title }: { items: { label: string; colour: string }[]; title?: string }) => (
  <Group gap={8} justify="center">
    {title && (
      <Text size="xs" c="dimmed">
        {title}:
      </Text>
    )}
    {items.map((item) => (
      <Group key={item.label} gap={4} wrap="nowrap">
        <ColorSwatch color={item.colour} size={10} />
        <Text size="xs">{item.label}</Text>
      </Group>
    ))}
  </Group>
);

/** A small card with title, chart and legend beneath. */
const ChartCard = ({ title, sub, children, legend }: { title: string; sub: string; children: ReactNode; legend: ReactNode }) => (
  <Card withBorder padding="xs">
    <Stack gap={4}>
      <Text size="sm" fw={600}>
        {title}
      </Text>
      <Text size="xs" c="dimmed">
        {sub}
      </Text>
      <Box h={HEIGHT}>{children}</Box>
      {legend}
    </Stack>
  </Card>
);

/** Layout shared by the three charts: no margins, no plotly legend. */
const layout = { height: HEIGHT, margin: { l: 0, r: 0, t: 0, b: 0 }, showlegend: false };

/** Donut of flat segments (E2HU chart, HU chart). */
const Donut = ({ name, segments, unit, onAdd }: { name: string; segments: Segment[]; unit: string; onAdd: Add }) => {
  const scheme = useScheme();
  const total = segments.reduce((sum, s) => sum + s.count, 0);
  return (
    <ThemedPlot
      data={[
        {
          type: "pie",
          hole: 0.5,
          sort: false,
          direction: "clockwise",
          labels: segments.map((s) => s.label),
          values: segments.map((s) => s.count),
          customdata: segments.map((_, i) => i) as unknown as number[],
          marker: { colors: segments.map((s) => STATUS[scheme][s.label] ?? OTHER[scheme]) },
          textinfo: "none",
          hovertext: segments.map((s) => hover(s, total, unit)),
          hoverinfo: "text",
        },
      ]}
      layout={layout}
      config={plotConfig(name)}
      style={{ width: "100%" }}
      onClick={(e) => {
        const point = e.points?.[0] as { customdata?: number } | undefined;
        const segment = point?.customdata === undefined ? undefined : segments[point.customdata];
        if (segment) onAdd(segment);
      }}
    />
  );
};

/** Events sunburst: inner ring locatedness, middle ring type, outer ring agreement. */
const Sunburst = ({ segments, onAdd }: { segments: Segment[]; onAdd: Add }) => {
  const scheme = useScheme();
  const total = segments.filter((s) => s.parent === "").reduce((sum, s) => sum + s.count, 0);
  return (
    <ThemedPlot
      data={[
        {
          type: "sunburst",
          ids: segments.map((s) => s.id),
          labels: segments.map((s) => s.label),
          parents: segments.map((s) => s.parent),
          values: segments.map((s) => s.count),
          branchvalues: "total",
          sort: false,
          customdata: segments.map((_, i) => i) as unknown as number[],
          marker: { colors: segments.map((s) => STATUS[scheme][s.label] ?? OTHER[scheme]) },
          textinfo: "none",
          hovertext: segments.map((s) => hover(s, total, "events")),
          hoverinfo: "text",
        },
      ]}
      layout={layout}
      config={plotConfig("Events")}
      style={{ width: "100%" }}
      onSunburstClick={(e) => {
        const point = e.points?.[0] as { customdata?: number } | undefined;
        const segment = point?.customdata === undefined ? undefined : segments[point.customdata];
        if (segment) onAdd(segment);
        return false; // no zoom into the segment
      }}
    />
  );
};

/** Legend entries of a list of labels, in the given order. */
const legendOf = (labels: string[], scheme: "light" | "dark") =>
  labels.map((label) => ({ label, colour: STATUS[scheme][label] ?? OTHER[scheme] }));

/** The three data overview charts in one row. */
export const DataCharts = ({ ocelId }: { ocelId: string }) => {
  const [filter] = usePageFilter(ocelId);
  const scheme = useScheme();
  const onAdd = useAddFilter(ocelId);
  const { data, error } = useGetDataCharts(ocelId, filterParams(filter), { request: filterRequest });
  if (error) return <Alert color="red">{errorText(error)}</Alert>;
  if (!data) return <Loader size="sm" />;
  const kept = (what: string) => (data.filtered ? `kept ${what}` : what);
  const present = new Set(data.events.map((s) => s.label));
  return (
    <SimpleGrid cols={{ base: 1, md: 3 }} spacing="sm">
      <ChartCard
        title="Events"
        sub={`${kept("events")} · inner: located · middle: type · outer: agreement (Level ${data.level})`}
        legend={
          <Stack gap={2}>
            {RINGS.map(([ring, values]) => (
              <Legend key={ring} title={ring} items={legendOf(values.filter((v) => present.has(v)), scheme)} />
            ))}
          </Stack>
        }
      >
        <Sunburst segments={data.events} onAdd={onAdd} />
      </ChartCard>
      <ChartCard
        title="Relations: first level with a location"
        sub={`${kept("hu-event relations")} · all levels`}
        legend={<Legend items={data.relations.map((s) => ({ label: s.label === "⊥" ? "⊥" : `Level ${s.label}`, colour: STATUS[scheme][s.label] }))} />}
      >
        <Donut name="Relations first level" segments={data.relations} unit="relations" onAdd={onAdd} />
      </ChartCard>
      <ChartCard
        title="Handling units"
        sub={`${kept("handling units")} · located at Level ${data.level}`}
        legend={<Legend items={legendOf(data.handling_units.map((s) => s.label), scheme)} />}
      >
        <Donut name="Handling units located" segments={data.handling_units} unit="handling units" onAdd={onAdd} />
      </ChartCard>
    </SimpleGrid>
  );
};
