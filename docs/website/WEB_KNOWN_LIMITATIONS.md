# Web Known Limitations

The authoritative list is section 7 of `PR6_WEB_ACCEPTANCE_REPORT.md`. It covers maintainer decisions MD-1 to MD-5 (licence, release date, DOI, contact and maintenance placeholders), which block PR-7. It also lists open items P2-1 to P2-3 (mobile CLS after a sequence search, mobile Slow-4G LCP and mobile Browse INP) and P3-1 to P3-8. Earlier limitations L-1 to L-5 are in `PR5A_AUTO_ACCEPTANCE_REPORT.md`.

## PR-7 (deployment)

- Production deployment is blocked by 12 open release blockers (`PR7_RELEASE_BLOCKERS.md`): MD-1 to MD-5, RA-1, RA-2, OPS-1, OPS-2, CI-1, VER-1 and ACC-1. They block production only, not development or previews.
- None of the deployment workflows has run on GitHub yet: `deploy-site.yml` and `site-preview.yml` are new, and `web-data.yml` gained PR-7 steps. Their remote behaviour is pending CI-1, so only local actionlint and static audits exist.
- Switching Pages to GitHub Actions stops serving repository paths outside the artifact (for example `/MicroRhodoDB/releases/`). Rollback R1 restores them.
- Byte-for-byte reproducibility is verified for the same lockfile, Node and Python versions. A different runner image may change minified bytes. V1 to V11 and the smoke tests still verify content.
- Live smoke tests answer the RCSB and AFDB structure requests from fixtures. Real external availability is covered only by the opt-in `@live` E2E tests.
- The online release gate reads GitHub API data with the workflow token. If a read is refused, the gate fails closed.
