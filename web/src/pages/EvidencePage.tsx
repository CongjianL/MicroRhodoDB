/**
 * Evidence explorer (#/evidence), spec section 10.2. Evidence level (E1-E5) and the basis of the
 * function call are explored separately from membership status. Conflicts are shown as
 * original / motif / decision / current call, not as colour only. Validation tables are copied
 * verbatim from the release database by the exporter.
 *
 * Light data (summary, vocabulary, evidence-index, publications) renders first; the records index
 * (needed for the record and conflict tables) loads in the background.
 */
import { useSectionScroll } from "../components/useSectionScroll";
import { useMemo, useState } from "react";
import { replaceHash } from "../app/navigation";
import { href } from "../app/routes";
import { EvidenceBadge, FlagBadge, FunctionLabel, MembershipBadge } from "../components/Badges";
import { Callout, PageTitle } from "../components/common";
import { TableRegion, usePaged } from "../components/Paged";
import { Provenance, inclusionText } from "../components/Provenance";
import { ErrorState, LoadingSkeleton } from "../components/States";
import { loadEvidenceIndex, loadPublications, loadRecordsIndex, loadSummary, loadVocabulary, useResource, type Resource } from "../data/loaders";
import type { EvidenceIndex, EvidenceLevel, FuncClass, Publications, RecordsIndex, Summary, Vocabulary } from "../data/types";
import { Ext } from "../features/entry/ui";
import { toRows, type IndexRow } from "../lib/browse";
import { EVIDENCE_LEVELS, FUNC_LABEL, GROUP_LABEL, fmtInt } from "../lib/format";
import { BASIS_ORDER, actionLabel, basisCategory, basisLabel, matrix, parseConflictDetail } from "../lib/stats";
import { metric, mv } from "../lib/summary";

type PubRef = { pmid: string | null; doi: string | null; role: string; support: boolean };

export default function EvidencePage({ params }: { params: URLSearchParams }) {
  const light = useResource(() => Promise.all([loadSummary(), loadVocabulary(), loadEvidenceIndex(), loadPublications()]));
  const index = useResource(loadRecordsIndex);
  return (
    <div className="container-page pt-6">
      <PageTitle
        docTitle="Evidence explorer - MicroRhodoDB"
        lead="How each function call is supported (E1–E5 and the call basis), where calls conflict with sequence motifs, which membership calls were curated, and how the evidence ladder was validated."
      >
        Evidence explorer
      </PageTitle>
      {light.state === "loading" ? <LoadingSkeleton lines={8} /> : null}
      {light.state === "error" ? <ErrorState error={light.error} retry={light.retry} what="evidence data" /> : null}
      {light.state === "ready" ? (
        <EvidenceBody summary={light.data[0]} vocab={light.data[1]} ev={light.data[2]} pubs={light.data[3]} index={index} params={params} />
      ) : null}
    </div>
  );
}

function pubMap(p: Publications): Map<string, PubRef[]> {
  const m = new Map<string, PubRef[]>();
  for (const l of p.links) {
    const acc = (l as { source_acc?: string }).source_acc;
    if (!acc) continue;
    const arr = m.get(acc) ?? [];
    arr.push({ pmid: l.pmid, doi: l.doi, role: l.link_role, support: l.counts_as_support });
    m.set(acc, arr);
  }
  return m;
}

function PubRefs({ refs }: { refs: PubRef[] | undefined }) {
  if (!refs?.length) return <span className="text-ink-2">none</span>;
  const seen = new Set<string>();
  const uniq = refs.filter((r) => {
    const k = r.pmid ?? r.doi ?? "";
    if (!k || seen.has(k)) return false;
    seen.add(k);
    return true;
  });
  return (
    <span className="flex flex-wrap gap-x-2 gap-y-0.5">
      {uniq.slice(0, 4).map((r) =>
        r.pmid ? <Ext key={r.pmid} href={`https://pubmed.ncbi.nlm.nih.gov/${r.pmid}/`}>PMID {r.pmid}</Ext> : <Ext key={r.doi!} href={`https://doi.org/${r.doi}`}>DOI</Ext>,
      )}
      {uniq.length > 4 ? <span className="text-ink-2">+{uniq.length - 4}</span> : null}
    </span>
  );
}

function EvidenceBody({ summary, vocab, ev, pubs, index, params }: {
  summary: Summary;
  vocab: Vocabulary;
  ev: EvidenceIndex;
  pubs: Publications;
  index: Resource<RecordsIndex>;
  params: URLSearchParams;
}) {
  const refs = useMemo(() => pubMap(pubs), [pubs]);
  useSectionScroll(params, "ev-");
  const rows = useMemo(() => (index.state === "ready" ? toRows(index.data) : null), [index]);
  const bySource = useMemo(() => new Map((rows ?? []).map((r) => [r.source_acc, r])), [rows]);
  const evDef = new Map(vocab.evidence_level.map((e) => [e.level, e.definition]));
  const S = (id: string) => fmtInt(mv(summary, id));
  const basisX = summary.crosstabs.find((x) => x.id === "evidence_by_basis_category_counted");

  return (
    <>
      <Callout tone="warn" title="Read evidence levels as evidence types, not probabilities" testId="evidence-caveat">
        E1–E5 describe what kind of support exists for a function call. They are not calibrated probabilities of correctness, and they are a
        separate axis from membership status: a record’s evidence level never makes it a Type-I member, and membership never raises its evidence level.
        E3 and E4 functional labels can be inherited from motif and clade context rather than measured for that protein.
      </Callout>

      <nav aria-label="On this page" className="my-5 flex flex-wrap gap-2 text-sm">
        {[["ev-levels", "Levels"], ["ev-records", "Record explorer"], ["ev-e1", "E1 records"], ["ev-curated", "Curated overrides"], ["ev-conflicts", "Conflicts"], ["ev-rules", "Rules"], ["ev-engineered", "Engineered"], ["ev-pubs", "Publications"], ["ev-validation", "Validation"]].map(([id, l]) => (
          <button key={id} type="button" className="btn btn-secondary btn-sm" onClick={() => document.getElementById(id)?.scrollIntoView({ block: "start" })}>{l}</button>
        ))}
      </nav>

      <section id="ev-levels" aria-labelledby="ev-levels-h" className="mb-8 scroll-mt-20">
        <h2 id="ev-levels-h" className="mb-3 text-xl">Evidence levels</h2>
        <div className="grid gap-3 md:grid-cols-5">
          {vocab.evidence_level.map((e) => {
            const counted = summary.distributions.find((d) => d.id === "evidence_level_counted")!.items.find((i) => i.key === e.level)?.value ?? 0;
            const all = summary.distributions.find((d) => d.id === "evidence_level_all")!.items.find((i) => i.key === e.level)?.value ?? 0;
            return (
              <div key={e.level} className="card p-3 text-sm" data-testid={`level-${e.level}`}>
                <EvidenceBadge level={e.level} definition={e.definition} />
                <p className="mt-2">{e.definition}</p>
                <p className="mt-2 text-ink-2"><span className="tabular font-semibold text-ink">{fmtInt(counted)}</span> counted of {fmtInt(mv(summary, "records_counted"))}; {fmtInt(all)} of {fmtInt(mv(summary, "records_total"))} incl. engineered</p>
              </div>
            );
          })}
        </div>
        <p className="mt-3 text-sm text-ink-2">{vocab.evidence_note} Definitions: {vocab.evidence_level_source.table} ({vocab.evidence_level_source.object}).</p>
        {basisX ? <BasisCrosstab summary={summary} x={basisX} /> : null}
      </section>

      <RecordExplorer rows={rows} index={index} refs={refs} params={params} evDef={evDef} />

      <section id="ev-e1" aria-labelledby="ev-e1-h" className="mb-8 scroll-mt-20">
        <h2 id="ev-e1-h" className="mb-1 text-xl">E1: direct experimental evidence</h2>
        <p className="mb-3 text-sm text-ink-2" data-testid="e1-denominators">
          <strong className="text-ink">{S("e1_counted")}</strong> counted E1 records (of {fmtInt(metric(summary, "e1_counted").denominator!.value)} counted records);{" "}
          <strong className="text-ink">{S("e1_total")}</strong> E1 records in total including engineered constructs (of {fmtInt(metric(summary, "e1_total").denominator!.value)} source records);{" "}
          {S("e1_unique_sequences")} unique sequences.
        </p>
        <E1Table ev={ev} refs={refs} bySource={bySource} />
      </section>

      <section id="ev-curated" aria-labelledby="ev-curated-h" className="mb-8 scroll-mt-20">
        <h2 id="ev-curated-h" className="mb-1 text-xl">Curated membership overrides</h2>
        <p className="mb-3 max-w-3xl text-sm text-ink-2">
          {ev.curated_overrides.length} records whose scored membership status was overridden to “Member (curated override)” because of primary experimental evidence.
          This changes membership status only; the evidence level comes from the cited publication.
        </p>
        <TableRegion label="Curated membership overrides" testId="curated-table">
          <table className="data-table">
            <thead><tr><th scope="col">Source record</th><th scope="col">Current status</th><th scope="col">Evidence</th><th scope="col">Rationale (as stored)</th></tr></thead>
            <tbody>
              {ev.curated_overrides.map((c) => {
                const r = bySource.get(c.source_acc);
                return (
                  <tr key={c.source_acc}>
                    <td><a href={href.record(c.source_acc)} className="font-mono">{c.source_acc}</a>{r ? <span className="block text-xs text-ink-2">{r.protein_name}</span> : null}</td>
                    <td>{r ? <MembershipBadge status={r.membership_status} /> : "…"}</td>
                    <td>{r ? <EvidenceBadge level={r.evidence_level} /> : "…"}</td>
                    <td className="min-w-[18rem]">{c.rationale}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </TableRegion>
      </section>

      <ConflictSection ev={ev} rows={rows} index={index} summary={summary} />

      <section id="ev-rules" aria-labelledby="ev-rules-h" className="mb-8 scroll-mt-20">
        <h2 id="ev-rules-h" className="mb-1 text-xl">Rule-based function calls</h2>
        <p className="mb-3 max-w-3xl text-sm text-ink-2">Records whose function call was set or adjusted by a named curated or audit rule (override_rule).</p>
        <TableRegion label="Override rules" testId="rules-table">
          <table className="data-table">
            <thead><tr><th scope="col">Rule</th><th scope="col" className="num">Records</th><th scope="col">Records (source accessions)</th></tr></thead>
            <tbody>
              {Object.entries(ev.override_rules).sort((a, b) => b[1].length - a[1].length).map(([rule, accs]) => (
                <tr key={rule}>
                  <td><code className="text-xs">{rule}</code></td>
                  <td className="num">{fmtInt(accs.length)}</td>
                  <td className="min-w-[18rem]">
                    <details><summary className="cursor-pointer text-accent">Show {accs.length}</summary>
                      <span className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 font-mono text-xs">{accs.map((a) => <a key={a} href={href.record(a)}>{a}</a>)}</span>
                    </details>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableRegion>
      </section>

      <section id="ev-engineered" aria-labelledby="ev-eng-h" className="mb-8 scroll-mt-20">
        <h2 id="ev-eng-h" className="mb-1 text-xl">Engineered constructs</h2>
        <p className="mb-3 max-w-3xl text-sm text-ink-2">Policy (as stored): {ev.engineered_policy}</p>
        <TableRegion label="Engineered constructs" testId="engineered-table">
          <table className="data-table">
            <thead><tr><th scope="col">Engineered record</th><th scope="col">Wild type</th><th scope="col">Evidence</th><th scope="col">Counted</th></tr></thead>
            <tbody>
              {ev.engineered.map((e) => {
                const r = bySource.get(e.source_acc);
                return (
                  <tr key={e.source_acc}>
                    <td><a className="font-mono" href={href.record(e.source_acc)}>{e.source_acc}</a></td>
                    <td><a className="font-mono" href={href.record(e.wild_type_acc)}>{e.wild_type_acc}</a></td>
                    <td>{r ? <EvidenceBadge level={r.evidence_level} /> : "…"}</td>
                    <td>No (excluded from counts)</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </TableRegion>
      </section>

      <PublicationsSection pubs={pubs} summary={summary} />
      <ValidationSection ev={ev} />
    </>
  );
}

function BasisCrosstab({ summary, x }: { summary: Summary; x: Summary["crosstabs"][number] }) {
  const m = matrix(x, BASIS_ORDER, EVIDENCE_LEVELS);
  return (
    <div className="card mt-4 p-4" data-testid="crosstab-basis">
      <h3 className="text-base">Evidence level by basis of the function call</h3>
      <p className="mt-0.5 text-sm text-ink-2">{summary.denominators[x.denominator.id]?.label}: n = {fmtInt(x.denominator.value)}</p>
      <div className="mt-2 relative overflow-x-auto" role="region" aria-label="Evidence level by call basis" tabIndex={0}>
        <table className="data-table">
          <thead><tr><th scope="col">Basis</th>{m.cols.map((c) => <th key={String(c)} scope="col" className="num">{c}</th>)}<th scope="col" className="num">Total</th></tr></thead>
          <tbody>
            {m.rows.map((r) => (
              <tr key={String(r)}>
                <th scope="row" className="!static !bg-transparent !font-normal">{basisLabel(r)}<code className="block text-xs text-ink-2">{r}</code></th>
                {m.cols.map((c) => <td key={String(c)} className="num">{m.value(r, c) ? <a href={href.section("evidence", `level=${c}&basis=${encodeURIComponent(String(r))}`)}>{fmtInt(m.value(r, c))}</a> : "0"}</td>)}
                <td className="num font-semibold">{fmtInt(m.rowTotal(r))}</td>
              </tr>
            ))}
          </tbody>
          <tfoot><tr><th scope="row" className="!static !bg-transparent">Total</th>{m.cols.map((c) => <td key={String(c)} className="num">{fmtInt(m.colTotal(c))}</td>)}<td className="num font-semibold">{fmtInt(m.total)}</td></tr></tfoot>
        </table>
      </div>
      <div className="mt-2"><Provenance summary={summary} sql={x.sql} denominatorId={x.denominator.id} inclusion={inclusionText(x.denominator.id)} /></div>
    </div>
  );
}

/* ------------------------------------------------------------------ record explorer */

function RecordExplorer({ rows, index, refs, params, evDef }: {
  rows: IndexRow[] | null;
  index: Resource<RecordsIndex>;
  refs: Map<string, PubRef[]>;
  params: URLSearchParams;
  evDef: Map<EvidenceLevel, string>;
}) {
  const level = (EVIDENCE_LEVELS as string[]).includes(params.get("level") ?? "") ? (params.get("level") as EvidenceLevel) : "";
  const basis = BASIS_ORDER.includes(params.get("basis") ?? "") ? (params.get("basis") as string) : "";
  const group = Object.keys(GROUP_LABEL).includes(params.get("group") ?? "") ? (params.get("group") as string) : "";
  const conflict = params.get("conflict") === "1";
  const eng = params.get("eng") === "1";
  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    replaceHash(href.section("evidence", p.toString()));
  };
  const filtered = useMemo(
    () => (rows ?? []).filter((r) =>
      (eng || r.counts_eligible) && (!level || r.evidence_level === level) && (!basis || basisCategory(r.function_basis) === basis) &&
      (!group || r.membership_group === group) && (!conflict || r.call_conflict)),
    [rows, level, basis, group, conflict, eng],
  );
  const { slice, pager } = usePaged(filtered, 50, `${level}|${basis}|${group}|${conflict}|${eng}`);
  return (
    <section id="ev-records" aria-labelledby="ev-records-h" className="mb-8 scroll-mt-20">
      <h2 id="ev-records-h" className="mb-1 text-xl">Record explorer</h2>
      <p className="mb-3 max-w-3xl text-sm text-ink-2">Filter records by evidence level and call basis; each row shows the stored basis, any E2 transfer reference and linked publications.</p>
      <div className="mb-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <label className="text-sm">Evidence level
          <select className="field mt-1 w-full" value={level} onChange={(e) => set("level", e.target.value)} data-testid="ev-filter-level">
            <option value="">Any</option>{EVIDENCE_LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </label>
        <label className="text-sm">Call basis
          <select className="field mt-1 w-full" value={basis} onChange={(e) => set("basis", e.target.value)} data-testid="ev-filter-basis">
            <option value="">Any</option>{BASIS_ORDER.map((b) => <option key={b} value={b}>{basisLabel(b)}</option>)}
          </select>
        </label>
        <label className="text-sm">Membership group
          <select className="field mt-1 w-full" value={group} onChange={(e) => set("group", e.target.value)}>
            <option value="">Any</option>{Object.entries(GROUP_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2 self-end text-sm"><input type="checkbox" checked={conflict} onChange={(e) => set("conflict", e.target.checked ? "1" : "")} /> Conflict flag only</label>
        <label className="flex items-center gap-2 self-end text-sm"><input type="checkbox" checked={eng} onChange={(e) => set("eng", e.target.checked ? "1" : "")} /> Include engineered constructs</label>
      </div>
      {index.state === "loading" ? <LoadingSkeleton label="Loading records index" /> : null}
      {index.state === "error" ? <ErrorState error={index.error} retry={index.retry} what="the records index" /> : null}
      {rows ? (
        <>
          <p className="mb-2 text-sm" aria-live="polite" data-testid="ev-records-count">
            <span className="tabular font-semibold">{fmtInt(filtered.length)}</span> {eng ? "source" : "counted"} records{level ? ` at ${level}` : ""}{basis ? ` with basis “${basisLabel(basis)}”` : ""}.
            {level ? <span className="text-ink-2"> {evDef.get(level)}</span> : null}
          </p>
          <TableRegion label="Records by evidence" testId="ev-records-table">
            <table className="data-table">
              <thead><tr><th scope="col">Record</th><th scope="col">Function</th><th scope="col">Evidence</th><th scope="col">Basis (stored)</th><th scope="col">E2 reference</th><th scope="col">Publications</th><th scope="col">Flags</th></tr></thead>
              <tbody>
                {slice.map((r) => (
                  <tr key={r.source_acc}>
                    <td><a href={href.record(r.source_acc)} className="font-mono">{r.source_acc}</a><span className="block max-w-[16rem] truncate text-xs text-ink-2" title={r.protein_name ?? ""}>{r.mrdb_acc} · {r.protein_name ?? "unnamed"}</span></td>
                    <td><FunctionLabel func={r.func_class} /></td>
                    <td><EvidenceBadge level={r.evidence_level} /></td>
                    <td><code className="break-all text-xs">{r.function_basis ?? "—"}</code></td>
                    <td>{r.e2_ref ? <><a className="font-mono" href={href.record(r.e2_ref)}>{r.e2_ref}</a>{r.e2_identity !== null ? <span className="block text-xs text-ink-2">identity {(r.e2_identity * 100).toFixed(0)}%</span> : null}</> : <span className="text-ink-2">—</span>}</td>
                    <td><PubRefs refs={refs.get(r.source_acc)} /></td>
                    <td className="space-x-1">
                      {r.call_conflict ? <FlagBadge tone="warn">conflict</FlagBadge> : null}
                      {r.membership_status === "typeI_member_curated" ? <FlagBadge tone="info">curated membership</FlagBadge> : null}
                      {r.is_engineered ? <FlagBadge>engineered</FlagBadge> : null}
                      {r.override_rule ? <FlagBadge title={r.override_rule}>rule</FlagBadge> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableRegion>
          <div className="mt-3">{pager}</div>
        </>
      ) : null}
    </section>
  );
}

function E1Table({ ev, refs, bySource }: { ev: EvidenceIndex; refs: Map<string, PubRef[]>; bySource: Map<string, IndexRow> }) {
  const [withEng, setWithEng] = useState(false);
  const list = ev.e1.filter((r) => withEng || r.counts_eligible);
  const { slice, pager } = usePaged(list, 25, String(withEng));
  return (
    <>
      <label className="mb-2 flex items-center gap-2 text-sm"><input type="checkbox" checked={withEng} onChange={(e) => setWithEng(e.target.checked)} data-testid="e1-include-engineered" /> Include engineered constructs</label>
      <p className="mb-2 text-sm" aria-live="polite" data-testid="e1-row-count">Showing {fmtInt(list.length)} E1 records.</p>
      <TableRegion label="E1 records" testId="e1-table">
        <table className="data-table">
          <thead><tr><th scope="col">Source record</th><th scope="col">MRDB</th><th scope="col">Function</th><th scope="col">Basis</th><th scope="col">Publications</th><th scope="col">Counted</th></tr></thead>
          <tbody>
            {slice.map((r) => (
              <tr key={r.source_acc}>
                <td><a className="font-mono" href={href.record(r.source_acc)}>{r.source_acc}</a><span className="block max-w-[16rem] truncate text-xs text-ink-2">{bySource.get(r.source_acc)?.protein_name ?? ""}</span></td>
                <td className="font-mono">{r.mrdb_acc}</td>
                <td>{FUNC_LABEL[r.func_class as FuncClass] ?? r.func_class}</td>
                <td><code className="text-xs">{r.function_basis ?? "—"}</code></td>
                <td><PubRefs refs={refs.get(r.source_acc)} /> <span className="text-xs text-ink-2">({r.n_support_links} supporting)</span></td>
                <td>{r.counts_eligible ? "Yes" : "No (engineered)"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableRegion>
      <div className="mt-3">{pager}</div>
    </>
  );
}

/* ------------------------------------------------------------------ conflicts */

function ConflictSection({ ev, rows, index, summary }: { ev: EvidenceIndex; rows: IndexRow[] | null; index: Resource<RecordsIndex>; summary: Summary }) {
  const [action, setAction] = useState("");
  const all = useMemo(() => (rows ?? []).filter((r) => r.call_conflict).map((r) => ({ r, d: parseConflictDetail(r.call_conflict_detail) })), [rows]);
  const actions = useMemo(() => [...new Set(all.map((x) => x.d?.action ?? null))], [all]);
  const list = all.filter((x) => !action || (x.d?.action ?? "") === action);
  const { slice, pager } = usePaged(list, 25, action);
  return (
    <section id="ev-conflicts" aria-labelledby="ev-conf-h" className="mb-8 scroll-mt-20">
      <h2 id="ev-conf-h" className="mb-1 text-xl">Function-call conflicts</h2>
      <p className="mb-2 max-w-3xl text-sm text-ink-2">
        {fmtInt(mv(summary, "call_conflict"))} records (of {fmtInt(mv(summary, "records_total"))}) where the earlier functional call disagrees with the class implied by the helix-C motif.
        Rule (as stored): {ev.function_conflict_rule}
      </p>
      {index.state === "loading" ? <LoadingSkeleton label="Loading records index" /> : null}
      {index.state === "error" ? <ErrorState error={index.error} retry={index.retry} what="the records index" /> : null}
      {rows ? (
        <>
          <div className="mb-3 flex flex-wrap gap-1" role="group" aria-label="Conflict decision">
            <button type="button" className={`btn btn-sm ${!action ? "btn-primary" : "btn-secondary"}`} aria-pressed={!action} onClick={() => setAction("")}>All ({fmtInt(all.length)})</button>
            {actions.map((a) => (
              <button key={String(a)} type="button" className={`btn btn-sm ${action === a ? "btn-primary" : "btn-secondary"}`} aria-pressed={action === a} onClick={() => setAction(a ?? "")}>
                {actionLabel(a)} ({fmtInt(all.filter((x) => (x.d?.action ?? null) === a).length)})
              </button>
            ))}
          </div>
          <TableRegion label="Function-call conflicts" testId="conflict-table">
            <table className="data-table">
              <thead><tr><th scope="col">Record</th><th scope="col">Original call (v1.4)</th><th scope="col">Motif implies</th><th scope="col">Decision</th><th scope="col">Current call</th><th scope="col">Evidence</th></tr></thead>
              <tbody>
                {slice.map(({ r, d }) => (
                  <tr key={r.source_acc}>
                    <td><a className="font-mono" href={href.record(r.source_acc)}>{r.source_acc}</a><span className="block text-xs text-ink-2">{r.helixC_motif ? `motif ${r.helixC_motif}` : ""}</span></td>
                    <td>{d?.original ?? "—"}</td>
                    <td>{d?.motif ?? "—"}</td>
                    <td>{actionLabel(d?.action ?? null)}</td>
                    <td><FunctionLabel func={r.func_class} /></td>
                    <td><EvidenceBadge level={r.evidence_level} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableRegion>
          <div className="mt-3">{pager}</div>
          <p className="mt-2 text-sm text-ink-2">Caveat: a withdrawn call means the evidence could not support a class, not that the protein lacks function.</p>
        </>
      ) : null}
    </section>
  );
}

/* ------------------------------------------------------------------ publications */

function PublicationsSection({ pubs, summary }: { pubs: Publications; summary: Summary }) {
  const [q, setQ] = useState("");
  const nLinks = useMemo(() => {
    const m = new Map<number, number>();
    for (const l of pubs.links) m.set(l.publication_id, (m.get(l.publication_id) ?? 0) + 1);
    return m;
  }, [pubs]);
  const ql = q.trim().toLowerCase();
  const list = pubs.publications.filter((p) => !ql || [p.title, p.journal, p.pmid, p.doi, String(p.year ?? "")].some((v) => v && v.toLowerCase().includes(ql)));
  const { slice, pager } = usePaged(list, 25, ql);
  return (
    <section id="ev-pubs" aria-labelledby="ev-pubs-h" className="mb-8 scroll-mt-20">
      <h2 id="ev-pubs-h" className="mb-1 text-xl">Publications</h2>
      <p className="mb-3 text-sm text-ink-2">
        {fmtInt(mv(summary, "publications"))} publications; {fmtInt(mv(summary, "publication_links_active"))} active record–publication links, of which {fmtInt(mv(summary, "publication_links_support"))} count as supporting evidence.
      </p>
      <label className="mb-3 block max-w-md text-sm">Filter publications<input type="search" className="field mt-1 w-full" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Title, journal, PMID, DOI or year" /></label>
      <TableRegion label="Publications" testId="pubs-table">
        <table className="data-table">
          <thead><tr><th scope="col">Year</th><th scope="col">Title</th><th scope="col">Identifiers</th><th scope="col" className="num">Active links</th><th scope="col">Verification</th></tr></thead>
          <tbody>
            {slice.map((p) => (
              <tr key={p.publication_id}>
                <td className="tabular">{p.year ?? "—"}</td>
                <td className="min-w-[18rem]">{p.title ?? <span className="text-ink-2">Title not recorded</span>}{p.journal ? <span className="block text-xs text-ink-2">{p.journal}</span> : null}</td>
                <td className="space-x-2 whitespace-nowrap">
                  {p.pmid ? <Ext href={`https://pubmed.ncbi.nlm.nih.gov/${p.pmid}/`}>PMID {p.pmid}</Ext> : null}
                  {p.doi_corrected ?? p.doi ? <Ext href={`https://doi.org/${p.doi_corrected ?? p.doi}`}>DOI</Ext> : null}
                </td>
                <td className="num">{fmtInt(nLinks.get(p.publication_id) ?? 0)}</td>
                <td className="text-xs">{p.verdict_summary ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableRegion>
      <div className="mt-3">{pager}</div>
    </section>
  );
}

/* ------------------------------------------------------------------ validation */

const pct = (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(1)}%`);

function ValidationSection({ ev }: { ev: EvidenceIndex }) {
  const v = ev.validation;
  return (
    <section id="ev-validation" aria-labelledby="ev-val-h" className="mb-8 scroll-mt-20">
      <h2 id="ev-val-h" className="mb-1 text-xl">Validation</h2>
      <p className="mb-3 max-w-3xl text-sm text-ink-2">{v.note} See <a href={href.section("methods", "s=validation")}>Methods: validation</a>.</p>
      <h3 className="mb-2 text-base">Blind annotation audit</h3>
      <TableRegion label="Blind audit agreement" testId="audit-table">
        <table className="data-table">
          <thead><tr><th scope="col">Tier</th><th scope="col">Metric</th><th scope="col" className="num">Agreement</th><th scope="col" className="num">95% CI (Wilson)</th><th scope="col">Note</th></tr></thead>
          <tbody>
            {v.audit_agreement.map((a, i) => (
              <tr key={i}>
                <td>{a.tier}</td>
                <td><code className="text-xs">{a.metric}</code></td>
                <td className="num">{a.n_match}/{a.n} ({pct(a.agreement)})</td>
                <td className="num">{pct(a.wilson_lo)}–{pct(a.wilson_hi)}</td>
                <td className="min-w-[14rem] text-xs">{a.note ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableRegion>
      <details className="mt-1 text-sm"><summary className="cursor-pointer text-accent">Query</summary><code className="block whitespace-pre-wrap text-xs">{v.audit_sql}</code></details>

      <h3 className="mb-2 mt-5 text-base">Leave-one-clade-out (LOCO) validation</h3>
      <TableRegion label="LOCO validation" testId="loco-table">
        <table className="data-table">
          <thead><tr><th scope="col">Subset</th><th scope="col">Hold-out</th><th scope="col">Policy</th><th scope="col" className="num">n</th><th scope="col" className="num">Coverage (95% CI)</th><th scope="col" className="num">Precision (95% CI)</th></tr></thead>
          <tbody>
            {v.loco.map((l, i) => (
              <tr key={i}>
                <td><code className="text-xs">{l.subset}</code></td>
                <td>{l.holdout}</td>
                <td>{l.policy}</td>
                <td className="num">{l.n}</td>
                <td className="num">{l.coverage === null ? "—" : `${l.n_assigned}/${l.n} ${pct(l.coverage)} (${pct(l.cov_lo)}–${pct(l.cov_hi)})`}</td>
                <td className="num">{l.precision === null ? "—" : `${l.n_correct}/${l.n_assigned} ${pct(l.precision)} (${pct(l.prec_lo)}–${pct(l.prec_hi)})`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableRegion>
      <p className="mt-2 text-sm text-ink-2">Variant {v.loco[0]?.variant ?? "—"}; interval method: {v.ci_method}. Precision and coverage are estimates for the E1 benchmark set, not per-record confidence.</p>
      <details className="mt-1 text-sm"><summary className="cursor-pointer text-accent">Query</summary><code className="block whitespace-pre-wrap text-xs">{v.loco_sql}</code></details>
    </section>
  );
}
