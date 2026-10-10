# MicroRhodoDB v1.4.0 — Release Report

**Date:** 2026-10-02 · **DB:** `db/microrhododb_v1.4.0.sqlite` (sha256 `21342d94b207b6e0b9e8f313d3689ea962fc59c89503c287ee59de46061f6854`) · **Schema:** v140.1 · **Base:** v1.3.0 (immutable)

## Summary

v1.4.0 extends the frozen v1.3.0 knowledgebase append-only with the UniProtKB 2026_03 delta (105 new accessions) and promotes the 278-tip reference tree MR_RT_002 to canonical, with a full re-placement of the eligible population. The headline enabling result is the **exact reconstruction of the frozen v1.2 membership scorer** — previously the largest documented reproducibility gap — verified at 0/5,361 score and category differences against the frozen database.

## Methods

### Append-only contract
All v1.3.0 content rows are carried byte-identical (verified by row-hash over 35 frozen table/key sets, `tests/release_v140.py` F-series). New content lands in new rows (extended tables) or new tables (`extension_delta`, `placement_v140`, `qc_feature_tool`). Documented exceptions: the `reference_tree.MR_RT_002.status` lifecycle transition (`orphaned_candidate` → `canonical_release`, gated) and release-identity keys in `release_metadata` (the same convention v1.3.0 used).

### Scorer reconstruction (the rosetta gate)
`releases/v1.0/tables/membership_assignments.tsv` (5,361 rows × 37 columns) carries raw features, evidence axes, gates, and frozen scores. The scorer was reverse-engineered and locked in `pipeline/v140/scorer_v140.py`:
- evidence axes: `e_domain=expit((dom_score−40)/15)`, `e_coverage=hmm_cov`, `e_retinal=lysine 0/1`, `e_margin=expit((PF01036−PF18761)/40)`, `e_homology=seed_best_id×seed_best_cov`, `e_topology=expit((kd_max−1.6)/0.4)`; weights 0.28/0.20/0.25/0.15/0.10/0.02; `membership_score=round(Σ wᵢeᵢ, 4)`; categories from the **unrounded** score (thresholds 0.86/0.70/0.40 with lysine/completeness/margin gates).
- Gate A (rosetta features → scorer → frozen DB): **0/5,361 score diffs, 0/5,361 category diffs**.
- Gate B (end-to-end from raw sequence, `features_v140.py`): 5,360/5,361 scores exact (single +0.0002 DIAMOND bitscore tie, category unaffected); 5,361/5,361 categories exact. Feature conventions verified exactly: pyhmmer default-pipeline domain calls; `hmm_cov` = union of ≥2-bit domain alignment columns over model length; retinal lysine via HMMER 3.4 CLI `hmmalign` at match-state 210 (PF01036) / 230 (PF18761); DIAMOND seed homology (max bitscore, 15 seeds); KD w=19; architecture rules (fusion > truncated > extended > single; extension threshold 60 aa).

### Extension admission
UniProtKB 2026_03 delta (harvested 2026-10-01 via `xref:pfam-PF01036` / `PF18761`): 111 delta rows — 105 new accessions, 6 demoted/merged (logged in `extension_delta`, frozen rows untouched). New sequences were clustered by assignment (exact-NR `EXNR_<sha256[:16]>`; MMseqs2 18.8cc5c search against frozen clusters; new-cluster namespace `V140_<acc>`), QC'd with the pinned feature pipeline, and scored with the frozen scorer. Outcome: 52 high_confidence_type_I, 2 putative_type_I, 41 rhodopsin_like, 1 ambiguous, 9 rejected (all heliorhodopsin-primary). Statuses: 48 typeI_core, 4 typeI_core_architecture_supported, 3 typeI_candidate, 41 typeI_candidate_unresolved, 9 heliorhodopsin.

### MR_RT_002 promotion
The 278-tip IQ-TREE2 backbone (Q.PFAM+F+R6, logL −101,143.4561) was parsed as-parsed (trifurcating root; 554 nodes/553 edges) and stored under the exact MR_RT_001 conventions — reverse-engineered from the frozen rows and verified: DFS-preorder `T###`/`N###` counters, `E###` assigned at parent visit, `branch_length` = incoming edge, `sh_alrt/ufboot` labels. Clades were enumerated on a midpoint-rooted copy with the v1 algorithm (level-order, 3–60 tips, pre-dedup ids, dedup on `(n_tips, n_tierA_anchors)`), using tier-A accessions present among the 278 tips (17; the v1 anchor set is 24 holdout representatives of which only 6 are in this tree). 59 enumerated → 55 stored; the 4 excluded clades (`MR_CLD2_018/027/040/057`) are nested root-side complements of the midpoint rooting (51/40/38/8 tips, containing the two singleton root-adjacent tips) — monophyletic in the unrooted topology but not representable as descendant sets in the as-parsed storage orientation. Gates: 55/55 stored clades are exact descendant sets (100% monophyly), edge links = incoming edges, parentage = smallest containing clade.

### placement_v140
Eligibility rule recovered exactly from the frozen layer (active status ∧ `complete_core` ∧ not a reference tip; reproduces the frozen 4,326/4,326). Queries aligned to the 219-column reference MSA via `hmmbuild --symfrac 0` + `hmmalign` (insert columns stripped); EPA-ng 0.3.8 `--redo -m LG+G` (libpll lacks Q.PFAM; v1-era convention for this tree). jplace edge numbers mapped to `tree_edge.edge_id` by below-set equality (553/553). Derived columns follow the frozen conventions: `dispersion = 1 − best_lwr`; status thresholds 0.90/0.50; `clade_id` = smallest clade containing the best edge's below-set. `n_credible` = #edges with LWR ≥ 0.05 (v1.4.0 convention; frozen rule unrecoverable).

## Results

- **Coverage gate:** 4,335/4,335 eligible placed = 100% (baseline v1.3.0: 4,326/4,326 = 100%) — PASS.
- Placement quality: 3,375 high-confidence (77.9%), 839 clade-compatible, 121 ambiguous; 57/4,335 (1.3%) outside all clades (frozen baseline 1.0%). All 52 new core sequences placed and clade-assigned (37 high-confidence).
- Cross-tree concordance over 4,142 shared queries: median best-LWR 1.0 on both trees; 83/3,485 (2.4%) of MR_RT_001-high-confidence queries are ambiguous on the expanded tree.
- Active population: 4,977 active members (3,085 core, 1,892 candidates), up from 4,881.

## Validation

- `tests/release_v140.py`: **18/18 PASS** on the shipped artifact (`validation/validation_v140.json`) — frozen-layer row-hashes (35/35), extension invariants, scorer gates, MR_RT_002 gates, placement integrity.
- Recovery probes P1–P9 regression (`validation/recovery_probes_v140.txt`): 7 PASS + 2 documented MATCH-WITH-DIFFERENCES (P4 MMseqs2, P8 HMMER version drift) — identical to the 2026-09-28 verdicts. One latent probe bug fixed (P2 active-population comparison; fix validated against the Task-2 recorded numbers 4,881/3,033/1,848).

## Known limitations

See `RELEASE_NOTES_v1.4.0.md` (carried + new). Notable: MR_RT_001-side placement of new sequences not produced (v1.1 reference MSA does not survive); placement model is LG+G, not the tree's Q.PFAM+F+R6.

## Provenance

`build_provenance` (49 rows) records tool versions, input ordering, and code sha256 for every build step; `meta/build_manifest_v140.json` summarizes; `meta/release_boundaries_v140.json` states scope and the append-only contract.
