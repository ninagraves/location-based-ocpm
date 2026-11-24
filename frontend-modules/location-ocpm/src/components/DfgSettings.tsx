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
import { ChevronDownIcon, ChevronRightIcon, InfoIcon, SearchIcon, XIcon } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import type { DfgActivityOption, DfgActivityTypeOption, DfgObjectType, DfgRequest, DirectlyFollowsGraph } from "../api/locationBasedOcpm";
import { activitiesOfType, activityMatches, matchingObjectTypes, typeEvents } from "../lib/dfgActivitySearch";
import { type ArcSettings, type BaseArc, neededArcThresholds } from "../lib/dfgArcs";
import type { ArcLabel, Direction, PaperRatio } from "../lib/dfgLayout";
import { num } from "../lib/format";
import { useKeptScrollOf } from "../lib/keptView";
import { usePageState } from "../lib/pageState";
import { UI } from "../lib/palette";
import { useScheme } from "./plots";

/** An arc, as the backend identifies it (null = start / end node). */
export type ArcKey = { object_type: string; source: string | null; target: string | null };

/** The page's settings. `objectTypes` null = the object types with handling units. */
export type DfgState = {
  objectTypes: string[] | null;
  /** General variant threshold (percent) for every type without an own one; null = the default (80 %). */
  variantThreshold: number | null;
  /** General Arcs (projection) (percent) for every type without an own one. */
  arcThreshold: number;
  /** General Arcs (display) for every type without an own one; null = all arcs. */
  arcCount: number | null;
  /** How the general Arcs (display) counts: one limit for all these types together ("general") or per type. */
  arcCountMode: "general" | "perType";
  /** Own values per object type (kept while the type is unselected). */
  own: Record<string, { variant?: number; arc?: number; count?: number }>;
  /** Selected activities per object type; a type that is missing has the default selection. */
  activities: Record<string, string[]>;
  /** Every arc lies on a path from start to end ("Stay connected"). */
  stayConnected: boolean;
  /** Arcs removed by hand (double click on an arc). */
  removed: ArcKey[];
  /** Deselected event categories (keys, e.g. "to_vehicle"); their events are removed from the traces first. */
  excludedCategories: string[];
  arcLabel: ArcLabel;
  direction: Direction;
  compact: boolean;
  /** Aim the layout at the ratio of a portrait or landscape sheet of paper (Nina, 2026-11-23); "off": no aim. */
  paper: PaperRatio;
};

/**
 * Defaults (Nina, 2026-11-15/16): handling-unit types; per type its most frequent 40 % of activities (3 to 10), shared
 * between the handling-unit types; variants 80 % (backend default); Arcs (projection) 50 %; Arcs (display) all, general;
 * Stay connected on; Move to vehicle, Move to storage and Other movements deselected (Nina, 2026-11-19/20).
 */
export const DEFAULT_STATE: DfgState = {
  objectTypes: null,
  variantThreshold: null,
  arcThreshold: 50,
  arcCount: null,
  arcCountMode: "general",
  own: {},
  activities: {},
  stayConnected: true,
  removed: [],
  // All movements off by default (Nina, 2026-11-19; `categories.DEFAULT_EXCLUDED`).
  excludedCategories: ["to_vehicle", "to_storage", "other_movement"],
  arcLabel: "count",
  direction: "RIGHT",
  compact: false,
  paper: "off",
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

/**
 * The arc settings of a state, for `filterArcs` (own values of a type first, then the general ones). In "general"
 * mode, the general Arcs (display) is one limit for all types without an own value together (`total`).
 */
export const arcSettings = (state: DfgState): ArcSettings => ({
  threshold: (t) => state.own[t]?.arc ?? state.arcThreshold,
  count: (t) => state.own[t]?.count ?? (state.arcCountMode === "perType" ? state.arcCount : null),
  total: state.arcCountMode === "general" ? state.arcCount : null,
  removed: state.removed,
  stayConnected: state.stayConnected,
});

/** True if two arcs are the same. */
const sameArc = (a: ArcKey, b: ArcKey) => a.object_type === b.object_type && a.source === b.source && a.target === b.target;

/** Adds an arc to the removed arcs (double click on an arc in the graph). */
export const removeArc = (state: DfgState, arc: ArcKey): DfgState =>
  state.removed.some((r) => sameArc(r, arc)) ? state : { ...state, removed: [...state.removed, arc] };

/** Hover texts of the settings (short versions of the documentation). */
export const INFO = {
  reset: "Sets every setting of this page back to its default, and restores the arcs removed by hand.",
  general:
    "General values: apply to every object type that has no own value (set in the type's unfold). Types with own values are marked in the list.",
  variants:
    "Variant threshold: keeps the most frequent variants (activity sequences of the objects, after removing deselected activities) of a type until they cover at least this share of its objects; equally frequent variants by their first occurrence in the log. Only these objects' traces are used for everything else. 100 % keeps all. Default: 80 %. Click the number to type a value (decimals allowed).",
  arcs: "Arcs (projection), the arc threshold: ranks all arcs of a type (start and end arcs included) by objects, then traversals, and keeps this share of them (rounded up), together with every arc as frequent as the last kept one. 100 % keeps all. Default: 50 %. Click the number to type a value (decimals allowed).",
  arcCount:
    "Arcs (display), the arc count: of the arcs left by Arcs (projection), shows the first N, ranked by objects, traversals, first occurrence, then name (exactly N, ties broken by this order). General (default): N arcs of all object types together (types with an own value keep theirs); per type: N arcs of every type. − and + change it by one. The number shows how many arcs are shown of how many.",
  stay: "Stay connected: every shown arc lies on a path from the start to the end of its object type. Arcs that Arcs (projection) or Arcs (display) removed are added back where needed (drawn like the others; hovering such an arc says “only kept to stay connected”). It never adds arcs of removed variants, deselected activities or arcs removed by hand.",
  removed:
    "Arcs removed by hand (double click on an arc in the graph). While there are any, the sliders no longer describe the graph on their own (marked as manual). Click × to restore an arc.",
  objectTypes:
    "Checked object types are drawn with their directly-follows arcs, start and end nodes. Unchecked object types that are involved in the shown events appear only as circles on the activity nodes. Default: the object types of the handling units. Unfold a type for its own values.",
  categories:
    "Event categories: an event is removed from the traces (before anything else, like deselecting an activity) only when all categories it belongs to are deselected. Move to vehicle / storage: movements whose target location is a vehicle / storage unit. Other movements: all other movements (target location neither, or not given). Every movement is in exactly one of these three; it stays while a processing or transforming chip it also belongs to is on. Events in no category are not affected by the chips (the activity selection still applies).",
  activities:
    "Activities by number of events that involve a handling unit (in brackets). The events of an unchecked activity are removed from the traces before anything else (as in Ocelescope): a trace a, b, c without b becomes a, c. Unfold an activity for its events per object type and to (de)select it for single selected types. Default per type: its most frequent 40 % of activities (at least 3, at most 10) among those with events left after the event categories, plus every activity preselected for another selected handling-unit type. Upper part: the activities in the graph. Lower part: the others, each with the value it needs: in blue the smallest Arcs (projection) that would show it (it is on an included trace, but none of its arcs is kept), in grey the smallest variant threshold that would put it on an included trace. Unfold for the values per type. Search for movements, vehicles, storage, processing or transformation to find the activities with these events too. Search for an object type (at least 4 letters of its name, or its full name) and click it below the search box to list every activity it is involved in, most events of the type first.",
  typeHits:
    "Object types whose name contains the search text (at least 4 letters, or the full name). Click one to list every activity it is involved in, most events of the type first.",
  activityType:
    "Every activity with at least one event involving an object of this type (for a handling-unit type: one of its handling units), most such events first (the number in brackets; ties: events with a handling unit, then events in the log, then name). One list, without the parts; activities not in the graph keep their value on the right. The search text narrows the list further; the cross goes back to all activities.",
  outside:
    "Activities not in the graph. Blue: on an included trace, but none of its arcs is kept; the number is the smallest Arcs (projection) (of any selected type) that keeps one, \"display\" if Arcs (projection) keeps one but Arcs (display) or a removal by hand hides it. Grey: on no included trace; the number is the smallest variant threshold (of any selected type) that would put it on one (for an unchecked activity: if it were checked). Without a number, no threshold helps: “removed by an event category” means all its events were removed by the event category chips above the graph (each of them is only in categories that are switched off), checked or not, e.g. “load truck” with Move to vehicle off; “type not selected” means only unselected types have it. Unfold for each selected type.",
  withoutHu:
    "Activities with no event that involves a handling unit (not in the graph). The value names the object type for which the activity is easiest to include: the type with the smallest variant threshold that puts it on an included trace, if that type were selected with its default activities (and the activity checked), e.g. “operator · ≥ 67 %”. Blue as above: on an included trace of a selected type, but none of its arcs is kept. Unfold for the value of every type, selected or not.",
  arcLabel: "What the number on an arc counts: traversals (an object repeating the arc counts each time) or distinct objects.",
  direction: "Direction of the layout: from left to right (→) or from top to bottom (↓).",
  settings: "Show or hide the discovery settings.",
  pending:
    "The graph is recalculated 2 seconds after the last change, so several settings can be changed first. Update now: recalculate at once.",
  compact: "Less white space between nodes and arcs, e.g. to export the whole graph as a figure.",
  paper:
    "Paper: lays the graph out closer to the shape of a sheet of paper (A4 or any ISO size, width : height = 1 : 1.41 in portrait, 1.41 : 1 in landscape). The chain of activities is cut into several rows (left to right) or columns (top to bottom) placed below / next to each other; arcs between them run around. Only an approximation: a graph with few activities in a row cannot be cut finer. Works with and without Compact. Off: no aim (default).",
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
              {autoText ?? "auto"}
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
 * @param shown, total Arcs shown (kept by the arc settings) and arcs left by the arc threshold (for the note).
 * @param connecting Arcs added by Stay connected, shown apart as "+ n to stay connected" (Nina, 2026-11-19).
 * @param onCommit Called with the new value (null when set to `max` or more, i.e. all).
 */
const CountSlider = ({
  label,
  info,
  value,
  max,
  shown,
  total,
  connecting = 0,
  onCommit,
}: {
  label: string;
  info: string;
  value: number | null;
  max: number;
  shown: number;
  total: number;
  connecting?: number;
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
        <Text size="xs" c="dimmed" style={{ whiteSpace: "nowrap" }}>
          {num(shown)} of {num(total)} arcs{connecting > 0 && ` + ${num(connecting)} to connect`}
        </Text>
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
  connecting = 0,
  openKey,
}: {
  type: DfgObjectType;
  colour?: string;
  state: DfgState;
  setState: (update: (s: DfgState) => DfgState) => void;
  selectedTypes: string[];
  arcCountMax: number;
  variantDefault: number;
  /** Arcs of the type added by Stay connected. */
  connecting?: number;
  /** Where the row keeps whether it is unfolded (`usePageState`). */
  openKey: string;
}) => {
  const [open, setOpen] = usePageState(openKey, false);
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
          />
          <PercentSlider
            label="Arcs (projection)"
            info={INFO.arcs}
            value={own.arc ?? state.arcThreshold}
            onCommit={(v) => setOwn({ arc: v })}
          />
          <CountSlider
            label="Arcs (display)"
            info={INFO.arcCount}
            value={own.count ?? (state.arcCountMode === "perType" ? state.arcCount : null)}
            max={type.selected ? (type.threshold_arcs ?? 0) : arcCountMax}
            shown={(type.shown_arcs ?? 0) - connecting}
            total={type.threshold_arcs ?? 0}
            connecting={connecting}
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
 * unit, P processing operations, T transformations (Nina, 2026-11-15: small, single letters). M marks the other
 * movements (to neither a vehicle nor a storage unit; Nina, 2026-11-20, replacing all movements).
 */
const CATEGORY_BADGE: Record<string, { letter: string; long: string }> = {
  to_vehicle: { letter: "V", long: "movements to a vehicle" },
  to_storage: { letter: "W", long: "movements to a storage unit" },
  other_movement: { letter: "M", long: "other movements" },
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
 * Why an activity of the lower part is not on an included trace of a type when no variant threshold helps: the type is
 * not selected, or all its events of the type were removed by the event category chips (checked or not: an unchecked
 * activity gets the threshold it would need if checked, so no value means the same; Nina, 2026-11-18).
 *
 * @param t The activity's entry for the type.
 */
const missingReason = (t: DfgActivityTypeOption) => (!t.selected_type ? "type not selected" : "removed by an event category");

/**
 * Summary of an activity without handling units (Nina, 2026-11-19): the type for which it is easiest to include and
 * its whole variant threshold, e.g. "operator · ≥ 67 %"; "event category" if no type has a value.
 *
 * @param option The activity.
 */
const easiestText = (option: DfgActivityOption) => {
  const easiest = option.object_types.find((t) => t.object_type === option.easiest_type);
  const needed = neededText(easiest?.variant_threshold_needed);
  return easiest && needed ? `${easiest.object_type} · ${needed}` : "event category";
};

/** For an activity of the upper part that is not in the graph: per type the Arcs (projection) needed, or "display" if
 * Arcs (projection) already keeps one of its arcs (it is hidden by Arcs (display) or by arcs removed by hand). */
export type ProjectionNeed = number | "display";

/** Text of a `ProjectionNeed`. */
const projectionText = (need: ProjectionNeed | undefined) => (need === undefined ? null : need === "display" ? "display" : `≥ ${num(need)} %`);

/** Hover text of a blue number (lower part, on an included trace but not drawn). */
const PROJECTION_HINT =
  "For the Arcs (projection) slider: the smallest value (of any selected type) at which an arc of the activity is kept. \"display\": Arcs (projection) already keeps one, but Arcs (display) or an arc removed by hand hides it.";
/** Hover text of a grey number (lower part, on no included trace). */
const VARIANT_HINT =
  "For the Variants slider: the smallest variant threshold (of any selected type) that puts the activity on an included trace (for an unchecked activity: if it were checked). \"event category\" / \"removed by an event category\": all events of the activity were removed by the event category chips above the graph (every category of each of its events is switched off), so no variant threshold helps, checked or not; switch a chip on again. Unfolded: the exact values (up to 3 decimals). \"type not selected\": only unselected object types have the activity.";
/** Hover text of the value of an activity without handling units (third part). */
const EASIEST_HINT =
  "For the Variants slider of the named object type: the type for which the activity is easiest to include, i.e. the smallest variant threshold that would put it on an included trace if that type were selected with its default activities (and the activity checked). Select the type under Object types first. Unfold for every type.";
/** Colour of the Arcs (projection) values, to tell them from the variant thresholds (Nina, 2026-11-17). */
const PROJECTION_COLOUR = "blue.7";

/** Height of the object type list in px before it scrolls (about 6 types; Nina, 2026-11-19, before 300). */
const TYPE_LIST_HEIGHT = 160;
/** Smallest height of the activity list in px; it takes all the rest of the sidebar (Nina, 2026-11-19, before 320). */
const ACTIVITY_LIST_MIN_HEIGHT = 360;
/** Object types offered below the activity search at most (the others: "+n more, type more letters"). */
const TYPE_HITS_SHOWN = 6;

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
  projection,
  projectionExact,
  withoutHu,
  missingTypes,
  countType,
  openKey,
}: {
  option: DfgActivityOption;
  colours: Map<string, string>;
  selectedTypes: Set<string>;
  setIncluded: (activity: string, types: string[], included: boolean) => void;
  /** Lower part of the list (not in the graph): show what it needs per type. */
  outside?: boolean;
  /** On an included trace but not in the graph: Arcs (projection) needed per type (shown in blue). */
  projection?: Map<string, ProjectionNeed>;
  /** The same with up to 3 decimals, for the unfold ("display" types are left out). */
  projectionExact?: Map<string, number>;
  /** Third part (no event with a handling unit): name the easiest type and show values for unselected types too. */
  withoutHu?: boolean;
  /** Upper part: the selected types without a drawn arc of the activity; their unfold shows the values as below. */
  missingTypes?: Set<string>;
  /** Object type search: the number in brackets and the badges count the events of this type instead of those with a
   * handling unit. */
  countType?: string;
  /** Where the row keeps whether it is unfolded (`usePageState`). */
  openKey: string;
}) => {
  const [open, setOpen] = usePageState(openKey, false);
  const count = countType ? typeEvents(option, countType) : option.hu_events;
  const countCategories = countType
    ? option.object_types.find((t) => t.object_type === countType)?.categories
    : option.categories;
  const selectable = option.object_types.filter((t) => selectedTypes.has(t.object_type));
  const included = selectable.filter((t) => t.included).length;
  // Per type (unfold, exact values with up to 3 decimals): the Arcs (projection) needed (blue), "in the graph", or the
  // variant threshold needed (or why none helps).
  const status = (t: DfgActivityTypeOption): { text: string | null; projection: boolean } => {
    if (!outside && !missingTypes?.has(t.object_type)) return { text: null, projection: false };
    const need = projection?.get(t.object_type);
    if (need !== undefined) {
      return { text: projectionText(need === "display" ? need : (projectionExact?.get(t.object_type) ?? need)), projection: true };
    }
    if (t.on_included_trace) return { text: projection && outside ? "in the graph" : null, projection: false };
    return { text: neededText(t.variant_threshold_needed_exact ?? t.variant_threshold_needed) ?? missingReason(t), projection: false };
  };
  const numbers = [...(projection?.values() ?? [])].filter((v): v is number => v !== "display");
  const summary = !outside
    ? null
    : projection
      ? projectionText(numbers.length > 0 ? Math.min(...numbers) : "display")
      : withoutHu
        ? easiestText(option)
        : (neededText(option.variant_threshold_needed) ??
          (selectable.length === 0 ? "other types only" : "event category"));
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
              <Text size="xs" c="dimmed">({num(count)})</Text>
              <CategoryBadges categories={countCategories} events={count} />
            </Group>
          }
        />
        {summary && (
          <Tooltip
            label={projection ? PROJECTION_HINT : withoutHu ? EASIEST_HINT : VARIANT_HINT}
            withinPortal
            multiline
            w={260}
          >
            <Text size="xs" c={projection ? PROJECTION_COLOUR : "dimmed"} ml="auto" style={{ whiteSpace: "nowrap" }}>{summary}</Text>
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
                  {(t.selected_type || withoutHu) && status(t).text && (
                    <Text size="xs" c={status(t).projection ? PROJECTION_COLOUR : "dimmed"}>· {status(t).text}</Text>
                  )}
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
 * The sidebar "Discovery Settings": general values (variants, Arcs (projection), stay connected), arcs removed by hand,
 * object types (searchable, scrollable, each with an unfold for own values), activities (searchable incl. category
 * words, "Select all" for the results, scrollable, each with an unfold per object type). Arcs (display) and the
 * layout settings are in the toolbar above the graph (DfgToolbar.tsx). Fills the height it is given.
 *
 * @param graph The drawn graph (object types, activity options, shown activities, defaults, removed arcs).
 * @param baseArcs All arcs of the included traces (for the Arcs (projection) needed by activities not in the graph).
 * @param colours Colour per object type.
 * @param state The settings; `setState` changes them (every change keeps the other settings).
 */
export const DfgSettings = ({
  graph,
  baseArcs,
  colours,
  state,
  setState,
  footer,
  stateKey,
}: {
  graph: DirectlyFollowsGraph;
  baseArcs: BaseArc[];
  colours: Map<string, string>;
  state: DfgState;
  setState: (update: (s: DfgState) => DfgState) => void;
  /** Shown below the scrolling part, at the bottom of the sidebar ("Save to session", `DfgSave`). */
  footer?: ReactNode;
  /** Where the searches, unfolded rows and scroll positions are kept, with the log id (e.g. `dfg.sidebar.<log id>`). */
  stateKey: string;
}) => {
  const [typeQuery, setTypeQuery] = usePageState(`${stateKey}.typeQuery`, "");
  const [activityQuery, setActivityQuery] = usePageState(`${stateKey}.activityQuery`, "");
  /** Object type search (Nina, 2026-11-24): the type whose activities are listed, most events of the type first. */
  const [activityType, setActivityType] = usePageState<string | null>(`${stateKey}.activityType`, null);
  const sidebarScroll = useKeptScrollOf<HTMLDivElement>(`${stateKey}.scroll`);
  const typeScroll = useKeptScrollOf<HTMLDivElement>(`${stateKey}.types.scroll`);
  const activityScroll = useKeptScrollOf<HTMLDivElement>(`${stateKey}.activities.scroll`);
  const objectTypes = graph.object_types;
  const activityOptions = graph.activity_options;
  const selected = objectTypes.filter((t) => t.selected);
  const selectedTypes = selected.map((t) => t.object_type);
  const selectedSet = new Set(selectedTypes);
  // Types with handling units first, whatever their number of objects (Nina, 2026-11-14); otherwise as sent (most objects first).
  const listedTypes = [...objectTypes.filter((t) => t.handling_units), ...objectTypes.filter((t) => !t.handling_units)];
  const matches = (text: string, query: string) => text.toLowerCase().includes(query.trim().toLowerCase());
  const manual = state.removed.length > 0;

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
  // Select all search results for every selected type with events of them (Nina, 2026-11-16).
  const selectAll = (options: DfgActivityOption[]) =>
    setState((s) => {
      const activities = { ...s.activities };
      for (const o of options)
        for (const t of o.object_types.filter((t) => selectedSet.has(t.object_type))) {
          const current = activities[t.object_type] ?? includedOf(t.object_type);
          activities[t.object_type] = [...new Set([...current, o.activity])];
        }
      return { ...s, activities };
    });
  // Upper part: the activities in the graph; lower part: the others (Nina, 2026-11-17; before: upper part = on an
  // included trace). Lower part: first those on an included trace (Arcs (projection) needed, in blue), then the
  // others (variant threshold needed), least first.
  // Object type search (Nina, 2026-11-24): with a type picked, the list holds every activity the type is involved in,
  // most events of the type first, in one part (the search text narrows it further).
  const listType = activityType !== null && objectTypes.some((t) => t.object_type === activityType) ? activityType : null;
  const listed = (listType ? activitiesOfType(activityOptions, listType) : activityOptions).filter((a) =>
    activityMatches(a, activityQuery),
  );
  const typeHits = matchingObjectTypes(listedTypes.map((t) => t.object_type), activityQuery).filter((t) => t !== listType);
  const pickType = (type: string | null) => {
    setActivityType(type);
    setActivityQuery("");
  };
  const needed = useMemo(() => neededArcThresholds(baseArcs), [baseArcs]);
  const neededExact = useMemo(() => neededArcThresholds(baseArcs, 3), [baseArcs]);
  const shownActivities = new Set(graph.activities.map((a) => a.activity));
  // (type, activity) pairs with a drawn arc: an activity of the upper part can miss arcs of some types (Nina,
  // 2026-11-19: their unfold shows the same values as the lower part).
  const drawnPairs = new Set(graph.arcs.flatMap((a) => [a.source, a.target].filter((x) => x != null).map((x) => `${a.object_type}\u0000${x}`)));
  const missingTypes = (option: DfgActivityOption) =>
    new Set(option.object_types.filter((t) => t.selected_type && !drawnPairs.has(`${t.object_type}\u0000${option.activity}`)).map((t) => t.object_type));
  /**
   * Arcs (projection) needed per type: for an activity not in the graph every type, else only `types` (the types
   * without a drawn arc of it).
   */
  const projectionNeeds = (option: DfgActivityOption, types?: Set<string>) => {
    if (shownActivities.has(option.activity) && !types) return undefined;
    const needs = new Map<string, ProjectionNeed>();
    for (const t of option.object_types) {
      if (types && !types.has(t.object_type)) continue;
      const value = t.on_included_trace ? needed.get(t.object_type)?.get(option.activity) : undefined;
      if (value === undefined) continue;
      const current = state.own[t.object_type]?.arc ?? state.arcThreshold;
      needs.set(t.object_type, value <= current ? "display" : value);
    }
    return needs.size > 0 ? needs : undefined;
  };
  /** Of `projectionNeeds`, the numbers with up to 3 decimals (for the unfold). */
  const projectionExact = (option: DfgActivityOption, needs: Map<string, ProjectionNeed> | undefined) => {
    const exact = new Map<string, number>();
    for (const [t, need] of needs ?? []) {
      const value = neededExact.get(t)?.get(option.activity);
      if (need !== "display" && value !== undefined) exact.set(t, value);
    }
    return exact;
  };
  const inGraph = listed.filter((a) => shownActivities.has(a.activity));
  const rank = (a: DfgActivityOption) => {
    const needs = projectionNeeds(a);
    if (needs) return Math.min(...[...needs.values()].map((v) => (v === "display" ? 0 : v)));
    return 1000 + (a.variant_threshold_needed ?? 1000);
  };
  // Third part: activities with no event with a handling unit (Nina, 2026-11-19), easiest first.
  const notShown = listed.filter((a) => !shownActivities.has(a.activity));
  const outsideGraph = notShown.filter((a) => a.hu_events > 0).sort((x, y) => rank(x) - rank(y));
  const withoutHu = notShown
    .filter((a) => a.hu_events === 0)
    .sort((x, y) => rank(x) - rank(y) || (x.variant_threshold_needed_exact ?? 1000) - (y.variant_threshold_needed_exact ?? 1000));
  const removedInfo = new Map((graph.removed_arcs ?? []).map((a) => [arcText(a), a]));
  /** One row of the activity list, with the values of its part (in the graph, not in the graph, without handling units). */
  const activityRow = (a: DfgActivityOption) => {
    const inGraphRow = shownActivities.has(a.activity);
    const missing = inGraphRow ? missingTypes(a) : undefined;
    const needs = projectionNeeds(a, missing);
    return (
      <ActivityRow
        key={a.activity}
        openKey={`${stateKey}.open.activity.${a.activity}`}
        option={a}
        colours={colours}
        selectedTypes={selectedSet}
        setIncluded={setIncluded}
        projection={needs}
        projectionExact={projectionExact(a, needs)}
        missingTypes={missing}
        outside={!inGraphRow}
        withoutHu={!inGraphRow && a.hu_events === 0}
        countType={listType ?? undefined}
      />
    );
  };

  return (
    <Card withBorder padding="xs" h="100%" style={{ display: "flex", flexDirection: "column" }}>
      <Text size="sm" fw={700} mb={6}>Discovery Settings</Text>
      <Box ref={sidebarScroll} style={{ flex: 1, minHeight: 0, overflowY: "auto", overflowX: "hidden" }} pr={4}>
      {/* Fills the sidebar's height; the activity list takes the rest (Nina, 2026-11-19: more room than the types). */}
      <Stack gap={6} mih="100%">

        <Divider label={<Group gap={6}>General<Manual on={manual} /></Group>} labelPosition="left" />
        <PercentSlider
          label="Variants"
          info={`${INFO.general} ${INFO.variants}`}
          value={state.variantThreshold}
          autoText="default"
          autoValue={graph.variant_default}
          onCommit={(v) => setState((s) => ({ ...s, variantThreshold: v }))}
          onAuto={() => setState((s) => ({ ...s, variantThreshold: null }))}
        />
        <PercentSlider
          label="Arcs (projection)"
          info={`${INFO.general} ${INFO.arcs}`}
          value={state.arcThreshold}
          onCommit={(v) => setState((s) => ({ ...s, arcThreshold: v }))}
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
        <ScrollArea.Autosize viewportRef={typeScroll} mah={TYPE_LIST_HEIGHT} type="auto" offsetScrollbars>
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
                  connecting={graph.arcs.filter((a) => a.connecting && a.object_type === t.object_type).length}
                  openKey={`${stateKey}.open.type.${t.object_type}`}
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
        <Group gap={4} wrap="nowrap">
          <Box style={{ flex: 1 }}>
            <Search value={activityQuery} onChange={setActivityQuery} placeholder="Search activities or movements, vehicles, …" />
          </Box>
          {(activityQuery.trim() !== "" || listType !== null) && listed.length > 0 && (
            <Tooltip label="Select every activity found, for every selected object type with events of it" withinPortal multiline w={220}>
              <Button size="compact-xs" variant="light" onClick={() => selectAll(listed)}>
                Select all ({listed.length})
              </Button>
            </Tooltip>
          )}
        </Group>
        {typeHits.length > 0 && (
          <Group gap={4} wrap="wrap">
            <Tooltip label={INFO.typeHits} withinPortal multiline w={260}>
              <Text size="xs" c="dimmed">Object type:</Text>
            </Tooltip>
            {typeHits.slice(0, TYPE_HITS_SHOWN).map((t) => (
              <Badge
                key={t}
                size="sm"
                variant="light"
                color="gray"
                tt="none"
                style={{ cursor: "pointer" }}
                leftSection={<Swatch colour={colours.get(t)} circle />}
                onClick={() => pickType(t)}
              >
                {t}
              </Badge>
            ))}
            {typeHits.length > TYPE_HITS_SHOWN && (
              <Text size="xs" c="dimmed">+{typeHits.length - TYPE_HITS_SHOWN} more, type more letters</Text>
            )}
          </Group>
        )}
        {listType && (
          <Group gap={4} wrap="nowrap" justify="space-between">
            <Group gap={5} wrap="nowrap" style={{ minWidth: 0 }}>
              <Swatch colour={colours.get(listType)} circle />
              <Heading info={INFO.activityType}>
                {listed.length} {listed.length === 1 ? "activity" : "activities"} of {listType}, most events first
              </Heading>
            </Group>
            <ActionIcon size="xs" variant="subtle" color="gray" aria-label="Back to all activities" onClick={() => pickType(null)}>
              <XIcon size={12} />
            </ActionIcon>
          </Group>
        )}
        <ScrollArea viewportRef={activityScroll} type="auto" offsetScrollbars style={{ flex: "1 1 0", minHeight: ACTIVITY_LIST_MIN_HEIGHT }}>
          <Stack gap={2}>
            {listType ? (
              listed.map(activityRow)
            ) : (
              <>
                {inGraph.map(activityRow)}
                {outsideGraph.length > 0 && (
                  <Divider
                    my={2}
                    label={<Heading info={INFO.outside}>Not in the graph ({outsideGraph.length})</Heading>}
                    labelPosition="left"
                    variant="dashed"
                  />
                )}
                {outsideGraph.map(activityRow)}
                {withoutHu.length > 0 && (
                  <Divider
                    my={2}
                    label={<Heading info={INFO.withoutHu}>Without handling units ({withoutHu.length})</Heading>}
                    labelPosition="left"
                    variant="dashed"
                  />
                )}
                {withoutHu.map(activityRow)}
              </>
            )}
          </Stack>
        </ScrollArea>
      </Stack>
      </Box>
      {footer}
    </Card>
  );
};
