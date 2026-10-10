# MR_RT_003 reference package

Reference tree + alignment + HMMs + clade definitions backing MicroRhodoDB v1.5.0
(`clade.tree_id = 'MR_RT_003'`, `placement.tree_id = 'MR_RT_003'`). Supersedes MR_RT_001
(MSA lost; see `data/README.md`) and MR_RT_002 (placement-only, no refpkg). Built to answer
referee comments on model mismatch, rooting, excluded clades, and reproducibility.

## Composition (472 tips)

| tip_role | n | meaning |
|---|---|---|
| cl0.6_representative | 394 | MMseqs2 cluster (60% identity) representatives spanning the Type-I corpus |
| anchor_characterized | 57 | experimentally characterized (Tier A/E1) proteins, forced in regardless of clustering |
| outgroup_heliorhodopsin | 15 | PF18761 heliorhodopsins; root/outgroup for ingroup rooting |
| seed | 4 | curated family seeds |
| boundary_schizorhodopsin | 2 | schizorhodopsin exemplars (boundary family, referee comment 2) |

Full per-tip metadata: `tips.tsv`, `tips_annot.tsv` (role, v1.4 subfamily/function, helix-C motif,
taxonomy, organism).

## Build pipeline

1. **Alignment** (`alignment/`): MAFFT L-INS-i (`MR_RT_003.msa.faa`) -> ClipKIT `kpic-gappy`
   trimming, 453 of 773 columns retained (`MR_RT_003.trim.faa`, log in `.trim.faa.log`).
   `ref_for_placement.trim.faa` is the exact alignment EPA-ng places queries against.
2. **Model selection + tree search** (`tree/`): IQ-TREE 2.3.6, ModelFinder (BIC) selected
   **Q.pfam+F+R9** (replaces the v1.4 LG+G4 tree model / LG+G4 placement-model mismatch flagged
   by referee comment 4 -- the v1.5 placement primary model is the same PROTGTR string as the
   tree model). UFBoot2 (1000) + SH-aLRT (1000). **3 independent ML searches** from different
   random seeds (`run1` seed 1501, `run2` seed 1502, `run3` seed 1503); `run1` is the release
   tree (best log-likelihood -188453.09; `run2` -188456.19, `run3` -188453.89 -- statistically
   indistinguishable). Pairwise RF distance in `ml3.rfdist` (raw bipartition count out of a
   possible 938 for 472 unrooted taxa: run1-run2 114 (0.122 normalized), run1-run3 126 (0.134),
   run2-run3 72 (0.077)).
3. **Rooting**: outgroup (heliorhodopsin clade) is monophyletic in every one of the 3 searches.
   Midpoint rooting gives identical level-1/level-2 clades to outgroup rooting on all 3 trees
   (referee comment 4's rooting-choice concern: the choice does not change the clades).
   `MR_RT_003.rooted.treefile` is the outgroup-rooted release tree (= `run1.treefile` rerooted).
4. **Clade definitions** (`clades/`): top-down rule -- a node is a clade if UFBoot>=95 & SH-aLRT>=80
   and holds 5-100 ingroup tips (level 1, `MR_CLD3_0xx`) or 3-40 tips nested inside a level-1 clade
   or on the backbone (level 2, `MR_CLD3_0xx.0y`); backbone groups below the level-1 floor that are
   still well-supported are kept as `MR_CLD3_B0x`. `MR_CLD3_clades.tsv` / `_subclades.tsv` / `_tips.tsv`
   are the level-1/level-2/tip-membership tables at the primary setting.
5. **Robustness** (`clades/clade_robustness_grid.tsv`, `clade_stability_primary_replicates.tsv`):
   - `clade_robustness_grid.tsv`: single-tree (`run1`) parameter grid over rooting x min/max size x
     UFBoot/SH-aLRT thresholds, scored against the primary setting (ARI, median best-Jaccard).
   - `clade_robustness_grid_replicates.tsv` / `clade_stability_primary_replicates.tsv`: the same
     grid run jointly across `run1`+`run2`+`run3`+midpoint rooting. At the primary setting,
     cross-replicate ARI = 0.921, median best-Jaccard = 1.0. Per level-1 clade (`clade_stability_
     primary_replicates.tsv`, mapped to clade IDs): **10/17 clades are Jaccard=1.0 in both other
     seeds and under midpoint rooting** (001-005, 007-009, 014, 015). **7/17 show instability in
     at least one replicate**, mostly small clades at the 5-9 tip floor (006, 010, 011, 012, 013,
     016); notably **017 ("Fungal rhodopsins", 100 tips, at the max-size ceiling) drops to
     Jaccard 0.52 in one of two replicates** -- disclosed alongside its thin 3-E1 functional
     consensus basis (see `clade_function_consensus.tsv` in the build inputs, not duplicated here).
6. **Placement models** (`placement_models/`): EPA-ng was run three times against the fixed
   MR_RT_003 topology+alignment with (a) the tree's own model string, Q.pfam+F+R9 (primary), and
   two sensitivity models, (b) LG+G4, (c) LG+R4 -- `model_*.txt` are the exact RAxML-style model
   strings passed to `--evaluate`/placement, `eval_*.log` are the per-model fit logs.
7. **HMMs** (`hmm/`): PF01036.25 (Bacteriorhodopsin, Type-I) and PF18761.8 (Heliorhodopsin),
   used for domain scoring, retinal match-state (210) calls, and the trimmed-alignment coordinate
   system shared with placement.

## Using this package

- To re-place a new query sequence: align/trim it consistently with `alignment/ref_for_placement.
  trim.faa` (same HMM coordinate frame), then run EPA-ng against `tree/run1.treefile` +
  `alignment/ref_for_placement.trim.faa` with `placement_models/model_Q_pfam_F_R9.txt`.
- To re-test clade robustness on a new tree search: `pipeline/v150/define_clades.py grid
  <newtree> tips_annot.tsv <outdir>` and compare to `clade_stability_primary_replicates.tsv`.
- `run2`/`run3` are provided for independent reproduction checks only; they are not used anywhere
  in the v1.5.0 database build (which reads `run1.treefile`/`run1.iqtree` exclusively).

## Integrity

Every file in this directory is checksummed in `SHA256SUMS` (paths relative to this directory).
Verify with `sha256sum -c SHA256SUMS` from inside `refpkg/MR_RT_003/`.
