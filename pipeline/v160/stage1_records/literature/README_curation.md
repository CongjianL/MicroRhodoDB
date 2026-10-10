# v1.6.0 Literature Curation — Methods and Summary

Produces `curation_proposals_literature.tsv` (70 rows) from four linked tasks (A–D), covering the
referee-driven E1 targeted fixes, the 101-landmark evidence sweep, the 21 external-positive
cross-check, and the 41 linkless-E1 citation cleanup. All claims are grounded in live API data
(Europe PMC, UniProt REST, RCSB, Crossref, NCBI) cached to disk (`cache/`, full raw HTTP audit
trail under `cache/raw/*.json`) so every PMID/DOI/snippet is independently re-verifiable offline.
Script: `generate_proposals.py`. Helper module: `lit.py`.

## Task A — Targeted E1 fixes (11 named records + 2 construct flags + 1 bonus finding)

14 actionable proposals + 1 needs_manual (CryoR2 bonus finding, out of the brief's explicit
scope). Every snippet is a verbatim quote confirmed present (Python `in`) in the real fetched
abstract or full text; two were full-text (Europe PMC XML), not abstract-only (CryoR1).

Highlights: UmOps1/UmOps2 → E1 proton_pump_outward (UmOps3 stays as-is, confirmed non-electrogenic
by the same paper); Glycylhalorhodopsin corrected proton_pump→anion_pump; SpaR E4→E1 proton_pump;
NOP-1 E4→E1 photoreceptor_no_transport; exoKCR1/ExoC110T/GtCCR2/CryoR1 E5→E1; HcKCR1 and
ExoC110T confirmed single-point mutants (engineered_flag) with wild-type accession proposals.

**Two citation errors in the input brief, caught and corrected:**
- GtCCR2 (L1K1K8): brief named PMID 39232582 (a 2024 structural follow-up) as primary; the actual
  primary electrophysiological characterization is **PMID 29078348**, found by this session's
  literature search. Both are consistent (cation_channel); 39232582 is now cited as secondary.
- HcKCR1 wild-type characterization: external-positives file cited **PMID 35750865**, which is
  wrong; the correct PMID for Govorunova et al. 2022 Nat Neurosci (DOI
  10.1038/s41593-022-01094-6) is **35726059**, confirmed via Crossref DOI lookup.

## Task B — 101-landmark sweep

**Method:** 15 landmarks were already hand/script-verified in a prior audit pass
(`auditC_landmark_function_check.tsv`). Of those, 7 are the exact same records already resolved
in Task A (cross-referenced, not duplicated) and 2 concern clade/membership placement rather than
literature evidence (logged as out-of-scope informational rows — a placement question, not a
citation question). The remaining 6 "verdict=correct" landmarks had the right func_class but were
not yet linked to E1; each gets a clean evidence_level promotion citing the already-identified
PMID. The other 86 landmarks were swept **programmatically**: UniProt FUNCTION comments tagged
`ECO:0000269` (direct experimental evidence on this protein, not `ECO:0000305` "by similarity")
were extracted and keyword-classified into the DB's func_class vocabulary, then compared to the
current DB call.

**Result:** 14 confirmed already-E1-and-consistent (logged only in the full sweep table, not the
proposals table), 69 have no `ECO:0000269` this-protein evidence at all (no_change, nothing
actionable — expected, since most landmarks' FUNCTION comments are curator-inferred `ECO:0000305`
even for very well-established proteins such as bacteriorhodopsin itself), 0 clean same-class
promotions beyond the 6 pre-identified ones, and 1 genuine classifier-flagged mismatch
(O74870, "Meiotically up-regulated gene 73 protein" — UniProt's only `ECO:0000269` evidence
describes a role in meiosis, not any rhodopsin transport/sensory function; left `needs_manual`,
no function call is asserted). Full 101-row audit trail: `task_b_landmark_sweep_full.tsv`.

**Keyword classifier was iteratively corrected this session** after two false positives were
caught by inspecting the actual UniProt text: (1) no negation handling — "has **no**
proton-pumping activity" was initially misread as a proton-pump signal (Q18DH5); (2) a vocabulary
gap — "photorepellent response" wasn't recognised as a sensory-function phrase (Q5V5V3). Both
were fixed (negation guard + added keyword) and re-verified against the DB's existing sensory
calls, which the corrected classifier now confirms rather than contradicts.

**Notable finding beyond the brief's explicit scope — carO is likely mis-annotated at E1 in the
current (v1.5.0) corpus.** Two accessions (Q70LL3, S0ELR6; Fusarium/Gibberella fujikuroi, a
carotenoid-gene-cluster "opsin-like protein") currently carry `evidence_level=E1,
basis=experimental:this_protein, func_class=proton_pump` citing PMID 15133714. Direct reading of
that paper's abstract (this session) shows it is a gene-expression/genetics study only: carO
transcription is light-induced, but "targeted mutagenesis of carO produced no apparent phenotypic
modification, including no change in the photoinduction of carotenoid biosynthesis" — a **null**
knockout phenotype — and UniProt's own FUNCTION comment independently states the role is "not
known yet" (Probable only). No ion-transport or sensory assay was ever performed on carO itself;
the existing snippet used to justify E1 appears to have been pulled from the abstract's generic
background sentence about opsins as a family, not a carO-specific result. Proposed fix: downgrade
`evidence_level` E1→E4, `basis` experimental→motif_only (func_class=proton_pump stays
motif-supported — the DTD helix-C motif independently predicts proton_pump in 1,155/1,155 DTD
records corpus-wide, so this is not a func_class change, only an evidence-tier correction), and
clear `exp_class` (no real transport-direction data exists). S0ELR6 is also one of the 41
linkless-E1 Task D records; its Task D row cross-references this Task B proposal instead of
independently "filling in" the same PMID as if it confirmed E1.

## Task C — 21 external positives

**Scope:** only external accessions ≥95% identical to an existing corpus member are the "same
protein" and eligible for a corpus-record correction/confirmation; the other 19 (~30–70% identity)
are distinct, non-redundant proteins and are handled by the novel-family candidate layer
(bestrhodopsin/schizorhodopsin/xenorhodopsin/viral_rhodopsin/MerMAID seed families), not Task C.

Exactly 2 of 21 qualify: UOK93384.1 (99.6% id → A0ABF7PQA2) and 6EDQ_A (99.7% id → A0A0C3TEH9).
Both corpus records are already correctly E1 with matching func_class — confirmed, no_change.
For UOK93384.1, a data-quality note is logged (not a MicroRhodoDB error): this session's own
fresh sequence re-verification (Task A) found UOK93384.1 is an *exact* 0-mismatch match to
A0ABF7PQ82 (exoKCR1), not A0ABF7PQA2 as this file's precomputed `nearest_corpus_acc` states;
A0ABF7PQA2 is itself a confirmed C110A point mutant of A0ABF7PQ82, which explains the near-miss.

PMID 35114111 (ChRmine, Cell 2022) was traced to the 7W9W_A external-positive row (33.1%
identity, out of Task C's actionable scope) — noted as context for the novel-family workstream,
not used as a corpus correction.

## Task D — 41 linkless E1 records

**Method:** each record's semicolon-joined `pmid` string is split; UniProt ECO-evidence-code
artifacts (`0000269`, `0000305`, etc. — 4-zero-prefixed tokens, not real PMIDs) are dropped;
duplicates removed preserving order; the two known compilation/review papers (**PMID 30349080**,
Inoue 2018 Sci Rep; **PMID 33741996**, Karasuyama/Kojima 2021 Commun Biol — both reused across
dozens of unrelated records) are excluded from the primary slot unless nothing else is available.
The first remaining non-compilation PMID is taken as primary; doi/title/year/abstract are fetched
live via Europe PMC (cached). The record's own pre-existing `snippet` text is reused if it
verifies verbatim in the fetched abstract; otherwise a keyword-matched sentence is substituted, or
(last resort) the abstract's first sentence, explicitly flagged `snippet_source="... unverified
relevance"` — still a real, verbatim sentence, never fabricated text.

**Result:** 15 of 41 get a clean primary PMID+DOI fill-in (1 more, S0ELR6, cross-references the
Task B carO downgrade instead — see above), 25 remain `needs_manual` because only the two
compilation papers are cited in the raw data and no protein-specific primary paper is present —
an honest outcome, not a processing failure; these need a dedicated literature search per record,
out of scope for an automated pass.

**Two previously-flagged PMID ambiguities, resolved this session:**
- **PMID 30158607** ("Measurements of the gravitational constant using two independent methods",
  Nature 2018 — an unrelated physics paper) does **not** appear anywhere in the 41-record Task D
  table; it does not contaminate any current citation. The only GtACR1-adjacent PMID actually
  present is **30158697** (L1J207), which independently resolves to "Structural mechanisms of
  selectivity and gating in anion channelrhodopsins" (Kim et al. 2018, DOI
  10.1038/s41586-018-0504-5) — a genuine, directly relevant GtACR structural paper, and a
  companion paper (same 2018 Nature issue) to PMID 30158696 / DOI 10.1038/s41586-018-0511-6
  ("Crystal structure of the natural anion-conducting channelrhodopsin GtACR1", Li et al.). Both
  are legitimate primary GtACR1 citations from different groups; 30158697 is **not** an error.
- **PMID 35114111** (ChRmine, Cell 2022) was traced to Task C's external-positive set (7W9W_A),
  not to any of the 41 Task D records (confirmed absent from `e1_without_publication_link.tsv`).

## Headline counts (curation_proposals_literature.tsv, 70 rows)

| Task | Rows | Actionable proposal | needs_manual | out_of_scope / informational |
|---|---|---|---|---|
| A | 15 | 14 | 1 (CryoR2 bonus) | — |
| B | 11 | 8 | 1 (O74870) | 2 (membership-only) |
| C | 3 | 3 (2 confirmed no_change + 1 scoping note) | — | — |
| D | 41 | 15 (+1 cross-ref) | 25 | — |

Supporting artifact (not a proposal table): `task_b_landmark_sweep_full.tsv` — full 101-row audit
trail (bucket + DB state + note per landmark), for sign-off reviewers who want to see every
landmark's disposition, not only the actionable subset.

## Known limitations / explicitly not verified

- Task B's keyword-based func_class classifier is a heuristic, not a per-record literature read;
  after this session's two bug fixes (negation handling, vocabulary gap) it was re-validated
  against all 5 of its own original flags, but it was not independently stress-tested against the
  full UniProt function-comment vocabulary beyond what appeared in this corpus's 101 landmarks.
  Any future UniProt text with a different negation phrasing or synonym could still slip through;
  all classifier-driven items remain `needs_manual` or confirmation-only, never auto-applied.
- Task D's fallback snippet selection (keyword-matched or first-abstract-sentence) is weaker
  evidence than Task A's individually-read snippets; it is explicitly labeled by
  `snippet_source` so sign-off reviewers can tell which of the 15 primary-assigned rows have a
  pre-vetted snippet vs. a programmatically-selected one.
- The 19 Task C external positives below 95% identity were not evaluated for corpus corrections
  (by design, out of scope) — they feed the separate novel-family candidate layer.
- No new wet-lab or structural validation was performed; all findings are literature/database
  cross-checks only.

## Files produced

- `curation_proposals_literature.tsv` — 70-row proposals table (this task's main deliverable).
- `task_b_landmark_sweep_full.tsv` — full 101-landmark audit trail supporting Task B.
- `cache/` — all underlying API responses (UniProt, Europe PMC, RCSB, Crossref, NCBI), keyed for
  offline re-verification.
