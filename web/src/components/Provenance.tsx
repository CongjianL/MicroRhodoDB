/** "How this is counted" disclosure: SQL, denominator definition and inclusion policy, all from summary.json. */
import type { Summary } from "../data/types";
import { fmtInt } from "../lib/format";

export function Provenance({ summary, sql, denominatorId, sourceFile, derivation, inclusion, testId }: {
  summary: Summary;
  sql: string | null;
  denominatorId: string | null;
  sourceFile?: string | null;
  derivation?: string | null;
  inclusion?: string;
  testId?: string;
}) {
  const den = denominatorId ? summary.denominators[denominatorId] : undefined;
  return (
    <details className="text-sm" data-testid={testId}>
      <summary className="cursor-pointer text-accent">How this is counted</summary>
      <dl className="mt-2 grid gap-x-3 gap-y-1.5 sm:grid-cols-[9rem_minmax(0,1fr)]">
        <dt className="text-ink-2">Release</dt>
        <dd>v{summary.dataset_release}</dd>
        {den ? (
          <>
            <dt className="text-ink-2">Denominator</dt>
            <dd>
              {den.label} (n = <span className="tabular">{fmtInt(den.value)}</span>)
              <code className="mt-0.5 block whitespace-pre-wrap break-words text-xs text-ink-2">{den.sql}</code>
            </dd>
          </>
        ) : (
          <>
            <dt className="text-ink-2">Denominator</dt>
            <dd>None (absolute count; not a fraction of the corpus)</dd>
          </>
        )}
        {inclusion ? (<><dt className="text-ink-2">Inclusion</dt><dd>{inclusion}</dd></>) : null}
        {sql ? (
          <>
            <dt className="text-ink-2">Query</dt>
            <dd><code className="block whitespace-pre-wrap break-words text-xs">{sql}</code></dd>
          </>
        ) : null}
        {sourceFile ? (<><dt className="text-ink-2">Source file</dt><dd><code className="text-xs">{sourceFile}</code></dd></>) : null}
        {derivation ? (<><dt className="text-ink-2">Derivation</dt><dd>{derivation}</dd></>) : null}
      </dl>
    </details>
  );
}

/** Inclusion-policy sentence for a denominator id. */
export function inclusionText(denominatorId: string | null): string {
  switch (denominatorId) {
    case "all_records": return "All source records in the corpus: engineered constructs included; watchlist excluded.";
    case "counted_records": return "Counted records only (counts_eligible = 1): engineered constructs excluded; watchlist excluded.";
    case "members_candidates": return "Type-I members and candidates (all member and candidate statuses), engineered constructs included; watchlist excluded.";
    case "mrdb_accessions": return "Unique sequences (MRDB accessions); watchlist excluded.";
    case "watchlist": return "Watchlist rows only; these are not corpus records and are never added to corpus totals.";
    case "pdb_entries": return "Distinct PDB entries linked to any source record.";
    case "pdb_links": return "Record-PDB link rows (one record may link many entries, one entry many records).";
    case "active_links": return "Active record-publication links.";
    case "tree_tips": return "Tips of the MR_RT_003 reference tree.";
    case "placements_current": return "Current EPA-ng placements on MR_RT_003.";
    case "clade_level1_rows": return "Level-1 clades plus the two backbone groups.";
    default: return "";
  }
}
