// The page "Directly-follows graph": settings sidebar on the left, the graph on the right.
// Documented in docs/pages/directly-follows-graph.md.
import { Alert, Box, Group, Loader } from "@mantine/core";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { getDirectlyFollowsGraph, type TypeSetting } from "../api/locationBasedOcpm";
import { DfgGraph } from "../components/DfgGraph";
import { DfgSettings } from "../components/DfgSettings";
import { ModulePage } from "../components/ModulePage";
import { useScheme } from "../components/plots";
import type { ArcLabel, Direction } from "../lib/dfgLayout";
import { errorText } from "../lib/errors";
import { usePageState } from "../lib/pageState";
import { colourMap } from "../lib/palette";

/** Width of the settings sidebar in pixels. */
const SIDEBAR_WIDTH = 330;
/** Height of the drawing area in pixels. */
const GRAPH_HEIGHT = 760;

/** The page's settings, kept per log across page switches and reloads; selection null = default (HU types). */
type DfgState = { selection: TypeSetting[] | null; arcLabel: ArcLabel; direction: Direction };
const INITIAL: DfgState = { selection: null, arcLabel: "count", direction: "RIGHT" };

/** Sidebar and graph of one log. */
const DfgContent = ({ ocelId }: { ocelId: string }) => {
  const [state, setState] = usePageState<DfgState>(`dfg.${ocelId}`, INITIAL);
  const scheme = useScheme();
  const { data, error, isFetching } = useQuery({
    queryKey: ["locationBasedOcpm", "dfg", ocelId, state.selection],
    queryFn: ({ signal }) => getDirectlyFollowsGraph(ocelId, { selection: state.selection }, undefined, undefined, signal),
    placeholderData: keepPreviousData,
  });
  // Colours follow the order of all object types (most objects first), so a type keeps its colour.
  const colours = useMemo(() => colourMap(data?.object_types.map((t) => t.object_type) ?? [], scheme), [data, scheme]);

  if (error) return <Alert color="red">{errorText(error)}</Alert>;
  if (!data) return <Loader size="sm" />;
  return (
    <Group align="flex-start" wrap="nowrap" gap="md">
      <Box w={SIDEBAR_WIDTH} style={{ flexShrink: 0, position: "sticky", top: 8 }}>
        <DfgSettings
          objectTypes={data.object_types}
          colours={colours}
          onSelection={(selection) => setState((s) => ({ ...s, selection }))}
          arcLabel={state.arcLabel}
          onArcLabel={(arcLabel) => setState((s) => ({ ...s, arcLabel }))}
          direction={state.direction}
          onDirection={(direction) => setState((s) => ({ ...s, direction }))}
        />
      </Box>
      <Box style={{ flex: 1, minWidth: 0, position: "relative", opacity: isFetching ? 0.6 : 1 }}>
        <DfgGraph graph={data} colours={colours} direction={state.direction} arcLabel={state.arcLabel} height={GRAPH_HEIGHT} />
      </Box>
    </Group>
  );
};

/** The page. */
export default function DirectlyFollowsGraphPage() {
  return <ModulePage title="Directly-follows graph">{({ ocelId }) => <DfgContent ocelId={ocelId} />}</ModulePage>;
}
