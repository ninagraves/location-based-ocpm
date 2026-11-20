// The page filter bar's state (concept section "Page Filter Bar"), kept per log across pages
// and reloads. Documented in docs/pages/overview.md, section "Page filter bar".
import { type GetKeyNumbersParams, useGetConfig } from "../api/locationBasedOcpm";
import { usePageState } from "./pageState";
import { useGlobalSettings } from "./settings";

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

/** Prefixes of high-level locations and single ids in the filter values (backend `overview/filters.py`). */
export const HIGH_LEVEL_PREFIX = "[high-level] ";
export const HU_PREFIX = "[hu] ";
export const EVENT_PREFIX = "[event] ";
const PREFIXES = [HIGH_LEVEL_PREFIX, HU_PREFIX, EVENT_PREFIX];

/** A filter value without its prefix, e.g. "s1" for "[hu] s1". */
export const shown = (value: string) => {
  const prefix = PREFIXES.find((p) => value.startsWith(p));
  return prefix ? value.slice(prefix.length) : value;
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

/** Clear every filter (also the role switch). Locations: low | high is in the settings bar and stays. */
export const cleared = (_f: PageFilter): PageFilter => emptyFilter;

/** True if any filter value is set (the role switch alone filters nothing). */
export const isActive = (f: PageFilter) =>
  [f.activities, f.exclude_activities, f.locations, f.exclude_locations, f.object_types, f.exclude_object_types].some(
    (values) => values.length > 0,
  );

/**
 * The location context of the applied configuration: withHighLevel = high-level locations are configured;
 * high = the settings bar is on Locations: high (only possible with high-level locations); withTypes = vehicles
 * or storage units are configured (location-type options).
 */
export const useLocationContext = (ocelId: string) => {
  const { data } = useGetConfig(ocelId);
  const { data: settings } = useGlobalSettings(ocelId);
  const config = data?.config;
  const withHighLevel = !!config?.high_level_locations;
  return {
    withHighLevel,
    high: withHighLevel && settings?.location_mode === "high",
    withTypes: !!config?.vehicles || !!config?.storage_units,
  };
};

/** The filter of a log, shared by all pages. */
export const usePageFilter = (ocelId: string) => usePageState<PageFilter>(`filter.${ocelId}`, emptyFilter);

/** The filter lists, i.e. the filter's keys without the location role. */
export type FilterKey = Exclude<keyof PageFilter, "location_role">;

/** Include and exclude list of the same filter: a value can be in only one of them. */
const OPPOSITE: Record<FilterKey, FilterKey> = {
  activities: "exclude_activities",
  exclude_activities: "activities",
  locations: "exclude_locations",
  exclude_locations: "locations",
  object_types: "exclude_object_types",
  exclude_object_types: "object_types",
};

/**
 * Special values of which a filter list holds at most one when set by a chart click
 * (one category each, e.g. movement vs transformation events).
 */
export const CATEGORIES: readonly (readonly string[])[] = [
  ["[movement events]", "[transformation events]", "[processing operations]"],
  ["[vehicles]", "[storage units]"],
  ["[fully located events]", "[partially located events]", "[unlocated events]"],
  ["[agreeing events]", "[disagreeing events]"],
  ["[fully located HUs]", "[partially located HUs]", "[unlocated HUs]"],
];

/**
 * Set one filter list; the values are removed from the opposite list (include vs exclude),
 * so a value is never included and excluded at the same time.
 */
export const withValues = (f: PageFilter, key: FilterKey, values: string[]): PageFilter => {
  const opposite = OPPOSITE[key];
  return { ...f, [key]: values, [opposite]: f[opposite].filter((v) => !values.includes(v)) };
};

/**
 * Add one value to a filter list (a chart click): other values of its category are removed from
 * the list, and the value is removed from the opposite list.
 */
export const withValue = (f: PageFilter, key: FilterKey, value: string): PageFilter => {
  const category = CATEGORIES.find((values) => values.includes(value)) ?? [];
  const kept = f[key].filter((v) => v !== value && !category.includes(v));
  return withValues(f, key, [...kept, value]);
};

/**
 * Query parameters of a filtered route. The location mode is not among them: the backend takes it from the settings
 * bar. A filter stored before 2026-11-20 may still hold `location_mode`; it is dropped here.
 */
export const filterParams = (f: PageFilter): GetKeyNumbersParams => {
  const { location_mode: _old, ...params } = f as PageFilter & { location_mode?: string };
  return params;
};

/** Request option so that lists are sent as `a=x&a=y`, as FastAPI expects. */
export const filterRequest = { paramsSerializer: { indexes: null } };
