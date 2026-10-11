/**
 * Interactive SVG renderer for the MR_RT_003 explorer (custom SVG, no extra dependency).
 *
 * Branches are drawn once per layout/colour change in layout coordinates inside a scaled <g>
 * (non-scaling strokes); everything that must keep a constant on-screen size (tip labels, support
 * labels, hit targets, highlights) is drawn in screen coordinates and culled to the viewport, so
 * zoom/pan stays cheap for the 943-node tree.
 */
import { forwardRef, useCallback, useEffect, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  COLLAPSED_SLOTS, MIXED_COLOR, OUTGROUP_KEY, ancestors, branchPath, branchSegment, collapsedPath, computeLayout, connectorPath,
  leafRuns, meetsThresholds, nodeColor, shortGroup, spanPath, supportOf, tipInfo, visibleRepresentative,
  type ColorScheme, type Layout, type LayoutOpts, type XTree,
} from "./explorerModel";

export interface SupportOpts { show: boolean; sh: number; uf: number }

export interface TreeCanvasProps {
  tree: XTree;
  opts: LayoutOpts;
  scheme: ColorScheme;
  /** Level-1 clade scheme for the clade strip (always shown, independent of the colour mode). */
  cladeScheme: ColorScheme;
  failingGroups: ReadonlySet<string>;
  support: SupportOpts;
  selected: number | null;
  tip: number | null;
  placement: number[];
  cladeSpan: number | null;
  /** Changing this value re-centres the view on the given node. */
  focus: { pre: number; nonce: number } | null;
  height: number;
  onSelect: (pre: number | null) => void;
  onHover: (pre: number | null) => void;
  label: string;
  testId?: string;
}

export interface TreeCanvasHandle {
  zoom: (f: number) => void;
  reset: () => void;
  svg: () => SVGSVGElement | null;
}

interface View { k: number; tx: number; ty: number }

const MIN_K = 0.6;
const MAX_K = 80;
const FONT = 11;
const LABEL_MIN_PX = 10;
const STRIP_W = 7;

function useWidth(ref: React.RefObject<HTMLElement | null>): number {
  const [w, setW] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setW(el.clientWidth);
    const ro = new ResizeObserver(() => setW(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return w;
}

export function geometry(width: number, height: number, layout: "rect" | "radial") {
  const narrow = width < 560;
  if (layout === "rect") {
    const gutter = narrow ? 92 : 190;
    return { size: { w: Math.max(60, width - 16 - gutter), h: Math.max(60, height - 28) }, origin: { x: 10, y: 14 }, gutter };
  }
  const gutter = narrow ? 34 : 64;
  const d = Math.max(60, Math.min(width, height) - 2 * gutter);
  return { size: { w: d, h: d }, origin: { x: width / 2, y: height / 2 }, gutter };
}

export const TreeCanvas = forwardRef<TreeCanvasHandle, TreeCanvasProps>(function TreeCanvas(p, ref) {
  const { tree, opts, scheme, cladeScheme, support, height } = p;
  const wrap = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const width = useWidth(wrap);
  const geo = useMemo(() => geometry(width || 800, height, opts.layout), [width, height, opts.layout]);
  const L: Layout = useMemo(() => computeLayout(tree, opts, geo.size), [tree, opts, geo]);
  const home = useMemo<View>(() => ({ k: 1, tx: geo.origin.x, ty: geo.origin.y }), [geo]);
  const [view, setView] = useState<View>(home);
  // Reset the view when the drawing changes shape (not on colour/support/collapse changes).
  useEffect(() => setView(home), [home, opts.layout, opts.branch, opts.rootPre]);

  /* ---------------- zoom / pan */
  const zoomAt = useCallback((f: number, sx: number, sy: number) => {
    setView((v) => {
      const k = Math.min(MAX_K, Math.max(MIN_K, v.k * f));
      return { k, tx: sx - (sx - v.tx) * (k / v.k), ty: sy - (sy - v.ty) * (k / v.k) };
    });
  }, []);
  const W = width || 800;
  useImperativeHandle(ref, () => ({
    zoom: (f) => zoomAt(f, W / 2, height / 2),
    reset: () => setView(home),
    svg: () => svgRef.current,
  }), [zoomAt, W, height, home]);

  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      // Zoom only when the tree has focus or a modifier is held, so page scrolling is never trapped.
      if (document.activeElement !== el && !e.ctrlKey && !e.metaKey) return;
      e.preventDefault();
      const r = el.getBoundingClientRect();
      zoomAt(Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [zoomAt]);

  const drag = useRef<{ id: number; x: number; y: number; moved: boolean; target: number | null; pts: Map<number, { x: number; y: number }>; dist: number } | null>(null);
  const onPointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    const hit = (e.target as Element).closest?.("[data-pre]");
    const d = drag.current ?? { id: e.pointerId, x: e.clientX, y: e.clientY, moved: false, target: hit ? Number(hit.getAttribute("data-pre")) : null, pts: new Map(), dist: 0 };
    d.pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (d.pts.size === 2) {
      const [a, b] = [...d.pts.values()];
      d.dist = Math.hypot(a.x - b.x, a.y - b.y);
    }
    drag.current = d;
    try {
      (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
    } catch {
      /* synthetic or already-released pointer: capture is only a convenience for panning */
    }
  };
  const onPointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const d = drag.current;
    if (!d || !d.pts.has(e.pointerId)) {
      return;
    }
    const prev = d.pts.get(e.pointerId)!;
    d.pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (Math.hypot(e.clientX - d.x, e.clientY - d.y) > 4) d.moved = true;
    if (d.pts.size === 2) {
      const [a, b] = [...d.pts.values()];
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      const r = svgRef.current!.getBoundingClientRect();
      if (d.dist > 0) zoomAt(dist / d.dist, (a.x + b.x) / 2 - r.left, (a.y + b.y) / 2 - r.top);
      d.dist = dist;
      d.moved = true;
      return;
    }
    if (d.moved) setView((v) => ({ ...v, tx: v.tx + e.clientX - prev.x, ty: v.ty + e.clientY - prev.y }));
  };
  const onPointerUp = (e: React.PointerEvent<SVGSVGElement>) => {
    const d = drag.current;
    if (!d) return;
    d.pts.delete(e.pointerId);
    if (d.pts.size === 0) {
      if (!d.moved) p.onSelect(d.target);
      drag.current = null;
    }
  };
  const onKeyDown = (e: React.KeyboardEvent<SVGSVGElement>) => {
    const step = 48;
    const k: Record<string, () => void> = {
      "+": () => zoomAt(1.4, W / 2, height / 2),
      "=": () => zoomAt(1.4, W / 2, height / 2),
      "-": () => zoomAt(1 / 1.4, W / 2, height / 2),
      "0": () => setView(home),
      ArrowLeft: () => setView((v) => ({ ...v, tx: v.tx + step })),
      ArrowRight: () => setView((v) => ({ ...v, tx: v.tx - step })),
      ArrowUp: () => setView((v) => ({ ...v, ty: v.ty + step })),
      ArrowDown: () => setView((v) => ({ ...v, ty: v.ty - step })),
      Escape: () => p.onSelect(null),
    };
    if (k[e.key]) {
      e.preventDefault();
      k[e.key]();
    }
  };

  /* ---------------- focus on a node (tip search, clade, placement) */
  const focusNonce = p.focus?.nonce;
  useEffect(() => {
    if (!p.focus) return;
    const rep = visibleRepresentative(tree, L, p.focus.pre);
    if (rep === null) return;
    const n = tree.nodes[rep];
    // slot span of the node's visible leaves
    let lo = Infinity;
    let hi = -Infinity;
    for (const q of L.leaves) {
      if (q >= rep && tree.nodes[q].first >= n.first && tree.nodes[q].last <= n.last) {
        const w = ((L.collapseExtent.has(q) ? COLLAPSED_SLOTS : 1) * L.step) / 2;
        lo = Math.min(lo, L.slot[q] - w);
        hi = Math.max(hi, L.slot[q] + w);
      }
    }
    if (!Number.isFinite(lo)) return;
    if (opts.layout === "rect") {
      const want = Math.min(MAX_K, Math.max(1, Math.min((height * 0.8) / (hi - lo), Math.max(1, (FONT + 4) / L.step))));
      const yMid = (lo + hi) / 2;
      setView({ k: want, tx: geo.origin.x, ty: height / 2 - yMid * want });
    } else {
      const r = Math.max(L.rad[rep], 1);
      const arc = Math.max((hi - lo) * r, L.step * r);
      const want = Math.min(MAX_K, Math.max(1, Math.min((Math.min(W, height) * 0.6) / arc, (FONT + 4) / (L.step * Math.max(L.bbox.x1, 1)) * 1.1)));
      const px = L.x[rep];
      const py = L.y[rep];
      setView({ k: want, tx: W / 2 - px * want, ty: height / 2 - py * want });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusNonce, home, opts.layout, opts.branch, opts.rootPre]);

  /* ---------------- static branch geometry (layout coordinates) */
  const edges = useMemo(() => {
    const byColor = new Map<string, string[]>();
    const push = (c: string, d: string) => {
      if (!d) return;
      const a = byColor.get(c);
      if (a) a.push(d);
      else byColor.set(c, [d]);
    };
    const wedges: { pre: number; d: string; color: string }[] = [];
    for (const q of L.visible) {
      const c = nodeColor(scheme, q);
      push(c, branchPath(tree, L, q));
      push(c, connectorPath(tree, L, q));
      if (L.collapseExtent.has(q)) wedges.push({ pre: q, d: collapsedPath(L, q), color: c });
    }
    return { paths: [...byColor.entries()].map(([c, ds]) => ({ c, d: ds.join("") })), wedges };
  }, [tree, L, scheme]);

  const runs = useMemo(() => leafRuns(tree, L, cladeScheme), [tree, L, cladeScheme]);

  /* ---------------- screen-space overlay */
  // Rectangular layout zooms the vertical (leaf) axis only: the tree always spans the canvas width,
  // so tip labels stay in the right-hand gutter at every zoom level. Radial zoom is uniform.
  const rect = opts.layout === "rect";
  const { k, ty } = view;
  const tx = rect ? geo.origin.x : view.tx;
  const kx = rect ? 1 : k;
  const sx = (x: number) => x * kx + tx;
  const sy = (y: number) => y * k + ty;
  const inView = (x: number, y: number, m = 30) => x > -m && x < W + m && y > -m && y < height + m;
  const leafPx = rect ? L.step * k : L.step * L.bbox.x1 * k;
  const showLabels = leafPx >= LABEL_MIN_PX;
  const stripX = rect ? sx(L.bbox.x1) + 8 : 0; // rect: strip left edge
  const stripR = rect ? 0 : L.bbox.x1 * k + 8; // radial: strip inner radius
  const cx = tx;
  const cy = ty;

  const hits: { pre: number; x: number; y: number }[] = [];
  for (const q of L.visible) {
    const x = sx(L.x[q]);
    const y = sy(L.y[q]);
    if (inView(x, y, 8)) hits.push({ pre: q, x, y });
  }
  const hitR = Math.max(3, Math.min(8, leafPx / 2));

  const labels: { pre: number; x: number; y: number; a: number; text: string; collapsed: boolean }[] = [];
  for (const q of L.leaves) {
    const collapsed = L.collapseExtent.has(q);
    if (!showLabels && !(collapsed && leafPx * COLLAPSED_SLOTS >= LABEL_MIN_PX)) continue;
    let text: string;
    if (collapsed) {
      const e = tree.info.get(q)!;
      const g = e.clade_mrca[0] ?? e.subclade_mrca[0];
      text = `${g ? g + " " : ""}(${tree.nodes[q].nTips} tips, collapsed)`;
    } else {
      const t = tipInfo(tree, q)!;
      text = tree.nodes[q].name + (leafPx >= 13 && t.organism ? ` ${t.organism.length > 34 ? t.organism.slice(0, 33) + "\u2026" : t.organism}` : "");
    }
    if (rect) {
      const y = sy(L.y[q]);
      if (y < -10 || y > height + 10) continue;
      labels.push({ pre: q, x: stripX + STRIP_W + 5, y, a: 0, text, collapsed });
    } else {
      const a = L.slot[q];
      const r = stripR + STRIP_W + 5;
      const x = cx + r * Math.cos(a);
      const y = cy + r * Math.sin(a);
      if (!inView(x, y, 120)) continue;
      labels.push({ pre: q, x, y, a, text, collapsed });
    }
  }

  const supportMarks: { pre: number; x: number; y: number; ok: boolean; label: string }[] = [];
  if (support.show) {
    for (const h of hits) {
      const s = supportOf(tree, h.pre);
      if (!s) continue;
      supportMarks.push({ pre: h.pre, x: h.x, y: h.y, ok: meetsThresholds(s, support.sh, support.uf), label: s.label });
    }
  }
  const showSupportText = support.show && leafPx >= 12;

  const seg = (q: number) => {
    const s = branchSegment(tree, L, q);
    return s ? { x1: sx(s[0]), y1: sy(s[1]), x2: sx(s[2]), y2: sy(s[3]) } : null;
  };
  const lineage = p.selected !== null && !Number.isNaN(L.rad[p.selected]) ? [p.selected, ...ancestors(tree, p.selected)].filter((q) => !Number.isNaN(L.rad[q])) : [];
  const tipRep = p.tip !== null ? visibleRepresentative(tree, L, p.tip) : null;
  const placementSegs = p.placement.map((q) => ({ q, rep: visibleRepresentative(tree, L, q) })).filter((x) => x.rep !== null);

  const runPath = (r: { lo: number; hi: number }) => {
    if (rect) return `M${stripX} ${sy(r.lo) + 0.5}h${STRIP_W}V${sy(r.hi) - 0.5}h${-STRIP_W}Z`;
    const r0 = stripR;
    const r1 = stripR + STRIP_W;
    const a0 = r.lo + 0.002;
    const a1 = r.hi - 0.002;
    const pt = (rr: number, aa: number) => `${(cx + rr * Math.cos(aa)).toFixed(1)} ${(cy + rr * Math.sin(aa)).toFixed(1)}`;
    const large = a1 - a0 > Math.PI ? 1 : 0;
    return `M${pt(r0, a0)}L${pt(r1, a0)}A${r1} ${r1} 0 ${large} 1 ${pt(r1, a1)}L${pt(r0, a1)}A${r0} ${r0} 0 ${large} 0 ${pt(r0, a0)}Z`;
  };

  return (
    <div ref={wrap} className="relative w-full overflow-hidden rounded-md border border-line bg-surface" style={{ height }}>
      <svg
        ref={svgRef}
        width={W}
        height={height}
        viewBox={`0 0 ${W} ${height}`}
        role="application"
        aria-label={p.label}
        aria-roledescription="phylogenetic tree"
        tabIndex={0}
        className="block cursor-grab touch-none select-none outline-none focus-visible:ring-2 focus-visible:ring-accent"
        data-testid={p.testId ?? "tree-canvas"}
        data-layout={opts.layout}
        data-branch={opts.branch}
        data-color={scheme.mode}
        data-root={L.opts.rootPre}
        data-visible-leaves={L.leaves.length}
        data-zoom={k.toFixed(3)}
        data-labels={showLabels ? "on" : "off"}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => (drag.current = null)}
        onKeyDown={onKeyDown}
        onMouseOver={(e) => {
          const t = (e.target as Element).closest?.("[data-pre]");
          p.onHover(t ? Number(t.getAttribute("data-pre")) : null);
        }}
        onMouseLeave={() => p.onHover(null)}
        xmlns="http://www.w3.org/2000/svg"
        fontFamily="Liberation Sans, Arimo, Arial, sans-serif"
      >
        <defs>
          <pattern id="tc-hatch" patternUnits="userSpaceOnUse" width="5" height="5" patternTransform="rotate(45)">
            <rect width="5" height="5" fill="#fff7ed" />
            <line x1="0" y1="0" x2="0" y2="5" stroke="#b45309" strokeWidth="2.4" />
          </pattern>
        </defs>
        <rect width={W} height={height} fill="#ffffff" />
        <g transform={`translate(${tx} ${ty}) scale(${kx} ${k})`}>
          {p.cladeSpan !== null ? <path d={spanPath(tree, L, p.cladeSpan, 6 / k)} fill="#E9ED4C" opacity="0.28" data-testid="tree-clade-span" /> : null}
          <g fill="none" strokeLinecap="square">
            {edges.paths.map((e) => (
              <path key={e.c} d={e.d} stroke={e.c} strokeWidth={e.c === MIXED_COLOR ? 1.1 : 1.4} vectorEffect="non-scaling-stroke" />
            ))}
          </g>
          {edges.wedges.map((w) => (
            <path key={w.pre} d={w.d} fill={w.color} fillOpacity="0.55" stroke={w.color} strokeWidth="1" vectorEffect="non-scaling-stroke" data-testid="tree-collapsed" data-pre={w.pre} />
          ))}
        </g>

        {/* clade strip */}
        <g data-testid="clade-strip">
          {runs.map((r) => {
            const fail = p.failingGroups.has(r.key);
            const mid = (r.lo + r.hi) / 2;
            const big = rect ? (r.hi - r.lo) * k >= 13 : (r.hi - r.lo) * (stripR + STRIP_W) >= 16;
            const lx = rect ? stripX + STRIP_W + 4 : cx + (stripR + STRIP_W + 4) * Math.cos(mid);
            const ly = rect ? sy(mid) : cy + (stripR + STRIP_W + 4) * Math.sin(mid);
            const anchor = rect ? "start" : Math.cos(mid) >= 0 ? "start" : "end";
            return (
              <g key={r.key + r.lo} data-group={r.key}>
                <path d={runPath(r)} fill={fail ? "url(#tc-hatch)" : cladeScheme.color.get(r.key) ?? MIXED_COLOR} stroke={fail ? "#b45309" : "none"} strokeWidth="1">
                  <title>{r.key === OUTGROUP_KEY ? `Heliorhodopsin outgroup (${r.n} tips)` : `${r.key} (${r.n} tips)${fail ? " - legacy assignment; fails corrected support thresholds" : ""}`}</title>
                </path>
                {!showLabels && big && r.key !== "unclustered_backbone" ? (
                  <text x={lx} y={ly} fontSize="11" dominantBaseline="central" textAnchor={anchor} fill={fail ? "#8a3c04" : "#142238"} fontWeight={fail ? 700 : 600}>
                    {r.key === OUTGROUP_KEY ? "Outgroup" : shortGroup(r.key)}{fail ? " (legacy)" : ""}
                  </text>
                ) : null}
              </g>
            );
          })}
        </g>

        {/* leaders + tip labels */}
        {labels.length ? (
          <g fontSize={FONT} fill="#142238" data-testid="tree-tip-labels">
            {rect
              ? labels.map((l) => (
                  <line key={`ld${l.pre}`} x1={sx(L.collapseExtent.get(l.pre) ?? L.x[l.pre]) + 2} x2={stripX - 2} y1={l.y} y2={l.y} stroke="#c3ced9" strokeDasharray="1 2" />
                ))
              : null}
            {labels.map((l) => {
              const deg = (l.a * 180) / Math.PI;
              const flip = !rect && Math.cos(l.a) < 0;
              return (
                <text
                  key={l.pre}
                  data-pre={l.pre}
                  data-testid="tree-tip-label"
                  x={l.x}
                  y={l.y}
                  dominantBaseline="central"
                  textAnchor={flip ? "end" : "start"}
                  transform={rect ? undefined : `rotate(${flip ? deg + 180 : deg} ${l.x} ${l.y})`}
                  fontStyle={l.collapsed ? "italic" : undefined}
                  fontWeight={l.pre === tipRep || l.pre === p.selected ? 700 : 400}
                  className="cursor-pointer"
                >
                  {l.text}
                </text>
              );
            })}
          </g>
        ) : null}

        {/* placement best branch (dashed); position along the branch is not stored */}
        {placementSegs.map(({ q, rep }) => {
          const s = seg(rep!);
          if (!s) return null;
          return (
            <g key={`pl${q}`} data-testid="tree-placement-edge" data-pre={q} data-drawn-pre={rep}>
              <line {...s} stroke="#FF9400" strokeWidth="9" strokeOpacity="0.35" strokeLinecap="round" />
              <line {...s} stroke="#b45309" strokeWidth="3" strokeDasharray="6 4" strokeLinecap="round" />
            </g>
          );
        })}

        {/* selected lineage */}
        {lineage.length ? (
          <g data-testid="tree-lineage" stroke="#142238" strokeWidth="2.5" strokeLinecap="round">
            {lineage.map((q) => {
              const s = seg(q);
              return s ? <line key={q} {...s} /> : null;
            })}
          </g>
        ) : null}

        {/* support markers */}
        {supportMarks.length ? (
          <g data-testid="tree-support">
            {supportMarks.map((m) => (
              <g key={m.pre} data-pre={m.pre} data-support={m.label} data-meets={m.ok ? "1" : "0"}>
                <circle cx={m.x} cy={m.y} r={3.2} fill={m.ok ? "#142238" : "#ffffff"} stroke={m.ok ? "#142238" : "#b45309"} strokeWidth="1.3" />
                {showSupportText ? (
                  <text x={m.x - 4} y={m.y - 5} fontSize="9.5" textAnchor="end" fill={m.ok ? "#142238" : "#8a3c04"} paintOrder="stroke" stroke="#ffffff" strokeWidth="3">
                    {m.label}
                  </text>
                ) : null}
              </g>
            ))}
          </g>
        ) : null}

        {/* highlighted tip (search / ?tip=) */}
        {tipRep !== null && !Number.isNaN(L.x[tipRep]) ? (
          <circle data-testid="tree-highlight-tip" data-pre={p.tip!} cx={sx(L.x[tipRep])} cy={sy(L.y[tipRep])} r="6.5" fill="#E9ED4C" stroke="#142238" strokeWidth="2.2" pointerEvents="none" />
        ) : null}
        {p.selected !== null && !Number.isNaN(L.x[p.selected]) ? (
          <circle data-testid="tree-selected" data-pre={p.selected} cx={sx(L.x[p.selected])} cy={sy(L.y[p.selected])} r="5" fill="none" stroke="#0279EE" strokeWidth="2.5" pointerEvents="none" />
        ) : null}

        {/* hit targets */}
        <g fill="transparent" data-testid="tree-hits">
          {hits.map((h) => (
            <circle key={h.pre} data-pre={h.pre} cx={h.x} cy={h.y} r={tree.nodes[h.pre].isTip ? hitR : hitR + 1} className="cursor-pointer" />
          ))}
        </g>

        {/* scale bar */}
        <ScaleBar L={L} k={k} y={height - 12} />
      </svg>
    </div>
  );
});

function ScaleBar({ L, k, y }: { L: Layout; k: number; y: number }) {
  const prop = L.opts.branch === "prop";
  // pick a round length that is 40-120 px on screen
  const unitPx = L.scale * k;
  const cands = prop ? [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1, 2] : [1, 2, 5, 10, 20];
  const len = cands.find((c) => c * unitPx >= 40) ?? cands[cands.length - 1];
  const w = len * unitPx;
  return (
    <g transform={`translate(12 ${y})`} fontSize="11" fill="#526175" data-testid="tree-scale">
      <rect x="-6" y="-12" width={w + 150} height="20" fill="#ffffff" opacity="0.85" />
      <line x1="0" x2={w} y1="0" y2="0" stroke="#142238" strokeWidth="1.5" />
      <line x1="0" x2="0" y1="-4" y2="4" stroke="#142238" strokeWidth="1.5" />
      <line x1={w} x2={w} y1="-4" y2="4" stroke="#142238" strokeWidth="1.5" />
      <text x={w + 6} y="0" dominantBaseline="central">{prop ? `${len} substitutions/site` : `${len} branch${len === 1 ? "" : "es"} (uniform)`}</text>
    </g>
  );
}
