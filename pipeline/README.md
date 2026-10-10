# pipeline/

**Status: the original staged builder is LOST. This directory holds what the
2026-09-28 reproducibility recovery could salvage — evidence and legacy code,
not a runnable pipeline.**

## What the original pipeline was

MicroRhodoDB v1.2.0 was built by a 12-stage builder (`s01_protein.py` …
`s12_provenance.py` under `v12/build/stages/`, driven by `build_v120.py` with
`manifest.py` and `active_policy.py`), and v1.3.0 added an overlay
(`build_v13_base/`: `ingest_evidence.py`, `populate_external.py`,
`score_external.py`, `run_holdouts.py`, `holdout_engine.py`,
`populate_holdout.py`, `build_tree_provenance.py`, `build_sequence_source.py`,
`tests_release.py`, `tests_env.py`, schema fragments). The authoritative record
of what each stage did is the v1.3.0 database table `build_provenance`
(37 rows), summarized in `docs/BUILD_PIPELINE.md`.

**None of these files survive in full anywhere** (verified 2026-09-28 across
all six project sessions, HPC history, and both session workspaces). The
original session's transcript is lossy (tool-call arguments truncated at
~624 characters), so only file prefixes and exact byte sizes survive.

## Contents

- `recovery_probes.py` — **runnable** layer-reproducibility probes (P1–P9)
  written during the recovery. Re-derives every fully-specified deterministic
  layer from preserved inputs and compares against the frozen v1.3.0 DB:
  raw-input identity, membership carry, exact-NR redundancy, MMseqs2
  90/65/40 clustering (external mmseqs2 step), tree provenance, external
  validation metrics, holdout metrics, QC hmmsearch (pyhmmer), environmental
  invariants. Result: 7 PASS, 2 MATCH-WITH-DIFFERENCES (MMseqs2 clustering and
  HMMER QC — both tool-version/order-sensitive; differences documented in
  `report_reproducibility_recovery.md`).
- `legacy_notebook_code/` — unmodified code-cell dumps of the two historical
  notebooks. `rhodo_v1_era_cells.py` (195 cells) contains the complete
  v1.0-era research-pipeline code from which the staged builder was later
  formalized; `rhodo2_v13_era_cells.py` (18 cells) contains v1.3-era
  PR13.4–PR13.9 logic. These are the **largest surviving bodies of original
  pipeline logic**, in their original notebook form.
- `transcript_evidence/` — the recovery evidence base:
  - `lost_files_manifest.tsv` — all 77 files the original session wrote via
    the Write tool: path, exact byte size, surviving prefix length, transcript
    line references, LOST/SURVIVED status.
  - `heredoc_files.tsv` — 15 additional files created via Bash heredocs.
  - `prefixes/` — the surviving ~500-character prefix of each lost file
    (docstrings, imports, function signatures). Genuine historical evidence;
    **no content beyond these prefixes exists anywhere.**
  - `bash_command_log.tsv` — 1,144 executed commands (truncated), the
    workflow-level execution log.
  - `edit_events.tsv` — 71 Edit events (paths + transcript lines).

## What recovery established

- The **raw input ancestor** survives and is sequence-verified:
  `data/preserved_inputs/precursor_sessions/sess_a09c9ba0dda8_type1_rhodopsin_dataset/`
  (5,361/5,361 sequences identical to the frozen DB).
- **Layer-by-layer probes** (`recovery_probes.py`): P1 raw input PASS,
  P2 membership carry PASS, P3 exact-NR PASS, P4 MMseqs2 90/65/40
  MATCH-WITH-DIFFERENCES (partitions 98–99% pure; tool version/input order/
  representative re-ranking not fully preserved), P5 tree provenance PASS
  (MR_RT_001 topology + all 60 clades internally consistent; the preserved
  treefile is the documented orphan MR_RT_002), P6 external validation PASS
  (18/18 metrics + Clopper-Pearson CIs), P7 holdout PASS (264/264 pooled+fold
  metrics), P8 QC hmmsearch MATCH-WITH-DIFFERENCES (hmm_cov definition
  confirmed, 92.4% coordinate-exact under HMMER 3.4 vs 3.3; complete_core rule
  100%), P9 environmental PASS (501/851 split, full membership isolation).
- Full detail: `report_reproducibility_recovery.md` (delivered alongside the
  repository) and `docs/BUILD_PIPELINE.md`.

## If the original builder is ever recovered

Land it here (`pipeline/`), register SHA-256s in
`docs/repository_inventory.tsv`, and reconcile against
`transcript_evidence/lost_files_manifest.tsv` (exact byte sizes) and the
`prefixes/` (content must match). Only then does a true clean rebuild become
possible.
