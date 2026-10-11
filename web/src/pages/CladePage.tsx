/**
 * #/clade/<id>: Clade Explorer entry for the 17 level-1 clades, 2 backbone groups and 30 subclades
 * (scheme MR_CLD3). Every value comes from clades.json / explorer.json (v1.6.0); memberships are not
 * re-derived. Support is the corrected IQ-TREE run1 value (bipartition-mapped); a level-1 group that
 * fails the thresholds (MR_CLD3_017) is labelled as a legacy assignment.
 */
import { useMemo, useState } from "react";
import { href } from "../app/routes";
import { FlagBadge } from "../components/Badges";
import { CladeSupportNotice } from "../components/CladeSupportNotice";
import { Breadcrumbs, PageTitle } from "../components/common";
import { ErrorState, LoadingSkeleton } from "../components/States";
import type { CladeLevel1, Clades, ExplorerTip, Subclade } from "../data/types";
import { CLADE_STATE_LABEL, FUNC_LABEL, fmtInt } from "../lib/format";
import { thresholdText } from "../lib/summary";
import { buildColorScheme, scopeScheme, tipRoleLabel, type XTree } from "../features/tree/explorerModel";
import { Legend } from "../features/tree/ExplorerPanels";
import { phyloQueryString } from "../features/tree/phyloQuery";
import { TreeCanvas } from "../features/tree/TreeCanvas";
import { useExplorerData } from "../features/tree/useExplorer";
import { NotFoundPage } from "./PlaceholderPage";

type AnyClade = CladeLevel1 | Subclade;
const isLevel1 = (c: AnyClade): c is CladeLevel1 => c.level === 1;
const funcLabel = (f: string | null) => (f ? FUNC_LABEL[f as keyof typeof FUNC_LABEL] ?? f : null);

export default function CladePage({ cladeId }: { cladeId: string }) {
  const res = useExplorerData();
  if (res.state === "loading") return <div className="container-page pt-6"><LoadingSkeleton label="Loading clade" /></div>;
  if (res.state === "error") return <div className="container-page pt-6"><ErrorState error={res.error} retry={res.retry} what="the clade data" /></div>;
  const { tree, clades } = res.data;
  const c: AnyClade | undefined = clades.level1.find((x) => x.clade_id === cladeId) ?? clades.subclades.find((x) => x.clade_id === cladeId);
  if (!c) return <NotFoundPage path={`/clade/${cladeId}`} />;
  return <CladeEntry key={c.clade_id} c={c} tree={tree} clades={clades} />;
}

function Stat({ k, children, testId }: { k: string; children: React.ReactNode; testId?: string }) {
  return (
    <>
      <dt className="text-ink-2">{k}</dt>
      <dd data-testid={testId}>{children}</dd>
    </>
  );
}
const nr = (v: React.ReactNode) => (v === null || v === undefined || v === "" ? <span className="text-ink-2">Not recorded</span> : v);
const jac = (v: number | null) => (v === null ? <span className="text-ink-2">n/a</span> : v.toFixed(2));

function CladeEntry({ c, tree, clades }: { c: AnyClade; tree: XTree; clades: Clades }) {
  const l1 = isLevel1(c) ? c : null;
  const parent = !l1 && c.parent_clade_id ? clades.level1.find((x) => x.clade_id === c.parent_clade_id) ?? null : null;
  const a = c.support_audit;
  const top = l1 ?? parent;
  const legacy = !!top && !top.support_audit.iqtree_run1_meets_support_thresholds;
  const kind = l1 ? (l1.kind === "backbone_group" ? "Backbone group" : "Level-1 clade") : "Subclade (level 2)";
  const members = useMemo(
    () => Object.entries(tree.ex.tips).filter(([, t]) => t.level1 === c.clade_id || t.backbone_group === c.clade_id || t.subclade === c.clade_id).sort((x, y) => x[1].pre - y[1].pre),
    [tree, c.clade_id],
  );
  const subs = l1 ? clades.subclades.filter((s) => s.parent_clade_id === l1.clade_id) : [];
  const nTips = l1 ? l1.n_tips_in_tree : c.n_tips;
  const browseKey = l1 ? "clade" : "sub";
  const fc = c.function_consensus;
  const eligibleE1 = l1 ? l1.e1_anchors.filter((e) => e.counts_eligible === true).length : 0;

  return (
    <div className="container-page pt-6" data-testid="clade-page" data-clade={c.clade_id} data-legacy={legacy ? "true" : "false"}>
      <Breadcrumbs items={[{ label: "Phylogeny", href: href.phylogeny() }, ...(parent ? [{ label: parent.clade_id, href: href.clade(parent.clade_id) }] : []), { label: c.clade_id }]} />
      <PageTitle
        docTitle={`${c.clade_id} - MicroRhodoDB`}
        eyebrow={<span className="flex flex-wrap items-center gap-2"><span className="font-mono">{c.clade_id}</span> <FlagBadge>{kind}</FlagBadge>{legacy ? <FlagBadge tone="warn">legacy assignment</FlagBadge> : null}</span>}
        lead={c.naming_basis ? <>Naming basis: {c.naming_basis}</> : undefined}
      >
        {c.name ?? c.clade_id}
      </PageTitle>

      {legacy && top ? (
        <div className="mb-4 max-w-4xl" data-testid="clade-legacy-banner">
          <CladeSupportNotice clades={clades} only={[top.clade_id]} extra={!l1 ? <p className="mt-1">This subclade itself meets the thresholds (SH-aLRT {a.iqtree_run1_sh_alrt} / UFBoot {a.iqtree_run1_ufboot}); its parent clade is the legacy assignment.</p> : undefined} />
        </div>
      ) : null}

      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-2">
        <section className="card p-4" aria-labelledby="cs-h" data-testid="clade-stats">
          <h2 id="cs-h" className="text-lg">Summary</h2>
          <dl className="mt-2 grid grid-cols-[minmax(0,1fr)] gap-x-4 [overflow-wrap:anywhere] gap-y-1.5 text-sm sm:grid-cols-[13rem_minmax(0,1fr)]">
            <Stat k="Group">{kind}{parent ? <> of <a href={href.clade(parent.clade_id)} className="font-mono">{parent.clade_id}</a></> : null}</Stat>
            <Stat k="Tips in MR_RT_003" testId="clade-ntips">{fmtInt(nTips)} ({fmtInt(c.n_reference_tips_in_corpus)} in the v1.6.0 corpus)</Stat>
            {l1 ? <Stat k="Records (confident / tentative)" testId="clade-records">{fmtInt(l1.n_records_confident)} / {fmtInt(l1.n_records_tentative)}</Stat> : null}
            <Stat k="Records assigned">{c.n_records_assigned === null ? nr(null) : fmtInt(c.n_records_assigned)}</Stat>
            <Stat k="Support (run1, corrected)" testId="clade-support">
              SH-aLRT {a.iqtree_run1_sh_alrt} / UFBoot {a.iqtree_run1_ufboot}{" "}
              {a.iqtree_run1_meets_support_thresholds ? <FlagBadge tone="info">meets thresholds</FlagBadge> : <FlagBadge tone="warn">fails thresholds</FlagBadge>}
              <span className="block text-xs text-ink-2">Thresholds: {thresholdText(clades)}.</span>
            </Stat>
            <Stat k="Stored database label" testId="clade-db-label">
              {a.db_label} {a.db_matches_iqtree_run1 ? <span className="text-xs text-ink-2">(matches run1)</span> : <FlagBadge tone="warn">differs from run1</FlagBadge>}
            </Stat>
            <Stat k="Rooted-file label (audit)">{nr(a.rooted_file_label)}</Stat>
            <Stat k="MRCA node">pre {c.mrca_node}</Stat>
            <Stat k="Cross-replicate Jaccard">run2 {jac(c.jaccard_run2)} · run3 {jac(c.jaccard_run3)} · midpoint rooting {jac(c.jaccard_midpoint_rooting)} · min {jac(c.min_cross_replicate_jaccard)}</Stat>
            {l1 ? (
              <Stat k="Robustness caveat" testId="clade-robustness">
                {l1.robustness_caveat ? <><FlagBadge tone="warn">caveat</FlagBadge> {l1.robustness_caveat_reasons.join("; ")}</> : "None"}
              </Stat>
            ) : null}
            <Stat k="Dominant taxonomy">{nr([c.dominant_domain, c.dominant_phylum].filter(Boolean).join(" / "))}</Stat>
            <Stat k="Dominant helix-C motif">{nr(c.dominant_helixC_motif ? <span className="font-mono">{c.dominant_helixC_motif}</span> : null)}</Stat>
            <Stat k="Dominant v1.4 subfamily">{nr(c.dominant_subfamily_v14)}</Stat>
          </dl>
          <p className="mt-3 flex flex-wrap gap-2">
            <a className="btn btn-secondary btn-sm" href={href.browse(`group=all&eng=1&${browseKey}=${c.clade_id}`)} data-testid="clade-browse">Browse records</a>
            {l1 ? <a className="btn btn-secondary btn-sm" href={href.browse(`group=all&eng=1&clade=${c.clade_id}&tent=1`)}>Browse incl. tentative</a> : null}
            <a className="btn btn-secondary btn-sm" href={href.phylogeny(phyloQueryString({ clade: c.clade_id }))} data-testid="clade-in-tree">Highlight in tree</a>
            <a className="btn btn-secondary btn-sm" href={href.phylogeny(phyloQueryString({ clade: c.clade_id, node: c.mrca_node }))}>Open subtree in explorer</a>
          </p>
        </section>

        <section className="card p-4" aria-labelledby="cf-h" data-testid="clade-function">
          <h2 id="cf-h" className="text-lg">Function consensus (v1.6.0)</h2>
          <dl className="mt-2 grid grid-cols-[minmax(0,1fr)] gap-x-4 [overflow-wrap:anywhere] gap-y-1.5 text-sm sm:grid-cols-[13rem_minmax(0,1fr)]">
            <Stat k="Clade function" testId="clade-func">{fc.clade_function ? <>{funcLabel(fc.clade_function)} <code className="text-xs text-ink-2">{fc.clade_function}</code></> : <span className="text-ink-2">None (no consensus call)</span>}</Stat>
            <Stat k="Consensus status">{fc.consensus_status}</Stat>
            <Stat k="E1 records (counted)" testId="clade-ne1">{fc.n_E1}{l1 && l1.e1_anchors.length !== fc.n_E1 ? <span className="block text-xs text-ink-2">{l1.e1_anchors.length} E1 records are listed below; {eligibleE1} are counts-eligible and form the official count.</span> : null}</Stat>
            <Stat k="E1 classes">{nr(fc.E1_classes)}</Stat>
            <Stat k="Top-class fraction">{fc.top_frac === null ? nr(null) : fc.top_frac.toFixed(2)}</Stat>
            <Stat k="Records considered">{fmtInt(fc.n_records)}</Stat>
            <Stat k="E1 classes among tips">{nr(c.e1_classes_tips)}</Stat>
          </dl>
          <h3 className="mt-4 text-base">Placements</h3>
          <p className="text-xs text-ink-2">{c.placement_counts.basis}.</p>
          {Object.keys(c.placement_counts.counts).length ? (
            <ul className="mt-1 flex flex-wrap gap-2 text-sm" data-testid="clade-placements">
              {Object.entries(c.placement_counts.counts).map(([k, n]) => <li key={k}><code>{k}</code> {fmtInt(n)}</li>)}
            </ul>
          ) : <p className="mt-1 text-sm text-ink-2" data-testid="clade-placements">No current placements.</p>}
          <p className="mt-1 text-xs text-ink-2">Placements are EPA-ng results on the fixed reference tree; they are not tips of the tree.</p>
        </section>
      </div>

      {subs.length ? (
        <section className="mt-6" aria-labelledby="sub-h" data-testid="clade-subclades">
          <h2 id="sub-h" className="text-xl">Subclades</h2>
          <div className="mt-2 overflow-x-auto rounded-md border border-line">
            <table className="data-table">
              <thead><tr><th>Subclade</th><th className="num">Tips</th><th>Support (run1)</th><th>Function consensus</th><th>Dominant phylum</th><th className="num">Records assigned</th></tr></thead>
              <tbody>
                {subs.map((s) => (
                  <tr key={s.clade_id}>
                    <td><a href={href.clade(s.clade_id)} className="font-mono">{s.clade_id}</a>{s.name ? <span className="block text-xs text-ink-2">{s.name}</span> : null}</td>
                    <td className="num">{s.n_tips}</td>
                    <td>{s.support_audit.iqtree_run1_label} {s.support_audit.iqtree_run1_meets_support_thresholds ? null : <FlagBadge tone="warn">fails</FlagBadge>}</td>
                    <td>{s.function_consensus.clade_function ?? <span className="text-ink-2">none</span>} <span className="text-xs text-ink-2">({s.function_consensus.consensus_status})</span></td>
                    <td>{nr(s.dominant_phylum)}</td>
                    <td className="num">{s.n_records_assigned === null ? "" : fmtInt(s.n_records_assigned)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <CladeTree c={c} tree={tree} clades={clades} />

      {l1 && l1.e1_anchors.length ? (
        <section className="mt-6" aria-labelledby="e1-h" data-testid="clade-e1">
          <h2 id="e1-h" className="text-xl">E1 records assigned to this group</h2>
          <p className="mt-1 text-sm text-ink-2">Experimentally characterised (E1) records confidently assigned to {c.clade_id}. Only counts-eligible records enter the official E1 count ({fc.n_E1}).</p>
          <div className="mt-2 overflow-x-auto rounded-md border border-line">
            <table className="data-table">
              <thead><tr><th>Protein Entry</th><th>Source</th><th>Protein</th><th>Organism</th><th>Function</th><th>Counts-eligible</th><th>Tip</th></tr></thead>
              <tbody>
                {l1.e1_anchors.map((e) => (
                  <tr key={e.source_acc}>
                    <td><a href={href.record(e.mrdb_acc)}>{e.mrdb_acc}</a></td>
                    <td className="font-mono">{e.source_acc}</td>
                    <td>{nr(e.protein_name)}</td>
                    <td><i>{e.organism}</i></td>
                    <td>{nr(funcLabel(e.func_class))}</td>
                    <td>{e.counts_eligible === true ? "yes" : e.counts_eligible === false ? <FlagBadge tone="warn">no</FlagBadge> : "n/a"}</td>
                    <td>{e.is_reference_tip ? <a href={href.phylogeny(phyloQueryString({ tip: e.source_acc }))}>reference tip</a> : <span className="text-ink-2">placed</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {l1 && l1.representatives.length ? (
        <section className="mt-6" aria-labelledby="rep-h" data-testid="clade-representatives">
          <h2 id="rep-h" className="text-xl">Representatives</h2>
          <p className="mt-1 text-sm text-ink-2">{clades.representative_rule}</p>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {l1.representatives.map((r) => (
              <li key={r.source_acc} className="card p-3 text-sm">
                <a href={href.record(r.mrdb_acc)} className="font-semibold">{r.mrdb_acc}</a> <span className="font-mono text-ink-2">{r.source_acc}</span>
                <span className="block">{r.protein_name ?? <span className="text-ink-2">Unnamed protein</span>}</span>
                <span className="block text-ink-2"><i>{r.organism}</i></span>
                <span className="mt-1 block text-xs text-ink-2">{r.reason}{r.func_class ? ` · ${funcLabel(r.func_class)}` : ""}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <MemberTable members={members} cladeId={c.clade_id} />
    </div>
  );
}

function CladeTree({ c, tree, clades }: { c: AnyClade; tree: XTree; clades: Clades }) {
  const [mode, setMode] = useState<"subclade" | "function">(isLevel1(c) ? "subclade" : "function");
  const scheme = useMemo(() => buildColorScheme(tree, mode), [tree, mode]);
  const cladeScheme = useMemo(() => buildColorScheme(tree, "clade"), [tree]);
  const failing = useMemo(() => new Set(clades.level1.filter((x) => !x.support_audit.iqtree_run1_meets_support_thresholds).map((x) => x.clade_id)), [clades]);
  const [sel, setSel] = useState<number | null>(null);
  const opts = useMemo(() => ({ layout: "rect" as const, branch: "prop" as const, rootPre: c.mrca_node, collapsed: new Set<number>() }), [c.mrca_node]);
  const n = tree.nodes[c.mrca_node].nTips;
  const height = Math.min(1240, Math.max(320, n * 13 + 40));
  const subScheme = useMemo(() => scopeScheme(tree, scheme, c.mrca_node), [tree, scheme, c.mrca_node]);
  const selTip = sel !== null && tree.nodes[sel].isTip ? tree.ex.tips[tree.nodes[sel].name] : null;
  return (
    <section className="mt-6" aria-labelledby="ct-h" data-testid="clade-tree">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h2 id="ct-h" className="text-xl">Subtree</h2>
        <label className="text-sm">Colour by{" "}
          <select className="field inline-block w-auto" value={mode} onChange={(e) => setMode(e.target.value as "subclade" | "function")} data-testid="clade-tree-color">
            <option value="subclade">Subclade</option>
            <option value="function">Function (v1.6.0)</option>
          </select>
        </label>
      </div>
      <p className="mt-1 text-sm text-ink-2">Subtree of MR_RT_003 below the MRCA of {c.clade_id} (pre {c.mrca_node}, {n} tips), branch lengths to scale. <a href={href.phylogeny(phyloQueryString({ clade: c.clade_id, node: c.mrca_node }))}>Open in the explorer</a> for support values, search and downloads.</p>
      <div className="mt-2 grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <TreeCanvas
          tree={tree} opts={opts} scheme={scheme} cladeScheme={cladeScheme} failingGroups={failing}
          support={{ show: false, sh: 80, uf: 95 }} selected={sel} tip={null} placement={[]} cladeSpan={null} focus={null}
          height={height} onSelect={setSel} onHover={() => undefined}
          label={`Subtree of ${c.clade_id}, ${n} tips`} testId="clade-tree-canvas"
        />
        <div className="space-y-3">
          {selTip ? (
            <div className="card p-3 text-sm" data-testid="clade-tree-info">
              <p className="font-mono font-semibold">{tree.nodes[sel!].name}</p>
              <p>{selTip.mrdb_acc ? <a href={href.record(selTip.mrdb_acc)}>Protein Entry {selTip.mrdb_acc}</a> : "Not in the v1.6.0 corpus"}</p>
              <p className="text-ink-2"><i>{selTip.organism}</i></p>
              <p className="text-ink-2">{selTip.subclade ?? "No subclade"} · {tipRoleLabel(selTip.tip_role)}</p>
            </div>
          ) : null}
          <Legend scheme={subScheme} failing={[]} support={{ show: false, sh: 80, uf: 95 }} placement={false} />
        </div>
      </div>
    </section>
  );
}

function MemberTable({ members, cladeId }: { members: [string, ExplorerTip][]; cladeId: string }) {
  const absent = members.filter(([, t]) => !t.in_corpus).length;
  return (
    <section className="mt-6" aria-labelledby="mt-h" data-testid="clade-members">
      <h2 id="mt-h" className="text-xl">Reference tips ({members.length})</h2>
      <p className="mt-1 text-sm text-ink-2">Tips of MR_RT_003 belonging to {cladeId}, in tree order.{absent ? ` ${absent} tip${absent > 1 ? "s are" : " is"} not in the v1.6.0 corpus and has no Protein Entry.` : ""} Records placed into this group are listed in Browse.</p>
      <div className="mt-2 max-h-[32rem] overflow-auto rounded-md border border-line">
        <table className="data-table">
          <thead><tr><th>Tip</th><th>Protein Entry</th><th>Role</th><th>Subclade</th><th>Organism</th><th>Function</th><th>Evidence</th><th>State</th></tr></thead>
          <tbody>
            {members.map(([acc, t]) => (
              <tr key={acc} data-testid="clade-member" data-acc={acc}>
                <td><a href={href.phylogeny(phyloQueryString({ tip: acc }))} className="font-mono">{acc}</a></td>
                <td>{t.mrdb_acc ? <a href={href.record(t.mrdb_acc)}>{t.mrdb_acc}</a> : <FlagBadge tone="warn">not in corpus</FlagBadge>}</td>
                <td>{tipRoleLabel(t.tip_role)}</td>
                <td>{t.subclade ?? <span className="text-ink-2">none</span>}</td>
                <td><i>{t.organism}</i></td>
                <td>{t.func_class ? funcLabel(t.func_class) : <span className="text-ink-2">n/a</span>}</td>
                <td>{t.evidence_level ?? <span className="text-ink-2">n/a</span>}</td>
                <td>{t.clade_state ? CLADE_STATE_LABEL[t.clade_state] : <span className="text-ink-2">n/a</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
