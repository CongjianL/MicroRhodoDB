# MicroRhodoDB v1.3.0 — Release Report

**Date:** 2026-09-24 · **Scope:** validation + provenance + controlled environmental pilot around the frozen v1.2.0 core · **Release test status:** 52/52 PASS on the shipped artifact

## 1. Summary

MicroRhodoDB v1.3.0 hardens the v1.2.0 release along three axes — independent validation, provenance, and a first controlled look at environmental sequence space — without changing any membership decision. The guiding policy held throughout: *candidate discovery prioritizes sensitivity; core-dataset construction prioritizes specificity; conflicting evidence lowers confidence rather than being forced into one label.* All v1.2.0 thresholds (0.70/0.86/0.90) and membership rules remained frozen; nothing was retuned on external or environmental data.

## 2. The frozen core is unchanged

- `membership`: 5,361 rows, byte-identical to v1.2.0 (test X6b compares every (source_acc, score, status) triple against the v1.2.0 release DB).
- Active Type-I population: 4,881 (2,656 core + 377 core architecture-supported + 207 candidate + 276 candidate architecture-supported + 1,365 candidate unresolved); 377 heliorhodopsin; 103 decoy/rejected.
- 31 of 33 legacy v1.2.0 tests run unchanged against v1.3.0; V2 and V20 were adjusted with documented rationale (environmental proteins intentionally have no membership row; version pin 1.3.0).

## 3. Independent validation (WS1, WS2)

- **External set** (106 records, exposure-audited, `ever_exposed_flag=0`, zero hash collisions with corpus/dev inputs): specificity **1.000** on 100 negatives; E2 novel-family sensitivity 0.333 at 0.86/0.90 (n=6; low precision, expected — the frozen model is conservative on novel families).
- **Leakage-controlled holdouts** (6 regimes): primary phylogenetic regime `reference_clade_msc` sensitivity **0.891 @0.86 / 0.652 @0.90**; sequence regimes std_90/intermediate_65 and taxonomic_phylum consistent; specificity @0.90 = 1.000 in all regimes. These are the honest generalization bounds for the frozen model.

## 4. Provenance (WS3, WS4, WS5)

- **Tree**: MR_RT_001 (185 tips, 367 edges, unrooted) fully decomposed into `tree_node`/`tree_edge`; 60 clades each linked to a defining node + edge; 986 clade-tip rows; placement edges map to clades with a 367/367 gate.
- **Evidence**: all 69 publications carry DOI/PMID; 11 raw-only landmark references resolved and cross-verified against PubMed/CrossRef/RCSB (two metadata corrections: id=15 year 2011→2013, id=16 journal Biophys J→Science); gates G1–G4 pass; `raw_ref` preserved identical to v1.2.0.
- **Sequence provenance**: every one of the 6,713 proteins has exactly one `sequence_source` row with SHA-256.

## 5. Environmental pilot (WS6, WS7)

1,352 MGnify candidates (976 marine, 376 soil; permissive PF01036 retrieval E≤10, ≥50 aa) scored with the frozen model: **501 environmental_candidate / 851 unresolved**, fully isolated from membership.

- **Marine**: mean 0.606, 29.5% ≥0.90; mostly novel sequence space (27% no corpus hit; 87.6% singletons @90%); 55% place in the proteorhodopsin clade MR_CLD_033; median placement LWR 0.995; false-positive-like share 9.4%.
- **Soil**: mean 0.386, 66% <0.40; fragment-dominated (78.5% truncated core); phylogenetically diffuse (41 clades, median LWR 0.645); false-positive-like 5.1%. Soil yield is a source property (584/627 MGnify soil studies are amplicon-only).
- **Concordance**: among score ≥0.70 records, 81.2% place with LWR ≥0.9 and 0.2% are novel-clade — the frozen score and independent phylogenetic evidence agree.
- Full detail: `report_pilot_error_analysis.md` + `validation/error_analysis_metrics.tsv` (149 rows, dimensions A–H, BH-FDR stats battery).

## 6. Expansion decision (WS8)

`report_expansion_decision_memo.md`: a **medium, marine-first MGnify expansion** is conditionally defensible behind measurable gates (≥75% concordance, ≤10% fragment share, ≤1% novelty among confirmed, GEM replication before any full expansion). A four-tier environmental confidence policy (confirmed / candidate / fragment / unresolved) is **proposed, not applied** — a v1.4 candidate pending user approval.

## 7. Release contents

```
v1.3.0/
  RELEASE_NOTES_v1.3.0.md
  report_microrhododb_v1.3.0.md
  SHA256SUMS
  db/microrhododb_v1.3.0.sqlite          (39 tables; 18,034,688 bytes)
  meta/schema_v130.sql                   (authoritative schema dump)
  meta/microrhododb_api_v13.py           (API 1.3.0)
  meta/build_manifest_v130.json
  meta/release_boundaries_v130.json
  figures/pr13_pilot_distribution_shift.{svg,png}
  validation/release_test_results.json   (52 tests)
  validation/error_analysis_metrics.{tsv,json}
  validation/external_validation_metrics.csv
  validation/holdout_metrics_pooled.csv
  analysis/pilot_annotated.tsv           (1,352 records x full annotation)
  analysis/placement_pilot_annotated.tsv
  analysis/placement_pilot.jplace
```

## 8. Limitations

Carried from v1.2.0 plus: pilot fusion not assessable; prevalence not estimable; soil yield source-limited; placement FreeRate weights uniform (rate ratios exact); E2 n=6 low-precision; MR_CLD_026 taxonomically mixed. See RELEASE_NOTES for the full list.
