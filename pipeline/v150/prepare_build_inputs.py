#!/usr/bin/env python
"""Assemble build-ready inputs + config.json for build_v150.py from the v1.5 work products.

Usage: prepare_build_inputs.py WORK_DIR SHARED_DIR REPO_DIR BUILD_DIR CLADE_NAMES_TSV
  WORK_DIR    /workspace/v150 (work products)
  SHARED_DIR  /mnt/shared-workspace/v150 (frozen external set, pubverify, charset)
  REPO_DIR    MicroRhodoDB repo root (v1.4.0 release DB)
  BUILD_DIR   output dir for build inputs, config.json and the DBs
  CLADE_NAMES clade_id, proposed_name/name, naming_basis (curator-approved names at release)
"""
import sys, os, json, hashlib, datetime
import pandas as pd


def md5(fn):
    return hashlib.md5(open(fn, "rb").read()).hexdigest()


def main():
    W, S, REPO, B, NAMES = sys.argv[1:6]
    os.makedirs(B, exist_ok=True)
    names = pd.read_csv(NAMES, sep="\t")
    if "name" not in names:
        names = names.rename(columns={"proposed_name": "name"})
    cl = pd.read_csv(f"{W}/clades/MR_CLD3_clades.tsv", sep="\t")
    sub = pd.read_csv(f"{W}/clades/MR_CLD3_subclades.tsv", sep="\t")
    cf = pd.read_csv(f"{W}/clades/clade_function_consensus.tsv", sep="\t")
    rc = pd.read_csv(f"{W}/clades/record_clades.tsv", sep="\t")
    tips = pd.read_csv(f"{W}/clades/MR_CLD3_tips.tsv", sep="\t")

    l1 = cl.assign(level=1, parent_clade_id="")
    l2 = sub.rename(columns={"subclade_id": "clade_id", "parent_clade": "parent_clade_id"}).assign(level=2)
    l2["parent_clade_id"] = l2.parent_clade_id.fillna("")
    l2.loc[l2.clade_id.str.contains("_B"), "level"] = 1   # backbone groups are top-level named groups
    keep = ["clade_id", "level", "parent_clade_id", "n_tips", "ufboot", "sh_alrt", "dominant_subfamily_v14",
            "dominant_helixC_motif", "dominant_domain", "dominant_phylum", "e1_classes"]
    C = pd.concat([l1[[c for c in keep if c in l1]], l2[[c for c in keep if c in l2]]], ignore_index=True)
    C = C.rename(columns={"e1_classes": "e1_classes_tips"})
    C = C.merge(names[["clade_id", "name", "naming_basis"]], on="clade_id", how="left")
    cfx = cf.rename(columns={"group_id": "clade_id"}).drop(columns=["level"]).drop_duplicates("clade_id")
    C = C.merge(cfx.rename(columns={"n_records": "n_records_assigned", "clade_function": "e1_function_consensus",
                                    "E1_classes": "e1_classes_records"}), on="clade_id", how="left")
    C["tree_id"] = "MR_RT_003"
    C["scheme"] = "MR_CLD3"
    # cross-replicate robustness (3 independent IQ-TREE searches, seeds 1501-1503): per-primary-clade best-match
    # Jaccard vs each replicate + midpoint rooting. Only computed for the 17 level-1/PRIMARY-setting clades
    # (min_size=5..100); backbone groups (_B01/_B02, 4 tips) are below that floor and left NaN here.
    stab_fn = f"{W}/clades/clade_stability_primary_replicates.tsv"
    if os.path.exists(stab_fn):
        st = pd.read_csv(stab_fn, sep="\t").rename(columns={
            "jaccard_run1.treefile": "jaccard_run1", "jaccard_run2.treefile": "jaccard_run2",
            "jaccard_run3.treefile": "jaccard_run3", "jaccard_midpoint": "jaccard_midpoint_rooting"})
        st["min_cross_replicate_jaccard"] = st[["jaccard_run2", "jaccard_run3", "jaccard_midpoint_rooting"]].min(axis=1)
        C = C.merge(st[["clade_id", "jaccard_run2", "jaccard_run3", "jaccard_midpoint_rooting",
                        "min_cross_replicate_jaccard"]], on="clade_id", how="left")
    C.to_csv(f"{B}/clade_v150.tsv", sep="\t", index=False)

    # route-3 (checkpoint-approved: annotation only, no status change). 267 typeI_candidate* records with
    # an intact retinal K at match state 210 AND a QC-ok primary-model placement. strict_subset_154 flags the
    # stricter rule (non-truncated architecture, placement covers TM7, score>=0.70) for downstream filtering.
    r3_fn = f"{W}/clades/route3_proposal.tsv"
    if os.path.exists(r3_fn):
        r3 = pd.read_csv(r3_fn, sep="\t")
        r3["placement_supports_membership"] = True
        r3["strict_subset_154"] = ((r3.architecture_class != "truncated_core") & r3.covers_TM7.astype(bool)
                                    & (r3.membership_score >= 0.70))
        r3["basis"] = "route3 (checkpoint-approved annotation-only): K observed at match state 210 + QC-ok placement on MR_RT_003"
        r3.to_csv(f"{B}/route3_v150.tsv", sep="\t", index=False)

    rec = rc.rename(columns={"e1_class": "e1_class_this_record"}).fillna({"clade_id": "", "subclade_id": ""})
    rec.to_csv(f"{B}/record_clade_v150.tsv", sep="\t", index=False)
    tips[["source_acc", "clade_id", "subclade_id"]].assign(tree_id="MR_RT_003").to_csv(f"{B}/clade_tip_v150.tsv", sep="\t", index=False)

    # robustness: run1 grid (+ replicate grid when present)
    grids = [pd.read_csv(f"{W}/clades/clade_robustness_grid.tsv", sep="\t")]
    if os.path.exists(f"{W}/clades/clade_robustness_grid_replicates.tsv"):
        grids.append(pd.read_csv(f"{W}/clades/clade_robustness_grid_replicates.tsv", sep="\t"))
    pd.concat(grids, ignore_index=True).drop_duplicates().to_csv(f"{B}/clade_robustness_v150.tsv", sep="\t", index=False)

    tf = f"{W}/tree/run1.treefile"
    logl = None
    for line in open(f"{W}/tree/run1.iqtree"):
        if line.startswith("Log-likelihood of the tree:"):
            logl = float(line.split(":")[1].split()[0])
    rt = dict(tree_id="MR_RT_003", n_tips=472, method="IQ-TREE 2.3.6; UFBoot2 1000 + SH-aLRT 1000; 3 independent searches (seeds 1501-1503)",
              model="Q.pfam+F+R9", log_likelihood=logl, treefile_md5=md5(tf), unrooted=1, status="canonical_release",
              note="472 tips: 394 cl0.6 representatives, 57 anchors, 4 seeds, 15 heliorhodopsin outgroup, 2 schizorhodopsins. "
                   "MAFFT L-INS-i, ClipKIT kpic-gappy (453 of 773 columns). Biological root = heliorhodopsin outgroup "
                   "(midpoint rooting gives identical clades). EPA-ng placement uses the same Q.pfam+F+R9 model; "
                   "tree_edge.edge_id = jplace edge_num. Reference package archived in refpkg/MR_RT_003/.")
    cfg = dict(
        v140_db=f"{REPO}/releases/v1.4.0/db/microrhododb_v1.4.0.sqlite",
        out_db=f"{B}/microrhododb_v1.5.0.sqlite", out_env_db=f"{B}/microrhododb_v1.5.0_env_pilot.sqlite",
        status_definition=f"{W}/wp2/out/status_definition.tsv", membership=f"{W}/wp2/out/membership_v150.tsv",
        mr_rt_003=rt, mr_rt_003_nodes=f"{W}/build/mr_rt_003_nodes.tsv", mr_rt_003_edges=f"{W}/build/mr_rt_003_edges.tsv",
        clades=f"{B}/clade_v150.tsv", clade_tips=f"{B}/clade_tip_v150.tsv", record_clade=f"{B}/record_clade_v150.tsv",
        route3=f"{B}/route3_v150.tsv",
        placements=f"{W}/place/mr_rt_003_placements_all_models.tsv", primary_model_tag="Q_pfam_F_R9",
        model_sensitivity=f"{W}/place/mr_rt_003_model_sensitivity.tsv", clade_robustness=f"{B}/clade_robustness_v150.tsv",
        clade_crosswalk=f"{W}/clades/clade_crosswalk.tsv",
        function_evidence=f"{W}/wp5_pass2/function_evidence_v150.tsv", characterized=f"{W}/wp5_pass2/characterized_v150.tsv",
        publication=f"{W}/wp5_pass2/publication_v150.tsv", assertion_link=f"{W}/wp5_pass2/assertion_link_v150.tsv",
        motif_benchmark_summary=f"{W}/wp5_pass2/motif_benchmark_summary.tsv", spectral_audit=f"{W}/wp5_pass2/spectral_audit.tsv",
        afdb=f"{W}/ext/afdb_models.tsv", pocket_long=f"{W}/wp6/retinal_pocket_long.tsv",
        pocket_summary=f"{W}/wp6/retinal_pocket_summary.tsv", gtdb=f"{W}/wp6/gtdb_taxonomy.tsv",
        ext_pos=f"{S}/extset/external_positives_new.tsv", ext_neg=f"{S}/extset/external_negatives_new.tsv",
        ext_freeze=f"{S}/extset/FREEZE_SHA256.txt", ext_placement=f"{W}/place/external_set_placement.tsv",
        ext_scores=f"{W}/wp3/ext/out/wp3_external_scores.tsv",
        ext_metrics=f"{W}/wp3/ext/out/wp3_external_metrics.tsv", ext_ops=f"{W}/wp3/ext/out/wp3_external_operating_points.tsv",
        ext_strata=f"{W}/wp3/ext/out/wp3_external_strata.tsv",
        hold_metrics=f"{W}/wp3/wp3_holdout_metrics.tsv", hold_ops=f"{W}/wp3/wp3_holdout_operating_points.tsv",
        spotcheck_decisions=f"{REPO}/curation/spotcheck_decisions_v150.tsv",
        field_corrections=f"{REPO}/curation/field_corrections_v150.tsv",
        release_metadata={"version": "1.5.0", "release_date": datetime.date.today().isoformat(),
                          "database_release": "1.5.0", "schema_revision": "v150.1",
                          "base_release": "1.4.0 (immutable; opened read-only and copied; superseded tables kept as legacy_*)",
                          "curator_signoff": "65/65 spot-check rows signed by CongJian Li (curation/spotcheck_decisions_v150.tsv); "
                                             "E1 policy 'replace or downgrade'",
                          "tentative_clade": "v_master.tentative_clade_id/name: primary-model placement with clade_call=assigned "
                                             "but pendant QC failed (clade_call_qc=distant_assigned); distant placement, low "
                                             "confidence; not counted in clade coverage",
                          "license": "CC BY 4.0 (data); MIT (code)", "scope": "UniProt-derived Type-I microbial rhodopsin corpus",
                          "n_protein_records": "5466", "reference_tree": "MR_RT_003", "clade_scheme": "MR_CLD3",
                          "status_vocabulary": "member/candidate/boundary/outgroup/rejected (see status_definition); v1.4 names in membership.alias_v14 (deprecated, removed in 1.6.0)",
                          "external_validation_freeze_sha256": open(f"{S}/extset/FREEZE_SHA256.txt").read().split()[0],
                          "environmental_layer": "microrhododb_v1.5.0_env_pilot.sqlite (supplementary)",
                          "ci_method": "Wilson score interval for all proportions; bootstrap (cluster-resampled) for AUPRC",
                          "clade_robustness": "MR_RT_003 clades tested across 3 independent IQ-TREE searches (seeds 1501-1503) "
                                              "plus midpoint rooting; cross-replicate ARI 0.921 at the primary setting. "
                                              "Per-clade min Jaccard vs replicates in clade.min_cross_replicate_jaccard "
                                              "(10/17 clades = 1.0 in all replicates; see clade_robustness table for the full grid).",
                          "route3_candidate_support": "Annotation-only layer (267 typeI_candidate* records with retinal K at "
                                                       "match state 210 and a QC-ok MR_RT_003 placement; 154-record strict "
                                                       "subset flagged). Does not change membership_status."},
        provenance_rows=[
            ["tree_node/tree_edge (MR_RT_003)", "MR_RT_003 reference package", "build_tree.sh; export_tree_tables.py", "IQ-TREE ML, Q.pfam+F+R9 (BIC)", "-B 1000 -alrt 1000", "reference_tree"],
            ["placement", "corpus + external + boundary sequences", "place_queries.sh; placement_assign.py", "EPA-ng on fixed MR_RT_003; models Q.pfam+F+R9 (primary), LG+G4, LG+R4", "assigned: clade LWR>=0.9; tentative 0.5-0.9; pendant QC <=1.0", "tree_edge, clade"],
            ["clade", "MR_RT_003 (outgroup-rooted)", "define_clades.py", "level 1: monophyletic, 5-100 tips, UFBoot>=95 & SH-aLRT>=80; level 2: 3-40 tips nested", "", "tree_node"],
            ["record_clade", "clade_tip + placement", "record_clades.py", "tip clade or QC-passed assigned placement; E1 consensus >=2 E1 & >=80% agreement, subclade first", "", "placement, characterized_protein"],
            ["function_evidence", "characterized_protein + record_clade + motifs", "wp5_evidence.py", "E1 experimental; E2 >=90% id & same clade; E3 motif agrees with clade E1 consensus; E4 motif only / curated rule; E5 unresolved", "", "record_clade"],
            ["curator_spotcheck_decision", "65-row WP5 spot-check sheet", "curation_v150.py; wp5_evidence.py --decisions; build_v150.py",
             "signed curator decisions applied: link drop/replace (3 verified replacement publications), field corrections to "
             "tier_a_assertion/tier_a_evidence/characterized_protein (original values in v150_original_values), E1 downgrades",
             "E1 requires >=1 active verified/verified_with_correction link when links exist", "assertion_publication, publication, function_evidence"],
            ["external_validation", "frozen external set v2", "wp3_external.py", "frozen v1.2 scorer; cluster bootstrap", "sha256 freeze", ""],
            ["route3_candidate_support", "record_clade + placement (typeI_candidate* with K at 210)", "route3 analysis + prepare_build_inputs.py",
             "K present at match state 210 AND primary-model (Q.pfam+F+R9) placement clade_call_qc ok; strict_subset_154 = "
             "architecture_class!=truncated_core & covers_TM7 & membership_score>=0.70",
             "checkpoint-approved annotation only; does NOT change membership_status", "record_clade, placement, membership"],
        ])
    json.dump(cfg, open(f"{B}/config.json", "w"), indent=1)
    print("clade rows", len(C), "record_clade", len(rec), "config", f"{B}/config.json")


if __name__ == "__main__":
    main()
