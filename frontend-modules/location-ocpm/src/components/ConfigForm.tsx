// Configuration form: the inputs of overview/Deriving Locations.md, section "input data".
// Documented in docs/pages/configuration.md.
import {
  Alert,
  Anchor,
  Button,
  FileButton,
  Group,
  MultiSelect,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
  Tooltip,
} from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { DownloadIcon, FolderOpenIcon, InfoIcon, UploadIcon } from "lucide-react";
import { type ReactNode, useState } from "react";
import {
  type ApplyResult,
  type DerivationConfig,
  type Message,
  type TableInfo,
  type ValueCount,
  getGetConfigQueryKey,
  getListTablesQueryKey,
  useApplyConfig,
  useGetAttributeValues,
  useGetOptions,
  useListTables,
  useUploadTable,
} from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";

// region Form state
// The form keeps the entries of every option of an input, so switching the option and back
// loses nothing. `toConfig` turns it into the configuration the backend expects.

type Level = 0 | 1 | 2 | 3;

type TableEntries = { table: string | null; event_column: string | null };

type EventSetDraft = TableEntries & {
  option: "none" | "activities" | "attribute_values" | "qualifiers" | "table";
  activities: string[];
  attribute: string | null;
  values: string[];
  qualifiers: string[];
};

type LocationsDraft = TableEntries & {
  option: "none" | "attribute" | "qualifiers" | "table";
  attribute: string | null;
  qualifiers: string[];
  name_attribute: string | null;
  location_column: string | null;
};

/** Everything the form holds. */
export type ConfigDraft = {
  handling_units: {
    option: "object_types" | "table";
    object_types: string[];
    table: string | null;
    object_column: string | null;
  };
  movement_events: EventSetDraft;
  transformation_events: EventSetDraft;
  target_locations: LocationsDraft;
  pickup_locations: LocationsDraft;
  level: Level;
};

const emptyEvents = (option: EventSetDraft["option"]): EventSetDraft => ({
  option,
  activities: [],
  attribute: null,
  values: [],
  qualifiers: [],
  table: null,
  event_column: null,
});

const emptyLocations = (option: LocationsDraft["option"]): LocationsDraft => ({
  option,
  attribute: null,
  qualifiers: [],
  name_attribute: null,
  table: null,
  event_column: null,
  location_column: null,
});

/** The empty form: no choices yet, Level 3 (the default of the concept). */
export const emptyDraft = (): ConfigDraft => ({
  handling_units: { option: "object_types", object_types: [], table: null, object_column: null },
  movement_events: emptyEvents("activities"),
  transformation_events: emptyEvents("none"),
  target_locations: emptyLocations("attribute"),
  pickup_locations: emptyLocations("none"),
  level: 3,
});

const eventsToConfig = (d: EventSetDraft) => {
  switch (d.option) {
    case "activities":
      return { option: "activities" as const, activities: d.activities };
    case "attribute_values":
      return { option: "attribute_values" as const, attribute: d.attribute ?? "", values: d.values };
    case "qualifiers":
      return { option: "qualifiers" as const, qualifiers: d.qualifiers };
    case "table":
      return { option: "table" as const, table: d.table ?? "", event_column: d.event_column ?? "" };
    default:
      return null;
  }
};

const locationsToConfig = (d: LocationsDraft) => {
  switch (d.option) {
    case "attribute":
      return { option: "attribute" as const, attribute: d.attribute ?? "" };
    case "qualifiers":
      return { option: "qualifiers" as const, qualifiers: d.qualifiers, name_attribute: d.name_attribute };
    case "table":
      return {
        option: "table" as const,
        table: d.table ?? "",
        event_column: d.event_column ?? "",
        location_column: d.location_column ?? "",
      };
    default:
      return null;
  }
};

/** The configuration the backend expects, from the form. */
export const toConfig = (d: ConfigDraft): DerivationConfig => ({
  handling_units:
    d.handling_units.option === "table"
      ? { option: "table", table: d.handling_units.table ?? "", object_column: d.handling_units.object_column ?? "" }
      : { option: "object_types", object_types: d.handling_units.object_types },
  movement_events: eventsToConfig(d.movement_events) as DerivationConfig["movement_events"],
  transformation_events: eventsToConfig(d.transformation_events),
  target_locations: locationsToConfig(d.target_locations) as DerivationConfig["target_locations"],
  pickup_locations: locationsToConfig(d.pickup_locations),
  level: d.level,
});

/** The form, filled with a configuration (e.g. the applied one, or one loaded from a file). */
export const fromConfig = (config: DerivationConfig): ConfigDraft => {
  const draft = emptyDraft();
  const hu = config.handling_units;
  draft.handling_units = { ...draft.handling_units, ...hu, option: hu.option ?? "object_types" } as ConfigDraft["handling_units"];
  draft.movement_events = { ...emptyEvents("activities"), ...config.movement_events } as EventSetDraft;
  draft.transformation_events = config.transformation_events
    ? ({ ...emptyEvents("activities"), ...config.transformation_events } as EventSetDraft)
    : emptyEvents("none");
  draft.target_locations = { ...emptyLocations("attribute"), ...config.target_locations } as LocationsDraft;
  draft.pickup_locations = config.pickup_locations
    ? ({ ...emptyLocations("attribute"), ...config.pickup_locations } as LocationsDraft)
    : emptyLocations("none");
  draft.level = (config.level ?? 3) as Level;
  return draft;
};

/** What is still missing before the form can be applied (one line per gap). */
export const missingEntries = (d: ConfigDraft): string[] => {
  const missing: string[] = [];
  const hu = d.handling_units;
  if (hu.option === "object_types" && !hu.object_types.length) missing.push("Handling units: select object types.");
  if (hu.option === "table" && !(hu.table && hu.object_column)) missing.push("Handling units: select a table and its object column.");
  const events = (name: string, e: EventSetDraft) => {
    if (e.option === "activities" && !e.activities.length) missing.push(`${name}: select activities.`);
    if (e.option === "attribute_values" && !(e.attribute && e.values.length)) missing.push(`${name}: select an attribute and values.`);
    if (e.option === "qualifiers" && !e.qualifiers.length) missing.push(`${name}: select qualifiers.`);
    if (e.option === "table" && !(e.table && e.event_column)) missing.push(`${name}: select a table and its event column.`);
  };
  events("Movement events", d.movement_events);
  events("Transformation events", d.transformation_events);
  const locations = (name: string, l: LocationsDraft) => {
    if (l.option === "attribute" && !l.attribute) missing.push(`${name}: select an event attribute.`);
    if (l.option === "qualifiers" && !l.qualifiers.length) missing.push(`${name}: select qualifiers.`);
    if (l.option === "table" && !(l.table && l.event_column && l.location_column))
      missing.push(`${name}: select a table, its event column and its location column.`);
  };
  locations("Target locations", d.target_locations);
  locations("Pickup locations", d.pickup_locations);
  return missing;
};

// endregion
// region Texts

/** The location levels; loc is the selected one (overview/Deriving Locations.md, "Deriving current locations"). */
const LEVELS = [
  { value: "0", label: "Level 0: provided locations only" },
  { value: "1", label: "Level 1: + forward fill" },
  { value: "2", label: "Level 2: + backward fill" },
  { value: "3", label: "Level 3: + transformation locations (default)" },
];

/** Lines of an info text, one paragraph each. */
const Lines = ({ lines }: { lines: ReactNode[] }) => (
  <Stack gap={4}>
    {lines.map((line, i) => (
      <Text key={i} size="xs">
        {line}
      </Text>
    ))}
  </Stack>
);

/** What each input means, shown when hovering over the ⓘ of its section. */
const INFO: Record<string, ReactNode> = {
  handlingUnits: (
    <Lines
      lines={[
        "Objects whose physical flow we follow, e.g. slabs and coils (HU).",
        "With object types, all objects of the selected types are handling units.",
        "Only relations between events and handling units get locations; other objects never appear in filters or charts.",
      ]}
    />
  ),
  movements: (
    <Lines
      lines={[
        "Events at which all involved handling units are transported from a pickup location to a target location (M).",
        "Every movement event needs a target location (RQ2), and no handling unit may be in two movement events at the same time (RQ3).",
        "Handling units change their location only at movement events.",
      ]}
    />
  ),
  transformations: (
    <Lines
      lines={[
        "Physical events in which at least one handling unit is consumed and/or produced, e.g. cast slab, roll, cut (T).",
        "Optional. Level 3 uses them: a handling unit involved in a transformation is where the event's other handling units are.",
        "Without transformation events, Level 3 equals Level 2.",
      ]}
    />
  ),
  targets: (
    <Lines
      lines={[
        "Where the handling units of an event are after it (uloc); for a movement, its target.",
        "Empty values (null, NaN, empty text, NA) are not provided locations; NA is never a location.",
        "No handling unit may have two different provided locations at the same time (RQ1).",
        "E2o qualifier: the object related to the event via one of the qualifiers is the location, named by its id or by an object attribute.",
      ]}
    />
  ),
  pickups: (
    <Lines
      lines={[
        "Where the handling units of a movement event are picked up (puloc). Optional.",
        "Where provided, it is the previous location (ploc) of the event's handling units.",
        "Pickup locations of events that are not movement events are ignored and reported.",
      ]}
    />
  ),
  level: (
    <Lines
      lines={[
        "Which current location (loc) and previous location (ploc) everything else uses. Each level adds to the previous one:",
        <>
          <b>Level 0:</b> provided locations only.
        </>,
        <>
          <b>Level 1:</b> + forward fill: a handling unit stays where it was last located.
        </>,
        <>
          <b>Level 2:</b> + backward fill: before its first movement, a handling unit is where it is first located, or at the
          pickup location of its first movement.
        </>,
        <>
          <b>Level 3 (default):</b> + transformation locations: before its first movement, a handling unit is where its earliest
          agreeing transformation event is.
        </>,
        "Flags always use the selected level.",
      ]}
    />
  ),
};

// endregion
// region Building blocks

const Section = ({ title, info, hint, children }: { title: string; info: ReactNode; hint?: string; children: ReactNode }) => (
  <Stack gap={6}>
    <Group gap={6}>
      <Text fw={600} size="sm">
        {title}
      </Text>
      <Tooltip label={info} multiline w={380} withArrow position="top-start">
        <InfoIcon size={14} style={{ cursor: "help", opacity: 0.6 }} aria-label={`About ${title}`} />
      </Tooltip>
    </Group>
    {hint && (
      <Text size="xs" c="dimmed">
        {hint}
      </Text>
    )}
    {children}
  </Stack>
);

const withCounts = (values: ValueCount[] | undefined) =>
  (values ?? []).map((v) => ({ value: v.value, label: `${v.value} (${v.count})` }));

/** Pick values with counts, e.g. object types or activities. */
const CountPicker = ({
  data,
  value,
  onChange,
  placeholder,
  label,
}: {
  data: ValueCount[] | undefined;
  value: string[];
  onChange: (v: string[]) => void;
  placeholder: string;
  label?: string;
}) => (
  <MultiSelect
    size="xs"
    label={label}
    data={withCounts(data)}
    value={value}
    onChange={onChange}
    placeholder={placeholder}
    searchable
    clearable
  />
);

/** Values of an event attribute with their number of events. */
const AttributeValuePicker = ({
  ocelId,
  attribute,
  value,
  onChange,
  label,
}: {
  ocelId: string;
  attribute: string | null;
  value: string[];
  onChange: (v: string[]) => void;
  label: string;
}) => {
  const { data } = useGetAttributeValues(ocelId, { attribute: attribute ?? "" }, { query: { enabled: !!attribute } });
  return (
    <MultiSelect
      size="xs"
      label={label}
      data={withCounts(data)}
      value={value}
      onChange={onChange}
      disabled={!attribute}
      searchable
      clearable
    />
  );
};

/** First rows of an uploaded table. */
const Preview = ({ table }: { table: TableInfo }) => (
  <Table.ScrollContainer minWidth={200}>
    <Table fz="xs" withTableBorder striped>
      <Table.Thead>
        <Table.Tr>
          {table.columns.map((column) => (
            <Table.Th key={column}>{column}</Table.Th>
          ))}
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {table.preview.map((row, i) => (
          <Table.Tr key={i}>
            {table.columns.map((column) => (
              <Table.Td key={column}>{row[column] ?? ""}</Table.Td>
            ))}
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  </Table.ScrollContainer>
);

/** Select an uploaded table (or upload one) and some of its columns; with a preview of the first rows. */
const TableColumns = ({
  tables,
  table,
  onTable,
  columns,
}: {
  tables: TableInfo[];
  table: string | null;
  onTable: (name: string | null) => void;
  columns: { label: string; value: string | null; onChange: (v: string | null) => void }[];
}) => {
  const queryClient = useQueryClient();
  const [showPreview, setShowPreview] = useState(false);
  const upload = useUploadTable({
    mutation: {
      onSuccess: async (info) => {
        await queryClient.invalidateQueries({ queryKey: getListTablesQueryKey() });
        // Re-uploading the selected table (or the table a loaded configuration names) keeps the
        // chosen columns; a different file becomes the selected table, with columns to choose.
        if (info.name !== table) onTable(info.name);
      },
    },
  });
  const selected = tables.find((t) => t.name === table);
  return (
    <Stack gap={4}>
      <Group grow align="flex-end">
        <Select
          size="xs"
          label="Table"
          placeholder={tables.length ? "Select an uploaded table" : "Upload a CSV file"}
          data={tables.map((t) => ({ value: t.name, label: `${t.name} (${t.row_count} rows)` }))}
          value={table}
          onChange={onTable}
          searchable
        />
        {columns.map((c) => (
          <Select
            key={c.label}
            size="xs"
            label={c.label}
            data={selected?.columns ?? []}
            value={c.value}
            onChange={c.onChange}
            disabled={!selected}
            searchable
          />
        ))}
      </Group>
      <Group gap="xs">
        <FileButton onChange={(file) => file && upload.mutate({ data: { file } })} accept=".csv,text/csv">
          {(props) => (
            <Button {...props} size="compact-xs" variant="subtle" leftSection={<UploadIcon size={12} />} loading={upload.isPending}>
              Upload CSV
            </Button>
          )}
        </FileButton>
        {selected && (
          <Anchor size="xs" onClick={() => setShowPreview((v) => !v)}>
            {showPreview ? "Hide preview" : "Show first rows"}
          </Anchor>
        )}
        {upload.error && (
          <Text size="xs" c="red">
            {errorText(upload.error)}
          </Text>
        )}
      </Group>
      {selected && showPreview && <Preview table={selected} />}
    </Stack>
  );
};

/** One blocking error or notice, with its ids (first 20, "show all" for the rest that was sent). */
const MessageLine = ({ message, colour }: { message: Message; colour?: string }) => {
  const [all, setAll] = useState(false);
  const shown = all ? message.ids : message.ids.slice(0, 20);
  return (
    <Stack gap={2}>
      <Text size="sm" c={colour}>
        {message.message}
      </Text>
      {message.ids.length > 0 && (
        <Text size="xs" c="dimmed">
          {shown.join(", ")}
          {message.ids.length > shown.length && (
            <>
              {" "}
              <Anchor size="xs" onClick={() => setAll(true)}>
                show all {message.ids.length}
              </Anchor>
            </>
          )}
          {all && message.count > message.ids.length && ` (first ${message.ids.length} of ${message.count})`}
        </Text>
      )}
    </Stack>
  );
};

/** Notices (grey lines) of the last applied configuration. */
export const Notices = ({ notices }: { notices: Message[] | undefined }) =>
  notices?.length ? (
    <Stack gap={4}>
      {notices.map((n) => (
        <MessageLine key={n.code + n.message} message={n} colour="dimmed" />
      ))}
    </Stack>
  ) : null;

// endregion
// region Sections

type SectionProps<T> = { value: T; onChange: (v: T) => void; ocelId: string; tables: TableInfo[] };

const EventSetFields = ({
  value: d,
  onChange,
  ocelId,
  tables,
  activities,
  qualifiers,
  eventAttributes,
  optional,
  valueLabel,
}: SectionProps<EventSetDraft> & {
  activities: ValueCount[] | undefined;
  qualifiers?: ValueCount[];
  eventAttributes: string[];
  optional: boolean;
  valueLabel: string;
}) => (
  <Stack gap={6}>
    <SegmentedControl
      size="xs"
      data={[
        ...(optional ? [{ value: "none", label: "none" }] : []),
        { value: "activities", label: "activities" },
        { value: "attribute_values", label: "event attribute" },
        ...(qualifiers ? [{ value: "qualifiers", label: "e2o qualifiers" }] : []),
        { value: "table", label: "table" },
      ]}
      value={d.option}
      onChange={(option) => onChange({ ...d, option: option as EventSetDraft["option"] })}
    />
    {d.option === "activities" && (
      <CountPicker data={activities} value={d.activities} onChange={(a) => onChange({ ...d, activities: a })} placeholder="Select activities" />
    )}
    {d.option === "attribute_values" && (
      <Group grow align="flex-start">
        <Select
          size="xs"
          label="Event attribute"
          data={eventAttributes}
          value={d.attribute}
          onChange={(attribute) => onChange({ ...d, attribute, values: [] })}
          searchable
        />
        <AttributeValuePicker ocelId={ocelId} attribute={d.attribute} value={d.values} onChange={(values) => onChange({ ...d, values })} label={valueLabel} />
      </Group>
    )}
    {d.option === "qualifiers" && (
      <CountPicker data={qualifiers} value={d.qualifiers} onChange={(q) => onChange({ ...d, qualifiers: q })} placeholder="Select qualifiers" />
    )}
    {d.option === "table" && (
      <TableColumns
        tables={tables}
        table={d.table}
        onTable={(table) => onChange({ ...d, table, event_column: null })}
        columns={[{ label: "Event column", value: d.event_column, onChange: (event_column) => onChange({ ...d, event_column }) }]}
      />
    )}
  </Stack>
);

const LocationFields = ({
  value: d,
  onChange,
  tables,
  qualifiers,
  eventAttributes,
  objectAttributes,
  optional,
}: SectionProps<LocationsDraft> & {
  qualifiers: ValueCount[] | undefined;
  eventAttributes: string[];
  objectAttributes: string[];
  optional: boolean;
}) => (
  <Stack gap={6}>
    <SegmentedControl
      size="xs"
      data={[
        ...(optional ? [{ value: "none", label: "none" }] : []),
        { value: "attribute", label: "event attribute" },
        { value: "qualifiers", label: "e2o qualifier" },
        { value: "table", label: "table" },
      ]}
      value={d.option}
      onChange={(option) => onChange({ ...d, option: option as LocationsDraft["option"] })}
    />
    {d.option === "attribute" && (
      <Select
        size="xs"
        data={eventAttributes}
        value={d.attribute}
        onChange={(attribute) => onChange({ ...d, attribute })}
        placeholder="Select the event attribute"
        searchable
      />
    )}
    {d.option === "qualifiers" && (
      <Group grow align="flex-start">
        <CountPicker
          label="Qualifiers"
          data={qualifiers}
          value={d.qualifiers}
          onChange={(q) => onChange({ ...d, qualifiers: q })}
          placeholder="Select qualifiers"
        />
        <Select
          size="xs"
          label="Location name"
          data={[{ value: "", label: "object id" }, ...objectAttributes.map((a) => ({ value: a, label: `attribute "${a}"` }))]}
          value={d.name_attribute ?? ""}
          onChange={(v) => onChange({ ...d, name_attribute: v || null })}
          allowDeselect={false}
        />
      </Group>
    )}
    {d.option === "table" && (
      <TableColumns
        tables={tables}
        table={d.table}
        onTable={(table) => onChange({ ...d, table, event_column: null, location_column: null })}
        columns={[
          { label: "Event column", value: d.event_column, onChange: (event_column) => onChange({ ...d, event_column }) },
          { label: "Location column", value: d.location_column, onChange: (location_column) => onChange({ ...d, location_column }) },
        ]}
      />
    )}
  </Stack>
);

// endregion
// region Download and load

const downloadJson = (config: DerivationConfig) => {
  const blob = new Blob([JSON.stringify(config, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "location-based-ocpm-configuration.json";
  link.click();
  URL.revokeObjectURL(url);
};

// endregion

/**
 * The configuration form. "Apply" derives everything in the backend; the configuration is
 * only stored if there is no blocking error, otherwise the errors are shown here.
 */
export const ConfigForm = ({
  ocelId,
  initial,
  onApplied,
  onCancel,
}: {
  ocelId: string;
  initial: DerivationConfig | null | undefined;
  onApplied: () => void;
  onCancel?: () => void;
}) => {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<ConfigDraft>(initial ? fromConfig(initial) : emptyDraft());
  const [result, setResult] = useState<ApplyResult | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const { data: options, error: optionsError } = useGetOptions(ocelId);
  const { data: tables = [] } = useListTables();
  const apply = useApplyConfig({
    mutation: {
      onSuccess: async (res) => {
        setResult(res);
        if (res.applied) {
          // Everything the module shows depends on the configuration.
          await queryClient.invalidateQueries({ queryKey: getGetConfigQueryKey(ocelId) });
          await queryClient.invalidateQueries({
            predicate: (q) => String(q.queryKey[0]).includes(`/locationBasedOcpm/v1/${ocelId}/`),
          });
          onApplied();
        }
      },
    },
  });
  const set = <K extends keyof ConfigDraft>(key: K) => (value: ConfigDraft[K]) => setDraft((d) => ({ ...d, [key]: value }));
  const missing = missingEntries(draft);
  const eventAttributes = options?.event_attributes ?? [];

  const load = async (file: File | null) => {
    if (!file) return;
    try {
      setDraft(fromConfig(JSON.parse(await file.text()) as DerivationConfig));
      setLoadError(null);
      setResult(null);
    } catch (error) {
      setLoadError(`Could not read the configuration file: ${String(error)}`);
    }
  };

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Title order={4}>Configuration</Title>
        <Group gap="xs">
          <FileButton onChange={load} accept=".json,application/json">
            {(props) => (
              <Button {...props} size="xs" variant="default" leftSection={<FolderOpenIcon size={14} />}>
                Load configuration
              </Button>
            )}
          </FileButton>
          <Button size="xs" variant="default" leftSection={<DownloadIcon size={14} />} onClick={() => downloadJson(toConfig(draft))}>
            Download configuration
          </Button>
        </Group>
      </Group>
      {optionsError && <Alert color="red">{errorText(optionsError)}</Alert>}
      {loadError && <Alert color="red">{loadError}</Alert>}

      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
        <Section title="Handling units (required)" info={INFO.handlingUnits} hint="All objects of the selected types, or the objects listed in a table.">
          <SegmentedControl
            size="xs"
            data={[
              { value: "object_types", label: "object types" },
              { value: "table", label: "table" },
            ]}
            value={draft.handling_units.option}
            onChange={(option) => set("handling_units")({ ...draft.handling_units, option: option as "object_types" | "table" })}
          />
          {draft.handling_units.option === "object_types" ? (
            <CountPicker
              data={options?.object_types}
              value={draft.handling_units.object_types}
              onChange={(object_types) => set("handling_units")({ ...draft.handling_units, object_types })}
              placeholder="Select object types"
            />
          ) : (
            <TableColumns
              tables={tables}
              table={draft.handling_units.table}
              onTable={(table) => set("handling_units")({ ...draft.handling_units, table, object_column: null })}
              columns={[
                {
                  label: "Object column",
                  value: draft.handling_units.object_column,
                  onChange: (object_column) => set("handling_units")({ ...draft.handling_units, object_column }),
                },
              ]}
            />
          )}
        </Section>

        <Section title="Location level" info={INFO.level} hint="Which current and previous locations all pages and flags use.">
          <Select
            size="xs"
            data={LEVELS}
            value={String(draft.level)}
            onChange={(v) => set("level")(Number(v ?? 3) as Level)}
            allowDeselect={false}
          />
        </Section>

        <Section title="Movement events (required)" info={INFO.movements} hint="Events at which all their handling units are moved to the event's target location.">
          <EventSetFields
            value={draft.movement_events}
            onChange={set("movement_events")}
            ocelId={ocelId}
            tables={tables}
            activities={options?.activities}
            eventAttributes={eventAttributes}
            optional={false}
            valueLabel='Values meaning "movement"'
          />
        </Section>

        <Section title="Transformation events (optional)" info={INFO.transformations} hint="Events in which handling units are consumed and/or produced.">
          <EventSetFields
            value={draft.transformation_events}
            onChange={set("transformation_events")}
            ocelId={ocelId}
            tables={tables}
            activities={options?.activities}
            qualifiers={options?.qualifiers}
            eventAttributes={eventAttributes}
            optional
            valueLabel='Values meaning "transformation"'
          />
        </Section>

        <Section title="Target locations (required)" info={INFO.targets} hint="Empty values (null, NaN, empty, NA) count as not provided.">
          <LocationFields
            value={draft.target_locations}
            onChange={set("target_locations")}
            ocelId={ocelId}
            tables={tables}
            qualifiers={options?.qualifiers}
            eventAttributes={eventAttributes}
            objectAttributes={options?.object_attributes ?? []}
            optional={false}
          />
        </Section>

        <Section title="Pickup locations (optional)" info={INFO.pickups} hint="Only used for movement events.">
          <LocationFields
            value={draft.pickup_locations}
            onChange={set("pickup_locations")}
            ocelId={ocelId}
            tables={tables}
            qualifiers={options?.qualifiers}
            eventAttributes={eventAttributes}
            objectAttributes={options?.object_attributes ?? []}
            optional
          />
        </Section>
      </SimpleGrid>

      {result && !result.applied && (
        <Alert color="red" title="The configuration could not be applied">
          <Stack gap="xs">
            {(result.errors ?? []).map((e) => (
              <MessageLine key={e.code + e.message} message={e} />
            ))}
          </Stack>
        </Alert>
      )}
      {result && <Notices notices={result.notices} />}
      {apply.error && <Alert color="red">{errorText(apply.error)}</Alert>}
      <Group>
        <Tooltip label={<Lines lines={missing} />} disabled={!missing.length} multiline w={320}>
          <Button onClick={() => apply.mutate({ ocelId, data: toConfig(draft) })} loading={apply.isPending} disabled={missing.length > 0}>
            Apply
          </Button>
        </Tooltip>
        {onCancel && (
          <Button variant="default" onClick={onCancel}>
            Cancel
          </Button>
        )}
        {missing.length > 0 && (
          <Text size="xs" c="dimmed">
            {missing.length === 1 ? "1 entry" : `${missing.length} entries`} missing (hover over Apply).
          </Text>
        )}
      </Group>
    </Stack>
  );
};
