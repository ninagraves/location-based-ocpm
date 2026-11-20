// Column filter of the HU profile table: the popover behind the filter icon of a column header. Depending on the
// column it offers checkboxes (categories such as object type), a text field (ids), or a range with a slider and
// two input fields (counts, durations, connectedness, timestamps). Documented in docs/pages/instances.md,
// section "HU profile".
import { Button, Checkbox, Group, NumberInput, RangeSlider, ScrollArea, Stack, Text, TextInput } from "@mantine/core";
import { useState } from "react";
import type { ColumnInfo, ProfileFilter, ProfileFilterColumn } from "../api/locationBasedOcpm";
import { num } from "../lib/format";

/** How the values of a column are shown and typed in. */
export type ValueFormat = "count" | "duration" | "share" | "time" | "text";

/** Key of the missing value in the checkbox list. */
const NONE = "\u0000none";

/** Unit of the input fields of a range: durations in hours, shares in %, the rest as stored. */
const factor = (format: ValueFormat) => (format === "duration" ? 3600 : format === "share" ? 0.01 : 1);

/** Suffix of the input fields of a range. */
const suffix = (format: ValueFormat) => (format === "duration" ? " h" : format === "share" ? " %" : "");

/** A timestamp in ms as "YYYY-MM-DD HH:MM" (UTC, like the table). */
const stampMs = (ms: number) => new Date(ms).toISOString().replace("T", " ").slice(0, 16);

/** A filter value as text, e.g. for the active filter pills. */
export const formatValue = (value: number, format: ValueFormat) =>
  format === "time"
    ? stampMs(value)
    : format === "duration"
      ? `${num(Math.round((value / 3600) * 100) / 100)} h`
      : format === "share"
        ? `${Math.round(value * 1000) / 10} %`
        : num(value);

/** A short text of an active filter, e.g. "≥ 1", "coil, slab", "contains c". */
export const filterText = (filter: ProfileFilter, format: ValueFormat) => {
  if (filter.values) return filter.values.map((v) => v ?? "(none)").join(", ");
  if (filter.text) return `contains “${filter.text}”`;
  const { min, max } = filter;
  if (min != null && max != null) return `${formatValue(min, format)} – ${formatValue(max, format)}`;
  if (min != null) return `≥ ${formatValue(min, format)}`;
  if (max != null) return `≤ ${formatValue(max, format)}`;
  return "";
};

/**
 * The filter panel of one column.
 *
 * @param column The column.
 * @param info What the column offers (values or range), from the profile page.
 * @param format How its values are shown.
 * @param value The active filter of the column, if any.
 * @param onChange Called with the new filter, or undefined to remove it.
 * @param close Closes the popover.
 */
export const ProfileColumnFilter = ({
  column,
  info,
  format,
  value,
  onChange,
  close,
}: {
  column: ProfileFilterColumn;
  info: ColumnInfo | undefined;
  format: ValueFormat;
  value: ProfileFilter | undefined;
  onChange: (filter: ProfileFilter | undefined) => void;
  close: () => void;
}) => {
  const apply = (filter: ProfileFilter | undefined) => {
    onChange(filter);
    close();
  };
  const buttons = (filter: ProfileFilter | undefined) => (
    <Group justify="space-between" gap="xs">
      <Button size="compact-xs" variant="subtle" onClick={() => apply(undefined)} disabled={!value}>
        Clear
      </Button>
      <Button size="compact-xs" onClick={() => apply(filter)}>
        Apply
      </Button>
    </Group>
  );
  if (!info)
    return (
      <Text size="xs" c="dimmed">
        Loading…
      </Text>
    );
  if (info.kind === "category") return <CategoryFilter column={column} info={info} value={value} buttons={buttons} />;
  if (info.kind === "text") return <TextFilter column={column} value={value} buttons={buttons} />;
  return <RangeFilter column={column} info={info} format={format} value={value} buttons={buttons} />;
};

type PanelProps = {
  column: ProfileFilterColumn;
  value: ProfileFilter | undefined;
  buttons: (filter: ProfileFilter | undefined) => React.ReactNode;
};

/** Checkboxes, one per value (most frequent first) with its number of handling units. */
const CategoryFilter = ({ column, info, value, buttons }: PanelProps & { info: ColumnInfo }) => {
  const values = info.values ?? [];
  const [picked, setPicked] = useState<string[]>((value?.values ?? []).map((v) => v ?? NONE));
  const [search, setSearch] = useState("");
  const shown = values.filter(([v]) => (v ?? "(none)").toLowerCase().includes(search.toLowerCase()));
  const filter = picked.length ? { column, values: picked.map((v) => (v === NONE ? null : v)) } : undefined;
  return (
    <Stack gap="xs" w={240}>
      {values.length > 8 && (
        <TextInput size="xs" placeholder="Search values" value={search} onChange={(e) => setSearch(e.currentTarget.value)} />
      )}
      <ScrollArea.Autosize mah={240}>
        <Checkbox.Group value={picked} onChange={setPicked}>
          <Stack gap={4}>
            {shown.map(([v, n]) => (
              <Checkbox key={v ?? NONE} size="xs" value={v ?? NONE} label={`${v ?? "(none)"} (${num(n)})`} />
            ))}
          </Stack>
        </Checkbox.Group>
      </ScrollArea.Autosize>
      {buttons(filter)}
    </Stack>
  );
};

/** A text field: keep rows whose value contains the text. */
const TextFilter = ({ column, value, buttons }: PanelProps) => {
  const [text, setText] = useState(value?.text ?? "");
  return (
    <Stack gap="xs" w={220}>
      <TextInput size="xs" label="Contains" value={text} onChange={(e) => setText(e.currentTarget.value)} data-autofocus />
      {buttons(text ? { column, text } : undefined)}
    </Stack>
  );
};

/**
 * A range: slider over all values of the column and two input fields (from, to). Durations are typed in hours,
 * connectedness in %; timestamps only by the slider.
 */
const RangeFilter = ({ column, info, format, value, buttons }: PanelProps & { info: ColumnInfo; format: ValueFormat }) => {
  const lo = info.min ?? 0;
  const hi = info.max ?? 0;
  const [range, setRange] = useState<[number, number]>([value?.min ?? lo, value?.max ?? hi]);
  const f = factor(format);
  const step = format === "count" ? 1 : format === "share" ? 0.01 : format === "time" ? 60_000 : Math.max((hi - lo) / 200, 1);
  // Bounds equal to the column's minimum or maximum are left out, so the filter keeps every row on that side.
  const filter =
    range[0] > lo || range[1] < hi
      ? {
          column,
          min: range[0] > lo ? range[0] : null,
          max: range[1] < hi ? range[1] : null,
        }
      : undefined;
  const input = (i: 0 | 1, label: string) => (
    <NumberInput
      size="xs"
      label={label}
      w={110}
      value={Math.round((range[i] / f) * 100) / 100}
      suffix={suffix(format)}
      decimalScale={format === "count" ? 0 : 2}
      onChange={(v) => {
        if (typeof v !== "number") return;
        const next: [number, number] = [...range];
        next[i] = v * f;
        setRange(next);
      }}
    />
  );
  return (
    <Stack gap="xs" w={280}>
      {hi > lo ? (
        <RangeSlider
          size="sm"
          min={lo}
          max={hi}
          step={step}
          minRange={0}
          value={range}
          onChange={setRange}
          label={(v) => formatValue(v, format)}
        />
      ) : (
        <Text size="xs" c="dimmed">
          All handling units have the same value ({formatValue(lo, format)}).
        </Text>
      )}
      {format === "time" ? (
        <Text size="xs">{`${stampMs(range[0])} – ${stampMs(range[1])}`}</Text>
      ) : (
        <Group gap="xs">
          {input(0, "From")}
          {input(1, "To")}
        </Group>
      )}
      <Text size="xs" c="dimmed">{`All handling units: ${formatValue(lo, format)} – ${formatValue(hi, format)}`}</Text>
      {buttons(filter)}
    </Stack>
  );
};
