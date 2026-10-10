/**
 * Browse exports (spec section 5.4). Pure functions; unit tested against the legacy v1.6.0 oracle.
 *
 * TSV: the 39 legacy columns in legacy order (site/app.js downloadTSV), then PR-2 columns appended.
 *   - missing values are empty cells; booleans are 1/0 (legacy encoding);
 *   - numbers are written at full exported precision (legacy data.js rounded membership_score and
 *     e2_identity to 3 decimals and afdb_global_plddt to 1; contract deviation T1);
 *   - clade_confidence is derived from clade_state (contract mapping T4);
 *   - tab/CR/LF inside text are replaced by a space so every record stays on one line.
 * FASTA (source records): exact legacy header, sequence wrapped at 60 columns.
 * FASTA (unique MRDB sequences): one entry per MRDB accession present in the selection.
 */
import type { IndexRow } from "./browse";

export const LEGACY_TSV_COLUMNS = [
  "mrdb_acc", "source_acc", "protein_name", "organism", "tax_domain", "length", "membership_status",
  "membership_score", "retinal_site_residue", "func_class", "evidence_level", "function_basis", "func_class_v14",
  "helixC_motif", "motif_class", "call_conflict", "call_conflict_detail", "is_engineered", "wild_type_acc",
  "counts_eligible", "exact_duplicate_of", "e1_representative", "clade_id", "subclade_id", "clade_name",
  "tentative_clade_id", "tentative_clade_name", "gtdb_taxonomy", "afdb_model_id", "afdb_global_plddt", "reviewed",
  "e2_ref", "e2_identity", "override_rule", "pocket_string_br", "status_reason", "novel_family_flag",
  "is_mrdb_representative", "clade_confidence",
] as const;

export const EXTRA_TSV_COLUMNS = [
  "clade_state", "membership_group", "n_pdb", "pdb_ids", "has_afdb", "has_predicted", "n_support_links", "lineage",
] as const;

export const TSV_COLUMNS = [...LEGACY_TSV_COLUMNS, ...EXTRA_TSV_COLUMNS];

export function cladeConfidence(r: IndexRow): "confident" | "tentative" | "none" {
  return r.clade_state === "confident" ? "confident" : r.clade_state === "tentative" ? "tentative" : "none";
}

export function tsvCell(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "boolean") return v ? "1" : "0";
  if (Array.isArray(v)) return v.map(tsvCell).join(";");
  if (typeof v === "number") return Number.isFinite(v) ? String(v) : "";
  return String(v).replace(/[\t\r\n]+/g, " ");
}

export function tsvValue(r: IndexRow, c: (typeof TSV_COLUMNS)[number]): unknown {
  return c === "clade_confidence" ? cladeConfidence(r) : (r as unknown as Record<string, unknown>)[c];
}

export function toTSV(rows: IndexRow[]): string {
  const lines = [TSV_COLUMNS.join("\t")];
  for (const r of rows) lines.push(TSV_COLUMNS.map((c) => tsvCell(tsvValue(r, c))).join("\t"));
  return lines.join("\n") + "\n";
}

/** Legacy clade_display (site/app.js). */
export function cladeDisplay(r: IndexRow): string {
  const c = cladeConfidence(r);
  return c === "confident" ? (r.clade_id ?? "") : c === "tentative" ? `TENTATIVE:${r.tentative_clade_id}` : "";
}

export const wrap60 = (s: string) => s.replace(/(.{60})/g, "$1\n").replace(/\n$/, "");

export function fastaHeader(r: IndexRow): string {
  return `>${r.mrdb_acc} ${r.source_acc} status=${r.membership_status} evidence=${r.evidence_level} ` +
    `func=${r.func_class} clade=${cladeDisplay(r) || "none"} engineered=${r.is_engineered ? 1 : 0}`;
}

export function toFasta(rows: IndexRow[], seqs: Map<string, string>): string {
  return rows.map((r) => {
    const s = seqs.get(r.source_acc);
    if (!s) throw new Error(`No sequence for ${r.source_acc}`);
    if (s.length !== r.length) throw new Error(`Sequence length mismatch for ${r.source_acc}`);
    return `${fastaHeader(r)}\n${wrap60(s)}\n`;
  }).join("");
}

/** One entry per MRDB accession (identical sequences), in first-appearance order of the selection. */
export function toUniqueFasta(rows: IndexRow[], seqs: Map<string, string>): { text: string; n: number } {
  const groups = new Map<string, IndexRow[]>();
  for (const r of rows) {
    const g = groups.get(r.mrdb_acc);
    if (g) g.push(r);
    else groups.set(r.mrdb_acc, [r]);
  }
  let text = "";
  for (const [mrdb, rs] of groups) {
    const s = seqs.get(rs[0].source_acc);
    if (!s) throw new Error(`No sequence for ${rs[0].source_acc}`);
    for (const r of rs) {
      if (seqs.get(r.source_acc) !== s) throw new Error(`${mrdb}: source sequences differ`);
    }
    text += `>${mrdb} selected_source_records=${rs.map((r) => r.source_acc).join(",")}\n${wrap60(s)}\n`;
  }
  return { text, n: groups.size };
}

/** 32-bit FNV-1a hash as 8 hex digits (stable selection id for file names). */
export function fnv1a(s: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, "0");
}

export type ExportKind = "records_tsv" | "records_fasta" | "mrdb_fasta" | "manifest";

export function exportFilename(release: string, kind: ExportKind, n: number, filterQ: string): string {
  const id = fnv1a(filterQ);
  const base = `microrhododb_v${release}_browse_${id}`;
  switch (kind) {
    case "records_tsv": return `${base}_${n}_source_records.tsv`;
    case "records_fasta": return `${base}_${n}_source_records.fasta`;
    case "mrdb_fasta": return `${base}_${n}_mrdb_sequences.fasta`;
    case "manifest": return `${base}_selection.json`;
  }
}

export interface SelectionManifest {
  database: "MicroRhodoDB";
  dataset_release: string;
  release_date: string | null;
  schema_version: string;
  website_version: string;
  source_db_sha256: string;
  selection_id: string;
  filter_query: string;
  filters: Record<string, string>;
  sort: { key: string; dir: string } | null;
  n_source_records: number;
  n_mrdb_accessions: number;
  n_engineered_in_selection: number;
  files: Record<string, string>;
  tsv_columns: string[];
  notes: string[];
  generated_at: string;
}

export function selectionManifest(args: {
  release: string; releaseDate: string | null; schemaVersion: string; websiteVersion: string; dbSha: string;
  filterQ: string; sortKey: string; sortDir: string; rows: IndexRow[]; now: Date;
}): SelectionManifest {
  const { release, filterQ, rows } = args;
  const mrdb = new Set(rows.map((r) => r.mrdb_acc));
  return {
    database: "MicroRhodoDB",
    dataset_release: release,
    release_date: args.releaseDate,
    schema_version: args.schemaVersion,
    website_version: args.websiteVersion,
    source_db_sha256: args.dbSha,
    selection_id: fnv1a(filterQ),
    filter_query: filterQ,
    filters: Object.fromEntries(new URLSearchParams(filterQ)),
    sort: args.sortKey ? { key: args.sortKey, dir: args.sortDir } : null,
    n_source_records: rows.length,
    n_mrdb_accessions: mrdb.size,
    n_engineered_in_selection: rows.filter((r) => r.is_engineered).length,
    files: {
      records_tsv: exportFilename(release, "records_tsv", rows.length, filterQ),
      records_fasta: exportFilename(release, "records_fasta", rows.length, filterQ),
      mrdb_fasta: exportFilename(release, "mrdb_fasta", mrdb.size, filterQ),
    },
    tsv_columns: [...TSV_COLUMNS],
    notes: [
      "Rows are source records (UniProt accessions); several source records can share one MRDB accession (identical sequence).",
      "Empty filter_query = default Browse filters: group=member (Type-I members), engineered constructs hidden.",
      "TSV: legacy v1.6.0 columns first (same order), PR-2 columns appended; booleans 1/0; numbers at full exported precision.",
      "E1-E5 are evidence types, not probabilities; membership status and evidence level are separate axes.",
    ],
    generated_at: args.now.toISOString(),
  };
}

export function saveText(text: string, filename: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
