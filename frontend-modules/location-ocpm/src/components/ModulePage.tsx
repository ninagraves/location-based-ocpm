// The frame of every page of the module: title, the configuration (Configuration page only), the settings bar
// (every page), then the page's content. Documented in docs/pages/configuration.md and docs/pages/settings-bar.md.
import { Alert, Button, Card, Group, Loader, Stack, Text, Title } from "@mantine/core";
import { getModuleRoute, useCurrentOcel } from "@ocelescope/core";
import { DownloadIcon, SettingsIcon } from "lucide-react";
import { useRouter } from "next/router";
import { type ReactNode, useEffect } from "react";
import { type DerivationConfig, useGetConfig, useGetStatus } from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import { useKeptScroll } from "../lib/keptView";
import { usePageState } from "../lib/pageState";
import { useKeptAnswers } from "../lib/queries";
import { ConfigForm, downloadJson, Notices } from "./ConfigForm";
import { SettingsBar } from "./SettingsBar";
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
 * e.g. 'handling units coil, slab; locations from "to_loc"'. The level is in the settings bar. More than five
 * object types are shortened to the first five (in the order selected) and "+ n more".
 */
export const SummaryLine = ({ config }: { config: DerivationConfig }) => {
  const hu = config.handling_units;
  const context = contextParts(config);
  return (
    <>
      handling units {"table" in hu ? `from table "${hu.table}"` : <ShortList items={hu.object_types} separator=", " />};
      locations {locationSource(config.target_locations)}
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
  // Whether the transformation events count too is the settings bar's choice, so only the selection is named.
  if (processing?.selection) parts.push(`processing operations ${sourceOf(processing.selection)}`);
  return parts;
};

/** Route of the Configuration page (module "locationBasedOcpm", route "configuration" in `index.ts`). */
const CONFIGURATION_ROUTE = getModuleRoute({ moduleName: "locationBasedOcpm", routeName: "configuration" });

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
 * A page of the module: title; on the Configuration page (`configuration`) the configuration summary with "Edit
 * configuration", or the form while no configuration is applied or while editing; on every page the settings bar
 * (`SettingsBar`, once a configuration is applied); then the page's content. Other pages open the Configuration
 * page instead while no configuration is applied for the log (Nina, 2026-11-20: Ocelescope 0.13 cannot hide
 * sidebar entries, so the pages stay listed but redirect). Every page opens again as it was left: scroll position
 * (`useKeptScroll`), editing state, and the answers of its requests (`useKeptAnswers`); see
 * docs/hosting/state-and-caching.md, section "Page state".
 */
export const ModulePage = ({
  title,
  configuration = false,
  children,
}: {
  title: string;
  /** True on the Configuration page: show the configuration summary and form. */
  configuration?: boolean;
  children: (context: PageContext) => ReactNode;
}) => {
  const { id: ocelId } = useCurrentOcel();
  const { data: state, isLoading, error } = useGetConfig(ocelId ?? "", { query: { enabled: !!ocelId } });
  // Kept across page switches like the rest of the page (the form keeps its unapplied changes, `ConfigForm`).
  const [editingKept, setEditing] = usePageState(`config.editing.${ocelId}`, false);
  // Only the Configuration page has the form; other pages show their content meanwhile.
  const editing = configuration && editingKept;
  const config = state?.config;
  const router = useRouter();
  // Answers of the module's requests stay in the browser for a while, so a page opened again shows them at once.
  useKeptAnswers();
  // The page opens again where it was scrolled to (per page and log).
  const scrollAnchor = useKeptScroll<HTMLDivElement>(`scroll.${ocelId}.${router.asPath.split(/[?#]/)[0]}`);
  const unconfigured = !configuration && !!ocelId && !isLoading && !error && !!state && !config;

  useEffect(() => {
    // `replace`, not `push`: "back" then skips the page that could not be shown.
    if (unconfigured) void router.replace(CONFIGURATION_ROUTE);
  }, [unconfigured, router]);

  let header: ReactNode;
  if (!ocelId) header = <Alert color="gray">Select an event log to start.</Alert>;
  else if (isLoading) header = <Loader size="sm" />;
  else if (error) header = <Alert color="red">{errorText(error)}</Alert>;
  else if (!configuration)
    // Shown only for the moment until the redirect to the Configuration page has happened.
    header = config ? null : <Loader size="sm" />;
  else if (config && !editing)
    header = (
      <Stack gap="xs">
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
        {/* Notices of the current derivation (e.g. unmapped locations), as grey lines below the summary. */}
        <Notices notices={state?.notices} />
      </Stack>
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
    <Stack ref={scrollAnchor} p="md" gap="lg">
      <Group justify="space-between" align="flex-end">
        <Title order={2}>{title}</Title>
        <Versions />
      </Group>
      {header}
      {ocelId && config && !editing && <SettingsBar ocelId={ocelId} />}
      {ocelId && config && !editing && children({ ocelId, config })}
    </Stack>
  );
};
