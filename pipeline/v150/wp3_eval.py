#!/usr/bin/env python
"""WP3 - membership-classifier evaluation for v1.5.0: baselines, ablation, PR curves, calibration.

Scores are those of the frozen v1.4 scorer (reproduced by score_v150.py). For held-out regimes the
fold-specific homology axis (e_hom_fold) is used; all other axes are seed-independent.

Methods
  full_gated  : frozen membership_score, set to 0 when a hard gate fails (no PF01036 domain,
                heliorhodopsin-primary, or non-positive Type-I margin) - this is the released decision rule
  full_raw    : frozen membership_score without gates
  abl_<axis>  : full_gated recomputed with one axis removed and remaining weights renormalised to 1
  B1_pfam_ga  : PF01036 sequence bitscore >= gathering threshold (24.6), binary
  B2_pfam_bits: PF01036 sequence bitscore, continuous
  B2b_margin  : PF01036 - PF18761 bitscore, continuous
  B3_nn_bits  : best MMseqs2 bitscore to a training positive (seeds not excluded for the fold + positives
                of other folds), continuous; binary version at E <= 1e-5
  B4_retK     : retinal lysine present in the TM7 window (binary)
  B4b_ga_retK : B1 AND B4 (binary)
Pooling: each held-out positive appears once (its own fold score); each negative is evaluated in every
fold, so its pooled score is the mean over folds (deterministic, one row per record).
Uncertainty: cluster bootstrap (resampling benchmark_v2.cluster units, stratified by class), 2000 reps.
"""
import argparse, json, os, sqlite3, subprocess
import numpy as np, pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score, precision_recall_curve
from statsmodels.stats.proportion import proportion_confint

W = dict(e_domain=.28, e_coverage=.20, e_retinal=.25, e_margin=.15, e_homology=.10, e_topology=.02)
GA = 24.6
THR = (0.70, 0.86, 0.90)
CONT = ["full_gated", "full_raw", "B2_pfam_bits", "B2b_margin", "B3_nn_bits"] + [f"abl_{k}" for k in W]
BIN = ["B1_pfam_ga", "B3_nn_bin", "B4_retK", "B4b_ga_retK"]


def wilson(k, n):
    if n == 0:
        return (np.nan, np.nan)
    return proportion_confint(k, n, method="wilson")


def ece(y, p, bins=10):
    p = np.clip(p, 0, 1)
    idx = np.minimum((p * bins).astype(int), bins - 1)
    e = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            e += m.mean() * abs(y[m].mean() - p[m].mean())
    return e


def read_fasta(p):
    seqs, acc = {}, None
    for line in open(p):
        if line.startswith(">"):
            acc = line[1:].split()[0]
            seqs[acc] = []
        elif acc:
            seqs[acc].append(line.strip())
    return {k: "".join(v) for k, v in seqs.items()}


def nn_hits(bench_faa, seeds_faa, wd, threads=8):
    os.makedirs(wd, exist_ok=True)
    ref = f"{wd}/ref.faa"
    with open(ref, "w") as f:
        for p in (bench_faa, seeds_faa):
            for k, v in read_fasta(p).items():
                f.write(f">{k}\n{v}\n")
    out = f"{wd}/nn.m8"
    if not os.path.exists(out):
        subprocess.run(["mmseqs", "easy-search", bench_faa, ref, out, f"{wd}/tmp", "-s", "7.5",
                        "--exhaustive-search", "-e", "10", "--threads", str(threads),
                        "--format-output", "query,target,evalue,bits"], check=True, stdout=subprocess.DEVNULL)
    h = pd.read_csv(out, sep="\t", header=None, names=["q", "t", "evalue", "bits"])
    return h[h.q != h.t]


def gated(df, score):
    ok = (df.gate_has_domain.astype(bool) & ~df.is_helio_primary.astype(bool)
          & df.gate_positive_typeI_margin.astype(bool))
    return np.where(ok, score, 0.0)


def build_scores(h, feat, nn, seeds_typeI):
    d = h.merge(feat, on="source_acc", how="left")
    ax = d[list(W)].copy()
    ax["e_homology"] = d.e_hom_fold
    d["full_raw"] = d.score_fold
    d["full_gated"] = gated(d, d.score_fold)
    for k in W:
        ww = {j: w for j, w in W.items() if j != k}
        s = sum(ax[j] * w for j, w in ww.items()) / sum(ww.values())
        d[f"abl_{k}"] = gated(d, s)
    d["B1_pfam_ga"] = (d.score_PF01036.fillna(0) >= GA).astype(float)
    d["B2_pfam_bits"] = d.score_PF01036.fillna(0)
    d["B2b_margin"] = d.score_PF01036.fillna(0) - d.score_PF18761.fillna(0)
    d["B4_retK"] = d.has_retinal_lysine.fillna(0).astype(float)
    d["B4b_ga_retK"] = d.B1_pfam_ga * d.B4_retK
    # B3: nearest training positive, fold-aware
    pos = set(h.loc[h.role == "held_out_positive", "source_acc"])
    fold_pos = h[h.role == "held_out_positive"].groupby("fold_id").source_acc.apply(set).to_dict()
    nnb, nne = [], []
    hq = {q: g for q, g in nn.groupby("q")}
    for _, r in d.iterrows():
        excl = set(json.loads(r.excluded_seeds or "[]"))
        train = (pos - fold_pos.get(r.fold_id, set())) | (seeds_typeI - excl)
        g = hq.get(r.source_acc)
        if g is None:
            nnb.append(0.0); nne.append(np.inf); continue
        g = g[g.t.isin(train)]
        nnb.append(g.bits.max() if len(g) else 0.0)
        nne.append(g.evalue.min() if len(g) else np.inf)
    d["B3_nn_bits"] = nnb
    d["B3_nn_bin"] = (np.array(nne) <= 1e-5).astype(float)
    return d


def pool(d):
    cols = CONT + BIN
    p = d[d.role == "held_out_positive"][["source_acc", "cluster"] + cols].assign(y=1)
    n = d[d.role == "eval_negative"].groupby(["source_acc", "cluster"])[cols].mean().reset_index().assign(y=0)
    return pd.concat([p, n], ignore_index=True)


def metrics(P, rng, nboot):
    y = P.y.values
    out = []
    clus_pos = P[P.y == 1].groupby("cluster").indices
    clus_neg = P[P.y == 0].groupby("cluster").indices
    cp, cn = list(clus_pos.values()), list(clus_neg.values())
    boots = []
    for _ in range(nboot):
        ip = np.concatenate([P[P.y == 1].index.values[cp[i]] for i in rng.integers(0, len(cp), len(cp))])
        ineg = np.concatenate([P[P.y == 0].index.values[cn[i]] for i in rng.integers(0, len(cn), len(cn))])
        boots.append(np.concatenate([ip, ineg]))
    for m in CONT + BIN:
        s = P[m].values
        ap = average_precision_score(y, s)
        auc = roc_auc_score(y, s)
        bap = np.array([average_precision_score(y[b], s[b]) for b in boots])
        bd = np.array([average_precision_score(y[b], P["full_gated"].values[b]) - average_precision_score(y[b], s[b])
                       for b in boots])
        row = dict(method=m, n_pos=int(y.sum()), n_neg=int((1 - y).sum()), auprc=ap,
                   auprc_lo=np.quantile(bap, .025), auprc_hi=np.quantile(bap, .975), roc_auc=auc,
                   d_auprc_full_minus_method=average_precision_score(y, P.full_gated) - ap,
                   d_lo=np.quantile(bd, .025), d_hi=np.quantile(bd, .975))
        if m.startswith("full") or m.startswith("abl"):
            row["brier"] = float(np.mean((np.clip(s, 0, 1) - y) ** 2))
            row["ece10"] = ece(y, s)
        out.append(row)
    return pd.DataFrame(out)


def operating_points(P):
    y = P.y.values
    rows = []
    for m in ["full_gated", "full_raw"]:
        for t in THR:
            pr = P[m].values >= t
            tp, fp = int((pr & (y == 1)).sum()), int((pr & (y == 0)).sum())
            fn, tn = int((~pr & (y == 1)).sum()), int((~pr & (y == 0)).sum())
            for name, k, n in [("sensitivity", tp, tp + fn), ("specificity", tn, tn + fp), ("precision", tp, tp + fp)]:
                lo, hi = wilson(k, n)
                rows.append(dict(method=m, threshold=t, metric=name, k=k, n=n, value=k / n if n else np.nan,
                                 ci_lo=lo, ci_hi=hi, ci_method="wilson"))
    for m in BIN:
        pr = P[m].values >= 0.5
        tp, fp = int((pr & (y == 1)).sum()), int((pr & (y == 0)).sum())
        fn, tn = int((~pr & (y == 1)).sum()), int((~pr & (y == 0)).sum())
        for name, k, n in [("sensitivity", tp, tp + fn), ("specificity", tn, tn + fp), ("precision", tp, tp + fp)]:
            lo, hi = wilson(k, n)
            rows.append(dict(method=m, threshold=np.nan, metric=name, k=k, n=n, value=k / n if n else np.nan,
                             ci_lo=lo, ci_hi=hi, ci_method="wilson"))
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--feat", required=True, help="bench_scores_v150.tsv")
    ap.add_argument("--bench_faa", required=True)
    ap.add_argument("--seeds_faa", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--nboot", type=int, default=2000)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    h = pd.read_sql("select * from holdout_assignment", con)
    bm = pd.read_sql("select source_acc, cluster, provenance from benchmark_v2", con)
    seeds = pd.read_sql("select acc, subfamily from seed", con)
    seeds_typeI = set(seeds.loc[seeds.subfamily != "heliorhodopsin", "acc"])
    feat = pd.read_csv(a.feat, sep="\t")
    h = h.merge(bm, on="source_acc", how="left")
    nn = nn_hits(a.bench_faa, a.seeds_faa, os.path.join(a.outdir, "_nn"))
    rng = np.random.default_rng(150)
    allm, allop, pooled = [], [], []
    for reg, g in h.groupby("regime"):
        d = build_scores(g, feat, nn, seeds_typeI)
        P = pool(d)
        P["regime"] = reg
        pooled.append(P.merge(bm[["source_acc", "provenance"]], on="source_acc", how="left"))
        mm = metrics(P.reset_index(drop=True), rng, a.nboot); mm.insert(0, "regime", reg); allm.append(mm)
        op = operating_points(P); op.insert(0, "regime", reg); allop.append(op)
        print(reg, "done", flush=True)
    pd.concat(allm).to_csv(f"{a.outdir}/wp3_holdout_metrics.tsv", sep="\t", index=False)
    pd.concat(allop).to_csv(f"{a.outdir}/wp3_holdout_operating_points.tsv", sep="\t", index=False)
    pd.concat(pooled).to_csv(f"{a.outdir}/wp3_holdout_pooled_scores.tsv", sep="\t", index=False)


if __name__ == "__main__":
    main()
