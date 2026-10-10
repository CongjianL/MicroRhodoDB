# v1.6.0 Stage-1 records (not part of the re-executable workflow)

These scripts produced the curation *proposals* that the curator signed before the v1.6.0 build. They are kept
as an exact record of what was run. They are **not** re-executable from this repository as-is:

- they contain absolute paths of the build sandbox (`/workspace/...`, `/mnt/...`);
- they call network services whose content changes over time (EBI HMMER REST API on UniProtKB, UniProt REST,
  Europe PMC, RCSB PDB);
- their outputs were reviewed and signed by a curator, so re-running them would produce a new proposal set that
  needs a new sign-off, not a reproduction of v1.6.0.

What *is* reproducible is everything downstream of the signed decisions: `snakemake -c 4` rebuilds the v1.6.0
database from `releases/v1.5.0` and `curation/v160/*.tsv` and checks that it is content-identical to the shipped
database.

| Folder | Produced | Signed / shipped result |
|---|---|---|
| `novel_family/` | Seed alignments and profile HMMs for MerMAID, bestrhodopsin, schizorhodopsin, xenorhodopsin and viral rhodopsin (`seeds/`); EBI HMMER search of UniProtKB (run log `run_log_v2.txt`, job IDs `ebi_jobs_v2_fresh.json`) and a local Swiss-Prot `hmmsearch`; the filter funnel | `curation/v160/novel_family_funnel_v160.tsv`, `novel_family_candidates_v160.tsv` (0 candidates) |
| `literature/` | Literature/UniProt/PDB sweep of the PE1/reviewed landmark proteins and external positives; record-level proposals | `curation/v160/curation_v160_records_signed.tsv`, `curation_v160_groups_signed.tsv` |

The other Stage-1 scripts (`conflicts_loco.py`, `engineered.py`, `build_link_spec.py`, `build_addendum.py`,
`loco_sensitivity.py`) are in `pipeline/v160/` and use repository-relative paths; set `MRDB_V160_WORK` for their
scratch directory (default `work/v160_stage1`).
