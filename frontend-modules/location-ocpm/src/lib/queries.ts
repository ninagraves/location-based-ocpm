// Which requests belong to the module or to one log, and how long their answers are kept in the browser.
// Documented in docs/hosting/state-and-caching.md, section "Page state".
import { type Query, type QueryClient, useQueryClient } from "@tanstack/react-query";

/**
 * How long the answer of a module request is kept in the browser after no page shows it any more (React Query's
 * `gcTime`; its default is 5 minutes). A page opened again within this time shows the kept answer at once and checks
 * it in the background (React Query refetches on mount, as before), so it is never older than the log and
 * configuration. Longer means more memory in the tab.
 */
export const KEEP_ANSWERS_MS = 30 * 60 * 1000;

/** Key prefix of the module's hand-written queries (the generated ones start with the route's URL). */
export const QUERY_PREFIX = "locationBasedOcpm";

/** True if a query key belongs to the module (hand-written `["locationBasedOcpm", ...]` or a generated URL key). */
export const isModuleQuery = (key: readonly unknown[]) =>
  key[0] === QUERY_PREFIX || String(key[0]).includes("/locationBasedOcpm/v1/");

/**
 * True if a query belongs to a log of this module, i.e. may change with its configuration or settings: generated keys
 * contain `/locationBasedOcpm/v1/<log id>/`, hand-written ones `["locationBasedOcpm", ..., <log id>, ...]`.
 *
 * Example: `queryClient.invalidateQueries({ predicate: ofLog(ocelId) })` refetches every page's content of the log.
 */
export const ofLog = (ocelId: string) => (query: { queryKey: readonly unknown[] }) => {
  const key = query.queryKey;
  return (key[0] === QUERY_PREFIX && key.includes(ocelId)) || String(key[0]).includes(`/locationBasedOcpm/v1/${ocelId}/`);
};

const raised = new WeakSet<QueryClient>();

/** Raise the `gcTime` of a module query to `KEEP_ANSWERS_MS` (React Query keeps the longest `gcTime` it saw). */
const raise = (query: Query) => {
  if (isModuleQuery(query.queryKey) && (query.gcTime ?? 0) < KEEP_ANSWERS_MS)
    query.setOptions({ ...query.options, gcTime: KEEP_ANSWERS_MS });
};

/**
 * Keep the module's answers for `KEEP_ANSWERS_MS` in Ocelescope's query client (once per client; queries of other
 * modules are left alone). Called by every page of the module (`ModulePage`).
 */
export const useKeptAnswers = () => {
  const client = useQueryClient();
  if (raised.has(client)) return;
  raised.add(client);
  const cache = client.getQueryCache();
  for (const query of cache.getAll()) raise(query);
  cache.subscribe((event) => {
    if (event.type === "added") raise(event.query);
  });
};
