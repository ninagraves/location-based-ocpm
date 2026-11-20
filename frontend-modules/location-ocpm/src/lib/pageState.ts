// Page state that survives switching between the module's pages (and, for JSON values, reloading the browser tab).
// Values live in memory (shared by all components using the same key); `usePageState` also writes them to the tab's
// sessionStorage where available. Documented in docs/hosting/state-and-caching.md, section "Page state".
import { type SetStateAction, useCallback, useSyncExternalStore } from "react";

const values = new Map<string, unknown>();
const listeners = new Set<() => void>();
const storageKey = (key: string) => `locationBasedOcpm.${key}`;

/** Current value of a key: memory, else sessionStorage (if `stored`), else `initial`. */
const read = <T>(key: string, initial: T, stored: boolean): T => {
  if (values.has(key)) return values.get(key) as T;
  let value = initial;
  if (stored) {
    try {
      const text = sessionStorage.getItem(storageKey(key));
      if (text) value = JSON.parse(text) as T;
    } catch {
      // No storage (private window, server render): start from the initial value.
    }
  }
  values.set(key, value);
  return value;
};

/** Set a key in memory (and in sessionStorage if `stored`) and tell every component using a key. */
const write = (key: string, value: unknown, stored: boolean) => {
  values.set(key, value);
  if (stored) {
    try {
      sessionStorage.setItem(storageKey(key), JSON.stringify(value));
    } catch {
      // Keep the in-memory value only.
    }
  }
  for (const listener of listeners) listener();
};

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

/** `useState` kept per key in memory, and in sessionStorage if `stored`. */
const useKeyedState = <T>(key: string, initial: T, stored: boolean) => {
  const value = useSyncExternalStore(
    subscribe,
    () => read(key, initial, stored),
    () => initial,
  );
  const setValue = useCallback(
    (next: SetStateAction<T>) => {
      const previous = read(key, initial, stored);
      const resolved = typeof next === "function" ? (next as (old: T) => T)(previous) : next;
      write(key, resolved, stored);
    },
    // `initial` only matters on first read.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key, stored],
  );
  return [value, setValue] as const;
};

/**
 * Like `useState`, but kept per key across page switches and reloads of the browser tab.
 * Put the log id into the key, e.g. `filter.${ocelId}`; the value must be JSON.
 *
 * Example: `const [search, setSearch] = usePageState("profile.search." + ocelId, "")` keeps a search box's text.
 */
export const usePageState = <T>(key: string, initial: T) => useKeyedState(key, initial, true);

/**
 * Like `usePageState`, but in memory only: kept across page switches, lost on a reload. For values that are not
 * JSON (e.g. a `Map`) or that are only worth keeping while the tab lives (e.g. a counter that forces a new layout).
 */
export const useMemoryState = <T>(key: string, initial: T) => useKeyedState(key, initial, false);

/** Values kept by `keep` (memory only, not reactive). */
const kept = new Map<string, unknown>();

/**
 * The value kept under a key by `keep`, or undefined. Not reactive: for values that a component reads when it
 * mounts (layouts, zoom and pan, scroll position), not for values that other components display.
 */
export const recall = <T>(key: string): T | undefined => kept.get(key) as T | undefined;

/** Keep a value under a key in memory until the tab is closed or reloaded (`recall` reads it). */
export const keep = (key: string, value: unknown) => {
  kept.set(key, value);
};

/**
 * True if two lists of inputs are the same: entry by entry identical (`Object.is`), or, for entries that are not,
 * equal maps (same keys, identical values) or equal JSON; functions always count as the same (callbacks are created
 * anew on every visit of a page). Used to decide whether a kept layout still fits the current data; the JSON
 * comparison only runs when the references differ (e.g. a graph derived anew from the same response).
 *
 * Example: `sameInputs([graph, "LR"], [structuredClone(graph), "LR"])` is true.
 */
export const sameInputs = (a: readonly unknown[], b: readonly unknown[]): boolean =>
  a.length === b.length && a.every((x, i) => sameValue(x, b[i]));

const sameValue = (x: unknown, y: unknown): boolean => {
  if (Object.is(x, y)) return true;
  if (typeof x === "function" && typeof y === "function") return true;
  if (x instanceof Map && y instanceof Map)
    return x.size === y.size && [...x].every(([k, v]) => y.has(k) && Object.is(v, y.get(k)));
  if (typeof x !== "object" || typeof y !== "object" || x === null || y === null) return false;
  try {
    return JSON.stringify(x) === JSON.stringify(y);
  } catch {
    return false;
  }
};
