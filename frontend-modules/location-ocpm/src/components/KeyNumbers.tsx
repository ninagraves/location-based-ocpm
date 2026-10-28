// Key numbers tiles of the overview page. Documented in docs/pages/overview.md, section "Key numbers".
import { Alert, Card, Loader, SimpleGrid, Text } from "@mantine/core";
import type { ReactNode } from "react";
import { useGetKeyNumbers } from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import { num, pct } from "../lib/format";

/** One tile: label, big number, small grey line. */
const Tile = ({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) => (
  <Card withBorder padding="sm">
    <Text size="xs" c="dimmed">
      {label}
    </Text>
    <Text fw={700} size="xl">
      {value}
    </Text>
    {sub && (
      <Text size="xs" c="dimmed">
        {sub}
      </Text>
    )}
  </Card>
);

/** The six key number tiles of the whole log at the selected level. */
export const KeyNumbers = ({ ocelId }: { ocelId: string }) => {
  const { data, error } = useGetKeyNumbers(ocelId);
  if (error) return <Alert color="red">{errorText(error)}</Alert>;
  if (!data) return <Loader size="sm" />;
  return (
    <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }} spacing="sm">
      <Tile
        label="Handling units"
        value={num(data.handling_units)}
        sub={data.handling_units_per_type.map((t) => `${t.object_type} ${num(t.count)}`).join(" · ")}
      />
      <Tile
        label="Agreed located events"
        value={`${num(data.agreed_located_events)} of ${num(data.events)}`}
        sub={pct(data.agreed_located_events / data.events)}
      />
      <Tile
        label="Relations with a known location"
        value={`${num(data.located_relations)} of ${num(data.relations)}`}
        sub={`${pct(data.located_relations / data.relations)} · loc at Level ${data.level}`}
      />
      <Tile label="Movement events" value={num(data.movement_events)} sub="provided" />
      <Tile
        label="Locations"
        value={num(data.locations)}
        sub={`target ${num(data.target_locations)} · pickup ${num(data.pickup_locations)}`}
      />
      <Tile
        label="Transformation events"
        value={num(data.transformation_events)}
        sub={data.transformation_events === null || data.transformation_events === undefined ? "no transformation events configured" : undefined}
      />
    </SimpleGrid>
  );
};
