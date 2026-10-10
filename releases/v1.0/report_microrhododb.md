# MicroRhodoDB v1.0 — A Standardized, Evidence-Graded Database of Type-I Microbial Rhodopsins

*Build date: 2026-07-30 · Source release: UniProtKB 2026_02 · Project: rhodopsins (CongJian Li)*

> **Naming note.** "MicroRhodoDB" is a working placeholder and is trivially changeable throughout the release (single configuration string). It does not imply any claim of completeness or priority over existing resources.

---

## 1. Scope and design philosophy

MicroRhodoDB v1.0 is a research-grade, reproducible, and extensible catalogue of **Type-I (microbial) rhodopsins** — the retinylidene, seven-transmembrane, light-driven ion pumps, channels, sensors, and enzyme-rhodopsins found across Bacteria, Archaea, microbial eukaryotes, and viruses. **Heliorhodopsins (HeR)** are built and shipped as a **separate companion module**, never folded into the Type-I taxonomy: they share the retinal/7-TM bauplan but are an independent family with inverted membrane topology, and conflating them is a common annotation error the database is explicitly designed to avoid.

Four design commitments distinguish this build:

1. **Evidence-vector membership, not criteria counting.** Family membership is a transparent, benchmark-calibrated continuous score built from an interpretable per-sequence evidence vector (domain signal, core coverage, retinal-binding lysine, Type-I-vs-HeR margin, seed homology, topology). Sequences are graded into `confirmed_type_I / high_confidence_type_I / putative_type_I / rhodopsin_like / ambiguous / rejected`. **Incomplete or conflicting sequences are retained and remain queryable — never force-classified.**
2. **Transparent rules over trained ML.** Classification uses auditable rules over the evidence vector plus phylogenetic placement. However, the **full ML-ready schema is persisted** (per-axis evidence, continuous score, gate booleans), so a supervised classifier can be dropped in later without re-engineering.
3. **Measured vs. predicted, strictly separated.** Spectral λmax values in this release are **tuning-residue proxy predictions**, flagged as such; no measured λmax is imputed (all `lambda_max_measured_nm` are null where unmeasured). Functional class is inferred and flagged; sequence-motif vs. subfamily discordances are surfaced rather than silently resolved.
4. **Phylogeny-first subfamilies, lineage-aware function.** Subfamily identity derives from a reference phylogeny + placement; functional annotation combines lineage-specific ion-transport motif logic with a seed-homology evidence ladder.

The build is fully provenance-tracked across eight recorded stages (QC → membership → redundancy → phylogeny → subfamily → function → structure → database), and **no claim of global completeness is made** — the catalogue reflects UniProtKB 2026_02 retrieved through the seeded, multi-layer search described below.

---

## 2. Contents at a glance

| Quantity | Value |
|---|---|
| Total candidate sequences catalogued | **5,361** |
| Type-I module (membership-retained) | **4,886** |
| Heliorhodopsin companion module | **377** |
| Rejected (retained, queryable) | 98 |
| Sequences with experimental 3-D structure (Type-I) | **65** |
| PDB entries linked | **438** (382 retinal-bound) |
| Predicted structures (ESMFold, this release) | **2** |
| Predicted spectral λmax (proteorhodopsins only) | **138** |
| Measured λmax imputed | **0** (never imputed) |
| Motif↔subfamily discordances surfaced | **859** |
| Release validation checks passed | **10 / 10** |

Membership grades (all 5,361 candidates): confirmed 58 · high-confidence 3,002 · putative 313 · rhodopsin-like 1,370 · ambiguous 143 · rejected 475.

Taxonomic composition: Eukaryota 2,929 · Bacteria 1,149 · Archaea 639 · unclassified 168 · Viruses 1.

See **figure1_database_overview.svg/.png** (six-panel summary: membership, subfamily, taxonomic domain, inferred function, function×domain, spectral tuning) and **figure2_phylogeny.svg/.png** (278-tip reference backbone phylogram, tips coloured by subfamily).

---

## 3. Methods

### 3.1 Seeds, models, and benchmark set

Fifteen curated seeds anchor the build — **12 Type-I** spanning the functional breadth of the family (bacteriorhodopsin P02945, halorhodopsin P0DMH7, sensory rhodopsin I P0DMH8 and II P42196, proteorhodopsin Q9F7P4, xanthorhodopsin Q2S2F8, sodium pump KR2 N0DKS8, chloride-pump NTQ W8VZW3, channelrhodopsins Q8RUT8 and H2EZZ6, *Anabaena* sensory rhodopsin, and the enzyme-rhodopsin/guanylyl-cyclase RhoGC A0A060H1D7) and **3 heliorhodopsin** seeds for the companion module. Family HMMs are Pfam **PF01036** (Bac_rhodopsin, Type-I core) and **PF18761** (Heliorhodopsin).

A **curated benchmark of 261 sequences** (46 positives, 215 negatives) was assembled to calibrate and stress-test membership. Negatives were chosen to break naive classifiers: animal Type-II opsins (60), heliorhodopsins (50), non-opsin 7-TM GPCRs (60), synthetic fragments (20) and frameshifts (20), and — importantly — five **fungal HSP30 proteins** (P25619, P38079, Q12117, O74631, O74870) that share the PF01036 clan fold but carry no retinal Schiff-base lysine. Four "partial positives" (P33969–P33972, historical *Halobacterium* bacterio-/halo-opsin records lacking the C-terminal retinal-lysine region as sequenced) were deliberately kept as positives to test conservative behaviour.

### 3.2 Candidate retrieval

A seeded, multi-layer search over UniProtKB 2026_02 (Pfam-domain retrieval on PF01036 and PF18761, plus seed-homology expansion) yielded **5,361** candidate sequences (4,984 with a PF01036 hit, 377 with PF18761). All downstream annotation is applied to this candidate pool; retrieval breadth, not classification, defines the catalogue boundary.

### 3.3 QC, topology, and domain architecture

Domain signal for every candidate was scored by `hmmsearch` against PF01036 and PF18761 (permissive E=10), yielding per-sequence best domain score, coverage (`hmm_cov`), independent E-values, and the **Type-I-vs-HeR score margin** used later to separate the companion module. Membrane topology was summarised with descriptive Kyte–Doolittle hydrophobicity features only; because rhodopsin TM helices are unusually polar (retinal pocket and proton wire), authoritative 7-TM evidence is taken from **PF01036 domain completeness**, not from raw hydropathy. Domain architecture was classified into `single_domain_core`, `extended`, `truncated_core`, and `fusion` categories, and the retinal-binding lysine was detected against the aligned bacteriorhodopsin K216 position.

### 3.4 Evidence-vector membership and benchmark calibration

Each candidate receives a six-axis evidence vector:

- `e_domain` = sigmoid(PF01036 domain score; x₀=40, k=15)
- `e_coverage` = PF01036 `hmm_cov` (0–1)
- `e_retinal` = retinal Schiff-base lysine present (0/1) — **the defining feature**
- `e_margin` = sigmoid(score_PF01036 − score_PF18761; x₀=0, k=40) — separates the HeR companion
- `e_homology` = best seed identity signal
- `e_topology` = descriptive hydrophobicity consistency

The continuous membership score is a fixed weighted sum:

```
score = 0.28·e_domain + 0.20·e_coverage + 0.25·e_retinal + 0.15·e_margin + 0.10·e_homology + 0.02·e_topology
```

Tier rules (benchmark-calibrated) apply thresholds **confirmed 0.90, high-confidence 0.86, putative 0.70, rhodopsin-like 0.40**, with two hard gates: **confirmed requires a retinal lysine**, and top tiers require a **positive Type-I-vs-HeR margin** (this is the invariant that keeps heliorhodopsins out of the Type-I module). On the curated benchmark the full-evidence model reaches **best-F1 = 0.944 at threshold 0.87** (precision 0.977, recall 0.913, specificity 0.995, FPR 0.005). By contrast, naive Pfam-only membership scores precision 0.329 / specificity 0.563 — it accepts heliorhodopsins, fragments, and HSP30-clan proteins — quantifying why domain membership alone is insufficient. On the benchmark's held-out discrimination test the model separates positives from negatives with **AUC = 0.929** (Mann–Whitney p = 7.0×10⁻¹⁴; positives median 0.944, negatives median 0.789, negatives max 0.834 — no negative reaches the high-confidence threshold).

### 3.5 Redundancy reduction (tiered datasets)

To serve both comprehensive and tractable use-cases, MMseqs2 clustering produced **four nested redundancy tiers** within the Type-I module (4,886 sequences):

| Tier | Identity | Clusters (reps) | Reduction | Mean cluster size |
|---|---|---|---|---|
| exact_nr | ~100% | 4,632 | 5.2% | 1.06 |
| std_90 | 90% | 2,968 | 39.3% | 1.65 |
| intermediate | ~70% | 1,071 | 78.1% | 4.56 |
| backbone | 40% | **298** | 93.9% | 16.4 |

The heliorhodopsin module is clustered independently (38 backbone representatives). The 40% backbone tier is the substrate for phylogeny.

### 3.6 Reference phylogeny and placement

The 298 backbone representatives were aligned by **profile-HMM match-state extraction** against PF01036 (224 raw match columns; full-length MSA is not homology-valid given 55–2,650 aa length heterogeneity, including 104 fusion/extended architectures such as the enzyme-rhodopsin guanylyl-cyclase). After trimAl (`-gt 0.2`, mean gap fraction 0.11) the **core alignment is 219 columns**; 20 core fragments failing the 0.5 occupancy cutoff were dropped, leaving **278 reference tips**.

The reference tree was inferred with **IQ-TREE 3.1.3**, ModelFinder Plus selecting **Q.PFAM+F+R6** by BIC (log-likelihood −101,143.46; total tree length 276.5), with UFBoot 1000 + SH-aLRT 1000 + `--bnni` support. Support is modest and depth-dependent (SH-aLRT median 86.5, UFBoot median 80.0; **30.5% of internal branches are well-supported** at SH-aLRT≥80 & UFBoot≥95), which is expected for superfamily-wide sampling at 40% identity with saturated pairwise distances — shallow clades resolve well, the deep backbone does not. **The tree is therefore presented unrooted**; heliorhodopsins are *not* used as an automatic outgroup. The reference set is strongly **eukaryote-skewed (223 of 278 tips)**, reflecting the current composition of UniProtKB microbial-eukaryote rhodopsin entries rather than true family diversity — an important interpretive caveat.

Remaining sequences were placed onto the fixed reference with **EPA-ng 0.3.8** (LG+G; libpll does not support the Q.PFAM matrix or free-rate categories, and placement on a fixed topology is robust to this approximation). Queries were aligned to the same 219 reference columns; **3,502 sequences were placed** (2,696 std_90 + 806 intermediate; median best likelihood-weight-ratio = 1.0).

### 3.7 Subfamily assignment

Subfamily identity was assigned by combining reference-tree clade membership with EPA-ng placement, giving **2,990 subfamily-assigned sequences** (278 reference tips + 2,712 placed queries). All nine seed representatives recovered their curated subfamily; the chloride-pump NTQ seed (W8VZW3), which collapses with the Na⁺-pump seed at 40% identity, was correctly resolved by its placement. Subfamily distribution (assigned set): sensory rhodopsin II 549 · halorhodopsin 364 · *Anabaena* sensory 360 · bacteriorhodopsin 329 · proteorhodopsin 313 · unclassified Type-I 308 · xanthorhodopsin 283 · channelrhodopsin 267 · enzyme-rhodopsin 69 · sodium pump 60 · sensory rhodopsin I 57 · chloride-pump NTQ 31.

### 3.8 Functional and spectral annotation

Functional class was inferred (and flagged `function_is_inferred = True`) from a combination of subfamily identity and **ion-transport motif logic** at the three functionally decisive positions homologous to bacteriorhodopsin Asp85 / Thr89 / Asp96. The canonical motif rules follow the established microbial-rhodopsin literature: **DTD/DTE → proton pump**, **NDQ → sodium pump** [12], **NTQ → chloride/anion pump** [8, 13], with sensory, channel, and enzyme-rhodopsin classes taken from subfamily-specific signatures and fusion architecture [9, 10, 11]. Inferred Type-I function (n=4,886): proton_pump 2,252 · sensory 966 · unassigned 695 · anion_pump 310 · light_gated_channel 267 · sensory_like 152 · insufficient_data 94 · sodium_pump 81 · enzyme_rhodopsin 69. **859 sequences show a motif↔subfamily discordance** (motif prediction disagreeing with subfamily expectation); these are surfaced in the `function` table rather than silently reconciled.

Spectral λmax was predicted **only for proteorhodopsins**, using the single well-established colour-tuning switch at the position homologous to proteorhodopsin residue 105 (the "spectral tuning switch"): **Leu → green-absorbing (~525 nm), Gln → blue-absorbing (~490 nm)** [1, 2, 5, 7]. This yielded **138 predicted λmax values**, every one flagged `lambda_max_is_predicted = True`; **no measured λmax was imputed**. Colour tuning outside proteorhodopsins (e.g., by retinal-pocket residue volume [7]) is deliberately *not* predicted in v1.0 to avoid over-claiming.

### 3.9 Structural annotation

Experimental structures were mapped from UniProt→PDB cross-references. **65 Type-I sequences carry at least one experimental structure**, linked to **438 PDB entries** (393 X-ray, 38 cryo-EM; **382 retinal-bound**). A 66th structure-bearing candidate, A0A2R4S913 (PDBs 6SU3/6SU4/6UH3/9LJJ), is a **heliorhodopsin** and is correctly excluded from the Type-I module (membership: rejected, score 0.793) — a direct demonstration of the HeR-separation invariant working on a real, structurally characterised sequence. Domain architecture across the Type-I module: single_domain_core 3,631 · extended 679 · truncated_core 365 · fusion 211. Fusion functional types: rhodopsin-cyclase (enzyme rhodopsin) 79 · rhodopsin-histidine kinase 73 · rhodopsin-other 51 · rhodopsin-phosphodiesterase 5 · rhodopsin-response regulator 3.

For two structurally uncharacterised but confidently classified sequences, monomer structures were predicted with **ESMFold (ESMCFold2)**: A0A9X2L7U0 (chloride-pump NTQ, 293 aa, mean pLDDT **93.5**) and B0R633 (sensory rhodopsin I, 239 aa, mean pLDDT **93.7**). Both are high-confidence predictions and are stored as PDBs (`structures/A0A9X2L7U0_esmfold.pdb`, `structures/B0R633_esmfold.pdb`) and flagged as predictions in the `predicted_structure` table.

### 3.10 Relational database, API, and figures

All annotation layers were normalised into a **SQLite database** (`microrhododb_v1.0.sqlite`): a central `protein` table keyed on UniProt accession, 1:1 satellite tables (`qc_feature`, `membership`, `redundancy`, `subfamily`, `function`, `structure`, `predicted_structure`), a many-to-many `protein_pdb` junction to a `pdb_structure` entity, and `seed`/`citation` reference tables (12 tables total), plus a denormalised **`v_master` view** (5,361 rows) that LEFT-JOINs every satellite onto `protein`. The schema passed `PRAGMA integrity_check = ok` with **0 foreign-key violations**. A read-only Python query API (`microrhododb_api.py`, class `MicroRhodoDB`, standard-library `sqlite3` + `pandas`) exposes 15+ query methods; an executable **example notebook** (`example_usage.ipynb`) and a machine-readable **data dictionary** (`data_dictionary.json`, 98 columns) accompany it.

---

## 4. Results and key findings

### 4.1 A benchmark-validated membership boundary that keeps heliorhodopsins out

The central design goal — a defensible Type-I boundary that (a) admits genuine but incomplete Type-I sequences and (b) excludes look-alikes — holds under adversarial testing. At the tier level, all 42 complete Type-I benchmark positives were graded high-confidence, all 50 heliorhodopsins and all 60 animal Type-II opsins and all 60 GPCRs were rejected, and the five HSP30 clan decoys landed in `rhodopsin_like` (not rejected outright, not confirmed — exactly the intended "shares fold, lacks retinal" behaviour). The four partial *Halobacterium* positives, lacking the retinal-lysine region as sequenced, were **conservatively demoted to `rhodopsin_like`** (~0.68) rather than force-classified — a feature, not an error. The single most convincing real-world validation is structural: **A0A2R4S913, a heliorhodopsin with four solved PDB structures, is correctly rejected from the Type-I module**, confirming the score margin does the job it was designed for.

### 4.2 Halorhodopsin clade heterogeneity reveals a placement-vs-chemistry tension

The 364-member halorhodopsin subfamily splits by taxonomy in a biologically informative way. The **archaeal** members (95) are uniformly assigned `anion_pump`, consistent with classical halobacterial chloride pumping. The **eukaryotic** members (268) split — 117 `anion_pump` and 151 `proton_pump` — because the functional classifier assigns by **ion-transport chemistry (the D85/T89/D96-homologous motif)** while phylogenetic placement grouped them by overall sequence similarity. This is a genuine and useful signal: it flags that a subset of sequences placed in the halorhodopsin clade carry proton-pump motifs, i.e. **clade membership and predicted transport function disagree**, and the database surfaces both rather than papering over the conflict. Users should treat eukaryotic "halorhodopsin"-clade proton-motif sequences as a placement artefact to be examined case by case, not as confirmed anion pumps.

### 4.3 Structural coverage is thin and phylogenetically clustered

Only **65 of 4,886** Type-I sequences (1.3%) have experimental structure, and the 438 PDB entries are dominated by a handful of intensively studied models (e.g., bacteriorhodopsin P02945 alone maps to 174 structures, best 1.05 Å, 162 retinal-bound). This scarcity is why (a) function and spectra are annotated from sequence with explicit "predicted/inferred" flags, and (b) two targeted ESMFold predictions were added for well-classified but unsolved subfamilies. The catalogue does not present predictions as measurements anywhere.

---

## 5. Release validation

An automated release gate ran **10 checks, all passing** (`release_validation.json`):

1. **Relational integrity** — 0 FK violations, `integrity_check = ok`.
2. **Known-positive recovery** — all 12 Type-I seeds present, in the Type-I module, none rejected.
3. **Heliorhodopsin separation** — all 3 HeR seeds in the heliorhodopsin module; **0 heliorhodopsins in the Type-I subfamily table**.
4. **Benchmark-negative handling** — leaked negatives (HeRs + HSP30 decoys) all stay below the confirmed/high thresholds; 0 misclassified as confirmed/high.
5. **Cluster expansion** — std_90: 4,886 members → 2,968 clusters → 2,968 representatives (exactly one representative per cluster).
6. **Measured/predicted separation** — 0 measured λmax; 138 predicted λmax all flagged; 0 functions left un-inferred without a flag.
7. **No force-classification** — insufficient_data, unassigned, and ambiguous sequences all retained and queryable.
8. **Discordance surfaced** — 859 motif↔subfamily discordances exposed in the schema.
9. **Benchmark discrimination** — AUC 0.929, Mann–Whitney p = 7.0×10⁻¹⁴; no negative reaches the high-confidence threshold.
10. **Reproducibility** — 8 provenance-documented stages with top-level build provenance.

---

## 6. Limitations

- **No claim of global completeness.** The catalogue reflects UniProtKB 2026_02 retrieved through the seeded, multi-layer search of §3.2. Sequences absent from that snapshot, or too divergent to be retrieved by PF01036/PF18761 + seed homology, are not represented.
- **Spectra and function are predictions, not measurements.** λmax is predicted only for proteorhodopsins via a single tuning switch; functional class is motif/subfamily-inferred. All such fields are flagged; nothing is imputed as measured.
- **Structural coverage is sparse (65/4,886) and biased** toward historically studied models.
- **Deep phylogeny is weakly resolved.** Only ~30.5% of backbone branches are well-supported; the tree is presented **unrooted** and the reference set is **eukaryote-skewed (223/278 tips)**. Subfamily assignments for deep/divergent lineages, and any eukaryotic "halorhodopsin"-clade proton-motif sequences (§4.2), should be treated as hypotheses.
- **Membership uses transparent rules, not a trained classifier.** This is a deliberate v1.0 choice for auditability; the ML-ready schema is in place for a future supervised model.

---

## 7. Reproducibility

Every stage writes structured provenance to `build_provenance.json` (stages: `step4_qc`, `step5_membership`, `step6_redundancy`, `step7_phylogeny`, `step8_subfamily`, `step9_function`, `step10_structure`, `step11_database`), capturing tool versions, parameters, thresholds, and per-step result counts. Key fixed parameters: membership weights and thresholds (§3.4); MMseqs2 tiers at 100/90/70/40% (§3.5); IQ-TREE Q.PFAM+F+R6, seed 12345 (§3.6); EPA-ng LG+G, LWR≥0.5 (§3.6). Source release: **UniProtKB 2026_02**. The database, flat tables (TSV), sequences (FASTA), phylogeny files (Newick/alignment/placements), figures (SVG+PNG), API, example notebook, and data dictionary constitute the complete, self-describing release.

---

## 8. Deliverables

- **Database:** `microrhododb_v1.0.sqlite` (12 tables + `v_master` view)
- **Query API:** `microrhododb_api.py` · **Example notebook:** `example_usage.ipynb` · **Data dictionary:** `data_dictionary.json`
- **Flat tables:** `subfamily_assignments.tsv`, `functional_annotations.tsv`, `structural_annotations.tsv`, `structures_pdb_entries.tsv`
- **Phylogeny:** `typeI_backbone_reference.treefile` (+ `.contree`, `.iqtree`, alignment, tip metadata, `epang_placements.tsv`)
- **Predicted structures:** `A0A9X2L7U0_esmfold.pdb`, `B0R633_esmfold.pdb`
- **Figures:** `figure1_database_overview.svg/.png`, `figure2_phylogeny.svg/.png` (plus per-step figures)
- **Validation & provenance:** `release_validation.json`, `build_provenance.json`
