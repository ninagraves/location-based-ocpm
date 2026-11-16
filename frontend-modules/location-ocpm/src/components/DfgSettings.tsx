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
  NumberInput,
  ScrollArea,
  Slider,
  Stack,
  Switch,
  Text,
  TextInput,
  Tooltip,
} from "@mantine/core";
import { ChevronDownIcon, ChevronRightIcon, InfoIcon, PanelRightCloseIcon, SearchIcon, XIcon } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import type { DfgActivityOption, DfgActivityTypeOption, DfgObjectType, DfgRequest, DirectlyFollowsGraph } from "../api/locationBasedOcpm";
import type { ArcSettings } from "../lib/dfgArcs";
import type { ArcLabel, Direction } from "../lib/dfgLayout";
import { num } from "../lib/format";
import { UI } from "../lib/palette";
import { useScheme } from "./plots";

/** An arc, as the backend identifies it (null = start / end node). */
export type ArcKey = { object_type: string; source: string | null; target: string | null };

/** The page's settings. `objectTypes` null = the object types with handling units. */
export type DfgState = {
  objectTypes: string[] | null;
  /** General variant threshold (percent) for every type without an own one; null = the default (top 3 of every type). */
  variantThreshold: number | null;
  /** General arc threshold (percent) for every type without an own one. */
  arcThreshold: number;
  /** General arc count per type for every type without an own one; null = all arcs. */
  arcCount: number | null;
  /** Own values per object type (kept while the type is unselected). */
  own: Record<string, { variant?: number; arc?: number; count?: number }>;
  /** Selected activities per object type; a type that is missing has the default selection. */
  activities: Record<string, string[]>;
  /** Every arc lies on a path from start to end ("Stay connected"). */
  stayConnected: boolean;
  /** Arcs removed by hand (right click). */
  removed: ArcKey[];
  /** Deselected event categories (keys, e.g. "to_vehicle"); their events are removed from the traces first. */
  excludedCategories: string[];
  arcLabel: ArcLabel;
  direction: Direction;
  compact: boolean;
};

/**
 * Defaults (Nina, 2026-11-15): handling-unit types; per type its most frequent 40 % of activities (3 to 10);
 * variants: one threshold that keeps at least the top 3 of every type; arcs 100 %, all arcs; Stay connected on.
 */
export const DEFAULT_STATE: DfgState = {
  objectTypes: null,
  variantThreshold: null,
  arcThreshold: 100,
  arcCount: null,
  own: {},
  activities: {},
  stayConnected: true,
  removed: [],
  excludedCategories: [],
  arcLabel: "count",
  direction: "RIGHT",
  compact: false,
};

/**
 * The backend request of a state: only object types, event categories, variants and activities. The arc settings (arc threshold, arc
 * count, arcs removed by hand, Stay connected) are applied in the browser (`arcSettings`, lib/dfgArcs.ts), so that
 * they react without a request (Nina, 2026-11-15).
 */
export const toRequest = (state: DfgState): DfgRequest => ({
  object_types: state.objectTypes,
  variant_threshold: state.variantThreshold,
  type_thresholds: Object.entries(state.own)
    .filter(([, t]) => t.variant !== undefined)
    .map(([object_type, t]) => ({ object_type, variant_threshold: t.variant ?? null })),
  activities: state.activities,
  excluded_categories: state.excludedCategories,
});

/** The arc settings of a state, for `filterArcs` (own values of a type first, then the general ones). */
export const arcSettings = (state: DfgState): ArcSettings => ({
  threshold: (t) => state.own[t]?.arc ?? state.arcThreshold,
  count: (t) => state.own[t]?.count ?? state.arcCount,
  removed: state.removed,
  stayConnected: state.stayConnected,
});

/** True if two arcs are the same. */
const sameArc = (a: ArcKey, b: ArcKey) => a.object_type === b.object_type && a.source === b.source && a.target === b.target;

/** Adds an arc to the removed arcs (right click on the graph). */
export const removeArc = (state: DfgState, arc: ArcKey): DfgState =>
  state.removed.some((r) => sameArc(r, arc)) ? state : { ...state, removed: [...state.removed, arc] };

/** Hover texts of the settings (short versions of the documentation). */
export const INFO = {
  reset: "Sets every setting of this page back to its default, and restores the arcs removed by hand.",
  general:
    "General values: apply to every object type that has no own value (set in the type's unfold). Types with own values are marked in the list.",
  variants:
    "Variant threshold: keeps the most frequent variants (activity sequences of the objects, after removing deselected activities) of a type until they cover at least this share of its objects; equally frequent variants by their first occurrence in the log. Only these objects' traces are used for everything else. 100 % keeps all. Default: the smallest whole percentage that keeps at least the 3 most frequent variants of every selected type. Click the number to type a value (decimals allowed).",
  arcs: "Arcs (projection), the arc threshold: ranks all arcs of a type (start and end arcs included) by objects, then traversals, and keeps this share of them (rounded up), together with every arc as frequent as the last kept one. 100 % keeps all. Click the number to type a value (decimals allowed).",
  arcCount:
    "Arcs (display), the arc count: of the arcs left by Arcs (projection), shows the first N of every object type, ranked by objects, traversals, first occurrence, then name (exactly N, ties broken by this order). The number shows how many arcs are shown of how many.",
  stay: "Stay connected: every shown arc lies on a path from the start to the end of its object type. Arcs that Arcs (projection) or Arcs (display) removed are added back (dashed) where needed. It never adds arcs of removed variants, deselected activities or arcs removed by hand.",
  removed:
    "Arcs removed by hand (right click on an arc in the graph). While there are any, the sliders no longer describe the graph on their own (marked as manual). Click × to restore an arc.",
  objectTypes:
    "Checked object types are drawn with their directly-follows arcs, start and end nodes. Unchecked object types that are involved in the shown events appear only as circles on the activity nodes. Default: the object types of the handling units. Unfold a type for its own values.",
  categories:
    "Event categories: an event is removed from the traces (before anything else, like deselecting an activity) only when all categories it belongs to are deselected. Move to vehicle / storage: movements whose target location is a vehicle / storage unit; such an event is also a movement, so it stays until both Movements and its Move to chip are off. Events in no category are not affected by the chips (the activity selection still applies).",
  activities:
    "Activities by number of events that involve a handling unit (in brackets). The events of an unchecked activity are removed from the traces before anything else (as in Ocelescope): a trace a, b, c without b becomes a, c. Unfold an activity for its events per object type and to (de)select it for single selected types. Default per type: its most frequent 40 % of activities, at least 3 and at most 10. Upper part: activities on the included traces (the variants kept by the variant threshold). Lower part: the others, each with the smallest variant threshold that would include it (per type in the unfold).",
  outside:
    "Activities on no included trace: the number is the smallest variant threshold (of any selected type) at which they would be; unfold for each selected type. Without a number, no variant threshold helps: the activity is deselected, its events are removed by an event category, or only unselected types have it.",
  arcLabel: "What the number on an arc counts: traversals (an object repeating the arc counts each time) or distinct objects.",
  direction: "Direction of the layout: from left to right or from top to bottom.",
  compact: "Less white space between nodes and arcs, e.g. to export the whole graph as a figure.",
};

/** Heading with a hover text. */
const Heading = ({ children, info }: { children: ReactNode; info: string }) => (
  <Group gap={4} wrap="nowrap">
    <Text size="xs" fw={600}>{children}</Text>
    <Tooltip label={info} multiline w={300} withinPortal>
      <InfoIcon size={12} style={{ opacity: 0.6, flexShrink: 0 }} />
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

/**
 * A labelled 0-100 % slider whose value can also be typed (decimals allowed). Both only report their value when
 * the slider is released or the typed value is confirmed (Enter or leaving the field), not per step.
 *
 * @param value The current value; null = automatic (shown as `autoText`, the slider then shows `autoValue`).
 * @param onCommit Called with the new value.
 * @param onAuto If given and the value is not automatic: a button to return to the automatic value.
 */
const PercentSlider = ({
  label,
  info,
  value,
  onCommit,
  note,
  autoText,
  autoValue,
  onAuto,
}: {
  label: string;
  info: string;
  value: number | null;
  onCommit: (v: number) => void;
  note?: ReactNode;
  autoText?: string;
  autoValue?: number;
  onAuto?: () => void;
}) => {
  const [local, setLocal] = useState<number | null>(value);
  const [typed, setTyped] = useState<string | number>(value ?? "");
  useEffect(() => {
    setLocal(value);
    setTyped(value ?? "");
  }, [value]);
  const commitTyped = () => {
    const v = typeof typed === "number" ? typed : Number.parseFloat(String(typed).replace(",", "."));
    if (Number.isFinite(v)) onCommit(Math.min(100, Math.max(0, Math.round(v * 100) / 100)));
    else setTyped(value ?? "");
  };
  return (
    <Stack gap={0}>
      <Group justify="space-between" gap={4} wrap="nowrap">
        <Group gap={4} wrap="nowrap">
          <Heading info={info}>{label}</Heading>
          <NumberInput
            aria-label={`${label} in percent`}
            size="xs"
            variant="unstyled"
            w={64}
            min={0}
            max={100}
            decimalScale={2}
            hideControls
            suffix=" %"
            placeholder={autoText ? (autoValue !== undefined ? `${autoValue} %` : "auto") : undefined}
            value={typed}
            onChange={setTyped}
            onBlur={commitTyped}
            onKeyDown={(e) => e.key === "Enter" && (e.currentTarget as HTMLInputElement).blur()}
            styles={{ input: { fontWeight: 600, fontSize: 12, height: 20, minHeight: 20, borderBottom: "1px dashed var(--mantine-color-default-border)" } }}
          />
          {local === null && autoText && <Text size="xs" c="dimmed">{autoText}</Text>}
          {local !== null && onAuto && (
            <Button size="compact-xs" variant="subtle" px={4} onClick={onAuto}>
              auto
            </Button>
          )}
        </Group>
        {note && <Text size="xs" c="dimmed">{note}</Text>}
      </Group>
      <Slider
        aria-label={label}
        size="xs"
        min={0}
        max={100}
        step={1}
        value={local ?? autoValue ?? 0}
        color={local === null ? "gray" : undefined}
        // Automatic without a value to show: no thumb (clicking the track sets a value).
        styles={local === null && autoValue === undefined ? { thumb: { display: "none" }, bar: { display: "none" } } : undefined}
        onChange={setLocal}
        onChangeEnd={onCommit}
        label={(v) => `${v} %`}
      />
    </Stack>
  );
};

/**
 * A slider for a number of arcs (0 to `max`) that shows "shown of total arcs" instead of a percentage; the value can
 * also be typed. null = all arcs (the slider is at `max`).
 *
 * @param value The current value; null = all.
 * @param max The largest useful value (the most arcs of one type).
 * @param shown, total Arcs shown and arcs left by the arc threshold (for the note).
 * @param onCommit Called with the new value (null when set to `max` or more, i.e. all).
 */
const CountSlider = ({
  label,
  info,
  value,
  max,
  shown,
  total,
  onCommit,
}: {
  label: string;
  info: string;
  value: number | null;
  max: number;
  shown: number;
  total: number;
  onCommit: (v: number | null) => void;
}) => {
  const top = Math.max(max, 1);
  const [local, setLocal] = useState<number>(value ?? top);
  const [typed, setTyped] = useState<string | number>(value ?? "");
  useEffect(() => {
    setLocal(value ?? top);
    setTyped(value ?? "");
  }, [value, top]);
  const commit = (v: number) => onCommit(v >= top ? null : Math.max(0, Math.round(v)));
  const commitTyped = () => {
    if (String(typed).trim() === "") return onCommit(null); // empty = all arcs
    const v = typeof typed === "number" ? typed : Number.parseInt(String(typed), 10);
    if (Number.isFinite(v)) commit(v);
    else setTyped(value ?? "");
  };
  return (
    <Stack gap={0}>
      <Group justify="space-between" gap={4} wrap="nowrap">
        <Group gap={4} wrap="nowrap">
          <Heading info={info}>{label}</Heading>
          <NumberInput
            aria-label={`${label} per object type`}
            size="xs"
            variant="unstyled"
            w={44}
            min={0}
            allowDecimal={false}
            hideControls
            placeholder="all"
            value={typed}
            onChange={setTyped}
            onBlur={commitTyped}
            onKeyDown={(e) => e.key === "Enter" && (e.currentTarget as HTMLInputElement).blur()}
            styles={{ input: { fontWeight: 600, fontSize: 12, height: 20, minHeight: 20, borderBottom: "1px dashed var(--mantine-color-default-border)" } }}
          />
          <Text size="xs" c="dimmed">per type</Text>
        </Group>
        <Text size="xs" c="dimmed">{num(shown)} of {num(total)} arcs</Text>
      </Group>
      <Slider aria-label={label} size="xs" min={0} max={top} step={1} value={local} onChange={setLocal} onChangeEnd={commit} label={(v) => `${v} arcs`} />
    </Stack>
  );
};

/** Search box of a list. */
const Search = ({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) => (
  <TextInput size="xs" placeholder={placeholder} value={value} onChange={(e) => onChange(e.currentTarget.value)} leftSection={<SearchIcon size={12} />} />
);

/** Mark "manual" next to slider headings while arcs are removed by hand (Nina, 2026-11-15). */
const Manual = ({ on }: { on: boolean }) =>
  on ? (
    <Tooltip label={INFO.removed} multiline w={280} withinPortal>
      <Badge size="xs" variant="light" color="pink">manual</Badge>
    </Tooltip>
  ) : null;

/** One object type in the list: checkbox, swatch, count, HU badge, mark for own values, and the unfold. */
const TypeRow = ({
  type,
  colour,
  state,
  setState,
  selectedTypes,
  arcCountMax,
  variantDefault,
}: {
  type: DfgObjectType;
  colour?: string;
  state: DfgState;
  setState: (update: (s: DfgState) => DfgState) => void;
  selectedTypes: string[];
  arcCountMax: number;
  variantDefault: number;
}) => {
  const [open, setOpen] = useState(false);
  const scheme = useScheme();
  const own = state.own[type.object_type] ?? {};
  const marks = [
    own.variant !== undefined ? `V ${own.variant} %` : "",
    own.arc !== undefined ? `A ${own.arc} %` : "",
    own.count !== undefined ? `N ${own.count}` : "",
  ].filter(Boolean);
  const setOwn = (change: { variant?: number; arc?: number; count?: number }) =>
    setState((s) => ({ ...s, own: { ...s.own, [type.object_type]: { ...s.own[type.object_type], ...change } } }));
  const toggle = (checked: boolean) =>
    setState((s) => ({
      ...s,
      objectTypes: checked ? [...selectedTypes, type.object_type] : selectedTypes.filter((t) => t !== type.object_type),
    }));
  return (
    <Stack gap={2}>
      <Group gap={6} wrap="nowrap" justify="space-between">
        <Checkbox
          size="xs"
          checked={type.selected}
          onChange={(e) => toggle(e.currentTarget.checked)}
          label={
            <Group gap={5} wrap="nowrap">
              <Swatch colour={colour} circle={!type.selected} />
              <Text size="xs">{type.object_type}</Text>
              <Text size="xs" c="dimmed">({num(type.objects)})</Text>
              {type.handling_units && <Badge size="xs" variant="light">HU</Badge>}
              {marks.length > 0 && (
                <Tooltip label="Own values, deviating from the general ones" withinPortal>
                  <Text size="xs" fw={600} style={{ color: UI[scheme].accent, whiteSpace: "nowrap" }}>
                    {marks.join(" · ")}
                  </Text>
                </Tooltip>
              )}
            </Group>
          }
        />
        <ActionIcon size="xs" variant="subtle" color="gray" onClick={() => setOpen((o) => !o)} aria-label={`Settings of ${type.object_type}`}>
          {open ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}
        </ActionIcon>
      </Group>
      <Collapse expanded={open}>
        <Stack gap={4} pl={22} pb={4}>
          <PercentSlider
            label="Variants"
            info={INFO.variants}
            value={own.variant ?? state.variantThreshold}
            autoText="default"
            autoValue={type.selected ? type.variant_threshold : variantDefault}
            onCommit={(v) => setOwn({ variant: v })}
            note={type.selected ? `${num(type.kept_variants)} of ${num(type.variants)} variants · ${num(type.kept_objects)} objects` : undefined}
          />
          <PercentSlider
            label="Arcs (projection)"
            info={INFO.arcs}
            value={own.arc ?? state.arcThreshold}
            onCommit={(v) => setOwn({ arc: v })}
            note={type.selected ? `${num(type.threshold_arcs)} of ${num(type.arcs)} arcs` : undefined}
          />
          <CountSlider
            label="Arcs (display)"
            info={INFO.arcCount}
            value={own.count ?? state.arcCount}
            max={type.selected ? (type.threshold_arcs ?? 0) : arcCountMax}
            shown={type.shown_arcs ?? 0}
            total={type.threshold_arcs ?? 0}
            onCommit={(v) => setOwn({ count: v ?? Math.max(type.threshold_arcs ?? 0, arcCountMax) })}
          />
          {marks.length > 0 && (
            <Button size="compact-xs" variant="subtle" onClick={() => setOwn({ variant: undefined, arc: undefined, count: undefined })}>
              Use the general values
            </Button>
          )}
        </Stack>
      </Collapse>
    </Stack>
  );
};

/**
 * Badge letter of each event category, as in the notation of the concept: M movements, V to a vehicle, W to a storage
 * unit, P processing operations, T transformations (Nina, 2026-11-15: small, single letters).
 */
const CATEGORY_BADGE: Record<string, { letter: string; long: string }> = {
  movement: { letter: "M", long: "movements" },
  to_vehicle: { letter: "V", long: "movements to a vehicle" },
  to_storage: { letter: "W", long: "movements to a storage unit" },
  processing: { letter: "P", long: "processing operations" },
  transformation: { letter: "T", long: "transformations" },
};

/**
 * Small single-letter badges of the event categories of an activity's events, in the order of `CATEGORY_BADGE`; a
 * letter is underlined (dotted) if only some of the events are in the category. The hover text gives the counts.
 *
 * @param categories Category key -> events in it.
 * @param events All events counted (the number in brackets).
 */
const CategoryBadges = ({ categories, events }: { categories?: Record<string, number>; events: number }) => {
  const shown = Object.entries(CATEGORY_BADGE).filter(([k]) => (categories?.[k] ?? 0) > 0);
  if (shown.length === 0) return null;
  const hint = shown.map(([k, b]) => `${b.letter}: ${num(categories?.[k] ?? 0)} of ${num(events)} events are ${b.long}`).join("\n");
  return (
    <Tooltip label={<span style={{ whiteSpace: "pre-line" }}>{hint}</span>} withinPortal multiline>
      <Group gap={1} wrap="nowrap" style={{ flexShrink: 0 }}>
        {shown.map(([k, b]) => (
          <Box
            key={k}
            component="span"
            style={{
              fontSize: 9,
              lineHeight: "11px",
              padding: "0 2px",
              borderRadius: 2,
              color: "var(--mantine-color-dimmed)",
              background: "var(--mantine-color-default-hover)",
              textDecoration: (categories?.[k] ?? 0) < events ? "underline dotted" : undefined,
            }}
          >
            {b.letter}
          </Box>
        ))}
      </Group>
    </Tooltip>
  );
};

/** "≥ 81 %": the smallest variant threshold that puts an activity on an included trace (null: none does). */
const neededText = (needed: number | null | undefined) => (needed == null ? null : `≥ ${num(needed)} %`);

/**
 * Why an activity of the lower part is not on an included trace of a type when no variant threshold helps.
 *
 * @param t The activity's entry for the type.
 * @param categoriesExcluded True if an event category is deselected.
 */
const missingReason = (t: DfgActivityTypeOption, categoriesExcluded: boolean) =>
  !t.selected_type ? "type not selected" : !t.included ? "deselected" : categoriesExcluded ? "removed by an event category" : "not on a trace";

/**
 * One activity in the list: a checkbox for all selected types (indeterminate if selected for some of them), its
 * events with handling units, and an unfold with its events per object type, each selected type with a checkbox.
 */
const ActivityRow = ({
  option,
  colours,
  selectedTypes,
  setIncluded,
  outside,
  categoriesExcluded,
}: {
  option: DfgActivityOption;
  colours: Map<string, string>;
  selectedTypes: Set<string>;
  setIncluded: (activity: string, types: string[], included: boolean) => void;
  /** Lower part of the list: show the variant threshold needed (or why it is missing). */
  outside?: boolean;
  categoriesExcluded?: boolean;
}) => {
  const [open, setOpen] = useState(false);
  const selectable = option.object_types.filter((t) => selectedTypes.has(t.object_type));
  const included = selectable.filter((t) => t.included).length;
  const status = (t: DfgActivityTypeOption) =>
    t.on_included_trace ? "in the graph" : (neededText(t.variant_threshold_needed) ?? missingReason(t, !!categoriesExcluded));
  const summary =
    neededText(option.variant_threshold_needed) ??
    (selectable.length === 0 ? "other types only" : included === 0 ? "deselected" : categoriesExcluded ? "event category" : "not on a trace");
  return (
    <Stack gap={1}>
      <Group gap={6} wrap="nowrap" justify="space-between">
        <Checkbox
          size="xs"
          disabled={selectable.length === 0}
          checked={selectable.length > 0 && included === selectable.length}
          indeterminate={included > 0 && included < selectable.length}
          onChange={() => setIncluded(option.activity, selectable.map((t) => t.object_type), included < selectable.length)}
          label={
            <Group gap={5} wrap="nowrap">
              <Text size="xs">{option.activity}</Text>
              <Text size="xs" c="dimmed">({num(option.hu_events)})</Text>
              <CategoryBadges categories={option.categories} events={option.hu_events} />
            </Group>
          }
        />
        {outside && (
          <Tooltip label="Smallest variant threshold that puts the activity into the graph (of any selected type), or why none does" withinPortal multiline w={240}>
            <Text size="xs" c="dimmed" ml="auto" style={{ whiteSpace: "nowrap" }}>{summary}</Text>
          </Tooltip>
        )}
        <ActionIcon size="xs" variant="subtle" color="gray" onClick={() => setOpen((o) => !o)} aria-label={`Object types of ${option.activity}`}>
          {open ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}
        </ActionIcon>
      </Group>
      <Collapse expanded={open}>
        <Stack gap={1} pl={22} pb={2}>
          {option.object_types.map((t) => (
            <Checkbox
              key={t.object_type}
              size="xs"
              disabled={!t.selected_type}
              checked={t.selected_type && t.included}
              onChange={(e) => setIncluded(option.activity, [t.object_type], e.currentTarget.checked)}
              label={
                <Group gap={5} wrap="nowrap">
                  <Swatch colour={colours.get(t.object_type)} circle={!t.selected_type} />
                  <Text size="xs">{t.object_type}</Text>
                  <Text size="xs" c="dimmed">({num(t.events)})</Text>
                  <CategoryBadges categories={t.categories} events={t.events} />
                  {outside && t.selected_type && <Text size="xs" c="dimmed">· {status(t)}</Text>}
                </Group>
              }
            />
          ))}
        </Stack>
      </Collapse>
    </Stack>
  );
};

/** Short text of an arc, e.g. "pallet: pick → pack" (▶ / ■ for start and end). */
const arcText = (a: ArcKey) => `${a.object_type}: ${a.source ?? "▶"} → ${a.target ?? "■"}`;

/**
 * The sidebar: reset, general values (variants, arcs, arc count, stay connected), arcs removed by hand, object types
 * (searchable, scrollable, each with an unfold for own values), activities (searchable, scrollable, each with an
 * unfold per object type), and the display options.
 *
 * @param graph The last graph (object types, activity options, defaults, removed arcs).
 * @param colours Colour per object type.
 * @param state The settings; `setState` changes them (every change keeps the other settings).
 * @param onHide Hides the sidebar (the page shows a button to bring it back).
 */
export const DfgSettings = ({
  graph,
  colours,
  state,
  setState,
  onHide,
}: {
  graph: DirectlyFollowsGraph;
  colours: Map<string, string>;
  state: DfgState;
  setState: (update: (s: DfgState) => DfgState) => void;
  onHide: () => void;
}) => {
  const [typeQuery, setTypeQuery] = useState("");
  const [activityQuery, setActivityQuery] = useState("");
  const objectTypes = graph.object_types;
  const activityOptions = graph.activity_options;
  const selected = objectTypes.filter((t) => t.selected);
  const selectedTypes = selected.map((t) => t.object_type);
  const selectedSet = new Set(selectedTypes);
  // Types with handling units first, whatever their number of objects (Nina, 2026-11-14); otherwise as sent (most objects first).
  const listedTypes = [...objectTypes.filter((t) => t.handling_units), ...objectTypes.filter((t) => !t.handling_units)];
  const matches = (text: string, query: string) => text.toLowerCase().includes(query.trim().toLowerCase());
  const manual = state.removed.length > 0;
  const sum = (f: (t: DfgObjectType) => number | undefined) => selected.reduce((n, t) => n + (f(t) ?? 0), 0);

  // The activities currently selected for a type (as the backend applied them, i.e. the default if not set).
  const includedOf = (type: string) =>
    activityOptions.filter((a) => a.object_types.some((t) => t.object_type === type && t.included)).map((a) => a.activity);
  const setIncluded = (activity: string, types: string[], include: boolean) =>
    setState((s) => {
      const activities = { ...s.activities };
      for (const t of types) {
        const current = activities[t] ?? includedOf(t);
        activities[t] = include ? [...new Set([...current, activity])] : current.filter((a) => a !== activity);
      }
      return { ...s, activities };
    });
  // Upper part: on an included trace (Nina, 2026-11-15); lower part: the others, least variant threshold needed first.
  const listed = activityOptions.filter((a) => matches(a.activity, activityQuery));
  const inGraph = listed.filter((a) => a.on_included_trace);
  const outsideGraph = listed
    .filter((a) => !a.on_included_trace)
    .sort((x, y) => (x.variant_threshold_needed ?? 1000) - (y.variant_threshold_needed ?? 1000));
  const removedInfo = new Map((graph.removed_arcs ?? []).map((a) => [arcText(a), a]));

  return (
    <Card withBorder padding="xs">
      <Stack gap={6}>
        <Group justify="space-between" gap={4} wrap="nowrap">
          <Text size="sm" fw={700}>Settings</Text>
          <Tooltip label="Hide the settings" withinPortal>
            <ActionIcon size="sm" variant="subtle" color="gray" onClick={onHide} aria-label="Hide the settings">
              <PanelRightCloseIcon size={14} />
            </ActionIcon>
          </Tooltip>
        </Group>

        <Divider label={<Group gap={6}>General<Manual on={manual} /></Group>} labelPosition="left" />
        <PercentSlider
          label="Variants"
          info={`${INFO.general} ${INFO.variants}`}
          value={state.variantThreshold}
          autoText="default"
          autoValue={graph.variant_default}
          onCommit={(v) => setState((s) => ({ ...s, variantThreshold: v }))}
          onAuto={() => setState((s) => ({ ...s, variantThreshold: null }))}
          note={`${num(sum((t) => t.kept_variants))} of ${num(sum((t) => t.variants))} variants`}
        />
        <PercentSlider
          label="Arcs (projection)"
          info={`${INFO.general} ${INFO.arcs}`}
          value={state.arcThreshold}
          onCommit={(v) => setState((s) => ({ ...s, arcThreshold: v }))}
          note={`${num(sum((t) => t.threshold_arcs))} of ${num(sum((t) => t.arcs))} arcs`}
        />
        <CountSlider
          label="Arcs (display)"
          info={`${INFO.general} ${INFO.arcCount}`}
          value={state.arcCount}
          max={graph.arc_count_max ?? 0}
          shown={sum((t) => t.shown_arcs)}
          total={sum((t) => t.threshold_arcs)}
          onCommit={(v) => setState((s) => ({ ...s, arcCount: v }))}
        />
        <Group justify="space-between" gap={4} wrap="nowrap">
          <Heading info={INFO.stay}>Stay connected</Heading>
          <Switch size="xs" checked={state.stayConnected} onChange={(e) => {
            const stayConnected = e.currentTarget.checked;
            setState((s) => ({ ...s, stayConnected }));
          }} aria-label="Stay connected" />
        </Group>
        {manual && (
          <Stack gap={2}>
            <Group justify="space-between" gap={4} wrap="nowrap">
              <Heading info={INFO.removed}>
                {state.removed.length} {state.removed.length === 1 ? "arc" : "arcs"} removed by hand
              </Heading>
              <Button size="compact-xs" variant="subtle" onClick={() => setState((s) => ({ ...s, removed: [] }))}>
                Restore all
              </Button>
            </Group>
            {state.removed.map((a) => {
              const info = removedInfo.get(arcText(a));
              return (
                <Group key={arcText(a)} gap={4} wrap="nowrap" justify="space-between">
                  <Group gap={5} wrap="nowrap" style={{ minWidth: 0 }}>
                    <Swatch colour={colours.get(a.object_type)} />
                    <Text size="xs" truncate>{arcText(a)}</Text>
                    {info && <Text size="xs" c="dimmed">({num(info.count)})</Text>}
                  </Group>
                  <ActionIcon size="xs" variant="subtle" color="gray" aria-label={`Restore ${arcText(a)}`} onClick={() => setState((s) => ({ ...s, removed: s.removed.filter((r) => !sameArc(r, a)) }))}>
                    <XIcon size={12} />
                  </ActionIcon>
                </Group>
              );
            })}
          </Stack>
        )}

        <Divider label="Object types" labelPosition="left" />
        <Group justify="space-between" gap={4} wrap="nowrap">
          <Heading info={INFO.objectTypes}>{selectedTypes.length} of {objectTypes.length} selected</Heading>
        </Group>
        <Search value={typeQuery} onChange={setTypeQuery} placeholder="Search object types" />
        <ScrollArea.Autosize mah={300} type="auto" offsetScrollbars>
          <Stack gap={2}>
            {listedTypes
              .filter((t) => matches(t.object_type, typeQuery))
              .map((t) => (
                <TypeRow
                  key={t.object_type}
                  type={t}
                  colour={colours.get(t.object_type)}
                  state={state}
                  setState={setState}
                  selectedTypes={selectedTypes}
                  arcCountMax={graph.arc_count_max ?? 0}
                  variantDefault={graph.variant_default ?? 100}
                />
              ))}
          </Stack>
        </ScrollArea.Autosize>

        <Divider label="Activities" labelPosition="left" />
        <Group justify="space-between" gap={4} wrap="nowrap">
          <Heading info={INFO.activities}>
            {activityOptions.filter((a) => a.object_types.some((t) => t.selected_type && t.included)).length} of {activityOptions.length} selected
          </Heading>
          {Object.keys(state.activities).length > 0 && (
            <Button size="compact-xs" variant="subtle" onClick={() => setState((s) => ({ ...s, activities: {} }))}>
              Default
            </Button>
          )}
        </Group>
        <Search value={activityQuery} onChange={setActivityQuery} placeholder="Search activities" />
        <ScrollArea.Autosize mah={320} type="auto" offsetScrollbars>
          <Stack gap={2}>
            {inGraph.map((a) => (
              <ActivityRow key={a.activity} option={a} colours={colours} selectedTypes={selectedSet} setIncluded={setIncluded} />
            ))}
            {outsideGraph.length > 0 && (
              <Divider
                my={2}
                label={<Heading info={INFO.outside}>Not on the included traces ({outsideGraph.length})</Heading>}
                labelPosition="left"
                variant="dashed"
              />
            )}
            {outsideGraph.map((a) => (
              <ActivityRow
                key={a.activity}
                option={a}
                colours={colours}
                selectedTypes={selectedSet}
                setIncluded={setIncluded}
                outside
                categoriesExcluded={state.excludedCategories.length > 0}
              />
            ))}
          </Stack>
        </ScrollArea.Autosize>

      </Stack>
    </Card>
  );
};
