/**
 * Browse model: typed index rows, URL-encoded filter state, filtering and sorting.
 *
 * Filter semantics of the legacy v1.6.0 browser (site/app.js apply()) are preserved exactly for the
 * fields it offered (q, status, clade + include-tentative, evidence, func, domain, conflict-only,
 * include-engineered); tests/unit/browse.legacy.test.ts checks this against the legacy data oracle.
 * New filters (spec section 5.2) are pure AND-conjunctions on exported index columns.
 */
import type {
  CladeState, EvidenceLevel, FuncClass, MembershipGroup, MembershipStatus, RecordsIndex,
} from "../data/types";
import { EVIDENCE_LEVELS, FUNC_ORDER, STATUS_GROUP, STATUS_ORDER } from "./format";

type Cols = RecordsIndex["columns"];
type Row = RecordsIndex["rows"][number];
export type IndexRow = { [K in keyof Cols & `${number}` as Cols[K] & string]: Row[K] } & { _i: number };

/** Convert the column-oriented records-index.json into row objects (index order preserved). */
export function toRows(ri: RecordsIndex): IndexRow[] {
  const cols = ri.columns as readonly string[];
  return ri.rows.map((r, i) => {
    const o: Record<string, unknown> = { _i: i };
    for (let j = 0; j < cols.length; j++) o[cols[j]] = r[j];
    return o as unknown as IndexRow;
  });
}

export type GroupFilter = MembershipGroup | "all";
export const GROUPS: GroupFilter[] = ["member", "candidate", "boundary", "outgroup", "rejected", "all"];
export const DOMAINS = ["Archaea", "Bacteria", "Eukaryota", "none"] as const;
export type DomainFilter = (typeof DOMAINS)[number] | "";
export const PAGE_SIZES = [25, 50, 100, 250] as const;
export const CLADE_STATES: CladeState[] = [
  "confident", "tentative", "reference_tip_unclustered", "outgroup_reference_tip", "outgroup_placed", "unassigned", "distant",
];

export const SORT_KEYS = [
  "mrdb_acc", "source_acc", "protein_name", "organism", "tax_domain", "length", "membership_status",
  "membership_score", "func_class", "evidence_level", "clade", "n_pdb", "has_afdb", "helixC_motif",
  "retinal_site_residue", "n_support_links",
] as const;
export type SortKey = (typeof SORT_KEYS)[number];

export interface BrowseState {
  group: GroupFilter;
  status: MembershipStatus | "";
  q: string;
  func: FuncClass | "";
  evidence: EvidenceLevel | "";
  clade: string;
  tent: boolean;
  sub: string;
  state: CladeState | "";
  domain: DomainFilter;
  motif: string;
  residue: string;
  pdb: boolean;
  pdbid: string;
  afdb: "" | "1" | "0";
  conflict: boolean;
  curated: boolean;
  eng: boolean;
  pub: boolean;
  lin: string;
  lmin: number | null;
  lmax: number | null;
  sort: SortKey | "";
  dir: "asc" | "desc";
  page: number;
  size: number;
}

export const DEFAULT_STATE: BrowseState = {
  group: "member", status: "", q: "", func: "", evidence: "", clade: "", tent: false, sub: "", state: "",
  domain: "", motif: "", residue: "", pdb: false, pdbid: "", afdb: "", conflict: false, curated: false,
  eng: false, pub: false, lin: "", lmin: null, lmax: null, sort: "", dir: "asc", page: 1, size: 50,
};

/** Canonical URL parameter order (also used for the export filter hash). */
const KEYS: (keyof BrowseState)[] = [
  "group", "status", "q", "func", "evidence", "clade", "tent", "sub", "state", "domain", "motif", "residue",
  "pdb", "pdbid", "afdb", "conflict", "curated", "eng", "pub", "lin", "lmin", "lmax", "sort", "dir", "page", "size",
];
export const FILTER_KEYS = KEYS.filter((k) => !["sort", "dir", "page", "size"].includes(k));

export interface ParseResult {
  state: BrowseState;
  /** URL parameters that were present but invalid (reported to the user, never silently applied). */
  ignored: { key: string; value: string }[];
}

export function parseBrowse(params: URLSearchParams): ParseResult {
  const s: BrowseState = { ...DEFAULT_STATE };
  const ignored: ParseResult["ignored"] = [];
  const bad = (key: string, value: string) => ignored.push({ key, value });
  const flag = (k: keyof BrowseState, v: string) => {
    if (v === "1" || v === "true") (s as unknown as Record<string, unknown>)[k] = true;
    else if (v === "0" || v === "false") (s as unknown as Record<string, unknown>)[k] = false;
    else bad(k, v);
  };
  const intOrNull = (k: "lmin" | "lmax", v: string) => {
    if (/^\d{1,5}$/.test(v)) s[k] = Number(v);
    else bad(k, v);
  };
  for (const [k, raw] of params) {
    const v = raw.trim();
    if (v === "") continue;
    switch (k) {
      case "group": GROUPS.includes(v as GroupFilter) ? (s.group = v as GroupFilter) : bad(k, v); break;
      case "status":
        // Exact database status code, or a membership-group name (spec 2.2 example "status=member"),
        // which is canonicalised to group=<name>.
        if (STATUS_ORDER.includes(v as MembershipStatus)) s.status = v as MembershipStatus;
        else if (v !== "all" && GROUPS.includes(v as GroupFilter)) s.group = v as GroupFilter;
        else bad(k, v);
        break;
      case "q": s.q = raw.slice(0, 200); break;
      case "func": FUNC_ORDER.includes(v as FuncClass) ? (s.func = v as FuncClass) : bad(k, v); break;
      case "evidence": EVIDENCE_LEVELS.includes(v as EvidenceLevel) ? (s.evidence = v as EvidenceLevel) : bad(k, v); break;
      case "clade": /^MR_CLD3_(\d{3}|B\d{2})$/.test(v) ? (s.clade = v) : bad(k, v); break;
      case "sub": /^MR_CLD3_(\d{3}|B\d{2})\.\d{2}$/.test(v) ? (s.sub = v) : bad(k, v); break;
      case "state": CLADE_STATES.includes(v as CladeState) ? (s.state = v as CladeState) : bad(k, v); break;
      case "domain": (DOMAINS as readonly string[]).includes(v) ? (s.domain = v as DomainFilter) : bad(k, v); break;
      case "motif": /^[A-Z\-]{1,5}$/i.test(v) ? (s.motif = v.toUpperCase()) : bad(k, v); break;
      case "residue": /^([A-Z\-]|none)$/.test(v) ? (s.residue = v) : bad(k, v); break;
      case "pdbid": /^[0-9][A-Z0-9]{3}$/i.test(v) ? (s.pdbid = v.toUpperCase()) : bad(k, v); break;
      case "afdb": v === "1" || v === "0" ? (s.afdb = v) : bad(k, v); break;
      case "tent": case "pdb": case "conflict": case "curated": case "eng": case "pub": flag(k, v); break;
      case "lin": s.lin = raw.slice(0, 200); break;
      case "lmin": case "lmax": intOrNull(k, v); break;
      case "sort": (SORT_KEYS as readonly string[]).includes(v) ? (s.sort = v as SortKey) : bad(k, v); break;
      case "dir": v === "asc" || v === "desc" ? (s.dir = v) : bad(k, v); break;
      case "page": /^\d{1,6}$/.test(v) && Number(v) >= 1 ? (s.page = Number(v)) : bad(k, v); break;
      case "size": (PAGE_SIZES as readonly number[]).includes(Number(v)) ? (s.size = Number(v)) : bad(k, v); break;
      default: bad(k, v);
    }
  }
  return { state: s, ignored };
}

/** Canonical query string: fixed key order, defaults omitted. */
export function serializeBrowse(s: BrowseState, keys: (keyof BrowseState)[] = KEYS): string {
  const p = new URLSearchParams();
  for (const k of keys) {
    const v = s[k];
    if (v === DEFAULT_STATE[k]) continue;
    if (typeof v === "boolean") p.set(k, v ? "1" : "0");
    else if (v !== null && v !== "") p.set(k, String(v));
  }
  return p.toString();
}

/** Query string of the filters only (no sort/paging): defines the selection for exports. */
export const filterQuery = (s: BrowseState) => serializeBrowse(s, FILTER_KEYS);

export function applyFilters(rows: IndexRow[], s: BrowseState): IndexRow[] {
  const q = s.q.toLowerCase().trim();
  const lin = s.lin.toLowerCase().trim();
  return rows.filter((r) =>
    // ---- legacy semantics (site/app.js apply()) ----
    (!s.status || r.membership_status === s.status) &&
    (!s.clade || r.clade_id === s.clade || (s.tent && r.clade_state === "tentative" && r.tentative_clade_id === s.clade)) &&
    (!s.evidence || r.evidence_level === s.evidence) &&
    (!s.func || r.func_class === s.func) &&
    (!s.domain || (s.domain === "none" ? r.tax_domain === null : r.tax_domain === s.domain)) &&
    (!s.conflict || r.call_conflict === true) &&
    (s.eng || r.is_engineered !== true) &&
    (!q || [r.mrdb_acc, r.source_acc, r.organism, r.protein_name, r.helixC_motif, r.clade_name]
      .some((v) => v !== null && v !== undefined && String(v).toLowerCase().includes(q))) &&
    // ---- PR-2 additions (spec section 5.2) ----
    (s.group === "all" || r.membership_group === s.group) &&
    (!s.sub || r.subclade_id === s.sub) &&
    (!s.state || r.clade_state === s.state) &&
    (!s.motif || r.helixC_motif === s.motif) &&
    (!s.residue || (s.residue === "none" ? r.retinal_site_residue === null : r.retinal_site_residue === s.residue)) &&
    (!s.pdb || r.n_pdb > 0) &&
    (!s.pdbid || r.pdb_ids.includes(s.pdbid)) &&
    (!s.afdb || r.has_afdb === (s.afdb === "1")) &&
    (!s.curated || r.membership_status === "typeI_member_curated") &&
    (!s.pub || r.n_support_links > 0) &&
    (!lin || (r.lineage !== null && r.lineage.toLowerCase().includes(lin))) &&
    (s.lmin === null || r.length >= s.lmin) &&
    (s.lmax === null || r.length <= s.lmax),
  );
}

const STATUS_RANK = new Map(STATUS_ORDER.map((x, i) => [x, i]));
const FUNC_RANK = new Map(FUNC_ORDER.map((x, i) => [x, i]));

function sortValue(r: IndexRow, k: SortKey): string | number | null {
  switch (k) {
    case "membership_status": return STATUS_RANK.get(r.membership_status) ?? null;
    case "func_class": return FUNC_RANK.get(r.func_class) ?? null;
    case "clade": return r.clade_id ?? (r.clade_state === "tentative" ? `~${r.tentative_clade_id}` : null);
    case "has_afdb": return r.has_afdb ? 1 : 0;
    default: {
      const v = (r as unknown as Record<string, unknown>)[k];
      return v === undefined ? null : (v as string | number | null);
    }
  }
}

/** Stable sort; numbers numerically, strings by code point; missing values always last. */
export function sortRows(rows: IndexRow[], key: SortKey | "", dir: "asc" | "desc"): IndexRow[] {
  if (!key) return rows;
  const m = dir === "desc" ? -1 : 1;
  return rows
    .map((r) => [sortValue(r, key), r] as const)
    .sort(([a, ra], [b, rb]) => {
      if (a === null && b === null) return ra._i - rb._i;
      if (a === null) return 1;
      if (b === null) return -1;
      const c = typeof a === "number" && typeof b === "number" ? a - b : a < b ? -1 : a > b ? 1 : 0;
      return c !== 0 ? c * m : ra._i - rb._i;
    })
    .map(([, r]) => r);
}

export function statusesForGroup(g: GroupFilter): MembershipStatus[] {
  return g === "all" ? STATUS_ORDER : STATUS_ORDER.filter((s) => STATUS_GROUP[s] === g);
}

/** Filters differing from the defaults, excluding the population controls (group tabs, engineered toggle). */
export function activeFilterKeys(s: BrowseState): (keyof BrowseState)[] {
  return FILTER_KEYS.filter((k) => s[k] !== DEFAULT_STATE[k] && k !== "group" && k !== "eng");
}
