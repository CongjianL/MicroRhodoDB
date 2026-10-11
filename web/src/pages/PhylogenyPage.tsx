/**
 * #/phylogeny: interactive explorer for the 472-tip MR_RT_003 reference tree (PR-4).
 *
 * Data: phylogeny/MR_RT_003.rooted.treefile (frozen topology + branch lengths), phylogeny/explorer.json
 * (preorder-aligned node table with bipartition-mapped IQ-TREE run1 support, tip annotations, edge map)
 * and clades.json. Placements are loaded from the record JSON on demand (?placement=MRDB...).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { href } from "../app/routes";
import { pushHash, replaceHash } from "../app/navigation";
import { FlagBadge } from "../components/Badges";
import { CladeSupportNotice } from "../components/CladeSupportNotice";
import { Breadcrumbs, PageTitle } from "../components/common";
import { ErrorState, LoadingSkeleton } from "../components/States";
import { loadRecord, releaseFileUrl } from "../data/loaders";
import type { Clades, MrdbEntry } from "../data/types";
import { fmtInt } from "../lib/format";
import { thresholdText } from "../lib/summary";
import { downloadText } from "../features/entry/ui";
import {
  COLOR_MODES, buildColorScheme, collapsedAncestors, isDescendant, level1Mrcas, placementTargets, scopeScheme, searchTips, subcladeMrcas,
  type XTree,
} from "../features/tree/explorerModel";
import { Legend, NodeInfo, PlacementPanel, type PlacementInfo } from "../features/tree/ExplorerPanels";
import { parsePhyloQuery, phyloQueryString, type PhyloQuery } from "../features/tree/phyloQuery";
import { exportSvg } from "../features/tree/svgExport";
import { TreeCanvas, type TreeCanvasHandle } from "../features/tree/TreeCanvas";
import { useExplorerData } from "../features/tree/useExplorer";
import { safeExternalUrl } from "../lib/safe";

export default function PhylogenyPage({ params }: { params: URLSearchParams }) {
  const res = useExplorerData();
  return (
    <div className="container-page pt-6" data-testid="phylogeny-page">
      <PageTitle
        docTitle="Phylogeny - MicroRhodoDB"
        eyebrow={<>Reference tree <span className="font-mono">MR_RT_003</span> · release v1.6.0</>}
        lead={<>The 472-tip maximum-likelihood reference tree, rooted on 15 heliorhodopsin outgroup tips. Branch support is the SH-aLRT / UFBoot value of the same bipartition in the original IQ-TREE run; topology and branch lengths are those of the frozen rooted tree. EPA-ng placements are not tips: a placement is shown only as its best reference branch.</>}
      >
        Phylogeny
      </PageTitle>
      {res.state === "loading" ? <LoadingSkeleton label="Loading reference tree" /> : null}
      {res.state === "error" ? <ErrorState error={res.error} retry={res.retry} what="the reference tree" /> : null}
      {res.state === "ready" ? <Explorer tree={res.data.tree} clades={res.data.clades} params={params} /> : null}
    </div>
  );
}

function useCanvasHeight(): number {
  const get = () => (typeof window === "undefined" ? 640 : window.innerWidth < 640 ? 440 : window.innerWidth < 1024 ? 560 : 660);
  const [h, setH] = useState(get);
  useEffect(() => {
    const on = () => setH(get());
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return h;
}

function Explorer({ tree, clades, params }: { tree: XTree; clades: Clades; params: URLSearchParams }) {
  const q = useMemo(() => parsePhyloQuery(params, tree.nodes.length), [params, tree]);
  const nav = useCallback((patch: Partial<PhyloQuery>, replace = false) => {
    const h = href.phylogeny(phyloQueryString({ ...q, ...patch }));
    (replace ? replaceHash : pushHash)(h);
  }, [q]);

  const canvas = useRef<TreeCanvasHandle>(null);
  const height = useCanvasHeight();
  const [selected, setSelected] = useState<number | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [focus, setFocus] = useState<{ pre: number; nonce: number } | null>(null);
  const focusOn = useCallback((pre: number) => setFocus((f) => ({ pre, nonce: (f?.nonce ?? 0) + 1 })), []);

  const rootPre = tree.nodes[q.node] && !tree.nodes[q.node].isTip ? q.node : 0;
  const collapsed = useMemo(() => new Set(q.collapsed.filter((p) => tree.nodes[p] && !tree.nodes[p].isTip)), [q.collapsed, tree]);
  const opts = useMemo(() => ({ layout: q.layout, branch: q.bl, rootPre, collapsed }), [q.layout, q.bl, rootPre, collapsed]);
  const scheme = useMemo(() => buildColorScheme(tree, q.color), [tree, q.color]);
  const legendScheme = useMemo(() => scopeScheme(tree, scheme, rootPre), [tree, scheme, rootPre]);
  const cladeScheme = useMemo(() => buildColorScheme(tree, "clade"), [tree]);
  const failing = useMemo(() => clades.level1.filter((c) => !c.support_audit.iqtree_run1_meets_support_thresholds).map((c) => c.clade_id), [clades]);
  const failingSet = useMemo(() => new Set(failing), [failing]);
  const mrcas = useMemo(() => new Map([...level1Mrcas(tree), ...subcladeMrcas(tree)]), [tree]);

  // ?tip=
  const tipPre = q.tip ? tree.tipPre.get(q.tip) ?? null : null;
  const tipMissing = !!q.tip && tipPre === null;
  // ?clade=
  const cladePre = q.clade ? mrcas.get(q.clade) ?? null : null;
  // ?placement=
  const placement = usePlacement(tree, q.placement, q.src);
  const placementPre = placement !== "loading" && placement !== "error" && placement ? placement.targets : [];

  // Reveal targets hidden inside collapsed nodes; focus on the most specific target once per change.
  useEffect(() => {
    const target = tipPre ?? (placementPre.length ? placementPre[0] : null) ?? cladePre;
    if (target === null) return;
    const hidden = collapsedAncestors(tree, target, collapsed);
    if (hidden.length) {
      nav({ collapsed: q.collapsed.filter((c) => !hidden.includes(c)) }, true);
      return;
    }
    if (tipPre !== null) setSelected(tipPre);
    focusOn(target);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tipPre, cladePre, placementPre.join(","), rootPre]);

  const outside = [tipPre, cladePre, ...placementPre].filter((p): p is number => p !== null && !isDescendant(tree, p, rootPre));

  const actions = {
    subtree: (pre: number) => {
      setSelected(null);
      nav({ node: pre });
    },
    toggleCollapse: (pre: number) => nav({ collapsed: collapsed.has(pre) ? q.collapsed.filter((c) => c !== pre) : [...q.collapsed, pre] }),
    focus: focusOn,
    select: (pre: number) => setSelected(pre),
  };
  const shown = hover ?? selected;

  // breadcrumbs for the subtree view
  const crumbs = rootPre ? [{ label: "Whole tree", href: href.phylogeny(phyloQueryString({ ...q, node: 0 })) }, { label: `Subtree pre ${rootPre} (${tree.nodes[rootPre].nTips} tips)` }] : null;
  const derived = tree.ex.meta.derived_newick;
  const [svgBusy, setSvgBusy] = useState<string | null>(null);
  const exportName = `MR_RT_003_${q.layout}_${q.color}${rootPre ? `_pre${rootPre}` : ""}`;
  const doExport = (kind: "svg" | "png") => {
    const { svg, width, height: h } = exportSvg(tree, {
      opts, scheme: legendScheme, cladeScheme, failingGroups: failingSet, support: { show: q.support, sh: q.sh, uf: q.uf }, tip: tipPre, placement: placementPre,
      title: `MicroRhodoDB v1.6.0 · MR_RT_003 reference tree${rootPre ? ` · subtree pre ${rootPre}` : ""}`,
      provenance: [
        `Topology and branch lengths: ${tree.ex.meta.frozen_treefile.path} (sha256 ${tree.ex.meta.frozen_treefile.sha256.slice(0, 16)}...). Colour: ${COLOR_MODES.find((m) => m.id === q.color)!.label}. Layout: ${q.layout}, ${q.bl === "prop" ? "proportional" : "uniform"} branch lengths.`,
        `Support (when shown): IQ-TREE run1 SH-aLRT/UFBoot mapped by bipartition (${tree.ex.meta.support_source.path}); rooted-file labels not used.`,
        failing.length ? `Hatched: ${failing.join(", ")} retained as legacy v1.6.0 assignment; corrected support fails ${thresholdText(clades)}.` : "",
        "Exported from the MicroRhodoDB website explorer (figure; not a data file).",
      ].filter(Boolean),
    });
    if (kind === "svg") {
      downloadText(`${exportName}.svg`, svg, "image/svg+xml");
      return;
    }
    setSvgBusy("png");
    const img = new Image();
    const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
    img.onload = () => {
      const scale = Math.min(2, 16000 / Math.max(width, h));
      const c = document.createElement("canvas");
      c.width = Math.round(width * scale);
      c.height = Math.round(h * scale);
      const ctx = c.getContext("2d")!;
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, c.width, c.height);
      ctx.drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      c.toBlob((b) => {
        setSvgBusy(null);
        if (!b) return;
        const a = document.createElement("a");
        a.href = URL.createObjectURL(b);
        a.download = `${exportName}.png`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      }, "image/png");
    };
    img.onerror = () => {
      setSvgBusy(null);
      URL.revokeObjectURL(url);
    };
    img.src = url;
  };

  return (
    <>
      {failing.length ? <div className="mb-4 max-w-4xl"><CladeSupportNotice clades={clades} compact /></div> : null}

      <Toolbar tree={tree} q={q} nav={nav} canvas={canvas} onPick={(acc) => nav({ tip: acc, node: isDescendant(tree, tree.tipPre.get(acc)!, rootPre) ? q.node : 0 })} collapseAll={() => nav({ collapsed: [...level1Mrcas(tree).values()].sort((a, b) => a - b) })} />

      {crumbs ? <Breadcrumbs items={crumbs} /> : null}
      {tipMissing ? <p className="mb-2 text-sm text-[#8a3c04]" data-testid="tip-missing">Tip <span className="font-mono">{q.tip}</span> is not a tip of MR_RT_003. Placed records are not tips; use the record's placement link instead.</p> : null}
      {outside.length ? (
        <p className="mb-2 text-sm text-[#8a3c04]" data-testid="target-outside">The highlighted target lies outside this subtree. <a href={href.phylogeny(phyloQueryString({ ...q, node: 0 }))}>Show the whole tree</a>.</p>
      ) : null}

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_21rem]">
        <div className="min-w-0">
          <TreeCanvas
            ref={canvas}
            tree={tree}
            opts={opts}
            scheme={scheme}
            cladeScheme={cladeScheme}
            failingGroups={failingSet}
            support={{ show: q.support, sh: q.sh, uf: q.uf }}
            selected={selected}
            tip={tipPre}
            placement={placementPre}
            cladeSpan={cladePre}
            focus={focus}
            height={height}
            onSelect={setSelected}
            onHover={setHover}
            describedBy="tree-text-alt"
            label={`MR_RT_003 reference tree, ${q.layout === "rect" ? "rectangular" : "radial"} layout, ${tree.nodes[rootPre].nTips} tips shown. Use plus and minus to zoom, arrow keys to pan, 0 to reset.`}
          />
          <p className="mt-1 text-xs text-ink-2">Click a node or tip for details. Drag to pan. Zoom with the buttons, or click the tree and use the mouse wheel or + / - keys; arrow keys pan, 0 resets. Tip labels appear when zoomed in far enough. The coloured strip marks level-1 clades and backbone groups.</p>
          <p id="tree-text-alt" className="mt-1 text-xs text-ink-2" data-testid="tree-text-alt">Text alternative: find any tip with the tip search above; the <button type="button" className="text-accent underline underline-offset-2" onClick={() => { const h = document.getElementById("ce-h"); h?.scrollIntoView(); h?.focus(); }}>Clade Explorer table</button> lists every level-1 clade and backbone group with tip counts, support and record counts; each clade page lists its reference tips in tree order with links to Protein Entries; the Newick trees are under Downloads below.</p>
        </div>
        <aside className="space-y-3" aria-label="Tree details">
          {q.placement ? <PlacementPanel tree={tree} info={placement ?? "loading"} mrdb={q.placement} onFocus={focusOn} /> : null}
          <div className="card p-3" data-testid="info-panel" aria-live="polite">
            {shown !== null ? (
              <NodeInfo tree={tree} pre={shown} q={q} clades={clades} collapsed={collapsed} actions={actions} hover={hover !== null && hover !== selected} />
            ) : (
              <p className="text-sm text-ink-2" data-testid="info-empty">Select a node or tip to see its support, annotations and links. {fmtInt(tree.ex.n_tips)} tips, {fmtInt(tree.ex.n_internal_incl_root)} internal nodes.</p>
            )}
          </div>
          <Legend scheme={legendScheme} failing={failing} support={{ show: q.support, sh: q.sh, uf: q.uf }} placement={placementPre.length > 0} />
        </aside>
      </div>

      <CladeTable tree={tree} clades={clades} q={q} />
      <Provenance tree={tree} clades={clades} />

      <section className="mt-8" aria-labelledby="dl-h" data-testid="tree-downloads">
        <h2 id="dl-h" className="text-xl">Downloads</h2>
        <ul className="mt-3 grid grid-cols-[minmax(0,1fr)] gap-3 [overflow-wrap:anywhere] md:grid-cols-2">
          <DlItem file={tree.ex.meta.frozen_treefile.web_file} name="MR_RT_003.rooted.treefile" testId="dl-original" title="Original rooted Newick (frozen, unmodified)">
            Byte-identical copy of <code>{tree.ex.meta.frozen_treefile.path}</code> (sha256 <code className="break-all">{tree.ex.meta.frozen_treefile.sha256}</code>). Its internal labels are not authoritative: {tree.ex.meta.n_label_disagreements} are attached to the wrong bipartition after rerooting.
          </DlItem>
          <DlItem file={tree.ex.meta.support_source.web_file} name="run1.treefile" testId="dl-run1" title="IQ-TREE run1 tree (support source, unrooted)">
            Byte-identical copy of <code>{tree.ex.meta.support_source.path}</code> (sha256 <code className="break-all">{tree.ex.meta.support_source.sha256}</code>), the source of all displayed support values.
          </DlItem>
          <DlItem file={derived.web_file} name={derived.web_file.split("/").pop()!} testId="dl-derived" title={<>Rooted Newick with corrected support <FlagBadge tone="warn">DERIVED</FlagBadge></>}>
            Frozen topology and branch lengths with internal labels replaced by the run1 label of the same bipartition ({derived.n_labels_changed} labels differ from the frozen file). Generated by the website exporter; not a release file. See the <ReadmeLink file={derived.readme} /> (sha256 <code className="break-all">{derived.sha256}</code>).
          </DlItem>
          <li className="card p-3" data-testid="dl-figure">
            <h3 className="text-base">Figure of the current view</h3>
            <p className="mt-1 text-sm text-ink-2">Current layout, colouring, subtree, collapsed nodes, support and highlights, with all tips labelled, a legend and provenance.</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => doExport("svg")} data-testid="dl-svg">Download SVG</button>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => doExport("png")} disabled={svgBusy === "png"} data-testid="dl-png">{svgBusy === "png" ? "Rendering PNG" : "Download PNG"}</button>
            </div>
          </li>
        </ul>
      </section>
    </>
  );
}

function useReleaseUrl(file: string): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    void releaseFileUrl(file).then((u) => alive && setUrl(u));
    return () => {
      alive = false;
    };
  }, [file]);
  return url;
}

function ReadmeLink({ file }: { file: string }) {
  const url = useReleaseUrl(file);
  return <a href={safeExternalUrl(url)} target="_blank" rel="noopener noreferrer" data-testid="dl-derived-readme">README<span className="sr-only"> (opens in a new tab)</span></a>;
}

function DlItem({ file, name, title, children, testId }: { file: string; name: string; title: React.ReactNode; children: React.ReactNode; testId: string }) {
  const url = useReleaseUrl(file);
  return (
    <li className="card p-3" data-testid={testId}>
      <h3 className="text-base">{title}</h3>
      <p className="mt-1 text-sm text-ink-2">{children}</p>
      {url ? <a className="btn btn-secondary btn-sm mt-2" href={url} download={name} data-testid={`${testId}-link`}>Download {name}</a> : null}
    </li>
  );
}

function usePlacement(tree: XTree, mrdb: string | null, src: string | null): PlacementInfo | "loading" | "error" | null {
  const [st, setSt] = useState<PlacementInfo | "loading" | "error" | null>(null);
  useEffect(() => {
    if (!mrdb) {
      setSt(null);
      return;
    }
    let alive = true;
    setSt("loading");
    loadRecord(mrdb).then(
      (entry: MrdbEntry | null) => {
        if (!alive) return;
        if (!entry) return setSt({ entry: null, sourceAcc: null, edge: null, targets: [], placement: null, isTip: false });
        const s = entry.sources.find((x) => x.source_acc === src) ?? entry.sources.find((x) => x.source_acc === entry.representative_source_acc) ?? entry.sources[0];
        const ph = s.phylogeny;
        const pl = (ph.placement ?? null) as Record<string, unknown> | null;
        const edge = pl ? ((pl.best_edge as string | null) ?? null) : null;
        setSt({ entry, sourceAcc: s.source_acc, edge, targets: placementTargets(tree, edge), placement: pl, isTip: ph.is_reference_tip });
      },
      () => alive && setSt("error"),
    );
    return () => {
      alive = false;
    };
  }, [tree, mrdb, src]);
  return st;
}

/* ---------------------------------------------------------------- toolbar */

function Toolbar({ tree, q, nav, canvas, onPick, collapseAll }: {
  tree: XTree;
  q: PhyloQuery;
  nav: (p: Partial<PhyloQuery>, replace?: boolean) => void;
  canvas: React.RefObject<TreeCanvasHandle | null>;
  onPick: (acc: string) => void;
  collapseAll: () => void;
}) {
  const [term, setTerm] = useState("");
  const hits = useMemo(() => searchTips(tree, term, 12), [tree, term]);
  const seg = (active: boolean) => `btn btn-sm ${active ? "btn-primary" : "btn-secondary"}`;
  return (
    <div className="card mb-3 flex flex-wrap items-end gap-x-5 gap-y-3 p-3" data-testid="tree-toolbar">
      <fieldset>
        <legend className="field-label">Layout</legend>
        <div className="flex gap-1" role="group">
          <button type="button" className={seg(q.layout === "rect")} aria-pressed={q.layout === "rect"} onClick={() => nav({ layout: "rect" })} data-testid="layout-rect">Rectangular</button>
          <button type="button" className={seg(q.layout === "radial")} aria-pressed={q.layout === "radial"} onClick={() => nav({ layout: "radial" })} data-testid="layout-radial">Radial</button>
        </div>
      </fieldset>
      <fieldset>
        <legend className="field-label">Branch lengths</legend>
        <div className="flex gap-1" role="group">
          <button type="button" className={seg(q.bl === "prop")} aria-pressed={q.bl === "prop"} onClick={() => nav({ bl: "prop" })} data-testid="bl-prop">Proportional</button>
          <button type="button" className={seg(q.bl === "uniform")} aria-pressed={q.bl === "uniform"} onClick={() => nav({ bl: "uniform" })} data-testid="bl-uniform">Uniform</button>
        </div>
      </fieldset>
      <div>
        <label className="field-label" htmlFor="tree-color">Colour by</label>
        <select id="tree-color" className="field" value={q.color} onChange={(e) => nav({ color: e.target.value as PhyloQuery["color"] })} data-testid="tree-color">
          {COLOR_MODES.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
        </select>
      </div>
      <fieldset className="flex flex-wrap items-end gap-2">
        <legend className="field-label">Support</legend>
        <label className="inline-flex min-h-10 items-center gap-2 text-sm">
          <input type="checkbox" checked={q.support} onChange={(e) => nav({ support: e.target.checked })} data-testid="support-toggle" /> Show
        </label>
        <label className="text-sm">
          <span className="sr-only">SH-aLRT threshold</span>SH-aLRT &ge;
          <input type="number" min={0} max={100} step={1} className="field ml-1 inline-block w-20" value={q.sh} onChange={(e) => nav({ sh: Number(e.target.value) }, true)} data-testid="support-sh" />
        </label>
        <label className="text-sm">
          <span className="sr-only">UFBoot threshold</span>UFBoot &ge;
          <input type="number" min={0} max={100} step={1} className="field ml-1 inline-block w-20" value={q.uf} onChange={(e) => nav({ uf: Number(e.target.value) }, true)} data-testid="support-uf" />
        </label>
      </fieldset>
      <div className="relative min-w-[14rem] flex-1">
        <label className="field-label" htmlFor="tree-search">Find tip</label>
        <input
          id="tree-search"
          className="field"
          placeholder="Accession, MRDB, organism, protein"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && hits.length) {
              onPick(hits[0].acc);
              setTerm("");
            }
          }}
          autoComplete="off"
          aria-controls={term.trim().length >= 2 ? "tree-search-results" : undefined}
          data-testid="tree-search"
        />
        {term.trim().length >= 2 ? (
          <ul id="tree-search-results" className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-md border border-line-strong bg-surface shadow-lg" data-testid="tree-search-results">
            {hits.length ? hits.map((h) => (
              <li key={h.acc}>
                <button type="button" className="block w-full px-3 py-1.5 text-left text-sm hover:bg-subtle" onClick={() => { onPick(h.acc); setTerm(""); }}>
                  {h.label}
                </button>
              </li>
            )) : <li className="px-3 py-1.5 text-sm text-ink-2">No reference tip matches. Placed records are not tips.</li>}
          </ul>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-1">
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => canvas.current?.zoom(1.5)} aria-label="Zoom in" data-testid="zoom-in">+</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => canvas.current?.zoom(1 / 1.5)} aria-label="Zoom out" data-testid="zoom-out">&minus;</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => canvas.current?.reset()} data-testid="zoom-reset">Reset view</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={collapseAll} data-testid="collapse-all">Collapse clades</button>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => nav({ collapsed: [] })} disabled={!q.collapsed.length} data-testid="expand-all">Expand all</button>
        {q.tip || q.clade || q.placement || q.node ? (
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => nav({ tip: null, clade: null, placement: null, src: null, node: 0 })} data-testid="clear-targets">Clear highlights</button>
        ) : null}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- clade table */

function CladeTable({ tree, clades, q }: { tree: XTree; clades: Clades; q: PhyloQuery }) {
  const mrca = level1Mrcas(tree);
  return (
    <section className="mt-8" aria-labelledby="ce-h" data-testid="clade-explorer">
      <h2 id="ce-h" className="text-xl" tabIndex={-1}>Clade Explorer</h2>
      <p className="mt-1 max-w-4xl text-sm text-ink-2">
        {clades.level1.filter((c) => c.kind === "clade").length} level-1 clades and {clades.level1.filter((c) => c.kind === "backbone_group").length} backbone groups (scheme {clades.scheme}). Support: corrected IQ-TREE run1 values; thresholds {thresholdText(clades)}. Memberships are those of v1.6.0 and are not re-derived here.
      </p>
      <div className="mt-3 overflow-x-auto rounded-md border border-line">
        <table className="data-table">
          <thead>
            <tr>
              <th>Group</th><th>Name</th><th className="num">Tips</th><th>Support (run1)</th><th className="num">Records (confident / tentative)</th><th>Function consensus</th><th>Tree</th>
            </tr>
          </thead>
          <tbody>
            {clades.level1.map((c) => {
              const ok = c.support_audit.iqtree_run1_meets_support_thresholds;
              return (
                <tr key={c.clade_id} data-testid={`ce-row-${c.clade_id}`}>
                  <td className="whitespace-nowrap"><a href={href.clade(c.clade_id)} className="font-mono">{c.clade_id}</a>{c.kind === "backbone_group" ? <span className="block text-xs text-ink-2">backbone group</span> : null}</td>
                  <td className="min-w-[14rem]">{c.name ?? <span className="text-ink-2">Unnamed</span>}</td>
                  <td className="num">{c.n_tips_in_tree}</td>
                  <td className="whitespace-nowrap">{c.support_audit.iqtree_run1_sh_alrt} / {c.support_audit.iqtree_run1_ufboot} {ok ? null : <FlagBadge tone="warn">legacy; fails</FlagBadge>}</td>
                  <td className="num">{fmtInt(c.n_records_confident)} / {fmtInt(c.n_records_tentative)}</td>
                  <td>{c.function_consensus.clade_function ?? <span className="text-ink-2">none</span>} <span className="text-xs text-ink-2">({c.function_consensus.consensus_status})</span></td>
                  <td className="whitespace-nowrap">
                    <a href={href.phylogeny(phyloQueryString({ ...q, clade: c.clade_id, tip: null, placement: null, node: 0 }))}>Highlight</a>
                    {" · "}
                    <a href={href.phylogeny(phyloQueryString({ ...q, clade: c.clade_id, tip: null, placement: null, node: mrca.get(c.clade_id) ?? 0 }))}>Subtree</a>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/* ---------------------------------------------------------------- provenance */

function Provenance({ tree, clades }: { tree: XTree; clades: Clades }) {
  const m = tree.ex.meta;
  const roles = Object.entries(m.tip_roles);
  return (
    <section className="mt-8" aria-labelledby="prov-h" data-testid="tree-provenance">
      <h2 id="prov-h" className="text-xl">Tree metadata and provenance</h2>
      <dl className="card mt-3 grid grid-cols-[minmax(0,1fr)] gap-x-4 gap-y-2 p-4 text-sm [overflow-wrap:anywhere] md:grid-cols-[14rem_minmax(0,1fr)]">
        <dt className="text-ink-2">Tree</dt><dd><span className="font-mono">{m.tree_id}</span> ({m.status}; release run {m.release_run}); {tree.ex.n_tips} tips, {tree.ex.n_internal_incl_root} internal nodes incl. root.</dd>
        <dt className="text-ink-2">Inference</dt><dd>{m.method}; model {m.model}; log-likelihood (run1) {m.log_likelihood_run1}.</dd>
        <dt className="text-ink-2">Tips</dt><dd>{roles.map(([k, n]) => `${n} ${k}`).join(", ")}. {m.reference_tree_note}</dd>
        <dt className="text-ink-2">Rooting</dt><dd>{m.rooting}. {m.root_split_rule}</dd>
        <dt className="text-ink-2">Support shown</dt><dd data-testid="prov-support-rule">{m.support_display_rule}</dd>
        <dt className="text-ink-2">Clade rule</dt><dd>Level 1: {thresholdText(clades)}. Clade definitions and memberships are fixed v1.6.0 values; the explorer does not re-derive them.</dd>
        <dt className="text-ink-2">Placements</dt><dd>{m.placement_rule} Current placements by clade_call_qc: {Object.entries(m.placement_status_counts).map(([k, n]) => `${k} ${fmtInt(n)}`).join(", ")}.</dd>
        <dt className="text-ink-2">Known issues</dt>
        <dd>
          <ul className="list-disc pl-5" data-testid="prov-issues">
            <li>{m.n_label_disagreements} internal labels in the frozen rooted file are attached to a different bipartition (rerooting artefact); they are kept as audit fields only.</li>
            {clades.level1.filter((c) => !c.support_audit.iqtree_run1_meets_support_thresholds).map((c) => (
              <li key={c.clade_id}><span className="font-mono">{c.clade_id}</span>: corrected support {c.support_audit.iqtree_run1_label} fails the clade thresholds; the database stores {c.support_audit.db_label}. Retained as a legacy assignment.</li>
            ))}
            <li>{m.db_edge_length_note.replace("this value", String(m.db_edge_length_max_abs_diff))}</li>
          </ul>
        </dd>
        <dt className="text-ink-2">Files</dt>
        <dd>Topology: <code>{m.frozen_treefile.path}</code>; support: <code>{m.support_source.path}</code> (md5 <code>{m.support_source.md5}</code>).</dd>
      </dl>
    </section>
  );
}
