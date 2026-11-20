// The Configuration page (before 2026-11-20 "Overview"): the configuration (summary with "Edit configuration", or
// the form) and its notices (both in `ModulePage`), the settings bar, input flags, data overview charts (never
// filtered), then the overview section (filter bar and everything the filters act on). Its content elements are documented in docs/pages/overview.md.
import { Stack, Title } from "@mantine/core";
import { ActivityProfile } from "../components/ActivityProfile";
import { DataCharts } from "../components/DataCharts";
import { FilterBar } from "../components/FilterBar";
import { FlagBadges } from "../components/FlagBadges";
import { KeyNumbers } from "../components/KeyNumbers";
import { ModulePage } from "../components/ModulePage";
import { OverviewCharts } from "../components/OverviewCharts";

/** The Configuration page; the only page that shows the configuration summary and form. */
export default function Configuration() {
  return (
    <ModulePage title="Configuration" configuration>
      {({ ocelId }) => (
        <Stack gap="md">
          <FlagBadges ocelId={ocelId} />
          <DataCharts ocelId={ocelId} />
          <Title order={2} mt="md">
            Overview
          </Title>
          <FilterBar ocelId={ocelId} />
          <KeyNumbers ocelId={ocelId} />
          <ActivityProfile ocelId={ocelId} />
          <OverviewCharts ocelId={ocelId} />
        </Stack>
      )}
    </ModulePage>
  );
}
