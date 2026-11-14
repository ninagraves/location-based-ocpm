// The page "Directly-follows graph": the graph on the left, the settings sidebar on the right (width adjustable
// by dragging its left edge, can be hidden).
// Documented in docs/pages/directly-follows-graph.md.
import { ActionIcon, Alert, Box, Group, Loader, Tooltip } from "@mantine/core";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { PanelRightOpenIcon } from "lucide-react";
import { useCallback, useMemo } from "react";
import { getDirectlyFollowsGraph } from "../api/locationBasedOcpm";
import { DfgGraph } from "../components/DfgGraph";
import { DEFAULT_STATE, DfgSettings, type DfgState, toRequest } from "../components/DfgSettings";
import { ModulePage } from "../components/ModulePage";
import { useScheme } from "../components/plots";
import { errorText } from "../lib/errors";
import { usePageState } from "../lib/pageState";
import { colourMap } from "../lib/palette";

/** Default, smallest and largest width of the settings sidebar in pixels. */
const SIDEBAR_WIDTH = { initial: 300, min: 220, max: 640 };
/** Height of the drawing area in pixels. */
const GRAPH_HEIGHT = 760;

/** Width and visibility of the sidebar (one for all logs). */
type SidebarState = { width: number; hidden: boolean };

/**
 * Thin vertical bar on the left edge of the sidebar: dragging it changes the sidebar's width.
 *
 * @param width The current width.
 * @param onChange Called with the new width while dragging (clamped to `SIDEBAR_WIDTH`).
 */
const ResizeHandle = ({ width, onChange }: { width: number; onChange: (width: number) => void }) => {
  const start = (e: React.PointerEvent) => {
    e.preventDefault();
    const x0 = e.clientX;
    const move = (m: PointerEvent) =>
      onChange(Math.min(SIDEBAR_WIDTH.max, Math.max(SIDEBAR_WIDTH.min, width + x0 - m.clientX)));
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };
  return (
    <Box
      onPointerDown={start}
      role="separator"
      aria-label="Drag to change the width of the settings"
      style={{ width: 6, alignSelf: "stretch", cursor: "col-resize", flexShrink: 0, borderRadius: 3 }}
      bg="var(--mantine-color-default-border)"
    />
  );
};

/** Sidebar and graph of one log. */
const DfgContent = ({ ocelId }: { ocelId: string }) => {
  const [stored, setStored] = usePageState<DfgState>(`dfg.v2.${ocelId}`, DEFAULT_STATE);
  // Settings saved by an older version may lack fields: fill them with the defaults.
  const state = useMemo(() => ({ ...DEFAULT_STATE, ...stored }), [stored]);
  const setState = useCallback(
    (update: (s: DfgState) => DfgState) => setStored((s) => update({ ...DEFAULT_STATE, ...s })),
    [setStored],
  );
  const [sidebar, setSidebar] = usePageState<SidebarState>("dfg.sidebar", { width: SIDEBAR_WIDTH.initial, hidden: false });
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
    <Group align="flex-start" wrap="nowrap" gap={6}>
      <Box style={{ flex: 1, minWidth: 0, position: "relative", opacity: isFetching ? 0.6 : 1 }}>
        <DfgGraph
          graph={data}
          colours={colours}
          direction={state.direction}
          arcLabel={state.arcLabel}
          compact={state.compact}
          height={GRAPH_HEIGHT}
        />
        {sidebar.hidden && (
          <Tooltip label="Show the settings" withinPortal>
            <ActionIcon
              variant="default"
              aria-label="Show the settings"
              onClick={() => setSidebar((s) => ({ ...s, hidden: false }))}
              style={{ position: "absolute", top: 8, right: 8, zIndex: 5 }}
            >
              <PanelRightOpenIcon size={16} />
            </ActionIcon>
          </Tooltip>
        )}
      </Box>
      {!sidebar.hidden && (
        <>
          <ResizeHandle width={sidebar.width} onChange={(width) => setSidebar((s) => ({ ...s, width }))} />
          <Box w={sidebar.width} style={{ flexShrink: 0, position: "sticky", top: 8 }}>
            <DfgSettings
              objectTypes={data.object_types}
              activityOptions={data.activity_options}
              colours={colours}
              state={state}
              setState={setState}
              onHide={() => setSidebar((s) => ({ ...s, hidden: true }))}
            />
          </Box>
        </>
      )}
    </Group>
  );
};

/** The page. */
export default function DirectlyFollowsGraphPage() {
  return <ModulePage title="Directly-follows graph">{({ ocelId }) => <DfgContent ocelId={ocelId} />}</ModulePage>;
}
