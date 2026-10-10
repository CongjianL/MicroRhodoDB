# MicroRhodoDB v1.6.0 - Release Notes

**Release date:** 2026-10-10 - **Base:** v1.5.0 (immutable; opened read-only and copied) - **Schema:** v160.1 -
**DB SHA-256:** `379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f` - **Curation:** all v1.6.0
sign-off rows decided by CongJian Li (round 1 on 2026-10-09, round 2 "R2" on 2026-10-10; 622 rows in
`curation_v160_decision`).

## What v1.6.0 is

A **function-evidence and usability release** made in response to peer review of v1.5.0. The corpus (5,466
UniProtKB records), membership scorer, thresholds, reference tree MR_RT_003 and clade assignments are unchanged.
`membership_status` changes only for 4 E1 records moved to `typeI_member_curated` by a signed, PMID-backed
override (R2). What changes is how function calls are labelled and validated, which records count, and how the
data can be reached (browser, API, data dictionary, workflow).

## Changes

| Area | Change | Result |
|---|---|---|
| Function-call conflicts | Compatibility-aware rule: a motif of `unassigned` is untestable; a `sensory_like` motif conflicts only with pump calls; a pump motif conflicts with any other call. E3/E4 calls that contradict the record's own motif are downgraded to E5 `unassigned`; E1, E2 and curated-rule conflicts are flagged only | 468 records flagged (`call_conflict = 1`); 439 downgrades applied (443 signed; the other 4 were promoted to E1 instead); 29 flagged-only conflicts (E1 14, E2 9, E4 6) |
| Curated audit rules (R2) | Signed decisions on v1.5.0 audit rules: the xenorhodopsin-like D-T-A / D-S-A rule and the OpsA-like D-S-E rule no longer assign a class; the two schizorhodopsins conflicting with their family are reassigned | 69 (xeno) + 47 (OpsA) records E4 -> E5 `unresolved`; schizorhodopsins A0AAP2RB57 and A0ABT8M6U9 -> E5 `unresolved` (`override_rule = schizorhodopsin_family_conflict`) |
| Basis labels | E3/E4 classes are inherited v1.4 labels and are now named that way | `legacy_v14_concordant_motif` 973 records, `legacy_v14_motif_untestable` 51 records |
| `clade_function` (R2) | Recomputed with the v1.5.0 rule on the 88 non-engineered v1.6.0 E1 records (was frozen at v1.5.0 values); per-group result in `clade_function_consensus` | 16/49 groups have a consensus; 657 records lose an inherited `clade_function` (625 proton_pump, 32 anion_pump). MR_CLD3_017 is now `mixed` (3/4 = 0.75) and MR_CLD3_017.01 `no_E1` |
| MR_CLD3_017 | Re-examined with the new rule and the recomputed `clade_function` | 1,646 confident records; 382 call conflicts; 377 now E5 `unassigned`; remaining E4 calls: proton_pump 586, sensory 47, sensory_like 29 (239 former E3 proton_pump calls in this clade, 223 of them in MR_CLD3_017.01, are now E4 because neither the clade, now `mixed`, nor MR_CLD3_017.01, now without E1, has a consensus `clade_function`); 597 further records have only a tentative MR_CLD3_017 placement |
| E-level totals | v1.5.0 -> v1.6.0 (counted records) | E1 85 -> 88, E2 119 -> 109, E3 1,388 -> 1,143, E4 1,358 -> 1,050, E5 2,516 -> 3,070 |
| E1 literature sweep | 16 promotions to E1 (incl. UmOps1 A0A0D1EC87, UmOps2 A0A0D1E071, glycylhalorhodopsin A0A5B2VFD4 as anion_pump, SpaR A0A411LJN5 as proton_pump, NOP-1 Q9UW81 as photoreceptor_unassigned, exoKCR1 A0ABF7PQ82, GtCCR2 L1K1K8, CryoR1 A0A1I3DJQ0 as proton_pump_inward) | E1 85 -> 91 records (88 counted); 76 unique non-engineered E1 sequences |
| E1 re-tiering | 6 records whose only support was a compilation table (A0A0G9MK34, A0A0M7BDG0, A0A1C7DB83, A0A840I7T6, A0ABX5PZH6, A6W8Z2) left E1 by curator decision; the carO pair (Q70LL3, S0ELR6) was set to E4 proton_pump by signed override | 8 records left E1 |
| E1 evidence checks (R2) | Full-text checks of the 4 E1 records whose support was unverified or missing | Q6R5N7 (HxAR; abstract reports a photoelectric response only) -> E2 proton_pump, link set to `context`; A0A0P6XBM7 (no paper on this protein; BeNaR, PMID 36724978, is 89.2% identical) -> E4 sodium_pump, BeNaR linked as `context`; A0A0M5L0M3 keeps E1 (quote verified in the bioRxiv preprint 10.1101/2025.04.29.651185); A0ACE3JIR6 keeps E1 with a new primary paper (PaR, Harris et al. 2015, PMID 26260121; quote verified in the author's 2016 M.Sc. thesis) |
| Membership override (R2, R-F3) | New status `typeI_member_curated` for E1 records with direct experimental evidence that the scorer leaves as candidates. Scores and thresholds unchanged | 4 records: CryoR1 A0A1I3DJQ0, GtCCR2 L1K1K8, GtCCR4 A0A3G1I4H9, exoKCR1 A0ABF7PQ82. Members 3,085 -> 3,089; candidates 1,383 -> 1,379. The engineered A0ABF7PQ84 and A0ABF7PQA2 remain candidates |
| Engineered constructs | `is_engineered = 1` with `wild_type_acc`; excluded from counts, coverage, E2 transfer references, benchmarks, holdout assignment and scorer seeds | 6 records (A0A6I8WFQ3, A0A7M4DUE4, A0A7M4DUE9, A0A8X6EH36, A0ABF7PQ84, A0ABF7PQA2); 5,460 counted records |
| Publications | 49 publications added; compilation-PMID rows fixed (characterized_protein 67, spectral_audit 65); ECO-token rows cleaned (16 and 12); 15 DOI/PMID fills | 121 publications; 178 links added (compilation 109, support 66, context 3); all 66 new support links have a quote verified in retrieved text (64 abstracts, 2 full texts); 91/91 E1 records have a support link |
| Blind audit (R2, R-V2) | The 120-record sample (40 each of E2/E3/E4; seed 160) was re-annotated by an annotator blind to the stored call; results in `audit_blind` and `audit_agreement` | Exact agreement E2 39/40 (0.975, 95% CI 0.871-0.996), E3 39/40 (0.975), E4 22/40 (0.550, 0.398-0.693; 22/37 excluding unresolvable), all 100/120 (0.833, 0.757-0.889) |
| Leave-one-clade-out (LOCO) | E1 estimate with frozen motif rules on 76 unique non-engineered E1 sequences in 13 clades | Inherited (legacy) class correct for 52/70 (0.743, 95% CI 0.63-0.83); downgrade policy 49/64 (0.766, 0.65-0.85); motif call 45/57 (0.789, 0.67-0.88) |
| Family-HMM flag (R2, R-V3) | Per-record flag (`novel_family_flag`) when the best of five family HMMs (viral, schizo-, xeno-, bestrhodopsin, MerMAID) beats PF01036 (E <= 1e-10, bits > PF01036 bits, `-Z 5466`). Flag only: scores and membership unchanged | 139/5,466 records flagged (xeno 125, MerMAID 9, schizo 3, bestR 2). External set: 16/21 positives flagged (2/7 non-seed), 1/345 negatives; detected at 0.70 or flagged 20/21 (`validation/family_flag_rates_v160.tsv`) |
| Foldseek watchlist (R2, R-C1) | 10 structure queries against AFDB50 and MGnify (web server); hits filtered to rhodopsin-like structures absent from the corpus, stored in `foldseek_query`, `foldseek_hit`, `foldseek_funnel`; added to `novel_family_candidate` as a watchlist | 786 hits (605 Pfam-detectable sampling gaps, 155 under-represented families, 26 structure-only without PF01036); `novel_family_candidate` 181 rows (viral 138, structure-only 23, schizo 12, bestR 5, MerMAID 3). Counts unaffected |
| Clade coverage (R-C1) | Coverage of members + candidates by confident clades (`validation/clade_coverage_v160.tsv`, `tools/clade_coverage_v160.py`) | 3,821/4,468 (85.5%); members 97.9%; 407 (9.1%) have only a tentative MR_CLD3_017 placement |
| Scorer validation summary | `validation/scorer_validation_v160.tsv` (134 rows) collects the external, clade-root holdout, identity-stratified and family-level results, with the InterPro retrieval record | See "Scorer" below |
| Data dictionary | `data_dictionary` table and `tables/data_dictionary_v160.tsv` | 1,232 rows covering 91 tables and views (100%) |
| Provenance | `sequence_source.source_release` backfilled | 5,361 UniProtKB_2026_02 + 105 UniProtKB_2026_03 |
| Deprecations | `membership.alias_v14` and the compatibility views `v_typeI_core`, `v_typeI_candidates`, `v_typeI_active`, `v_rejected_or_decoy` removed | 8 views remain: `v_master`, `v_counted`, `v_typeI_member`, `v_typeI_candidate`, `v_boundary_family`, `v_heliorhodopsin`, `v_call_conflict`, `v_engineered` |
| Browser | Static site with record pages (deep links), DOI/PMID display, FASTA/TSV export, in-browser Smith-Waterman search, curated-member and family flags, Foldseek watchlist view | Works from `file://`; 42/42 walkthrough checks pass; P02945 is the top hit for the bacteriorhodopsin query |
| API / CLI | `src/microrhododb` (read-only, `pip install .`, version 1.6.0); CLI adds `typeI_detected_070` (score >= 0.70) and the family flag | 12-query CLI run: 3 member_like, 8 candidate_like, 1 not_rhodopsin |
| Workflow | `snakemake -c 4` rebuilds v1.6.0 from the v1.5.0 DB plus signed curation and checks the rebuilt DB is content-identical (91/91 objects) | Dry run lists 8 jobs |

## Scorer (unchanged; description corrected)

- On the external set (21 positives / 345 negatives), `full_gated` AUPRC 0.910 [0.795-1.0] **equals** the rule
  baseline `B4b_ga_retK` (0.910). Five of six ablations leave it unchanged; only removing the retinal-lysine axis
  lowers it (0.608). The v1.5.0 statement that the score "clearly outperforms every baseline" was wrong.
- On the clade-root holdout (46 / 215; no held-out positive has a training positive >= 50% identical), `full_gated`
  ranks better than the rule (AUPRC 0.987 vs 0.814), but at 0.70 its calls equal the rule's: sensitivity 42/46
  (0.913), specificity 209/215 (0.972).
- Recommended threshold for discovery: **0.70**. At 0.90 sensitivity falls to 18/46 (0.391) on the clade-root
  holdout and 3/21 on the external set. Specificity on the external set is 1.0 at every threshold.
- The random-5 holdout is leaky: 27/46 held-out positives have a training positive >= 90% identical.
- Identity-stratified external results (any-reference identity < 90%: 19/244, AUPRC 0.902, sensitivity at 0.70
  14/19). Bestrhodopsins are missed by the score at every threshold (0/4); the family-HMM flag marks all 4, but
  they are family-HMM seeds, so this is circular.
- InterPro retrieval (2026-10-07): PF01036 API count 5,076, 5,088 retrieved; PF18761 386/386. Overlap with
  MicroRhodoDB 5,460 accessions (99.74% of the 5,474 InterPro union).

## Known limitations

- **LOCO estimate fell** from 63/75 (0.840) on the v1.5.0 E1 set (n = 85) to 52/70 (0.743) on the v1.6.0 set.
  The likely cause is selection: many new E1 records were added because they were mis-called. E3-like calls are
  much more reliable than E4-like calls (leave-one-out 30/31 vs 22/39), in line with the blind audit (E3 0.975 vs
  E4 0.550).
- **The blind audit is not fully independent.** The blind annotator also used homology, so E2/E3 agreement partly
  reflects shared reasoning; it measures reproducibility of the call, not ground truth. E1-E5 are evidence levels,
  not accuracy tiers.
- **Two E1 quotes are verified outside the version of record.** A0A0M5L0M3 in the bioRxiv preprint (not the
  Structure article) and A0ACE3JIR6 in the author's M.Sc. thesis (the BBA article was not accessible).
- **Foldseek watchlist caveats.** Web-server hit lists are capped at 1000 per query and database; the cap was
  reached for 9 of 10 queries (the bestrhodopsin surrogate A0AAE0C9L8 returned 632 AFDB50 / 557 MGnify hits), so
  the watchlist is a sample, not a census. TM-scores were not available; the retinal lysine (K216) was checked by
  pairwise alignment only; MGnify hits carry no taxonomy. Viral rhodopsins are under-sampled in the corpus (138
  watchlist rows).
- **Family-HMM flag recall outside its seeds is low** (2/7 non-seed external positives). The flag is a pointer for
  review, not a classifier.
- **E1 records that are membership candidates.** Only the engineered A0ABF7PQ84 and A0ABF7PQA2 remain; they are
  excluded from counts.
- `accession_map` is many-to-one: 5,466 source accessions map to 5,299 MRDB accessions; 129 MRDB accessions carry
  more than one source accession.
- Stage-1 curation and audit scripts in `pipeline/v160/stage1_records/` and `curation/v160/audit_v150/` are records
  of what was run, not re-executable steps. The blind-audit calls and Foldseek hits are inputs to the build, not
  regenerated by it.
- DIAMOND 2.1.10 is used (2.2.8, used for the original v1.4.0 scorer, is not on bioconda).
- No wet-lab validation was performed; funding for hosting beyond the current term is not secured (`MAINTENANCE.md`).

## Integrity

`SHA256SUMS` covers every file in this release directory. The v1.5.0 and v1.4.0 directories are unchanged and
verified by the test suite. Build log: `meta/build_log_v160.txt`.
