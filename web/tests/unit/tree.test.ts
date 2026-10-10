/** The Home tree preview is drawn from the real exported MR_RT_003 rooted Newick and phylogeny/tips.json. */
import { describe, expect, it } from "vitest";
import { buildTreeModel, OUTGROUP_KEY, TREE_RADIUS } from "../../src/features/tree/TreePreview";
import { leaves, parseNewick } from "../../src/features/tree/newick";
import { clades, newick, tips } from "./helpers";

describe("MR_RT_003 preview", () => {
  const root = parseNewick(newick());
  const lv = leaves(root);
  const T = tips();
  const C = clades();

  it("parses all 472 tips, matching tips.json exactly", () => {
    expect(lv.length).toBe(472);
    expect(new Set(lv.map((l) => l.name))).toEqual(new Set(T.tips.map((t) => t.tip)));
  });

  it("tip composition: 422 level-1 + 35 backbone_unassigned (27 unclustered + 4 B01 + 4 B02) + 15 outgroup", () => {
    const by = (f: (t: (typeof T.tips)[number]) => boolean) => T.tips.filter(f).length;
    expect(by((t) => t.level1 !== null && !/_B\d\d$/.test(t.level1))).toBe(422);
    expect(by((t) => t.tip_role === "outgroup_heliorhodopsin")).toBe(15);
    expect(by((t) => !!t.unclustered_backbone)).toBe(27);
  });

  it("each level-1 clade and backbone group occupies one contiguous ring arc of n_tips_in_tree tips", () => {
    const m = buildTreeModel(newick(), T, TREE_RADIUS);
    expect(m.nTips).toBe(472);
    expect(m.nOutgroup).toBe(15);
    const arcs = new Map<string, number[]>();
    for (const a of m.layout.arcs) (arcs.get(a.group) ?? arcs.set(a.group, []).get(a.group)!).push(a.n);
    expect(C.level1.length).toBe(19);
    for (const c of C.level1) {
      expect(arcs.get(c.clade_id), c.clade_id).toEqual([c.n_tips_in_tree]);
    }
    expect(arcs.get(OUTGROUP_KEY)).toEqual([15]);
    expect(m.colorOf.size).toBe(arcs.size);
  });

  it("branch lengths are used (radial phylogram, not a cladogram)", () => {
    const bl = lv.map((l) => l.length ?? 0);
    expect(new Set(bl).size).toBeGreaterThan(100);
  });

  it("rejects a tips.json that does not match the tree", () => {
    expect(() => buildTreeModel(newick(), { ...T, tips: T.tips.slice(1) }, TREE_RADIUS)).toThrow();
  });
});
