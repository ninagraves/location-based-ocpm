// The frame of every page of the module: title, shared header, then the page's content.
import { Alert, Card, Group, Loader, Stack, Text, Title } from "@mantine/core";
import { useCurrentOcel } from "@ocelescope/core";
import type { ReactNode } from "react";
import { useGetStatus } from "../api/locationBasedOcpm";

/** What a page's content gets from the frame. */
export type PageContext = {
  ocelId: string;
};

/** Read the error message of a failed request. */
export const errorText = (error: unknown) =>
  (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? String(error);

/**
 * The shared header on top of every page. For now it only confirms the backend connection;
 * the configuration and the export controls follow in the next iterations.
 */
const Header = () => {
  const { data: status, error, isPending } = useGetStatus();
  return (
    <Card withBorder padding="xs">
      <Group justify="space-between">
        {isPending ? (
          <Loader size="xs" />
        ) : error ? (
          <Text size="sm" c="red">
            Backend not reachable: {errorText(error)}
          </Text>
        ) : (
          <Text size="sm">
            Configuration: not available yet. Backend module {status?.module_version}, Ocelescope{" "}
            {status?.ocelescope_version}.
          </Text>
        )}
      </Group>
    </Card>
  );
};

/** A page of the module: title, shared header, then the page's content for the current OCEL. */
export const ModulePage = ({ title, children }: { title: string; children: (context: PageContext) => ReactNode }) => {
  const { id: ocelId } = useCurrentOcel();
  return (
    <Stack p="md" gap="lg">
      <Title order={2}>{title}</Title>
      <Header />
      {ocelId ? children({ ocelId }) : <Alert color="gray">Select an event log to start.</Alert>}
    </Stack>
  );
};
