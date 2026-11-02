// The frame of every page of the module: title, shared header, then the page's content.
// The shared header is documented in docs/pages/configuration.md.
import { Alert, Button, Card, Group, Loader, Stack, Text, Title } from "@mantine/core";
import { useCurrentOcel } from "@ocelescope/core";
import { DownloadIcon, SettingsIcon } from "lucide-react";
import { type ReactNode, useState } from "react";
import { type DerivationConfig, useGetConfig, useGetStatus } from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import { ConfigForm, downloadJson } from "./ConfigForm";
import { ShortList } from "./ShortList";

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
 * e.g. 'handling units coil, slab; locations from "to_loc"; Level 3'. More than five
 * object types are shortened to the first five (in the order selected) and "+ n more".
 */
export const SummaryLine = ({ config }: { config: DerivationConfig }) => {
  const hu = config.handling_units;
  const context = contextParts(config);
  return (
    <>
      handling units {"table" in hu ? `from table "${hu.table}"` : <ShortList items={hu.object_types} separator=", " />};
      locations {locationSource(config.target_locations)}; Level {config.level ?? 3}
      {context.map((part) => `; ${part}`).join("")}
    </>
  );
};

/** Where an input of the location context comes from, in a few words (e.g. 'from table "locations.csv"'). */
const sourceOf = (input: object): string => {
  const option = input as Record<string, unknown>;
  switch (option.option) {
    case "table":
      return `from table "${option.table}"`;
    case "event_attributes":
      return `from "${option.low_attribute}" and "${option.high_attribute}"`;
    case "object_attribute":
      return `from object attribute "${option.attribute}"`;
    case "o2o":
      return `from o2o ${quote(option.qualifiers as string[])}`;
    case "pattern":
      return `by pattern ${option.pattern}`;
    case "locations":
      return (option.locations as string[]).join(", ");
    case "attribute_values":
      return `targets of "${option.attribute}" = ${quote(option.values as string[])}`;
    case "object_types":
      return `object types ${quote(option.object_types as string[])}`;
    case "activities":
      return (option.activities as string[]).join(", ");
    case "qualifiers":
      return `qualifiers ${quote(option.qualifiers as string[])}`;
    default:
      return "";
  }
};

/** Summary parts of the configured location-context inputs (overview/module/Module Overview.md, section 1). */
const contextParts = (config: DerivationConfig): string[] => {
  const parts: string[] = [];
  if (config.high_level_locations) parts.push(`high-level locations ${sourceOf(config.high_level_locations)}`);
  if (config.vehicles) parts.push(`vehicles ${sourceOf(config.vehicles)}`);
  if (config.storage_units) parts.push(`storage units ${sourceOf(config.storage_units)}`);
  const processing = config.processing_operations;
  if (processing) {
    const selected = processing.selection ? sourceOf(processing.selection) : "";
    const withT = processing.include_transformations !== false;
    parts.push(
      `processing operations: ${[withT ? "transformation events" : "", selected].filter(Boolean).join(" and ") || "none"}`,
    );
  }
  return parts;
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
        <Group justify="space-between">
          <Text size="sm">Configuration: <SummaryLine config={config} />.</Text>
          <Group gap="xs">
            <Button size="xs" variant="default" leftSection={<DownloadIcon size={14} />} onClick={() => downloadJson(config)}>
              Download configuration
            </Button>
            <Button size="xs" variant="default" leftSection={<SettingsIcon size={14} />} onClick={() => setEditing(true)}>
              Edit configuration
            </Button>
          </Group>
        </Group>
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
