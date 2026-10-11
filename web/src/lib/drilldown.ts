/**
 * Statistics -> Browse drilldowns (PR-5a).
 *
 * A drilldown link must reproduce exactly the source records counted by the statistic it originates
 * from: the same category filter AND the same population (denominator). The population is taken from
 * the distribution's own denominator id in summary.json, never chosen ad hoc per chart, so a chart
 * computed over the 4,468 members and candidates cannot open a Browse view over all 5,466 records.
 *
 * tests/unit/drilldown.test.ts checks every generated link against the per-record definition of the
 * distribution (accession sets, not only counts); tests/test_web_pr5a.py checks the same sets against
 * the frozen SQLite database.
 */
import { href } from "../app/routes";
import { DEFAULT_STATE, filterQuery, inGroup, type BrowseState, type IndexRow } from "./browse";

/** Denominators that correspond to a Browse population. */
export const POPULATIONS = {
  /** All source records, engineered constructs included. */
  all_records: { group: "all", eng: true },
  /** Counted records: engineered constructs excluded (counts_eligible = 1). */
  counted_records: { group: "all", eng: false },
  /** Type-I members + candidates, engineered constructs included (members_candidates, n = 4,468). */
  members_candidates: { group: "member_candidate", eng: true },
} as const satisfies Record<string, Pick<BrowseState, "group" | "eng">>;
export type PopulationId = keyof typeof POPULATIONS;

export const isPopulation = (id: string): id is PopulationId => Object.prototype.hasOwnProperty.call(POPULATIONS, id);

/**
 * Browse query for a category of a statistic computed over `denominatorId`. Returns undefined (no
 * link) when the denominator has no Browse equivalent, rather than a link to a different population.
 */
export function drilldownQuery(denominatorId: string, filters: Partial<BrowseState>): string | undefined {
  if (!isPopulation(denominatorId)) return undefined;
  if ("group" in filters || "eng" in filters) {
    // A filter on the membership group narrows the population; it must be a subset of it.
    const pop = POPULATIONS[denominatorId];
    if (filters.group && pop.group !== "all" && filters.group !== pop.group) {
      if (!(pop.group === "member_candidate" && (filters.group === "member" || filters.group === "candidate"))) return undefined;
    }
    if (filters.eng !== undefined && filters.eng !== pop.eng) return undefined;
  }
  return filterQuery({ ...DEFAULT_STATE, ...POPULATIONS[denominatorId], ...filters });
}

/** Hash link for drilldownQuery, or undefined (render no link) if there is no exact Browse equivalent. */
export function drillHref(denominatorId: string, filters: Partial<BrowseState>): string | undefined {
  const q = drilldownQuery(denominatorId, filters);
  return q === undefined ? undefined : href.browse(q);
}

type Key = string | null;
const MOTIF_LINKABLE = /^[A-Z-]{1,5}$/;

/**
 * Category -> Browse filter for every drillable distribution in summary.json. Returning undefined
 * means "no exact Browse filter for this category" (no link is rendered).
 */
export const DIST_FILTER: Record<string, (key: Key) => Partial<BrowseState> | undefined> = {
  membership_status: (k) => (k ? { status: k as BrowseState["status"] } : undefined),
  membership_status_counted: (k) => (k ? { status: k as BrowseState["status"] } : undefined),
  membership_group: (k) => (k ? { group: k as BrowseState["group"] } : undefined),
  evidence_level_counted: (k) => (k ? { evidence: k as BrowseState["evidence"] } : undefined),
  evidence_level_all: (k) => (k ? { evidence: k as BrowseState["evidence"] } : undefined),
  func_class_counted: (k) => (k ? { func: k as BrowseState["func"] } : undefined),
  tax_domain_counted: (k) => ({ domain: (k ?? "none") as BrowseState["domain"] }),
  ncbi_phylum_counted: (k) => (k ? { lin: `${k} (phylum)` } : undefined),
  clade_state: (k) => (k ? { state: k as BrowseState["state"] } : undefined),
  clade_state_members_candidates: (k) => (k ? { state: k as BrowseState["state"] } : undefined),
  helixC_motif_counted: (k) => (k && MOTIF_LINKABLE.test(k) ? { motif: k } : undefined),
};

/** Crosstab (row field, column field) -> Browse filter. */
export const CROSSTAB_FILTER: Record<string, (row: Key, col: Key) => Partial<BrowseState> | undefined> = {
  evidence_by_membership_group_counted: (row, col) =>
    row && col ? { group: row as BrowseState["group"], evidence: col as BrowseState["evidence"] } : undefined,
};

interface DistLike { id: string; denominator: { id: string } }

/** Browse query for one category of a distribution, or undefined if there is no exact equivalent. */
export function distItemQuery(d: DistLike, key: Key): string | undefined {
  const f = DIST_FILTER[d.id]?.(key);
  return f ? drilldownQuery(d.denominator.id, f) : undefined;
}
export function crosstabCellQuery(x: DistLike, row: Key, col: Key): string | undefined {
  const f = CROSSTAB_FILTER[x.id]?.(row, col);
  return f ? drilldownQuery(x.denominator.id, f) : undefined;
}
export const distItemHref = (d: DistLike, key: Key) => { const q = distItemQuery(d, key); return q === undefined ? undefined : href.browse(q); };
export const crosstabCellHref = (x: DistLike, row: Key, col: Key) => { const q = crosstabCellQuery(x, row, col); return q === undefined ? undefined : href.browse(q); };

/**
 * Independent per-record definition of each population (used by tests and by the runtime
 * self-check). Counted records are defined by counts_eligible, not by the Browse engineered flag,
 * so the two definitions check each other.
 */
export function inPopulation(id: PopulationId, r: IndexRow): boolean {
  switch (id) {
    case "all_records": return true;
    case "counted_records": return r.counts_eligible === true;
    case "members_candidates": return inGroup("member_candidate", r.membership_group);
  }
}
