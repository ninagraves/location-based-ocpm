// Download of the drawn DFG as an image: SVG, PDF or PNG (Nina, 2026-11-20).
//
// The same approach as Ocelescope's graph viewer (`GraphFlow/utils/download.ts` in @ocelescope/resources): html-to-image
// draws React Flow's viewport (nodes, arcs, arc labels) into an image of the whole graph, whatever is zoomed in on
// screen; the controls are left out. The PDF holds the image as a PNG (jsPDF), so it is not a vector graphic; the SVG
// is one (with the node and label HTML embedded as foreignObject).
//
// Example: `downloadGraph(container, "pdf", "directly-follows-graph")` saves "directly-follows-graph.pdf" with the
// graph on one page of the image's size.

import { toPng, toSvg } from "html-to-image";
import { jsPDF } from "jspdf";

/** File formats of the download. */
export type ImageFormat = "svg" | "pdf" | "png";

/** The formats in the order of the menu, with their labels. */
export const IMAGE_FORMATS: { format: ImageFormat; label: string }[] = [
  { format: "svg", label: "SVG (vector)" },
  { format: "pdf", label: "PDF" },
  { format: "png", label: "PNG" },
];

/** Longest side of the image in CSS pixels (PNG and PDF are drawn at twice this, `PIXEL_RATIO`). */
const MAX_SIDE = 3000;
/** Pixels per CSS pixel of PNG and PDF, for sharp print. */
const PIXEL_RATIO = 2;
/** White space around the graph, as a share of its width and height. */
const PADDING = 0.03;

/** A rectangle in flow coordinates. */
interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * The flow-coordinate box of everything drawn in the viewport: nodes, arc paths and arc labels. Measured on the page
 * (not from the node positions), so arcs that bend outside the nodes are included.
 *
 * @param viewport React Flow's `.react-flow__viewport` element.
 * @returns The box, or null if nothing is drawn.
 */
export const contentBox = (viewport: HTMLElement): Box | null => {
  const { a: zoom, e: tx, f: ty } = new DOMMatrixReadOnly(getComputedStyle(viewport).transform);
  const origin = viewport.parentElement?.getBoundingClientRect();
  if (!origin || !zoom) return null;
  let box: { left: number; top: number; right: number; bottom: number } | null = null;
  for (const el of viewport.querySelectorAll(".react-flow__node, .react-flow__edge path, .react-flow__edgelabel-renderer > *")) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    box = box
      ? { left: Math.min(box.left, r.left), top: Math.min(box.top, r.top), right: Math.max(box.right, r.right), bottom: Math.max(box.bottom, r.bottom) }
      : { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
  }
  if (!box) return null;
  const x = (box.left - origin.left - tx) / zoom;
  const y = (box.top - origin.top - ty) / zoom;
  return { x, y, width: (box.right - box.left) / zoom, height: (box.bottom - box.top) / zoom };
};

/**
 * Save a data URL or blob as a file through a temporary link.
 *
 * @param href The data.
 * @param filename The file name with extension.
 */
const save = (href: string, filename: string) => {
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  link.click();
};

/**
 * Download the graph drawn in `container` as an image of the whole graph.
 *
 * @param container The element around React Flow (any ancestor of `.react-flow__viewport`).
 * @param format SVG, PDF or PNG.
 * @param name File name without extension.
 * @returns Resolves when the file has been handed to the browser; rejects if the graph could not be drawn.
 */
export const downloadGraph = async (container: HTMLElement, format: ImageFormat, name: string): Promise<void> => {
  const viewport = container.querySelector<HTMLElement>(".react-flow__viewport");
  const box = viewport ? contentBox(viewport) : null;
  if (!viewport || !box) throw new Error("Nothing to download: the graph is empty.");
  const padX = box.width * PADDING;
  const padY = box.height * PADDING;
  const zoom = Math.min(1.5, MAX_SIDE / (box.width + 2 * padX), MAX_SIDE / (box.height + 2 * padY));
  const width = Math.round((box.width + 2 * padX) * zoom);
  const height = Math.round((box.height + 2 * padY) * zoom);
  const options = {
    // The page background, so that the colours fit light and dark mode.
    backgroundColor: getComputedStyle(document.body).backgroundColor || "#ffffff",
    width,
    height,
    skipFonts: true,
    style: {
      width: `${width}px`,
      height: `${height}px`,
      transform: `translate(${(padX - box.x) * zoom}px, ${(padY - box.y) * zoom}px) scale(${zoom})`,
    },
  };
  if (format === "svg") {
    save(await toSvg(viewport, options), `${name}.svg`);
    return;
  }
  const png = await toPng(viewport, { ...options, pixelRatio: PIXEL_RATIO });
  if (format === "png") {
    save(png, `${name}.png`);
    return;
  }
  const pdf = new jsPDF({ orientation: width >= height ? "landscape" : "portrait", unit: "px", format: [width, height], hotfixes: ["px_scaling"], compress: true });
  pdf.addImage(png, "PNG", 0, 0, width, height, undefined, "FAST");
  pdf.save(`${name}.pdf`);
};
