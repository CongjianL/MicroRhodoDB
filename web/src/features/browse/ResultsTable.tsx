/**
 * Browse results table (TanStack Table v8, headless). Sorting and pagination are done by the URL-driven
 * browse model (manualSorting/manualPagination); TanStack manages columns and visibility.
 */
import { flexRender, getCoreRowModel, useReactTable, type ColumnDef, type VisibilityState } from "@tanstack/react-table";
import { href } from "../../app/routes";
import { CladeBadge, EvidenceBadge, FlagBadge, FunctionLabel, MembershipBadge } from "../../components/Badges";
import type { IndexRow, SortKey } from "../../lib/browse";
import { CLADE_STATE_LABEL, domainLabel, fmtInt } from "../../lib/format";

export interface ColumnMeta {
  sortKey?: SortKey;
  numeric?: boolean;
  label: string;
  optional?: boolean; // hidden by default
  description?: string;
}

export interface TableContext {
  multiSource: Map<string, number>;
  caveats: Map<string, string>;
  statusDef: Map<string, string>;
  evidenceDef: Map<string, string>;
}

const NR = <span className="text-ink-2">Not reported</span>;

export function makeColumns(ctx: TableContext): ColumnDef<IndexRow>[] {
  const col = (id: string, meta: ColumnMeta, cell: (r: IndexRow) => React.ReactNode): ColumnDef<IndexRow> => ({
    id,
    header: meta.label,
    meta,
    cell: (c) => cell(c.row.original),
    enableHiding: id !== "mrdb_acc",
  });
  return [
    col("mrdb_acc", { label: "MRDB accession", sortKey: "mrdb_acc" }, (r) => {
      const n = ctx.multiSource.get(r.mrdb_acc) ?? 1;
      return (
        <span className="flex flex-col items-start gap-0.5">
          <a href={href.record(r.mrdb_acc)} className="font-mono text-[0.8125rem] font-medium">{r.mrdb_acc}</a>
          {n > 1 ? (
            <span className="text-xs text-ink-2" title={`${n} source records share this MRDB accession (identical sequence)`}>
              {r.is_mrdb_representative ? "representative" : "member"} of {n}
            </span>
          ) : null}
        </span>
      );
    }),
    col("source_acc", { label: "Source accession", sortKey: "source_acc" }, (r) => (
      <span className="flex flex-col items-start gap-0.5">
        <a href={href.record(r.source_acc)} className="font-mono text-[0.8125rem]">{r.source_acc}</a>
        <span className="flex flex-wrap gap-1">
          {r.reviewed ? <FlagBadge title="UniProtKB/Swiss-Prot reviewed entry">reviewed</FlagBadge> : null}
          {r.is_engineered ? <FlagBadge tone="warn" title={`Engineered construct; not counted. Wild type: ${r.wild_type_acc ?? "not reported"}`}>engineered</FlagBadge> : null}
        </span>
      </span>
    )),
    col("protein_name", { label: "Protein", sortKey: "protein_name" }, (r) => (
      <span className="block min-w-[12rem] max-w-[22rem]">
        {/* long names are clamped to two lines; the full value is in the tooltip, the record page and exports */}
        <span className="line-clamp-2" title={r.protein_name ?? undefined}>{r.protein_name ?? NR}</span>
        {r.novel_family_flag ? <FlagBadge tone="info" title="Novel-family profile hit (flag only, not a reclassification)">{r.novel_family_flag}</FlagBadge> : null}
      </span>
    )),
    col("organism", { label: "Organism", sortKey: "organism" }, (r) => (
      <span className="block min-w-[12rem] max-w-[18rem]">
        <span className="line-clamp-2" title={r.organism ?? undefined}>{r.organism ?? NR}</span>
        <span className="block text-xs text-ink-2">{domainLabel(r.tax_domain)}</span>
      </span>
    )),
    col("tax_domain", { label: "Domain", sortKey: "tax_domain", optional: true }, (r) => domainLabel(r.tax_domain)),
    col("length", { label: "Length (aa)", sortKey: "length", numeric: true }, (r) => fmtInt(r.length)),
    col("membership_status", { label: "Membership", sortKey: "membership_status" }, (r) => (
      <MembershipBadge status={r.membership_status} definition={ctx.statusDef.get(r.membership_status)} />
    )),
    col("membership_score", { label: "Membership score", sortKey: "membership_score", numeric: true, optional: true }, (r) =>
      r.membership_score === null ? NR : r.membership_score.toFixed(3)),
    col("func_class", { label: "Function", sortKey: "func_class" }, (r) => (
      <span className="flex flex-col items-start gap-0.5">
        <FunctionLabel func={r.func_class} />
        {r.call_conflict ? <FlagBadge tone="warn" title={r.call_conflict_detail ?? "Function-call conflict"}>call conflict</FlagBadge> : null}
      </span>
    )),
    col("evidence_level", { label: "Evidence", sortKey: "evidence_level" }, (r) => (
      <EvidenceBadge level={r.evidence_level} definition={ctx.evidenceDef.get(r.evidence_level)} />
    )),
    col("clade", { label: "Clade", sortKey: "clade" }, (r) => (
      <CladeBadge state={r.clade_state} cladeId={r.clade_id} tentativeId={r.tentative_clade_id} failing={ctx.caveats} />
    )),
    col("subclade_id", { label: "Subclade", optional: true }, (r) =>
      r.subclade_id ? <span className="font-mono text-[0.8125rem]">{r.subclade_id}</span> : <span className="text-ink-2">None</span>),
    col("clade_state", { label: "Placement state", optional: true }, (r) => CLADE_STATE_LABEL[r.clade_state]),
    col("n_pdb", { label: "Experimental PDB", sortKey: "n_pdb", numeric: false }, (r) =>
      r.n_pdb ? (
        <span className="block min-w-[7rem] font-mono text-[0.8125rem]" title={r.pdb_ids.join(", ")}>
          {r.pdb_ids.slice(0, 3).join(", ")}
          {r.pdb_ids.length > 3 ? <span className="font-sans text-ink-2"> +{r.pdb_ids.length - 3} more</span> : null}
        </span>
      ) : <span className="text-ink-2">None</span>),
    col("structures", { label: "Structure availability", sortKey: "has_afdb" }, (r) => {
      const parts: React.ReactNode[] = [];
      if (r.n_pdb) parts.push(<FlagBadge key="p" title={`${r.n_pdb} experimental PDB entries`}>PDB ({r.n_pdb})</FlagBadge>);
      if (r.has_afdb) parts.push(<FlagBadge key="a" title={`AlphaFold DB ${r.afdb_model_id ?? ""}${r.afdb_global_plddt !== null ? `, mean pLDDT ${r.afdb_global_plddt}` : ""}`}>AlphaFold DB</FlagBadge>);
      if (r.has_predicted) parts.push(<FlagBadge key="m" title="Other predicted structure model (non-AlphaFold DB)">Predicted</FlagBadge>);
      return parts.length ? <span className="flex flex-wrap gap-1">{parts}</span> : <span className="text-ink-2">None</span>;
    }),
    col("helixC_motif", { label: "Helix-C motif", sortKey: "helixC_motif", optional: true }, (r) =>
      r.helixC_motif ? <span className="font-mono">{r.helixC_motif}</span> : NR),
    col("retinal_site_residue", { label: "Retinal-site residue", sortKey: "retinal_site_residue", optional: true }, (r) =>
      r.retinal_site_residue ? <span className="font-mono">{r.retinal_site_residue}</span> : NR),
    col("n_support_links", { label: "Supporting publications", sortKey: "n_support_links", numeric: true, optional: true }, (r) => fmtInt(r.n_support_links)),
    col("lineage", { label: "Lineage", optional: true }, (r) => <span className="block min-w-[16rem] max-w-[28rem] text-xs">{r.lineage ?? NR}</span>),
  ];
}

export const DEFAULT_VISIBILITY = (cols: ColumnDef<IndexRow>[]): VisibilityState =>
  Object.fromEntries(cols.map((c) => [c.id!, !(c.meta as ColumnMeta).optional]));

export function ResultsTable({ rows, columns, visibility, sortKey, sortDir, onSort, caption }: {
  rows: IndexRow[];
  columns: ColumnDef<IndexRow>[];
  visibility: VisibilityState;
  sortKey: SortKey | "";
  sortDir: "asc" | "desc";
  onSort: (k: SortKey) => void;
  caption: string;
}) {
  const table = useReactTable({
    data: rows,
    columns,
    state: { columnVisibility: visibility },
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualPagination: true,
    getRowId: (r) => r.source_acc,
  });
  return (
    <div className="card overflow-x-auto" role="region" aria-label="Results table; scroll horizontally for more columns" tabIndex={0} data-testid="results-scroll">
      <table className="data-table sticky-first" data-testid="results-table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => {
                const meta = h.column.columnDef.meta as ColumnMeta;
                const sorted = meta.sortKey && meta.sortKey === sortKey ? sortDir : null;
                return (
                  <th
                    key={h.id}
                    scope="col"
                    className={meta.numeric ? "num" : undefined}
                    aria-sort={sorted === "asc" ? "ascending" : sorted === "desc" ? "descending" : meta.sortKey ? "none" : undefined}
                    data-col={h.column.id}
                  >
                    {meta.sortKey ? (
                      <button
                        type="button"
                        className="inline-flex items-center gap-1 rounded font-semibold text-ink hover:text-accent"
                        onClick={() => onSort(meta.sortKey!)}
                        title={`Sort by ${meta.label}`}
                      >
                        {flexRender(h.column.columnDef.header, h.getContext())}
                        <SortIcon dir={sorted} />
                      </button>
                    ) : (
                      flexRender(h.column.columnDef.header, h.getContext())
                    )}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} data-source={row.original.source_acc}>
              {row.getVisibleCells().map((cell) => {
                const meta = cell.column.columnDef.meta as ColumnMeta;
                return (
                  <td key={cell.id} className={meta.numeric ? "num" : undefined} data-col={cell.column.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SortIcon({ dir }: { dir: "asc" | "desc" | null }) {
  return (
    <svg aria-hidden="true" width="10" height="14" viewBox="0 0 10 14" className={dir ? "text-accent" : "text-line-strong"}>
      <path d="M5 1l4 5H1z" fill={dir === "asc" ? "currentColor" : dir ? "#c3ced9" : "currentColor"} />
      <path d="M5 13l4-5H1z" fill={dir === "desc" ? "currentColor" : dir ? "#c3ced9" : "currentColor"} />
    </svg>
  );
}
