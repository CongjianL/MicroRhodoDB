/**
 * PR-4 phylogeny explorer model: preorder alignment with explorer.json (fail closed), corrected
 * run1 support (17 rerooting discrepancies, MR_CLD3_017, root split), layouts, colour schemes,
 * placement edge highlighting, search, the derived Newick and the figure export.
 */
import { describe, expect, it } from "vitest";
import type { Explorer, MrdbEntry } from "../../src/data/types";
import {
  COLOR_MODES, buildColorScheme, buildExplorerTree, branchSegment, computeLayout, isDescendant, leafRuns, level1Mrcas,
  meetsThresholds, placementTargets, scopeScheme, searchTips, subcladeMrcas, supportOf, visibleRepresentative,
} from "../../src/features/tree/explorerModel";
import { leaves, parseNewick, type TreeNode } from "../../src/features/tree/newick";
import { buildTreeModel, TREE_RADIUS } from "../../src/features/tree/TreePreview";
import { exportSvg } from "../../src/features/tree/svgExport";
import { parsePhyloQuery, phyloQueryString } from "../../src/features/tree/phyloQuery";
import { href, parseHash } from "../../src/app/routes";
import { clades, json, newick, readData, tips } from "./helpers";

const ex = () => json<Explorer>("phylogeny/explorer.json");
const T = () => buildExplorerTree(newick(), ex());
const clone = <X,>(x: X): X => JSON.parse(JSON.stringify(x)) as X;

describe("explorer tree alignment", () => {
  it("943 nodes / 472 tips / 471 internal, leaf order identical to the Home preview parse", () => {
    const t = T();
    expect(t.nodes.length).toBe(943);
    expect(t.leafOrder.length).toBe(472);
    expect(t.info.size).toBe(471);
    expect(t.leafOrder.map((p) => t.nodes[p].name)).toEqual(leaves(parseNewick(newick())).map((l) => l.name));
  });

  it("Home preview and explorer read the same frozen rooted Newick", () => {
    expect(ex().meta.frozen_treefile.web_file).toBe("phylogeny/MR_RT_003.rooted.treefile");
    expect(ex().meta.frozen_treefile.path).toBe("refpkg/MR_RT_003/tree/MR_RT_003.rooted.treefile");
  });

  it("fails closed on any mismatch", () => {
    const e1 = clone(ex());
    const [a, b] = Object.keys(e1.tips);
    const pa = e1.tips[a].pre;
    (e1.tips[a] as { pre: number }).pre = e1.tips[b].pre;
    (e1.tips[b] as { pre: number }).pre = pa;
    expect(() => buildExplorerTree(newick(), e1)).toThrow(/preorder/);
    const e2 = clone(ex());
    (e2.nodes[5] as { n_tips: number }).n_tips += 1;
    expect(() => buildExplorerTree(newick(), e2)).toThrow(/tips/);
    const e3 = clone(ex());
    (e3.nodes[7] as { length: number | null }).length = 9.99;
    expect(() => buildExplorerTree(newick(), e3)).toThrow(/branch length/);
    // a Newick with one tip renamed
    const first = Object.keys(ex().tips)[0];
    expect(() => buildExplorerTree(newick().replace(first + ":", "XXXX_RENAMED:"), ex())).toThrow();
  });
});

describe("support: run1 by bipartition", () => {
  it("exactly 17 rooted-file labels disagree; the explorer always shows the run1 value", () => {
    const t = T();
    const bad = ex().nodes.filter((n) => !n.label_agrees);
    expect(bad.length).toBe(17);
    expect(ex().meta.n_label_disagreements).toBe(17);
    for (const n of bad) {
      expect(n.rooted_label, `pre ${n.pre}`).not.toBe(n.run1_label);
      const s = supportOf(t, n.pre);
      if (n.support_displayed) {
        expect(s, `pre ${n.pre}`).not.toBeNull();
        expect(`${s!.sh}/${s!.uf}`).toBe(`${n.sh_alrt}/${n.ufboot}`);
        expect(s!.label).toBe(n.run1_label);
      }
    }
  });

  it("469 branches carry support; root and ingroup root child carry none (root split shown once)", () => {
    const t = T();
    const shown = [...t.info.keys()].filter((p) => supportOf(t, p) !== null);
    expect(shown.length).toBe(469);
    const rs = ex().root_split;
    expect(rs).toMatchObject({ edge_id: "E0397", nodes: [1, 30], displayed_on: 1, run1_label: "98.8/100" });
    expect(supportOf(t, 0)).toBeNull();
    expect(supportOf(t, 30)).toBeNull();
    expect(supportOf(t, 1)!.label).toBe("98.8/100");
    expect(t.nodes[1].nTips).toBe(15);
    expect(t.nodes[30].nTips).toBe(457);
    expect(t.nodes[0].children).toEqual([1, 30]);
  });

  it("MR_CLD3_017 is the only level-1 group failing 80/95: run1 50.3/72 at pre 744 (rooted file and DB say 100/100)", () => {
    const t = T();
    const c = clades().level1.find((x) => x.clade_id === "MR_CLD3_017")!;
    expect(c.mrca_node).toBe(744);
    const s = supportOf(t, 744)!;
    expect(s).toEqual({ sh: 50.3, uf: 72, label: "50.3/72" });
    expect(meetsThresholds(s, 80, 95)).toBe(false);
    expect(t.info.get(744)!.rooted_label).toBe("100/100");
    expect(t.info.get(744)!.label_agrees).toBe(false);
    expect(c.support_audit.db_label).toBe("100/100");
    expect(t.nodes[744].nTips).toBe(100);
    const failing = clades().level1.filter((x) => {
      const v = supportOf(t, x.mrca_node)!;
      return !meetsThresholds(v, 80, 95);
    }).map((x) => x.clade_id);
    expect(failing).toEqual(["MR_CLD3_017"]);
    // historical membership retained
    expect(Object.values(ex().tips).filter((x) => x.level1 === "MR_CLD3_017").length).toBe(100);
  });

  it("all 30 subclades meet the thresholds with run1 support at their MRCA", () => {
    const t = T();
    expect(clades().subclades.length).toBe(30);
    for (const s of clades().subclades) {
      const v = supportOf(t, s.mrca_node)!;
      expect(meetsThresholds(v, 80, 95), s.clade_id).toBe(true);
      expect(v.label).toBe(s.support_audit.iqtree_run1_label);
    }
  });

  it("clade MRCAs in explorer.json agree with clades.json", () => {
    const t = T();
    const m1 = level1Mrcas(t);
    const m2 = subcladeMrcas(t);
    for (const c of clades().level1) expect(m1.get(c.clade_id), c.clade_id).toBe(c.mrca_node);
    for (const c of clades().subclades) expect(m2.get(c.clade_id), c.clade_id).toBe(c.mrca_node);
  });

  it("the DERIVED Newick has the frozen topology and the explorer's displayed labels", () => {
    const t = T();
    const d = parseNewick(readData(ex().meta.derived_newick.web_file));
    const pre: TreeNode[] = [];
    const st = [d];
    while (st.length) {
      const n = st.pop()!;
      pre.push(n);
      for (let k = n.children.length - 1; k >= 0; k--) st.push(n.children[k]);
    }
    expect(pre.length).toBe(943);
    for (let p = 0; p < 943; p++) {
      const n = t.nodes[p];
      if (n.isTip) {
        expect(pre[p].name).toBe(n.name);
        continue;
      }
      const s = supportOf(t, p);
      expect(pre[p].name || null, `pre ${p}`).toBe(s ? s.label : null);
    }
    expect(readData(ex().meta.derived_newick.readme)).toMatch(/DERIVED/);
  });
});

describe("layouts", () => {
  const none = new Set<number>();
  for (const layout of ["rect", "radial"] as const) {
    for (const branch of ["prop", "uniform"] as const) {
      it(`${layout} / ${branch}: all 472 tips, monotone slots, depth mapping`, () => {
        const t = T();
        const L = computeLayout(t, { layout, branch, rootPre: 0, collapsed: none }, { w: 800, h: 600 });
        expect(L.leaves.length).toBe(472);
        expect(L.visible.length).toBe(943);
        for (let i = 1; i < L.leaves.length; i++) expect(L.slot[L.leaves[i]]).toBeGreaterThan(L.slot[L.leaves[i - 1]]);
        for (const p of [5, 100, 744]) {
          const d = branch === "prop" ? t.nodes[p].depthProp : t.nodes[p].depthUnit;
          expect(L.rad[p]).toBeCloseTo(d * L.scale, 6);
        }
        if (branch === "uniform") expect(Number.isInteger(L.maxDepth)).toBe(true);
      });
    }
  }

  it("collapse and subtree views", () => {
    const t = T();
    const L = computeLayout(t, { layout: "rect", branch: "prop", rootPre: 0, collapsed: new Set([744]) }, { w: 800, h: 600 });
    expect(L.leaves.length).toBe(472 - 100 + 1);
    expect(L.collapseExtent.has(744)).toBe(true);
    const S = computeLayout(t, { layout: "radial", branch: "prop", rootPre: 744, collapsed: new Set() }, { w: 800, h: 600 });
    expect(S.leaves.length).toBe(100);
    expect(S.rad[744]).toBe(0);
    // tips outside the subtree have no position
    expect(Number.isNaN(S.rad[t.leafOrder[0]])).toBe(true);
    expect(isDescendant(t, t.tipPre.get("A0AAV9X7P9")!, 744)).toBe(true);
    // a tip hidden in a collapsed clade is represented by the collapsed node
    expect(visibleRepresentative(t, L, t.tipPre.get("A0AAV9X7P9")!)).toBe(744);
  });

  it("clade strip: each level-1 group and the outgroup form one contiguous run", () => {
    const t = T();
    const L = computeLayout(t, { layout: "rect", branch: "prop", rootPre: 0, collapsed: new Set() }, { w: 800, h: 600 });
    const runs = leafRuns(t, L, buildColorScheme(t, "clade"));
    for (const c of clades().level1) expect(runs.filter((r) => r.key === c.clade_id).map((r) => r.n), c.clade_id).toEqual([c.n_tips_in_tree]);
    expect(runs.filter((r) => r.key === "outgroup").map((r) => r.n)).toEqual([15]);
  });
});

describe("colour schemes", () => {
  it("clade colours equal the Home preview colours", () => {
    const t = T();
    const s = buildColorScheme(t, "clade");
    const home = buildTreeModel(newick(), tips(), TREE_RADIUS).colorOf;
    for (const [g, c] of home) expect(s.color.get(g), g).toBe(c);
  });

  it("every mode accounts for all 472 tips and lists the 15 outgroup tips separately", () => {
    const t = T();
    for (const m of COLOR_MODES) {
      const s = buildColorScheme(t, m.id);
      const nIn = s.entries.reduce((a, e) => a + e.nIngroup, 0);
      const nOut = s.entries.reduce((a, e) => a + e.nOutgroup, 0);
      expect(nIn + nOut, m.id).toBe(472);
      expect(nOut, m.id).toBe(15);
      expect(new Set(s.entries.map((e) => e.key)).size).toBe(s.entries.length);
    }
  });

  it("subtree legends count only the subtree's tips (MR_CLD3_017 at pre 744: 100 tips, no outgroup)", () => {
    const t = T();
    const s = scopeScheme(t, buildColorScheme(t, "subclade"), 744);
    const byKey = Object.fromEntries(s.entries.map((e) => [e.key, e.nIngroup]));
    expect(s.entries.reduce((a, e) => a + e.nIngroup + e.nOutgroup, 0)).toBe(100);
    expect(s.entries.reduce((a, e) => a + e.nOutgroup, 0)).toBe(0);
    expect(byKey).toMatchObject({ "MR_CLD3_017.01": 21, "MR_CLD3_017.02": 22, "MR_CLD3_017.03": 5, "MR_CLD3_017.04": 3, "MR_CLD3_017.05": 3, "MR_CLD3_017.06": 30 });
    // colours are those of the whole-tree scheme
    const full = buildColorScheme(t, "subclade");
    for (const e of s.entries) expect(e.color).toBe(full.color.get(e.key) ?? e.color);
    expect(scopeScheme(t, full, 0)).toBe(full);
  });

  it("the 2 tips absent from the corpus are shown as such, never with invented annotations", () => {
    const t = T();
    const absent = Object.entries(ex().tips).filter(([, x]) => !x.in_corpus).map(([a]) => a).sort();
    expect(absent).toEqual(["QBQ84355", "QBQ84358"]);
    const f = buildColorScheme(t, "function");
    const e = buildColorScheme(t, "evidence");
    for (const a of absent) {
      const x = ex().tips[a];
      expect(x).toMatchObject({ mrdb_acc: null, func_class: null, evidence_level: null, clade_state: null, tip_role: "boundary_schizorhodopsin", level1: "MR_CLD3_001" });
      expect(f.keyOfTip.get(x.pre)).toBe("not_in_corpus");
      expect(e.keyOfTip.get(x.pre)).toBe("not_in_corpus");
    }
    const og = Object.values(ex().tips).filter((x) => x.tip_role === "outgroup_heliorhodopsin");
    expect(og.length).toBe(15);
    expect(og.every((x) => x.in_corpus && x.clade_state === "outgroup_reference_tip")).toBe(true);
  });
});

describe("placements and edges", () => {
  it("every DB edge maps to a rooted branch; only the root split maps to two", () => {
    const t = T();
    const L = computeLayout(t, { layout: "rect", branch: "prop", rootPre: 0, collapsed: new Set() }, { w: 800, h: 600 });
    const m = ex().edge_map;
    expect(Object.keys(m).length).toBe(941);
    const multi = Object.entries(m).filter(([, v]) => v.length !== 1);
    expect(multi).toEqual([["E0397", [1, 30]]]);
    for (const [eid] of Object.entries(m)) for (const p of placementTargets(t, eid)) expect(branchSegment(t, L, p), eid).not.toBeNull();
    expect(placementTargets(t, "E9999")).toEqual([]);
    expect(placementTargets(t, null)).toEqual([]);
  });

  it("a placed record highlights its best_edge branch; placements are never tips", () => {
    const t = T();
    const r = json<MrdbEntry>("records/MRDB000101.json");
    const s = r.sources.find((x) => x.source_acc === r.representative_source_acc)!;
    const pl = s.phylogeny.placement as unknown as { best_edge: string; clade_call_qc: string; subclade_call: string };
    expect(s.phylogeny.is_reference_tip).toBe(false);
    expect(t.tipPre.has(s.source_acc)).toBe(false);
    const tg = placementTargets(t, pl.best_edge);
    expect(tg.length).toBe(1);
    expect(isDescendant(t, tg[0], 744)).toBe(true); // MR_CLD3_017 placement
    expect(pl.clade_call_qc).toBe("assigned");
  });
});

describe("search", () => {
  it("finds tips by accession, MRDB accession and organism; exact hits first", () => {
    const t = T();
    expect(searchTips(t, "A0AAV9X7P9")[0].acc).toBe("A0AAV9X7P9");
    const x = ex().tips["A0A021VV84"];
    expect(searchTips(t, x.mrdb_acc!)[0].acc).toBe("A0A021VV84");
    expect(searchTips(t, "neurospora").length).toBeGreaterThan(0);
    expect(searchTips(t, "a")).toEqual([]);
  });
});

describe("routes and query", () => {
  it("#/phylogeny is a real page; #/clade without id opens it", () => {
    expect(parseHash("#/phylogeny").name).toBe("phylogeny");
    expect(parseHash("#/clade").name).toBe("phylogeny");
    expect(parseHash("#/phylogeny/x").name).toBe("not-found");
    expect(href.phylogeny("tip=A")).toBe("#/phylogeny?tip=A");
    const r = parseHash("#/phylogeny?layout=radial&color=function&support=1");
    expect(r.name === "phylogeny" && r.params.get("layout")).toBe("radial");
  });

  it("query round trip, defaults omitted, invalid values rejected", () => {
    const q = parsePhyloQuery(new URLSearchParams("layout=radial&bl=uniform&color=evidence&tip=A0A021VV84&node=744&clade=mr_cld3_017&placement=MRDB000101&support=1&sh=70&uf=90&collapsed=31,744,744,0,99999"), 943);
    expect(q).toMatchObject({ layout: "radial", bl: "uniform", color: "evidence", tip: "A0A021VV84", node: 744, clade: "MR_CLD3_017", placement: "MRDB000101", support: true, sh: 70, uf: 90, collapsed: [31, 744] });
    expect(parsePhyloQuery(new URLSearchParams(phyloQueryString(q)), 943)).toEqual(q);
    expect(phyloQueryString({})).toBe("");
    const bad = parsePhyloQuery(new URLSearchParams("layout=x&color=nope&node=-1&sh=200&clade=foo&placement=P02945"), 943);
    expect(bad).toMatchObject({ layout: "rect", color: "clade", node: 0, sh: 80, clade: null, placement: null });
  });
});

describe("figure export", () => {
  it("labels every tip, includes legend, provenance and the legacy-clade note", () => {
    const t = T();
    const out = exportSvg(t, {
      opts: { layout: "rect", branch: "prop", rootPre: 0, collapsed: new Set() },
      scheme: buildColorScheme(t, "clade"), cladeScheme: buildColorScheme(t, "clade"), failingGroups: new Set(["MR_CLD3_017"]),
      support: { show: true, sh: 80, uf: 95 }, tip: null, placement: [1, 30], title: "test", provenance: ["prov line"],
    });
    expect(out.svg.startsWith("<svg")).toBe(true);
    expect(out.svg.match(/<svg/g)!.length).toBe(1);
    expect(out.svg.trim().endsWith("</svg>")).toBe(true);
    for (const acc of Object.keys(ex().tips)) expect(out.svg.includes(`>${acc} `) || out.svg.includes(`>${acc}<`), acc).toBe(true);
    expect(out.svg).toContain("prov line");
    expect(out.svg).toContain("Legacy clade, fails corrected support");
    expect(out.svg).toContain("50.3/72");
    expect(out.svg).not.toContain(">100/100</text><circle cx=\"NaN");
    expect(out.svg).not.toContain("NaN");
    const r = exportSvg(t, {
      opts: { layout: "radial", branch: "uniform", rootPre: 744, collapsed: new Set() },
      scheme: buildColorScheme(t, "function"), cladeScheme: buildColorScheme(t, "clade"), failingGroups: new Set(),
      support: { show: false, sh: 80, uf: 95 }, tip: t.tipPre.get("A0AAV9X7P9")!, placement: [], title: "t", provenance: [],
    });
    expect(r.svg).not.toContain("NaN");
    expect((r.svg.match(/<text [^>]*rotate/g) ?? []).length).toBe(100);
  });
});
