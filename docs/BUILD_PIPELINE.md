# Build Pipeline

How MicroRhodoDB releases were constructed, as far as can be documented from
the repository's surviving evidence: the v1.3.0 `build_provenance` table
(37 rows — the authoritative record), release manifests (`build_manifest_v120/
v130.json`), release notes, reports, and the historical notebooks/plan in
`notebooks/legacy_execution_trace/`.

> **Reproducibility statement (read first).** The builder source code and the
> preserved build inputs are **NOT present in this repository**. Every absent
> component is marked `MISSING FROM CURRENT REPOSITORY` below. The database
> **cannot currently be rebuilt from repository contents alone**; the frozen
> artifacts under `releases/` are authoritative. Nothing here has been
> reconstructed or reverse-engineered — this document only organizes what the
> preserved provenance records state.

## v1.0 — notebook-era build (2026-07-30)

Built interactively; the execution record survives as
`notebooks/legacy_execution_trace/rhodo.ipynb` (195 cells). Inputs: UniProtKB
2026_02, Pfam PF01036.25 / PF18761.8, 15 seeds (12 Type-I + 3 heliorhodopsin).
Output: `releases/v1.0/` (12 tables, 5,361 proteins, 10/10 release checks).
No staged builder, no checksum manifest, no `release_metadata` table.

## v1.1 — remediation build (2026-08-04)

Workspace-driven remediation (WS1/WS4 membership, WS3 backbone phylogeny via
IQ-TREE2 Q.PFAM+F+R6, WS5 benchmark redesign with hard negatives). Partial
execution record: `notebooks/legacy_execution_trace/rhodo2.ipynb`;
benchmark provenance: `releases/v1.1/meta/ws5_provenance.json`. The v1.1
workspaces (`v11_*.parquet` files referenced by v1.2.0 provenance) are
`MISSING FROM CURRENT REPOSITORY`.

## v1.2.0 — staged builder architecture (built 2026-08-30)

A reproducible 12-stage builder assembled v1.2.0 from the v1.1 workspaces.
**All stage scripts are `MISSING FROM CURRENT REPOSITORY`**; the table below
reproduces what `build_provenance` records about each.

| Stage | Script (MISSING) | Builds | Recorded algorithm / notes |
|---|---|---|---|
| s01 | `s01_protein.py` | `protein` | normalize `candidates_L1.parquet`; `tax_domain` from lineage |
| s02 | `s02_qc.py` | `qc_feature`, `protein_architecture_flag` | carry + boolean checks; split `arch_flags` on `;` |
| s03 | `s03_membership.py` | `membership` | carry (WS1/WS4 remediated); `membership_status` authoritative |
| s04 | `s04_active.py` | `active_population` | `active_policy.classify` |
| s05 | `s05_redundancy.py` | `redundancy` | exact = SHA-256(normalized seq); 90/65/40 = MMseqs2 `--min-seq-id {0.9,0.65,0.4} -c 0.8 --cov-mode 0` |
| s06 | `s06_phylogeny.py` | `reference_backbone`, `placement`, `reference_clade`, `reference_clade_member` | carry from v1.1 workspaces |
| s07 | `s07_subfamily.py` | `subfamily`, `subfamily_assignment` | active/exploratory separation: active iff primary track & `can_generate_active_label` & active protein |
| s08 | `s08_function.py` | `function`, `function_assignment` | structured evidence columns; active iff active protein & (experimental \| allowed computational) |
| s09 | `s09_structure.py` | `structure`, `pdb_structure`, `protein_pdb`, `seed`, `citation`, `predicted_structure` | carry |
| s10 | `s10_evidence_pub.py` | `tier_a_evidence`, `tier_a_holdout`, `tier_a_assertion`, `assertion_publication` | parse `evidence_ref` (doi/pmid/year) |
| s11 | `s11_benchmark.py` | `benchmark_v2` | carry (WS5) |
| s12 | `s12_provenance.py` | `release_metadata` | release metadata |

Validation at v1.2.0: invariants V1–V20 + API acceptance A1–A7 +
normalization acceptance (33 tests). Test code `MISSING FROM CURRENT
REPOSITORY`; results preserved in `releases/v1.2.0/validation/`.

## v1.3.0 — build_v13_base overlay (built 2026-08-31 … 2026-09-24)

v1.3.0 kept the v1.2.0 core byte-frozen and added new tables via a separate
`build_v13_base/` tree. **All scripts are `MISSING FROM CURRENT REPOSITORY`**;
recorded behavior:

| Script (MISSING) | Builds | Recorded algorithm / notes |
|---|---|---|
| `build_v13_base/ingest_evidence.py` | `publication`, `assertion_publication` | RCSB primary citation authoritative for PDB-anchored refs; PubMed E-utilities + CrossRef otherwise; 11 raw-only landmarks re-ingested `manual_verified`; 58 legacy flagged `parsed_heuristic`; gates G1–G4 (2026-09-02) |
| `build_v13_base/populate_external.py` | `external_validation`, `external_validation_metric` | frozen v1.2.0 evidence-vector scoring via `score_external.py` (also MISSING); exposure audit with `ever_exposed_flag`; thresholds 0.86/0.90, no retuning; Wilson CIs |
| `build_v13_base/run_holdouts.py` | `holdout_assignment` | 6 leakage-controlled regimes (random5, std_90, intermediate_65, taxonomic_phylum, reference_clade_msc, reference_clade_root); 215 eval negatives/fold; checkpoint v13_ws2 (MISSING) |
| `build_v13_base/populate_holdout.py` | `holdout_metric` | sensitivity @0.86/0.90 + specificity @0.90, fold + pooled, Wilson CIs, adequacy gates |
| `build_v13_base/build_tree_provenance.py` | `reference_tree`, `tree_node`, `tree_edge`, `reference_clade_tip` | recursive-descent Newick parse of frozen v1.1 IQ-TREE2 treefile; jplace edge numbering; GATE: 0 placement best_edges missing from `tree_edge` |
| `build_v13_base/build_sequence_source.py` | `sequence_source`, `environmental_admission` | DDL via `schema_v130_env.sql` (MISSING); deterministic UniProt backfill; PR13.6 MGnify pilot ingest (976 marine + 376 soil, permissive PF01036 retrieval) |
| `tests_release.py` (MISSING) | — | 52-test release suite; surviving output `releases/v1.3.0/validation/release_test_results.json` (52/52 PASS) |
| pilot analysis scripts (MISSING): `error_analysis.py`, `placement_pilot.py`, `make_figure.py` | `releases/v1.3.0/analysis/`, `validation/error_analysis_metrics.*`, `figures/pr13_*` | WS7 error analysis; epa-ng 0.3.8 placement of 1,352 pilot sequences onto MR_RT_001; outputs preserved |

## v1.5.0 and v1.6.0 — Snakemake rebuild (2026-10-06, 2026-10-10)

v1.6.0 is built by `pipeline/v160/build_v160.py` from the immutable v1.5.0 DB and the signed files in
`curation/v160/` (round 1 and R2 sign-off, blind-audit calls, family-flag table, Foldseek hits). `snakemake -c 4`
(see `workflow/README.md`) reruns the build, data dictionary, exports, browser data and scorer-validation
summary, then compares the rebuilt DB with the release (91/91 objects identical) and runs the v1.6.0 tests.
Literature, Foldseek and blind-audit steps were run outside the workflow; their outputs are shipped as inputs.

## Preserved inputs — status

| Input | Status |
|---|---|
| UniProtKB 2026_02 candidate extract (`candidates_L1.parquet`) | `MISSING FROM CURRENT REPOSITORY` |
| v1.1 workspaces (`v11_*.parquet`) | `MISSING FROM CURRENT REPOSITORY` |
| Checkpoint workspace `rhodo_checkpoints/` (v11/v12/v13 checkpoints, seeds, HMMs, backbone alignments) | `MISSING FROM CURRENT REPOSITORY` |
| Pfam HMMs PF01036.25 / PF18761.8 | `MISSING FROM CURRENT REPOSITORY` (publicly re-downloadable) |
| v1.1 backbone treefile + `.iqtree` | **PRESENT** in `releases/v1.0/phylogeny/` (v1.0 carried the same backbone reference files) |
| MGnify pilot raw assemblies | `MISSING FROM CURRENT REPOSITORY` (ingested output preserved in DB + `releases/v1.3.0/analysis/`) |
| ESMFold HPC outputs | **PRESENT** in `workspaces/hpc/` |

## What *can* be verified today

- `releases/v1.3.0/SHA256SUMS` — 17/17 files check out.
- SQLite `PRAGMA integrity_check` / `foreign_key_check` on all four release DBs.
- Python syntax/import of all four release API modules and `src/microrhododb`.
- Byte-identity of every release file against the pre-reorganization manifest.

What **cannot** be rerun: the v1.2.0/v1.3.0 builds themselves and their test
suites (code and inputs absent). If the original session workspace is
recovered, register it under `data/` (with hashes) and land the code in
`pipeline/` + `tests/` before attempting any rebuild.
