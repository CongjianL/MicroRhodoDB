/**
 * Static preview of the real MR_RT_003 reference tree (472 tips), drawn from the exported rooted
 * Newick with branch lengths to scale. Ring segments mark level-1 clades and backbone groups using
 * phylogeny/tips.json; no tip labels (spec 4.3). Clades failing the corrected IQ-TREE run1 support
 * thresholds are hatched. The full interactive explorer is PR-4.
 */
import type { Clades, Tips } from "../../data/types";
import { cladeShort, fmtInt } from "../../lib/format";
import { parseNewick, radialLayout, sectorPath } from "./newick";

export const CLADE_PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#882255", "#117733", "#332288", "#AA4499"];
const BACKBONE = "#9aa5b1";
const OUTGROUP = "#526175";
export const OUTGROUP_KEY = "outgroup";

export interface TreeModel {
  layout: ReturnType<typeof radialLayout>;
  colorOf: Map<string, string>;
  nOutgroup: number;
  nUnclustered: number;
  nTips: number;
}

export function buildTreeModel(newick: string, tips: Tips, radius: number): TreeModel {
  const root = parseNewick(newick);
  const info = new Map(tips.tips.map((t) => [t.tip, t]));
  const groupOf = (name: string): string | null => {
    const t = info.get(name);
    if (!t) throw new Error(`Tree tip ${name} missing from tips.json`);
    if (t.tip_role === "outgroup_heliorhodopsin") return OUTGROUP_KEY;
    return t.level1 ?? t.backbone_group ?? null;
  };
  const layout = radialLayout(root, groupOf, radius);
  if (layout.nTips !== tips.tips.length) throw new Error(`Tree has ${layout.nTips} tips; tips.json lists ${tips.tips.length}`);
  const colorOf = new Map<string, string>();
  let k = 0;
  for (const a of layout.arcs) {
    if (a.group === OUTGROUP_KEY) colorOf.set(a.group, OUTGROUP);
    else if (!colorOf.has(a.group)) colorOf.set(a.group, CLADE_PALETTE[k++ % CLADE_PALETTE.length]);
  }
  return {
    layout,
    colorOf,
    nOutgroup: tips.tips.filter((t) => t.tip_role === "outgroup_heliorhodopsin").length,
    nUnclustered: tips.tips.filter((t) => t.unclustered_backbone).length,
    nTips: layout.nTips,
  };
}

export const TREE_RADIUS = 250;

export function TreePreview({ model, clades }: { model: TreeModel; clades: Clades }) {
  const R = model.layout.radius;
  const ring0 = R + 8;
  const ring1 = R + 26;
  const failing = new Set(clades.level1.filter((c) => !c.support_audit.iqtree_run1_meets_support_thresholds).map((c) => c.clade_id));
  const ext = ring1 + 34;
  const { layout, colorOf } = model;
  const scaleLen = 1; // substitutions per site
  const nClades = clades.level1.filter((c) => c.kind === "clade").length;
  const nBackbone = clades.level1.filter((c) => c.kind === "backbone_group").length;

  return (
    <svg
      viewBox={`${-ext} ${-ext} ${2 * ext} ${2 * ext + 26}`}
      className="h-auto w-full"
      role="img"
      aria-labelledby="tree-title tree-desc"
      data-testid="tree-preview"
      data-tips={model.nTips}
    >
      <title id="tree-title">MR_RT_003 reference tree preview ({model.nTips} tips)</title>
      <desc id="tree-desc">
        Circular phylogram of the {model.nTips}-tip MR_RT_003 reference tree rooted on {model.nOutgroup} heliorhodopsin outgroup tips,
        branch lengths to scale. Outer ring segments mark {nClades} level-1 clades and {nBackbone} backbone groups;
        {" "}{model.nUnclustered} backbone tips belong to no clade. Hatched segments fail the corrected clade-support thresholds.
        The table next to the figure lists every clade with its support.
      </desc>
      <defs>
        <pattern id="hatch-fail" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
          <rect width="6" height="6" fill="#fff7ed" />
          <line x1="0" y1="0" x2="0" y2="6" stroke="#b45309" strokeWidth="3" />
        </pattern>
      </defs>
      <g fill="none" strokeWidth="0.9" strokeLinecap="round">
        {layout.edges.map((e) => (
          <path key={e.group ?? "_"} d={e.d} stroke={e.group ? colorOf.get(e.group) ?? BACKBONE : BACKBONE} />
        ))}
      </g>
      <g>
        {layout.arcs.map((a) => {
          const fail = failing.has(a.group);
          const mid = (a.start + a.end) / 2;
          const big = a.n >= 9 || a.group === OUTGROUP_KEY;
          const lr = ring1 + 15;
          const label = a.group === OUTGROUP_KEY ? "OG" : cladeShort(a.group);
          return (
            <g key={a.group + a.start} data-group={a.group}>
              <path
                d={sectorPath(ring0, ring1, a.start, a.end)}
                fill={fail ? "url(#hatch-fail)" : colorOf.get(a.group)}
                stroke={fail ? "#b45309" : "#ffffff"}
                strokeWidth={fail ? 1.2 : 0.8}
              >
                <title>
                  {a.group === OUTGROUP_KEY ? `Heliorhodopsin outgroup (${a.n} tips)` : `${a.group} (${a.n} tips)${fail ? " - fails corrected support thresholds" : ""}`}
                </title>
              </path>
              {big ? (
                <text
                  x={lr * Math.cos(mid)}
                  y={lr * Math.sin(mid)}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize="15"
                  fontWeight={fail ? 700 : 600}
                  fill={fail ? "#8a3c04" : "#142238"}
                >
                  {label}
                  {fail ? "!" : ""}
                </text>
              ) : null}
            </g>
          );
        })}
      </g>
      <g transform={`translate(${-ext + 12} ${ext + 6})`} fontSize="13" fill="#526175">
        <line x1="0" x2={scaleLen * layout.scale} y1="0" y2="0" stroke="#142238" strokeWidth="1.5" />
        <line x1="0" x2="0" y1="-4" y2="4" stroke="#142238" strokeWidth="1.5" />
        <line x1={scaleLen * layout.scale} x2={scaleLen * layout.scale} y1="-4" y2="4" stroke="#142238" strokeWidth="1.5" />
        <text x={scaleLen * layout.scale + 8} y="0" dominantBaseline="central">{scaleLen} substitution/site</text>
      </g>
      <text x={ext - 12} y={ext + 6} textAnchor="end" dominantBaseline="central" fontSize="13" fill="#526175">
        {fmtInt(model.nTips)} tips · rooted on outgroup
      </text>
    </svg>
  );
}
