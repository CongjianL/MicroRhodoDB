/** Shared fixtures for unit tests: the exported PR-1 data (web/public/data) and the legacy v1.6.0 oracle (site/data.js). */
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import vm from "node:vm";
import type { Clades, Manifest, RecordsIndex, Summary, Tips } from "../../src/data/types";
import { toRows, type IndexRow } from "../../src/lib/browse";

export const WEB = resolve(__dirname, "../..");
export const REPO = resolve(WEB, "..");
const DATA = resolve(WEB, "public/data/v1.6.0");

if (!existsSync(DATA)) {
  throw new Error("web/public/data/v1.6.0 missing: run `python tools/export_web_data.py --repo . --out web/public/data` first");
}

const cache = new Map<string, unknown>();
function memo<T>(k: string, f: () => T): T {
  if (!cache.has(k)) cache.set(k, f());
  return cache.get(k) as T;
}

export const readData = (rel: string) => readFileSync(resolve(DATA, rel), "utf8");
export const json = <T>(rel: string): T => memo(rel, () => JSON.parse(readData(rel)) as T);

export const manifest = () => json<Manifest>("manifest.json");
export const summary = () => json<Summary>("summary.json");
export const clades = () => json<Clades>("clades.json");
export const tips = () => json<Tips>("phylogeny/tips.json");
export const newick = () => memo("nwk", () => readData("phylogeny/MR_RT_003.rooted.treefile"));
export const rows = (): IndexRow[] => memo("rows", () => toRows(json<RecordsIndex>("records-index.json")));

export interface Legacy {
  meta: Record<string, string>;
  columns: string[];
  rows: unknown[][];
  seqs: string[];
  clades: { clade_id: string }[];
}
export type LegacyRow = Record<string, unknown> & { _i: number };

/** Legacy v1.6.0 site data, evaluated exactly as the legacy browser did (window.MRDB). */
export const legacy = (): Legacy => memo("legacy", () => {
  const ctx = { window: {} as { MRDB?: Legacy } };
  vm.runInNewContext(readFileSync(resolve(REPO, "site/data.js"), "utf8"), ctx);
  return ctx.window.MRDB!;
});

/** Legacy row objects incl. clade_display, as built by site/app.js. */
export const legacyRows = (): LegacyRow[] => memo("legacyRows", () => {
  const D = legacy();
  return D.rows.map((r, i) => {
    const o: LegacyRow = { _i: i };
    D.columns.forEach((c, j) => (o[c] = r[j]));
    o.clade_display = o.clade_confidence === "confident" ? o.clade_id
      : o.clade_confidence === "tentative" ? "TENTATIVE:" + o.tentative_clade_id : "";
    return o;
  });
});

/** Verbatim port of the legacy filter (site/app.js apply(), lines 45-50). */
export interface LegacyFilter { q: string; s: string; c: string; e: string; f: string; dm: string; ft: boolean; fx: boolean; fg: boolean }
export function legacyApply(R: LegacyRow[], o: LegacyFilter): LegacyRow[] {
  const q = o.q.toLowerCase().trim();
  return R.filter((r) => (!o.s || r.membership_status === o.s) &&
    (!o.c || r.clade_id === o.c || (o.ft && r.clade_confidence === "tentative" && r.tentative_clade_id === o.c)) &&
    (!o.e || r.evidence_level === o.e) && (!o.f || r.func_class === o.f) && (!o.dm || r.tax_domain === o.dm) &&
    (!o.fx || r.call_conflict === 1) && (o.fg || r.is_engineered !== 1) &&
    (!q || [r.mrdb_acc, r.source_acc, r.organism, r.protein_name, r.helixC_motif, r.clade_name]
      .some((v) => v && String(v).toLowerCase().includes(q))));
}
