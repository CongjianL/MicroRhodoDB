/**
 * PR-4a: formal v1.6.0 assignments vs EPA-ng placements on clade pages (cladeCounts) and the
 * MR_CLD3_009 E1 note. Values come from clades.json; the expected numbers were recomputed
 * independently from the frozen v1.6.0 SQLite in tests/test_web_pr4a.py.
 */
import { describe, expect, it } from "vitest";
import type { CladeLevel1, Subclade } from "../../src/data/types";
import { cladeCounts } from "../../src/features/tree/cladeCounts";
import { clades } from "./helpers";

const l1 = (id: string) => clades().level1.find((c) => c.clade_id === id) as CladeLevel1;
const sub = (id: string) => clades().subclades.find((c) => c.clade_id === id) as Subclade;

describe("cladeCounts: formal assignments are not placement counts", () => {
  it("MR_CLD3_B02: 4 placements (1 ok + 3 long pendant) but 5 formal assignments = 4 tips + 1 placement", () => {
    const m = cladeCounts(l1("MR_CLD3_B02"));
    expect(m.callField).toBe("subclade_call");
    expect([m.formalTips, m.formalPlacements, m.formalTotal]).toEqual([4, 1, 5]);
    expect(m.placementsTotal).toBe(4);
    expect(m.placementRows).toEqual([{ call: "assigned", ok: 1, longPendant: 3, total: 4, formal: 1 }]);
    expect(m.assignedCallFailingQc).toBe(3);
    expect(m.failingQcMeaning).toBe("placement_only");
    const only = l1("MR_CLD3_B02").placement_only_records ?? [];
    expect(only.map((r) => r.source_acc).sort()).toEqual(["A0A2P6MQ02", "A0A2P6NAG6", "A0A2P6NFX8"]);
    for (const r of only) {
      expect(r.placement_qc).toBe("long_pendant");
      expect(r.subclade_call).toBe("assigned");
      expect(r.clade_call_qc).toBe("unassigned");
      expect(r.clade_state).toBe("unassigned");
      expect(r.lwr_weighted_pendant).toBeGreaterThan(1.0);
    }
  });

  it("backbone groups: 97 placements, 94 formal placement assignments", () => {
    const b = ["MR_CLD3_B01", "MR_CLD3_B02"].map((id) => cladeCounts(l1(id)));
    expect(b.reduce((s, m) => s + m.placementsTotal, 0)).toBe(97);
    expect(b.reduce((s, m) => s + m.formalPlacements, 0)).toBe(94);
    expect(b[0].formalTotal).toBe(97); // B01 = 4 tips + 93 placements
    expect(l1("MR_CLD3_B01").placement_only_records).toEqual([]);
  });

  it("MR_CLD3_017 (level 1): 1,646 formal = 100 tips + 1,546; 597 long-pendant placements are the tentative records", () => {
    const c = l1("MR_CLD3_017");
    const m = cladeCounts(c);
    expect(m.callField).toBe("clade_call");
    expect([m.formalTips, m.formalPlacements, m.formalTotal]).toEqual([100, 1546, 1646]);
    expect(m.placementRows.find((r) => r.call === "assigned")).toMatchObject({ ok: 1546, longPendant: 597 });
    expect(m.assignedCallFailingQc).toBe(597);
    expect(m.failingQcMeaning).toBe("tentative_level1");
    expect(m.formalTotal).toBe(c.n_records_confident);
    expect(c.placement_only_records).toBeNull();
  });

  it("MR_CLD3_017.02 (subclade): 311 formal, not the 480 placements with subclade call assigned", () => {
    const s = sub("MR_CLD3_017.02");
    const m = cladeCounts(s);
    expect([m.formalTips, m.formalPlacements, m.formalTotal]).toEqual([22, 289, 311]);
    expect(m.placementRows.find((r) => r.call === "assigned")).toMatchObject({ ok: 289, longPendant: 191, total: 480 });
    expect(m.placementRows.find((r) => r.call === "unassigned")).toMatchObject({ longPendant: 2 });
    expect(m.formalTotal).toBe(s.n_records_assigned);
  });

  it("every group: formal total = tips + placements; formal placements = assigned & QC ok; level-1 failing = tentative", () => {
    for (const c of [...clades().level1, ...clades().subclades]) {
      const m = cladeCounts(c);
      expect(m.formalTotal, c.clade_id).toBe(m.formalTips + m.formalPlacements);
      expect(m.formalPlacements, c.clade_id).toBe(c.placement_counts.by_call_and_qc.assigned?.ok ?? 0);
      expect(m.formalTips, c.clade_id).toBe(c.n_reference_tips_in_corpus);
      if (c.level === 1 && (c as CladeLevel1).kind === "clade") {
        expect(m.formalTotal, c.clade_id).toBe((c as CladeLevel1).n_records_confident);
        expect(m.assignedCallFailingQc, c.clade_id).toBe((c as CladeLevel1).n_records_tentative);
      } else {
        expect(m.formalTotal, c.clade_id).toBe(c.n_records_assigned);
      }
    }
  });
});

describe("MR_CLD3_009 E1 note", () => {
  it("12 E1 source records, 11 counted; the excluded one is engineered A0A8X6EH36", () => {
    const c = l1("MR_CLD3_009");
    expect(c.e1_anchors.length).toBe(12);
    expect(c.function_consensus.n_E1).toBe(11);
    expect(cladeCounts(c).e1Excluded).toEqual([{ source_acc: "A0A8X6EH36", mrdb_acc: "MRDB003178", is_engineered: true }]);
  });

  it("no other group has an excluded E1 record", () => {
    for (const c of clades().level1.filter((x) => x.clade_id !== "MR_CLD3_009")) {
      expect(cladeCounts(c).e1Excluded, c.clade_id).toEqual([]);
      expect(c.e1_anchors.length, c.clade_id).toBe(c.function_consensus.n_E1);
    }
  });
});
