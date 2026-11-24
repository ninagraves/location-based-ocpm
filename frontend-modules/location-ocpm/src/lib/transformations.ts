// Shared bits of the transformations page (draft): the page filters and the readable kind names.
// Documented in docs/pages/transformations.md.
import type { GetTransformationOverviewKind } from "../api/locationBasedOcpm";
import { usePageState } from "./pageState";

/** The page filters of the transformations page; each selects whole transformation events. */
export type TransformationFilter = { consumes: string[]; produces: string[]; kind: GetTransformationOverviewKind };

/** No filter set. */
export const EMPTY_TRANSFORMATION_FILTER: TransformationFilter = { consumes: [], produces: [], kind: "all" };

/** Readable names of the kinds (and of "all" in the kind filter). */
export const KIND_LABELS: Record<string, string> = {
  all: "all",
  both: "both",
  consumption_only: "consumption only",
  production_only: "production only",
};

/**
 * The page filters of a log, kept across page switches (`usePageState`).
 *
 * @param ocelId Id of the log.
 */
export const useTransformationFilter = (ocelId: string) =>
  usePageState<TransformationFilter>(`transformations.filter.${ocelId}`, EMPTY_TRANSFORMATION_FILTER);

/** Request option so that lists are sent as `a=x&a=y`, as FastAPI expects. */
export const listRequest = { paramsSerializer: { indexes: null } };
