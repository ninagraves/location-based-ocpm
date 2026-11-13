// Configuration form: the inputs of overview/Deriving Locations.md, section "input data", and the location
// context of overview/module/Module Overview.md ("Update Overview Page", section 1).
// Documented in docs/pages/configuration.md.
import {
  Alert,
  Anchor,
  Button,
  FileButton,
  Group,
  MultiSelect,
  NumberInput,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  TagsInput,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { DownloadIcon, FolderOpenIcon, InfoIcon, UploadIcon } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { DropTarget } from "./DropTarget";
import {
  type ApplyResult,
  type DerivationConfig,
  type LocationOptions,
  type Message,
  type TableInfo,
  type ValueCount,
  getGetConfigQueryKey,
  getListTablesQueryKey,
  useApplyConfig,
  useGetAttributeValues,
  useGetLocations,
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

type HighLevelDraft = {
  option: "none" | "table" | "event_attributes" | "object_attribute" | "o2o" | "pattern";
  table: string | null;
  location_column: string | null;
  high_level_column: string | null;
  low_attribute: string | null;
  high_attribute: string | null;
  attribute: string | null;
  qualifiers: string[];
  name_attribute: string | null;
  pattern: string;
};

type LocationSetDraft = {
  option: "none" | "locations" | "table" | "attribute_values" | "object_types";
  locations: string[];
  table: string | null;
  location_column: string | null;
  flag_column: string | null;
  attribute: string | null;
  values: string[];
  object_types: string[];
};

/** A set of objects (option 4 of the transformation inputs): object-attribute values or a table. */
type ObjectSetDraft = {
  option: "none" | "attribute_values" | "table";
  attribute: string | null;
  values: string[];
  table: string | null;
  object_column: string | null;
};

/** Consumed and produced handling units: options 1 to 6 of overview/concepts/Transformations.md ("default" = option 5
 * if transformation events are given, otherwise none). */
type RolesDraft = {
  option: "default" | "qualifiers" | "table" | "parents" | "object_sets" | "first_last" | "frequency";
  consumed_qualifiers: string[];
  produced_qualifiers: string[];
  table: string | null;
  event_column: string | null;
  object_column: string | null;
  role_column: string | null;
  consumed_values: string[];
  produced_values: string[];
  qualifiers: string[];
  direction: "child_of" | "parent_of";
  produced: ObjectSetDraft;
  consumed: ObjectSetDraft;
  consumption: "final" | "partial";
  threshold: number;
};

/** Processing operations: a selection like the transformation events ("none" = no further events), plus T. */
type ProcessingDraft = EventSetDraft & { include_transformations: boolean };

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
  transformation_roles: RolesDraft;
  target_locations: LocationsDraft;
  pickup_locations: LocationsDraft;
  level: Level;
  high_level_locations: HighLevelDraft;
  vehicles: LocationSetDraft;
  storage_units: LocationSetDraft;
  processing_operations: ProcessingDraft;
};

const emptyHighLevel = (): HighLevelDraft => ({
  option: "none",
  table: null,
  location_column: null,
  high_level_column: null,
  low_attribute: null,
  high_attribute: null,
  attribute: null,
  qualifiers: [],
  name_attribute: null,
  pattern: "",
});

const emptyLocationSet = (): LocationSetDraft => ({
  option: "none",
  locations: [],
  table: null,
  location_column: null,
  flag_column: null,
  attribute: null,
  values: [],
  object_types: [],
});

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

const emptyObjectSet = (): ObjectSetDraft => ({ option: "none", attribute: null, values: [], table: null, object_column: null });

const emptyRoles = (): RolesDraft => ({
  option: "default",
  consumed_qualifiers: [],
  produced_qualifiers: [],
  table: null,
  event_column: null,
  object_column: null,
  role_column: null,
  consumed_values: ["consumed"],
  produced_values: ["produced"],
  qualifiers: [],
  direction: "child_of",
  produced: emptyObjectSet(),
  consumed: emptyObjectSet(),
  consumption: "final",
  threshold: 0.5,
});

/** Options of the consumed/produced input that derive T themselves (the transformation-events input is not used). */
const DERIVES_T = ["qualifiers", "frequency"];
/** Options that need the transformation events. */
const NEEDS_T = ["parents", "object_sets", "first_last"];

/** The empty form: no choices yet, Level 3 (the default of the concept). */
export const emptyDraft = (): ConfigDraft => ({
  handling_units: { option: "object_types", object_types: [], table: null, object_column: null },
  movement_events: emptyEvents("activities"),
  transformation_events: emptyEvents("none"),
  transformation_roles: emptyRoles(),
  target_locations: emptyLocations("attribute"),
  pickup_locations: emptyLocations("none"),
  level: 3,
  high_level_locations: emptyHighLevel(),
  vehicles: emptyLocationSet(),
  storage_units: emptyLocationSet(),
  processing_operations: { ...emptyEvents("none"), include_transformations: true },
});

const highLevelToConfig = (d: HighLevelDraft): DerivationConfig["high_level_locations"] => {
  switch (d.option) {
    case "table":
      return {
        option: "table",
        table: d.table ?? "",
        location_column: d.location_column ?? "",
        high_level_column: d.high_level_column ?? "",
      };
    case "event_attributes":
      return { option: "event_attributes", low_attribute: d.low_attribute ?? "", high_attribute: d.high_attribute ?? "" };
    case "object_attribute":
      return { option: "object_attribute", attribute: d.attribute ?? "" };
    case "o2o":
      return { option: "o2o", qualifiers: d.qualifiers, name_attribute: d.name_attribute };
    case "pattern":
      return { option: "pattern", pattern: d.pattern };
    default:
      return null;
  }
};

const locationSetToConfig = (d: LocationSetDraft): DerivationConfig["vehicles"] => {
  switch (d.option) {
    case "locations":
      return { option: "locations", locations: d.locations };
    case "table":
      return { option: "table", table: d.table ?? "", location_column: d.location_column ?? "", flag_column: d.flag_column };
    case "attribute_values":
      return { option: "attribute_values", attribute: d.attribute ?? "", values: d.values };
    case "object_types":
      return { option: "object_types", object_types: d.object_types };
    default:
      return null;
  }
};

const objectSetToConfig = (d: ObjectSetDraft) => {
  switch (d.option) {
    case "attribute_values":
      return { option: "attribute_values" as const, attribute: d.attribute ?? "", values: d.values };
    case "table":
      return { option: "table" as const, table: d.table ?? "", object_column: d.object_column ?? "" };
    default:
      return null;
  }
};

const rolesToConfig = (d: RolesDraft): DerivationConfig["transformation_roles"] => {
  switch (d.option) {
    case "qualifiers":
      return { option: "qualifiers", consumed_qualifiers: d.consumed_qualifiers, produced_qualifiers: d.produced_qualifiers };
    case "table":
      return {
        option: "table",
        table: d.table ?? "",
        event_column: d.event_column ?? "",
        object_column: d.object_column ?? "",
        role_column: d.role_column ?? "",
        consumed_values: d.consumed_values,
        produced_values: d.produced_values,
      };
    case "parents":
      return { option: "parents", qualifiers: d.qualifiers, direction: d.direction };
    case "object_sets":
      return { option: "object_sets", produced: objectSetToConfig(d.produced), consumed: objectSetToConfig(d.consumed), consumption: d.consumption };
    case "first_last":
      return { option: "first_last" };
    case "frequency":
      return { option: "frequency", threshold: d.threshold };
    default:
      return null;
  }
};

/** null (P = T) unless the user selected events or switched the transformation events off. */
const processingToConfig = (d: ProcessingDraft): DerivationConfig["processing_operations"] => {
  const selection = eventsToConfig(d);
  if (!selection && d.include_transformations) return null;
  return { selection, include_transformations: d.include_transformations };
};

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
  transformation_events: DERIVES_T.includes(d.transformation_roles.option) ? null : eventsToConfig(d.transformation_events),
  transformation_roles: rolesToConfig(d.transformation_roles),
  target_locations: locationsToConfig(d.target_locations) as DerivationConfig["target_locations"],
  pickup_locations: locationsToConfig(d.pickup_locations),
  level: d.level,
  high_level_locations: highLevelToConfig(d.high_level_locations),
  vehicles: locationSetToConfig(d.vehicles),
  storage_units: locationSetToConfig(d.storage_units),
  processing_operations: processingToConfig(d.processing_operations),
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
  const roles = config.transformation_roles;
  if (roles) {
    const sets = roles as { produced?: Partial<ObjectSetDraft> | null; consumed?: Partial<ObjectSetDraft> | null };
    draft.transformation_roles = {
      ...emptyRoles(),
      ...roles,
      produced: { ...emptyObjectSet(), ...(sets.produced ?? {}) },
      consumed: { ...emptyObjectSet(), ...(sets.consumed ?? {}) },
    } as RolesDraft;
  }
  draft.target_locations = { ...emptyLocations("attribute"), ...config.target_locations } as LocationsDraft;
  draft.pickup_locations = config.pickup_locations
    ? ({ ...emptyLocations("attribute"), ...config.pickup_locations } as LocationsDraft)
    : emptyLocations("none");
  draft.level = (config.level ?? 3) as Level;
  if (config.high_level_locations) draft.high_level_locations = { ...emptyHighLevel(), ...config.high_level_locations } as HighLevelDraft;
  if (config.vehicles) draft.vehicles = { ...emptyLocationSet(), ...config.vehicles } as LocationSetDraft;
  if (config.storage_units) draft.storage_units = { ...emptyLocationSet(), ...config.storage_units } as LocationSetDraft;
  const processing = config.processing_operations;
  if (processing)
    draft.processing_operations = {
      ...emptyEvents("none"),
      ...(processing.selection ?? {}),
      include_transformations: processing.include_transformations ?? true,
    } as ProcessingDraft;
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
  const r = d.transformation_roles;
  if (!DERIVES_T.includes(r.option)) events("Transformation events", d.transformation_events);
  if (NEEDS_T.includes(r.option) && d.transformation_events.option === "none")
    missing.push("Consumed and produced: this option needs the transformation events.");
  if (r.option === "qualifiers" && !(r.consumed_qualifiers.length || r.produced_qualifiers.length))
    missing.push("Consumed and produced: select consumed and/or produced qualifiers.");
  if (r.option === "table" && !(r.table && r.event_column && r.object_column && r.role_column))
    missing.push("Consumed and produced: select a table and its event, object and role columns.");
  if (r.option === "parents" && !r.qualifiers.length) missing.push("Consumed and produced: select o2o qualifiers.");
  if (r.option === "object_sets") {
    for (const [name, s] of [["produced", r.produced], ["consumed", r.consumed]] as const) {
      if (s.option === "attribute_values" && !(s.attribute && s.values.length)) missing.push(`Consumed and produced: ${name} objects need an attribute and values.`);
      if (s.option === "table" && !(s.table && s.object_column)) missing.push(`Consumed and produced: ${name} objects need a table and its object column.`);
    }
  }
  const locations = (name: string, l: LocationsDraft) => {
    if (l.option === "attribute" && !l.attribute) missing.push(`${name}: select an event attribute.`);
    if (l.option === "qualifiers" && !l.qualifiers.length) missing.push(`${name}: select qualifiers.`);
    if (l.option === "table" && !(l.table && l.event_column && l.location_column))
      missing.push(`${name}: select a table, its event column and its location column.`);
  };
  locations("Target locations", d.target_locations);
  locations("Pickup locations", d.pickup_locations);
  events("Processing operations", d.processing_operations);
  const h = d.high_level_locations;
  if (h.option === "table" && !(h.table && h.location_column && h.high_level_column))
    missing.push("High-level locations: select a table, its location column and its high-level column.");
  if (h.option === "event_attributes" && !(h.low_attribute && h.high_attribute))
    missing.push("High-level locations: select the two event attributes.");
  if (h.option === "object_attribute" && !h.attribute) missing.push("High-level locations: select an object attribute.");
  if (h.option === "o2o" && !h.qualifiers.length) missing.push("High-level locations: select o2o qualifiers.");
  if (h.option === "pattern" && !h.pattern.trim()) missing.push("High-level locations: enter a pattern.");
  const sets = (name: string, v: LocationSetDraft) => {
    if (v.option === "locations" && !v.locations.length) missing.push(`${name}: pick locations.`);
    if (v.option === "table" && !(v.table && v.location_column)) missing.push(`${name}: select a table and its location column.`);
    if (v.option === "attribute_values" && !(v.attribute && v.values.length)) missing.push(`${name}: select an attribute and values.`);
    if (v.option === "object_types" && !v.object_types.length) missing.push(`${name}: select object types.`);
  };
  sets("Vehicles", d.vehicles);
  sets("Storage units", d.storage_units);
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
  roles: (
    <Lines
      lines={[
        "Which handling units each transformation event consumes and produces (cons, prod); also decides which events are transformation events.",
        <>
          <b>Default:</b> first/last timestamps if transformation events are given, otherwise there are none.
        </>,
        <>
          <b>e2o qualifiers:</b> qualifiers meaning consumed and produced; the transformation events are the events with such a handling unit.
        </>,
        <>
          <b>table:</b> one row per event, handling unit and role; transformation events from the input above, or the table's events.
        </>,
        <>
          <b>parents (o2o):</b> a handling unit starting at a transformation event is produced from its parents involved in it; a
          handling unit ending at one is consumed once all its children have started.
        </>,
        <>
          <b>produced/consumed objects:</b> the handling units created and consumed in the log; consumed at their last event (final)
          or at every transformation event they are involved in (partial).
        </>,
        <>
          <b>first/last timestamps:</b> produced are the handling units starting at the event, consumed those ending there.
        </>,
        <>
          <b>frequency:</b> no input needed: an activity counts as producing (consuming) if it is at least this share of the first
          (last) events of a handling-unit type; its first (last) events become transformation events.
        </>,
        "First and last events: at equal timestamps, selected processing operations first, then the smallest event id.",
        "Events without any consumed or produced handling unit are not transformation events (AS-T1); violations of AS-T2 to AS-T4 are reported.",
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
  highLevel: (
    <Lines
      lines={[
        "Groups locations into high-level locations, e.g. bays A1 and A2 into hall A (agg).",
        "Partial mappings are fine: a location without a high-level location is its own high-level location.",
        "A location with two different high-level locations is a blocking error; an unmapped location whose name is a high-level location of others is flagged (F6).",
        "Naming pattern: a regular expression with one group; the group is the high-level location, e.g. ^([A-Z]+) maps A1 to A.",
      ]}
    />
  ),
  vehicles: (
    <Lines
      lines={[
        "Locations that are vehicles, e.g. trucks or forklifts (V). Optional.",
        "Event attribute: the target locations of the events with the selected values are vehicles.",
        "A location that is both a vehicle and a storage unit is flagged (F10).",
      ]}
    />
  ),
  storage: (
    <Lines
      lines={[
        "Locations that are storage units, e.g. racks or buffers (W). Optional.",
        "Taking a handling unit out of a storage unit resets the waiting clock of the visits.",
      ]}
    />
  ),
  processing: (
    <Lines
      lines={[
        "Events at which a handling unit is actually processed (P), e.g. roll, cut, label. Optional.",
        "Default: the transformation events (none if there are none). Tick the box to add the transformation events to a selection.",
        "Events with the same timestamp are ordered movements first, then processing operations, then the rest (AS4); Level 3 uses this order.",
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
  const [rejected, setRejected] = useState<string | null>(null);
  const uploadFile = (file: File) => {
    setRejected(null);
    upload.mutate({ data: { file } });
  };
  return (
    <DropTarget accept={[".csv"]} onFile={uploadFile} onReject={(name) => setRejected(`${name} is not a CSV file`)}>
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
          <FileButton onChange={(file) => file && uploadFile(file)} accept=".csv,text/csv">
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
          {rejected && (
            <Text size="xs" c="red">
              {rejected}
            </Text>
          )}
        </Group>
        {selected && showPreview && <Preview table={selected} />}
      </Stack>
    </DropTarget>
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

/** High-level locations: table, two event attributes, location-object attribute, o2o relations, naming pattern. */
const HighLevelFields = ({
  value: d,
  onChange,
  tables,
  eventAttributes,
  objectAttributes,
  o2oQualifiers,
  hasObjects,
}: SectionProps<HighLevelDraft> & {
  eventAttributes: string[];
  objectAttributes: string[];
  o2oQualifiers: ValueCount[] | undefined;
  hasObjects: boolean;
}) => (
  <Stack gap={6}>
    <SegmentedControl
      size="xs"
      data={[
        { value: "none", label: "none" },
        { value: "table", label: "table" },
        { value: "event_attributes", label: "event attributes" },
        ...(hasObjects
          ? [
              { value: "object_attribute", label: "object attribute" },
              { value: "o2o", label: "o2o relation" },
            ]
          : []),
        { value: "pattern", label: "naming pattern" },
      ]}
      value={d.option}
      onChange={(option) => onChange({ ...d, option: option as HighLevelDraft["option"] })}
    />
    {d.option === "table" && (
      <TableColumns
        tables={tables}
        table={d.table}
        onTable={(table) => onChange({ ...d, table, location_column: null, high_level_column: null })}
        columns={[
          { label: "Location column", value: d.location_column, onChange: (location_column) => onChange({ ...d, location_column }) },
          { label: "High-level column", value: d.high_level_column, onChange: (high_level_column) => onChange({ ...d, high_level_column }) },
        ]}
      />
    )}
    {d.option === "event_attributes" && (
      <Group grow align="flex-start">
        <Select size="xs" label="Low-level location" data={eventAttributes} value={d.low_attribute} onChange={(low_attribute) => onChange({ ...d, low_attribute })} searchable />
        <Select size="xs" label="High-level location" data={eventAttributes} value={d.high_attribute} onChange={(high_attribute) => onChange({ ...d, high_attribute })} searchable />
      </Group>
    )}
    {d.option === "object_attribute" && (
      <Select
        size="xs"
        data={objectAttributes}
        value={d.attribute}
        onChange={(attribute) => onChange({ ...d, attribute })}
        placeholder="Select the attribute of the location objects"
        searchable
      />
    )}
    {d.option === "o2o" && (
      <Group grow align="flex-start">
        <CountPicker label="O2o qualifiers" data={o2oQualifiers} value={d.qualifiers} onChange={(q) => onChange({ ...d, qualifiers: q })} placeholder="e.g. part of" />
        <Select
          size="xs"
          label="High-level name"
          data={[{ value: "", label: "object id" }, ...objectAttributes.map((a) => ({ value: a, label: `attribute "${a}"` }))]}
          value={d.name_attribute ?? ""}
          onChange={(v) => onChange({ ...d, name_attribute: v || null })}
          allowDeselect={false}
        />
      </Group>
    )}
    {d.option === "pattern" && (
      <TextInput size="xs" value={d.pattern} onChange={(e) => onChange({ ...d, pattern: e.currentTarget.value })} placeholder="^([A-Z]+)" />
    )}
  </Stack>
);

/** A set of objects: values of an object attribute (typed in) or a table with an object column. */
const ObjectSetFields = ({
  label,
  value: d,
  onChange,
  tables,
  objectAttributes,
}: {
  label: string;
  value: ObjectSetDraft;
  onChange: (v: ObjectSetDraft) => void;
  tables: TableInfo[];
  objectAttributes: string[];
}) => (
  <Stack gap={4}>
    <Text size="xs" fw={500}>
      {label}
    </Text>
    <SegmentedControl
      size="xs"
      data={[
        { value: "none", label: "none" },
        { value: "attribute_values", label: "object attribute" },
        { value: "table", label: "table" },
      ]}
      value={d.option}
      onChange={(option) => onChange({ ...d, option: option as ObjectSetDraft["option"] })}
    />
    {d.option === "attribute_values" && (
      <Group grow align="flex-start">
        <Select size="xs" label="Object attribute" data={objectAttributes} value={d.attribute} onChange={(attribute) => onChange({ ...d, attribute })} searchable />
        <TagsInput size="xs" label="Values" value={d.values} onChange={(values) => onChange({ ...d, values })} placeholder="Type values" />
      </Group>
    )}
    {d.option === "table" && (
      <TableColumns
        tables={tables}
        table={d.table}
        onTable={(table) => onChange({ ...d, table, object_column: null })}
        columns={[{ label: "Object column", value: d.object_column, onChange: (object_column) => onChange({ ...d, object_column }) }]}
      />
    )}
  </Stack>
);

/** Consumed and produced handling units: options 1 to 6 of the Transformations concept. */
const RolesFields = ({
  value: d,
  onChange,
  tables,
  qualifiers,
  o2oQualifiers,
  objectAttributes,
}: {
  value: RolesDraft;
  onChange: (v: RolesDraft) => void;
  tables: TableInfo[];
  qualifiers: ValueCount[] | undefined;
  o2oQualifiers: ValueCount[] | undefined;
  objectAttributes: string[];
}) => (
  <Stack gap={6}>
    <Select
      size="xs"
      data={[
        { value: "default", label: "default (first/last timestamps of the transformation events)" },
        { value: "qualifiers", label: "e2o qualifiers" },
        { value: "table", label: "table" },
        { value: "parents", label: "parent relations (o2o)" },
        { value: "object_sets", label: "produced/consumed objects" },
        { value: "first_last", label: "first/last timestamps" },
        { value: "frequency", label: "frequency of first/last activities" },
      ]}
      value={d.option}
      onChange={(option) => onChange({ ...d, option: (option ?? "default") as RolesDraft["option"] })}
      allowDeselect={false}
    />
    {d.option === "qualifiers" && (
      <Group grow align="flex-start">
        <CountPicker label="Consumed" data={qualifiers} value={d.consumed_qualifiers} onChange={(consumed_qualifiers) => onChange({ ...d, consumed_qualifiers })} placeholder="Qualifiers" />
        <CountPicker label="Produced" data={qualifiers} value={d.produced_qualifiers} onChange={(produced_qualifiers) => onChange({ ...d, produced_qualifiers })} placeholder="Qualifiers" />
      </Group>
    )}
    {d.option === "table" && (
      <>
        <TableColumns
          tables={tables}
          table={d.table}
          onTable={(table) => onChange({ ...d, table, event_column: null, object_column: null, role_column: null })}
          columns={[
            { label: "Event column", value: d.event_column, onChange: (event_column) => onChange({ ...d, event_column }) },
            { label: "Object column", value: d.object_column, onChange: (object_column) => onChange({ ...d, object_column }) },
            { label: "Role column", value: d.role_column, onChange: (role_column) => onChange({ ...d, role_column }) },
          ]}
        />
        <Group grow align="flex-start">
          <TagsInput size="xs" label='Values meaning "consumed"' value={d.consumed_values} onChange={(consumed_values) => onChange({ ...d, consumed_values })} />
          <TagsInput size="xs" label='Values meaning "produced"' value={d.produced_values} onChange={(produced_values) => onChange({ ...d, produced_values })} />
        </Group>
      </>
    )}
    {d.option === "parents" && (
      <Group grow align="flex-start">
        <CountPicker label="o2o qualifiers" data={o2oQualifiers} value={d.qualifiers} onChange={(q) => onChange({ ...d, qualifiers: q })} placeholder="Select qualifiers" />
        <Select
          size="xs"
          label="Meaning"
          data={[
            { value: "child_of", label: "source is a child of target" },
            { value: "parent_of", label: "source is a parent of target" },
          ]}
          value={d.direction}
          onChange={(direction) => onChange({ ...d, direction: (direction ?? "child_of") as RolesDraft["direction"] })}
          allowDeselect={false}
        />
      </Group>
    )}
    {d.option === "object_sets" && (
      <>
        <ObjectSetFields label="Produced objects" value={d.produced} onChange={(produced) => onChange({ ...d, produced })} tables={tables} objectAttributes={objectAttributes} />
        <ObjectSetFields label="Consumed objects" value={d.consumed} onChange={(consumed) => onChange({ ...d, consumed })} tables={tables} objectAttributes={objectAttributes} />
        <SegmentedControl
          size="xs"
          data={[
            { value: "final", label: "consumed at last event (final)" },
            { value: "partial", label: "at every involvement (partial)" },
          ]}
          value={d.consumption}
          onChange={(consumption) => onChange({ ...d, consumption: consumption as RolesDraft["consumption"] })}
        />
      </>
    )}
    {d.option === "frequency" && (
      <NumberInput
        size="xs"
        label="Threshold τ (share of the first/last events of a handling-unit type)"
        min={0}
        max={1}
        step={0.05}
        decimalScale={2}
        value={d.threshold}
        onChange={(v) => onChange({ ...d, threshold: typeof v === "number" ? v : Number(v) || 0 })}
      />
    )}
  </Stack>
);

/** Vehicles or storage units: locations (picked or typed in), table, event attribute, location-object types. */
const LocationSetFields = ({
  value: d,
  onChange,
  ocelId,
  tables,
  eventAttributes,
  locations,
  hasObjects,
  valueLabel,
}: SectionProps<LocationSetDraft> & {
  eventAttributes: string[];
  locations: LocationOptions | undefined;
  hasObjects: boolean;
  valueLabel: string;
}) => (
  <Stack gap={6}>
    <SegmentedControl
      size="xs"
      data={[
        { value: "none", label: "none" },
        { value: "locations", label: "locations" },
        { value: "table", label: "table" },
        { value: "attribute_values", label: "event attribute" },
        ...(hasObjects ? [{ value: "object_types", label: "object types" }] : []),
      ]}
      value={d.option}
      onChange={(option) => onChange({ ...d, option: option as LocationSetDraft["option"] })}
    />
    {d.option === "locations" && (
      <TagsInput
        size="xs"
        data={(locations?.locations ?? []).map((v) => v.value)}
        value={d.locations}
        onChange={(picked) => onChange({ ...d, locations: picked })}
        placeholder="Pick or type locations"
        clearable
      />
    )}
    {d.option === "table" && (
      <TableColumns
        tables={tables}
        table={d.table}
        onTable={(table) => onChange({ ...d, table, location_column: null, flag_column: null })}
        columns={[
          { label: "Location column", value: d.location_column, onChange: (location_column) => onChange({ ...d, location_column }) },
          { label: "True/false column (optional)", value: d.flag_column, onChange: (flag_column) => onChange({ ...d, flag_column }) },
        ]}
      />
    )}
    {d.option === "attribute_values" && (
      <Group grow align="flex-start">
        <Select size="xs" label="Event attribute" data={eventAttributes} value={d.attribute} onChange={(attribute) => onChange({ ...d, attribute, values: [] })} searchable />
        <AttributeValuePicker ocelId={ocelId} attribute={d.attribute} value={d.values} onChange={(values) => onChange({ ...d, values })} label={valueLabel} />
      </Group>
    )}
    {d.option === "object_types" && (
      <CountPicker
        data={locations?.location_object_types}
        value={d.object_types}
        onChange={(object_types) => onChange({ ...d, object_types })}
        placeholder="Select object types of the location objects"
      />
    )}
  </Stack>
);

/** Downloads a CSV with one row per location and empty columns high_level, is_vehicle, is_storage. */
const downloadTemplate = (locations: LocationOptions | undefined) => {
  const escape = (v: string) => (/[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v);
  const rows = (locations?.locations ?? []).map((v) => v.value).sort();
  const csv = ["location,high_level,is_vehicle,is_storage", ...rows.map((r) => `${escape(r)},,,`)].join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "locations.csv";
  link.click();
  URL.revokeObjectURL(url);
};

/** The locations L of the current target and pickup inputs (for pickers and the template), refreshed on change. */
const useFormLocations = (ocelId: string, draft: ConfigDraft): LocationOptions | undefined => {
  const { mutate, data } = useGetLocations();
  // Only complete location inputs are sent (an incomplete one would just report what is missing).
  const complete = (l: LocationsDraft) =>
    (l.option === "attribute" && !!l.attribute) ||
    (l.option === "qualifiers" && l.qualifiers.length > 0) ||
    (l.option === "table" && !!(l.table && l.event_column && l.location_column));
  const target = complete(draft.target_locations) ? locationsToConfig(draft.target_locations) : null;
  const pickup = complete(draft.pickup_locations) ? locationsToConfig(draft.pickup_locations) : null;
  const key = JSON.stringify([target, pickup]);
  useEffect(() => {
    if (target) mutate({ ocelId, data: { target_locations: target, pickup_locations: pickup } });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ocelId, key]);
  return target ? data : undefined;
};

// endregion
// region Download and load

/** Saves a configuration as location-based-ocpm-configuration.json (form and folded header). */

export const downloadJson = (config: DerivationConfig) => {
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
  const locations = useFormLocations(ocelId, draft);
  const hasObjects = draft.target_locations.option === "qualifiers" || draft.pickup_locations.option === "qualifiers";

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
          <DropTarget
            accept={[".json"]}
            onFile={load}
            onReject={(name) => setLoadError(`${name} is not a configuration file (.json)`)}
          >
            <FileButton onChange={load} accept=".json,application/json">
              {(props) => (
                <Button {...props} size="xs" variant="default" leftSection={<FolderOpenIcon size={14} />}>
                  Load configuration
                </Button>
              )}
            </FileButton>
          </DropTarget>
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
          {DERIVES_T.includes(draft.transformation_roles.option) ? (
            <Text size="xs" c="dimmed">
              Determined by the consumed and produced handling units below.
            </Text>
          ) : (
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
          )}
          <Group gap={6} mt={4}>
            <Text size="xs" fw={600}>
              Consumed and produced handling units
            </Text>
            <Tooltip label={INFO.roles} multiline w={420} withArrow position="top-start">
              <InfoIcon size={12} style={{ cursor: "help", opacity: 0.6 }} aria-label="About consumed and produced handling units" />
            </Tooltip>
          </Group>
          <RolesFields
            value={draft.transformation_roles}
            onChange={set("transformation_roles")}
            tables={tables}
            qualifiers={options?.qualifiers}
            o2oQualifiers={options?.o2o_qualifiers}
            objectAttributes={options?.object_attributes ?? []}
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

      <Group justify="space-between">
        <Text fw={600}>Location context (optional)</Text>
        <Tooltip
          label="A CSV with one row per location and empty columns high_level, is_vehicle, is_storage. Fill it in, upload it once and pick it in the three inputs below."
          multiline
          w={320}
        >
          <Button
            size="compact-xs"
            variant="subtle"
            leftSection={<DownloadIcon size={12} />}
            disabled={!locations?.locations?.length}
            onClick={() => downloadTemplate(locations)}
          >
            Location template
          </Button>
        </Tooltip>
      </Group>
      {locations?.problems?.length ? (
        <Text size="xs" c="dimmed">
          Locations cannot be listed yet: {locations.problems.join(" ")}
        </Text>
      ) : null}
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="lg">
        <Section title="High-level locations" info={INFO.highLevel} hint="Without them, every location is its own high-level location.">
          <HighLevelFields
            value={draft.high_level_locations}
            onChange={set("high_level_locations")}
            ocelId={ocelId}
            tables={tables}
            eventAttributes={eventAttributes}
            objectAttributes={options?.object_attributes ?? []}
            o2oQualifiers={options?.o2o_qualifiers}
            hasObjects={hasObjects}
          />
        </Section>
        <Section title="Processing operations" info={INFO.processing} hint="Default: the transformation events.">
          <EventSetFields
            value={draft.processing_operations}
            onChange={(v) => set("processing_operations")({ ...draft.processing_operations, ...v })}
            ocelId={ocelId}
            tables={tables}
            activities={options?.activities}
            qualifiers={options?.qualifiers}
            eventAttributes={eventAttributes}
            optional
            valueLabel='Values meaning "processing"'
          />
          <Switch
            size="xs"
            label="and all transformation events"
            checked={draft.processing_operations.include_transformations}
            onChange={(e) => set("processing_operations")({ ...draft.processing_operations, include_transformations: e.currentTarget.checked })}
          />
        </Section>
        <Section title="Vehicles" info={INFO.vehicles} hint="Locations that are vehicles.">
          <LocationSetFields
            value={draft.vehicles}
            onChange={set("vehicles")}
            ocelId={ocelId}
            tables={tables}
            eventAttributes={eventAttributes}
            locations={locations}
            hasObjects={hasObjects}
            valueLabel='Values whose targets are vehicles'
          />
        </Section>
        <Section title="Storage units" info={INFO.storage} hint="Locations that are storage units.">
          <LocationSetFields
            value={draft.storage_units}
            onChange={set("storage_units")}
            ocelId={ocelId}
            tables={tables}
            eventAttributes={eventAttributes}
            locations={locations}
            hasObjects={hasObjects}
            valueLabel='Values whose targets are storage units'
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
