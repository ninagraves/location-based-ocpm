// Key numbers tiles of the overview page. Documented in docs/pages/overview.md, section "Key numbers".
import { Alert, Card, Group, Loader, SimpleGrid, Text } from "@mantine/core";
import type { ReactNode } from "react";
import { type KeyNumbers as KeyNumbersData, useGetKeyNumbers } from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import { filterParams, filterRequest, usePageFilter } from "../lib/filters";
import { num, pct } from "../lib/format";
import { UI } from "../lib/palette";
import { useScheme } from "./plots";
import { ShortList } from "./ShortList";

/** One tile: label, big number (whole log), filtered value (if filtered), small grey line; `hint` on hover. */
const Tile = ({
  label,
  value,
  filtered,
  sub,
  hint,
}: {
  label: string;
  value: ReactNode;
  filtered?: ReactNode;
  sub?: ReactNode;
  hint?: string;
}) => {
  const scheme = useScheme();
  return (
    <Card withBorder padding="sm" title={hint}>
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Group gap={6} align="baseline">
        <Text fw={700} size="xl">
          {value}
        </Text>
        {filtered !== undefined && (
          <Text fw={600} size="sm" c={UI[scheme].accent} title="with the page filters">
            ({filtered})
          </Text>
        )}
      </Group>
      {sub && (
        <Text size="xs" c="dimmed">
          {sub}
        </Text>
      )}
    </Card>
  );
};

/** The small line of the Locations tile: targets and pickups in the mode, then the other level, V and W. */
const locationLine = (data: KeyNumbersData) => {
  const high = data.location_mode === "high";
  const parts = [`target ${num(data.target_locations)}`, `pickup ${num(data.pickup_locations)}`];
  if (data.other_level_locations != null) parts.push(`${high ? "low-level" : "high-level"} ${num(data.other_level_locations)}`);
  if (data.vehicles != null) parts.push(`vehicles ${num(data.vehicles)}`);
  if (data.storage_units != null) parts.push(`storage units ${num(data.storage_units)}`);
  return parts.join(" · ");
};

/**
 * The seven key number tiles: big numbers for the whole log at the selected level, and with an
 * active page filter the filtered values next to them, smaller and in the accent colour. Locations and agreed
 * located events follow the switch "Locations: low | high".
 */
export const KeyNumbers = ({ ocelId }: { ocelId: string }) => {
  const [filter] = usePageFilter(ocelId);
  const { data, error } = useGetKeyNumbers(ocelId, filterParams(filter), { request: filterRequest });
  if (error) return <Alert color="red">{errorText(error)}</Alert>;
  if (!data) return <Loader size="sm" />;
  const f = data.filtered ?? undefined;
  return (
    <SimpleGrid cols={{ base: 2, sm: 4, lg: 7 }} spacing="sm">
      <Tile
        label="Handling units"
        value={num(data.handling_units)}
        filtered={f && num(f.handling_units)}
        sub={<ShortList items={data.handling_units_per_type.map((t) => `${t.object_type} ${num(t.count)}`)} />}
      />
      <Tile
        label="Agreed located events"
        value={`${num(data.agreed_located_events)} of ${num(data.events)}`}
        filtered={f && num(f.agreed_located_events)}
        sub={pct(data.agreed_located_events / data.events)}
        hint={
          data.location_mode === "low" && data.agreed_high_level_only
            ? `+${num(data.agreed_high_level_only)} agreeing at high level only`
            : data.location_mode === "high"
              ? "agreement under the high-level locations"
              : undefined
        }
      />
      <Tile
        label="Relations with a known location"
        value={`${num(data.located_relations)} of ${num(data.relations)}`}
        filtered={f && `${num(f.located_relations)} of ${num(f.relations)}`}
        sub={pct(data.located_relations / data.relations)}
      />
      <Tile
        label="Movement events"
        value={num(data.movement_events)}
        filtered={f && num(f.movement_events)}
        sub={<ShortList items={data.movement_activities.map((a) => `${a.activity} ${num(a.count)}`)} limit={3} />}
      />
      <Tile
        label={data.location_mode === "high" ? "High-level locations" : "Locations"}
        value={num(data.locations)}
        filtered={f && num(f.locations)}
        sub={locationLine(data)}
      />
      <Tile
        label="Transformation events"
        value={num(data.transformation_events)}
        filtered={f && data.transformation_events !== null && data.transformation_events !== undefined ? num(f.transformation_events) : undefined}
        sub={
          data.transformation_events === null || data.transformation_events === undefined ? (
            "no transformation events configured"
          ) : data.transformation_activities.length > 0 ? (
            <ShortList items={data.transformation_activities.map((a) => `${a.activity} ${num(a.count)}`)} limit={3} />
          ) : undefined
        }
      />
      <Tile
        label="Processing operations"
        value={num(data.processing_operations ?? 0)}
        filtered={f && num(f.processing_operations ?? 0)}
        hint={data.processing_default ? "default: the transformation events" : undefined}
        sub={
          data.processing_activities?.length ? (
            <ShortList items={data.processing_activities.map((a) => `${a.activity} ${num(a.count)}`)} limit={3} />
          ) : (
            "no processing operations"
          )
        }
      />
    </SimpleGrid>
  );
};
