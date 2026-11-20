// What a page looked like when it was left: graph layouts, zoom and pan, the scroll position. Kept in memory per key
// (`lib/pageState.ts`, `keep`/`recall`), so that a page opened again looks as it was left, and only as long as it fits
// the current data. Documented in docs/hosting/state-and-caching.md, section "Page state".
import type { Viewport } from "@xyflow/react";
import { type RefObject, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { keep, recall, sameInputs } from "./pageState";

/** A layout with the inputs it was computed from. */
type KeptLayout<L> = { inputs: readonly unknown[]; layout: L };

/**
 * A layout computed in the browser (e.g. by ELK), kept per key: opening the page again with the same inputs
 * (`sameInputs`: identical, or equal maps or JSON) shows the kept layout at once instead of computing it again.
 * Other inputs compute a new layout (and keep that one instead).
 *
 * @param key Where the layout is kept, with the log id (e.g. `instances.lineage.layout.<log id>`).
 * @param inputs Everything the layout depends on; the list must keep its length. Callbacks among them are not
 *   compared, so they must not depend on the page visit (e.g. a setter of `usePageState`).
 * @param compute Computes the layout from the inputs.
 * @param enabled False while the inputs are not there yet (nothing is computed).
 * @returns The layout (null until there is one) and the error of the last computation.
 *
 * Example: `useKeptLayout("lineage." + ocelId, [data, colours], () => layoutLineage(data, colours), !!data)`.
 */
export const useKeptLayout = <L>(key: string, inputs: readonly unknown[], compute: () => Promise<L>, enabled = true) => {
  const [state, setState] = useState<{ layout: L | null; error: string | null }>(() => {
    const kept = recall<KeptLayout<L>>(key);
    return { layout: enabled && kept && sameInputs(kept.inputs, inputs) ? kept.layout : null, error: null };
  });
  useEffect(() => {
    if (!enabled) return;
    const kept = recall<KeptLayout<L>>(key);
    if (kept && sameInputs(kept.inputs, inputs)) {
      setState((s) => (s.layout === kept.layout && !s.error ? s : { layout: kept.layout, error: null }));
      return;
    }
    let cancelled = false;
    compute().then(
      (layout) => {
        if (cancelled) return;
        keep(key, { inputs, layout });
        setState({ layout, error: null });
      },
      (e: unknown) => !cancelled && setState((s) => ({ ...s, error: String(e) })),
    );
    return () => {
      cancelled = true;
    };
    // The inputs are the dependencies; `compute` follows them.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, enabled, ...inputs]);
  return state;
};

/** Zoom and pan of a React Flow graph, with the layout (`token`) they belong to. */
type KeptViewport = { token: unknown; viewport: Viewport };

/**
 * Zoom and pan of a React Flow graph, kept per key for the layout they were set on (`token`, e.g. the layout object
 * or its generation). Pass `defaultViewport` and `fitView` to `ReactFlow`, `onMoveEnd` too, and do not fit the view
 * for a token for which `skipFit` is true (it was restored as the user left it).
 *
 * @param key Where the view is kept, with the log id (e.g. `dfg.viewport.<log id>`).
 * @param token The current layout; read when the graph is first drawn.
 *
 * Example: `<ReactFlow {...view} />` with `const { skipFit, ...view } = useKeptViewport("dfg.viewport." + ocelId, layout)`.
 */
export const useKeptViewport = (key: string, token: unknown) => {
  // Only the view of the layout shown when the component mounts is restored; later layouts are fitted.
  const [restored] = useState(() => {
    const kept = recall<KeptViewport>(key);
    return kept && token !== null && token !== undefined && kept.token === token ? kept : null;
  });
  const current = useRef(token);
  current.current = token;
  const onMoveEnd = useCallback(
    (_event: unknown, viewport: Viewport) => keep(key, { token: current.current, viewport }),
    [key],
  );
  const skipFit = useCallback((t: unknown) => restored !== null && t === restored.token, [restored]);
  return { defaultViewport: restored?.viewport, fitView: restored === null, onMoveEnd, skipFit };
};

/** Longest time a scroll position is waited for (content that loads later makes the page tall enough). */
const SCROLL_RESTORE_MS = 4000;

/** The nearest ancestor of an element that scrolls vertically (Ocelescope's main area). */
const scrollParent = (element: HTMLElement | null): HTMLElement | null => {
  for (let e = element?.parentElement ?? null; e; e = e.parentElement) {
    const overflow = getComputedStyle(e).overflowY;
    if (overflow === "auto" || overflow === "scroll") return e;
  }
  return null;
};

const scrollStorageKey = (key: string) => `locationBasedOcpm.${key}`;

/**
 * Keeps the scroll position of a scrolling element per key (memory and the tab's sessionStorage) and restores it: the
 * position is set again on every animation frame until the content is tall enough (charts and lists load later), for
 * at most `SCROLL_RESTORE_MS`, and not any more once the user scrolls, clicks or types in it.
 *
 * @param box The scrolling element.
 * @param key Where the position is kept.
 * @returns The cleanup: keeps the current position and removes the listeners.
 */
const keepScrollOf = (box: HTMLElement, key: string) => {
  let target = recall<number>(key);
  if (target === undefined) {
    try {
      target = Number(sessionStorage.getItem(scrollStorageKey(key)) ?? 0) || 0;
    } catch {
      target = 0;
    }
  }
  let restoring = true;
  let frame = 0;
  const start = performance.now();
  const store = (top: number) => {
    keep(key, top);
    try {
      sessionStorage.setItem(scrollStorageKey(key), String(Math.round(top)));
    } catch {
      // Memory only.
    }
  };
  const stop = () => {
    restoring = false;
    cancelAnimationFrame(frame);
  };
  const restore = () => {
    box.scrollTop = target;
    if (Math.abs(box.scrollTop - target) < 2 || performance.now() - start > SCROLL_RESTORE_MS) restoring = false;
    else frame = requestAnimationFrame(restore);
  };
  const onScroll = () => {
    if (!restoring) keep(key, box.scrollTop);
  };
  const onPageHide = () => store(restoring ? target : box.scrollTop);
  const userEvents = ["wheel", "touchstart", "keydown", "mousedown"] as const;
  for (const e of userEvents) box.addEventListener(e, stop, { passive: true });
  box.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("pagehide", onPageHide);
  restore();
  return () => {
    store(restoring ? target : box.scrollTop);
    stop();
    for (const e of userEvents) box.removeEventListener(e, stop);
    box.removeEventListener("scroll", onScroll);
    window.removeEventListener("pagehide", onPageHide);
  };
};

/**
 * Keeps the scroll position of a page per key and restores it when the page opens again (`keepScrollOf`). The page
 * itself does not scroll but Ocelescope's main area around it does, so the ref goes on the page's outermost element
 * and the nearest scrolling ancestor is used.
 *
 * @param key Where the position is kept (e.g. `scroll.<log id>./locationBasedOcpm/dfg`).
 * @returns A ref for an element inside the scrolling area.
 */
export const useKeptScroll = <E extends HTMLElement>(key: string): RefObject<E | null> => {
  const anchor = useRef<E>(null);
  // A layout effect's cleanup runs before the page's elements are removed, so the position is still the user's.
  useLayoutEffect(() => {
    const box = scrollParent(anchor.current);
    return box ? keepScrollOf(box, key) : undefined;
  }, [key]);
  return anchor;
};

/**
 * Like `useKeptScroll`, for an element that scrolls itself (e.g. a list in a sidebar; for Mantine's `ScrollArea` pass
 * the ref as `viewportRef`).
 *
 * @param key Where the position is kept (e.g. `dfg.sidebar.activities.<log id>`).
 * @returns A ref for the scrolling element.
 */
export const useKeptScrollOf = <E extends HTMLElement>(key: string): RefObject<E | null> => {
  const box = useRef<E>(null);
  useLayoutEffect(() => (box.current ? keepScrollOf(box.current, key) : undefined), [key]);
  return box;
};
