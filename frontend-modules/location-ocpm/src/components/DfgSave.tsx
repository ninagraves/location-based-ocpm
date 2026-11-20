// "Save to session" at the bottom of the DFG sidebar (Nina, 2026-11-16/19).

import { Button, Divider, Group, SegmentedControl, Stack, Text, TextInput, Tooltip } from "@mantine/core";
import { InfoIcon } from "lucide-react";
import { useState } from "react";
import { type DfgArc, type DirectlyFollowsGraph, saveDirectlyFollowsGraph } from "../api/locationBasedOcpm";
import { applyArcSettings } from "../lib/dfgView";
import { errorText } from "../lib/errors";
import { num } from "../lib/format";
import { usePageState } from "../lib/pageState";
import { arcSettings, type DfgState, toRequest } from "./DfgSettings";

/** What is saved: the model (Ocelescope's DFG resource) or the log (a new OCEL). */
export type SaveKind = "model" | "log";
/** Which version: as projected (Arcs (display) at all, no hand removals) or as displayed (as drawn). */
export type SaveVersion = "projected" | "displayed";

/** Hover text of the section. */
const SAVE_INFO =
  "Saves the current graph to the session as a normal Ocelescope resource. Model: a Directly-Follows Graph resource (its arcs with traversals and objects), shown on Ocelescope's resource pages. Log: a new OCEL with the events of the included traces (after the event categories, the activity projection and the variant filter) and their relations; it appears in the list of logs. Projected: the graph with Arcs (display) at all and no arcs removed by hand (Stay connected as set); for the log, all events of the included traces. Displayed: exactly the drawn graph; for the log, without the events of activities that are not drawn (arcs hidden between two drawn activities cannot be removed from a log).";

/**
 * The arcs to save as the model: as drawn, or as projected (the same arc settings, but Arcs (display) at "all" and no
 * arcs removed by hand).
 *
 * @param base The backend's graph (all arcs of the included traces).
 * @param state The applied page state.
 * @param version Projected or displayed.
 * @returns The arcs.
 */
export const arcsToSave = (base: DirectlyFollowsGraph, state: DfgState, version: SaveVersion): DfgArc[] => {
  const settings = arcSettings(state);
  const used = version === "displayed" ? settings : { ...settings, count: () => null, total: null, removed: [] };
  return applyArcSettings(base, used).arcs;
};

/**
 * The section "Save to session": model or log, projected or displayed, a name and the button. Saves what was last
 * drawn (the applied settings); while a change is waiting, the button waits too.
 *
 * Example: Model + Displayed saves the drawn arcs as "DFG model (displayed)"; Log + Projected saves a new OCEL with
 * the events of the included traces.
 *
 * @param ocelId The log.
 * @param base The backend's graph for the applied settings (all arcs of the included traces).
 * @param applied The applied page state (the one drawn).
 * @param pending True while a change waits for the recalculation.
 */
export const DfgSave = ({
  ocelId,
  base,
  applied,
  pending,
}: {
  ocelId: string;
  base: DirectlyFollowsGraph;
  applied: DfgState;
  pending: boolean;
}) => {
  // Kept with the page (per log), like the rest of the sidebar.
  const [kind, setKind] = usePageState<SaveKind>(`dfg.save.kind.${ocelId}`, "model");
  const [version, setVersion] = usePageState<SaveVersion>(`dfg.save.version.${ocelId}`, "displayed");
  const [name, setName] = usePageState(`dfg.save.name.${ocelId}`, "");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const defaultName = `DFG ${kind} (${version})`;

  const save = async () => {
    setBusy(true);
    setResult(null);
    try {
      const drawn = applyArcSettings(base, arcSettings(applied));
      const saved = await saveDirectlyFollowsGraph(ocelId, {
        kind,
        name: name.trim() || defaultName,
        request: toRequest(applied),
        arcs: kind === "model" ? arcsToSave(base, applied, version) : [],
        activities: kind === "log" && version === "displayed" ? drawn.activities.map((a) => a.activity) : null,
      });
      const size = saved.kind === "model" ? `${num(saved.size)} arcs` : `${num(saved.size)} events`;
      setResult({ ok: true, text: `Saved “${saved.name}” to the session (${size}).` });
    } catch (e) {
      setResult({ ok: false, text: errorText(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack gap={4} pt={6}>
      <Divider
        label={
          <Group gap={4} wrap="nowrap">
            <Text size="xs" fw={600}>Save to session</Text>
            <Tooltip label={SAVE_INFO} multiline w={320} withinPortal>
              <InfoIcon size={12} style={{ opacity: 0.6 }} aria-label="About saving to the session" />
            </Tooltip>
          </Group>
        }
        labelPosition="left"
      />
      <Group gap={4} grow wrap="nowrap">
        <SegmentedControl
          size="xs"
          value={kind}
          onChange={(v) => setKind(v as SaveKind)}
          data={[
            { value: "model", label: "Model" },
            { value: "log", label: "Log" },
          ]}
        />
        <SegmentedControl
          size="xs"
          value={version}
          onChange={(v) => setVersion(v as SaveVersion)}
          data={[
            { value: "projected", label: "Projected" },
            { value: "displayed", label: "Displayed" },
          ]}
        />
      </Group>
      <Group gap={4} wrap="nowrap">
        <TextInput
          size="xs"
          style={{ flex: 1 }}
          placeholder={defaultName}
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
          aria-label="Name in the session"
        />
        <Tooltip label="Waiting for the graph to update" disabled={!pending} withinPortal>
          <Button size="xs" loading={busy} disabled={pending} onClick={save}>
            Save
          </Button>
        </Tooltip>
      </Group>
      {result && (
        <Text size="xs" c={result.ok ? "dimmed" : "red"}>
          {result.text}
        </Text>
      )}
    </Stack>
  );
};
