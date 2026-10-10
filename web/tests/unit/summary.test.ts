/**
 * Home-page statistics and links: every number shown on Home comes from summary.json / clades.json,
 * and every Home link into Browse opens a selection whose size equals the number displayed.
 */
import { describe, expect, it } from "vitest";
import { applyFilters, parseBrowse } from "../../src/lib/browse";
import { caveatMap, distribution, failingClades, mv, thresholdText } from "../../src/lib/summary";
import { clades, rows, summary } from "./helpers";

const count = (q: string) => applyFilters(rows(), parseBrowse(new URLSearchParams(q)).state).length;

describe("frozen v1.6.0 headline numbers", () => {
  const S = summary();
  it("records, counted records, MRDB accessions, tree tips, clades", () => {
    expect(mv(S, "records_total")).toBe(5466);
    expect(mv(S, "records_counted")).toBe(5460);
    expect(mv(S, "mrdb_accessions")).toBe(5299);
    expect(mv(S, "tree_tips")).toBe(472);
    expect(mv(S, "level1_clades")).toBe(17);
    expect(mv(S, "backbone_groups")).toBe(2);
    expect(mv(S, "e1_counted")).toBe(88);
  });
  it("every metric with a denominator states it", () => {
    for (const m of S.metrics) if (m.denominator) expect(m.denominator.value).toBeGreaterThan(0);
  });
});

describe("Home links open selections of the displayed size", () => {
  const S = summary();
  it("stat cards", () => {
    expect(count("group=all&eng=1")).toBe(mv(S, "records_total"));
    expect(count("group=member&eng=1")).toBe(mv(S, "typeI_members"));
    expect(count("group=all&evidence=E1")).toBe(mv(S, "e1_counted"));
  });
  it("function links (counted records: engineered hidden)", () => {
    for (const it of distribution(S, "func_class_counted").items) expect(count(`group=all&func=${it.key}`)).toBe(it.value);
  });
  it("clade legend: confident records, and confident + tentative with tent=1", () => {
    for (const c of clades().level1) {
      expect(count(`group=all&eng=1&clade=${c.clade_id}`), c.clade_id).toBe(c.n_records_confident);
      expect(count(`group=all&eng=1&clade=${c.clade_id}&tent=1`), c.clade_id).toBe(c.n_records_confident + c.n_records_tentative);
    }
  });
});

describe("phylogenetic-uncertainty disclosure", () => {
  const C = clades();
  it("only MR_CLD3_017 fails the corrected IQ-TREE run1 support thresholds", () => {
    const f = failingClades(C);
    expect(f.map((x) => x.clade_id)).toEqual(["MR_CLD3_017"]);
    expect(f[0].support_audit.iqtree_run1_sh_alrt).toBe(50.3);
    expect(f[0].support_audit.iqtree_run1_ufboot).toBe(72);
    expect(f[0].n_records_confident).toBe(1646);
    expect(f[0].n_records_tentative).toBe(597);
  });
  it("caveat text states the corrected values and thresholds", () => {
    expect(thresholdText(C)).toBe("SH-aLRT \u2265 80 and UFBoot \u2265 95");
    expect(caveatMap(C).get("MR_CLD3_017")).toBe(
      "legacy v1.6.0 assignment; corrected IQ-TREE run1 support SH-aLRT 50.3 / UFBoot 72 fails the thresholds (SH-aLRT \u2265 80 and UFBoot \u2265 95)",
    );
  });
  it("all other clades meet the thresholds with run1 support", () => {
    for (const c of C.level1) {
      if (c.clade_id === "MR_CLD3_017") continue;
      expect(c.support_audit.iqtree_run1_sh_alrt!).toBeGreaterThanOrEqual(80);
      expect(c.support_audit.iqtree_run1_ufboot!).toBeGreaterThanOrEqual(95);
    }
  });
});
