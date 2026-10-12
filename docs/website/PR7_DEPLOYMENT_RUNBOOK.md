# PR-7 deployment runbook (website 2.0 to GitHub Pages)

Do not start until `python web/scripts/release_gate.py --mode production --online --sha <sha>` exits 0 on the
commit to deploy. While it exits 3, stop: blockers are resolved only by the maintainer
(`PR7_RELEASE_BLOCKERS.md`).

## 0. Record the current production state (for rollback)

```bash
git ls-remote https://github.com/CongjianL/MicroRhodoDB refs/heads/main          # expected fab9182044c45670c869c8778fd8d48932bd35b8 before the first deployment
curl -s https://api.github.com/repos/CongjianL/MicroRhodoDB/pages | python -m json.tool   # build_type: legacy (branch) or workflow
python web/scripts/site_rollback.py verify-served --base https://congjianl.github.io/MicroRhodoDB/ \
  --sums web/release/rollback/legacy_fab9182044c4.sha256 \
  --paths index.html site/index.html site/app.js site/data.js site/style.css --json /tmp/pre_deploy_live.json
```

Keep the output with the deployment record. If production has already moved to website 2.0, record the
`source_commit` of `https://congjianl.github.io/MicroRhodoDB/site/BUILD_INFO.json` instead: that SHA is the
R3 rollback target.

## 1. Local pre-flight on the exact commit (clean clone)

```bash
SHA=<40-hex main commit>
git clone https://github.com/CongjianL/MicroRhodoDB /tmp/mrdb-deploy && cd /tmp/mrdb-deploy && git checkout "$SHA"
python web/scripts/fetch_release_db.py
(cd web && npm ci)
python web/scripts/build_site_artifact.py --production --out /tmp/mrdb-site --tarball /tmp/mrdb-site.tar.gz --json /tmp/mrdb-build.json
python web/scripts/verify_site_artifact.py /tmp/mrdb-site --repo . --expect-commit "$SHA" --require-clean
(cd web && npx playwright install chromium && SMOKE_ARTIFACT=/tmp/mrdb-site SMOKE_EXPECT_COMMIT="$SHA" npx playwright test -c playwright.smoke.config.ts)
python web/scripts/release_gate.py --mode production --online --sha "$SHA"     # must exit 0
cat /tmp/mrdb-site.tar.gz.sha256
```

Optionally compare with the `site-preview` artifact of the same commit:
`python web/scripts/site_rollback.py compare /tmp/mrdb-site <extracted preview>` (exit 0 required).

## 2. Repository settings (maintainer, immediately before dispatch)

1. Settings > Environments > `github-pages`: Deployment branches = Selected branches, only `main` (remove
   `None`, `website/pr-1-exporter`, `website/pr-3-protein-entry`); Required reviewers = at least one maintainer;
   enable "Prevent self-review"; disable "Allow administrators to bypass" if available.
2. Settings > Pages > Build and deployment > Source = **GitHub Actions**. From this moment the legacy branch
   deployment no longer updates; the currently served site stays until the next deployment.

## 3. Dispatch

Actions > deploy-site > Run workflow, branch `main`:

| Input | Value |
|---|---|
| kind | `website` |
| source_sha | `<SHA>` (full 40 characters) |
| confirm | `deploy website <SHA>` |
| reason | link to the approval (ACC-1 reference) |

CLI equivalent (maintainer token): `gh workflow run deploy-site.yml --ref main -f kind=website -f source_sha=$SHA -f confirm="deploy website $SHA" -f reason="<url>"`.

## 4. Watch the run

1. preflight: confirmation, ref, ancestry, production gate (online). Any failure stops everything.
2. build: database fetch, `npm ci`, production artifact, scientific gates, Vitest, smoke, re-verify, upload;
   release record `mrdb-site-release-<SHA>` (tarball, `SHA256SUMS`, `BUILD_INFO.json`, gate JSON, smoke
   report) kept for 90 days.
3. deploy: waits for the environment reviewer. The reviewer checks the build summary and approves.
4. verify-live: every live file must equal the artifact's `SHA256SUMS` (full-file SHA-256). One bounded call
   to `site_rollback.py verify-served` (PR-7a): 16 concurrent requests, 30 s per request, up to 3 retries with
   backoff for network errors and HTTP 408/425/429/5xx, files that are missing (404) or stale are re-requested
   every 30 s until they converge, total deadline 15 minutes. Then live smoke tests with
   `SMOKE_EXPECT_COMMIT=<SHA>`. The job timeout is 35 minutes.

## 5. Post-deployment checks (manual, read-only)

```bash
curl -s https://congjianl.github.io/MicroRhodoDB/site/BUILD_INFO.json | python -m json.tool     # source_commit == SHA
curl -sI https://congjianl.github.io/MicroRhodoDB/ | head -1
python web/scripts/site_rollback.py verify-served --base https://congjianl.github.io/MicroRhodoDB/ --sums /tmp/mrdb-site/SHA256SUMS
```

Open `#/record/MRDB000001`, `#/record/P02945`, `#/clade/MR_CLD3_017`, `#/statistics`, `#/downloads`, and an
unknown route; check the footer build label.

## 6. Failure handling

| Symptom | Action |
|---|---|
| preflight or build fails | nothing was published; fix and re-dispatch (new commit if code changed) |
| deploy step fails | Pages keeps the previous deployment; re-run the failed job once; otherwise R1/R2 |
| verify-live: missing assets / hash differences at the 15 min deadline | `PR7_ROLLBACK_RUNBOOK.md` R2 (or R1), then investigate |
| live smoke fails, files match | inspect the report; if user-visible breakage, roll back (R2/R3) |
| scientific-data difference | roll back immediately (R2/R3) and run `site_rollback.py compare` |
| GitHub Pages outage | do nothing to the site; check githubstatus.com; re-run verify-live later |
