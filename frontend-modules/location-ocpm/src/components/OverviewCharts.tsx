// Overview charts: Activities, Locations and Movement activities bar charts in one row, then the
// location × activity heatmap. Counting happens in the backend (`overview/overview_charts.py`);
// this file draws, colours and turns clicks into filter values.
// Documented in docs/pages/overview.md, section "Overview charts".
import { Alert, Box, Card, ColorSwatch, Group, Loader, SegmentedControl, Select, SimpleGrid, Stack, Text, Tooltip } from "@mantine/core";
import { useElementSize } from "@mantine/hooks";
import type { ReactNode } from "react";
import {
  type Bar,
  type BarChart as BarChartData,
  type GetBarChartBy,
  type GetBarChartChart,
  type GetBarChartMeasure,
  type GetBarChartMode,
  type GetHeatmapEvents,
  useGetBarChart,
  useGetHeatmap,
} from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import { type FilterKey, filterParams, filterRequest, type PageFilter, usePageFilter, withValue } from "../lib/filters";
import { num, pct } from "../lib/format";
import { usePageState } from "../lib/pageState";
import { categoricalColour, OTHER, plotlyScale, type Scheme, SEQUENTIAL, UI } from "../lib/palette";
import { plotConfig, ThemedPlot, useScheme } from "./plots";

/** Labels the backend uses for missing values, the summed rest, and mixed object types. */
const MISSING = "–";
const OTHER_LABEL = "other";
const SEVERAL_TYPES = "[several types]";

/** Height of each bar chart in pixels. */
const HEIGHT = 300;
/** Approximate width of one character of a 12px label, to cut labels to ¼ of the chart width. */
const CHAR_WIDTH = 6.5;

type End = "top" | "bottom";
type Settings = { measure: GetBarChartMeasure; by: GetBarChartBy; mode: GetBarChartMode };

/** Hover texts of the controls (concept section "Overview charts"). */
const INFO = {
  measure:
    "relations: hu-event relations, each under its own value. events: only agreeing events, each once under the common value of its handling units ('–' if none has one); not agreeing events are left out.",
  mode: "most frequent: bar = events or relations of the activity. most locations: bar = number of distinct locations (≠ ⊥) of the activity, counted over its relations.",
  end: "top 10: the 10 largest bars, the rest summed into a grey 'other' bar. bottom 10: the 10 smallest bars, the rest left out. Also applies to both axes of the heatmap.",
  events: "Keep all relations or events, only those of movement events, or only those of transformation events.",
};

/** Filter list a value of a dimension goes to on a click (none: no filter matches). */
const FILTER_OF: Record<string, FilterKey | undefined> = {
  activity: "activities",
  location: "locations",
  object_type: "object_types",
};

/** Options of the "by" dropdown, per chart. */
const BY_OPTIONS: Record<GetBarChartChart, { value: GetBarChartBy; label: string }[]> = {
  activities: [
    { value: "none", label: "none" },
    { value: "location", label: "location" },
    { value: "object_type", label: "object type" },
  ],
  locations: [
    { value: "none", label: "none" },
    { value: "activity", label: "activity" },
    { value: "object_type", label: "object type" },
  ],
  movements: [
    { value: "none", label: "none" },
    { value: "movement_status", label: "movement status" },
    { value: "location", label: "location" },
    { value: "object_type", label: "object type" },
  ],
};

/** Title, bar dimension and default settings per chart. */
const CHARTS: Record<GetBarChartChart, { title: string; bar: string; defaults: Settings }> = {
  activities: { title: "Activities", bar: "activity", defaults: { measure: "relations", by: "location", mode: "frequent" } },
  locations: { title: "Locations", bar: "location", defaults: { measure: "relations", by: "activity", mode: "frequent" } },
  movements: {
    title: "Movement activities",
    bar: "activity",
    defaults: { measure: "relations", by: "movement_status", mode: "frequent" },
  },
};

/**
 * Adds the clicked values to the page filter: each (dimension, value) pair goes to the
 * dimension's include list ("–" as "[unknown]"; "other" and "[several types]" add nothing).
 * Chart locations are loc (post), so a location switches the role "pre" to "post".
 */
const useAddValues = (ocelId: string) => {
  const [, setFilter] = usePageFilter(ocelId);
  return (pairs: [string, string][]) =>
    setFilter((f) =>
      pairs.reduce<PageFilter>((acc, [dimension, value]) => {
        const key = FILTER_OF[dimension];
        if (!key || value === OTHER_LABEL || value === SEVERAL_TYPES) return acc;
        const next = withValue(acc, key, key === "locations" && value === MISSING ? "[unknown]" : value);
        return key === "locations" && next.location_role === "before" ? { ...next, location_role: "after" } : next;
      }, f),
    );
};

/** Colour of a segment value: its rank in the chart, grey for "other" and "–". */
const colourOf = (value: string, colours: string[], scheme: Scheme) => {
  const index = colours.indexOf(value);
  return index < 0 ? OTHER[scheme] : categoricalColour(index, scheme);
};

/** A label cut to `chars` characters, with "…". */
const cut = (label: string, chars: number) => (label.length > chars ? `${label.slice(0, Math.max(1, chars - 1))}…` : label);

/** Legend beside a chart (at most ¼ of the card width): one swatch per value; long names are cut. */
const Legend = ({ items, width }: { items: { label: string; colour: string; hatched?: boolean }[]; width: number }) => (
  <Stack gap={2} maw={width} style={{ flexShrink: 0, overflow: "hidden" }}>
    {items.map((item) => (
      <Tooltip key={item.label} label={item.label} withArrow openDelay={300}>
        <Group gap={4} wrap="nowrap">
          <ColorSwatch
            color={item.colour}
            size={10}
            style={{
              flexShrink: 0,
              backgroundImage: item.hatched ? "repeating-linear-gradient(45deg, transparent 0 2px, #fff 2px 3px)" : undefined,
            }}
          />
          <Text size="xs" truncate>
            {item.label}
          </Text>
        </Group>
      </Tooltip>
    ))}
  </Stack>
);

/** A small inline control with a hover text. */
const Control = ({ info, children }: { info: string; children: ReactNode }) => (
  <Tooltip label={info} multiline maw={360} withArrow openDelay={300}>
    <Box>{children}</Box>
  </Tooltip>
);

/** Hover text of one segment (or of a plain bar). */
const hoverText = (bar: Bar, unit: string, segment?: { value: string; count: number }, byLabel?: string) => {
  const lines = [`<b>${bar.label}</b>: ${num(bar.count)} ${unit}`];
  if (segment && byLabel) lines.push(`${byLabel} ${segment.value}: ${num(segment.count)} (${pct(segment.count / bar.count)})`);
  if (bar.left_out) lines.push(`${num(bar.left_out)} not agreeing events left out`);
  if (bar.locations?.length) lines.push(`locations: ${bar.locations.join(", ")}`);
  if (bar.label === OTHER_LABEL) lines.push(`sum of ${num(bar.bars)} further bars`);
  return lines.join("<br>");
};

/** Plotly traces of a stacked horizontal bar chart: one trace per segment value, largest bar on top. */
const traces = (data: BarChartData, by: GetBarChartBy, unit: string, byLabel: string, scheme: Scheme) => {
  const bars = data.other ? [...data.bars, data.other] : data.bars;
  const y = bars.map((b) => b.label);
  const grey = OTHER[scheme];
  if (by === "none") {
    return [
      {
        type: "bar" as const,
        orientation: "h" as const,
        y,
        x: bars.map((b) => b.count),
        customdata: bars.map((b) => [b.label, ""]),
        marker: {
          color: bars.map((b) => (b.label === MISSING || b === data.other ? grey : UI[scheme].primary)),
          pattern: { shape: bars.map((b) => (b.label === MISSING ? "/" : "")) },
        },
        hovertext: bars.map((b) => hoverText(b, unit)),
        hoverinfo: "text" as const,
      },
    ];
  }
  const values = [...data.colours, OTHER_LABEL, MISSING];
  const perValue = values
    .map((value) => {
      const shown = data.bars.flatMap((b) => {
        const segment = (b.segments ?? []).find((s) => s.value === value);
        return segment ? [{ bar: b, segment }] : [];
      });
      return {
        type: "bar" as const,
        orientation: "h" as const,
        name: value,
        y: shown.map(({ bar }) => bar.label),
        x: shown.map(({ segment }) => segment.count),
        customdata: shown.map(({ bar }) => [bar.label, value]),
        marker: {
          color: colourOf(value, data.colours, scheme),
          // "–" values and the "–" bar are hatched.
          pattern: { shape: shown.map(({ bar }) => (value === MISSING || bar.label === MISSING ? "/" : "")) },
        },
        hovertext: shown.map(({ bar, segment }) => hoverText(bar, unit, segment, byLabel)),
        hoverinfo: "text" as const,
      };
    })
    .filter((t) => t.y.length);
  if (data.other) {
    perValue.push({
      type: "bar",
      orientation: "h",
      name: OTHER_LABEL,
      y: [data.other.label],
      x: [data.other.count],
      customdata: [[OTHER_LABEL, ""]],
      marker: { color: grey, pattern: { shape: [""] } },
      hovertext: [hoverText(data.other, unit)],
      hoverinfo: "text",
    });
  }
  return perValue;
};

/** One bar chart card: title, its controls, the chart and its legend. */
const BarChartCard = ({ ocelId, chart, end }: { ocelId: string; chart: GetBarChartChart; end: End }) => {
  const { title, bar, defaults } = CHARTS[chart];
  const [filter] = usePageFilter(ocelId);
  const [settings, setSettings] = usePageState<Settings>(`charts.${chart}`, defaults);
  const scheme = useScheme();
  const addValues = useAddValues(ocelId);
  const { ref, width } = useElementSize();
  const mostLocations = chart === "activities" && settings.mode === "locations";
  const by = mostLocations && settings.by === "object_type" ? "none" : settings.by;
  const measure = chart === "movements" ? "relations" : settings.measure;
  const { data, error } = useGetBarChart(
    ocelId,
    { ...filterParams(filter), chart, measure, by, mode: settings.mode, end },
    { request: filterRequest },
  );
  const set = (change: Partial<Settings>) => setSettings((s) => ({ ...s, ...change }));
  const byOptions = BY_OPTIONS[chart].filter((o) => !(mostLocations && o.value === "object_type"));
  const byLabel = byOptions.find((o) => o.value === by)?.label ?? "";
  const unit = mostLocations ? "locations" : measure;
  const labelChars = Math.max(6, Math.floor(width / 4 / CHAR_WIDTH));
  const sub = [
    mostLocations ? "distinct locations" : measure === "events" ? "agreeing events" : "hu-event relations",
    chart === "movements" && "ranked by moved relations",
    data?.left_out ? `${num(data.left_out)} not agreeing events left out` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  const legend =
    data && by !== "none"
      ? [
          ...data.colours.map((v) => ({ label: v, colour: colourOf(v, data.colours, scheme) })),
          ...(data.bars.some((b) => b.segments?.some((s) => s.value === OTHER_LABEL)) ? [{ label: OTHER_LABEL, colour: OTHER[scheme] }] : []),
          ...(data.bars.some((b) => b.segments?.some((s) => s.value === MISSING))
            ? [{ label: MISSING, colour: OTHER[scheme], hatched: true }]
            : []),
        ]
      : [];
  return (
    <Card withBorder padding="xs">
      <Stack gap={4} ref={ref}>
        <Text size="sm" fw={600}>
          {title}
        </Text>
        <Group gap={6} wrap="wrap">
          {chart !== "movements" && (
            <Control info={INFO.measure}>
              <SegmentedControl
                size="xs"
                data={["relations", "events"]}
                value={measure}
                onChange={(v) => set({ measure: v as GetBarChartMeasure })}
                disabled={mostLocations}
              />
            </Control>
          )}
          {chart === "activities" && (
            <Control info={INFO.mode}>
              <SegmentedControl
                size="xs"
                data={[
                  { value: "frequent", label: "most frequent" },
                  { value: "locations", label: "most locations" },
                ]}
                value={settings.mode}
                onChange={(v) => set({ mode: v as GetBarChartMode })}
              />
            </Control>
          )}
          <Select
            size="xs"
            w={150}
            aria-label="by"
            leftSection={<Text size="xs">by</Text>}
            data={byOptions}
            value={by}
            onChange={(v) => v && set({ by: v as GetBarChartBy })}
            allowDeselect={false}
            comboboxProps={{ withinPortal: true }}
          />
        </Group>
        <Text size="xs" c="dimmed">
          {sub}
        </Text>
        {error ? (
          <Alert color="red">{errorText(error)}</Alert>
        ) : !data ? (
          <Loader size="sm" />
        ) : !data.bars.length ? (
          <Text size="xs" c="dimmed">
            nothing to show
          </Text>
        ) : (
          <Group gap="xs" wrap="nowrap" align="center">
            <Box h={HEIGHT} style={{ flex: 1, minWidth: 0 }}>
              <ThemedPlot
                data={traces(data, by, unit, byLabel, scheme)}
                layout={{
                  height: HEIGHT,
                  barmode: "stack",
                  showlegend: false,
                  bargap: 0.25,
                  margin: { l: 0, r: 8, t: 4, b: 24 },
                  yaxis: {
                    // Bars in the backend's order (largest first, "other" last), from the top.
                    categoryorder: "array",
                    categoryarray: [...data.bars, ...(data.other ? [data.other] : [])].map((b) => b.label),
                    autorange: "reversed",
                    automargin: true,
                    tickfont: { size: 11 },
                    tickvals: [...data.bars, ...(data.other ? [data.other] : [])].map((b) => b.label),
                    ticktext: [...data.bars, ...(data.other ? [data.other] : [])].map((b) => cut(b.label, labelChars)),
                  },
                  xaxis: { automargin: true, tickfont: { size: 10 } },
                }}
                config={plotConfig(title)}
                style={{ width: "100%" }}
                onClick={(e) => {
                  const point = e.points?.[0] as { customdata?: [string, string] } | undefined;
                  if (!point?.customdata) return;
                  const [barValue, segmentValue] = point.customdata;
                  addValues([
                    [bar, barValue],
                    [by, segmentValue],
                  ]);
                }}
              />
            </Box>
            {legend.length > 0 && <Legend items={legend} width={Math.max(60, width / 4)} />}
          </Group>
        )}
      </Stack>
    </Card>
  );
};

/** The location × activity heatmap: counts in the cells, a grey "–" row for ⊥. */
const HeatmapCard = ({ ocelId, end }: { ocelId: string; end: End }) => {
  const [filter] = usePageFilter(ocelId);
  const [settings, setSettings] = usePageState<{ measure: GetBarChartMeasure; events: GetHeatmapEvents }>("charts.heatmap", {
    measure: "relations",
    events: "all",
  });
  const scheme = useScheme();
  const addValues = useAddValues(ocelId);
  const { data, error } = useGetHeatmap(ocelId, { ...filterParams(filter), ...settings, end }, { request: filterRequest });
  const set = (change: Partial<typeof settings>) => setSettings((s) => ({ ...s, ...change }));
  const unit = settings.measure === "events" ? "agreeing events" : "hu-event relations";
  const height = 80 + 32 * Math.max(3, data?.rows.length ?? 0);
  // Cells with 0 stay empty; the "–" row is drawn by a second, grey trace.
  const cells = (keep: (row: string) => boolean) =>
    data?.cells.map((row, i) => row.map((n) => (n && keep(data.rows[i]) ? n : null))) ?? [];
  const common = {
    type: "heatmap" as const,
    x: data?.columns,
    y: data?.rows,
    xgap: 2,
    ygap: 2,
    texttemplate: "%{z}",
    hovertemplate: `location %{y}<br>activity %{x}<br>%{z} ${unit}<extra></extra>`,
  };
  return (
    <Card withBorder padding="xs">
      <Stack gap={4}>
        <Group justify="space-between">
          <Text size="sm" fw={600}>
            Location × activity{" "}
            <Text span size="xs" c="dimmed" fw={400}>
              {unit}
              {data?.left_out ? ` · ${num(data.left_out)} not agreeing events left out` : ""}
            </Text>
          </Text>
          <Group gap={6}>
            <Control info={INFO.measure}>
              <SegmentedControl
                size="xs"
                data={["relations", "events"]}
                value={settings.measure}
                onChange={(v) => set({ measure: v as GetBarChartMeasure })}
              />
            </Control>
            <Control info={INFO.events}>
              <SegmentedControl
                size="xs"
                data={["all", "movements", "transformations"]}
                value={settings.events}
                onChange={(v) => set({ events: v as GetHeatmapEvents })}
              />
            </Control>
          </Group>
        </Group>
        {error ? (
          <Alert color="red">{errorText(error)}</Alert>
        ) : !data ? (
          <Loader size="sm" />
        ) : !data.rows.length ? (
          <Text size="xs" c="dimmed">
            nothing to show
          </Text>
        ) : (
          <ThemedPlot
            data={[
              { ...common, z: cells((r) => r !== MISSING), colorscale: plotlyScale(SEQUENTIAL[scheme]), showscale: false },
              {
                ...common,
                z: cells((r) => r === MISSING),
                colorscale: [
                  [0, OTHER[scheme]],
                  [1, OTHER[scheme]],
                ],
                showscale: false,
              },
            ]}
            layout={{
              height,
              margin: { l: 0, r: 8, t: 4, b: 0 },
              yaxis: { autorange: "reversed", automargin: true, type: "category", categoryorder: "array", categoryarray: data.rows, tickfont: { size: 11 } },
              xaxis: { automargin: true, type: "category", categoryorder: "array", categoryarray: data.columns, tickangle: -30, tickfont: { size: 11 } },
            }}
            config={plotConfig("Location activity heatmap")}
            style={{ width: "100%" }}
            onClick={(e) => {
              const point = e.points?.[0] as { x?: string; y?: string } | undefined;
              if (point?.x === undefined || point.y === undefined) return;
              addValues([
                ["activity", String(point.x)],
                ["location", String(point.y)],
              ]);
            }}
          />
        )}
      </Stack>
    </Card>
  );
};

/** The overview charts: top/bottom switch, three bar charts in one row, then the heatmap. */
export const OverviewCharts = ({ ocelId }: { ocelId: string }) => {
  const [end, setEnd] = usePageState<End>("charts.end", "top");
  return (
    <Stack gap="xs">
      <Group gap="xs">
        <Text size="sm" fw={600}>
          Overview charts
        </Text>
        <Control info={INFO.end}>
          <SegmentedControl
            size="xs"
            data={[
              { value: "top", label: "top 10" },
              { value: "bottom", label: "bottom 10" },
            ]}
            value={end}
            onChange={(v) => setEnd(v as End)}
          />
        </Control>
      </Group>
      <SimpleGrid cols={{ base: 1, md: 3 }} spacing="sm">
        <BarChartCard ocelId={ocelId} chart="activities" end={end} />
        <BarChartCard ocelId={ocelId} chart="locations" end={end} />
        <BarChartCard ocelId={ocelId} chart="movements" end={end} />
      </SimpleGrid>
      <HeatmapCard ocelId={ocelId} end={end} />
    </Stack>
  );
};
