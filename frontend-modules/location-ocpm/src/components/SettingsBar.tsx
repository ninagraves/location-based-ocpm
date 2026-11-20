// The settings bar, on top of every page (Nina, 2026-11-20). Every change applies to all pages. Level and
// "transformation events are processing operations" are only set here (not in the configuration form).
// Documented in docs/pages/settings-bar.md.
import { Alert, Card, Group, Loader, SegmentedControl, Select, Stack, Switch, Text, Tooltip } from "@mantine/core";
import { type ReactNode, useState } from "react";
import type { SettingsResult } from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import { useChangeSettings, useGlobalSettings } from "../lib/settings";
import { INFO as FORM_INFO, LEVELS, MessageLine } from "./ConfigForm";

/** Hover texts of the settings. */
const INFO = {
  processing: "On: the processing operations P are the selected processing events and all transformation events. Off: only the selected ones.",
  high: "High: the provided high-level locations agg. Low: every location is its own high-level location (identity), on every page.",
  noHigh: "No high-level locations are configured, so every location is its own high-level location (low).",
};

/** A labelled control of the bar, with its hover text. */
const Setting = ({ label, info, children }: { label: string; info: ReactNode; children: ReactNode }) => (
  <Group gap={6} wrap="nowrap">
    <Tooltip label={info} multiline w={320} withArrow>
      <Text size="xs" c="dimmed" style={{ cursor: "help" }}>
        {label}
      </Text>
    </Tooltip>
    {children}
  </Group>
);

/**
 * The settings bar of a log: location function (Level 0-3), "Transformation events are processing operations" and
 * "Locations: low | high" (high only if high-level locations are configured; default high then). A change is sent
 * to the backend (`PUT /{ocel_id}/settings`), which derives with it; every page then reloads its content. Blocking
 * errors of a change are shown below the bar, and the previous settings stay.
 */
export const SettingsBar = ({ ocelId }: { ocelId: string }) => {
  const { data: settings, error } = useGlobalSettings(ocelId);
  const [result, setResult] = useState<SettingsResult | null>(null);
  const { change, isPending, error: changeError } = useChangeSettings(ocelId, setResult);
  if (error) return <Alert color="red">{errorText(error)}</Alert>;
  if (!settings?.configured) return null;
  const highAvailable = !!settings.high_level_available;
  const mode = (
    <SegmentedControl
      size="xs"
      data={[
        { value: "low", label: "low" },
        { value: "high", label: "high", disabled: !highAvailable },
      ]}
      value={settings.location_mode ?? "low"}
      disabled={isPending}
      onChange={(v) => change({ location_mode: v as "low" | "high" })}
    />
  );
  return (
    <Card withBorder padding="xs">
      <Stack gap={4}>
        <Group gap="lg" wrap="wrap">
          <Text size="sm" fw={600}>
            Settings
          </Text>
          <Setting label="Location function" info={FORM_INFO.level}>
            <Select
              size="xs"
              w={300}
              data={LEVELS}
              value={String(settings.level ?? 3)}
              disabled={isPending}
              allowDeselect={false}
              onChange={(v) => v !== null && change({ level: Number(v) as 0 | 1 | 2 | 3 })}
            />
          </Setting>
          <Setting label="Transformation events are processing operations" info={INFO.processing}>
            <Switch
              size="xs"
              checked={settings.include_transformations ?? true}
              disabled={isPending}
              onChange={(e) => change({ include_transformations: e.currentTarget.checked })}
            />
          </Setting>
          <Setting label="Locations:" info={highAvailable ? INFO.high : INFO.noHigh}>
            {highAvailable ? (
              mode
            ) : (
              <Tooltip label={INFO.noHigh} multiline w={320} withArrow>
                <span>{mode}</span>
              </Tooltip>
            )}
          </Setting>
          {isPending && <Loader size="xs" />}
        </Group>
        {changeError && (
          <Text size="sm" c="red">
            {errorText(changeError)}
          </Text>
        )}
        {result && !result.applied && (
          <Stack gap={2}>
            <Text size="sm" c="red">
              The change was not applied:
            </Text>
            {result.errors?.map((e) => <MessageLine key={e.code + e.message} message={e} colour="red" />)}
          </Stack>
        )}
      </Stack>
    </Card>
  );
};
