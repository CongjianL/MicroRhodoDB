# PR-1 validation report: deterministic scientific data exporter

Branch `website/pr-1-exporter` (from PR-0a `2527237`). Dataset v1.6.0 (frozen). Not pushed, not deployed.
PR-2 has not been started.

## 1. Status

| Gate / item | Status | Evidence |
|---|---|---|
| G1.1 Source set 5,466 = `v_master`; 5,299 MRDB; 5,460 counted | PASS | `test_source_set_and_accessions` |
| G1.2 `accessions.json` = `accession_map` row for row; representatives = `mrdb_accession` | PASS | same |
| G1.3 PDB sets for all 5,466 records = `protein_pdb`; metadata = `pdb_structure`; MRDB000001 union 175; 58 MRDB with PDB | PASS | `test_pdb_associations_per_record`, `test_pdb_metadata` |
| AFDB metadata (4,397 ok / 1,069 no_model) | PASS | `test_afdb_metadata` |
| Predicted structures: both ESMCFold2 models resolved from `releases/v1.0/structures/`, byte copies, SHA-256 = frozen manifest | PASS | `test_predicted_structures` |
| G1.4 472 tips = 422 level-1 + 8 backbone-group + 27 unclustered + 15 outgroup; tip roles 394/57/4/15/2; `clade_state` 7 states sum to 5,466; 19 + 30 clade rows, all columns = DB | PASS | `test_tips`, `test_clade_state`, `test_clades` |
| Tree census 471 internal (incl. root) / 469 support labels / 2 unlabelled (root + 25-tip node) | PASS | `test_tree_file_and_stats` (regex count independent of the exporter parser) |
| Support-label audit vs IQ-TREE `run1` (17 disagreements; MR_CLD3_017 100/100 vs 50.3/72) | PASS (finding, see section 3) | `test_support_audit_against_iqtree` (independent bipartition parser) |
| G1.5 28 summary metrics and 15 distributions recomputed independently with pandas; baselines from audit section 4.1 | PASS | `test_summary_metrics_recomputed`, `test_summary_distributions_recomputed` |
| Every `v_master` cell (35 columns x 5,466) equals its record path | PASS | `test_every_v_master_cell` |
| G1.6 Legacy `site/data.js` oracle: 39 columns x 5,466 rows, strict equality with only T1-T7 (test oracle only, never a data source) | PASS, 0 mismatches | `test_legacy_oracle_cells`, `test_legacy_oracle_publications` |
| Publications 121; 255 active links; 7 inactive links never support | PASS | `test_publications_file` |
| G1.7 Watchlist (181) disjoint from the corpus | PASS | `test_watchlist_disjoint` |
| G1.8 JSON Schema on all 5,315 JSON payloads; generated `types.ts` up to date; `tsc --strict --noEmit` clean | PASS | `test_json_schema_all_payloads`, `test_typescript_types_up_to_date`; tsc run manually (TypeScript 5.9.3) |
| G1.8 Two CLI exports into fresh directories are byte-identical (incl. `export_manifest.json`); no wall-clock timestamps; no absolute paths; canonical JSON | PASS | `test_second_export_byte_identical`, `test_no_wall_clock_or_absolute_paths`, `test_json_canonical_encoding`, `test_export_manifest_covers_every_file` |
| G1.9 176 frozen files unchanged; DB SHA-256 unchanged after export | PASS | `test_frozen_files_and_db_unchanged` |
| Fail-closed exit codes (wrong SHA / missing DB -> 2 `BLOCKED_DATA_SOURCE`; foreign output dir -> 4) | PASS | three failure-mode tests |
| Release fetcher (verified download, 404, checksum mismatch, already present) | PASS | `tests/test_fetch_release_db.py` (file:// mirrors) |
| **CI data source (official v1.6.0 GitHub Release)** | **BLOCKED_DATA_SOURCE** | section 2 |

Test totals: `tests/test_web_export.py` 31 passed, `tests/test_fetch_release_db.py` 4 passed; full repository
suite `pytest -q tests/` **87 passed** (52 pre-existing + 35 new) with the pinned `mrdb` env on PATH.

Export size (clean tree, `git_dirty: false`): 5,319 files, 25,521,831 bytes (5,299 record files, 21 MB; `records-index.json` 1.36 MB, 173 KB gzip).

## 2. CI data source: BLOCKED_DATA_SOURCE

- GitHub API `releases/tags/v1.6.0` -> 404; the repository has no releases.
- `web/scripts/fetch_release_db.py` (live) -> `BLOCKED_DATA_SOURCE: .../releases/download/v1.6.0/microrhododb_v1.6.0.sqlite: HTTP 404`.
- `.github/workflows/web-data.yml` (validation only: fetch + verify, export, pytest, types check; `contents: read`; no
  build, no Pages, no deploy) will fail at the fetch step with that message until the owner publishes the Release
  with `microrhododb_v1.6.0.sqlite` attached. Expected size and SHA-256 are read from `BINARIES.md`, not from the
  download. Nothing has been pushed, so the workflow has not run on GitHub.
- All PR-1 validation above ran locally against the checksum-verified DB (`379a2543...dce17f`).

## 3. Scientific finding for owner review (frozen data unchanged)

Full write-up: `WEB_BASELINE_AUDIT.md` section 10.2; data: `pr1/support_label_audit.json`,
`phylogeny/support_audit.json`.

- The rooted reference tree attaches SH-aLRT/UFBoot labels to the wrong node on **17 of 470** non-root internal
  nodes (one-node shift along the rerooting path, caused by ete3 node features not moving with `set_outgroup`).
  The DB `tree_node` table (unrooted run1) is correct.
- Among the 49 clade rows only **MR_CLD3_017** is affected: DB support 100/100, IQ-TREE 50.3/72. With IQ-TREE labels
  the PRIMARY rule would not recover it (it splits into 48-, 30- and 5-tip clades). The other 16 level-1 clades are
  unaffected. Subclades and the robustness grid were not re-derived.
- Owner decisions requested before PR-4: (a) display IQ-TREE run1 support per bipartition, or (b) display rooted-file
  labels with caveats on the 17 nodes; and the caveat wording for MR_CLD3_017. Any re-derivation of clades is a
  future scientific release, outside the website project.

## 4. Documentation corrections in this PR

- PR-0a error corrected: the second unlabelled internal node is a non-root 25-tip node (former run1 top node),
  not a root child (`WEB_BASELINE_AUDIT.md` sections 1.2 and 10.1; `WEB_DATA_CONTRACT.md` section 7.1).
- `WEB_DATA_CONTRACT.md`: the JSON Schema is declared normative; section 10 lists the as-built deviations (typed
  `year`/`agreement`, `architecture` always an object, curated-override object, publication tie-breaks, inactive
  link roles, added record fields, excluded UniProt cross-reference strings, exit codes).
- New `WEB_DATA_EXPORT.md` (commands, inputs, outputs); `WEB_TEST_INVENTORY.md` PR-1 row.

## 5. Files

New: `tools/export_web_data.py`, `web/src/data/schemas/web-data.schema.json`, `web/src/data/types.ts` (generated),
`web/scripts/{schema_to_ts.py, fetch_release_db.py, pr1_support_label_audit.py}`,
`tests/{test_web_export.py, test_fetch_release_db.py}`, `.github/workflows/web-data.yml`, `web/.gitignore`
(`public/data/`), `docs/website/{WEB_DATA_EXPORT.md, PR1_VALIDATION_REPORT.md, pr1/support_label_audit.json}`.
Modified: `docs/website/{WEB_BASELINE_AUDIT.md, WEB_DATA_CONTRACT.md, WEB_TEST_INVENTORY.md}`.
Not modified: `releases/**`, `refpkg/MR_RT_003/**`, the DB, classifications, phylogeny, `site/**`.
Generated data are not committed (`web/public/data/` is gitignored; CI regenerates them from the Release).

## 6. Known limitations

- The JSON Schema was authored once and is now maintained by hand; `types.ts` is generated from it and checked.
- Watchlist isolation is tested by identifier disjointness; watchlist entries carry no sequences to compare.
- `chain_mapping` (PDB chain/residue to UniProt) is not provided; the index says so explicitly.
- `tsc` is not yet part of CI (no Node toolchain until PR-2); it was run locally.
