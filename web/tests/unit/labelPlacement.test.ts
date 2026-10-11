/** PR-3a: mini-tree label clearance (MR_CLD3_017 label was partly covered by the highlight outline). */
import { describe, expect, it } from "vitest";
import { boxExtent, CHAR_EM, clearLabelRadius, labelBox } from "../../src/features/tree/labelPlacement";

/** Minimum distance from the origin to an axis-aligned box centred at (r, angle). */
function minDist(r: number, w: number, h: number, a: number): number {
  const cx = r * Math.cos(a);
  const cy = r * Math.sin(a);
  const dx = Math.max(0, Math.abs(cx) - w / 2);
  const dy = Math.max(0, Math.abs(cy) - h / 2);
  return Math.hypot(dx, dy);
}

describe("clearLabelRadius", () => {
  const texts = ["017!", "017", "CLD3_017!", "4"];
  it("keeps every point of the label box outside the outline (all angles, several label sizes)", () => {
    for (const t of texts) {
      for (const fs of [7, 8.5, 10]) {
        const { w, h } = labelBox(t, fs);
        for (let k = 0; k < 720; k++) {
          const a = (k / 720) * 2 * Math.PI;
          const clearR = 46;
          const r = clearLabelRadius(40, clearR, w, h, a);
          expect(r).toBeGreaterThanOrEqual(40);
          expect(minDist(r, w, h, a)).toBeGreaterThanOrEqual(clearR + 2 - 1e-9);
        }
      }
    }
  });

  it("never moves a label inward and leaves already-clear labels where they were", () => {
    expect(clearLabelRadius(200, 46, 20, 10, 0.3)).toBe(200);
    expect(clearLabelRadius(10, 46, 20, 10, 0)).toBe(46 + 2 + 10);
    expect(clearLabelRadius(10, 46, 20, 10, Math.PI / 2)).toBeCloseTo(46 + 2 + 5, 9);
  });

  it("label box uses a conservative glyph width and boxExtent contains the box", () => {
    expect(CHAR_EM).toBeGreaterThanOrEqual(0.7);
    expect(labelBox("017!", 10)).toEqual({ w: 4 * CHAR_EM * 10, h: 12 });
    const { w, h } = labelBox("017!", 9);
    for (const a of [0, 0.7, 2.2, 3.9, 5.5]) {
      const r = 60;
      const e = boxExtent(r, w, h, a);
      expect(e).toBeGreaterThanOrEqual(Math.abs(r * Math.cos(a)) + w / 2);
      expect(e).toBeGreaterThanOrEqual(Math.abs(r * Math.sin(a)) + h / 2);
    }
  });
});
