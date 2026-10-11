/**
 * Unified search (#/search), spec section 9.
 *  - Text mode (?q=): identifier / PDB / clade / motif / function / free-text search over records-index.json,
 *    reporting the field that matched each record (features/search/textSearch.ts).
 *  - Sequence mode (?mode=sequence): the legacy browser sequence search (3-mer prefilter + Smith-Waterman,
 *    BLOSUM62, top 10) run in a Web Worker. It is a similarity lookup against the corpus sequences only:
 *    it is not exhaustive and it never computes the official membership score.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { replaceHash } from "../app/navigation";
import { href } from "../app/routes";
import { EvidenceBadge, FlagBadge, FunctionLabel, MembershipBadge } from "../components/Badges";
import { Callout, PageTitle } from "../components/common";
import { TableRegion } from "../components/Paged";
import { EmptyState, ErrorState, LoadingSkeleton } from "../components/States";
import { loadRecord, loadRecordsIndex, releaseFileUrl, useResource } from "../data/loaders";
import { Ext } from "../features/entry/ui";
import { SearchClient } from "../features/search/client";
import type { Phase, WorkerResult } from "../features/search/protocol";
import { METHOD, parseQuery, type QueryError } from "../features/search/swCore";
import { FIELD_LABEL, fieldCounts, textSearch } from "../features/search/textSearch";
import { toRows, type IndexRow } from "../lib/browse";
import { fmtInt } from "../lib/format";

const TEXT_EXAMPLES = ["P02945", "MRDB000001", "1C3W", "MR_CLD3_017", "DTE", "bacteriorhodopsin", "Halobacterium"];

/** records-index rows, converted once per page lifetime. */
let rowsPromise: Promise<IndexRow[]> | null = null;
const loadRows = () => (rowsPromise ??= loadRecordsIndex().then(toRows).catch((e) => { rowsPromise = null; throw e; }));

export default function SearchPage({ params }: { params: URLSearchParams }) {
  const mode = params.get("mode") === "sequence" ? "sequence" : "text";
  const q = params.get("q") ?? "";
  const setMode = (m: "text" | "sequence") => replaceHash(href.section("search", m === "sequence" ? "mode=sequence" : q ? `q=${encodeURIComponent(q)}` : ""));
  return (
    <div className="container-page pt-6">
      <PageTitle docTitle="Search - MicroRhodoDB" lead="Find corpus records by identifier, PDB entry, clade, motif or text, or compare a protein sequence with the corpus sequences.">
        Search
      </PageTitle>
      <div role="tablist" aria-label="Search mode" className="mb-5 flex gap-2">
        {(["text", "sequence"] as const).map((m) => (
          <button key={m} type="button" role="tab" aria-selected={mode === m} data-testid={`mode-${m}`}
            className={`btn btn-sm ${mode === m ? "btn-primary" : "btn-secondary"}`} onClick={() => setMode(m)}>
            {m === "text" ? "Text and identifiers" : "Protein sequence"}
          </button>
        ))}
      </div>
      {mode === "text" ? <TextMode q={q} /> : <SequenceMode />}
    </div>
  );
}

/* ------------------------------------------------------------------------------------------- text */

function TextMode({ q }: { q: string }) {
  const [draft, setDraft] = useState(q);
  useEffect(() => setDraft(q), [q]);
  const submit = (v: string) => replaceHash(href.section("search", v.trim() ? `q=${encodeURIComponent(v.trim())}` : ""));
  return (
    <section aria-labelledby="text-search-h">
      <h2 id="text-search-h" className="sr-only">Text search</h2>
      <form role="search" aria-label="Text search" className="flex max-w-3xl gap-2" onSubmit={(e) => { e.preventDefault(); submit(draft); }}>
        <label htmlFor="text-q" className="sr-only">Search text</label>
        <input id="text-q" type="search" className="field min-w-0 flex-1" value={draft} onChange={(e) => setDraft(e.target.value)}
          placeholder="MRDB ID, UniProt accession, PDB ID, clade ID, helix-C motif, protein or organism" autoComplete="off" spellCheck={false} data-testid="text-q" />
        <button type="submit" className="btn btn-primary shrink-0" data-testid="text-submit">Search</button>
      </form>
      <p className="mt-2 text-sm text-ink-2">
        Examples:{" "}
        {TEXT_EXAMPLES.map((x, i) => (
          <span key={x}>{i ? ", " : ""}<a href={href.section("search", `q=${encodeURIComponent(x)}`)}>{x}</a></span>
        ))}
      </p>
      {q ? <TextResults q={q} /> : (
        <div className="mt-6 max-w-3xl text-sm text-ink-2">
          <p>The search covers the corpus records in records-index.json. Identifiers match exactly (accessions also by prefix); PDB IDs match only the stored protein-PDB links; clade and subclade IDs match placements; free text matches protein names, organisms, clade names, NCBI lineage and GTDB taxonomy.</p>
          <p className="mt-2">Watchlist candidates are not corpus records and are not searched here; see the <a href={href.section("watchlist")}>novel-family watchlist</a>.</p>
        </div>
      )}
    </section>
  );
}

function TextResults({ q }: { q: string }) {
  const res = useResource(loadRows, []);
  if (res.state === "loading") return <div className="mt-6"><LoadingSkeleton label="Loading the record index" /></div>;
  if (res.state === "error") return <div className="mt-6"><ErrorState error={res.error} retry={res.retry} what="the record index" /></div>;
  return <TextHits rows={res.data} q={q} />;
}

function TextHits({ rows, q }: { rows: IndexRow[]; q: string }) {
  const r = useMemo(() => textSearch(rows, q), [rows, q]);
  const browse = href.browse(new URLSearchParams({ group: "all", eng: "1", q }).toString());
  if (r.kind === "too_short") return <p className="mt-6" data-testid="text-status">Enter at least 2 characters.</p>;
  if (!r.total) {
    return (
      <div className="mt-6" data-testid="text-status">
        <EmptyState title={`No corpus record matches “${r.query}”`}>
          <p>Check the spelling, try a shorter fragment, or use <a href={href.section("search", "mode=sequence")}>sequence search</a>. Identifiers that are not in the v1.6.0 corpus (including watchlist candidates) are not found here.</p>
        </EmptyState>
      </div>
    );
  }
  const fc = fieldCounts(r.hits);
  return (
    <div className="mt-6">
      <p data-testid="text-status" className="text-sm">
        <strong data-testid="text-total">{fmtInt(r.total)}</strong> record{r.total === 1 ? "" : "s"} match “{r.query}” out of {fmtInt(rows.length)} corpus records
        {r.truncated ? <> (showing the {fmtInt(r.hits.length)} best-ranked; <a href={browse}>open all text matches in Browse</a> for filtering and export)</> : null}.
        {" "}Matched in: {fc.map(([f, n]) => `${FIELD_LABEL[f]} (${fmtInt(n)})`).join(", ")}{r.truncated ? " among those shown" : ""}.
      </p>
      <TableRegion label="Text search results" testId="text-results">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Record</th><th scope="col">Protein</th><th scope="col">Organism</th>
              <th scope="col">Membership</th><th scope="col">Evidence</th><th scope="col">Function</th><th scope="col">Matched field</th>
            </tr>
          </thead>
          <tbody>
            {r.hits.map((h) => (
              <tr key={h.row.source_acc} data-testid={`text-hit-${h.row.source_acc}`}>
                <td><a href={href.record(h.row.mrdb_acc)} className="font-mono">{h.row.mrdb_acc}</a><span className="block font-mono text-xs text-ink-2">{h.row.source_acc}</span>
                  {h.row.is_engineered ? <FlagBadge tone="warn">engineered</FlagBadge> : null}</td>
                <td>{h.row.protein_name ?? "—"}</td>
                <td className="italic">{h.row.organism ?? "—"}</td>
                <td><MembershipBadge status={h.row.membership_status} /></td>
                <td><EvidenceBadge level={h.row.evidence_level} /></td>
                <td><FunctionLabel func={h.row.func_class} /></td>
                <td className="text-sm" data-field={h.field}><span className="font-medium">{FIELD_LABEL[h.field]}</span><span className="block max-w-[22rem] truncate text-xs text-ink-2" title={h.value}>{h.value}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableRegion>
    </div>
  );
}

/* --------------------------------------------------------------------------------------- sequence */

const PHASE_LABEL: Record<Phase, string> = {
  load: "Loading corpus sequences",
  prefilter: "3-mer prefilter",
  align: "Smith-Waterman scoring of prefiltered candidates",
  traceback: "Computing alignments for the top hits",
};

type SeqState =
  | { s: "idle" }
  | { s: "invalid"; error: QueryError }
  | { s: "running"; phase: Phase; done: number; total: number }
  | { s: "cancelled" }
  | { s: "error"; message: string }
  | { s: "done"; result: WorkerResult; ms: number; warnings: string[]; header: string | null };

function SequenceMode() {
  const [text, setText] = useState("");
  const [st, setSt] = useState<SeqState>({ s: "idle" });
  const [rows, setRows] = useState<IndexRow[] | null>(null);
  const [exampleErr, setExampleErr] = useState<string | null>(null);
  const client = useRef<SearchClient | null>(null);
  useEffect(() => () => client.current?.dispose(), []);

  const getClient = () =>
    (client.current ??= new SearchClient(
      () => releaseFileUrl("sequences/corpus.fasta"),
      async () => {
        const r = await loadRows();
        setRows(r);
        return { accs: r.map((x) => x.source_acc), reviewed: r.map((x) => Number(x.reviewed ?? 0)), rep: r.map((x) => Number(x.is_mrdb_representative ?? 0)) };
      },
    ));

  const run = async () => {
    const p = parseQuery(text);
    if (!p.ok) { setSt({ s: "invalid", error: p.error }); return; }
    setSt({ s: "running", phase: "load", done: 0, total: 1 });
    try {
      const { result, ms } = await getClient().search(p.sequence, (phase, done, total) => setSt({ s: "running", phase, done, total }));
      setSt({ s: "done", result, ms, warnings: p.warnings, header: p.header });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setSt(msg === "cancelled" ? { s: "cancelled" } : { s: "error", message: msg });
    }
  };

  const example = async () => {
    setExampleErr(null);
    try {
      const e = await loadRecord("MRDB000001");
      const src = e?.sources.find((s) => s.source_acc === "P02945");
      if (!src) throw new Error("P02945 not found in MRDB000001");
      setText(`>P02945 bacteriorhodopsin (example)\n${src.sequence}`);
      setSt({ s: "idle" });
    } catch (err) {
      setExampleErr(err instanceof Error ? err.message : String(err));
    }
  };

  const running = st.s === "running";
  return (
    <section aria-labelledby="seq-h">
      <h2 id="seq-h" className="sr-only">Sequence search</h2>
      <MethodCallout />
      <div className="mt-4 max-w-4xl">
        <label htmlFor="seq-input" className="block text-sm font-medium">Protein sequence (plain text or one FASTA record)</label>
        <textarea id="seq-input" className="field mt-1 h-40 w-full font-mono text-sm" value={text} onChange={(e) => setText(e.target.value)}
          spellCheck={false} data-testid="seq-input" data-length={text.length} aria-describedby="seq-help" />
        <p id="seq-help" className="mt-1 text-xs text-ink-2">
          {METHOD.minLength}–{fmtInt(METHOD.maxLength)} residues; one query at a time. Digits, whitespace and gap characters are ignored, as in the legacy search.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" className="btn btn-primary" onClick={run} disabled={running} data-testid="seq-run">Search corpus sequences</button>
          {running ? <button type="button" className="btn btn-secondary" onClick={() => client.current?.cancel()} data-testid="seq-cancel">Cancel</button> : null}
          <button type="button" className="btn btn-secondary" onClick={example} disabled={running} data-testid="seq-example">Load example (P02945)</button>
          <button type="button" className="btn btn-secondary" onClick={() => { setText(""); setSt({ s: "idle" }); }} disabled={running}>Clear</button>
        </div>
        {exampleErr ? <p className="mt-2 text-sm text-[#8a3c04]" role="alert">Could not load the example: {exampleErr}</p> : null}
      </div>
      <div className="mt-6" aria-live="polite" data-testid="seq-status">
        {st.s === "running" ? (
          <p className="text-sm" data-testid="seq-progress">
            {PHASE_LABEL[st.phase]}{st.phase !== "load" && st.total > 1 ? ` (${fmtInt(st.done)} of ${fmtInt(st.total)})` : ""}. The search runs in a background worker; the page stays responsive.
          </p>
        ) : null}
        {st.s === "invalid" ? <Callout tone="warn" title="Query not searched" testId="seq-invalid"><span data-code={st.error.code}>{st.error.message}</span></Callout> : null}
        {st.s === "cancelled" ? <p className="text-sm" data-testid="seq-cancelled">Search cancelled. No results are shown.</p> : null}
        {st.s === "error" ? (
          <Callout tone="warn" title="The browser search failed" testId="seq-error">
            <p>{st.message}</p>
            <Fallback />
          </Callout>
        ) : null}
        {st.s === "done" ? <SeqResults st={st} rows={rows} /> : null}
      </div>
    </section>
  );
}

function Fallback() {
  return (
    <p className="mt-2 text-sm">
      Alternatives: download corpus.fasta from <a href={href.section("downloads")}>Downloads</a> and search it with BLAST or DIAMOND, or run <code>tools/mrdb_search.py</code> from the{" "}
      <Ext href="https://github.com/CongjianL/MicroRhodoDB">repository</Ext> against the release database.
    </p>
  );
}

function MethodCallout() {
  return (
    <Callout tone="info" title="What this search does, and what it does not" testId="seq-method">
      <ul className="list-disc space-y-1 pl-5">
        <li>Method: {METHOD.label}; {METHOD.legacy}. Results are ranked by alignment score, ties broken by reviewed status, MRDB representative and accession.</li>
        <li>It compares your sequence with the corpus sequences only. Only the {METHOD.prefilter} subjects sharing the most distinct 3-mers are aligned, so it is <strong>not exhaustive</strong>: a distant homolog can be missed, and absence from the top {METHOD.top} is not evidence that no related record exists.</li>
        <li data-testid="seq-not-classifier">It <strong>does not compute the official membership score</strong> and does not classify your query. Membership, evidence and function shown for hits belong to the corpus records, not to the query.</li>
        <li data-testid="seq-cli">
          To score a query with the frozen membership scorer, use the command-line tool <code>tools/mrdb_search.py</code> (requires HMMER 3.4 and DIAMOND). It reports a membership score, a
          provisional status that approximates the release rules (the architecture route and curator overrides are not re-evaluated) and a DIAMOND nearest neighbour over the whole release.
          For your own all-against-all searches, download corpus.fasta from <a href={href.section("downloads")}>Downloads</a>.
        </li>
      </ul>
    </Callout>
  );
}

function SeqResults({ st, rows }: { st: Extract<SeqState, { s: "done" }>; rows: IndexRow[] | null }) {
  const { result, ms, warnings, header } = st;
  const [open, setOpen] = useState<number | null>(null);
  return (
    <div data-testid="seq-results">
      {warnings.length ? (
        <Callout tone="warn" title="Input notes" testId="seq-warnings"><ul className="list-disc pl-5">{warnings.map((w) => <li key={w}>{w}</li>)}</ul></Callout>
      ) : null}
      <p className="my-3 text-sm" data-testid="seq-summary">
        Query{header ? <> <code>{header.slice(0, 60)}</code></> : null}: {fmtInt(result.queryLength)} residues. {fmtInt(result.prefiltered)} of {fmtInt(result.nSubjects)} corpus sequences passed the 3-mer prefilter and were aligned; top {fmtInt(result.hits.length)} shown ({(ms / 1000).toFixed(1)} s).
      </p>
      {result.hits.length === 0 ? <EmptyState title="No alignment">No prefiltered sequence produced a positive local alignment score. <Fallback /></EmptyState> : (
        <TableRegion label="Sequence search hits" testId="seq-table">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col" className="num">Rank</th><th scope="col">Record</th><th scope="col">Protein / organism</th>
                <th scope="col" className="num">Identity</th><th scope="col" className="num">Query cov.</th><th scope="col" className="num">Subject cov.</th>
                <th scope="col" className="num">Score</th><th scope="col">Aligned region</th><th scope="col">Corpus record annotation</th><th scope="col"><span className="sr-only">Alignment</span></th>
              </tr>
            </thead>
            <tbody>
              {result.hits.map((h) => {
                const r = rows?.[h.idx];
                const ok = r && r.source_acc === h.source_acc;
                return (
                  <FragmentRow key={h.rank} open={open === h.rank} colSpan={10} alignment={<AlignmentBlock h={h} />}>
                    <tr data-testid={`seq-hit-${h.rank}`} data-acc={h.source_acc} data-identity={h.identity}>
                      <td className="num">{h.rank}</td>
                      <td>{ok ? <a href={href.record(r.mrdb_acc)} className="font-mono">{r.mrdb_acc}</a> : null}<span className="block font-mono text-xs">{h.source_acc}</span></td>
                      <td>{ok ? <>{r.protein_name ?? "—"}<span className="block text-xs italic text-ink-2">{r.organism ?? ""}</span></> : "—"}</td>
                      <td className="num">{(100 * h.identity).toFixed(1)}%</td>
                      <td className="num">{(100 * h.qcov).toFixed(1)}%</td>
                      <td className="num">{(100 * h.scov).toFixed(1)}%</td>
                      <td className="num">{h.score}</td>
                      <td className="whitespace-nowrap text-xs">query {h.qStart}–{h.qEnd}<br />subject {h.sStart}–{h.sEnd}</td>
                      <td>{ok ? <span className="flex flex-wrap gap-1"><MembershipBadge status={r.membership_status} /><EvidenceBadge level={r.evidence_level} /></span> : null}</td>
                      <td><button type="button" className="btn btn-secondary btn-sm" aria-expanded={open === h.rank} onClick={() => setOpen(open === h.rank ? null : h.rank)} data-testid={`seq-aln-toggle-${h.rank}`}>{open === h.rank ? "Hide" : "Alignment"}</button></td>
                    </tr>
                  </FragmentRow>
                );
              })}
            </tbody>
          </table>
        </TableRegion>
      )}
      <p className="mt-2 text-xs text-ink-2">Identity = identical positions / alignment length ({"\u201c"}|{"\u201d"} in the alignment); coverage = aligned residues / sequence length. The annotation column describes the matched corpus record, not your query.</p>
    </div>
  );
}

function FragmentRow({ children, open, colSpan, alignment }: { children: React.ReactNode; open: boolean; colSpan: number; alignment: React.ReactNode }) {
  return (
    <>
      {children}
      {open ? <tr><td colSpan={colSpan} className="!bg-surface-2">{alignment}</td></tr> : null}
    </>
  );
}

function AlignmentBlock({ h }: { h: { qAln: string; mid: string; sAln: string; qStart: number; sStart: number; alen: number } }) {
  const W = 60;
  const blocks: React.ReactNode[] = [];
  let qi = h.qStart;
  let si = h.sStart;
  for (let i = 0; i < h.qAln.length; i += W) {
    const qa = h.qAln.slice(i, i + W);
    const ma = h.mid.slice(i, i + W);
    const sa = h.sAln.slice(i, i + W);
    const qn = qa.replace(/-/g, "").length;
    const sn = sa.replace(/-/g, "").length;
    blocks.push(
      <pre key={i} className="mb-2 font-mono text-xs leading-tight">
        {`Query   ${String(qi).padStart(5)} ${qa} ${qi + qn - 1}\n                ${ma}\nSubject ${String(si).padStart(5)} ${sa} ${si + sn - 1}`}
      </pre>,
    );
    qi += qn;
    si += sn;
  }
  return <div className="relative overflow-x-auto" data-testid="seq-alignment">{blocks}</div>;
}
