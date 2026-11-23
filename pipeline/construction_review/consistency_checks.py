#!/usr/bin/env python
"""Cross-layer consistency checks that the release tests do not cover.

1. placement_vs_membership: Type-I members and candidates whose current MR_RT_003 placement (Q.pfam+F+R9) is
   `outgroup_heliorhodopsin`. The membership scorer already rejects helio-primary sequences, so for these records
   the tree and the scorer disagree. Each row carries the two model-sensitivity placements (LG+G4, LG+R4) and the
   MR_RT_002 clade, to separate a model artefact (the models disagree) from a sampling gap in MR_RT_003 (all
   MR_RT_003 models agree, MR_RT_002 placed the record in a Type-I clade).
2. e2_motif_mismatch: E2 calls whose helix-C motif differs from the motif of their E1 reference. At >= 90% identity
   a changed helix-C residue is the case in which function transfer is least safe.

Usage: python pipeline/construction_review/consistency_checks.py <release db> <outdir>
"""
import os
import sqlite3
import sys

import pandas as pd


def placement_vs_membership(con):
    df = pd.read_sql("""
        SELECT m.source_acc, m.mrdb_acc, m.membership_status, m.membership_score, m.retinal_site_residue,
               m.architecture_class, q.hmm_cov, f.evidence_level, f.func_class, COALESCE(f.is_engineered, 0) AS is_engineered,
               p.protein_name, p.organism, p.tax_domain,
               pl.best_lwr, pl.best_pendant, pl.lwr_weighted_pendant, pl.placement_qc
        FROM membership m
        JOIN record_clade rc USING(source_acc)
        JOIN placement pl ON pl.source_acc = m.source_acc AND pl.tree_id = 'MR_RT_003' AND pl.is_current = 1
        JOIN protein p ON p.source_acc = m.source_acc
        JOIN function_evidence f ON f.source_acc = m.source_acc
        LEFT JOIN qc_feature q ON q.source_acc = m.source_acc
        WHERE m.membership_status LIKE 'typeI_%' AND rc.clade_call = 'outgroup_heliorhodopsin'
        ORDER BY m.membership_status, m.membership_score DESC""", con)
    alt = pd.read_sql("""SELECT source_acc, model_tag, clade_call, clade_id FROM placement
                         WHERE tree_id = 'MR_RT_003' AND model_tag IN ('LG_G4', 'LG_R4')""", con)
    for tag in ("LG_G4", "LG_R4"):
        a = alt[alt.model_tag == tag].set_index("source_acc")
        df[f"call_{tag}"] = df.source_acc.map(a.clade_call)
    rt2 = pd.read_sql("SELECT source_acc, clade_id FROM placement WHERE tree_id = 'MR_RT_002'", con)
    df["mr_rt_002_clade"] = df.source_acc.map(rt2.drop_duplicates("source_acc").set_index("source_acc").clade_id)
    models_agree = df.call_LG_G4.eq("outgroup_heliorhodopsin") & df.call_LG_R4.eq("outgroup_heliorhodopsin")
    df["diagnosis"] = [
        "model_sensitive" if not ok else
        "mr_rt_003_sampling_gap" if isinstance(c2, str) and c2 not in ("", "outgroup_heliorhodopsin") else
        "consistent_outgroup_placement"
        for ok, c2 in zip(models_agree, df.mr_rt_002_clade)]
    return df


def e2_motif_mismatch(con):
    return pd.read_sql("""
        SELECT q.source_acc, q.func_class, q.helixC_motif, q.motif_class, q.e2_ref, ROUND(q.e2_identity, 3) AS e2_identity,
               r.helixC_motif AS ref_helixC_motif, r.func_class AS ref_func_class, q.call_conflict,
               COALESCE(q.is_engineered, 0) AS is_engineered
        FROM function_evidence q JOIN function_evidence r ON r.source_acc = q.e2_ref
        WHERE q.evidence_level = 'E2' AND q.helixC_motif IS NOT r.helixC_motif
        ORDER BY is_engineered, q.source_acc""", con)


def main():
    db, outdir = sys.argv[1:3]
    os.makedirs(outdir, exist_ok=True)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    pm = placement_vs_membership(con)
    em = e2_motif_mismatch(con)
    con.close()
    pm.to_csv(f"{outdir}/placement_vs_membership.tsv", sep="\t", index=False)
    em.to_csv(f"{outdir}/e2_motif_mismatch.tsv", sep="\t", index=False)
    print(f"placement_vs_membership: {len(pm)} Type-I records placed in the heliorhodopsin outgroup")
    print(pm.groupby(["membership_status", "diagnosis"]).size().to_string())
    print(pm.groupby("placement_qc").size().to_string())
    print(f"\ne2_motif_mismatch: {len(em)} E2 calls ({int((em.is_engineered == 0).sum())} non-engineered)")
    print(em.to_string(index=False))


if __name__ == "__main__":
    main()
