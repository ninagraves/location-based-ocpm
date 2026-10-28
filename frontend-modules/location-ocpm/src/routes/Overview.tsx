// The overview page. Its content elements are documented in docs/pages/overview.md.
import { Stack } from "@mantine/core";
import { useGetConfig } from "../api/locationBasedOcpm";
import { Notices } from "../components/ConfigForm";
import { FlagBadges } from "../components/FlagBadges";
import { KeyNumbers } from "../components/KeyNumbers";
import { ModulePage } from "../components/ModulePage";

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
          <KeyNumbers ocelId={ocelId} />
          <ConfigNotices ocelId={ocelId} />
          <FlagBadges ocelId={ocelId} />
        </Stack>
      )}
    </ModulePage>
  );
}
