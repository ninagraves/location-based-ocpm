// Number formatting shared by all pages.

/** A count with thousands separators, "–" if missing. */
export const num = (value: number | null | undefined) =>
  value === null || value === undefined ? "–" : value.toLocaleString("en-GB");

/** A share (0..1) as a percentage, "–" if missing. */
export const pct = (share: number | null | undefined, digits = 0) =>
  share === null || share === undefined || Number.isNaN(share) ? "–" : `${(share * 100).toFixed(digits)} %`;
