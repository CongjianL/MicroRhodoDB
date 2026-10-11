# PR-6 Web Acceptance Report: accessibility, performance, regression and scientific audit

**Branch:** `website/pr-6-acceptance`, created from the accepted PR-5a commit `64f8a18947f716610e3a29f3bac58ac55466c6f6`.
**Dataset:** v1.6.0 (frozen). DB SHA-256 is `379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f`. The MR_RT_003 tree SHA-256 is `c56196970698decea8384c1cad97545794268e6d8a2df2b195e7d35d5ded9aef`.
**Validation scope:** everything here is **local**, run in the development sandbox (Linux, Node 22, Chromium 153 headless). **GitHub CI has never run** on this branch or on any earlier redesign branch. Nothing was pushed, merged or deployed.

## Decision: Gate G6 = PASS (local), with 5 maintainer-decision PR-7 blockers open

| G6 criterion | Result | Evidence |
|---|---|---|
| Zero open P0/P1 defects | Met: 0 P0, 0 P1. Open items are 3 P2 and 8 P3 (section 7). | This report |
| Zero known uncaught production JS exceptions | Met. 0 page errors and 0 console errors across 40 route-profiles x 3 runs. The e2e fixture fails any test on a console error or HTTP >= 400 (246 tests). 23 failure-injection tests pass, including worker 404, data 404/500/truncated/timeout and RCSB/AFDB outage. | `pr6/performance_audit.json`, `pr6/logs/playwright_full.log` |
| Direct navigation to all mandatory routes | Met. 20 routes are loaded directly at 375/768/1440. Legacy `#/record/<MRDB/source>`, `#/novel` and `#/search` deep links are tested. | `pr6_a11y.spec.ts`, `routes.spec.ts` |
| Unchanged official scientific checksums | Met. Frozen baseline 176/176, refpkg 37/37, DB SHA unchanged, empty `git diff 7546a7a -- releases refpkg pipeline site`. | `pr6/logs/frozen_*.log`, `refpkg_sums.log`, `db_sha.log` |

The 5 maintainer decisions (MD-1 to MD-5: licence, release date, DOI, contact, maintenance placeholders) are **not website defects**. The agent must not resolve them. They **block PR-7 publication** until the maintainer decides (see `pr6/publication_readiness.md`). A reviewer who treats the visible licence conflict as a P1 should read this verdict as "G6 conditional on MD-1".

## 1. Regression: local suite results versus PR-5a

| Check | PR-5a (64f8a18) | PR-6 (this commit) | Log |
|---|---|---|---|
| pytest (repository root) | 139 passed | **139 passed** | `pr6/logs/pytest.log` |
| Vitest | 197 passed | **213 passed** (+16 `pr6.test.ts`) | `vitest.log` |
| Playwright (all specs, mocked structures) | 163 passed, 1 skipped | **246 passed, 1 skipped** (+60 axe/responsive, +23 reliability) | `playwright_full.log` |
| TypeScript `tsc --noEmit` / `npm run build` | pass | pass | `tsc.log`, `build.log` |
| Schema types / structure fixtures / drilldown golden `--check` | pass | pass | `schema_check.log`, `fixtures_check.log`, `golden_check.log` |
| SQL reconciliation (57 SQL-replayed + 1 derived) | 58/58 | pass (exit 0) | `pr6/reconciliation/`, `reconciliation.log` |
| PR-6 independent scientific audit | n/a | **47/47** | `pr6/scientific_audit_table.md` |
| PR-6 audit mutation self-test | n/a | control passes; **12/12 mutations rejected** | `pr6/scientific_audit_mutations.json` |
| Export drift vs committed export | n/a | 5,325/5,325 files identical except provenance fields, plus one expected change: the `README.md` checksum in `downloads.json` (README edited, D-48) and the `export_manifest` hash of that file | `export_drift.log`, `export_drift_detail.log` |

Legacy tests: the release suite (`tests/`) is included in the 139 pytest results. The legacy `site/` is byte-identical.

## 2. (A) Scientific integrity

`web/scripts/pr6_scientific_audit.py` reads the DB read-only, uses its own Newick parser, and does not import the exporter. It reconciles the export against SQLite and the refpkg. Its 47/47 PASS covers:
- **Records:** 5,466 source / 5,460 counted / 6 engineered / 5,299 MRDB (129 multi-source). Per-record equality holds on 30 columns. The only representation change is DB `""` rendered as `null` (clade_id 1,312; subclade_id 1,741).
- **Evidence:** E1 88 counted / 91 total.
- **Membership:** members + candidates 4,468; confident 3,821. MR_CLD3_017 has 1,646 records, of which 597 are tentative.
- **Structures:** PDB links 472 / 438 / 66; AFDB 4,397.
- **Tree:**
  - Treefiles are byte-identical to the refpkg, with 472 tips.
  - The 469 bipartitions are identical between rooted and run1.
  - Displayed support equals the run1 label for all 469; there are 17 rooted-label disagreements, which are documented.
  - The outgroup is 15 tips forming one root child.
  - Tip roles are 394/57/4/15/2.
- **Clades:** 19 level-1 groups and 30 subclades, all monophyletic. Support equals run1, except **MR_CLD3_017 (DB 100/100 vs run1 50.3/72)**, which is the only group failing SH-aLRT >= 80 / UFBoot >= 95. The site flags it.
- **Placements:** 4,996 current. Record placement objects equal the DB on all fields. Every best edge is in the 941-edge map. There are 27 unclustered backbone tips.

The mutation self-test confirms that the audit detects the following corruptions:
- evidence, membership, clade or engineered flags;
- a dropped record;
- swapped support values;
- a moved tip;
- a wrong edge;
- MR_CLD3_017 marked as robust;
- a mislinked PDB;
- a wrong MRDB map;
- a changed placement edge.

**Claim audit of the UI copy (manual, from source):**
- The MR_CLD3_017 robustness caveat appears on Clade, record and Methods pages (`CladeSupportNotice`, `clade-robustness`).
- "Formal assignment" (record_clade) is shown apart from "EPA-ng placement" (`AssignmentsVsPlacements`). The Phylogeny page states that placed records are not tips.
- Sequence search is described as "not exhaustive" and as not computing the membership score (Search, Methods, Help). The site says it "computes no new classification".
- The watchlist is described as excluded from all statistics and as "not rhodopsin classifications".

No displayed claim was found that exceeds its evidence. **No scientific data, threshold or classification was changed.**

## 3. (B) Performance (lab, `pr6/performance_audit_generated.md`, 3 cold runs, median)

**Environment:**
- Desktop: 1440x900, RTT 40 ms, 10 Mbit/s, CPU 1x.
- Mobile: 375x812 DPR 2, RTT 562.5 ms, 1.47 Mbit/s, CPU 4x (DevTools Slow-4G-like).
- Server: local gzip, no-store.

**Bundles:**
- Initial JS+CSS is 62.3 KiB gzip (54.3 KiB brotli), against the legacy monolithic ~4.35 MB data.js payload.
- The Home cold load transfers 277 KiB in total, with no `corpus.fasta`, no Mol* and no records index.
- Mol* (853 KiB gzip) and echarts (154 KiB gzip) are lazy chunks.

**Desktop results:**
- LCP 256-852 ms on all 20 routes.
- CLS <= 0.005.
- INP <= 72 ms.
- Sequence search of P02945 takes 1.8 s in a worker, with 0 long tasks.
- Tree layout and support toggles take ~100 ms.

**Mobile results:**
- CLS 0.000-0.021 on load.
- LCP 2.3-6.4 s. Data-heavy routes (Browse, Record, Evidence) are over the 2.5 s target, and FCP alone is ~1.7 s at 562 ms RTT.
- INP: Browse 208 ms, Phylogeny 120 ms.
- Mol* first load (mocked structure, SwiftShader) takes 11.4 s with a 1.6 s long task.

**Memory:** the JS heap after 3 navigation rounds is 23.5, 23.8 and 24.1 MB, with no growth trend.

**Fix applied (D-47):**
- Before: the footer was painted in the viewport and then pushed out, giving CLS 0.17 (desktop) and 0.40 (mobile).
- Change: `<main>` now reserves the viewport height.
- After: CLS is ~0 on all routes.

**Remaining:** see P2-1 to P2-3 and P3-1 to P3-3.

## 4. (C) Accessibility and responsive design

**axe-core 4.13** (wcag2a/2aa/21a/21aa/22aa) was run on 20 routes x 375/768/1440, giving 60 pages. Every page has **0 violations of any impact** and **0 px page overflow**. The checks also covered:
- landmarks, one `h1` per page, and labelled controls;
- the skip link and visible focus;
- keyboard operation of the mobile menu.

axe left 4,159 colour-contrast nodes as "incomplete". These were overlaps, images, short text and non-BMP glyphs. They were resolved by an independent computed-style scan of 33,813 HTML and SVG text nodes, which found **0 active-text failures**; the lowest ratio was 4.65. Disabled controls are at 4.33, which WCAG 1.4.3 exempts.

**Fixes (D-43):**
- In-prose links are underlined.
- `link-row` targets are at least 24 px.
- 5 scrollable Clade tables are focusable labelled regions.
- `aria-controls` is set only while tree-search results exist.
- A redundant label was removed from the sequence `<pre>`.

**Text alternatives:** the tree canvas has `aria-describedby` and a button that focuses the Clade Explorer table. Structures keep their tabular metadata and the viewer status text. Screenshots: `pr6/screenshots/` (60). axe JSON: `pr6/axe/` (60).

**Not done:** manual screen-reader sessions (NVDA/VoiceOver) were not possible in the sandbox and are recommended before PR-7. This is P3-6.

## 5. (D) Security and reliability

**Security:**
- No `innerHTML` or `eval` exists in `src/`.
- The new `safeExternalUrl` allows only relative, http(s) and mailto URLs. It is applied to every external link built from data; anything else renders as inert text.
- ECharts tooltip labels are escaped.
- All `target=_blank` links carry `rel="noopener noreferrer"`.
- A build-time CSP `<meta>` sets `default-src 'self'`. Connections are allowed only to RCSB model/file hosts and AFDB. `object-src 'none'`. Inline style is permitted for React/ECharts.
- Dependencies are exact-pinned (`npm ci`).

**Reliability:**
- Data requests time out after 45 s, and truncated JSON raises a typed error.
- A failed search worker now reports a user-facing message. Previously it raised a null `postMessage` TypeError (D-46).

**Tests:** 23 reliability tests cover:
- malformed routes and invalid accessions;
- data 404/500/truncated/timeout;
- worker 404;
- RCSB and AFDB failure;
- failed downloads;
- repeated interactions and back/forward;
- a memory check.

## 6. (E) Publication readiness

See `pr6/publication_readiness.md`. The README now has website export/dev/build/preview/validation commands, and states that deployment is PR-7. Licence, date, DOI and contact were **not** edited.

## 7. Unresolved issues

| ID | Sev. | Issue | Blocks PR-7 |
|---|---|---|---|
| MD-1 | decision | Code licence conflict: README/DB/package.json say MIT; LICENSE and CITATION say CC BY 4.0 | **Yes** |
| MD-2 | decision | Release date: 2026-10-10 (README/DB) vs 2026-10-09 (CITATION.cff) | **Yes** |
| MD-3 | decision | No DOI; Citation page shows "not supplied" | **Yes**, if a DOI is required for publication |
| MD-4 | decision | No contact address (MAINTENANCE placeholder) | **Yes** (spec 14.8) |
| MD-5 | decision | MAINTENANCE placeholders: cadence, hosting term, funding, successor | **Yes** (spec 14.8) |
| PR7-1 | scope | `deploy-site.yml`, `WEB_BUILD_AND_DEPLOY.md` and rollback docs do not exist yet; they are PR-7 deliverables | **Yes**, until PR-7 delivers them |
| P2-1 | P2 | Mobile `#/search?mode=sequence`: CLS 0.259 after a search completes. When the results table renders ~8 s after the click (beyond the 500 ms input exclusion), the footer moves out of view. Load-time CLS is 0. | No |
| P2-2 | P2 | Mobile Slow-4G LCP is above 2.5 s on 15/20 routes (2.3-6.4 s; desktop <= 0.85 s). The cause is round trips plus `records-index.json` (392 KiB gzip) and `accessions.json` (~320 KiB gzip) on record cold loads. Sharding would need an exporter/schema change. | No |
| P2-3 | P2 | Mobile Browse INP is 208 ms (median of 3, threshold 200; the pilot gave 192) | No |
| P3-1 | P3 | Mol* first load has a ~1.1 s (desktop) / 1.6 s (mobile) long task; it is lazy and only runs on user request | No |
| P3-2 | P3 | echarts 5.6.0 advisory GHSA-fgmj-fm8m-jvvx (line-series tooltip XSS). Not reachable: only Bar is registered and the formatter is escaped. The fix is semver-major. | No |
| P3-3 | P3 | The CSP is a `<meta>` tag. `frame-ancestors` and reporting cannot be set on GitHub Pages, and `style-src 'unsafe-inline'` is required. | No |
| P3-4 | P3 | TSV downloads do not neutralise spreadsheet formula prefixes. The data are UniProt/curated text, and altering values would change exports. | No |
| P3-5 | P3 | CITATION abstract wording ("~472 tips", "19 named subfamilies" vs 17 named + 2 backbone groups) | No |
| P3-6 | P3 | No manual screen-reader session (automated checks only) | No |
| P3-7 | P3 | The Structures PDB table scrolls horizontally inside its own labelled region on mobile; the page itself does not overflow | No |
| P3-8 | P3 | Disabled tree controls have 4.33:1 contrast (WCAG-exempt) | No |

## 8. Deviations (D-41 onward)

| ID | Deviation |
|---|---|
| D-41 | Dev dependencies `@axe-core/playwright` 4.13.0 and `web-vitals` 6.2.3 were added (exact pins). |
| D-42 | CSP is delivered as a build-time `<meta>` tag (`web/csp.config.ts`), because GitHub Pages cannot set headers. |
| D-43 | Accessibility CSS/markup fixes: link underline, 24 px targets, focusable table regions, `aria-controls`, tree text alternative. There is no visual redesign. |
| D-44 | Data fetch timeout of 45 s (test override `window.__MRDB_DATA_TIMEOUT_MS`), and a typed error for truncated JSON. |
| D-45 | `safeExternalUrl` and `escapeHtml` (`src/lib/safe.ts`). Unsafe URLs render as inert text. |
| D-46 | The search client keeps the worker failure reason instead of dereferencing a null worker. |
| D-47 | `<main class="min-h-screen">` fixes load-time CLS. |
| D-48 | New audit scripts (`pr6_scientific_audit.py`, `pr6_audit_mutations.py`, `pr6_perf*.{py,mjs}`, `serve_perf.py`). The README gets a Website 2.0 command section. `package.json` gets a `preview` script, version 2.0.0-pr6 and a description fix. The CI workflow runs the PR-6 audit (it has not run). |

The deliverable names in the spec (`WEB_ACCEPTANCE_REPORT.md`, `WEB_KNOWN_LIMITATIONS.md`) are short pointer files to this report.
