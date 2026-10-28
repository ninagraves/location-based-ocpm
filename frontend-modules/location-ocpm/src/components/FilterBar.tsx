// The page filter bar. Documented in docs/pages/overview.md, section "Page filter bar".
import { Alert, Button, Card, Group, MultiSelect, SegmentedControl, SimpleGrid, Stack, Text } from "@mantine/core";
import { FilterXIcon } from "lucide-react";
import type { ReactNode } from "react";
import { type FilterOption, useGetFilterOptions } from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import { emptyFilter, type FilterKey, isActive, type PageFilter, usePageFilter, withValues } from "../lib/filters";
import { num } from "../lib/format";

const withCounts = (options: FilterOption[] | undefined) =>
  (options ?? []).map((o) => ({ value: o.value, label: `${o.value} (${num(o.count)})` }));

/** Height of a column heading, so the pickers of all columns line up. */
const HEADING_HEIGHT = 26;

/** One multi-select of the bar; the placeholder ("include" / "exclude") shows while it is empty. */
const Pick = ({
  placeholder,
  options,
  value,
  onChange,
}: {
  placeholder: string;
  options: { value: string; label: string }[];
  value: string[];
  onChange: (v: string[]) => void;
}) => (
  <MultiSelect
    size="xs"
    aria-label={placeholder}
    placeholder={value.length ? undefined : placeholder}
    data={options}
    value={value}
    onChange={onChange}
    searchable
    clearable
    comboboxProps={{ withinPortal: true }}
  />
);

/**
 * One column of the bar: a heading (with optional controls on the right), the include picker
 * and below it the exclude picker.
 */
const Column = ({
  title,
  extra,
  options,
  include,
  exclude,
  onInclude,
  onExclude,
}: {
  title: string;
  extra?: ReactNode;
  options: { value: string; label: string }[];
  include: string[];
  exclude: string[];
  onInclude: (v: string[]) => void;
  onExclude: (v: string[]) => void;
}) => (
  <Stack gap={4}>
    <Group justify="space-between" gap={4} h={HEADING_HEIGHT} wrap="nowrap">
      <Text size="xs" fw={600}>
        {title}
      </Text>
      {extra}
    </Group>
    <Pick placeholder="include" options={options} value={include} onChange={onInclude} />
    <Pick placeholder="exclude" options={options} value={exclude} onChange={onExclude} />
  </Stack>
);

/**
 * The page filter bar: sticks to the top while scrolling; one column per filter (Activity,
 * Location, Object type), each with an include and an exclude picker; each option shows its count
 * over the whole log. Filters act on hu-event relations at the selected level (see `overview/filters.py`).
 */
export const FilterBar = ({ ocelId }: { ocelId: string }) => {
  const [filter, setFilter] = usePageFilter(ocelId);
  const { data: options, error } = useGetFilterOptions(ocelId);
  const set = (key: FilterKey) => (values: string[]) => setFilter((f) => withValues(f, key, values));
  if (error) return <Alert color="red">{errorText(error)}</Alert>;
  const role = (
    <SegmentedControl
      size="xs"
      title="Location filters match ploc (pre), loc (post) or either"
      data={[
        { value: "either", label: "either" },
        { value: "before", label: "pre" },
        { value: "after", label: "post" },
      ]}
      value={filter.location_role}
      onChange={(v) => setFilter((f) => ({ ...f, location_role: v as PageFilter["location_role"] }))}
    />
  );
  const clear = isActive(filter) && (
    <Button size="compact-xs" variant="subtle" leftSection={<FilterXIcon size={14} />} onClick={() => setFilter(emptyFilter)}>
      Clear filters
    </Button>
  );
  return (
    <Card withBorder padding="xs" style={{ position: "sticky", top: 0, zIndex: 20 }}>
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
        <Column
          title="Activity"
          options={withCounts(options?.activities)}
          include={filter.activities}
          exclude={filter.exclude_activities}
          onInclude={set("activities")}
          onExclude={set("exclude_activities")}
        />
        <Column
          title="Location"
          extra={role}
          options={withCounts(options?.locations)}
          include={filter.locations}
          exclude={filter.exclude_locations}
          onInclude={set("locations")}
          onExclude={set("exclude_locations")}
        />
        <Column
          title="Object type"
          extra={clear}
          options={withCounts(options?.object_types)}
          include={filter.object_types}
          exclude={filter.exclude_object_types}
          onInclude={set("object_types")}
          onExclude={set("exclude_object_types")}
        />
      </SimpleGrid>
    </Card>
  );
};
