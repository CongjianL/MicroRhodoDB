/**
 * PR-4a: keep formal v1.6.1 record assignments apart from EPA-ng placement counts on clade pages.
 *
 * Formal assignment (pipeline/v150/record_clades.py, exported as clades.json -> assignment_counts):
 *   reference tips in the corpus + placements whose call (clade_call for level-1 clades, subclade_call for
 *   subclades and backbone groups) is "assigned" AND placement_qc is "ok" (LWR-weighted pendant <= 1.0).
 * Placements with call "assigned" but placement_qc "long_pendant" are placements only: at level 1 they are the
 * tentative (distant_assigned) records; for subclades and backbone groups they carry no formal assignment.
 */
import type { CladeLevel1, Subclade } from "../../data/types";

export type CladeLike = CladeLevel1 | Subclade;

export interface PlacementRow {
  call: string;
  ok: number;
  longPendant: number;
  total: number;
  /** number of placements in this row that are formal assignments (call assigned and QC ok) */
  formal: number;
}

export interface CladeCountModel {
  callField: "clade_call" | "subclade_call";
  formalTotal: number;
  formalTips: number;
  formalPlacements: number;
  placementsTotal: number;
  placementRows: PlacementRow[];
  /** placements with call = assigned that fail pendant QC (not formal assignments) */
  assignedCallFailingQc: number;
  /** level-1 clades: those records are the tentative ones; elsewhere they have no formal assignment */
  failingQcMeaning: "tentative_level1" | "placement_only";
  /** E1 source records listed for the group that are excluded from the official count (engineered constructs) */
  e1Excluded: { source_acc: string; mrdb_acc: string; is_engineered: boolean | null }[];
}

const CALL_ORDER = ["assigned", "tentative", "unassigned"];

export function cladeCounts(c: CladeLike): CladeCountModel {
  const pc = c.placement_counts;
  const rows: PlacementRow[] = Object.entries(pc.by_call_and_qc)
    .map(([call, q]) => {
      const ok = q.ok ?? 0;
      const lp = q.long_pendant ?? 0;
      const other = Object.entries(q).filter(([k]) => k !== "ok" && k !== "long_pendant").reduce((s, [, n]) => s + n, 0);
      return { call, ok, longPendant: lp, total: ok + lp + other, formal: call === "assigned" ? ok : 0 };
    })
    .sort((a, b) => (CALL_ORDER.indexOf(a.call) + 99 * +!CALL_ORDER.includes(a.call)) - (CALL_ORDER.indexOf(b.call) + 99 * +!CALL_ORDER.includes(b.call)) || a.call.localeCompare(b.call));
  const ac = c.assignment_counts;
  const isLevel1Clade = c.level === 1 && "kind" in c && c.kind === "clade";
  const e1 = "e1_anchors" in c ? c.e1_anchors : [];
  return {
    callField: pc.call_field,
    formalTotal: ac.total,
    formalTips: ac.reference_tips,
    formalPlacements: ac.placements,
    placementsTotal: rows.reduce((s, r) => s + r.total, 0),
    placementRows: rows,
    assignedCallFailingQc: ac.placements_assigned_call_failing_qc,
    failingQcMeaning: isLevel1Clade ? "tentative_level1" : "placement_only",
    e1Excluded: e1.filter((e) => e.counts_eligible === false).map((e) => ({ source_acc: e.source_acc, mrdb_acc: e.mrdb_acc, is_engineered: e.is_engineered })),
  };
}
