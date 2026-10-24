# Maintenance, hosting and sustainability

This file states how MicroRhodoDB is kept up to date and what happens if maintenance stops. Decided by the lead
maintainer on 2026-10-24.

## Maintainers and contact

- Lead maintainer: CongJian Li (GitHub `CongjianL`)
- Contact: GitHub issues on `CongjianL/MicroRhodoDB` are the only support channel; there is no e-mail contact.
- Issues and data corrections: GitHub issues on `CongjianL/MicroRhodoDB`

## Update cadence

- **Corpus updates:** irregular, best effort: there is no fixed schedule; a new corpus release is made when
  resources allow. Each update re-retrieves PF01036/PF18761 proteins, records the UniProtKB release and retrieval date per
  record (`sequence_source.source_release`), and reports InterPro counts with retrieval dates.
- **Curation updates:** literature-driven E1 changes and error corrections reported by users are batched into
  the next minor release. Every curator decision is recorded with decider and date in the release database.
- **Versioning:** semantic versions. Released databases are immutable; corrections always go into a new release
  with a `CHANGELOG.md` entry.

## Hosting

| Component | Location | Term |
|---|---|---|
| Source, flat files, browser | GitHub repository `CongjianL/MicroRhodoDB` | while the account exists |
| Browser (live) | GitHub Pages, https://congjianl.github.io/MicroRhodoDB/site/ | no fixed term: online while the GitHub account and GitHub Pages remain available |
| Release databases and archives | GitHub Release assets | while the account exists; no archival deposit with a DOI exists yet |

The browser is a static site with no server component, so any static host (or a local copy opened from disk)
can serve it.

## Funding

No dedicated funding.

## End of life

If active maintenance stops:

1. The final release stays available on GitHub (repository and Release assets) for as long as the account exists.
2. The README will state the date maintenance ended and the last release.
3. There is no named successor or institutional custodian.

Because every release is a self-contained SQLite file plus TSV/FASTA exports and a static browser, the data
remain usable without any running service.
