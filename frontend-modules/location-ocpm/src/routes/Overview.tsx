// The overview page: a configuration section (configuration bar, notices, input flags, data
// overview charts; never filtered), then the overview section (filter bar and everything the
// filters act on). Its content elements are documented in docs/pages/overview.md.
import { Stack, Title } from "@mantine/core";
import { useGetConfig } from "../api/locationBasedOcpm";
import { ActivityProfile } from "../components/ActivityProfile";
import { Notices } from "../components/ConfigForm";
import { DataCharts } from "../components/DataCharts";
import { FilterBar } from "../components/FilterBar";
import { FlagBadges } from "../components/FlagBadges";
import { KeyNumbers } from "../components/KeyNumbers";
import { ModulePage } from "../components/ModulePage";
import { OverviewCharts } from "../components/OverviewCharts";

/** Configuration notices (e.g. ignored pickups), as grey lines below the configuration bar. */
const ConfigNotices = ({ ocelId }: { ocelId: string }) => {
  const { data } = useGetConfig(ocelId);
  return <Notices notices={data?.notices} />;
};

export default function Overview() {
  return (
    <ModulePage title="Configuration">
      {({ ocelId }) => (
        <Stack gap="md">
          <ConfigNotices ocelId={ocelId} />
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
