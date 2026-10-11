/**
 * Unified text search over records-index.json (spec section 9.1). Pure and deterministic.
 *
 * Every result reports which field matched. Identifiers match exactly (or by prefix for accessions);
 * PDB IDs match only the stored protein_pdb links (pdb_ids column), never protein names; free text
 * (protein name, organism, lineage, GTDB taxonomy, clade name) matches case-insensitive substrings.
 * Ranking: exact identifier > exact PDB/clade/motif/function code > accession prefix > word-start
 * text match > other substring; ties keep records-index order (stable).
 */
import { applyFilters, parseBrowse, type IndexRow } from "../../lib/browse";
import { FUNC_LABEL } from "../../lib/format";

export type MatchField =
  | "mrdb_acc" | "source_acc" | "pdb_id" | "clade_id" | "subclade_id" | "tentative_clade_id" | "helixC_motif" | "func_class"
  | "protein_name" | "organism" | "clade_name" | "lineage" | "gtdb_taxonomy";

export const FIELD_LABEL: Record<MatchField, string> = {
  mrdb_acc: "MRDB accession",
  source_acc: "Source accession",
  pdb_id: "PDB entry (protein_pdb)",
  clade_id: "Clade",
  subclade_id: "Subclade",
  tentative_clade_id: "Tentative placement",
  helixC_motif: "Helix-C motif",
  func_class: "Functional class",
  protein_name: "Protein name",
  organism: "Organism",
  clade_name: "Clade name",
  lineage: "NCBI lineage",
  gtdb_taxonomy: "GTDB taxonomy",
};

export interface TextHit {
  row: IndexRow;
  field: MatchField;
  value: string;
  score: number;
}

export interface TextResult {
  query: string;
  hits: TextHit[];
  total: number;
  truncated: boolean;
  /** Source accessions of all hits (not only the displayed, truncated list). */
  keys: Set<string>;
  /** Which kind of query this looked like (for explanations). */
  kind: "empty" | "too_short" | "identifier" | "text";
}

const ACC_RE = /^(MRDB\d{1,6}|[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2})$/i;
const PDB_RE = /^[0-9][A-Z0-9]{3}$/i;
const CLADE_RE = /^MR_CLD3_/i;

function wordStart(hay: string, needle: string): boolean {
  let i = hay.indexOf(needle);
  while (i >= 0) {
    if (i === 0 || /[\s,;()\-/[\]]/.test(hay[i - 1])) return true;
    i = hay.indexOf(needle, i + 1);
  }
  return false;
}

/** Best match of one row, or null. */
export function matchRow(r: IndexRow, qRaw: string): Omit<TextHit, "row"> | null {
  const q = qRaw.trim();
  const ql = q.toLowerCase();
  const qu = q.toUpperCase();
  let best: Omit<TextHit, "row"> | null = null;
  const consider = (field: MatchField, value: string | null | undefined, score: number) => {
    if (value && (!best || score > best.score)) best = { field, value, score };
  };
  // Identifiers (exact, then prefix).
  if (r.mrdb_acc === qu) consider("mrdb_acc", r.mrdb_acc, 100);
  if (r.source_acc === qu) consider("source_acc", r.source_acc, 100);
  if (PDB_RE.test(q) && r.pdb_ids.includes(qu)) consider("pdb_id", qu, 95);
  if (CLADE_RE.test(q)) {
    if (r.clade_id && r.clade_id.toUpperCase() === qu) consider("clade_id", r.clade_id, 90);
    if (r.subclade_id && r.subclade_id.toUpperCase() === qu) consider("subclade_id", r.subclade_id, 90);
    if (r.tentative_clade_id && r.tentative_clade_id.toUpperCase() === qu) consider("tentative_clade_id", r.tentative_clade_id, 85);
    if (r.subclade_id && r.subclade_id.toUpperCase().startsWith(qu)) consider("subclade_id", r.subclade_id, 70);
  }
  if (r.helixC_motif && q.length >= 2 && q.length <= 5 && r.helixC_motif === qu) consider("helixC_motif", r.helixC_motif, 80);
  if (r.func_class === ql || FUNC_LABEL[r.func_class].toLowerCase() === ql) consider("func_class", FUNC_LABEL[r.func_class], 75);
  if (q.length >= 3) {
    if (r.mrdb_acc.startsWith(qu)) consider("mrdb_acc", r.mrdb_acc, 60);
    if (r.source_acc.startsWith(qu)) consider("source_acc", r.source_acc, 60);
  }
  // Free text.
  if (ql.length >= 2) {
    const text: [MatchField, string | null, number, number][] = [
      ["protein_name", r.protein_name, 45, 35],
      ["organism", r.organism, 44, 34],
      ["clade_name", r.clade_name, 42, 32],
      ["lineage", r.lineage, 25, 20],
      ["gtdb_taxonomy", r.gtdb_taxonomy, 24, 19],
    ];
    for (const [f, v, ws, sub] of text) {
      if (!v) continue;
      const vl = v.toLowerCase();
      if (vl === ql) consider(f, v, ws + 10);
      else if (wordStart(vl, ql)) consider(f, v, ws);
      else if (vl.includes(ql)) consider(f, v, sub);
    }
  }
  return best;
}

export function textSearch(rows: readonly IndexRow[], qRaw: string, limit = 200): TextResult {
  const q = qRaw.trim().slice(0, 200);
  if (!q) return { query: q, hits: [], total: 0, truncated: false, keys: new Set(), kind: "empty" };
  if (q.length < 2) return { query: q, hits: [], total: 0, truncated: false, keys: new Set(), kind: "too_short" };
  const hits: TextHit[] = [];
  for (const row of rows) {
    const m = matchRow(row, q);
    if (m) hits.push({ row, ...m });
  }
  // Stable: Array.prototype.sort is stable, rows are visited in index order.
  hits.sort((a, b) => b.score - a.score);
  return {
    query: q,
    hits: hits.slice(0, limit),
    total: hits.length,
    truncated: hits.length > limit,
    keys: new Set(hits.map((h) => h.row.source_acc)),
    kind: ACC_RE.test(q) || PDB_RE.test(q) || CLADE_RE.test(q) ? "identifier" : "text",
  };
}

/** Count hits per matched field (for the "matched in" summary). */
export function fieldCounts(hits: readonly TextHit[]): [MatchField, number][] {
  const m = new Map<MatchField, number>();
  for (const h of hits) m.set(h.field, (m.get(h.field) ?? 0) + 1);
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
}

/* ------------------------------------------------------------------ Search -> Browse (PR-5a) */

export interface BrowseOption {
  /** Browse filter query (always over all records, engineered constructs included). */
  query: string;
  /** What the Browse filter selects. */
  label: string;
  /** Number of source records Browse returns for `query`. */
  n: number;
  /** True only when the Browse accession set equals the full text-search hit set. */
  same: boolean;
  /** Search hits that Browse does not return / Browse records that are not search hits. */
  onlySearch: number;
  onlyBrowse: number;
}

const PDB_ID_RE = /^[0-9][A-Z0-9]{3}$/;
const CLADE_ID_RE = /^MR_CLD3_(?:\d{3}|B\d{2})$/;
const SUBCLADE_ID_RE = /^MR_CLD3_(?:\d{3}|B\d{2})\.\d{2}$/;
const MOTIF_RE = /^[A-Z-]{2,5}$/;

/**
 * Structured Browse views corresponding to a text query, in order of specificity. Each candidate is
 * evaluated with the real Browse filter (parseBrowse + applyFilters) and compared with the complete
 * set of text-search hits, so the page never claims "the same records" unless the accession sets are
 * identical. Structured fields (clade, subclade, PDB, motif, function) map to their exact Browse
 * filters; the Browse free-text filter searches fewer fields than this page and is offered last.
 */
export function browseOptions(rows: readonly IndexRow[], qRaw: string, keys: ReadonlySet<string>): BrowseOption[] {
  const q = qRaw.trim().slice(0, 200);
  const qu = q.toUpperCase();
  const ql = q.toLowerCase();
  const cands: [string, string][] = [];
  if (CLADE_ID_RE.test(qu)) {
    cands.push([`clade=${qu}`, `Formal assignments to clade ${qu}`]);
    cands.push([`clade=${qu}&tent=1`, `Clade ${qu} including tentative placements`]);
  } else if (SUBCLADE_ID_RE.test(qu)) {
    cands.push([`sub=${qu}`, `Subclade ${qu}`]);
  }
  if (PDB_ID_RE.test(qu)) cands.push([`pdbid=${qu}`, `Records linked to PDB entry ${qu}`]);
  if (MOTIF_RE.test(qu) && rows.some((r) => r.helixC_motif === qu)) cands.push([`motif=${qu}`, `Helix-C motif ${qu}`]);
  const func = rows.find((r) => r.func_class === ql || FUNC_LABEL[r.func_class].toLowerCase() === ql)?.func_class;
  if (func) cands.push([`func=${func}`, `Functional class ${FUNC_LABEL[func]}`]);
  cands.push([`q=${encodeURIComponent(q)}`, "Browse free-text filter (accession, protein, organism, motif, clade name)"]);
  const out: BrowseOption[] = [];
  for (const [filter, label] of cands) {
    const query = `group=all&${filter}&eng=1`;
    const { state, ignored } = parseBrowse(new URLSearchParams(query));
    if (ignored.length) continue;
    const sel = applyFilters(rows as IndexRow[], state);
    let both = 0;
    for (const r of sel) if (keys.has(r.source_acc)) both++;
    out.push({ query, label, n: sel.length, same: both === keys.size && both === sel.length, onlySearch: keys.size - both, onlyBrowse: sel.length - both });
  }
  return out;
}
