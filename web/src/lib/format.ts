/**
 * Display labels and number formatting. Labels are presentation only: the raw database code is
 * always kept (tooltips, exports, URLs) and no label merges or renames a scientific category.
 */
import type { CladeState, EvidenceLevel, FuncClass, MembershipGroup, MembershipStatus } from "../data/types";

const nf = new Intl.NumberFormat("en-US");
export const fmtInt = (n: number) => nf.format(n);

/** "56.5%" with one decimal; denominators must be shown next to it by the caller. */
export function fmtPct(n: number, d: number): string {
  if (!d) return "n/a";
  const p = (100 * n) / d;
  return `${p < 0.1 && p > 0 ? "<0.1" : p.toFixed(1)}%`;
}

export const STATUS_LABEL: Record<MembershipStatus, string> = {
  typeI_member_core: "Member (core)",
  typeI_member_architecture_supported: "Member (architecture-supported)",
  typeI_member_curated: "Member (curated override)",
  typeI_candidate: "Candidate",
  typeI_candidate_architecture_supported: "Candidate (architecture-supported)",
  typeI_candidate_unresolved: "Candidate (unresolved)",
  boundary_family: "Boundary family",
  heliorhodopsin: "Heliorhodopsin",
  decoy_or_rejected: "Decoy / rejected",
};

export const STATUS_ORDER: MembershipStatus[] = [
  "typeI_member_core", "typeI_member_architecture_supported", "typeI_member_curated",
  "typeI_candidate", "typeI_candidate_architecture_supported", "typeI_candidate_unresolved",
  "boundary_family", "heliorhodopsin", "decoy_or_rejected",
];

export const STATUS_GROUP: Record<MembershipStatus, MembershipGroup> = {
  typeI_member_core: "member",
  typeI_member_architecture_supported: "member",
  typeI_member_curated: "member",
  typeI_candidate: "candidate",
  typeI_candidate_architecture_supported: "candidate",
  typeI_candidate_unresolved: "candidate",
  boundary_family: "boundary",
  heliorhodopsin: "outgroup",
  decoy_or_rejected: "rejected",
};

export const GROUP_LABEL: Record<MembershipGroup, string> = {
  member: "Type-I members",
  candidate: "Candidates",
  boundary: "Boundary families",
  outgroup: "Heliorhodopsins",
  rejected: "Decoys / rejected",
};

export const FUNC_LABEL: Record<FuncClass, string> = {
  proton_pump: "Proton pump (outward)",
  proton_pump_inward: "Proton pump (inward)",
  anion_pump: "Anion pump",
  sodium_pump: "Sodium pump",
  light_gated_channel: "Light-gated channel",
  sensory: "Sensory",
  sensory_like: "Sensory-like",
  enzyme_rhodopsin: "Enzyme rhodopsin",
  photoreceptor_unassigned: "Photoreceptor (unassigned)",
  unresolved: "Unresolved (no call)",
  unassigned: "Unassigned (call withdrawn)",
};

export const FUNC_ORDER: FuncClass[] = [
  "proton_pump", "proton_pump_inward", "anion_pump", "sodium_pump", "light_gated_channel", "sensory",
  "sensory_like", "enzyme_rhodopsin", "photoreceptor_unassigned", "unassigned", "unresolved",
];

export const EVIDENCE_LEVELS: EvidenceLevel[] = ["E1", "E2", "E3", "E4", "E5"];

export const CLADE_STATE_LABEL: Record<CladeState, string> = {
  confident: "Clade assigned",
  tentative: "Tentative placement",
  reference_tip_unclustered: "Backbone tip (unclustered)",
  outgroup_reference_tip: "Outgroup reference tip",
  outgroup_placed: "Placed in outgroup",
  unassigned: "Unassigned",
  distant: "Distant placement",
};

export const DOMAIN_NONE = "none";
export const domainLabel = (d: string | null) => d ?? "No domain assigned";

/** Short display of a clade id: MR_CLD3_006 -> "006", MR_CLD3_B01 -> "B01". */
export const cladeShort = (id: string) => id.replace(/^MR_CLD3_/, "");
