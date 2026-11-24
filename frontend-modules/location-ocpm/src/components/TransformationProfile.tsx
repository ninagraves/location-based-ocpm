// Transformation profile of the transformations page (draft), as in the playground: one row per transformation type,
// sortable, searchable, paged, a click unfolds the type's activities (its recipes).
// Documented in docs/pages/transformations.md, section "Transformation profile".
import {
  ActionIcon,
  Alert,
  Card,
  Group,
  Loader,
  Pagination,
  Progress,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Tooltip,
  UnstyledButton,
} from "@mantine/core";
import { ChevronDownIcon, ChevronRightIcon, ChevronsUpDownIcon, ChevronUpIcon, SearchIcon } from "lucide-react";
import { Fragment } from "react";
import { type TransformationTypeRow, useGetTransformationProfile } from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import { num, pct } from "../lib/format";
import { usePageState } from "../lib/pageState";
import { KIND_LABELS, listRequest, type TransformationFilter } from "../lib/transformations";

/** Rows per page that can be chosen; the first is the default. */
const PAGE_SIZES = [10, 25, 50, 100];

type SortKey = "transformation_type" | "kind" | "events" | "transformations" | "lineage_relations" | "activity_count";
type Sort = { key: SortKey; descending: boolean };

/** Hover texts of the column headings. */
const INFO: Record<SortKey, string> = {
  transformation_type: "Input → output as multisets of object types. Click a row to show its activities (each one is a recipe).",
  kind: "Whether the type consumes and produces, only consumes or only produces.",
  events: "Kept transformation events of this type.",
  transformations: "Consumed handling units, plus handling units produced at events without consumption.",
  lineage_relations: "Consumed × produced handling units, summed over the type's events.",
  activity_count: "Most frequent activity with its share of the type's events, and the number of activities (= recipes). Sorted by the number of activities.",
};

const sortValue = (r: TransformationTypeRow, key: SortKey): number | string => r[key];

/** The rows sorted by a column (ties by transformation type). */
const sorted = (rows: TransformationTypeRow[], sort: Sort) =>
  [...rows].sort((a, b) => {
    const x = sortValue(a, sort.key);
    const y = sortValue(b, sort.key);
    const order = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
    return (sort.descending ? -order : order) || a.transformation_type.localeCompare(b.transformation_type);
  });

/** A column heading: hover text, click to sort. */
const Heading = ({ label, sortKey, sort, onSort }: { label: string; sortKey: SortKey; sort: Sort; onSort: (k: SortKey) => void }) => (
  <Table.Th style={{ whiteSpace: "nowrap" }}>
    <Tooltip label={INFO[sortKey]} multiline maw={320} withArrow openDelay={300}>
      <UnstyledButton onClick={() => onSort(sortKey)}>
        <Group gap={2} wrap="nowrap">
          <Text size="xs" fw={600}>
            {label}
          </Text>
          {sort.key !== sortKey ? (
            <ChevronsUpDownIcon size={12} opacity={0.4} />
          ) : sort.descending ? (
            <ChevronDownIcon size={12} />
          ) : (
            <ChevronUpIcon size={12} />
          )}
        </Group>
      </UnstyledButton>
    </Tooltip>
  </Table.Th>
);

/** One row and, unfolded, the type's activities with their shares. */
const Row = ({ row, openKey }: { row: TransformationTypeRow; openKey: string }) => {
  const [open, setOpen] = usePageState(openKey, false);
  const cell = (content: string) => (
    <Table.Td style={{ whiteSpace: "nowrap" }}>
      <Text size="xs">{content}</Text>
    </Table.Td>
  );
  return (
    <Fragment>
      <Table.Tr onClick={() => setOpen(!open)} style={{ cursor: "pointer" }} aria-expanded={open}>
        <Table.Td>
          <Group gap={4} wrap="nowrap">
            <ActionIcon size="xs" variant="subtle" color="gray" component="span" aria-hidden>
              {open ? <ChevronDownIcon size={12} /> : <ChevronRightIcon size={12} />}
            </ActionIcon>
            <Text size="xs" fw={500}>
              {row.transformation_type}
            </Text>
          </Group>
        </Table.Td>
        {cell(KIND_LABELS[row.kind] ?? row.kind)}
        {cell(num(row.events))}
        {cell(num(row.transformations))}
        {cell(num(row.lineage_relations))}
        <Table.Td>
          <Text size="xs">
            {row.typical_activity}{" "}
            <Text span size="xs" c="dimmed">
              {pct(row.typical_share)} · {num(row.activity_count)} {row.activity_count === 1 ? "activity" : "activities"}
            </Text>
          </Text>
        </Table.Td>
      </Table.Tr>
      {open && (
        <Table.Tr>
          <Table.Td colSpan={6}>
            <Stack gap={2} pl={28} py={4} maw={420}>
              <Text size="xs" fw={600}>
                Activities{" "}
                <Text span size="xs" c="dimmed">
                  {row.activity_count > row.activities.length
                    ? `${num(row.activity_count)} in total, top ${row.activities.length} shown`
                    : `${num(row.activity_count)} in total`}
                </Text>
              </Text>
              {row.activities.map((a) => (
                <Group key={a.activity} gap={6} wrap="nowrap">
                  <Progress value={a.share * 100} w={60} size="sm" />
                  <Text size="xs">
                    {a.activity} · {pct(a.share)} ({num(a.count)})
                  </Text>
                </Group>
              ))}
            </Stack>
          </Table.Td>
        </Table.Tr>
      )}
    </Fragment>
  );
};

/**
 * The transformation profile card: search box, the sortable table and its pages.
 *
 * @param ocelId Id of the log.
 * @param filter The page filters.
 */
export const TransformationProfile = ({ ocelId, filter }: { ocelId: string; filter: TransformationFilter }) => {
  const [search, setSearch] = usePageState(`transformations.profile.search.${ocelId}`, "");
  const [sort, setSort] = usePageState<Sort>("transformations.profile.sort", { key: "events", descending: true });
  const [pageSize, setPageSize] = usePageState<number>("transformations.profile.pageSize", PAGE_SIZES[0]);
  const [page, setPage] = usePageState(`transformations.profile.page.${ocelId}`, 1);
  const { data, error } = useGetTransformationProfile(ocelId, filter, { request: listRequest });
  if (error) return <Alert color="red">{errorText(error)}</Alert>;
  if (!data) return <Loader size="sm" />;
  const onSort = (key: SortKey) => {
    setSort((s) => (s.key === key ? { key, descending: !s.descending } : { key, descending: key !== "transformation_type" && key !== "kind" }));
    setPage(1);
  };
  const needle = search.trim().toLowerCase();
  const rows = sorted(data, sort).filter(
    (r) => !needle || r.transformation_type.toLowerCase().includes(needle) || r.activities.some((a) => a.activity.toLowerCase().includes(needle)),
  );
  const pages = Math.max(1, Math.ceil(rows.length / pageSize));
  const current = Math.min(page, pages);
  const first = (current - 1) * pageSize;
  const shown = rows.slice(first, first + pageSize);
  const head = (label: string, key: SortKey) => <Heading label={label} sortKey={key} sort={sort} onSort={onSort} />;
  return (
    <Card withBorder padding="xs">
      <Stack gap={6}>
        <Group justify="space-between">
          <Text size="sm" fw={600}>
            Transformation profile{" "}
            <Text span size="xs" c="dimmed" fw={400}>
              {num(data.length)} transformation types
            </Text>
          </Text>
          <TextInput
            size="xs"
            w={240}
            placeholder="Search type or activity"
            leftSection={<SearchIcon size={12} />}
            value={search}
            onChange={(e) => {
              setSearch(e.currentTarget.value);
              setPage(1);
            }}
          />
        </Group>
        <Table.ScrollContainer minWidth={760}>
          <Table striped highlightOnHover verticalSpacing={4}>
            <Table.Thead>
              <Table.Tr>
                {head("transformation type", "transformation_type")}
                {head("kind", "kind")}
                {head("events", "events")}
                {head("transformations", "transformations")}
                {head("lineage relations", "lineage_relations")}
                {head("typical activity", "activity_count")}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {shown.map((row) => (
                <Row key={row.transformation_type} row={row} openKey={`transformations.profile.open.${ocelId}.${row.transformation_type}`} />
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
        <Group justify="space-between" gap="xs">
          <Text size="xs" c="dimmed">
            {rows.length ? `${num(first + 1)}–${num(first + shown.length)} of ${num(rows.length)}` : "no matching transformation type"}
            {needle && rows.length < data.length ? ` (search; ${num(data.length)} in total)` : ""}
          </Text>
          <Group gap="xs">
            <Select
              size="xs"
              w={120}
              aria-label="rows per page"
              data={PAGE_SIZES.map((n) => ({ value: String(n), label: `${n} per page` }))}
              value={String(pageSize)}
              onChange={(v) => {
                if (!v) return;
                setPageSize(Number(v));
                setPage(1);
              }}
              allowDeselect={false}
              comboboxProps={{ withinPortal: true }}
            />
            {pages > 1 && <Pagination size="xs" total={pages} value={current} onChange={setPage} />}
          </Group>
        </Group>
      </Stack>
    </Card>
  );
};
