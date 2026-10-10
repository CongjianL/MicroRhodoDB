# Novel-family candidate layer — methods, findings, and limitations (v1.6.0)

## Purpose

MicroRhodoDB v1.5.0's 5,466-protein corpus covers Type-I microbial rhodopsins in the
functional classes already modeled by the DB's curation scheme. Five additional,
taxonomically/functionally distinct rhodopsin-superfamily groups are **not** systematically
represented: **viral rhodopsin, schizorhodopsin, xenorhodopsin, bestrhodopsin, MerMAID**.//
This task searches public sequence databases for members of these five families that are
(a) not already in the corpus or in `external_validation`, and (b) pass independent
sequence-based confirmation of the retinal-binding Schiff-base lysine.

Per the agreed v1.6.0 fix plan, results are delivered as a **separate candidate table**
(`novel_family_candidate`, built in Stage 2) — **the main `protein` corpus and its
membership counts (5,466) are unchanged.** Nothing in this layer is auto-promoted into the
corpus; it is a curator-facing watchlist.

## Method

1. **Seed HMMs** (prior session): built per family from 2–6 reference sequences each
   (`seeds/fasta/{family}.hmm`, built with `hmmbuild` from MAFFT alignments).
2. **Two independent search sources**, both filtered identically where applicable:
   - **EBI HMMER `hmmscan`/`hmmsearch` REST API**, hosted "uniprot" sequence database
     (`fetch_and_filter_candidates.py`).
   - **Local `hmmsearch`** (HMMER 3.4, `-E 1e-10`) against a freshly downloaded **current
     Swiss-Prot** release (575,748 reviewed sequences; `local_swissprot_search.py`).
3. **Filters applied, in order:**
   - `is_included` (HMMER's own inclusion threshold) — EBI path only; Swiss-Prot tblout is
     already restricted to E ≤ 1e-10 at search time.
   - **Pfam architecture must contain `PF01036`** (Bac_rhodopsin) — see Finding 1 below for
     why this is necessary, not optional.
   - **E-value ≤ 1e-10** (standard confident-homology threshold).
   - **Exclude already-known accessions**: union of the 5,466 `protein.source_acc` corpus
     entries and the 366-row `external_validation` table (confirmed this cycle to be the
     canonical/superset exclusion source — the previously-supplied 21-row
     `external_positives_new.tsv` is an exact subset of it, 21/21 matched).
   - **Empirical per-family length filter**: `[floor(0.6 × min(seed lengths)), ceil(1.5 ×
     max(seed lengths))]`, computed from each family's own seed `.faa` file (not an
     arbitrary round number). See `candidates/length_filter_rules.tsv`.
   - **Retinal-Schiff-base-lysine confirmation**: `hmmalign --mapali` merges each surviving
     candidate into the family's seed alignment; the retinal-K column is **re-derived per
     run** as the alignment column with maximum K-frequency across seed rows only (not
     reused from any hardcoded prior value, since merging shifts column numbering); a
     candidate passes if a `K` appears within ±2 columns of that position.

## Key methodological findings

**Finding 1 — bestrhodopsin HMM fusion-domain contamination.** The bestrhodopsin seed
proteins are ~1,150–1,244 aa rhodopsin–bestrophin **fusion** proteins. Searched as-is
against the EBI "uniprot" index, the HMM returned 16,979 hits, but **88% (13,958/15,864
included hits) carried Pfam architecture `PF01062` (Bestrophin) without `PF01036`**
— i.e., they are ordinary standalone bestrophin anion-channel proteins matched via the
non-opsin half of the fusion HMM, not rhodopsins. Requiring `PF01036` in the architecture
string (applied uniformly to all 5 families, near-redundant for the other 4) collapsed this
from 15,796 false "candidates" to 7. The same artifact reproduced independently in the
Swiss-Prot search (all 9 raw bestrhodopsin hits are standalone bestrophins, e.g. Q8YSU5,
P72926, P76146) and was correctly removed by the length filter (bestrophins are far shorter
than the full fusion protein) and would also have failed the retinal-K check.

**Finding 2 — the EBI-hosted "uniprot" HMMER index is a stale, non-live snapshot.** After
domain+E-value+exclusion filtering, 1,795 unique candidate accessions remained across the 5
families. Individual UniProt REST lookups (the batch `accessions=` endpoint silently drops
unresolvable accessions with HTTP 200 and no error — a separate pitfall worth flagging for
any future batch UniProt use) showed **1,787/1,795 (99.6%) are now `Inactive`/`DELETED`**
(`deletedReason: "Not part of a reference proteome"`, a large-scale TrEMBL redundancy
cleanup) and 7 are `DEMERGED` to a single live replacement. **Resubmitting fresh EBI jobs
reproduced byte-identical funnel counts at every stage** — the hosted index itself is
periodically rebuilt and was not refreshed by resubmission. This is a genuine data-currency
limitation of the EBI HMMER service, not a pipeline defect, and it means a substantial pool
of candidate hits (e.g. 124 viral_rhodopsin, 261 schizorhodopsin "novel" accessions) could
not be evaluated further because their sequences are no longer retrievable under those
accessions.

**Finding 3 — Swiss-Prot supplement resolves the open "already known?" question.**
Searching current, reviewed-only Swiss-Prot (stable, no demerge/deletion churn) directly
against the exclusion set showed that **all 29 schizorhodopsin and all 43 xenorhodopsin raw
Swiss-Prot hits are already in the v1.5.0 corpus** (spot-checked directly against the DB:
P69051, P69052, P96787, P29563, O93740 — well-known Archaerhodopsins/Bacteriorhodopsins —
all confirmed present in `protein.source_acc`). This resolves the question raised mid-sweep:
these are catalogued, not novel. Swiss-Prot's 9 bestrhodopsin hits reproduce Finding 1 (pure
bestrophins, fail length filter). Viral_rhodopsin and MerMAID returned 0 raw Swiss-Prot hits
at E ≤ 1e-10.

## Final result

**Combining both sources, exactly 1 candidate passes every filter:**

| family | source | query acc. | resolved (live) acc. | organism | E-value | length | retinal-K |
|---|---|---|---|---|---|---|---|
| xenorhodopsin | EBI uniprot snapshot | Q8YSC4 (Q8YSC4_NOSS1) | **A0ACD6B968** | *Nostoc* sp. PCC 7120 (cyanobacterium) | 3.49×10⁻⁷⁵ | 261 aa | pass (window `FSKVG`) |

Independently re-verified directly against UniProt's live record for A0ACD6B968: entry is
**active** (TrEMBL), same organism and 261-aa length, protein name "Bacteriorhodopsin", and
**UniProt's own Pfam cross-reference confirms `PF01036` (Bac_rhodopsin)** — an independent
line of evidence beyond this pipeline's own architecture filter.

All other 4 families yield 0 final candidates from either source. Full combined per-family
funnel (`candidates/combined_funnel_summary_v160.tsv`):

| family | EBI raw hits | EBI incl. | EBI PF01036+ | EBI E≤1e-10 | EBI excl.known | EBI resolved-live | EBI length-pass | EBI retinalK-pass | SwissProt raw(E≤1e-10) | SP excl.known | SP length-pass | SP retinalK-pass | **final** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| viral_rhodopsin | 246 | 155 | 155 | 124 | 124 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **0** |
| schizorhodopsin | 3,536 | 3,015 | 3,015 | 543 | 261 | 0 | 0 | 0 | 29 | 0 | 0 | 0 | **0** |
| xenorhodopsin | 9,820 | 8,179 | 8,093 | 3,313 | 1,519 | 1 | 1 | 1 | 43 | 0 | 0 | 0 | **1** |
| bestrhodopsin | 16,979 | 15,864 | 189 | 8 | 7 | 1 | 1 | 0 | 9 | 9 | 0 | 0 | **0** |
| MerMAID | 4,637 | 2,892 | 2,892 | 232 | 137 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **0** |

## Caveats and limitations (disclosed, not computationally resolvable within this task)

- **This is a computational flag, not a validated new family member.** A0ACD6B968 should
  undergo curator literature/sequence review (and ideally functional validation) before any
  future promotion into the main corpus; it is surfaced here only as a candidate.
- **EBI index staleness leaves a real coverage gap.** 124 + 261 + 137 = 522 (viral_rhodopsin
  + schizorhodopsin + MerMAID) accession hits that passed domain/E-value/exclusion filtering
  could not be evaluated at all because their accessions are now deleted/demerged in the
  EBI-hosted snapshot and were not independently traceable to replacement sequences at
  scale. Some of these may include genuine positives now living under different accessions.
  A full resolution would require either a live-UniProt-backed HMMER service or a
  locally-hosted current TrEMBL search (full TrEMBL is ~250M+ sequences — far larger than
  the 575,748-sequence Swiss-Prot subset used here as a tractable, currently-reliable
  stand-in).
- **Swiss-Prot-only supplement is reviewed/stable but small.** It does not provide
  TrEMBL-level breadth; it only confirms/refutes "already known" status and catches
  reviewed-space novel hits.
- **No wet-lab confirmation.** Retinal-K presence is necessary but not sufficient evidence
  of a functional light-driven ion pump/sensor; this cannot be established computationally.

## Files

- `candidates/novel_family_candidates_FINAL_v160.tsv` — the 1-row final candidate table
  (source for the Stage-2 `novel_family_candidate` DB table).
- `candidates/combined_funnel_summary_v160.tsv` — full per-family funnel, both sources.
- `candidates/filter_funnel.tsv`, `candidates/novel_family_candidate_counts.tsv`,
  `candidates/ebi_job_stats.tsv`, `candidates/accession_resolution_log.tsv` (1,795-row
  audit trail), `candidates/length_filter_rules.tsv`, `candidates/retinalK_mapali_columns.tsv`
  — EBI-path intermediate detail.
- `candidates/swissprot_funnel.tsv`, `candidates/swissprot_candidates_full.tsv` — Swiss-Prot
  path detail.
- `candidates/A0ACD6B968_verify.json` — live UniProt record for the final candidate.
- `candidates_v1_stale_STALE_DATA/` — preserved first-run outputs (kept for the audit
  record; superseded by the fresh-job rerun which reproduced identical numbers, confirming
  Finding 2).
- `fetch_and_filter_candidates.py`, `local_swissprot_search.py`, `build_final_layer.py` —
  pipeline scripts (fully documented inline).
