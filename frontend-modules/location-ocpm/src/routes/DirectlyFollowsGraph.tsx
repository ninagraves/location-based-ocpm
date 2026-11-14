// The page "Directly-follows graph": the graph on the left, the settings sidebar on the right.
// Documented in docs/pages/directly-follows-graph.md.
import { Alert, Box, Group, Loader } from "@mantine/core";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import { getDirectlyFollowsGraph } from "../api/locationBasedOcpm";
import { DfgGraph } from "../components/DfgGraph";
import { DEFAULT_STATE, DfgSettings, type DfgState, toRequest } from "../components/DfgSettings";
import { ModulePage } from "../components/ModulePage";
import { useScheme } from "../components/plots";
import { errorText } from "../lib/errors";
import { usePageState } from "../lib/pageState";
import { colourMap } from "../lib/palette";

/** Width of the settings sidebar in pixels. */
const SIDEBAR_WIDTH = 340;
/** Height of the drawing area in pixels. */
const GRAPH_HEIGHT = 760;

/** Sidebar and graph of one log. */
const DfgContent = ({ ocelId }: { ocelId: string }) => {
  const [stored, setStored] = usePageState<DfgState>(`dfg.v2.${ocelId}`, DEFAULT_STATE);
  // Settings saved by an older version may lack fields: fill them with the defaults.
  const state = useMemo(() => ({ ...DEFAULT_STATE, ...stored }), [stored]);
  const setState = useCallback(
    (update: (s: DfgState) => DfgState) => setStored((s) => update({ ...DEFAULT_STATE, ...s })),
    [setStored],
  );
  const scheme = useScheme();
  const request = useMemo(() => toRequest(state), [state]);
  const { data, error, isFetching } = useQuery({
    queryKey: ["locationBasedOcpm", "dfg", ocelId, request],
    queryFn: ({ signal }) => getDirectlyFollowsGraph(ocelId, request, undefined, undefined, signal),
    placeholderData: keepPreviousData,
  });
  // Colours follow the order of all object types (most objects first), so a type keeps its colour.
  const colours = useMemo(() => colourMap(data?.object_types.map((t) => t.object_type) ?? [], scheme), [data, scheme]);

  if (error) return <Alert color="red">{errorText(error)}</Alert>;
  if (!data) return <Loader size="sm" />;
  return (
    <Group align="flex-start" wrap="nowrap" gap="md">
      <Box style={{ flex: 1, minWidth: 0, position: "relative", opacity: isFetching ? 0.6 : 1 }}>
        <DfgGraph
          graph={data}
          colours={colours}
          direction={state.direction}
          arcLabel={state.arcLabel}
          compact={state.compact}
          height={GRAPH_HEIGHT}
        />
      </Box>
      <Box w={SIDEBAR_WIDTH} style={{ flexShrink: 0, position: "sticky", top: 8 }}>
        <DfgSettings
          objectTypes={data.object_types}
          activityOptions={data.activity_options}
          colours={colours}
          state={state}
          setState={setState}
        />
      </Box>
    </Group>
  );
};

/** The page. */
export default function DirectlyFollowsGraphPage() {
  return <ModulePage title="Directly-follows graph">{({ ocelId }) => <DfgContent ocelId={ocelId} />}</ModulePage>;
}
