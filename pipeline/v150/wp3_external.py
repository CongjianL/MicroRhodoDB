#!/usr/bin/env python
"""WP3 - evaluation on the frozen corpus-novel external set (external_new.faa, sha256 in FREEZE_SHA256.txt).

Same methods as wp3_eval.py except:
  * homology axis = production e_homology (seed reference), i.e. the released decision rule;
  * B3 reference = all v1.5 Type-I members of the v1.4.0 corpus (production analogue of nearest-neighbour);
  * bootstrap units = MMseqs2 clusters of the external set (min-seq-id 0.5, cov 0.8), stratified by class.
Strata reported: all, excluding schizorhodopsin positives, positives by distance class, negatives by class.

CLI: wp3_external.py --scores ext_scores.tsv --pos pos.tsv --neg neg.tsv --faa external_new.faa
                     --freeze FREEZE_SHA256.txt --corpus corpus.faa --membership membership_v150.tsv --outdir out
"""
import argparse, hashlib, os, subprocess
import numpy as np, pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score, precision_recall_curve
import wp3_eval as E

MEMBER = {"typeI_member_core", "typeI_member_architecture_supported"}


def main():
    ap = argparse.ArgumentParser()
    for k in ("scores", "pos", "neg", "faa", "freeze", "corpus", "membership", "outdir"):
        ap.add_argument(f"--{k}", required=True)
    ap.add_argument("--nboot", type=int, default=2000)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    h = hashlib.sha256(open(a.faa, "rb").read()).hexdigest()
    assert h == open(a.freeze).read().split()[0], "external set differs from frozen hash"
    pos = pd.read_csv(a.pos, sep="\t").assign(y=1)
    neg = pd.read_csv(a.neg, sep="\t").assign(y=0)
    lab = pd.concat([pos, neg], ignore_index=True).rename(columns={"ext_acc": "source_acc"})
    lab["stratum"] = np.where(lab.y == 1, lab.protein_label, lab.negative_class)
    s = pd.read_csv(a.scores, sep="\t").drop_duplicates("source_acc")
    d = lab[["source_acc", "y", "stratum", "distance_class"]].merge(s, on="source_acc", how="left")
    assert d.membership_score.notna().sum() + d.gate_has_domain.eq(False).sum() >= 0
    d["membership_score"] = d.membership_score.fillna(0.0)
    for c in ("gate_has_domain", "is_helio_primary", "gate_positive_typeI_margin"):
        d[c] = d[c].fillna(False).astype(bool)
    # clusters
    wd = os.path.join(a.outdir, "_mm")
    os.makedirs(wd, exist_ok=True)
    if not os.path.exists(f"{wd}/cl_cluster.tsv"):
        subprocess.run(["mmseqs", "easy-cluster", a.faa, f"{wd}/cl", f"{wd}/tmp", "--min-seq-id", "0.5", "-c", "0.8",
                        "--threads", "8"], check=True, stdout=subprocess.DEVNULL)
    cl = pd.read_csv(f"{wd}/cl_cluster.tsv", sep="\t", header=None, names=["cluster", "source_acc"])
    d = d.merge(cl, on="source_acc", how="left")
    # B3 against corpus Type-I members
    M = pd.read_csv(a.membership, sep="\t")
    mem = set(M.loc[M.membership_status_v150.isin(MEMBER), "source_acc"])
    ref = f"{wd}/members.faa"
    with open(ref, "w") as f:
        for k, v in E.read_fasta(a.corpus).items():
            if k in mem:
                f.write(f">{k}\n{v}\n")
    out = f"{wd}/nn.m8"
    if not os.path.exists(out):
        subprocess.run(["mmseqs", "easy-search", a.faa, ref, out, f"{wd}/tmp2", "-s", "7.5", "--exhaustive-search",
                        "-e", "10", "--threads", "8", "--format-output", "query,target,evalue,bits"],
                       check=True, stdout=subprocess.DEVNULL)
    nn = pd.read_csv(out, sep="\t", header=None, names=["q", "t", "evalue", "bits"])
    g = nn.groupby("q").agg(bits=("bits", "max"), ev=("evalue", "min"))
    d["B3_nn_bits"] = d.source_acc.map(g.bits).fillna(0.0)
    d["B3_nn_bin"] = (d.source_acc.map(g.ev).fillna(np.inf) <= 1e-5).astype(float)
    # methods
    ax = d[list(E.W)].fillna(0.0)
    d["full_raw"] = d.membership_score
    d["full_gated"] = E.gated(d, d.membership_score)
    for k in E.W:
        ww = {j: w for j, w in E.W.items() if j != k}
        d[f"abl_{k}"] = E.gated(d, sum(ax[j] * w for j, w in ww.items()) / sum(ww.values()))
    d["B1_pfam_ga"] = (d.score_PF01036.fillna(0) >= E.GA).astype(float)
    d["B2_pfam_bits"] = d.score_PF01036.fillna(0)
    d["B2b_margin"] = d.score_PF01036.fillna(0) - d.score_PF18761.fillna(0)
    d["B4_retK"] = d.has_retinal_lysine.fillna(0).astype(float)
    d["B4b_ga_retK"] = d.B1_pfam_ga * d.B4_retK
    d.to_csv(f"{a.outdir}/wp3_external_scores.tsv", sep="\t", index=False)
    rng = np.random.default_rng(150)
    allm, allop = [], []
    sets = {"all": d, "excl_schizorhodopsin": d[d.stratum != "schizorhodopsin"]}
    for name, P in sets.items():
        P = P.reset_index(drop=True)
        mm = E.metrics(P, rng, a.nboot); mm.insert(0, "set", name); allm.append(mm)
        op = E.operating_points(P); op.insert(0, "set", name); allop.append(op)
    pd.concat(allm).to_csv(f"{a.outdir}/wp3_external_metrics.tsv", sep="\t", index=False)
    pd.concat(allop).to_csv(f"{a.outdir}/wp3_external_operating_points.tsv", sep="\t", index=False)
    # per-stratum recall / specificity at the released thresholds (Wilson)
    rows = []
    for (y, st), gg in d.groupby(["y", "stratum"]):
        for t in E.THR:
            k = int((gg.full_gated >= t).sum()) if y == 1 else int((gg.full_gated < t).sum())
            lo, hi = E.wilson(k, len(gg))
            rows.append(dict(cls="positive" if y else "negative", stratum=st, threshold=t,
                             metric="recall" if y else "specificity", k=k, n=len(gg), value=k / len(gg), ci_lo=lo, ci_hi=hi))
    for dc, gg in d[d.y == 1].groupby("distance_class"):
        for t in E.THR:
            k = int((gg.full_gated >= t).sum()); lo, hi = E.wilson(k, len(gg))
            rows.append(dict(cls="positive", stratum=f"distance_{dc}", threshold=t, metric="recall", k=k, n=len(gg),
                             value=k / len(gg), ci_lo=lo, ci_hi=hi))
    pd.DataFrame(rows).to_csv(f"{a.outdir}/wp3_external_strata.tsv", sep="\t", index=False)
    print(pd.concat(allm)[["set", "method", "n_pos", "n_neg", "auprc", "auprc_lo", "auprc_hi", "roc_auc"]].round(3).to_string())


if __name__ == "__main__":
    main()
