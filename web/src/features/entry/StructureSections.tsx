import { useMemo, useState } from "react";
import { href } from "../../app/routes";
import { FlagBadge } from "../../components/Badges";
import { Pagination } from "../../components/common";
import type { MrdbEntry, PdbMethod, SourceRecord } from "../../data/types";
import { fmtInt } from "../../lib/format";
import {
  DEFAULT_PDB_FILTER, PDB_METHOD_SHORT, afdbEntryUrl, filterSortPdb, focusedRows, pdbUrls, resolutionText, unionRows,
  type PdbFilter, type PdbSortKey, type StructureSel,
} from "../../lib/entry";
import { Ext, Row, Section, fmtNum, na } from "./ui";

const PAGE = 25;
const METHODS: PdbMethod[] = ["X-RAY DIFFRACTION", "ELECTRON MICROSCOPY", "ELECTRON CRYSTALLOGRAPHY", "SOLUTION NMR"];

export function ExperimentalSection({ entry, src, onView }: { entry: MrdbEntry; src: SourceRecord; onView: (s: StructureSel) => void }) {
  const multi = entry.sources.length > 1 && entry.pdb_union.length !== src.structures.experimental.length;
  const [scope, setScope] = useState<"focused" | "all">("focused");
  const [f, setF] = useState<PdbFilter>(DEFAULT_PDB_FILTER);
  const [page, setPage] = useState(1);
  const base = useMemo(() => (scope === "all" ? unionRows(entry) : focusedRows(src)), [scope, entry, src]);
  const rows = useMemo(() => filterSortPdb(base, f), [base, f]);
  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE));
  const cur = Math.min(page, pageCount);
  const shown = rows.slice((cur - 1) * PAGE, cur * PAGE);
  const n = src.structures.experimental.length;
  const upd = (p: Partial<PdbFilter>) => {
    setF((x) => ({ ...x, ...p }));
    setPage(1);
  };
  const sortBtn = (k: PdbSortKey, label: string) => {
    const active = f.sort === k;
    return (
      <button
        type="button"
        className="inline-flex items-center gap-1 font-semibold"
        onClick={() => upd({ sort: k, dir: active && f.dir === "asc" ? "desc" : "asc" })}
        aria-label={`Sort by ${label}`}
      >
        {label}
        <span aria-hidden="true" className="text-ink-2">{active ? (f.dir === "asc" ? "▲" : "▼") : "↕"}</span>
      </button>
    );
  };
  const ariaSort = (k: PdbSortKey) => (f.sort === k ? (f.dir === "asc" ? "ascending" : "descending") : "none");

  return (
    <Section
      id="experimental"
      title="Experimental structures"
      lead={
        <>
          <span data-testid="pdb-count-focused" data-n={n}>{fmtInt(n)} PDB entr{n === 1 ? "y is" : "ies are"} linked to {src.source_acc}</span>
          {entry.sources.length > 1 ? <span data-testid="pdb-count-union" data-n={entry.pdb_union.length}>; {fmtInt(entry.pdb_union.length)} across all {entry.n_source_records} source records of {entry.mrdb_acc}</span> : null}.
          {" "}PDB links are source-specific and are not merged across source records unless you choose to show all sources.
        </>
      }
    >
      {n === 0 && !multi ? (
        <div className="card p-4 text-sm" data-testid="pdb-none">
          No experimental PDB linked to {src.source_acc} in v1.6.0.
          {entry.pdb_union.length ? <> Other source records of {entry.mrdb_acc} have {entry.pdb_union.length} linked entries.</> : null}
        </div>
      ) : (
        <div className="card">
          <div className="flex flex-wrap items-end gap-3 border-b border-line p-3">
            {multi ? (
              <fieldset className="flex flex-wrap items-center gap-1">
                <legend className="field-label">Show</legend>
                <button type="button" className={`btn btn-sm ${scope === "focused" ? "btn-primary" : "btn-secondary"}`} aria-pressed={scope === "focused"} onClick={() => { setScope("focused"); setPage(1); }} data-testid="pdb-scope-focused">
                  {src.source_acc} ({n})
                </button>
                <button type="button" className={`btn btn-sm ${scope === "all" ? "btn-primary" : "btn-secondary"}`} aria-pressed={scope === "all"} onClick={() => { setScope("all"); setPage(1); }} data-testid="pdb-scope-all">
                  All sources ({entry.pdb_union.length})
                </button>
              </fieldset>
            ) : null}
            <div className="min-w-[10rem] flex-1">
              <label className="field-label" htmlFor="pdb-q">Filter</label>
              <input id="pdb-q" className="field" type="search" placeholder="PDB ID, title word or ligand code" value={f.q} onChange={(e) => upd({ q: e.target.value })} data-testid="pdb-filter-q" />
            </div>
            <div>
              <label className="field-label" htmlFor="pdb-method">Method</label>
              <select id="pdb-method" className="field" value={f.method} onChange={(e) => upd({ method: e.target.value as PdbFilter["method"] })} data-testid="pdb-filter-method">
                <option value="">All methods</option>
                {METHODS.map((m) => <option key={m} value={m}>{PDB_METHOD_SHORT[m]}</option>)}
              </select>
            </div>
            <div>
              <label className="field-label" htmlFor="pdb-ret">Retinal (RET) in entry</label>
              <select id="pdb-ret" className="field" value={f.retinal} onChange={(e) => upd({ retinal: e.target.value as PdbFilter["retinal"] })} data-testid="pdb-filter-retinal">
                <option value="">Any</option>
                <option value="yes">Present</option>
                <option value="no">Not present</option>
              </select>
            </div>
          </div>
          <div className="relative overflow-x-auto" role="region" aria-label="Experimental PDB entries" tabIndex={0}>
            <table className="data-table sticky-first" data-testid="pdb-table" data-rows={rows.length} data-scope={scope}>
              <thead>
                <tr>
                  <th scope="col" aria-sort={ariaSort("pdb_id")}>{sortBtn("pdb_id", "PDB ID")}</th>
                  {scope === "all" ? <th scope="col">Source</th> : null}
                  <th scope="col" aria-sort={ariaSort("method")}>{sortBtn("method", "Method")}</th>
                  <th scope="col" aria-sort={ariaSort("resolution")}>{sortBtn("resolution", "Resolution")}</th>
                  <th scope="col" aria-sort={ariaSort("year")}>{sortBtn("year", "Year")}</th>
                  <th scope="col">Title</th>
                  <th scope="col">Retinal</th>
                  <th scope="col">Ligands</th>
                  <th scope="col">Shared with</th>
                  <th scope="col">Links</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((p) => {
                  const u = pdbUrls(p.pdb_id);
                  return (
                    <tr key={p.pdb_id} data-pdb={p.pdb_id}>
                      <td>
                        <span className="font-mono font-semibold">{p.pdb_id}</span>
                        <span className="mt-1 flex flex-wrap gap-1">
                          {p.is_rep ? <FlagBadge tone="info" title="Representative structure for this source record (as recorded in v1.6.0)">rep</FlagBadge> : null}
                          {p.is_highest_res ? <FlagBadge tone="neutral" title="Highest-resolution entry for this source record">highest res.</FlagBadge> : null}
                        </span>
                      </td>
                      {scope === "all" ? (
                        <td className="font-mono text-xs">
                          {p.sources.map((s) => (s === src.source_acc ? <span key={s} className="block">{s}</span> : <a key={s} className="block" href={href.record(s)}>{s}</a>))}
                        </td>
                      ) : null}
                      <td className="whitespace-nowrap">{PDB_METHOD_SHORT[p.method]}</td>
                      <td className="whitespace-nowrap tabular">{resolutionText(p.resolution_A)}</td>
                      <td className="tabular">{p.year}</td>
                      <td className="min-w-[14rem] max-w-[28rem] text-sm">{p.title}</td>
                      <td>{p.has_retinal ? "RET present" : <span className="text-ink-2">Not present</span>}</td>
                      <td className="font-mono text-xs">{p.ligands.length ? p.ligands.join(", ") : <span className="font-sans text-ink-2">None</span>}</td>
                      <td className="font-mono text-xs">{p.shared_with.length ? p.shared_with.map((s) => <a key={s} className="block" href={href.record(s)}>{s}</a>) : <span className="font-sans text-ink-2">None</span>}</td>
                      <td className="min-w-[7.5rem] text-sm">
                        <button type="button" className="btn btn-secondary btn-sm mb-1 whitespace-nowrap" onClick={() => onView({ kind: "pdb", id: p.pdb_id })} data-testid="pdb-view">View in 3D<span className="sr-only"> {p.pdb_id}</span></button>
                        <span className="flex flex-wrap gap-x-2">
                          <Ext href={u.rcsb}>RCSB</Ext>
                          <Ext href={u.pdbe}>PDBe</Ext>
                          <a href={u.mmcif} download>mmCIF</a>
                        </span>
                      </td>
                    </tr>
                  );
                })}
                {!shown.length ? (
                  <tr><td colSpan={10} className="text-ink-2">{base.length ? "No entries match the filters." : `No experimental PDB linked to ${src.source_acc}.`}</td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
          {rows.length > PAGE ? <div className="border-t border-line p-3"><Pagination page={cur} pageCount={pageCount} total={rows.length} size={PAGE} onPage={setPage} /></div> : null}
          <p className="border-t border-line p-3 text-xs text-ink-2">
            Retinal: &quot;RET present&quot; means the PDB entry contains the retinal ligand RET as recorded in v1.6.0; &quot;not present&quot; does not show that the protein lacks retinal
            (e.g. apo-protein fragments or other chromophore codes). Resolution is not defined for NMR entries. &quot;Shared with&quot; lists other source accessions linked to the same PDB entry.
            No chain or residue mapping between PDB entries and the source sequence is claimed.
          </p>
        </div>
      )}
    </Section>
  );
}

export function PredictedSection({ src, releaseUrl, onView }: { src: SourceRecord; releaseUrl: string | null; onView: (s: StructureSel) => void }) {
  const af = src.structures.afdb;
  const pm = src.structures.predicted;
  const ok = af.status === "ok" && !!af.model_id;
  return (
    <Section id="predicted" title="Predicted structures" lead="Predicted models are not experimental structures. pLDDT is a per-residue model-confidence score (0-100), not a resolution.">
      <div className="grid gap-6 xl:grid-cols-2">
        <div className="card p-4" data-testid="afdb-block" data-status={af.status}>
          <h3 className="text-base">AlphaFold DB</h3>
          {ok ? (
            <>
              <dl className="mt-2">
                <Row k="Model"><Ext href={afdbEntryUrl(src.source_acc)}><span className="font-mono">{af.model_id}</span></Ext>{af.version !== null ? <span className="text-sm text-ink-2"> · version {af.version}</span> : null}</Row>
                <Row k="Global pLDDT">{af.global_plddt !== null ? <>{fmtNum(af.global_plddt)} <span className="text-sm text-ink-2">(mean model confidence; not resolution)</span></> : na(null)}</Row>
                <Row k="Residue range">{af.seq_start !== null && af.seq_end !== null ? `${af.seq_start}-${af.seq_end} of ${src.length}` : na(null)}</Row>
                <Row k="Sequence match">
                  {af.seq_match === true ? "AFDB sequence identical to the source sequence" : af.seq_match === false ? (
                    <span className="text-[#8a3c04]" data-testid="afdb-seq-mismatch"><FlagBadge tone="warn">mismatch</FlagBadge> The AFDB model sequence differs from the source sequence; residue numbering may not correspond.</span>
                  ) : na(null)}
                </Row>
                <Row k="Model created">{na(af.model_created)}</Row>
              </dl>
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => onView({ kind: "afdb" })} data-testid="afdb-view">View in 3D</button>
                {af.model_url ? <a className="btn btn-secondary btn-sm" href={af.model_url} download>Download model (PDB)</a> : null}
              </div>
            </>
          ) : (
            <p className="mt-2 text-sm text-ink-2" data-testid="afdb-none">No AlphaFold DB model for {src.source_acc} in v1.6.0.</p>
          )}
        </div>

        <div className="card p-4" data-testid="release-models">
          <h3 className="text-base">Other predicted models</h3>
          {pm.length ? (
            pm.map((m) => (
              <div key={m.sha256} className="mt-2" data-testid="release-model">
                <p className="font-semibold">Predicted model: {m.method}, not experimental</p>
                <dl className="mt-1 text-sm">
                  <Row k="Note (verbatim)"><q>{m.note ?? "No note recorded"}</q></Row>
                  <Row k="Mean pLDDT">{fmtNum(m.mean_plddt)} <span className="text-ink-2">(model confidence; not resolution)</span></Row>
                  <Row k="Subfamily">{na(m.subfamily)}</Row>
                  <Row k="File"><code className="break-all text-xs">{m.file}</code> · {fmtInt(m.bytes)} bytes</Row>
                  <Row k="SHA-256"><code className="break-all text-xs">{m.sha256}</code></Row>
                  <Row k="B-factor column">pLDDT stored as a fraction (0-1); the viewer multiplies by 100 for display.</Row>
                </dl>
                <p className="mt-2 text-xs text-ink-2">Method and note labels as recorded in v1.6.0.</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => onView({ kind: "pred" })} data-testid="pred-view">View in 3D</button>
                  {releaseUrl ? <a className="btn btn-secondary btn-sm" href={releaseUrl} download>Download model (PDB)</a> : null}
                </div>
              </div>
            ))
          ) : (
            <p className="mt-2 text-sm text-ink-2" data-testid="release-none">No other predicted model is distributed with the release for this source record.</p>
          )}
        </div>
      </div>
    </Section>
  );
}
