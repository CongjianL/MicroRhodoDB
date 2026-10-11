# PR-3a correction report: targeted fixes to the Protein Entry page

Branch `website/pr-3-protein-entry`, on top of PR-3 commit `3ff0c1e`. The scope is the five corrections from the PR-3 review (CONDITIONAL PASS), plus a regression test for each. Nothing else was changed:

- no frozen scientific data, reference trees, releases or SQLite database;
- no data-export schema (1.1.0) or exporter;
- no membership or function annotation;
- no unrelated refactoring.

The website version stays `2.0.0-pr2`, as in PR-3.

## 1. Local checks vs CI

All checks below ran locally in the development sandbox (headless Chromium with SwiftShader WebGL). **CI has not run.** Nothing was pushed, merged or deployed.

| Check | Result (local) |
|---|---|
| TypeScript (`tsc --noEmit -p .`, includes tests) | exit 0 |
| Build (`npm run build`) | exit 0 |
| Vitest (`web/tests/unit`) | 9 files, **94 passed**. PR-3 had 7 files / 72 tests. 22 new tests and 2 new files |
| Playwright (`web/tests/e2e`, includes the responsive and layout tests) | 92 tests: **91 passed, 1 skipped**. The skipped test is `@live`, excluded by default. PR-3 had 77 (76 + 1); 15 are new |
| Playwright `@live` (`E2E_LIVE=1`, real RCSB and AlphaFold DB) | 1 passed |
| pytest (repository root) | **89 passed**, unchanged |
| `schema_to_ts.py --check` | `types.ts is up to date` |
| `fetch_structure_fixtures.py --check` | all structure fixtures OK |
| Frozen checksums `docs/website/baseline/frozen_sha256_fab9182.txt` | 176/176 OK |
| Reference package `refpkg/MR_RT_003/SHA256SUMS` | 37/37 OK |
| v1.6.0 SQLite sha256 | `379a2543...dce17f`, unchanged |
| `git diff 3ff0c1e -- releases refpkg pipeline site tools` | empty |
| Re-export `tools/export_web_data.py` vs `web/public/data` | 5,321 files with the same paths. 5,319 are byte-identical. `manifest.json` and `export_manifest.json` differ only in the exporter git-commit provenance fields |
| Responsive audit (375/768/1440; Home, Browse, About, records) | 27 page/viewport audits, no horizontal overflow, 0 console errors (`pr3a/responsive_audit.json`) |
| `git diff --cached --check` | clean |

**Mutation check.** The new tests were confirmed to fail when the following fixes are reverted:

| Fix reverted | New e2e tests that fail |
|---|---|
| Hardcoded `1 of N` | 2 position tests |
| Abort and generation check removed from the viewer | 4 race tests |
| Highlighted label put back at the old radius | the MR_CLD3_017 label test |
| Copy link without the query | the Copy link test |
| `export_id` ignoring the sort order | the Browse export test, and 2 unit tests |

The three unmount and source-switch race tests passed under the viewer mutation, because they are guarded by the separate unmount/dispose path. The provenance tests were not mutation-tested.

The fixes were restored afterwards and the full suite was re-run.

## 2. Corrections

### 2.1 Multi-accession numbering

**Root cause.** The eyebrow in `RecordPage.tsx` rendered `(1 of ${entry.n_source_records})` for every source. Opening `#/record/B0R5N9` therefore showed "1 of 2", although B0R5N9 is the second source of MRDB000001.

**Fix.**
- New `sourcePosition(entry, sourceAcc)` in `lib/entry.ts` gives the 1-based position in `entry.sources`. This is the order of the source-record table on the page.
- The eyebrow shows ` (i of N)` only when N > 1. It is exposed as `data-testid="source-position"` with `data-index` and `data-total`.

**Tests.**

Unit:
- MRDB000001: P02945 is 1 of 2 and B0R5N9 is 2 of 2.
- MRDB000249: positions 1–7.
- A single-source entry has total 1.
- The integrity sweep now asserts `sources.length == n_source_records` and the position of every one of the 5,466 sources.

E2E:
- B0R5N9 shows "(2 of 2)", and switching to P02945 shows "(1 of 2)".
- Each of the 7 MRDB000249 sources, opened in table order, shows its own index.
- MRDB000009 shows no position.

### 2.2 Mol* asynchronous race conditions

**Root cause.**
- In PR-3 every `load()` awaited fetch and build steps and then set the phase unconditionally.
- A slower, older request could therefore finish after a newer one and overwrite both the displayed structure and the status.
- The plugin creation in `ensureViewer` was not single-flight: two loads started while the Mol* chunk was still downloading could create two plugins.
- An unmount during initialisation could leave a plugin that was never disposed.

**Fix.** There are two layers.

1. **`StructureViewer.tsx`**
   - Each `load` takes a generation number from `Generations` and aborts the previous request's `AbortController`.
   - Every UI update is guarded by `live()`: mounted, latest generation, and not aborted.
   - Plugin creation is single-flight (`SingleFlight`). If the component unmounted in the meantime, the new plugin is disposed immediately.
   - Unmount invalidates all generations, aborts, and disposes.

2. **`molstarViewer.ts`**
   - All Mol* state changes (clear/build, style, colouring, ligand toggle, dispose) run under a FIFO `Mutex`, so builds can never interleave.
   - Fetching happens outside the lock.
   - A superseded request never enters the build. If it is superseded during the build, it clears its partial state and reports "aborted", not success.
   - A failed current request clears the old structure, so an outdated structure is never left on screen under an error.
   - `dispose()` is idempotent and queued behind running work.

`loadControl.ts` holds the three primitives as small, Mol*-free classes.

**Test hook.** The wrapper fills `window.__MRDB_VIEWER_STATS` only when a page defines that object first. It records plugins created and disposed, every label committed to the Mol* state (in order), and the label currently committed. Production pages never define it.

**Tests.**

Unit (`loadControl.test.ts`, 7 tests):
- a stale generation cannot commit;
- FIFO without interleaving;
- a rejected or synchronously throwing section does not block the queue;
- concurrent `get` calls share one initialisation, and it resets after failure.

E2E (`record_pr3a.spec.ts`, 7 race tests):
- **Slow 5ZIM superseded by AFDB.** 5ZIM is delayed 3 s and the selection switches to AFDB. AFDB is shown, `current` is AFDB, 5ZIM is never committed, and one plugin is created.
- **Five rapid picker changes.** Responses are delayed 2.5 / 1.2 / 0.4 s. The final 4Y9H wins, and nothing other than 4Y9H is ever committed.
- **Double Retry.** Retry is clicked twice in one task after a 404. Exactly one commit, one plugin.
- **Picker changed twice while the Mol* chunk is delayed 2 s.** One plugin, and only the final AFDB model is fetched.
- **Leave the page during loading.** created = disposed = 1, nothing committed.
- **Leave the page during initialisation.** No plugin is ever created.
- **Switch source during loading.** The old viewer is disposed and the new one is idle on 4Y9H.

### 2.3 Browse export file names

**Root cause.** This was the unresolved PR-2 issue. File names used only `fnv1a(filterQuery)`. Exports list rows in the displayed sort order, so the same filters under two sort orders produced different files with identical names.

**Fix.**
- `exportIds(filterQ, sortKey, sortDir)` in `lib/exporters.ts` returns three values:
  - `selection_id = fnv1a(filterQ)`, unchanged and filter-only;
  - `sort_token`, which is `key:asc|desc`, or `index` when unsorted (the direction is then ignored);
  - `export_id = fnv1a(filterQ + "\0sort=" + sort_token)`.
- File names are now `microrhododb_v1.6.0_browse_<selection_id>_<export_id>_<n>_source_records.tsv`, with the same pattern for `.fasta`, `_mrdb_sequences.fasta` and `_selection.json`.
- `ExportMenu` and the selection manifest call the same function, so the names cannot drift apart.
- The manifest gains `export_id`, `sort_token`, `files.manifest`, and a note explaining the two ids.

The data-export schema is untouched; this manifest is the client-side download manifest.

**Tests.**

Unit:
- One filter with four sort variants: one `selection_id`, four `export_id`s, and four distinct names for each file kind.
- Unsorted output ignores the direction.
- The manifest `files` equal `exportFilename` for every kind and sort.

E2E:
- The existing 88-row E1 export test asserts the new pattern, `sort_token: "length:desc"`, and that manifest `files` equal the four downloaded names.
- A new test downloads the same selection sorted length-desc, length-asc and unsorted:
  - the bodies differ in order but contain the same row set;
  - all three share one `selection_id`, with three `export_id`s and three names;
  - repeating length-desc reproduces the same name.

### 2.4 Release-model provenance warning

**Root cause.** v1.6.0 stores method `ESMCFold2 (full)` for the two release models, B0R633 and A0A9X2L7U0. Their stored notes say "ESMFold prediction ..." and their files are named `*_esmfold.pdb`. PR-3 showed these values verbatim but did not flag the contradiction.

**Fix.**
- `releaseModelProvenanceWarning(model)` returns a warning when the method names ESMCFold but the note and/or file name name ESMFold. It names only the fields that disagree.
- The warning reads:

  > Method label discrepancy: the stored method is "ESMCFold2 (full)", but the note and file name refer to ESMFold. ESMCFold2 and ESMFold are different predictors; which one produced this model cannot be confirmed from the v1.6.0 release metadata. Values are shown as stored and have not been corrected.

- It appears in the Predicted structures card (with a "provenance" badge) and in the viewer detail line whenever the release model is selected.
- Method, note, file name and checksum are still displayed exactly as stored, and nothing in the data or the exporter was changed.

**Tests.**

Unit:
- Both models warn.
- The model object is unchanged after the call (JSON before = after).
- `releaseOption` carries the warning.
- Consistent labels produce no warning.

E2E:
- For both records, the warning is visible in the Predicted section and in the viewer, and the verbatim method and note are still shown.
- Experimental selections show no warning.

### 2.5 Minor UI

**MR_CLD3_017 mini-tree label.**
- *Root cause.* Labels sat at a fixed radius `ring1 + 15`. The highlight outline (`ring1 + 4`, 3 px stroke, outer edge `ring1 + 5.5`) is drawn above the labels. At the MR_CLD3_017 bisector angle, the inner half of the "017!" box therefore lay under the outline.
- *Fix.* `labelPlacement.ts` pushes only the highlighted group's label outward. It uses the smallest radius at which every point of a conservative text box is at least 2 px outside the outline.
  - The drawing extent grows only if that label would otherwise be clipped.
  - The Home tree and non-highlighted labels are unchanged.
  - The "!" for failing clades is now part of the same text string.
- *Tests.*
  - Unit: clearance across 720 angles × 4 label strings × 3 font sizes.
  - E2E: for A0A135LS53 the highlighted label is `MR_CLD3_017` / "017!", and its rendered SVG bounding box (real font metrics) has a minimum origin distance ≥ the outline radius. It lies inside the viewBox, and it is the topmost element at its centre.

**Copy link.**
- *Root cause.* `permalink()` rebuilt the hash from the accession only and dropped `section` and `structure`.
- *Fix.*
  - `permalinkQuery(hash)` parses the current hash with the same validator as page load and re-serialises it canonically. The copied link therefore keeps the selected section and structure, and drops invalid values.
  - The success message now reads "Link copied (includes the selected section and structure)."
- *Tests.*
  - Unit: valid, invalid and mixed parameters.
  - E2E: the clipboard is stubbed.
    - B0R5N9 + AFDB + Predicted section copies `#/record/B0R5N9?section=predicted&structure=afdb`.
    - `?section=bogus&structure=pdb:4Y9H` copies `structure=pdb:4Y9H` only.
    - Reopening the copied link restores the view.

## 3. Files changed

**Source**
- `web/src/pages/RecordPage.tsx`: position label, Copy link.
- `web/src/lib/entry.ts`: `sourcePosition`, `permalinkQuery`, `releaseModelProvenanceWarning`, optional `StructureOption.warning`.
- `web/src/features/structure/StructureViewer.tsx`, `molstarViewer.ts`, new `loadControl.ts`.
- `web/src/features/entry/StructureSections.tsx`: warning in the release-model card.
- `web/src/features/tree/TreePreview.tsx`, new `labelPlacement.ts`.
- `web/src/lib/exporters.ts`, `web/src/features/browse/ExportMenu.tsx`.

**Tests**
- `web/tests/unit/entry.test.ts` and `exporters.test.ts` (updated).
- New `loadControl.test.ts` and `labelPlacement.test.ts`.
- `web/tests/e2e/browse.spec.ts` (updated, plus 1 new test).
- New `record_pr3a.spec.ts` (14 tests).

**Docs**
- This report.
- `WEB_TEST_INVENTORY.md`: PR-3a row.
- `docs/website/pr3a/`:
  - `responsive_audit.json`;
  - screenshots: the eyebrow "(2 of 2)", the MR_CLD3_017 mini tree, the provenance warning, and refreshed phylogeny, release-model viewer and MRDB000249 record views.

## 4. Size and performance impact

The performance audit was not re-run because the changes are small.

| Chunk (raw KiB, from the build) | PR-3 | PR-3a |
|---|---|---|
| `RecordPage` | 66.3 | 68.6 |
| `molstarViewer` | 3,102.1 | 3,103.3 |
| `index` | 164.4 | 164.4 |

Home, Browse and About still never request the Mol* chunk; the existing isolation test passes.

## 5. Notes and limitations

- **Race tests.** They use controlled network delays and an opt-in diagnostics object, and they verify commit order and plugin lifecycle. They cannot cover every possible timing interleaving inside Mol*. The serialising lock is what guarantees ordering for those cases.
- **Label glyph width.** The clearance uses a conservative glyph width (0.72 em per character). It is checked in the browser against real font metrics, but an unusually wide fallback font could still reduce the margin.
- **Export file names.** Names changed from the PR-2 pattern. Any external script that matched `browse_<8 hex>_<n>_...` must allow the extra `_<export_id>` segment.
- **The method discrepancy itself is unresolved.** Settling which predictor produced the two models is a data-curation question for a future release and is outside this website PR.

## 6. Status

Committed locally on `website/pr-3-protein-entry`. A verified git bundle contains the full branch history. Stopped after PR-3a: no push, merge, deployment or PR-4 work, pending acceptance.
