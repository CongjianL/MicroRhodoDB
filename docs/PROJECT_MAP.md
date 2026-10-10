# Project Map

> **v1.6.0 note.** The current release is `releases/v1.6.0/`; the README "Repository layout" table lists the v1.6.0
> directories (`pipeline/v160/`, `curation/v160/`, `src/microrhododb/`, `site/`, `workflow/`). The tree below is the
> v1.4.0 map.

Annotated map of the repository. Every top-level directory has exactly one
purpose. Generated at the 2026-09-27 reorganization; the machine-readable
companion is `docs/repository_inventory.tsv`.

```text
MicroRhodoDB/
├── README.md                  # START HERE — what/where/how (short, operational)
├── CHANGELOG.md               # release history + reorganization entry
├── pyproject.toml             # packaging for src/microrhododb (the only package)
│
├── docs/                      # ALL documentation lives here
│   ├── ARCHITECTURE.md        #   how the system works (9-layer scientific flow)
│   ├── PROJECT_MAP.md         #   this file
│   ├── DATA_MODEL.md          #   v1.3.0 tables grouped by responsibility + v1.4.0 delta
│   ├── BUILD_PIPELINE.md      #   known build stages + what is MISSING
│   ├── RELEASE_HISTORY.md     #   v1.0→v1.3 evolution (facts vs inference)
│   ├── SCIENTIFIC_SCOPE.md    #   what MicroRhodoDB is and is not
│   ├── LEGACY_AND_MISSING_COMPONENTS.md
│   └── repository_inventory.tsv  # machine-readable file classification
│
├── src/
│   └── microrhododb/          # ACTIVE CODE — the only maintained surface
│       ├── __init__.py        #   package exports
│       └── api.py             #   query API v1.4.0 (adds placement_v140 /
│                              #   extension_delta queries, clade tree-join fix)
│
├── schema/
│   ├── current/schema_v130.sql       # convenience copy of the v1.3.0 DDL
│   └── historical/schema_v120.sql    # v1.2.0 DDL (authoritative copies live
│                                     # inside the immutable releases)
│
├── pipeline/                  # recovery (2026-09-28) + v1.4.0 reconstruction
│   ├── README.md              #   what was lost, what survives, landing zone
│   ├── recovery_probes.py     #   runnable layer-reproducibility probes P1–P9
│   ├── v140/                  #   reconstructed frozen scorer (0-diff gate) used
│   │                          #   to build v1.4.0: scorer/features/tree modules
│   ├── legacy_notebook_code/  #   unmodified cell dumps of both notebooks
│   └── transcript_evidence/   #   lost-files manifest, file prefixes, cmd log
│
├── tests/
│   ├── README.md              # v1.2/v1.3 suites LOST; landing zone + what survives
│   └── release_v140.py        # v1.4.0 release suite (18 tests; 18/18 PASS)
│
├── data/
│   ├── README.md              # preserved-inputs status
│   └── preserved_inputs/      # recovery (2026-09-28): precursor-session copies
│       ├── recovery_manifest.tsv   # SHA-256 for every recovered file
│       └── precursor_sessions/     # type1_rhodopsin_dataset (raw-input
│                                   # ancestor, sequence-verified), rhodopsin_tool,
│                                   # rhodopsin_survey — each with SHA256SUMS+PROVENANCE
│
├── notebooks/
│   └── legacy_execution_trace/  # HISTORICAL EVIDENCE, not the canonical build
│       ├── rhodo.ipynb          #   v1.0-era build notebook (195 cells)
│       ├── rhodo2.ipynb         #   v1.1/v1.3-era notebook (18 cells)
│       └── PLAN_v130_historical.md  # approved v1.3.0 build plan
│
├── workspaces/                # development workspaces (non-release by definition)
│   ├── historical/
│   │   └── v13_pr7_pilot_analysis/  # v1.3 pilot workspace; all 7 files
│   │                                # byte-identical to releases/v1.3.0 outputs
│   └── hpc/                       # HPC job outputs with full provenance
│       ├── hpc_955c5479-…/          # ESMFold B0R633 (PDB byte-identical to
│       │                            # releases/v1.0/structures/; JSON unique)
│       └── hpc_e5907b70-…/          # ESMFold A0A9X2L7U0 (same pattern)
│
├── reports/                   # release-era analysis reports (not part of any
│   ├── report_pilot_error_analysis.md    # release directory; v1.3.0 WS7/WS8)
│   └── report_expansion_decision_memo.md
│
├── releases/                  # IMMUTABLE ARTIFACTS — never edit anything here
│   ├── v1.0/    # 2026-07-30 notebook-era release: api/ benchmark/ db/
│   │            # figures/ meta/ phylogeny/ sequences/ structures/ tables/
│   │            # + report_microrhododb.md
│   ├── v1.1/    # 2026-08-04 remediation/phylogeny/benchmark: db/ figures/
│   │            # meta/ + report
│   ├── v1.2.0/  # 2026-08-30 staged-builder release: db/ figures/ meta/
│   │            # validation/ + RELEASE_NOTES + report
│   ├── v1.3.0/  # 2026-09-24 frozen golden artifact: analysis/ db/ figures/
│   │            # meta/ validation/ + RELEASE_NOTES + report + SHA256SUMS
│   └── v1.4.0/  # 2026-10-02 CURRENT: append-only extension + MR_RT_002
│                # promotion: db/ meta/ tables/ validation/ + RELEASE_NOTES
│                # + report + SHA256SUMS (10 files)
│
└── archive/
    └── unclassified_or_superseded/  # holding area — currently EMPTY
        └── README.md                # (everything was classifiable)
```

## Designated-but-absent directories — UPDATED 2026-09-28

`pipeline/` and `tests/` now exist, populated by the reproducibility recovery:

- `pipeline/` — **not a runnable pipeline**: the original staged builder is
  confirmed lost. Holds `legacy_notebook_code/` (unmodified cell dumps of the
  two historical notebooks — the largest surviving original logic),
  `transcript_evidence/` (lost-files manifest with exact byte sizes, surviving
  ~500-char prefixes of every lost builder file, bash command log), and
  `recovery_probes.py` (the runnable P1–P9 layer-reproducibility probes; 7 PASS,
  2 MATCH-WITH-DIFFERENCES — see `report_reproducibility_recovery.md`). See
  `pipeline/README.md`.
- `tests/` — the v1.2/v1.3 release suites remain lost (landing-zone README);
  `release_v140.py` (2026-10-02) is the new, runnable v1.4.0 suite.
- `data/preserved_inputs/` — recovered precursor assets with SHA-256 manifests
  (see `data/preserved_inputs/README.md`); the original build inputs
  (`rhodo_checkpoints/`, `v11_*.parquet`) remain missing.

## One-line routing guide

| You want to… | Go to |
|---|---|
| Use the database | `releases/v1.4.0/db/` via `src/microrhododb/` |
| Understand the system | `docs/ARCHITECTURE.md` |
| Understand the tables | `docs/DATA_MODEL.md` |
| Rebuild the DB | `docs/BUILD_PIPELINE.md` first — currently not possible from repo alone |
| Check a release's integrity | `releases/v1.4.0/SHA256SUMS` (and each release's own) |
| See how v1.0 was actually built | `notebooks/legacy_execution_trace/rhodo.ipynb` (historical evidence) |
| Find why a decision was made | per-release `RELEASE_NOTES`/`report`, then `reports/` |
| Develop new code | `src/microrhododb/` (never inside `releases/`) |
