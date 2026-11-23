// Download button for a graph drawn with React Flow (top right panel): a menu with PDF, SVG, HTML and PNG and the
// option "With legend", as on the DFG page (`DownloadMenu` in DfgGraph.tsx). The graph is redrawn as a scene of plain
// shapes by `scene` (e.g. `typeGraphScene`, lib/typeGraphDrawing.ts) and written by `downloadScene` (lib/dfgDownload.ts).
import { ActionIcon, Box, Checkbox, Group, Menu, Text, Tooltip } from "@mantine/core";
import { Panel } from "@xyflow/react";
import { DownloadIcon } from "lucide-react";
import { useState } from "react";
import { downloadScene, IMAGE_FORMATS, type ImageFormat } from "../lib/dfgDownload";
import type { Scene } from "../lib/dfgDrawing";

/**
 * The download menu; place it inside `<ReactFlow>`.
 *
 * @param scene Returns the graph as currently drawn as a scene, with or without the legend.
 * @param fileName File name without extension.
 * @param title Title of the interactive HTML page.
 * @param legendLabel Label of the legend checkbox.
 */
export const GraphDownloadMenu = ({
  scene,
  fileName,
  title,
  legendLabel = "With legend",
}: {
  scene: (legend: boolean) => Scene;
  fileName: string;
  title: string;
  legendLabel?: string;
}) => {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [legend, setLegend] = useState(true);
  const download = async (format: ImageFormat) => {
    setBusy(true);
    setError(null);
    try {
      await downloadScene(scene(legend), format, fileName, title);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel position="top-right">
      <Group gap={6} wrap="nowrap">
        {error && (
          <Text size="xs" c="red">
            {error}
          </Text>
        )}
        <Menu position="bottom-end" withinPortal shadow="sm" closeOnItemClick>
          <Menu.Target>
            <Tooltip label="Download the graph" withinPortal>
              <ActionIcon size="sm" variant="default" loading={busy} aria-label="Download the graph">
                <DownloadIcon size={13} />
              </ActionIcon>
            </Tooltip>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Label>Download as</Menu.Label>
            {IMAGE_FORMATS.map(({ format, label, hint }) => (
              <Menu.Item key={format} onClick={() => download(format)}>
                <Text size="sm">{label}</Text>
                <Text size="xs" c="dimmed">
                  {hint}
                </Text>
              </Menu.Item>
            ))}
            <Menu.Divider />
            <Box px="sm" py={6}>
              <Checkbox size="xs" label={legendLabel} checked={legend} onChange={(e) => setLegend(e.currentTarget.checked)} />
            </Box>
          </Menu.Dropdown>
        </Menu>
      </Group>
    </Panel>
  );
};
