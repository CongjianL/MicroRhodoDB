# MicroRhodoDB Data Model (v1.3.0, schema `v130.1`; v1.4.0 and v1.6.0 deltas at end)

> For v1.6.0 every table and column is described in the `data_dictionary` table
> (`releases/v1.6.0/tables/data_dictionary_v160.tsv`); the delta below lists what is new.

The v1.3.0 database contains **39 tables + 7 views**. They are grouped here by
scientific responsibility, not alphabetically. Authoritative DDL:
`schema/current/schema_v130.sql` (convenience copy; the immutable original is
`releases/v1.3.0/meta/schema_v130.sql`). The current release is **v1.4.0**
(schema `v140.1`), a strict superset — see the v1.4.0 delta section at the end
of this file.

Row counts below are from the shipped v1.3.0 artifact.

## 1. Core sequence / source tables

| Table | Rows | Responsibility |
|---|---|---|
| `protein` | 6,713 | One row per sequence record: accession, sequence, organism/lineage, cross-refs (Pfam, PDB, KEGG, RefSeq), seed flag. 5,361 UniProt + 1,352 MGnify pilot. |
| `sequence_source` | 6,713 | Per-record provenance: source database/release, study/sample/assembly/contig coordinates, biome, lat/lon, collection date, `sequence_sha256`, partial flag. |

## 2. QC / admission tables

| Table | Rows | Responsibility |
|---|---|---|
| `qc_feature` | 5,361 | HMM coverage, retinal-lysine presence, complete-core flag, primary architecture, raw architecture flags (UniProt proteins only). |
| `protein_architecture_flag` | 2,840 | Normalized one-row-per-flag split of `qc_feature.arch_flags`. |
| `environmental_admission` | 1,352 | MGnify pilot admission decisions: `admission_state` (501 `environmental_candidate` / 851 `environmental_unresolved`), frozen classifier score + release, score band. **Isolated from membership by design.** |

## 3. Membership / population tables

| Table | Rows | Responsibility |
|---|---|---|
| `membership` | 5,361 | **Authoritative membership.** `membership_status` (7 controlled values), score, category, architecture class/route, reason code. Byte-identical to v1.2.0. |
| `active_population` | 5,361 | Policy classification derived from membership: `is_active` / `is_core` / `is_candidate` (4,881 active Type-I). |

Membership statuses: `typeI_core` (2,656), `typeI_core_architecture_supported`
(377), `typeI_candidate` (207), `typeI_candidate_architecture_supported`
(276), `typeI_candidate_unresolved` (1,365), `heliorhodopsin` (377),
`decoy_or_rejected` (103).

## 4. Redundancy tables

| Table | Rows | Responsibility |
|---|---|---|
| `redundancy` | 5,361 | Four dereplication levels with representative flags: `exact_nr` (SHA-256 of normalized sequence), `std_90`, `intermediate` (65% id), `backbone` (40% id) — MMseqs2 cov-mode 0. |

## 5. Phylogenetic tables

| Table | Rows | Responsibility |
|---|---|---|
| `reference_backbone` | 186 | Backbone representatives with diversity statistics and anchor flags. |
| `reference_tree` | 2 | Tree registry: MR_RT_001 (auditable IQ-TREE2 Q.PFAM+F+R6 backbone, 185 tips) and MR_RT_002 (registered orphan, not promoted). |
| `tree_node` | 368 | Nodes with kind, label, SH-aLRT/UFBoot supports, branch length. |
| `tree_edge` | 367 | Edges with parent/child nodes and lengths (jplace-numbered). |
| `placement` | 4,326 | Per-protein epa-ng placements: track (`primary`/`exploratory`), best edge, LWR, credible set, `can_generate_active_label`, clade. |
| `reference_clade` | 60 | Named clades linked to `tree_node`/`tree_edge`, with anchor counts and parent clade. |
| `reference_clade_member` | 161 | Anchor (Tier-A) membership per clade. |
| `reference_clade_tip` | 986 | Full tip membership per clade (subtree traversal). |

## 6. Annotation tables (subfamily / function / structure)

| Table | Rows | Responsibility |
|---|---|---|
| `subfamily_assignment` | 2,990 | Evidence-gated subfamily labels; `is_active=1` only via an allowed path (primary track + active protein). |
| `function_assignment` | 4,119 | Rule-based function calls with motif/phylogenetic/structural/experimental support flags, discordance, confidence. |
| `structure` | 4,886 | Per-protein structure summary: architecture, fusions, experimental-structure counts, representative PDB + resolution, retinal presence. |
| `pdb_structure` | 438 | PDB entry metadata (method, resolution, ligands, retinal, year). |
| `protein_pdb` | 472 | Protein↔PDB links. |
| `predicted_structure` | 2 | ESMFold models (B0R633, A0A9X2L7U0) with mean pLDDT; PDB files in `releases/v1.0/structures/`. |
| `seed` | 15 | Seed set registry (12 Type-I + 3 heliorhodopsin) with subfamily/function class. |
| `subfamily` | 2,990 | **Legacy** v1.1-carried subfamily calls (superseded by `subfamily_assignment`; retained for audit). |
| `function` | 5,361 | **Legacy** v1.1-carried function/motif/spectral columns (superseded by `function_assignment`; retained for audit). |

## 7. Evidence / publication tables

| Table | Rows | Responsibility |
|---|---|---|
| `tier_a_evidence` | 63 | Curated Tier-A evidence records (assay, ion, direction, evidence ref, curator). |
| `tier_a_assertion` | 63 | Structured assertions parsed from evidence (assay type, transported ion, direction, strength). |
| `tier_a_holdout` | 34 | Designated Tier-A holdout positives with rationale (used in WS2 regimes). |
| `publication` | 69 | Publications, all DOI/PMID-resolved; `ingestion` flags `manual_verified` (11) vs `parsed_heuristic` (58). |
| `assertion_publication` | 81 | Assertion↔publication links. |
| `citation` | 10 | **Legacy** free-text citations (retained for audit). |

## 8. External-validation / benchmark tables

| Table | Rows | Responsibility |
|---|---|---|
| `benchmark_v2` | 261 | WS5 benchmark with hard negatives; full/LOCO/LOSO scores per record. |
| `external_validation` | 106 | Independent external set (E1 temporal + E2 novel-family positives, 100 negatives); exposure-audited, `ever_exposed_flag=0`; frozen scores. |
| `external_validation_metric` | 18 | Sensitivity/specificity at frozen thresholds with Wilson CIs. |
| `holdout_assignment` | 15,110 | Per-fold scores across 6 leakage-controlled regimes (random5, std_90, intermediate_65, taxonomic_phylum, reference_clade_msc, reference_clade_root). |
| `holdout_metric` | 264 | Fold + pooled metrics with Wilson CIs and adequacy gates. |

## 9. Provenance / release tables

| Table | Rows | Responsibility |
|---|---|---|
| `release_metadata` | 10 | Release keys: `database_release=1.3.0`, `schema_revision=v130.1`, `base_release=1.2.0`, status vocabularies, membership authority, deprecated column, environmental pilot summary. |
| `build_provenance` | 37 | Per-table build record: source data, script, algorithm, parameters, upstream deps, release, timestamp. **The authoritative record of the (currently missing) builder code.** |
| `sqlite_sequence` | 6 | SQLite-internal AUTOINCREMENT bookkeeping (not scientific data). |

## Views (public query surface)

| View | Rows | Definition |
|---|---|---|
| `v_typeI_active` | 4,881 | All active Type-I (core + candidate statuses). Never includes decoys. |
| `v_typeI_core` | 3,033 | `typeI_core` + `typeI_core_architecture_supported`. |
| `v_typeI_candidates` | 1,848 | The three candidate statuses. |
| `v_rejected_or_decoy` | 103 | Decoy/rejected records (incl. 5 HSP30) for benchmark/audit only. |
| `v_active_subfamily` | 1,813 | Subfamily labels with `is_active=1`. |
| `v_active_function` | 4,096 | Function assignments with `is_active=1`. |
| `v_master` | 6,713 | Backward-compatible wide join (ALL proteins; filter by `membership_status`, never `module`). |

## Legacy / deprecated elements (documented, NOT deleted)

- **`membership.module`** — deprecated since v1.2.0; never controls membership
  (`release_metadata.deprecated_column`). Retained for backward compatibility.
- **`subfamily`, `function`** — v1.1-era flat annotation tables, superseded by
  the evidence-gated `*_assignment` tables. Retained for audit.
- **`citation`** — superseded by `publication` + `assertion_publication`.
- **v1.1 redundancy cluster IDs** — invalidated by the v1.2.0 exact-NR
  correction; not comparable across releases.

Schema cleanup of these elements belongs to a future database version, not to
repository maintenance.

## v1.4.0 delta (schema `v140.1`)

v1.4.0 is a strict superset of v1.3.0: every v1.3.0 table is carried
content-identical (verified by 35 frozen-table row-hash checks in
`tests/release_v140.py`). Documented exceptions: the
`reference_tree.MR_RT_002.status` lifecycle flip (`registered_orphan` →
`canonical_release`) and `release_metadata` identity keys. Authoritative DDL:
`releases/v1.4.0/meta/schema_v140.sql`.

Changed row counts:

| Table | v1.3.0 → v1.4.0 | Change |
|---|---|---|
| `protein` | 6,713 → 6,818 | +105 UniProtKB 2026_03 extension records |
| `sequence_source` | 6,713 → 6,818 | +105 source rows |
| `membership` / `active_population` / `qc_feature` / `redundancy` | 5,361 → 5,466 | +105 extension rows scored by the reconstructed frozen scorer |
| `tree_node` / `tree_edge` | 368/367 → 922/920 | +554/+553 MR_RT_002 promotion |
| `reference_clade` | 60 → 115 | +55 MR_CLD2_* clades (MR_RT_002) |
| `reference_clade_tip` | 986 → 1,882 | +896 MR_RT_002 tip rows |
| `release_metadata` | 10 → 13 | +`canonical_tree_id`, `extension`, `mr_rt_002_promotion` |
| `build_provenance` | 37 → 49 | +12 v1.4.0 build records |

New tables:

| Table | Rows | Responsibility |
|---|---|---|
| `extension_delta` | 111 | Per-accession extension log: 105 admitted + 6 `demoted_or_merged`. |
| `placement_v140` | 4,335 | epa-ng 0.3.8 (LG+G) placements on MR_RT_002; frozen `placement` (MR_RT_001) untouched. |
| `qc_feature_tool` | 105 | Tool/version record for extension QC feature derivation. |

Population effects: active Type-I 4,881 → 4,977; core 3,033 → 3,085;
candidates 1,848 → 1,892. Clade namespaces: MR_CLD_* anchors to MR_RT_001;
MR_CLD2_* anchors to MR_RT_002 (now the canonical tree; MR_RT_001 remains
canonical for frozen v1.2/v1.3 placement content).

## v1.6.0 delta (schema `v160.1`)

Full column definitions: `data_dictionary` (1,232 rows, 91 tables and views, 100% coverage).

| Table / view | Rows | Content |
|---|---|---|
| `curation_v160_decision` | 622 | Every signed v1.6.0 decision (round 1 and R2) with item_id, action, recommendation, signed_by, signed_date |
| `loco_validation` / `loco_validation_record` | 126 / 76 | Leave-one-out, -subfamily-out and -clade-out estimates on the 76 unique non-engineered E1 sequences |
| `clade_function_consensus` | 49 | Per clade/subclade E1 consensus used for `clade_function` (16 consensus, 8 mixed, 19 no_E1, 6 single_E1) |
| `audit_blind` / `audit_agreement` | 120 / 8 | Blind re-annotation of the 120-record E2-E4 sample and agreement with Wilson CIs |
| `novel_family_flag` | 5,466 | Per-record family-HMM flag (139 flagged): best family HMM vs PF01036 |
| `novel_family_candidate` / `novel_family_funnel` | 181 / 5 | Watchlist of rhodopsin-like sequences outside the corpus (sequence search + Foldseek); counts unaffected |
| `foldseek_query` / `foldseek_hit` / `foldseek_funnel` | 11 / 786 / 23 | Foldseek AFDB50/MGnify queries, filtered hits (3 tiers) and per-query funnel |
| `data_dictionary` | 1,232 | Table and column definitions |
| `v_counted`, `v_call_conflict`, `v_engineered` | views | Counted records (engineered excluded), call conflicts, engineered constructs |

Changed: `membership.membership_status` gains `typeI_member_curated` (4 records, with `override_rule` and
`status_reason`); `function_evidence` gains `call_conflict`, `call_conflict_detail`, `override_rule` and new basis
labels; `record_clade.clade_function` is recomputed; `is_engineered` / `wild_type_acc` added. Removed:
`membership.alias_v14` and views `v_typeI_core`, `v_typeI_candidates`, `v_typeI_active`, `v_rejected_or_decoy`.
