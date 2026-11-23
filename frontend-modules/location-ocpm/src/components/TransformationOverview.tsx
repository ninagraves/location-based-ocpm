// Transformations page (draft), upper part as in the playground: page filters and key numbers.
// Documented in docs/pages/transformations.md, sections "Page filters" and "Key numbers".
import { Alert, Card, Group, Loader, MultiSelect, SegmentedControl, SimpleGrid, Stack, Text, Tooltip } from "@mantine/core";
import type { ReactNode } from "react";
import {
  type Count,
  type GetTransformationOverviewKind,
  type TransformationKeyNumbers,
  type TransformationOverview as OverviewData,
} from "../api/locationBasedOcpm";
import { num, pct } from "../lib/format";
import { KIND_LABELS, type TransformationFilter } from "../lib/transformations";

/** Hover texts of the tiles. */
const INFO = {
  events: "Transformation events kept by the page filters.",
  transformations:
    "Consumed handling units, plus handling units produced at events without consumption (welding two coils into one counts 2).",
  activities: "Distinct activities of the kept transformation events.",
  types: "Distinct transformation types: input → output as multisets of object types, e.g. '1 slab → 2 coil'.",
  recipes: "Distinct recipes: activity, input and output, e.g. 'roll: 1 slab → 2 coil' (the rectangles of the type graph).",
  lineage: "Sum over the kept events of consumed × produced handling units.",
  produced: "Handling units produced at a kept transformation event, of all handling units with at least one event.",
  consumed: "Handling units consumed at a kept transformation event, of all handling units with at least one event.",
  filters: "All filters select whole transformation events, so a transformation type or recipe is never cut.",
};

/** Options of an object type picker: types with their events, plus selected types the log no longer has. */
const typeOptions = (types: Count[], selected: string[]) => [
  ...selected.filter((t) => !types.some((o) => o.name === t)).map((t) => ({ value: t, label: t })),
  ...types.map((t) => ({ value: t.name, label: `${t.name} (${num(t.count)})` })),
];

/**
 * The page filter bar: consumed and produced object types, and the kind of transformation.
 *
 * @param value Current filters.
 * @param onChange Called with the changed filters.
 * @param consumedTypes Object types consumed somewhere, with their events.
 * @param producedTypes Object types produced somewhere, with their events.
 */
export const TransformationFilterBar = ({
  value,
  onChange,
  consumedTypes,
  producedTypes,
}: {
  value: TransformationFilter;
  onChange: (value: TransformationFilter) => void;
  consumedTypes: Count[];
  producedTypes: Count[];
}) => (
  <Group gap="md" align="flex-end">
    <MultiSelect
      size="xs"
      label="Consumes"
      placeholder={value.consumes.length ? undefined : "any type"}
      data={typeOptions(consumedTypes, value.consumes)}
      value={value.consumes}
      onChange={(consumes) => onChange({ ...value, consumes })}
      clearable
      searchable
      w={240}
    />
    <MultiSelect
      size="xs"
      label="Produces"
      placeholder={value.produces.length ? undefined : "any type"}
      data={typeOptions(producedTypes, value.produces)}
      value={value.produces}
      onChange={(produces) => onChange({ ...value, produces })}
      clearable
      searchable
      w={240}
    />
    <div>
      <Text size="xs" fw={500}>
        Kind
      </Text>
      <SegmentedControl
        size="xs"
        value={value.kind}
        onChange={(kind) => onChange({ ...value, kind: kind as GetTransformationOverviewKind })}
        data={Object.entries(KIND_LABELS).map(([v, label]) => ({ value: v, label }))}
      />
    </div>
    <Text size="xs" c="dimmed" pb={4}>
      {INFO.filters}
    </Text>
  </Group>
);

/** One tile: label, big number, small grey line; `hint` on hover. */
const Tile = ({ label, value, sub, hint }: { label: string; value: ReactNode; sub?: ReactNode; hint: string }) => (
  <Tooltip label={hint} multiline maw={320} withArrow openDelay={300}>
    <Card withBorder padding="sm">
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text fw={700} size="xl">
        {value}
      </Text>
      {sub && (
        <Text size="xs" c="dimmed">
          {sub}
        </Text>
      )}
    </Card>
  </Tooltip>
);

/**
 * The key number tiles, with the split by kind below them.
 *
 * @param data The key numbers of the kept transformation events.
 */
export const TransformationKeyNumberTiles = ({ data }: { data: TransformationKeyNumbers }) => {
  const share = (n: number) => pct(n / Math.max(data.handling_units, 1));
  return (
    <Stack gap={4}>
      <SimpleGrid cols={{ base: 2, sm: 4, lg: 8 }} spacing="sm">
        <Tile label="Transformation events" value={num(data.transformation_events)} hint={INFO.events} />
        <Tile label="Transformations" value={num(data.transformations)} sub="consumed + produced without consumption" hint={INFO.transformations} />
        <Tile label="Transformation activities" value={num(data.activities)} hint={INFO.activities} />
        <Tile label="Transformation types" value={num(data.transformation_types)} sub="input → output" hint={INFO.types} />
        <Tile label="Recipes" value={num(data.recipes)} sub="activity: input → output" hint={INFO.recipes} />
        <Tile label="Lineage relations" value={num(data.lineage_relations)} sub="consumed × produced per event" hint={INFO.lineage} />
        <Tile
          label="HUs produced at least once"
          value={share(data.produced_handling_units)}
          sub={`${num(data.produced_handling_units)} of ${num(data.handling_units)}`}
          hint={INFO.produced}
        />
        <Tile
          label="HUs consumed at least once"
          value={share(data.consumed_handling_units)}
          sub={`${num(data.consumed_handling_units)} of ${num(data.handling_units)}`}
          hint={INFO.consumed}
        />
      </SimpleGrid>
      <Text size="xs" c="dimmed">
        {data.kinds.map((k) => `${KIND_LABELS[k.name] ?? k.name} ${num(k.count)}`).join(" · ")}
      </Text>
    </Stack>
  );
};

/**
 * The overview card: filter bar and key numbers.
 *
 * @param data The overview from the backend (undefined while loading).
 * @param error A failed request.
 * @param filter Current page filters.
 * @param onFilter Called with the changed page filters.
 */
export const TransformationOverview = ({
  data,
  error,
  filter,
  onFilter,
}: {
  data: OverviewData | undefined;
  error: string | null;
  filter: TransformationFilter;
  onFilter: (filter: TransformationFilter) => void;
}) => (
  <Card withBorder padding="sm">
    <Stack gap="sm">
      <TransformationFilterBar
        value={filter}
        onChange={onFilter}
        consumedTypes={data?.consumed_types ?? []}
        producedTypes={data?.produced_types ?? []}
      />
      {error ? <Alert color="red">{error}</Alert> : !data ? <Loader size="sm" /> : <TransformationKeyNumberTiles data={data.key_numbers} />}
    </Stack>
  </Card>
);
