// The settings bar's state (Nina, 2026-11-20): kept in the backend per log (`global_settings.py`), so every page and
// every request sees the same values. Documented in docs/pages/settings-bar.md.
import { useQueryClient } from "@tanstack/react-query";
import { type SettingsResult, type SettingsUpdate, useGetSettings, useUpdateSettings } from "../api/locationBasedOcpm";
import { ofLog } from "./queries";

/** The settings bar of a log (level, transformations as processing operations, Locations: low | high). */
export const useGlobalSettings = (ocelId: string) => useGetSettings(ocelId, { query: { enabled: !!ocelId } });

/**
 * Change settings of a log. On success every query of the log is refetched (settings, configuration and all page
 * content), since all of them may depend on the settings; `onResult` gets the outcome (also with blocking errors).
 *
 * Example: `change({ location_mode: "low" })` switches every page to low-level locations.
 */
export const useChangeSettings = (ocelId: string, onResult?: (result: SettingsResult) => void) => {
  const queryClient = useQueryClient();
  const mutation = useUpdateSettings({
    mutation: {
      onSuccess: async (result) => {
        onResult?.(result);
        if (result.applied) await queryClient.invalidateQueries({ predicate: ofLog(ocelId) });
      },
    },
  });
  const change = (update: SettingsUpdate) => mutation.mutate({ ocelId, data: update });
  return { change, isPending: mutation.isPending, error: mutation.error };
};
