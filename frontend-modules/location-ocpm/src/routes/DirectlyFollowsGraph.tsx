// The page "Directly-follows graph": toolbar and graph on the left (height adjustable by dragging its bottom edge),
// the sidebar "Discovery Settings" on the right, from the top of the toolbar to the bottom of the graph (width
// adjustable by dragging its left edge; shown or hidden by the settings button of the toolbar).
// Documented in docs/pages/directly-follows-graph.md.
import { Alert, Box, Group, Loader, Stack } from "@mantine/core";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";
import { getDirectlyFollowsGraph } from "../api/locationBasedOcpm";
import { DfgGraph } from "../components/DfgGraph";
import { arcSettings, DEFAULT_STATE, DfgSettings, type DfgState, removeArc, toRequest } from "../components/DfgSettings";
import { DfgToolbar } from "../components/DfgToolbar";
import { applyArcSettings } from "../lib/dfgView";
import type { LaidOutArc } from "../lib/dfgLayout";
import { ModulePage } from "../components/ModulePage";
import { useScheme } from "../components/plots";
import { errorText } from "../lib/errors";
import { usePageState } from "../lib/pageState";
import { emphasisColourMap } from "../lib/palette";

/** Default, smallest and largest width of the settings sidebar in pixels. */
const SIDEBAR_WIDTH = { initial: 300, min: 220, max: 640 };
/** Default, smallest and largest height of the drawing area in pixels (adjustable by dragging its bottom edge). */
const GRAPH_HEIGHT = { initial: 760, min: 300, max: 4000 };

/** Width and visibility of the sidebar (one for all logs). */
type SidebarState = { width: number; hidden: boolean };

/**
 * Grab area on the left edge of the sidebar (a hairline shows on hover): dragging it changes the sidebar's width.
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
  const [hover, setHover] = useState(false);
  // Invisible 8 px grab area with a hairline in the middle that only shows on hover (a visible bar looked like a scrollbar).
  return (
    <Box
      onPointerDown={start}
      onPointerEnter={() => setHover(true)}
      onPointerLeave={() => setHover(false)}
      role="separator"
      aria-label="Drag to change the width of the settings"
      title="Drag to change the width of the settings"
      style={{ width: 8, alignSelf: "stretch", cursor: "col-resize", flexShrink: 0, display: "flex", justifyContent: "center" }}
    >
      <Box style={{ width: 2, borderRadius: 1, background: hover ? "var(--mantine-color-gray-5)" : "transparent" }} />
    </Box>
  );
};

/**
 * Grab area below the graph (a hairline shows on hover): dragging it down makes the drawing area taller.
 *
 * @param height The current height.
 * @param onChange Called with the new height while dragging (clamped to `GRAPH_HEIGHT`).
 */
const HeightHandle = ({ height, onChange }: { height: number; onChange: (height: number) => void }) => {
  const start = (e: React.PointerEvent) => {
    e.preventDefault();
    const y0 = e.clientY;
    const move = (m: PointerEvent) => onChange(Math.min(GRAPH_HEIGHT.max, Math.max(GRAPH_HEIGHT.min, height + m.clientY - y0)));
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };
  const [hover, setHover] = useState(false);
  return (
    <Box
      onPointerDown={start}
      onPointerEnter={() => setHover(true)}
      onPointerLeave={() => setHover(false)}
      onDoubleClick={() => onChange(GRAPH_HEIGHT.initial)}
      role="separator"
      aria-label="Drag to change the height of the graph"
      title="Drag to change the height of the graph (double click: default height)"
      style={{ height: 10, cursor: "row-resize", display: "flex", alignItems: "center", justifyContent: "center" }}
    >
      <Box style={{ width: 48, height: 3, borderRadius: 2, background: hover ? "var(--mantine-color-gray-6)" : "var(--mantine-color-gray-4)" }} />
    </Box>
  );
};

/** Sidebar and graph of one log. */
const DfgContent = ({ ocelId }: { ocelId: string }) => {
  const [stored, setStored] = usePageState<DfgState>(`dfg.v5.${ocelId}`, DEFAULT_STATE);
  // Settings saved by an older version may lack fields: fill them with the defaults.
  const state = useMemo(() => ({ ...DEFAULT_STATE, ...stored }), [stored]);
  const setState = useCallback(
    (update: (s: DfgState) => DfgState) => setStored((s) => update({ ...DEFAULT_STATE, ...s })),
    [setStored],
  );
  const [sidebar, setSidebar] = usePageState<SidebarState>("dfg.sidebar", { width: SIDEBAR_WIDTH.initial, hidden: false });
  const [height, setHeight] = usePageState<number>("dfg.height", GRAPH_HEIGHT.initial);
  const scheme = useScheme();
  // Right click on an arc removes it (Nina, 2026-11-15).
  const onRemoveArc = useCallback(
    (arc: LaidOutArc) =>
      setState((s) => removeArc(s, { object_type: arc.objectType, source: arc.sourceActivity, target: arc.targetActivity })),
    [setState],
  );
  const request = useMemo(() => toRequest(state), [state]);
  const { data: base, error, isFetching } = useQuery({
    queryKey: ["locationBasedOcpm", "dfg", ocelId, request],
    queryFn: ({ signal }) => getDirectlyFollowsGraph(ocelId, request, undefined, undefined, signal),
    placeholderData: keepPreviousData,
  });
  // Arc threshold, arc count, removed arcs and Stay connected: in the browser, without a request (Nina, 2026-11-15).
  const arcs = useMemo(() => arcSettings(state), [state]);
  const data = useMemo(() => (base ? applyArcSettings(base, arcs) : undefined), [base, arcs]);
  // Handling-unit types get the signature colours first, the other types paler colours (Nina, 2026-11-15); each
  // group in the order of all object types (most objects first), so a type keeps its colour.
  const colours = useMemo(() => {
    const types = data?.object_types ?? [];
    return emphasisColourMap(
      types.filter((t) => t.handling_units).map((t) => t.object_type),
      types.filter((t) => !t.handling_units).map((t) => t.object_type),
      scheme,
    );
  }, [data, scheme]);

  if (error) return <Alert color="red">{errorText(error)}</Alert>;
  if (!data) return <Loader size="sm" />;
  return (
    <Group align="stretch" wrap="nowrap" gap={6}>
      <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
        <DfgToolbar
          graph={data}
          state={state}
          setState={setState}
          sidebarHidden={sidebar.hidden}
          onToggleSidebar={() => setSidebar((s) => ({ ...s, hidden: !s.hidden }))}
        />
        <Box style={{ opacity: isFetching ? 0.6 : 1 }}>
          <DfgGraph
            graph={data}
            colours={colours}
            direction={state.direction}
            arcLabel={state.arcLabel}
            compact={state.compact}
            height={height}
            onRemoveArc={onRemoveArc}
          />
          <HeightHandle height={height} onChange={setHeight} />
        </Box>
      </Stack>
      {!sidebar.hidden && (
        <>
          <ResizeHandle width={sidebar.width} onChange={(width) => setSidebar((s) => ({ ...s, width }))} />
          {/* Ends with the bottom of the graph (above the height grab bar, 10 px). */}
          <Box w={sidebar.width} mb={10} style={{ flexShrink: 0, minHeight: 0, position: "relative" }}>
            <Box style={{ position: "absolute", inset: 0 }}>
              <DfgSettings graph={data} baseArcs={base?.arcs ?? []} colours={colours} state={state} setState={setState} />
            </Box>
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
