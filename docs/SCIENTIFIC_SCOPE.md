# Scientific Scope

> **Status as of v1.6.0 (2026-10-10).** The sections below describe the v1.3.0 design and are kept for history.
> Where they differ, these statements are current:
> - Current release v1.6.0: 5,466 UniProtKB records (5,460 counted); 3,089 Type-I members (4 by signed curated
>   override, `typeI_member_curated`), 1,379 candidates, 509 boundary family, 386 heliorhodopsins, 103
>   decoy/rejected. Function evidence E1-E5 are evidence levels, not accuracy tiers.
> - Membership authority is still `membership.membership_status`; the only curated exception is the
>   `typeI_member_curated` route for E1 records with a cited experiment. Scores and thresholds are unchanged.
> - `tools/mrdb_search.py` scores user sequences with the frozen scorer (recommended threshold 0.70) and reports a
>   family-HMM flag; the database itself is still a frozen release.
> - v1.6.0 is rebuildable from the archive (`snakemake -c 4`, 91/91 objects identical to the release); earlier
>   builds remain non-rebuildable as described in `docs/LEGACY_AND_MISSING_COMPONENTS.md`.
> - Novel families outside Pfam reach are tracked in a separate watchlist (`novel_family_candidate`, 181 rows)
>   and never enter counts.

## What MicroRhodoDB is

MicroRhodoDB is a **versioned, evidence-aware, reproducibly validated Type-I
microbial rhodopsin knowledgebase**.

Each word of that definition is a design commitment:

- **Versioned** — science ships as immutable, checksummed releases
  (v1.0 → v1.3.0). A release, once published, never changes; corrections and
  expansions become new releases.
- **Evidence-aware** — labels are gated by evidence paths. Subfamily and
  function assignments carry `is_active` flags; exploratory phylogenetic
  placements and heuristic publication parsing are retained as evidence but
  never silently promoted to active annotations. Tier-A experimental evidence
  is curated separately (`tier_a_evidence`) with literature linkage.
- **Reproducibly validated** — every release ships machine-checkable proof:
  invariant suites (v1.2.0: V1–V20 + A1–A7; v1.3.0: 52 release tests),
  SHA-256 manifests, per-table build provenance, leakage-controlled holdout
  benchmarks, and an exposure-audited external validation set scored at
  **frozen** thresholds (confirmed 0.90 / high 0.86 / candidate 0.70 /
  rhodopsin-like 0.40).
- **Type-I microbial rhodopsin** — the scientific target is the Type-I
  (microbial, retinal-binding) rhodopsin family: ion pumps, channels, and
  sensory rhodopsins across bacteria, archaea, and microbial eukaryotes,
  sourced from UniProtKB with a controlled MGnify environmental pilot.

The current scientific state is **v1.3.0**: 5,361 UniProt proteins with
authoritative membership (4,881 active Type-I: 3,033 core + 1,848 candidate),
377 heliorhodopsins tracked as a related outgroup family, 103
decoy/rejected records retained for benchmark audit, and 1,352 environmental
pilot records isolated from membership.

## What MicroRhodoDB is not

- **Not an arbitrary collection of analysis outputs.** Every table exists
  because a defined pipeline layer produces it and a release test guards it
  (see `docs/ARCHITECTURE.md`).
- **Not a general rhodopsin database.** Animal (Type-II) rhodopsins are out
  of scope; heliorhodopsins are included only as a explicitly-labeled
  neighboring family for boundary control.
- **Not a real-time mirror of UniProt/MGnify.** Sources are pinned per
  release (v1.x: UniProtKB 2026_02). Updates require a new release.
- **Not a prediction service.** The API exposes the frozen release; it does
  not re-score or re-classify arbitrary user sequences.
- **Not yet an environmental catalog.** The MGnify pilot is deliberately
  isolated from membership; the WS8 expansion memo *proposes* a marine-first
  expansion with confidence tiers — that policy is **not applied** in v1.3.0
  and belongs to a future release decision.
- **Not currently rebuildable from source.** The builder code and preserved
  inputs are absent from this repository (see
  `docs/LEGACY_AND_MISSING_COMPONENTS.md`). The frozen releases are the
  authoritative artifacts; claims of reproducibility apply to *validation of
  the shipped artifacts*, not to re-execution of the build.

## Boundary policies that define the science

1. **Membership authority:** `membership.membership_status` — never the
   deprecated `module` column.
2. **Decoys stay visible but excluded:** HSP30 and other decoy/rejected
   records remain in the DB for benchmark/audit, excluded from every active
   view.
3. **Environmental isolation:** pilot records have no membership rows and
   never appear in active views.
4. **Frozen thresholds:** validation never retunes; new evidence triggers new
   releases, not silent edits.
