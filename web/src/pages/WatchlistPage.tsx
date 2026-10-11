/**
 * Novel-family watchlist (#/watchlist; legacy #/novel redirects here), spec section 10.3.
 * Watchlist rows are research candidates that were NOT admitted to the corpus: the page shows only the
 * stored candidate fields (source, family flag, Foldseek provenance) and never a membership status,
 * evidence level, function or record link. Loads watchlist.json and summary.json only.
 */
import { useMemo, useState } from "react";
import { Callout, PageTitle } from "../components/common";
import { TableRegion, usePaged } from "../components/Paged";
import { Provenance, inclusionText } from "../components/Provenance";
import { ErrorState, LoadingSkeleton } from "../components/States";
import { loadSummary, loadWatchlist, useResource } from "../data/loaders";
import type { Summary, Watchlist } from "../data/types";
import { BarChart, type BarItem } from "../features/charts/BarChart";
import { Ext, downloadText } from "../features/entry/ui";
import { cat } from "../lib/chartColors";
import { fmtInt } from "../lib/format";
import { distribution, mv } from "../lib/summary";

import { watchlistTsv, type WatchlistCandidate } from "../lib/watchlist";

export default function WatchlistPage() {
  const res = useResource(() => Promise.all([loadSummary(), loadWatchlist()]));
  return (
    <div className="container-page pt-6">
      <PageTitle
        docTitle="Novel-family watchlist - MicroRhodoDB"
        lead="Structure-similarity candidates for under-represented rhodopsin families, kept for follow-up research."
      >
        Novel-family watchlist
      </PageTitle>
      {res.state === "loading" ? <LoadingSkeleton lines={6} /> : null}
      {res.state === "error" ? <ErrorState error={res.error} retry={res.retry} what="the watchlist" /> : null}
      {res.state === "ready" ? <Body summary={res.data[0]} wl={res.data[1]} /> : null}
    </div>
  );
}

const FUNNEL_LABEL: Record<string, string> = {
  ebi_n_total_hits: "EBI: total hits",
  ebi_n_included: "EBI: included",
  ebi_n_has_PF01036: "EBI: with PF01036",
  ebi_n_evalue_pass: "EBI: E-value pass",
  ebi_n_excl_known: "EBI: excluded as known",
  ebi_n_length_pass: "EBI: length pass",
  ebi_n_retinalK_pass: "EBI: retinal-lysine pass",
  ebi_n_resolved_live: "EBI: resolved (live)",
  sprot_n_raw_hits_Ele10: "Swiss-Prot: raw hits (E ≤ 10)",
  sprot_n_excl_known: "Swiss-Prot: excluded as known",
  sprot_n_length_pass: "Swiss-Prot: length pass",
  sprot_n_retinalK_pass: "Swiss-Prot: retinal-lysine pass",
  removed_resolved_acc_in_corpus: "Removed: already in corpus",
  final_combined_candidates: "Final combined candidates",
};

function Body({ summary, wl }: { summary: Summary; wl: Watchlist }) {
  const cands = wl.candidates as unknown as WatchlistCandidate[];
  const dist = distribution(summary, "watchlist_family");
  const items: BarItem[] = dist.items.slice().sort((a, b) => b.value - a.value).map((i, k) => ({ key: String(i.key), label: String(i.key), value: i.value, color: cat(k + 4) }));
  const [family, setFamily] = useState("");
  const [db, setDb] = useState("");
  const [retK, setRetK] = useState("");
  const [q, setQ] = useState("");
  const families = useMemo(() => [...new Set(cands.map((c) => c.family))].sort(), [cands]);
  const dbs = useMemo(() => [...new Set(cands.map((c) => c.source_db))].sort(), [cands]);
  const ql = q.trim().toLowerCase();
  const filtered = cands.filter((c) =>
    (!family || c.family === family) && (!db || c.source_db === db) && (!retK || String(c.has_retinalK) === retK) &&
    (!ql || [c.identifier, c.resolved_accession, c.query_accession, c.species].some((v) => v && v.toLowerCase().includes(ql))));
  const { slice, pager } = usePaged(filtered, 50, `${family}|${db}|${retK}|${ql}`);
  const funnelCols = Object.keys(FUNNEL_LABEL).filter((k) => wl.funnel.some((f) => k in f));

  return (
    <>
      <div className="mb-6 rounded-xl border-2 border-warn-line bg-warn-soft p-4" role="note" data-testid="watchlist-isolation">
        <p className="text-lg font-semibold text-[#8a3c04]">Not admitted to the corpus</p>
        <p className="mt-1 text-sm text-ink">
          {wl.isolation} These {fmtInt(mv(summary, "watchlist"))} entries are excluded from all {fmtInt(mv(summary, "records_total"))} corpus records,
          from every statistic, from Browse, from search results and from downloads of corpus data. They are not rhodopsin classifications.
        </p>
      </div>

      <Callout tone="warn" title="Not an exhaustive discovery census" testId="watchlist-caveat">
        {wl.caveat}. Because the web-server hit lists were capped, families may have further members that were never returned; absence from this list says nothing about absence in nature.
      </Callout>

      <div className="my-6 grid gap-4 lg:grid-cols-2">
        <BarChart testId="chart-watchlist-family" title="Watchlist entries by family" items={items} denominator={dist.denominator.value} denominatorLabel={summary.denominators.watchlist?.label ?? "Watchlist entries"}
          footer={<Provenance summary={summary} sql={dist.sql} denominatorId={dist.denominator.id} inclusion={inclusionText(dist.denominator.id)} />} />
        <div className="card p-4 text-sm">
          <h2 className="text-base">How candidates were found</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li>Family representatives (query accessions such as {[...new Set(cands.map((c) => c.query_accession).filter(Boolean))].slice(0, 4).join(", ")}) were searched with the Foldseek web server against {dbs.map((d) => d.replace("foldseek_web:", "")).join(" and ")}.</li>
            <li>{fmtInt(mv(summary, "foldseek_hits"))} hits survived the screening funnel (foldseek_hit); {fmtInt(cands.length)} rows were kept as watchlist candidates.</li>
            <li>“has_retinalK” records whether a retinal-binding lysine was found; “description” records why the row is on the list (as stored).</li>
          </ul>
        </div>
      </div>

      <section aria-labelledby="wl-funnel" className="mb-8">
        <h2 id="wl-funnel" className="mb-1 text-xl">Family-HMM screening funnel</h2>
        <p className="mb-3 text-sm text-ink-2">Per-family stage counts as stored in the release (EBI and Swiss-Prot searches). Shown verbatim; families can appear here with no watchlist row.</p>
        <TableRegion label="Screening funnel" testId="funnel-table">
          <table className="data-table">
            <thead><tr><th scope="col">Stage</th>{wl.funnel.map((f) => <th key={String(f.family)} scope="col" className="num">{String(f.family)}</th>)}</tr></thead>
            <tbody>
              {funnelCols.map((k) => (
                <tr key={k}>
                  <th scope="row" className="!static !bg-transparent !font-normal">{FUNNEL_LABEL[k]}<code className="block text-xs text-ink-2">{k}</code></th>
                  {wl.funnel.map((f) => <td key={String(f.family)} className="num">{f[k] === null || f[k] === undefined ? "—" : fmtInt(Number(f[k]))}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </TableRegion>
      </section>

      <section aria-labelledby="wl-cands" className="mb-8">
        <h2 id="wl-cands" className="mb-1 text-xl">Candidates</h2>
        <div className="my-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="text-sm">Identifier or species<input type="search" className="field mt-1 w-full" value={q} onChange={(e) => setQ(e.target.value)} /></label>
          <label className="text-sm">Family<select className="field mt-1 w-full" value={family} onChange={(e) => setFamily(e.target.value)} data-testid="wl-filter-family"><option value="">Any</option>{families.map((f) => <option key={f} value={f}>{f}</option>)}</select></label>
          <label className="text-sm">Source database<select className="field mt-1 w-full" value={db} onChange={(e) => setDb(e.target.value)}><option value="">Any</option>{dbs.map((d) => <option key={d} value={d}>{d}</option>)}</select></label>
          <label className="text-sm">Retinal lysine<select className="field mt-1 w-full" value={retK} onChange={(e) => setRetK(e.target.value)}><option value="">Any</option><option value="1">Found</option><option value="0">Not found</option></select></label>
        </div>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm" aria-live="polite" data-testid="wl-count"><span className="tabular font-semibold">{fmtInt(filtered.length)}</span> of {fmtInt(cands.length)} watchlist candidates</p>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => downloadText(`microrhododb_v${wl.dataset_release}_watchlist_${filtered.length}.tsv`, watchlistTsv(filtered), "text/tab-separated-values")} data-testid="wl-download">
            Download TSV ({fmtInt(filtered.length)})
          </button>
        </div>
        <TableRegion label="Watchlist candidates" testId="wl-table">
          <table className="data-table">
            <thead><tr><th scope="col">Identifier</th><th scope="col">Family flag</th><th scope="col">Source</th><th scope="col">Query</th><th scope="col" className="num">E-value</th><th scope="col" className="num">Score</th><th scope="col" className="num">Length</th><th scope="col">Retinal K</th><th scope="col">Architecture</th><th scope="col">Species</th></tr></thead>
            <tbody>
              {slice.map((c) => (
                <tr key={c.identifier}>
                  <td className="font-mono text-xs">
                    {c.source_db.endsWith("afdb50") && c.resolved_accession ? <Ext href={`https://www.uniprot.org/uniprotkb/${encodeURIComponent(c.resolved_accession)}`}>{c.identifier}</Ext> : c.identifier}
                  </td>
                  <td>{c.family}<span className="block text-xs text-ink-2">{c.description}</span></td>
                  <td className="text-xs">{c.source_db}</td>
                  <td className="font-mono text-xs">{c.query_accession ?? "—"}</td>
                  <td className="num">{c.evalue === null ? "—" : c.evalue.toExponential(1)}</td>
                  <td className="num">{c.score ?? "—"}</td>
                  <td className="num">{c.seq_length ?? "—"}</td>
                  <td>{c.has_retinalK === 1 ? "found" : c.has_retinalK === 0 ? "not found" : "—"}</td>
                  <td className="max-w-[14rem] text-xs">{c.architecture ?? "—"}</td>
                  <td className="text-xs italic">{c.species ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableRegion>
        <div className="mt-3">{pager}</div>
      </section>
    </>
  );
}
