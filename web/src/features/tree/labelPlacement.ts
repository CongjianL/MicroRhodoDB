/**
 * Label placement for the circular tree preview (PR-3a). A clade label is a text box centred at
 * radius r on the bisector of its ring segment. When that segment is highlighted with an outline
 * (Protein Entry mini tree), the label is pushed outward until no point of its box lies inside the
 * outline, so the label (e.g. "017!") is never obscured.
 */

/** Conservative glyph advance (em) for bold digits in common sans-serif fonts (DejaVu Sans Bold is about 0.70). */
export const CHAR_EM = 0.72;

export function labelBox(text: string, fontSize: number): { w: number; h: number } {
  return { w: text.length * CHAR_EM * fontSize, h: fontSize * 1.2 };
}

/**
 * Smallest radius >= `base` at which a box (w x h) centred on the ray at `angle` keeps every point at
 * least `clearR + gap` from the origin. For a point p of the box and the radial unit vector u,
 * |p| >= p.u >= r - (w/2)|cos a| - (h/2)|sin a|, so this radius is a strict bound.
 */
export function clearLabelRadius(base: number, clearR: number, w: number, h: number, angle: number, gap = 2): number {
  const inward = (w / 2) * Math.abs(Math.cos(angle)) + (h / 2) * Math.abs(Math.sin(angle));
  return Math.max(base, clearR + gap + inward);
}

/** Half-extent of the drawing needed to contain a box centred at (r, angle). */
export function boxExtent(r: number, w: number, h: number, angle: number): number {
  return Math.max(Math.abs(r * Math.cos(angle)) + w / 2, Math.abs(r * Math.sin(angle)) + h / 2);
}
