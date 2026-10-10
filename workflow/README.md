# MicroRhodoDB build workflow (v1.6.0)

`workflow/Snakefile` has two targets.

- **`all` (default) - v1.6.0, re-executable from the repository or the release archive.** It applies the signed
  v1.6.0 curation decisions to the immutable v1.5.0 database and regenerates every v1.6.0 derived file. It then
  checks that the rebuilt database is content-identical to the shipped one and runs the release tests.
- **`all_v150` - the v1.5.0 build, kept as a record.** It is *not* re-executable from the archive, because it needs
  the v1.5.0 work directory (corpus FASTA, HMM alignments, tree and placement intermediates), which is not
  shipped. See "Re-executability" below.

## Quick start

Run everything from the repository root (or the root of the extracted archive).

```bash
conda env create -f workflow/envs/mrdb.lock.yml      # pinned environment (see "Environment")
conda activate mrdb
snakemake -n                                         # dry run: lists the 8 jobs
snakemake -c 4                                       # about 1 minute
```

All paths are relative and are set in `workflow/config.yaml` (`repo_dir: "."`, `v160_out: "work/v160_rebuild"`,
`mmseqs: "mmseqs"`). Override them with `--config key=value`. Nothing is written under `releases/`. Outputs go to
`work/v160_rebuild/`.

## v1.6.0 DAG

| Rule | Does | Output (under `work/v160_rebuild/`) |
|---|---|---|
| `rebuild_v160` | `pipeline/v160/build_v160.py`: copies `releases/v1.5.0/db/microrhododb_v1.5.0.sqlite` (opened `?mode=ro`) and applies `curation/v160/*_signed.tsv` (round 1 and R2), the blind-audit calls, the family-flag table and the Foldseek hit tables. The only external tool is MMseqs2, used for the E2 re-search. | `stage/microrhododb_v1.6.0.sqlite`, `build_log_v160.txt` |
| `data_dictionary_v160` | Adds the `data_dictionary` table from `curation/v160/{table,column}_definitions_v160.tsv`; fails unless 100% of columns are described | `db/microrhododb_v1.6.0.sqlite`, `data_dictionary_v160.tsv` |
| `export_tables_v160` | Flat TSV/FASTA exports, with tentative clades marked | `tables/` |
| `site_data_v160` | Browser payload `data.js` | `site/data.js` |
| `scorer_validation_v160` | Collects the scorer validation results (rule baseline, ablations, clade-root holdout, identity strata, family recall, InterPro retrieval counts) | `validation/scorer_validation_v160.tsv` |
| `compare_release_v160` | Compares every table and view of the rebuilt DB with `releases/v1.6.0/db/` (build timestamps excluded) | `compare_to_release_v160.tsv` |
| `test_v160` | `pytest tests/test_v160_release.py` against the rebuilt DB | `.tests_v160_passed` |

Verified result: 91/91 objects identical. The exports, `data.js`, the data dictionary TSV and the build log are
byte-identical to the shipped files. On the round-1 build, MMseqs2 18.8cc5c (pinned) and 17-b804f gave the same build log; the final build used 18.8cc5c.

## Re-executability

| Step | Re-executable from the archive? | Notes |
|---|---|---|
| v1.6.0 rebuild, data dictionary, exports, browser data, scorer-validation summary, comparison, tests (`all`) | **Yes** | Inputs shipped: `releases/v1.5.0/db`, `curation/v160/`, `pipeline/v160/`, `tools/` |
| CLI search (`tools/mrdb_search.py`) | **Yes** | Needs HMMER 3.4 and DIAMOND 2.1.10; tested on the 12 sequences in `tests/data/` |
| v1.6.0 Stage-1 curation proposals: conflicts and LOCO, engineered constructs, link labelling, addendum, LOCO sensitivity | Partly | Scripts in `pipeline/v160/` use relative paths (scratch dir `MRDB_V160_WORK`). The literature parts used network services. The *signed* outputs are what the build consumes. |
| Clade coverage report (`tools/clade_coverage_v160.py`) | **Yes** | Reads the release DB; output `releases/v1.6.0/validation/clade_coverage_v160.tsv` |
| R2 inputs: `pipeline/v160/r2_prepare_inputs.py`, `pipeline/v160/r2_clade_function.py` | Partly | Prepare and check the R2 inputs; the build applies them |
| R2 blind audit (`curation/v160/audit_blind_calls_v160.tsv`) and Foldseek watchlist (`curation/v160/foldseek_*_v160.tsv`) | No (record only) | Blind annotation by a separate annotator; Foldseek web-server queries (2026-10-10). Shipped as build inputs |
| R2 family-HMM flag (`curation/v160/novel_family_flag_v160.tsv`) | Yes | `tools/family_flag.py` (also run by `tools/mrdb_search.py`) with the five family HMMs in `releases/v1.6.0/scorer/family_hmms/` |
| v1.6.0 novel-family search and literature sweep | No (record only) | `pipeline/v160/stage1_records/`: sandbox paths and live EBI/UniProt/Europe PMC queries; results are signed in `curation/v160/` |
| v1.5.0 audit tables used by `scorer_validation_v160` | No (record only) | `curation/v160/audit_v150/` holds the audit tables and the two scripts that made them (sandbox paths) |
| v1.5.0 status, tree, placement, clades, evidence and DB build (`all_v150`: `wp2_status` ... `refpkg_checksums`) | No | Needs the unshipped v1.5.0 work directory. `build_tree` takes hours and `fetch_afdb_gtdb` makes thousands of network calls. The v1.5.0 DB is shipped and checksum-verified instead. |
| v1.4.0 scorer modules (`pipeline/v140/`) | Yes (as a library) | Imported by `pipeline/v150/score_v150.py` and therefore by the CLI |

## Environment

`workflow/envs/mrdb.lock.yml` is a full `conda env export --no-builds` of the build environment. It includes
IQ-TREE 2.3.6, HMMER 3.4, MAFFT 7.526, MMseqs2 18.8cc5c, EPA-ng 0.3.8, gappa 0.9.0, ClipKIT 2.14.0,
DIAMOND 2.1.10, Snakemake 8.30.0 and Python 3.11.16 with pandas 3.0.6 and numpy 2.4.6.

**DIAMOND.** DIAMOND is part of membership scoring. The membership score includes the seed-homology axis `e_homology`
(weight 0.10; best identity x coverage from DIAMOND blastp against the 15 scorer seeds), and the CLI uses DIAMOND a second time for its nearest-neighbour
search. The v1.5.0 README wrongly said DIAMOND was not used "for membership calling itself"; this is corrected here.
DIAMOND is pinned to 2.1.10. The reconstructed v1.4.0 scorer was built with 2.2.8, which is not on bioconda. The
v1.5.0 benchmark numbers and the CLI test expectations were produced with 2.1.10. Version 2.1.10 is not
guaranteed to give bit-identical homology scores to 2.2.8.

`workflow/Dockerfile` is provided but has not been built or tested. The conda lock file is the tested path.

## v1.5.0 historical target (`all_v150`)

The rules from `wp2_status` to `refpkg_checksums` are the exact record of how v1.5.0 was built. Every rule calls a
checked-in script in `pipeline/v150/` (or `pipeline/v140/`). Running them needs `work_dir`/`shared_dir` populated
with the v1.5.0 intermediates. Three rules are expensive:

- `build_tree`: hours on 16 threads.
- `fetch_afdb_gtdb`: network-bound.
- `place_queries`: under 1 h.

If the intermediates are restored, run `snakemake --touch all_v150` once before any real run. WP5 was revised in a
second pass after the tree was built, so the file modification times do not follow the DAG order.
