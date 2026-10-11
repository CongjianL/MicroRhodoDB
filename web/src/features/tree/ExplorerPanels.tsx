/** Side panels of the phylogeny explorer: node/tip information, placement details, legend. */
import { href } from "../../app/routes";
import { FlagBadge } from "../../components/Badges";
import type { Clades, MrdbEntry } from "../../data/types";
import { CLADE_STATE_LABEL, FUNC_LABEL } from "../../lib/format";
import {
  MIXED_COLOR, OUTGROUP_KEY, fmtSupport, meetsThresholds, supportOf, tipInfo, tipRoleLabel,
  type ColorScheme, type XTree,
} from "./explorerModel";
import { phyloQueryString, type PhyloQuery } from "./phyloQuery";

const dash = <span className="text-ink-2">Not recorded</span>;
const v = (x: React.ReactNode) => (x === null || x === undefined || x === "" ? dash : x);

function KV({ k, children, testId }: { k: string; children: React.ReactNode; testId?: string }) {
  return (
    <div className="grid grid-cols-[8.5rem_minmax(0,1fr)] gap-2 border-b border-line py-1.5 text-sm last:border-b-0" data-testid={testId}>
      <dt className="text-ink-2">{k}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

export interface NodeActions {
  subtree: (pre: number) => void;
  toggleCollapse: (pre: number) => void;
  focus: (pre: number) => void;
  select: (pre: number) => void;
}

export function NodeInfo({ tree, pre, q, clades, collapsed, actions, hover }: {
  tree: XTree;
  pre: number;
  q: PhyloQuery;
  clades: Clades;
  collapsed: ReadonlySet<number>;
  actions: NodeActions;
  hover: boolean;
}) {
  const n = tree.nodes[pre];
  if (n.isTip) {
    const t = tipInfo(tree, pre)!;
    const group = t.level1 ?? t.backbone_group;
    return (
      <div data-testid="info-tip" data-pre={pre} data-acc={n.name}>
        <h3 className="text-base"><span className="font-mono">{n.name}</span> <span className="text-sm font-normal text-ink-2">reference tip</span></h3>
        {hover ? <p className="text-xs text-ink-2">Hovering. Click to keep this panel.</p> : null}
        <dl className="mt-2">
          <KV k="Protein Entry" testId="info-entry">
            {t.mrdb_acc ? <a href={href.record(t.mrdb_acc)} data-testid="info-entry-link">{t.mrdb_acc}</a> : <span>None: this tip is <strong>not in the v1.6.0 corpus</strong></span>}
          </KV>
          <KV k="Protein">{v(t.protein_name)}</KV>
          <KV k="Organism">{v(t.organism ? <i>{t.organism}</i> : null)}</KV>
          <KV k="Tip role">{tipRoleLabel(t.tip_role)} <code className="text-xs text-ink-2">{t.tip_role}</code></KV>
          <KV k="Level-1 group">
            {group ? <a href={href.clade(group)}>{group}</a> : t.tip_role === "outgroup_heliorhodopsin" ? "Heliorhodopsin outgroup" : t.unclustered_backbone ? "None (backbone tip, unclustered)" : dash}
          </KV>
          <KV k="Subclade">{t.subclade ? <a href={href.clade(t.subclade)}>{t.subclade}</a> : <span className="text-ink-2">None</span>}</KV>
          <KV k="Clade state">{t.clade_state ? <>{CLADE_STATE_LABEL[t.clade_state]} <code className="text-xs text-ink-2">{t.clade_state}</code></> : <span className="text-ink-2">No record (not in corpus)</span>}</KV>
          <KV k="Taxonomy">{v([t.tax_domain, t.phylum].filter(Boolean).join(" / "))}</KV>
          <KV k="Function (v1.6.0)">{t.func_class ? <>{FUNC_LABEL[t.func_class as keyof typeof FUNC_LABEL] ?? t.func_class} <code className="text-xs text-ink-2">{t.func_class}</code></> : dash}</KV>
          <KV k="Evidence">{v(t.evidence_level)}</KV>
          <KV k="Helix-C motif">{v(t.helixC_motif ? <span className="font-mono">{t.helixC_motif}</span> : null)}</KV>
          <KV k="v1.4 tip annotation">{v([t.func_class_v14, t.subfamily_v14].filter(Boolean).join(" / "))}</KV>
          <KV k="Branch length">{n.length.toFixed(6)}</KV>
        </dl>
        <p className="mt-1 text-xs text-ink-2">Annotation source: {t.annotation_source}.</p>
        <div className="mt-2 flex flex-wrap gap-2">
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => actions.focus(pre)}>Zoom to tip</button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => actions.select(n.parent)}>Parent node</button>
        </div>
      </div>
    );
  }
  const e = tree.info.get(pre)!;
  const s = supportOf(tree, pre);
  const split = tree.ex.root_split;
  const isCollapsed = collapsed.has(pre);
  const level1 = e.clade_mrca.map((id) => clades.level1.find((c) => c.clade_id === id)).filter(Boolean);
  return (
    <div data-testid="info-node" data-pre={pre}>
      <h3 className="text-base">{e.is_root ? "Root" : "Internal node"} <span className="text-sm font-normal text-ink-2">pre {pre} · {n.nTips} tips</span></h3>
      {hover ? <p className="text-xs text-ink-2">Hovering. Click to keep this panel.</p> : null}
      <dl className="mt-2">
        <KV k="Support (run1)" testId="info-support">
          {s ? (
            <>
              SH-aLRT {fmtSupport(s.sh)} / UFBoot {fmtSupport(s.uf)}{" "}
              {meetsThresholds(s, q.sh, q.uf) ? <FlagBadge tone="info">meets {q.sh}/{q.uf}</FlagBadge> : <FlagBadge tone="warn">below {q.sh}/{q.uf}</FlagBadge>}
              {e.root_split_shared ? <span className="mt-1 block text-xs text-ink-2">Root split: this value belongs to the outgroup | ingroup bipartition and is shown once, on the outgroup branch.</span> : null}
            </>
          ) : e.is_root ? (
            <span className="text-ink-2">None: the root has no branch above it.</span>
          ) : e.root_split_shared ? (
            <span className="text-ink-2" data-testid="info-root-split">Root split: support {split.run1_label} is shown on the outgroup branch (pre {split.displayed_on}); both root branches are one bipartition.</span>
          ) : (
            <span className="text-ink-2">Not available</span>
          )}
        </KV>
        <KV k="Rooted-file label" testId="info-rooted-label">
          {e.rooted_label ?? <span className="text-ink-2">None</span>}{" "}
          {e.label_agrees ? <span className="text-xs text-ink-2">(agrees with run1)</span> : (
            <span className="mt-1 block text-xs text-[#8a3c04]" data-testid="info-label-discrepancy">
              Audit only: in the frozen rooted file this label is attached to a different bipartition (one of {tree.ex.meta.n_label_disagreements} rerooting discrepancies). It is not displayed as support.
            </span>
          )}
        </KV>
        {e.clade_mrca.length || e.subclade_mrca.length ? (
          <KV k="MRCA of">
            {[...e.clade_mrca, ...e.subclade_mrca].map((id) => <a key={id} href={href.clade(id)} className="mr-2 font-mono">{id}</a>)}
            {level1.some((c) => c && !c.support_audit.iqtree_run1_meets_support_thresholds) ? <FlagBadge tone="warn">legacy assignment</FlagBadge> : null}
          </KV>
        ) : null}
        <KV k="Branch length">{e.length === null ? <span className="text-ink-2">None (root)</span> : e.length.toFixed(6)}</KV>
        <KV k="Tip span">{e.first_tip} … {e.last_tip}</KV>
      </dl>
      <div className="mt-2 flex flex-wrap gap-2">
        {pre !== q.node ? <button type="button" className="btn btn-secondary btn-sm" onClick={() => actions.subtree(pre)} data-testid="info-subtree">View subtree</button> : null}
        {!e.is_root && pre !== q.node ? <button type="button" className="btn btn-secondary btn-sm" onClick={() => actions.toggleCollapse(pre)} data-testid="info-collapse">{isCollapsed ? "Expand" : "Collapse"}</button> : null}
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => actions.focus(pre)}>Zoom to node</button>
        {n.parent >= 0 ? <button type="button" className="btn btn-secondary btn-sm" onClick={() => actions.select(n.parent)}>Parent</button> : null}
        {n.children.map((c, i) => <button key={c} type="button" className="btn btn-secondary btn-sm" onClick={() => actions.select(c)}>Child {i + 1}</button>)}
      </div>
    </div>
  );
}

export interface PlacementInfo {
  entry: MrdbEntry | null;
  sourceAcc: string | null;
  edge: string | null;
  targets: number[];
  placement: Record<string, unknown> | null;
  isTip: boolean;
}

const PL_FIELDS: [string, string][] = [
  ["best_edge", "Best edge"], ["best_lwr", "Best LWR"], ["n_credible95", "Edges in 95% credible set"], ["best_pendant", "Pendant length (best)"],
  ["lwr_weighted_pendant", "Pendant length (LWR-weighted)"], ["placement_qc", "Placement QC"], ["clade_id", "Clade (placement)"], ["clade_lwr", "Clade LWR"],
  ["clade_call", "Clade call"], ["clade_call_qc", "Clade call QC"], ["subclade_id", "Subclade (placement)"], ["subclade_lwr", "Subclade LWR"],
  ["subclade_call", "Subclade call"], ["model_tag", "Model"], ["track", "Track"],
];

export function PlacementPanel({ tree, info, mrdb, onFocus }: { tree: XTree; info: PlacementInfo | "loading" | "error"; mrdb: string; onFocus: (pre: number) => void }) {
  return (
    <div className="card p-3" data-testid="placement-panel">
      <h3 className="text-base">Placement of <a href={href.record(mrdb)} className="font-mono">{mrdb}</a></h3>
      {info === "loading" ? <p className="text-sm text-ink-2">Loading record…</p> : null}
      {info === "error" ? <p className="text-sm text-[#8a3c04]">The record could not be loaded.</p> : null}
      {info !== "loading" && info !== "error" ? (
        !info.entry ? (
          <p className="text-sm text-[#8a3c04]" data-testid="placement-missing">No record {mrdb} in v1.6.0.</p>
        ) : info.isTip ? (
          <p className="text-sm" data-testid="placement-is-tip">Source <span className="font-mono">{info.sourceAcc}</span> is itself a reference tip, so it has no placement. <a href={href.phylogeny(phyloQueryString({ tip: info.sourceAcc }))}>Show the tip</a>.</p>
        ) : !info.placement ? (
          <p className="text-sm text-ink-2" data-testid="placement-none">No placement is recorded for source <span className="font-mono">{info.sourceAcc}</span>.</p>
        ) : (
          <>
            <p className="text-sm">Source <span className="font-mono">{info.sourceAcc}</span>. EPA-ng placement on the fixed reference tree; it is <strong>not a tip</strong>.</p>
            <dl className="mt-1" data-testid="placement-fields">
              {PL_FIELDS.filter(([k]) => info.placement![k] !== undefined).map(([k, label]) => (
                <KV key={k} k={label} testId={`pl-${k}`}>{info.placement![k] === null ? <span className="text-ink-2">null</span> : <code className="text-xs">{String(info.placement![k])}</code>}</KV>
              ))}
            </dl>
            {info.targets.length ? (
              <p className="mt-2 text-xs text-ink-2" data-testid="placement-targets">
                Highlighted: the whole reference branch {info.edge} (rooted node{info.targets.length > 1 ? "s" : ""} pre {info.targets.join(" and ")}).
                {info.targets.length > 1 ? " This edge is the root split, drawn as the two root branches." : ""} The position along the branch is not stored in v1.6.0 and is not drawn.
              </p>
            ) : (
              <p className="mt-2 text-xs text-[#8a3c04]" data-testid="placement-unmapped">Best edge {info.edge ?? "(none)"} is not in the edge map; nothing is highlighted.</p>
            )}
            {info.targets.length ? <button type="button" className="btn btn-secondary btn-sm mt-2" onClick={() => onFocus(info.targets[0])}>Zoom to branch</button> : null}
          </>
        )
      ) : null}
      <p className="mt-2 text-xs text-ink-2">{tree.ex.meta.placement_rule}</p>
    </div>
  );
}

export function Legend({ scheme, failing, support, placement }: { scheme: ColorScheme; failing: string[]; support: { show: boolean; sh: number; uf: number }; placement: boolean }) {
  const ingroup = scheme.entries.filter((e) => e.nIngroup > 0 && e.key !== OUTGROUP_KEY);
  const outgroup = scheme.entries.filter((e) => e.nOutgroup > 0);
  const nOut = outgroup.reduce((s, e) => s + e.nOutgroup, 0);
  const sw = (c: string, extra = "") => <span aria-hidden="true" className={`inline-block h-3 w-3 shrink-0 rounded-sm border border-line-strong ${extra}`} style={{ background: c }} />;
  return (
    <div className="card p-3 text-sm" data-testid="tree-legend" data-mode={scheme.mode}>
      <h3 className="text-base">Legend</h3>
      <p className="mt-1 text-xs font-semibold uppercase tracking-wide text-ink-2">Ingroup tips</p>
      <ul className="mt-1 space-y-0.5" data-testid="legend-ingroup">
        {ingroup.map((e) => (
          <li key={e.key} className="flex items-center gap-2" data-key={e.key}>
            {sw(e.color)} <span className="min-w-0 flex-1 truncate" title={e.key}>{e.label}{failing.includes(e.key) ? " (legacy)" : ""}</span> <span className="tabular-nums text-ink-2">{e.nIngroup}</span>
          </li>
        ))}
      </ul>
      {nOut > 0 ? (
        <>
        <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-ink-2" data-testid="legend-outgroup-title">Heliorhodopsin outgroup ({nOut} tips)</p>
        <ul className="mt-1 space-y-0.5" data-testid="legend-outgroup">
          {outgroup.map((e) => (
            <li key={e.key} className="flex items-center gap-2" data-key={e.key}>
              {sw(e.color)} <span className="min-w-0 flex-1 truncate">{e.label}</span> <span className="tabular-nums text-ink-2">{e.nOutgroup}</span>
            </li>
          ))}
        </ul>
        <p className="mt-1 text-xs text-ink-2">The outgroup roots the tree; it is not a MicroRhodoDB type-I clade.</p>
        </>
      ) : null}
      <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-ink-2">Symbols</p>
      <ul className="mt-1 space-y-0.5 text-xs">
        <li className="flex items-center gap-2">{sw(MIXED_COLOR)} Branch with mixed descendants</li>
        {failing.length ? <li className="flex items-center gap-2"><span aria-hidden="true" className="inline-block h-3 w-3 border border-[#b45309] bg-[repeating-linear-gradient(45deg,#b45309_0_2px,#fff7ed_2px_4px)]" /> Clade strip: legacy assignment failing corrected support ({failing.join(", ")})</li> : null}
        {support.show ? (
          <>
            <li className="flex items-center gap-2"><span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-full bg-ink" /> Support meets SH-aLRT &ge; {support.sh} and UFBoot &ge; {support.uf}</li>
            <li className="flex items-center gap-2"><span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-full border border-[#b45309] bg-white" /> Support below the display thresholds</li>
          </>
        ) : null}
        {placement ? <li className="flex items-center gap-2"><span aria-hidden="true" className="inline-block h-0 w-4 border-t-2 border-dashed border-[#b45309]" /> Placement best branch (position along it not stored)</li> : null}
        <li className="flex items-center gap-2"><span aria-hidden="true" className="inline-block h-3 w-3 rounded-full border-2 border-ink bg-[#E9ED4C]" /> Highlighted tip</li>
      </ul>
    </div>
  );
}
