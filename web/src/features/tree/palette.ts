/** Shared tree colours (Home preview and phylogeny explorer use the same assignment rule). */

/** Colour-blind-safe categorical palette (Okabe-Ito + Tol). */
export const CLADE_PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#882255", "#117733", "#332288", "#AA4499"];
export const BACKBONE_COLOR = "#9aa5b1";
export const OUTGROUP_COLOR = "#526175";

/** Assign palette colours to groups in order of first appearance (leaf order), cycling the palette. */
export function assignGroupColors(seq: readonly string[], palette: readonly string[]): Map<string, string> {
  const m = new Map<string, string>();
  let k = 0;
  for (const g of seq) if (!m.has(g)) m.set(g, palette[k++ % palette.length]);
  return m;
}
