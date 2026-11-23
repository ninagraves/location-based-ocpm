// The one colour per object type that every page, chart and download of the module uses (Nina, 2026-11-23).
// Documented in docs/resources/object-type-colours.md.
import { useMemo } from "react";
import { type ObjectTypeEntry, useGetObjectTypes } from "../api/locationBasedOcpm";
import { useScheme } from "../components/plots";
import { emphasisColourMap, type Scheme } from "./palette";

/** Colours of the object types of a log (`useObjectTypeColours`). */
export type ObjectTypeColours = {
  /** Colour per object type in the page's colour scheme. */
  colours: Map<string, string>;
  /** Colour per object type in the light scheme, for downloads (always on white). */
  exportColours: Map<string, string>;
  /** The handling-unit types, in colour order (most handling units first). */
  huTypes: string[];
  /** True once the object types of the log are loaded (before, both maps are empty). */
  loaded: boolean;
};

/**
 * Colour per object type from the module-wide order (`GET /{ocel_id}/object-types`, most objects first;
 * handling units for a handling-unit type): the handling-unit types get the signature colours first (petrol, pink,
 * turquoise, blue, orange, then further categorical colours), all other types the remaining categorical colours.
 * Since the order belongs to the log, not to a page or chart, a type has the same colour everywhere.
 *
 * Example: handling-unit types pallet (3 handling units) and box (1), other type order. Every page draws pallet
 * petrol (#006165) and box pink (#CE108A); order is #5291cc, on the directly-follows graph paler (#5291cc8c).
 *
 * @param types The object types of the log in colour order (`getObjectTypes`).
 * @param scheme Light or dark.
 * @param fadeOther True: the other (not handling-unit) types are paler (`FADED_ALPHA`), as on the directly-follows graph.
 * @returns Colour per object type.
 */
export const objectTypeColourMap = (types: readonly ObjectTypeEntry[], scheme: Scheme, fadeOther = false) =>
  emphasisColourMap(
    types.filter((t) => t.handling_units).map((t) => t.object_type),
    types.filter((t) => !t.handling_units).map((t) => t.object_type),
    scheme,
    fadeOther,
  );

/**
 * The colours of the object types of a log for the current colour scheme and for downloads (`objectTypeColourMap`).
 * Every component that colours object types takes its colours from here (or is handed them by its page).
 *
 * @param ocelId Id of the log.
 * @param fadeOther True: the other (not handling-unit) types are paler, as on the directly-follows graph.
 * @returns Colours per object type, the handling-unit types and whether the order is loaded.
 */
export const useObjectTypeColours = (ocelId: string, fadeOther = false): ObjectTypeColours => {
  const scheme = useScheme();
  const { data } = useGetObjectTypes(ocelId);
  return useMemo(() => {
    const types = data ?? [];
    const colours = objectTypeColourMap(types, scheme, fadeOther);
    return {
      colours,
      exportColours: scheme === "light" ? colours : objectTypeColourMap(types, "light", fadeOther),
      huTypes: types.filter((t) => t.handling_units).map((t) => t.object_type),
      loaded: data !== undefined,
    };
  }, [data, scheme, fadeOther]);
};
