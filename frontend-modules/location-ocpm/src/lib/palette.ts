// Module-wide colour palette, built from Nina's colours (same as in the material flow playground).
// Every page imports its colours from here; no component defines its own.

export type Scheme = "light" | "dark";

/**
 * Categorical colours (identity: activity, location, object type, ...), in fixed order.
 * Slots 1-8 are the core set, checked for colour-vision deficiency (worst neighbouring
 * pair ΔE 10.3 under deuteranopia, Machado et al. 2009). Slots 9-48 extend it within the
 * neighbourhoods of Nina's colours, each picked to be as far as possible (OKLab distance)
 * from all earlier slots; the smallest distance shrinks from 24 (slot 9) to 8 (slot 48).
 * Beyond slot 48, `categoricalColour` derives further colours, so no colour repeats.
 */
export const CATEGORICAL: Record<Scheme, readonly string[]> = {
  light: [
    "#0098A1", "#d98b09", "#CE108A", "#5291cc", "#88375e", "#00549F", "#007e56", "#cd00cd",
    "#f897e5", "#7bd591", "#1e4729", "#73c9fb", "#b8758d", "#595dec", "#8602a8", "#fe579d",
    "#2d11a7", "#ea5efe", "#deb58f", "#572069", "#9953ab", "#977d3c", "#55af6d", "#616c98",
    "#243e61", "#bc78d6", "#8d9bff", "#6db2b5", "#730238", "#1a636d", "#cb9ab6", "#eab60b",
    "#413cc9", "#0283fc", "#925d69", "#a20080", "#056fc7", "#d354af", "#00642c", "#36aef9",
    "#be4d74", "#b19c6c", "#618c6a", "#5c4167", "#58d4ce", "#b652d8", "#127c8d", "#a41acc",
  ],
  dark: [
    "#0098A1", "#ce810a", "#CE108A", "#5291cc", "#a34772", "#196cbf", "#007e56", "#cd00cd",
    "#ffb2fb", "#83ebae", "#fec011", "#f7719d", "#73c9fb", "#d773fb", "#61bb79", "#891faa",
    "#bd9ec9", "#c4af7e", "#a56cba", "#6972ff", "#f83ebf", "#927e4e", "#8d9bff", "#4643d0",
    "#f2c8a2", "#535a85", "#6db2b8", "#bb7584", "#fa9fb3", "#399c60", "#ff85e1", "#f79803",
    "#c4cefe", "#a3037a", "#077689", "#6ce7ed", "#ea4183", "#a941b0", "#36aef9", "#95ccb1",
    "#88678d", "#d56bc2", "#824791", "#7f4c58", "#bc59df", "#ad9566", "#068dfa", "#6974bb",
  ],
};

/** Colour for the folded "Other" group and for missing values. */
export const OTHER: Record<Scheme, string> = { light: "#adb5bd", dark: "#5c6366" };

/** Sequential ramp (magnitude, e.g. the heatmap), low to high: light turquoise to petrol. */
export const SEQUENTIAL: Record<Scheme, readonly string[]> = {
  light: ["#daf7f7", "#a1dfd7", "#4fbec1", "#0098A1", "#067b7e", "#006165", "#034648"],
  dark: ["#023032", "#044043", "#005256", "#188489", "#42a3a8", "#6cbec2", "#a1dfd7"],
};

/** Diverging ramp (polarity, e.g. net outflow vs inflow): pink, grey midpoint, petrol. */
export const DIVERGING: Record<Scheme, readonly string[]> = {
  light: ["#CE108A", "#e266a9", "#efa3c8", "#e3e7e8", "#9cd7da", "#42a3a8", "#006165"],
  dark: ["#e266a9", "#b8487f", "#6d3150", "#3a3f41", "#1d4f52", "#188489", "#6cbec2"],
};

/** Petrol as a ten-shade Mantine colour tuple (shade 6 is Nina's #006165). */
export const PETROL = [
  "#eaf8f9", "#cbecee", "#9cd7da", "#6cbec2", "#42a3a8",
  "#188489", "#006165", "#005256", "#044043", "#023032",
] as const;

/** Interface roles: primary (buttons, links, flag counts), accent (highlight, selection), error. */
export const UI: Record<Scheme, { primary: string; accent: string; error: string }> = {
  light: { primary: "#006165", accent: "#CE108A", error: "#c92a2a" },
  dark: { primary: "#42a3a8", accent: "#e266a9", error: "#ff6b6b" },
};

/**
 * Fixed colours of the data overview charts (status values, not identities): locatedness from
 * petrol (fully) to grey (unlocated), agreement green / pink / light grey, derivation levels
 * from dark (Level 0, provided) to light (Level 3), ⊥ grey. Event types use categorical slots.
 */
export const STATUS: Record<Scheme, Record<string, string>> = {
  light: {
    "fully located": "#006165", "partially located": "#4fbec1", unlocated: OTHER.light,
    movement: CATEGORICAL.light[0], transformation: CATEGORICAL.light[1],
    "movement and transformation": CATEGORICAL.light[3], other: CATEGORICAL.light[4],
    agreeing: "#007e56", "not agreeing": "#CE108A", "not tested": "#dee2e6",
    "0": "#034648", "1": "#067b7e", "2": "#4fbec1", "3": "#a1dfd7", "⊥": OTHER.light,
  },
  dark: {
    "fully located": "#42a3a8", "partially located": "#188489", unlocated: OTHER.dark,
    movement: CATEGORICAL.dark[0], transformation: CATEGORICAL.dark[1],
    "movement and transformation": CATEGORICAL.dark[3], other: CATEGORICAL.dark[4],
    agreeing: "#61bb79", "not agreeing": "#e266a9", "not tested": "#373a40",
    "0": "#a1dfd7", "1": "#6cbec2", "2": "#188489", "3": "#005256", "⊥": OTHER.dark,
  },
};

// --- OKLCH helpers (only used to derive colours beyond the listed slots) ---

const toLinear = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const toGamma = (c: number) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);

/** Convert a hex colour to OKLCH [L, C, h in radians]. */
function hexToOklch(hex: string): [number, number, number] {
  const [r, g, b] = [1, 3, 5].map((i) => toLinear(parseInt(hex.slice(i, i + 2), 16) / 255));
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  return [L, Math.hypot(A, B), Math.atan2(B, A)];
}

/** Convert OKLCH to hex, reducing chroma until the colour fits into sRGB. */
function oklchToHex(L: number, C: number, h: number): string {
  for (let c = C; c >= 0; c -= 0.002) {
    const a = c * Math.cos(h);
    const b = c * Math.sin(h);
    const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
    const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
    const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
    const rgb = [
      4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
      -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
      -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
    ];
    if (rgb.every((x) => x >= -1e-4 && x <= 1 + 1e-4)) {
      return `#${rgb
        .map((x) => Math.round(toGamma(Math.min(1, Math.max(0, x))) * 255).toString(16).padStart(2, "0"))
        .join("")}`;
    }
  }
  return "#808080";
}

// --- Assignment ---

/**
 * Colour of the categorical slot at `index` (0-based).
 * Beyond the listed slots, the list is reused with a lightness shift per round
 * (round 1 lighter, round 2 darker, round 3 lighter still, ...).
 */
export function categoricalColour(index: number, scheme: Scheme = "light"): string {
  const list = CATEGORICAL[scheme];
  if (index < list.length) return list[index];
  const round = Math.floor(index / list.length);
  const [L, C, h] = hexToOklch(list[index % list.length]);
  const shift = (round % 2 === 1 ? 1 : -1) * 0.07 * Math.ceil(round / 2);
  return oklchToHex(Math.min(0.92, Math.max(0.22, L + shift)), C, h);
}

/**
 * Assign each value of a domain its own colour, in domain order.
 * Pass the FULL domain (e.g. all activities of the log, most frequent first),
 * not just the values currently shown, so a value keeps its colour when filters change.
 * The result never contains the same colour twice, until the palette runs out (a few hundred
 * values: the lightness shift stops at its bounds); further values then reuse colours.
 */
export function colourMap(domain: readonly string[], scheme: Scheme = "light"): Map<string, string> {
  const used = new Set<string>();
  const map = new Map<string, string>();
  const roundLength = CATEGORICAL[scheme].length;
  let slot = 0;
  let exhausted = false;
  for (const value of domain) {
    if (map.has(value)) continue;
    let colour = categoricalColour(slot++, scheme);
    // A whole round without a new colour means the palette is used up (an unbounded search hangs).
    for (let tries = 0; !exhausted && used.has(colour.toLowerCase()); tries++) {
      if (tries >= roundLength) exhausted = true;
      else colour = categoricalColour(slot++, scheme);
    }
    used.add(colour.toLowerCase());
    map.set(value, colour);
  }
  return map;
}

/** Turn a ramp into a Plotly colorscale ([[0, c0], ..., [1, cn]]). */
export function plotlyScale(ramp: readonly string[]): [number, string][] {
  return ramp.map((c, i) => [i / (ramp.length - 1), c]);
}
