#!/usr/bin/env python
"""WP3 external-set figure: PR curves, score by stratum, ablation. Usage: wp3_external_figure.py out_dir out_prefix"""
import sys
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import precision_recall_curve
from wp3_figures import OI, CONT, BIN

STRAT_NEG = ["retinal_site_lacking_PF01036_homolog", "heliorhodopsin", "animal_typeII_opsin", "classA_GPCR",
             "classB_GPCR", "classC_GPCR", "PAQR_7TM", "MFS_transporter_7TM", "bacterial_7TM_other",
             "fungal_Hsp30_named_nonhomolog"]


def main():
    d, out = sys.argv[1], sys.argv[2]
    D = pd.read_csv(f"{d}/wp3_external_scores.tsv", sep="\t")
    M = pd.read_csv(f"{d}/wp3_external_metrics.tsv", sep="\t")
    M = M[M.set == "all"]
    fig, ax = plt.subplots(1, 3, figsize=(8.4, 4.2), constrained_layout=True, gridspec_kw=dict(width_ratios=[1, 1.35, 0.9]))
    a = ax[0]
    for m, (lab, c) in CONT.items():
        p, r, _ = precision_recall_curve(D.y, D[m])
        a.step(r, p, where="post", color=c, lw=1.1, label=lab)
    p, r, _ = precision_recall_curve(D.y, D.abl_e_retinal)
    a.step(r, p, where="post", color=OI[6], lw=1.0, ls="--", label="score without retinal axis")
    for m, (lab, mk) in BIN.items():
        pr = D[m] >= 0.5
        tp = (pr & (D.y == 1)).sum()
        a.plot(tp / D.y.sum(), tp / max(pr.sum(), 1), mk, color="0.35", ms=4, mfc="white", label=lab)
    a.axhline(D.y.mean(), color="0.7", lw=0.6, ls=":")
    a.set(xlim=(0, 1.02), ylim=(0, 1.03), xlabel="Recall", ylabel="Precision",
          title=f"External set ({int(D.y.sum())} pos / {int((1 - D.y).sum())} neg)")
    a.legend(fontsize=5.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2)
    # score by stratum
    a = ax[1]
    pos = D[D.y == 1].copy()
    order = list(pos.groupby("stratum").full_gated.median().sort_values(ascending=False).index) + STRAT_NEG
    rng = np.random.default_rng(1)
    for i, st in enumerate(order):
        g = D[D.stratum == st]
        if not len(g):
            continue
        c = OI[5] if g.y.iloc[0] == 1 else OI[6]
        a.scatter(g.full_raw, i + rng.uniform(-0.18, 0.18, len(g)), s=9, facecolor="white", edgecolor="0.6", lw=0.5, zorder=1)
        a.scatter(g.full_gated, i + rng.uniform(-0.18, 0.18, len(g)), s=9, color=c, lw=0, zorder=2)
    for t in (0.70, 0.86):
        a.axvline(t, color="0.5", lw=0.6, ls="--")
    a.set_yticks(range(len(order)))
    a.set_yticklabels([f"{s.replace('_', ' ')} (n={int((D.stratum == s).sum())})" for s in order], fontsize=6)
    a.invert_yaxis()
    a.set(xlabel="Membership score", xlim=(-0.03, 1.0), title="Score by stratum")
    a.scatter([], [], s=9, color=OI[5], label="positive, gated"); a.scatter([], [], s=9, color=OI[6], label="negative, gated")
    a.scatter([], [], s=9, facecolor="white", edgecolor="0.6", label="no gates")
    a.legend(fontsize=5.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=3)
    # ablation
    a = ax[2]
    g = M[M.method.str.startswith("abl_")].copy()
    g["axis"] = g.method.str.replace("abl_e_", "")
    g = g.sort_values("d_auprc_full_minus_method")
    y = np.arange(len(g))
    a.barh(y, g.d_auprc_full_minus_method, color=OI[5], height=0.6)
    a.errorbar(g.d_auprc_full_minus_method, y, xerr=[(g.d_auprc_full_minus_method - g.d_lo).clip(0),
                                                     (g.d_hi - g.d_auprc_full_minus_method).clip(0)],
               fmt="none", ecolor="0.2", lw=0.8)
    a.plot(g.d_auprc_full_minus_method, y, "o", color=OI[5], ms=3)
    for yi, v in zip(y, g.d_auprc_full_minus_method):
        a.text(max(v, 0) + 0.02, yi + 0.25, f"{v:.3f}", fontsize=6, va="center")
    a.axvline(0, color="0.5", lw=0.6)
    a.set_yticks(y); a.set_yticklabels(g.axis)
    a.set_xlim(-0.05, max(0.6, float(g.d_hi.max()) + 0.05))
    a.set(xlabel="AUPRC loss (axis removed)", title="Ablation (external)")
    fig.savefig(out + ".svg"); fig.savefig(out + ".png", dpi=200)


if __name__ == "__main__":
    main()
