// The Transformations page (DRAFT, Nina 2026-11-23): page filters, key numbers, charts and transformation profile as
// in the playground, then the transformation type graph (Lineage (DRAFT).md, "Transformation Type Level Model").
// Its content elements are documented in docs/pages/transformations.md.
import { Alert, Card, Stack, Text } from "@mantine/core";
import { useGetTransformationOverview } from "../api/locationBasedOcpm";
import { ModulePage } from "../components/ModulePage";
import { TransformationCharts } from "../components/TransformationCharts";
import { TransformationOverview } from "../components/TransformationOverview";
import { TransformationProfile } from "../components/TransformationProfile";
import { TransformationTypeGraph } from "../components/TransformationTypeGraph";
import { errorText } from "../lib/errors";
import { listRequest, useTransformationFilter } from "../lib/transformations";

/** The page's content for one log. */
const TransformationsContent = ({ ocelId }: { ocelId: string }) => {
  const [filter, setFilter] = useTransformationFilter(ocelId);
  const { data, error } = useGetTransformationOverview(ocelId, filter, { request: listRequest });
  if (data && !data.configured)
    return (
      <Alert color="gray">
        No transformation events are configured. Add them in the configuration (group "Transformations (optional)") to use
        this page.
      </Alert>
    );
  return (
    <Stack gap="md">
      <TransformationOverview data={data} error={error ? errorText(error) : null} filter={filter} onFilter={setFilter} />
      <TransformationCharts ocelId={ocelId} filter={filter} />
      <TransformationProfile ocelId={ocelId} filter={filter} />
      <Card withBorder padding="xs">
        <Stack gap={6}>
          <Text size="sm" fw={600}>
            Transformation type graph
          </Text>
          <TransformationTypeGraph ocelId={ocelId} filter={filter} />
        </Stack>
      </Card>
    </Stack>
  );
};

/** The Transformations page (draft). */
export default function Transformations() {
  return (
    <ModulePage title="Transformations (draft)">
      {({ ocelId }) => (
        <Stack gap="md">
          <Alert color="yellow" title="Draft page">
            This page is a draft: its content is still being conceptualised and may change or go away. Definitions:
            transformation type = input → output, recipe = activity, input and output (both as multisets of object types).
          </Alert>
          <TransformationsContent ocelId={ocelId} />
        </Stack>
      )}
    </ModulePage>
  );
}
