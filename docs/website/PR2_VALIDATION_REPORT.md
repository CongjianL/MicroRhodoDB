# PR-2 validation report: design system, Home and Browse

- Branch: `website/pr-2-design`, created from the accepted PR-1 commit `4b8391c` (PR-0 `edbb085`, PR-0a `2527237`, PR-1 `4b8391c` history kept).
- Dataset: v1.6.0 (frozen). Source DB SHA-256 `379a2543...dce17f`; MR_RT_003 rooted tree SHA-256 `c5619697...5aded9aef`.
- Data export schema: 1.1.0 (additive; `WEB_DATA_CONTRACT.md` section 11). Website version `2.0.0-pr2`.
- Status: committed locally only. Not pushed, not merged, not deployed. PR-3 not started.

## 1. Local checks vs CI

All results below were run locally in the development sandbox (Linux x86_64, Node 22.21.1, Python 3.11.16, Playwright 1.63.0 with Chromium 153).
**No CI has run for PR-2.** The `web-data` workflow was extended with frontend steps (npm ci, build, Vitest, Playwright install and tests, artifact upload); those steps have not executed on GitHub yet.

| Check | Command (from repo root unless noted) | Local result |
|---|---|---|
| Python suite, including PR-1 gate G1 | `python -m pytest -q tests/` | **89 passed** (v1.6.0 35, v1.5.0 17, web export 33, fetch 4) |
| Generated TS types in sync with schema | `python web/scripts/schema_to_ts.py --check` | up to date |
| TypeScript | `npm run typecheck` (in `web/`) | 0 errors |
| Production build | `npm run build` (in `web/`) | built in about 1.3 s |
| Unit tests | `npx vitest run` (in `web/`) | **6 files, 50 tests passed** |
| Browser tests | `npx playwright test` (in `web/`) | **46 passed, 1 skipped** (the mobile-menu test is skipped at 1440 px, where there is no menu button) |
| Frozen files | `sha256sum -c docs/website/baseline/frozen_sha256_fab9182.txt` | **176/176 OK** |
| Reference package | `sha256sum -c refpkg/MR_RT_003/SHA256SUMS` | all OK |
| Source DB | `sha256sum releases/v1.6.0/db/microrhododb_v1.6.0.sqlite` | `379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f` (matches) |
| No changes to frozen or legacy trees | `git diff --stat 4b8391c -- releases refpkg pipeline site` | empty |
| Whitespace | `git diff --check` | clean |
| Performance and contrast audit | `python web/scripts/pr2_perf_audit.py --out docs/website/pr2` | 0 console errors, 0 contrast failures |

Environment notes:
- `tests/test_v160_release.py` needs the pinned env on PATH (HMMER, Snakemake). Without it, 3 tests fail, as recorded in PR-0.
- In this sandbox, headless Chromium needed `LD_LIBRARY_PATH=/opt/conda/lib` to find `libatk-1.0.so.0`. CI uses `npx playwright install --with-deps chromium` instead.
- Browser tests need the PR-1 export in `web/public/data` and a build in `web/dist`. They are served by `web/scripts/serve_e2e.py`, which reproduces `/MicroRhodoDB/` including the repository-root `index.html` redirect.

## 2. What was implemented

### 2.1 Architecture

- React 18 + TypeScript + Vite 8 + Tailwind 4 + TanStack Table 8 + ECharts 5 (modular core). Base path `/MicroRhodoDB/site/`; the build writes to `web/dist/site/`.
- Typed hash routes (`src/app/routes.ts`): `#/`, `#/browse?…`, `#/record/<MRDB or source accession>`, `#/about`, `#/clade/<id>`, ten planned pages, and not-found. `#/novel` redirects to `#/watchlist` (replace, no extra history entry).
- Route-level lazy loading: Home, Browse, Record, About and Placeholder are separate chunks. ECharts is a separate chunk imported only by Home.
- Data loading (`src/data/loaders.ts`) uses the PR-1 per-file layout: `current.json` → `manifest.json` → the files the route needs. No `data.js`; nothing falls back to the legacy site.
- Layers are separated: `components/` (design system), `features/` (browse, charts, tree), `lib/` (pure logic: filters, exporters, summary, formatting; unit tested), `pages/`.

### 2.2 Design system

- Tokens follow spec section 3.2: canvas `#F8FAFC`, surface white, ink `#142238`, secondary `#526175`, accent blue `#1665B5`, teal `#087F78`, border `#DEE5EC`, warn `#B45309`. System font stack; 16 px body, line height 1.55.
- Components: `SiteHeader` (desktop nav plus a full mobile menu with Escape/focus return; secondary pages under "More"), `SiteFooter` (release, license, DB checksum, schema), `PageTitle` (sets `<title>`), `Breadcrumbs`, `SearchBox`, `StatCard`, `Callout`, `MembershipBadge`, `EvidenceBadge` (text label, not colour alone), `CladeBadge` (confident/tentative, with a support-caveat marker), `FunctionLabel`, `FlagBadge`, `PlannedTag`, `LoadingSkeleton`, `ErrorState` (retry), `EmptyState`, `CladeSupportNotice`, `BarChart` (ECharts plus an accessible data table), `TreePreview`, `CladeLegend`, `FilterPanel`, `ResultsTable`, `ExportMenu`.
- Accessibility: skip link; real `<a>` for navigation and `<button>` for actions; every filter is labelled; visible `:focus-visible` rings; `aria-sort` on sortable headers; `aria-live` counts and export status; charts and tree have text equivalents (data tables and `<title>`/`<desc>`); `prefers-reduced-motion` respected; tap targets of at least 44 px for primary controls on mobile.

### 2.3 Home (`#/`)

- Hero with the specified heading and subtitle; release line (v1.6.0, date, scope, license) read from `manifest.json`/`summary.json`.
- Universal search. MRDB IDs and UniProt accessions open the record. PDB IDs, clade IDs and subclade IDs open Browse with that filter. Anything else becomes a Browse text search across all records. Example chips are provided.
- Primary actions: Browse proteins; Explore phylogeny and Sequence search (both labelled "planned").
- Six statistic cards (5,466 source records; 3,089 Type-I members; 88 E1 of 5,460 counted; 472 tree tips; 121 publications; 181 watchlist), each stating its counting policy. Eight context metrics follow (5,460 counted; 5,299 MRDB with 129 multi-source; 1,379 candidates; 66 records with PDB / 438 entries; 4,397 with AFDB; 468 call conflicts). All values come from `summary.json`; the UI has no numeric literals.
- Membership composition (n = 5,466, engineered included) and E1-E5 composition (n = 5,460 counted, engineered excluded), each with its denominator and a data table.
- MR_RT_003 preview: circular phylogram drawn from the frozen rooted Newick (all 472 tips, branch lengths to scale, no tip labels). The outer ring marks 17 level-1 clades + 2 backbone groups using `phylogeny/tips.json`. MR_CLD3_017 is hatched and marked "!". The clade legend table lists records (confident + tentative), tips, and IQ-TREE run1 support, with a "fails thresholds" badge on 017. The phylogenetic-uncertainty callout follows.
- Function-class quick links: all 11 official classes, none merged. Each opens Browse with the exact filter; the link count equals the resulting selection (tested).
- Transparency note (spec section 4.6, verbatim) and links to Methods/About.
- Entry cards to Browse, Phylogeny, Structures, Search, Downloads and About; the planned ones are labelled.

### 2.4 Browse (`#/browse`)

- Default view: Type-I members with engineered constructs hidden, stated in the heading ("Type-I members, engineered constructs hidden: 3,085 of 5,466 source records (2,991 MRDB accessions)"). One-click groups: All records, Candidates, Boundary families, Heliorhodopsins, Decoys/rejected. Visible engineered toggle.
- Filters, all in the URL: text (`q`: MRDB/source accession, protein, organism, motif, clade name), lineage, membership status (9), functional class (11), evidence E1-E5, clade (19, with a "(support caveat)" suffix for 017) and "include tentative placements", subclade, placement state (confident/tentative/unassigned/…), domain (Archaea/Bacteria/Eukaryota/no domain assigned), helix-C motif, retinal-site residue, PDB ID, has experimental PDB, has AFDB model, call conflict, curated membership override, has supporting publication, length interval.
- Filter semantics match the legacy `apply()` exactly (section 4.2) and use one validated index (`records-index.json`, schema 1.1.0). Invalid URL values are reported in a visible "ignored parameters" notice, never applied silently. Legacy `status=member|candidate|…` is accepted as an alias of `group=`.
- Results table (TanStack): MRDB accession, Source accession (+reviewed), Protein, Organism (+domain), Length, Membership, Function, Evidence, Clade (confident/tentative badge), Experimental PDB, Structure availability, plus optional columns (score, motif, residue, lineage, …) through a column menu. Numeric sorting with `aria-sort`; 25/50/100/250 rows per page; first/previous/next/last. The first column is sticky and the table scrolls horizontally inside its own region. Protein and organism are clamped to two lines (full text in `title`, on the record page and in exports).
- Every row links to `#/record/<source accession>`. MRDB accessions link to `#/record/<MRDB>`.
- Uncertainty: when the selection contains records assigned to or tentatively placed near MR_CLD3_017, a callout states the count, the corrected support (SH-aLRT 50.3 / UFBoot 72) and the thresholds.
- Exports of the current selection:
  - TSV of source records: the 39 legacy columns in legacy order with identical values (full precision), plus 8 appended columns. It has one header row and no comment lines, so it stays loadable like the legacy file.
  - FASTA of source records: byte-identical headers and sequences to the legacy export.
  - FASTA of unique MRDB sequences (one per MRDB accession, representative source).
  - JSON selection manifest: release, release date, schema/website version, filter query and parsed filters, sort, counts (source records, MRDB accessions, engineered in selection), TSV columns and the companion filenames.
  - Filenames are generated from a hash of the filter state and the count, never from user text.
- History: each discrete filter change adds one history entry (Back/Forward restores it). Successive edits of the same text field replace the entry. Page clamping uses replace.

### 2.5 Record (`#/record/<acc>`, interim) and clade summary

- Legacy deep links work for both MRDB and source accessions. MRDB IDs are resolved through `accessions.json` before fetching a record file, so unknown IDs show a not-found page with search and no failed request.
- The interim page is clearly labelled ("Interim record view … complete Protein Entry planned for PR-3"). It shows the MRDB/source relationship (MRDB representative vs E1 representative kept distinct), membership with the DB definition, evidence, function, phylogeny (state, clade, tentative placement and caveat, link to the clade summary), source-level PDB IDs, AFDB, and the sequence. Mol* and the full tabs are not implemented (PR-3).
- `#/clade/<id>` is a minimal summary (level, tips, run1 support with pass/fail, uncertainty callout, Browse link) and carries a "planned" notice for the PR-4 explorer.

### 2.6 About and planned pages

- About covers scope, membership statuses and evidence levels (definitions from `vocabulary.json`), the classification ("17 level-1 clades + 2 backbone groups"), the support correction, provenance and license.
- Phylogeny, Structures, Search, Downloads, Statistics, Evidence, Watchlist, Methods, Citation and Help are placeholders. Each shows "Planned: PR-x" and "not available in this development build", and none presents a working tool.

## 3. Scientific constraints: evidence

| Constraint | How it is enforced | Test |
|---|---|---|
| 5,466 source records, 5,460 counted, 5,299 MRDB accessions | Values read from `summary.json`; Browse "All records + engineered" = 5,466; unique FASTA = 5,299 | `summary.test.ts`, `home.spec.ts`, `browse.spec.ts`, `exporters.test.ts`, pytest G1 |
| MRDB representative ≠ E1 representative | Separate fields and labels (record table role "MRDB representative"; `e1_representative` column) | record route test (P02945 is the MRDB representative of MRDB000001; its E1 representative is B0R5N9); TSV oracle |
| Membership statuses, E1-E5 definitions, denominators | Definitions from DB (`vocabulary.json`); E1 card "of 5,460 counted"; charts state n and engineered policy | `test_vocabulary`, `home.spec.ts` |
| Tentative placements | Separate `tentative` state and badge; included only with `tent=1`; legend shows "+N tentative" | `browse.legacy.test.ts`, `browse.spec.ts` (017: 1,646 confident → 2,243 with tentative) |
| "17 level-1 clades + 2 backbone groups" | Text from `clades.json.display`; 19 legend rows; ring arcs | `tree.test.ts`, `home.spec.ts` |
| Support = IQ-TREE run1 mapped by bipartition, never rooted-file labels | UI reads only `support_audit.iqtree_run1_*` | `test_clades` (pytest), `summary.test.ts` |
| MR_CLD3_017 legacy assignment, 50.3 / 72, fails SH-aLRT ≥ 80 and UFBoot ≥ 95 | Callout on Home, About, Browse (when relevant), record (tentative or confident in 017) and clade page; hatched arc; legend badge | `summary.test.ts` (exact text), `home.spec.ts`, `browse.spec.ts`, `routes.spec.ts` |
| No clade/topology/frozen-file changes | Exporter is read-only; tree drawn from the byte-copied Newick | frozen checksums 176/176, refpkg SHA256SUMS, DB SHA-256, empty `git diff` on `releases refpkg pipeline site` |
| Export correctness | TSV/FASTA built from the same index; legacy oracle | `exporters.test.ts` (all 5,466 rows × 39 columns; FASTA byte-identical), `browse.spec.ts` (downloaded files parsed and compared with the on-screen selection) |
| No silent field loss | All 39 legacy TSV fields exported; extra fields appended, not substituted | `test_records_index_v11_columns_cover_legacy_tsv`, `exporters.test.ts` |

## 4. Performance

Full tables: `docs/website/pr2/perf_audit.md` (machine-readable: `perf_audit.json`). Method: Playwright Chromium, 1440×900, a fresh context per run (cold cache), 5 runs per route, local loopback server without compression or throttling. Byte counts are exact for the requested files; gzip sizes are computed with gzip -9 because GitHub Pages serves gzip.

| Route | Total transferred, raw / gzip | Data files | Heavy data files | Ready (median) |
|---|---|---|---|---|
| Home `#/` | 876 / 249 KiB | 186 / 25 KiB: current, manifest, summary, clades, vocabulary, tips.json, rooted Newick | **none** | 160 ms (tree drawn 226 ms) |
| About `#/about` | 286 / 75 KiB | 79 / 11 KiB: current, manifest, summary, clades, vocabulary | **none** | 141 ms |
| Planned page `#/phylogeny` | 206 / 64 KiB | current, manifest | none | 146 ms |
| Browse `#/browse` | 4,486 / 454 KiB | records-index (4,139 KiB raw), clades, vocabulary | records-index.json only | 246 ms |
| Record `#/record/P02945` or `MRDB000001` | 1,447 / 399 KiB | accessions.json (1,112 KiB), 1 record file (P02945/MRDB000001 is the largest, 57.5 KiB), clades, vocabulary | accessions.json, 1 record | 153-158 ms |

For comparison, the legacy site loads `site/data.js` (4,249 KiB raw / 935 KiB gzip) on every page. The full PR-1 export (28,487 KiB raw) is never downloaded as a whole.

JS chunks (raw / gzip):

| Chunk | Size |
|---|---|
| Entry | 164.0 / 52.6 KiB |
| ECharts core (Home only) | 464.7 / 153.9 KiB |
| BrowsePage | 81.3 / 23.2 KiB |
| HomePage | 24.2 / 8.1 KiB |
| RecordPage | 12.1 / 3.7 KiB |
| AboutPage | 5.4 / 2.1 KiB |
| CSS | 33.5 / 6.9 KiB |

Timings are relative measurements on a fast local machine, not field latency. Core Web Vitals under throttling are PR-6 scope.

## 5. Responsive layout and visual review

Machine audit: `docs/website/pr2/responsive_audit.json` (from `responsive.spec.ts`). Screenshots: `docs/website/pr2/screenshots/pr2_<page>_<width>.png` (18 viewport captures). Full-page captures are delivered separately (not committed; about 9 MB).

| Page | 375 px | 768 px | 1440 px |
|---|---|---|---|
| Home | no overflow; stacked cards, legend table fixed layout | no overflow; 2-column cards | no overflow; tree + legend side by side |
| Browse (default) | no overflow; filters in a collapsible panel; table scrolls in its region (341 / 1,800 px) | no overflow; table region 718 / 1,800 px | no overflow; sidebar filters; table region 1,038 / 1,800 px |
| Browse (MR_CLD3_017 + tentative) | no overflow; uncertainty callout visible above the table | no overflow | no overflow |
| Record P02945 | no overflow; source table scrolls in its region | no overflow | no overflow |
| About | no overflow; definition tables wrap | no overflow | no overflow |
| Planned (Phylogeny) | no overflow; "Planned: PR-4" | no overflow | no overflow |

All 18 page/viewport combinations: `document.scrollWidth <= innerWidth`, 0 console errors, header height 65 px.

WCAG 2.1 text contrast (computed styles on every visible HTML text node, 7 routes): **0 pairs below AA**. The minimum is 4.65:1 (teal eyebrow text on the canvas); the next lowest is 5.17:1. SVG/canvas chart text is not covered by this scan; chart values are duplicated in accessible HTML tables.

Defects found in the screenshot review and fixed in this PR:
1. Mobile Browse rows were very tall because protein and organism names wrapped freely. They are now clamped to 2 lines with the full text in `title`; organism has min/max widths.
2. Mobile Home clade legend: the "Records" header broke and the support column overflowed. Fixes: fixed table layout with 50/22/28% columns; tips moved under the clade name below 640 px; the "fails thresholds" badge wraps under the value; hyphenation instead of breaks at arbitrary characters (which had split "channelrhodopsins").
3. The legend caption was hidden inside the scroll region. It is now a visible paragraph referenced by `aria-describedby`.
4. Double parentheses in the uncertainty callout ("(Fungal rhodopsins (CarO / LR / NOP-1-like))"). The clade name is now set off with dashes.
5. The clade id on the record page had no link. A "Clade summary" link was added (E2E tested).
6. Unknown MRDB deep links caused a 404 fetch and a console error. They are now resolved via `accessions.json` first.

Known cosmetic items left as they are: a reserved line under the Download button (the export-status live region keeps its height to avoid layout shift); the 1440 px legend scrolls inside a 34 rem box so that it matches the tree height.

## 6. Deviations from `WEBSITE_REDESIGN_SPEC.md` / `WEB_DATA_CONTRACT.md`

| # | Spec / contract | PR-2 as built | Reason |
|---|---|---|---|
| D-1 | Contract schema 1.0.0; records-index 25 columns | Schema 1.1.0, additive: 46 index columns, run1 support numbers + threshold flag + `clade_rule` in `clades.json`, new `vocabulary.json` | Lossless Browse filters/exports without 5,299 record fetches; UI labels from DB definitions (contract section 11) |
| D-2 | Contract 3: Home loads `current`, `manifest`, `summary`, `preview.svg` | Home also loads `clades.json`, `tips.json`, the rooted Newick and `vocabulary.json` (25 KiB gzip total); `preview.svg` is not used | The interactive-quality preview is drawn from the real Newick and clade tips so arcs, hatching and legend come from one source; still no heavy files |
| D-3 | Legacy root `#/` was the Browse table | `#/` is Home; Browse is `#/browse` | Spec section 2.1 (Home at `#/`). Home links to Browse prominently |
| D-4 | Legacy `#/search` was a working sequence search | `#/search` is a labelled placeholder (PR-5) | Spec scope: sequence search is PR-5; not presented as a working tool |
| D-5 | Spec 5.2 lists domain "Viruses" | No Viruses option; "No domain assigned" (`domain=none`) plus lineage filter | The legacy Viruses option matched 0 records (tested against the legacy oracle); offering it would imply data that do not exist |
| D-6 | Spec 2.2 example `status=member` | Canonical parameters `group=` and `evidence=`; `status=<group>` accepted as an alias; `status=<membership_status>` filters the exact status | `status` is also the 9-value membership status; the alias keeps old links working |
| D-7 | Legacy TSV numbers rounded; legacy filename `microrhododb_v1.6.0_selection.tsv` | Full precision (contract T1); 8 appended columns (47 in total); filename `microrhododb_v1.6.0_browse_<hash>_<n>_source_records.tsv` plus FASTA/manifest variants | Lossless; spec 5.4 asks for filter-specific, safe filenames |
| D-8 | Spec 3.3 `DefinitionTooltip` | Definitions panel / expandable definitions and `title` text | Tooltips are not reachable on touch and are poor for long DB definitions |
| D-9 | Spec 5.3 responsive table | Horizontal scroll inside a labelled region with a sticky first column (no card layout); 2-line clamps | Keeps column comparison and sorting intact on mobile; no page-level overflow |
| D-10 | Browse history (spec 2.2.5) | One history entry per discrete change; text fields replace | Deterministic Back/Forward without flooding history while typing |
| D-11 | Record page (PR-3) | Interim labelled record view; minimal clade summary | Needed so legacy deep links and Browse links resolve now |
| D-12 | — | MRDB deep links load `accessions.json` (1.1 MB raw / 0.3 MB gzip) before the record | Avoids 404/console errors for unknown IDs and resolves source accessions without a server |
| D-13 | Spec 11.1 tree viewer phylotree.js | The Home preview is a custom static SVG (no phylotree) | Spec 4.3 requires a lightweight preview; phylotree remains the PR-4 choice (PoC in PR-0) |
| D-14 | — | ECharts core chunk 154 KiB gzip, loaded on Home only | Spec 11.1 chose ECharts; the modular core and lazy loading keep it off Browse, Record and About |
| D-15 | — | E2E server is a Python static server (`serve_e2e.py`), not `vite preview` | Reproduces the real `/MicroRhodoDB/` layout including the repository-root redirect |

## 7. UI usage notes

- Local development: run the exporter first (`python tools/export_web_data.py --out web/public/data`), then `npm ci && npm run dev` in `web/`, and open `http://localhost:5173/MicroRhodoDB/site/`.
- Shareable Browse URLs, for example:
  - `#/browse?evidence=E1` (Type-I members with E1)
  - `#/browse?group=all&eng=1&clade=MR_CLD3_017&tent=1`
  - `#/browse?status=member` (legacy alias)
- Keyboard: Tab reaches the skip link first. In the mobile menu, Escape closes it and returns focus. Sortable headers are buttons (Enter/Space); filter controls are native inputs.

## 8. Files

- Source: `web/src/**`, `web/index.html`, `web/vite.config.ts`, `web/tsconfig.json`, `web/package.json`, `web/package-lock.json`, `web/public/favicon.svg`.
- Tests: `web/tests/unit/*.test.ts`, `web/tests/e2e/*.spec.ts`, `web/playwright.config.ts`, `web/scripts/serve_e2e.py`, `tests/test_web_export.py`.
- Exporter and schema: `tools/export_web_data.py`, `web/src/data/schemas/web-data.schema.json`, `web/src/data/types.ts` (generated).
- Audit tooling: `web/scripts/pr2_perf_audit.py`, `web/scripts/perf_capture.mjs`.
- Docs: this report, `docs/website/pr2/{perf_audit.md,perf_audit.json,responsive_audit.json,screenshots/}`, updates to `WEB_DATA_CONTRACT.md` (section 11), `WEB_DATA_EXPORT.md` and `WEB_TEST_INVENTORY.md`.
- CI: `.github/workflows/web-data.yml` extended with frontend steps (not yet run on GitHub).
- Not committed (generated): `web/public/data/`, `web/dist/`, `web/node_modules/`, `web/test-results/`, `web/tests/e2e/.served/`.
