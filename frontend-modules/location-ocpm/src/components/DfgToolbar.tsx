// The toolbar above the directly-follows graph (Nina, 2026-11-15): the event categories (deselect one to remove its
// events from the traces), arc labels, direction, compact and reset. The other settings are in the sidebar
// (DfgSettings.tsx). Documented in docs/pages/directly-follows-graph.md, section "Settings".
import { Button, Chip, Group, SegmentedControl, Switch, Tooltip } from "@mantine/core";
import { InfoIcon, RotateCcwIcon } from "lucide-react";
import type { DfgEventCategory } from "../api/locationBasedOcpm";
import type { ArcLabel, Direction } from "../lib/dfgLayout";
import { num } from "../lib/format";
import { DEFAULT_STATE, type DfgState, INFO } from "./DfgSettings";

/** Categories that are part of another one: deselecting the parent removes their events too. */
const PARENT: Record<string, string> = { to_vehicle: "movement", to_storage: "movement" };

/**
 * One chip per event category, all selected by default; clicking one (de)selects it. A sub-category ("Move to
 * vehicle", "Move to storage") is shown deselected and disabled while its parent ("Movements") is deselected.
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
      {categories.map((c) => {
        const parentOff = PARENT[c.key] !== undefined && excluded.includes(PARENT[c.key]);
        return (
          <Chip
            key={c.key}
            size="xs"
            variant="light"
            checked={!excluded.includes(c.key) && !parentOff}
            disabled={parentOff || c.events === 0}
            onChange={(on) => onChange(on ? excluded.filter((k) => k !== c.key) : [...excluded, c.key])}
          >
            {c.label} ({num(c.events)})
          </Chip>
        );
      })}
    <Tooltip label={INFO.categories} multiline w={340} withinPortal>
      <InfoIcon size={12} style={{ opacity: 0.6 }} aria-label="About the event categories" />
    </Tooltip>
  </Group>
);

/**
 * The toolbar: event categories on the left; arc labels, direction, compact and reset on the right.
 *
 * @param categories The event categories of the graph.
 * @param state The settings; `setState` changes them.
 */
export const DfgToolbar = ({
  categories,
  state,
  setState,
}: {
  categories: DfgEventCategory[];
  state: DfgState;
  setState: (update: (s: DfgState) => DfgState) => void;
}) => (
  <Group justify="space-between" gap={8} wrap="wrap">
    <CategoryChips
      categories={categories}
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
            { value: "RIGHT", label: "Left to right" },
            { value: "DOWN", label: "Top to bottom" },
          ]}
        />
      </Tooltip>
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
    </Group>
  </Group>
);
