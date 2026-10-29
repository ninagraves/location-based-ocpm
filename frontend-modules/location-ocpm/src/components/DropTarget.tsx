// Drop target for files: wraps a button or field so that a file can be dragged onto it.
// Documented in docs/pages/configuration.md, section "Loading files by drag and drop".
import { Box } from "@mantine/core";
import { type DragEvent, type ReactNode, useState } from "react";
import { UI } from "../lib/palette";
import { useScheme } from "./plots";

/**
 * Wraps `children` so that dropping a file on them calls `onFile`, like choosing the file in the
 * dialog. While a file is dragged over, the area gets a dashed outline in the primary colour.
 *
 * @param accept File name endings that are taken (e.g. [".csv"]); other files are ignored and
 *   reported via `onReject`. Empty: every file.
 * @param onFile Called with the first dropped file.
 * @param onReject Called with the file name if it does not end in one of `accept`.
 */
export const DropTarget = ({
  accept = [],
  onFile,
  onReject,
  children,
}: {
  accept?: string[];
  onFile: (file: File) => void;
  onReject?: (name: string) => void;
  children: ReactNode;
}) => {
  const scheme = useScheme();
  const [over, setOver] = useState(false);
  const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer.types).includes("Files");
  return (
    <Box
      onDragOver={(e) => {
        if (!hasFiles(e)) return;
        e.preventDefault(); // allows the drop
        e.dataTransfer.dropEffect = "copy";
        setOver(true);
      }}
      onDragLeave={(e) => {
        // Only when the pointer leaves the area, not when it moves onto a child.
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOver(false);
      }}
      onDrop={(e) => {
        if (!hasFiles(e)) return;
        e.preventDefault(); // stops the browser from opening the file
        setOver(false);
        const file = e.dataTransfer.files[0];
        if (!file) return;
        const name = file.name.toLowerCase();
        if (accept.length && !accept.some((ending) => name.endsWith(ending))) onReject?.(file.name);
        else onFile(file);
      }}
      style={{
        borderRadius: 4,
        outline: over ? `2px dashed ${UI[scheme].primary}` : "2px dashed transparent",
        outlineOffset: 2,
      }}
    >
      {children}
    </Box>
  );
};
