# MicroRhodoDB v1.3.0 — Release Notes

**Release date:** 2026-09-24 · **Base:** v1.2.0 (immutable) · **Schema:** v130.1 · **Validation:** 52/52 release tests pass on the shipped artifact

## What v1.3.0 is

A **validation, provenance, and controlled-pilot release** built around the frozen v1.2.0 core. No membership decision, threshold, or score changed: the `membership` table is byte-identical to v1.2.0 (release test X6b), and the active Type-I population is unchanged.

## What is new

| Workstream | Content | Key result |
|---|---|---|
| WS1 external validation | `external_validation` (106 records) + `external_validation_metric` | Specificity 1.000 on 100 independent negatives; E2 novel-family sensitivity 0.333 @0.86/0.90 (n=6) — thresholds are conservative on novel families |
| WS2 leakage benchmarks | `holdout_assignment` (15,110) + `holdout_metric` (264) | 6 regimes; primary `reference_clade_msc`: sensitivity 0.891 @0.86 / 0.652 @0.90; specificity @0.90 = 1.000 everywhere |
| WS3 tree provenance | `reference_tree`, `tree_node` (368), `tree_edge` (367), `reference_clade_tip` (986) | MR_RT_001 fully auditable; every clade linked to node + edge; MR_RT_002 registered as orphan (not promoted) |
| WS4 evidence ingestion | `publication` (69, all DOI/PMID) + `assertion_publication` (81) | 11 raw-only landmark refs resolved and cross-verified (PubMed + CrossRef + RCSB); gates G1–G4 |
| WS5/6 environmental pilot | `sequence_source` (6,713 = 5,361 UniProt + 1,352 MGnify) + `environmental_admission` (1,352) | 501 environmental_candidate / 851 unresolved under frozen scores; complete isolation from membership |
| WS7 error analysis | `analysis/` + `validation/error_analysis_metrics.*` | Marine/soil distribution shift quantified (8 dimensions); epa-ng placement of all 1,352 onto MR_RT_001; score–placement concordance 81.2% |
| WS8 decision memo | `report_expansion_decision_memo.md` (in this repo's results) | Medium marine-first expansion conditionally recommended; confidence-tier policy proposed, NOT applied |

## API

`meta/microrhododb_api_v13.py` — `__version__ = "1.3.0"`; all v1.2.0 accessors unchanged; new: `query_environmental(biome, state)`, `query_external_validation()`, `query_clade_provenance()`.

## Documented adjustments to the legacy suite

Two v1.2.0 invariants were **superseded by design** (not weakened silently):
- `V2_membership_1to1`: v1.2 required membership to cover all proteins; v1.3 deliberately gives environmental proteins **no** membership row. Adjusted: membership is 1:1 with exactly the UniProt-sourced proteins.
- `V20_release_version`: version pin updated 1.2.0 → 1.3.0.

## Known limitations (carried + new)

- Environmental pilot: fusion not assessable (PF01036-only retrieval); prevalence not estimable (Pfam-pre-screened assemblies); soil yield is a source property (584/627 soil studies amplicon-only); placement used uniform FreeRate weights (epa-ng 0.3.8 cannot pin them; Q matrix/frequencies/rate ratios exact).
- E2 external positives are few (n=6) — novel-family sensitivity estimate is low-precision.
- MR_CLD_026 is taxonomically mixed; do not label it "haloarchaeal".

## Integrity

SHA-256 checksums in `SHA256SUMS`; full test detail in `validation/release_test_results.json`; build provenance in the DB table `build_provenance` (37 rows) and `meta/build_manifest_v130.json`.
