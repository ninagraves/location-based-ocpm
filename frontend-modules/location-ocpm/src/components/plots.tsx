// Plotly basics shared by every chart: the theme-aware plot and the chart toolbar.
import { Loader, useComputedColorScheme } from "@mantine/core";
import { useMounted } from "@mantine/hooks";
import { type ComponentProps, lazy, Suspense } from "react";
import type { Scheme } from "../lib/palette";

// Plotly needs the browser, so the plot is only loaded there (like Ocelescope's own charts).
const LazyPlot = lazy(() => import("@r4pm/components/charts").then((m) => ({ default: m.ThemedPlot })));

/** Plotly chart in Ocelescope's theme, rendered only in the browser. */
export const ThemedPlot = (props: ComponentProps<typeof LazyPlot>) => {
  const mounted = useMounted();
  return mounted ? (
    <Suspense fallback={<Loader size="sm" />}>
      <LazyPlot {...props} />
    </Suspense>
  ) : null;
};

/** The current colour scheme, for picking palette colours. */
export const useScheme = () => useComputedColorScheme("light") as Scheme;

// --- Toolbar: download as PNG or SVG, reset the axes ---

type PlotlyGlobal = { downloadImage: (gd: unknown, options: object) => Promise<unknown> };

/** Filled download arrow, as a Plotly mode bar icon. */
const SVG_ICON = { width: 24, height: 24, path: "M11 3h2v9h3l-4 5-4-5h3zM4 19h16v2H4z" };

/**
 * Plotly config of every chart of the module: the mode bar (shown on hover) has
 * "download as PNG", "download as SVG" and "reset axes" (recentre after zooming or panning).
 *
 * @param name Chart name, used for the file name, e.g. "Activities" → activities.png.
 */
export const plotConfig = (name = "chart") => {
  const filename = name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "chart";
  return {
    responsive: true,
    displaylogo: false,
    toImageButtonOptions: { format: "png", filename, scale: 2 },
    modeBarButtons: [
      [
        "toImage",
        {
          name: "Download plot as SVG",
          icon: SVG_ICON,
          // Plotly is loaded with the chart and registers itself globally.
          click: (gd: unknown) =>
            (globalThis as { Plotly?: PlotlyGlobal }).Plotly?.downloadImage(gd, { format: "svg", filename }),
        },
        "resetScale2d",
      ],
    ],
  };
};

