# Changelog

All notable changes to MicroRhodoDB. Release entries summarize the immutable
release artifacts under `releases/`; see `docs/RELEASE_HISTORY.md` for the
architectural narrative and per-release `RELEASE_NOTES`/`report_*.md` for full
detail.

## [1.6.1] - 2026-10-24

**Correction release.** Built from the immutable v1.6.0 database (opened read-only, SHA-256 checked) plus
`curation/v161/` (107 field changes on 23 records, rule set approved by CongJian Li on 2026-10-24). Corpus, scorer,
thresholds, tree, placements and clade assignments unchanged. Release artifact: `releases/v1.6.1/` (schema
`v161.1`); rebuild with `snakemake -c 1 all_v161` (93/93 objects identical). Full detail:
`releases/v1.6.1/RELEASE_NOTES_v1.6.1.md`.

- **One decision per unique sequence.** Byte-identical records now share one membership status and one function call
  (rules M1, M2, F1-F5 in `pipeline/v161/identical_sequences_v161.py`). HSP30 copies follow the curated decoys; twins
  of CryoR1 and GtCCR2 become curated members (E2 at identity 1.00). Members 3,089 -> 3,091, candidates 1,379 ->
  1,374, rejected 103 -> 106; counted E2 109 -> 111, E4 1,050 -> 1,045, E5 3,070 -> 3,073; conflict flags 468 -> 480.
- **Clade names.** `clade.name_basis_type` marks the 6 provisional names (no characterised member); MR_CLD3_017
  naming basis corrected (Q70LL3 is E4 since v1.6.0).
- **Stated policies.** Candidates are never called (E5 by policy); curation recommendations and the blind audit
  calls were AI-assisted and curator-reviewed (`release_metadata`, data dictionary).
- **Provenance.** View `v_curation_decision`: one decider and date for every v1.6.0 and v1.6.1 decision.
- **CLI fix.** `typeI_detected_070` applies the `full_gated` gates; heliorhodopsins are no longer reported as
  detected Type-I rhodopsins.
- **New validation.** Hard-negative specificity, nearest-E1 transfer baseline, E3 robustness on the replicate trees
  (`releases/v1.6.1/validation/`).
- **Known issue.** A0A0C3UE61 (E2; identical to the E1 record L1K1K8) copied its twin's `call_conflict_detail`
  verbatim, so it reads `action=flag_only_E1` although the record is E2. To be corrected to `flag_only_E2` in the
  next release; the website tests allow exactly this record.
- **Website (after release).** Website 2.0 exports and serves v1.6.1 (dataset release in `web/src/data/release.ts`,
  `web/release/release_contract.json`, `CITATION.cff`); the release gate reads the dataset release from `CITATION.cff`.

## [1.6.0] - 2026-10-10

**Response to the v1.5.0 referee report (23 actions) and to the second-round comments (R2).** Built from the
immutable v1.5.0 database (opened read-only) plus curator-signed decisions (`curation/v160/`, 622 rows in the
`curation_v160_decision` table, all decided by CongJian Li on 2026-10-09 and, for R2, 2026-10-10). The membership
scorer and thresholds are unchanged; `membership_status` changes only for 4 curated overrides (R2).
Release artifact: `releases/v1.6.0/` (schema `v160.1`). Full detail: `releases/v1.6.0/RELEASE_NOTES_v1.6.0.md`.

Function evidence
- **Conflict flag.** New `function_evidence.call_conflict` / `call_conflict_detail`. A call conflicts when the
  record's motif class is defined and incompatible with the call (compatibility map in `func_class_definition`).
  468 records flagged. The 439 conflicting E3/E4 calls are downgraded to E5 `unassigned` (basis
  `conflict: v14=<X>; motif=<Y>`; 377 of them in the fungal clade MR_CLD3_017). The 29 conflicting E1/E2/
  curated-rule calls are flagged only (E1 14, E2 9, E4 curated rule 6).
- **Basis wording.** E3/E4 calls whose inherited v1.4 class agrees with the motif now read
  `legacy_v14_concordant_motif` (973) or `legacy_v14_motif_untestable` (51) instead of `motif_only:`.
  `func_class_v14` and `motif_class` are kept as columns.
- **Record corrections and E1 sweep.** 16 records promoted to E1, including UmOps1/UmOps2 (proton pumps),
  glycylhalorhodopsin A0A5B2VFD4 (inward anion pump), SpaR A0A411LJN5 (proton pump), NOP-1 Q9UW81
  (`photoreceptor_unassigned`), exoKCR1, ExoC110T, GtCCR2 and CryoR1. 8 records leave E1: 6 whose only support
  was a compilation (re-tiered, curator decision) and the 2 carO entries Q70LL3/S0ELR6 (E4 proton_pump by signed
  curated rule). R2 evidence checks withdrew 2 more (Q6R5N7 -> E2 proton_pump; A0A0P6XBM7 -> E4 sodium_pump).
  E1: 85 -> 91 records (88 counted, 76 unique non-engineered sequences).
- **Publications.** 49 publications added (72 -> 121) and 178 links added, each labelled `support`,
  `compilation` or `context`; compilation links no longer count as E1 support. All 91 E1 records have a support
  link; all 66 new support links have a quote verified in retrieved text (2 in full text: A0A0M5L0M3 preprint,
  A0ACE3JIR6 thesis). ECO tokens removed from PMID fields.
- **Held-out estimate.** New `loco_validation` / `loco_validation_record` tables: leave-one-out,
  leave-one-subfamily-out and leave-one-clade-out on the 76 unique E1 sequences with motif rules frozen
  (LOCO legacy 52/70 = 0.743, 95% CI 0.63-0.83).

Records
- **Engineered constructs.** New `is_engineered` and `wild_type_acc`. 6 constructs flagged (His-tagged PDB
  constructs and point mutants); excluded from counts, coverage, E2 transfer and benchmarks (`v_counted`,
  5,460 records). HcKCR1 C110A/C110T keep their own E1 (curator Option B) and exoKCR1 A0ABF7PQ82 carries E1.
- **Novel-family layer.** New `novel_family_candidate` / `novel_family_funnel` tables: profile-HMM search of
  UniProtKB for MerMAID, bestrhodopsin, schizorhodopsin, xenorhodopsin and viral rhodopsin seeds outside the
  corpus. No sequence candidate passed all filters; R2 adds a Foldseek watchlist (below). Counts unchanged.
- **Provenance.** `sequence_source.source_release` now stores `UniProtKB_2026_02` (5,361) / `UniProtKB_2026_03`
  (105).

Schema and documentation
- `data_dictionary` table (1,232 rows, 91 objects, 100% column coverage), also exported as TSV.
- Removed, as announced in v1.5.0: `membership.alias_v14` and the compatibility views `v_typeI_core`,
  `v_typeI_candidates`, `v_typeI_active`, `v_rejected_or_decoy`. Residual `alias_v14` columns in
  `status_definition` and `route3_candidate_support` renamed `status_label_v14`.
- New views `v_counted`, `v_call_conflict`, `v_engineered`.
- Scorer reporting corrected: the two-rule baseline `B4b_ga_retK` equals `full_gated` on the external set
  (AUPRC 0.910); the v1.5.0 statement that the score "clearly outperforms every baseline" is withdrawn.
  Recommended detection threshold 0.70. `releases/v1.6.0/validation/scorer_validation_v160.tsv`.

Second-round referee comments (R2; signed 2026-10-10)
- **Curated membership override (R-F3).** New status `typeI_member_curated` for E1 records with direct
  experimental evidence (PMID) that the scorer leaves as candidates: CryoR1 A0A1I3DJQ0, GtCCR2 L1K1K8, GtCCR4
  A0A3G1I4H9, exoKCR1 A0ABF7PQ82. Members 3,085 -> 3,089, candidates 1,383 -> 1,379; scores unchanged.
- **`clade_function` recomputed** with the v1.5.0 rule on the v1.6.0 E1 set (new table
  `clade_function_consensus`: 16/49 groups with consensus). 657 records lose an inherited class (625 proton_pump,
  32 anion_pump); 239 MR_CLD3_017 calls (223 in MR_CLD3_017.01) fall from E3 to E4.
- **Curated audit rules.** Xenorhodopsin-like D-T-A/D-S-A (69) and OpsA-like D-S-E (47) E4 calls -> E5
  `unresolved`; schizorhodopsins A0AAP2RB57 and A0ABT8M6U9 -> E5 `unresolved`.
- **E1 evidence checks.** A0A0M5L0M3 kept (quote in bioRxiv preprint); A0ACE3JIR6 kept with new primary paper
  PMID 26260121; Q6R5N7 and A0A0P6XBM7 withdrawn (links set to `context`).
- **Blind audit (R-V2).** New `audit_blind` / `audit_agreement` tables: exact agreement E2 39/40, E3 39/40,
  E4 22/40, all 100/120 (0.833, 95% CI 0.757-0.889). Audit frame frozen in
  `curation/v160/audit_frame_v160_pre_r2.tsv`; `tools/draw_audit_sample.py --frame` redraws the sample.
- **Family-HMM flag (R-V3).** New `novel_family_flag` column/table: 139 records flagged when a family HMM beats
  PF01036. Flag only. External set: 16/21 positives, 1/345 negatives.
- **Foldseek watchlist and clade coverage (R-C1).** New `foldseek_query` / `foldseek_hit` / `foldseek_funnel`:
  786 structure hits outside the corpus (cap reached for 9 of 10 queries); `novel_family_candidate` 181 rows.
  Clade coverage of members + candidates 85.5% confident.
- Site, exports, CLI, data dictionary and workflow updated for the new tables; Snakemake rebuild 91/91 objects
  identical.

Access and reproducibility
- New static browser (`site/`): works from `file://` and HTTP; deep links, publication display, flags, FASTA/TSV
  export, in-browser Smith-Waterman sequence search, novel-family view.
- Python API rewritten for v1.6.0 (`src/microrhododb`, read-only); `pyproject.toml` 1.6.0.
- `tools/mrdb_search.py` defaults to v1.6.0, reports the new flags and a `typeI_detected_070` column.
- Default Snakemake target rebuilds v1.6.0 from the archive and checks it is content-identical to the shipped DB;
  paths are relative. The archive now includes `pipeline/v140`, `pipeline/v160`, `releases/v1.4.0`, `src/`,
  `site/` and `tests/data`.
- `tools/draw_audit_sample.py`: re-drawable audit samples; v1.6.0 sample frozen (seed 160).
- Tests: 52 (35 for v1.6.0, 17 for v1.5.0), 0 skips. Browser walkthrough 42/42.

## [1.5.0] - 2026-10-06

Status-model, reference-tree and reproducibility overhaul in response to review of v1.4.0. 8-category
`membership_status` vocabulary (3,085 members, 1,383 candidates, 509 boundary family, 386 heliorhodopsins,
103 decoy/rejected); MR_RT_003 reference tree (472 tips, 19 named clades) with EPA-ng placements; five-level
function-evidence ladder (E1 85, E2 119, E3 1,388, E4 1,358, E5 2,516); frozen external validation set
(21 positives / 345 negatives); MGnify environmental layer moved to a separate database; Snakemake workflow
with a pinned conda environment. Release artifact `releases/v1.5.0/` (schema `v150.1`, DB SHA-256
`d715baf8...e33a`). Details: `releases/v1.5.0/RELEASE_NOTES_v1.5.0.md`. Known problems in this release are
listed in the v1.6.0 entry above.

## [1.4.0] — 2026-10-02

**Append-only sequence extension + MR_RT_002 promotion against the frozen
v1.3.0 core.** No frozen value recomputed or edited (documented exceptions:
the `reference_tree.MR_RT_002.status` lifecycle flip and `release_metadata`
identity keys). Release artifact: `releases/v1.4.0/` (SHA256SUMS, 10 files;
DB 18,759,680 B, schema `v140.1`).

- **Extension:** 105 new UniProtKB 2026_03 accessions admitted (membership /
  active_population / qc_feature / redundancy 5,361 → 5,466; protein /
  sequence_source 6,713 → 6,818). 52 high-confidence Type-I (48 `typeI_core`
  + 4 `typeI_core_architecture_supported`), 3 `typeI_candidate`, 41
  `rhodopsin_like`, 1 ambiguous, 9 rejected (helio-primary); 6
  demoted/merged accessions logged in the new `extension_delta` table (111
  rows). Nondeterministic layers (MMseqs2 clusters, HMMER QC) extended by
  assignment, never recomputed.
- **Frozen scorer reconstructed** (`pipeline/v140/`: scorer, features, tree
  modules; hashes in `build_provenance`): 0/5,361 score and category
  differences against the frozen membership rosetta — the admission gate for
  all new rows.
- **MR_RT_002 promoted** to `canonical_release`: 554 tree_node + 553
  tree_edge rows, 55 MR_CLD2_* clades (100% monophyly gate; 4 root-side
  complement clades excluded, documented), 896 reference_clade_tip rows.
- **`placement_v140`** (new table, 4,335 rows): epa-ng 0.3.8 LG+G placements
  on MR_RT_002; eligibility rule reproduces the frozen 4,326/4,326 baseline
  and covers 52/52 new core proteins (37 high-confidence). MR_RT_001-side
  placement of new cores skipped — the v1.1 185-tip MSA is unrecoverable
  (documented in `build_provenance`).
- **Validation:** `tests/release_v140.py` 18/18 PASS (35 frozen-table
  row-hash checks + extension/scorer/tree gates); P1–P9 recovery probes
  regression unchanged (7 PASS, 2 MATCH-WITH-DIFFERENCES).
- **API v1.4.0** (`src/microrhododb/api.py`): default DB → v1.4.0; new
  `query_placement_v140` / `query_extension_delta`; `query_clade_provenance`
  tree-join fix.

## [Reproducibility recovery] — 2026-09-28

**No scientific change; no release artifact touched.** Systematic recovery of
the missing build system and preserved inputs across all six project sessions.

- Recovered the **raw-input ancestor** (type1_rhodopsin_dataset session;
  5,361/5,361 sequences identical to the frozen DB) and two related precursor
  assets (rhodopsin_tool, rhodopsin_survey) into
  `data/preserved_inputs/precursor_sessions/` with SHA-256 manifests.
- Extracted surviving original logic: notebook cell dumps →
  `pipeline/legacy_notebook_code/`; transcript evidence (exact byte sizes +
  ~500-char prefixes of all 77 originally-written files, 1,144-command log) →
  `pipeline/transcript_evidence/`.
- Confirmed the v1.2/v1.3 staged builder and test suites are **unrecoverable**
  (only prefixes survive; binary workspaces lost with the original session's
  shared workspace). Full clean rebuild documented as BLOCKED.
- Ran 9 layer-by-layer reproducibility probes against the frozen releases
  (`pipeline/recovery_probes.py`): **7 PASS, 2 MATCH-WITH-DIFFERENCES**
  (MMseqs2 redundancy and HMMER QC — tool-version/order sensitivity, not
  missing scientific state). Full results and the v1.4.0-baseline verdict in
  `report_reproducibility_recovery.md`.
- Amended docs: LEGACY_AND_MISSING_COMPONENTS (recovery outcome), PROJECT_MAP,
  repository_inventory.tsv (recovered-file rows).

## [Repository reorganization] — 2026-09-27

**No scientific change.** Repository restructured for clarity; every release
artifact byte-preserved (verified by full-tree SHA-256 before/after).

- Root-level v1.0 directories (`api/ benchmark/ db/ figures/ meta/ phylogeny/
  sequences/ structures/ tables/` + report) moved to `releases/v1.0/`.
- `v1.1/`, `v1.2.0/`, `v1.3.0/` moved to `releases/`.
- `v13_pr7_pilot_analysis/` (byte-identical to v1.3.0 outputs) moved to
  `workspaces/historical/`; HPC ESMFold outputs to `workspaces/hpc/`.
- v1.3.0-era loose reports moved to `reports/`; historical notebooks to
  `notebooks/legacy_execution_trace/`.
- v1.3.0 API promoted to `src/microrhododb/` as the current development
  surface (only change: optional default DB path; release copy untouched).
- Added root README, this CHANGELOG, `pyproject.toml`, and seven documents
  under `docs/` plus a machine-readable `docs/repository_inventory.tsv`.
- Initialized version control (single baseline commit; no remote).

## [1.3.0] — 2026-09-24

Validation, provenance, and controlled-pilot release around the **frozen
v1.2.0 core** (membership byte-identical; no threshold or score changes).
Schema `v130.1`; 52/52 release tests pass.

- WS1 external validation: 106-record independent set; specificity 1.000 on
  100 negatives; E2 novel-family sensitivity 0.333 @0.86/0.90 (n=6).
- WS2 leakage benchmarks: 6 regimes, 15,110 assignments; primary
  `reference_clade_msc` sensitivity 0.891 @0.86 / 0.652 @0.90.
- WS3 tree provenance: `reference_tree`/`tree_node`/`tree_edge`/
  `reference_clade_tip`; MR_RT_001 fully auditable.
- WS4 evidence ingestion: 69 publications (all DOI/PMID), 81 assertion links.
- WS5/6 environmental pilot: `sequence_source` (6,713) +
  `environmental_admission` (1,352 MGnify: 976 marine, 376 soil), fully
  isolated from membership.
- WS7 error analysis + WS8 expansion decision memo (policy proposed, NOT applied).
- API v1.3.0: adds `query_environmental`, `query_external_validation`,
  `query_clade_provenance`.

## [1.2.0] — 2026-08-30

Data-integrity and schema-hardening release; rebuilt reproducibly by the
staged builder (`s01`–`s12`). No new biological expansion.

- **Breaking:** authoritative membership becomes `membership.membership_status`
  (legacy `module` column deprecated); 5 HSP30 records reclassified
  `decoy_or_rejected`; `exact_nr_cluster` replaced with true SHA-256 exact-NR;
  exploratory placements no longer generate active labels.
- New views (`v_typeI_active`, `v_typeI_core`, `v_typeI_candidates`,
  `v_rejected_or_decoy`, `v_active_subfamily`, `v_active_function`,
  `v_master`) and tables (`active_population`, `subfamily_assignment`,
  `function_assignment`, `protein_architecture_flag`, `publication`,
  `tier_a_assertion`, `assertion_publication`, `reference_clade_member`,
  `build_provenance`, `release_metadata`); CHECK constraints + foreign keys.
- Validation: invariants V1–V20 + API acceptance A1–A7 (33 tests).

## [1.1] — 2026-08-04

Remediation / phylogeny / benchmark extension. Supersedes v1.0 (which remains
frozen). Remediated membership workspaces (WS1/WS4), added the Type-I backbone
reference phylogeny (WS3, IQ-TREE2 Q.PFAM+F+R6), and redesigned the benchmark
with hard negatives (WS5). API v1.1.

## [1.0] — 2026-07-30

First release, built in the notebook/research-pipeline era from UniProtKB
2026_02 with Pfam PF01036.25/PF18761.8 and 15 seeds (12 Type-I + 3
heliorhodopsin). 5,361 proteins; 12 tables; 10/10 release checks pass.
