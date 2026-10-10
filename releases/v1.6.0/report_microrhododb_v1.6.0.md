# MicroRhodoDB v1.6.0 - Release Report

Release 1.6.0, 2026-10-10, schema v160.1. Base: v1.5.0 (unchanged on disk). Curator: CongJian Li.
DB SHA-256 `379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f`.

## 1. Summary

v1.6.0 answers a referee report on v1.5.0 (23 items) and a second round of referee comments (R2). It does not
change the corpus, the membership scorer, its thresholds or the tree. It changes how function calls are
labelled, which records count, how the scorer is described, and how users reach the data. Membership changes
only through a signed curated override for 4 E1 records.

| Quantity | v1.5.0 | v1.6.0 |
|---|---|---|
| Records (all / counted) | 5,466 / 5,466 | 5,466 / 5,460 (6 engineered excluded) |
| Type-I members / candidates | 3,085 / 1,383 | 3,089 / 1,379 (4 curated overrides) |
| E1 / E2 / E3 / E4 / E5 (counted) | 85 / 119 / 1,388 / 1,358 / 2,516 | 88 / 109 / 1,143 / 1,050 / 3,070 |
| Records with a function-call conflict flag | not flagged | 468 |
| Groups with a `clade_function` consensus | frozen | 16 of 49 (recomputed) |
| Publications / E1 records with a support link | 72 / - | 121 / 91 of 91 |
| Blind-audit agreement, E2-E4 sample | not audited | 100/120 (0.833) |
| Records with a family-HMM flag | - | 139 |
| Foldseek watchlist hits / novel-family rows | - / 0 | 786 / 181 |
| Data dictionary | none | 1,232 rows, 91 objects |

Transitions of evidence level, v1.5.0 (rows) to v1.6.0 (columns), all 5,466 records:

| v1.5.0 | E1 | E2 | E3 | E4 | E5 |
|---|---|---|---|---|---|
| E1 | 75 | 1 | 1 | 8 | 0 |
| E2 | 1 | 95 | 0 | 22 | 1 |
| E3 | 3 | 0 | 1,142 | 217 | 26 |
| E4 | 8 | 16 | 0 | 803 | 531 |
| E5 | 4 | 0 | 0 | 0 | 2,512 |

## 2. Function evidence

**Conflict rule.** For each record the helix-C motif class is compared with the called class. A motif of
`unassigned` cannot be tested. A `sensory_like` motif conflicts only with pump calls. A pump motif conflicts with
any other call. E3/E4 calls that conflict are downgraded to E5 `unassigned`. E1, E2 and curated-rule conflicts are
flagged but kept, because their basis is not the motif.

**Result.** 468 records carry `call_conflict = 1`. 439 E3/E4 calls were downgraded. The signed list had 443; the
other 4 (A0A0D1E071, A0A0D1EC87, A0A517QXI7, A0AAJ6N6B2) were promoted to E1 by the literature sweep. 29 conflicts
are flagged only (E1 14, E2 9, E4 6). Inherited classes that agree with the motif are labelled
`legacy_v14_concordant_motif` (973); those whose motif cannot be tested are labelled `legacy_v14_motif_untestable`
(51).

**Curated audit rules (R2, signed).** Two v1.5.0 audit rules assigned classes that the curator judged
unsupported: the D-T-A / D-S-A rule (could be ASR-like sensory or xenorhodopsin inward pump) and the D-S-E rule
(OpsA-like, a non-pumping lineage). Their 69 and 47 E4 records are now E5 `unresolved`. The two schizorhodopsins
A0AAP2RB57 (FSE motif) and A0ABT8M6U9 (YSD motif) conflicted with their family's inward-pump function and are now
E5 `unresolved` (`override_rule = schizorhodopsin_family_conflict`).

**`clade_function` recomputed (R2).** In earlier builds `clade_function` was frozen at v1.5.0 values. It is now
recomputed with the unchanged v1.5.0 rule on the 88 non-engineered v1.6.0 E1 records. 16 of 49 clade or subclade
groups reach a consensus (`clade_function_consensus`: 16 consensus, 8 mixed, 19 no E1, 6 single E1). 657 records
lose an inherited `clade_function` (625 proton_pump, 32 anion_pump), so calls that rested on it fall from E3 to
E4. MR_CLD3_017 is now `mixed` (3 of 4 E1 records proton_pump) and MR_CLD3_017.01 has no E1 record; in v1.5.0 both the
clade and MR_CLD3_017.01 had a proton_pump consensus.

**MR_CLD3_017.** Of 1,646 confident records, 382 had a call conflict and 377 are E5 `unassigned`. The remaining E4
calls are proton_pump 586, sensory 47 and sensory_like 29; 239 of the proton_pump calls (223 in MR_CLD3_017.01,
16 outside any subclade) were E3 before `clade_function` was recomputed. A further 597 records have only a tentative placement in this clade; every export
marks tentative calls (`clade_display = TENTATIVE:<clade>`).

**E1 sweep.** 16 records were promoted to E1, including the five confirmed wrong calls in the review: UmOps1
A0A0D1EC87 and UmOps2 A0A0D1E071 (proton_pump), glycylhalorhodopsin A0A5B2VFD4 (anion_pump), SpaR A0A411LJN5
(proton_pump) and NOP-1 Q9UW81 (photoreceptor_unassigned). exoKCR1 A0ABF7PQ82, GtCCR2 L1K1K8 and CryoR1
A0A1I3DJQ0 (proton_pump_inward) were also promoted. Ten records left E1: six whose only support was a compilation
table were re-tiered by curator decision (A0A0G9MK34, A0A0M7BDG0, A0A1C7DB83, A0A840I7T6, A0ABX5PZH6, A6W8Z2), the
carO pair Q70LL3 and S0ELR6 was set to E4 proton_pump by signed override, and two were withdrawn after the R2
evidence checks (below). The E1 set is 91 records (88 counted) and 76 unique non-engineered sequences; 11 E1
sequence clusters hold more than one record.

**E1 evidence checks (R2).** The four E1 records whose support was unverified or missing in the first build were
checked against full texts:

| Record | Finding | Decision |
|---|---|---|
| Q6R5N7 (HxAR) | Abstract (PMID 16075162) reports a photoelectric film response; transport polarity not stated | E1 withdrawn; now E2 proton_pump (transfer from P69051, 0.96 identity, same clade); link set to `context` |
| A0A0P6XBM7 | No paper on this protein; BeNaR (PMID 36724978) is 89.2% identical | E1 withdrawn; now E4 sodium_pump (NDQ motif); BeNaR linked as `context` |
| A0A0M5L0M3 (Ps PR paralog) | Pumping quote verified in the bioRxiv preprint 10.1101/2025.04.29.651185 | Keeps E1 |
| A0ACE3JIR6 (PaR) | Primary paper Harris et al. 2015 (PMID 26260121); quote verified in the author's 2016 M.Sc. thesis | Keeps E1 (curator decision); primary paper replaced |

**Publications.** 49 publications were added (121 total) with 178 links (compilation 109, support 66, context 3).
All 66 new support links have a supporting quote verified in retrieved text: 64 in the abstract, A0A0M5L0M3 in the
preprint and A0ACE3JIR6 in the thesis. All 91 E1 records have a support link.

**Engineered constructs.** Six records are tagged or mutant constructs: A0A6I8WFQ3, A0A7M4DUE4 and A0A7M4DUE9
(wild type A0A6P3CW41), A0A8X6EH36 (wild type A0AAJ0LKB3, which received the E1 annotation), and A0ABF7PQ84 and
A0ABF7PQA2 (wild type A0ABF7PQ82). They are excluded from counts, coverage, E2 transfer references, benchmarks,
holdout assignment and scorer seeds. Under the signed Option B the two exoKCR1/HcKCR1 mutants keep their own E1,
because the cited work tested them directly.

## 3. Membership: curated override (R2, R-F3)

The scorer left four non-engineered E1 records as candidates. A new status, `typeI_member_curated`, admits an E1
record to membership when a signed decision cites direct experimental evidence (PMID). Scores and thresholds are
unchanged and the record keeps its score.

| Record | PMID | Score | Former status |
|---|---|---|---|
| CryoR1 A0A1I3DJQ0 | 40614199 | 0.854 | typeI_candidate_architecture_supported |
| GtCCR2 L1K1K8 | 29078348 | 0.798 | typeI_candidate_architecture_supported |
| GtCCR4 A0A3G1I4H9 | 39232582 | 0.773 | typeI_candidate_architecture_supported |
| exoKCR1 A0ABF7PQ82 | 39181878 | 0.772 | typeI_candidate |

Members rise from 3,085 to 3,089 and candidates fall from 1,383 to 1,379. The engineered A0ABF7PQ84 and
A0ABF7PQA2 remain candidates (excluded from counts).

## 4. How reliable are E1-E5 calls?

E1-E5 are levels of evidence, not of accuracy. Two estimates are now available.

**Blind audit of E2-E4 (R2, R-V2).** The frozen 120-record sample (40 per level; seed 160; redrawn byte-identically
from `curation/v160/audit_frame_v160_pre_r2.tsv`) was re-annotated by an annotator who did not see the stored call.

| Level | Exact agreement | 95% CI (Wilson) | Excluding unresolvable |
|---|---|---|---|
| E2 | 39/40 (0.975) | 0.871-0.996 | 39/40 |
| E3 | 39/40 (0.975) | 0.871-0.996 | 39/40 |
| E4 | 22/40 (0.550) | 0.398-0.693 | 22/37 (0.595) |
| All | 100/120 (0.833) | 0.757-0.889 | 100/117 (0.855) |

The annotator also used homology, so E2/E3 agreement is not fully independent of the stored reasoning; it shows
the calls are reproducible, not that they are correct. All 48 high-confidence blind calls agreed.

**Leave-one-clade-out (LOCO)** on the 76 unique non-engineered E1 sequences in 13 clades, with the motif rules
frozen:

| Policy | Correct / called | Precision (95% CI) |
|---|---|---|
| Inherited (legacy) class | 52 / 70 | 0.743 (0.63-0.83) |
| Downgrade policy (as shipped) | 49 / 64 | 0.766 (0.65-0.85) |
| Motif call only | 45 / 57 | 0.789 (0.67-0.88) |

E3-like calls are much more reliable than E4-like calls: leave-one-out 30/31 (0.968) vs 22/39 (0.564);
leave-one-subfamily-out 17/18 (0.944) vs 35/52 (0.673). The blind audit agrees (E3 0.975, E4 0.550). On the
v1.5.0 E1 set (n = 85) the LOCO test gave 63/75 (0.840). The drop is most likely a selection effect, because many
of the new E1 records were added precisely because their earlier calls were wrong.

## 5. Membership scorer

The scorer, its weights and thresholds are unchanged. The v1.5.0 description is corrected.

**External set** (21 positives / 345 negatives, frozen before scoring). `full_gated` AUPRC 0.910 [0.795-1.0] equals
the rule `B4b_ga_retK` (domain hit + retinal lysine). Removing any axis except the retinal lysine leaves AUPRC at
0.910; removing the retinal axis gives 0.608. Ungated `full_raw` gives 0.763 and the best non-rule baseline
`B2b_margin` 0.589. Sensitivity is 16/21 (0.762) at 0.70, 10/21 at 0.86 and 3/21 at 0.90; specificity is 1.0 at
all three thresholds.

**Clade-root holdout** (46 positives / 215 negatives; no held-out positive has a training positive >= 50%
identical). This is the main validation. `full_gated` AUPRC 0.987 [0.93-1.0] vs 0.814 [0.545-0.94] for B4b, so the
continuous score ranks better than the rule. At 0.70, however, its calls are the same as the rule's: sensitivity
42/46 (0.913), specificity 209/215 (0.972), precision 42/48. At 0.86: 41/46 and 214/215. At 0.90: 18/46 (0.391) and
215/215. In the random-5 regime 27/46 held-out positives have a training positive >= 90% identical, so that split
is not used as evidence.

**Identity-stratified external results.** Strata use the identity of each external sequence to its nearest
sequence in any development set (corpus, scorer seeds, benchmark, reference-tree tips).

| Stratum | Positives / negatives | AUPRC | Sensitivity at 0.70 |
|---|---|---|---|
| all | 21 / 345 | 0.910 | 16/21 |
| < 90% | 19 / 244 | 0.902 | 14/19 |
| < 70% | 17 / 215 | 0.891 | 12/17 |
| < 50% | 14 / 196 | 0.933 (nearest-neighbour bits 0.995) | 10/14 |

`full_gated` equals B4b in every stratum. The >= 90% stratum has 2 positives (anion channelrhodopsin 6EDQ_A, score
0.8946; HcKCR1 UOK93384.1, 0.7717, whose nearest corpus record A0ABF7PQ82 is 100% identical) and 101 negatives:
both positives are detected at 0.70, neither at 0.90, and there are no false positives.

**Families.** At 0.70: MerMAID 6/6, xenorhodopsin 2/2, kalium channelrhodopsin 2/2, bestrhodopsin 0/4 (0/4 at every
threshold).

**Family-HMM flag (R2, R-V3).** A record is flagged (`novel_family_flag`) when the best of five family HMMs (viral,
schizo-, xeno-, bestrhodopsin, MerMAID) has E <= 1e-10 and more bits than PF01036 (`hmmsearch -Z 5466`). The flag
does not change scores or membership. In the corpus 139 of 5,466 records are flagged (xenorhodopsin 125, MerMAID 9,
schizorhodopsin 3, bestrhodopsin 2). On the external set it flags 16/21 positives and 1/345 negatives; detection at
0.70 or a flag covers 20/21 positives (missed: A0A507FHL0). Most flagged positives are family-HMM seeds; only 2 of 7
non-seed positives are flagged, so recall outside the seeds is low (`validation/family_flag_rates_v160.tsv`).

**Recommendation.** Use 0.70 for discovery (CLI column `typeI_detected_070`), and review flagged records by family.
0.86 and 0.90 trade large losses in sensitivity on novel families for little gain in specificity.

**InterPro coverage.** Retrieved 2026-10-07: PF01036 API count 5,076, 5,088 proteins retrieved (02:20:07 UTC);
PF18761 386/386 (02:20:38 UTC). The union is 5,474 accessions; 5,460 (99.74%) are in MicroRhodoDB. The 14
InterPro-only accessions were all created after the corpus snapshot; the 6 MicroRhodoDB-only accessions are
obsolete or merged in UniProt.

## 6. Novel-family layer and clade coverage (R2, R-C1)

**Sequence search.** Seed HMMs (2-6 reference sequences each) for five published families (viral rhodopsin,
schizorhodopsin, xenorhodopsin, bestrhodopsin, MerMAID) were searched against UniProtKB through EBI and against
Swiss-Prot. After removing known corpus records and applying length and retinal-lysine filters, no sequence
candidates remained. For bestrhodopsins, only 189 of 16,979 EBI hits carry PF01036, which is why the Pfam-based
corpus misses them.

**Foldseek watchlist.** Ten structure queries were run against AFDB50 and MGnify (ESM-30) on the Foldseek web
server: five reference Type-I structures (BR 1C3W, HR 1E12, KR2 3X3C, PR 4JQ6, KCR1 8H86), four under-represented
families (schizorhodopsin 7E4G, viral rhodopsin VR1 7AKX, xenorhodopsin 6EYU, bestrhodopsin surrogate A0AAE0C9L8)
and heliorhodopsin 6IS6 as an outgroup; no MerMAID structure was available. Of 14,701 raw hits (unique across
queries), 2,365 passed E <= 1e-3 and probability >= 0.9, 1,562 remained after removing corpus and external-set
sequences, 1,043 kept the retinal lysine (K216) in the pairwise alignment, 834 scored closer to Type-I than to
heliorhodopsin and 786 had a rhodopsin-like length. They are stored in `foldseek_hit` and tiered as Pfam-detectable sampling gaps (605),
under-represented families (155) and structure-only hits without PF01036 (26). Together with the sequence-search
layer, `novel_family_candidate` now holds 181 watchlist rows (viral rhodopsin 138, structure-only 23,
schizorhodopsin 12, bestrhodopsin 5, MerMAID 3). The layer does not affect counts. Hit lists are capped at 1000 per
query and database; 9 of 10 queries reached the cap (the bestrhodopsin surrogate A0AAE0C9L8 returned 632 AFDB50 and
557 MGnify hits), so the watchlist is a sample, not a census.

**Clade coverage** (`validation/clade_coverage_v160.tsv`). Of 4,468 members and candidates, 3,821 (85.5%) have a confident clade, 407 (9.1%) only a
tentative MR_CLD3_017 placement, 90 (2.0%) another tentative placement and 150 are unplaced. Members alone: 3,025 of
3,089 (97.9%) confident.

## 7. Access and reproducibility

- **Browser**: `site/index.html`, self-contained (opens from disk), with record deep links, DOI/PMID display,
  FASTA/TSV export, in-browser Smith-Waterman search (k-mer prefilter, BLOSUM62), curated-member and family flags,
  and a Foldseek watchlist view. 42/42 walkthrough checks pass; P02945 is the top hit for the bacteriorhodopsin
  query.
- **API**: `pip install .`; read-only `MicroRhodoDB` class; `include_engineered` switch on membership queries.
- **CLI**: `python tools/mrdb_search.py query.faa -o hits.tsv` (reports `typeI_detected_070` and the family flag).
- **Workflow**: `snakemake -c 4` rebuilds v1.6.0 from the v1.5.0 DB and the signed curation files (including the R2
  sign-off, blind-audit calls, family-flag table and Foldseek hits) and checks that the rebuilt DB matches the
  shipped one (91/91 objects). The data dictionary, exports, browser data and scorer validation summary are
  regenerated by the same run.
- **Tests**: 52 tests, 0 skips with v1.4.0 and v1.5.0 present.
- **Audit sampler**: `tools/draw_audit_sample.py --frame curation/v160/audit_frame_v160_pre_r2.tsv` redraws the
  frozen 120-record sample with seed 160.

## 8. Limitations

1. E2-E4 accuracy is estimated by a blind audit that shares homology reasoning with the stored calls; LOCO applies
   to the E1 set only.
2. Two E1 quotes are verified outside the version of record (A0A0M5L0M3 preprint; A0ACE3JIR6 thesis).
3. The Foldseek watchlist is capped (9 of 10 queries at 1000 hits per database), has no TM-scores, checks the
   retinal lysine (K216) only by pairwise alignment, and MGnify hits carry no taxonomy. Viral rhodopsins are
   under-sampled in the corpus.
4. Bestrhodopsins are not detected by the score (0/4); the family-HMM flag recovers few non-seed family members
   (2/7).
5. 129 MRDB accessions carry more than one source accession (`accession_map` is many-to-one).
6. Stage-1 curation and audit scripts, the blind-audit calls and the Foldseek hits are shipped as records, not
   re-executable steps.
7. DIAMOND 2.1.10 replaces 2.2.8.
8. No wet-lab validation; long-term funding not secured (see `MAINTENANCE.md`).
