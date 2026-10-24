# MicroRhodoDB v1.6.1 - Release Notes

Release 1.6.1, 2026-10-24, schema `v161.1`. Base: v1.6.0 (immutable; opened read-only and copied, SHA-256 checked).
Correction release answering a pre-submission review of the MicroRhodoDB manuscript. The corpus, the membership
scorer, its thresholds, the reference tree, the placements and the clade assignments are unchanged.

## What changed

**One decision per unique sequence.** In v1.6.0, 19 of the 129 groups of byte-identical, non-engineered records
carried different annotations: 4 groups differed in membership tier and 15 in function call. Identical sequences now
share one membership status and one function call. 23 records changed (107 field changes, all listed with old and
new values in `curation_v161_decision` and `tables/identical_sequence_decisions_v161.tsv`). The rule set was approved
by the curator (CongJian Li) on 2026-10-24; `pipeline/v161/identical_sequences_v161.py` applies it record by record.

| Rule | Situation | Records |
|---|---|---|
| M1 | Candidate copies of the curated HSP30 decoys (P25619, Q12117) become `decoy_or_rejected` | 3 (B3LU93, A0A6C1DPQ8, B3LGN3) |
| M2 + F1 | Twins of the curated E1 members CryoR1 (A0A1I3DJQ0) and GtCCR2 (L1K1K8) become `typeI_member_curated`, E2 at identity 1.00 | 2 (A0ABY1EHF9, A0A0C3UE61) |
| F2 | E4 calls whose identical twin was withdrawn for a motif conflict become E5 `unassigned` (conservative) | 9 |
| F3 | Uncalled twins of a conflict-withdrawn record become E5 `unassigned` | 2 |
| F4 | Uncalled twins of an unconflicted E4 call receive the same call (same sequence and motif) | 4 |
| F5 | `sensory` vs `sensory_like`: E3 follows the clade consensus (`sensory`); E4 keeps `sensory_like` | 3 |

The twin of L1K1K8 (A0A0C3UE61) is unplaced, like L1K1K8 itself, so its E2 call rests on sequence identity alone,
not on the usual same-clade condition.

**Effect on counts**

| Quantity | v1.6.0 | v1.6.1 |
|---|---|---|
| Members / candidates / boundary / outgroup / rejected (all records) | 3,089 / 1,379 / 509 / 386 / 103 | 3,091 / 1,374 / 509 / 386 / 106 |
| E1 / E2 / E3 / E4 / E5 (counted) | 88 / 109 / 1,143 / 1,050 / 3,070 | 88 / 111 / 1,143 / 1,045 / 3,073 |
| Records with a call-conflict flag | 468 | 480 |

**Clade names.** New column `clade.name_basis_type`. Six level-1 groups have no characterised member and carry
provisional names from motif, taxonomy or legacy labels: MR_CLD3_002, 005, 008, 014, 015 and B02. The naming basis
of MR_CLD3_017 no longer cites CarO (Q70LL3) as E1; Q70LL3 was re-tiered to E4 in v1.6.0.

**Policies stated in the database.** `release_metadata` (release 1.6.1) and the data dictionary now state that
candidates receive no function call (E5 by policy), and that curation recommendations and the blind re-annotation of
the E2-E4 audit sample were drafted with an AI assistant and reviewed and signed by the curator.

**Curation provenance.** New view `v_curation_decision` gives one decider and one date for every v1.6.0 and v1.6.1
decision (v1.6.0 stores them in either `signed_by`/`signed_date` or `decided_by`/`decided_at`).

**Command-line scorer.** `typeI_detected_070` now applies the gates of the validated `full_gated` score (PF01036
domain, not heliorhodopsin-primary, positive Type-I margin). Before, heliorhodopsins scoring at least 0.70 were
reported as detected. The v1.6.0 release notes describe the column as "score >= 0.70"; that description is
superseded. Shipped data were not affected (the Foldseek watchlist has no heliorhodopsin-like hits).

## New validation analyses (`validation/`)

| File | Result |
|---|---|
| `hard_negative_specificity_v161.tsv` | Of the 345 external negatives, 290 have no PF01036/PF18761 domain and score 0. On the 55 hard negatives at 0.70, the score alone passes all 25 heliorhodopsins (specificity 30/55 = 0.545); the full rule rejects all 55. |
| `nearest_e1_baseline_v161.tsv` | Transferring the class of the nearest other E1 protein is correct for 63/76 (0.83) when only the record is hidden, but 38/76 (0.50) with its subfamily hidden and 36/76 (0.47) with its clade hidden, against 52/70 (0.74) for the shipped legacy policy at leave-one-clade-out. |
| `e3_replicate_robustness_v161.tsv` | The reference tips of all 16 E1-consensus groups form the same clade in both independent replicate searches (run2, run3; run1 is the release tree); all 1,143 E3 calls keep their consensus. This tests the reference tree, not the placement of query records. |

## Reproduce

```bash
conda activate mrdb
snakemake -c 1 all_v161      # rebuild from v1.6.0 + curation/v161, rerun the analyses, compare (93/93 objects identical), test
python -m pytest -q tests/test_v161_release.py
cd releases/v1.6.1 && sha256sum -c SHA256SUMS
```

## Not changed

The website and the Python API still default to v1.6.0 (website data are exported from the v1.6.0 database). Set
`MRDB_DB=releases/v1.6.1/db/microrhododb_v1.6.1.sqlite` for the API, or pass `--release releases/v1.6.1` to the CLI.
