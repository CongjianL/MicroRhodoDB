# PR-7 deployment plan

Status: **PR7_IMPLEMENTED_PENDING_RELEASE_APPROVAL**. Nothing has been pushed, merged, released or deployed;
no GitHub setting has been changed. Spec reference: `WEBSITE_REDESIGN_SPEC.md` PR-7, sections 14 and 15.

## Current production (unchanged)

- GitHub Pages, legacy "pages build and deployment" from branch `main`, repository root.
- `main` = `fab9182044c45670c869c8778fd8d48932bd35b8` (`git ls-remote`, `pr7/evidence/`).
- Live `index.html`, `site/index.html`, `site/app.js`, `site/data.js`, `site/style.css`, `README.md`,
  `CITATION.cff` are byte-identical to that commit (`pr7/evidence/live_legacy_vs_manifest.json`, 7/7).

## Target

- Same URL `https://congjianl.github.io/MicroRhodoDB/site/`, served from a GitHub Actions Pages artifact built
  by `web/scripts/build_site_artifact.py --production` (layout in `WEB_BUILD_AND_DEPLOY.md` section 1).
- Root `https://congjianl.github.io/MicroRhodoDB/` keeps redirecting to `site/` (same `index.html`).
- Existing `#/record/...` permalinks keep working (hash routing; smoke-tested).

## Components delivered

| Requirement | Implementation |
|---|---|
| A. deterministic build + provenance | `build_site_artifact.py`, `verify_site_artifact.py` (V1-V11), `web/release/release_contract.json`, `BUILD_INFO.json`, Vite `__MRDB_BUILD__` stamp shown in the footer and About page |
| B. secure manual Pages deploy | `.github/workflows/deploy-site.yml` |
| C. non-production preview + smoke | `.github/workflows/site-preview.yml`, `web/scripts/serve_artifact.py`, `web/playwright.smoke.config.ts`, `web/tests/smoke/` |
| D. executable rollback | `web/scripts/site_rollback.py`, `web/release/rollback/legacy_fab9182044c4.sha256` (334 files), `PR7_ROLLBACK_RUNBOOK.md` |
| E. release-blocker checklist | `docs/website/release_blockers.json`, `web/scripts/release_gate.py`, `PR7_RELEASE_BLOCKERS.md` |
| F. docs | this file, `PR7_DEPLOYMENT_RUNBOOK.md`, `PR7_ROLLBACK_RUNBOOK.md`, `PR7_RELEASE_BLOCKERS.md`, `PR7_VALIDATION_REPORT.md`, `WEB_BUILD_AND_DEPLOY.md`, README section |
| Regression tests | `tests/test_web_pr7.py`, `web/tests/unit/pr7.test.ts`, smoke suites; `web-data.yml` now builds and verifies the artifact |

## Security model of `deploy-site.yml`

- `workflow_dispatch` only; must run from `refs/heads/main`; `source_sha` must be 40-hex and an ancestor of
  `origin/main`; the dispatcher types `deploy <kind> <source_sha>`; a reason is mandatory and recorded in the
  job summary together with actor, run id/attempt and UTC time.
- Top-level `permissions: {}`. preflight: `contents: read, actions: read, pages: read` (PR-7a, for the OPS-1 check); build and verify-live:
  `contents: read`; only `deploy` has `pages: write` and `id-token: write`.
- `deploy` uses the `github-pages` environment, so a required reviewer (OPS-2) must approve in the GitHub UI.
  GitHub does not let the dispatcher self-approve when "Prevent self-review" is enabled; the runbook requires it.
- `concurrency: pages-production`, `cancel-in-progress: false` (an in-flight deployment is never cancelled).
- For `kind=website` the production gate runs online and exits 3 while any blocker is open: there is no
  input, flag or variable that skips it. All scientific, unit and smoke gates run again on the exact commit.
- Actions pinned to commit SHAs; no secrets other than the automatic token passed to the read-only gate;
  `persist-credentials: false` everywhere.
- `kind=legacy-rollback` restores the previously published site, so it is not gated by publication blockers
  (they concern website 2.0); it still requires the confirmation string and environment approval.

## Order of operations for the first production deployment

1. Maintainer resolves MD-1..MD-5, RA-1, RA-2, VER-1 in the repository (separate reviewed commits) and records
   each resolution in `release_blockers.json`.
2. Push the PR-3a..PR-7 branches; `web-data` and `site-preview` must succeed on GitHub (CI-1).
3. Review the preview artifact (ACC-1); merge to `main`.
4. OPS-2 then OPS-1 settings changes by the maintainer, immediately before dispatch.
5. Dispatch `deploy-site` (`PR7_DEPLOYMENT_RUNBOOK.md`); approve the environment; check verify-live.
6. If anything fails: `PR7_ROLLBACK_RUNBOOK.md`.

## Known risks

- Switching the Pages source to Actions stops Pages from serving repository paths outside the artifact
  (e.g. `/MicroRhodoDB/releases/...`, `/MicroRhodoDB/docs/...`). No such links are known to be used by the
  website, but external links to them would 404. R1 rollback restores them.
- The online gate reads environment protection and Actions runs with the workflow token. If GitHub refuses
  those reads, the gate fails closed (blocks); it never passes on missing information.
- `site-preview` on pull requests builds GitHub's merge commit, so its repository-document links point at that
  merge commit; production builds use the `main` commit.
- Determinism is guaranteed for the same lockfile, Node and Python versions; a different runner image may
  change minified bytes (content is still verified by V1-V11 and smoke tests).
