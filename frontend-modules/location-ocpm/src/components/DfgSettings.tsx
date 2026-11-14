// The settings sidebar of the directly-follows graph page: every setting of the page is here (and only here).
// Each setting is documented in docs/pages/directly-follows-graph.md, section "Settings".
import {
  Badge,
  Box,
  Button,
  Card,
  Checkbox,
  Divider,
  Group,
  ScrollArea,
  SegmentedControl,
  Slider,
  Stack,
  Text,
  Tooltip,
} from "@mantine/core";
import { InfoIcon, RotateCcwIcon } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import type { DfgObjectType, TypeSetting } from "../api/locationBasedOcpm";
import type { ArcLabel, Direction } from "../lib/dfgLayout";
import { num } from "../lib/format";

/** Hover texts of the settings (short versions of the documentation). */
export const INFO = {
  objectTypes:
    "Checked object types are drawn with their directly-follows arcs, start and end nodes. Unchecked object types that are involved in the shown events appear only as circles on the activity nodes. Default: the object types of the handling units.",
  paths:
    "Path threshold: keeps the most frequent paths (activity sequences of the objects) of this type until they cover at least this share of its objects. Only kept objects contribute to arcs and frequencies. 100 % keeps all.",
  arcs: "Arc threshold: keeps an arc only if at least this share of the (path-filtered) objects of this type traverse it. 0 % keeps all.",
  arcLabel: "What the number on an arc counts: traversals (an object repeating the arc counts each time) or distinct objects.",
  direction: "Direction of the layout: from left to right or from top to bottom.",
};

/** Heading with a hover text. */
const Heading = ({ children, info }: { children: ReactNode; info: string }) => (
  <Group gap={4}>
    <Text size="sm" fw={600}>{children}</Text>
    <Tooltip label={info} multiline w={300} withinPortal>
      <InfoIcon size={13} style={{ opacity: 0.6 }} />
    </Tooltip>
  </Group>
);

/** Colour swatch of an object type: a short line (selected, drawn as arcs) or a circle (not selected). */
export const Swatch = ({ colour, circle }: { colour?: string; circle?: boolean }) => (
  <Box
    style={
      circle
        ? { width: 10, height: 10, borderRadius: "50%", background: colour, flexShrink: 0 }
        : { width: 16, height: 4, borderRadius: 2, background: colour, flexShrink: 0 }
    }
  />
);

/** A threshold slider that only reports its value when released (so dragging does not send a request per step). */
const ThresholdSlider = ({ value, onCommit, label }: { value: number; onCommit: (v: number) => void; label: string }) => {
  const [local, setLocal] = useState(value);
  useEffect(() => setLocal(value), [value]);
  return (
    <Slider
      aria-label={label}
      size="sm"
      min={0}
      max={100}
      step={1}
      value={local}
      onChange={setLocal}
      onChangeEnd={onCommit}
      label={(v) => `${v} %`}
    />
  );
};

/** Path and arc threshold of one selected object type, with what they keep. */
const TypeThresholds = ({
  type,
  colour,
  onChange,
}: {
  type: DfgObjectType;
  colour?: string;
  onChange: (setting: TypeSetting) => void;
}) => {
  const path = type.path_threshold ?? 100;
  const arc = type.arc_threshold ?? 0;
  return (
    <Stack gap={4}>
      <Group gap={6} wrap="nowrap">
        <Swatch colour={colour} />
        <Text size="sm" fw={600} truncate>{type.object_type}</Text>
      </Group>
      <Group justify="space-between" gap={4}>
        <Heading info={INFO.paths}>Paths {path} %</Heading>
        <Text size="xs" c="dimmed">
          {num(type.kept_paths)} of {num(type.paths)} paths · {num(type.kept_objects)} of {num(type.objects)} objects
        </Text>
      </Group>
      <ThresholdSlider label={`Path threshold ${type.object_type}`} value={path} onCommit={(v) => onChange({ object_type: type.object_type, path_threshold: v, arc_threshold: arc })} />
      <Group justify="space-between" gap={4} mt={4}>
        <Heading info={INFO.arcs}>Arcs {arc} %</Heading>
        <Text size="xs" c="dimmed">
          {num(type.kept_arcs)} of {num(type.arcs)} arcs
        </Text>
      </Group>
      <ThresholdSlider label={`Arc threshold ${type.object_type}`} value={arc} onCommit={(v) => onChange({ object_type: type.object_type, path_threshold: path, arc_threshold: v })} />
    </Stack>
  );
};

/**
 * The sidebar: object type selection, per selected type its path and arc threshold, arc labels, direction,
 * and the legend of the symbols.
 *
 * @param objectTypes All object types of the log with their state (from the last graph).
 * @param colours Colour per object type.
 * @param onSelection New selection (selected types with their thresholds), or null for the default.
 */
export const DfgSettings = ({
  objectTypes,
  colours,
  onSelection,
  arcLabel,
  onArcLabel,
  direction,
  onDirection,
}: {
  objectTypes: DfgObjectType[];
  colours: Map<string, string>;
  onSelection: (selection: TypeSetting[] | null) => void;
  arcLabel: ArcLabel;
  onArcLabel: (label: ArcLabel) => void;
  direction: Direction;
  onDirection: (direction: Direction) => void;
}) => {
  const current = (): TypeSetting[] =>
    objectTypes
      .filter((t) => t.selected)
      .map((t) => ({ object_type: t.object_type, path_threshold: t.path_threshold ?? 100, arc_threshold: t.arc_threshold ?? 0 }));
  const toggle = (objectType: string, checked: boolean) => {
    const rest = current().filter((s) => s.object_type !== objectType);
    onSelection(checked ? [...rest, { object_type: objectType, path_threshold: 100, arc_threshold: 0 }] : rest);
  };
  const update = (setting: TypeSetting) =>
    onSelection(current().map((s) => (s.object_type === setting.object_type ? setting : s)));
  const selected = objectTypes.filter((t) => t.selected);

  return (
    <Card withBorder padding="sm">
      <Stack gap="sm">
        <Heading info={INFO.objectTypes}>Object types</Heading>
        <ScrollArea.Autosize mah={240} type="auto" offsetScrollbars>
          <Stack gap={6}>
            {objectTypes.map((t) => (
              <Checkbox
                key={t.object_type}
                size="xs"
                checked={t.selected}
                onChange={(e) => toggle(t.object_type, e.currentTarget.checked)}
                label={
                  <Group gap={6} wrap="nowrap">
                    <Swatch colour={colours.get(t.object_type)} circle={!t.selected} />
                    <Text size="sm">{t.object_type}</Text>
                    <Text size="xs" c="dimmed">({num(t.objects)})</Text>
                    {t.handling_units && (
                      <Badge size="xs" variant="light">HU</Badge>
                    )}
                  </Group>
                }
              />
            ))}
          </Stack>
        </ScrollArea.Autosize>
        <Button size="xs" variant="default" leftSection={<RotateCcwIcon size={12} />} onClick={() => onSelection(null)}>
          Reset to handling-unit types
        </Button>

        {selected.length > 0 && <Divider label="Thresholds per object type" labelPosition="left" />}
        <ScrollArea.Autosize mah={380} type="auto" offsetScrollbars>
          <Stack gap="md">
            {selected.map((t) => (
              <TypeThresholds key={t.object_type} type={t} colour={colours.get(t.object_type)} onChange={update} />
            ))}
          </Stack>
        </ScrollArea.Autosize>

        <Divider label="Display" labelPosition="left" />
        <Heading info={INFO.arcLabel}>Arc labels</Heading>
        <SegmentedControl
          size="xs"
          value={arcLabel}
          onChange={(v) => onArcLabel(v as ArcLabel)}
          data={[
            { value: "count", label: "Traversals" },
            { value: "objects", label: "Objects" },
          ]}
        />
        <Heading info={INFO.direction}>Direction</Heading>
        <SegmentedControl
          size="xs"
          value={direction}
          onChange={(v) => onDirection(v as Direction)}
          data={[
            { value: "RIGHT", label: "Left to right" },
            { value: "DOWN", label: "Top to bottom" },
          ]}
        />

        <Divider label="Legend" labelPosition="left" />
        <Stack gap={4}>
          <Text size="xs">▶ in a circle: start of an object type · ■ in a circle: end; named below.</Text>
          <Text size="xs">Line: directly-follows arc of a checked object type (thicker = more traversals).</Text>
          <Text size="xs">Small circle on an activity: an unchecked object type is involved in its events.</Text>
          <Text size="xs">Number in an activity: its frequency (events shown).</Text>
        </Stack>
      </Stack>
    </Card>
  );
};
