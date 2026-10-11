/**
 * Stand-alone SVG export of the current explorer view (layout, branch-length mode, colour mode,
 * subtree, collapsed nodes, support, highlights), with every tip labelled, a legend and a
 * provenance footer. Pure string builder (unit tested); the page turns it into SVG / PNG downloads.
 */
import {
  MIXED_COLOR, branchPath, branchSegment, collapsedPath, computeLayout, connectorPath, leafRuns,
  meetsThresholds, nodeColor, supportOf, tipInfo, visibleRepresentative,
  type ColorScheme, type LayoutOpts, type XTree,
} from "./explorerModel";

export interface ExportOpts {
  opts: LayoutOpts;
  scheme: ColorScheme;
  cladeScheme: ColorScheme;
  failingGroups: ReadonlySet<string>;
  support: { show: boolean; sh: number; uf: number };
  tip: number | null;
  placement: number[];
  title: string;
  provenance: string[];
}

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const r1 = (v: number) => (Math.round(v * 10) / 10).toString();
const ROW = 11;

export function exportSvg(tree: XTree, o: ExportOpts): { svg: string; width: number; height: number } {
  const rect = o.opts.layout === "rect";
  // size the drawing so that every leaf gets ROW px
  let nSlots = computeLayout(tree, o.opts, { w: 100, h: 100 }).nSlots;
  const labelW = 300;
  const legendW = 260;
  let size: { w: number; h: number };
  if (rect) size = { w: 620, h: Math.max(300, nSlots * ROW) };
  else {
    const R = Math.max(260, (nSlots * ROW) / (2 * Math.PI * 0.93));
    size = { w: 2 * R, h: 2 * R };
  }
  const L = computeLayout(tree, o.opts, size);
  nSlots = L.nSlots;
  const top = 56;
  const pad = 20;
  const ox = rect ? pad : pad + labelW + size.w / 2;
  const oy = rect ? top : top + labelW + size.h / 2;
  const drawW = rect ? pad + size.w + 16 + labelW : 2 * (pad + labelW) + size.w;
  const drawH = rect ? top + size.h + 20 : top + 2 * labelW + size.h;
  const legendRows = o.scheme.entries.length + 6;
  const width = Math.ceil(drawW + legendW);
  const footer = 18 * (o.provenance.length + 1);
  const height = Math.ceil(Math.max(drawH, top + legendRows * 16) + footer + 10);
  const out: string[] = [];
  out.push(`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" font-family="Liberation Sans, Arimo, Arial, sans-serif">`);
  out.push(`<title>${esc(o.title)}</title>`);
  out.push(`<defs><pattern id="hatch" patternUnits="userSpaceOnUse" width="5" height="5" patternTransform="rotate(45)"><rect width="5" height="5" fill="#fff7ed"/><line x1="0" y1="0" x2="0" y2="5" stroke="#b45309" stroke-width="2.4"/></pattern></defs>`);
  out.push(`<rect width="${width}" height="${height}" fill="#ffffff"/>`);
  out.push(`<text x="${pad}" y="26" font-size="16" font-weight="700" fill="#142238">${esc(o.title)}</text>`);
  out.push(`<g transform="translate(${r1(ox)} ${r1(oy)})">`);

  // branches
  const byColor = new Map<string, string[]>();
  for (const q of L.visible) {
    const c = nodeColor(o.scheme, q);
    const d = branchPath(tree, L, q) + connectorPath(tree, L, q);
    if (!d) continue;
    (byColor.get(c) ?? byColor.set(c, []).get(c)!).push(d);
  }
  out.push(`<g fill="none" stroke-linecap="square">`);
  for (const [c, ds] of byColor) out.push(`<path d="${ds.join("")}" stroke="${c}" stroke-width="${c === MIXED_COLOR ? 1 : 1.3}"/>`);
  out.push(`</g>`);
  for (const q of L.leaves) if (L.collapseExtent.has(q)) {
    const c = nodeColor(o.scheme, q);
    out.push(`<path d="${collapsedPath(L, q)}" fill="${c}" fill-opacity="0.55" stroke="${c}"/>`);
  }

  // clade strip + labels
  const ext = L.bbox.x1;
  const runs = leafRuns(tree, L, o.cladeScheme);
  for (const r of runs) {
    const fail = o.failingGroups.has(r.key);
    const fill = fail ? "url(#hatch)" : o.cladeScheme.color.get(r.key) ?? MIXED_COLOR;
    if (rect) out.push(`<rect x="${r1(ext + 8)}" y="${r1(r.lo)}" width="7" height="${r1(r.hi - r.lo)}" fill="${fill}"${fail ? ' stroke="#b45309"' : ""}/>`);
    else {
      const a0 = r.lo;
      const a1 = r.hi;
      const ra = ext + 8;
      const rb = ext + 15;
      const p = (rr: number, aa: number) => `${r1(rr * Math.cos(aa))} ${r1(rr * Math.sin(aa))}`;
      const lg = a1 - a0 > Math.PI ? 1 : 0;
      out.push(`<path d="M${p(ra, a0)}L${p(rb, a0)}A${rb} ${rb} 0 ${lg} 1 ${p(rb, a1)}L${p(ra, a1)}A${ra} ${ra} 0 ${lg} 0 ${p(ra, a0)}Z" fill="${fill}"${fail ? ' stroke="#b45309"' : ""}/>`);
    }
  }
  out.push(`<g font-size="9" fill="#142238">`);
  for (const q of L.leaves) {
    const collapsed = L.collapseExtent.has(q);
    let text: string;
    if (collapsed) {
      const e = tree.info.get(q)!;
      const g = e.clade_mrca[0] ?? e.subclade_mrca[0];
      text = `${g ? g + " " : ""}(${tree.nodes[q].nTips} tips, collapsed)`;
    } else {
      const t = tipInfo(tree, q)!;
      const grp = t.level1 ?? t.backbone_group ?? (t.tip_role === "outgroup_heliorhodopsin" ? "outgroup" : "");
      text = `${tree.nodes[q].name}${t.organism ? " " + t.organism.slice(0, 40) : ""}${grp ? " [" + grp + "]" : ""}`;
    }
    if (rect) out.push(`<text x="${r1(ext + 20)}" y="${r1(L.y[q])}" dominant-baseline="central"${collapsed ? ' font-style="italic"' : ""}>${esc(text)}</text>`);
    else {
      const a = L.slot[q];
      const rr = ext + 20;
      const x = rr * Math.cos(a);
      const y = rr * Math.sin(a);
      const flip = Math.cos(a) < 0;
      const deg = (a * 180) / Math.PI + (flip ? 180 : 0);
      out.push(`<text x="${r1(x)}" y="${r1(y)}" dominant-baseline="central" text-anchor="${flip ? "end" : "start"}" transform="rotate(${r1(deg)} ${r1(x)} ${r1(y)})"${collapsed ? ' font-style="italic"' : ""}>${esc(text)}</text>`);
    }
  }
  out.push(`</g>`);

  // support
  if (o.support.show) {
    out.push(`<g font-size="7.5">`);
    for (const q of L.visible) {
      const s = supportOf(tree, q);
      if (!s) continue;
      const ok = meetsThresholds(s, o.support.sh, o.support.uf);
      out.push(`<circle cx="${r1(L.x[q])}" cy="${r1(L.y[q])}" r="2.4" fill="${ok ? "#142238" : "#ffffff"}" stroke="${ok ? "#142238" : "#b45309"}"/>`);
      out.push(`<text x="${r1(L.x[q] - 3)}" y="${r1(L.y[q] - 3.5)}" text-anchor="end" fill="${ok ? "#142238" : "#8a3c04"}">${s.label}</text>`);
    }
    out.push(`</g>`);
  }
  // placement + tip highlight
  for (const q of o.placement) {
    const rep = visibleRepresentative(tree, L, q);
    const sg = rep === null ? null : branchSegment(tree, L, rep);
    if (sg) out.push(`<line x1="${r1(sg[0])}" y1="${r1(sg[1])}" x2="${r1(sg[2])}" y2="${r1(sg[3])}" stroke="#b45309" stroke-width="3" stroke-dasharray="6 4"/>`);
  }
  if (o.tip !== null) {
    const rep = visibleRepresentative(tree, L, o.tip);
    if (rep !== null) out.push(`<circle cx="${r1(L.x[rep])}" cy="${r1(L.y[rep])}" r="5" fill="#E9ED4C" stroke="#142238" stroke-width="2"/>`);
  }
  out.push(`</g>`);

  // legend
  const lx = drawW + 10;
  let ly = top;
  out.push(`<g font-size="11" fill="#142238">`);
  out.push(`<text x="${lx}" y="${ly}" font-weight="700">Colour: ${esc(colorTitle(o.scheme))}</text>`);
  ly += 18;
  for (const e of o.scheme.entries) {
    out.push(`<rect x="${lx}" y="${ly - 8}" width="10" height="10" fill="${e.color}" stroke="#526175" stroke-width="0.5"/>`);
    const cnt = e.nOutgroup ? `${e.nIngroup} + ${e.nOutgroup} outgroup` : `${e.nIngroup}`;
    out.push(`<text x="${lx + 16}" y="${ly}">${esc(e.label)} (${cnt})</text>`);
    ly += 16;
  }
  out.push(`<rect x="${lx}" y="${ly - 8}" width="10" height="10" fill="${MIXED_COLOR}"/><text x="${lx + 16}" y="${ly}">Mixed descendants</text>`);
  ly += 16;
  if (o.failingGroups.size) {
    out.push(`<rect x="${lx}" y="${ly - 8}" width="10" height="10" fill="url(#hatch)" stroke="#b45309"/><text x="${lx + 16}" y="${ly}">Legacy clade, fails corrected support</text>`);
    ly += 16;
  }
  if (o.support.show) {
    out.push(`<circle cx="${lx + 5}" cy="${ly - 3}" r="3" fill="#142238"/><text x="${lx + 16}" y="${ly}">Support meets SH-aLRT &#8805; ${o.support.sh} and UFBoot &#8805; ${o.support.uf}</text>`);
    ly += 16;
    out.push(`<circle cx="${lx + 5}" cy="${ly - 3}" r="3" fill="#ffffff" stroke="#b45309"/><text x="${lx + 16}" y="${ly}">Below thresholds</text>`);
    ly += 16;
  }
  if (o.placement.length) {
    out.push(`<line x1="${lx}" x2="${lx + 12}" y1="${ly - 3}" y2="${ly - 3}" stroke="#b45309" stroke-width="3" stroke-dasharray="4 2"/><text x="${lx + 16}" y="${ly}">Placement best branch (position not stored)</text>`);
    ly += 16;
  }
  out.push(`</g>`);
  // scale bar + footer
  const fy = height - footer;
  const unit = o.opts.branch === "prop" ? 0.1 : 5;
  const w = unit * L.scale;
  out.push(`<g font-size="10" fill="#526175"><line x1="${pad}" x2="${r1(pad + w)}" y1="${fy - 6}" y2="${fy - 6}" stroke="#142238" stroke-width="1.5"/><text x="${r1(pad + w + 6)}" y="${fy - 3}">${o.opts.branch === "prop" ? `${unit} substitutions/site` : `${unit} branches (uniform lengths)`}</text>`);
  o.provenance.forEach((line, i) => out.push(`<text x="${pad}" y="${fy + 14 + i * 16}">${esc(line)}</text>`));
  out.push(`</g></svg>`);
  return { svg: out.join("\n"), width, height };
}

function colorTitle(s: ColorScheme): string {
  return ({ clade: "level-1 clade", subclade: "subclade", domain: "taxonomic domain", phylum: "phylum", function: "function (v1.6.0)", evidence: "evidence level", motif: "helix-C motif", role: "tip role" } as const)[s.mode];
}
