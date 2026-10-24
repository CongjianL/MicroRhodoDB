/**
 * PR-5 scientific regression tests: Statistics reconciliation against the exported index, top-N folding,
 * crosstab margins, basis mapping, conflict parsing, text-search golden cases, citation formatting and
 * watchlist isolation. All expected numbers are read from the export (summary.json) except the frozen
 * corpus headline values, which are asserted literally as the G5 reconciliation targets.
 */
import { describe, expect, it } from "vitest";
import type { Downloads, EvidenceIndex, Watchlist } from "../../src/data/types";
import { FIELD_LABEL, fieldCounts, matchRow, textSearch } from "../../src/features/search/textSearch";
import { apa, bibEscape, bibtex, fmtBytes } from "../../src/lib/citation";
import { NULL_KEY, OTHER_KEY, basisCategory, matrix, parseConflictDetail, reconcile, topN } from "../../src/lib/stats";
import { distribution, mv } from "../../src/lib/summary";
import { WATCHLIST_COLUMNS, watchlistTsv, type WatchlistCandidate } from "../../src/lib/watchlist";
import { json, rows, summary } from "./helpers";

describe("G5 corpus reconciliation (frozen v1.6.1 targets)", () => {
  it("headline denominators are 5,466 source / 5,460 counted / 5,299 MRDB", () => {
    const s = summary();
    expect(mv(s, "records_total")).toBe(5466);
    expect(mv(s, "records_counted")).toBe(5460);
    expect(mv(s, "mrdb_accessions")).toBe(5299);
    expect(rows().length).toBe(5466);
    expect(rows().filter((r) => r.counts_eligible).length).toBe(5460);
    expect(new Set(rows().map((r) => r.mrdb_acc)).size).toBe(5299);
    expect(s.denominators.all_records.value).toBe(5466);
    expect(s.denominators.counted_records.value).toBe(5460);
    expect(s.denominators.mrdb_accessions.value).toBe(5299);
  });
  it("every recountable chart reconciles category by category with records-index.json", () => {
    const rec = reconcile(summary(), rows());
    expect(rec.length).toBe(12);
    for (const r of rec) {
      expect(r.mismatches, r.id).toEqual([]);
      expect(r.ok, r.id).toBe(true);
    }
  });
  it("every distribution sums to its denominator", () => {
    for (const d of summary().distributions) {
      const sum = d.items.reduce((a, b) => a + b.value, 0);
      expect(sum, d.id).toBe(d.denominator.value);
    }
  });
  it("E1 is 88 of counted records and 91 of all records; never mixed", () => {
    const s = summary();
    expect(mv(s, "e1_counted")).toBe(88);
    expect(mv(s, "e1_total")).toBe(91);
    const c = distribution(s, "evidence_level_counted");
    const a = distribution(s, "evidence_level_all");
    expect(c.items.find((i) => i.key === "E1")?.value).toBe(88);
    expect(a.items.find((i) => i.key === "E1")?.value).toBe(91);
    expect(c.denominator.id).toBe("counted_records");
    expect(a.denominator.id).toBe("all_records");
    expect(rows().filter((r) => r.evidence_level === "E1" && r.counts_eligible).length).toBe(88);
    expect(rows().filter((r) => r.evidence_level === "E1").length).toBe(91);
  });
  it("clade coverage is 3,821 of 4,465 members + candidates", () => {
    const s = summary();
    expect(mv(s, "members_candidates")).toBe(4465);
    expect(mv(s, "clade_confident_members_candidates")).toBe(3821);
    const d = distribution(s, "clade_state_members_candidates");
    expect(d.denominator.value).toBe(4465);
    expect(d.items.find((i) => i.key === "confident")?.value).toBe(3821);
  });
  it("crosstabs: cells sum to the denominator and margins equal the 1-D distributions", () => {
    const s = summary();
    for (const x of s.crosstabs) {
      const m = matrix(x);
      expect(m.total, x.id).toBe(x.denominator.value);
      expect(m.rows.reduce((a, r) => a + m.rowTotal(r), 0)).toBe(m.total);
      expect(m.cols.reduce((a, c) => a + m.colTotal(c), 0)).toBe(m.total);
    }
    const ev = distribution(s, "evidence_level_counted");
    const byGroup = matrix(s.crosstabs.find((x) => x.id === "evidence_by_membership_group_counted")!);
    const levelsAsCols = byGroup.cols.includes("E1");
    for (const it of ev.items) {
      expect(levelsAsCols ? byGroup.colTotal(it.key) : byGroup.rowTotal(it.key), String(it.key)).toBe(it.value);
    }
  });
  it("membership group and evidence level are separate axes (E1 spans several membership groups)", () => {
    const groups = new Set(rows().filter((r) => r.evidence_level === "E1").map((r) => r.membership_group));
    expect(groups.size).toBeGreaterThan(1);
  });
});

describe("topN folding", () => {
  it("keeps totals, keeps null separate and counts folded categories", () => {
    const items = [{ key: "a", value: 5 }, { key: "b", value: 3 }, { key: "c", value: 2 }, { key: "d", value: 1 }, { key: null, value: 4 }];
    const r = topN(items, 2);
    expect(r.total).toBe(15);
    expect(r.items.map((i) => i.key)).toEqual(["a", "b", OTHER_KEY, NULL_KEY]);
    expect(r.items[2]).toMatchObject({ value: 3, nOther: 2 });
  });
  it("phylum (top 12) and helix-C motif (top 15) charts still total their denominators", () => {
    for (const [id, n] of [["ncbi_phylum_counted", 12], ["helixC_motif_counted", 15]] as const) {
      const d = distribution(summary(), id);
      expect(topN(d.items, n).total, id).toBe(d.denominator.value);
    }
  });
});

describe("function basis and conflicts", () => {
  it("every counted record maps to a known basis category (no UNMAPPED)", () => {
    const counted = rows().filter((r) => r.counts_eligible);
    expect(counted.filter((r) => basisCategory(r.function_basis) === "UNMAPPED").length).toBe(0);
    expect(basisCategory(null)).toBe("UNMAPPED");
    expect(basisCategory("Curated_Rule:x")).toBe("curated_rule");
  });
  it("parses every stored conflict detail and the action counts match the export", () => {
    const c = rows().filter((r) => r.call_conflict);
    expect(c.length).toBe(mv(summary(), "call_conflict"));
    const counts = new Map<string, number>();
    for (const r of c) {
      const p = parseConflictDetail(r.call_conflict_detail);
      expect(p?.action, r.source_acc).toBeTruthy();
      counts.set(p!.action!, (counts.get(p!.action!) ?? 0) + 1);
    }
    expect(Object.fromEntries(counts)).toEqual({ downgraded_to_E5: 450, flag_only_E1: 15, flag_only_E2: 9, flag_only_E4_curated_rule: 6 });
    // Downgraded calls are E5 in the release; flagged-only calls keep their level.
    for (const r of c) {
      const p = parseConflictDetail(r.call_conflict_detail)!;
      if (p.action === "downgraded_to_E5") expect(r.evidence_level).toBe("E5");
      // Known v1.6.1 issue: A0A0C3UE61 (E2, identical to E1 record L1K1K8) copied its twin's detail verbatim,
      // including "action=flag_only_E1"; to be corrected to flag_only_E2 in the next release (CHANGELOG).
      if (p.action === "flag_only_E1" && r.source_acc !== "A0A0C3UE61") expect(r.evidence_level).toBe("E1");
    }
  });
  it("curated overrides and engineered constructs are as stored", () => {
    const ev = json<EvidenceIndex>("evidence-index.json");
    const cur = (ev.curated_overrides as unknown as { source_acc: string }[]).map((x) => x.source_acc).sort();
    expect(cur).toEqual(["A0A0C3UE61", "A0A1I3DJQ0", "A0A3G1I4H9", "A0ABF7PQ82", "A0ABY1EHF9", "L1K1K8"]);
    const eng = rows().filter((r) => r.is_engineered);
    expect(eng.length).toBe(6);
    expect(eng.every((r) => !r.counts_eligible && r.wild_type_acc)).toBe(true);
  });
});

describe("text search golden cases", () => {
  const R = () => rows();
  const top = (q: string) => textSearch(R(), q).hits[0];
  it("exact accessions rank first", () => {
    expect(top("P02945")).toMatchObject({ field: "source_acc", score: 100 });
    expect(top("P02945").row.source_acc).toBe("P02945");
    expect(top("mrdb000001")).toMatchObject({ field: "mrdb_acc" });
    expect(top("MRDB000001").row.mrdb_acc).toBe("MRDB000001");
  });
  it("PDB IDs match stored protein-PDB links only", () => {
    const r = textSearch(R(), "1C3W");
    expect(r.total).toBeGreaterThan(0);
    for (const h of r.hits.filter((x) => x.field === "pdb_id")) expect(h.row.pdb_ids).toContain("1C3W");
    expect(r.hits[0].field).toBe("pdb_id");
    expect(r.hits[0].row.mrdb_acc).toBe("MRDB000001");
  });
  it("clade IDs return the confident assignments of that clade", () => {
    const r = textSearch(R(), "MR_CLD3_017", 10000);
    const confident = R().filter((x) => x.clade_id === "MR_CLD3_017").length;
    expect(r.hits.filter((h) => h.field === "clade_id").length).toBe(confident);
    expect(r.hits.filter((h) => h.field === "tentative_clade_id").every((h) => h.row.clade_id !== "MR_CLD3_017")).toBe(true);
  });
  it("helix-C motif matches the motif column exactly", () => {
    const r = textSearch(R(), "DTE", 10000);
    const n = R().filter((x) => x.helixC_motif === "DTE").length;
    expect(r.hits.filter((h) => h.field === "helixC_motif").length).toBe(n);
  });
  it("free text reports the matched field; results are deterministic and capped", () => {
    const a = textSearch(R(), "bacteriorhodopsin");
    const b = textSearch(R(), "bacteriorhodopsin");
    expect(a.hits.map((h) => h.row.source_acc)).toEqual(b.hits.map((h) => h.row.source_acc));
    expect(a.total).toBeGreaterThan(0);
    expect(a.hits.length).toBeLessThanOrEqual(200);
    expect(a.truncated).toBe(a.total > 200);
    for (const h of a.hits) expect(FIELD_LABEL[h.field]).toBeTruthy();
    expect(fieldCounts(a.hits).reduce((s, [, n]) => s + n, 0)).toBe(a.hits.length);
  });
  it("short, empty and absent queries", () => {
    expect(textSearch(R(), "").kind).toBe("empty");
    expect(textSearch(R(), "a").kind).toBe("too_short");
    expect(textSearch(R(), "zzzzqqqq").total).toBe(0);
  });
  it("watchlist identifiers are not corpus records and are not found", () => {
    const wl = json<Watchlist>("watchlist.json").candidates as unknown as WatchlistCandidate[];
    const corpus = new Set(R().map((r) => r.source_acc));
    const notInCorpus = wl.map((c) => c.resolved_accession).filter((a): a is string => !!a && !corpus.has(a)).slice(0, 20);
    expect(notInCorpus.length).toBeGreaterThan(0);
    for (const a of notInCorpus) expect(textSearch(R(), a).hits.filter((h) => h.field === "source_acc" && h.score === 100)).toEqual([]);
  });
  it("matchRow never matches PDB IDs against protein names", () => {
    const r = R().find((x) => x.pdb_ids.length === 0)!;
    expect(matchRow(r, "1C3W")).toBeNull();
  });
});

describe("watchlist isolation", () => {
  it("candidate rows and the TSV export carry no membership, evidence or function field", () => {
    const wl = json<Watchlist>("watchlist.json");
    const cands = wl.candidates as unknown as WatchlistCandidate[];
    expect(cands.length).toBe(mv(summary(), "watchlist"));
    const forbidden = /membership|evidence|func|clade|mrdb_acc|status/i;
    for (const c of cands) for (const k of Object.keys(c)) expect(k).not.toMatch(forbidden);
    for (const k of WATCHLIST_COLUMNS) expect(k).not.toMatch(forbidden);
    const tsv = watchlistTsv(cands);
    expect(tsv.split("\n").filter(Boolean).length).toBe(cands.length + 1);
    expect(tsv.split("\n")[0].split("\t")).toEqual(WATCHLIST_COLUMNS);
  });
  it("no watchlist entry is counted in any corpus distribution", () => {
    for (const d of summary().distributions) {
      if (d.id === "watchlist_family") expect(d.denominator.id).toBe("watchlist");
      else expect(d.denominator.id).not.toBe("watchlist");
    }
  });
});

describe("citation", () => {
  const d = () => json<Downloads>("downloads.json");
  it("APA and BibTeX come from CITATION.cff and cite the data release, not the website version", () => {
    const c = d().citation;
    const a = apa(c);
    expect(a).toContain("Li, C. (2026).");
    expect(a).toContain("(Version 1.6.1) [Data set].");
    expect(a).toContain("https://github.com/CongjianL/MicroRhodoDB");
    expect(a).not.toContain(d().website_version);
    const b = bibtex(c);
    expect(b).toMatch(/^@misc\{li_microrhododb_161_2026,/);
    expect(b).toContain("version = {1.6.1}");
    expect(b).not.toContain("doi =");
    expect(b).not.toContain(d().website_version);
    expect(c.doi).toBeNull();
  });
  it("escapes BibTeX specials and formats sizes", () => {
    expect(bibEscape("a & b_c 50%")).toBe("a \\& b\\_c 50\\%");
    expect(fmtBytes(999)).toBe("999 B");
    expect(fmtBytes(12379)).toBe("12 kB");
    expect(fmtBytes(1500)).toBe("1.5 kB");
  });
  it("downloads list the 39 release files and keeps the database as an unverified release asset", () => {
    const x = d();
    expect(x.release_files.length).toBe(39);
    const notGit = x.release_files.filter((f) => !f.in_git_at_tag);
    expect(notGit.map((f) => f.path)).toEqual(["db/microrhododb_v1.6.1.sqlite"]);
    expect(notGit[0].sha256).toBe("b8215cffa9d2fdab1e65b904f4bafbe9edf6578aed7b4fb028a890850e704c2d");
    expect(notGit[0].distribution).toMatch(/not verified/);
    expect(x.maintenance_placeholders.every((m) => /not supplied/.test(m.status))).toBe(true);
  });
});
