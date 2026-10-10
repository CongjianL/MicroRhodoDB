# MicroRhodoDB website redesign: PR-0 baseline audit

Stage: PR-0 (baseline, data audit and architecture freeze). Read-only. No scientific data were modified and nothing was deployed.
Dataset: MicroRhodoDB v1.6.0 (frozen). Website version under development: "website 2.0" (separate from the dataset version).
Audit date: 2026-10-10. Branch: `website/pr-0-baseline`, based on `fab9182`.

Machine-readable evidence is in `docs/website/baseline/`:

| File | Content |
|---|---|
| `pr0_db_audit.json` | Every metric below, with the SQL that produced it (`web/scripts/pr0_baseline_audit.py`) |
| `legacy_walkthrough_local.tsv`, `legacy_walkthrough_live.tsv` | Legacy Playwright walkthrough results |
| `legacy_ux_metrics.json`, `screenshots/legacy_*.png` | 15 legacy screenshots (5 routes x 375/768/1440 px) and per-view metrics (`web/scripts/legacy_screenshots.py`) |
| `poc_results.json`, `screenshots/poc_*.png` | Mol* and phylotree.js proof-of-concept results (`web/poc/verify_poc.py`) |
| `frozen_sha256_fab9182.txt`, `tracked_index_fab9182.txt` | Checksums of the 176 non-SQLite files under `releases/` and `refpkg/`, and the `git ls-files -s` index at baseline |

## 1. Provenance

| Item | Finding |
|---|---|
| Repository | `https://github.com/CongjianL/MicroRhodoDB`, branch `main` |
| HEAD | `fab9182044c45670c869c8778fd8d48932bd35b8` (single commit, 2026-10-10). Tag `v1.6.0` (annotated, object `a4214e92`) points to it |
| Tracked files | 334. A fresh clone is identical to the locally built v1.6.0 publication tree |
| Uncommitted user changes | None in the clone. The working tree used for this audit holds only the gitignored release SQLite files (copied in for testing) and the new PR-0 files |
| Live site | `https://congjianl.github.io/MicroRhodoDB/` returns 200 (meta-refresh redirect to `site/`). `/site/` returns 200 |
| Live vs repo | `site/app.js` (sha256 `f43ebe69...`) and `site/data.js` (sha256 `485b2296...`, 4,350,576 bytes) are byte-identical to HEAD. So the site the user judged poor is the v1.6.0 legacy browser itself |
| Pages source | Not confirmable without authentication (the Pages API returns 404 unauthenticated). There is no `.github/workflows/`, so the source is almost certainly "deploy from branch `main`, root". **The owner needs to confirm this in Settings > Pages** |
| Custom domain | None (`CNAME` returns 404) |
| Root redirect | `index.html` uses `<meta http-equiv="refresh" content="0; url=site/">`. A hash on the root URL (for example `/MicroRhodoDB/#/record/P02945`) is dropped by this redirect. Documented permalinks use `/site/#/record/...`, which works |

### 1.1 Official SQLite inputs

The release databases are gitignored and must be obtained separately (`BINARIES.md`). For this audit they were taken from the verified v1.6.0 archive build and placed at `releases/<ver>/db/`. All six SHA-256 values match `BINARIES.md` (`sha256sum -c` OK). The v1.6.0 DB is:

`releases/v1.6.0/db/microrhododb_v1.6.0.sqlite`, SHA-256 `379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f`, opened only with `?mode=ro`.

**Missing dependency (blocks CI data builds, not PR-1 locally).** The repository has **no GitHub Release**: the Releases API returns `[]` and `releases/download/v1.6.0/microrhododb_v1.6.0.sqlite` returns 404. The download links in `BINARIES.md` are therefore dead, and a GitHub Actions job cannot fetch the official DB. Options (owner decision, see section 8):

1. Publish the v1.6.0 GitHub Release with the deposit assets (DB + archive + checksums) that were already prepared. CI then downloads and verifies the SHA-256.
2. Follow plan section 14.4: commit provenance-bearing, pre-generated static data (`data/v1.6.0/`, with the input SHA-256 and exporter commit in `manifest.json`), and have CI build only the frontend from it.

Until one of these exists, any CI export step must stop with `BLOCKED_DATA_SOURCE`. It must not fall back to `site/data.js`.

### 1.2 Reference tree

| Item | Value |
|---|---|
| File | `refpkg/MR_RT_003/tree/MR_RT_003.rooted.treefile`, 17,517 bytes, SHA-256 `c56196970698decea8384c1cad97545794268e6d8a2df2b195e7d35d5ded9aef`, MD5 `f47ef7649dc5b01a6ea58e9c0ea1c238` |
| DB `reference_tree` row | `MR_RT_003`, status `canonical_release`, IQ-TREE 2.3.6, Q.pfam+F+R9, 472 tips |
| `reference_tree.treefile_md5` | `712f53eb06fcb0277c79f188dd4bb574`. This is the MD5 of `run1.treefile` (the unrooted primary ML tree), **not** of the rooted file. This is expected (the rooted file is derived), but the website manifest must record the rooted file's own checksum and say which file the DB MD5 refers to |
| Support label format | `SH-aLRT/UFBoot` on internal nodes (e.g. `96.2/100`). 470 internal nodes; 469 carry labels (the root does not) |
| Legacy trees | `MR_RT_001` (185 tips) and `MR_RT_002` (278 tips) are `legacy`. Their placements have `is_current=0` and must not be shown as current |

## 2. Baseline tests (recorded honestly)

| Suite | Environment | Result |
|---|---|---|
| `python -m pytest -q tests/` | Pinned env (`hmmsearch`, `hmmscan`, `diamond`, `snakemake` on PATH) | **52 passed** |
| same | Python env without the pinned bioinformatics tools on PATH | 49 passed, 3 failed (`test_family_flag_cli`, `test_cli_smoke_12_queries`, `test_snakemake_dry_run`). All three fail with "hmmsearch/hmmscan/snakemake not on PATH". These are environment failures, not data failures |
| `tests/browser_walkthrough_v160.py` (local `site/`, file:// and HTTP) | Playwright Chromium 1243 | **42 steps, 0 failed** |
| `tests/browser_walkthrough_v160.py --url https://congjianl.github.io/MicroRhodoDB/site/` | live site | **21 steps, 0 failed** (only the HTTP mode runs against a URL) |

Notes:
- The headless Chromium dependencies had to be reinstalled (`playwright install-deps chromium`) because system libraries are not persistent in this sandbox. CI will need the same step (`npx playwright install --with-deps`).
- `tests/README.md` says "45 tests" (28 + 17) and "38 checks". The current suite collects 52 tests (35 + 17), and the walkthrough runs 42 steps. This is documentation drift only. It is recorded here and not edited in PR-0.

## 3. Legacy browser inventory

| File | Bytes | gzip -9 | Role |
|---|---|---|---|
| `site/index.html` | 4,475 | n/a | Single page: nav (Browse `#/`, Sequence search `#/search`, Novel-family candidates `#/novel`, About `#/about`), all four views in one DOM, side panel `aside#detail` |
| `site/app.js` | 20,788 | 7,260 | Routing, filters, pagination, record panel, 3-mer prefilter (300) + Smith-Waterman (BLOSUM62, gap 11/1, top 10) on the main thread |
| `site/data.js` | 4,350,576 | 958,648 | `window.MRDB = {meta, columns(39), rows(5466), seqs(5466), pubs, status(9), func_classes(11), clades(19), novel}`, loaded and parsed on every route |
| `site/style.css` | 2,413 | n/a | Fixed side panel, 12-13 px text |

Exporter: `tools/build_site_v160.py` (88 lines, read-only SQL over `v_master` + `protein`, `mrdb_accession`, `function_evidence`, `retinal_pocket_summary`, `membership`, `novel_family_flag`, `assertion_publication` + `publication`, `release_metadata`, `status_definition`, `func_class_definition`, `clade`, `novel_family_funnel`, `novel_family_candidate`). Preserve it for regression comparison (plan 11.2).

### 3.1 Legacy data fidelity

`site/data.js` was compared cell by cell against `v_master` (ordered by `mrdb_acc, source_acc`):

- 5,466 rows. 30 of 39 columns come from `v_master`: **0 mismatched cells**.
- 9 columns are derived outside `v_master`: `reviewed`, `e2_ref`, `e2_identity`, `override_rule`, `pocket_string_br`, `status_reason`, `novel_family_flag`, `is_mrdb_representative` (= `source_acc == mrdb_accession.representative_source_acc`), and `clade_confidence` (computed by the exporter: `confident` if `clade_id` is non-empty, `tentative` if only `tentative_clade_id` is set, else `none`).
- Publications: 106 accessions and 255 link rows. This **equals** the DB's active links (`assertion_publication.is_active=1`: 255 rows, 106 distinct `source_acc`). The legacy publication export is complete; "only 106" is the true number of accessions with links.
- **No PDB fields** are exported: no `protein_pdb`, `pdb_structure` or `structure` content. None of the 472 PDB links reach the website.
- No tree, tip, placement detail, clade robustness, AFDB status, pLDDT-per-residue or predicted-structure data are exported.

Conclusion: the legacy data are correct but incomplete. The redesign problem is missing content and poor presentation, not corrupted data.

### 3.2 Legacy UX measurements (live site, headless Chromium)

| Route | 375 px overflow | 768 px overflow | 1440 px overflow | Notes |
|---|---|---|---|---|
| `#/` Browse | 818 px | 425 px | 0 | 9-column table does not reflow |
| `#/record/MRDB000001` | 818 px | 425 px | 0 | Record exists only as a side panel. At 375 px it starts at x = -30 px (left edge clipped); see `legacy_record_MRDB000001_375.png` |
| `#/search` | 0 | 0 | 0 | |
| `#/novel` | 1,692 px | 1,299 px | 627 px | Overflows even on desktop |
| `#/about` | 0 | 0 | 0 | |

- Every route downloads the full ~0.96 MB gzip (4.35 MB raw) `data.js`, including About. Load time was about 1.45-1.57 s to network-idle on this connection.
- No console errors on any route.
- There is no homepage, statistics, tree, structure or standalone record page.

## 4. Data audit: official v1.6.0 SQLite

All values come from `pr0_db_audit.json`, which stores the SQL for each one.

### 4.1 Plan section 1.3 headline metrics

| Metric | Plan | DB | SQL basis |
|---|---|---|---|
| Records | 5,466 | 5,466 | `v_master` |
| Counted | 5,460 | 5,460 | `v_counted` (`counts_eligible=1`; the 6 engineered constructs are excluded) |
| MRDB accessions | 5,299 | 5,299 | `mrdb_accession`; also `COUNT(DISTINCT mrdb_acc)` in `accession_map` |
| Type-I members | 3,089 | 3,089 | `v_typeI_member` = core 2,704 + architecture_supported 381 + curated 4 |
| Candidates | 1,379 | 1,379 | `v_typeI_candidate` = unresolved 897 + architecture_supported 273 + plain 209 |
| Boundary family | 509 | 509 | `v_boundary_family` |
| Heliorhodopsins | 386 | 386 | `v_heliorhodopsin` |
| Decoy/rejected | 103 | 103 | `membership_status='decoy_or_rejected'` |
| E1 counted / total | 88 / 91 | 88 / 91 | `evidence_level='E1'` in `v_counted` / `v_master` |
| E2 / E3 / E4 / E5 counted | 109 / 1,143 / 1,050 / 3,070 | 109 / 1,143 / 1,050 / 3,070 | E2 total is 112 (3 engineered) |
| Publications | 121 | 121 | `publication` |
| Active links | 255 | 255 | `assertion_publication.is_active=1` (support 141, compilation 109, context 3, conflicting 1, unresolvable 1) |
| Watchlist | 181 | 181 | `novel_family_candidate`; 0 of them are in the corpus |
| Tree tips | 472 | 472 | treefile, `tips.tsv` and `tree_node(kind='tip')` all agree, 472/472 |
| Level-1 clades | 17 | **19 rows at `level=1`** | See 4.5: 17 `MR_CLD3_001`-`017` + 2 backbone groups `MR_CLD3_B01`, `B02` |

Engineered constructs: 6 records (`v_engineered`). Four are `typeI_member_core` and two are `typeI_candidate`; all have `counts_eligible=0`. The constructs and their wild types are:
- A0A6I8WFQ3, A0A7M4DUE4, A0A7M4DUE9 → A0A6P3CW41
- A0A8X6EH36 → A0AAJ0LKB3
- A0ABF7PQ84, A0ABF7PQA2 → A0ABF7PQ82

Note the status split between denominators: `typeI_member_core` is 2,704 over all records but 2,700 over counted records; `typeI_candidate` is 209 vs 207.

### 4.2 MRDB to source accession mapping

- `accession_map`: 5,466 rows, all `is_current=1`, `source_database='UniProt'`. 0 source accessions are missing from `v_master`, 0 `v_master` rows are missing from the map, and 0 `mrdb_acc` disagreements.
- Multiplicity (sources per MRDB accession): 1 → 5,170; 2 → 104; 3 → 18; 4 → 4; 5 → 1; 6 → 1; 7 → 1. This is the many-to-one relation, e.g. MRDB000001 = {P02945, B0R5N9}.
- Representative: `mrdb_accession.representative_source_acc` (P02945 for MRDB000001). 5,299 records are representatives and 167 are not. Legacy `#/record/MRDB000001` focuses the representative, P02945.
- **There are two different "representative" concepts, and the UI must label them separately**: the MRDB representative (P02945) and `e1_representative` (B0R5N9 for MRDB000001, the E1 sequence-cluster representative).
- `exact_duplicate_of` is non-empty for 6 records (e.g. B0R5N9 → P02945).

### 4.3 Experimental structures (PDB)

| Check | Result |
|---|---|
| `protein_pdb` rows / distinct (source_acc, pdb_id) pairs | 472 / 472 (no duplicate links) |
| Distinct PDB IDs | 438. All have metadata in `pdb_structure` (0 missing, 0 orphans) |
| PDB ID format | All 4-character, upper case |
| Source accessions with ≥1 PDB | 66 (all in the corpus). They belong to **58 MRDB accessions** |
| Links per accession | 1 → 27 accessions, 2 → 11, 3 → 7, 4 → 5, 5 → 5, 6 → 3, 8, 12, 14 (×2), 23, 41, 53 → 1 each; **P02945 → 174** |
| PDB IDs shared by several source accessions | 414 have 1 accession, 14 have 2, 10 have 3 (e.g. `8R0K`: A0A1I3DJQ0 and A0ABY1EHF9). The structure index must therefore map `pdb_id → [source_acc]` |
| MRDB-level union | MRDB000001 = 174 (P02945) + 1 (B0R5N9, `4Y9H`) = 175 distinct PDB IDs |
| Methods | X-ray 393, EM 32, solution NMR 7, electron crystallography 6. `has_retinal`: 382 yes, 56 no. Resolution is null for 7 entries (NMR), which the UI must show as "not applicable" |
| `structure.n_pdb_structures` vs actual distinct links | 0 mismatches |
| `rep_pdb_id` / `highest_res_pdb_id` outside the linked set | 0 / 0. The structure-integrity gate (plan 7.2) passes on the source DB |
| `structure` table coverage | 4,886 of 5,466 records. The 580 without a row are 386 heliorhodopsins, 98 decoys, 48 core members, 23 boundary, 18 unresolved candidates, 4 architecture-supported members and 3 candidates. **One PDB-linked accession, A0A2R4S913 (heliorhodopsin), has no `structure` row**, so experimental-structure presence must be derived from `protein_pdb`, not from `structure.has_experimental_structure` |
| Example values | P02945: `rep_pdb_id` 5ZIM (X-ray, 1.25 Å), `highest_res_pdb_id` 7Z09 (1.05 Å) |

### 4.4 Predicted structures

- `afdb_model`: 5,466 rows. 4,397 have status `ok` (version 6, `seq_match=1`, `model_url` like `https://alphafold.ebi.ac.uk/files/AF-<acc>-F1-model_v6.pdb`). 1,069 are `no_model`. `v_master.afdb_model_id` agrees with the table in all 5,466 records.
- Combined structure coverage:
  - AFDB-only (no PDB link): 4,336
  - neither PDB nor AFDB: 1,064
  - PDB: 66
- `predicted_structure`: 2 ESMCFold2 models, for A0A9X2L7U0 and B0R633. Their `pdb_file` paths (`structures/*.pdb`) are **not present in the repository**. The website can show the metadata but cannot serve these coordinates unless the files are found (open question).
- Network: RCSB (`files.rcsb.org`, `models.rcsb.org`) returns `Access-Control-Allow-Origin: *`. AFDB serves files to browsers (it returns 403 to the default curl user agent but 200 to a browser user agent and inside Chromium). The AFDB API reports the latest version as 6 for P02945, which matches the DB.

### 4.5 Reference tree, clades and placements

- 472 tips = 394 `cl0.6_representative` + 57 `anchor_characterized` + 4 `seed` + 15 `outgroup_heliorhodopsin` + 2 `boundary_schizorhodopsin` (`tips.tsv`).
- **Two tips are not corpus records**: `QBQ84355` and `QBQ84358` (GenBank schizorhodopsin tips). Tip-to-record navigation must handle "reference tip without a record".
- `clade_tip` has 457 rows. 472 − 457 = 15, the heliorhodopsin outgroup tips. These 15 are exactly the 15 records without a `record_clade` row (verified as set equality).
- `record_clade` has 5,451 rows: 4,996 `placement` + 455 `reference_tip` (457 clade tips − the 2 non-corpus tips).
- `clade` table: 19 rows at level 1 and 30 at level 2 (scheme MR_CLD3, tree MR_RT_003).
  - Level 1 = the 17 refpkg clades `MR_CLD3_001`-`017` plus `MR_CLD3_B01` (haloarchaeal BR/archaerhodopsins backbone group, 4 tips, 97 records, including P02945) and `MR_CLD3_B02` (Amoebozoan DTE backbone group, 4 tips, 5 records).
  - In the refpkg, B01 and B02 are listed in `MR_CLD3_subclades.tsv` with `parent_clade=backbone`, not in `MR_CLD3_clades.tsv` (17 rows). The refpkg has 32 subclade rows = DB level 2 (30) + B01/B02.
  - In `clade_tip`, the B01/B02 tips are under `clade_id='backbone_unassigned'` with `subclade_id='MR_CLD3_B01'/'B02'`. There are 35 `backbone_unassigned` tips in total: 8 in B01/B02 and 27 in no group.
  - **The plan's "17 level-1 clades" is therefore correct for the refpkg, but the DB and the legacy UI show 19 level-1 entries.** The website must present this as "17 level-1 clades + 2 backbone groups". The tree contract (below) encodes it.
- Placements: 4,996 current (`is_current=1`, tree MR_RT_003, one per record).
  - `clade_call`: assigned 4,337, outgroup_heliorhodopsin 456, unassigned 199, tentative 4.
  - The 18,653 non-current placements (MR_RT_001/002 and superseded MR_RT_003 model runs) must not be shown as current.
- `v_master.clade_id` uses `''` (1,310 counted records) and `NULL` (15) with different meanings:
  - `NULL` = outgroup reference tip with no `record_clade` row
  - `''` = placed or reference-tip record with no confident clade (distant_assigned 718, outgroup_heliorhodopsin 456, unassigned 105, reference tips outside level-1 clades 27, distant_tentative 4)
  - `tentative_clade_id` is set for 720 records
  - The exporter must turn these into explicit enums, not blanks.
- Clade function consensus (`clade.consensus_status`, v1.6.0) at level 1:
  - `consensus` 7 (003, 004, 006, 011, 012, 013, B01)
  - `mixed` 3 (007, 009, 017)
  - `single_E1` 2 (010, 016)
  - `no_E1` 7 (001, 002, 005, 008, 014, 015, B02)
- MR_CLD3_017 (Fungal rhodopsins CarO/LR/NOP-1-like): `mixed`, 1,646 records assigned, 4 E1 records, min cross-replicate Jaccard 0.52. It carries the robustness caveat.

### 4.6 Regression fixtures resolved from SQLite (plan 13.2)

| Accession | MRDB | Status / evidence / function | Clade | PDB IDs (from `protein_pdb`) |
|---|---|---|---|---|
| P02945 | MRDB000001 (repr.) | member_core / E1 / proton_pump | MR_CLD3_B01 | 174 |
| B0R5N9 | MRDB000001 | member_core / E1 / proton_pump; exact duplicate of P02945 | MR_CLD3_B01 | 1 (4Y9H) |
| A0A1I3DJQ0 (CryoR1) | MRDB000238 | member_curated / E1 / proton_pump_inward | MR_CLD3_007 | 5 (8R0K-8R0O) |
| L1K1K8 (GtCCR2) | MRDB001687 | member_curated / E1 / light_gated_channel | none (no confident or tentative clade) | 2 (8YEJ, 8YEK) |
| A0A3G1I4H9 (GtCCR4) | MRDB002499 | member_curated / E1 / light_gated_channel | tentative MR_CLD3_002 | 1 (8YEL) |
| A0ABF7PQ82 (exoKCR1) | MRDB003606 | member_curated / E1 / light_gated_channel | tentative MR_CLD3_002 | 1 (8ZAO) |
| A0ABF7PQA2 (engineered, WT A0ABF7PQ82) | MRDB003608 | candidate / E1 / light_gated_channel, `counts_eligible=0` | tentative MR_CLD3_002 | 3 (9CDC-9CDE) |
| A0ABF7PQ84 (engineered, WT A0ABF7PQ82) | MRDB003607 | candidate / E1, `counts_eligible=0` | tentative MR_CLD3_002 | 2 (8ZAP, 8ZAQ) |
| A0AAP2RB57 (schizorhodopsin) | MRDB003484 | member_core / E5 / unresolved | MR_CLD3_001 | 0 |
| Multi-PDB (DB-selected) | | | | W8VZW3 53, N0DKS8 41, P42196 23 |
| AFDB-only (DB-selected) | | Q53461 (MRDB000053, pLDDT 98.06), U5TV41, W0FV18 | | 0 |
| No PDB and no AFDB (DB-selected) | | A0A060JDQ1 (MRDB001781, member_core), A0A0K3CUU3, A0A150G9K7 | | 0 |

## 5. Proofs of concept (plan 11.1)

A scratch app in `web/poc/` (to be deleted when PR-2 creates the real `web/` app) was built with pinned versions:
- Vite 8.3.4, @vitejs/plugin-react 6.1.2, React 18.3.1, TypeScript 5.9.3 (strict, `tsc --noEmit` clean)
- `phylotree` 2.6.0, `molstar` 5.13.1, sass 1.93.2
- `base: '/MicroRhodoDB/site/'`, output to `dist/site/`

It was served under `/MicroRhodoDB/site/` and checked in headless Chromium (SwiftShader WebGL).

| Test | Real asset | Result |
|---|---|---|
| phylotree.js, rectangular | `MR_RT_003.rooted.treefile` (copied byte-identically; SHA-256 checked) | 472 tips (472 unique), 470 internal labels parsed (`SH-aLRT/UFBoot` strings), 472 tip text nodes in SVG, render 124 ms, 0 console errors |
| phylotree.js, radial | same | 472 tips, 130 ms, 0 errors |
| Mol*, experimental | PDB 1C3W (linked to P02945 in `protein_pdb`), RCSB ModelServer BinaryCIF | Loaded, 6,219 atoms (protein + lipids/waters/RET), about 2.1 s, 0 errors |
| Mol*, predicted | `afdb_model.model_url` for P02945 (`AF-P02945-F1-model_v6.pdb`) | Loaded, 1,995 atoms (262 aa), about 1.9 s, 0 errors |

Bundle (raw / gzip -9):

| Chunk | Raw | gzip -9 | Loaded on |
|---|---|---|---|
| App entry | 146 KB | 47 KB | Every route |
| phylotree + d3/jquery/lodash dependencies | 299 KB | 98 KB | Tree routes only |
| Mol* | 3.56 MB | 977 KB (+ 69 KB CSS) | **Structure routes only** (lazy, verified from request logs) |

Findings:
- Both libraries work with the approved stack. No alternative is needed.
- phylotree.css must be imported. Without it, SVG paths render as filled black wedges.
- phylotree 2.6.0 pulls in jQuery, lodash, underscore and moment (about 98 KB gzip). This is acceptable for a lazily loaded tree route. The homepage tree preview should be a lightweight static SVG generated by the exporter from the same Newick, so Home does not load phylotree.
- Mol* is about 1 MB gzip and must stay behind a dynamic import (plan 9.3). Default coloring is uniform. pLDDT coloring for AFDB models and ligand/RET focus are PR-3 work.
- Vite 8 (Rolldown) handled the Mol* SCSS and dynamic imports without problems.

## 6. Issues found (classified for the redesign; nothing fixed in PR-0)

| ID | Severity | Issue | Addressed in |
|---|---|---|---|
| A1 | P0 (dependency) | No GitHub Release or assets. `BINARIES.md` links 404. CI cannot fetch the official DB | Owner decision; PR-1/PR-7 |
| A2 | P0 | Website exposes no PDB data (472 links, 438 PDB IDs, 66 accessions) | PR-1, PR-3 |
| A3 | P0 | No phylogeny view of MR_RT_003; placements, outgroup and robustness are not explained | PR-1, PR-4 |
| A4 | P1 | Monolithic 4.35 MB `data.js` on every route | PR-1, PR-2 |
| A5 | P1 | Horizontal overflow: Browse 818 px at 375 px, Novel 627 px even at 1440 px; record panel clipped on mobile; no standalone record page | PR-2, PR-3 |
| A6 | P1 | "17 vs 19 level-1 clades": DB/legacy show B01/B02 as level-1 rows while the refpkg treats them as backbone subclades | Contract (section 7 of `WEB_DATA_CONTRACT.md`); confirm with owner |
| A7 | P2 | `clade_id` blank vs NULL vs tentative semantics are implicit | PR-1 exporter enums |
| A8 | P2 | `structure` lacks a row for PDB-linked A0A2R4S913 and 579 others; `predicted_structure.pdb_file` files are absent | Contract rule; owner question |
| A9 | P2 | Root redirect drops hash fragments | PR-2/PR-7 (JS redirect that preserves `location.hash`) |
| A10 | P3 | `tests/README.md` test counts are stale (45/38 vs 52/42) | PR-6 docs |
| A11 | P3 | `reference_tree.treefile_md5` refers to `run1.treefile`, not the rooted file | Document in manifest; no data change |

## 7. Frozen-file and checksum verification

At the end of PR-0:
- All 176 non-SQLite files under `releases/` and `refpkg/` match `frozen_sha256_fab9182.txt`.
- The 6 release DBs match `BINARIES.md`.
- `git diff fab9182 -- releases refpkg` is empty.

Output: `baseline/frozen_check.txt`.

## 8. Decisions requested from the owner before PR-1

1. **Data source for CI**: publish the v1.6.0 GitHub Release (recommended) or approve committed, provenance-bearing pre-generated `data/v1.6.0/`?
2. **Pages source**: confirm the current setting (branch `main` / root assumed). Approve switching to GitHub Actions in PR-7?
3. **Level-1 clade presentation**: approve "17 level-1 clades + 2 backbone groups (B01, B02)" as the display rule?
4. **ESMCFold2 files** (`structures/A0A9X2L7U0_esmfold.pdb`, `structures/B0R633_esmfold.pdb`): are they available somewhere for publication? Otherwise the site shows metadata only.
5. Approve PR-1 (deterministic exporter) to start.
