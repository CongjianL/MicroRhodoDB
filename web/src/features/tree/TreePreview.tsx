/**
 * Static preview of the real MR_RT_003 reference tree (472 tips), drawn from the exported rooted
 * Newick with branch lengths to scale. Ring segments mark level-1 clades and backbone groups using
 * phylogeny/tips.json; no tip labels (spec 4.3). Clades failing the corrected IQ-TREE run1 support
 * thresholds are hatched. The full interactive explorer is #/phylogeny (PhylogenyPage).
 */
import type { Clades, Tips } from "../../data/types";
import { cladeShort, fmtInt } from "../../lib/format";
import { parseNewick, radialLayout, sectorPath } from "./newick";
import { boxExtent, clearLabelRadius, labelBox } from "./labelPlacement";

import { BACKBONE_COLOR as BACKBONE, CLADE_PALETTE, OUTGROUP_COLOR as OUTGROUP, assignGroupColors } from "./palette";

export { CLADE_PALETTE };
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
  // Same leaf-order rule as the phylogeny explorer (explorerModel.buildColorScheme "clade").
  const colorOf = assignGroupColors(layout.arcs.map((a) => a.group).filter((g) => g !== OUTGROUP_KEY), CLADE_PALETTE);
  if (layout.arcs.some((a) => a.group === OUTGROUP_KEY)) colorOf.set(OUTGROUP_KEY, OUTGROUP);
  return {
    layout,
    colorOf,
    nOutgroup: tips.tips.filter((t) => t.tip_role === "outgroup_heliorhodopsin").length,
    nUnclustered: tips.tips.filter((t) => t.unclustered_backbone).length,
    nTips: layout.nTips,
  };
}

export const TREE_RADIUS = 250;

export interface TreeHighlight {
  /** Reference-tree tip to mark (only for records that are themselves tips). */
  tip?: string | null;
  /** Level-1 clade / backbone group whose ring segment is emphasised (placed records: clade arc only). */
  group?: string | null;
  label: string;
}

export function TreePreview({ model, clades, highlight, idPrefix = "tree" }: { model: TreeModel; clades: Clades; highlight?: TreeHighlight; idPrefix?: string }) {
  const R = model.layout.radius;
  const ring0 = R + 8;
  const ring1 = R + 26;
  const failing = new Set(clades.level1.filter((c) => !c.support_audit.iqtree_run1_meets_support_thresholds).map((c) => c.clade_id));
  const { layout, colorOf } = model;
  const scaleLen = 1; // substitutions per site
  const nClades = clades.level1.filter((c) => c.kind === "clade").length;
  const nBackbone = clades.level1.filter((c) => c.kind === "backbone_group").length;
  const hiGroup = highlight?.group ?? null;
  const dim = (g: string) => !!highlight && hiGroup !== null && g !== hiGroup;
  const tip = highlight?.tip ? layout.tipPos.get(highlight.tip) : undefined;
  const hiArcs = hiGroup ? layout.arcs.filter((a) => a.group === hiGroup) : [];
  // Highlight outline: sector ring0-4 .. ring1+4 with a 3 px stroke, so its outer edge is ring1 + 5.5.
  const hiOuter = ring1 + 4 + 1.5;
  const labelFor = (a: (typeof layout.arcs)[number]) => {
    const text = (a.group === OUTGROUP_KEY ? "OG" : cladeShort(a.group)) + (failing.has(a.group) ? "!" : "");
    const mid = (a.start + a.end) / 2;
    const base = ring1 + 15;
    if (a.group !== hiGroup) return { text, mid, r: base, w: 0, h: 0 };
    const { w, h } = labelBox(text, 15);
    return { text, mid, r: clearLabelRadius(base, hiOuter, w, h, mid), w, h };
  };
  // Enlarge the drawing only when a pushed-out highlighted label would otherwise be clipped.
  const ext = Math.max(ring1 + 34, ...hiArcs.map((a) => {
    const l = labelFor(a);
    return boxExtent(l.r, l.w, l.h, l.mid) + 4;
  }));

  return (
    <svg
      viewBox={`${-ext} ${-ext} ${2 * ext} ${2 * ext + 26}`}
      className="h-auto w-full"
      role="img"
      aria-labelledby={`${idPrefix}-title ${idPrefix}-desc`}
      data-testid="tree-preview"
      data-tips={model.nTips}
      data-highlight-tip={highlight?.tip ?? undefined}
      data-highlight-group={highlight?.group ?? undefined}
    >
      <title id={`${idPrefix}-title`}>MR_RT_003 reference tree preview ({model.nTips} tips){highlight ? `: ${highlight.label}` : ""}</title>
      <desc id={`${idPrefix}-desc`}>
        Circular phylogram of the {model.nTips}-tip MR_RT_003 reference tree rooted on {model.nOutgroup} heliorhodopsin outgroup tips,
        branch lengths to scale. Outer ring segments mark {nClades} level-1 clades and {nBackbone} backbone groups;
        {" "}{model.nUnclustered} backbone tips belong to no clade. Hatched segments fail the corrected clade-support thresholds.
        The table next to the figure lists every clade with its support.
      </desc>
      <defs>
        <pattern id={`${idPrefix}-hatch-fail`} patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
          <rect width="6" height="6" fill="#fff7ed" />
          <line x1="0" y1="0" x2="0" y2="6" stroke="#b45309" strokeWidth="3" />
        </pattern>
      </defs>
      <g fill="none" strokeWidth="0.9" strokeLinecap="round">
        {layout.edges.map((e) => (
          <path key={e.group ?? "_"} d={e.d} stroke={e.group ? colorOf.get(e.group) ?? BACKBONE : BACKBONE} opacity={highlight && (dim(e.group ?? "") || !e.group) ? 0.35 : 1} />
        ))}
      </g>
      <g>
        {layout.arcs.map((a) => {
          const fail = failing.has(a.group);
          const big = a.n >= 9 || a.group === OUTGROUP_KEY;
          const { text: label, mid, r: lr } = labelFor(a);
          const isHi = a.group === hiGroup;
          return (
            <g key={a.group + a.start} data-group={a.group}>
              <path
                d={sectorPath(ring0, ring1, a.start, a.end)}
                fill={fail ? `url(#${idPrefix}-hatch-fail)` : colorOf.get(a.group)}
                opacity={dim(a.group) ? 0.28 : 1}
                stroke={fail ? "#b45309" : "#ffffff"}
                strokeWidth={fail ? 1.2 : 0.8}
              >
                <title>
                  {a.group === OUTGROUP_KEY ? `Heliorhodopsin outgroup (${a.n} tips)` : `${a.group} (${a.n} tips)${fail ? " - fails corrected support thresholds" : ""}`}
                </title>
              </path>
              {big ? (
                <text
                  data-testid="tree-label"
                  data-group={a.group}
                  data-highlighted={isHi ? "true" : undefined}
                  data-clear-r={isHi ? hiOuter : undefined}
                  x={lr * Math.cos(mid)}
                  y={lr * Math.sin(mid)}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize="15"
                  fontWeight={fail ? 700 : 600}
                  fill={fail ? "#8a3c04" : "#142238"}
                >
                  {label}
                </text>
              ) : null}
            </g>
          );
        })}
      </g>
      {hiArcs.map((a) => (
        <path key={`hi${a.start}`} d={sectorPath(ring0 - 4, ring1 + 4, a.start, a.end)} fill="none" stroke="#142238" strokeWidth="3" data-testid="tree-highlight-arc" />
      ))}
      {tip ? (
        <g data-testid="tree-highlight-tip">
          <line
            x1={tip.r * Math.cos(tip.angle)}
            y1={tip.r * Math.sin(tip.angle)}
            x2={(ring1 + 10) * Math.cos(tip.angle)}
            y2={(ring1 + 10) * Math.sin(tip.angle)}
            stroke="#142238"
            strokeWidth="2"
            strokeDasharray="3 3"
          />
          <circle cx={tip.r * Math.cos(tip.angle)} cy={tip.r * Math.sin(tip.angle)} r="7" fill="#E9ED4C" stroke="#142238" strokeWidth="2.5" />
        </g>
      ) : null}
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
