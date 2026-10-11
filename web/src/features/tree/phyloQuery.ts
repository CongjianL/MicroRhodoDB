/**
 * #/phylogeny query-string contract (shareable explorer state). Pure; unit tested.
 *
 *   layout=rect|radial        bl=prop|uniform          color=<ColorMode>
 *   tip=<accession>           node=<pre>  (subtree root; 0 = whole tree)
 *   clade=<MR_CLD3_xxx[.yy]>  placement=<MRDB######> [src=<source accession>]
 *   support=1  sh=<0-100>  uf=<0-100>   collapsed=<pre>,<pre>,...
 *
 * Defaults are omitted from the serialised form so the canonical URL stays short.
 */
import { CLADE_RE, MRDB_RE, SUBCLADE_RE } from "../../app/routes";
import { isColorMode, type BranchMode, type ColorMode, type LayoutKind } from "./explorerModel";

export interface PhyloQuery {
  layout: LayoutKind;
  bl: BranchMode;
  color: ColorMode;
  tip: string | null;
  node: number;
  clade: string | null;
  placement: string | null;
  src: string | null;
  support: boolean;
  sh: number;
  uf: number;
  collapsed: number[];
}

export const DEFAULT_SH = 80;
export const DEFAULT_UF = 95;

export const DEFAULT_QUERY: PhyloQuery = {
  layout: "rect", bl: "prop", color: "clade", tip: null, node: 0, clade: null, placement: null, src: null,
  support: false, sh: DEFAULT_SH, uf: DEFAULT_UF, collapsed: [],
};

const pct = (v: string | null, d: number) => {
  if (v === null || v.trim() === "") return d;
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 && n <= 100 ? n : d;
};
const ACC_RE = /^[A-Za-z0-9_.]{3,40}$/;

export function parsePhyloQuery(p: URLSearchParams, nNodes = Infinity): PhyloQuery {
  const node = Number(p.get("node"));
  const clade = (p.get("clade") ?? "").trim().toUpperCase();
  const placement = (p.get("placement") ?? "").trim().toUpperCase();
  const tip = (p.get("tip") ?? "").trim();
  const src = (p.get("src") ?? "").trim();
  const color = p.get("color");
  const collapsed = (p.get("collapsed") ?? "")
    .split(",")
    .map((s) => Number(s))
    .filter((n) => Number.isInteger(n) && n > 0 && n < nNodes);
  return {
    layout: p.get("layout") === "radial" ? "radial" : "rect",
    bl: p.get("bl") === "uniform" ? "uniform" : "prop",
    color: isColorMode(color) ? color : "clade",
    tip: tip && ACC_RE.test(tip) ? tip : null,
    node: Number.isInteger(node) && node > 0 && node < nNodes ? node : 0,
    clade: CLADE_RE.test(clade) || SUBCLADE_RE.test(clade) ? clade : null,
    placement: MRDB_RE.test(placement) ? placement : null,
    src: src && ACC_RE.test(src) ? src : null,
    support: p.get("support") === "1",
    sh: pct(p.get("sh"), DEFAULT_SH),
    uf: pct(p.get("uf"), DEFAULT_UF),
    collapsed: [...new Set(collapsed)].sort((a, b) => a - b),
  };
}

export function phyloQueryString(q: Partial<PhyloQuery>): string {
  const f = { ...DEFAULT_QUERY, ...q };
  const p = new URLSearchParams();
  if (f.layout !== "rect") p.set("layout", f.layout);
  if (f.bl !== "prop") p.set("bl", f.bl);
  if (f.color !== "clade") p.set("color", f.color);
  if (f.node) p.set("node", String(f.node));
  if (f.clade) p.set("clade", f.clade);
  if (f.tip) p.set("tip", f.tip);
  if (f.placement) p.set("placement", f.placement);
  if (f.placement && f.src) p.set("src", f.src);
  if (f.support) p.set("support", "1");
  if (f.sh !== DEFAULT_SH) p.set("sh", String(f.sh));
  if (f.uf !== DEFAULT_UF) p.set("uf", String(f.uf));
  if (f.collapsed.length) p.set("collapsed", [...f.collapsed].sort((a, b) => a - b).join(","));
  return p.toString();
}
