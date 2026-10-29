// Key numbers tiles of the overview page. Documented in docs/pages/overview.md, section "Key numbers".
import { Alert, Card, Group, Loader, SimpleGrid, Text } from "@mantine/core";
import type { ReactNode } from "react";
import { useGetKeyNumbers } from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import { filterParams, filterRequest, usePageFilter } from "../lib/filters";
import { num, pct } from "../lib/format";
import { UI } from "../lib/palette";
import { useScheme } from "./plots";
import { ShortList } from "./ShortList";

/** One tile: label, big number (whole log), filtered value (if filtered), small grey line. */
const Tile = ({ label, value, filtered, sub }: { label: string; value: ReactNode; filtered?: ReactNode; sub?: ReactNode }) => {
  const scheme = useScheme();
  return (
    <Card withBorder padding="sm">
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

/**
 * The six key number tiles: big numbers for the whole log at the selected level, and with an
 * active page filter the filtered values next to them, smaller and in the accent colour.
 */
export const KeyNumbers = ({ ocelId }: { ocelId: string }) => {
  const [filter] = usePageFilter(ocelId);
  const { data, error } = useGetKeyNumbers(ocelId, filterParams(filter), { request: filterRequest });
  if (error) return <Alert color="red">{errorText(error)}</Alert>;
  if (!data) return <Loader size="sm" />;
  const f = data.filtered ?? undefined;
  return (
    <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }} spacing="sm">
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
        label="Locations"
        value={num(data.locations)}
        filtered={f && num(f.locations)}
        sub={`target ${num(data.target_locations)} · pickup ${num(data.pickup_locations)}`}
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
    </SimpleGrid>
  );
};
