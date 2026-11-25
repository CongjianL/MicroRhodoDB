# MicroRhodoDB

A versioned, evidence-aware knowledgebase of Type-I microbial rhodopsins. MicroRhodoDB curates the
UniProtKB proteins that carry the Pfam bacteriorhodopsin-like domains PF01036 and PF18761 and gives each one:

- an explicit **membership status** (Type-I member, candidate, boundary family, heliorhodopsin outgroup, decoy);
- a placement on the **MR_RT_003 reference tree** (472 tips) with named clades (13 of the 19 level-1 groups are
  named after a characterised member; 6 carry provisional names, marked in the data);
- a **function-evidence level** (E1 experimental ... E5 none) with the basis of every call, conflict flags and
  linked publications;
- QC, redundancy, AlphaFold DB, retinal-pocket and GTDB taxonomy annotations.

Every release is an immutable SQLite database with SHA-256 checksums. Earlier releases are never modified.

## Current release: v1.6.1 (2026-10-24, schema `v161.1`)

| | |
|---|---|
| Records | 5,466 UniProtKB records (5,361 from UniProtKB 2026_02, 105 from 2026_03); 5,460 counted after excluding 6 engineered constructs |
| Membership | 3,091 Type-I members (incl. 6 curated overrides), 1,374 candidates, 509 boundary family, 386 heliorhodopsins, 106 decoy/rejected |
| Function evidence (counted records) | E1 88, E2 111, E3 1,143, E4 1,045, E5 3,073 |
| Function-call conflicts | 480 records flagged (`call_conflict = 1`) |
| Publications | 121 publications, 255 active record-publication links |
| Novel families | 139 records carry a family-HMM flag (best of five family HMMs beats PF01036); a Foldseek watchlist of 786 structure hits outside the corpus (181 `novel_family_candidate` rows); counts unaffected |

v1.6.1 corrects v1.6.0: identical sequences now share one membership status and one function call (23 records),
provisional clade names are marked, and the command-line scorer no longer reports heliorhodopsins as detected
Type-I rhodopsins. Details: `releases/v1.6.1/RELEASE_NOTES_v1.6.1.md` and `CHANGELOG.md`.

**v1.6.2 (2026-11-25) is built but not yet published.** It adds a helix-C motif for the 105 records that lacked one,
flags 51 Type-I records placed in the heliorhodopsin outgroup, and withdraws one E2 call whose motif differs from its
reference (`releases/v1.6.2/RELEASE_NOTES_v1.6.2.md`). Its database will be attached to a GitHub Release; until then
the defaults below stay at v1.6.1. The previous release,
v1.6.0 (2026-10-10), is described in `releases/v1.6.0/RELEASE_NOTES_v1.6.0.md` and its full report
`releases/v1.6.0/report_microrhododb_v1.6.0.md`.

**How to read the evidence levels.** E1-E5 are levels of *evidence*, not of accuracy. E1 records have direct
experimental characterisation. In a blind re-annotation of 40 records per level, the stored call was reproduced
for E2 39/40, E3 39/40 and E4 22/40. The re-annotation was drafted with an AI assistant and reviewed by the curator,
and the annotator also used homology, so this measures reproducibility, not ground truth. A leave-one-clade-out test
on the 76 unique E1 sequences gives the out-of-sample estimate: when a record's own clade is hidden, the inherited
(legacy) class is correct for 52/70 records (0.743, 95% CI 0.63-0.83), against 36/76 (0.47) for transferring the
class of the nearest other characterised protein. E3/E4 classes are inherited v1.4 labels; when they agree with the
motif evidence the basis reads `legacy_v14_concordant_motif`. Treat E4 calls as hypotheses.

**E5 mixes two cases.** E2-E4 calls are made only for Type-I members, so every candidate, boundary-family,
heliorhodopsin and decoy record is E5 by construction (2,373 of the 3,073 E5 records); only 700 E5 records are
members for which the evidence was insufficient. Filter on `membership_status` before reading E5 as "no evidence".
Membership needs a score of at least 0.86, while the command-line scorer's recommended discovery threshold is 0.70
(`typeI_detected_070`), so a sequence the CLI detects can be a candidate in the database with no function call.

## Getting the data

The SQLite databases are not in git. They are attached to the GitHub Release
[v1.6.1](https://github.com/CongjianL/MicroRhodoDB/releases/tag/v1.6.1); `BINARIES.md` lists every file with its
size and SHA-256.

```bash
python web/scripts/fetch_release_db.py    # downloads releases/v1.6.1/db/microrhododb_v1.6.1.sqlite and verifies it
```

## Quick start

**Browser.** The hosted browser is at https://congjianl.github.io/MicroRhodoDB/site/ (see `MAINTENANCE.md`).
A self-contained copy of the v1.6.0 browser is in `site/`: open `site/index.html` in any modern browser (no server
needed). Routes: `#/record/<MRDB or UniProt accession>`, `#/search` (Smith-Waterman/BLOSUM62 against all 5,466
records, top 10 hits), `#/novel`, `#/about`. The website for v1.6.1 is built from `web/` (see `docs/DEVELOPMENT.md`).

**Command-line search** (full membership score + nearest neighbour; needs HMMER 3.4 and DIAMOND 2.1.10):

```bash
conda env create -f workflow/envs/mrdb.lock.yml && conda activate mrdb   # Linux; on Apple-silicon macOS use workflow/envs/mrdb.macos-arm64.yml
python tools/mrdb_search.py my_proteins.faa -o hits.tsv                 # default: releases/v1.6.1
```

**Python API** (read-only):

```python
pip install -e .            # package in src/microrhododb
from microrhododb import MicroRhodoDB
with MicroRhodoDB() as db:  # default: releases/v1.6.1/db/microrhododb_v1.6.1.sqlite (or set MRDB_DB)
    db.counted()            # 5,460 records used in all statistics
    db.get("MRDB000001")    # bacteriorhodopsin P02945 and its identical-sequence records
    db.function_evidence(level="E1")
    db.data_dictionary("function_evidence")
```

**SQL.** The database is plain SQLite. Start from the view `v_master` (one row per record) or `v_counted`
(engineered constructs excluded). Every table and column is described in the `data_dictionary` table, also
shipped as `releases/v1.6.1/tables/data_dictionary_v161.tsv`.

**Flat files.** `releases/v1.6.1/tables/` holds TSV exports (records, function evidence, publication links,
call conflicts, engineered constructs, identical-sequence decisions, LOCO validation, clade-function consensus,
blind audit, Foldseek watchlist, novel-family layer, data dictionary) and `sequences_v161.fasta`. Tentative clade
calls are marked in every export (`clade_confidence`, and `clade_display` = `TENTATIVE:<clade>`).

## Reproducing the release

Each release is built from the database of the release before it plus signed curation files:

| Target | Input database | Re-executable from public files? |
|---|---|---|
| v1.6.1: `snakemake -c 1 all_v161` (seconds; 93/93 objects identical to the shipped DB) | v1.6.0 (on the v1.6.1 GitHub Release) | Yes |
| v1.6.0: `snakemake -c 4` (about 1 minute; 91/91 objects identical) | v1.5.0 | Not yet: the v1.5.0 database is not published (checksum in `BINARIES.md`) |
| v1.5.0 corpus, tree, placement and evidence build (`all_v150`) | v1.5.0 work directory | No: kept as a record only |

```bash
conda env create -f workflow/envs/mrdb.lock.yml && conda activate mrdb
python web/scripts/fetch_release_db.py --asset microrhododb_v1.6.0.sqlite --dest releases/v1.6.0/db/microrhododb_v1.6.0.sqlite
snakemake -c 1 all_v161          # writes to work/v161_rebuild/ and compares with the shipped v1.6.1 DB
python -m pytest -q tests/       # tests that need an absent database skip
```

`workflow/README.md` lists which steps are re-executable and which were run outside the workflow (literature
sweep, novel-family search, blind audit, Foldseek queries); `docs/LEGACY_AND_MISSING_COMPONENTS.md` records what
the repository does not contain for the releases before v1.5.0.

## Repository layout

| Path | Content |
|---|---|
| `releases/v1.6.1/` | current release: tables, scorer files, validation analyses, build log, notes, `SHA256SUMS` (DB on the GitHub Release) |
| `releases/v1.6.0/` | previous release, base of v1.6.1: tables, scorer files, validation summary, notes, report |
| `releases/v1.5.0/`, `releases/v1.4.0/`, `releases/v1.3.0/`, `releases/v1.0/` | immutable earlier releases (base of v1.6.0; read by the historical tests) |
| `curation/v161/`, `curation/v160/` | signed curator decisions, publication metadata, data-dictionary definitions, audit inputs |
| `pipeline/v161/`, `pipeline/v160/` | release builds, data dictionaries, validation analyses, DB comparison |
| `pipeline/v150/`, `pipeline/v140/` | v1.5.0 build and the v1.4.0 scorer/feature modules the scorer still imports |
| `refpkg/MR_RT_003/` | reference tree package (alignments, HMMs, model files) |
| `src/microrhododb/` | Python API |
| `tools/` | CLI search, exports, browser data builder, audit sampler |
| `site/` | static v1.6.0 browser |
| `web/` | website 2.0 source (see `docs/DEVELOPMENT.md`) |
| `workflow/` | Snakefile, config, pinned conda environments |
| `tests/` | release tests and the Playwright browser walkthrough |
| `docs/` | data model, architecture, release history, scientific scope; `docs/DEVELOPMENT.md` for website build and deployment |

## Integrity

```bash
cd releases/v1.6.1 && sha256sum -c SHA256SUMS
```

## Licence and citation

Data: CC BY 4.0. Code: MIT. Cite the release you used via `CITATION.cff`. No DOI has been minted yet: cite the
release version and the GitHub Release (https://github.com/CongjianL/MicroRhodoDB/releases/tag/v1.6.1).
Maintenance, hosting and update policy: `MAINTENANCE.md`.
