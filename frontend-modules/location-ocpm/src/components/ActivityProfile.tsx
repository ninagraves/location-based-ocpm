// Activity profile: one row per activity, sortable, with a search box and expandable rows.
// Documented in docs/pages/overview.md, section "Activity profile".
import { ActionIcon, Alert, Card, Group, Loader, Stack, Table, Text, TextInput, Tooltip, UnstyledButton } from "@mantine/core";
import { ChevronDownIcon, ChevronRightIcon, ChevronsUpDownIcon, ChevronUpIcon, SearchIcon } from "lucide-react";
import { Fragment, type ReactNode, useState } from "react";
import { type ActivityRow, type Typical, useGetActivityProfile } from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import { filterParams, filterRequest, usePageFilter } from "../lib/filters";
import { num, pct } from "../lib/format";
import { usePageState } from "../lib/pageState";

/** Hover texts of the column headings (concept section "Activity Profile"). */
const INFO = {
  events: "Kept events of the activity.",
  share: "Share of all kept events that belong to this activity (only with a location filter).",
  role: "M: share of the events that are movement events; T: share that are transformation events ('–' if none are configured).",
  hus: "Median (max) number of handling units per event; hover a cell for the object types, counted as hu-event relations. Sorted by max.",
  location:
    "Most frequent location after the event among the hu-event relations of this activity with a known location (relations without a location are not counted). Ties: alphabetically first, with the number of tied locations. 'provided x/y': x of the y events have a location from the input.",
  located: "Fully located events (partially located, unlocated) and the share of fully located events. Sorted by the share.",
  agreed:
    "Agreeing events: no two handling units of the event have different known locations; this includes events with fewer than two located handling units. In brackets: only events with at least two located handling units, where agreement is actually tested.",
  route:
    "Most frequent 'ploc → loc' over the handling units that actually moved at this activity's movement events, with its share and the number of distinct routes. Ties: alphabetically first, with the number of tied routes.",
};

type SortKey = "activity" | "events" | "share" | "role" | "hus" | "located" | "agreed";
type Sort = { key: SortKey; descending: boolean };

/** The value a row is sorted by, per column. */
const sortValue: Record<SortKey, (r: ActivityRow) => number | string> = {
  activity: (r) => r.activity,
  events: (r) => r.events,
  share: (r) => r.share_at_location ?? 0,
  role: (r) => r.movement_share * 2 + (r.transformation_share ?? 0),
  hus: (r) => r.hus_max,
  located: (r) => r.fully_located / r.events,
  agreed: (r) => r.agreed,
};

/** Rows sorted by a column; ties by most events, then alphabetically. */
const sorted = (rows: ActivityRow[], sort: Sort) =>
  [...rows].sort((a, b) => {
    const [x, y] = [sortValue[sort.key](a), sortValue[sort.key](b)];
    const order = typeof x === "string" ? x.localeCompare(y as string) : (x as number) - (y as number);
    if (order !== 0) return sort.descending ? -order : order;
    return b.events - a.events || a.activity.localeCompare(b.activity);
  });

/** "A2 (4/6 = 67 %; 2 tied)", optionally with the number of distinct values. */
const typicalText = (t: Typical, withDistinct: boolean) => {
  const extras = [withDistinct ? `${num(t.distinct)} distinct` : undefined, t.tied > 1 ? `${num(t.tied)} tied` : undefined].filter(Boolean);
  return `${t.value} (${num(t.count)}/${num(t.total)} = ${pct(t.count / t.total)}${extras.map((e) => `; ${e}`).join("")})`;
};

/** A median as "1.5" or "2". */
const median = (value: number) => (Number.isInteger(value) ? num(value) : value.toLocaleString("en-GB", { maximumFractionDigits: 1 }));

/** A column heading with hover text; sortable if `sortKey` is given. */
const Heading = ({
  label,
  info,
  sortKey,
  sort,
  onSort,
}: {
  label: string;
  info: string;
  sortKey?: SortKey;
  sort: Sort;
  onSort: (key: SortKey) => void;
}) => {
  const active = sortKey && sort.key === sortKey;
  const Icon = !active ? ChevronsUpDownIcon : sort.descending ? ChevronDownIcon : ChevronUpIcon;
  const text = (
    <Tooltip label={info} multiline maw={360} withArrow>
      <Text size="xs" fw={600} style={{ cursor: "help" }}>
        {label}
      </Text>
    </Tooltip>
  );
  return (
    <Table.Th>
      {sortKey ? (
        <UnstyledButton onClick={() => onSort(sortKey)}>
          <Group gap={2} wrap="nowrap">
            {text}
            <Icon size={12} opacity={active ? 1 : 0.4} />
          </Group>
        </UnstyledButton>
      ) : (
        text
      )}
    </Table.Th>
  );
};

/** One activity row and, if expanded, its top locations below. */
const Row = ({ row, withShare, kept, columns }: { row: ActivityRow; withShare: boolean; kept: number; columns: number }) => {
  const [open, setOpen] = useState(false);
  // Short cells stay on one line; typical location and route may wrap.
  const cell = (content: ReactNode, wrap = false) => (
    <Table.Td style={wrap ? undefined : { whiteSpace: "nowrap" }}>
      <Text size="xs">{content}</Text>
    </Table.Td>
  );
  const located = row.top_locations.reduce((sum, v) => sum + v.count, 0);
  return (
    <Fragment>
      <Table.Tr>
        <Table.Td style={{ whiteSpace: "nowrap" }}>
          <Group gap={4} wrap="nowrap">
            <ActionIcon size="xs" variant="subtle" color="gray" onClick={() => setOpen(!open)} aria-label="expand">
              {open ? <ChevronDownIcon size={12} /> : <ChevronRightIcon size={12} />}
            </ActionIcon>
            <Text size="xs" fw={500}>
              {row.activity}
            </Text>
          </Group>
        </Table.Td>
        {cell(num(row.events))}
        {withShare && cell(`${num(row.events)}/${num(kept)} = ${pct(row.share_at_location)}`)}
        {cell(`M ${pct(row.movement_share)}, T ${row.transformation_share == null ? "–" : pct(row.transformation_share)}`)}
        <Table.Td style={{ whiteSpace: "nowrap" }}>
          <Tooltip label={row.object_types.map((t) => `${t.object_type} ${num(t.count)}`).join(" · ")} withArrow>
            <Text size="xs" style={{ cursor: "help" }}>
              {median(row.hus_median)} ({num(row.hus_max)})
            </Text>
          </Tooltip>
        </Table.Td>
        {cell(
          `${row.typical_location ? typicalText(row.typical_location, false) : "unknown"}; provided ${num(row.provided)}/${num(row.events)}`,
          true,
        )}
        {cell(`${num(row.fully_located)} (${num(row.partially_located)}, ${num(row.unlocated)}) · ${pct(row.fully_located / row.events)}`)}
        {cell(`${num(row.agreed)}/${num(row.events)} (${num(row.tested_agreed)}/${num(row.tested)})`)}
        {cell(row.typical_route ? typicalText(row.typical_route, true) : "–", true)}
      </Table.Tr>
      {open && (
        <Table.Tr>
          <Table.Td colSpan={columns}>
            <Text size="xs" c="dimmed" pl={28}>
              Top locations:{" "}
              {row.top_locations.length === 0
                ? "none (no located relations)"
                : `${row.top_locations
                    .map((v) => `${v.value} ${num(v.count)} (${pct(v.count / (row.typical_location?.total ?? located))})`)
                    .join(", ")}; ${num(row.typical_location?.distinct ?? row.top_locations.length)} distinct`}
            </Text>
          </Table.Td>
        </Table.Tr>
      )}
    </Fragment>
  );
};

/** The activity profile card: search box and the sortable table. */
export const ActivityProfile = ({ ocelId }: { ocelId: string }) => {
  const [filter] = usePageFilter(ocelId);
  const [search, setSearch] = useState("");
  const [sort, setSort] = usePageState<Sort>("profile.sort", { key: "events", descending: true });
  const { data, error } = useGetActivityProfile(ocelId, filterParams(filter), { request: filterRequest });
  if (error) return <Alert color="red">{errorText(error)}</Alert>;
  if (!data) return <Loader size="sm" />;
  const onSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, descending: !s.descending } : { key, descending: key !== "activity" }));
  const needle = search.trim().toLowerCase();
  const rows = sorted(data.rows, sort).filter((r) => !needle || r.activity.toLowerCase().includes(needle));
  const withShare = data.location_filter;
  const head = (label: string, info: string, sortKey?: SortKey) => (
    <Heading label={label} info={info} sortKey={sortKey} sort={sort} onSort={onSort} />
  );
  return (
    <Card withBorder padding="xs">
      <Stack gap={6}>
        <Group justify="space-between">
          <Text size="sm" fw={600}>
            Activity profile{" "}
            <Text span size="xs" c="dimmed" fw={400}>
              Level {data.level} · {num(data.rows.length)} activities
            </Text>
          </Text>
          <TextInput
            size="xs"
            w={220}
            placeholder="Search activity"
            leftSection={<SearchIcon size={12} />}
            value={search}
            onChange={(e) => setSearch(e.currentTarget.value)}
          />
        </Group>
        <Table.ScrollContainer minWidth={900}>
          <Table striped highlightOnHover verticalSpacing={4}>
            <Table.Thead>
              <Table.Tr>
                {head("activity", "Click the arrow to show the top 5 locations.", "activity")}
                {head("events", INFO.events, "events")}
                {withShare && head("share at location", INFO.share, "share")}
                {head("role", INFO.role, "role")}
                {head("HUs per event", INFO.hus, "hus")}
                {head("typical location", INFO.location)}
                {head("located", INFO.located, "located")}
                {head("agreed (tested)", INFO.agreed, "agreed")}
                {head("typical route", INFO.route)}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((row) => (
                <Row key={row.activity} row={row} withShare={withShare} kept={data.kept_events} columns={withShare ? 9 : 8} />
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Stack>
    </Card>
  );
};
