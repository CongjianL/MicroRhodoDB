# Web data export (PR-1; schema 1.1.0 since PR-2)

`tools/export_web_data.py` turns the official v1.6.0 SQLite database plus the frozen reference package into the
static JSON/FASTA/Newick/PDB files the website reads. It uses the Python standard library only and opens the
database read-only. The contract is `WEB_DATA_CONTRACT.md`; normative shapes are
`web/src/data/schemas/web-data.schema.json` (TypeScript: `web/src/data/types.ts`, generated).

## Commands

```bash
# 1. Get the database (CI: from the GitHub Release; verified against BINARIES.md, SHA-256 + size)
python web/scripts/fetch_release_db.py          # exit 2 + BLOCKED_DATA_SOURCE if the Release/asset is absent

# 2. Export (default output web/public/data/, which is gitignored)
python tools/export_web_data.py                 # --db, --out, --expected-sha256, --repo are optional

# 3. Validate (gate G1)
python -m pytest -q tests/test_web_export.py tests/test_fetch_release_db.py

# 4. After editing the schema, regenerate and check the TypeScript types
python web/scripts/schema_to_ts.py && python web/scripts/schema_to_ts.py --check

# Support-label audit (owner review item; WEB_BASELINE_AUDIT.md section 10.2)
python web/scripts/pr1_support_label_audit.py
```

## Inputs and checks (fail closed)

| Input | Check | On failure |
|---|---|---|
| `releases/v1.6.0/db/microrhododb_v1.6.0.sqlite` | SHA-256 `379a2543...dce17f` | exit 2 `BLOCKED_DATA_SOURCE` |
| `refpkg/MR_RT_003/{tree/MR_RT_003.rooted.treefile, tree/run1.treefile, tips.tsv, clades/MR_CLD3_tips.tsv}` | `refpkg/MR_RT_003/SHA256SUMS`; rooted tree pinned | exit 2 `BLOCKED_DATA_SOURCE` |
| `predicted_structure.pdb_file` (stored release-relative, e.g. `structures/B0R633_esmfold.pdb`) | resolved by `releases/*/<pdb_file>`; exactly one match; SHA-256 equals the frozen value | exit 3 `STRUCTURE_SOURCE_ANOMALY` |
| Any contract invariant (empty strings outside `EMPTY_STRING_RULES`, tip/clade mismatches, distribution totals vs denominators, ...) | in-exporter `require(...)` | exit 4 `CONTRACT_VIOLATION` |

The exporter writes into `<out>/.staging-v1.6.0/` and renames it into place. It only replaces an existing
`<out>/v1.6.0/` that contains `export_manifest.json` (a previous export).

## Output (`<out>/`)

```
current.json                         {"dataset_release","path","schema_version"}
v1.6.0/manifest.json                 release, input checksums, counts, exporter commit + git_dirty (no timestamps)
v1.6.0/summary.json                  28 metrics + 15 distributions, each with its SQL (or source file) and denominator
v1.6.0/records-index.json            5,466 rows x 46 columns (Browse / search; 25 in schema 1.0.0)
v1.6.0/accessions.json               by_source (5,466) and by_mrdb (5,299)
v1.6.0/records/MRDB*.json            5,299 entries; every v_master column, PDB links, AFDB, predicted, publications
v1.6.0/sequences/corpus.fasta        5,466 sequences
v1.6.0/structures-index.json         438 PDB entries, 2 predicted models, AFDB URL template
v1.6.0/structures/predicted/*.pdb    byte copies of releases/v1.0/structures/{A0A9X2L7U0,B0R633}_esmfold.pdb
v1.6.0/evidence-index.json           E1 set, call conflicts, curated overrides, policies
v1.6.0/clades.json                   17 level-1 clades + 2 backbone groups, 30 subclades, function consensus, support audit
                                     (+ IQ-TREE run1 SH-aLRT/UFBoot numbers, threshold flag, clade_rule; schema 1.1.0)
v1.6.0/vocabulary.json               membership-status, function-class, E1-E5 and clade-state definitions (schema 1.1.0)
v1.6.0/phylogeny/                    rooted Newick (byte copy), tips, clade_tips, tree_stats, support_audit, robustness, preview.svg
v1.6.0/publications.json             121 publications, 255 active links, 7 inactive links (audit only)
v1.6.0/watchlist.json                181 candidates, isolated from the corpus
v1.6.0/export_manifest.json          sha256/bytes/records of every other file
```

Determinism: sorted keys, compact separators, UTF-8, `allow_nan=False`, trailing newline, stable row order, full
precision floats, no wall-clock timestamps. Two exports at the same commit are byte-identical (tested).

Schema 1.1.0 (PR-2) is additive; see `WEB_DATA_CONTRACT.md` section 11. The website build (`web/`, `npm run build`)
reads this export from `web/public/data/`; run the exporter before building or running the browser tests.
