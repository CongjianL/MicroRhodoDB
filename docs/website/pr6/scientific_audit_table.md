| ID | Check | Expected | Observed | Result |
|---|---|---|---|---|
| D0 | official v1.6.0 SQLite sha256 unchanged | `"379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f"` | `"379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f"` | PASS |
| R1 | records-index source_acc rows (no duplicates) | `5466` | `5466` | PASS |
| R2 | source records: export set == v_master set (5,466) | `[5466, true]` | `[5466, true]` | PASS |
| R3 | counted records: export set == v_counted (5,460) | `[5460, true]` | `[5460, true]` | PASS |
| R4 | engineered records: export set == v_engineered (6) | `[6, true]` | `[6, true]` | PASS |
| R5 | MRDB accessions: export set == mrdb_accession (5,299) | `[5299, true]` | `[5299, true]` | PASS |
| R6 | MRDB accessions with more than one source record | `129` | `129` | PASS |
| R7 | records-index vs v_master: per-record equality of 30 shared columns x 5,466 records | `{}` | `{}` | PASS |
| R7b | the only representation change: DB empty strings exported as null (count per column == DB empty-string count) | `{"clade_id": 1312, "subclade_id": 1741}` | `{"subclade_id": 1741, "clade_id": 1312}` | PASS |
| R8 | accessions.json by_source == accession_map (current) | `[5466, true]` | `[5466, true]` | PASS |
| R9 | accessions.json by_mrdb representative == mrdb_accession | `true` | `true` | PASS |
| R10 | record files: one file per MRDB accession; every source exactly once | `[5299, 5466, 1]` | `[5299, 5466, 1]` | PASS |
| R11 | record files vs v_master (status, evidence, function, clade, subclade, tentative, placement call, clade source) | `{}` | `{}` | PASS |
| R12 | E1 counted / total | `[88, 91]` | `[88, 91]` | PASS |
| R13 | members + candidates (all source records, status_definition) / confident clade state | `[4468, 3821]` | `[4468, 3821]` | PASS |
| R14 | MR_CLD3_017 source records (v_master.clade_id) / tentative | `[1646, 597]` | `[1646, 597]` | PASS |
| S1 | protein_pdb links / distinct PDB entries / records with PDB | `[472, 438, 66]` | `[472, 438, 66]` | PASS |
| S2 | structures-index PDB entries == protein_pdb distinct entries | `true` | `true` | PASS |
| S3 | structures-index (record, PDB) links == protein_pdb | `true` | `true` | PASS |
| S4 | records-index n_pdb and pdb_ids == protein_pdb per record | `0` | `0` | PASS |
| S5 | AlphaFold DB models (has_afdb) == v_master.afdb_model_id not null (4,397) | `[4397, true]` | `[4397, true]` | PASS |
| T1 | web rooted treefile and run1.treefile byte-identical to refpkg/MR_RT_003 | `[true, true]` | `[true, true]` | PASS |
| T2 | tips: 472 in rooted and run1, identical sets, no duplicates | `[472, 472, true]` | `[472, 472, true]` | PASS |
| T3 | tips == DB tree_node tips (MR_RT_003) | `true` | `true` | PASS |
| T4 | topology: non-trivial bipartitions of rooted == run1 (rerooting preserves splits) | `[true, 469]` | `[true, 469]` | PASS |
| T5 | explorer internal nodes == rooted internal nodes (471 = 470 unrooted internal nodes + root) | `471` | `471` | PASS |
| T6 | explorer nodes map to the same tip span (first, last, n) as the parsed rooted tree | `0` | `0` | PASS |
| T7 | displayed support == IQ-TREE run1 SH-aLRT/UFBoot label of the same bipartition (all displayed nodes) | `[]` | `[]` | PASS |
| T8 | nodes with displayed support (469 non-root bipartitions; root split shown once) | `469` | `469` | PASS |
| T9 | rooted-file labels attached to a different bipartition after rerooting (audit only, not displayed) | `17` | `17` | PASS |
| T10 | outgroup: 15 heliorhodopsin tips form one root child | `[15, true]` | `[15, true]` | PASS |
| T11 | tip roles (394 cl0.6 reps, 57 anchors, 4 seeds, 15 outgroup, 2 schizorhodopsins) | `{"cl0.6_representative": 394, "anchor_characterized": 57, "seed": 4, "outgroup_h` | `{"cl0.6_representative": 394, "anchor_characterized": 57, "outgroup_heliorhodops` | PASS |
| T12 | DB clades: 19 level-1 groups (17 clades + 2 backbone groups) and 30 subclades | `[19, 30]` | `[19, 30]` | PASS |
| T13 | clades.json clade ids == DB clade ids | `true` | `true` | PASS |
| T14 | clade_tip sizes == clade.n_tips (49 groups) | `[]` | `[]` | PASS |
| T15 | every clade / subclade tip set is one node of the rooted tree (monophyletic) | `[]` | `[]` | PASS |
| T16 | DB clade support == run1 label of the clade bipartition, except the documented MR_CLD3_017 legacy value | `[["MR_CLD3_017", 100.0, 100.0, "50.3/72"]]` | `[["MR_CLD3_017", 100.0, 100.0, "50.3/72"]]` | PASS |
| T16b | clades.json support_audit (run1 label, thresholds SH-aLRT >= 80 and UFBoot >= 95, DB match flag) recomputed for all 49 groups | `[]` | `[]` | PASS |
| T16c | groups failing the corrected support thresholds (shown with the website warning) | `["MR_CLD3_017"]` | `["MR_CLD3_017"]` | PASS |
| T17 | explorer clade/subclade MRCA nodes == parsed MRCA of DB clade_tip sets | `true` | `true` | PASS |
| T18 | explorer tip group == clade_tip.clade_id; 'backbone_unassigned' tips == explorer unclustered_backbone; outgroup has no group | `[true, 27, true]` | `[true, 27, true]` | PASS |
| T19 | edge_map: every DB tree_edge maps to rooted node(s) with the same bipartition | `[941, []]` | `[941, []]` | PASS |
| P1 | current placements (MR_RT_003, is_current = 1) | `4996` | `4996` | PASS |
| P2 | placement objects in record files: same source set as current DB placements | `[4996, true]` | `[4996, true]` | PASS |
| P3 | per-record placement fields == DB placement row (all fields, all current placements) | `{}` | `{}` | PASS |
| P4 | placement clade_call_qc counts == explorer meta placement_status_counts | `{"assigned": 3617, "distant_assigned": 720, "distant_tentative": 4, "outgroup_he` | `{"assigned": 3617, "distant_assigned": 720, "distant_tentative": 4, "outgroup_he` | PASS |
| P5 | placement best_edge exists in edge_map (placement drawn on a real reference branch) | `0` | `0` | PASS |
