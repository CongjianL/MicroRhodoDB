/**
 * Statistics (#/statistics), spec section 8. Every chart value comes from summary.json (exporter-owned,
 * each distribution carries its SQL, denominator and release). The optional "Filter and recount"
 * panel loads records-index.json on request, recounts the distributions it can and compares every
 * category with summary.json (runtime reconciliation), then lets the user filter the corpus.
 * The watchlist is shown in its own panel and never enters a corpus total.
 */
import { useMemo, useState } from "react";
import { href } from "../app/routes";
import { Callout, PageTitle, StatCard } from "../components/common";
import { Provenance, inclusionText } from "../components/Provenance";
import { ErrorState, LoadingSkeleton } from "../components/States";
import { loadRecordsIndex, loadSummary, loadVocabulary, useResource } from "../data/loaders";
import type { FuncClass, Summary, Vocabulary } from "../data/types";
import { BarChart, type BarItem } from "../features/charts/BarChart";
import { DEFAULT_STATE, filterQuery, toRows, type IndexRow } from "../lib/browse";
import { crosstabCellHref, distItemHref } from "../lib/drilldown";
import { CATEGORICAL, EV_COLOR, GROUP_COLOR, MISSING_COLOR, OTHER_COLOR, cat } from "../lib/chartColors";
import {
  CLADE_STATE_LABEL, EVIDENCE_LEVELS, FUNC_LABEL, FUNC_ORDER, GROUP_LABEL, STATUS_GROUP, STATUS_LABEL, STATUS_ORDER, fmtInt, fmtPct,
} from "../lib/format";
import { BASIS_ORDER, NULL_KEY, OTHER_KEY, basisLabel, countBy, lengthBinOrder, matrix, ordered, reconcile, topN, type Dist } from "../lib/stats";
import { distribution, metric, mv } from "../lib/summary";

const CLADE_STATE_ORDER = ["confident", "tentative", "reference_tip_unclustered", "outgroup_reference_tip", "outgroup_placed", "unassigned", "distant"];

export default function StatisticsPage() {
  const res = useResource(() => Promise.all([loadSummary(), loadVocabulary()]));
  return (
    <div className="container-page pt-6">
      <PageTitle
        docTitle="Statistics - MicroRhodoDB"
        lead="Composition and annotation coverage of the v1.6.1 release. Each chart states its denominator; open “How this is counted” for the exact query and inclusion policy."
      >
        Statistics
      </PageTitle>
      {res.state === "loading" ? <LoadingSkeleton lines={8} /> : null}
      {res.state === "error" ? <ErrorState error={res.error} retry={res.retry} what="the release summary" /> : null}
      {res.state === "ready" ? <StatsBody summary={res.data[0]} vocab={res.data[1]} /> : null}
    </div>
  );
}

/** Chart + provenance for one exported distribution. */
function DistChart({ summary, dist, items, title, testId, footer }: {
  summary: Summary;
  dist: Dist;
  items: BarItem[];
  title: string;
  testId: string;
  footer?: React.ReactNode;
}) {
  const den = summary.denominators[dist.denominator.id];
  return (
    <BarChart
      testId={testId}
      title={title}
      items={items}
      denominator={dist.denominator.value}
      denominatorLabel={den?.label ?? dist.denominator.id}
      footer={
        <>
          {footer ? <div className="mb-1.5">{footer}</div> : null}
          <Provenance summary={summary} sql={dist.sql} denominatorId={dist.denominator.id} sourceFile={dist.source_file} derivation={dist.derivation} inclusion={inclusionText(dist.denominator.id)} testId={`${testId}-provenance`} />
        </>
      }
    />
  );
}

function ScopeToggle<T extends string>({ value, options, onChange, label }: { value: T; options: { v: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="inline-flex flex-wrap gap-1">
      {options.map((o) => (
        <button key={o.v} type="button" aria-pressed={value === o.v} className={`btn btn-sm ${value === o.v ? "btn-primary" : "btn-secondary"}`} onClick={() => onChange(o.v)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

function StatsBody({ summary, vocab }: { summary: Summary; vocab: Vocabulary }) {
  const S = (id: string) => fmtInt(mv(summary, id));
  const [memberScope, setMemberScope] = useState<"all" | "counted">("all");
  const [evScope, setEvScope] = useState<"counted" | "all">("counted");
  const [cladeScope, setCladeScope] = useState<"mc" | "all">("mc");
  const evDef = new Map(vocab.evidence_level.map((e) => [e.level, e.definition]));
  const funcDef = new Map(vocab.func_class.map((f) => [f.func_class, f.definition]));
  const cladeDef = new Map(vocab.clade_state.map((c) => [c.state, c.definition]));

  const memberDist = distribution(summary, memberScope === "all" ? "membership_status" : "membership_status_counted");
  const memberItems: BarItem[] = ordered(memberDist.items, STATUS_ORDER).map((i) => ({
    key: String(i.key),
    label: STATUS_LABEL[i.key as keyof typeof STATUS_LABEL] ?? String(i.key),
    value: i.value,
    color: GROUP_COLOR[STATUS_GROUP[i.key as keyof typeof STATUS_GROUP]] ?? OTHER_COLOR,
    href: distItemHref(memberDist, i.key),
    note: `${GROUP_LABEL[STATUS_GROUP[i.key as keyof typeof STATUS_GROUP]]} · code ${i.key}`,
  }));

  const evDist = distribution(summary, evScope === "counted" ? "evidence_level_counted" : "evidence_level_all");
  const evItems: BarItem[] = ordered(evDist.items, EVIDENCE_LEVELS).map((i) => ({
    key: String(i.key), label: String(i.key), value: i.value, color: EV_COLOR[i.key as keyof typeof EV_COLOR],
    href: distItemHref(evDist, i.key), note: evDef.get(i.key as never),
  }));

  const funcDist = distribution(summary, "func_class_counted");
  const funcItems: BarItem[] = ordered(funcDist.items, FUNC_ORDER).map((i, k) => ({
    key: String(i.key),
    label: FUNC_LABEL[i.key as FuncClass] ?? String(i.key),
    value: i.value,
    color: i.key === "unresolved" || i.key === "unassigned" ? MISSING_COLOR : cat(k),
    href: distItemHref(funcDist, i.key),
    note: funcDef.get(i.key as FuncClass),
  }));

  const domDist = distribution(summary, "tax_domain_counted");
  const domItems: BarItem[] = ordered(domDist.items, ["Bacteria", "Archaea", "Eukaryota", null]).map((i, k) => ({
    key: i.key ?? NULL_KEY, label: i.key ?? "No domain assigned", value: i.value, color: i.key === null ? MISSING_COLOR : cat(k),
    href: distItemHref(domDist, i.key),
  }));

  const phylumDist = distribution(summary, "ncbi_phylum_counted");
  const phylum = topN(phylumDist.items, 12);
  const phylumItems: BarItem[] = phylum.items.map((i, k) => ({
    key: i.key,
    label: i.key === OTHER_KEY ? `Other phyla (${i.nOther})` : i.key === NULL_KEY ? "No phylum rank in NCBI lineage" : i.key,
    value: i.value,
    color: i.key === NULL_KEY ? MISSING_COLOR : i.key === OTHER_KEY ? OTHER_COLOR : cat(k),
    href: i.key === OTHER_KEY ? undefined : distItemHref(phylumDist, i.rawKey ?? null),
  }));

  const cladeDist = distribution(summary, cladeScope === "mc" ? "clade_state_members_candidates" : "clade_state");
  const cladeItems: BarItem[] = ordered(cladeDist.items, CLADE_STATE_ORDER).map((i, k) => ({
    key: String(i.key),
    label: CLADE_STATE_LABEL[i.key as keyof typeof CLADE_STATE_LABEL] ?? String(i.key),
    value: i.value,
    color: i.key === "confident" ? "#1b7f4b" : i.key === "tentative" ? "#E69F00" : i.key === "unassigned" ? MISSING_COLOR : CATEGORICAL[(k + 3) % CATEGORICAL.length],
    href: distItemHref(cladeDist, i.key),
    note: cladeDef.get(i.key as never),
  }));

  const pdbMethod = distribution(summary, "pdb_method");
  const pdbItems: BarItem[] = pdbMethod.items.slice().sort((a, b) => b.value - a.value).map((i, k) => ({ key: String(i.key), label: String(i.key), value: i.value, color: cat(k) }));
  const cov = distribution(summary, "structure_coverage");
  const COV_LABEL: Record<string, string> = { pdb: "At least one experimental PDB entry", afdb_only: "AlphaFold DB model only", none: "No structure or model" };
  const covItems: BarItem[] = ordered(cov.items, ["pdb", "afdb_only", "none"]).map((i, k) => ({
    key: String(i.key), label: COV_LABEL[String(i.key)] ?? String(i.key), value: i.value, color: i.key === "none" ? MISSING_COLOR : cat(k),
  }));

  const motifDist = distribution(summary, "helixC_motif_counted");
  const motif = topN(motifDist.items, 15);
  const motifItems: BarItem[] = motif.items.map((i, k) => ({
    key: i.key,
    label: i.key === OTHER_KEY ? `Other motifs (${i.nOther})` : i.key === NULL_KEY ? "Motif not determined" : i.key,
    value: i.value,
    color: i.key === NULL_KEY ? MISSING_COLOR : i.key === OTHER_KEY ? OTHER_COLOR : cat(k),
    href: i.key === OTHER_KEY ? undefined : distItemHref(motifDist, i.rawKey ?? null),
  }));
  const mclass = distribution(summary, "motif_class_counted");
  const mclassItems: BarItem[] = ordered(mclass.items, [...FUNC_ORDER, null]).map((i, k) => ({
    key: i.key ?? NULL_KEY, label: i.key === null ? "Motif not classifiable" : FUNC_LABEL[i.key as FuncClass] ?? i.key, value: i.value,
    color: i.key === null ? MISSING_COLOR : cat(k),
  }));
  const lenDist = distribution(summary, "length_bin_counted");
  const lenItems: BarItem[] = lenDist.items.slice().sort((a, b) => lengthBinOrder(a.key) - lengthBinOrder(b.key)).map((i) => ({
    key: i.key ?? NULL_KEY, label: i.key ?? "Unknown", value: i.value, color: "#0072B2",
  }));
  const basisDist = distribution(summary, "function_basis_category_counted");
  const basisItems: BarItem[] = ordered(basisDist.items, BASIS_ORDER).map((i, k) => ({
    key: String(i.key), label: basisLabel(i.key), value: i.value, color: i.key === "insufficient" || i.key === "conflict" ? MISSING_COLOR : cat(k), note: `code ${i.key}`,
  }));

  const wl = distribution(summary, "watchlist_family");
  const wlItems: BarItem[] = wl.items.slice().sort((a, b) => b.value - a.value).map((i, k) => ({ key: String(i.key), label: String(i.key), value: i.value, color: cat(k + 4) }));

  const sx = summary.crosstabs.find((x) => x.id === "evidence_by_membership_group_counted");

  return (
    <>
      <section aria-labelledby="st-core" className="mb-8">
        <h2 id="st-core" className="mb-3 text-xl">Corpus size</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <StatCard testId="stat-records-total" value={mv(summary, "records_total")} label="Source records" detail={`All UniProt source records, including ${S("records_engineered")} engineered constructs.`} />
          <StatCard testId="stat-records-counted" value={mv(summary, "records_counted")} label="Counted records" detail="Engineered constructs excluded; the default denominator for evidence, function, taxonomy and motif statistics." />
          <StatCard testId="stat-mrdb" value={mv(summary, "mrdb_accessions")} label="MRDB accessions" detail={`One per unique sequence; ${S("mrdb_multi_source")} accessions group more than one source record.`} />
        </div>
        <p className="mt-3 text-sm text-ink-2">
          Reconciliation: {S("records_total")} source records = {S("records_counted")} counted + {S("records_engineered")} engineered constructs; these collapse to {S("mrdb_accessions")} unique sequences.
          The {S("watchlist")} watchlist entries are not part of any of these numbers.
        </p>
      </section>

      <section aria-labelledby="st-membership" className="mb-8">
        <h2 id="st-membership" className="mb-1 text-xl">Membership and evidence</h2>
        <p className="mb-3 max-w-3xl text-sm text-ink-2">
          Membership status (is it a Type-I microbial rhodopsin?) and evidence level (how its function call is supported) are separate axes; neither implies the other.
        </p>
        <div className="grid gap-4 lg:grid-cols-2">
          <DistChart summary={summary} dist={memberDist} items={memberItems} testId="chart-membership-status" title="Membership status"
            footer={<ScopeToggle label="Membership denominator" value={memberScope} onChange={setMemberScope} options={[{ v: "all", label: "All source records" }, { v: "counted", label: "Counted records" }]} />} />
          <DistChart summary={summary} dist={evDist} items={evItems} testId="chart-evidence-level" title="Functional evidence level (E1–E5)"
            footer={
              <>
                <ScopeToggle label="Evidence denominator" value={evScope} onChange={setEvScope} options={[{ v: "counted", label: "Counted records" }, { v: "all", label: "All source records" }]} />
                <p className="mt-1.5">E1 counted: {S("e1_counted")} of {fmtInt(metric(summary, "e1_counted").denominator!.value)}; E1 total including engineered constructs: {S("e1_total")} of {fmtInt(metric(summary, "e1_total").denominator!.value)}. Evidence levels are evidence types, not calibrated probabilities.</p>
              </>
            } />
        </div>
        {sx ? <CrosstabTable summary={summary} x={sx} /> : null}
      </section>

      <section aria-labelledby="st-function" className="mb-8">
        <h2 id="st-function" className="mb-3 text-xl">Function</h2>
        <div className="grid gap-4 lg:grid-cols-2">
          <DistChart summary={summary} dist={funcDist} items={funcItems} testId="chart-func-class" title="Functional class"
            footer="Unresolved (no call) and unassigned (call withdrawn) records are kept as their own categories." />
          <DistChart summary={summary} dist={basisDist} items={basisItems} testId="chart-basis" title="Basis of the function call"
            footer={<a href={href.section("evidence")}>Explore by evidence and basis</a>} />
        </div>
      </section>

      <section aria-labelledby="st-tax" className="mb-8">
        <h2 id="st-tax" className="mb-3 text-xl">Taxonomy</h2>
        <div className="grid gap-4 lg:grid-cols-2">
          <DistChart summary={summary} dist={domDist} items={domItems} testId="chart-domain" title="Taxonomic domain" />
          <DistChart summary={summary} dist={phylumDist} items={phylumItems} testId="chart-phylum" title="Phylum (NCBI lineage), 12 largest"
            footer={`The ${fmtInt(phylum.items.find((i) => i.key === OTHER_KEY)?.nOther ?? 0)} smaller phyla are summed in “Other”; records without a phylum rank in their NCBI lineage are shown separately. NCBI taxonomy, not GTDB.`} />
        </div>
      </section>

      <section aria-labelledby="st-clade" className="mb-8">
        <h2 id="st-clade" className="mb-3 text-xl">Phylogenetic placement (MR_RT_003)</h2>
        <div className="grid gap-4 lg:grid-cols-2">
          <DistChart summary={summary} dist={cladeDist} items={cladeItems} testId="chart-clade-state" title="Clade assignment state"
            footer={
              <>
                <ScopeToggle label="Clade denominator" value={cladeScope} onChange={setCladeScope} options={[{ v: "mc", label: "Members and candidates" }, { v: "all", label: "All source records" }]} />
                <p className="mt-1.5">
                  Confident clade for {S("clade_confident_members_candidates")} of {S("members_candidates")} Type-I members and candidates ({fmtPct(mv(summary, "clade_confident_members_candidates"), mv(summary, "members_candidates"))}).
                  Tentative placements are not clade assignments. <a href={href.phylogeny()}>Open the phylogeny</a>
                </p>
              </>
            } />
          <div className="card p-4 text-sm">
            <h3 className="text-base">Reference tree</h3>
            <ul className="mt-2 space-y-1">
              <li><span className="tabular font-semibold">{S("tree_tips")}</span> reference-tree tips</li>
              <li><span className="tabular font-semibold">{S("level1_clades")}</span> level-1 clades, {S("backbone_groups")} backbone groups, {S("subclades")} subclades</li>
              <li><span className="tabular font-semibold">{S("placements_current")}</span> current EPA-ng placements (of {S("records_total")} source records)</li>
            </ul>
            <p className="mt-2 text-ink-2">The reference tree was built once from the reference tips; corpus records are placed onto it, not used to rebuild it.</p>
          </div>
        </div>
      </section>

      <section aria-labelledby="st-struct" className="mb-8">
        <h2 id="st-struct" className="mb-3 text-xl">Structures</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard testId="stat-pdb-entries" value={mv(summary, "pdb_entries")} label="Distinct PDB entries" detail={`${S("pdb_entries_with_retinal")} contain retinal (RET).`} href={href.section("structures")} />
          <StatCard testId="stat-records-pdb" value={mv(summary, "records_with_pdb")} label="Source records with a PDB entry" detail={`${S("records_with_pdb_counted")} of them counted; ${S("mrdb_with_pdb")} MRDB accessions.`} />
          <StatCard testId="stat-pdb-links" value={mv(summary, "pdb_links")} label="Record–PDB links" detail="One entry can be linked to several records, and one record to several entries." />
          <StatCard testId="stat-afdb" value={mv(summary, "records_with_afdb")} label="Records with an AlphaFold DB model" detail={`${S("records_with_afdb_counted")} counted; plus ${S("predicted_models")} release models.`} />
        </div>
        <p className="mt-2 text-sm text-ink-2">These four numbers have different denominators and are not directly comparable.</p>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <DistChart summary={summary} dist={pdbMethod} items={pdbItems} testId="chart-pdb-method" title="Experimental method (distinct PDB entries)" />
          <DistChart summary={summary} dist={cov} items={covItems} testId="chart-structure-coverage" title="Structure coverage per source record" />
        </div>
      </section>

      <section aria-labelledby="st-seq" className="mb-8">
        <h2 id="st-seq" className="mb-3 text-xl">Motifs and sequence length</h2>
        <div className="grid gap-4 lg:grid-cols-2">
          <DistChart summary={summary} dist={motifDist} items={motifItems} testId="chart-helixc" title="Helix-C motif (BR positions 85/89/96), 15 most frequent"
            footer={`${fmtInt(motifDist.items.length)} distinct values in total; the rest are summed in “Other”.`} />
          <DistChart summary={summary} dist={mclass} items={mclassItems} testId="chart-motif-class" title="Function class implied by the motif"
            footer="Motif-implied class is a sequence feature, not the function call." />
          <DistChart summary={summary} dist={lenDist} items={lenItems} testId="chart-length" title="Sequence length (residues)" />
        </div>
      </section>

      <section aria-labelledby="st-watch" className="mb-8 rounded-xl border-2 border-dashed border-warn-line p-4" data-testid="watchlist-panel">
        <h2 id="st-watch" className="mb-1 text-xl">Novel-family watchlist (separate from the corpus)</h2>
        <p className="mb-3 max-w-3xl text-sm text-ink-2">
          {S("watchlist")} research candidates that were <strong>not admitted to the corpus</strong>. They have no membership status, evidence level or function, and are excluded from every number above.
        </p>
        <div className="grid gap-4 lg:grid-cols-2">
          <DistChart summary={summary} dist={wl} items={wlItems} testId="chart-watchlist" title="Watchlist entries by family" footer={<a href={href.section("watchlist")}>Open the watchlist</a>} />
        </div>
      </section>

      <FilterAndRecount summary={summary} />

      <section aria-labelledby="st-notes" className="mb-4 text-sm text-ink-2">
        <h2 id="st-notes" className="mb-2 text-base text-ink">Notes</h2>
        <ul className="list-disc space-y-1 pl-5">
          {summary.notes.map((n) => <li key={n}>{n}</li>)}
          <li>All values are read from summary.json, generated by tools/export_web_data.py from the read-only v{summary.dataset_release} database; the website computes no statistic of its own.</li>
        </ul>
      </section>
    </>
  );
}

function CrosstabTable({ summary, x }: { summary: Summary; x: Summary["crosstabs"][number] }) {
  const m = matrix(x, ["member", "candidate", "boundary", "outgroup", "rejected"], EVIDENCE_LEVELS);
  return (
    <div className="card mt-4 p-4" data-testid="crosstab-evidence-membership">
      <h3 className="text-base">Evidence level by membership group</h3>
      <p className="mt-0.5 text-sm text-ink-2">{summary.denominators[x.denominator.id]?.label}: n = {fmtInt(x.denominator.value)}</p>
      <div className="mt-2 relative overflow-x-auto" role="region" aria-label="Evidence level by membership group" tabIndex={0}>
        <table className="data-table">
          <thead>
            <tr><th scope="col">Membership group</th>{m.cols.map((c) => <th key={String(c)} scope="col" className="num">{c}</th>)}<th scope="col" className="num">Total</th></tr>
          </thead>
          <tbody>
            {m.rows.map((r) => (
              <tr key={String(r)}>
                <th scope="row" className="!static !bg-transparent !font-normal">{GROUP_LABEL[r as keyof typeof GROUP_LABEL] ?? r}</th>
                {m.cols.map((c) => <td key={String(c)} className="num">{m.value(r, c) ? <a href={crosstabCellHref(x, r as string, c as string)}>{fmtInt(m.value(r, c))}</a> : "0"}</td>)}
                <td className="num font-semibold">{fmtInt(m.rowTotal(r))}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr><th scope="row" className="!static !bg-transparent">Total</th>{m.cols.map((c) => <td key={String(c)} className="num">{fmtInt(m.colTotal(c))}</td>)}<td className="num font-semibold" data-testid="crosstab-total">{fmtInt(m.total)}</td></tr>
          </tfoot>
        </table>
      </div>
      <p className="mt-2 text-sm text-ink-2">
        Each cell counts records that have both values. In this release, groups whose counted records are all E5:{" "}
        {m.rows.filter((r) => m.rowTotal(r) > 0 && m.value(r, "E5") === m.rowTotal(r)).map((r) => GROUP_LABEL[r as keyof typeof GROUP_LABEL] ?? r).join(", ") || "none"}.
        Evidence level never decides membership, and membership never raises an evidence level.
      </p>
      <div className="mt-2"><Provenance summary={summary} sql={x.sql} denominatorId={x.denominator.id} inclusion={inclusionText(x.denominator.id)} /></div>
    </div>
  );
}

/* ------------------------------------------------------------------ filter + runtime reconciliation */

function FilterAndRecount({ summary }: { summary: Summary }) {
  const [open, setOpen] = useState(false);
  return (
    <section aria-labelledby="st-filter" className="mb-8" data-testid="filter-recount">
      <h2 id="st-filter" className="mb-1 text-xl">Filter and recount</h2>
      <p className="mb-3 max-w-3xl text-sm text-ink-2">
        Loads the records index (about 4 MB) to recount the distributions above from the per-record data, compare every category with summary.json, and break down any subset of the corpus.
      </p>
      {open ? <RecountBody summary={summary} /> : <button type="button" className="btn btn-secondary" onClick={() => setOpen(true)} data-testid="load-recount">Load records index</button>}
    </section>
  );
}

function RecountBody({ summary }: { summary: Summary }) {
  const ri = useResource(loadRecordsIndex);
  const rows = useMemo(() => (ri.state === "ready" ? toRows(ri.data) : null), [ri]);
  const recon = useMemo(() => (rows ? reconcile(summary, rows) : []), [rows, summary]);
  const [scope, setScope] = useState<"counted" | "all">("counted");
  const [group, setGroup] = useState("");
  const [domain, setDomain] = useState("");
  const [evidence, setEvidence] = useState("");
  const [func, setFunc] = useState("");
  if (ri.state === "loading") return <LoadingSkeleton label="Loading records index" />;
  if (ri.state === "error") return <ErrorState error={ri.error} retry={ri.retry} what="the records index" />;
  if (!rows) return null;
  const ok = recon.filter((r) => r.ok).length;
  const subset = rows.filter((r) =>
    (scope === "all" || r.counts_eligible) &&
    (!group || r.membership_group === group) &&
    (!domain || (domain === "none" ? r.tax_domain === null : r.tax_domain === domain)) &&
    (!evidence || r.evidence_level === evidence) &&
    (!func || r.func_class === func));
  const browseQ = filterQuery({
    ...DEFAULT_STATE,
    group: (group || "all") as typeof DEFAULT_STATE.group,
    domain: domain as typeof DEFAULT_STATE.domain,
    evidence: evidence as typeof DEFAULT_STATE.evidence,
    func: func as typeof DEFAULT_STATE.func,
    eng: scope === "all",
  });
  const breakdown = (f: (r: IndexRow) => string | null, label: (k: string | null) => string) =>
    [...countBy(subset, f).entries()].sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ k, label: label(k), v }));
  return (
    <div className="space-y-4">
      <Callout tone={ok === recon.length ? "info" : "warn"} title={`Runtime reconciliation: ${ok} of ${recon.length} distributions match summary.json exactly`} testId="recon-status">
        <div className="relative overflow-x-auto" role="region" aria-label="Reconciliation table" tabIndex={0}>
          <table className="data-table mt-2">
            <thead><tr><th scope="col">Distribution</th><th scope="col" className="num">Denominator</th><th scope="col" className="num">Recounted rows</th><th scope="col">Result</th></tr></thead>
            <tbody>
              {recon.map((r) => (
                <tr key={r.id} data-testid={`recon-${r.id}`}>
                  <th scope="row" className="!static !bg-transparent !font-normal">{r.label}<code className="block text-xs text-ink-2">{r.id}</code></th>
                  <td className="num">{fmtInt(r.denominator)}</td>
                  <td className="num">{fmtInt(r.recounted)}</td>
                  <td>{r.ok ? "match" : `MISMATCH (${r.mismatches.length} categories${r.duplicates.length ? `, ${r.duplicates.length} duplicate keys` : ""})`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Callout>

      <div className="card p-4">
        <h3 className="text-base">Break down a subset</h3>
        <div className="mt-2 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <label className="text-sm">Records<select className="field mt-1 w-full" value={scope} onChange={(e) => setScope(e.target.value as "counted" | "all")}><option value="counted">Counted records</option><option value="all">All source records</option></select></label>
          <label className="text-sm">Membership group<select className="field mt-1 w-full" value={group} onChange={(e) => setGroup(e.target.value)}><option value="">Any</option>{Object.entries(GROUP_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          <label className="text-sm">Domain<select className="field mt-1 w-full" value={domain} onChange={(e) => setDomain(e.target.value)}><option value="">Any</option>{["Archaea", "Bacteria", "Eukaryota"].map((d) => <option key={d} value={d}>{d}</option>)}<option value="none">No domain assigned</option></select></label>
          <label className="text-sm">Evidence level<select className="field mt-1 w-full" value={evidence} onChange={(e) => setEvidence(e.target.value)}><option value="">Any</option>{EVIDENCE_LEVELS.map((e) => <option key={e} value={e}>{e}</option>)}</select></label>
          <label className="text-sm">Function<select className="field mt-1 w-full" value={func} onChange={(e) => setFunc(e.target.value)}><option value="">Any</option>{FUNC_ORDER.map((f) => <option key={f} value={f}>{FUNC_LABEL[f]}</option>)}</select></label>
        </div>
        <p className="mt-3 text-sm" aria-live="polite" data-testid="subset-count">
          <span className="tabular font-semibold">{fmtInt(subset.length)}</span> {scope === "counted" ? "counted" : "source"} records match. <a href={href.browse(browseQ)}>Open them in Browse</a>
        </p>
        <div className="mt-3 grid gap-4 md:grid-cols-3">
          <MiniTable title="By evidence level" n={subset.length} rows={breakdown((r) => r.evidence_level, (k) => String(k))} />
          <MiniTable title="By function" n={subset.length} rows={breakdown((r) => r.func_class, (k) => FUNC_LABEL[k as FuncClass] ?? String(k))} />
          <MiniTable title="By clade state" n={subset.length} rows={breakdown((r) => r.clade_state, (k) => CLADE_STATE_LABEL[k as keyof typeof CLADE_STATE_LABEL] ?? String(k))} />
        </div>
      </div>
    </div>
  );
}

function MiniTable({ title, n, rows }: { title: string; n: number; rows: { k: string | null; label: string; v: number }[] }) {
  return (
    <table className="data-table">
      <caption className="text-left text-sm font-semibold">{title}</caption>
      <thead><tr><th scope="col">Category</th><th scope="col" className="num">Records</th><th scope="col" className="num">%</th></tr></thead>
      <tbody>
        {rows.map((r) => <tr key={String(r.k)}><th scope="row" className="!static !bg-transparent !font-normal">{r.label}</th><td className="num">{fmtInt(r.v)}</td><td className="num">{fmtPct(r.v, n)}</td></tr>)}
      </tbody>
    </table>
  );
}
