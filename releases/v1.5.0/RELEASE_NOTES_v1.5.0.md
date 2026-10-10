# MicroRhodoDB v1.5.0 — Release Notes

**Document status: final (curated build).** All sections were checked against the shipped release database and build provenance. The 65-row curator spot-check sheet is signed off in full (65/65, CongJian Li, 2026-10-06), and the release was rebuilt with the signed decisions applied.

**Release date:** 2026-10-06 · **Base:** v1.4.0 (`release_metadata.base_release`, release='1.5.0') · **Schema:** v150.1 (`release_metadata.schema_revision`) · **Validation:** 17/17 release tests pass on the shipped artifact (`validation/validation_v150.json`) · **DB SHA-256:** `d715baf8af951cb5a78aa2f5db042c03b8fff788d2627fc6df2d97b67e88e33a`

A pre-curation build of v1.5.0 (DB SHA-256 `1e8160df…0eab`) was assembled on 2026-10-05 but never tagged or published. It is superseded by this build; see `meta/superseded_build_v150_pre_curation.json`. The tree, the placements and the WP3 validation outputs are byte-identical between the two builds.

## What v1.5.0 is

A **status-model, phylogenetic-framework, and reproducibility overhaul**, built in response to peer review of the v1.4.0 preprint/submission. Unlike v1.4.0 (a strict append-only extension of v1.3.0), v1.5.0 restructures core semantics: the single legacy `active` status field is replaced by an 8-category vocabulary, 17 pre-existing tables are renamed with a `legacy_` prefix and retained behind compatibility views, and the reference tree is rebuilt from 278 to 472 tips. The full build is reproducible from preserved inputs via a version-pinned Snakemake workflow (21 rules, conda-locked tool versions) — the first MicroRhodoDB release built this way end-to-end.

## What is new

| Component | Content | Key result |
|---|---|---|
| Status vocabulary | `status_definition` (8 rows), `membership.membership_status` | 2,704 `typeI_member_core` + 381 `typeI_member_architecture_supported` + 210 `typeI_candidate` + 276 `typeI_candidate_architecture_supported` + 897 `typeI_candidate_unresolved` + 509 `boundary_family` + 386 `heliorhodopsin` (outgroup) + 103 `decoy_or_rejected` = 5,466. `alias_v14` preserves the old status string for one release (removal scheduled v1.6.0) |
| 1,406-candidate resolution | `pipeline/v150/wp2_status.py` | 509/1,406 (36.2%) reclassified `typeI_candidate_unresolved` → `boundary_family` (non-K at retinal match state 210, full TM7 coverage); 897/1,406 (63.8%) remain unresolved, annotated (not reclassified) via sequence-homology search |
| Reference tree MR_RT_003 | `reference_tree`, `tree_node`/`tree_edge`, `refpkg/MR_RT_003/` | 472 tips (394 MMseqs2 cl0.6 representatives + 57 Tier-A/E1 anchors + 15 heliorhodopsin outgroup + 4 seeds + 2 boundary schizorhodopsins); Q.pfam+F+R9 (ModelFinder/BIC), reused for EPA-ng placement (fixes the v1-era tree/placement model mismatch); 19 named clades (17 level-1 + 2 backbone); cross-replicate ARI = 0.921 across 3 independent searches |
| Crosswalk | `clade_crosswalk` (151 rows) | Links `MR_CLD3` ↔ legacy `MR_CLD2` ↔ MicRhoDE clusters with shared-record counts in both directions |
| Function evidence ladder | `function_evidence` (5,466 rows, one per record), `func_class_definition` | E1=85, E2=119, E3=1,388, E4=1,358, E5=2,516 (sum 5,466). E1 requires curator eligibility and ≥1 active supporting link when links exist. Motif+override call vs. 85 E1 records: 88.2% coverage, 84.0% precision (63/75). New class `photoreceptor_unassigned` (CryoR2-type: photoactive, no demonstrated transport). 72 publications (69 Crossref-resolved + 3 curator-verified replacements) |
| Curator spot-check sign-off | `curator_spotcheck_decision` (65 rows), `assertion_publication` link state columns | 65/65 signed: approve 45, approve with correction 10, replace link 4, drop link 2, keep unresolvable 1, downgrade E1 1, annotate conflict 1, annotate only 1. All 24 DTK rules approved. H2EZZ6 E1→E3; D2RRQ8 E1→E5 (accession-mapping conflict flag); CryoR2 trio → `photoreceptor_unassigned` |
| Tentative clade layer | `v_master.tentative_clade_id`/`tentative_clade_name` | 720 records (497 members+candidates) whose only clade call is a distant, low-confidence placement; shown separately in the browser/CLI and not counted in coverage |
| External validation | `external_validation` (366 rows), `external_validation_metric`/`operating_point`/`stratum` | Frozen post-cutoff set, 21 positives / 345 negatives (SHA256-frozen pre-scoring). `full_gated` external AUPRC = 0.9102 [0.7955,1.0], best baseline (`B2b_margin`) = 0.5888. Specificity 1.0 at all thresholds; sensitivity 0.762→0.143 over thresholds 0.70→0.90. Notable gap: `bestrhodopsin` stratum (n=4) recalled 0/4 at every threshold |
| Environmental layer | `microrhododb_v1.5.0_env_pilot.sqlite` (supplementary, not in the core release DB) | 1,352 MGnify-derived records demoted out of the core corpus; frozen v1.2.0-era scores, PF01036-only, no fusion/prevalence inference |
| Xenorhodopsin addition | 2 new UniProt accessions (A0AA82WPB4, A0AA82WP37), clade `MR_CLD3_009` | Motivated by the MicRhoDE-gap finding (Comment 1 of the review response): 86.1% of eukaryotic records and a 3-record xenorhodopsin lineage were MicRhoDE-unrepresented |
| AlphaFold / retinal pocket | `afdb_model` (4,397/5,466 records, 80.4%, linked), `retinal_pocket`/`retinal_pocket_summary` (109,320 position-level rows) | 20 BR-numbered pocket positions (19 within-4.5 Å contacts of retinal in PDB 1C3W + Asp85) mapped for all 5,466 records via MSA/HMM match-state mapping |
| GTDB taxonomy | `gtdb_taxonomy` (2,154 rows) | GTDB release v232 (dynamic "latest" at fetch time); 2,018/2,154 (93.7%) prokaryotic records map to an exact/species-level taxon |
| Route-3 candidate support | `route3_candidate_support` (267 rows; 154-row strict subset) | Annotation-only layer for `typeI_candidate*` records with retinal K at match state 210 and a QC-passing MR_RT_003 placement; does not alter `membership_status` |
| Reference package | `refpkg/MR_RT_003/` (36 files, SHA256-verified) | README, full/trimmed alignments, both Pfam HMMs, all 3 placement-model files/logs, rooted treefile, 3-replicate robustness files |
| Workflow | `workflow/Snakefile` (21 rules), `workflow/envs/mrdb.lock.yml` | Conda-pinned: IQ-TREE 2.3.6, HMMER 3.4, MAFFT 7.526, MMseqs2 18.8cc5c, EPA-ng 0.3.8, gappa 0.9.0, ClipKIT 2.14.0, Snakemake 8.30.0. DIAMOND pinned to 2.1.10 (2.2.8, used for the original v1.4.0 scorer, is unavailable on bioconda) |
| Browser / CLI | `tools/build_browser.py`, `tools/mrdb_search.py` | Static HTML/JS browser and DIAMOND-based CLI search tool, both regenerated from the curated build; distant placements shown as "distant placement, low confidence" (opt-in in the clade filter) |

## API

No new v1.5.0-specific API module was added. `releases/v1.4.0/meta/microrhododb_api_v14.py` remains valid for the renamed `legacy_*_v14` tables it was written against; it does not expose the new v1.5.0 tables (`status_definition`, `clade`, `placement`, `function_evidence`, etc.) or the `v_master` convenience view.

## Known limitations (carried + new)

- **Named-subfamily coverage below target for candidates.** Confident clade coverage is 98.0% for members (3,024/3,085) but 85.5% for members + candidates (3,821/4,468), short of the ≥90% target. A further 497 in-scope records carry only a tentative (distant, low-confidence) clade, which is not counted. An earlier draft's figure of 96.8% (COALESCE with placements) and its claim that 727 records were wrongly unassigned in the browser/CLI are **retracted**. Those placements are QC-flagged `distant_assigned`, and `record_clade` correctly withholds a confident clade.
- **Clade cache recount.** `clade.n_records_assigned` is now recomputed from corpus `record_clade`. Pre-curation cached counts also included non-corpus placements and differed for 5 level-1 clades.
- **Publication verification is a spot-check.** 33 publication links were curator-reviewed. This is a representative sample, not an exhaustive re-verification. 41 E1 records rest on UniProt/λmax experimental tables without a linked publication.
- **CryoR2 benchmark cost.** The 3 `photoreceptor_unassigned` records are kept in the motif benchmark. `func_call` assigns one of them a pump call, which is scored as incorrect.
- **MR_RT_003 clustering used 60% MMseqs2 identity**, not the 50% originally specified.
- **1,406-candidate resolution** used HMM-alignment retinal-site/TM7-coverage criteria plus a sequence-homology search, not the originally specified "MR_RT_003 placement plus AlphaFold-model architecture."
- **Rooting sensitivity** was checked outgroup-vs-midpoint only (identical clades on all 3 replicate searches); MAD (minimal ancestor deviation) rooting was not performed.
- **Retinal-pocket positions:** 20 implemented (19 within-4.5 Å contacts + Asp85), not the 24 originally specified.
- **GTDB release:** v232 used (the fetch script tracks GTDB's dynamic "latest" URL), not the originally specified r220; recommend pinning the GTDB version in a future build.
- **DIAMOND version:** 2.1.10, not 2.2.8 (used for the original, reverse-engineered v1.4.0 scorer); 2.2.8 is unavailable on bioconda for this release. Not guaranteed bit-identical to 2.2.8 output.
- **Placement-change comparison vs. the predecessor tree:** not a pipeline-native output; constructed post hoc for the review response from frozen tables (`legacy_placement_rt002`, `placement`, `clade_crosswalk`) rather than recomputed. 98.1% of dually-placed records land in a clade with documented historical overlap with their former clade; a stricter single-best-match test gives 55.7%, driven 81% by one legitimate consolidation (`MR_CLD3_017`, reflecting denser fungal taxon sampling). Note also that `MR_RT_002` itself was never the actual shipped v1.4.0 production tree (`reference_tree.note`: "built during v1.2 development but never wired into the release DB"); `MR_RT_001` underlies all shipped releases through v1.4.0.
- **Scorer provenance:** the v1.4.0 scorer (reused unchanged for v1.5.0 feature scoring) was reverse-engineered, not recovered from an original implementation. Its 0/5,361-difference reproduction demonstrates output stability, not that the reconstructed code is the original method.
- New accessions (the 2 xenorhodopsin additions) carry seed-homology and literature-exemplar evidence; no new wet-lab spectral curation was performed for this release.
- GitHub repository and Zenodo bundle are prepared but not yet published (see Integrity).

## Integrity

SHA-256 checksums in `SHA256SUMS` (all release files); full test detail in `validation/validation_v150.json` (17/17 PASS; generated by `tools/make_release_meta_v150.py` from `pytest --junitxml` output) and raw output in `validation/pytest_v150_raw_output.txt`; per-table build provenance (tool versions, parameters, upstream dependencies) in the DB table `build_provenance` (60 rows) and `meta/build_manifest_v150.json`; scope and known-limitations detail in `meta/release_boundaries_v150.json`. Signed curation inputs are in `curation/` (decisions, signed sheet, publication/link replacements, field corrections). A GitHub repository will be created privately and made public at submission; a Zenodo-ready bundle (CC BY 4.0) will be generated from this assembled release directory for upload once finalized.
