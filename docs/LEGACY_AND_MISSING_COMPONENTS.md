# Legacy and Missing Components

> **v1.6.0 note (2026-10-10).** The missing components below concern v1.0-v1.4.0 builds and still apply to them.
> v1.6.0 itself is rebuilt from the shipped v1.5.0 DB and signed curation by `snakemake -c 4` (91/91 objects
> identical). Steps run outside the workflow (literature sweep, novel-family search, blind audit, Foldseek queries)
> are shipped as records and build inputs; see `workflow/README.md`.

This document is the authoritative record of what the current repository
**does not contain**, and of legacy elements retained for audit. Nothing
listed as missing has been reconstructed, reverse-engineered, or fabricated.
Status vocabulary matches `docs/repository_inventory.tsv`.

## 1. Missing build/pipeline source code — `MISSING FROM CURRENT REPOSITORY`

The v1.2.0 staged builder and v1.3.0 overlay were developed in a session
workspace that is not part of this repository snapshot. Their existence,
roles, and parameters are authoritatively recorded in the v1.3.0 database
table `build_provenance` (37 rows) and summarized in `docs/BUILD_PIPELINE.md`.

| Component | Recorded role | Evidence it existed |
|---|---|---|
| `s01_protein.py` … `s12_provenance.py` | v1.2.0 12-stage builder | `build_provenance` rows (release=1.2.0, built 2026-08-30) |
| `build_v13_base/ingest_evidence.py` | v1.3.0 WS4 publication ingestion | `build_provenance` (2026-09-02) |
| `build_v13_base/populate_external.py` | v1.3.0 WS1 external validation | `build_provenance` |
| `build_v13_base/score_external.py` | frozen evidence-vector scorer | referenced in `populate_external` params |
| `build_v13_base/run_holdouts.py` | v1.3.0 WS2 holdout regimes | `build_provenance` |
| `build_v13_base/populate_holdout.py` | v1.3.0 WS2 metrics | `build_provenance` |
| `build_v13_base/build_tree_provenance.py` | v1.3.0 WS3 tree tables | `build_provenance` |
| `build_v13_base/build_sequence_source.py` | v1.3.0 WS5/6 source + admission | `build_provenance` |
| `build_v13_base/tests_release.py` | 52-test release suite | `releases/v1.3.0/validation/release_test_results.json` (52/52 PASS) |
| `error_analysis.py`, `placement_pilot.py`, `make_figure.py` | v1.3.0 WS7 pilot analysis/figure | outputs in `releases/v1.3.0/analysis/`, `validation/`, `figures/` |
| `schema_v130_env.sql` | v1.3.0 environmental DDL | referenced in `build_provenance` params |

**Consequence:** the database cannot be rebuilt from repository contents
alone. If these files are recovered (e.g. from the original build session),
land them in `pipeline/` (builders) and `tests/` (release suite) and register
hashes in `docs/repository_inventory.tsv`.

## 2. Missing preserved inputs — `MISSING FROM CURRENT REPOSITORY`

| Input | Notes |
|---|---|
| Checkpoint workspace `rhodo_checkpoints/` | v11/v12/v13 checkpoints, seed alignments (12 Type-I + 3 helio), Pfam HMMs (PF01036.25/PF18761.8), backbone alignments. Lived in a session shared-workspace not carried into this snapshot. |
| `candidates_L1.parquet` | UniProtKB 2026_02 candidate extract (v1.2.0 stage s01 input). |
| v1.1 workspaces (`v11_*.parquet`) | v1.2.0 builder inputs (membership, QC, phylogeny, subfamily, function, structure, evidence, benchmark carries). |
| MGnify pilot raw assemblies | 976 marine + 376 soil candidates; ingested output preserved in DB + `releases/v1.3.0/analysis/`. |
| v1.3.0 holdout checkpoint `v13_ws2` | referenced by `run_holdouts.py` provenance. |

## 3. Legacy / deprecated elements retained for audit (present, frozen)

| Element | Status | Note |
|---|---|---|
| `membership.module` column | deprecated since v1.2.0 | never controls membership; retained for backward compatibility |
| `subfamily`, `function` tables | legacy (v1.1 carry) | superseded by `subfamily_assignment` / `function_assignment` |
| `citation` table | legacy | superseded by `publication` + `assertion_publication` |
| v1.1 redundancy cluster IDs | invalidated | replaced by true exact-NR in v1.2.0; not comparable across releases |
| `reference_tree` MR_RT_002 | **promoted in v1.4.0** | `registered_orphan` through v1.3.0; v1.4.0 stored 554 nodes / 553 edges / 55 clades and flipped status to `canonical_release` |
| `publication.ingestion='parsed_heuristic'` (58 rows) | legacy parsing flag | 11 landmark refs re-ingested as `manual_verified` in v1.3.0 |

## 4. Legacy release limitations (documented, not fixed — releases are immutable)

- **v1.0:** no `release_metadata` table; no checksum manifest; flat
  type-organized layout; `module='type_I'` filtering could surface HSP30
  decoys as Type-I (corrected in v1.2.0).
- **v1.1 / v1.2.0:** no SHA256SUMS manifest (validation JSONs only).
  Checksums for these releases exist only as the reorganization baseline
  manifest (see the final reorganization report), not as release artifacts.
- **v1.3.0 known limitations** (carried from release notes): environmental
  fusion not assessable (PF01036-only retrieval); prevalence not estimable;
  soil yield is a source property; epa-ng 0.3.8 used uniform FreeRate
  weights; E2 external positives few (n=6); MR_CLD_026 taxonomically mixed.

## 5. Recovery outcome (2026-09-28 reproducibility recovery)

A systematic recovery sweep was performed across all six project sessions, HPC
history, and both session workspaces. Results:

**Recovered and organized** (hashes in `data/preserved_inputs/recovery_manifest.tsv`):

- The **raw-input ancestor**: `type1_rhodopsin_dataset/rhodopsin_sequences.fasta`
  is 5,361/5,361 sequence-identical to the frozen v1.3.0 UniProt proteins →
  `data/preserved_inputs/precursor_sessions/sess_a09c9ba0dda8_type1_rhodopsin_dataset/`.
- **Notebook code** (largest surviving original logic): v1.0-era pipeline
  (195 cells) and v1.3-era PR13.4–PR13.9 logic (18 cells) → extracted
  unmodified to `pipeline/legacy_notebook_code/`.
- **Transcript evidence**: exact byte sizes and ~500-char prefixes for all 77
  files the original session wrote (incl. every lost builder script), 15
  heredoc-created files, 71 edit events, 1,144 executed commands →
  `pipeline/transcript_evidence/`.
- **Related precursor assets**: rhodopsin_tool (8 scripts + PF01036 HMM) and
  rhodopsin_survey (10 curated datasets) → `data/preserved_inputs/precursor_sessions/`.

**Confirmed unrecoverable** (searched: all session result dirs, all session
execution traces incl. full transcript parse, HPC job history, current and
original session shared-workspaces): the v1.2 staged builder bodies
(`s01`–`s12`, `build_v120.py`, `manifest.py`, `active_policy.py`,
`run_tests.py`), the v1.3 `build_v13_base/*` bodies (incl. `tests_release.py`,
`tests_env.py`, `holdout_engine.py`, `score_external.py`), all binary
workspaces (`v11_*.parquet`, `rhodo_checkpoints/`, `v13_ws2`), the
`candidates_L1.parquet` binary, and MGnify pilot raw assemblies. The original
session's transcript truncates all tool-call arguments at ~624 characters, so
file bodies written to the lost `/workspace` are unrecoverable from it.

**Consequence:** a literal clean rebuild of v1.3.0 with the original code is
impossible. Layer-by-layer reproducibility probes were run instead
(`pipeline/recovery_probes.py`; full detail in
`report_reproducibility_recovery.md`):

- **PASS (exact re-derivation):** P1 raw input (5,361/5,361 sequences
  identical), P2 membership carry (v1.3.0 == v1.2.0, active population
  derivable), P3 exact-NR (SHA-256 rule + representative rule reproduce all
  cluster IDs and flags), P5 tree provenance (MR_RT_001 topology internally
  consistent: 368 nodes/367 edges, all 60 clades monophyletic and node-anchored;
  preserved treefile verified as the documented orphan MR_RT_002 by md5),
  P6 external validation (18/18 metrics + Clopper-Pearson CIs exact),
  P7 holdout (264/264 metrics exact: 138 fold-level + 126 pooled; pooled rule =
  held-out fold score for positives, full-model score for negatives),
  P9 environmental (501/851 split, admission rule from frozen scores exact,
  complete membership/active isolation, sequence_source SHA-256 backfill
  6,713/6,713).
- **MATCH-WITH-DIFFERENCES (documented causes, no missing scientific state):**
  P4 MMseqs2 90/65/40 clustering (partitions 98–99% pure, ARI 0.80–0.98;
  original MMseqs2 version and input order unrecorded, representative
  re-ranking rule only partially preserved) and P8 QC hmmsearch (PF01036.25
  HMM confirmed; hmm_cov = aligned HMM length/224 reproduced exactly for 92.4%
  of proteins, complete_core = hmm_cov ≥ 0.6 exact for 5,361/5,361; residual
  differences attributable to HMMER 3.3→3.4 domain-resolution drift).
- **Remaining partial specification:** the holdout `adequate` QC flag (a
  per-fold annotation, not a metric) is not fully determined by frozen data.

## 6. Historical execution records (present as copies)

| Record | Location | Nature |
|---|---|---|
| `rhodo.ipynb` (195 cells) | `notebooks/legacy_execution_trace/` | v1.0-era build notebook — historical evidence, **not** the canonical implementation |
| `rhodo2.ipynb` (18 cells) | `notebooks/legacy_execution_trace/` | v1.1/v1.3-era notebook — historical evidence |
| `PLAN_v130_historical.md` | `notebooks/legacy_execution_trace/` | approved v1.3.0 build plan |

These records may reference paths (e.g. session workspace locations) that no
longer exist. They are preserved unmodified as historical evidence; old paths
are documented here rather than rewritten in the notebooks.

## 7. v1.4.0 reconstructions (2026-10-02)

Two gaps recorded above were closed by **reconstruction** (not recovery) in
the v1.4.0 build:

- **Frozen membership scorer — gap RETIRED.** Reconstructed as
  `pipeline/v140/scorer_v140.py` + `features_v140.py` + `tree_v140.py`
  (SHA-256 of each module recorded in `build_provenance`). Admission gate:
  0/5,361 score and category differences against the frozen membership
  rosetta; 5,360/5,361 reproduced end-to-end from raw inputs (one documented
  exception).
- **MR_RT_002 orphan status — RESOLVED.** Promoted to `canonical_release`
  (section 3); full node/edge/clade content now stored and gated (100%
  clade monophyly).

Still missing after v1.4.0: the original v1.2/v1.3 builder bodies (section 1),
the preserved build inputs (section 2), and specifically **MR_RT_001's own
treefile and the v1.1 185-tip backbone MSA** (99/185 tips absent from the
surviving 278-tip alignment). MR_RT_001-side placement of new sequences
therefore remains impossible and was skipped in v1.4.0 (documented in
`build_provenance`).
