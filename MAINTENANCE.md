# Maintenance, hosting and sustainability

This file states how MicroRhodoDB is kept up to date and what happens if maintenance stops. Fields marked
`<<PLACEHOLDER>>` must be filled in by the maintainers before submission; they are not yet decided.

## Maintainers and contact

- Lead maintainer: CongJian Li (GitHub `CongjianL`)
- Contact address: `<<PLACEHOLDER: institutional e-mail>>`
- Issues and data corrections: GitHub issues on `CongjianL/MicroRhodoDB`

## Update cadence

- **Corpus updates:** `<<PLACEHOLDER: e.g. one release per year, following a UniProtKB release>>`.
  Each update re-retrieves PF01036/PF18761 proteins, records the UniProtKB release and retrieval date per
  record (`sequence_source.source_release`), and reports InterPro counts with retrieval dates.
- **Curation updates:** literature-driven E1 changes and error corrections reported by users are batched into
  the next minor release. Every curator decision is recorded with decider and date in the release database.
- **Versioning:** semantic versions. Released databases are immutable; corrections always go into a new release
  with a `CHANGELOG.md` entry.

## Hosting

| Component | Location | Term |
|---|---|---|
| Source, flat files, browser | GitHub repository `CongjianL/MicroRhodoDB` | while the account exists |
| Browser (live) | GitHub Pages, https://congjianl.github.io/MicroRhodoDB/site/ | `<<PLACEHOLDER: hosting term>>` |
| Release databases and archives | GitHub Release assets and Zenodo (DOI `<<PLACEHOLDER: Zenodo DOI>>`) | Zenodo: long-term archive |

The browser is a static site with no server component, so any static host (or a local copy opened from disk)
can serve it.

## Funding

`<<PLACEHOLDER: funding source and period, or "no dedicated funding">>`.

## End of life

If active maintenance stops:

1. The final release stays available on Zenodo under its DOI and on GitHub.
2. The README will state the date maintenance ended and the last release.
3. `<<PLACEHOLDER: named successor or institutional custodian, if any>>`.

Because every release is a self-contained SQLite file plus TSV/FASTA exports and a static browser, the data
remain usable without any running service.
