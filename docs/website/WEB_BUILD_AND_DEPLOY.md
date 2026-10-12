# Website 2.0: build, preview, validation and deployment

Scope: MicroRhodoDB website 2.0 (`web/`) serving **dataset v1.6.0**, published on GitHub Pages at
`https://congjianl.github.io/MicroRhodoDB/site/`. Introduced in PR-7. Operational detail lives in
`PR7_DEPLOYMENT_RUNBOOK.md` (deploy), `PR7_ROLLBACK_RUNBOOK.md` (rollback) and `PR7_RELEASE_BLOCKERS.md`
(what must be decided before the first production deployment).

All commands run from the repository root unless stated otherwise, with the `mrdb` conda environment on PATH
and Node >= 22.

## 1. What is deployed

The Pages artifact is a directory that becomes `https://congjianl.github.io/MicroRhodoDB/`:

| Path | Content |
|---|---|
| `index.html` | the repository root redirect (`meta refresh` to `site/`), byte-identical to `index.html` at the source commit |
| `site/index.html`, `site/assets/` | Vite build, base `/MicroRhodoDB/site/`, hashed assets, CSP meta tag |
| `site/data/` | exporter output (`tools/export_web_data.py`); `site/data/v1.6.0/export_manifest.json` lists every data file with SHA-256 |
| `site/data/v1.6.0/phylogeny/MR_RT_003.rooted.treefile` | frozen reference tree, byte-identical to `refpkg/MR_RT_003/tree/MR_RT_003.rooted.treefile` |
| `site/BUILD_INFO.json` | provenance: source commit, clean flag, SOURCE_DATE_EPOCH, website version, dataset release, schema, source DB SHA-256/size, reference tree, export manifest digest, content digest, toolchain |
| `SHA256SUMS` | SHA-256 of every other file, sorted by path |

Routing is hash-based (`#/record/MRDB000001`), so deep links need no server-side fallback. Only the files above
are published: switching Pages from "branch main / root" to "GitHub Actions" stops serving the other repository
paths (legacy `site/`, `releases/`, `docs/` ...) from Pages. They remain in git and on GitHub.

Invariants are fixed in `web/release/release_contract.json` (dataset 1.6.0, schema 1.4.0, base path, DB SHA-256
`379a2543...ce17f` / 33,464,320 B, tree SHA-256 `c5619697...9aef`, legacy rollback commit, Pages size limits).

## 2. Build data dependency

The exporter reads the official release database `releases/v1.6.0/db/microrhododb_v1.6.0.sqlite`, which is
not in git. `python web/scripts/fetch_release_db.py` downloads it from the GitHub Release v1.6.0 asset and
verifies SHA-256 and size against `BINARIES.md`; any mismatch or absence stops with `BLOCKED_DATA_SOURCE`.
`build_site_artifact.py` re-checks the database and the tree against the release contract before exporting.
No field is fabricated at runtime: every displayed value comes from the exported JSON.

## 3. Development and local preview

```bash
python tools/export_web_data.py --repo . --out web/public/data
cd web && npm ci
npm run dev                         # http://localhost:5173/MicroRhodoDB/site/
npm run build && npm run preview    # http://localhost:4173/MicroRhodoDB/site/ (footer: "Development build; not the deployed site")
```

## 4. Deterministic artifact build

```bash
# development (dirty tree allowed, BUILD_INFO.source_tree_clean = false)
python web/scripts/build_site_artifact.py --out /tmp/mrdb-site --tarball /tmp/mrdb-site.tar.gz

# production (refuses a dirty working tree; same command the deploy workflow runs)
python web/scripts/build_site_artifact.py --production --out /tmp/mrdb-site --tarball /tmp/mrdb-site.tar.gz --json /tmp/mrdb-build.json
```

Steps: provenance (commit, clean flag, `SOURCE_DATE_EPOCH` = commit time) -> input check against the contract ->
fresh export -> `npm run build` with `SOURCE_DATE_EPOCH`, `TZ=UTC`, `MRDB_BUILD_COMMIT`, `MRDB_BUILD_DATE`
(the footer then shows `Build <sha7> (<commit date>)`) -> assemble -> `BUILD_INFO.json` + `SHA256SUMS` ->
optional tarball (sorted entries, fixed mtime/uid/gid, gzip mtime 0) -> offline verification.
`--out` must be outside the repository. Two production builds of the same commit with the same lockfile and
Node/Python versions are byte-identical (verified in `PR7_VALIDATION_REPORT.md`).

## 5. Offline verification

```bash
python web/scripts/verify_site_artifact.py /tmp/mrdb-site --repo . --expect-commit "$(git rev-parse HEAD)" [--require-clean] [--json report.json]
```

| Check | Meaning |
|---|---|
| V1 | layout; no hidden files, symlinks, source maps, `node_modules`; root redirect equals `index.html` at the source commit |
| V2 | `SHA256SUMS` covers exactly the artifact and every hash matches |
| V3 | `BUILD_INFO.json` agrees with the contract, the export manifest and `SHA256SUMS` (content digest) |
| V4 | every asset referenced by `site/index.html` and by JS/CSS resolves under `/MicroRhodoDB/site/` and exists |
| V5 | `site/data` equals the export manifest (paths, SHA-256, sizes); release, schema, DB hash equal the contract; export made at the build commit |
| V6 | every data JSON parses and validates against `web/src/data/schemas/web-data.schema.json` |
| V7 | reference tree byte-identical to the frozen refpkg tree |
| V8 | downloads: website-derived files exist; repository documents link to `blob/<source_commit>/...` with the shipped SHA-256 (checked with `git show`); release and refpkg checksums equal the repository |
| V9 | CSP present; no `localhost`, test endpoints, sandbox or `file://` paths in shipped text |
| V10 | GitHub Pages limits (each file < 100 MB, total < 1 GB) |
| V11 | the official SQLite database matches the contract |

Exit 0 = all pass, 1 = a check failed (`ARTIFACT_VERIFICATION_FAILED`), 2 = usage error.

## 6. Serving and smoke tests

```bash
python web/scripts/serve_artifact.py /tmp/mrdb-site 4173      # Pages-like: /MicroRhodoDB/... only, 301 for /MicroRhodoDB, 404 elsewhere
cd web
SMOKE_ARTIFACT=/tmp/mrdb-site SMOKE_EXPECT_COMMIT=<sha> npx playwright test -c playwright.smoke.config.ts
SMOKE_ARTIFACT=/tmp/mrdb-legacy SMOKE_LEGACY=1 npx playwright test -c playwright.smoke.config.ts      # rollback artifact
SMOKE_BASE_URL=https://congjianl.github.io/MicroRhodoDB/ SMOKE_LIVE=1 SMOKE_EXPECT_COMMIT=<sha> npx playwright test -c playwright.smoke.config.ts   # after a deployment (read-only)
```

`tests/smoke/site_smoke.spec.ts` (41 tests): root redirect and asset base path; BUILD_INFO and footer show the
same commit; CSP and no test endpoints; Home, Browse, Entry, Phylogeny, Clade, Structures, Statistics,
Evidence, Watchlist, Search (text and sequence), Downloads, Methods, Citation, Help and Not Found render with
one h1, no console errors and no horizontal overflow; same-origin-only network sweep; deep links
`MRDB000001`, `P02945`, `q9f7p4` -> `MRDB000011`; MR_CLD3_017 tentative caveat with corrected run1 support
SH-aLRT 50.3 / UFBoot 72 on the record, clade and home pages; PDB and AlphaFold DB structures load (answered
from committed fixtures); missing `summary.json` shows Retry and recovers; RCSB/AFDB 503 shows a viewer error
while the record stays usable; axe (serious/critical) and overflow at 375 px and 1440 px on 8 routes.

## 7. Workflows

| Workflow | Trigger | Permissions | Purpose |
|---|---|---|---|
| `web-data.yml` | pull_request / push to main (paths), manual | `contents: read` | all data, scientific, unit and E2E gates; builds and verifies a non-production artifact; runs `tests/test_web_pr7.py` with `MRDB_REQUIRE_ARTIFACT=1`; blocker report. Never deploys. |
| `site-preview.yml` | pull_request (paths), manual | `contents: read` | builds the same artifact, verifies, smoke-tests, reports blockers and uploads `mrdb-site-preview-<sha>` (tarball, build JSON, gate JSON, smoke report; 14 days). No environment, no secrets, never touches Pages. |
| `deploy-site.yml` | `workflow_dispatch` only | top level `{}`; `pages: write` + `id-token: write` only in the `deploy` job | manual production deployment or legacy rollback (section 8). |

All actions are pinned to commit SHAs and every checkout uses `persist-credentials: false`.
`tests/test_web_pr7.py` enforces these properties; `actionlint` validates all three files.

## 8. Production deployment (summary)

Only after every blocker in `release_blockers.json` is resolved by the maintainer (see `PR7_RELEASE_BLOCKERS.md`):

1. Maintainer: Pages source -> GitHub Actions (OPS-1); `github-pages` environment -> required reviewer,
   deployment branches = `main` only (OPS-2).
2. Merge the reviewed PR into `main`; wait for `web-data` (and `site-preview`) to succeed on that commit (CI-1).
3. Actions > deploy-site > Run workflow on `main`: `kind=website`, `source_sha=<40-hex main commit>`,
   `confirm=deploy website <sha>`, `reason=<approval reference>`.
4. preflight (event, ref, SHA format, confirmation, ancestry, production gate online; permissions
   `contents: read`, `actions: read`, `pages: read`) -> build (all gates, production build, smoke, re-verify)
   -> deploy (waits for reviewer approval) -> verify-live (every live file equals `SHA256SUMS`, full-file
   SHA-256, 16 concurrent requests, 3 retries per request, re-checks only lagging files every 30 s, total
   deadline 15 min; then live smoke).
5. On any post-deployment failure follow `PR7_ROLLBACK_RUNBOOK.md`.

## 9. Future dataset releases

A new scientific release must update `web/release/release_contract.json` (and the exporter constants) in the
same PR, re-export, and pass every gate; `site_rollback.py compare` between the previous and new artifact
must report the data change as intended. Within one dataset release, `compare` exits 4 on any scientific-data
difference.
