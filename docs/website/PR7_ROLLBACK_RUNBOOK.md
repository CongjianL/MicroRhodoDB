# PR-7 rollback runbook

## Recorded previous production

| Item | Value |
|---|---|
| Serving mode | GitHub Pages "Deploy from a branch", `main`, `/ (root)` (legacy pages build and deployment) |
| Production commit | `fab9182044c45670c869c8778fd8d48932bd35b8` (`main`, `pr7/evidence/`) |
| Recoverable artifact | `git archive fab9182044c45670c869c8778fd8d48932bd35b8` (full history in git and in the delivered bundles) |
| Manifest | `web/release/rollback/legacy_fab9182044c4.sha256` (334 files, SHA-256 of every file of that tree) |
| Live check before PR-7 | `index.html`, `site/{index.html,app.js,data.js,style.css}`, `README.md`, `CITATION.cff` live == manifest (7/7) |

The legacy files themselves (`site/`, root `index.html`) are frozen and are not modified by the redesign.

## Choose a path

| Path | When | Needs a build | Time |
|---|---|---|---|
| R1 | website 2.0 broken or untrusted, fastest full restore of the old site and of every repository path | no | minutes |
| R2 | Pages source must stay on Actions; restore the old site | yes (git archive) | ~5 min |
| R3 | restore an earlier accepted website 2.0 deployment | yes (rebuild) | ~30 min |

### R1: switch Pages back to the branch (maintainer, no workflow)

Settings > Pages > Source = "Deploy from a branch", Branch `main`, folder `/ (root)`. Save.
GitHub rebuilds from `main`; because `main` keeps the legacy `site/` and root `index.html`, the old site is
restored exactly (and every other repository path is served again). Then verify:

```bash
python web/scripts/site_rollback.py verify-served --base https://congjianl.github.io/MicroRhodoDB/ \
  --sums web/release/rollback/legacy_fab9182044c4.sha256 --deadline 900   # all 334 manifest files
cd web && SMOKE_BASE_URL=https://congjianl.github.io/MicroRhodoDB/ SMOKE_LEGACY=1 npx playwright test -c playwright.smoke.config.ts
```

If `main` has changed `site/` or `index.html` after `fab9182`, R1 serves that newer content; use R2 instead.

### R2: deploy the legacy artifact through Actions

Actions > deploy-site > Run workflow on `main`: `kind=legacy-rollback`,
`source_sha=fab9182044c45670c869c8778fd8d48932bd35b8`,
`confirm=deploy legacy-rollback fab9182044c45670c869c8778fd8d48932bd35b8`, `reason=<incident link>`.
The build job runs `site_rollback.py legacy-build`, which archives that commit and refuses to continue unless
every file matches the committed manifest; hidden files (`.nojekyll`) are kept. verify-live compares all 334 live
legacy files with the manifest (PR-7a; previously 5 paths), using the same bounded verifier as website deployments. Local rehearsal:

```bash
python web/scripts/site_rollback.py legacy-build --ref fab9182044c45670c869c8778fd8d48932bd35b8 --out /tmp/mrdb-legacy
cd web && SMOKE_ARTIFACT=/tmp/mrdb-legacy SMOKE_LEGACY=1 npx playwright test -c playwright.smoke.config.ts
```

### R3: redeploy an earlier website 2.0 commit

Take `source_commit` from the release record `mrdb-site-release-<sha>` of the last good run (or from a saved
`BUILD_INFO.json`). Dispatch `kind=website` with that SHA. The gate and all tests run again; the rebuilt
artifact must have the same `content_sha256` as the recorded `BUILD_INFO.json` (same toolchain), which can be
checked locally:

```bash
python web/scripts/site_rollback.py compare /tmp/recorded-site /tmp/rebuilt-site     # 0 = identical or provenance-only
```

## Incident procedures

| Incident | Detection | Response |
|---|---|---|
| Failed deployment (deploy job error) | run status | previous deployment stays live; re-run once, else R1/R2 |
| Missing assets (404 on `site/assets/*`) | verify-live `SERVED_SITE_DIFFERS`, smoke failure | R2 (or R1); then rebuild locally and run `verify_site_artifact.py`; V4 identifies the missing reference |
| Scientific-data difference | `compare` exit 4 (`UNEXPECTED_SCIENTIFIC_DATA_CHANGE`), V5/V7 failure, user report | roll back immediately (R2/R3); diff with `site_rollback.py compare <good> <bad> --json diff.json`; the frozen DB/tree are verified by V7/V11 |
| GitHub Pages outage | githubstatus.com, all URLs failing including the legacy paths | no rollback (it would not help); wait, then re-run verify-live |
| Wrong commit deployed | footer / `BUILD_INFO.json` `source_commit` | R3 with the intended SHA |

## Drill (executed locally in PR-7)

```bash
python web/scripts/site_rollback.py drill --new /tmp/mrdb-site --legacy /tmp/mrdb-legacy \
  --legacy-ref fab9182044c45670c869c8778fd8d48932bd35b8 --port 4354 --work /tmp/mrdb-drill --json drill.json
```

Serves deploy -> rollback -> roll-forward from a single Pages-like root and checks every file byte-for-byte
after each switch, plus root redirect, `site/` 200, unknown path 404 and the BUILD_INFO commit. Result in
`pr7/logs/art_rollback_drill.log` (`ROLLBACK_DRILL_PASS`).
