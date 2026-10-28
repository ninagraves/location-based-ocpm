// Page state that survives switching between the module's pages and reloading the browser tab.
// Values live in memory (shared by all components using the same key) and in sessionStorage
// where available. Documented in docs/hosting/state-and-caching.md.
import { type SetStateAction, useCallback, useSyncExternalStore } from "react";

const values = new Map<string, unknown>();
const listeners = new Set<() => void>();
const storageKey = (key: string) => `locationBasedOcpm.${key}`;

/** Current value of a key: memory, else sessionStorage, else `initial`. */
const read = <T>(key: string, initial: T): T => {
  if (values.has(key)) return values.get(key) as T;
  let value = initial;
  try {
    const stored = sessionStorage.getItem(storageKey(key));
    if (stored) value = JSON.parse(stored) as T;
  } catch {
    // No storage (private window, server render): start from the initial value.
  }
  values.set(key, value);
  return value;
};

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

/**
 * Like `useState`, but kept per key across page switches and reloads of the browser tab.
 * Put the log id into the key, e.g. `filter.${ocelId}`; the value must be JSON.
 */
export const usePageState = <T>(key: string, initial: T) => {
  const value = useSyncExternalStore(
    subscribe,
    () => read(key, initial),
    () => initial,
  );
  const setValue = useCallback(
    (next: SetStateAction<T>) => {
      const previous = read(key, initial);
      const resolved = typeof next === "function" ? (next as (old: T) => T)(previous) : next;
      values.set(key, resolved);
      try {
        sessionStorage.setItem(storageKey(key), JSON.stringify(resolved));
      } catch {
        // Keep the in-memory value only.
      }
      for (const listener of listeners) listener();
    },
    // `initial` only matters on first read.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key],
  );
  return [value, setValue] as const;
};
