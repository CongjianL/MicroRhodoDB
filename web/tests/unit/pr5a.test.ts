/**
 * PR-5a regression tests. Each of the four defects found in the PR-5 review has an executable test here
 * (plus tests/test_web_pr5a.py on the Python side), and each test is shown to reject a deliberately
 * corrupted input (mutation tests), so a test that cannot fail does not count as evidence.
 *
 *  D1  Statistics -> Browse drilldowns: filters, engineered-record inclusion and denominator.
 *  D2  Search -> Browse: structured clade / PDB / motif semantics; "same records" only for equal sets.
 *  D3  Reconciliation: keyed comparison incl. null categories and duplicate keys.
 *  D4  Clade-state drilldowns keep the 4,468 members + candidates population.
 *
 * Accession sets are compared, not only counts: every drilldown is checked against (a) its per-record
 * definition and (b) the DB-derived golden (tests/data/web_drilldown_golden_v160.json, n + SHA-256 of
 * the sorted source accessions, generated from the frozen SQLite by web/scripts/pr5a_drilldown_golden.py).
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { Summary } from "../../src/data/types";
import { browseOptions, textSearch } from "../../src/features/search/textSearch";
import { applyFilters, GROUPS, inGroup, parseBrowse, statusesForGroup, type IndexRow } from "../../src/lib/browse";
import {
  CROSSTAB_FILTER, DIST_FILTER, POPULATIONS, crosstabCellQuery, distItemQuery, drilldownQuery, inPopulation, type PopulationId,
} from "../../src/lib/drilldown";
import { reconcile } from "../../src/lib/stats";
import { REPO, rows, summary } from "./helpers";

interface GoldenItem { kind: string; id: string; key: string | null | [string, string]; population: PopulationId; n: number; sha256: string }
const golden = JSON.parse(readFileSync(resolve(REPO, "tests/data/web_drilldown_golden_v160.json"), "utf8")) as { db_sha256: string; items: GoldenItem[] };

const R = () => rows();
const browse = (query: string): IndexRow[] => {
  const { state, ignored } = parseBrowse(new URLSearchParams(query));
  expect(ignored, query).toEqual([]);
  return applyFilters(R(), state);
};
const accs = (rs: readonly IndexRow[]) => rs.map((r) => r.source_acc).sort();
const digest = (rs: readonly IndexRow[]) => {
  const a = accs(rs);
  return { n: a.length, sha256: createHash("sha256").update(a.join("\n")).digest("hex") };
};
const sameSet = (a: readonly IndexRow[], b: readonly IndexRow[]) => {
  const x = accs(a), y = accs(b);
  return x.length === y.length && x.every((v, i) => v === y[i]);
};
const PHYLUM = /(?:^|, )([^,]+?) \(phylum\)/;

/** Per-record category of each distribution: written independently of the Browse filter code. */
const CATEGORY: Record<string, (r: IndexRow) => string | null> = {
  membership_status: (r) => r.membership_status,
  membership_status_counted: (r) => r.membership_status,
  membership_group: (r) => r.membership_group,
  evidence_level_counted: (r) => r.evidence_level,
  evidence_level_all: (r) => r.evidence_level,
  func_class_counted: (r) => r.func_class,
  tax_domain_counted: (r) => r.tax_domain,
  ncbi_phylum_counted: (r) => PHYLUM.exec(r.lineage ?? "")?.[1] ?? null,
  clade_state: (r) => r.clade_state,
  clade_state_members_candidates: (r) => r.clade_state,
  helixC_motif_counted: (r) => r.helixC_motif,
};
const definitionSet = (distId: string, pop: PopulationId, key: string | null) =>
  R().filter((r) => inPopulation(pop, r) && CATEGORY[distId](r) === key);

const dist = (id: string) => summary().distributions.find((d) => d.id === id)!;

/* ------------------------------------------------------------------ D1 + D4: drilldowns */

describe("D1/D4 Statistics and Home drilldowns return exactly the counted source records", () => {
  it("the DB-derived golden is for the frozen database", () => {
    expect(golden.db_sha256).toBe("379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f");
    expect(golden.items.length).toBeGreaterThan(400);
  });

  it("population definitions match the frozen denominators (5,466 / 5,460 / 4,468)", () => {
    const n = (p: PopulationId) => R().filter((r) => inPopulation(p, r)).length;
    expect(n("all_records")).toBe(5466);
    expect(n("counted_records")).toBe(5460);
    expect(n("members_candidates")).toBe(4468);
    for (const p of Object.keys(POPULATIONS) as PopulationId[]) {
      expect(sameSet(browse(drilldownQuery(p, {})!), R().filter((r) => inPopulation(p, r))), p).toBe(true);
      expect(summary().denominators[p].value, p).toBe(R().filter((r) => inPopulation(p, r)).length);
    }
  });

  it("every drillable distribution category: Browse set = definition set, |set| = exported value", () => {
    let checked = 0;
    for (const id of Object.keys(DIST_FILTER)) {
      const d = dist(id);
      expect(d, id).toBeTruthy();
      const pop = d.denominator.id as PopulationId;
      expect(Object.keys(POPULATIONS)).toContain(pop);
      for (const it of d.items) {
        const q = distItemQuery(d, it.key);
        if (q === undefined) continue;
        const got = browse(q);
        const def = definitionSet(id, pop, it.key);
        expect(sameSet(got, def), `${id} ${it.key} -> ${q}`).toBe(true);
        expect(got.length, `${id} ${it.key}`).toBe(it.value);
        checked++;
      }
    }
    expect(checked).toBe(golden.items.filter((g) => g.kind === "distribution").length);
  });

  it("every drilldown reproduces the DB-derived accession set (n + SHA-256)", () => {
    for (const g of golden.items) {
      let q: string | undefined;
      if (g.kind === "distribution") q = distItemQuery(dist(g.id), g.key as string | null);
      else if (g.kind === "crosstab") {
        const x = summary().crosstabs.find((c) => c.id === g.id)!;
        q = crosstabCellQuery(x, (g.key as string[])[0], (g.key as string[])[1]);
      } else if (g.kind === "metric") {
        const m = summary().metrics.find((x) => x.id === g.id)!;
        const f = g.id === "typeI_members" ? { group: "member" as const } : g.id === "e1_counted" ? { evidence: "E1" as const } : {};
        q = drilldownQuery(m.denominator!.id, f);
        expect(m.value, g.id).toBe(g.n);
      } else continue;
      expect(q, `${g.kind} ${g.id} ${JSON.stringify(g.key)}`).toBeDefined();
      expect(digest(browse(q!)), `${g.id} ${JSON.stringify(g.key)} -> ${q}`).toEqual({ n: g.n, sha256: g.sha256 });
    }
  });

  it("membership-status drilldowns cover every status in both scopes (regression: group=member default)", () => {
    for (const id of ["membership_status", "membership_status_counted"]) {
      const d = dist(id);
      for (const it of d.items) {
        const q = distItemQuery(d, it.key)!;
        expect(q).toContain("group=all");
        expect(q.includes("eng=1"), `${id} ${q}`).toBe(d.denominator.id === "all_records");
        expect(browse(q).length, `${id} ${it.key}`).toBe(it.value);
      }
    }
    // The PR-5 link (no group, Browse defaults to members) returned 0 for every non-member status.
    expect(browse("status=boundary_family&eng=1").length).toBe(0);
    expect(browse(distItemQuery(dist("membership_status"), "boundary_family")!).length).toBe(509);
  });

  it("clade-state drilldowns keep the 4,468 members + candidates population (D4)", () => {
    const d = dist("clade_state_members_candidates");
    expect(d.denominator).toEqual({ id: "members_candidates", value: 4468 });
    let tot = 0;
    for (const it of d.items) {
      const q = distItemQuery(d, it.key)!;
      expect(q).toContain("group=member_candidate");
      const got = browse(q);
      expect(got.every((r) => r.membership_group === "member" || r.membership_group === "candidate")).toBe(true);
      expect(got.length).toBe(it.value);
      tot += got.length;
    }
    expect(tot).toBe(4468);
    expect(browse(distItemQuery(d, "confident")!).length).toBe(3821);
    // The all-records chart keeps the all-records population.
    const all = dist("clade_state");
    expect(browse(distItemQuery(all, "confident")!).length).toBe(all.items.find((i) => i.key === "confident")!.value);
  });

  it("crosstab cells reproduce their counts and sets", () => {
    const x = summary().crosstabs.find((c) => c.id === "evidence_by_membership_group_counted")!;
    expect(Object.keys(CROSSTAB_FILTER)).toContain(x.id);
    for (const c of x.cells) {
      const got = browse(crosstabCellQuery(x, c.row, c.col)!);
      expect(got.length, `${c.row}/${c.col}`).toBe(c.value);
      expect(got.every((r) => r.counts_eligible && r.membership_group === c.row && r.evidence_level === c.col)).toBe(true);
    }
  });

  it("drilldownQuery refuses filters that would leave the statistic's population", () => {
    expect(drilldownQuery("members_candidates", { group: "all" })).toBeUndefined();
    expect(drilldownQuery("members_candidates", { group: "boundary" })).toBeUndefined();
    expect(drilldownQuery("counted_records", { eng: true })).toBeUndefined();
    expect(drilldownQuery("pdb_entries", {})).toBeUndefined();
    // group=member is the Browse default and is therefore omitted from the canonical query
    expect(drilldownQuery("members_candidates", { group: "member" })).toBe("eng=1");
    expect(browse(drilldownQuery("members_candidates", { group: "member" })!).length).toBe(3089);
  });

  it("member_candidate group: tab, statuses and filter semantics", () => {
    expect(GROUPS).toContain("member_candidate");
    expect(inGroup("member_candidate", "member") && inGroup("member_candidate", "candidate")).toBe(true);
    expect(inGroup("member_candidate", "boundary")).toBe(false);
    expect(statusesForGroup("member_candidate")).toEqual([...statusesForGroup("member"), ...statusesForGroup("candidate")]);
    expect(browse("group=member_candidate&eng=1").length).toBe(4468);
    expect(browse("group=member_candidate").length).toBe(4468 - R().filter((r) => r.is_engineered && inGroup("member_candidate", r.membership_group)).length);
  });
});

describe("D1/D4 mutation tests: corrupted drilldowns are detected", () => {
  it("a clade-state link over all records (the PR-5 bug) does not reproduce the members+candidates set", () => {
    const d = dist("clade_state_members_candidates");
    const wrong = browse("group=all&state=confident&eng=1");
    const def = definitionSet(d.id, "members_candidates", "confident");
    expect(sameSet(wrong, def)).toBe(false);
    expect(wrong.length).not.toBe(3821);
  });
  it("dropping eng=1 from an all-records link changes the set (engineered constructs)", () => {
    const def = definitionSet("evidence_level_all", "all_records", "E1");
    expect(sameSet(browse("group=all&evidence=E1"), def)).toBe(false);
    expect(sameSet(browse("group=all&evidence=E1&eng=1"), def)).toBe(true);
  });
  it("a swapped category filter fails the golden hash even when counts are equal by chance", () => {
    const g = golden.items.find((x) => x.id === "membership_status" && x.key === "typeI_member_core")!;
    const other = golden.items.find((x) => x.id === "membership_status" && x.key !== g.key)!;
    expect(digest(browse(distItemQuery(dist("membership_status"), other.key as string)!))).not.toEqual({ n: g.n, sha256: g.sha256 });
  });
});

/* ------------------------------------------------------------------ D2: search -> browse */

describe("D2 Search -> Browse keeps structured semantics", () => {
  const opt = (q: string) => {
    const r = textSearch(R(), q);
    return { r, o: browseOptions(R(), q, r.keys) };
  };

  it("MR_CLD3_017: formal clade filter = the 1,646 formally assigned source records (DB golden)", () => {
    const { r, o } = opt("MR_CLD3_017");
    const formal = o.find((x) => x.query === "group=all&clade=MR_CLD3_017&eng=1")!;
    const g = golden.items.find((x) => x.kind === "search" && x.key === "formal")!;
    expect(g.n).toBe(1646);
    expect(formal.n).toBe(1646);
    expect(digest(browse(formal.query))).toEqual({ n: g.n, sha256: g.sha256 });
    // the text search also matches tentative placements, so the formal view is not "the same records"
    const gt = golden.items.find((x) => x.kind === "search" && x.key === "text_search_hits")!;
    expect(r.total).toBe(gt.n);
    expect(formal.same).toBe(false);
    expect(formal.onlySearch).toBe(gt.n - 1646);
    expect(formal.onlyBrowse).toBe(0);
  });

  it("MR_CLD3_017 incl. tentative equals the full search hit set (and the DB golden)", () => {
    const { r, o } = opt("MR_CLD3_017");
    const tent = o.find((x) => x.query === "group=all&clade=MR_CLD3_017&tent=1&eng=1")!;
    const g = golden.items.find((x) => x.kind === "search" && x.key === "formal_or_tentative")!;
    expect(digest(browse(tent.query))).toEqual({ n: g.n, sha256: g.sha256 });
    expect(tent.same).toBe(true);
    const hits = R().filter((x) => r.keys.has(x.source_acc));
    expect(sameSet(browse(tent.query), hits)).toBe(true);
  });

  it("the Browse free-text filter is never presented as equivalent for a clade ID", () => {
    const { o } = opt("MR_CLD3_017");
    const free = o.find((x) => x.query.includes("q="))!;
    expect(free.same).toBe(false);
    expect(free.n).toBeLessThan(1646);
  });

  it("PDB ID maps to pdbid= and equals the search set", () => {
    const { r, o } = opt("1C3W");
    const p = o.find((x) => x.query === "group=all&pdbid=1C3W&eng=1")!;
    expect(p.n).toBeGreaterThan(0);
    expect(p.n).toBe(r.total);
    expect(p.same).toBe(true);
  });

  it("subclade, motif and function map to their exact filters", () => {
    const sub = R().find((x) => x.subclade_id)!.subclade_id!;
    expect(opt(sub).o[0].query).toBe(`group=all&sub=${sub}&eng=1`);
    const m = opt("DTE").o.find((x) => x.query === "group=all&motif=DTE&eng=1")!;
    expect(m.n).toBe(R().filter((x) => x.helixC_motif === "DTE").length);
    expect(opt("proton_pump").o.find((x) => x.query === "group=all&func=proton_pump&eng=1")).toBeTruthy();
  });

  it("'same' is true only when accession sets are identical, for every option of several queries", () => {
    for (const q of ["MR_CLD3_017", "MR_CLD3_012", "1C3W", "DTE", "bacteriorhodopsin", "Halobacterium", "proton_pump"]) {
      const r = textSearch(R(), q);
      const hits = R().filter((x) => r.keys.has(x.source_acc));
      expect(r.keys.size).toBe(r.total);
      for (const o of browseOptions(R(), q, r.keys)) expect(o.same, `${q} ${o.query}`).toBe(sameSet(browse(o.query), hits));
    }
  });

  it("mutation: a corrupted hit set or mapping is not reported as the same records", () => {
    const r = textSearch(R(), "MR_CLD3_017");
    const keys = new Set(r.keys);
    keys.delete([...keys][0]);
    expect(browseOptions(R(), "MR_CLD3_017", keys).some((o) => o.same)).toBe(false);
    keys.add("NOT_A_RECORD");
    expect(browseOptions(R(), "MR_CLD3_017", keys).some((o) => o.same)).toBe(false);
  });
});

/* ------------------------------------------------------------------ D3: keyed reconciliation */

type DeepMutable<T> = { -readonly [K in keyof T]: DeepMutable<T[K]> };
const clone = (s: Summary): DeepMutable<Summary> => JSON.parse(JSON.stringify(s)) as DeepMutable<Summary>;
const reconBad = (s: DeepMutable<Summary>, id: string) => reconcile(s as Summary, R()).find((x) => x.id === id)!;

describe("D3 browser reconciliation is keyed and rejects corrupted distributions", () => {
  it("the unmodified summary reconciles exactly", () => {
    for (const r of reconcile(summary(), R())) expect(r.ok, r.id).toBe(true);
  });
  it("swapped category counts (same multiset of values) are detected", () => {
    const s = clone(summary());
    const d = s.distributions.find((x) => x.id === "evidence_level_counted")!;
    const a = d.items.find((i) => i.key === "E1")!, b = d.items.find((i) => i.key === "E2")!;
    [a.value, b.value] = [b.value, a.value];
    const r = reconBad(s, d.id);
    expect(r.ok).toBe(false);
    expect(r.mismatches.map((m) => m.key).sort()).toEqual(["E1", "E2"]);
  });
  it("a renamed null (missing) category is detected", () => {
    const s = clone(summary());
    const d = s.distributions.find((x) => x.id === "tax_domain_counted")!;
    d.items.find((i) => i.key === null)!.key = "Unknown";
    expect(reconBad(s, d.id).ok).toBe(false);
  });
  it("a duplicated key is detected even when it does not change the total", () => {
    const s = clone(summary());
    const d = s.distributions.find((x) => x.id === "func_class_counted")!;
    d.items.push({ ...d.items[0], value: 0 });
    const r = reconBad(s, d.id);
    expect(r.ok).toBe(false);
    expect(r.duplicates.length).toBe(1);
  });
  it("an extra zero-valued category is detected", () => {
    const s = clone(summary());
    s.distributions.find((x) => x.id === "membership_group")!.items.push({ key: "invented", value: 0 } as never);
    expect(reconBad(s, "membership_group").ok).toBe(false);
  });
  it("a missing distribution is reported, not skipped", () => {
    const s = clone(summary());
    s.distributions = s.distributions.filter((x) => x.id !== "clade_state_members_candidates");
    const r = reconcile(s as Summary, R());
    expect(r.length).toBe(12);
    expect(r.find((x) => x.id === "clade_state_members_candidates")!.ok).toBe(false);
  });
});
