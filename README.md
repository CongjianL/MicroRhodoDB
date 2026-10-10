# MicroRhodoDB

A versioned, evidence-aware knowledgebase of Type-I microbial rhodopsins. MicroRhodoDB curates the
UniProtKB proteins that carry the Pfam bacteriorhodopsin-like domains PF01036 and PF18761 and gives each one:

- an explicit **membership status** (Type-I member, candidate, boundary family, heliorhodopsin outgroup, decoy);
- a placement on the **MR_RT_003 reference tree** (472 tips) with literature-named clades;
- a **function-evidence level** (E1 experimental ... E5 none) with the basis of every call, conflict flags and
  linked publications;
- QC, redundancy, AlphaFold DB, retinal-pocket and GTDB taxonomy annotations.

Every release is an immutable SQLite database with SHA-256 checksums. Earlier releases are never modified.

## Current release: v1.6.0 (2026-10-10, schema `v160.1`)

| | |
|---|---|
| Records | 5,466 UniProtKB records (5,361 from UniProtKB 2026_02, 105 from 2026_03); 5,460 counted after excluding 6 engineered constructs |
| Membership | 3,089 Type-I members (incl. 4 curated overrides of E1 records), 1,379 candidates, 509 boundary family, 386 heliorhodopsins, 103 decoy/rejected |
| Function evidence (counted records) | E1 88, E2 109, E3 1,143, E4 1,050, E5 3,070 |
| Function-call conflicts | 468 records flagged (`call_conflict = 1`); 439 E3/E4 calls that contradicted the record's own motif evidence were downgraded to E5 `unassigned` |
| Publications | 121 publications, 255 active record-publication links; all 91 E1 records have a supporting publication |
| Novel families | 139 records carry a family-HMM flag (best of five family HMMs beats PF01036); a Foldseek watchlist of 786 structure hits outside the corpus (181 `novel_family_candidate` rows); counts unaffected |
| Browser | `site/index.html` - opens directly from disk or over HTTP; sequence search, deep links, FASTA/TSV export. Hosted copy: https://congjianl.github.io/MicroRhodoDB/site/ (see `MAINTENANCE.md` for status) |

What changed in v1.6.0 and why is in `CHANGELOG.md` and `releases/v1.6.0/RELEASE_NOTES_v1.6.0.md`; the full
release report is `releases/v1.6.0/report_microrhododb_v1.6.0.md`.

**How to read the evidence levels.** E1-E5 are levels of *evidence*, not of accuracy. E1 records have direct
experimental characterisation. In a blind re-annotation of 40 records per level, the stored call was reproduced
for E2 39/40, E3 39/40 and E4 22/40 (the annotator also used homology, so this measures reproducibility, not
ground truth). A leave-one-clade-out test on the 76 unique E1 sequences gives the out-of-sample estimate: when a
record's own clade is hidden, the inherited (legacy) class is correct for 52/70 records (0.743, 95% CI 0.63-0.83).
E3/E4 classes are inherited v1.4 labels; when they agree with the motif evidence the basis reads
`legacy_v14_concordant_motif`. Treat E4 calls as hypotheses.

## Quick start

**Browser.** Open `site/index.html` in any modern browser (no server needed). Routes: `#/record/<MRDB or
UniProt accession>`, `#/search` (Smith-Waterman/BLOSUM62 against all 5,466 records, top 10 hits),
`#/novel`, `#/about`.

**Command-line search** (full membership score + nearest neighbour; needs HMMER 3.4 and DIAMOND 2.1.10):

```bash
conda env create -f workflow/envs/mrdb.lock.yml && conda activate mrdb
python tools/mrdb_search.py my_proteins.faa -o hits.tsv
```

**Python API** (read-only):

```python
pip install -e .            # package in src/microrhododb
from microrhododb import MicroRhodoDB
with MicroRhodoDB() as db:  # default: releases/v1.6.0/db/microrhododb_v1.6.0.sqlite (or set MRDB_DB)
    db.counted()            # 5,460 records used in all statistics
    db.get("MRDB000001")    # bacteriorhodopsin P02945 and its identical-sequence records
    db.function_evidence(level="E1")
    db.data_dictionary("function_evidence")
```

**SQL.** The database is plain SQLite. Start from the view `v_master` (one row per record) or `v_counted`
(engineered constructs excluded). Every table and column is described in the `data_dictionary` table, also
shipped as `releases/v1.6.0/tables/data_dictionary_v160.tsv`.

**Flat files.** `releases/v1.6.0/tables/` holds TSV exports (records, function evidence, publication links,
call conflicts, engineered constructs, LOCO validation, clade-function consensus, blind audit, Foldseek
watchlist, novel-family layer, data dictionary) and
`sequences_v160.fasta`. Tentative clade calls are marked in every export (`clade_confidence`, and
`clade_display` = `TENTATIVE:<clade>`).

## Reproducing the release

```bash
conda env create -f workflow/envs/mrdb.lock.yml && conda activate mrdb
snakemake -n                     # dry run, from the repository root
snakemake -c 4                   # rebuild v1.6.0 from the immutable v1.5.0 DB + signed curation (~1 min)
python -m pytest -q tests/       # 52 tests, 0 skips when releases/v1.0, v1.3.0, v1.4.0 and v1.5.0 are present (all in the archive)
```

The rebuild writes to `work/v160_rebuild/` and checks that the rebuilt database is content-identical to the
shipped one (91/91 objects). `workflow/README.md` lists which steps are re-executable from this repository and
which were run outside the workflow.

## Repository layout

| Path | Content |
|---|---|
| `releases/v1.6.0/` | current release: DB, tables, scorer files, validation summary, build log, notes, report, `SHA256SUMS` |
| `releases/v1.5.0/`, `releases/v1.4.0/` | immutable earlier releases (base of v1.6.0; checked by the tests) |
| `releases/v1.3.0/`, `releases/v1.0/` | immutable earlier releases read by the historical v1.4.0 test suite |
| `curation/v160/` | signed curator decisions, publication metadata, data-dictionary definitions, audit inputs |
| `pipeline/v160/` | v1.6.0 build, data dictionary, scorer-validation summary, DB comparison |
| `pipeline/v150/`, `pipeline/v140/` | v1.5.0 build and the v1.4.0 scorer/feature modules the scorer still imports |
| `refpkg/MR_RT_003/` | reference tree package (alignments, HMMs, model files) |
| `src/microrhododb/` | Python API |
| `tools/` | CLI search, exports, browser data builder, audit sampler |
| `site/` | static browser |
| `workflow/` | Snakefile, config, pinned conda environment |
| `tests/` | release tests and the Playwright browser walkthrough |

Large binary files (SQLite databases, archives) are attached to the GitHub Release and the Zenodo deposit, not
committed to git; `BINARIES.md` lists them with SHA-256 checksums.

## Integrity

```bash
cd releases/v1.6.0 && sha256sum -c SHA256SUMS
```

## Licence and citation

Data: CC BY 4.0. Code: MIT. Cite the release you used via `CITATION.cff` (Zenodo DOI to be added on deposit).
Maintenance, hosting and update policy: `MAINTENANCE.md`.
