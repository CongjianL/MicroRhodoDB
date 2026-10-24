/**
 * Legacy filter equivalence: for every combination of the legacy v1.6.0 browser controls, the PR-2
 * filter (with group=all, since the legacy page had no group tabs) selects exactly the same source
 * records as a verbatim port of site/app.js apply() run on site/data.js.
 */
import { describe, expect, it } from "vitest";
import { applyFilters, DEFAULT_STATE, type BrowseState } from "../../src/lib/browse";
import { legacy, legacyApply, legacyRows, rows, v161Changes, type LegacyFilter } from "./helpers";

const NONE: LegacyFilter = { q: "", s: "", c: "", e: "", f: "", dm: "", ft: false, fx: false, fg: true };

function toState(o: LegacyFilter): BrowseState {
  return {
    ...DEFAULT_STATE, group: "all", q: o.q, status: o.s as BrowseState["status"], clade: o.c, tent: o.ft,
    evidence: o.e as BrowseState["evidence"], func: o.f as BrowseState["func"], domain: o.dm as BrowseState["domain"],
    conflict: o.fx, eng: o.fg,
  };
}

describe("legacy oracle", () => {
  const R = legacyRows();
  const all = rows();
  const ids = (xs: readonly object[]) => xs.map((x) => String((x as { source_acc: unknown }).source_acc)).sort();
  // Only records changed by the v1.6.1 decisions may enter or leave a filter result relative to the v1.6.0 oracle.
  const changed = v161Changes();
  const check = (o: LegacyFilter) => {
    const want = ids(legacyApply(R, o)).filter((a) => !changed.has(a));
    const got = ids(applyFilters(all, toState(o))).filter((a) => !changed.has(a));
    expect(got, JSON.stringify(o)).toEqual(want);
    return want.length;
  };

  it("legacy data has the same 5,466 source records", () => {
    expect(R.length).toBe(5466);
    expect(ids(R)).toEqual(ids(all));
  });

  it("single controls match (all statuses, clades +/- tentative, evidence, functions, domains, flags)", () => {
    const D = legacy();
    const statuses = [...new Set(R.map((r) => String(r.membership_status)))];
    const funcs = [...new Set(R.map((r) => r.func_class).filter(Boolean).map(String))];
    let n = 0;
    for (const fg of [true, false]) {
      n += check({ ...NONE, fg });
      n += check({ ...NONE, fg, fx: true });
      for (const s of statuses) check({ ...NONE, fg, s });
      for (const c of D.clades.map((x) => x.clade_id)) for (const ft of [false, true]) check({ ...NONE, fg, c, ft });
      for (const e of ["E1", "E2", "E3", "E4", "E5"]) check({ ...NONE, fg, e });
      for (const f of funcs) check({ ...NONE, fg, f });
      for (const dm of ["Bacteria", "Archaea", "Eukaryota"]) check({ ...NONE, fg, dm });
    }
    expect(n).toBeGreaterThan(0);
  });

  it("legacy 'Viruses' domain option matched no records (documented deviation: option removed)", () => {
    expect(legacyApply(R, { ...NONE, dm: "Viruses" }).length).toBe(0);
  });

  it("free-text search matches over the same six fields", () => {
    for (const q of ["halobacterium", "MRDB00001", "P029", "DTE", "fungal", "xenorhodopsin", "  Sodium  ", "mr_cld3_017", "zzzz"]) {
      for (const fg of [true, false]) check({ ...NONE, q, fg });
    }
  });

  it("combined controls match", () => {
    const combos: Partial<LegacyFilter>[] = [
      { s: "typeI_member_core", e: "E3", c: "MR_CLD3_017", ft: true },
      { f: "proton_pump", dm: "Bacteria", fx: true },
      { q: "rhodopsin", e: "E1", fg: false },
      { c: "MR_CLD3_006", ft: true, f: "sensory" },
      { s: "typeI_candidate", dm: "Eukaryota", q: "a" },
    ];
    for (const c of combos) check({ ...NONE, ...c });
  });
});
