// The page "Directly-follows graph": toolbar and graph on the left (height adjustable by dragging its bottom edge),
// the sidebar "Discovery Settings" on the right, from the top of the toolbar to the bottom of the graph (width
// adjustable by dragging its left edge; shown or hidden by the settings button of the toolbar).
// Documented in docs/pages/directly-follows-graph.md.
import { Alert, Box, Group, Loader, Stack } from "@mantine/core";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { type DfgActivityOption, getDirectlyFollowsGraph } from "../api/locationBasedOcpm";
import { DfgGraph } from "../components/DfgGraph";
import { arcSettings, DEFAULT_STATE, DfgSettings, type DfgState, removeArc, toRequest } from "../components/DfgSettings";
import { DfgToolbar } from "../components/DfgToolbar";
import { applyArcSettings, pendingSelection } from "../lib/dfgView";
import { useDebounced } from "../lib/useDebounced";
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

/** Waiting time after the last change of a setting before the graph is recalculated (Nina, 2026-11-17). */
const RECALCULATION_DELAY_MS = 2000;

/**
 * True if two states differ only by more arcs removed by hand (`b` removes all arcs that `a` removes, and more).
 *
 * @param a The earlier state.
 * @param b The later state.
 */
const onlyRemovedDiffers = (a: DfgState, b: DfgState) => {
  if (a === b || b.removed.length <= a.removed.length) return false;
  const key = (r: DfgState["removed"][number]) => JSON.stringify([r.object_type, r.source, r.target]);
  const later = new Set(b.removed.map(key));
  return (
    a.removed.every((r) => later.has(key(r))) && JSON.stringify({ ...a, removed: [] }) === JSON.stringify({ ...b, removed: [] })
  );
};

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

/**
 * Deselects an activity for every object type that has it selected (double click on its node).
 * A type without own selection in the state gets its current selection (from the graph's activity options) minus the
 * activity. Example: coil selects crane move, roll, cut; slab cast slab, roll: double click on roll leaves crane move,
 * cut and cast slab.
 *
 * @param state The page state.
 * @param options The activity options of the last graph (`activity_options`).
 * @param activity The activity to deselect.
 * @returns The new state.
 */
export const deselectActivity = (state: DfgState, options: DfgActivityOption[], activity: string): DfgState => {
  const activities = { ...state.activities };
  const types = options.find((o) => o.activity === activity)?.object_types.filter((t) => t.selected_type) ?? [];
  for (const t of types) {
    const current =
      activities[t.object_type] ??
      options.filter((o) => o.object_types.some((x) => x.object_type === t.object_type && x.included)).map((o) => o.activity);
    activities[t.object_type] = current.filter((a) => a !== activity);
  }
  return { ...state, activities };
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
  // Right click on an arc removes it (Nina, 2026-11-15), at once and without a new layout if nothing else waits
  // (Nina, 2026-11-17): it only takes arcs out, in the browser.
  const removeNow = useRef(false);
  const onRemoveArc = useCallback(
    (arc: LaidOutArc) => {
      removeNow.current = true;
      setState((s) => removeArc(s, { object_type: arc.objectType, source: arc.sourceActivity, target: arc.targetActivity }));
    },
    [setState],
  );
  // Double click on an activity node deselects it for every object type (Nina, 2026-11-19); applied after the usual
  // 2 s wait, like a checkbox in the sidebar.
  const options = useRef<DfgActivityOption[]>([]);
  const onDeselectActivity = useCallback(
    (activity: string) => setState((s) => deselectActivity(s, options.current, activity)),
    [setState],
  );
  // The graph follows the settings 2 s after the last change, so that several can be changed first (Nina,
  // 2026-11-17); the controls show the new values at once. "Update now" in the toolbar skips the wait.
  const [applied, pending, applyNow] = useDebounced(state, RECALCULATION_DELAY_MS);
  const lastApplied = useRef(applied);
  useEffect(() => {
    if (!removeNow.current) return;
    removeNow.current = false;
    // Apply a removal at once only if it is the only change waiting.
    if (onlyRemovedDiffers(lastApplied.current, state)) applyNow();
  }, [state, applyNow]);
  // Only arcs removed by hand changed since the last drawing: keep the layout (`DfgGraph`, `keepLayout`).
  const keepLayout = useMemo(() => onlyRemovedDiffers(lastApplied.current, applied), [applied]);
  useEffect(() => {
    lastApplied.current = applied;
  }, [applied]);
  const request = useMemo(() => toRequest(applied), [applied]);
  const { data: base, error, isFetching } = useQuery({
    queryKey: ["locationBasedOcpm", "dfg", ocelId, request],
    queryFn: ({ signal }) => getDirectlyFollowsGraph(ocelId, request, undefined, undefined, signal),
    placeholderData: keepPreviousData,
  });
  // Arc threshold, arc count, removed arcs and Stay connected: in the browser, without a request (Nina, 2026-11-15).
  const arcs = useMemo(() => arcSettings(applied), [applied]);
  const data = useMemo(() => (base ? applyArcSettings(base, arcs) : undefined), [base, arcs]);
  options.current = data?.activity_options ?? [];
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

  // The sidebar's checkboxes show the current selection while the graph still shows the applied one.
  const sidebarGraph = useMemo(
    () => (data ? pendingSelection(data, state.objectTypes, state.activities) : undefined),
    [data, state.objectTypes, state.activities],
  );

  if (error) return <Alert color="red">{errorText(error)}</Alert>;
  if (!data || !sidebarGraph) return <Loader size="sm" />;
  return (
    <Group align="stretch" wrap="nowrap" gap={6}>
      <Stack gap={6} style={{ flex: 1, minWidth: 0 }}>
        <DfgToolbar
          graph={data}
          state={state}
          setState={setState}
          pending={pending}
          onApplyNow={applyNow}
          sidebarHidden={sidebar.hidden}
          onToggleSidebar={() => setSidebar((s) => ({ ...s, hidden: !s.hidden }))}
        />
        <Box style={{ opacity: isFetching ? 0.6 : 1 }}>
          <DfgGraph
            graph={data}
            colours={colours}
            direction={applied.direction}
            arcLabel={applied.arcLabel}
            compact={applied.compact}
            height={height}
            onRemoveArc={onRemoveArc}
            onDeselectActivity={onDeselectActivity}
            keepLayout={keepLayout}
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
              <DfgSettings graph={sidebarGraph} baseArcs={base?.arcs ?? []} colours={colours} state={state} setState={setState} />
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
