# PR-4a auto-acceptance report: corrections to PR-4 and independent acceptance of PR-4 + PR-4a

> **Erratum (PR-6a, see `CI_STATUS.md`):** GitHub CI did run for this project. The `web-data` workflow passed on GitHub for PR-1 (`4b8391c`), PR-2 (`b5416b1`) and PR-3 (`7546a7a`). The statement that CI had "never" run applies only to the unpushed branches from PR-3a onward, including PR-4a, which have not yet had their own remote CI run.

- Branch: `website/pr-4-phylogeny`. PR-4a is one commit on top of PR-4 `ded4a840372573d2c841097bc14d110c62ba12f5` (parent PR-3a `7546a7a`).
- Dataset: v1.6.0 (frozen). Source DB SHA-256 `379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f`.
- Data export schema: **1.3.0** (additive over 1.2.0; `WEB_DATA_CONTRACT.md` section 13). Website version `2.0.0-pr4a`.
- Scientific scope: no new inference; no classification, function, clade assignment, membership score, tree or release changed.

## Decision

**PASS.** All 33 independent audit checks, all test suites, the build and all checksum gates pass locally. No P0/P1 defect remains open.
**PR-4 status: LOCAL_ACCEPTED** (PR-4 `ded4a84` + PR-4a; the accepted SHA is the PR-4a commit recorded in the delivery folder, `FINAL_COMMIT.txt`).
**GitHub CI has not run** for PR-4 or PR-4a; nothing here claims CI passed.

## 1. Local checks vs CI

All checks ran locally (Linux x86_64, Node 22, Python 3.11.16, Playwright Chromium). No CI has executed. The `web-data` workflow names its pytest files explicitly; this commit adds `tests/test_web_pr4a.py` to its path filter and pytest step (unexecuted).

| Check | Command (repo root unless noted) | Local result |
|---|---|---|
| Python suite | `python -m pytest -q tests/` | **117 passed** (PR-4: 110; +7 in new `tests/test_web_pr4a.py`) |
| Independent acceptance audit | `python web/scripts/pr4a_acceptance_audit.py --repo . --export web/public/data/v1.6.0 --baseline-export <PR-4 export>` | **33/33 PASS** |
| Generated TS types | `python web/scripts/schema_to_ts.py --check` | up to date |
| Structure fixtures | `python web/scripts/fetch_structure_fixtures.py --check` | 5/5 OK |
| TypeScript + build | `npm run typecheck && npm run build` (in `web/`) | 0 errors, exit 0 |
| Unit tests | `npx vitest run` | **11 files, 126 tests passed** (PR-4: 10 / 119; +7 in `cladeCounts.test.ts`) |
| Browser tests | `npx playwright test` | **117 passed, 1 skipped** (PR-4: 115 + 1; +2 clade tests; the skip is the PR-2 mobile-menu test at 1440 px) |
| Live smoke | `E2E_LIVE=1 npx playwright test --grep @live` | **1 passed** |
| Frozen files | `sha256sum -c docs/website/baseline/frozen_sha256_fab9182.txt` | **176/176 OK** |
| Reference package | `sha256sum -c SHA256SUMS` (in `refpkg/MR_RT_003/`) | **37/37 OK** |
| Source DB | `sha256sum` | matches `379a2543...dce17f` |
| Frozen trees untouched | `git diff 7546a7a -- releases refpkg pipeline site` | empty |
| Responsive screenshots | `node web/scripts/pr4a_screenshots.mjs <base> docs/website/pr4a/screenshots` | 12 PNG at 375/768/1440, 0 console errors, 0 horizontal overflow |
| Clone verification | fresh clone of the PR-4a commit, re-export, `npm ci`, all suites | recorded in the delivery folder |

## 2. The four PR-4a corrections

### 2.1 Backbone groups: 97 placements vs 94 formal assignments

The formal v1.6.0 rule (`pipeline/v150/record_clades.py`): a record belongs to a group if it is a reference tip of the group, or if its current MR_RT_003 placement has call `assigned` (LWR >= 0.9) **and** `placement_qc = ok` (LWR-weighted pendant <= 1.0). Backbone groups use `subclade_call`, because a backbone subclade call without a level-1 clade becomes the record's level-1 group.

| Group | Placements (`subclade_call = assigned`) | QC ok = formal | Long pendant = placement only | Reference tips | Formal total |
|---|---|---|---|---|---|
| MR_CLD3_B01 | 93 | 93 | 0 | 4 | **97** |
| MR_CLD3_B02 | 4 | 1 (A0A2P6NRH4, pendant 0.463) | 3 | 4 | **5** |
| Total | **97** | **94** | 3 | 8 | 102 |

The three placement-only records, values as stored:

| Source | MRDB | LWR-weighted pendant | subclade LWR | clade_call_qc | v_master clade | clade_state |
|---|---|---|---|---|---|---|
| A0A2P6MQ02 | MRDB002347 | 1.7339990644 | 1.0 | unassigned | none | unassigned |
| A0A2P6NAG6 | MRDB002348 | 1.4235411783 | 1.0 | unassigned | none | unassigned |
| A0A2P6NFX8 | MRDB002350 | 2.110793762 | 1.0 | unassigned | none | unassigned |

Their placements are kept and shown on the B02 page in a "Placement-only records (no formal assignment)" table with links to their entries. No assignment is created. Only backbone groups get this list: level-1 long-pendant placements are the tentative records (reachable through the tentative filter), and subclade long-pendant placements stay tentative at level 1.

### 2.2 Placement-based vs assignment-based counts (P1 defect, fixed)

PR-4 showed `placement_counts` (grouped by `clade_call_qc`, or by `subclade_call` for subclades and backbone groups) beside "Records assigned". For subclades and backbone groups, "assigned" in that grouping included long-pendant placements: e.g. MR_CLD3_017.02 showed 480 "assigned" placements while it has 311 formal members. Across the 30 subclades, 354 long-pendant placements with `subclade_call = assigned` were shown this way (plus the 3 B02 records). A reader could take placement counts for membership. **Severity P1** (scientifically misleading display; no data wrong).

Fix:
- Exporter (schema 1.3.0, additive): `assignment_counts` {reference_tips, placements, total, placements_assigned_call_failing_qc}, `placement_counts.call_field`, `placement_counts.by_call_and_qc`, `placement_only_records`, `is_engineered` on E1 anchors and representatives. The exporter fails closed if formal tips differ from reference tips in the corpus, or formal placements differ from placements with call assigned and QC ok.
- Clade page: "Formal assignments" stat (tips + placements passing QC); a new section "Formal assignments and EPA-ng placements" with a formal table and a placement table (call x QC ok / long pendant), a warning line for assigned-call placements that fail QC (level 1: "the tentative (distant_assigned) records"; elsewhere: "kept as placements only and carry no formal assignment"); subclade table columns "Formal assignments" and "Placements with subclade call assigned (QC ok / long pendant)".

Reconciliation, for all 49 groups (17 clades, 2 backbone groups, 30 subclades), recomputed from the DB:

| Invariant | Holds |
|---|---|
| formal total = `record_clade` rows = `v_master` rows with this `clade_id` (`subclade_id` for subclades) | 49/49 |
| formal reference tips = reference tips in the corpus | 49/49 |
| formal placements = placements with call assigned and `placement_qc = ok` = `record_clade.source = placement` | 49/49 |
| subclades and backbone groups: formal total = DB `clade.n_records_assigned` | 32/32 |
| level-1 clades: formal total = confident records; assigned-call long-pendant placements = tentative records | 17/17 |
| `placement_qc = ok` exactly when LWR-weighted pendant <= 1.0 | 4,996/4,996 placements |

Examples: MR_CLD3_017 formal 1,646 = 100 tips + 1,546; 597 long-pendant (tentative). MR_CLD3_017.02 formal 311 = 22 + 289; placements with subclade call assigned 480 (289 ok / 191 long pendant), plus 2 unassigned long pendant.

### 2.3 MR_CLD3_009: 12 E1 source records vs 11 counted

All 12 E1 records with `v_master.clade_id = MR_CLD3_009` are listed. A0A8X6EH36 (MRDB003178, Bacteriorhodopsin-like protein, a reference tip) is an engineered construct (`is_engineered = 1`, `counts_eligible = 0`) and is excluded from the official `clade.n_E1 = 11`, as every engineered construct is excluded from official counts. The page now names it in the E1 note. No other group has an excluded E1 record (tested).

### 2.4 SVG export size

`PR4_VALIDATION_REPORT.md` (and the PR-4 chat summary) said the SVG export was 4.6 MB. Measured: the PR-4 audit export (`#/phylogeny?support=1`, rectangular, all 472 labels, support marks, legacy hatching) is **158,004 bytes (154 KiB)**; the default view without support marks is **89,023 bytes**. The report is corrected, and the Playwright download test now asserts both sizes within bounds (50-150 kB and 100-300 kB) and at least 472 text labels.

## 3. Independent acceptance audit (PR-4 + PR-4a)

`web/scripts/pr4a_acceptance_audit.py` uses its own Newick tokenizer, bipartition code and SQL, written separately from the exporter and the pytest suites. It compares the export with the frozen refpkg, the read-only DB and a fresh export made with the PR-4 exporter (`ded4a84`). Log: `pr4a_acceptance_audit.log` / `.json` in the delivery folder.

| # | Check | Result |
|---|---|---|
| 1.1-1.4 | 472 unique tips = `tips.tsv` = explorer tips; 15 heliorhodopsin outgroups forming one root child; roles match | PASS |
| 2.1-2.4 | node table = rooted preorder topology; every branch length equals the frozen string; served rooted Newick byte-identical; DERIVED Newick identical to the frozen file once internal labels are removed | PASS |
| 3.1-3.3 | all 470 non-root rooted bipartitions found in run1, labels and numbers equal; 17 frozen-label disagreements (known shift); root unlabelled, root split displayed once | PASS |
| 4.1-4.4 | 17 clades, 2 backbone groups, 30 subclades = refpkg; each tip set is exactly one rooted clade at `mrca_node`; MR_CLD3_017 the only failing level-1 clade, run1 50.3/72 at its MRCA (100 tips), DB label 100/100 unchanged; all 30 subclades meet the rule | PASS |
| 5.1-5.5 | QC rule; formal vs placement invariants for 49 groups (every formal placement record is an assigned + ok placement into that group); backbone 97/94 and the 3 B02 records; MR_CLD3_009 12/11; placement status counts = DB | PASS |
| 6.1-6.6 | run1 byte copy; provenance SHA-256s; DERIVED README; export manifest lists exactly the 5,324 files with matching SHA-256; all 470 in-corpus tips resolve to record files (only QBQ84355, QBQ84358 absent); `edge_map` 941 entries, 1 root split | PASS |
| 7.1-7.7 | no diff in releases/refpkg/pipeline/site; 176 frozen + 37 refpkg checksums; DB SHA-256; vs PR-4 export: same 5,324 files, only `clades.json`, `manifest.json`, `export_manifest.json` changed beyond the schema-version string (`summary.json` and the DERIVED README differ only in "1.2.0" → "1.3.0"); every PR-4 field of `clades.json` unchanged; `manifest.counts` unchanged | PASS |

Navigation and downloads in the browser are covered by Playwright (tip → record → back, placement highlight, B02 placement-only links, frozen file byte/SHA-256 equality, DERIVED file, SVG/PNG).

## 4. Tests added or changed

- `tests/test_web_pr4a.py` (new, 7): schema 1.3.0; QC rule; 49-group invariants vs `record_clade`, `v_master`, `clade`; backbone 97/94; B02 placement-only records (no `v_master` clade); 354 subclade long-pendant placements without formal subclade; MR_CLD3_009.
- `tests/test_web_phylogeny.py`: expects schema 1.3.0.
- `web/tests/unit/cladeCounts.test.ts` (new, 7).
- `web/tests/e2e/clade.spec.ts`: 017 assertions moved from the old placement list to the formal/placement tables and the 017.02 subclade row; new B02/B01 test; new 009 test.
- `web/tests/e2e/phylogeny.spec.ts`: SVG export size bounds (default and support views).

## 5. Responsive evidence

`docs/website/pr4a/screenshots/` (12 PNG): B02, 017 and 009 at 375/768/1440; 017 subclade table, 017.02 and B01 at 1440. The first full run found horizontal overflow at 375 px caused by the new tables (533 px); fixed by wrapping row headers and putting each table in a horizontal scroll container; rerun clean.

## 6. Remaining limitations

- L-1 GitHub CI has not run. All results are local.
- L-2 Placement position along the branch is not stored in v1.6.0 (unchanged from PR-4).
- L-3 The placement-only list is exported for backbone groups only; subclade long-pendant placements are visible as counts, not as record lists.
- L-4 On 375 px screens the placement table scrolls horizontally to show the Total column.
- L-5 `.github/workflows/web-data.yml` now lists `tests/test_web_pr4a.py`, but that version of the workflow has not executed on GitHub (earlier versions passed for PR-1 to PR-3; see `CI_STATUS.md`), and its DB fetch step stays BLOCKED_DATA_SOURCE until the v1.6.0 Release asset is published.

## 7. Unresolved scientific issues (carried over; not changed)

1. MR_CLD3_017 fails the MR_CLD3 rule under corrected run1 support (50.3/72); shown as a legacy v1.6.0 assignment.
2. 7 of 17 level-1 clades have min cross-replicate Jaccard < 0.8 (006, 010, 011, 012, 013, 016, 017).
3. DB `tree_edge.length` differs from frozen lengths by up to 0.0039705737; not used for display.
4. The 17 misplaced support labels persist in the frozen rooted file.
5. Two reference tips are absent from the corpus (QBQ84355, QBQ84358).
6. PR-4 items 8 (backbone 97 vs 94) and 9 (MR_CLD3_009 12 vs 11) are **resolved** (explained, displayed, tested); no data change was needed.

## 8. Files

- Exporter / schema: `tools/export_web_data.py`, `web/src/data/schemas/web-data.schema.json`, `web/src/data/types.ts` (generated).
- Source: `web/src/features/tree/cladeCounts.ts` (new), `web/src/pages/CladePage.tsx`, `web/src/data/loaders.ts` (comment); `web/package.json`, `package-lock.json` (version).
- Tests: as in section 4.
- Tooling: `web/scripts/pr4a_acceptance_audit.py`, `web/scripts/pr4a_screenshots.mjs` (new).
- Docs: this report; `docs/website/pr4a/screenshots/`; `PR4_VALIDATION_REPORT.md` (SVG size, issues 8 and 9 marked resolved); `WEB_DATA_CONTRACT.md` section 13; `WEB_DATA_EXPORT.md`; `WEB_TEST_INVENTORY.md`.
- CI: `.github/workflows/web-data.yml` (adds `tests/test_web_pr4a.py`; not executed).
