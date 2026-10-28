// The page filter bar. Documented in docs/pages/overview.md, section "Page filter bar".
import { Alert, Button, Card, Group, MultiSelect, SegmentedControl, Stack, Text } from "@mantine/core";
import { FilterXIcon } from "lucide-react";
import { type FilterOption, useGetFilterOptions } from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import { emptyFilter, isActive, type PageFilter, usePageFilter } from "../lib/filters";
import { num } from "../lib/format";

const withCounts = (options: FilterOption[] | undefined) =>
  (options ?? []).map((o) => ({ value: o.value, label: `${o.value} (${num(o.count)})` }));

/** One multi-select of the bar. */
const Pick = ({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: string; label: string }[];
  value: string[];
  onChange: (v: string[]) => void;
}) => (
  <MultiSelect
    size="xs"
    label={label}
    data={options}
    value={value}
    onChange={onChange}
    searchable
    clearable
    w={220}
    comboboxProps={{ withinPortal: true }}
  />
);

/**
 * The page filter bar: sticks to the top while scrolling; each option shows its count over the
 * whole log. Filters act on hu-event relations at the selected level (see `overview/filters.py`).
 */
export const FilterBar = ({ ocelId }: { ocelId: string }) => {
  const [filter, setFilter] = usePageFilter(ocelId);
  const { data: options, error } = useGetFilterOptions(ocelId);
  const set = <K extends keyof PageFilter>(key: K) => (value: PageFilter[K]) => setFilter((f) => ({ ...f, [key]: value }));
  if (error) return <Alert color="red">{errorText(error)}</Alert>;
  const activities = withCounts(options?.activities);
  const locations = withCounts(options?.locations);
  const objectTypes = withCounts(options?.object_types);
  return (
    <Card withBorder padding="xs" style={{ position: "sticky", top: 0, zIndex: 20 }}>
      <Group align="flex-end" gap="sm">
        <Pick label="Activity" options={activities} value={filter.activities} onChange={set("activities")} />
        <Pick label="Exclude activity" options={activities} value={filter.exclude_activities} onChange={set("exclude_activities")} />
        <Pick label="Location" options={locations} value={filter.locations} onChange={set("locations")} />
        <Pick label="Exclude location" options={locations} value={filter.exclude_locations} onChange={set("exclude_locations")} />
        <Stack gap={2}>
          <Text size="xs" fw={500}>
            Location filters match
          </Text>
          <SegmentedControl
            size="xs"
            data={[
              { value: "either", label: "either" },
              { value: "before", label: "before (pickup)" },
              { value: "after", label: "after (target)" },
            ]}
            value={filter.location_role}
            onChange={(v) => set("location_role")(v as PageFilter["location_role"])}
          />
        </Stack>
        <Pick label="Object type" options={objectTypes} value={filter.object_types} onChange={set("object_types")} />
        <Pick label="Exclude object type" options={objectTypes} value={filter.exclude_object_types} onChange={set("exclude_object_types")} />
        {isActive(filter) && (
          <Button size="xs" variant="subtle" leftSection={<FilterXIcon size={14} />} onClick={() => setFilter(emptyFilter)}>
            Clear filters
          </Button>
        )}
      </Group>
    </Card>
  );
};
