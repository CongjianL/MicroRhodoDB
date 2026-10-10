# MicroRhodoDB v1.5.0 — Release Report

**Document status: final (curated build).** All sections were checked against the shipped release database and build provenance. Curator spot-check sign-off: 65/65 (CongJian Li, 2026-10-06).

**Date:** 2026-10-06 · **DB:** `db/microrhododb_v1.5.0.sqlite` (sha256 `d715baf8af951cb5a78aa2f5db042c03b8fff788d2627fc6df2d97b67e88e33a`, 30,932,992 bytes) · **Base:** v1.4.0 · **Schema:** v150.1 · **Companion file:** `db/microrhododb_v1.5.0_env_pilot.sqlite` (1,400,832 bytes, supplementary, not part of the core release) · **Supersedes:** the untagged pre-curation build of 2026-10-05 (`meta/superseded_build_v150_pre_curation.json`)

## Summary

v1.5.0 is a reviewer-response release that restructures MicroRhodoDB's status model (8-category vocabulary replacing a single `active` flag), rebuilds the reference phylogeny (472-tip `MR_RT_003`, replacing the 278-tip `MR_RT_002`), externalizes the MGnify environmental layer to a supplementary database, adds a reproducible version-pinned Snakemake workflow with an archived reference package, adds structural (AlphaFold/retinal-pocket) and taxonomic (GTDB) annotation layers, formalizes classifier validation against a frozen external set, and applies a signed curator spot-check to the function-evidence layer. It is the first MicroRhodoDB release built end-to-end by a preserved, tested build pipeline rather than assembled by hand.

## Methods

### Status vocabulary (WP2)

The legacy single-status field is replaced by an 8-category vocabulary (`status_definition`), each with a `status_group` tier (`member` / `candidate` / `boundary` / `outgroup` / `rejected`) and explicit operational criteria. The 1,406 v1.4.0-era `typeI_candidate_unresolved` records were re-examined (`pipeline/v150/wp2_status.py`) and binned by missing-evidence category; 509/1,406 (36.2%) were reclassified to `boundary_family`, and the remaining 897 (63.8%) were annotated (not reclassified) via a DIAMOND/MMseqs2 homology search against full-length references. A new curated rule, `DTK_EsR_group` (84-97% identity to the E1-characterized outward pump EsR/B1YFV8), reclassifies 6 of the 10 originally-flagged v1.4.0 DTK-motif `sensory_like` records to `proton_pump`; 4 remain `sensory_like`. `membership.alias_v14` preserves the pre-v1.5.0 status string for one release.

### Reference tree MR_RT_003 and clade scheme (WP4)

A new 472-tip reference tree was built from 394 MMseqs2 60%-identity cluster representatives, 57 Tier-A/E1 characterized-protein anchors, 15 heliorhodopsin outgroup sequences, 4 curated seeds, and 2 boundary schizorhodopsins. Alignment: MAFFT L-INS-i, trimmed with ClipKIT (`kpic-gappy`, 453/773 columns retained). Model: Q.pfam+F+R9 (ModelFinder/BIC), reused unchanged for EPA-ng placement, eliminating the tree/placement model mismatch present in the legacy MR_RT_001/MR_RT_002 layers. Three independent IQ-TREE 2.3.6 ML searches (seeds 1501-1503) plus a midpoint-rerooted copy were compared against the primary clade definitions: cross-replicate Adjusted Rand Index = 0.921, median best-match Jaccard = 1.0; instability is concentrated in 7/17 level-1 clades, most at the 5-9 tip size floor, plus `MR_CLD3_017` ("Fungal rhodopsins") at the 100-tip size ceiling (Jaccard 0.52 against one replicate). Outgroup and midpoint rooting give identical clades on all three searches (MAD rooting was not performed). 17 level-1 clades plus 2 backbone groups (19 total) carry literature-anchored names; a 151-row crosswalk table links `MR_CLD3` <-> legacy `MR_CLD2` <-> MicRhoDE clusters.

### Function evidence ladder (WP5)

`function_evidence` assigns exactly one evidence tier (E1–E5) to every one of the 5,466 records: E1=85, E2=119, E3=1,388, E4=1,358, E5=2,516. A record is E1 only if it is E1-eligible: the curator decision is not `downgrade_E1`/`annotate_only`, and, where publication links exist, at least one link is active and counted as support. The evidence base has 72 publications: 69 DOI-resolved via Crossref plus 3 curator-verified replacement primary papers. A 65-row curator spot-check sheet was signed off in full; its decisions are stored in `curator_spotcheck_decision` and applied at build time. They cover 24 DTK rules, 33 publication links, 7 E1-class overrides and the D2RRQ8 conflict. Each link's state (`is_active`, `counts_as_support`, `link_role`) is recorded in `assertion_publication`, which retains the inactive links. A new function class, `photoreceptor_unassigned`, covers experimentally photoactive proteins with no demonstrated ion transport (the CryoR2-type trio). The motif+curated-rule call (`func_call`) was benchmarked against the 85 E1 records. The legacy proteorhodopsin Leu105/Gln105 spectral rule was audited (not re-run) against 72 E1-eligible literature `lambda_max_nm` values.

### External validation (WP3)

A frozen, post-cutoff external set (21 positives / 345 negatives, "freeze v2," frozen 2026-10-03, SHA-256 recorded before scoring) underlies the classifier-validation layer (`external_validation`, 366 rows; `external_validation_metric`/`operating_point`/`stratum` populated, 30/60/72 rows respectively). The production classifier (`full_gated`) is compared against its own ungated score (`full_raw`) and five simpler baselines, with six feature-ablations and a Wilson/bootstrap confidence-interval policy applied throughout.

### Environmental layer (WP7)

The 1,352 MGnify-derived records are removed from the core corpus and relocated to `microrhododb_v1.5.0_env_pilot.sqlite`, retaining PF01036-only retrieval with frozen v1.2.0-era scores and no fusion or environmental-prevalence inference.

### Reproducible workflow and reference package (WP1, WP6)

`workflow/Snakefile` (21 rules) drives the build from preserved inputs under `workflow/envs/mrdb.lock.yml` (conda-pinned: IQ-TREE 2.3.6, HMMER 3.4, MAFFT 7.526, MMseqs2 18.8cc5c, EPA-ng 0.3.8, gappa 0.9.0, ClipKIT 2.14.0, Snakemake 8.30.0; DIAMOND 2.1.10 substituted for the unavailable 2.2.8). `refpkg/MR_RT_003/` archives the full/trimmed alignments, both Pfam HMMs, all three placement-model files/logs, the rooted treefile, and the three-replicate robustness files (36 files, SHA-256 verified). The v1.4.0 membership scorer, reused unchanged for v1.5.0 feature scoring, is explicitly disclosed as reverse-engineered rather than recovered from an original implementation.

## Results

- **Corpus:** 5,466 total records (unchanged from v1.4.0): 3,085 member-tier (2,704 core + 381 architecture-supported), 1,383 candidate-tier (210 + 276 + 897 unresolved), 509 boundary, 386 heliorhodopsin outgroup, 103 rejected.
- **Named-subfamily coverage (confident clades):** members 98.0% (3,024/3,085); members + candidates 85.5% (3,821/4,468), below the ≥90% target. A further 497 in-scope records (720 corpus-wide) carry only a tentative clade from a distant, low-confidence placement (`clade_call_qc='distant_assigned'`). These are exposed as `v_master.tentative_clade_*` and are not counted. An earlier draft's 96.8% figure is retracted.
- **AlphaFold / retinal pocket:** 4,397/5,466 records (80.4%) linked to an AlphaFold DB model; 20 BR-numbered pocket positions mapped for all 5,466 records (109,320 position-level rows).
- **GTDB taxonomy:** 2,018/2,154 prokaryotic records (93.7%) map to an exact/species-level GTDB (v232) taxon.
- **Route-3 candidate-support annotation:** 267 `typeI_candidate*` records flagged (154-record strict subset), annotation-only, no `membership_status` change.
- **Post-hoc MR_RT_002-vs-MR_RT_003 placement-change analysis** (constructed for the review response, not a pipeline-native output): of 3,803 records placed on both trees with resolvable clades, 98.1% land in a clade with documented historical overlap with their former clade; a stricter single-best-match test gives 55.7%, with 81% of the strict mismatches concentrated in one legitimate consolidation (`MR_CLD3_017`, reflecting denser fungal taxon sampling in the expanded tree — corroborated by that clade's independently-observed cross-replicate instability).
- **Classifier validation (external set, n=366):** `full_gated` AUPRC = 0.9102 [95% CI 0.7955-1.0], ROC-AUC = 0.9482, clearly outperforming every baseline (best baseline `B2b_margin` = 0.5888) and the ungated score (`full_raw` = 0.7628). Specificity = 1.0 (345/345) at operating thresholds 0.70/0.86/0.90; sensitivity falls from 0.762 to 0.143 over that same threshold range. Calibration (gated vs. raw): Brier 0.0336 vs. 0.0769, ECE(10) 0.0549 vs. 0.0990. Internal hardest-regime holdout (`reference_clade_root`, entire clade withheld): AUPRC still high but sensitivity falls to 0.391 [0.264,0.535] at the 0.90 threshold. Disclosed failure mode: the `bestrhodopsin` external-positive stratum (n=4) is recalled 0/4 at every threshold tested.
- **Function evidence ladder outcomes:** E1=85, E2=119, E3=1,388, E4=1,358, E5=2,516 (pre-curation: 86/120/1,387/1,358/2,515; five records changed). Motif+override call vs. 85 E1 records: 88.2% coverage [79.7–93.5%], 84.0% precision [74.1–90.6%] (63/75). Precision is uneven by class: `motif_call` is perfect on the `sodium_pump`/`anion_pump` subsets, 0/2 and 0/1 on the very small `light_gated_channel`/`proton_pump_inward` subsets, and 0/1 assigned `photoreceptor_unassigned` for `func_call`. DTK rule fix: 6/10 originally flagged v1.4.0 DTK `sensory_like` records move to `proton_pump` (EsR-identity rule) and 4/10 remain `sensory_like`; all 24 DTK rules were curator-approved.
- **Curator spot-check outcomes (65/65 signed):** approve 45, approve with correction 10, replace link 4, drop link 2, keep unresolvable 1, downgrade E1 1, annotate conflict 1, annotate only 1. Record-level changes:
  - H2EZZ6: E1 → E3 `light_gated_channel`. Pub 15 concerns *Platymonas subcordiformis*, and no primary functional study of the *Pleodorina starrii* sequence was found.
  - D2RRQ8: E1 → E5, flagged `accession_mapping_conflict`; it stays `boundary_family`.
  - A0ABF7PQ03, A0ABF7PQ05, A0AC62AE26 (CryoR2): `proton_pump_inward` → E1 `photoreceptor_unassigned`.
  - P42196: stays E1 via a verified replacement paper (Lüttenberg et al. 1998).
- **Clade cache:** `clade.n_records_assigned` is recomputed from corpus `record_clade`, which corrects 5 level-1 and 4 level-2 counts.

## Validation

`tests/test_v150_release.py`: **17/17 PASS** against the assembled release DB (`validation/validation_v150.json`, generated from `pytest --junitxml` output by `tools/make_release_meta_v150.py`; raw output in `validation/pytest_v150_raw_output.txt`; pytest 9.1.1 from the pinned environment).

The suite has 11 original tests: `test_integrity` (incl. `PRAGMA foreign_key_check` = 0 violations), `test_corpus_counts`, `test_env_pilot_separate`, `test_one_status_per_record`, `test_member_definition`, `test_one_evidence_level`, `test_tree_and_clades`, `test_external_freeze`, `test_views`, `test_ci_method` and `test_v140_untouched` (SHA-256 re-verification of every v1.4.0 file). Six tests were added for the curated build:

- `test_spotcheck_signed_off`: 65/65 decisions present and signed
- `test_no_E1_without_support`
- `test_D2RRQ8_not_E1`
- `test_identical_sequences_consistent`
- `test_clade_cache_consistent`
- `test_tentative_clade_rules`

Checks outside the automated suite:

- Tree, placement and WP3 outputs are SHA-256-identical to the pre-curation build.
- `refpkg/MR_RT_003/SHA256SUMS` (36 files) verifies clean.
- The CLI test set reproduces the pre-curation output in every shared column.
- `snakemake -n` builds an acyclic DAG. In the archived work directory, restored mtimes would schedule `place_queries`, so the curated steps were run with explicit targets, never by re-running the tree.

CI policy: Wilson for all proportions and cluster bootstrap for AUPRC, applied without exception in the production `external_validation_metric` table. Recomputing the legacy v1.4.0 external metrics under Wilson is only partially done (sensitivity/specificity recomputed; precision/NPV keep Clopper–Pearson bounds).

## Known limitations

See `RELEASE_NOTES_v1.5.0.md` for the full list. Headline items:

- Confident named-subfamily coverage is 85.5% for members + candidates, below the 90% target. Tentative placements are shown but not counted.
- Publication verification is a 33-link spot-check, not exhaustive.
- MR_RT_003 clustering was run at 60% identity, not the planned 50%.
- GTDB v232 was used, not r220.
- 20 retinal-pocket positions, not 24.
- DIAMOND 2.1.10, not 2.2.8.
- NTQ/NDQ motif-level confusion is not quantified separately (function-class level only).

## Provenance

`build_provenance` (60 rows) records tool versions, parameters, and upstream dependencies for every build step; `meta/build_manifest_v150.json` summarizes (including full `table_counts` for all 70 tables and per-component algorithm descriptions); `meta/release_boundaries_v150.json` states scope, taxonomic breakdown, and the full known-limitations list.
