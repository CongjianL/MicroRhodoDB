# PR-6 (E): Publication-readiness audit

Scope: `README.md`, `MAINTENANCE.md`, `CITATION.cff`, `LICENSE`, `web/package.json`, and the website's
Downloads, Methods, Help, Citation, About and footer pages, plus the release metadata in the official v1.6.0
database as exported to `manifest.json` and `downloads.json`.

Rule applied: the agent does **not** settle conflicting legal or scientific metadata. It does not invent a
DOI, contact address, hosting term, funding statement or successor. Each conflict is recorded below. If it
needs a maintainer decision, it is listed as a PR-7 release blocker (MD-n).

## 1. What the website displays (all values read from the export; no hard-coded legal text)

| Item | Website value | Source |
|---|---|---|
| Dataset release | v1.6.0, schema `v160.1` | `manifest.json` (release DB metadata) |
| Release date | 2026-10-10 (Home, About, footer, Downloads) | release DB metadata |
| Citation date | 2026-10-09 ("date-released") on Citation and Downloads | `CITATION.cff` |
| Licence | "CC BY 4.0 (data); MIT (code)" (Home, About, footer, Downloads) | release DB metadata |
| Citation licence | CC-BY-4.0 | `CITATION.cff` |
| DOI | "not supplied" (Citation page) | `CITATION.cff` has no `doi` |
| Contact | none shown | no decided value exists |

The Downloads page already states the date discrepancy ("release-database metadata; CITATION.cff gives
date-released 2026-10-09"). It also names the licences of both the LICENSE file and CITATION.cff, so the
conflict is disclosed to users and not hidden. Displaying a value is not the same as resolving it.

## 2. Discrepancies

| ID | Discrepancy | Evidence | Decision owner | Blocks PR-7 |
|---|---|---|---|---|
| MD-1 | **Code licence conflict.** README and the release DB say "Code: MIT"; `LICENSE` says code under `src/`, `pipeline/`, `workflow/`, `tools/` is CC BY 4.0 "unless a file states otherwise"; `web/package.json` says `MIT`; `CITATION.cff` says `CC-BY-4.0` (single licence). | README "Licence and citation"; LICENSE lines 6-8; `web/package.json` `license`; CITATION.cff `license` | Maintainer (legal) | **Yes**: the public site must not show a licence that contradicts the LICENSE file |
| MD-2 | **Release date conflict.** README and DB give 2026-10-10; `CITATION.cff` gives 2026-10-09. | README heading; `manifest.json` `release_date`; CITATION.cff `date-released` | Maintainer | **Yes** (citation metadata must be consistent at publication) |
| MD-3 | **No DOI.** README says "Zenodo DOI to be added on deposit"; MAINTENANCE has `<<PLACEHOLDER: Zenodo DOI>>`; the Citation page shows "not supplied". | README; MAINTENANCE line 28 | Maintainer (requires a deposit) | **Yes** if publication requires a citable DOI. Otherwise this is a documented limitation that the maintainer accepts. |
| MD-4 | **No contact address.** MAINTENANCE: `<<PLACEHOLDER: institutional e-mail>>`. The site shows no contact route except the GitHub repository. | MAINTENANCE line 9 | Maintainer | **Yes**: spec section 14.8 requires Contact information, and it must not be invented |
| MD-5 | **Maintenance placeholders**: update cadence, hosting term, funding, successor/custodian. | MAINTENANCE lines 14, 27, 35, 43 | Maintainer | **Yes**: spec section 14.8 (Maintenance information) |
| P-6 | `CITATION.cff` abstract: "~472 tips" (exact value is 472) and "19 named subfamilies". The database has 17 named level-1 clades plus 2 backbone/unassigned groups (19 level-1 groups) and 30 subclades. | CITATION.cff abstract; `clades.json` | Maintainer (scientific wording) | No (P3). Recommended correction at the next CITATION edit. |
| P-7 | `CITATION.cff` abstract describes "a static browser". It does not mention website 2.0, which is right while website 2.0 is not deployed. | CITATION.cff | Maintainer | No (P3). Revisit at PR-7. |
| P-8 | README test count: "52 tests" refers to `python -m pytest -q tests/` for the release suite. The repository-root run now also collects the website tests (139 at PR-6). | README "Reproducing the release" | n/a | No (P3, informational). The command in the README is scoped to `tests/` and was not changed. |
| P-9 | Spec section 15 lists `WEB_BUILD_AND_DEPLOY.md` and `.github/workflows/deploy-site.yml`. Neither exists, because deployment is PR-7 scope. | `docs/website/`, `.github/workflows/` | PR-7 | Yes. These are **PR-7 deliverables**, not PR-6 defects. |

## 3. Changes made in PR-6 (non-legal, factual only)

- `README.md`: added a "Website 2.0 (redesign in `web/`, not yet deployed)" section with executable
  export, install, dev, build, preview and validation commands (spec section 15). It states that deployment
  is not configured and belongs to PR-7. No licence, date, DOI or contact text was changed.
- `web/package.json`: added a `preview` script (`vite preview --port 4173 --strictPort`), updated the stale
  description ("PR-2: design system, Home, Browse"), and changed the package version from `2.0.0-pr5` to
  `2.0.0-pr6`. This version is not displayed on the site, which shows only the dataset release v1.6.0.
  The `license` field (`MIT`) was **not** changed; see MD-1.
- `.github/workflows/web-data.yml`: added the PR-6 scientific audit and its mutation self-test. CI has
  **not** run on this branch (no push).

## 4. Hosted-copy status

The README and MAINTENANCE reference https://congjianl.github.io/MicroRhodoDB/site/. A read-only fetch
on 2026-10-11 returned the **legacy** browser, whose search text matches `site/`. This is the expected
production state. Website 2.0 is not deployed, and no Pages setting was changed.
