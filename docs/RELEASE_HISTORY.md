# Release History

Architectural evolution of MicroRhodoDB. **Documented facts** (from release
notes, reports, manifests, validation JSONs, and the database itself) are
stated plainly; **inferred history** is marked *[inferred]*.

```text
v1.0 — notebook/research-pipeline era
v1.1 — remediation / phylogeny / benchmark extension
v1.2 — reproducible staged builder architecture
v1.3 — frozen scientific core + external validation/environmental extension
v1.4 — append-only sequence extension + MR_RT_002 promotion
```

## v1.0 — 2026-07-30 — notebook/research-pipeline era

**Facts.** First release. Built from UniProtKB 2026_02 with Pfam
PF01036.25 / PF18761.8 and 15 seeds (12 Type-I + 3 heliorhodopsin). 5,361
proteins, 12 tables, no `release_metadata` table, no checksum manifest.
Release validation: 10/10 checks pass (`releases/v1.0/meta/release_validation.json`).
Shipped with API v1.0 (`microrhododb_api.py`), benchmark TSVs, backbone
phylogeny files, 4 sequence FAAs, 2 ESMFold structures, 10 tables, 18 figures.
The build execution record is `notebooks/legacy_execution_trace/rhodo.ipynb`
(195 cells).

**[inferred]** The flat root-level layout (`api/`, `db/`, `benchmark/`, …)
reflects a research-pipeline workflow: artifacts organized by type rather than
by release, with the notebook as the de-facto builder.

## v1.1 — 2026-08-04 — remediation / phylogeny / benchmark extension

**Facts.** Supersedes and remediates v1.0 (v1.0 remains frozen). Remediated
membership (workspaces WS1/WS4, per v1.2.0 provenance), added the Type-I
backbone reference phylogeny (WS3; IQ-TREE2 Q.PFAM+F+R6, 185 tips — the same
run later registered as MR_RT_001), and redesigned the benchmark with hard
negatives (WS5; `releases/v1.1/meta/ws5_provenance.json`). Shipped API v1.1,
8 figures, data dictionary, release validation JSON. DB: 9,535,488 B.

**[inferred]** v1.1 was still workspace/notebook-driven (partial record in
`rhodo2.ipynb`); the `v11_*.parquet` workspaces it produced became the inputs
to the v1.2.0 staged builder.

## v1.2.0 — 2026-08-30 — reproducible staged builder architecture

**Facts.** Data-integrity and schema-hardening release, "rebuilt reproducibly
from preserved source inputs" by a 12-stage builder (`s01_protein.py` …
`s12_provenance.py`; per-table provenance in `build_provenance`). No new
biological expansion. Breaking correctness changes: authoritative membership
moved to `membership.membership_status` (legacy `module` deprecated); 5 HSP30
records reclassified `decoy_or_rejected`; `exact_nr_cluster` replaced with
true SHA-256 exact-NR (v1.1 values invalid); exploratory placements stopped
generating active labels. Added 7 public views and 10 new tables, CHECK
constraints, and foreign keys. Validation: V1–V20 invariants + A1–A7 API
acceptance (33 tests). Shipped `schema_v120.sql`, build manifest, release
boundaries, API v1.2. DB: 10,706,944 B.

**[inferred]** v1.2.0 is the architectural pivot: from notebooks to a staged,
provenance-recording builder — the pattern v1.3.0 reused as `build_v13_base/`.

## v1.3.0 — 2026-09-24 — frozen scientific core + external validation/environmental extension

**Facts.** Validation, provenance, and controlled-pilot release around the
frozen v1.2.0 core: `membership` byte-identical to v1.2.0 (test X6b); no
threshold or score changes. Schema `v130.1`; 52/52 release tests pass;
SHA256SUMS (17 files). Eight workstreams: WS1 external validation (106
records; specificity 1.000), WS2 leakage holdouts (6 regimes; primary
`reference_clade_msc` sensitivity 0.891 @0.86 / 0.652 @0.90), WS3 tree
provenance (MR_RT_001 fully auditable), WS4 evidence ingestion (69
publications, all DOI/PMID), WS5/6 MGnify environmental pilot (1,352 records:
976 marine + 376 soil; 501 `environmental_candidate` / 851
`environmental_unresolved`; complete isolation from membership), WS7 error
analysis (8-dimension distribution shift; 81.2% score–placement concordance),
WS8 expansion decision memo (medium marine-first expansion conditionally
recommended; confidence-tier policy proposed, **NOT applied**). API v1.3.0
adds `query_environmental`, `query_external_validation`,
`query_clade_provenance`. DB: 18,034,688 B.

**Documented adjustments:** two v1.2.0 invariants superseded by design
(`V2_membership_1to1` — environmental proteins deliberately have no
membership row; `V20_release_version` pin bump).

## v1.4.0 — 2026-10-02 — append-only sequence extension + MR_RT_002 promotion

**Facts.** Strictly additive extension of the frozen v1.3.0 core: every v1.3.0
table carried content-identical (35 frozen-table row-hash checks,
`tests/release_v140.py`), with two documented exceptions
(`reference_tree.MR_RT_002.status` lifecycle flip to `canonical_release`;
`release_metadata` identity keys). 105 new UniProtKB 2026_03 accessions
admitted by a **reconstructed frozen scorer** (`pipeline/v140/`; admission
gate: 0/5,361 score and category differences vs the frozen membership
rosetta): 52 high-confidence Type-I (48 `typeI_core` + 4
`typeI_core_architecture_supported`), 3 `typeI_candidate`, 41
`rhodopsin_like`, 1 ambiguous, 9 rejected (helio-primary); 6 demoted/merged
accessions logged in the new `extension_delta` table. Nondeterministic layers
(MMseqs2 clusters, HMMER QC) extended by assignment, never recomputed.
**MR_RT_002 promoted**: 554 nodes / 553 edges stored as parsed, 55 MR_CLD2_*
clades (100% monophyly; 4 root-side complement clades excluded, documented),
896 clade-tip rows. New `placement_v140` (4,335 rows; epa-ng 0.3.8 LG+G on
MR_RT_002; eligibility rule reproduces the frozen 4,326/4,326 baseline; 52/52
new cores placed, 37 high-confidence). MR_RT_001-side placement of new cores
skipped — the v1.1 185-tip MSA is unrecoverable (documented in
`build_provenance`). Validation: 18/18 release tests; P1–P9 recovery probes
regression unchanged (7 PASS, 2 MATCH-WITH-DIFFERENCES). API v1.4.0 adds
`query_placement_v140`, `query_extension_delta`; fixes the
`query_clade_provenance` tree join. DB: 18,759,680 B; schema `v140.1`;
SHA256SUMS (10 files).

## v1.5.0 — 2026-10-06 — status model, MR_RT_003 tree, reproducibility

Summarized in `CHANGELOG.md` and `releases/v1.5.0/`: 8-category `membership_status` (3,085 members, 1,383
candidates, 509 boundary family, 386 heliorhodopsins, 103 decoy/rejected), MR_RT_003 reference tree (472 tips),
five-level function evidence (E1-E5). Immutable base of v1.6.0.

## v1.6.0 — 2026-10-10 — function evidence, validation and access (response to review)

**Facts.** Built from the immutable v1.5.0 DB (opened read-only) plus 622 signed curation decisions
(`curation_v160_decision`; round 1 2026-10-09, round 2 "R2" 2026-10-10). Corpus, scorer, thresholds, tree and
clade assignments unchanged. Function calls: compatibility-aware conflict flag (468 records; 439 E3/E4
downgrades), curated audit rules (xeno 69 and OpsA 47 E4 -> E5 `unresolved`), `clade_function` recomputed on the
v1.6.0 E1 set (16/49 groups with consensus; 657 records lose an inherited class). E1 91 records (88 counted, 76
unique non-engineered). Membership changes only by 4 curated overrides (`typeI_member_curated`; 3,089 members /
1,379 candidates). New validation: LOCO (legacy 52/70 = 0.743), blind audit of 120 E2-E4 records (100/120 =
0.833; E4 22/40), family-HMM flag (139 records), Foldseek watchlist (786 hits; 181 `novel_family_candidate`
rows). Access: static browser, read-only API, CLI, data dictionary (1,232 rows, 91 objects), Snakemake rebuild
checked content-identical (91/91 objects). Tests 52/52; browser walkthrough 42/42. DB 33,464,320 B; schema
`v160.1`; SHA-256 `379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f`.

## Cross-release notes

- **Environmental sequencing:** the v1.0 report described environmental
  catalogues as planned for "v1.1" *[fact: stated in the v1.0 report]*; they
  actually arrived as the v1.3.0 MGnify pilot *[fact]*. The interim releases
  prioritized correctness and validation instead *[inferred]*.
- **Membership continuity:** the 5,361 UniProt proteins and their membership
  statuses are stable from v1.2.0 through v1.3.0; v1.4.0 extended the core
  append-only to 5,466 (all v1.3.0 rows content-identical; new rows added
  alongside, never edited in place).
- **Artifact growth:** 8.7 MB (v1.0) → 9.5 MB (v1.1) → 10.7 MB (v1.2.0) →
  18.0 MB (v1.3.0) → 18.8 MB (v1.4.0) → 30.9 MB (v1.5.0) → 33.5 MB (v1.6.0), tracking the shift from flat results
  to provenance-rich, validation-heavy releases.
