/**
 * Pure model for the PR-4 phylogeny explorer (no React, no DOM; unit tested).
 *
 * Topology and branch lengths: the frozen MR_RT_003.rooted.treefile (parsed here).
 * Node identity: preorder index `pre` (root = 0, children in file order), which must agree exactly
 * with phylogeny/explorer.json; any mismatch throws (fail closed) instead of drawing a wrong tree.
 * Support: explorer.json sh_alrt/ufboot (the IQ-TREE run1 label of the same bipartition). The
 * rooted file's own internal labels are never read for display (17 are attached to the wrong
 * bipartition after rerooting).
 */
import type { Explorer, ExplorerNode, ExplorerTip } from "../../data/types";
import { FUNC_LABEL, FUNC_ORDER, cladeShort } from "../../lib/format";
import { parseNewick, type TreeNode } from "./newick";
import { CLADE_PALETTE, OUTGROUP_COLOR, BACKBONE_COLOR, assignGroupColors } from "./palette";

/* ------------------------------------------------------------------ tree */

export interface XNode {
  pre: number;
  parent: number; // -1 for the root
  children: number[];
  length: number; // branch length to the parent (0 for the root)
  name: string; // tip accession; "" for internal nodes
  isTip: boolean;
  nTips: number;
  /** Leaf-order index range [first, last] of the tips below this node. */
  first: number;
  last: number;
  /** Root-to-node path length (proportional) and edge count (uniform). */
  depthProp: number;
  depthUnit: number;
}

export interface XTree {
  nodes: XNode[];
  /** pre of each tip in leaf order. */
  leafOrder: number[];
  tipPre: Map<string, number>;
  ex: Explorer;
  /** explorer.json node record by pre (internal nodes only). */
  info: Map<number, ExplorerNode>;
}

const EPS = 1e-9;

export function buildExplorerTree(newick: string, ex: Explorer): XTree {
  const root = parseNewick(newick);
  const nodes: XNode[] = [];
  const leafOrder: number[] = [];
  const tipPre = new Map<string, number>();
  // iterative preorder, children in file order
  const stack: [TreeNode, number][] = [[root, -1]];
  while (stack.length) {
    const [t, parent] = stack.pop()!;
    const pre = nodes.length;
    const isTip = t.children.length === 0;
    const pd = parent >= 0 ? nodes[parent] : null;
    const n: XNode = {
      pre, parent, children: [], length: parent >= 0 ? t.length : 0, name: isTip ? t.name : "", isTip,
      nTips: 0, first: 0, last: 0,
      depthProp: pd ? pd.depthProp + t.length : 0, depthUnit: pd ? pd.depthUnit + 1 : 0,
    };
    nodes.push(n);
    if (pd) pd.children.push(pre);
    if (isTip) {
      n.nTips = 1;
      n.first = n.last = leafOrder.length;
      leafOrder.push(pre);
      if (tipPre.has(t.name)) throw new Error(`Explorer: duplicate tip ${t.name}`);
      tipPre.set(t.name, pre);
    }
    for (let k = t.children.length - 1; k >= 0; k--) stack.push([t.children[k], pre]);
  }
  for (let p = nodes.length - 1; p >= 0; p--) {
    const n = nodes[p];
    if (n.isTip) continue;
    n.nTips = n.children.reduce((s, c) => s + nodes[c].nTips, 0);
    n.first = nodes[n.children[0]].first;
    n.last = nodes[n.children[n.children.length - 1]].last;
  }

  // ---- fail-closed alignment with explorer.json
  if (nodes.length !== ex.n_nodes) throw new Error(`Explorer: Newick has ${nodes.length} nodes, explorer.json ${ex.n_nodes}`);
  if (leafOrder.length !== ex.n_tips) throw new Error(`Explorer: Newick has ${leafOrder.length} tips, explorer.json ${ex.n_tips}`);
  const exTips = Object.entries(ex.tips);
  if (exTips.length !== ex.n_tips) throw new Error("Explorer: explorer.json tips count mismatch");
  for (const [acc, t] of exTips) {
    const p = tipPre.get(acc);
    if (p === undefined) throw new Error(`Explorer: tip ${acc} missing from Newick`);
    if (p !== t.pre) throw new Error(`Explorer: tip ${acc} preorder ${p} != explorer.json ${t.pre}`);
    if (Math.abs(nodes[p].length - t.length) > EPS) throw new Error(`Explorer: tip ${acc} branch length mismatch`);
  }
  const info = new Map<number, ExplorerNode>();
  if (ex.nodes.length !== ex.n_internal_incl_root) throw new Error("Explorer: internal node count mismatch");
  for (const e of ex.nodes) {
    const n = nodes[e.pre];
    if (!n || n.isTip) throw new Error(`Explorer: node pre ${e.pre} is not internal in the Newick`);
    if ((n.parent < 0 ? null : n.parent) !== e.parent) throw new Error(`Explorer: node ${e.pre} parent mismatch`);
    if (n.nTips !== e.n_tips) throw new Error(`Explorer: node ${e.pre} has ${n.nTips} tips, explorer.json ${e.n_tips}`);
    if (nodes[leafOrder[n.first]].name !== e.first_tip || nodes[leafOrder[n.last]].name !== e.last_tip) throw new Error(`Explorer: node ${e.pre} tip span mismatch`);
    if (e.length === null ? n.parent >= 0 : Math.abs(e.length - n.length) > EPS) throw new Error(`Explorer: node ${e.pre} branch length mismatch`);
    info.set(e.pre, e);
  }
  if (info.size !== nodes.length - leafOrder.length) throw new Error("Explorer: internal nodes missing from explorer.json");
  return { nodes, leafOrder, tipPre, ex, info };
}

export const tipInfo = (tree: XTree, pre: number): ExplorerTip | null => {
  const n = tree.nodes[pre];
  return n && n.isTip ? tree.ex.tips[n.name] ?? null : null;
};

/** True when `pre` lies in the subtree of `anc` (inclusive). */
export function isDescendant(tree: XTree, pre: number, anc: number): boolean {
  const a = tree.nodes[anc];
  const n = tree.nodes[pre];
  if (!a || !n) return false;
  // preorder: subtree of anc is the contiguous pre range [anc, anc + size)
  return pre >= anc && pre < anc + subtreeSize(tree, anc);
}

const sizeCache = new WeakMap<XTree, Int32Array>();
export function subtreeSize(tree: XTree, pre: number): number {
  let s = sizeCache.get(tree);
  if (!s) {
    s = new Int32Array(tree.nodes.length).fill(1);
    for (let p = tree.nodes.length - 1; p > 0; p--) s[tree.nodes[p].parent] += s[p];
    sizeCache.set(tree, s);
  }
  return s[pre];
}

export function ancestors(tree: XTree, pre: number): number[] {
  const out: number[] = [];
  for (let p = tree.nodes[pre]?.parent ?? -1; p >= 0; p = tree.nodes[p].parent) out.push(p);
  return out;
}

/* ------------------------------------------------------------------ support */

export interface SupportValue { sh: number; uf: number; label: string }

/**
 * Displayed support for the branch above `pre` (run1, bipartition-mapped). Null for tips, the
 * root, and the ingroup root child (the root split is shown once, on the outgroup branch).
 */
export function supportOf(tree: XTree, pre: number): SupportValue | null {
  const e = tree.info.get(pre);
  if (!e || !e.support_displayed || e.sh_alrt === null || e.ufboot === null) return null;
  return { sh: e.sh_alrt, uf: e.ufboot, label: `${fmtSupport(e.sh_alrt)}/${fmtSupport(e.ufboot)}` };
}

export const fmtSupport = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(1));

export const meetsThresholds = (s: SupportValue, sh: number, uf: number) => s.sh >= sh && s.uf >= uf;

/* ------------------------------------------------------------------ placements */

/** Rooted node(s) whose parent branch is the placement's best edge (two for the root split). */
export function placementTargets(tree: XTree, edgeId: string | null | undefined): number[] {
  if (!edgeId) return [];
  const t = tree.ex.edge_map[edgeId];
  return t ? [...t] : [];
}

/* ------------------------------------------------------------------ layout */

export type LayoutKind = "rect" | "radial";
export type BranchMode = "prop" | "uniform";

export interface LayoutOpts {
  layout: LayoutKind;
  branch: BranchMode;
  rootPre: number;
  collapsed: ReadonlySet<number>;
}

export interface Layout {
  opts: LayoutOpts;
  /** Visible nodes in preorder (collapsed nodes included, their descendants excluded). */
  visible: number[];
  x: Float64Array;
  y: Float64Array;
  /** Rect: slot centre (y units). Radial: angle (radians). NaN if hidden. */
  slot: Float64Array;
  /** Rect: x (depth). Radial: radius. */
  rad: Float64Array;
  /** Visible leaves (tips or collapsed nodes) in drawing order. */
  leaves: number[];
  nSlots: number;
  maxDepth: number;
  /** Units per substitution/site (proportional) or per branch (uniform). */
  scale: number;
  /** Bounding box of the drawing (excluding labels). */
  bbox: { x0: number; y0: number; x1: number; y1: number };
  /** Slot spacing: rect = y distance; radial = angle step (radians). */
  step: number;
  /** Radial only: angular span start. */
  angle0: number;
  /** Deepest descendant depth of each collapsed node (rect x / radial r). */
  collapseExtent: Map<number, number>;
}

/** Collapsed nodes occupy this many leaf slots so their wedge is visible. */
export const COLLAPSED_SLOTS = 2;
const RADIAL_GAP = 0.035;

export function computeLayout(tree: XTree, opts: LayoutOpts, size: { w: number; h: number }): Layout {
  const { nodes } = tree;
  const N = nodes.length;
  const rootPre = nodes[opts.rootPre] && !nodes[opts.rootPre].isTip ? opts.rootPre : 0;
  const depth = (p: number) => (opts.branch === "prop" ? nodes[p].depthProp - nodes[rootPre].depthProp : nodes[p].depthUnit - nodes[rootPre].depthUnit);

  const visible: number[] = [];
  const leaves: number[] = [];
  const slotW = new Map<number, number>();
  const collapseExtent = new Map<number, number>();
  let nSlots = 0;
  let maxDepth = 0;
  const stack = [rootPre];
  while (stack.length) {
    const p = stack.pop()!;
    visible.push(p);
    const n = nodes[p];
    const collapsed = !n.isTip && p !== rootPre && opts.collapsed.has(p);
    if (n.isTip || collapsed) {
      leaves.push(p);
      const w = collapsed ? COLLAPSED_SLOTS : 1;
      slotW.set(p, w);
      nSlots += w;
      let d = depth(p);
      if (collapsed) {
        // deepest tip below
        for (let k = n.first; k <= n.last; k++) d = Math.max(d, depth(tree.leafOrder[k]));
        collapseExtent.set(p, d);
      }
      maxDepth = Math.max(maxDepth, d);
      continue;
    }
    for (let k = n.children.length - 1; k >= 0; k--) stack.push(n.children[k]);
  }
  if (maxDepth <= 0) maxDepth = 1;

  const slot = new Float64Array(N).fill(NaN);
  const rad = new Float64Array(N).fill(NaN);
  let acc = 0;
  for (const p of leaves) {
    const w = slotW.get(p)!;
    slot[p] = acc + w / 2;
    acc += w;
  }
  for (let k = visible.length - 1; k >= 0; k--) {
    const p = visible[k];
    if (!Number.isNaN(slot[p])) continue;
    const ch = nodes[p].children;
    slot[p] = (slot[ch[0]] + slot[ch[ch.length - 1]]) / 2;
  }

  const x = new Float64Array(N).fill(NaN);
  const y = new Float64Array(N).fill(NaN);
  let bbox: Layout["bbox"];
  let step: number;
  let scale: number;
  let angle0 = 0;
  if (opts.layout === "rect") {
    const W = Math.max(50, size.w);
    const H = Math.max(50, size.h);
    scale = W / maxDepth;
    step = H / nSlots;
    for (const p of visible) {
      rad[p] = depth(p) * scale;
      slot[p] = slot[p] * step;
      x[p] = rad[p];
      y[p] = slot[p];
    }
    for (const [p, d] of collapseExtent) collapseExtent.set(p, d * scale);
    bbox = { x0: 0, y0: 0, x1: W, y1: H };
  } else {
    const R = Math.max(25, Math.min(size.w, size.h) / 2);
    scale = R / maxDepth;
    const span = 2 * Math.PI * (1 - 2 * RADIAL_GAP);
    angle0 = -Math.PI / 2 + RADIAL_GAP * 2 * Math.PI;
    step = span / nSlots;
    for (const p of visible) {
      rad[p] = depth(p) * scale;
      slot[p] = angle0 + slot[p] * step;
      x[p] = rad[p] * Math.cos(slot[p]);
      y[p] = rad[p] * Math.sin(slot[p]);
    }
    for (const [p, d] of collapseExtent) collapseExtent.set(p, d * scale);
    bbox = { x0: -R, y0: -R, x1: R, y1: R };
  }
  return { opts: { ...opts, rootPre }, visible, x, y, slot, rad, leaves, nSlots, maxDepth, scale, bbox, step, angle0, collapseExtent };
}

const f2 = (v: number) => (Math.round(v * 100) / 100).toString();

/** Path for the branch above `pre` (parent depth -> node depth). Empty for the layout root. */
export function branchPath(tree: XTree, L: Layout, pre: number): string {
  const n = tree.nodes[pre];
  if (pre === L.opts.rootPre || n.parent < 0) return "";
  const pr = L.rad[n.parent];
  if (L.opts.layout === "rect") return `M${f2(pr)} ${f2(L.y[pre])}H${f2(L.x[pre])}`;
  const a = L.slot[pre];
  return `M${f2(pr * Math.cos(a))} ${f2(pr * Math.sin(a))}L${f2(L.x[pre])} ${f2(L.y[pre])}`;
}

/** Connector spanning the children of a visible, expanded internal node. */
export function connectorPath(tree: XTree, L: Layout, pre: number): string {
  const n = tree.nodes[pre];
  if (n.isTip || L.collapseExtent.has(pre) || n.children.length < 2) return "";
  const c0 = n.children[0];
  const c1 = n.children[n.children.length - 1];
  const r = L.rad[pre];
  if (L.opts.layout === "rect") return `M${f2(r)} ${f2(L.y[c0])}V${f2(L.y[c1])}`;
  if (r < 0.01) return "";
  const a0 = L.slot[c0];
  const a1 = L.slot[c1];
  const large = a1 - a0 > Math.PI ? 1 : 0;
  return `M${f2(r * Math.cos(a0))} ${f2(r * Math.sin(a0))}A${f2(r)} ${f2(r)} 0 ${large} 1 ${f2(r * Math.cos(a1))} ${f2(r * Math.sin(a1))}`;
}

/** Closed wedge (triangle / annular sector) drawn for a collapsed node. */
export function collapsedPath(L: Layout, pre: number): string {
  const ext = L.collapseExtent.get(pre);
  if (ext === undefined) return "";
  const half = (COLLAPSED_SLOTS * L.step) / 2 * 0.9;
  const r = L.rad[pre];
  const end = Math.max(ext, r + 4);
  if (L.opts.layout === "rect") {
    const yc = L.y[pre];
    return `M${f2(r)} ${f2(yc)}L${f2(end)} ${f2(yc - half)}L${f2(end)} ${f2(yc + half)}Z`;
  }
  const a = L.slot[pre];
  const p = (rr: number, aa: number) => `${f2(rr * Math.cos(aa))} ${f2(rr * Math.sin(aa))}`;
  return `M${p(r, a)}L${p(end, a - half)}A${f2(end)} ${f2(end)} 0 0 1 ${p(end, a + half)}Z`;
}

/** Background band covering the leaves below `pre` (rect: rectangle; radial: sector), for clade highlighting. */
export function spanPath(tree: XTree, L: Layout, pre: number, pad = 0): string {
  const n = tree.nodes[pre];
  if (Number.isNaN(L.slot[pre])) return "";
  // first/last visible leaf below pre
  let lo = Infinity;
  let hi = -Infinity;
  for (const p of L.leaves) {
    if (isDescendant(tree, p, pre)) {
      const w = (L.collapseExtent.has(p) ? COLLAPSED_SLOTS : 1) / 2;
      lo = Math.min(lo, L.slot[p] - w * L.step);
      hi = Math.max(hi, L.slot[p] + w * L.step);
    }
  }
  if (!Number.isFinite(lo)) return "";
  const pr = n.parent >= 0 && !Number.isNaN(L.rad[n.parent]) ? L.rad[n.parent] : L.rad[pre];
  const r0 = Math.max(0, (pr + L.rad[pre]) / 2);
  const r1 = L.bbox.x1 + pad;
  if (L.opts.layout === "rect") return `M${f2(r0)} ${f2(lo)}H${f2(r1)}V${f2(hi)}H${f2(r0)}Z`;
  const p = (rr: number, aa: number) => `${f2(rr * Math.cos(aa))} ${f2(rr * Math.sin(aa))}`;
  const large = hi - lo > Math.PI ? 1 : 0;
  return `M${p(r0, lo)}L${p(r1, lo)}A${f2(r1)} ${f2(r1)} 0 ${large} 1 ${p(r1, hi)}L${p(r0, hi)}A${f2(r0)} ${f2(r0)} 0 ${large} 0 ${p(r0, lo)}Z`;
}

/* ------------------------------------------------------------------ colour schemes */

export type ColorMode = "clade" | "subclade" | "domain" | "phylum" | "function" | "evidence" | "motif" | "role";

export const COLOR_MODES: { id: ColorMode; label: string; field: string }[] = [
  { id: "clade", label: "Clade (level 1)", field: "level1 / backbone_group" },
  { id: "subclade", label: "Subclade (level 2)", field: "subclade" },
  { id: "domain", label: "Taxonomy: domain", field: "tax_domain" },
  { id: "phylum", label: "Taxonomy: phylum", field: "phylum" },
  { id: "function", label: "Function (v1.6.1)", field: "func_class" },
  { id: "evidence", label: "Evidence level", field: "evidence_level" },
  { id: "motif", label: "Helix-C motif", field: "helixC_motif" },
  { id: "role", label: "Tip role", field: "tip_role" },
];

export const isColorMode = (s: string | null): s is ColorMode => !!s && COLOR_MODES.some((m) => m.id === s);

export interface LegendEntry { key: string; label: string; color: string; nIngroup: number; nOutgroup: number }

export interface ColorScheme {
  mode: ColorMode;
  /** Category key of each tip (by pre). */
  keyOfTip: Map<number, string>;
  /** Category of each node: shared by all tips below, else null (mixed). */
  keyOfNode: (string | null)[];
  color: Map<string, string>;
  entries: LegendEntry[];
}

export const MIXED_COLOR = "#8a96a3";
const OTHER_COLOR = "#c7ced6";
const MISSING_COLOR = "#e3e7eb";
export const OUTGROUP_KEY = "outgroup";
export const UNCLUSTERED_KEY = "unclustered_backbone";
const NOT_IN_CORPUS = "not_in_corpus";
const NONE = "none";

/** Categorical palette beyond the clade palette (Okabe-Ito + Tol muted, colour-blind safe). */
const CAT = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#882255", "#117733", "#332288", "#999933"];
const EVIDENCE_COLOR: Record<string, string> = { E1: "#0f4f91", E2: "#1665b5", E3: "#5b9bd5", E4: "#a9c8e8", E5: "#dbe7f3" };
const ROLE_ORDER = ["anchor_characterized", "seed", "cl0.6_representative", "boundary_schizorhodopsin", "outgroup_heliorhodopsin"];
const ROLE_LABEL: Record<string, string> = {
  anchor_characterized: "Characterised anchor",
  seed: "Seed",
  "cl0.6_representative": "cl0.6 cluster representative",
  boundary_schizorhodopsin: "Schizorhodopsin (boundary)",
  outgroup_heliorhodopsin: "Heliorhodopsin (outgroup)",
};
export const tipRoleLabel = (r: string) => ROLE_LABEL[r] ?? r;
const TOP_N = 9;

function rawKey(mode: ColorMode, t: ExplorerTip): string {
  switch (mode) {
    case "clade":
      if (t.tip_role === "outgroup_heliorhodopsin") return OUTGROUP_KEY;
      return t.level1 ?? t.backbone_group ?? UNCLUSTERED_KEY;
    case "subclade":
      if (t.tip_role === "outgroup_heliorhodopsin") return OUTGROUP_KEY;
      return t.subclade ?? NONE;
    case "domain": return t.tax_domain ?? (t.in_corpus ? NONE : NOT_IN_CORPUS);
    case "phylum": return t.phylum ?? NONE;
    case "function": return t.in_corpus ? t.func_class ?? NONE : NOT_IN_CORPUS;
    case "evidence": return t.in_corpus ? t.evidence_level ?? NONE : NOT_IN_CORPUS;
    case "motif": return t.helixC_motif ?? NONE;
    case "role": return t.tip_role;
  }
}

function labelFor(mode: ColorMode, key: string): string {
  if (key === NOT_IN_CORPUS) return "Not in the v1.6.1 corpus";
  if (key === OUTGROUP_KEY) return "Heliorhodopsin outgroup";
  if (key === UNCLUSTERED_KEY) return "Backbone tip (no clade)";
  if (key === "__other") return "Other (grouped)";
  if (key === NONE) return mode === "subclade" ? "No subclade" : "Not recorded";
  if (mode === "function") return FUNC_LABEL[key as keyof typeof FUNC_LABEL] ?? key;
  if (mode === "role") return tipRoleLabel(key);
  if (mode === "clade" || mode === "subclade") return key;
  return key;
}

/**
 * Build a colour scheme. Clade colours are assigned in leaf order with the same palette and rule
 * as the Home preview (assignGroupColors), so both views colour each clade identically.
 */
/** Legend entries restricted to the tips below `rootPre` (subtree views); colours are unchanged. */
export function scopeScheme(tree: XTree, scheme: ColorScheme, rootPre: number): ColorScheme {
  if (!rootPre) return scheme;
  const a = tree.nodes[rootPre];
  const cnt = new Map<string, { i: number; o: number }>();
  for (const p of tree.leafOrder.slice(a.first, a.last + 1)) {
    const k = scheme.keyOfTip.get(p)!;
    const og = tipInfo(tree, p)!.tip_role === "outgroup_heliorhodopsin";
    const v = cnt.get(k) ?? { i: 0, o: 0 };
    if (og) v.o++;
    else v.i++;
    cnt.set(k, v);
  }
  return {
    ...scheme,
    entries: scheme.entries.filter((e) => cnt.has(e.key)).map((e) => ({ ...e, nIngroup: cnt.get(e.key)!.i, nOutgroup: cnt.get(e.key)!.o })),
  };
}

export function buildColorScheme(tree: XTree, mode: ColorMode): ColorScheme {
  const keyOfTip = new Map<number, string>();
  const counts = new Map<string, { i: number; o: number }>();
  for (const p of tree.leafOrder) {
    const t = tipInfo(tree, p)!;
    keyOfTip.set(p, rawKey(mode, t));
  }
  // group rare categories for high-cardinality fields
  if (mode === "phylum" || mode === "motif") {
    const freq = new Map<string, number>();
    for (const k of keyOfTip.values()) if (k !== NONE) freq.set(k, (freq.get(k) ?? 0) + 1);
    const top = new Set([...freq.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, TOP_N).map((e) => e[0]));
    for (const [p, k] of keyOfTip) if (k !== NONE && !top.has(k)) keyOfTip.set(p, "__other");
  }
  for (const p of tree.leafOrder) {
    const k = keyOfTip.get(p)!;
    const og = tipInfo(tree, p)!.tip_role === "outgroup_heliorhodopsin";
    const c = counts.get(k) ?? { i: 0, o: 0 };
    if (og) c.o++;
    else c.i++;
    counts.set(k, c);
  }

  const color = new Map<string, string>();
  const special = (k: string) => k === NONE || k === NOT_IN_CORPUS || k === "__other" || k === UNCLUSTERED_KEY || k === OUTGROUP_KEY;
  const fixed = (k: string): string | undefined => {
    if (k === OUTGROUP_KEY) return OUTGROUP_COLOR;
    if (k === UNCLUSTERED_KEY) return BACKBONE_COLOR;
    if (k === "__other") return OTHER_COLOR;
    if (k === NONE || k === NOT_IN_CORPUS) return MISSING_COLOR;
    return undefined;
  };
  let order: string[];
  if (mode === "clade" || mode === "subclade") {
    const seq = tree.leafOrder.map((p) => keyOfTip.get(p)!).filter((k) => !special(k));
    const m = assignGroupColors(seq, CLADE_PALETTE);
    for (const [k, c] of m) color.set(k, c);
    order = [...new Set(seq)].sort();
  } else if (mode === "function") {
    order = FUNC_ORDER.filter((f) => counts.has(f));
    order.forEach((k, i) => color.set(k, CAT[i % CAT.length]));
  } else if (mode === "evidence") {
    order = ["E1", "E2", "E3", "E4", "E5"].filter((e) => counts.has(e));
    for (const k of order) color.set(k, EVIDENCE_COLOR[k]);
  } else if (mode === "role") {
    order = ROLE_ORDER.filter((r) => counts.has(r));
    const rc: Record<string, string> = {
      anchor_characterized: "#D55E00", seed: "#CC79A7", "cl0.6_representative": "#0072B2", boundary_schizorhodopsin: "#009E73", outgroup_heliorhodopsin: OUTGROUP_COLOR,
    };
    for (const k of order) color.set(k, rc[k] ?? MIXED_COLOR);
  } else {
    order = [...counts.entries()].filter(([k]) => !special(k)).sort((a, b) => b[1].i + b[1].o - (a[1].i + a[1].o) || a[0].localeCompare(b[0])).map((e) => e[0]);
    order.forEach((k, i) => color.set(k, CAT[i % CAT.length]));
  }
  const tail = [UNCLUSTERED_KEY, "__other", NONE, NOT_IN_CORPUS, OUTGROUP_KEY].filter((k) => counts.has(k) && !order.includes(k));
  for (const k of tail) color.set(k, fixed(k)!);
  const entries: LegendEntry[] = [...order, ...tail].map((k) => ({
    key: k, label: labelFor(mode, k), color: color.get(k)!, nIngroup: counts.get(k)?.i ?? 0, nOutgroup: counts.get(k)?.o ?? 0,
  }));

  const keyOfNode: (string | null)[] = new Array(tree.nodes.length).fill(null);
  for (let p = tree.nodes.length - 1; p >= 0; p--) {
    const n = tree.nodes[p];
    if (n.isTip) keyOfNode[p] = keyOfTip.get(p)!;
    else {
      const k0 = keyOfNode[n.children[0]];
      keyOfNode[p] = k0 !== null && n.children.every((c) => keyOfNode[c] === k0) ? k0 : null;
    }
  }
  return { mode, keyOfTip, keyOfNode, color, entries };
}

export const nodeColor = (s: ColorScheme, pre: number) => {
  const k = s.keyOfNode[pre];
  return k === null ? MIXED_COLOR : s.color.get(k) ?? MIXED_COLOR;
};

/* ------------------------------------------------------------------ search */

export interface SearchHit { acc: string; pre: number; label: string; score: number }

export function searchTips(tree: XTree, q: string, limit = 20): SearchHit[] {
  const s = q.trim().toLowerCase();
  if (s.length < 2) return [];
  const hits: SearchHit[] = [];
  for (const [acc, t] of Object.entries(tree.ex.tips)) {
    const a = acc.toLowerCase();
    const m = (t.mrdb_acc ?? "").toLowerCase();
    let score = 0;
    if (a === s || m === s) score = 100;
    else if (a.startsWith(s) || (m && m.startsWith(s))) score = 60;
    else if (a.includes(s)) score = 40;
    else if ((t.organism ?? "").toLowerCase().includes(s) || (t.protein_name ?? "").toLowerCase().includes(s)) score = 20;
    else if ((t.level1 ?? "").toLowerCase() === s || (t.subclade ?? "").toLowerCase() === s) score = 10;
    if (score) hits.push({ acc, pre: t.pre, score, label: [acc, t.mrdb_acc, t.organism].filter(Boolean).join(" · ") });
  }
  return hits.sort((x, y) => y.score - x.score || x.acc.localeCompare(y.acc)).slice(0, limit);
}

/* ------------------------------------------------------------------ misc */

/** Visible ancestor collapsed nodes of `pre` (to expand when revealing a tip). */
export function collapsedAncestors(tree: XTree, pre: number, collapsed: ReadonlySet<number>): number[] {
  return ancestors(tree, pre).filter((a) => collapsed.has(a));
}

/** Pre index of each level-1 MRCA (for "collapse all clades"). */
export function level1Mrcas(tree: XTree): Map<string, number> {
  const m = new Map<string, number>();
  for (const e of tree.ex.nodes) for (const c of e.clade_mrca) m.set(c, e.pre);
  return m;
}

export function subcladeMrcas(tree: XTree): Map<string, number> {
  const m = new Map<string, number>();
  for (const e of tree.ex.nodes) for (const c of e.subclade_mrca) m.set(c, e.pre);
  return m;
}

export const shortGroup = (k: string) => (k.startsWith("MR_CLD3_") ? cladeShort(k) : k);

/** Contiguous runs of visible leaves sharing a scheme key (clade strip). Mixed collapsed leaves break runs. */
export interface Run { key: string; lo: number; hi: number; n: number }
export function leafRuns(tree: XTree, L: Layout, scheme: ColorScheme): Run[] {
  const out: Run[] = [];
  for (const p of L.leaves) {
    const k = scheme.keyOfNode[p];
    const w = ((L.collapseExtent.has(p) ? COLLAPSED_SLOTS : 1) * L.step) / 2;
    const last = out[out.length - 1];
    const n = tree.nodes[p].nTips;
    if (k !== null && last && last.key === k) {
      last.hi = L.slot[p] + w;
      last.n += n;
    } else if (k !== null) out.push({ key: k, lo: L.slot[p] - w, hi: L.slot[p] + w, n });
  }
  return out;
}

/** Endpoints of the branch above `pre` in layout coordinates: [x0, y0, x1, y1]. */
export function branchSegment(tree: XTree, L: Layout, pre: number): [number, number, number, number] | null {
  const n = tree.nodes[pre];
  if (!n || pre === L.opts.rootPre || n.parent < 0 || Number.isNaN(L.rad[pre]) || Number.isNaN(L.rad[n.parent])) return null;
  const pr = L.rad[n.parent];
  if (L.opts.layout === "rect") return [pr, L.y[pre], L.x[pre], L.y[pre]];
  const a = L.slot[pre];
  return [pr * Math.cos(a), pr * Math.sin(a), L.x[pre], L.y[pre]];
}

/** Visible node that represents `pre` (itself, or its collapsed ancestor), or null if outside the subtree. */
export function visibleRepresentative(tree: XTree, L: Layout, pre: number): number | null {
  if (!isDescendant(tree, pre, L.opts.rootPre)) return null;
  let best: number | null = Number.isNaN(L.rad[pre]) ? null : pre;
  for (const a of ancestors(tree, pre)) {
    if (a === L.opts.rootPre) break;
    if (L.collapseExtent.has(a)) best = a;
  }
  return best;
}
