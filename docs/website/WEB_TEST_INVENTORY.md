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
| PR-1 | pytest (`tests/test_web_export.py`) | Section 9 of `WEB_DATA_CONTRACT.md`. Source set and accession map equality; per-record PDB set equality (all 5,466); PDB metadata equality; 472 tips and tip tallies; clade_state sums to 5,466; summary metrics recomputed independently; legacy `data.js` column oracle (39 columns); watchlist disjoint; JSON Schema on every payload; reproducible `export_manifest.json`; frozen-file checksums |
| PR-2 | Vitest | Route parser (`#/`, `#/browse?…`, `#/record/<id>`, unknown), filter state ⇄ query string, TSV/FASTA serializers (row counts equal the active filter) |
| PR-2 | Playwright | Home renders summary values from `summary.json` (no literals); legacy `#/` and `#/record/MRDB000001` resolve; no horizontal overflow at 375/768/1440; keyboard navigation of nav and filters |
| PR-3 | Playwright | Fixtures from section 4.6 of `WEB_BASELINE_AUDIT.md`: P02945 (174 PDB, MRDB union 175), B0R5N9, CryoR1 (curated rationale shown), GtCCR2/GtCCR4/exoKCR1, A0ABF7PQA2 (engineered, WT link, excluded from counts), A0AAP2RB57, multi-PDB W8VZW3, AFDB-only Q53461, no-structure A0A060JDQ1; Mol* success plus forced-failure state; predicted models shown separately from experimental ones |
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
