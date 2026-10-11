/**
 * Pure helpers for the PR-5 Statistics and Evidence pages. Nothing here creates a scientific value:
 * every number is read from summary.json (exporter-owned, with SQL provenance) or counted from the
 * exported records index for the runtime reconciliation check.
 */
import type { Summary } from "../data/types";
import type { IndexRow } from "./browse";

export type Dist = Summary["distributions"][number];
export type Crosstab = Summary["crosstabs"][number];
export type DistItem = Dist["items"][number];

export const NULL_KEY = "__null__";
export const OTHER_KEY = "__other__";

/**
 * Keep the `n` largest categories and aggregate the remainder into a single "Other" bucket, so that
 * the displayed total still equals the distribution total (and its denominator). Missing values (key
 * null) are always kept as their own bucket, never folded into "Other".
 */
export function topN(items: readonly DistItem[], n: number): { items: { key: string; rawKey: string | null; value: number; nOther?: number }[]; total: number } {
  const nonNull = items.filter((i) => i.key !== null).slice().sort((a, b) => b.value - a.value || String(a.key).localeCompare(String(b.key)));
  const nul = items.find((i) => i.key === null);
  const head = nonNull.slice(0, n);
  const rest = nonNull.slice(n);
  const out: { key: string; rawKey: string | null; value: number; nOther?: number }[] = head.map((i) => ({ key: i.key as string, rawKey: i.key, value: i.value }));
  if (rest.length) out.push({ key: OTHER_KEY, rawKey: null, value: rest.reduce((a, b) => a + b.value, 0), nOther: rest.length });
  if (nul) out.push({ key: NULL_KEY, rawKey: null, value: nul.value });
  return { items: out, total: out.reduce((a, b) => a + b.value, 0) };
}

/** Items in a fixed order (unknown keys appended in exported order; nothing dropped). */
export function ordered(items: readonly DistItem[], order: readonly (string | null)[]): DistItem[] {
  const rank = new Map(order.map((k, i) => [k, i]));
  return items
    .map((it, i) => ({ it, r: rank.has(it.key) ? (rank.get(it.key) as number) : order.length + i }))
    .sort((a, b) => a.r - b.r)
    .map((x) => x.it);
}

/** Length bins in numeric order ("<200", "200-224", ..., ">=N"). */
export function lengthBinOrder(key: string | null): number {
  if (key === null) return Number.MAX_SAFE_INTEGER;
  if (key.startsWith("<")) return -1;
  const m = /^(?:>=|≥)?(\d+)/.exec(key);
  return m ? Number(m[1]) : Number.MAX_SAFE_INTEGER - 1;
}

export interface Matrix {
  rows: (string | null)[];
  cols: (string | null)[];
  value: (r: string | null, c: string | null) => number;
  rowTotal: (r: string | null) => number;
  colTotal: (c: string | null) => number;
  total: number;
}

/** Turn crosstab cells into a lookup matrix with margins. Rows/cols follow the given orders, then any extras. */
export function matrix(x: Crosstab, rowOrder: readonly (string | null)[] = [], colOrder: readonly (string | null)[] = []): Matrix {
  const m = new Map<string, number>();
  const k = (r: string | null, c: string | null) => `${r ?? NULL_KEY}\u0000${c ?? NULL_KEY}`;
  const rs: (string | null)[] = [...rowOrder];
  const cs: (string | null)[] = [...colOrder];
  for (const cell of x.cells) {
    m.set(k(cell.row, cell.col), (m.get(k(cell.row, cell.col)) ?? 0) + cell.value);
    if (!rs.includes(cell.row)) rs.push(cell.row);
    if (!cs.includes(cell.col)) cs.push(cell.col);
  }
  const rows = rs.filter((r) => x.cells.some((c) => c.row === r));
  const cols = cs.filter((cc) => x.cells.some((c) => c.col === cc));
  const value = (r: string | null, c: string | null) => m.get(k(r, c)) ?? 0;
  return {
    rows,
    cols,
    value,
    rowTotal: (r) => cols.reduce((a, c) => a + value(r, c), 0),
    colTotal: (c) => rows.reduce((a, r) => a + value(r, c), 0),
    total: x.cells.reduce((a, c) => a + c.value, 0),
  };
}

/* ------------------------------------------------------------------ runtime reconciliation */

type Scope = "all" | "counted" | "members_candidates";

/** Function-call basis category: the same CASE mapping as the exporter (BASIS_CATEGORY_SQL). */
export function basisCategory(b: string | null): string {
  if (b === null) return "UNMAPPED";
  const lb = b.toLowerCase();
  if (lb === "experimental:this_protein") return "experimental:this_protein";
  if (lb.startsWith("experimental_ortholog:")) return "experimental_ortholog";
  if (lb.startsWith("motif+phylogeny:")) return "motif+phylogeny";
  if (lb.startsWith("legacy_v14_concordant_motif:")) return "legacy_v14_concordant_motif";
  if (lb.startsWith("legacy_v14_motif_untestable:")) return "legacy_v14_motif_untestable";
  if (lb.startsWith("curated_rule:")) return "curated_rule";
  if (lb.startsWith("audit_rule_")) return "audit_rule";
  if (lb.startsWith("family_hmm_")) return "family_hmm_conflict";
  if (lb.startsWith("conflict:")) return "conflict";
  if (lb === "insufficient") return "insufficient";
  return "UNMAPPED";
}

export const BASIS_LABEL: Record<string, string> = {
  "experimental:this_protein": "Experimental: this protein",
  experimental_ortholog: "Transferred from an experimentally characterised ortholog",
  "motif+phylogeny": "Helix-C motif + clade context",
  legacy_v14_concordant_motif: "Legacy v1.4 call, concordant motif",
  legacy_v14_motif_untestable: "Legacy v1.4 call, motif untestable",
  curated_rule: "Curated rule",
  audit_rule: "Audit rule",
  family_hmm_conflict: "Family-HMM conflict",
  conflict: "Function-call conflict (call withdrawn)",
  insufficient: "Insufficient evidence",
};
export const basisLabel = (k: string | null) => (k === null ? "Missing" : BASIS_LABEL[k] ?? k);
export const BASIS_ORDER = Object.keys(BASIS_LABEL);

/** Distributions that can be recounted from columns of records-index.json, with their record scope. */
export const RECOUNTABLE: { id: string; scope: Scope; get: (r: IndexRow) => string | null }[] = [
  { id: "membership_status", scope: "all", get: (r) => r.membership_status },
  { id: "membership_group", scope: "all", get: (r) => r.membership_group },
  { id: "membership_status_counted", scope: "counted", get: (r) => r.membership_status },
  { id: "evidence_level_counted", scope: "counted", get: (r) => r.evidence_level },
  { id: "evidence_level_all", scope: "all", get: (r) => r.evidence_level },
  { id: "func_class_counted", scope: "counted", get: (r) => r.func_class },
  { id: "tax_domain_counted", scope: "counted", get: (r) => r.tax_domain },
  { id: "clade_state", scope: "all", get: (r) => r.clade_state },
  { id: "clade_state_members_candidates", scope: "members_candidates", get: (r) => r.clade_state },
  { id: "motif_class_counted", scope: "counted", get: (r) => r.motif_class },
  { id: "helixC_motif_counted", scope: "counted", get: (r) => r.helixC_motif },
  { id: "function_basis_category_counted", scope: "counted", get: (r) => basisCategory(r.function_basis) },
];

export function countBy<T>(rows: readonly T[], f: (r: T) => string | null): Map<string | null, number> {
  const m = new Map<string | null, number>();
  for (const r of rows) {
    const k = f(r);
    m.set(k, (m.get(k) ?? 0) + 1);
  }
  return m;
}

export interface ReconRow {
  id: string;
  label: string;
  denominator: number;
  recounted: number;
  mismatches: { key: string | null; summary: number; index: number }[];
  /** Keys that occur more than once in summary.json (always an error). */
  duplicates: (string | null)[];
  ok: boolean;
}

/** Recount each RECOUNTABLE distribution from the index rows and compare every category with summary.json. */
export function reconcile(summary: Summary, rows: readonly IndexRow[]): ReconRow[] {
  const scoped: Record<Scope, readonly IndexRow[]> = {
    all: rows,
    counted: rows.filter((r) => r.counts_eligible),
    members_candidates: rows.filter((r) => r.membership_group === "member" || r.membership_group === "candidate"),
  };
  return RECOUNTABLE.map((spec) => {
    const d = summary.distributions.find((x) => x.id === spec.id);
    const src = scoped[spec.scope];
    if (!d) return { id: spec.id, label: `${spec.id} (missing from summary.json)`, denominator: 0, recounted: src.length, mismatches: [], duplicates: [], ok: false };
    const got = countBy(src, spec.get);
    // Keyed comparison: a key present on only one side is a mismatch (even with value 0), and a key that
    // occurs twice in summary.json is an error rather than being silently merged or shadowed.
    const exp = new Map<string | null, number>();
    const duplicates: (string | null)[] = [];
    for (const i of d.items) {
      if (exp.has(i.key)) duplicates.push(i.key);
      exp.set(i.key, i.value);
    }
    const keys = new Set<string | null>([...exp.keys(), ...got.keys()]);
    const mismatches: ReconRow["mismatches"] = [];
    for (const key of keys) {
      const a = exp.get(key);
      const b = got.get(key);
      if (a === undefined || b === undefined || a !== b) mismatches.push({ key, summary: a ?? 0, index: b ?? 0 });
    }
    return {
      id: d.id, label: d.label, denominator: d.denominator.value, recounted: src.length, mismatches, duplicates,
      ok: mismatches.length === 0 && duplicates.length === 0 && src.length === d.denominator.value && d.total === d.denominator.value,
    };
  });
}

/* ------------------------------------------------------------------ function-call conflicts */

export interface ConflictDetail {
  original: string | null;
  motif: string | null;
  action: string | null;
  raw: string;
}

/** Parse call_conflict_detail ("v14=X; motif=Y; action=Z"); unknown parts are kept in `raw`. */
export function parseConflictDetail(s: string | null): ConflictDetail | null {
  if (!s) return null;
  const out: ConflictDetail = { original: null, motif: null, action: null, raw: s };
  for (const part of s.split(";")) {
    const m = /^\s*([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$/.exec(part);
    if (!m) continue;
    if (m[1] === "v14") out.original = m[2] || null;
    else if (m[1] === "motif") out.motif = m[2] || null;
    else if (m[1] === "action") out.action = m[2] || null;
  }
  return out;
}

export const ACTION_LABEL: Record<string, string> = {
  downgraded_to_E5: "Call withdrawn: downgraded to E5 (unassigned)",
  flag_only_E1: "Flag only: E1 call kept",
  flag_only_E2: "Flag only: E2 call kept",
  flag_only_E4_curated_rule: "Flag only: E4 curated-rule call kept",
};
export const actionLabel = (a: string | null) => (a === null ? "Not recorded" : ACTION_LABEL[a] ?? a);
