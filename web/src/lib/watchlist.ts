/** Watchlist candidate rows (novel_family_candidate) and their TSV export. No membership, evidence or function field exists. */
export interface WatchlistCandidate {
  architecture: string | null;
  description: string | null;
  evalue: number | null;
  family: string;
  has_retinalK: number | null;
  identifier: string;
  query_accession: string | null;
  resolved_accession: string | null;
  score: number | null;
  seq_length: number | null;
  source_db: string;
  species: string | null;
  taxonomy_id: number | null;
  mapali_window: string | null;
}

export const WATCHLIST_COLUMNS: (keyof WatchlistCandidate)[] = [
  "identifier", "family", "source_db", "query_accession", "resolved_accession", "evalue", "score", "seq_length",
  "has_retinalK", "architecture", "description", "species", "taxonomy_id", "mapali_window",
];

export function watchlistTsv(rows: WatchlistCandidate[]): string {
  const cell = (v: unknown) => (v === null || v === undefined ? "" : String(v).replace(/[\t\r\n]+/g, " "));
  return [WATCHLIST_COLUMNS.join("\t"), ...rows.map((r) => WATCHLIST_COLUMNS.map((c) => cell(r[c])).join("\t"))].join("\n") + "\n";
}
