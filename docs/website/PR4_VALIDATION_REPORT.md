# PR-4 validation report: Phylogeny & Clade Explorer

- Branch: `website/pr-4-phylogeny`, created from the accepted PR-3a commit `7546a7a` (history of PR-0 to PR-3a kept).
- Dataset: v1.6.0 (frozen). Source DB SHA-256 `379a2543...dce17f`; MR_RT_003 rooted tree SHA-256 `c5619697...5aded9aef`; IQ-TREE `run1.treefile` SHA-256 `a7fe2292...a8913db0e`.
- Data export schema: **1.2.0** (additive over 1.1.0; `WEB_DATA_CONTRACT.md` section 12). Website version `2.0.0-pr4`.
- New runtime dependencies: none. The tree is rendered by our own SVG code (owner decision); phylotree.js and D3 are not used.
- Scientific scope: no new inference, no clade re-derivation, no change to any frozen file. The clade rule is reported, never applied.
- Status: committed locally only. Not pushed, not merged, not deployed. PR-5 not started.

## 1. Local checks vs CI

All results were run locally in the development sandbox (Linux x86_64, 16 logical CPUs, Node 22, Python 3.11.16, Playwright with Chromium 153).
**No CI has run for PR-4.** The `web-data` workflow now also runs `tests/test_web_phylogeny.py` (gate G4) in its pytest step and triggers on that file. None of the workflow steps has executed on GitHub.

| Check | Command (from repo root unless noted) | Local result |
|---|---|---|
| Python suite (gates G1 and G4) | `python -m pytest -q tests/` | **110 passed** (PR-3a: 89; +21 in the new `tests/test_web_phylogeny.py`) |
| Generated TS types in sync with schema | `python web/scripts/schema_to_ts.py --check` | up to date |
| Structure fixtures | `python web/scripts/fetch_structure_fixtures.py --check` | 5/5 OK against `SHA256SUMS` |
| TypeScript | `npm run typecheck` (in `web/`) | 0 errors |
| Production build | `npm run build` (in `web/`) | exit 0 |
| Unit tests | `npx vitest run` (in `web/`) | **10 files, 119 tests passed** (PR-3a: 9 files, 94) |
| Browser tests | `npx playwright test` (in `web/`) | **115 passed, 1 skipped** (PR-3a: 91 passed, 1 skipped; the skip is still the PR-2 mobile-menu test at 1440 px) |
| Live smoke (network) | `E2E_LIVE=1 npx playwright test --grep @live` | **1 passed** |
| Frozen files | `sha256sum -c docs/website/baseline/frozen_sha256_fab9182.txt` | **176/176 OK** |
| Reference package | `sha256sum -c SHA256SUMS` (in `refpkg/MR_RT_003/`) | **37/37 OK** |
| Source DB | `sha256sum releases/v1.6.0/db/microrhododb_v1.6.0.sqlite` | `379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f` (matches) |
| No changes to frozen or legacy trees | `git diff --stat 7546a7a -- releases refpkg pipeline site` | empty |
| Performance and contrast audit | `python web/scripts/pr4_perf_audit.py --out docs/website/pr4 --runs 5` | 0 console errors, 0 contrast failures, Mol* never requested |
| Screenshots | `node web/scripts/pr4_screenshots.mjs <base> docs/website/pr4/screenshots` | 25 PNG + 1 SVG export, 0 console errors |

Environment notes are unchanged from PR-3: the pinned conda env is on PATH for pytest; Chromium needed `LD_LIBRARY_PATH=/opt/conda/lib` in this sandbox; browser tests need the export in `web/public/data` and a build in `web/dist`. The clone verification (fresh clone, re-export, `npm ci`, all suites) is recorded with the commit SHA in the delivery folder, outside the repository.

## 2. Scope and decisions

| Topic | Decision (owner-approved plan) |
|---|---|
| Tree shown | Frozen `refpkg/MR_RT_003/tree/MR_RT_003.rooted.treefile`: 472 tips, 943 nodes, heliorhodopsin outgroup root. Topology and branch lengths are never edited |
| Support shown | SH-aLRT/UFBoot of the **same bipartition** in IQ-TREE `run1.treefile`. The 17 rooted-file labels attached to a neighbouring bipartition are audit fields only |
| Root split | The two root branches are one unrooted bipartition (DB edge `E0397`, run1 98.8/100). Displayed once, on the outgroup branch (pre 1); the ingroup root child (pre 30) and the root (pre 0) show none |
| MR_CLD3_017 | Legacy v1.6.0 assignment kept unchanged; flagged everywhere because run1 support is 50.3/72 (rule: SH-aLRT >= 80 and UFBoot >= 95) |
| Placements | Never tips. One record at a time (`?placement=`) as a highlight of its stored `best_edge` branch, with stored statuses verbatim |
| Downloads | Frozen rooted Newick (unmodified), `run1.treefile` (unmodified), a DERIVED rooted Newick with run1 labels plus README, client-side SVG and PNG of the current view |
| Rendering | Custom SVG, no new dependency |
| Schema | 1.2.0, additive |

## 3. Reconciliation (gate G4)

All values below are asserted by `tests/test_web_phylogeny.py`, which recomputes them from refpkg and the read-only DB with a Newick parser and bipartition code written independently of the exporter, and most are re-asserted in Vitest and Playwright.

### 3.1 Tips and splits

| Item | Value | Test |
|---|---|---|
| Tips | 472 unique, equal to `tips.tsv` and `tips_annot.tsv` | pytest, Vitest |
| Nodes | 943 (472 tips, 471 internal including the root), preorder `pre` aligned between `explorer.json` and the browser parse (fail closed) | pytest, Vitest |
| Tip groups | 422 in the 17 level-1 clades, 8 in backbone groups B01/B02, 27 unclustered backbone, 15 heliorhodopsin outgroup | pytest, Vitest, Playwright legend (ingroup 457, outgroup 15) |
| Tips absent from the corpus | QBQ84355, QBQ84358 (`boundary_schizorhodopsin`, members of MR_CLD3_001): shown as "not in v1.6.0 corpus", no Protein Entry link, no invented annotation | pytest, Vitest, Playwright |
| Bipartitions | every rooted bipartition is present in run1; all 470 non-root values equal run1; 469 branches display support | pytest, Vitest, Playwright (469 marks) |
| Home preview vs explorer | same frozen Newick, same leaf order and clade colours | Vitest |

### 3.2 The 17 rooted-file support discrepancies

All 17 lie on the path from the outgroup root to the former run1 top node (last tip A0A3E2H811). The pattern is a one-step shift of node-attached labels caused by rerooting. The DERIVED Newick changes exactly these 17 labels.

| pre | Internal index | Tips | Rooted-file label (not shown) | run1 label (shown) |
|---|---|---|---|---|
| 30 | 15 | 457 | 92.1/96 | 98.8/100 (root split; shown on pre 1) |
| 40 | 20 | 452 | 82.2/82 | 92.1/96 |
| 112 | 56 | 416 | 76.7/84 | 82.2/82 |
| 162 | 81 | 391 | 64.9/67 | 76.7/84 |
| 408 | 204 | 268 | 61.4/84 | 64.9/67 |
| 412 | 206 | 266 | 73.3/76 | 61.4/84 |
| 424 | 212 | 260 | 98.7/81 | 73.3/76 |
| 662 | 331 | 141 | 18.9/64 | 98.7/81 |
| 692 | 346 | 126 | 87.6/88 | 18.9/64 |
| 712 | 356 | 116 | 75.3/86 | 87.6/88 |
| 716 | 358 | 114 | 11.1/62 | 75.3/86 |
| 724 | 362 | 110 | 93.9/89 | 11.1/62 |
| 726 | 363 | 109 | 50.3/72 | 93.9/89 |
| **744** | **372** | **100** | **100/100** | **50.3/72 (MR_CLD3_017 MRCA)** |
| 848 | 424 | 48 | 87.1/98 | 100/100 |
| 850 | 425 | 47 | 40/51 | 87.1/98 |
| 894 | 447 | 25 | (none) | 40/51 |

The info panel of each of these nodes states that the rooted-file label was moved by rerooting and is not used (Playwright checks 40, 662, 848 and 894).

### 3.3 Clades and subclades

| Item | Value |
|---|---|
| Level-1 groups | 17 clades + 2 backbone groups (B01, B02: 4 tips each); every frozen tip set is a clade of the rooted tree; `mrca_node` exported and checked |
| Support under run1 | 16 of 17 clades meet the rule. **MR_CLD3_017 fails**: MRCA pre 744, 100 tips, run1 SH-aLRT 50.3 / UFBoot 72; frozen DB and rooted-file label 100/100 |
| Subclades | 30, matching `MR_CLD3_subclades.tsv`; all 30 meet the rule (minimum SH-aLRT 82.2 in MR_CLD3_009.01, minimum UFBoot 96 in MR_CLD3_006.02) |
| Function consensus | equal to DB `clade_function_consensus` (v1.6.0), not v1.5.0 labels |
| Robustness caveat | shown for 9 groups: 006, 010, 011, 012, 013, 016 (cross-replicate Jaccard < 0.8), 007, 009 (consensus mixed), 017 (both) |

### 3.4 Edges and placements

| Item | Value |
|---|---|
| DB `tree_edge` → rooted branches | 941 entries, 0 missing; exactly one (`E0397`, the root split) maps to the two root branches [1, 30]; every one of the 942 rooted branches is covered once |
| Current placements | 4,996: `clade_call_qc` assigned 3,617; distant_assigned 720; distant_tentative 4; outgroup_heliorhodopsin 456; unassigned 199 (equal to the DB) |
| Example | MRDB000101: best_edge `E0832` → pre 802, one branch highlighted, no tip added; MRDB000012 is a reference tip, so `?placement=` explains that and points to `?tip=` |
| MR_CLD3_017 placements | assigned 1,546, distant_assigned 597 (records: 1,646 confident, 597 tentative) |

## 4. What was implemented

### 4.1 Exporter (schema 1.2.0)

- New files under `phylogeny/`: `explorer.json` (node table, tip annotations, `edge_map`, `root_split`, provenance and display rules), `run1.treefile` (byte copy), `MR_RT_003.rooted.run1-support.DERIVED.nwk` and its `.README.txt`.
- The DERIVED Newick is built by replacing internal-label spans in the frozen text, so topology, tip names, tip order and every branch-length string are byte-identical to the frozen file. SHA-256 `9e6a7c27...604b910e5`, 17 labels changed.
- `clades.json` gains `mrca_node`, `placement_counts`, `n_reference_tips_in_corpus` (all groups) and `e1_anchors`, `representatives` (level-1 groups), plus a top-level `representative_rule`.
- `tips_annot.tsv` is added to the refpkg inputs and checked against the treefile and `tips.tsv`.
- Details: `WEB_DATA_CONTRACT.md` section 12 and `WEB_DATA_EXPORT.md`.

### 4.2 `#/phylogeny` explorer

- Query parameters (all optional, validated, defaults omitted from the URL): `layout=rect|radial`, `bl=prop|uniform`, `color=clade|subclade|domain|phylum|function|evidence|motif|role`, `support=1`, `sh`, `uf` (display thresholds, default 80/95), `node` (subtree root), `clade`, `tip`, `placement`, `src`, `collapsed`.
- Rendering: rectangular and radial layouts; proportional or uniform branch lengths; zoom (wheel, pinch, buttons, keyboard), pan, reset. In the rectangular layout zoom acts on the vertical axis only, so tip labels stay in the label gutter; horizontal detail comes from the subtree view. Radial zoom is uniform.
- Colour modes (8) with a legend whose counts match the visible tips; heliorhodopsin outgroup tips always have their own style and a **separate outgroup legend**; absent tips are neutral.
- Support: toggle and thresholds. Marks are filled when both values meet the thresholds; values come only from run1.
- Info panel: tips (accession, MRDB accession, organism, protein, function, evidence, clade/subclade, role, Protein Entry link); internal nodes (run1 support with pass/fail, rooted-file audit label on the 17 nodes, root-split note, MRCA clade/subclade, parent/child navigation, collapse, view subtree, clade page link).
- Subtree view (display root without rerooting), collapse/expand of single nodes and of all 19 level-1 groups, clade table (19 rows with support, robustness and the 017 flag).
- Tip search by accession, MRDB accession or organism with keyboard navigation; placed records are not offered as tips.
- Placement panel (`?placement=MRDB…`): exact stored status (`clade_call_qc`, `subclade_call`), best_lwr, clade_lwr, subclade_lwr, best_pendant, lwr_weighted_pendant, n_credible95, placement_qc, model_tag; the best_edge branch is drawn dashed and labelled "position along the branch is not stored in v1.6.0 and is not drawn".
- Provenance card: tree ID, method, model, run1 log-likelihood, rooting, 472-tip scope, release, file SHA-256s, the support-display, root-split and placement rules.
- Downloads: original rooted Newick and `run1.treefile` (byte-identical to the repository files), DERIVED Newick (badged DERIVED) with a README link, SVG (with title/desc provenance, "support: IQ-TREE run1 by bipartition", legend and the legacy-clade note) and PNG of the current view.

### 4.3 Clade Explorer (`#/clade/<ID>`)

- 19 level-1 pages and 30 subclade pages: ID, name, naming basis, kind, tip counts (and tips in corpus), corrected run1 support with threshold status, DB and rooted-file labels as audit fields, robustness (Jaccard run2/run3/midpoint, caveat reasons), dominant domain/phylum/motif/subfamily, v1.6.0 function consensus (status, top fraction, n_E1), E1 anchors, representatives, confident vs tentative record counts, placement status counts, subclade navigation with support, an embedded explorer focused on the MRCA with a subtree-scoped legend, the member tip list with Protein Entry links, and filtered Browse links.
- **MR_CLD3_017**: persistent banner "Legacy v1.6.0 assignment" with run1 50.3/72 vs >= 80/>= 95, the stored 100/100 label marked "differs from run1", the cross-replicate instability (Jaccard run2 0.52) and the statement that membership is retained unchanged. Its 6 subclade pages carry the parent's legacy note; in the explorer the 017 clade strip is hatched and the legend explains the hatching.
- Backbone group pages (B01, B02) make no clade claims.
- `#/clade` without an ID opens the explorer; unknown IDs show the not-found page.

### 4.4 Integration

- Header navigation: Phylogeny is active; the planned-page placeholder is removed.
- Home links ("Explore phylogeny", "Explore tree" under the preview, the Phylogeny feature card) open the explorer. The record page's "View in reference tree" opens `?tip=` for reference tips, `?placement=` for placed records, or `?clade=` otherwise; "Clade summary" opens `#/clade/<ID>`.

## 5. Scientific constraints: evidence

| Constraint | How it is enforced | Test |
|---|---|---|
| Genuine MR_RT_003 topology | frozen Newick parsed in the browser; preorder checked against `explorer.json`; fail closed on mismatch | Vitest, pytest |
| Support from the correct bipartition | run1 values only; 17 rooted-file labels kept as audit | pytest regression table, Vitest, Playwright |
| Root split counted once | `support_displayed` false on the root and the ingroup root child | pytest, Vitest, Playwright |
| MR_CLD3_017 legacy | banner and badges; rule reported, membership unchanged (100 tips = TSV) | pytest, Playwright |
| Placements are not tips | best_edge highlight only; no position drawn; search never offers placements | Vitest, Playwright |
| Statuses preserved | stored `clade_call_qc`/`subclade_call` shown verbatim | Playwright |
| No invented annotations | absent tips neutral and unlinked; tip fields from `v_master` or `tips_annot.tsv` with `annotation_source` | pytest, Vitest, Playwright |
| Unmodified Newick download | byte and SHA-256 equality with the repository file | Playwright |
| Frozen data untouched | checksums 176/176, refpkg 37/37, DB SHA-256, empty protected diff | section 1 |

## 6. Performance

Full tables: `docs/website/pr4/perf_audit.md` (machine-readable `perf_audit.json`). Chromium at 1440x900, cold cache, 5 runs per route, loopback server without compression or throttling; gzip -9 sizes computed.

| Route | Total gzip | Ready (median) |
|---|---|---|
| `#/phylogeny` | 156.3 KiB (JS 79.3, data 68.4) | 579 ms |
| `#/phylogeny?placement=MRDB000101` | 158.1 KiB (adds `records/MRDB000101.json`) | 655 ms |
| `#/clade/MR_CLD3_017` | 151.7 KiB | 541 ms |
| Home `#/` | 260.3 KiB (PR-3: 251.5) | 509 ms (PR-3: 430) |
| Record MRDB000001 | 437.6 KiB (PR-3: 422.6) | 605 ms (PR-3: 422) |

Interactions on the full 472-tip tree, click to painted (median of 5, ms): radial layout 177, rectangular 163, uniform branch lengths 131, colour by function 77, colour by phylum 80, support on (469 marks) 145, collapse all 131, expand all 165, zoom in 115.

- Plan targets met: first render < 2 s (579 ms) and layout switch < 300 ms (177 ms).
- `explorer.json` is 449.5 KiB raw / 46.6 KiB gzip and is loaded only on phylogeny and clade routes.
- Home and record pages grew by 9-15 KiB gzip: `clades.json` grew from 5.1 to 12.9 KiB gzip (`representatives`, `e1_anchors`), plus the shared `palette` chunk (1.3 KiB gzip); the record page also loads `phyloQuery` (5.1 KiB gzip) for its explorer links.
- The ready-time differences against PR-3 compare different sessions on a shared sandbox, not a same-machine baseline; they were not investigated further.
- 0 console errors, 0 text-contrast failures (HTML text; SVG text not scanned), Mol* never requested on these routes.

## 7. Responsive layout and visual review

- Machine audit: `docs/website/pr4/responsive_audit.json`: `#/phylogeny` and `#/clade/MR_CLD3_017` at 375, 768 and 1440 px; in all 6 combinations `scrollWidth == innerWidth`, 0 console errors. Playwright also checks the explorer at 375/768/1280 (canvas heights 440/560/660 px) and every clade page at three widths.
- Screenshots: `docs/website/pr4/screenshots/` (31 PNG). The SVG figure export (4.6 MB, all 472 labels) is delivered with the review package, not committed.

Defects found in review and fixed in this PR:
1. **Page overflow at 375 px** (405 px document) from long SHA-256 values and file names in the provenance and download lists; fixed with `minmax(0,1fr)` grids and `overflow-wrap:anywhere` on both pages.
2. **Wrong subtree legend counts** (for example "No subclade 86" on the 017 page): legends counted all 472 tips; `scopeScheme` now counts only the visible subtree and hides the outgroup block when it is empty.
3. **Tip labels pushed off-canvas when zooming the rectangular layout**: rectangular zoom is now vertical-only (section 4.2).
4. Synthetic pointer events threw on `setPointerCapture`; wrapped so tests and unusual input devices do not break panning.

Known UI limitations left as they are:
- Hit circles for the 943 nodes are not tab stops; keyboard users reach nodes through search, the clade table and the info panel's parent/child buttons.
- Long tip labels of a highlighted placement can be truncated at the canvas edge (190 px label gutter).
- At full-tree scale, tip labels are shown only when zoom or the subtree view gives them enough room.

## 8. Unresolved scientific issues (for a separate revision; not changed here)

1. **MR_CLD3_017 fails the MR_CLD3 rule under corrected support** (run1 50.3/72), while the frozen DB `clade` row and the rooted file store 100/100. It is shown as a legacy assignment.
2. **7 of 17 level-1 clades are unstable across replicates** (min cross-replicate Jaccard < 0.8): 006, 010, 011, 012, 013, 016, 017.
3. **DB `tree_edge.length` deviates** from the run1/frozen branch lengths by up to 0.0039705737; DB lengths are not used for display.
4. **The 17 misplaced support labels persist in the frozen rooted file**; the website shows run1 values and offers the DERIVED file, but the frozen artefact is unchanged.
5. **Subclades:** all 30 meet the rule with run1 support; none needs flagging.
6. **Placement position along the branch is not stored** in v1.6.0, so placements can only be shown as a whole-branch highlight.
7. **Two reference tips are absent from the corpus**: QBQ84355 and QBQ84358 (boundary_schizorhodopsin, MR_CLD3_001).
8. **Backbone-group assignments come through `subclade_call`, not a level-1 clade call.** 97 current placements have `subclade_id` B01 (93) or B02 (4), all with `clade_call_qc = unassigned` and `subclade_call = assigned`. 94 of them are record assignments (`record_clade.source = placement`: B01 93, B02 1); the other 3 (B02) have no record clade (`v_master.clade_id` empty). All are shown as stored; the 3 vs 94 difference is not reconciled here.
9. **MR_CLD3_009 lists 12 E1 anchors while `clade.n_E1` = 11**; both are shown from their sources, and the difference is not reconciled here.

## 9. Deviations from `WEBSITE_REDESIGN_SPEC.md` / the approved plan

| # | Spec / plan | PR-4 as built | Reason |
|---|---|---|---|
| D-21 | Spec 7.2: support parsed from the authoritative Newick | run1 label of the same bipartition; rooted-file labels are audit fields | Owner decision; 17 rooted-file labels sit on the wrong bipartition |
| D-22 | Contract 7.3: placements only as aggregated clade annotations | single-record best_edge highlight in addition | Owner decision; no tip, no position drawn |
| D-23 | Plan: 6 colour modes | 8 (taxonomy split into domain and phylum; subclade added) | Additive |
| D-24 | Plan: `explorer.json` node key `i`, `n_outgroup_or_absent`, root-split flag inside `edge_map` | key `pre` (all-node preorder) plus `internal_index`; `n_reference_tips_in_corpus`; `edge_map` values are lists, and a separate `root_split` object | Clearer indexing; same information |
| D-25 | Plan: representatives ordered E1 first, then reference tips by accession | E1 first, then reference tips by role (anchor_characterized, seed, cl0.6_representative) and accession, up to 12 | Shows characterised anchors first; rule exported in `representative_rule` |
| D-26 | Plan performance: throttled mobile, zoom-frame timing, long tasks | desktop cold-cache loads and click-to-paint interaction timings only | Not measured in this PR; candidate for PR-6 |
| D-27 | Free 2-D zoom | rectangular zoom is vertical-only | Keeps labels readable; subtree view gives horizontal detail |
| D-28 | Spec section 15 lists `PHYLOGENY_DISPLAY_SPEC.md` | consolidated into `WEB_DATA_CONTRACT.md` sections 7 and 12 | As in earlier PRs; the spec itself is not edited |

## 10. Files

- **Exporter and schema:** `tools/export_web_data.py`; `web/src/data/schemas/web-data.schema.json`; `web/src/data/types.ts` (generated).
- **New source:** `web/src/features/tree/{explorerModel.ts,TreeCanvas.tsx,ExplorerPanels.tsx,useExplorer.ts,phyloQuery.ts,palette.ts,svgExport.ts}`; `web/src/pages/{PhylogenyPage.tsx,CladePage.tsx}`.
- **Modified source:** `web/src/app/{routes.ts,App.tsx}`, `web/src/components/SiteHeader.tsx`, `web/src/data/loaders.ts`, `web/src/features/entry/PhylogenySection.tsx`, `web/src/features/tree/TreePreview.tsx`, `web/src/pages/{HomePage.tsx,PlaceholderPage.tsx}`; `web/package.json` and `package-lock.json` (version only).
- **Tests:** `tests/test_web_phylogeny.py` (new), `tests/test_web_export.py`; `web/tests/unit/phylogeny.test.ts` (new), `routes.test.ts`; `web/tests/e2e/{phylogeny.spec.ts,clade.spec.ts}` (new), `routes.spec.ts`, `responsive.spec.ts`.
- **Tooling:** `web/scripts/pr4_perf_audit.py`, `web/scripts/pr4_screenshots.mjs` (new); `web/scripts/perf_capture.mjs` (pr4 mode with interaction steps).
- **Docs:** this report; `docs/website/pr4/` (perf audit, responsive audit, screenshots); `WEB_DATA_CONTRACT.md` (section 12, notes in 7.1 and 7.3); `WEB_DATA_EXPORT.md`; `WEB_TEST_INVENTORY.md`.
- **CI:** `.github/workflows/web-data.yml` (G4 tests added). It has not run on GitHub.
- **Not committed (generated):** `web/public/data/`, `web/dist/`, `web/node_modules/`, `web/test-results/`, `web/tests/e2e/.served/`.
