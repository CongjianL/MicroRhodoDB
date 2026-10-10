"""Scorer validation summary for v1.6.0 (R-V1, R-V3, R-M7, R-M10).

The membership scorer is unchanged from v1.5.0. This script does not re-score anything: it collects the
already-computed validation results into one long table, in the order the v1.6.0 report presents them:

  A  external set (frozen, 21 positives / 345 negatives): full_gated vs the two-rule baseline B4b_ga_retK
     and the six single-axis ablations                          <- release DB, external_validation_metric
  B  clade-root holdout (the only internal regime without >=50% identity leakage)
                                                                   <- release DB, holdout_metric / _operating_point
  C  holdout leakage by regime                                    <- audit_v150/auditA_holdout_contamination_summary.tsv
  D  identity-stratified external results; recommended threshold 0.70
                                                                   <- audit_v150/auditA_identity_filtered_*.tsv
  E  >=90%-identity external stratum reported separately (R-M7)   <- audit_v150/auditA_per_record_identity.tsv
  F  per-family recall on the external set                       <- release DB, external_validation_stratum
  G  InterPro retrieval: date, API count, retrieved count (R-M10) <- audit_v150/auditC_interpro_*.txt/tsv

usage: python scorer_validation_v160.py <release.sqlite> <curation/v160/audit_v150> <out.tsv>
"""
import os
import sqlite3
import sys

import pandas as pd

COLS = ["section", "set", "method", "threshold", "metric", "k", "n", "value", "ci_lo", "ci_hi", "source"]
HEAD_METHODS = ["full_gated", "B4b_ga_retK", "abl_e_domain", "abl_e_coverage", "abl_e_retinal", "abl_e_margin",
                "abl_e_homology", "abl_e_topology", "full_raw", "B2b_margin"]


def main(db, audit, out):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = []

    def add(**kw):
        rows.append({c: kw.get(c, "") for c in COLS})

    # A: external AUPRC, score vs rule baseline vs ablations
    m = pd.read_sql("SELECT * FROM external_validation_metric WHERE \"set\"='all'", con)
    for meth in HEAD_METHODS:
        r = m[m.method == meth].iloc[0]
        add(section="A_external_auprc", set=f"all ({r.n_pos}/{r.n_neg})", method=meth, metric="auprc",
            n=f"{r.n_pos}+{r.n_neg}", value=round(r.auprc, 3), ci_lo=round(r.auprc_lo, 3), ci_hi=round(r.auprc_hi, 3),
            source="external_validation_metric")
    # B: clade-root holdout
    h = pd.read_sql("SELECT * FROM holdout_metric WHERE regime='reference_clade_root'", con)
    for meth in HEAD_METHODS:
        r = h[h.method == meth].iloc[0]
        add(section="B_clade_root_auprc", set=f"reference_clade_root ({r.n_pos}/{r.n_neg})", method=meth,
            metric="auprc", n=f"{r.n_pos}+{r.n_neg}", value=round(r.auprc, 3), ci_lo=round(r.auprc_lo, 3),
            ci_hi=round(r.auprc_hi, 3), source="holdout_metric")
    op = pd.read_sql("SELECT * FROM holdout_operating_point WHERE regime='reference_clade_root' "
                     "AND method IN ('full_gated','B4b_ga_retK')", con)
    for r in op.itertuples():
        thr = "rule" if pd.isna(r.threshold) else f"{r.threshold:.2f}"
        add(section="B_clade_root_operating_point", set="reference_clade_root", method=r.method, threshold=thr,
            metric=r.metric, k=r.k, n=r.n, value=round(r.value, 3), ci_lo=round(r.ci_lo, 3), ci_hi=round(r.ci_hi, 3),
            source="holdout_operating_point")
    # C: leakage by regime
    c = pd.read_csv(os.path.join(audit, "auditA_holdout_contamination_summary.tsv"), sep="\t")
    for r in c.to_dict("records"):
        add(section="C_holdout_leakage", set=r["regime"], method="heldout positives with a training positive >=90% id",
            metric="trainpos_id>=90", k=r["trainpos_id>=90"], n=r["n_heldout"], source="auditA_holdout_contamination_summary")
        add(section="C_holdout_leakage", set=r["regime"], method="heldout positives with a training positive >=50% id",
            metric="trainpos_id>=50", k=r["trainpos_id>=50"], n=r["n_heldout"], source="auditA_holdout_contamination_summary")
    # D: identity-stratified external
    im = pd.read_csv(os.path.join(audit, "auditA_identity_filtered_metrics.tsv"), sep="\t")
    io = pd.read_csv(os.path.join(audit, "auditA_identity_filtered_operating_points.tsv"), sep="\t")
    for f in ["none", "any<90", "any<70", "any<50"]:
        for meth in ["full_gated", "B4b_ga_retK", "B3_nn_bits"]:
            r = im[(im["filter"] == f) & (im.method == meth)].iloc[0]
            add(section="D_identity_filtered_auprc", set=f"{f} ({r.n_pos}/{r.n_neg})", method=meth, metric="auprc",
                n=f"{r.n_pos}+{r.n_neg}", value=round(r.auprc, 3), ci_lo=round(r.auprc_lo, 3),
                ci_hi=round(r.auprc_hi, 3), source="auditA_identity_filtered_metrics")
        for thr in [0.70, 0.86, 0.90]:
            for met in ["sensitivity", "specificity"]:
                r = io[(io["filter"] == f) & (io.method == "full_gated") & (io.threshold.round(2) == thr)
                       & (io.metric == met)].iloc[0]
                add(section="D_identity_filtered_operating_point", set=f, method="full_gated", threshold=f"{thr:.2f}",
                    metric=met, k=r.k, n=r.n, value=round(r.value, 3), ci_lo=round(r.ci_lo, 3),
                    ci_hi=round(r.ci_hi, 3), source="auditA_identity_filtered_operating_points")
    # E: >=90% identity stratum (identity to any reference set: seeds, benchmark, corpus, tree tips, dev)
    pr = pd.read_csv(os.path.join(audit, "auditA_per_record_identity.tsv"), sep="\t")
    hi = pr[pr.id_any.fillna(0) >= 90]
    add(section="E_identity_ge90_stratum", set="id_any>=90", method="count", metric="positives",
        k=int(hi.y.sum()), n=int(pr.y.sum()), source="auditA_per_record_identity")
    add(section="E_identity_ge90_stratum", set="id_any>=90", method="count", metric="negatives",
        k=int((hi.y == 0).sum()), n=int((pr.y == 0).sum()), source="auditA_per_record_identity")
    for r in hi[hi.y == 1].sort_values("source_acc").itertuples():
        add(section="E_identity_ge90_stratum", set="id_any>=90 positive", method="full_gated",
            metric=f"{r.source_acc} ({r.stratum}; nearest corpus {r.nn_corpus} at {r.id_corpus:.1f}%)",
            value=r.full_gated, source="auditA_per_record_identity")
    for thr in [0.70, 0.86, 0.90]:
        k = int(((hi.y == 1) & (hi.full_gated >= thr)).sum())
        add(section="E_identity_ge90_stratum", set="id_any>=90", method="full_gated", threshold=f"{thr:.2f}",
            metric="sensitivity", k=k, n=int(hi.y.sum()), value=round(k / max(1, hi.y.sum()), 3),
            source="auditA_per_record_identity")
        k = int(((hi.y == 0) & (hi.full_gated >= thr)).sum())
        add(section="E_identity_ge90_stratum", set="id_any>=90", method="full_gated", threshold=f"{thr:.2f}",
            metric="false_positives", k=k, n=int((hi.y == 0).sum()), source="auditA_per_record_identity")
    # F: per-family recall on the external set
    s = pd.read_sql("SELECT * FROM external_validation_stratum WHERE cls='positive' AND stratum NOT LIKE 'distance%'",
                    con)
    for r in s.itertuples():
        add(section="F_family_recall", set=r.stratum, method="full_gated", threshold=f"{r.threshold:.2f}",
            metric="recall", k=r.k, n=r.n, value=round(r.value, 3), ci_lo=round(r.ci_lo, 3), ci_hi=round(r.ci_hi, 3),
            source="external_validation_stratum")
    # G: InterPro retrieval (counts of retrieved records are the ones used)
    for line in open(os.path.join(audit, "auditC_interpro_fetch_log.txt")):
        p = line.split()
        if len(p) == 8:  # "<pfam> API count <n> retrieved <n> <date> <time>"
            when = f"retrieved {p[6]} {p[7]} UTC"
            add(section="G_interpro_retrieval", set=p[0], method=when, metric="api_count_field", value=p[3],
                source="auditC_interpro_fetch_log")
            add(section="G_interpro_retrieval", set=p[0], method=when, metric="records_retrieved", value=p[5],
                source="auditC_interpro_fetch_log")
    ov = pd.read_csv(os.path.join(audit, "auditC_interpro_overlap_summary.tsv"), sep="\t")
    for r in ov.itertuples():
        add(section="G_interpro_overlap", set=r.item, metric="n", k=r.n, value=r.pct_of_interpro,
            source="auditC_interpro_overlap_summary")
    pd.DataFrame(rows, columns=COLS).to_csv(out, sep="\t", index=False)
    print(f"scorer validation summary: {len(rows)} rows -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
