# PR-7 validation report: deployment engineering

**Status: `PR7_IMPLEMENTED_PENDING_RELEASE_APPROVAL`**

| Item | Value |
|---|---|
| Branch | `website/pr-7-deployment` (base: PR-6a `d4dacd679d557cab8fa3ee6378ffc8086959860b`) |
| Implementation commit | `1ba1fa7a54c49cc17d715dc6846bbedcd0625cd2` |
| Fix commit (validated artifact source) | `23688479325370638bfdbb1e41e9d58011c59108` |
| Docs/evidence commit | the commit that adds this file (changes only `docs/website/`; see section 6) |
| Dataset | v1.6.0, frozen; DB sha256 `379a2543...dce17f` (33,464,320 B); tree sha256 `c5619697...5ded9aef` |
| Production deploy | **not performed**. No push, merge, release, Pages or settings changes were made |

This report has two parts that are kept separate. Section 2 covers local checks, which were executed and have evidence. Section 3 covers remote CI, which has **not run**. Nothing here claims that remote CI passed.

## 1. Scope delivered (A-F)

| Part | Delivered |
|---|---|
| A. Deterministic build and provenance | `web/scripts/build_site_artifact.py` (export, then `npm run build` with `SOURCE_DATE_EPOCH`/`TZ=UTC`/`MRDB_BUILD_COMMIT`/`MRDB_BUILD_DATE`, `BUILD_INFO.json`, `SHA256SUMS`, normalised tarball). `--production` refuses a dirty tree. `web/scripts/verify_site_artifact.py` V1-V11 runs offline and without the repository |
| B. Secure Pages deploy | `.github/workflows/deploy-site.yml`: `workflow_dispatch` only, top-level `permissions: {}`, `pages: write`/`id-token: write` only in the `deploy` job, `github-pages` environment, non-cancelling `pages-production` concurrency, typed confirmation plus ref and ancestry checks, online production gate, then artifact tests, verifier and smoke before upload, and post-deploy live verification |
| C. Preview and smoke | `.github/workflows/site-preview.yml` (read-only, uploads an artifact, never deploys) and `web/tests/smoke/site_smoke.spec.ts` (41 tests: all routes, deep links, PDB and predicted structures, MR_CLD3_017 warning and run1 support, responsive layout and accessibility, missing data, CDN outage, build commit) plus `legacy_smoke.spec.ts` |
| D. Executable rollback | `web/scripts/site_rollback.py` (`legacy-manifest`, `legacy-build --ref`, `compare`, `drill`) and `web/release/rollback/legacy_fab9182044c4.sha256` (334 files) |
| E. Release blockers | `web/scripts/release_gate.py`, `docs/website/release_blockers.json` (12 open), `web/release/release_contract.json`. In report mode it exits 0, so local and preview work is not blocked; production mode exits 3. A blocker resolves only when a maintainer record exists **and** an automated check passes. No metadata was invented or changed |
| F. Docs | `PR7_DEPLOYMENT_PLAN.md`, `PR7_DEPLOYMENT_RUNBOOK.md`, `PR7_ROLLBACK_RUNBOOK.md`, `PR7_RELEASE_BLOCKERS.md`, this report, `WEB_BUILD_AND_DEPLOY.md`, README website section, `WEB_KNOWN_LIMITATIONS.md` and `WEB_TEST_INVENTORY.md` updates |

## 2. Local validation (executed)

### 2.1 Working-tree gates (`pr7/logs/wt_*.log`, `WT_SUMMARY.txt`)

All exited 0: frozen baseline, refpkg checksums, frozen diff, DB sha, schema, fixtures, golden, reconciliation, scientific audit, mutation-audit self-test, actionlint (3 workflows), pytest, tsc, Vite build, Vitest and full Playwright.

| Suite | Result |
|---|---|
| pytest (working tree) | 182 passed, 0 skipped |
| pytest at `2368847` against the clean-clone artifact (`art_pytest_full_at_head.log`) | **183 passed**, 0 skipped (adds the compare regression test) |
| Vitest | 227 passed (17 files) |
| Playwright E2E | 250 passed, 1 skipped (opt-in live test) |

The fix commit `2368847` touches only `web/scripts/site_rollback.py` and `tests/test_web_pr7.py`. The TypeScript, Vitest and Playwright results from the `1ba1fa7` working tree therefore still apply. The artifact smoke tests were rerun at `2368847`.

### 2.2 Clean-clone artifact validation at `2368847` (`pr7/logs/art_*.log`, `ART_SUMMARY.txt`)

The two builds ran in independent fresh clones at different paths (`.../pr7art/clone_a` and `.../pr7art/deeper/path/clone_b`). Each clone had its own `npm ci` and its own DB copy.

| Step | Result |
|---|---|
| clone_a, clone_b, build_a, build_b (`--production`) | exit 0 |
| Trees clean after build | exit 0 (no tracked or untracked changes) |
| Reproducibility: `diff -r` of the two artifacts | identical |
| Reproducibility: tarball | both `b6549ad4c43f6cdac0ea9b890a1963f034bbae13a2623128bf60821d4cb8314e` |
| Reproducibility: `SHA256SUMS` | both `9c88861af82c6fb52225f0f8bce4c1f8140478a15bb5bdb5bb5920bf684ac579` |
| `site_rollback.py compare A B` | `ARTIFACTS_IDENTICAL` |
| Offline verification of the extracted tarball | V1-V11 PASS, `ARTIFACT_VERIFIED` |
| Verification with no repository present | `ARTIFACT_VERIFIED`: 5,374 files, 34,727,432 B, 203 asset references, 43 asset files, 5,325 manifest data files, 5,318 JSON files |
| pytest artifact tests (`MRDB_REQUIRE_ARTIFACT=1`) | 35 passed |
| Smoke against the served artifact (`SMOKE_EXPECT_COMMIT=2368847...`) | 41 passed |
| Smoke negative control (wrong expected commit) | fails as required (1 failed, so the step passes) |
| Legacy build `fab9182` from manifest | `LEGACY_ARTIFACT_VERIFIED` |
| Legacy smoke | 1 passed |
| Rollback drill (deploy new, roll back to legacy, roll forward) | `ROLLBACK_DRILL_PASS`: 5,374 / 334 / 5,374 served files byte-identical; root redirect, `/site/` 200 and missing-path 404 checked at every stage |
| compare legacy vs new | `ARTIFACTS_DIFFER (one side has no BUILD_INFO.json ...)`, exit 0 |
| Gate, report mode | exit 0; 12 blockers listed |
| Gate, production mode | **exit 3** (blocked, as required) |
| Permissions audit | see 2.3 |
| actionlint | exit 0, no findings |

`BUILD_INFO.json` (evidence) records `source_commit` and `exporter_git_commit` = `2368847...`, `source_tree_clean: true`, `source_date_epoch` 1791753647, `dataset_release` 1.6.0, `schema_version` 1.4.0, base path `/MicroRhodoDB/site/`, and the source DB and reference tree hashes, which equal the frozen values.

Toolchain used: node v22.21.1, npm 10.9.4, Python 3.11.16. Byte-identity is only claimed for the same toolchain.

### 2.3 Permissions audit (`art_permissions_audit.log`)

| Workflow | Triggers | Top-level permissions | Write scopes |
|---|---|---|---|
| deploy-site.yml | `workflow_dispatch` | `{}` | `deploy` job only: `pages: write`, `id-token: write`, environment `github-pages`. The other jobs have `contents: read` (preflight also has `actions: read`) |
| site-preview.yml | `pull_request`, `workflow_dispatch` | `contents: read` | none; it never deploys |
| web-data.yml | `pull_request`, `push`, `workflow_dispatch` | `contents: read` | none |

Every `uses:` in all three workflows is pinned to a 40-hex commit SHA, and checkouts use `persist-credentials: false`. This is enforced by pytest.

### 2.4 Live and online evidence (read-only, queried 2026-10-11T21:00:42Z)

- The live legacy site matches the rollback manifest: 7/7 sampled files are byte-identical (`SERVED_SITE_MATCHES`), and `main` = `fab9182044c45670c869c8778fd8d48932bd35b8`.
- Online gate (`release_gate_online.txt`):
  - RA-1: the v1.6.0 GitHub Release lacks `MicroRhodoDB_v1.6.0.tar.gz` (+ `.sha256`) and the v1.0, v1.3.0, v1.4.0, v1.5.0 and v1.5.0_env_pilot SQLite files that BINARIES.md lists. `downloads.json` links only `microrhododb_v1.6.0.sqlite`, so the website itself does not link to any missing asset.
  - OPS-2: environment protection is `branch_policy` only, with no required reviewers; allowed branches include `main`, `website/pr-1-exporter` and `website/pr-3-protein-entry`.
  - CI-1: no workflow runs exist for these commits.

## 3. Remote CI (pending: no evidence, not PASS)

| Commit | Remote CI |
|---|---|
| PR-1 `4b8391c` | PASS (run 38044933968) |
| PR-2 `b5416b1` | PASS (run 38058112858) |
| PR-3 `7546a7a` | PASS (run 38104338951) |
| PR-3a … PR-6a `d4dacd6` | **not run** (not pushed) |
| PR-7 `1ba1fa7` / `2368847` / docs commit | **not run** (not pushed). `deploy-site.yml` and `site-preview.yml` have never executed on GitHub |

## 4. Deviations and fixes found during validation

| ID | Item |
|---|---|
| D-56 | Verifier V4 resolved relative asset references wrongly (`./favicon.svg`). It now uses `urljoin(base, ref)` |
| D-57 | The MD-1 README licence regex did not parse the README's `Data: ... Code: ...` sentence. Fixed, and a missing statement now yields None, which never passes |
| D-58 | `downloads.json` repository-document links now point at `blob/<build commit>/...`, falling back to the release tag, instead of a moving branch |
| D-59 | The website version label is `2.0.0-pr7` (exporter, package.json, package-lock). It is a pre-release label, so VER-1 stays open |
| D-60 | `web-data.yml`: actions pinned to SHAs (this was **not** done in PR-6a; that report was corrected). It now also builds the artifact, runs the artifact tests with `MRDB_REQUIRE_ARTIFACT=1`, and runs the gate in report mode |
| D-61 | `deploy-site.yml` hardened: the build-step pytest is forced onto the built artifact, and both smoke runs assert `SMOKE_EXPECT_COMMIT` |
| D-62 | Defect found in the first clean-clone run at `1ba1fa7`: `site_rollback.py compare` crashed (`FileNotFoundError`) on a legacy-build directory without `SHA256SUMS`, and the run script masked the exit code. Fixed in `2368847`: compare hashes such directories itself, and `same_dataset_release` = None when either side lacks `BUILD_INFO.json`. A regression test was added and the run script now propagates the exit code. The entire artifact validation was rerun from scratch at `2368847` (section 2.2). The first-run tarball (`3ad9bc0e...fcd2`, identical across both clones) is superseded |

## 5. Risks

1. **Pages source switch (OPS-1).** Switching Pages from "Deploy from a branch" to "GitHub Actions" stops serving every other path of the repository (for example raw files under `/MicroRhodoDB/`); only the uploaded artifact is served. Rollback R1, which switches the source back to the branch, restores them. See `PR7_ROLLBACK_RUNBOOK.md`.
2. **Determinism is toolchain-bound.** Byte-identity holds for node 22.21.1 / npm 10.9.4 / Python 3.11.16 with `npm ci`. The workflows pin only the major/minor lines (`node-version: "22"`, `python-version: "3.11"`), so a newer patch release or runner image can change bytes. In that case `compare` classifies the difference as no scientific-data change and the content checks still apply.
3. **Preview builds on pull requests use the merge commit,** so their `BUILD_INFO.source_commit` is not the PR head. They are previews only and never deploy.
4. **Remote workflows are unexercised.** The first real run of `deploy-site.yml`/`site-preview.yml` may surface hosted-runner differences, for example the Playwright browser install.
5. **The gate fails closed.** If the GitHub API refuses reads (rate limit, token scope), the production gate blocks. This is intended.
6. **Provenance of the validated artifact.** It is stamped `2368847`. A production deploy from a later commit, such as the docs commit or any merge commit, produces a different `source_commit` and different provenance fields, and must pass the same in-workflow gates again. `deploy-site.yml` rebuilds and re-verifies before upload, so this is enforced.

## 6. Docs commit scope

The commit that adds this report changes only files under `docs/website/` (this report, `WEB_TEST_INVENTORY.md`, `pr7/logs/`, `pr7/evidence/`). None of these paths is in the exporter's `REPO_DOCUMENTS` (CITATION.cff, LICENSE, README.md, MAINTENANCE.md, CHANGELOG.md, docs/RELEASE_HISTORY.md, tools/mrdb_search.py). Scientific data and site content are therefore unchanged relative to the validated `2368847` artifact. Only the commit-dependent provenance fields would differ.

## 7. Maintainer decisions required (open production blockers)

None of these were decided or edited by this work.

| ID | Decision |
|---|---|
| MD-1 | Code licence: LICENSE says CC-BY-4.0 for everything, while README and `web/package.json` say MIT for code |
| MD-2 | v1.6.0 release date: CITATION.cff 2026-10-09 vs `.zenodo.json`/CHANGELOG/release notes 2026-10-10 |
| MD-3 | DOI, or an approved alternative citation policy |
| MD-4 | Public support/contact channel (placeholder in MAINTENANCE.md) |
| MD-5 | Maintenance cadence, hosting term, funding and succession (7 placeholder lines in MAINTENANCE.md) |
| RA-1 | Upload the assets listed in BINARIES.md to the v1.6.0 Release, or correct BINARIES.md |
| RA-2 | Verify the claimed Zenodo deposit, or remove the claim |
| VER-1 | Choose the final website version (replace `2.0.0-pr7`) |
| ACC-1 | Final review and explicit production authorisation |

## 8. Manual pre-deploy steps (maintainer, in order)

1. Resolve MD-1 to MD-5, RA-1, RA-2 and VER-1, and record each resolution in `docs/website/release_blockers.json`.
2. Push the branches (PR-3a … PR-7) and open PRs. Remote CI must pass on the exact commit to be deployed (CI-1).
3. OPS-2: on the `github-pages` environment, add required reviewers, enable "prevent self-review", and restrict deployment branches to `main` only (remove `website/pr-1-exporter`, `website/pr-3-protein-entry`).
4. Merge to `main`. Then OPS-1: set Pages source to "GitHub Actions" (see risk 1), and record OPS-1 and ACC-1.
5. Run `deploy-site.yml` by hand from `main` with the typed confirmation. Then follow `PR7_DEPLOYMENT_RUNBOOK.md`, with `PR7_ROLLBACK_RUNBOOK.md` ready.

Until then, `release_gate.py --mode production` exits 3 and `deploy-site.yml` stops at the gate before any upload.
