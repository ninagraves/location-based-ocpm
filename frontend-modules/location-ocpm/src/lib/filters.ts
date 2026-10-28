// The page filter bar's state (concept section "Page Filter Bar"), kept per log across pages
// and reloads. Documented in docs/pages/overview.md, section "Page filter bar".
import type { GetKeyNumbersParams } from "../api/locationBasedOcpm";
import { usePageState } from "./pageState";

/** The filter bar's state; sent as query parameters to every filtered route. */
export type PageFilter = {
  activities: string[];
  exclude_activities: string[];
  locations: string[];
  exclude_locations: string[];
  location_role: "either" | "before" | "after";
  object_types: string[];
  exclude_object_types: string[];
};

/** No filter set. */
export const emptyFilter: PageFilter = {
  activities: [],
  exclude_activities: [],
  locations: [],
  exclude_locations: [],
  location_role: "either",
  object_types: [],
  exclude_object_types: [],
};

/** True if any filter value is set (the role switch alone filters nothing). */
export const isActive = (f: PageFilter) =>
  [f.activities, f.exclude_activities, f.locations, f.exclude_locations, f.object_types, f.exclude_object_types].some(
    (values) => values.length > 0,
  );

/** The filter of a log, shared by all pages. */
export const usePageFilter = (ocelId: string) => usePageState<PageFilter>(`filter.${ocelId}`, emptyFilter);

/** Query parameters of a filtered route. */
export const filterParams = (f: PageFilter): GetKeyNumbersParams => ({ ...f });

/** Request option so that lists are sent as `a=x&a=y`, as FastAPI expects. */
export const filterRequest = { paramsSerializer: { indexes: null } };
