/**
 * Browse (#/browse?...). The URL query is the single source of truth for filters, sort and page;
 * in-page changes use history.replaceState so Back/Forward move between pages, not keystrokes.
 * Loads records-index.json (+ clades, vocabulary, manifest); corpus.fasta only for FASTA exports.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { href } from "../app/routes";
import { pushHash, replaceHash } from "../app/navigation";
import { CladeSupportNotice } from "../components/CladeSupportNotice";
import { Callout, Disclosure, PageTitle, Pagination } from "../components/common";
import { EmptyState, ErrorState, LoadingSkeleton } from "../components/States";
import { loadClades, loadManifest, loadRecordsIndex, loadVocabulary, useResource } from "../data/loaders";
import type { Clades, Manifest, RecordsIndex, Vocabulary } from "../data/types";
import { ExportMenu } from "../features/browse/ExportMenu";
import { FilterPanel } from "../features/browse/FilterPanel";
import { DEFAULT_VISIBILITY, ResultsTable, makeColumns, type ColumnMeta } from "../features/browse/ResultsTable";
import {
  DEFAULT_STATE, GROUPS, PAGE_SIZES, activeFilterKeys, applyFilters, filterQuery, parseBrowse, serializeBrowse, sortRows, toRows,
  type BrowseState, type GroupFilter, type SortKey,
} from "../lib/browse";
import { CLADE_STATE_LABEL, FUNC_LABEL, GROUP_LABEL, STATUS_LABEL, domainLabel, fmtInt } from "../lib/format";
import { caveatMap } from "../lib/summary";

export default function BrowsePage({ params }: { params: URLSearchParams }) {
  const data = useResource(() => Promise.all([loadRecordsIndex(), loadClades(), loadVocabulary(), loadManifest()]));
  return (
    <div className="container-page pt-6">
      <PageTitle docTitle="Browse records - MicroRhodoDB">Browse source records</PageTitle>
      {data.state === "loading" ? <LoadingSkeleton label="Loading the record index" lines={8} /> : null}
      {data.state === "error" ? <ErrorState error={data.error} retry={data.retry} what="the record index" /> : null}
      {data.state === "ready" ? <BrowseBody params={params} ri={data.data[0]} clades={data.data[1]} vocab={data.data[2]} manifest={data.data[3]} /> : null}
    </div>
  );
}

const COLS_KEY = "mrdb.browse.columns.v1";
const TEXT_KEYS = new Set(["q", "lin", "motif", "pdbid", "lmin", "lmax"]);

function BrowseBody({ params, ri, clades, vocab, manifest }: { params: URLSearchParams; ri: RecordsIndex; clades: Clades; vocab: Vocabulary; manifest: Manifest }) {
  const qs = params.toString();
  const { state: s, ignored } = useMemo(() => parseBrowse(new URLSearchParams(qs)), [qs]);
  const rows = useMemo(() => toRows(ri), [ri]);
  const total = rows.length;

  // History policy: every discrete change (tab, select, checkbox, sort, page, chip) adds one history
  // entry, so Back/Forward step through filter states. Consecutive debounced commits from the same
  // text field replace that entry instead of adding one per keystroke pause.
  const lastText = useRef<string | null>(null);
  const update = useCallback(
    (patch: Partial<BrowseState>, keepPage = false) => {
      const next = { ...s, ...patch };
      if (!keepPage) next.page = 1;
      const keys = Object.keys(patch);
      const textKey = keys.length === 1 && TEXT_KEYS.has(keys[0]) ? keys[0] : null;
      const target = href.browse(serializeBrowse(next));
      if (textKey !== null && lastText.current === textKey) replaceHash(target);
      else pushHash(target);
      lastText.current = textKey;
    },
    [s],
  );

  const fq = filterQuery(s);
  const filtered = useMemo(() => applyFilters(rows, s), [rows, fq]); // eslint-disable-line react-hooks/exhaustive-deps
  const sorted = useMemo(() => sortRows(filtered, s.sort, s.dir), [filtered, s.sort, s.dir]);
  const pageCount = Math.max(1, Math.ceil(sorted.length / s.size));
  const page = Math.min(s.page, pageCount);
  useEffect(() => {
    if (s.page !== page) replaceHash(href.browse(serializeBrowse({ ...s, page })));
  }, [s, page]);
  const pageRows = useMemo(() => sorted.slice((page - 1) * s.size, page * s.size), [sorted, page, s.size]);

  // Static context for cells.
  const ctx = useMemo(() => {
    const multiSource = new Map<string, number>();
    for (const r of rows) multiSource.set(r.mrdb_acc, (multiSource.get(r.mrdb_acc) ?? 0) + 1);
    return {
      multiSource,
      caveats: caveatMap(clades),
      statusDef: new Map<string, string>(vocab.membership_status.map((x) => [x.status, x.definition])),
      evidenceDef: new Map<string, string>(vocab.evidence_level.map((x) => [x.level, x.definition])),
    };
  }, [rows, clades, vocab]);
  const columns = useMemo(() => makeColumns(ctx), [ctx]);
  const [visibility, setVisibility] = useState(() => {
    const def = DEFAULT_VISIBILITY(columns);
    try {
      const saved = JSON.parse(localStorage.getItem(COLS_KEY) ?? "null") as Record<string, boolean> | null;
      if (saved) for (const k of Object.keys(def)) if (typeof saved[k] === "boolean") def[k] = saved[k];
    } catch {
      /* ignore unreadable preferences */
    }
    def.mrdb_acc = true;
    return def;
  });
  const setVis = (v: Record<string, boolean>) => {
    setVisibility(v);
    try {
      localStorage.setItem(COLS_KEY, JSON.stringify(v));
    } catch {
      /* storage unavailable */
    }
  };

  const residues = useMemo(() => {
    const set = new Set<string>();
    let none = false;
    for (const r of rows) {
      if (r.retinal_site_residue === null) none = true;
      else set.add(r.retinal_site_residue);
    }
    return [...[...set].sort(), ...(none ? ["none"] : [])];
  }, [rows]);

  const groupCounts = useMemo(() => {
    const m = new Map<GroupFilter, number>();
    for (const r of rows) if (s.eng || !r.is_engineered) m.set(r.membership_group, (m.get(r.membership_group) ?? 0) + 1);
    m.set("all", [...m.values()].reduce((a, b) => a + b, 0));
    return m;
  }, [rows, s.eng]);
  const nEngineered = useMemo(() => rows.filter((r) => r.is_engineered).length, [rows]);

  const cav = ctx.caveats;
  const caveatHits = useMemo(() => {
    const out = new Map<string, number>();
    for (const r of filtered) {
      const id = r.clade_state === "tentative" ? r.tentative_clade_id : r.clade_id;
      if (id && cav.has(id)) out.set(id, (out.get(id) ?? 0) + 1);
    }
    return out;
  }, [filtered, cav]);

  const nMrdb = useMemo(() => new Set(filtered.map((r) => r.mrdb_acc)).size, [filtered]);
  const scope = s.group === "all" ? "All records" : GROUP_LABEL[s.group];
  const active = activeFilterKeys(s);

  const onSort = (k: SortKey) => {
    if (s.sort !== k) update({ sort: k, dir: "asc" }, true);
    else if (s.dir === "asc") update({ dir: "desc" }, true);
    else update({ sort: "", dir: "asc" }, true);
  };

  const filters = <FilterPanel s={s} update={update} clades={clades} vocab={vocab} residues={residues} />;

  return (
    <>
      <p className="-mt-4 mb-4 max-w-4xl text-ink-2" data-testid="browse-scope">
        <strong className="text-ink">{scope}</strong>
        {s.eng ? ", engineered constructs included" : ", engineered constructs hidden"}
        {active.length ? `, ${active.length} additional filter${active.length > 1 ? "s" : ""}` : ""}:{" "}
        <strong className="tabular text-ink" data-testid="browse-count">{fmtInt(filtered.length)}</strong> of{" "}
        <span className="tabular" data-testid="browse-total">{fmtInt(total)}</span> source records
        (<span className="tabular">{fmtInt(nMrdb)}</span> MRDB accessions).
        {s.group === "member" && !active.length ? " The database also contains candidates, boundary families, heliorhodopsins and decoys; choose a view below." : ""}
      </p>

      {ignored.length ? (
        <div className="mb-4" role="status" data-testid="ignored-params">
          <Callout tone="warn" title="Some link parameters were not applied">
            {ignored.map((x) => <code key={x.key + x.value} className="mr-2">{x.key}={x.value}</code>)}
            <span>These values are not valid Browse filters and were ignored; the table shows the remaining filters.</span>
          </Callout>
        </div>
      ) : null}

      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-3">
        <div role="group" aria-label="Record population" className="flex flex-wrap gap-1.5" data-testid="group-tabs">
          {GROUPS.map((g) => (
            <button
              key={g}
              type="button"
              aria-pressed={s.group === g}
              onClick={() => update({ group: g, status: "" })}
              className={`btn btn-sm ${s.group === g ? "btn-primary" : "btn-secondary"}`}
              data-group={g}
            >
              {g === "all" ? "All records" : GROUP_LABEL[g]}
              <span className={`tabular text-xs ${s.group === g ? "text-white/90" : "text-ink-2"}`}>{fmtInt(groupCounts.get(g) ?? 0)}</span>
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="h-4 w-4 accent-[#1665b5]" checked={s.eng} onChange={(e) => update({ eng: e.target.checked })} data-testid="toggle-eng" />
          Include engineered constructs ({fmtInt(nEngineered)})
        </label>
      </div>

      <div className="grid gap-6 lg:grid-cols-[17.5rem_minmax(0,1fr)]">
        <aside aria-label="Filters" className="lg:sticky lg:top-20 lg:max-h-[calc(100vh-6rem)] lg:self-start lg:overflow-y-auto lg:pr-1">
          <div className="hidden lg:block">
            <h2 className="mb-3 text-base">Filters</h2>
            {filters}
          </div>
          <details className="card p-3 lg:hidden" data-testid="mobile-filters">
            <summary className="cursor-pointer font-semibold">Filters{active.length ? ` (${active.length} active)` : ""}</summary>
            <div className="mt-3">{filters}</div>
          </details>
        </aside>

        <div className="min-w-0 space-y-3">
          {active.length ? (
            <div className="flex flex-wrap items-center gap-2" data-testid="filter-chips">
              <span className="text-sm text-ink-2">Active filters:</span>
              {active.map((k) => (
                <button key={k} type="button" className="badge badge-info cursor-pointer" onClick={() => update({ [k]: DEFAULT_STATE[k] } as Partial<BrowseState>)} aria-label={`Remove filter ${chipLabel(k, s)}`}>
                  {chipLabel(k, s)} <span aria-hidden="true">×</span>
                </button>
              ))}
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => update({ ...DEFAULT_STATE, group: s.group, eng: s.eng, sort: s.sort, dir: s.dir, size: s.size })} data-testid="clear-filters">
                Clear filters
              </button>
            </div>
          ) : null}

          {caveatHits.size ? (
            <CladeSupportNotice
              clades={clades}
              only={[...caveatHits.keys()]}
              compact
              extra={[...caveatHits].map(([id, n]) => (
                <p key={id} className="mt-1" data-testid="caveat-count">
                  {fmtInt(n)} record{n === 1 ? "" : "s"} in this selection {n === 1 ? "is" : "are"} assigned to or tentatively placed near <span className="font-mono">{id}</span>.
                </p>
              ))}
            />
          ) : null}

          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <label htmlFor="page-size" className="text-ink-2">Rows per page</label>
              <select id="page-size" className="field w-auto" style={{ minHeight: "2.25rem" }} value={s.size} onChange={(e) => update({ size: Number(e.target.value) })} data-testid="page-size">
                {PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
              <Disclosure label="Columns" align="left">
                {() => (
                  <fieldset className="grid gap-1 p-1" data-testid="column-menu">
                    <legend className="mb-1 text-sm font-semibold">Visible columns</legend>
                    {columns.map((c) => {
                      const meta = c.meta as ColumnMeta;
                      const id = `col-${c.id}`;
                      return (
                        <div key={c.id} className="flex items-center gap-2">
                          <input id={id} type="checkbox" className="h-4 w-4 accent-[#1665b5]" disabled={c.id === "mrdb_acc"} checked={visibility[c.id!] !== false} onChange={(e) => setVis({ ...visibility, [c.id!]: e.target.checked })} />
                          <label htmlFor={id} className="text-sm">{meta.label}</label>
                        </div>
                      );
                    })}
                    <button type="button" className="btn btn-secondary btn-sm mt-1" onClick={() => setVis(DEFAULT_VISIBILITY(columns))}>Reset columns</button>
                  </fieldset>
                )}
              </Disclosure>
            </div>
            <ExportMenu rows={sorted} filterQ={fq} sortKey={s.sort} sortDir={s.dir} manifest={manifest} />
          </div>

          {sorted.length === 0 ? (
            <EmptyState title="No records match these filters">
              <p>Try removing a filter, choosing <a href={href.browse("group=all&eng=1")}>All records</a>, or including tentative placements.</p>
            </EmptyState>
          ) : (
            <>
              <ResultsTable
                rows={pageRows}
                columns={columns}
                visibility={visibility}
                sortKey={s.sort}
                sortDir={s.dir}
                onSort={onSort}
                caption={`${scope}: ${filtered.length} matching source records, page ${page} of ${pageCount}`}
              />
              <Pagination page={page} pageCount={pageCount} total={sorted.length} size={s.size} onPage={(p) => update({ page: p }, true)} />
            </>
          )}

          <details className="card p-4 text-sm" data-testid="definitions">
            <summary className="cursor-pointer font-semibold">Definitions used in this table</summary>
            <div className="mt-3 grid gap-6 md:grid-cols-2">
              <div>
                <h3 className="text-sm">Membership status</h3>
                <dl className="mt-1 space-y-1.5">
                  {vocab.membership_status.map((m) => (
                    <div key={m.status}><dt className="font-medium">{STATUS_LABEL[m.status]} <code className="text-xs text-ink-2">{m.status}</code></dt><dd className="text-ink-2">{m.definition}</dd></div>
                  ))}
                </dl>
              </div>
              <div>
                <h3 className="text-sm">Evidence level</h3>
                <dl className="mt-1 space-y-1.5">
                  {vocab.evidence_level.map((e) => (
                    <div key={e.level}><dt className="font-mono font-semibold">{e.level}</dt><dd className="text-ink-2">{e.definition}</dd></div>
                  ))}
                </dl>
                <p className="mt-2 text-ink-2">{vocab.evidence_note}</p>
                <h3 className="mt-4 text-sm">Clade placement</h3>
                <dl className="mt-1 space-y-1.5">
                  {vocab.clade_state.map((c) => (
                    <div key={c.state}><dt className="font-medium">{CLADE_STATE_LABEL[c.state]} <code className="text-xs text-ink-2">{c.state}</code></dt><dd className="text-ink-2">{c.definition}</dd></div>
                  ))}
                </dl>
              </div>
            </div>
          </details>
        </div>
      </div>
    </>
  );
}

function chipLabel(k: keyof BrowseState, s: BrowseState): string {
  const v = s[k];
  switch (k) {
    case "status": return `Status: ${STATUS_LABEL[s.status as keyof typeof STATUS_LABEL]}`;
    case "func": return `Function: ${FUNC_LABEL[s.func as keyof typeof FUNC_LABEL]}`;
    case "evidence": return `Evidence: ${v}`;
    case "q": return `Text: "${v}"`;
    case "clade": return `Clade: ${v}${s.tent ? " (+tentative)" : ""}`;
    case "tent": return "Include tentative";
    case "sub": return `Subclade: ${v}`;
    case "state": return `Placement: ${CLADE_STATE_LABEL[s.state as keyof typeof CLADE_STATE_LABEL]}`;
    case "domain": return `Domain: ${s.domain === "none" ? domainLabel(null) : v}`;
    case "motif": return `Motif: ${v}`;
    case "residue": return `Residue: ${v === "none" ? "not reported" : v}`;
    case "pdb": return "Has PDB";
    case "pdbid": return `PDB: ${v}`;
    case "afdb": return `AlphaFold DB: ${v === "1" ? "yes" : "no"}`;
    case "conflict": return "Call conflict";
    case "curated": return "Curated override";
    case "eng": return "Engineered included";
    case "pub": return "Supporting publication";
    case "lin": return `Lineage: "${v}"`;
    case "lmin": return `Length >= ${v}`;
    case "lmax": return `Length <= ${v}`;
    default: return `${k}: ${String(v)}`;
  }
}
