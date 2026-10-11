# PR-5 validation report: Statistics, Evidence, Structures, Watchlist, Search, Downloads, Methods, Citation, Help

Branch `website/pr-5-explorers`, built on PR-4a (`148de8e`). Dataset release v1.6.0 is frozen and unchanged.
Website version `2.0.0-pr5`, web-data schema 1.4.0 (additive, see `WEB_DATA_CONTRACT.md` section 14).

## Decision

**PR-5 status: LOCAL_ACCEPTED (Gate G5 met on local evidence).** No spec 13.5 blocker was found. CI has **not** run
(nothing was pushed). Acceptance becomes final only after the `web-data` workflow (export validation, Vitest, Playwright) passes on GitHub and the
maintainer items in section 8 are settled; none of them blocks G5.

## 1. Local checks vs CI

| Check | Local result (this sandbox) | CI |
|---|---|---|
| pytest, all of `tests/` (pinned `mrdb` env on PATH) | **128 passed** (117 before + 11 in `tests/test_web_pr5.py`) | not run |
| Vitest (`web/tests/unit`) | **172 passed**, 13 files (+25 `pr5.test.ts`, +21 `seqsearch.test.ts`, `routes.test.ts` updated) | not run |
| Playwright (`web/tests/e2e`, Chromium) | **156 passed, 1 skipped** (the expected `@live` skip); new `pr5.spec.ts` 9 tests, `responsive` +30, `routes` planned-page test replaced | not run |
| `tsc --noEmit`, `npm run build` | clean; worker chunk `seqSearch.worker-*.js` (6.3 KiB) and Mol* (`molstarViewer-*.js`) are separate lazy chunks | not run |
| `schema_to_ts.py --check` | types.ts up to date | not run |
| Frozen baseline `frozen_sha256_fab9182.txt` | 176 / 176 OK | n/a |
| `refpkg/MR_RT_003/SHA256SUMS` | 37 / 37 OK | n/a |
| Release DB SHA-256 | `379a2543…dce17f` (unchanged) | n/a |
| `git diff 7546a7a -- releases refpkg pipeline site` | empty | n/a |
| `fetch_structure_fixtures.py --check` | 5 / 5 OK | n/a |
| Reconciliation (`web/scripts/pr5_reconciliation.py`) | 58 / 58 rows OK | n/a |
| Legacy golden regeneration (`legacy_seqsearch_golden.mjs --check`) | golden OK (13 cases), identical; 17 min 25 s | not in CI (slow) |

Logs: `docs/website/pr5/` (perf, reconciliation, responsive audit) and the delivery `logs/` folder.
Note: three `tests/test_v160_release.py` tests need `hmmsearch`, `hmmscan` and `snakemake`; they fail if the pinned
environment is not on PATH (environment, not code) and pass when it is.

## 2. Gate G5

| G5 criterion | Evidence | Result |
|---|---|---|
| Chart totals match source data | Every metric, distribution and crosstab carries its stored SQL; `test_every_stored_sql_reproduces_the_exported_value` replays all of them against the read-only DB (the NCBI-phylum chart replays its stated derivation). `pr5_reconciliation.md`: 58 / 58. In the browser the "Recount from records index" button recomputes 12 distributions from `records-index.json`; Playwright asserts "12 of 12 distributions match summary.json exactly". | met |
| Watchlist stays isolated | `watchlist.json` has no membership, score, evidence, MRDB, function or clade field (pytest); no resolved watchlist accession is in `v_master` or `records-index.json` (pytest); the page says "not admitted to the corpus", shows 181 candidates, has no membership/evidence column and loads neither `records-index.json` nor record files (Playwright). Statistics shows the 181 in its own panel, excluded from every corpus denominator. | met |
| Search golden cases remain valid | Sequence: `seqsearch.test.ts` runs the worker core on all 13 golden queries and matches the legacy hit lists (rank, accession, score, identity, coverage); pytest pins the golden file to the SHA-256 of the frozen `site/app.js` and `site/data.js`; Playwright runs the real Web Worker on the P02945 example (top hit P02945, identity 1). Text: golden cases in `pr5.test.ts` (accessions, MRDB IDs, PDB 1C3W, clade MR_CLD3_017, motif DTE, free text, organism) and 2 in Playwright (accession, PDB ID → P02945 with the `pdb` field). | met |
| Never claims to compute the official membership score | Search shows "It does not compute the official membership score and does not classify your query", states that the 3-mer prefilter is not exhaustive, and points to `tools/mrdb_search.py` (frozen v1.2 scorer, needs HMMER 3.4 + DIAMOND) for the official approximation. pytest scans every `.tsx` for an affirmative claim; Playwright scans the rendered text of all nine section pages. | met |

## 3. Spec 13.5 blockers (checked)

| # | Blocker | Status |
|---|---|---|
| 1 | Frozen DB / artefact / refpkg / threshold modified | not triggered: checksums and frozen diff above |
| 2 | Invented labels, PDB IDs, properties or topology | not triggered: all values are copied from the export; the Methods page quotes only stored rules |
| 3 | Tree reconstruction conflated with placement | not triggered (PR-4/4a pages unchanged) |
| 4 | Membership conflated with evidence level | not triggered: separate charts and a crosstab; Evidence opens with "a record's evidence level never makes it a Type-I member". Among counted records non-members are E5 only; the two E1 engineered constructs A0ABF7PQ84 and A0ABF7PQA2 remain `typeI_candidate` (pytest), which is exactly the separation |
| 5 | Wrong denominator (E1 counted vs total, watchlist vs corpus) | not triggered: E1 88 of 5,460 counted vs 91 of 5,466 incl. engineered, shown side by side with a toggle (88 → 91 tested); the watchlist is never added to a corpus count |
| 6 | Permalinks or FASTA/TSV downloads regress | not triggered: all PR-2 to PR-4a e2e tests pass; `#/novel` still redirects to `#/watchlist` |
| 7 | Accession mapped to the wrong protein | not triggered: worker hits are mapped through `hit.idx` and re-checked against `source_acc` |
| 8 | Undocumented fallback to stale `site/data.js` | not triggered: the app reads only the exported release files |
| 9 | Browser search presented as exhaustive or as an official classifier | not triggered: see G5 row 4 |

## 4. What was built

### 4.1 Pages (all navigation destinations are now real pages)

- **Statistics.** Corpus size (5,466 / 5,460 / 5,299 with the reconciliation sentence), membership status, evidence level
  (counted vs all toggle), evidence × membership-group crosstab, function class, taxonomy (domain, NCBI phylum top 12 +
  Other), helix-C motif (top 15 + Other) and motif class, length bins, clade state for members + candidates (3,821 of
  4,468 clade-confident), structure coverage, PDB method, watchlist panel. Each chart has a data table and a "How this
  is counted" block (denominator, inclusion policy, stored SQL, derivation). Optional filtered recount with explicit
  subset counts.
- **Evidence explorer.** E1–E5 definitions and counts, evidence × call-basis crosstab, record explorer (filter by level
  and basis), E1 table (88; 91 with engineered), curated membership overrides, conflict table (439 / 14 / 9 / 6 by action;
  downgraded → E5, flag_only_E1 → E1), stored rules, the 6 engineered constructs, 121 publications / 255 active links,
  LOCO and audit validation tables. Section deep links (`?s=`).
- **Structure explorer.** PDB entries (438 entries / 66 records / 472 links, units kept distinct), AlphaFold DB models
  (4,397), the 2 release models with a provenance warning; Mol* is fetched only after "View in 3D".
- **Watchlist.** 181 candidates, isolation banner, Foldseek funnel, family chart, TSV download; no corpus fields.
- **Search.** Unified text search (identifier, PDB, clade, motif, protein, organism; 200-row cap with a link to Browse)
  and sequence search in a Web Worker with the legacy method, input validation, progress, cancel, alignments and the
  method/limits callout.
- **Downloads** (39 release files with SHA-256, 37 refpkg files, documents, website files, release history,
  maintenance placeholders), **Methods** (11 sections from stored data), **Citation** (APA, BibTeX, CFF; DOI shown as
  "not supplied (pending confirmation by the maintainer)"), **Help** (page guide, 8 FAQs, accessibility, support).

### 4.2 Exporter (schema 1.4.0)

Additive only. Versus the PR-4a export: one new file (`downloads.json`); `summary.json` gains 6 metrics, 7
distributions and 2 crosstabs; `evidence-index.json` gains `validation`; no existing metric or distribution value
changed (compared file by file).

### 4.3 Sequence-search golden file

`tests/data/web_seqsearch_golden_v160.json` was produced by running the unmodified legacy search block of
`site/app.js` on `site/data.js` in a Node `vm` (12 CLI queries + P02945). Regenerating it takes more than 10 minutes in
this sandbox, so CI pins it by source hashes instead (pytest) and compares the worker against it (Vitest).
Regeneration result in this run: `golden OK (13 cases)`, byte-identical to the committed file, exit 0, 17 min 25 s wall time.

## 5. Performance (spec 13.4; `docs/website/pr5/perf_audit.md`)

Loopback server, no throttling, Chromium headless, 1440×900, cold cache, 5 runs per route; timings are relative.

- **Home** loads neither the corpus (`records-index.json`, `sequences/corpus.fasta`) nor Mol*: 266.3 KiB gzip total
  (PR-4: 260.3), ready 496 ms median (PR-4: 509).
- No PR-5 route loads Mol* without a click; Downloads, Citation and Help load only `downloads.json` (about 75 KiB gzip total).
- **Search runs off the main thread.** P02945 example search: 1,411 ms median, click to painted results; across
  5 runs one main-thread long task over 50 ms (longest 87 ms). The worker chunk is 2.6 KiB gzip.
- Statistics runtime recount: 252 ms median, longest long task 79 ms.
- WCAG AA text contrast: 0 failing colour pairs on all 11 routes (HTML text; SVG text not scanned). 0 console errors.
- The per-route request lists include files fetched by the timed interactions (for example `corpus.fasta` and
  `records/MRDB000001.json` on the sequence route). Playwright separately asserts that Statistics does not fetch
  `records-index.json` until the recount is requested.
- LCP / CLS / INP are not measured here (PR-6, Lighthouse).

## 6. Responsive evidence (`docs/website/pr5/responsive_audit.json`, `screenshots/`)

30 screenshots (10 PR-5 views × 375 / 768 / 1440 px). No horizontal page overflow and 0 console errors at any width.
The audit found one real defect, now fixed: at 375 and 768 px the Evidence page overflowed to 879 px because the visually
hidden "(opens in a new tab)" spans (`position: absolute`) in scrolling tables had no positioned ancestor and escaped
the scroll container. PR-5 scroll regions are now `position: relative` (D-36).

## 7. Deviations (as built)

- **D-29** Header search (`routeForQuery`) is unchanged: identifiers go to the record, anything else to Browse. The
  unified text search is the Search page.
- **D-30** Sequence input is validated before searching (20–5,000 residues; one record; reject text that looks
  nucleotide). The legacy page checked only the minimum length. This is an input gate; the scoring is unchanged.
- **D-31** The phylum chart uses the NCBI lineage, not GTDB (GTDB exists only for mapped prokaryotic records); the
  derivation is stored with the distribution.
- **D-32** Long categorical charts show top N + Other (phylum 12, helix-C motif 15); the data table lists every category.
- **D-33** The Methods page quotes stored rules and links documents at tag v1.6.0; it does not restate thresholds that
  are not stored in the release.
- **D-34** The refpkg file list uses a native `<details>` element instead of the Disclosure popover.
- **D-35** Text search shows at most 200 rows and links to Browse with the same query for the rest.
- **D-36** PR-5 table scroll regions are `position: relative` (fix from section 6). Pre-PR-5 scroll regions were not
  changed; they pass the overflow audit.

## 8. Maintainer items (not blockers; nothing was changed)

1. **Licence string.** The DB metadata (and README) says "CC BY 4.0 (data); MIT (code)"; the `LICENSE` file contains
   only CC BY 4.0, and `CITATION.cff` says CC-BY-4.0. Downloads shows the stored string as release metadata and states
   the `LICENSE` / CFF values.
2. **Release date.** DB metadata 2026-10-10 vs `CITATION.cff` `date-released` 2026-10-09; both shown.
3. **DOI.** None in `CITATION.cff`; shown as "not supplied (pending confirmation by the maintainer)" and omitted from BibTeX.
4. **Contact / maintenance placeholders.** Shown as "not supplied" on Downloads and Help.

## 9. Known limitations

- At 1440 px the Structures PDB table is wider than its column, so the "View in 3D" button is reached by scrolling
  inside the table region (no page overflow).
- Statistics, Evidence, Structures and text search fetch `records-index.json` (4.1 MB raw, about 350 KiB gzip).
- The browser sequence search is a 3-mer-prefiltered Smith–Waterman over the corpus only. It is not exhaustive and not
  a classifier, as the page states.

## 10. Files

- New pages: `web/src/pages/{Statistics,Evidence,Structures,Watchlist,Search,Downloads,Methods,Citation,Help}Page.tsx`
- New libraries and components: `web/src/lib/{stats,chartColors,citation,watchlist}.ts`,
  `web/src/components/{Provenance,Paged}.tsx`, `useSectionScroll.ts`, `web/src/features/search/*`
- Exporter and data: `tools/export_web_data.py`, schema and types
- Tests: `tests/test_web_pr5.py`, `web/tests/unit/{pr5,seqsearch}.test.ts`, `web/tests/e2e/pr5.spec.ts`, updated
  `routes`, `responsive`, `fixtures`
- Scripts: `web/scripts/legacy_seqsearch_golden.mjs`, `pr5_perf_audit.py`, `pr5_reconciliation.py`; `perf_capture.mjs` gains the `pr5` set
- CI: `.github/workflows/web-data.yml` runs `tests/test_web_pr5.py`
- Evidence: `docs/website/pr5/` (perf_audit, reconciliation, responsive_audit, screenshots)
