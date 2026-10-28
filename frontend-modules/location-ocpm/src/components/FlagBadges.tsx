// Flag badges of the overview page. Documented in docs/pages/overview.md, section "Flags".
import { Alert, Badge, Group, Loader, Text, Tooltip } from "@mantine/core";
import { useGetFlagCounts } from "../api/locationBasedOcpm";
import { errorText } from "../lib/errors";
import { num } from "../lib/format";

/**
 * One badge per flag with its count (whole log, selected level): grey at 0, amber above 0;
 * hovering shows the definition. The explore sections follow in later steps.
 */
export const FlagBadges = ({ ocelId }: { ocelId: string }) => {
  const { data, error } = useGetFlagCounts(ocelId);
  if (error) return <Alert color="red">{errorText(error)}</Alert>;
  if (!data) return <Loader size="sm" />;
  return (
    <Group gap="xs">
      <Text size="sm" c="dimmed">
        Flags
      </Text>
      {data.map((flag) => (
        <Tooltip key={flag.key} label={flag.definition} multiline w={360} withArrow>
          <Badge variant="light" color={flag.count > 0 ? "yellow" : "gray"} style={{ textTransform: "none", cursor: "help" }}>
            {flag.key} {flag.label} · {num(flag.count)} {flag.count === 1 ? flag.unit.replace(/s$/, "") : flag.unit}
          </Badge>
        </Tooltip>
      ))}
    </Group>
  );
};
