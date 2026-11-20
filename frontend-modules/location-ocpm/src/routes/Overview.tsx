// The Overview page (Nina, 2026-11-20: moved out of the Configuration page): the filter bar and everything the
// filters act on. Its content elements are documented in docs/pages/overview.md.
import { Stack } from "@mantine/core";
import { ActivityProfile } from "../components/ActivityProfile";
import { FilterBar } from "../components/FilterBar";
import { KeyNumbers } from "../components/KeyNumbers";
import { ModulePage } from "../components/ModulePage";
import { OverviewCharts } from "../components/OverviewCharts";

/** The Overview page: filter bar, key numbers, activity profile and overview charts (all filtered). */
export default function Overview() {
  return (
    <ModulePage title="Overview">
      {({ ocelId }) => (
        <Stack gap="md">
          <FilterBar ocelId={ocelId} />
          <KeyNumbers ocelId={ocelId} />
          <ActivityProfile ocelId={ocelId} />
          <OverviewCharts ocelId={ocelId} />
        </Stack>
      )}
    </ModulePage>
  );
}
