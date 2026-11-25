# MicroRhodoDB v1.6.2 - Release Notes

**Release date:** 2026-11-25

Release 1.6.2, schema `v162.1`. Base: v1.6.1 (immutable; opened read-only and copied, SHA-256 checked).
Correction release from a review of the database construction method (`pipeline/construction_review/`). The corpus,
the membership scorer, its thresholds, the reference tree, the placements, the clade assignments and every membership
status are unchanged.

## What changed

The curator (CongJian Li) approved three decisions on 2026-11-25. `pipeline/v162/decisions_v162.py` applies them record by record.
Every one of the 270 field changes on 157 records is listed with its old and new value in `curation_v162_decision` and
`tables/construction_review_decisions_v162.tsv`.

| Rule | Change | Records |
|---|---|---|
| MOTIF1 | Helix-C motif (`helixC_motif`, `motif_class`) for the records that had none | 105 |
| PLACE1 | New QC flag `record_clade.placement_qc_flag` for Type-I members and candidates placed in the heliorhodopsin outgroup | 51 |
| E2M1 | E2 call withdrawn because the helix-C motif differs from the E1 reference's | 1 |

**MOTIF1: helix-C motif from sequence.** In v1.6.1 the motif came from the v1.1 `function` table, and the code that
produced it is not in the repository. The 105 records added from UniProtKB 2026_03 had no motif, so the v1.6.0 conflict
rule could not test them. The new `tools/helixc_motif.py` reads the residues at BR D85, T89 and D96 from an hmmalign
alignment against PF01036.25, the same way the scorer reads K216. It reproduces the stored motif and `motif_class`
for all 5,361 UniProtKB 2026_02 records. For the 105 new records the classes are:

| Class | Records |
|---|---|
| unassigned | 39 |
| proton_pump | 37 |
| anion_pump | 13 |
| sensory_like | 10 |
| sodium_pump | 3 |
| empty (`---`, sequence does not cover helix C) | 3 |

The conflict rule was then applied with the new motif. It flags one record: PaR A0ACE3JIR6, an E1 proton pump with a
DTG motif (`sensory_like`). E1 conflicts are flag-only, so its call and level are unchanged. No other call changed.
Existing conflict flags were not cleared.

**PLACE1: placement disagrees with membership.** The scorer already rejects heliorhodopsin-primary sequences, yet 51
Type-I records are placed in the heliorhodopsin outgroup on MR_RT_003. All 51 already had `placement_qc = long_pendant`.
The new column `record_clade.placement_qc_flag` (also in `v_master` and `tables/records_v162.tsv`) reads
`typeI_status_in_heliorhodopsin_outgroup:<diagnosis>`:

| Diagnosis | Meaning | Records |
|---|---|---|
| `mr_rt_003_sampling_gap` | Outgroup in all three MR_RT_003 placement models; MR_RT_002 placed the sequence in a Type-I clade | 26 |
| `model_sensitive` | The LG+G4 or LG+R4 placement differs | 16 |
| `consistent_outgroup_placement` | Outgroup in every model and on MR_RT_002 | 9 |

The 51 are 45 `typeI_candidate_architecture_supported`, 3 `typeI_candidate`, 1 `typeI_candidate_unresolved` and 2
`typeI_member_curated`: GtCCR2 L1K1K8 and its identical twin A0A0C3UE61, both `mr_rt_003_sampling_gap`. The flag only
annotates; placements and clade calls are unchanged.

**E2M1: E2 requires the reference's helix-C motif.** An E2 call is now kept only when the record's helix-C motif
equals that of its E1 reference. One non-engineered record failed this: A0AAE0MU22 (DTD) had E2
`photoreceptor_unassigned` from NOP-1 Q9UW81 (DTE) at 0.924 identity. Its motif reads as a proton pump and its
reference is a characterised non-pumping photoreceptor, so neither is taken: it is now E5 `unresolved`
(`override_rule = e2_motif_mismatch_v162`). Engineered constructs keep the E2 from their own wild type (v1.6.0
Option B). The one affected construct, A0A7M4DUE4 (DSD vs wild type A0A6P3CW41, TSD), is unchanged and excluded from
counts.

**Effect on counts**

| Quantity | v1.6.1 | v1.6.2 |
|---|---|---|
| Members / candidates / boundary / outgroup / rejected (all records) | 3,091 / 1,374 / 509 / 386 / 106 | unchanged |
| E1 / E2 / E3 / E4 / E5 (counted) | 88 / 111 / 1,143 / 1,045 / 3,073 | 88 / 110 / 1,143 / 1,045 / 3,074 |
| Records with a call-conflict flag | 480 | 480 (PaR flagged; A0AAE0MU22's flag cleared with its call) |
| Records without a helix-C motif | 105 | 0 |

**Validation analyses not recomputed.** The v1.6.0 LOCO tables (`loco_validation`, `loco_validation_record`) and
`spectral_audit` are frozen analyses and keep PaR's blank motif. With PaR's motif, the motif-only policy at LOCO would
be 45/58 (0.776, 95% CI 0.653-0.864) instead of 45/57 (0.789). The legacy and downgrade policies do not use the motif
for PaR and are unchanged (52/70 and 49/64).

## Validation (`validation/`)

| File | Result |
|---|---|
| `helixc_motif_summary_v162.tsv` | The motif re-derived from sequence equals the stored motif and class for all 5,466 records. The K216 read agrees with `qc_feature.has_retinal_lysine` for all 5,080 non-heliorhodopsin records. |
| `specificity_by_negative_class_v162.tsv` | Specificity split by negative class and by the step that rejects each negative. The pooled counts reproduce the shipped operating points. On the negatives that reach the score, at 0.70: external 30/30 (Wilson lower bound 0.886), clade-root holdout 39/45 (0.867, 0.738-0.937). The holdout's 6 false positives are synthetic fragments. Extends `releases/v1.6.1/validation/hard_negative_specificity_v161.tsv` (external set only) to the holdout. |
| `placement_vs_membership_v162.tsv` | The 51 flagged records with their placement statistics, alternative-model calls and MR_RT_002 clade. |
| `e2_motif_mismatch_v162.tsv` | E2 calls whose motif differs from the reference's: only the engineered A0A7M4DUE4 remains. |

## Command-line scorer

`tools/mrdb_search.py` now reports `helixC_motif` and `motif_class` for each query, from `tools/helixc_motif.py`. Both
are empty when the query has no PF01036/PF18761 hit, because the forced alignment is then not homologous. The membership
score and every other column are unchanged.

## Reproduce

```bash
conda activate mrdb
snakemake -c 1 all_v162      # rebuild from v1.6.1 + curation/v162, rerun the review checks, compare, test
python -m pytest -q tests/test_v162_release.py
cd releases/v1.6.2 && sha256sum -c SHA256SUMS
```

## Not changed

The website, the Python API and the CLI still default to v1.6.1 until the v1.6.2 database is attached to a GitHub
Release. Set `MRDB_DB=releases/v1.6.2/db/microrhododb_v1.6.2.sqlite` for the API, or pass `--release releases/v1.6.2`
to the CLI.
