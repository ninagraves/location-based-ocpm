// Charts of the transformations page (draft), as in the playground: transformation activities, transformation types,
// transformation locations and unique counts. Counting happens in the backend (`transformations/charts.py`); drawing
// reuses the stacked bars of the overview charts. Documented in docs/pages/transformations.md, section "Charts".
import { Alert, Box, Card, Group, Loader, SegmentedControl, Select, SimpleGrid, Stack, Text } from "@mantine/core";
import { useElementSize } from "@mantine/hooks";
import {
  type GetTransformationBarChartBy,
  type GetTransformationBarChartChart,
  type GetTransformationBarChartPer,
  useGetTransformationBarChart,
} from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import { num } from "../lib/format";
import { usePageState } from "../lib/pageState";
import { OTHER } from "../lib/palette";
import { listRequest, type TransformationFilter } from "../lib/transformations";
import { CHAR_WIDTH, colourOf, cut, HEIGHT, Legend, MISSING, OTHER_LABEL, traces } from "./OverviewCharts";
import { plotConfig, ThemedPlot, useScheme } from "./plots";

type End = "top" | "bottom";

/** Per chart: title, the "by" options (first = default) and the unit. */
const CHARTS: Record<
  GetTransformationBarChartChart,
  { title: string; by: { value: GetTransformationBarChartBy; label: string }[]; unit: string }
> = {
  activities: {
    title: "Transformation activities",
    by: [
      { value: "kind", label: "kind" },
      { value: "transformation_type", label: "transformation type" },
      { value: "location", label: "location" },
      { value: "none", label: "none" },
    ],
    unit: "transformation events",
  },
  transformation_types: {
    title: "Transformation types",
    by: [
      { value: "activity", label: "activity" },
      { value: "kind", label: "kind" },
      { value: "location", label: "location" },
      { value: "none", label: "none" },
    ],
    unit: "transformation events",
  },
  locations: {
    title: "Transformation locations",
    by: [
      { value: "activity", label: "activity" },
      { value: "kind", label: "kind" },
      { value: "transformation_type", label: "transformation type" },
      { value: "none", label: "none" },
    ],
    unit: "transformation events",
  },
  diversity: { title: "Unique counts", by: [{ value: "none", label: "none" }], unit: "" },
};

/** Hover text of the charts' subtitle. */
const LOCATIONS_INFO =
  "Locations are the known locations of an event's handling units after the event (loc at the selected level; high-level locations in high-level mode). An event at several locations counts once at each, an event without any under '–'.";

/** One chart card: title, its controls, the chart and its legend. */
const ChartCard = ({
  ocelId,
  filter,
  chart,
  end,
}: {
  ocelId: string;
  filter: TransformationFilter;
  chart: GetTransformationBarChartChart;
  end: End;
}) => {
  const { title, by: byOptions, unit: chartUnit } = CHARTS[chart];
  const [by, setBy] = usePageState<GetTransformationBarChartBy>(`transformations.charts.${chart}.by`, byOptions[0].value);
  const [per, setPer] = usePageState<GetTransformationBarChartPer>("transformations.charts.diversity.per", "activity");
  const scheme = useScheme();
  const { ref, width } = useElementSize();
  const { data, error } = useGetTransformationBarChart(ocelId, { ...filter, chart, by, per, end }, { request: listRequest });
  const unit =
    chart === "diversity" ? (per === "activity" ? "distinct transformation types" : "distinct activities") : chartUnit;
  const shownBy = chart === "diversity" ? "none" : by;
  const byLabel = byOptions.find((o) => o.value === by)?.label ?? "";
  const labelChars = Math.max(6, Math.floor(width / 4 / CHAR_WIDTH));
  const sub = [
    unit,
    data?.other ? `${num(data.other.bars)} more ${data.other.bars === 1 ? "bar" : "bars"} not shown` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  const legend =
    data && shownBy !== "none"
      ? [
          ...data.colours.map((v) => ({ label: v, colour: colourOf(v, data.colours, scheme, shownBy) })),
          ...(data.bars.some((b) => b.segments?.some((s) => s.value === OTHER_LABEL)) ? [{ label: OTHER_LABEL, colour: OTHER[scheme] }] : []),
          ...(data.bars.some((b) => b.segments?.some((s) => s.value === MISSING))
            ? [{ label: MISSING, colour: OTHER[scheme], hatched: true }]
            : []),
        ]
      : [];
  return (
    <Card withBorder padding="xs">
      <Stack gap={4} ref={ref}>
        <Group gap={6} wrap="wrap" justify="space-between">
          <Text size="sm" fw={600}>
            {chart === "diversity" ? (per === "activity" ? "Transformation types per activity" : "Activities per transformation type") : title}
          </Text>
          {chart === "diversity" ? (
            <SegmentedControl
              size="xs"
              value={per}
              onChange={(v) => setPer(v as GetTransformationBarChartPer)}
              data={[
                { value: "activity", label: "types per activity" },
                { value: "transformation_type", label: "activities per type" },
              ]}
            />
          ) : (
            <Select
              size="xs"
              w={190}
              aria-label="by"
              leftSection={<Text size="xs">by</Text>}
              data={byOptions}
              value={by}
              onChange={(v) => v && setBy(v as GetTransformationBarChartBy)}
              allowDeselect={false}
              comboboxProps={{ withinPortal: true }}
            />
          )}
        </Group>
        <Text size="xs" c="dimmed" title={chart === "locations" || by === "location" ? LOCATIONS_INFO : undefined}>
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
                data={traces(data, shownBy, unit, byLabel, scheme)}
                layout={{
                  height: HEIGHT,
                  barmode: "stack",
                  showlegend: false,
                  bargap: 0.25,
                  margin: { l: 0, r: 8, t: 4, b: 24 },
                  yaxis: {
                    categoryorder: "array",
                    categoryarray: data.bars.map((b) => b.label),
                    autorange: "reversed",
                    automargin: true,
                    tickfont: { size: 11 },
                    tickvals: data.bars.map((b) => b.label),
                    ticktext: data.bars.map((b) => cut(b.label, labelChars)),
                  },
                  xaxis: { automargin: true, tickfont: { size: 10 } },
                }}
                config={plotConfig(title)}
                style={{ width: "100%" }}
              />
            </Box>
            {legend.length > 0 && <Legend items={legend} width={Math.max(60, width / 4)} />}
          </Group>
        )}
      </Stack>
    </Card>
  );
};

/**
 * The four charts of the transformations page in a 2×2 grid, with one top / bottom 10 switch for all.
 *
 * @param ocelId Id of the log.
 * @param filter The page filters.
 */
export const TransformationCharts = ({ ocelId, filter }: { ocelId: string; filter: TransformationFilter }) => {
  const [end, setEnd] = usePageState<End>("transformations.charts.end", "top");
  return (
    <Stack gap="xs">
      <Group justify="space-between" align="flex-end">
        <Text size="sm" fw={600}>
          Charts{" "}
          <Text span size="xs" c="dimmed" fw={400}>
            each shows 10 bars ({end === "top" ? "the largest" : "the smallest"}); the rest is left out
          </Text>
        </Text>
        <SegmentedControl
          size="xs"
          value={end}
          onChange={(v) => setEnd(v as End)}
          data={[
            { value: "top", label: "top 10" },
            { value: "bottom", label: "bottom 10" },
          ]}
        />
      </Group>
      <SimpleGrid cols={{ base: 1, lg: 2 }} spacing="sm">
        <ChartCard ocelId={ocelId} filter={filter} chart="activities" end={end} />
        <ChartCard ocelId={ocelId} filter={filter} chart="transformation_types" end={end} />
        <ChartCard ocelId={ocelId} filter={filter} chart="locations" end={end} />
        <ChartCard ocelId={ocelId} filter={filter} chart="diversity" end={end} />
      </SimpleGrid>
    </Stack>
  );
};
