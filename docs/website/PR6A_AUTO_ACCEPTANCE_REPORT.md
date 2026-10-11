# PR-6a automatic acceptance report

**Verdict: PASS** (local). No unresolved P0 or P1 defect.
Status: `PR6A_LOCAL_ACCEPTED`. Remote CI for this commit: **not run** (branch not pushed; see `CI_STATUS.md`).

- Branch: `website/pr-6-acceptance`, base `68e301b88d5b1b7ad3aa735327ad2778e7615ae4` (PR-6).
- Dataset: v1.6.0 (frozen; unchanged). DB sha256 `379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f`.
- Logs: `pr6a/logs/` (`SUMMARY.txt` lists every gate exit code). Evidence: `pr6a/evidence/`.

## 1. Required corrections and how each was verified

| # | Requirement | Change | Verification |
|---|---|---|---|
| 1 | Mutation audit must not depend on `/workspace` | `web/scripts/pr6_audit_mutations.py` uses `scratch_root()`: `--tmp-root`, then `$RUNNER_TEMP`, then `tempfile.gettempdir()`; scratch directory removed in `finally`. No `/workspace` literal in any CI script. | `tests/test_web_pr6a.py` runs the full audit under a `sitecustomize` audit hook that makes `/workspace` (other than the checkout and the Python install) behave as missing and rejects writes outside the scratch directory: exit 0, 13/13 mutations detected, scratch removed. **Positive control**: the unmodified PR-6 script under the same hook exits 1 with `MISSING_WORKSPACE tempfile.mkdtemp /workspace/...` (`pr6a/evidence/adversarial_pr6_script_under_hook.txt`). |
| 2 | `web-data.yml` triggers cover README.md, LICENSE, CITATION.cff, MAINTENANCE.md, BINARIES.md | `pull_request` and `push` path filters list every repository document published by the exporter (also CHANGELOG.md, `index.html`, `docs/RELEASE_HISTORY.md` and the frozen inputs the exporter reads). Added `concurrency`, `persist-credentials: false`, explicit `pyyaml`. All earlier gates kept. | `tests/test_web_pr6a.py` parses the workflow with PyYAML and a GitHub path-glob matcher: each published document matches a trigger on both events; every gate and every `tests/test_web_*.py` is still invoked; permissions are `contents: read` at workflow and job level; every checkout sets `persist-credentials: false`; concurrency cancels superseded runs. Third-party actions are still referenced by major-version tag (not pinned to commit SHAs; not tested in PR-6a). `actionlint` exit 0. |
| 3 | Data-loading timeout must cover stalled response bodies | New `web/src/data/fetchText.ts`: inactivity (idle) timer over the whole transfer, re-armed on every progress event; on expiry the request is aborted and the UI receives "Timed out while loading ...". Used by all data loaders and by the sequence-search worker (timeout passed at worker init). | Vitest (12): stall after headers times out; slow-but-progressing body does not; per-chunk re-arm; HTTP/network/truncated-JSON messages; worker timeout; XHR transport cases. Playwright (4): stalled `structures-index.json` body shows the timeout alert and Retry recovers; 6 x 700 ms drip is not cut off; stalled `corpus.fasta` body gives a search error with Run re-enabled; ordinary page loads finish every data request. |
| 4 | Correct CI-history wording | New `CI_STATUS.md` (GitHub API evidence, queried read-only). Errata added to the PR-4a, PR-5a, PR-6 and overall acceptance reports and to `pr6/publication_readiness.md`. | PR-1 `4b8391c` (run 38044933968), PR-2 `b5416b1` (38058112858), PR-3 `7546a7a` (38104338951) **passed** remote CI. PR-3a onward, including PR-5a and PR-6, were never pushed and have **no** remote run. No document now claims that CI never ran for the project. |

## 2. Defect found during acceptance (fixed)

The first full validation run failed: Playwright 157 failed / 92 passed (log kept as negative-control evidence:
`pr6a/evidence/playwright_full_fetch_reader_attempt_FAILED.log`).

- Cause: the first `fetchText` implementation read bodies with `fetch()` + `ReadableStream` reader. In Chromium, when
  script finishes reading before the network loader completes, the request is reported as `net::ERR_ABORTED`
  (`requestfailed`) although the data are complete. Measured in-browser over 100 parallel small-file fetches:
  `response.text()` 0 failures, stream reader 85 failures, XMLHttpRequest 0 failures. Instrumenting
  `AbortController.abort` and `reader.cancel` showed no script-initiated abort.
- Fix: `fetchText` uses XMLHttpRequest (main thread and worker). Idle timer re-armed on `readystatechange`
  (readyState >= 2) and `progress`; `xhr.abort()` on expiry. The stream-reader path remains only as a fallback where
  XHR is absent (Node unit tests).
- Regression test: "PR-6a data transport > ordinary page loads finish every data request" asserts zero
  `requestfailed` events across Browse, Statistics and an entry page plus reload.
- Two other first-run failures were harness issues: an invalid actionlint flag (`-color=never`; now `-no-color`) and a
  stale local `web/public/data` export (re-exported; drift check now exit 0).

## 3. Final validation run (all gates exit 0)

| Gate | Result |
|---|---|
| Frozen baseline, refpkg checksums, frozen diff, DB sha256 | exit 0 (no frozen file changed) |
| Export drift, schema, fixtures, golden, reconciliation | exit 0 (5,325 files) |
| PR-6 scientific audit; mutation self-test (13/13) | exit 0 |
| actionlint (`web-data.yml`) | exit 0 |
| pytest | 148 passed (PR-6: 139) |
| tsc, `npm run build` | exit 0 |
| Vitest | 225 passed, 16 files (PR-6: 213) |
| Playwright full suite | 250 passed, 1 skipped (`@live`) (PR-6: 246) |

## 4. Deviations

| ID | Deviation |
|---|---|
| D-49 | Data timeout is an inactivity (idle) timeout over the full transfer, default 45 s, not a total-duration limit, so slow but progressing downloads (e.g. `corpus.fasta` on slow links) complete. |
| D-50 | Transport is XMLHttpRequest, not `fetch()` streaming, because of the Chromium `ERR_ABORTED` behaviour in section 2. |
| D-51 | Sequence-search worker receives the timeout at init and applies the same idle rule to `corpus.fasta`. |
| D-52 | `serve_e2e.py` gains test-only endpoints `/__test__/stall` and `/__test__/drip`. They exist only in the E2E server, never in the build output. |
| D-53 | `web-data.yml`: `push` trigger added alongside `pull_request`; `concurrency`; `persist-credentials: false`; PyYAML installed for workflow tests. |
| D-54 | Mutation audit counts a mutation as detected only when a check fails (not when the harness crashes). |
| D-55 | E2E race fix: `pr5.spec.ts` waits until the example sequence is in the input before clicking Run. |

## 5. Residual risks (not blocking)

- Remote CI has not run for PR-3a through PR-6a. Pending until the maintainer pushes.
- Idle timeout cannot detect a server that keeps sending bytes indefinitely; the files are static and bounded.
- Maintainer metadata decisions (MD-1 to MD-5) and release-asset gaps remain open; they are tracked as production
  blockers in PR-7 and do not affect local development.
