# Construction review checks

Read-only checks of the v1.6.1 release that the release tests do not cover. Nothing here changes a release
database: findings that would change data need a new release with signed curator decisions.

Run from the repository root in the pinned environment (`workflow/envs/`), with the v1.6.1 database present:

```bash
DB=releases/v1.6.1/db/microrhododb_v1.6.1.sqlite
OUT=pipeline/construction_review/results
python pipeline/construction_review/specificity_by_negative_class.py $DB $OUT/specificity_by_negative_class.tsv
python pipeline/construction_review/consistency_checks.py $DB $OUT
python pipeline/construction_review/helixc_motif.py $DB releases/v1.6.1/scorer/PF01036.25.hmm $OUT
python -m pytest -q tests/test_construction_review.py
```

`helixc_motif.py` also writes the full per-record comparison (`helixc_motif_rederived.tsv`, 5,466 rows), which is not
committed.

## Results (v1.6.1, 2026-11-23)

**Helix-C motif is reproducible from sequence.** `tools/helixc_motif.py` reads BR D85/T89/D96 from an hmmalign
alignment against PF01036.25, the same way the frozen scorer reads K216. It reproduces the stored `helixC_motif`
and `motif_class` for 5,361 of 5,361 UniProtKB 2026_02 records, and the K216 read agrees with
`qc_feature.has_retinal_lysine` for 5,080 of 5,080 non-heliorhodopsin records (`helixc_motif_summary.tsv`). The
`motif_class` is a function of the motif:

| Motif | Class |
|---|---|
| DTD, DTE, DSD, DSE | proton_pump |
| NTN, NTQ, NSN | anion_pump |
| NDQ, NCQ | sodium_pump |
| D-[T/S]-x, any other x | sensory_like |
| any position deleted | (empty) |
| everything else | unassigned |

The 105 UniProtKB 2026_03 records have **no stored motif**, so the v1.6.0 conflict rule could not test them
(`helixc_motif_missing_in_release.tsv`). Only 3 of them are called (E1-E4). Applying the conflict rule with the
re-derived motif flags one: PaR A0ACE3JIR6 (E1 proton_pump, motif DTG, a known DTG proton pump). E1 conflicts are
flag-only, so no evidence level would change.

The inherited v1.4 function labels behind E3/E4 (`func_class_v14`) are still not reproducible: their rules were in
the lost v1.2 stage `s08_function.py`.

**Specificity on negatives that reach the score** (`specificity_by_negative_class.tsv`). The pooled counts
reproduce the shipped operating points exactly (the script fails otherwise).

| Set | Negatives | Specificity at 0.70 | Wilson 95% CI |
|---|---|---|---|
| External, all | 345 | 345/345 | 0.989-1.0 |
| External, pass both gates (`retinal_site_lacking_PF01036_homolog`) | 30 | 30/30 | 0.886-1.0 |
| Clade-root holdout, all | 215 | 209/215 | 0.940-0.987 |
| Clade-root holdout, hard and not helio-gated (fragments, frameshifts, HSP30) | 45 | 39/45 | 0.738-0.937 |

Of the 345 external negatives, 290 have no PF01036/PF18761 hit and 25 are heliorhodopsins removed by the
helio-primary gate, which all score at least 0.70 on the ungated score. The holdout's 6 false positives at 0.70
are synthetic fragments.

**Placement and membership disagree for 51 records** (`placement_vs_membership.tsv`). These Type-I members and
candidates are placed in the heliorhodopsin outgroup on MR_RT_003 (Q.pfam+F+R9). All 51 have
`placement_qc = long_pendant`.

| Status | Outgroup in all MR_RT_003 models; Type-I clade on MR_RT_002 | Depends on the placement model | Outgroup throughout | Total |
|---|---|---|---|---|
| typeI_member_curated | 1 | 0 | 1 | 2 |
| typeI_candidate_architecture_supported | 23 | 14 | 8 | 45 |
| typeI_candidate | 0 | 2 | 1 | 3 |
| typeI_candidate_unresolved | 1 | 0 | 0 | 1 |

The two curated members are GtCCR2 L1K1K8 and its identical twin A0A0C3UE61. The first column is most likely a
gap in MR_RT_003's tip sampling.

**E2 transfer across a helix-C difference** (`e2_motif_mismatch.tsv`). One non-engineered E2 call has a different
motif from its E1 reference: A0AAE0MU22 (DTD) takes `photoreceptor_unassigned` from NOP-1 Q9UW81 (DTE) at 0.924
identity. Every other non-engineered E2 call shares its reference's motif.

**Checked and withdrawn: batch-size dependence of the scorer.** `features_v140.scan_domains` uses pyhmmer's
default search space (Z = number of sequences searched), so in principle a weak domain hit could be reported in a
small batch and not in a large one. Scoring all 5,466 records one at a time and as one batch gives identical
`dom_score`, `hmm_cov`, PF01036/PF18761 scores and primary model for every record. A hit that the batch size could
change would score about 9 bits or less, far below any threshold. The frozen scorer is left unchanged.
