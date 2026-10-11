/**
 * Methods (#/methods; ?s=<section> deep links), spec section 10.5. Every rule, definition and number
 * on this page is read from the exported data files (vocabulary, clades, evidence-index, manifest,
 * summary, structures-index, watchlist, downloads) or from the search module constants; nothing is
 * paraphrased into new method claims. Longer narrative lives in the repository documents linked below.
 */
import { href } from "../app/routes";
import { Callout, PageTitle } from "../components/common";
import { TableRegion } from "../components/Paged";
import { ErrorState, LoadingSkeleton } from "../components/States";
import { useSectionScroll } from "../components/useSectionScroll";
import {
  loadClades, loadDownloads, loadEvidenceIndex, loadManifest, loadStructuresIndex, loadSummary, loadVocabulary, loadWatchlist, useResource,
} from "../data/loaders";
import type { Clades, Downloads, EvidenceIndex, Manifest, StructuresIndex, Summary, Vocabulary, Watchlist } from "../data/types";
import { Ext } from "../features/entry/ui";
import { METHOD } from "../features/search/swCore";
import { FUNC_LABEL, STATUS_LABEL, fmtInt } from "../lib/format";

const SECTIONS: [string, string][] = [
  ["data", "Data source"], ["membership", "Membership"], ["evidence", "Evidence levels"], ["function", "Function calls"],
  ["phylogeny", "Clades and placement"], ["structures", "Structures"], ["watchlist", "Watchlist"], ["validation", "Validation"],
  ["search", "Browser search"], ["statistics", "Statistics"], ["docs", "Documentation"],
];

async function load() {
  return Promise.all([loadManifest(), loadSummary(), loadVocabulary(), loadClades(), loadEvidenceIndex(), loadStructuresIndex(), loadWatchlist(), loadDownloads()]);
}

export default function MethodsPage({ params }: { params: URLSearchParams }) {
  const res = useResource(load, []);
  useSectionScroll(params, "m-", res.state === "ready");
  return (
    <div className="container-page pt-6">
      <PageTitle docTitle="Methods - MicroRhodoDB" lead="How the records, evidence levels, clades and statistics shown on this website were produced. All rules are quoted from the release.">
        Methods
      </PageTitle>
      <nav aria-label="On this page" className="mb-6 flex flex-wrap gap-2 text-sm">
        {SECTIONS.map(([id, l]) => <a key={id} className="btn btn-secondary btn-sm" href={href.section("methods", `s=${id}`)}>{l}</a>)}
      </nav>
      {res.state === "loading" ? <LoadingSkeleton lines={10} /> : null}
      {res.state === "error" ? <ErrorState error={res.error} retry={res.retry} what="the methods data" /> : null}
      {res.state === "ready" ? <Body d={res.data} /> : null}
    </div>
  );
}

function Sec({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={`m-${id}`} aria-labelledby={`m-${id}-h`} className="mb-10 max-w-5xl scroll-mt-20" data-testid={`methods-${id}`}>
      <h2 id={`m-${id}-h`} className="mb-2 text-xl">{title}</h2>
      <div className="space-y-3 text-sm leading-relaxed">{children}</div>
    </section>
  );
}

const Q = ({ children }: { children: React.ReactNode }) => <blockquote className="border-l-4 border-line pl-3 text-ink-2">{children}</blockquote>;

function Body({ d }: { d: [Manifest, Summary, Vocabulary, Clades, EvidenceIndex, StructuresIndex, Watchlist, Downloads] }) {
  const [m, s, v, c, ev, st, wl, dl] = d;
  const repo = dl.citation["repository-code"] ?? "https://github.com/CongjianL/MicroRhodoDB";
  const doc = (p: string) => `${repo}/blob/${dl.release.tag}/${p}`;
  const den = s.denominators;
  const val = ev.validation;
  return (
    <>
      <Sec id="data" title="Data source">
        <p>
          Every page is generated from the read-only release database <code>{m.source_db.file}</code> (SHA-256 <code className="break-all text-xs">{m.source_db.sha256}</code>),
          data release {m.dataset_release} (schema revision {m.schema_revision}), by <code>{m.exporter.path}</code>. The export is deterministic ({m.timestamps}).
          The website computes no new classification, function call, clade assignment or membership score.
        </p>
        <p>
          The corpus has {fmtInt(den.all_records.value)} source records; {fmtInt(den.counted_records.value)} are counted in statistics ({s.notes.find((n) => n.startsWith("Counted")) ?? ""}),
          grouped into {fmtInt(den.mrdb_accessions.value)} MRDB accessions (identical sequences share one accession).
        </p>
      </Sec>

      <Sec id="membership" title="Membership status">
        <p>Membership status is stored per source record and is the only authority for “member” and “candidate”. Definitions as stored in the release:</p>
        <TableRegion label="Membership status definitions" testId="methods-status-table">
          <table className="data-table">
            <thead><tr><th scope="col">Status</th><th scope="col">Group</th><th scope="col">Definition</th></tr></thead>
            <tbody>{v.membership_status.map((x) => (
              <tr key={x.status}><td><span className="font-medium">{STATUS_LABEL[x.status as keyof typeof STATUS_LABEL] ?? x.status}</span><code className="block text-xs text-ink-2">{x.status}</code></td><td>{x.group}</td><td className="min-w-[24rem]">{x.definition}</td></tr>
            ))}</tbody>
          </table>
        </TableRegion>
      </Sec>

      <Sec id="evidence" title="Function evidence levels (E1–E5)">
        <Q>{v.evidence_level_source.text}</Q>
        <p className="font-medium">{v.evidence_note}</p>
        <ul className="list-disc pl-5">{v.evidence_level.map((e) => <li key={e.level}><strong>{e.level}</strong>: {e.definition}</li>)}</ul>
        <p>Engineered constructs: <Q>{ev.engineered_policy}</Q></p>
        <p>Records, overrides and publications for each level: <a href={href.section("evidence")}>Evidence Explorer</a>.</p>
      </Sec>

      <Sec id="function" title="Function classes and conflicts">
        <ul className="list-disc pl-5">{v.func_class.map((f) => <li key={f.func_class}><strong>{FUNC_LABEL[f.func_class as keyof typeof FUNC_LABEL] ?? f.func_class}</strong> (<code>{f.func_class}</code>): {f.definition}</li>)}</ul>
        <p>Function-call conflict rule, as stored:</p>
        <Q>{ev.function_conflict_rule}</Q>
        <p>{fmtInt(Object.keys(ev.override_rules).length)} curated override rules are applied in the release; their member records are listed in the <a href={href.section("evidence", "s=rules")}>Evidence Explorer</a>.</p>
      </Sec>

      <Sec id="phylogeny" title="Clades and phylogenetic placement">
        <p>Reference tree {c.tree_id}, clade scheme {c.scheme} ({c.display}).</p>
        <ul className="list-disc pl-5">
          <li>Level-1 clades: {c.clade_rule.level1.min_tips}–{c.clade_rule.level1.max_tips} tips, SH-aLRT ≥ {c.clade_rule.level1.min_sh_alrt} and UFBoot ≥ {c.clade_rule.level1.min_ufboot}, {c.clade_rule.level1.rooting} rooting.</li>
          <li>Backbone groups: {c.clade_rule.backbone_group}.</li>
          <li>Subclades: {c.clade_rule.subclade.min_tips}–{c.clade_rule.subclade.max_tips} tips, SH-aLRT ≥ {c.clade_rule.subclade.min_sh_alrt} and UFBoot ≥ {c.clade_rule.subclade.min_ufboot}.</li>
          <li>Support test: {c.clade_rule.support_test}. {c.support_display}</li>
          <li>Robustness caveat: {c.robustness_caveat_rule}</li>
          <li>Rule sources: {c.clade_rule.source.join("; ")}.</li>
        </ul>
        <p>Clade states of records:</p>
        <ul className="list-disc pl-5">{v.clade_state.map((x) => <li key={x.state}><code>{x.state}</code>: {x.definition}</li>)}</ul>
        <p>Tentative placements are shown separately from clade assignments everywhere on this website. Tree and clade pages: <a href={href.phylogeny()}>Phylogeny</a>.</p>
      </Sec>

      <Sec id="structures" title="Structures">
        <ul className="list-disc pl-5">
          <li>Experimental structures: {fmtInt(den.pdb_entries.value)} PDB entries in {fmtInt(den.pdb_links.value)} record–PDB links, as stored in the release (protein_pdb).</li>
          <li>Chain mapping: {st.chain_mapping}.</li>
          <li>AlphaFold DB models are linked by accession using <code>{st.afdb_url_template}</code>; the model is fetched from AlphaFold DB only when you open it.</li>
          <li>Predicted models distributed with the release: {st.predicted.map((p) => `${p.source_acc} (${p.method}; stored note: “${p.note}”)`).join("; ")}. Where the stored method and note disagree, the record page shows a provenance warning instead of choosing one.</li>
        </ul>
      </Sec>

      <Sec id="watchlist" title="Novel-family watchlist">
        <Q>{wl.isolation}</Q>
        <Q>{wl.caveat}</Q>
        <p>See the <a href={href.section("watchlist")}>watchlist</a>. Watchlist rows never enter any corpus statistic.</p>
      </Sec>

      <Sec id="validation" title="Validation">
        <p>{val.note} Confidence intervals: {val.ci_method}</p>
        <p>Blind audit of function calls (agreement of the release call with a blind annotator, per tier):</p>
        <TableRegion label="Blind audit agreement" testId="methods-audit-table">
          <table className="data-table">
            <thead><tr><th scope="col">Tier</th><th scope="col">Metric</th><th scope="col" className="num">Agree / n</th><th scope="col" className="num">Agreement (95% CI)</th><th scope="col">Note</th></tr></thead>
            <tbody>{val.audit_agreement.map((a, i) => (
              <tr key={i}><td>{String(a.tier)}</td><td><code className="text-xs">{String(a.metric)}</code></td><td className="num">{fmtInt(Number(a.n_match))} / {fmtInt(Number(a.n))}</td>
                <td className="num">{(100 * Number(a.agreement)).toFixed(1)}% ({(100 * Number(a.wilson_lo)).toFixed(1)}–{(100 * Number(a.wilson_hi)).toFixed(1)})</td><td className="text-xs">{String(a.note ?? "")}</td></tr>
            ))}</tbody>
          </table>
        </TableRegion>
        <p>Leave-one-clade-out (LOCO) benchmark of clade-based function transfer: {fmtInt(val.loco.length)} rows (variant {[...new Set(val.loco.map((r) => String(r.variant)))].join(", ")}; policies {[...new Set(val.loco.map((r) => String(r.policy)))].join(", ")}). Full table: <a href={href.section("evidence", "s=validation")}>Evidence Explorer: validation</a>.</p>
        <details className="text-xs"><summary className="cursor-pointer">SQL</summary><pre className="whitespace-pre-wrap">{val.audit_sql}{"\n"}{val.loco_sql}</pre></details>
      </Sec>

      <Sec id="search" title="Browser search">
        <ul className="list-disc pl-5">
          <li>Text search matches identifiers exactly (accessions also by prefix), PDB IDs against stored record–PDB links only, clade and subclade IDs against placements, and free text against protein name, organism, clade name, NCBI lineage and GTDB taxonomy. Each result names the field that matched.</li>
          <li>Sequence search: {METHOD.label}; {METHOD.legacy}. Queries of {METHOD.minLength}–{fmtInt(METHOD.maxLength)} residues; runs in a Web Worker.</li>
          <li>The sequence search is not exhaustive (only {METHOD.prefilter} prefiltered subjects are aligned) and does not compute the membership score. <code>tools/mrdb_search.py</code> applies the frozen scorer and a DIAMOND nearest-neighbour search.</li>
        </ul>
        <p><a href={href.section("search")}>Open Search</a></p>
      </Sec>

      <Sec id="statistics" title="Statistics and denominators">
        <p>Every chart states its denominator and the SQL that produced it. Denominators used on this website:</p>
        <TableRegion label="Denominators" testId="methods-denominators">
          <table className="data-table">
            <thead><tr><th scope="col">Denominator</th><th scope="col" className="num">Value</th><th scope="col">SQL</th></tr></thead>
            <tbody>{Object.values(den).map((x) => <tr key={x.id}><td>{x.label}<code className="block text-xs text-ink-2">{x.id}</code></td><td className="num">{fmtInt(x.value)}</td><td><code className="whitespace-pre-wrap text-xs">{x.sql}</code></td></tr>)}</tbody>
          </table>
        </TableRegion>
        <Callout tone="info" title="Display aggregation">For readability, the phylum and helix-C motif charts show the largest categories and fold the rest into “Other”; totals and denominators are unchanged. <a href={href.section("statistics")}>Statistics</a> can recount every chart from the record index.</Callout>
      </Sec>

      <Sec id="docs" title="Documentation">
        <ul className="list-disc space-y-1.5 pl-5">
          <li><Ext href={doc("docs/SCIENTIFIC_SCOPE.md")}>Scientific scope</Ext> (design history and current-state notes)</li>
          <li><Ext href={doc("docs/DATA_MODEL.md")}>Data model</Ext> and the <Ext href={doc("releases/v1.6.0/tables/data_dictionary_v160.tsv")}>data dictionary</Ext></li>
          <li><Ext href={doc("docs/BUILD_PIPELINE.md")}>Build pipeline</Ext> and <Ext href={doc("docs/LEGACY_AND_MISSING_COMPONENTS.md")}>legacy and missing components</Ext></li>
          <li><Ext href={doc(`releases/${dl.release.tag}/RELEASE_NOTES_${dl.release.tag}.md`)}>Release notes {dl.release.tag}</Ext></li>
          <li><Ext href={doc("refpkg/MR_RT_003/README.md")}>Reference package MR_RT_003</Ext></li>
        </ul>
      </Sec>
    </>
  );
}
