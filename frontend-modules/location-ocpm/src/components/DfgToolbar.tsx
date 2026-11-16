// The toolbar above the directly-follows graph (Nina, 2026-11-15/16): the event categories (deselect one to remove
// its events from the traces); arc labels, direction, Arcs (display) (general or per type, − / + and slider),
// compact, reset and the button that shows or hides the sidebar "Discovery Settings" (DfgSettings.tsx).
// Documented in docs/pages/directly-follows-graph.md, section "Settings".
import { ActionIcon, Button, Chip, Group, SegmentedControl, Slider, Switch, Text, Tooltip } from "@mantine/core";
import { ArrowDownIcon, ArrowRightIcon, InfoIcon, MinusIcon, PlusIcon, RotateCcwIcon, SlidersHorizontalIcon } from "lucide-react";
import { useEffect, useState } from "react";
import type { DfgEventCategory, DirectlyFollowsGraph } from "../api/locationBasedOcpm";
import type { ArcLabel, Direction } from "../lib/dfgLayout";
import { num } from "../lib/format";
import { DEFAULT_STATE, type DfgState, INFO } from "./DfgSettings";

/**
 * One chip per event category; clicking one (de)selects it. A category without events is disabled. An event is
 * removed only when all its categories are deselected (Nina, 2026-11-15).
 *
 * @param categories The categories of the graph (key, label, events).
 * @param excluded The deselected keys; `onChange` gets the new list.
 */
const CategoryChips = ({
  categories,
  excluded,
  onChange,
}: {
  categories: DfgEventCategory[];
  excluded: string[];
  onChange: (excluded: string[]) => void;
}) => (
  <Group gap={4} wrap="wrap">
    {categories.map((c) => (
      <Chip
        key={c.key}
        size="xs"
        variant="light"
        checked={!excluded.includes(c.key)}
        disabled={c.events === 0}
        onChange={(on) => onChange(on ? excluded.filter((k) => k !== c.key) : [...excluded, c.key])}
      >
        {c.label} ({num(c.events)})
      </Chip>
    ))}
    <Tooltip label={INFO.categories} multiline w={340} withinPortal>
      <InfoIcon size={12} style={{ opacity: 0.6 }} aria-label="About the event categories" />
    </Tooltip>
  </Group>
);

/**
 * The numbers of the general Arcs (display) control. General mode: the types without an own count share one limit,
 * so the slider goes up to the sum of their arcs left by Arcs (projection). Per type: up to the most arcs of one type.
 *
 * Example: coil has 6 arcs left, slab 4, neither has an own count; general: max 10, per type: max 6.
 *
 * @param graph The graph as drawn (`applyArcSettings`).
 * @param state The settings.
 * @returns The slider's maximum, and the arcs shown and left (of the types it applies to).
 */
export const displayNumbers = (graph: DirectlyFollowsGraph, state: DfgState) => {
  const types = graph.object_types.filter((t) => t.selected && state.own[t.object_type]?.count === undefined);
  const sum = (f: (t: (typeof types)[number]) => number | undefined) => types.reduce((n, t) => n + (f(t) ?? 0), 0);
  const max = state.arcCountMode === "general" ? sum((t) => t.threshold_arcs) : Math.max(0, ...types.map((t) => t.threshold_arcs ?? 0));
  return { max, shown: sum((t) => t.shown_arcs), left: sum((t) => t.threshold_arcs) };
};

/**
 * The general Arcs (display), grouped in one box: mode (general / per type), − and +, the slider and "x of y arcs".
 * The value null means all arcs (the slider at its maximum; + at the maximum sets it).
 *
 * @param graph The graph as drawn.
 * @param state The settings; `setState` changes them.
 */
const DisplayArcs = ({
  graph,
  state,
  setState,
}: {
  graph: DirectlyFollowsGraph;
  state: DfgState;
  setState: (update: (s: DfgState) => DfgState) => void;
}) => {
  const { max, shown, left } = displayNumbers(graph, state);
  const top = Math.max(max, 1);
  const value = state.arcCount ?? top;
  const [local, setLocal] = useState(value);
  useEffect(() => setLocal(value), [value]);
  const commit = (v: number) => setState((s) => ({ ...s, arcCount: v >= top ? null : Math.max(0, Math.round(v)) }));
  return (
    <Group
        gap={6}
        wrap="nowrap"
        px={6}
        py={2}
        style={{ border: "1px solid var(--mantine-color-default-border)", borderRadius: "var(--mantine-radius-sm)" }}
      >
        <Tooltip label={INFO.arcCount} multiline w={320} withinPortal>
          <Group gap={3} wrap="nowrap">
            <Text size="xs" fw={600}>Arcs (display)</Text>
            <InfoIcon size={11} style={{ opacity: 0.6 }} aria-label="About Arcs (display)" />
          </Group>
        </Tooltip>
        <SegmentedControl
          size="xs"
          aria-label="Arcs (display) counts"
          value={state.arcCountMode}
          onChange={(v) => setState((s) => ({ ...s, arcCountMode: v as DfgState["arcCountMode"] }))}
          data={[
            { value: "general", label: "General" },
            { value: "perType", label: "Per type" },
          ]}
        />
        <Group gap={2} wrap="nowrap">
          <ActionIcon size="sm" variant="default" aria-label="One arc fewer" disabled={value <= 0} onClick={() => commit(value - 1)}>
            <MinusIcon size={12} />
          </ActionIcon>
          <ActionIcon size="sm" variant="default" aria-label="One arc more" disabled={state.arcCount === null} onClick={() => commit(value + 1)}>
            <PlusIcon size={12} />
          </ActionIcon>
        </Group>
        <Slider
          aria-label="Arcs (display)"
          size="xs"
          w={120}
          min={0}
          max={top}
          step={1}
          value={local}
          onChange={setLocal}
          onChangeEnd={commit}
          label={(v) => (v >= top ? "all" : `${v} arcs`)}
        />
        <Text size="xs" c="dimmed" style={{ whiteSpace: "nowrap" }}>
          {num(shown)} of {num(left)} arcs
        </Text>
    </Group>
  );
};

/**
 * The toolbar: event categories on the left; arc labels, direction, Arcs (display), compact, reset and the settings
 * button on the right.
 *
 * @param graph The graph as drawn (categories and arc numbers).
 * @param state The settings; `setState` changes them.
 * @param sidebarHidden, onToggleSidebar Whether the sidebar is hidden; shows or hides it.
 */
export const DfgToolbar = ({
  graph,
  state,
  setState,
  sidebarHidden,
  onToggleSidebar,
}: {
  graph: DirectlyFollowsGraph;
  state: DfgState;
  setState: (update: (s: DfgState) => DfgState) => void;
  sidebarHidden: boolean;
  onToggleSidebar: () => void;
}) => (
  <Group justify="space-between" gap={8} wrap="wrap">
    <CategoryChips
      categories={graph.event_categories ?? []}
      excluded={state.excludedCategories}
      onChange={(excludedCategories) => setState((s) => ({ ...s, excludedCategories }))}
    />
    <Group gap={8} wrap="wrap">
      <Tooltip label={INFO.arcLabel} multiline w={260} withinPortal>
        <SegmentedControl
          size="xs"
          aria-label="Arc labels"
          value={state.arcLabel}
          onChange={(v) => setState((s) => ({ ...s, arcLabel: v as ArcLabel }))}
          data={[
            { value: "count", label: "Traversals" },
            { value: "objects", label: "Objects" },
          ]}
        />
      </Tooltip>
      <Tooltip label={INFO.direction} multiline w={260} withinPortal>
        <SegmentedControl
          size="xs"
          aria-label="Direction"
          value={state.direction}
          onChange={(v) => setState((s) => ({ ...s, direction: v as Direction }))}
          data={[
            { value: "RIGHT", label: <ArrowRightIcon size={14} aria-label="Left to right" style={{ display: "block" }} /> },
            { value: "DOWN", label: <ArrowDownIcon size={14} aria-label="Top to bottom" style={{ display: "block" }} /> },
          ]}
        />
      </Tooltip>
      <DisplayArcs graph={graph} state={state} setState={setState} />
      <Tooltip label={INFO.compact} multiline w={260} withinPortal>
        <Switch
          size="xs"
          checked={state.compact}
          onChange={(e) => {
            const compact = e.currentTarget.checked;
            setState((s) => ({ ...s, compact }));
          }}
          label="Compact"
        />
      </Tooltip>
      <Tooltip label={INFO.reset} multiline w={260} withinPortal>
        <Button size="compact-xs" variant="default" leftSection={<RotateCcwIcon size={11} />} onClick={() => setState(() => DEFAULT_STATE)}>
          Reset
        </Button>
      </Tooltip>
      <Tooltip label={INFO.settings} withinPortal>
        <ActionIcon
          size="sm"
          variant={sidebarHidden ? "default" : "light"}
          aria-label={INFO.settings}
          aria-pressed={!sidebarHidden}
          onClick={onToggleSidebar}
        >
          <SlidersHorizontalIcon size={13} />
        </ActionIcon>
      </Tooltip>
    </Group>
  </Group>
);
