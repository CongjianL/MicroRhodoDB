# Development: website 2.0, deployment and release gate

Maintainer-facing material moved out of the top-level `README.md`. Users of the data need none of this.

## Website 2.0 (`web/`)

The website (React + TypeScript + Vite, "website 2.0") lives in `web/` and serves **dataset v1.6.1**. It is built
from static JSON exported from the official v1.6.1 SQLite database. The legacy static browser in `site/` (dataset
v1.6.0) is kept as the rollback target.

Requirements: Node >= 22 and the `mrdb` conda environment (Python with the release DB present;
`python web/scripts/fetch_release_db.py` downloads it from the GitHub Release and verifies it against
`BINARIES.md`).

```bash
# 1. Export the static website data from the official database (refuses to run on checksum mismatch)
python tools/export_web_data.py --repo . --out web/public/data

# 2. Install pinned dependencies
cd web && npm ci

# Development server (http://localhost:5173/MicroRhodoDB/site/)
npm run dev

# Production build (type-check + Vite) and local preview of the built site
npm run build
npm run preview                  # serves web/dist at http://localhost:4173/MicroRhodoDB/site/

# Validation
npx tsc --noEmit -p .            # type-check
npx vitest run                   # unit / integration tests
npx playwright install chromium  # once
npx playwright test              # end-to-end, accessibility (axe) and failure-injection tests
cd .. && python -m pytest -q     # release + website data-contract tests (repository root)
python web/scripts/schema_to_ts.py --check
python web/scripts/pr5_reconciliation.py --out /tmp/recon      # SQL replay of every displayed statistic
python web/scripts/pr6_scientific_audit.py --out /tmp/sci      # independent tree/clade/placement audit
```

## Deployment artifact, preview and deployment (PR-7)

Full procedure: `docs/website/WEB_BUILD_AND_DEPLOY.md`.

```bash
# Build the exact GitHub Pages artifact (provenance, SHA256SUMS, deterministic tarball) and verify it offline
python web/scripts/build_site_artifact.py --out /tmp/mrdb-site --tarball /tmp/mrdb-site.tar.gz   # add --production on a clean checkout
python web/scripts/verify_site_artifact.py /tmp/mrdb-site --repo .

# Preview it exactly as Pages would serve it: http://127.0.0.1:4173/MicroRhodoDB/site/
python web/scripts/serve_artifact.py /tmp/mrdb-site 4173

# Browser smoke tests against the artifact (routes, deep links, structures, MR_CLD3_017, a11y, outages)
cd web && SMOKE_ARTIFACT=/tmp/mrdb-site npx playwright test -c playwright.smoke.config.ts && cd ..

# Release-blocker checklist (report mode never blocks; production mode exits 3 while blockers are open)
python web/scripts/release_gate.py --mode report

# Rollback artifact of the pre-redesign site, verified against the committed manifest
python web/scripts/site_rollback.py legacy-build --ref fab9182044c45670c869c8778fd8d48932bd35b8 --out /tmp/mrdb-legacy
```

Production deployment is **manual only**: the `deploy-site` workflow (Actions > deploy-site > Run workflow, from
`main`, with `kind`, the full `source_sha`, the confirmation string `deploy <kind> <source_sha>` and a reason).
It refuses to deploy website 2.0 while any release blocker in `docs/website/release_blockers.json` is open,
and the `github-pages` environment must require reviewer approval. The deployed artifact is served only while the
repository's Pages source is set to "GitHub Actions"; with "Deploy from a branch" Pages serves `main` as is,
i.e. the legacy `site/` browser. See `docs/website/PR7_DEPLOYMENT_RUNBOOK.md` and
`docs/website/PR7_ROLLBACK_RUNBOOK.md`.

## Process records

`docs/website/pr*/` and the `docs/website/PR*_*.md` reports are the validation and acceptance records of the
website pull requests (logs, screenshots, audits). They document how the website was checked; they are not
needed to use or rebuild the data.
