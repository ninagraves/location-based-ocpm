// The overview page. Its content elements are documented in docs/pages/overview.md.
import { Text } from "@mantine/core";
import { ModulePage } from "../components/ModulePage";

export default function Overview() {
  return (
    <ModulePage title="Overview">
      {() => (
        <Text size="sm" c="dimmed">
          The overview page's sections follow in the next iterations.
        </Text>
      )}
    </ModulePage>
  );
}
