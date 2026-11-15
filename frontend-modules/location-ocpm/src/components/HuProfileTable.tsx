// HU profile of the instance page: one row per handling unit, searchable, filterable by object type, sortable,
// paginated, with a checkbox per row to select handling units for the charts below. The overview shows counts (easy
// to sort); clicking a row unfolds it with the names behind the counts (as in the activity profile).
// Documented in docs/pages/instances.md, section "HU profile".
import { Anchor, Badge, Box, Chip, Group, Loader, MultiSelect, SimpleGrid, Stack, Text, TextInput, Tooltip } from "@mantine/core";
import { useDebouncedValue, useElementSize } from "@mantine/hooks";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { SearchIcon } from "lucide-react";
import { type DataTableColumn, DataTable, type DataTableSortStatus } from "mantine-datatable";
import { useMemo } from "react";
import { type DetailEvent, getHuDetails, getHuProfile, type GetHuProfileSortBy, type HuProfilePage, type HuProfileRow } from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import { num } from "../lib/format";
import { usePageState } from "../lib/pageState";
import { OTHER, type Scheme, STATUS, UI } from "../lib/palette";
import { ShortList } from "./ShortList";
import { useScheme } from "./plots";

/** Rows per page offered (default 25). */
const PAGE_SIZES = [10, 25, 50, 100];

/** Column groups that can be shown or hidden. */
const GROUPS = ["Lifecycle", "Lineage", "Locations", "Time", "Activities", "Connectedness"] as const;
type Group = (typeof GROUPS)[number];

/** Table state kept per log. */
type TableState = {
  search: string;
  objectTypes: string[];
  sort: { columnAccessor: GetHuProfileSortBy; direction: "asc" | "desc" };
  page: number;
  pageSize: number;
  groups: Group[];
};

const DEFAULT_TABLE: TableState = {
  search: "",
  objectTypes: [],
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
  full: { label: "full", info: "produced and finally consumed in the log" },
  produced: { label: "produced", info: "produced in the log, not finally consumed" },
  consumed: { label: "consumed", info: "finally consumed in the log, not produced in it" },
  open: { label: "open", info: "neither produced nor finally consumed in the log" },
};

/** An event with its activity, e.g. "roll (e3)". */
const eventText = (activity?: string | null, event?: string | null) => (event ? `${activity ?? "?"} (${event})` : "–");


/** The columns of the shown groups. */
const columns = (groups: Group[], page: HuProfilePage | undefined, scheme: Scheme): DataTableColumn<HuProfileRow>[] => {
  const on = (g: Group) => groups.includes(g);
  const cols: DataTableColumn<HuProfileRow>[] = [
    { accessor: "hu", title: "Handling unit", sortable: true },
    { accessor: "object_type", title: "Object type", sortable: true },
    {
      accessor: "lifecycle",
      title: "Lifecycle",
      sortable: true,
      render: (r) => (
        <Tooltip label={LIFECYCLE[r.lifecycle]?.info} withinPortal>
          <Badge size="xs" variant={r.lifecycle === "full" ? "filled" : "light"} color={UI[scheme].primary} style={{ textTransform: "none" }}>{LIFECYCLE[r.lifecycle]?.label ?? r.lifecycle}</Badge>
        </Tooltip>
      ),
    },
  ];
  if (on("Lifecycle"))
    cols.push(
      { accessor: "n_events", title: "Events", sortable: true, textAlign: "right", render: (r) => num(r.n_events) },
      { accessor: "first", title: "First", sortable: true, render: (r) => stamp(r.first) },
      { accessor: "last", title: "Last", sortable: true, render: (r) => stamp(r.last) },
      { accessor: "lifespan", title: "Lifespan", sortable: true, textAlign: "right", render: (r) => duration(r.lifespan) },
      { accessor: "n_partial_consumptions", title: "Partial consumptions", sortable: true, textAlign: "right", render: (r) => num(r.n_partial_consumptions) },
    );
  if (on("Lineage"))
    cols.push(
      { accessor: "n_parents", title: "Parents", sortable: true, textAlign: "right", render: (r) => num(r.n_parents) },
      { accessor: "n_children", title: "Children", sortable: true, textAlign: "right", render: (r) => num(r.n_children) },
      { accessor: "n_siblings", title: "Siblings", sortable: true, textAlign: "right", render: (r) => num(r.n_siblings) },
    );
  if (on("Locations")) {
    cols.push({ accessor: "n_locations", title: "Locations", sortable: true, textAlign: "right", render: (r) => num(r.n_locations) });
    if (page?.has_high_level)
      cols.push({ accessor: "n_high_level_locations", title: "High-level locations", sortable: true, textAlign: "right", render: (r) => num(r.n_high_level_locations) });
    cols.push(
      { accessor: "first_location", title: "First location", sortable: true, render: (r) => r.first_location ?? "⊥" },
      { accessor: "last_location", title: "Last location", sortable: true, render: (r) => r.last_location ?? "⊥" },
      { accessor: "n_location_changes", title: "Location changes", sortable: true, textAlign: "right", render: (r) => num(r.n_location_changes) },
      { accessor: "locatedness", title: "Locatedness", sortable: true, render: (r) => r.locatedness ?? "–" },
    );
  }
  if (on("Time")) {
    cols.push({ accessor: "time_split", title: "Time split", render: (r) => <TimeSplit row={r} scheme={scheme} /> });
    if (page?.has_vehicles) cols.push({ accessor: "time_vehicle", title: "On vehicles", sortable: true, textAlign: "right", render: (r) => duration(r.time_vehicle) });
    if (page?.has_storage) cols.push({ accessor: "time_storage", title: "In storage", sortable: true, textAlign: "right", render: (r) => duration(r.time_storage) });
    cols.push(
      { accessor: "time_other", title: "At other locations", sortable: true, textAlign: "right", render: (r) => duration(r.time_other) },
      { accessor: "time_unlocated", title: "Unlocated", sortable: true, textAlign: "right", render: (r) => duration(r.time_unlocated) },
    );
  }
  if (on("Activities"))
    cols.push(
      { accessor: "n_movements", title: "Movements", sortable: true, textAlign: "right", render: (r) => num(r.n_movements) },
      { accessor: "n_processing", title: "Processing operations", sortable: true, textAlign: "right", render: (r) => num(r.n_processing) },
    );
  if (on("Connectedness"))
    cols.push(
      {
        accessor: "n_shared_events",
        title: <Tooltip label="Events that are not transformation events and involve at least one other handling unit" withinPortal><span>Shared events</span></Tooltip>,
        sortable: true,
        textAlign: "right",
        render: (r) => num(r.n_shared_events),
      },
      {
        accessor: "connectedness",
        title: <Tooltip label="Shared events / events that are not transformation events" withinPortal><span>Connectedness</span></Tooltip>,
        sortable: true,
        textAlign: "right",
        render: (r) => (r.connectedness == null ? "–" : `${Math.round(r.connectedness * 100)} %`),
      },
      {
        accessor: "n_co_handled",
        title: <Tooltip label="Other handling units in the shared events" withinPortal><span>Co-handled HUs</span></Tooltip>,
        sortable: true,
        textAlign: "right",
        render: (r) => num(r.n_co_handled),
      },
    );
  // One line per row: names are in the unfolded row, so no cell needs to wrap.
  return cols.map((col) => ({ ...col, noWrap: true }) as DataTableColumn<HuProfileRow>);
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
        <Text size="xs" fw={600}>Activities and connectedness</Text>
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
 * The HU profile table.
 *
 * @param ocelId The log.
 * @param selected Ids of the selected handling units (kept across pages and searches).
 * @param onSelected Called with the new selection.
 */
export const HuProfileTable = ({ ocelId, selected, onSelected }: { ocelId: string; selected: string[]; onSelected: (ids: string[]) => void }) => {
  const scheme = useScheme();
  const [stored, setStored] = usePageState<TableState>(`instances.table.${ocelId}`, DEFAULT_TABLE);
  const state = { ...DEFAULT_TABLE, ...stored };
  const set = (change: Partial<TableState>) => setStored((s) => ({ ...DEFAULT_TABLE, ...s, ...change }));
  const [search] = useDebouncedValue(state.search, 250);
  const params = {
    search,
    object_types: state.objectTypes,
    sort_by: state.sort.columnAccessor,
    descending: state.sort.direction === "desc",
    offset: (state.page - 1) * state.pageSize,
    limit: state.pageSize,
  };
  const { data, error, isFetching } = useQuery({
    queryKey: ["locationBasedOcpm", "instances", "profile", ocelId, params],
    queryFn: ({ signal }) => getHuProfile(ocelId, params, undefined, signal),
    placeholderData: keepPreviousData,
  });
  const cols = useMemo(() => columns(state.groups, data, scheme), [state.groups, data, scheme]);
  const { ref, width } = useElementSize();
  const selectedRecords = useMemo(() => selected.map((hu) => ({ hu }) as HuProfileRow), [selected]);

  return (
    <Stack gap="xs" ref={ref}>
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
        <MultiSelect
          size="xs"
          label="Object types"
          placeholder={state.objectTypes.length ? undefined : "all"}
          data={(data?.object_types ?? []).map(([t, n]) => ({ value: t, label: `${t} (${num(n)})` }))}
          value={state.objectTypes}
          onChange={(v) => set({ objectTypes: v, page: 1 })}
          clearable
          w={260}
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
      {state.groups.includes("Time") && <TimeLegend scheme={scheme} />}
      {error ? (
        <Text size="sm" c="red">{errorText(error)}</Text>
      ) : (
        <DataTable<HuProfileRow>
          withTableBorder
          striped
          highlightOnHover
          fz="xs"
          minHeight={160}
          idAccessor="hu"
          records={data?.rows ?? []}
          fetching={isFetching && !data}
          columns={cols}
          totalRecords={data?.total ?? 0}
          page={state.page}
          onPageChange={(page) => set({ page })}
          recordsPerPage={state.pageSize}
          recordsPerPageOptions={PAGE_SIZES}
          onRecordsPerPageChange={(pageSize) => set({ pageSize, page: 1 })}
          sortStatus={state.sort as DataTableSortStatus<HuProfileRow>}
          onSortStatusChange={(s) => set({ sort: { columnAccessor: s.columnAccessor as GetHuProfileSortBy, direction: s.direction }, page: 1 })}
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
