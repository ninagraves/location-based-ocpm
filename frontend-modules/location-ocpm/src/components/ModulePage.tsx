// The frame of every page of the module: title, shared header, then the page's content.
// The shared header is documented in docs/pages/configuration.md.
import { Alert, Button, Card, Group, Loader, Stack, Text, Title } from "@mantine/core";
import { useCurrentOcel } from "@ocelescope/core";
import { SettingsIcon } from "lucide-react";
import { type ReactNode, useState } from "react";
import { type DerivationConfig, useGetConfig, useGetStatus } from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import { ConfigForm, Notices } from "./ConfigForm";

export { errorText };

/** What a page's content gets from the frame. */
export type PageContext = {
  ocelId: string;
  config: DerivationConfig;
};

const quote = (values: string[]) => values.map((v) => `"${v}"`).join(", ");

/** Where the target locations come from, in a few words. */
const locationSource = (locations: DerivationConfig["target_locations"]) => {
  if ("qualifiers" in locations) return `from qualifier ${quote(locations.qualifiers)}`;
  if ("table" in locations) return `from table "${locations.table}"`;
  return `from "${locations.attribute}"`;
};

/**
 * The configuration summary in one line (overview/Deriving Locations.md, "shared header"),
 * e.g. 'handling units coil, slab; locations from "to_loc"; Level 3'.
 */
export const summaryLine = (config: DerivationConfig) => {
  const hu = config.handling_units;
  const handlingUnits = "table" in hu ? `from table "${hu.table}"` : hu.object_types.join(", ");
  return `handling units ${handlingUnits}; locations ${locationSource(config.target_locations)}; Level ${config.level ?? 3}`;
};

/** Backend versions, as a small grey line (confirms the connection). */
const Versions = () => {
  const { data: status, error } = useGetStatus();
  if (error)
    return (
      <Text size="sm" c="red">
        Backend not reachable: {errorText(error)}
      </Text>
    );
  return status ? (
    <Text size="xs" c="dimmed">
      Backend module {status.module_version}, Ocelescope {status.ocelescope_version}
    </Text>
  ) : null;
};

/**
 * A page of the module: title, the shared header (configuration summary with "Edit
 * configuration", or the form while no configuration is applied or while editing), then
 * the page's content once a configuration is applied.
 */
export const ModulePage = ({ title, children }: { title: string; children: (context: PageContext) => ReactNode }) => {
  const { id: ocelId } = useCurrentOcel();
  const { data: state, isLoading, error } = useGetConfig(ocelId ?? "", { query: { enabled: !!ocelId } });
  const [editing, setEditing] = useState(false);
  const config = state?.config;

  let header: ReactNode;
  if (!ocelId) header = <Alert color="gray">Select an event log to start.</Alert>;
  else if (isLoading) header = <Loader size="sm" />;
  else if (error) header = <Alert color="red">{errorText(error)}</Alert>;
  else if (config && !editing)
    header = (
      <Card withBorder padding="xs">
        <Stack gap={4}>
          <Group justify="space-between">
            <Text size="sm">Configuration: {summaryLine(config)}.</Text>
            <Button size="xs" variant="default" leftSection={<SettingsIcon size={14} />} onClick={() => setEditing(true)}>
              Edit configuration
            </Button>
          </Group>
          <Notices notices={state?.notices} />
        </Stack>
      </Card>
    );
  else
    header = (
      <Card withBorder padding="md">
        <ConfigForm
          key={ocelId}
          ocelId={ocelId}
          initial={config}
          onApplied={() => setEditing(false)}
          onCancel={config ? () => setEditing(false) : undefined}
        />
      </Card>
    );

  return (
    <Stack p="md" gap="lg">
      <Group justify="space-between" align="flex-end">
        <Title order={2}>{title}</Title>
        <Versions />
      </Group>
      {header}
      {ocelId && config && !editing && children({ ocelId, config })}
    </Stack>
  );
};
