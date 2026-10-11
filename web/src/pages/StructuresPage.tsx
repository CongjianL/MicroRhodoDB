/**
 * Structure explorer (#/structures), spec section 10.1. Three separate tabs: experimental PDB entries
 * (structures-index.json, from protein_pdb + pdb_structure), AlphaFold DB models (records index) and the
 * predicted models distributed with the release. The three PDB statistics (distinct entries, records with
 * an entry, record-PDB links) are kept distinct. The shared Mol* StructureViewer is a separate chunk and
 * Mol* itself is downloaded only when the user asks for a 3D view.
 *
 * URL state: ?tab=pdb|afdb|release and an optional selection pdb=<ID> | afdb=<source acc> | pred=<source acc>.
 */
import { useEffect, useMemo, useState } from "react";
import { replaceHash } from "../app/navigation";
import { href } from "../app/routes";
import { EvidenceBadge, FunctionLabel } from "../components/Badges";
import { Callout, PageTitle, StatCard } from "../components/common";
import { TableRegion, usePaged } from "../components/Paged";
import { ErrorState, LoadingSkeleton } from "../components/States";
import { loadRecord, loadRecordsIndex, loadStructuresIndex, loadSummary, useResource } from "../data/loaders";
import type { EvidenceLevel, FuncClass, PdbIndexEntry, PdbLink, PredictedModel, SourceRecord, StructuresIndex, Summary } from "../data/types";
import { StructureViewer } from "../features/structure/StructureViewer";
import { toRows, type IndexRow } from "../lib/browse";
import { PDB_METHOD_SHORT, afdbOption, pdbOption, pdbUrls, releaseOption, resolutionText, type StructureOption } from "../lib/entry";
import { EVIDENCE_LEVELS, FUNC_LABEL, FUNC_ORDER, fmtInt } from "../lib/format";
import { mv } from "../lib/summary";

type Tab = "pdb" | "afdb" | "release";
const TABS: { id: Tab; label: string }[] = [
  { id: "pdb", label: "Experimental (PDB)" },
  { id: "afdb", label: "AlphaFold DB models" },
  { id: "release", label: "Release models" },
];

export default function StructuresPage({ params }: { params: URLSearchParams }) {
  const light = useResource(() => Promise.all([loadSummary(), loadStructuresIndex()]));
  const index = useResource(loadRecordsIndex);
  const rows = useMemo(() => (index.state === "ready" ? toRows(index.data) : null), [index]);
  return (
    <div className="container-page pt-6">
      <PageTitle
        docTitle="Structure explorer - MicroRhodoDB"
        lead="Experimental structures from the PDB, AlphaFold DB models and the release’s own predicted models, each with its provenance. Predicted models are never presented as experimental structures."
      >
        Structure explorer
      </PageTitle>
      {light.state === "loading" ? <LoadingSkeleton lines={6} /> : null}
      {light.state === "error" ? <ErrorState error={light.error} retry={light.retry} what="the structure index" /> : null}
      {light.state === "ready" ? (
        <Body summary={light.data[0]} si={light.data[1]} rows={rows} indexState={index} params={params} />
      ) : null}
    </div>
  );
}

function Body({ summary, si, rows, indexState, params }: {
  summary: Summary;
  si: StructuresIndex;
  rows: IndexRow[] | null;
  indexState: ReturnType<typeof useResource<unknown>>;
  params: URLSearchParams;
}) {
  const tab: Tab = (["pdb", "afdb", "release"] as Tab[]).includes(params.get("tab") as Tab) ? (params.get("tab") as Tab) : params.get("afdb") ? "afdb" : params.get("pred") ? "release" : "pdb";
  const bySource = useMemo(() => new Map((rows ?? []).map((r) => [r.source_acc, r])), [rows]);
  const [selected, setSelected] = useState<StructureOption | null>(null);
  const [activate, setActivate] = useState(0);
  const [selError, setSelError] = useState<string | null>(null);
  const S = (id: string) => mv(summary, id);

  const setParams = (next: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) (v ? p.set(k, v) : p.delete(k));
    replaceHash(href.section("structures", p.toString()));
  };

  // Resolve a URL selection into a viewer option (no Mol* download until the user loads the viewer).
  const pdbSel = params.get("pdb")?.toUpperCase() ?? null;
  const afdbSel = params.get("afdb") ?? null;
  const predSel = params.get("pred") ?? null;
  useEffect(() => {
    let alive = true;
    setSelError(null);
    (async () => {
      if (pdbSel) {
        const p = si.pdb[pdbSel];
        if (!p) throw new Error(`PDB entry ${pdbSel} is not linked to any MicroRhodoDB record.`);
        return pdbOption(p as unknown as PdbLink, p.source_accs.join(", "));
      }
      if (predSel) {
        const m = si.predicted.find((x) => x.source_acc === predSel);
        if (!m) throw new Error(`No release model for ${predSel}.`);
        return { ...releaseOption({ source_acc: predSel } as SourceRecord, m as unknown as PredictedModel), key: `pred:${predSel}` };
      }
      if (afdbSel) {
        const r = rows ? bySource.get(afdbSel) : undefined;
        if (!rows) return undefined; // wait for the index
        if (!r) throw new Error(`${afdbSel} is not a MicroRhodoDB source record.`);
        const entry = await loadRecord(r.mrdb_acc);
        const src = entry?.sources.find((s) => s.source_acc === afdbSel);
        const opt = src ? afdbOption(src) : null;
        if (!opt) throw new Error(`No AlphaFold DB model is recorded for ${afdbSel}.`);
        return { ...opt, key: `afdb:${afdbSel}` };
      }
      return null;
    })().then(
      (o) => {
        if (alive && o !== undefined) setSelected(o);
      },
      (e: Error) => alive && (setSelError(e.message), setSelected(null)),
    );
    return () => {
      alive = false;
    };
  }, [pdbSel, afdbSel, predSel, rows, bySource, si]);

  const view = (sel: Record<string, string | null>) => {
    setParams({ pdb: null, afdb: null, pred: null, ...sel });
    setActivate((n) => n + 1);
    window.setTimeout(() => document.getElementById("structure-viewer-panel")?.scrollIntoView({ block: "start", behavior: "smooth" }), 50);
  };

  return (
    <>
      <section aria-label="Structure statistics" className="mb-6">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <StatCard testId="st-pdb-entries" value={S("pdb_entries")} label="Distinct PDB entries" detail={`${fmtInt(S("pdb_entries_with_retinal"))} contain retinal`} />
          <StatCard testId="st-records-pdb" value={S("records_with_pdb")} label="Source records with PDB entries" detail={`${fmtInt(S("mrdb_with_pdb"))} MRDB accessions`} />
          <StatCard testId="st-pdb-links" value={S("pdb_links")} label="Record–PDB links" detail="Entry–record pairs" />
          <StatCard testId="st-afdb" value={S("records_with_afdb")} label="Records with AlphaFold DB models" detail="Predicted, not experimental" />
          <StatCard testId="st-pred" value={S("predicted_models")} label="Release models" detail="Predicted models shipped with the release" />
        </div>
        <p className="mt-2 text-sm text-ink-2">These counts use different units (entries, records, links, models) and are not comparable with each other. PDB chain-to-UniProt mapping: {si.chain_mapping}.</p>
      </section>

      <div role="tablist" aria-label="Structure type" className="mb-4 flex flex-wrap gap-1 border-b border-line">
        {TABS.map((t) => (
          <button key={t.id} role="tab" type="button" aria-selected={tab === t.id} data-testid={`tab-${t.id}`}
            className={`-mb-px rounded-t-md border px-3 py-2 text-sm ${tab === t.id ? "border-line border-b-white bg-white font-semibold" : "border-transparent text-ink-2"}`}
            onClick={() => setParams({ tab: t.id })}>
            {t.label}
          </button>
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,28rem)]">
        <div role="tabpanel" aria-label={TABS.find((t) => t.id === tab)!.label} className="min-w-0">
          {tab === "pdb" ? <PdbTab si={si} bySource={bySource} rowsReady={!!rows} onView={(id) => view({ pdb: id })} /> : null}
          {tab === "afdb" ? (
            rows ? <AfdbTab rows={rows} onView={(acc) => view({ afdb: acc })} />
              : indexState.state === "error" ? <ErrorState error={indexState.error} retry={indexState.retry} what="the records index" /> : <LoadingSkeleton label="Loading records index" />
          ) : null}
          {tab === "release" ? <ReleaseTab si={si} onView={(acc) => view({ pred: acc })} /> : null}
        </div>
        <aside id="structure-viewer-panel" aria-label="3D viewer" className="min-w-0 scroll-mt-20 xl:sticky xl:top-20 xl:self-start">
          {selError ? <Callout tone="warn" title="Selection unavailable">{selError}</Callout> : null}
          {selected ? (
            <StructureViewer options={[selected]} selected={selected} onSelect={() => undefined} activate={activate} />
          ) : !selError ? (
            <div className="card p-4 text-sm text-ink-2" data-testid="viewer-empty">Choose “View in 3D” on any row. The 3D viewer (Mol*) is downloaded only when you ask for it.</div>
          ) : null}
        </aside>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ PDB tab */

function PdbTab({ si, bySource, rowsReady, onView }: { si: StructuresIndex; bySource: Map<string, IndexRow>; rowsReady: boolean; onView: (id: string) => void }) {
  const [q, setQ] = useState("");
  const [method, setMethod] = useState("");
  const [maxRes, setMaxRes] = useState("");
  const [retinal, setRetinal] = useState("");
  const [func, setFunc] = useState("");
  const [evidence, setEvidence] = useState("");
  const [sort, setSort] = useState<"resolution" | "year" | "pdb_id">("resolution");
  const entries = useMemo(() => Object.values(si.pdb), [si]);
  const methods = useMemo(() => [...new Set(entries.map((e) => e.method))].sort(), [entries]);
  const ql = q.trim().toLowerCase();
  const mr = maxRes ? Number(maxRes) : null;
  const filtered = entries.filter((e) =>
    (!ql || e.pdb_id.toLowerCase().includes(ql) || e.title.toLowerCase().includes(ql) || e.source_accs.some((a) => a.toLowerCase() === ql) || e.mrdb_accs.some((a) => a.toLowerCase() === ql)) &&
    (!method || e.method === method) &&
    (mr === null || (typeof e.resolution_A === "number" && e.resolution_A <= mr)) &&
    (!retinal || e.has_retinal === (retinal === "yes")) &&
    (!func || e.source_accs.some((a) => bySource.get(a)?.func_class === func)) &&
    (!evidence || e.source_accs.some((a) => bySource.get(a)?.evidence_level === evidence)));
  const res = (e: PdbIndexEntry) => (typeof e.resolution_A === "number" ? e.resolution_A : Number.POSITIVE_INFINITY);
  const sorted = filtered.slice().sort((a, b) =>
    sort === "resolution" ? res(a) - res(b) || a.pdb_id.localeCompare(b.pdb_id) : sort === "year" ? b.year - a.year || a.pdb_id.localeCompare(b.pdb_id) : a.pdb_id.localeCompare(b.pdb_id));
  const links = filtered.reduce((n, e) => n + e.source_accs.length, 0);
  const recs = new Set(filtered.flatMap((e) => e.source_accs)).size;
  const { slice, pager } = usePaged(sorted, 25, `${ql}|${method}|${maxRes}|${retinal}|${func}|${evidence}|${sort}`);
  return (
    <>
      <div className="mb-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="text-sm sm:col-span-2">PDB ID, title or accession<input type="search" className="field mt-1 w-full" value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. 1C3W, bacteriorhodopsin, P02945" data-testid="pdb-filter-q" /></label>
        <label className="text-sm">Method<select className="field mt-1 w-full" value={method} onChange={(e) => setMethod(e.target.value)} data-testid="pdb-filter-method"><option value="">Any</option>{methods.map((m) => <option key={m} value={m}>{m}</option>)}</select></label>
        <label className="text-sm">Resolution at most (Å)<input inputMode="decimal" className="field mt-1 w-full" value={maxRes} onChange={(e) => setMaxRes(e.target.value.replace(/[^\d.]/g, ""))} placeholder="any" /></label>
        <label className="text-sm">Retinal (RET)<select className="field mt-1 w-full" value={retinal} onChange={(e) => setRetinal(e.target.value)}><option value="">Any</option><option value="yes">Present</option><option value="no">Absent</option></select></label>
        <label className="text-sm">Function of linked record<select className="field mt-1 w-full" value={func} onChange={(e) => setFunc(e.target.value)} disabled={!rowsReady}><option value="">{rowsReady ? "Any" : "Loading…"}</option>{FUNC_ORDER.map((f) => <option key={f} value={f}>{FUNC_LABEL[f]}</option>)}</select></label>
        <label className="text-sm">Evidence of linked record<select className="field mt-1 w-full" value={evidence} onChange={(e) => setEvidence(e.target.value)} disabled={!rowsReady}><option value="">{rowsReady ? "Any" : "Loading…"}</option>{EVIDENCE_LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}</select></label>
        <label className="text-sm">Sort by<select className="field mt-1 w-full" value={sort} onChange={(e) => setSort(e.target.value as typeof sort)}><option value="resolution">Resolution (best first)</option><option value="year">Year (newest first)</option><option value="pdb_id">PDB ID</option></select></label>
      </div>
      <p className="mb-2 text-sm" aria-live="polite" data-testid="pdb-count">
        <span className="tabular font-semibold">{fmtInt(filtered.length)}</span> PDB entries · {fmtInt(recs)} linked source records · {fmtInt(links)} record–PDB links
      </p>
      <TableRegion label="PDB entries" testId="pdb-table">
        <table className="data-table">
          <thead><tr><th scope="col">PDB</th><th scope="col">Method</th><th scope="col" className="num">Resolution</th><th scope="col" className="num">Year</th><th scope="col">Retinal</th><th scope="col">Title</th><th scope="col">Linked records</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>
            {slice.map((e) => (
              <tr key={e.pdb_id} data-testid={`pdb-row-${e.pdb_id}`}>
                <td><a className="font-mono" href={pdbUrls(e.pdb_id).rcsb} target="_blank" rel="noopener noreferrer">{e.pdb_id}</a></td>
                <td>{PDB_METHOD_SHORT[e.method]}</td>
                <td className="num">{resolutionText(e.resolution_A)}</td>
                <td className="num">{e.year}</td>
                <td>{e.has_retinal ? "RET" : "—"}{e.ligands.length > (e.has_retinal ? 1 : 0) ? <span className="block text-xs text-ink-2">{e.ligands.filter((l) => l !== "RET").slice(0, 4).join(", ")}</span> : null}</td>
                <td className="min-w-[14rem] text-xs">{e.title}</td>
                <td className="min-w-[10rem]">
                  {e.source_accs.map((a) => {
                    const r = bySource.get(a);
                    return (
                      <span key={a} className="block">
                        <a className="font-mono" href={href.record(a, `structure=pdb:${e.pdb_id}`)}>{a}</a>
                        {r ? <span className="ml-1 text-xs text-ink-2">{FUNC_LABEL[r.func_class]} · {r.evidence_level}</span> : null}
                      </span>
                    );
                  })}
                </td>
                <td><button type="button" className="btn btn-secondary btn-sm whitespace-nowrap" onClick={() => onView(e.pdb_id)} data-testid={`view-pdb-${e.pdb_id}`}>View in 3D</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableRegion>
      <div className="mt-3">{pager}</div>
    </>
  );
}

/* ------------------------------------------------------------------ AFDB tab */

function AfdbTab({ rows, onView }: { rows: IndexRow[]; onView: (acc: string) => void }) {
  const [q, setQ] = useState("");
  const [func, setFunc] = useState("");
  const [evidence, setEvidence] = useState("");
  const [minPlddt, setMinPlddt] = useState("");
  const withModel = useMemo(() => rows.filter((r) => r.has_afdb), [rows]);
  const ql = q.trim().toLowerCase();
  const mp = minPlddt ? Number(minPlddt) : null;
  const filtered = withModel.filter((r) =>
    (!ql || [r.source_acc, r.mrdb_acc, r.protein_name, r.organism, r.afdb_model_id].some((v) => v && v.toLowerCase().includes(ql))) &&
    (!func || r.func_class === func) && (!evidence || r.evidence_level === evidence) &&
    (mp === null || (r.afdb_global_plddt !== null && r.afdb_global_plddt >= mp)));
  const { slice, pager } = usePaged(filtered, 50, `${ql}|${func}|${evidence}|${minPlddt}`);
  return (
    <>
      <Callout title="Predicted models">
        AlphaFold DB models are computational predictions linked by UniProt accession. Colour in the viewer shows pLDDT confidence, not experimental resolution.
      </Callout>
      <div className="my-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="text-sm">Accession, protein or organism<input type="search" className="field mt-1 w-full" value={q} onChange={(e) => setQ(e.target.value)} data-testid="afdb-filter-q" /></label>
        <label className="text-sm">Function<select className="field mt-1 w-full" value={func} onChange={(e) => setFunc(e.target.value)}><option value="">Any</option>{FUNC_ORDER.map((f) => <option key={f} value={f}>{FUNC_LABEL[f]}</option>)}</select></label>
        <label className="text-sm">Evidence<select className="field mt-1 w-full" value={evidence} onChange={(e) => setEvidence(e.target.value)}><option value="">Any</option>{EVIDENCE_LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}</select></label>
        <label className="text-sm">Global pLDDT at least<input inputMode="decimal" className="field mt-1 w-full" value={minPlddt} onChange={(e) => setMinPlddt(e.target.value.replace(/[^\d.]/g, ""))} placeholder="any" /></label>
      </div>
      <p className="mb-2 text-sm" aria-live="polite" data-testid="afdb-count"><span className="tabular font-semibold">{fmtInt(filtered.length)}</span> of {fmtInt(withModel.length)} source records with an AlphaFold DB model</p>
      <TableRegion label="AlphaFold DB models" testId="afdb-table">
        <table className="data-table">
          <thead><tr><th scope="col">Record</th><th scope="col">Organism</th><th scope="col">Function</th><th scope="col">Evidence</th><th scope="col">Model</th><th scope="col" className="num">Global pLDDT</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>
            {slice.map((r) => (
              <tr key={r.source_acc}>
                <td><a className="font-mono" href={href.record(r.source_acc, "structure=afdb")}>{r.source_acc}</a><span className="block max-w-[14rem] truncate text-xs text-ink-2">{r.protein_name ?? "unnamed"}</span></td>
                <td className="max-w-[12rem] truncate text-xs italic" title={r.organism ?? ""}>{r.organism ?? "—"}</td>
                <td><FunctionLabel func={r.func_class as FuncClass} /></td>
                <td><EvidenceBadge level={r.evidence_level as EvidenceLevel} /></td>
                <td className="font-mono text-xs">{r.afdb_model_id ?? "—"}</td>
                <td className="num">{r.afdb_global_plddt ?? "—"}</td>
                <td><button type="button" className="btn btn-secondary btn-sm whitespace-nowrap" onClick={() => onView(r.source_acc)}>View in 3D</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableRegion>
      <div className="mt-3">{pager}</div>
    </>
  );
}

/* ------------------------------------------------------------------ release models */

function ReleaseTab({ si, onView }: { si: StructuresIndex; onView: (acc: string) => void }) {
  return (
    <>
      <p className="mb-3 text-sm text-ink-2">Predicted models distributed in the release itself, for clade representatives that lack an experimental structure. Values are shown as stored.</p>
      <div className="space-y-3" data-testid="release-models">
        {si.predicted.map((raw) => {
          const m = raw as unknown as PredictedModel & { source_acc: string; mrdb_acc: string };
          const opt = releaseOption({ source_acc: m.source_acc } as SourceRecord, m);
          return (
            <div key={m.source_acc} className="card p-4 text-sm">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="text-base"><a className="font-mono" href={href.record(m.source_acc, "structure=pred")}>{m.source_acc}</a> <span className="text-ink-2">({m.mrdb_acc})</span></h3>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => onView(m.source_acc)}>View in 3D</button>
              </div>
              <dl className="mt-2 grid gap-x-3 gap-y-1 sm:grid-cols-[10rem_minmax(0,1fr)]">
                <dt className="text-ink-2">Stored method</dt><dd>{m.method}</dd>
                <dt className="text-ink-2">Mean pLDDT</dt><dd>{m.mean_plddt}</dd>
                <dt className="text-ink-2">Subfamily (stored)</dt><dd>{m.subfamily ?? "—"}</dd>
                <dt className="text-ink-2">Note (stored)</dt><dd>{m.note ?? "—"}</dd>
                <dt className="text-ink-2">File</dt><dd className="break-all font-mono text-xs">{m.source_path} · SHA-256 {m.sha256}</dd>
              </dl>
              {opt.warning ? <p className="mt-2 text-[#8a3c04]" data-testid="release-provenance-warning"><strong>Provenance: </strong>{opt.warning}</p> : null}
            </div>
          );
        })}
      </div>
    </>
  );
}
