# MicroRhodoDB v1.4.0 — Release Notes

**Release date:** 2026-10-02 · **Base:** v1.3.0 (immutable) · **Schema:** v140.1 · **Validation:** 18/18 release tests pass on the shipped artifact; recovery probes P1–P9 regression matches the 2026-09-28 verdicts (7 PASS, 2 documented MATCH-WITH-DIFFERENCES)

## What v1.4.0 is

A **sequence-extension and tree-promotion release** on the frozen v1.3.0 core. Every v1.3.0 content row is carried byte-identical (35/35 frozen table row-hashes verified by `tests/release_v140.py` F-series). The only edited values are the `reference_tree.MR_RT_002.status` lifecycle transition and the three release-identity keys in `release_metadata` — both documented append-only exceptions.

## What is new

| Component | Content | Key result |
|---|---|---|
| UniProtKB 2026_03 delta | `extension_delta` (111 rows) + 105 new rows in `protein`/`sequence_source`/`redundancy`/`qc_feature`/`membership`/`active_population` | 105 new accessions (96 PF01036-primary, 9 PF18761-primary); 6 demoted/merged logged only. New membership: 52 high_confidence_type_I, 2 putative_type_I, 41 rhodopsin_like, 1 ambiguous, 9 rejected (all helio-primary) |
| Frozen scorer reconstruction | `pipeline/v140/scorer_v140.py` + `features_v140.py` | The v1.2 membership scorer (previously a documented recovery gap) is fully reconstructed and gated: **0/5,361 score diffs, 0/5,361 category diffs** against the frozen DB from the v1.0 rosetta table; 5,360/5,361 exact end-to-end from raw sequence (one documented DIAMOND bitscore tie, category unaffected) |
| MR_RT_002 promotion | `tree_node` (+554), `tree_edge` (+553), `reference_clade` (+55 `MR_CLD2_*`), `reference_clade_tip` (+896) | 278-tip backbone (Q.PFAM+F+R6) promoted orphaned_candidate → canonical_release. Storage conventions reverse-engineered from MR_RT_001 and verified (DFS-preorder T/N ids, edges-at-parent-visit E ids, incoming-edge clade links). 55/55 stored clades monophyletic; 4 root-side complement clades excluded (unrepresentable in the as-parsed orientation; documented) |
| v1.4.0 placements | `placement_v140` (4,335 rows) | EPA-ng 0.3.8 (LG+G) placement of **100% of the eligible population** (active ∧ complete_core ∧ non-reference-tip; eligibility rule recovered exactly from the frozen layer: 4,326/4,326 in v1.3.0). 52/52 new core sequences clade-assigned |

## API

`meta/microrhododb_api_v14.py` — `__version__ = "1.4.0"`; all v1.3.0 accessors unchanged; new: `query_placement_v140(tree_id=None)`, `query_extension_delta()`; fix: `query_clade_provenance()` now joins `tree_node`/`tree_edge` with the correct `tree_id` per clade namespace (node/edge ids are only unique within a tree).

## Known limitations (carried + new)

- Scorer end-to-end recomputation is 5,360/5,361 exact: A0ABR3CQ64 differs by +0.0002 (DIAMOND 2.2.8 bitscore tie between SRI/SRII seeds P0DMH8/P42196, both 37.4 bits; category unaffected).
- `placement_v140` uses LG+G (epa-ng 0.3.8/libpll lacks Q.PFAM); this is the documented v1-era convention for the 278-tip tree. `n_credible` = number of edges with LWR ≥ 0.05 (v1.4.0 convention; the frozen v1.x rule is unrecoverable).
- MR_RT_001-side placement of the 52 new core sequences was **not** produced: the v1.1 185-tip reference MSA does not survive (99/185 tips are absent from the surviving 278-tip alignment). The frozen `placement` table remains the authoritative MR_RT_001 layer.
- 83/3,485 queries high-confidence on MR_RT_001 place ambiguously on the expanded MR_RT_002 (2.4%; expected with more competing edges); median best-LWR is 1.0 on both trees.
- New accessions carry seed-homology evidence only; no new functional/spectral curation.

## Integrity

SHA-256 checksums in `SHA256SUMS`; full test detail in `validation/validation_v140.json`; probe regression in `validation/recovery_probes_v140.txt`; per-table build provenance (tool versions, input order, code hashes, gate results) in the DB table `build_provenance` (49 rows) and `meta/build_manifest_v140.json`.
