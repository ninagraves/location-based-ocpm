// The page filter bar. Documented in docs/pages/overview.md, section "Page filter bar".
import { Alert, Button, Card, Group, MultiSelect, SegmentedControl, SimpleGrid, Stack, Text } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { FilterXIcon } from "lucide-react";
import { type ReactNode, useState } from "react";
import {
  type FilterOption,
  type FilterOptions,
  type SearchIdsKind,
  useGetConfig,
  useGetFilterOptions,
  useSearchIds,
} from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import {
  cleared,
  EVENT_PREFIX,
  HU_PREFIX,
  isActive,
  isHigh,
  type FilterKey,
  type PageFilter,
  shown,
  usePageFilter,
  withValues,
} from "../lib/filters";
import { num } from "../lib/format";

/** One entry of a picker; `indent` marks a location below its high-level location. */
type Item = { value: string; label: string; indent?: boolean };
/** Entries of a picker, optionally under headings (Mantine option groups). */
type Data = (Item | { group: string; items: Item[] })[];

const withCounts = (options: FilterOption[] | undefined): Item[] =>
  (options ?? []).map((o) => ({ value: o.value, label: `${shown(o.value)} (${num(o.count)})` }));

/** Height of a column heading, so the pickers of all columns line up. */
const HEADING_HEIGHT = 26;
/** Characters typed before ids are searched. */
const SEARCH_FROM = 2;

/**
 * The grouped location picker (concept "Update Overview Page", section 7): special values, then each
 * high-level location with its locations indented below it, then the locations that are their own only
 * member (e.g. an unmapped T). In high-level mode, a location reads "A1 (in A)".
 */
export const locationItems = (options: FilterOptions | undefined, high: boolean): Item[] => {
  const all = options?.locations ?? [];
  const groups = options?.high_level_locations ?? [];
  if (!groups.length) return withCounts(all);
  const grouped = new Set(groups.flatMap((g) => g.members.map((m) => m.value)));
  const specials = all.filter((o) => o.value.startsWith("["));
  const single = all.filter((o) => !o.value.startsWith("[") && !grouped.has(o.value));
  return [
    ...withCounts(specials),
    ...groups.flatMap((g) => [
      { value: g.value, label: `${g.label}, all locations (${num(g.count)})` },
      ...g.members.map((m) => ({
        value: m.value,
        label: high ? `${m.value} (in ${g.label}) (${num(m.count)})` : `${m.value} (${num(m.count)})`,
        indent: true,
      })),
    ]),
    ...withCounts(single),
  ];
};

/**
 * Single ids (handling units or events) for a picker: the ids already picked, plus the search results
 * while the user types (from two characters, at most 20), under the heading `heading`.
 */
const useIdItems = (ocelId: string, kind: SearchIdsKind, picked: string[], search: string, heading: string) => {
  const [query] = useDebouncedValue(search.trim(), 200);
  const { data: found } = useSearchIds(ocelId, { kind, query }, { query: { enabled: query.length >= SEARCH_FROM } });
  const prefix = kind === "hu" ? HU_PREFIX : EVENT_PREFIX;
  const items = new Map<string, Item>();
  for (const value of picked.filter((v) => v.startsWith(prefix))) items.set(value, { value, label: shown(value) });
  for (const o of query.length >= SEARCH_FROM ? (found ?? []) : []) items.set(o.value, withCounts([o])[0]);
  return items.size ? [{ group: heading, items: [...items.values()] }] : [];
};

/** One multi-select of the bar; the placeholder ("include" / "exclude") shows while it is empty. */
const Pick = ({
  placeholder,
  options,
  value,
  onChange,
  onSearch,
}: {
  placeholder: string;
  options: Data;
  value: string[];
  onChange: (v: string[]) => void;
  onSearch?: (search: string) => void;
}) => {
  const indented = new Set(
    options.flatMap((o) => ("group" in o ? o.items : [o])).filter((o) => o.indent).map((o) => o.value),
  );
  return (
    <MultiSelect
      size="xs"
      aria-label={placeholder}
      placeholder={value.length ? undefined : placeholder}
      data={options}
      value={value}
      onChange={onChange}
      onSearchChange={onSearch}
      searchable
      clearable
      comboboxProps={{ withinPortal: true }}
      renderOption={({ option }) => (
        <Text size="xs" pl={indented.has(option.value) ? "md" : 0}>
          {option.label}
        </Text>
      )}
    />
  );
};

/** Include and exclude picker of one column, each with its own search (for the id search). */
type PickerProps = {
  options: Data;
  include: string[];
  exclude: string[];
  onInclude: (v: string[]) => void;
  onExclude: (v: string[]) => void;
};

/**
 * One column of the bar: a heading (with optional controls on the right), the include picker
 * and below it the exclude picker.
 */
const Column = ({ title, extra, children }: { title: string; extra?: ReactNode; children: ReactNode }) => (
  <Stack gap={4}>
    <Group justify="space-between" gap={4} h={HEADING_HEIGHT} wrap="nowrap">
      <Text size="xs" fw={600}>
        {title}
      </Text>
      {extra}
    </Group>
    {children}
  </Stack>
);

const Pickers = ({ options, include, exclude, onInclude, onExclude }: PickerProps) => (
  <>
    <Pick placeholder="include" options={options} value={include} onChange={onInclude} />
    <Pick placeholder="exclude" options={options} value={exclude} onChange={onExclude} />
  </>
);

/** A column whose pickers also find single ids by typing (Activity: events, Handling unit: handling units). */
const IdPickers = ({
  ocelId,
  kind,
  heading,
  base,
  include,
  exclude,
  onInclude,
  onExclude,
}: Omit<PickerProps, "options"> & { ocelId: string; kind: SearchIdsKind; heading: string; base: Data }) => {
  const [includeSearch, setIncludeSearch] = useState("");
  const [excludeSearch, setExcludeSearch] = useState("");
  const includeIds = useIdItems(ocelId, kind, include, includeSearch, heading);
  const excludeIds = useIdItems(ocelId, kind, exclude, excludeSearch, heading);
  return (
    <>
      <Pick
        placeholder="include"
        options={[...base, ...includeIds]}
        value={include}
        onChange={onInclude}
        onSearch={setIncludeSearch}
      />
      <Pick
        placeholder="exclude"
        options={[...base, ...excludeIds]}
        value={exclude}
        onChange={onExclude}
        onSearch={setExcludeSearch}
      />
    </>
  );
};

/**
 * The page filter bar: sticks to the top while scrolling; one column per filter (Activity,
 * Location, Handling unit), each with an include and an exclude picker; each option shows its count
 * over the whole log. Filters act on hu-event relations at the selected level (see `overview/filters.py`).
 * With high-level locations, the switch "Locations: low | high" changes how the Overview section shows
 * locations; filters are always evaluated on low-level locations, so switching never changes them.
 */
export const FilterBar = ({ ocelId }: { ocelId: string }) => {
  const [filter, setFilter] = usePageFilter(ocelId);
  const { data: options, error } = useGetFilterOptions(ocelId);
  const { data: state } = useGetConfig(ocelId);
  const withHighLevel = !!state?.config?.high_level_locations;
  const high = withHighLevel && isHigh(filter);
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
  const mode = withHighLevel && (
    <Group gap={4} wrap="nowrap">
      <Text size="xs" c="dimmed">
        Locations:
      </Text>
      <SegmentedControl
        size="xs"
        title="Show low-level locations or high-level locations in the Overview section; filters are unchanged"
        data={[
          { value: "low", label: "low" },
          { value: "high", label: "high" },
        ]}
        value={high ? "high" : "low"}
        onChange={(v) => setFilter((f) => ({ ...f, location_mode: v as "low" | "high" }))}
      />
    </Group>
  );
  // Always shown; disabled while no filter is set.
  const clear = (
    <Button
      size="compact-xs"
      variant="light"
      leftSection={<FilterXIcon size={14} />}
      disabled={!isActive(filter)}
      onClick={() => setFilter(cleared)}
    >
      Clear filters
    </Button>
  );
  const objectTypes = withCounts(options?.object_types);
  return (
    <Card withBorder padding="xs" style={{ position: "sticky", top: 0, zIndex: 20 }}>
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
        <Column title="Activity">
          <IdPickers
            ocelId={ocelId}
            kind="event"
            heading="Events"
            base={withCounts(options?.activities)}
            include={filter.activities}
            exclude={filter.exclude_activities}
            onInclude={set("activities")}
            onExclude={set("exclude_activities")}
          />
        </Column>
        <Column title="Location" extra={role}>
          <Pickers
            options={locationItems(options, high)}
            include={filter.locations}
            exclude={filter.exclude_locations}
            onInclude={set("locations")}
            onExclude={set("exclude_locations")}
          />
        </Column>
        <Column
          title="Handling unit"
          extra={
            <Group gap="xs" wrap="nowrap">
              {mode}
              {clear}
            </Group>
          }
        >
          <IdPickers
            ocelId={ocelId}
            kind="hu"
            heading="Handling units"
            base={objectTypes}
            include={filter.object_types}
            exclude={filter.exclude_object_types}
            onInclude={set("object_types")}
            onExclude={set("exclude_object_types")}
          />
        </Column>
      </SimpleGrid>
    </Card>
  );
};
