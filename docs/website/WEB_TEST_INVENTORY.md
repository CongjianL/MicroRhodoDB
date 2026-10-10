# MicroRhodoDB website 2.0: test inventory and acceptance strategy

## 1. Existing tests (baseline at `fab9182`)

| Suite | Count | Scope | Baseline result (PR-0) | Status in redesign |
|---|---|---|---|---|
| `tests/test_v160_release.py` | 35 tests | v1.6.0 DB integrity, identity, invariants, CLI, API, Snakemake dry run | 35 passed in the pinned env. 3 fail without HMMER/Snakemake on PATH | Unchanged; run in every PR (data must not drift) |
| `tests/test_v150_release.py` | 17 tests | Immutable v1.5.0 release | 17 passed | Unchanged |
| `tests/release_v140.py` | 18 checks | v1.4.0 suite, run inside `test_v140_release_suite` | Passed | Unchanged |
| `tests/browser_walkthrough_v160.py` | 42 steps (file:// + HTTP); 21 against a URL | Legacy `site/` routes, filters, search, downloads, scientific boundaries | 42/42 local; 21/21 live | Kept as the **legacy baseline**. After PR-7 it runs against the archived legacy build (rollback target). Its scientific assertions are ported to the new E2E suite |
| `web/scripts/pr0_baseline_audit.py` | about 120 SQL metrics | Read-only DB audit (this PR) | 0 errors; all section 1.3 metrics match | Basis for PR-1 golden tests |
| `web/scripts/legacy_screenshots.py` | 15 captures | Legacy screenshots + overflow metrics | Recorded | Re-run in PR-6 for before/after |
| `web/poc/verify_poc.py` | 4 checks | Mol* / phylotree.js on real assets | 4/4 | Superseded by PR-3/PR-4 E2E |

`tests/README.md` lists 45 tests and 38 checks. The current counts are 52 and 42. This is documentation drift, to be fixed in PR-6.

## 2. New tests by stage

| Stage | Layer | Tests (minimum) |
|---|---|---|
| PR-1 | pytest (`tests/test_web_export.py`) | Section 9 of `WEB_DATA_CONTRACT.md`. Source set and accession map equality; per-record PDB set equality (all 5,466); PDB metadata equality; 472 tips and tip tallies; clade_state sums to 5,466; summary metrics recomputed independently; legacy `data.js` column oracle (39 columns, strict equality with only the transformations T1-T7 of contract section 9.1); watchlist disjoint; JSON Schema on every payload; reproducible `export_manifest.json`; frozen-file checksums |
| PR-1 (as built) | pytest | `tests/test_web_export.py` (31 tests, two CLI exports into fresh directories; independent pandas/SQL recomputation, independent Newick bipartition parser for the support audit, failure modes for exit codes 2 and 4) and `tests/test_fetch_release_db.py` (4 tests, `file://` mirrors, no network). `web/scripts/schema_to_ts.py --check` keeps `types.ts` in sync with the schema |
| PR-2 | Vitest | Route parser (`#/`, `#/browse?…`, `#/record/<id>`, unknown), filter state ⇄ query string, TSV/FASTA serializers (row counts equal the active filter) |
| PR-2 | Playwright | Home renders summary values from `summary.json` (no literals); legacy `#/` and `#/record/MRDB000001` resolve; no horizontal overflow at 375/768/1440; keyboard navigation of nav and filters |
| PR-2 (as built) | pytest | `tests/test_web_export.py` grows to 33 tests for schema 1.1.0: the 21 appended index columns equal the record files (type and value), legacy TSV coverage, `vocabulary.json` equals the DB definition tables, run1 support numbers and the threshold flag (only MR_CLD3_017 fails, 50.3/72; frozen DB label 100/100 unchanged) |
| PR-2 (as built) | Vitest (`web/tests/unit`, 6 files, 50 tests) | `routes` (9): hash parser, legacy routes, `#/novel`, query routing. `browse` (13): filter state ⇄ URL, ignored params, `status=member` alias, default view 3,085, distributions equal `summary.json`, numeric sorting. `browse.legacy` (5): the new filter engine equals a verbatim port of legacy `site/app.js` `apply()` evaluated on legacy `site/data.js`, for every status, clade ± tentative, evidence, function, domain, flag, free-text and combined filter, with and without engineered constructs. `exporters` (10): 39 legacy TSV columns equal `D.columns`; every legacy cell of all 5,466 rows reproduced (T1 rounding only); source FASTA byte-identical to legacy; unique MRDB FASTA = 5,299; safe filenames and manifest. `tree` (5): 472 Newick tips equal `tips.json`, 422 level-1 + 15 outgroup + 27 unclustered tips, each of the 19 clade arcs contiguous with `n_tips_in_tree` tips. `summary` (8): headline numbers, Home links open selections of the displayed size, only MR_CLD3_017 fails, exact caveat text |
| PR-2 (as built) | Playwright (`web/tests/e2e`, 47 tests, Chromium) | `home` (7): statistics equal `summary.json` with denominators, charts, real 472-tip tree with the MR_CLD3_017 disclosure, no heavy data files, search/entry links, function links, About. `browse` (9): default view, filters + URL + Back/Forward, clade 017 ± tentative with the uncertainty banner, sort and `aria-sort`, pagination, ignored params, legacy alias and record links, four exports equal the selection, only `records-index.json` among heavy files. `routes` (7): root redirect and assets under `/MicroRhodoDB/site/`, MRDB/source deep links, tentative caveat, not-found pages, `#/novel`, planned pages, nav/history/refresh, skip link and focus. `responsive` (24): 6 pages x 375/768/1440 with no page-level horizontal overflow and screenshots; mobile menu keyboard/Escape (375/768); filter reachability. A shared fixture fails any test on a console error, page error, failed request or HTTP >= 400 |
| PR-3 | Playwright | Fixtures from section 4.6 of `WEB_BASELINE_AUDIT.md`: P02945 (174 PDB, MRDB union 175), B0R5N9, CryoR1 (curated rationale shown), GtCCR2/GtCCR4/exoKCR1, A0ABF7PQA2 (engineered, WT link, excluded from counts), A0AAP2RB57, multi-PDB W8VZW3, AFDB-only Q53461, no-structure A0A060JDQ1; Mol* success plus forced-failure state; predicted models shown separately from experimental ones |
| PR-3 (as built) | Vitest (`web/tests/unit`, 7 files, 72 tests) | `routes` grows to 12: record deep-link params (`section`, `structure`), lower-case canonical redirect keeping the query, `href.record` with a query. New `entry` (19): deep-link parse/serialise and invalid values; structure options (MRDB000001: 174 focused / 175 union rows, default 5ZIM, 4Y9H attributed to B0R5N9); AFDB and release-model fallbacks; `resolveSelection`; PDB filter/sort (non-numeric resolutions last, stable order); union rows (6CSM, MRDB000092); pLDDT rescaling of the two release models (CA mean within 0.1 of DB `mean_plddt`, PDB column widths preserved); publication grouping; sequence/FASTA; engineered variants; mini-tree highlight (P02945 tip; MRDB000003 confident arc; A0A135LS53 tentative arc, no tip). Integrity sweep over all 5,299 record files / 5,466 sources: `n_pdb`, `pdb_ids`, union sets, viewer options, AFDB option, `has_predicted`, `n_support_links` and defaults equal `records-index.json`; release models exist only for A0A9X2L7U0 and B0R633 |
| PR-3 (as built) | Playwright (`web/tests/e2e`, 77 tests: 76 passed, 1 skipped; plus 1 `@live`) | New `record` (30). MRDB000001: seven sections, counts (174/175 PDB), representatives, section nav. Viewer: loads only on click, BinaryCIF from mocked RCSB then AFDB with pLDDT colouring; View in 3D from the PDB table (4Y9H); deep link with `section`/`structure` survives reload; unknown structure falls back. Failure states: BinaryCIF 500 falls back to mmCIF; 404 then Retry; stalled AFDB request times out (test hook shortens the 30 s timeout to 1.5 s); HTML 200 reports a parse error. Release models B0R633 and A0A9X2L7U0 (pLDDT 0-1 rescaled). Record types: no structures (MRDB000003), AFDB-only (MRDB000009), multi-source MRDB000249 (switch to A0ACD1IKA6, Back restores), engineered A0A6I8WFQ3 to WT A0A6P3CW41 and back, curated override A0A1I3DJQ0, tentative MR_CLD3_017 placement A0A135LS53 (caveat, 50.3/72 vs thresholds, arc-only highlight), P02945 tip highlight, FASTA and JSON export. Invalid IDs (MRDB999999, malformed, P0294) fetch no record; lower-case redirect. Home/Browse/About never request the Mol* chunk. 3 records x 375/768/1440 without page-level overflow, with screenshots. `routes` updated for the full entry page. RCSB/AFDB requests are answered from committed real files (`web/tests/fixtures/structures`, SHA256SUMS, `fetch_structure_fixtures.py --check`). `live` (1, `@live`, excluded unless `E2E_LIVE=1`): real 5ZIM and AF-P02945-F1 |
| PR-4 | Vitest + Playwright | 472 tips rendered; 17 level-1 clades + 2 backbone groups highlighted from `clade_tips.json`; non-corpus tips (QBQ84355/QBQ84358) not linked to records; placements never drawn as tips; tip → record → Back; Newick download byte-equal to the refpkg |
| PR-5 | Vitest + Playwright | Chart totals equal `summary.json` denominators; E1 88/91 toggle; watchlist pages never show membership/evidence; search worker reproduces legacy SW golden hits (12 CLI queries + P02945 = 100% identity), handles invalid/long input and cancel; the UI never claims official membership scoring |
| PR-6 | Playwright + Lighthouse/axe | Full route crawl, zero uncaught exceptions, WCAG AA contrast, CSP/link `rel`, LCP/CLS/INP measured in a documented environment, Home transfer excludes Mol* and `corpus.fasta`, third-party failure isolation |
| PR-7 | Smoke (live) | Public routes, permalinks, assets 200, PDB/AFDB load, FASTA download, Not Found |

## 3. Fail-fast blockers checked in every PR

These are the nine blockers from plan section 13.5. Each is encoded as at least one automated assertion before the PR that could break it:
- frozen checksums
- no invented PDB IDs, functions or topology
- tips vs placements
- status vs evidence
- E1 and watchlist denominators
- permalinks and downloads
- accession routing
- no fallback to `data.js`
- the search disclaimer

## 4. Environment notes

- Python tests need the pinned env (`workflow/envs/mrdb.lock.yml`) on PATH.
- Playwright Chromium needs system libraries (`npx playwright install --with-deps chromium` in CI).
- Mol* tests run on headless Chromium with SwiftShader WebGL (`--use-angle=swiftshader --enable-unsafe-swiftshader`).
- Network-dependent tests (RCSB/AFDB) are tagged so that CI can run a mocked-fixture variant when external hosts are unavailable.
- PR-2 local runs: `npm ci`, the PR-1 exporter (`web/public/data`), `npm run build`, then `npx vitest run` and `npx playwright test` from `web/`. The E2E server is `web/scripts/serve_e2e.py` (Python static server reproducing `/MicroRhodoDB/` with the repository-root redirect). In the development sandbox, Chromium also needed `LD_LIBRARY_PATH` pointing at a conda `lib/` that provides `libatk-1.0`; CI should use `npx playwright install --with-deps chromium` instead.
- `web/scripts/pr2_perf_audit.py` (with `perf_capture.mjs`) measures per-route transfer, timings and WCAG text contrast; output in `docs/website/pr2/perf_audit.{json,md}`.
- PR-3: `web/scripts/pr3_perf_audit.py` (with `perf_capture.mjs ... pr3`) adds record types and click-to-rendered viewer timings (mocked; live with `PERF_LIVE=1`); output in `docs/website/pr3/perf_audit.{json,md}`. Viewer timings use SwiftShader software WebGL and overstate render time relative to GPU-backed browsers.
