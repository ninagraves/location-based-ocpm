// The Configuration page (before 2026-11-20 "Overview"): the configuration (summary with "Edit configuration", or
// the form) and its notices (both in `ModulePage`), the settings bar, input flags and data overview charts (never
// filtered). The filtered overview moved to its own page (`Overview.tsx`). Documented in docs/pages/overview.md.
import { Stack } from "@mantine/core";
import { DataCharts } from "../components/DataCharts";
import { FlagBadges } from "../components/FlagBadges";
import { ModulePage } from "../components/ModulePage";

/** The Configuration page; the only page that shows the configuration summary and form. */
export default function Configuration() {
  return (
    <ModulePage title="Configuration" configuration>
      {({ ocelId }) => (
        <Stack gap="md">
          <FlagBadges ocelId={ocelId} />
          <DataCharts ocelId={ocelId} />
        </Stack>
      )}
    </ModulePage>
  );
}
