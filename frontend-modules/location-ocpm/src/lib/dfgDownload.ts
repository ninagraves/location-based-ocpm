// Download of the drawn DFG (Nina, 2026-11-20; vector files, legend and interactive page: Nina, 2026-11-23).
//
// The graph is not photographed from the page (as html-to-image did before) but drawn again from the layout as plain
// shapes (`graphScene`, lib/dfgDrawing.ts). That scene is written as
// - SVG: vector, plain SVG shapes and texts, hover texts as `<title>` (shown by browsers);
// - PDF: vector (jsPDF drawing commands), fonts Helvetica / Helvetica Bold; no hover;
// - PNG: the SVG rasterised at up to 4 pixels per CSS pixel;
// - HTML: one self-contained page with the SVG, a tooltip like the page's, zoom (wheel, +/−) and pan (drag).
// All files are light (white background), whatever the page's colour scheme.
//
// Example: `downloadDrawing(drawing, "pdf", "directly-follows-graph", { legend: true })` saves
// "directly-follows-graph.pdf": one page of the drawing's size with the graph and the legend below it.

import { jsPDF } from "jspdf";
import { EXPORT_COLOURS, type Drawing, graphScene, type Group, type Scene, sceneSvg, type Segment, type Shape } from "./dfgDrawing";

/** File formats of the download. */
export type ImageFormat = "svg" | "pdf" | "png" | "html";

/** The formats in the order of the menu, with their labels and a hint. */
export const IMAGE_FORMATS: { format: ImageFormat; label: string; hint: string }[] = [
  { format: "pdf", label: "PDF (vector)", hint: "Sharp at any zoom; for papers and printing" },
  { format: "svg", label: "SVG (vector)", hint: "Sharp at any zoom; editable (e.g. Inkscape); hover texts in a browser" },
  { format: "html", label: "HTML (interactive)", hint: "Opens in a browser: zoom, pan and the hover texts of the page" },
  { format: "png", label: "PNG (image)", hint: "High-resolution image, up to 4 pixels per screen pixel" },
];

/** Largest PNG: at most 4 pixels per CSS pixel, 16 000 pixels per side and 120 million pixels (browser canvas limits). */
const PNG_LIMITS = { scale: 4, side: 16000, area: 120e6 };

/**
 * Save a URL as a file through a temporary link.
 *
 * @param href Object URL or data URL.
 * @param filename The file name with extension.
 */
const save = (href: string, filename: string) => {
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  link.click();
};

/** Save text as a file. */
const saveText = (content: string, type: string, filename: string) => {
  const url = URL.createObjectURL(new Blob([content], { type }));
  save(url, filename);
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
};

/** Draw path segments into the PDF's current path. */
const pdfPath = (pdf: jsPDF, d: Segment[]) => {
  for (const s of d) {
    if (s.op === "M") pdf.moveTo(s.p.x, s.p.y);
    else if (s.op === "L") pdf.lineTo(s.p.x, s.p.y);
    else if (s.op === "C") pdf.curveTo(s.c1.x, s.c1.y, s.c2.x, s.c2.y, s.p.x, s.p.y);
    else pdf.close();
  }
};

/**
 * Draw one shape into the PDF. Texts use Helvetica; a text more than 3 px wider in Helvetica than on the page is set
 * slightly smaller so that it stays inside its box.
 */
const pdfShape = (pdf: jsPDF, s: Shape) => {
  const style = (fill?: string, stroke?: string) => (fill && stroke ? "FD" : fill ? "F" : "S");
  if ("fill" in s && s.fill && s.fill !== "none") pdf.setFillColor(s.fill);
  if ("stroke" in s && s.stroke) {
    pdf.setDrawColor(s.stroke);
    pdf.setLineWidth(s.strokeWidth ?? 1);
  }
  switch (s.kind) {
    case "rect":
      if (s.r) pdf.roundedRect(s.x, s.y, s.w, s.h, s.r, s.r, style(s.fill, s.stroke));
      else pdf.rect(s.x, s.y, s.w, s.h, style(s.fill, s.stroke));
      return;
    case "circle":
      pdf.circle(s.cx, s.cy, s.r, style(s.fill, s.stroke));
      return;
    case "path": {
      if (s.hit || s.d.length === 0) return;
      pdfPath(pdf, s.d);
      const fill = s.fill && s.fill !== "none";
      if (fill && s.stroke) pdf.fillStroke();
      else if (fill) pdf.fill();
      else pdf.stroke();
      return;
    }
    case "text": {
      pdf.setFont("helvetica", s.weight >= 600 ? "bold" : "normal");
      // jsPDF font sizes are points; with the px_scaling hotfix one pixel is 0.75 pt.
      let size = s.size * 0.75;
      pdf.setFontSize(size);
      const width = pdf.getTextWidth(s.text);
      // Allowance of 3 px: digits are wider in Helvetica than in many page fonts, and short labels have room to spare.
      const room = s.width + 3;
      if (s.width > 0 && width > room) {
        size *= room / width;
        pdf.setFontSize(size);
      }
      pdf.setTextColor(s.fill);
      pdf.text(s.text, s.x, s.y, { align: s.anchor === "middle" ? "center" : "left", baseline: "alphabetic" });
    }
  }
};

/**
 * The scene as a vector PDF of one page of the scene's size.
 *
 * @param scene The scene.
 * @returns The jsPDF document (call `.save(name)`).
 */
export const scenePdf = (scene: Scene): jsPDF => {
  const pdf = new jsPDF({
    orientation: scene.width >= scene.height ? "landscape" : "portrait",
    unit: "px",
    format: [scene.width, scene.height],
    hotfixes: ["px_scaling"],
    compress: true,
  });
  pdf.setLineCap("round");
  pdf.setLineJoin("round");
  pdf.setFillColor(EXPORT_COLOURS.background);
  pdf.rect(0, 0, scene.width, scene.height, "F");
  const draw = (g: Group) => g.shapes.forEach((s) => ("shapes" in s ? draw(s) : pdfShape(pdf, s)));
  scene.groups.forEach(draw);
  return pdf;
};

/**
 * The scene as a PNG blob: the SVG drawn on a canvas at the largest scale within `PNG_LIMITS`.
 *
 * @param scene The scene.
 * @returns The PNG.
 */
export const scenePng = async (scene: Scene): Promise<Blob> => {
  const scale = Math.min(
    PNG_LIMITS.scale,
    PNG_LIMITS.side / Math.max(scene.width, scene.height),
    Math.sqrt(PNG_LIMITS.area / (scene.width * scene.height)),
  );
  const url = URL.createObjectURL(new Blob([sceneSvg(scene)], { type: "image/svg+xml" }));
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(scene.width * scale);
    canvas.height = Math.round(scene.height * scale);
    const context = canvas.getContext("2d");
    if (!context) throw new Error("The browser cannot draw the image.");
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("The image is too large for the browser."))), "image/png"),
    );
  } finally {
    URL.revokeObjectURL(url);
  }
};

/** Script of the interactive page: tooltip from `data-hover`, zoom with the wheel or the buttons, pan by dragging. */
const PAGE_SCRIPT = `
const svg = document.querySelector("svg");
const tip = document.getElementById("tip");
const full = svg.viewBox.baseVal;
const home = { x: full.x, y: full.y, w: full.width, h: full.height };
let view = { ...home };
svg.removeAttribute("width");
svg.removeAttribute("height");
const apply = () => svg.setAttribute("viewBox", view.x + " " + view.y + " " + view.w + " " + view.h);
const point = (e) => {
  const r = svg.getBoundingClientRect();
  const s = Math.max(view.w / r.width, view.h / r.height);
  const ox = (r.width * s - view.w) / 2, oy = (r.height * s - view.h) / 2;
  return { x: view.x - ox + (e.clientX - r.left) * s, y: view.y - oy + (e.clientY - r.top) * s, s };
};
const zoom = (factor, e) => {
  const r = svg.getBoundingClientRect();
  const p = e ? point(e) : { x: view.x + view.w / 2, y: view.y + view.h / 2 };
  const w = Math.min(home.w * 4, Math.max(home.w / 200, view.w / factor));
  const k = w / view.w;
  view = { x: p.x - (p.x - view.x) * k, y: p.y - (p.y - view.y) * k, w, h: view.h * k };
  apply();
};
svg.addEventListener("wheel", (e) => { e.preventDefault(); zoom(Math.exp(-e.deltaY * 0.0015), e); }, { passive: false });
let drag = null;
svg.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, y: e.clientY, view: { ...view }, s: point(e).s }; svg.setPointerCapture(e.pointerId); svg.classList.add("dragging"); });
svg.addEventListener("pointermove", (e) => {
  if (drag) { view = { ...drag.view, x: drag.view.x - (e.clientX - drag.x) * drag.s, y: drag.view.y - (e.clientY - drag.y) * drag.s }; apply(); return; }
  const target = e.target.closest ? e.target.closest("[data-hover]") : null;
  if (!target) { tip.style.display = "none"; return; }
  const [first, ...rest] = target.getAttribute("data-hover").split("\\n");
  tip.replaceChildren();
  const b = document.createElement("b"); b.textContent = first; tip.appendChild(b);
  for (const line of rest) { const d = document.createElement("div"); d.textContent = line; tip.appendChild(d); }
  tip.style.display = "block";
  const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
  const y = e.clientY + 16 + tip.offsetHeight > window.innerHeight ? e.clientY - tip.offsetHeight - 10 : e.clientY + 16;
  tip.style.left = x + "px"; tip.style.top = y + "px";
});
const stop = () => { drag = null; svg.classList.remove("dragging"); };
svg.addEventListener("pointerup", stop);
svg.addEventListener("pointercancel", stop);
svg.addEventListener("pointerleave", () => { tip.style.display = "none"; });
document.getElementById("in").onclick = () => zoom(1.4);
document.getElementById("out").onclick = () => zoom(1 / 1.4);
document.getElementById("fit").onclick = () => { view = { ...home }; apply(); };
apply();
`;

/**
 * The scene as a self-contained interactive HTML page (no external files): the SVG fills the window; hovering a node,
 * an object-type circle or an arc shows the same numbers as on the page; the wheel or the buttons zoom, dragging pans.
 *
 * @param scene The scene.
 * @param title Title of the page.
 * @returns The HTML text.
 */
export const sceneHtml = (scene: Scene, title: string): string => `<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title.replace(/</g, "&lt;")}</title>
<style>
  html, body { margin: 0; height: 100%; background: ${EXPORT_COLOURS.background}; color: ${EXPORT_COLOURS.text}; font-family: ${scene.fontFamily}; }
  svg { display: block; width: 100vw; height: 100vh; cursor: grab; touch-action: none; user-select: none; }
  svg.dragging { cursor: grabbing; }
  .node:hover > rect:first-of-type { stroke-width: 2; }
  .arc:hover > path:nth-of-type(2) { filter: brightness(0.8); }
  #tip { position: fixed; display: none; pointer-events: none; max-width: 420px; padding: 5px 8px; font-size: 12px; line-height: 1.4;
    background: #ffffff; border: 1px solid #ced4da; border-radius: 4px; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15); }
  #bar { position: fixed; top: 8px; right: 8px; display: flex; gap: 4px; }
  #bar button { font: inherit; font-size: 13px; min-width: 28px; height: 26px; border: 1px solid #ced4da; border-radius: 4px; background: #ffffff; cursor: pointer; }
  #bar button:hover { background: #f1f3f5; }
</style>
</head>
<body>
${sceneSvg(scene, "data")}
<div id="tip"></div>
<div id="bar"><button id="in" title="Zoom in">+</button><button id="out" title="Zoom out">−</button><button id="fit" title="Show the whole graph">Fit</button></div>
<script>${PAGE_SCRIPT}</script>
</body>
</html>
`;

/**
 * Download the drawing in one format.
 *
 * @param drawing Nodes and arcs as on the page, with colours and the arc labels' meaning.
 * @param format PDF, SVG, HTML or PNG.
 * @param name File name without extension.
 * @param options `legend`: add the legend of object types and symbols below the graph.
 * @returns Resolves when the file has been handed to the browser; rejects if the graph is empty or too large.
 */
export const downloadDrawing = async (drawing: Drawing, format: ImageFormat, name: string, options: { legend: boolean }): Promise<void> => {
  const scene = graphScene(drawing, options);
  if (format === "svg") saveText(sceneSvg(scene), "image/svg+xml", `${name}.svg`);
  else if (format === "html") saveText(sceneHtml(scene, "Directly-follows graph"), "text/html", `${name}.html`);
  else if (format === "pdf") scenePdf(scene).save(`${name}.pdf`);
  else {
    const url = URL.createObjectURL(await scenePng(scene));
    save(url, `${name}.png`);
    window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
  }
};
