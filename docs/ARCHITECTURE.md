# MicroRhodoDB Architecture

> **v1.6.0 note (2026-10-10).** This document describes the v1.2/v1.3 layer architecture. v1.5.0 and v1.6.0 keep
> the same layers and add a re-executable v1.6.0 build (`pipeline/v160/`, `workflow/Snakefile`), a function-evidence
> layer with conflict flags, LOCO and blind-audit validation, a curated membership override for 4 E1 records, a
> family-HMM flag and a Foldseek watchlist. See `docs/DATA_MODEL.md` (v1.6.0 delta), `workflow/README.md` and
> `releases/v1.6.0/report_microrhododb_v1.6.0.md`.

Read time: ~10 minutes. This document explains how the system works as a
scientific flow, layer by layer. For where files live, see `PROJECT_MAP.md`;
for table-level detail, `DATA_MODEL.md`; for the build mechanics,
`BUILD_PIPELINE.md`.

## The system in one paragraph

MicroRhodoDB turns raw rhodopsin-like protein sequences into a **validated,
evidence-aware knowledgebase**. Sequences are acquired from UniProtKB (and, in
a controlled pilot, MGnify), quality-checked, scored for membership against
frozen thresholds, dereplicated at four redundancy levels, placed onto a
reference phylogeny, annotated with subfamily/function/structure calls that
are gated by evidence rules, linked to literature, and finally stress-tested
against benchmarks, leakage-controlled holdouts, and an independent external
set. Each release is an immutable SQLite artifact with a machine-checkable
manifest.

```text
sequence/source acquisition
 ↓
QC and feature assessment
 ↓
membership / active population
 ↓
redundancy handling
 ↓
phylogeny
 ↓
subfamily / function / structure annotation
 ↓
evidence and publication linkage
 ↓
external validation / holdout / benchmark
 ↓
release construction and validation
```

**Reading the per-layer tables below:** "Implementation" names the historical
builder script recorded in the v1.3.0 `build_provenance` table (37 rows).
Scripts marked *MISSING* are not present in this repository — see
`LEGACY_AND_MISSING_COMPONENTS.md`. "Reproducible?" means reproducible **from
current repository contents**.

---

## 1. Sequence / source acquisition

- **Purpose:** define exactly which sequences enter the system and where each
  came from (database, release, study, sample, assembly, geography).
- **Major tables:** `protein` (6,713 rows: 5,361 UniProt + 1,352 MGnify pilot),
  `sequence_source` (6,713; per-record provenance incl. biome, lat/lon,
  sequence SHA-256).
- **Implementation:** `s01_protein.py` (v1.2.0; *MISSING*) — normalized
  `candidates_L1.parquet`, derived `tax_domain` from lineage;
  `build_v13_base/build_sequence_source.py` (v1.3.0; *MISSING*) — DDL via
  `schema_v130_env.sql`, deterministic UniProt backfill + MGnify pilot ingest.
- **Inputs:** UniProtKB 2026_02 candidate set (*input file MISSING*); MGnify
  marine/soil assemblies (976 + 376 candidates; raw inputs MISSING, ingested
  output preserved in the DB and `releases/v1.3.0/analysis/`).
- **Outputs:** `protein`, `sequence_source` rows.
- **Reproducible?** No — builder code and raw inputs absent. **Frozen.**

## 2. QC and feature assessment

- **Purpose:** compute per-protein quality/architecture features that gate
  downstream decisions: HMM coverage, retinal-lysine presence, core
  completeness, architecture class and flags.
- **Major tables:** `qc_feature` (5,361), `protein_architecture_flag` (2,840).
- **Implementation:** `s02_qc.py` (v1.2.0; *MISSING*) — carried v1.1 QC with
  boolean checks; split `arch_flags` into the flag table.
- **Inputs:** `v11_qc_feature.parquet` (v1.1 workspace; MISSING); Pfam HMMs
  PF01036.25 / PF18761.8 (MISSING).
- **Outputs:** one QC row per UniProt protein; normalized architecture flags.
- **Reproducible?** No. **Frozen.**

## 3. Membership / active population

- **Purpose:** the heart of the knowledgebase — decide what *is* a Type-I
  rhodopsin. Authoritative column: `membership.membership_status` (the legacy
  `module` column is deprecated and never controls membership).
- **Major tables:** `membership` (5,361; 7 statuses: `typeI_core` 2,656,
  `typeI_core_architecture_supported` 377, `typeI_candidate` 207,
  `typeI_candidate_architecture_supported` 276,
  `typeI_candidate_unresolved` 1,365, `heliorhodopsin` 377,
  `decoy_or_rejected` 103), `active_population` (5,361 policy-classified rows;
  4,881 active).
- **Implementation:** `s03_membership.py`, `s04_active.py` (v1.2.0; *MISSING*)
  — carried the WS1/WS4-remediated v1.1 membership; `active_policy.classify`.
- **Inputs:** v1.1 membership workspace (MISSING); **frozen thresholds** —
  confirmed 0.90, high 0.86, candidate 0.70, rhodopsin-like 0.40.
- **Outputs:** membership status per protein; active/core/candidate flags.
- **Reproducible?** No. **Frozen** — membership is byte-identical between
  v1.2.0 and v1.3.0 (release test X6b) and must never change without a new
  release.

## 4. Redundancy handling

- **Purpose:** dereplicate sequences at four stringencies so statistics,
  training, and benchmarks can pick representatives or control leakage.
- **Major tables:** `redundancy` (5,361) — `exact_nr` (SHA-256 of normalized
  sequence), `std_90`, `intermediate` (65), `backbone` (40) clusters with
  representative flags.
- **Implementation:** `s05_redundancy.py` (v1.2.0; *MISSING*) — exact:
  SHA-256; 90/65/40: MMseqs2 `--min-seq-id {0.9,0.65,0.4} -c 0.8 --cov-mode 0`.
- **Inputs:** candidate sequences; MMseqs2 (external tool).
- **Outputs:** cluster IDs + representative flags per level.
- **Reproducible?** No (code absent), though the algorithm is fully specified
  in `build_provenance.params`. **Frozen.** Note: v1.1 cluster IDs were
  invalidated by the v1.2.0 exact-NR correction; IDs are not comparable
  across releases.

## 5. Phylogeny

- **Purpose:** place every protein onto a reference Type-I backbone tree and
  define named reference clades with full node/edge provenance.
- **Major tables:** `reference_backbone` (186 representatives),
  `reference_tree` (2 trees: MR_RT_001 auditable backbone, MR_RT_002
  registered orphan), `tree_node` (368), `tree_edge` (367), `placement`
  (4,326; primary + exploratory tracks with LWR), `reference_clade` (60),
  `reference_clade_member` (161 anchors), `reference_clade_tip` (986).
- **Implementation:** `s06_phylogeny.py` (v1.2.0 carry; *MISSING*);
  `build_v13_base/build_tree_provenance.py` (v1.3.0; *MISSING*) — parsed the
  frozen v1.1 IQ-TREE2 run (Q.PFAM+F+R6, 185 tips) and epa-ng jplace edge
  numbering; GATE: zero placement best_edges missing from `tree_edge`.
- **Inputs:** v1.1 backbone alignment + `backbone_iqtree.treefile` (release
  copy: `releases/v1.0/phylogeny/`; build inputs MISSING); epa-ng placements.
- **Outputs:** tree topology with supports, per-protein placements, clade
  definitions linked to nodes/edges.
- **Reproducible?** No. **Frozen.**

## 6. Subfamily / function / structure annotation

- **Purpose:** attach biological labels — but only through allowed evidence
  paths. Labels supported solely by exploratory placements are retained as
  inactive evidence (`is_active=0`), never independently active.
- **Major tables:** `subfamily` (2,990 legacy), `subfamily_assignment`
  (2,990, evidence-gated), `function` (5,361 legacy motif/spectral columns),
  `function_assignment` (4,119, rule-based with support flags),
  `structure` (4,886), `pdb_structure` (438), `protein_pdb` (472),
  `predicted_structure` (2 ESMFold models), `seed` (15).
- **Implementation:** `s07_subfamily.py`, `s08_function.py`,
  `s09_structure.py` (v1.2.0; all *MISSING*).
- **Inputs:** v1.1 annotation workspaces (MISSING); RCSB PDB; ESMFold HPC runs
  (outputs preserved in `workspaces/hpc/`).
- **Outputs:** active/inactive subfamily and function assignments; structure
  summaries and PDB links.
- **Reproducible?** No. **Frozen.**

## 7. Evidence and publication linkage

- **Purpose:** connect assertions (e.g. "pumps protons outward") to
  publications with audited identifiers; maintain the Tier-A evidence set and
  its designated holdout positives.
- **Major tables:** `tier_a_evidence` (63), `tier_a_assertion` (63),
  `tier_a_holdout` (34), `publication` (69, all DOI/PMID-resolved),
  `assertion_publication` (81), `citation` (10, legacy).
- **Implementation:** `s10_evidence_pub.py` (v1.2.0; *MISSING*);
  `build_v13_base/ingest_evidence.py` (v1.3.0; *MISSING*) — RCSB primary
  citations authoritative for PDB-anchored refs; PubMed/CrossRef otherwise;
  11 raw-only landmarks re-ingested as `manual_verified`, 58 legacy
  regex-parsed flagged `parsed_heuristic`; gates G1–G4.
- **Inputs:** RCSB PDB API, NCBI E-utilities, CrossRef (queried 2026-09-02).
- **Outputs:** publication records and assertion–publication links.
- **Reproducible?** Partially re-derivable from public APIs, but the build
  code is absent → treated as not reproducible from repo. **Frozen.**

## 8. External validation / holdout / benchmark

- **Purpose:** quantify how well the frozen classifier generalizes — without
  ever retuning it. All scoring uses frozen v1.2.0 evidence vectors and
  thresholds (0.86/0.90).
- **Major tables:** `benchmark_v2` (261; WS5 redesign with hard negatives),
  `external_validation` (106 records, `ever_exposed_flag=0`),
  `external_validation_metric` (18), `holdout_assignment` (15,110),
  `holdout_metric` (264).
- **Implementation:** `s11_benchmark.py` (v1.2.0; *MISSING*);
  `build_v13_base/populate_external.py`, `run_holdouts.py`,
  `populate_holdout.py`, `score_external.py` (v1.3.0; all *MISSING*).
- **Inputs:** E1 temporal positives, E2 DOI-verified novel-family positives,
  100 independent negatives; tier-A holdout positives; 215 eval
  negatives/fold; checkpoint v13_ws2 (MISSING).
- **Outputs:** specificity 1.000 on external negatives; primary holdout
  regime `reference_clade_msc` sensitivity 0.891 @0.86 / 0.652 @0.90;
  specificity @0.90 = 1.000 in all regimes.
- **Reproducible?** No. **Frozen.**

## 9. Release construction and validation

- **Purpose:** assemble the immutable release artifact and prove its
  invariants before shipping.
- **Major tables:** `release_metadata` (10 keys), `build_provenance`
  (37 rows — the authoritative record of every builder script, its inputs,
  algorithm, and parameters).
- **Implementation:** `s12_provenance.py` (v1.2.0; *MISSING*); v1.3.0 release
  suite `tests_release.py` (52 tests; *MISSING* — its output survives as
  `releases/v1.3.0/validation/release_test_results.json`).
- **Inputs:** all upstream tables; release boundaries and manifests.
- **Outputs:** `releases/v1.3.0/` — DB + schema + API + figures + analysis +
  validation + `SHA256SUMS` (17 files).
- **Reproducible?** The *checks* that remain runnable (SHA256SUMS, SQLite
  integrity/foreign-key) pass; the full suite cannot be rerun (code absent).
  **Frozen.**

---

## What is active vs frozen

| Surface | Status |
|---|---|
| `releases/v1.0`–`v1.3.0` | **Frozen forever** — immutable artifacts |
| `src/microrhododb/` query API | **Active** — the only maintained code surface |
| Build pipeline (layers 1–9) | **Frozen + missing** — documented, not reproducible from repo |
| Environmental pilot / expansion policy | **Proposed, NOT applied** — see `reports/report_expansion_decision_memo.md`; any expansion is a future release |
