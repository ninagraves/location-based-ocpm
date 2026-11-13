// Data overview charts: events sunburst, E2HU chart, HU chart, locations sunburst. Clicking a segment sets the
// matching page filter value (replacing other values of its category). Documented in docs/pages/overview.md, section "Data overview charts".
import { type ReactNode, useState } from "react";
import { Alert, Box, Card, ColorSwatch, Group, Loader, SegmentedControl, SimpleGrid, Stack, Text } from "@mantine/core";
import type { Segment } from "../api/locationBasedOcpm";
import { useGetDataCharts } from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import { type FilterKey, usePageFilter, withValue } from "../lib/filters";
import { num, pct } from "../lib/format";
import { CATEGORICAL, OTHER, STATUS } from "../lib/palette";
import { plotConfig, ScrollLegend, ThemedPlot, useScheme } from "./plots";

/** Height of each chart in pixels ("rather small"). */
const HEIGHT = 220;

/** Hover texts of segments that need an explanation. */
const NOTES: Record<string, string> = {
  "not tested": "fewer than two located handling units: agreeing by definition, but nothing is compared",
  "agreeing at high level only": "its handling units are at different locations, but at the same high-level location",
  "⊥": "no location at any level",
};

type Add = (segment: Segment) => void;

/** Adds the segment's filter value to the page filter, replacing other values of its category. */
const useAddFilter = (ocelId: string): Add => {
  const [, setFilter] = usePageFilter(ocelId);
  return (segment) => {
    const target = segment.filter;
    if (target) setFilter((f) => withValue(f, target.filter as FilterKey, target.value));
  };
};

/** Shown name of a relations-chart segment: "Level 2", or "not located" for ⊥. */
const levelName = (label: string) => (label === "⊥" ? "not located" : `Level ${label}`);

/** Hover text of a segment: label (or its shown name), count and share, and a note where needed. */
const hover = (s: Segment, total: number, unit: string, name: (label: string) => string = (l) => l) =>
  [`<b>${name(s.label)}</b>`, `${num(s.count)} ${unit} (${pct(s.count / total)})`, NOTES[s.label]].filter(Boolean).join("<br>");

/** Values of the sunburst's rings in display order (as in `overview/data_charts.py`); the types are the
 * occurring combinations of movement, transformation and processing, in the backend's order. */
const RINGS: [string, string[] | null][] = [
  ["type", null],
  ["located", ["fully located", "partially located", "unlocated"]],
  ["agreement", ["agreeing", "agreeing at high level only", "not agreeing", "not tested"]],
];

/** Legend beside a chart: one swatch per value, one per line, optionally with a title. */
const Legend = ({ items, title }: { items: { label: string; colour: string }[]; title?: string }) => (
  <Stack gap={2}>
    {title && (
      <Text size="xs" c="dimmed">
        {title}
      </Text>
    )}
    {items.map((item) => (
      <Group key={item.label} gap={4} wrap="nowrap">
        <ColorSwatch color={item.colour} size={10} style={{ flexShrink: 0 }} />
        <Text size="xs" style={{ whiteSpace: "nowrap" }}>
          {item.label}
        </Text>
      </Group>
    ))}
  </Stack>
);

/** A small card with title, and the chart with its legend to the right (scrolling if it is taller than the chart). */
const ChartCard = ({
  title,
  sub,
  children,
  legend,
  control,
}: {
  title: string;
  sub: string;
  children: ReactNode;
  legend: ReactNode;
  control?: ReactNode;
}) => (
  <Card withBorder padding="xs">
    <Stack gap={4}>
      <Group justify="space-between" gap="xs">
        <Text size="sm" fw={600}>
          {title}
        </Text>
        {control}
      </Group>
      <Text size="xs" c="dimmed">
        {sub}
      </Text>
      <Group gap="xs" wrap="nowrap" align="center">
        <Box h={HEIGHT} style={{ flex: 1, minWidth: 0 }}>
          {children}
        </Box>
        <ScrollLegend height={HEIGHT}>{legend}</ScrollLegend>
      </Group>
    </Stack>
  </Card>
);

/** Layout shared by the three charts: no margins, no plotly legend. */
const layout = { height: HEIGHT, margin: { l: 0, r: 0, t: 0, b: 0 }, showlegend: false };

/** Donut of flat segments (E2HU chart, HU chart). */
const Donut = ({
  name,
  segments,
  unit,
  onAdd,
  labelOf,
}: {
  name: string;
  segments: Segment[];
  unit: string;
  onAdd: Add;
  labelOf?: (label: string) => string;
}) => {
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
          hovertext: segments.map((s) => hover(s, total, unit, labelOf)),
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

/** A sunburst (events: type, locatedness, agreement; locations: type, high-level location). */
const Sunburst = ({
  segments,
  onAdd,
  name = "Events",
  unit = "events",
  colour,
}: {
  segments: Segment[];
  onAdd: Add;
  name?: string;
  unit?: string;
  colour?: (s: Segment) => string;
}) => {
  const scheme = useScheme();
  const total = segments.filter((s) => s.parent === "").reduce((sum, s) => sum + s.count, 0);
  const colourOf = colour ?? ((s: Segment) => STATUS[scheme][s.label] ?? OTHER[scheme]);
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
          marker: { colors: segments.map(colourOf) },
          textinfo: "none",
          hovertext: segments.map((s) => hover(s, total, unit)),
          hoverinfo: "text",
        },
      ]}
      layout={layout}
      config={plotConfig(name)}
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

/** Colours of high-level locations: ranked by their total (largest first), one palette colour each. */
const highLevelColours = (segments: Segment[], scheme: "light" | "dark") => {
  const totals = new Map<string, number>();
  for (const s of segments.filter((s) => s.parent !== "")) totals.set(s.label, (totals.get(s.label) ?? 0) + s.count);
  const ranked = [...totals.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([label]) => label);
  return new Map(ranked.map((label, i) => [label, CATEGORICAL[scheme][i % CATEGORICAL[scheme].length]]));
};

/** Locations sunburst: inner ring location type, outer ring high-level location; # locations or # relations. */
const LocationsChart = ({ locations, relations, unlocated, onAdd }: { locations: Segment[]; relations: Segment[]; unlocated: number; onAdd: Add }) => {
  const scheme = useScheme();
  const [measure, setMeasure] = useState<"locations" | "relations">("locations");
  const segments = measure === "locations" ? locations : relations;
  const colours = highLevelColours(segments, scheme);
  const colour = (s: Segment) => (s.parent === "" ? STATUS[scheme][s.label] ?? OTHER[scheme] : colours.get(s.label) ?? OTHER[scheme]);
  const types = segments.filter((s) => s.parent === "").map((s) => s.label);
  const highLevel = [...colours.keys()];
  return (
    <ChartCard
      title="Locations"
      control={
        <SegmentedControl
          size="xs"
          data={[
            { value: "locations", label: "# locations" },
            { value: "relations", label: "# relations" },
          ]}
          value={measure}
          onChange={(v) => setMeasure(v as "locations" | "relations")}
        />
      }
      sub={
        measure === "locations"
          ? "locations · inner-outer: type, high-level location"
          : `relations by location · inner-outer: type, high-level location${unlocated ? ` · ${num(unlocated)} without a location left out` : ""}`
      }
      legend={
        <Stack gap={6}>
          <Legend title="type" items={legendOf(types, scheme)} />
          {highLevel.length > 0 && <Legend title="high-level" items={highLevel.map((label) => ({ label, colour: colours.get(label)! }))} />}
        </Stack>
      }
    >
      <Sunburst segments={segments} onAdd={onAdd} name="Locations" unit={measure} colour={colour} />
    </ChartCard>
  );
};

/**
 * The four data overview charts in a 2×2 grid. They sit in the configuration section, above the
 * filter bar, so they always show the whole log; a click still sets a page filter.
 */
export const DataCharts = ({ ocelId }: { ocelId: string }) => {
  const scheme = useScheme();
  const onAdd = useAddFilter(ocelId);
  const { data, error } = useGetDataCharts(ocelId);
  if (error) return <Alert color="red">{errorText(error)}</Alert>;
  if (!data) return <Loader size="sm" />;
  const present = new Set(data.events.map((s) => s.label));
  const types = data.events.filter((s) => s.parent === "").map((s) => s.label);
  return (
    <SimpleGrid cols={{ base: 1, md: 2 }} spacing="sm">
      <ChartCard
        title="Events"
        sub={`events · inner-outer: type, located, agreement (lvl ${data.level})`}
        legend={
          <Stack gap={6}>
            {RINGS.map(([ring, values]) => (
              <Legend key={ring} title={ring} items={legendOf((values ?? types).filter((v) => present.has(v)), scheme)} />
            ))}
          </Stack>
        }
      >
        <Sunburst segments={data.events} onAdd={onAdd} />
      </ChartCard>
      <ChartCard
        title="Relations: first level with a location"
        sub="hu-event relations · all levels"
        legend={<Legend items={data.relations.map((s) => ({ label: levelName(s.label), colour: STATUS[scheme][s.label] }))} />}
      >
        <Donut name="Relations first level" segments={data.relations} unit="relations" onAdd={onAdd} labelOf={levelName} />
      </ChartCard>
      <ChartCard
        title="Handling units"
        sub={`handling units · located at Level ${data.level}`}
        legend={<Legend items={legendOf(data.handling_units.map((s) => s.label), scheme)} />}
      >
        <Donut name="Handling units located" segments={data.handling_units} unit="handling units" onAdd={onAdd} />
      </ChartCard>
      {data.has_context ? (
        <LocationsChart
          locations={data.locations ?? []}
          relations={data.location_relations ?? []}
          unlocated={data.unlocated_relations ?? 0}
          onAdd={onAdd}
        />
      ) : (
        <Card withBorder padding="xs">
          <Text size="sm" fw={600}>
            Locations
          </Text>
          <Text size="xs" c="dimmed">
            no location context configured (high-level locations, vehicles or storage units)
          </Text>
        </Card>
      )}
    </SimpleGrid>
  );
};
