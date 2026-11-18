// HU profile of the instance page: one row per handling unit, searchable, filterable per column (filter icon in the
// column header), sortable, paginated, with a checkbox per row to select handling units for the charts below. The
// overview shows counts (easy to sort); clicking a row unfolds it with the names behind the counts (as in the activity
// profile). A header row names the column groups. The table as shown can be exported as CSV or saved to the session.
// Documented in docs/pages/instances.md, section "HU profile".
import { Anchor, Badge, Box, Button, Chip, Group, Loader, Pill, Popover, SimpleGrid, Stack, Text, TextInput, Tooltip } from "@mantine/core";
import { useDebouncedValue, useElementSize } from "@mantine/hooks";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { DownloadIcon, SaveIcon, SearchIcon } from "lucide-react";
import { type DataTableColumn, type DataTableColumnGroup, DataTable, type DataTableSortStatus } from "mantine-datatable";
import { useMemo, useState } from "react";
import {
  type DetailEvent,
  exportHuProfileCsv,
  getHuDetails,
  getHuProfile,
  type HuProfilePage,
  type HuProfileRow,
  type ProfileExportRequest,
  type ProfileFilter,
  type ProfileFilterColumn,
  type ProfileQuery,
  type ProfileQuerySortBy,
  saveHuProfile,
} from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import { num } from "../lib/format";
import { usePageState } from "../lib/pageState";
import { CATEGORICAL, OTHER, type Scheme, STATUS, UI } from "../lib/palette";
import { filterText, ProfileColumnFilter, type ValueFormat } from "./ProfileColumnFilter";
import { ShortList } from "./ShortList";
import { useScheme } from "./plots";

/** Rows per page offered (default 25). */
const PAGE_SIZES = [10, 25, 50, 100];

/** Column groups that can be shown or hidden, in table order (Time last). */
const GROUPS = ["Lifecycle", "Lineage", "Locations", "MF Profile", "Time"] as const;
type Group = (typeof GROUPS)[number];

/** Table state kept per log. */
type TableState = {
  search: string;
  /** Active column filters by column. */
  filters: Partial<Record<ProfileFilterColumn, ProfileFilter>>;
  sort: { columnAccessor: ProfileQuerySortBy; direction: "asc" | "desc" };
  page: number;
  pageSize: number;
  groups: Group[];
};

const DEFAULT_TABLE: TableState = {
  search: "",
  filters: {},
  sort: { columnAccessor: "hu", direction: "asc" },
  page: 1,
  pageSize: 25,
  groups: [...GROUPS],
};

/**
 * A duration in seconds as a short text with at most two units, e.g. "2 h", "1 d 3 h", "4 min 30 s"; "–" if missing,
 * "0" for zero.
 */
export const duration = (seconds: number | null | undefined) => {
  if (seconds === null || seconds === undefined) return "–";
  if (seconds === 0) return "0";
  const units: [string, number][] = [["d", 86400], ["h", 3600], ["min", 60], ["s", 1]];
  const parts: string[] = [];
  let rest = Math.round(seconds);
  for (const [unit, size] of units) {
    const n = Math.floor(rest / size);
    if (n > 0 && parts.length < 2) parts.push(`${n} ${unit}`);
    if (n > 0) rest -= n * size;
    if (parts.length === 2) break;
  }
  return parts.join(" ") || `${seconds.toFixed(1)} s`;
};

/** A timestamp as "YYYY-MM-DD HH:MM:SS". */
const stamp = (value: string | null | undefined) => (value ? value.replace("T", " ").slice(0, 19) : "–");

/** Colours of the four location kinds of the time split (vehicle, storage, other, unlocated). */
const kindColours = (scheme: Scheme) => ({
  vehicle: STATUS[scheme].movement,
  storage: STATUS[scheme].transformation,
  other: STATUS[scheme]["fully located"],
  unlocated: OTHER[scheme],
});

/** One horizontal bar per handling unit: shares of its lifespan on vehicles, in storage, at other locations, unlocated. */
const TimeSplit = ({ row, scheme }: { row: HuProfileRow; scheme: Scheme }) => {
  const colours = kindColours(scheme);
  const parts = [
    ["vehicle", row.time_vehicle],
    ["storage", row.time_storage],
    ["other", row.time_other],
    ["unlocated", row.time_unlocated],
  ] as const;
  const total = parts.reduce((s, [, v]) => s + (v ?? 0), 0);
  if (!total) return <Text size="xs" c="dimmed">–</Text>;
  return (
    <Tooltip
      withinPortal
      multiline
      label={parts.map(([k, v]) => `${k}: ${duration(v)} (${Math.round(((v ?? 0) / total) * 100)} %)`).join(" · ")}
    >
      <Box style={{ display: "flex", width: 90, height: 10, borderRadius: 2, overflow: "hidden" }}>
        {parts.map(([k, v]) => (v ? <Box key={k} style={{ width: `${(v / total) * 100}%`, background: colours[k] }} /> : null))}
      </Box>
    </Tooltip>
  );
};

/** Badge of the lifecycle class. */
const LIFECYCLE: Record<string, { label: string; info: string }> = {
  both: { label: "both", info: "produced and finally consumed in the log" },
  produced: { label: "produced", info: "produced in the log, not finally consumed" },
  consumed: { label: "consumed", info: "finally consumed in the log, not produced in it" },
  open: { label: "open", info: "neither produced nor finally consumed in the log" },
};

/** An event with its activity, e.g. "roll (e3)". */
const eventText = (activity?: string | null, event?: string | null) => (event ? `${activity ?? "?"} (${event})` : "–");


/** Hover text of the connectedness column. */
const CONNECTEDNESS_INFO =
  "Share of a handling unit’s own events that it shares with at least one other handling unit. Transformation events are left out, because sharing those is lineage, not being handled together.";

/** One column of the table: where it belongs, its title and hover text, how its values look. */
type ColumnSpec = {
  accessor: ProfileFilterColumn | "time_split";
  title: string;
  group: Group | "Handling unit";
  format: ValueFormat;
  info?: string;
  render?: (r: HuProfileRow, scheme: Scheme) => React.ReactNode;
  /** Shown only if the log has it. */
  when?: (page: HuProfilePage | undefined) => boolean;
};

const count = (accessor: ProfileFilterColumn, title: string, group: Group, info?: string): ColumnSpec => ({
  accessor,
  title,
  group,
  format: "count",
  info,
  render: (r) => num((r as unknown as Record<string, number>)[accessor]),
});
const time = (accessor: ProfileFilterColumn, title: string, info?: string, when?: ColumnSpec["when"]): ColumnSpec => ({
  accessor,
  title,
  group: "Time",
  format: "duration",
  info,
  when,
  render: (r) => duration((r as unknown as Record<string, number>)[accessor]),
});

/** All columns, in table order: handling unit, Lifecycle, Lineage, Locations, MF Profile, Time. */
const COLUMNS: ColumnSpec[] = [
  { accessor: "hu", title: "Handling unit", group: "Handling unit", format: "text" },
  { accessor: "object_type", title: "Object type", group: "Handling unit", format: "text" },
  {
    accessor: "lifecycle",
    title: "Lifecycle",
    group: "Handling unit",
    format: "text",
    render: (r, scheme) => (
      <Tooltip label={LIFECYCLE[r.lifecycle]?.info} withinPortal>
        <Badge size="xs" variant={r.lifecycle === "both" ? "filled" : "light"} color={UI[scheme].primary} style={{ textTransform: "none" }}>{LIFECYCLE[r.lifecycle]?.label ?? r.lifecycle}</Badge>
      </Tooltip>
    ),
  },
  count("n_events", "Events", "Lifecycle"),
  { accessor: "first", title: "First", group: "Lifecycle", format: "time", render: (r) => stamp(r.first) },
  { accessor: "last", title: "Last", group: "Lifecycle", format: "time", render: (r) => stamp(r.last) },
  { accessor: "lifespan", title: "Lifespan", group: "Lifecycle", format: "duration", render: (r) => duration(r.lifespan) },
  count("n_partial_consumptions", "Partial consumptions", "Lifecycle"),
  count(
    "n_linked",
    "Linked HUs",
    "Lifecycle",
    "Other handling units that share at least one event with this one, transformation events included (so its parents, children and siblings count too).",
  ),
  count("n_parents", "Parents", "Lineage"),
  count("n_children", "Children", "Lineage"),
  count("n_siblings", "Siblings", "Lineage"),
  count("n_locations", "Locations", "Locations"),
  { ...count("n_high_level_locations", "High-level locations", "Locations"), when: (p) => !!p?.has_high_level },
  { accessor: "first_location", title: "First location", group: "Locations", format: "text", render: (r) => r.first_location ?? "⊥" },
  { accessor: "last_location", title: "Last location", group: "Locations", format: "text", render: (r) => r.last_location ?? "⊥" },
  count("n_location_changes", "Location changes", "Locations"),
  { accessor: "locatedness", title: "Locatedness", group: "Locations", format: "text", render: (r) => r.locatedness ?? "–" },
  count("n_movements", "Movements", "MF Profile"),
  count("n_processing", "Processing operations", "MF Profile"),
  count("n_shared_events", "Shared events", "MF Profile", "Events that are not transformation events and involve at least one other handling unit."),
  {
    accessor: "connectedness",
    title: "Connectedness",
    group: "MF Profile",
    format: "share",
    info: CONNECTEDNESS_INFO,
    render: (r) => (r.connectedness == null ? "–" : `${Math.round(r.connectedness * 100)} %`),
  },
  count("n_co_handled", "Co-handled HUs", "MF Profile", "Other handling units in the shared events (transformation events left out)."),
  { accessor: "time_split", title: "Time split", group: "Time", format: "text", render: (r, scheme) => <TimeSplit row={r} scheme={scheme} /> },
  time("time_vehicle", "On vehicles", undefined, (p) => !!p?.has_vehicles),
  time("time_storage", "In storage", undefined, (p) => !!p?.has_storage),
  time("time_other", "At other locations"),
  time("time_unlocated", "Unlocated"),
];

/** Very pale background of each column group (header row and column titles), so the groups stand out. */
const GROUP_TINT: Record<Group | "Handling unit", number> = { "Handling unit": -1, Lifecycle: 0, Lineage: 1, Locations: 2, "MF Profile": 3, Time: 4 };
const tint = (group: Group | "Handling unit", scheme: Scheme) => {
  const i = GROUP_TINT[group];
  return i < 0 ? undefined : `${CATEGORICAL[scheme][i]}${scheme === "dark" ? "26" : "14"}`;
};

/** The shown columns (groups switched on, columns the log has). */
const shownColumns = (groups: Group[], page: HuProfilePage | undefined) =>
  COLUMNS.filter((c) => (c.group === "Handling unit" || groups.includes(c.group)) && (!c.when || c.when(page)));

/**
 * The column groups of the table (one header row naming the groups above the column titles).
 *
 * @param specs The shown columns.
 * @param page The current page (filter options).
 * @param scheme Colour scheme.
 * @param filters Active filters.
 * @param setFilter Sets or removes the filter of a column.
 */
const columnGroups = (
  specs: ColumnSpec[],
  page: HuProfilePage | undefined,
  scheme: Scheme,
  filters: TableState["filters"],
  setFilter: (column: ProfileFilterColumn, filter: ProfileFilter | undefined) => void,
): DataTableColumnGroup<HuProfileRow>[] => {
  const infos = new Map((page?.columns ?? []).map((i) => [i.column, i]));
  const column = (s: ColumnSpec): DataTableColumn<HuProfileRow> => {
    const filterable = s.accessor !== "time_split";
    const col = s.accessor as ProfileFilterColumn;
    return {
      accessor: s.accessor,
      title: s.info ? (
        <Tooltip label={s.info} withinPortal multiline w={320}>
          <span style={{ textDecoration: "underline dotted" }}>{s.title}</span>
        </Tooltip>
      ) : (
        s.title
      ),
      sortable: filterable,
      noWrap: true,
      textAlign: s.format === "count" || s.format === "duration" || s.format === "share" ? "right" : "left",
      titleStyle: { background: tint(s.group, scheme) },
      render: s.render ? (r) => s.render?.(r, scheme) : undefined,
      ...(filterable
        ? {
            filter: ({ close }: { close: () => void }) => (
              <ProfileColumnFilter
                key={JSON.stringify(filters[col] ?? null)}
                column={col}
                info={infos.get(col)}
                format={s.format}
                value={filters[col]}
                onChange={(f) => setFilter(col, f)}
                close={close}
              />
            ),
            filtering: !!filters[col],
          }
        : {}),
    };
  };
  const order: (Group | "Handling unit")[] = ["Handling unit", ...GROUPS];
  return order
    .map((g) => ({ g, cols: specs.filter((s) => s.group === g) }))
    .filter(({ cols }) => cols.length)
    .map(({ g, cols }) => ({
      id: g,
      title: <Text size="xs" fw={700} c="dimmed">{g === "Handling unit" ? "" : g}</Text>,
      className: `lbo-group-${GROUP_TINT[g]}`,
      columns: cols.map(column),
    }));
};

/** Styles of the group header cells (pale tint per group). */
const GroupStyles = ({ scheme }: { scheme: Scheme }) => (
  <style>
    {GROUPS.map((g) => `th.lbo-group-${GROUP_TINT[g]} { background: ${tint(g, scheme)} !important; }`).join("\n")}
  </style>
);

/** Starts a download of a text file. */
const download = (name: string, content: string, type: string) => {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
};

/** An event as "roll (e3) · 2026-01-01 03:00:00", "–" if missing. */
const eventLine = (e: DetailEvent | null | undefined) => (e ? `${eventText(e.activity, e.event)} · ${stamp(e.time)}` : "–");

/** Handling units listed as links at most (the rest as "(+n)" with the list on hover). */
const MAX_LINKS = 20;

/** Handling-unit ids as links that add the handling unit to the selection; "–" if none. */
const HuLinks = ({ ids, onPick }: { ids: string[]; onPick: (hu: string) => void }) =>
  ids.length ? (
    <Group gap={6}>
      {ids.slice(0, MAX_LINKS).map((hu) => (
        <Anchor key={hu} size="xs" component="button" type="button" onClick={() => onPick(hu)} title="add to the selection">
          {hu}
        </Anchor>
      ))}
      {ids.length > MAX_LINKS && <ShortList items={ids.slice(MAX_LINKS)} limit={0} />}
    </Group>
  ) : (
    <Text span size="xs" c="dimmed">–</Text>
  );

/** A labelled line of the unfolded row. */
const Line = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <Group gap={6} wrap="nowrap" align="flex-start">
    <Text size="xs" c="dimmed" w={130} style={{ flexShrink: 0 }}>{label}</Text>
    <Box style={{ fontSize: "var(--mantine-font-size-xs)" }}>{children}</Box>
  </Group>
);

/**
 * An unfolded row: the names behind the counts, start and end, the location path and the co-handled handling units.
 *
 * @param ocelId The log.
 * @param hu The handling unit.
 * @param onPick Called with a handling unit clicked in the details (adds it to the selection).
 * @param width Visible width of the table: the panel stays in view when the table scrolls sideways.
 */
const HuDetailsPanel = ({ ocelId, hu, onPick, width }: { ocelId: string; hu: string; onPick: (hu: string) => void; width: number }) => {
  const { data, error } = useQuery({
    queryKey: ["locationBasedOcpm", "instances", "details", ocelId, hu],
    queryFn: ({ signal }) => getHuDetails(ocelId, { hu }, undefined, signal),
  });
  if (error) return <Text size="xs" c="red">{errorText(error)}</Text>;
  if (!data) return <Loader size="xs" m="xs" />;
  return (
    <SimpleGrid cols={width > 1100 ? 4 : width > 560 ? 2 : 1} spacing="md" px="md" py="xs" style={{ position: "sticky", left: 0, width: width || undefined }}>
      <Stack gap={2}>
        <Text size="xs" fw={600}>Start and end</Text>
        <Line label="First event">{eventLine(data.first_event)}</Line>
        <Line label="Last event">{eventLine(data.last_event)}</Line>
        <Line label="Created by">{eventLine(data.creation)}</Line>
        <Line label="Finally consumed by">{eventLine(data.final_consumption)}</Line>
        <Line label={`Partial cons. (${data.partial_consumptions.length})`}>
          {data.partial_consumptions.length ? data.partial_consumptions.map((e) => <div key={e.event}>{eventLine(e)}</div>) : "–"}
        </Line>
      </Stack>
      <Stack gap={2}>
        <Text size="xs" fw={600}>Lineage</Text>
        <Line label={`Parents (${data.parents.length})`}><HuLinks ids={data.parents} onPick={onPick} /></Line>
        <Line label={`Children (${data.children.length})`}><HuLinks ids={data.children} onPick={onPick} /></Line>
        <Line label={`Siblings (${data.siblings.length})`}><HuLinks ids={data.siblings} onPick={onPick} /></Line>
      </Stack>
      <Stack gap={2}>
        <Text size="xs" fw={600}>Locations ({data.location_path.length} stays)</Text>
        {data.location_path.length ? (
          data.location_path.map((p, i) => (
            <Line key={`${p.event}-${i}`} label={stamp(p.time)}>{`${i ? "→ " : ""}${p.location} (${p.event})`}</Line>
          ))
        ) : (
          <Text size="xs" c="dimmed">never located</Text>
        )}
      </Stack>
      <Stack gap={2}>
        <Text size="xs" fw={600}>MF Profile</Text>
        <Line label="Processing">{data.processing.length ? data.processing.map((a) => `${a.activity} ${a.count}`).join(", ") : "–"}</Line>
        <Line label={`Co-handled (${data.co_handled.length})`}>
          {data.co_handled.length
            ? data.co_handled.map((h) => (
                <div key={h.hu}>
                  <Anchor size="xs" component="button" type="button" onClick={() => onPick(h.hu)} title="add to the selection">{h.hu}</Anchor>
                  {`: ${h.count} (${h.events.join(", ")})`}
                </div>
              ))
            : "–"}
        </Line>
      </Stack>
    </SimpleGrid>
  );
};

/** Legend of the time split colours. */
const TimeLegend = ({ scheme }: { scheme: Scheme }) => {
  const colours = kindColours(scheme);
  return (
    <Group gap="sm">
      {(Object.keys(colours) as (keyof typeof colours)[]).map((k) => (
        <Group key={k} gap={4}>
          <Box w={10} h={10} style={{ background: colours[k], borderRadius: 2 }} />
          <Text fz={11} c="dimmed">{k === "other" ? "other locations" : k === "vehicle" ? "on vehicles" : k === "storage" ? "in storage" : "unlocated"}</Text>
        </Group>
      ))}
    </Group>
  );
};

/**
 * Export of the table as shown (folded): all handling units matching search and filters, in the current order,
 * with the shown columns. As a CSV file, or saved to the session as an Ocelescope "OCEL Mapping" resource.
 */
const ExportButtons = ({ ocelId, request }: { ocelId: string; request: ProfileExportRequest }) => {
  const [name, setName] = useState("HU profile");
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const rows = (n: number) => `${num(n)} ${n === 1 ? "row" : "rows"}`;
  const run = async (task: () => Promise<string>) => {
    setBusy(true);
    try {
      setMessage({ text: await task() });
    } catch (e) {
      setMessage({ text: errorText(e), error: true });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Stack gap={4} align="flex-end">
      <Group gap="xs" align="flex-end">
        <Button
          size="xs"
          variant="default"
          leftSection={<DownloadIcon size={14} />}
          loading={busy}
          onClick={() =>
            run(async () => {
              const csv = await exportHuProfileCsv(ocelId, request);
              download(csv.file_name, csv.content, "text/csv");
              return `Downloaded ${csv.file_name} (${rows(csv.rows)}).`;
            })
          }
        >
          CSV
        </Button>
        <Popover position="bottom-end" withArrow trapFocus opened={saving} onChange={setSaving}>
          <Popover.Target>
            <Button size="xs" variant="default" leftSection={<SaveIcon size={14} />} loading={busy} onClick={() => setSaving((o) => !o)}>
              Save to session
            </Button>
          </Popover.Target>
          <Popover.Dropdown>
            <Stack gap="xs" w={240}>
              <TextInput size="xs" label="Resource name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
              <Text size="xs" c="dimmed">Saved as an OCEL Mapping: the handling units as objects, the shown columns as their values.</Text>
              <Button
                size="xs"
                onClick={() =>
                  run(async () => {
                    setSaving(false);
                    const saved = await saveHuProfile(ocelId, { ...request, name });
                    return `Saved “${saved.name}” to the session (${rows(saved.rows)}).`;
                  })
                }
              >
                Save
              </Button>
            </Stack>
          </Popover.Dropdown>
        </Popover>
      </Group>
      {message && (
        <Text size="xs" c={message.error ? "red" : "dimmed"}>
          {message.text}
        </Text>
      )}
    </Stack>
  );
};

/**
 * The HU profile table.
 *
 * @param ocelId The log.
 * @param selected Ids of the selected handling units (kept across pages and searches).
 * @param onSelected Called with the new selection.
 */
export const HuProfileTable = ({ ocelId, selected, onSelected }: { ocelId: string; selected: string[]; onSelected: (ids: string[]) => void }) => {
  const scheme = useScheme();
  const [stored, setStored] = usePageState<TableState>(`instances.table.v2.${ocelId}`, DEFAULT_TABLE);
  const state = { ...DEFAULT_TABLE, ...stored };
  const set = (change: Partial<TableState>) => setStored((s) => ({ ...DEFAULT_TABLE, ...s, ...change }));
  const setFilter = (column: ProfileFilterColumn, filter: ProfileFilter | undefined) =>
    setStored((s) => {
      const filters = { ...(s.filters ?? {}) };
      if (filter) filters[column] = filter;
      else delete filters[column];
      return { ...DEFAULT_TABLE, ...s, filters, page: 1 };
    });
  const [search] = useDebouncedValue(state.search, 250);
  const filters = Object.values(state.filters).filter((f): f is ProfileFilter => !!f);
  const query: ProfileQuery = {
    search,
    filters,
    sort_by: state.sort.columnAccessor,
    descending: state.sort.direction === "desc",
    offset: (state.page - 1) * state.pageSize,
    limit: state.pageSize,
  };
  const { data, error, isFetching } = useQuery({
    queryKey: ["locationBasedOcpm", "instances", "profile", ocelId, query],
    queryFn: ({ signal }) => getHuProfile(ocelId, query, undefined, undefined, signal),
    placeholderData: keepPreviousData,
  });
  const specs = useMemo(() => shownColumns(state.groups, data), [state.groups, data]);
  const groups = columnGroups(specs, data, scheme, state.filters, setFilter);
  const exportRequest: ProfileExportRequest = {
    ...query,
    columns: specs.filter((s) => s.accessor !== "time_split").map((s) => s.accessor as ProfileFilterColumn),
  };
  const formats = new Map(COLUMNS.map((c) => [c.accessor, c]));
  const { ref, width } = useElementSize();
  const selectedRecords = useMemo(() => selected.map((hu) => ({ hu }) as HuProfileRow), [selected]);

  return (
    <Stack gap="xs" ref={ref}>
      <GroupStyles scheme={scheme} />
      <Group gap="md" align="flex-end" justify="space-between">
        <Group gap="md" align="flex-end">
          <TextInput
            size="xs"
            label="Search"
            placeholder="id, type, location, activity, parent, child"
            leftSection={<SearchIcon size={14} />}
            value={state.search}
            onChange={(e) => set({ search: e.currentTarget.value, page: 1 })}
            w={300}
          />
          <div>
            <Text size="xs" fw={500}>Columns</Text>
            <Chip.Group multiple value={state.groups} onChange={(v) => set({ groups: GROUPS.filter((g) => v.includes(g)) })}>
              <Group gap={4}>
                {GROUPS.map((g) => (
                  <Chip key={g} value={g} size="xs" variant="outline">{g}</Chip>
                ))}
              </Group>
            </Chip.Group>
          </div>
        </Group>
        <ExportButtons ocelId={ocelId} request={exportRequest} />
      </Group>
      {filters.length > 0 && (
        <Group gap={6}>
          <Text size="xs" c="dimmed">Filters:</Text>
          {filters.map((f) => {
            const spec = formats.get(f.column);
            return (
              <Pill key={f.column} size="sm" withRemoveButton onRemove={() => setFilter(f.column, undefined)}>
                {`${spec?.title ?? f.column}: ${filterText(f, spec?.format ?? "text")}`}
              </Pill>
            );
          })}
          <Anchor size="xs" component="button" type="button" onClick={() => set({ filters: {}, page: 1 })}>
            Clear all
          </Anchor>
        </Group>
      )}
      {state.groups.includes("Time") && <TimeLegend scheme={scheme} />}
      {error ? (
        <Text size="sm" c="red">{errorText(error)}</Text>
      ) : (
        <DataTable<HuProfileRow>
          withTableBorder
          withColumnBorders
          striped
          highlightOnHover
          fz="xs"
          minHeight={160}
          idAccessor="hu"
          records={data?.rows ?? []}
          fetching={isFetching && !data}
          groups={groups}
          totalRecords={data?.total ?? 0}
          page={state.page}
          onPageChange={(page) => set({ page })}
          recordsPerPage={state.pageSize}
          recordsPerPageOptions={PAGE_SIZES}
          onRecordsPerPageChange={(pageSize) => set({ pageSize, page: 1 })}
          sortStatus={state.sort as DataTableSortStatus<HuProfileRow>}
          onSortStatusChange={(s) => set({ sort: { columnAccessor: s.columnAccessor as ProfileQuerySortBy, direction: s.direction }, page: 1 })}
          rowExpansion={{
            allowMultiple: true,
            content: ({ record }) => <HuDetailsPanel ocelId={ocelId} hu={record.hu} width={width - 2} onPick={(hu) => onSelected(selected.includes(hu) ? selected : [...selected, hu])} />,
          }}
          selectedRecords={selectedRecords}
          onSelectedRecordsChange={(records) => onSelected(records.map((r) => r.hu))}
          noRecordsText="No handling unit matches."
          paginationText={({ from, to, totalRecords }) => `${num(from)}–${num(to)} of ${num(totalRecords)} handling units`}
        />
      )}
    </Stack>
  );
};
