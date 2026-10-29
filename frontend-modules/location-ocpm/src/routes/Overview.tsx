// The overview page. Its content elements are documented in docs/pages/overview.md.
import { Stack } from "@mantine/core";
import { useGetConfig } from "../api/locationBasedOcpm";
import { Notices } from "../components/ConfigForm";
import { ActivityProfile } from "../components/ActivityProfile";
import { DataCharts } from "../components/DataCharts";
import { FilterBar } from "../components/FilterBar";
import { FlagBadges } from "../components/FlagBadges";
import { KeyNumbers } from "../components/KeyNumbers";
import { ModulePage } from "../components/ModulePage";
import { OverviewCharts } from "../components/OverviewCharts";

/** Configuration notices (e.g. ignored pickups), as grey lines below the key numbers. */
const ConfigNotices = ({ ocelId }: { ocelId: string }) => {
  const { data } = useGetConfig(ocelId);
  return <Notices notices={data?.notices} />;
};

export default function Overview() {
  return (
    <ModulePage title="Overview">
      {({ ocelId }) => (
        <Stack gap="md">
          <FilterBar ocelId={ocelId} />
          <KeyNumbers ocelId={ocelId} />
          <ConfigNotices ocelId={ocelId} />
          <FlagBadges ocelId={ocelId} />
          <DataCharts ocelId={ocelId} />
          <ActivityProfile ocelId={ocelId} />
          <OverviewCharts ocelId={ocelId} />
        </Stack>
      )}
    </ModulePage>
  );
}
