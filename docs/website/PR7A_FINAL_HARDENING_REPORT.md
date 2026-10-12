# PR-7a Final Release-Gate Hardening Report

Branch `website/pr-7-deployment`, based on `82c3aff673f253e2bb20e0eec562deb97c704374` (PR-7, review verdict
CONDITIONAL PASS). Implementation commit: `26405befa363b6c7baf6d3e60ec2c77491395d8c`. This report and the evidence are in the following
documentation commit. Dataset v1.6.0 is frozen and unchanged. Nothing was pushed, merged or deployed, and no
GitHub Pages or environment setting was changed. Every release-blocker status in `release_blockers.json` is
still `open` with `resolution: null`.

**Status: PR7A_LOCAL_PASS, remote CI pending.** Every feasible local check passed (section 6). None of the PR-3a
to PR-7a commits has run on GitHub Actions (CI-1).

## 1. Scope (only the three requested corrections)

| # | Review finding | Correction |
|---|---|---|
| 1 | Release-gate test paradox: some tests required all blockers to stay open forever, and required production mode always to exit 3. Resolving the blockers would therefore have broken CI. | Four state-dependent tests were removed. They were replaced by state-independent tests that use synthetic checklists, synthetic repositories and a synthetic GitHub API. The tests cover the positive path (fully resolved and authorised blockers exit 0) and every negative path. |
| 2 | Post-deployment verifier fetched 5,373 files one after another. The shell retry loop was unbounded (10 x (full pass + 60 s)). There was no deadline for each request or for the run as a whole. | Bounded worker pool, explicit per-request and total deadlines, and controlled retries for each file. Only files that have not converged are re-checked. Full-file SHA-256 is unchanged. Regression tests inject faults on a local server. |
| 3 | Production prerequisites: the Pages-source check and environment-protection checks must fail closed, and a resolution must not be able to bypass mandatory validation. | OPS-1 now has an automated check, and OPS-2 is stricter. Every API error, malformed response or exception in a check counts as "not passing". There is a hard-coded set of mandatory blockers, tampering with the checklist is detected, and resolution records are validated. Production mode requires `--online` and a full `--sha`. |

Out of scope, and unchanged: website code, the exporter, data, the build, the artifact verifier V1-V11, and the
`web-data.yml` and `site-preview.yml` workflows.

## 2. Release gate (`web/scripts/release_gate.py`)

### 2.1 Rules (all fail-closed)

- A blocker is resolved only when (a) its status is exactly `resolved`, (b) it has a **valid** maintainer record
  and (c) its automated check returns exactly `True`. ACC-1 has no automated check and needs (a) and (b).
- A record is valid only if:
  - `decided_by` matches the GitHub-login pattern;
  - `decided_at` is a real `YYYY-MM-DD` date and not in the future (UTC);
  - `reference` is an `https://` URL whose host is not reserved (example.com/.org/.net, `.invalid`, `.example`,
    `.test`, `.localhost`);
  - no field contains `<`, `>` or `<<PLACEHOLDER`.
- `MANDATORY_BLOCKERS` (MD-1 to MD-5, RA-1, RA-2, OPS-1, OPS-2, CI-1, VER-1, ACC-1) is hard-coded. Each of the
  following is a checklist problem that blocks production:
  - a mandatory blocker deleted from the JSON (it is re-added as unresolved);
  - `production` removed from a mandatory blocker's `blocks`;
  - a duplicate ID;
  - a status other than `open` or `resolved`;
  - a malformed entry;
  - an unreadable checklist, or one that is not a JSON object.
- Every check runs inside `try/except Exception`. An exception gives `None` ("not evaluated"), which never passes.
  The network primitive `_open_json` is shared by all API calls. A JSON body that is not an object is treated as
  an API error.
- `--mode production` without `--online`, or without a 40-hex `--sha`, exits 2. It can never pass offline.
  `--mode report` always exits 0.
- There is no override, waiver or skip flag. The deploy workflow has no `continue-on-error`, and the only `if:`
  conditions on gate-related steps are kind-based (a test enforces this).

### 2.2 Automated production prerequisites

| Check | Passes only if | Fail-closed cases (all tested) |
|---|---|---|
| OPS-1 Pages source (new) | `GET /repos/{o}/{r}/pages` returns an object with `build_type == "workflow"` | offline; HTTP 403/404/500; network error; non-object or invalid JSON; `build_type` missing, or `legacy` |
| OPS-2 environment protection (stricter) | `github-pages` has a `required_reviewers` rule with at least 1 reviewer; `deployment_branch_policy` = custom policies only (`custom_branch_policies is True`, `protected_branches is False`); the policy list is complete (`total_count` equals the number returned) and contains exactly one policy, `main`, of type `branch` | offline; API error on either endpoint; no reviewer rule; reviewer rule with 0 reviewers; extra branches (today: `None`, `website/pr-1-exporter`, `website/pr-3-protein-entry`); tag policy named `main`; policy without `type`; incomplete paginated list; all branches allowed; protected-branches mode |
| CI-1 remote CI (stricter) | a run with `path == .github/workflows/web-data.yml`, `head_sha == --sha`, `status completed`, `conclusion success` | other workflow reusing the name `web-data`; other commit; failure; in progress; API error |
| MD-2 / RA-1 (stricter) | as in PR-7 | online with an unreadable Release now gives `None`, not a pass based on files only; RA-1 also fails if BINARIES.md lists no assets |
| MD-1 (bug fix) | as in PR-7 | licence regexes are case-insensitive; a sentence-case LICENSE previously made a correct MD-1 fail (found by the independent check) |
| MD-3 (stricter) | DOI present, or a non-placeholder `alternative_citation_policy` string | empty or placeholder policy |

`prevent_self_review` and `can_admins_bypass` are **reported but not enforced**. The checklist describes disabling
admin bypass as optional, which is a maintainer decision. The runbook still requires self-review prevention.

`deploy-site.yml` preflight permissions are now `contents: read`, `actions: read` and `pages: read` (the last is
needed by OPS-1). Write scopes remain only in the `deploy` job.

### 2.3 Tests replaced

Removed (state-dependent):
- `test_gate_blocks_production_now_and_never_blocks_report_mode`;
- `test_checklist_is_open_and_resolution_only_by_maintainer`;
- `test_gate_allows_production_only_when_everything_resolved` (needed the real state);
- `test_current_repository_metadata_checks_fail_for_the_documented_reasons`.

Added (`tests/test_web_pr7.py`). They use a synthetic repository, a synthetic checklist and a synthetic GitHub/DOI
API that patches `_open_json`; real `urlopen` is blocked in these tests.

| Test | Cases | Expected |
|---|---|---|
| positive path: all 12 resolved with valid records, all checks pass, online, full SHA | 1 | `production_allowed`, CLI exit 0 |
| missing maintainer decision | 12 (one per blocker) | exit 3, exactly that blocker unresolved |
| invalid resolution record | 16 kinds x 3 blockers | blocked |
| failed automated check despite a valid record | 23 | blocked |
| API failure on each route | 6 error types x 6 routes | affected blockers `check None`, blocked |
| malformed API responses | 15 (list, string, null, wrong shapes) | blocked |
| exception inside a check | 1 | contained, blocked |
| checklist tampering | 6 (delete, re-scope, duplicate, invalid status, malformed entry, no list) | blocked |
| unreadable checklist | 4 | blocked |
| production needs `--online` and `--sha` | 1 test, several invocations | exit 2 |
| offline evaluation never allows production | 1 | |
| report mode never blocks | 2 | exit 0 |
| real checklist is well-formed whatever its state | 1 | 12 mandatory IDs, valid statuses, any resolved entry has a valid record |
| real repository checks are well-formed whatever their result | 1 | each returns (True, False or None, text) |

The gate part of `tests/test_web_pr7.py` now has 157 tests. None of them depends on whether the real blockers are
open or resolved.

## 3. Post-deployment verifier (`site_rollback.py verify-served`)

### 3.1 Why it changed

In PR-7 the verifier fetched every file with `urlopen(timeout=60)`, one after another. A 60 s socket timeout limits
each socket operation, not the whole request, so a CDN that drips bytes could hold a single request open
indefinitely. The artifact has 5,373 files, so even at 100 ms per request one pass takes about 9 minutes. In
`deploy-site.yml` the call sat inside a shell loop of up to 10 x (full pass + 60 s), but the job timeout was
30 minutes. A slow or partly propagated CDN therefore hit the job timeout rather than a clear, reported failure,
and every retry re-downloaded all 5,373 files. The legacy-rollback path checked only 5 of its 334 files.

### 3.2 Design

- **Bounded concurrency.** `ThreadPoolExecutor(max_workers=N)`. The default is 8; `deploy-site.yml` uses 16,
  which is modest for a CDN. The maximum number of requests in flight is measured and reported.
- **Per-request deadline.** `fetch_bounded` reads with `read1(64 KiB)` and re-checks a wall-clock limit between
  reads, so a slow-drip body ends at the limit. The socket timeout is set to the same value, and the limit is
  capped by the remaining total time. Further protections:
  - `Content-Length` must match the received bytes, so truncated bodies are never hashed as complete;
  - bodies are capped at 256 MiB;
  - `Cache-Control: no-cache` is sent.
- **Controlled retries.** Each file gets up to `--retries` (3) retries, with exponential backoff and jitter,
  only for network errors, timeouts and HTTP 408/425/429/500/502/503/504.
- **Partial CDN propagation.** A 404, another non-transient status, or bytes that differ from `SHA256SUMS` are
  not retried immediately. Those files, and only those, are re-checked in the next round after `--round-wait`
  (30 s), until all converge or the total deadline is reached.
- **Total deadline.** `--deadline` (900 s in the workflow) is enforced by `concurrent.futures.wait(timeout)`,
  `shutdown(cancel_futures=True)`, and the capped per-request limit. The worst-case wall time is about
  deadline + one request limit. The CLI exits non-zero at the deadline even if worker threads are still blocked
  (tested as a subprocess).
- **Integrity unchanged.** Every file's complete body is hashed with SHA-256 and compared with `SHA256SUMS`.
  There is no sampling, HEAD-only check or ETag shortcut.
- **Result fields.** The JSON result reports checked, ok, failed (with a reason for each file), rounds, requests,
  retries, max_in_flight, workers, deadline_s, elapsed_s and deadline_exceeded. `deploy-site.yml` writes it to
  `$RUNNER_TEMP/verify_served.json`.

`deploy-site.yml` verify-live now makes one call:
`--workers 16 --request-timeout 30 --retries 3 --round-wait 30 --deadline 900 --json ...`. The job timeout is
35 minutes, which covers the 15-minute verification plus the live smoke tests. The legacy rollback now verifies
all 334 manifest files. The drill uses `max_rounds=1, retries=1, deadline=600`.

### 3.3 Regression tests (local fault-injection HTTP server)

| Test | Fault | Assertion |
|---|---|---|
| bounded concurrency | 240 files, 50 ms latency each, 12 workers | finishes in under 6 s (sequential would take at least 12 s); in-flight count between 2 and 12 |
| per-file retries | 503 and connection resets on chosen files | exactly the expected retries and requests; all verified |
| truncated / partial body | body shorter than `Content-Length` | never accepted |
| full-file hash | 2 MiB file that differs only in its last byte | detected |
| slow drip | body trickles in forever | ended by the per-request deadline |
| hanging CDN | every request stalls | run ends at the total deadline, `deadline_exceeded` |
| process exit | stalled server, CLI subprocess | exits non-zero within the deadline plus a small margin |
| partial propagation that converges | some files 404 or stale for the first N requests | only lagging files are re-requested; all pass |
| partial propagation that does not converge | stale forever | fails at the deadline, listing the files |
| CLI | exit codes, `--paths`, `--json`, manifest paths | |
| workflow | bounded flags present, no shell retry loop, legacy path verifies the whole manifest | |

Live read-only check of the new verifier against the current legacy production site (2026-10-12T00:32:12Z):
331 non-hidden legacy files OK in 5.68 s with 8 workers, 1 round and 0 retries. `.gitignore`, `.nojekyll` and
`.zenodo.json` were checked separately and were also OK, so all 334 manifest files are served unchanged
(`pr7a/evidence/live_legacy_verify_served.json`).

## 4. Independent verification

### 4.1 Mutation audit (`web/scripts/pr7a_mutation_audit.py`)

The audit copies the gate, verifier and tests to a temporary directory. It re-introduces one weakness at a time
and runs the relevant tests. A mutation counts as detected only when a test fails (not when the run crashes),
and the baseline must pass first.

| ID | Weakness re-introduced | Result |
|---|---|---|
| G2 | resolution record not validated | killed |
| G3 | undecidable check (None) counts as passing | killed |
| G4 | checklist problems ignored | killed |
| G5 | deleted mandatory blocker not re-added | killed |
| G6 | production allowed offline / without --sha | killed |
| G7 | OPS-1 passes on API error | killed |
| G8 | OPS-1 passes when build_type is missing | killed |
| G9 | OPS-2 ignores required reviewers | killed |
| G10 | OPS-2 accepts extra deployment branches / tag policies | killed |
| G16 | OPS-2 assumes a policy without a type is a branch and ignores pagination | killed |
| G11 | CI-1 trusts the workflow name | killed |
| G12 | future decision dates accepted | killed |
| G13 | example/reserved reference hosts accepted | killed |
| G14 | MD-2 passes online when the Release cannot be read | killed |
| G15 | unexpected exception in a check not contained | killed |
| V1 | only a prefix of each file hashed | killed |
| V2 | truncated bodies accepted | killed |
| V3 | no per-request wall-clock deadline (slow-drip bodies) | killed |
| V4 | blocking read defeats the body deadline | killed |
| V5 | unbounded concurrency | killed |
| V6 | sequential verification | killed |
| V7 | per-request limit not capped by the total deadline | killed |
| V8 | no per-file retries for transient failures | killed |
| V9 | every file re-fetched in every propagation round | killed |
| V10 | no propagation re-check rounds | killed |

Result: **MUTATION_AUDIT_PASS 25/25**. The gate baseline was 157 passed and the verifier baseline 10 passed. G1, a mutation of the dead `has_record`, was removed together with the dead code. V7 survived at first and led to finding F4.

### 4.2 Independent gate check (`web/scripts/pr7a_gate_independent_check.py`)

This check does not use pytest or monkeypatching inside the gate. It runs the real CLI (`release_gate.py --mode
production --online --sha ...`) as a subprocess against a local HTTP fake of the GitHub API and doi.org. A
bootstrap redirects only the host, and there is no production override in the gate. The repository files and
checklist are synthetic copies.

| Scenario | Expected exit | Actual exit | Result |
|---|---|---|---|
| positive: all mandatory blockers resolved + authorised, all checks pass | 0 | 0 | pass |
| ACC-1 authorisation missing | 3 | 3 | pass |
| OPS-1 decision missing | 3 | 3 | pass |
| MD-1 record with future date | 3 | 3 | pass |
| MD-3 record with template reference | 3 | 3 | pass |
| status 'waived' instead of resolved | 3 | 3 | pass |
| ACC-1 deleted from the checklist | 3 | 3 | pass |
| MD-2 re-scoped out of production | 3 | 3 | pass |
| MD-2 dates disagree (valid record) | 3 | 3 | pass |
| VER-1 pre-release version (valid record) | 3 | 3 | pass |
| OPS-1 Pages source still legacy | 3 | 3 | pass |
| OPS-1 Pages API 403 | 3 | 3 | pass |
| OPS-1 Pages API 404 (as seen unauthenticated today) | 3 | 3 | pass |
| OPS-2 no required reviewers | 3 | 3 | pass |
| OPS-2 PR branches allowed | 3 | 3 | pass |
| OPS-2 environment API 500 | 3 | 3 | pass |
| CI-1 web-data failed | 3 | 3 | pass |
| RA-1 Release asset missing | 3 | 3 | pass |
| RA-2/MD-3 DOI does not resolve | 3 | 3 | pass |
| production without --online | 2 | 2 | pass |
| production without --sha | 2 | 2 | pass |
| report mode with every blocker open | 0 | 0 | pass |
| GitHub API unreachable (connection refused) | 3 | 3 | pass |

Result: **GATE_INDEPENDENT_CHECK_PASS 23/23**. The positive path is authorised (exit 0), and every negative path blocks (exit 3, or exit 2 for usage errors).

### 4.3 Real state (read-only, unchanged)

`release_gate.py --mode report --online --sha 82c3aff...` (2026-10-12T00:32:02Z, unauthenticated) reports all 12
blockers unresolved:

| Blocker | Online result |
|---|---|
| OPS-1 | `None`: "GitHub Pages API failed: HTTP Error 404", because the API refuses to answer without a token, so the check fails closed |
| OPS-2 | `False`: branch policy only, 0 reviewers, branches `None`/`main`/`website/pr-1-exporter`/`website/pr-3-protein-entry`, admin bypass on |
| CI-1 | `False`: 0 runs |
| RA-1 | `False`: 7 assets missing |
| MD-2 | `False`: CITATION.cff 2026-10-09 vs 2026-10-10 |

The clean-clone run also executed production mode online against the PR-7a commit, which gave exit 3 (section 6).
This is the expected result for the current state; it is not a test requirement.

## 5. Findings during PR-7a

| # | Finding | Severity | Resolution |
|---|---|---|---|
| F1 | A JSON response that was a list or string crashed a check with `AttributeError` before PR-7a. The run still failed closed, but only because of the crash. | low | `gh_get` rejects any response that is not an object; all checks are wrapped. |
| F2 | MD-1 regexes were case-sensitive, so a correctly harmonised sentence-case LICENSE would never pass (false block). | low | `re.I`; synthetic test. The real-repository result is unchanged (code licence CC-BY-4.0 in LICENSE vs MIT). |
| F3 | `has_record` was dead code; an earlier mutation (G1) of it survived. | info | Removed together with the mutation. |
| F4 | Verifier worker threads blocked in a read could outlive the total deadline (mutation V7 survived at first). | medium | Per-request limit capped by the remaining time, `cancel_futures`, and a subprocess exit test. |
| F5 | OPS-2 assumed that a branch policy without a `type` field was a branch, and did not detect a paginated, incomplete policy list. | low | Strict `type == "branch"`, `total_count` must equal the number of policies; 2 tests; mutation G16. |
| F6 | The legacy rollback verified 5 of 334 files. | low | All 334 files. |

## 6. Validation results

Committed implementation `26405be`, checked from a clean tree (`tracked_changes=0`). Logs are in
`pr7a/logs/` (`WT_SUMMARY.txt` and `ART_SUMMARY.txt`); evidence is in `pr7a/evidence/`.

### 6.1 Local checks (all exit 0)

| Area | Step | Result |
|---|---|---|
| Frozen science | `frozen_baseline`, `refpkg_sums`, `frozen_diff` vs 7546a7a (`releases refpkg pipeline site`) | unchanged |
| | DB SHA-256 | `379a2543...dce17f`, 33,464,320 B |
| | `blocker_status_unchanged` | 12 blockers, all `open`, `resolution null`; no `status` line changed since 82c3aff |
| Scientific integrity | schema, structure fixtures, drill-down golden | `--check` pass |
| | reconciliation | 58 items, `all_ok=True` |
| | scientific audit | 47/47 |
| | audit mutations | 13/13 detected |
| Workflows | actionlint (`web-data`, `deploy-site`, `site-preview`) | OK (run twice) |
| | permissions audit | write scopes only in `deploy` |
| Python | `pytest` (whole `tests/`) | **344 passed** (PR-7: 183; -35 +196 in `test_web_pr7.py`) |
| | `pytest tests/test_web_pr7.py` against the fresh clean-clone artifact, `MRDB_REQUIRE_ARTIFACT=1` | **196 passed** |
| Gate | mutation audit | 25/25 |
| | independent CLI check | 23/23 |
| Web (unchanged code) | `tsc --noEmit` | 0 errors |
| | Vitest | 227 passed |
| | `npm run build` | OK |
| | Playwright E2E | 250 passed + 1 skipped |
| Clean-clone artifact | 2 clones at different paths, 2 production builds | trees clean after build |
| | `diff -r` | identical |
| | tarball comparison | `cmp` identical |
| | `site_rollback compare` | identical |
| Artifact | contents | 5,374 files (5,373 in `SHA256SUMS`), 34,727,432 B |
| | tarball SHA-256 | `db9c2d80adb5c594df8d9847e856d513f13eed0bc2864cf08a295af15ff6565d` (differs from PR-7 only through the `BUILD_INFO` commit) |
| | `SHA256SUMS` hash | `e9ba7d80...abdaeb` |
| | offline verification of the extracted tarball | V1-V11 pass, commit `26405be` |
| Smoke | artifact | 41/41 |
| | wrong-commit negative | fails as required |
| | legacy | 1/1 |
| Rollback | legacy build | reproduces fab9182 (334 files) |
| | drill | **ROLLBACK_DRILL_PASS**: deploy-new 5,374/5,374, rollback-legacy 334/334, roll-forward 5,374/5,374 served files verified with the new verifier |
| | `compare` new vs legacy | flagged, not classified |
| Gate on this commit | report | exit 0 |
| | production without `--online` | **exit 2** |
| | production `--online --sha 26405be...` | **exit 3**, 12 unresolved (current state; OPS-1 `None` = API 404 unauthenticated, OPS-2 `False`, CI-1 `False` with 0 runs) |

### 6.2 Remote CI

Not run. Nothing was pushed. Remote CI exists only for PR-1 `4b8391c`, PR-2 `b5416b1` and PR-3 `7546a7a`. Every
claim in this report about GitHub behaviour (the token permission path, Pages/environment API answers with a
token, runner timings) is unverified until CI-1.

## 7. Residual risks (documented, not fixed in PR-7a)

1. The gate runs from the commit being deployed. A commit that weakens `release_gate.py` would weaken its own
   gate. Mitigations:
   - code review;
   - CI-1 (the `web-data` tests, including this suite, must succeed on that commit);
   - the OPS-2 environment reviewer, who approves the deploy job after the build summary.
2. The resolution record in the JSON file is an audit trail, not cryptographic authorisation. Anyone who can
   merge to `main` can write it. Authorisation in practice comes from branch protection and the environment
   reviewer.
3. `can_admins_bypass` and `prevent_self_review` are reported, not enforced (maintainer decision). With admin
   bypass on, an administrator can skip the reviewer.
4. Unauthenticated reads of the Pages and environment APIs return 404. The OPS-1/OPS-2 permission path through
   the workflow token (`pages: read`, `actions: read`) has not yet run on GitHub. If GitHub refuses it, the gate
   blocks (fail-closed), and the fix would be a token with the right scope, not a weaker check.
5. A file whose bytes are permanently wrong is indistinguishable from slow propagation until the 15-minute
   deadline, so failure is reported after 15 minutes rather than immediately. This is intended.
6. None of the workflows changed in PR-7/PR-7a has run on GitHub (CI-1).

## 8. Files changed (82c3aff..implementation commit)

| File | Change |
|---|---|
| `web/scripts/release_gate.py` | fail-closed rules, OPS-1 check, stricter OPS-2/CI-1/MD-2/MD-3/RA-1, MD-1 case fix, mandatory set, record and checklist validation, CLI exit 2 |
| `web/scripts/site_rollback.py` | `fetch_bounded`, concurrent bounded `verify_served`, new CLI options |
| `.github/workflows/deploy-site.yml` | preflight `pages: read`; one bounded verify-served call; legacy rollback verifies all files; verify-live timeout 35 min |
| `tests/test_web_pr7.py` | 4 state-dependent tests removed; gate and verifier suites added (196 tests in the file) |
| `web/scripts/pr7a_mutation_audit.py`, `web/scripts/pr7a_gate_independent_check.py` | new |
| `docs/website/release_blockers.json` | description and OPS-1/OPS-2 `required_decision` text only; no status or resolution changed |
| `PR7_RELEASE_BLOCKERS.md`, `PR7_DEPLOYMENT_RUNBOOK.md`, `PR7_ROLLBACK_RUNBOOK.md`, `PR7_DEPLOYMENT_PLAN.md`, `WEB_BUILD_AND_DEPLOY.md`, `WEB_KNOWN_LIMITATIONS.md` | updated to the new behaviour |

Documentation commit: this report, `WEB_TEST_INVENTORY.md` (PR-7a row), and `docs/website/pr7a/` (logs and
evidence).

## 9. Next steps (maintainer; not performed)

1. Final review of PR-7a.
2. Push the branch and open a PR; obtain a successful `web-data` run (CI-1). This is the first remote run of the
   PR-3a to PR-7a code.
3. Resolve MD-1 to MD-5, RA-1, RA-2, VER-1, then OPS-2, then OPS-1 immediately before dispatch, and ACC-1, each
   with a valid record. Then dispatch `deploy-site` as described in `PR7_DEPLOYMENT_RUNBOOK.md`.
