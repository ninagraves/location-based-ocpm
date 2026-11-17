// Debounced values: a value that follows another one only after it has stopped changing for a while (Nina,
// 2026-11-17: the directly-follows graph recalculates 2 s after the last change, so that several settings can be
// changed first). Documented in docs/pages/directly-follows-graph.md, section "Settings".
import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Follow `value` with a delay: the returned value takes over `value` once it has not changed for `delay` ms.
 * The first value is taken over at once (no delay when the page opens).
 *
 * Example: with `delay` 2000, three clicks 1 s apart lead to one update, 2 s after the third click.
 *
 * @param value The current value (compared by identity, e.g. a state object).
 * @param delay Waiting time in milliseconds after the last change.
 * @returns The delayed value, whether a change is waiting, and a function that takes over `value` at once.
 */
export const useDebounced = <T>(value: T, delay: number): [T, boolean, () => void] => {
  const [applied, setApplied] = useState(value);
  const latest = useRef(value);
  latest.current = value;
  useEffect(() => {
    if (Object.is(value, applied)) return;
    const timer = window.setTimeout(() => setApplied(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, applied, delay]);
  const flush = useCallback(() => setApplied(latest.current), []);
  return [applied, !Object.is(value, applied), flush];
};
