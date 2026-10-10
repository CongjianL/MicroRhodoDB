# PR-3 validation report: standalone Protein Entry and structure visualization

- Branch: `website/pr-3-protein-entry`, created from the accepted PR-2 commit `b5416b1` (history of PR-0 to PR-2 kept).
- Dataset: v1.6.0 (frozen). Source DB SHA-256 `379a2543...dce17f`; MR_RT_003 rooted tree SHA-256 `c5619697...5aded9aef`.
- Data export schema: 1.1.0, **unchanged**. No exporter change in this PR; the page uses only fields already exported.
- New runtime dependency: `molstar` 5.13.1 (pinned exactly; MIT).
- Status: committed locally only. Not pushed, not merged, not deployed. PR-4 not started.

## 1. Local checks vs CI

All results were run locally in the development sandbox (Linux x86_64, 16 logical CPUs, Node 22, Python 3.11.16, Playwright with Chromium 153, SwiftShader WebGL).
**No CI has run for PR-3.** The `web-data` workflow gained a fixture-integrity step and its Playwright step now runs with mocked structures (the `@live` test is excluded because `E2E_LIVE` is unset). None of these steps has executed on GitHub.

| Check | Command (from repo root unless noted) | Local result |
|---|---|---|
| Python suite, including PR-1 gate G1 | `python -m pytest -q tests/` | **89 passed** (unchanged from PR-2) |
| Generated TS types in sync with schema | `python web/scripts/schema_to_ts.py --check` | up to date |
| Structure fixtures | `python web/scripts/fetch_structure_fixtures.py --check` | 5/5 OK against `SHA256SUMS` |
| TypeScript | `npm run typecheck` (in `web/`) | 0 errors |
| Production build | `npm run build` (in `web/`) | built in about 4 s |
| Unit tests | `npx vitest run` (in `web/`) | **7 files, 72 tests passed** (PR-2: 6 files, 50) |
| Browser tests | `npx playwright test` (in `web/`) | **76 passed, 1 skipped** (PR-2: 46 passed, 1 skipped; the skip is the PR-2 mobile-menu test at 1440 px) |
| Live smoke (network) | `E2E_LIVE=1 npx playwright test --grep @live` | **1 passed** (real RCSB 5ZIM and AlphaFold DB AF-P02945-F1) |
| Frozen files | `sha256sum -c docs/website/baseline/frozen_sha256_fab9182.txt` | **176/176 OK** |
| Reference package | `sha256sum -c refpkg/MR_RT_003/SHA256SUMS` | all OK |
| Source DB | `sha256sum releases/v1.6.0/db/microrhododb_v1.6.0.sqlite` | `379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f` (matches) |
| No changes to frozen or legacy trees | `git diff --stat b5416b1 -- releases refpkg pipeline site` | empty |
| Whitespace | `git diff --cached --check` | clean (the verbatim structure fixtures are marked `binary` in `web/tests/fixtures/structures/.gitattributes`, so their trailing spaces are kept byte-exact) |
| Performance and contrast audit | `PERF_LIVE=1 python web/scripts/pr3_perf_audit.py --out docs/website/pr3 --runs 5 --baseline <same-machine PR-2 audit>` | 0 console errors, 0 contrast failures, Mol* never loaded before the click |

Environment notes (as in PR-2): the pinned conda env is on PATH for pytest; Chromium needed `LD_LIBRARY_PATH=/opt/conda/lib` in this sandbox; browser tests need the PR-1 export in `web/public/data` and a build in `web/dist`.

## 2. What was implemented

### 2.1 Route and deep links

- `#/record/<MRDB accession | source accession>` is now the full Protein Entry page (the PR-2 interim view is removed).
- Query parameters, all optional and validated:
  - `section=overview|sequence|experimental|predicted|phylogeny|evidence|publications` scrolls to that section;
  - `structure=pdb:<ID>|afdb|pred` preselects the structure in the viewer (it does **not** load Mol*).
- A source accession focuses that source within its MRDB entry; an MRDB accession focuses the MRDB representative. Switching source adds one history entry (Back restores).
- Lower-case accessions redirect (replace) to the canonical upper-case URL and keep the query.
- Unknown or malformed IDs (`MRDB999999`, `P0294`, `%3Cscript%3E`) show a not-found page with search. They are resolved through `accessions.json` first, so no record file is requested.
- Invalid `section` or `structure` values are ignored; an unknown PDB ID falls back to the default structure.

### 2.2 Page layout

One page with a sticky section navigation (horizontal strip on mobile; the active item scrolls into view inside the strip, never the page). Sections:

1. **Overview**
   - MRDB accession and the table of all source accessions in the entry, each with its role. "MRDB representative" and "E1 representative" are separate labels and fields.
   - Engineered constructs link to their wild type, and wild types list their variants.
   - Protein, organism, lineage and the GTDB match with release, level and agreement.
   - Membership status with its DB definition; classifier score and status reason. Curated overrides are shown separately from the classifier call.
   - Function class; release provenance (first release, release added, v1.6.0 change).
2. **Sequence and motifs**
   - Sequence in blocks of 10 with position numbers; copy and FASTA download (the FASTA uses the release header).
   - Helix-C motif, motif class and retinal-site residue.
   - BR-reference pocket string (20 positions, with an explicit note that the mapping onto this sequence is not exported); pocket pLDDT.
   - Architecture, fusion and TM7 coverage; engineered-construct note.
3. **Experimental structures**
   - Sortable, filterable table of every PDB association: ID, title, method, resolution, year, retinal state and links to RCSB, PDBe and mmCIF, plus a "View in 3D" button.
   - "This source" vs "All sources of this MRDB entry" toggle. MRDB000001 shows 174 for P02945 and 175 for the union, with 4Y9H attributed to B0R5N9.
   - The compact viewer (section 2.3) sits above the table.
4. **Predicted structures**
   - AlphaFold DB model card: model ID and version, global pLDDT labelled "mean model confidence; not resolution", residue range, sequence-match flag, creation date, and links.
   - The 2 release models (B0R633, A0A9X2L7U0) are labelled with the DB `method` and the verbatim DB `note`, mean pLDDT and SHA-256, and are shown separately from experimental structures.
5. **Phylogenetic placement**
   - Placement state (reference tip / confident / tentative / unassigned), level-1 clade and subclade, and placement statistics. The 95% credible set shows its edge count only, because its members are not exported.
   - For MR_CLD3_017: the support caveat with IQ-TREE run1 SH-aLRT 50.3 / UFBoot 72, which fails the thresholds SH-aLRT ≥ 80 and UFBoot ≥ 95.
   - On-demand mini tree reusing the PR-2 preview:
     - reference tips are highlighted as the tip;
     - placed records highlight only the clade arc and are never drawn as tips;
     - the tree title and caption state the placement (for example "tentative placement near MR_CLD3_017 (clade arc only; not a tree leaf)"). The arc stroke is the same for confident and tentative placements; clades failing the support thresholds keep the PR-2 hatching.
6. **Functional evidence**
   - Functional class, E1-E5 level with its DB definition, and function basis.
   - E1 experimental class and E1 representative, E2 transfer reference, and clade function (E3/E4 reasoning).
   - Override rule with the number of records it applies to; v1.4 class.
   - Call conflicts, the curated membership override with its rationale, and the engineered-construct policy, each where present.
7. **Publications**
   - Grouped as "supporting evidence" vs "other links", with DOI/PubMed links and link roles.

Also: JSON export of the record file, breadcrumbs, and a page title per record.

### 2.3 Structure viewer (Mol* 5.13.1)

- Mol* is loaded only on the "Load 3D viewer" click, as a separate dynamic chunk (`molstarViewer-*.js`, 3,102 KiB raw / 853 KiB gzip).
  - Home, Browse, About and record pages never request it before the click (E2E and perf audit).
  - Only the Mol* plugin core is used (no full plugin UI). The controls are our own.
- One selector covers every structure for the focused source: all PDB entries, the AFDB model and the release model. The selection is mirrored in the URL (`structure=`).
- Sources and fallbacks:
  - **PDB:** BinaryCIF from `models.rcsb.org`, falling back to mmCIF from `files.rcsb.org`.
  - **AFDB:** the exported `model_url`.
  - **Release models:** served from the site (`data/v1.6.0/structures/predicted/*.pdb`).
- Each URL has a 30 s timeout. The phases idle / starting / loading / ready / error are announced through an `aria-live` status.
- Errors state the cause (HTTP status, timeout, parse error) and offer Retry, coordinate download and external links.
- Controls:
  - representation: Cartoon / Surface / Ball and stick;
  - ligand toggle (disabled when there is no ligand);
  - colouring: by chain, or pLDDT confidence with the AFDB 4-band legend (predicted models only);
  - Reset view; PNG snapshot; Download coordinates.
- Release models store pLDDT as 0-1. The browser rescales the B-factor column to 0-100, keeping PDB column widths, before colouring.
  - Tested: the CA mean equals the DB `mean_plddt` within 0.1 for both models.
- Residue highlighting is deliberately not offered: v1.6.0 has no validated PDB chain/residue to UniProt mapping. The page says so.
- Mol* is credited with its licence and citation under the viewer.

## 3. Validation cases

| Case | Record(s) | What is verified | Where |
|---|---|---|---|
| Many PDB entries | MRDB000001 / P02945 (174), B0R5N9 (4Y9H) | counts 174 focused / 175 union; default 5ZIM; table filter/sort; View in 3D (4Y9H); load from mocked BinaryCIF; switch to AFDB with pLDDT | `record.spec`, `entry.test` |
| No structures | MRDB000003 (A0A5N6KXX2: no PDB, AFDB `no_model`) | explicit empty states; no viewer, no external request | `record.spec` |
| AFDB only | MRDB000009 (Q5V4H7) | default AFDB; pLDDT colouring and legend | `record.spec` |
| Multi-accession | MRDB000249 (7 sources, all tentative; A0ACD1IKA6 without AFDB) | source table, switch focus, Back restores, per-source structure options | `record.spec` |
| Engineered ↔ WT | A0A6I8WFQ3 ↔ A0A6P3CW41 | variant and WT links both ways | `record.spec` |
| Curated override | A0A1I3DJQ0 (MRDB000238) | override shown separately from the classifier call | `record.spec` |
| Tentative MR_CLD3_017 | A0A135LS53 (MRDB000015) | caveat, 50.3/72 vs ≥ 80/≥ 95, arc-only highlight with no tip | `record.spec`, `entry.test` |
| Reference tip | P02945 | mini tree highlights the tip | `record.spec`, `entry.test` |
| Release models | B0R633 (MRDB000030), A0A9X2L7U0 (MRDB003319) | local file loads; DB method and note verbatim; pLDDT rescaled | `record.spec`, `entry.test` |
| Invalid IDs | MRDB999999, malformed, P0294 | not-found page, no `records/` request | `record.spec` |
| Deep links | `?section=…&structure=…` | reload restores section and selection; viewer stays idle | `record.spec`, `routes.test` |
| Failure states | 5ZIM, Q5V4H7 | BinaryCIF 500 to mmCIF fallback; 404 then Retry; timeout; HTML 200 parse error | `record.spec` |
| Integrity sweep | all 5,299 record files / 5,466 sources | `n_pdb`, `pdb_ids`, union sets, viewer options, AFDB option, `has_predicted`, `n_support_links` and defaults equal `records-index.json`; release models only for A0A9X2L7U0 and B0R633 | `entry.test` |

External services in tests:
- E2E tests answer RCSB/AFDB requests from committed real files in `web/tests/fixtures/structures/`:
  - 5zim.bcif, 5ZIM.cif, 4y9h.bcif, AF-P02945-F1 and AF-Q5V4H7-F1;
  - 911 KiB in total, with `SHA256SUMS` and `SOURCES.txt`;
  - the fetch script is `web/scripts/fetch_structure_fixtures.py`.
- Any other external request returns 404, and the shared fixture fails the test on it.
- The `@live` test checks the real endpoints and is excluded by default.

## 4. Scientific constraints: evidence

| Constraint | How it is enforced | Test |
|---|---|---|
| MRDB representative ≠ E1 representative | separate role labels in the source table | `record.spec` (MRDB000001, MRDB000249) |
| All experimental PDB associations shown | table built from the record's `pdb` lists; union across sources with attribution | `entry.test` sweep (all 5,466 sources), `record.spec` (174/175) |
| No invented structure-residue mapping | no residue highlighting; explicit "no chain or residue mapping … is claimed" text | code review and screenshots (the text is not asserted by a test) |
| Predicted ≠ experimental | separate sections and selector groups; pLDDT stated as confidence, not resolution | `record.spec` |
| Release model provenance | DB `method` and `note` verbatim; file SHA-256 shown | `record.spec`, `entry.test` |
| E1-E5 provenance | level with DB definition; supporting publications counted from the record | `record.spec`, `entry.test` (`n_support_links`) |
| Tentative placements and MR_CLD3_017 | separate state; caveat with 50.3/72 and thresholds; arc-only highlight | `record.spec`, `entry.test` |
| Placements never drawn as tips | `treeHighlight` returns a tip only for reference tips | `entry.test` |
| Frozen data untouched | no exporter change; schema 1.1.0 unchanged | frozen checksums 176/176, refpkg, DB SHA-256, empty `git diff` |

## 5. Performance

Full tables: `docs/website/pr3/perf_audit.md` (machine-readable `perf_audit.json`).
- Method: Chromium at 1440×900, cold cache, 5 runs per route, loopback server without compression. gzip -9 sizes are computed.
- The PR-2 columns were re-measured **on the same machine** from a worktree at `b5416b1` (`pr2_baseline_same_machine.json`). This machine is slower than the one used for the PR-2 report, so absolute ready times are higher than those in PR2_VALIDATION_REPORT.md for both builds.

Page load before any viewer interaction:

| Route | PR-3 total gzip | PR-2 total gzip | PR-3 ready (median) | PR-2 ready (median) |
|---|---|---|---|---|
| Home `#/` | 251.5 KiB | 248.9 KiB | 430 ms | 378 ms |
| About | 75.7 KiB | 75.0 KiB | 271 ms | 281 ms |
| Browse | 454.7 KiB | 454.0 KiB | 491 ms | 493 ms |
| Record `#/record/P02945` | 422.6 KiB | 399.4 KiB | 393 ms | 345 ms |
| Record `#/record/MRDB000001` | 422.6 KiB | 399.4 KiB | 422 ms | 359 ms |
| Record MRDB000003 / 000009 / 000249 / A0A135LS53 | 415-416 KiB | n/a | 358-381 ms | n/a |

Notes:
- **Record pages grew by 23 KiB gzip.** The RecordPage chunk is now 66.3 / 18.4 KiB (PR-2: 12.1 / 3.7), and the page also loads `evidence-index.json` (23.9 KiB raw).
- **`accessions.json` dominates record transfer:** 1,112 KiB raw, about 0.3 MiB gzip, and it is still loaded on every record route (PR-2 deviation D-12, unchanged).
- **Home code is unchanged.** The 52 ms Home difference falls within the spread of these runs (About and Browse moved in the other direction); it was not investigated further.
- Contrast and errors: 0 text-contrast pairs below AA on all 11 routes (minimum 4.65:1), and 0 console errors.

Structure viewer, from the click to the structure being rendered (medians of 5; software WebGL via SwiftShader, so GPU-backed browsers should be faster; GPU timings were not measured):

| Case | External coordinates | Mol* chunk + init | Click to rendered |
|---|---|---|---|
| MRDB000001 5ZIM, mocked | 88.6 KB BinaryCIF | 1.46 s | 8.4 s |
| MRDB000001 5ZIM, live RCSB | 88.6 KB BinaryCIF | 1.45 s | 8.6 s |
| MRDB000009 AFDB Q5V4H7, mocked | 149 KB PDB | 1.45 s | 4.3 s |
| MRDB000001 AFDB P02945, live | 167 KB PDB | 1.45 s | 4.2 s |
| B0R633 release model (local) | 143 KiB raw / 30.4 KiB gzip | 1.45 s | 3.9 s |

- After the click, the viewer downloads 3,106 KiB raw / 854 KiB gzip of JS (the Mol* chunk plus tslib).
- 5ZIM is slower because Mol* builds assembly 1 (the trimer) with its lipid and retinal ligands. CPU rendering dominates; the download does not.

## 6. Responsive layout and visual review

- Machine audit: `docs/website/pr3/responsive_audit.json`. Three records (MRDB000001, MRDB000003, MRDB000249) at 375, 768 and 1440 px. In all 9 combinations `scrollWidth == innerWidth` and there were 0 console errors.
- Screenshots: `docs/website/pr3/screenshots/`, 23 PNG files:
  - full-page records at 3 widths;
  - experimental section and viewer at 3 widths;
  - viewer captures: PDB 4Y9H, AFDB P02945 and release B0R633;
  - mini tree (tip), tentative phylogeny, evidence (including the curated override) and publications.

Defects found in review and fixed in this PR:
1. **Page-level horizontal overflow at 375 px** (document 1,064 px wide). The cause was absolutely positioned `sr-only` text inside horizontally scrolling regions. Fixed by making those scroll containers `relative` (source table, sequence, PDB table, section nav).
2. **Links clipped in the PDB table at 1440 px.** The links column now has a minimum width and wraps; the View button does not wrap. The title column also has a minimum width.
3. **Active section hidden on mobile.** The active item in the section strip was off-screen; it now scrolls into view inside the strip only.
4. **Duplicated text.** The evidence definition appeared twice under the badge; removed.
5. **Header stamped into screenshots.** Sticky header and nav were repeated in stitched screenshots (test artefact only); hidden during element captures.

Known cosmetic item left as it is: on the mini tree, the "017" arc label is partly overlapped by the highlight arc.

## 7. Fields shown as "Not available" (frontend-only decision)

The approved scope kept schema 1.1.0 and the exporter unchanged. These items are therefore shown as "Not available in the v1.6.0 export" or with an explicit note, rather than computed in the browser:
- **Transmembrane segment boundaries.**
- **BR-numbering → sequence position mapping** for the 20-position pocket string. The string itself is shown.
- **Members of the 95% credible placement set.** Only the edge count is shown.
- **PDB chain/residue ↔ UniProt mapping.** Consequently there is no residue highlighting in Mol*.
- **Mutated positions of engineered constructs.**

Adding any of these requires an additive schema change in a later PR, through the exporter with tests.

## 8. Curation and implementation notes

- **Release-model naming inconsistency (curation item; data not changed).** Both release models carry `method = "ESMCFold2 (full)"`, while the `note` reads "ESMFold prediction for clade rep lacking experimental structure; …" and the files are named `*_esmfold.pdb`. The page shows both strings verbatim, so the inconsistency is visible. It should be resolved in the DB in a future release.
- **Timeout test hook.** The 30 s per-URL timeout reads `globalThis.__MRDB_VIEWER_TIMEOUT_MS` if set. Only the E2E timeout test sets it (1.5 s); it has no effect in production.
- **Website version not bumped.** `package.json` remains `2.0.0-pr2` because `manifest.website_version` is written by the exporter, which this PR does not change. Bumping only the frontend would make the two disagree. Both should be bumped together when the exporter next changes.
- **Fixtures.** The fixtures are committed (911 KiB). `--check` runs offline in CI; re-download only when RCSB or AFDB formats change.

## 9. Deviations from `WEBSITE_REDESIGN_SPEC.md` / `WEB_TEST_INVENTORY.md`

| # | Spec / plan | PR-3 as built | Reason |
|---|---|---|---|
| D-16 | Tabs per section | One page with sticky section nav and `section=` deep links | Approved decision; all content is indexable and printable, and the URL keeps the position |
| D-17 | Mol* default UI | Compact plugin core with our own controls, loaded on click | Approved decision; keeps record pages light and accessible |
| D-18 | Inventory fixture list for PR-3 (CryoR1, GtCCR2/4, exoKCR1, A0ABF7PQA2, A0AAP2RB57, W8VZW3, Q53461, A0A060JDQ1) | E2E uses the records in section 3, and the Vitest sweep covers all 5,466 sources | Each case type in the inventory list (multi-PDB, AFDB-only, no-structure, engineered, curated rationale) is covered by an equivalent record. The specific named examples are only covered by the sweep, not by individual E2E tests |
| D-19 | Residue highlighting / structure-sequence linking | Not offered | No validated mapping in v1.6.0 (section 7) |
| D-20 | — | `accessions.json` still loaded on record routes | Unchanged from D-12; a split or sharded accession map would need an exporter change (candidate for PR-6) |

## 10. Files

- **New source:**
  - `web/src/lib/entry.ts` (pure page model);
  - `web/src/features/entry/*` (sections);
  - `web/src/features/structure/{molstarViewer.ts,StructureViewer.tsx}`.
- **Modified source:**
  - `web/src/pages/RecordPage.tsx`, `web/src/app/{routes.ts,App.tsx}`, `web/src/data/loaders.ts`;
  - `web/src/features/tree/{newick.ts,TreePreview.tsx}`;
  - `web/package.json` and `package-lock.json` (molstar 5.13.1).
- **Tests:**
  - `web/tests/unit/entry.test.ts` (new) and `routes.test.ts`;
  - `web/tests/e2e/{record.spec.ts,live.spec.ts,structureMocks.ts}` (new) and `routes.spec.ts`;
  - `web/tests/fixtures/structures/` (new; `.gitattributes` marks the coordinate files binary);
  - `web/playwright.config.ts` (`@live` exclusion).
- **Tooling:** `web/scripts/fetch_structure_fixtures.py`, `web/scripts/pr3_perf_audit.py` (new) and `web/scripts/perf_capture.mjs` (pr3 mode).
- **Docs:**
  - this report;
  - `docs/website/pr3/` (perf audit, same-machine PR-2 baseline, responsive audit, screenshots);
  - `WEB_TEST_INVENTORY.md`.
- **CI:** `.github/workflows/web-data.yml` (fixture check; mocked Playwright). It has not run on GitHub.
- **Not committed (generated):** `web/public/data/`, `web/dist/`, `web/node_modules/`, `web/test-results/`, `web/tests/e2e/.served/`.
