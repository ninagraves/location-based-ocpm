// The settings sidebar of the directly-follows graph page: every setting of the page is here (and only here).
// Each setting is documented in docs/pages/directly-follows-graph.md, section "Settings".
import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Card,
  Checkbox,
  Collapse,
  Divider,
  Group,
  ScrollArea,
  SegmentedControl,
  Slider,
  Stack,
  Switch,
  Text,
  TextInput,
  Tooltip,
} from "@mantine/core";
import { ChevronDownIcon, ChevronRightIcon, InfoIcon, RotateCcwIcon, SearchIcon } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import type { DfgActivityOption, DfgObjectType, DfgRequest } from "../api/locationBasedOcpm";
import type { ArcLabel, Direction } from "../lib/dfgLayout";
import { num } from "../lib/format";
import { UI } from "../lib/palette";
import { useScheme } from "./plots";

/** The page's settings. `objectTypes` null = the object types with handling units. */
export type DfgState = {
  objectTypes: string[] | null;
  /** General path threshold (percent) for every type without an own one. */
  pathThreshold: number;
  /** General arc threshold (percent) for every type without an own one. */
  arcThreshold: number;
  /** Own thresholds per object type (kept while the type is unselected). */
  own: Record<string, { path?: number; arc?: number }>;
  /** Deselected activities. */
  excluded: string[];
  arcLabel: ArcLabel;
  direction: Direction;
  compact: boolean;
};

/** Defaults (Nina, 2026-11-14): paths 30 %, arcs 10 %, handling-unit types, all activities. */
export const DEFAULT_STATE: DfgState = {
  objectTypes: null,
  pathThreshold: 30,
  arcThreshold: 10,
  own: {},
  excluded: [],
  arcLabel: "count",
  direction: "RIGHT",
  compact: false,
};

/** The backend request of a state. */
export const toRequest = (state: DfgState): DfgRequest => ({
  object_types: state.objectTypes,
  path_threshold: state.pathThreshold,
  arc_threshold: state.arcThreshold,
  type_thresholds: Object.entries(state.own)
    .filter(([, t]) => t.path !== undefined || t.arc !== undefined)
    .map(([object_type, t]) => ({ object_type, path_threshold: t.path ?? null, arc_threshold: t.arc ?? null })),
  excluded_activities: state.excluded,
});

/** Hover texts of the settings (short versions of the documentation). */
export const INFO = {
  reset: "Sets every setting of this page back to its default.",
  general:
    "General thresholds: apply to every object type that has no own value (set in the type's unfold). Types with own values are marked in the list.",
  paths:
    "Path threshold: keeps the most frequent paths (activity sequences of the objects) of a type until they cover at least this share of its objects. Only these objects' traces are used for everything else. 100 % keeps all.",
  arcs: "Arc threshold: keeps this share of the type's directly-follows relations between activities, the most frequent first (rounded up). Arcs from the start and to the end are always kept. 100 % keeps all.",
  objectTypes:
    "Checked object types are drawn with their directly-follows arcs, start and end nodes. Unchecked object types that are involved in the shown events appear only as circles on the activity nodes. Default: the object types of the handling units. Unfold a type for its own thresholds.",
  activities:
    "Activities by number of events in the log. Checked: all activities on an included trace. Unchecking removes the activity and every arc touching it from the graph (no new arcs between its neighbours). Greyed: not on an included trace.",
  arcLabel: "What the number on an arc counts: traversals (an object repeating the arc counts each time) or distinct objects.",
  direction: "Direction of the layout: from left to right or from top to bottom.",
  compact: "Less white space between nodes and arcs, e.g. to export the whole graph as a figure.",
};

/** Heading with a hover text. */
const Heading = ({ children, info }: { children: ReactNode; info: string }) => (
  <Group gap={4} wrap="nowrap">
    <Text size="sm" fw={600}>{children}</Text>
    <Tooltip label={info} multiline w={300} withinPortal>
      <InfoIcon size={13} style={{ opacity: 0.6, flexShrink: 0 }} />
    </Tooltip>
  </Group>
);

/** Colour swatch of an object type: a short line (selected, drawn as arcs) or a circle (not selected). */
export const Swatch = ({ colour, circle }: { colour?: string; circle?: boolean }) => (
  <Box
    style={
      circle
        ? { width: 9, height: 9, borderRadius: "50%", background: colour, flexShrink: 0 }
        : { width: 14, height: 4, borderRadius: 2, background: colour, flexShrink: 0 }
    }
  />
);

/** A labelled 0-100 % slider that only reports its value when released (no request per step while dragging). */
const PercentSlider = ({
  label,
  info,
  value,
  onCommit,
  note,
}: {
  label: string;
  info: string;
  value: number;
  onCommit: (v: number) => void;
  note?: ReactNode;
}) => {
  const [local, setLocal] = useState(value);
  useEffect(() => setLocal(value), [value]);
  return (
    <Stack gap={2}>
      <Group justify="space-between" gap={4} wrap="nowrap">
        <Heading info={info}>{label} {local} %</Heading>
        {note && <Text size="xs" c="dimmed">{note}</Text>}
      </Group>
      <Slider aria-label={label} size="sm" min={0} max={100} step={1} value={local} onChange={setLocal} onChangeEnd={onCommit} label={(v) => `${v} %`} />
    </Stack>
  );
};

/** Search box of a list. */
const Search = ({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) => (
  <TextInput size="xs" placeholder={placeholder} value={value} onChange={(e) => onChange(e.currentTarget.value)} leftSection={<SearchIcon size={12} />} />
);

/** One object type in the list: checkbox, swatch, count, HU badge, mark for own thresholds, and the unfold. */
const TypeRow = ({
  type,
  colour,
  state,
  setState,
  selectedTypes,
}: {
  type: DfgObjectType;
  colour?: string;
  state: DfgState;
  setState: (update: (s: DfgState) => DfgState) => void;
  selectedTypes: string[];
}) => {
  const [open, setOpen] = useState(false);
  const scheme = useScheme();
  const own = state.own[type.object_type] ?? {};
  const custom = own.path !== undefined || own.arc !== undefined;
  const setOwn = (change: { path?: number; arc?: number }) =>
    setState((s) => ({ ...s, own: { ...s.own, [type.object_type]: { ...s.own[type.object_type], ...change } } }));
  const toggle = (checked: boolean) =>
    setState((s) => ({
      ...s,
      objectTypes: checked ? [...selectedTypes, type.object_type] : selectedTypes.filter((t) => t !== type.object_type),
    }));
  return (
    <Stack gap={4}>
      <Group gap={6} wrap="nowrap" justify="space-between">
        <Checkbox
          size="xs"
          checked={type.selected}
          onChange={(e) => toggle(e.currentTarget.checked)}
          label={
            <Group gap={5} wrap="nowrap">
              <Swatch colour={colour} circle={!type.selected} />
              <Text size="sm">{type.object_type}</Text>
              <Text size="xs" c="dimmed">({num(type.objects)})</Text>
              {type.handling_units && <Badge size="xs" variant="light">HU</Badge>}
              {custom && (
                <Tooltip label="Own thresholds, deviating from the general ones" withinPortal>
                  <Text size="xs" fw={600} style={{ color: UI[scheme].accent, whiteSpace: "nowrap" }}>
                    {own.path !== undefined ? `P ${own.path} %` : ""}
                    {own.path !== undefined && own.arc !== undefined ? " · " : ""}
                    {own.arc !== undefined ? `A ${own.arc} %` : ""}
                  </Text>
                </Tooltip>
              )}
            </Group>
          }
        />
        <ActionIcon size="sm" variant="subtle" color="gray" onClick={() => setOpen((o) => !o)} aria-label={`Thresholds of ${type.object_type}`}>
          {open ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}
        </ActionIcon>
      </Group>
      <Collapse expanded={open}>
        <Stack gap={6} pl={24} pb={6}>
          <PercentSlider
            label="Paths"
            info={INFO.paths}
            value={own.path ?? state.pathThreshold}
            onCommit={(v) => setOwn({ path: v })}
            note={type.selected ? `${num(type.kept_paths)} of ${num(type.paths)} paths · ${num(type.kept_objects)} objects` : undefined}
          />
          <PercentSlider
            label="Arcs"
            info={INFO.arcs}
            value={own.arc ?? state.arcThreshold}
            onCommit={(v) => setOwn({ arc: v })}
            note={type.selected ? `${num(type.kept_arcs)} of ${num(type.arcs)} arcs` : undefined}
          />
          {custom && (
            <Button size="compact-xs" variant="subtle" onClick={() => setOwn({ path: undefined, arc: undefined })}>
              Use the general thresholds
            </Button>
          )}
        </Stack>
      </Collapse>
    </Stack>
  );
};

/**
 * The sidebar: reset, general thresholds, object types (searchable, scrollable, each with an unfold for own
 * thresholds), activities (searchable, scrollable), and the display options.
 *
 * @param objectTypes All object types of the log with their state (from the last graph).
 * @param activityOptions All activities of the log, most events first.
 * @param colours Colour per object type.
 * @param state The settings; `setState` changes them (every change keeps the other settings).
 */
export const DfgSettings = ({
  objectTypes,
  activityOptions,
  colours,
  state,
  setState,
}: {
  objectTypes: DfgObjectType[];
  activityOptions: DfgActivityOption[];
  colours: Map<string, string>;
  state: DfgState;
  setState: (update: (s: DfgState) => DfgState) => void;
}) => {
  const [typeQuery, setTypeQuery] = useState("");
  const [activityQuery, setActivityQuery] = useState("");
  const selectedTypes = objectTypes.filter((t) => t.selected).map((t) => t.object_type);
  const matches = (text: string, query: string) => text.toLowerCase().includes(query.trim().toLowerCase());
  const excluded = new Set(state.excluded);
  const toggleActivity = (activity: string, checked: boolean) =>
    setState((s) => ({ ...s, excluded: checked ? s.excluded.filter((a) => a !== activity) : [...s.excluded, activity] }));

  return (
    <Card withBorder padding="sm">
      <Stack gap="sm">
        <Group justify="space-between">
          <Text size="sm" fw={700}>Settings</Text>
          <Tooltip label={INFO.reset} withinPortal>
            <Button size="xs" variant="default" leftSection={<RotateCcwIcon size={12} />} onClick={() => setState(() => DEFAULT_STATE)}>
              Reset to defaults
            </Button>
          </Tooltip>
        </Group>

        <Divider label="General thresholds" labelPosition="left" />
        <PercentSlider label="Paths" info={`${INFO.general} ${INFO.paths}`} value={state.pathThreshold} onCommit={(v) => setState((s) => ({ ...s, pathThreshold: v }))} />
        <PercentSlider label="Arcs" info={`${INFO.general} ${INFO.arcs}`} value={state.arcThreshold} onCommit={(v) => setState((s) => ({ ...s, arcThreshold: v }))} />

        <Divider label="Object types" labelPosition="left" />
        <Group justify="space-between" gap={4} wrap="nowrap">
          <Heading info={INFO.objectTypes}>{selectedTypes.length} of {objectTypes.length} selected</Heading>
        </Group>
        <Search value={typeQuery} onChange={setTypeQuery} placeholder="Search object types" />
        <ScrollArea.Autosize mah={300} type="auto" offsetScrollbars>
          <Stack gap={4}>
            {objectTypes
              .filter((t) => matches(t.object_type, typeQuery))
              .map((t) => (
                <TypeRow key={t.object_type} type={t} colour={colours.get(t.object_type)} state={state} setState={setState} selectedTypes={selectedTypes} />
              ))}
          </Stack>
        </ScrollArea.Autosize>

        <Divider label="Activities" labelPosition="left" />
        <Heading info={INFO.activities}>
          {activityOptions.filter((a) => a.on_included_trace && !excluded.has(a.activity)).length} of{" "}
          {activityOptions.filter((a) => a.on_included_trace).length} on included traces
        </Heading>
        <Search value={activityQuery} onChange={setActivityQuery} placeholder="Search activities" />
        <ScrollArea.Autosize mah={260} type="auto" offsetScrollbars>
          <Stack gap={4}>
            {activityOptions
              .filter((a) => matches(a.activity, activityQuery))
              .map((a) => (
                <Checkbox
                  key={a.activity}
                  size="xs"
                  disabled={!a.on_included_trace}
                  checked={a.on_included_trace && !excluded.has(a.activity)}
                  onChange={(e) => toggleActivity(a.activity, e.currentTarget.checked)}
                  label={
                    <Group gap={5} wrap="nowrap">
                      <Text size="sm">{a.activity}</Text>
                      <Text size="xs" c="dimmed">({num(a.log_events)})</Text>
                    </Group>
                  }
                />
              ))}
          </Stack>
        </ScrollArea.Autosize>

        <Divider label="Display" labelPosition="left" />
        <Heading info={INFO.arcLabel}>Arc labels</Heading>
        <SegmentedControl
          size="xs"
          value={state.arcLabel}
          onChange={(v) => setState((s) => ({ ...s, arcLabel: v as ArcLabel }))}
          data={[
            { value: "count", label: "Traversals" },
            { value: "objects", label: "Objects" },
          ]}
        />
        <Heading info={INFO.direction}>Direction</Heading>
        <SegmentedControl
          size="xs"
          value={state.direction}
          onChange={(v) => setState((s) => ({ ...s, direction: v as Direction }))}
          data={[
            { value: "RIGHT", label: "Left to right" },
            { value: "DOWN", label: "Top to bottom" },
          ]}
        />
        <Group gap={6}>
          <Switch size="xs" checked={state.compact} onChange={(e) => {
            const compact = e.currentTarget.checked;
            setState((s) => ({ ...s, compact }));
          }} label="Compact layout" />
          <Tooltip label={INFO.compact} multiline w={260} withinPortal>
            <InfoIcon size={13} style={{ opacity: 0.6 }} />
          </Tooltip>
        </Group>
      </Stack>
    </Card>
  );
};
