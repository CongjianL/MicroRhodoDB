#!/usr/bin/env python
"""WP3 figures: PR curves, AUPRC by regime, ablation, reliability. Usage: wp3_figures.py wp3_dir out_prefix"""
import sys
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import precision_recall_curve

matplotlib.rcParams.update({"font.family": ["Liberation Sans", "Arimo", "DejaVu Sans"], "svg.fonttype": "none",
                            "font.size": 8, "axes.spines.top": False, "axes.spines.right": False})
OI = ["#000000", "#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7"]
CONT = {"full_gated": ("MicroRhodoDB score (gated)", OI[0]), "full_raw": ("score, no gates", OI[7]),
        "B2_pfam_bits": ("PF01036 bitscore", OI[5]), "B2b_margin": ("PF01036 - PF18761", OI[2]),
        "B3_nn_bits": ("nearest-neighbour bitscore", OI[1])}
BIN = {"B1_pfam_ga": ("Pfam GA hit", "s"), "B3_nn_bin": ("NN E<=1e-5", "^"), "B4_retK": ("retinal Lys", "D"),
       "B4b_ga_retK": ("GA hit + retinal Lys", "o")}
REG = ["random5", "std_90", "intermediate_65", "taxonomic_phylum", "reference_clade_msc", "reference_clade_root"]


def main():
    d, out = sys.argv[1], sys.argv[2]
    P = pd.read_csv(f"{d}/wp3_holdout_pooled_scores.tsv", sep="\t")
    M = pd.read_csv(f"{d}/wp3_holdout_metrics.tsv", sep="\t")
    fig, ax = plt.subplots(2, 3, figsize=(8.4, 5.0), constrained_layout=True)
    for i, reg in enumerate(["random5", "reference_clade_msc", "taxonomic_phylum"]):
        a = ax[0, i]
        g = P[P.regime == reg]
        for m, (lab, c) in CONT.items():
            p, r, _ = precision_recall_curve(g.y, g[m])
            a.step(r, p, where="post", color=c, lw=1.1, label=lab)
        for m, (lab, mk) in BIN.items():
            pr = g[m] >= 0.5
            tp = (pr & (g.y == 1)).sum()
            a.plot(tp / g.y.sum(), tp / max(pr.sum(), 1), mk, color="0.35", ms=4, mfc="white", label=lab)
        a.axhline(g.y.mean(), color="0.7", lw=0.6, ls=":")
        a.set(xlim=(0, 1.02), ylim=(0, 1.03), xlabel="Recall", ylabel="Precision" if i == 0 else None, title=reg)
    ax[0, 2].legend(fontsize=6, frameon=False, loc="upper left", bbox_to_anchor=(1.02, 1.0))
    # AUPRC by regime
    a = ax[1, 0]
    meths = ["full_gated", "B2_pfam_bits", "B4b_ga_retK", "B3_nn_bits", "B1_pfam_ga"]
    cols = {"full_gated": OI[0], "B2_pfam_bits": OI[5], "B4b_ga_retK": OI[3], "B3_nn_bits": OI[1], "B1_pfam_ga": OI[6]}
    labs = {"full_gated": "score (gated)", "B2_pfam_bits": "PF01036 bits", "B4b_ga_retK": "GA + Lys",
            "B3_nn_bits": "NN bits", "B1_pfam_ga": "GA hit"}
    for j, m in enumerate(meths):
        g = M[M.method == m].set_index("regime").loc[REG]
        x = np.arange(len(REG)) + (j - 2) * 0.13
        a.errorbar(x, g.auprc, yerr=[g.auprc - g.auprc_lo, g.auprc_hi - g.auprc], fmt="o", ms=3, color=cols[m],
                   lw=0.8, capsize=0, label=labs[m])
    a.set_xticks(range(len(REG)))
    a.set_xticklabels([r.replace("reference_clade_", "clade_").replace("taxonomic_", "") for r in REG], rotation=40,
                      ha="right")
    a.set(ylabel="AUPRC (95% cluster bootstrap)", ylim=(0, 1.05))
    a.set_xlim(-0.5, len(REG) - 0.5)
    a.legend(fontsize=6, frameon=False, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=3)
    # ablation
    a = ax[1, 1]
    g = M[(M.regime == "reference_clade_msc") & M.method.str.startswith("abl_")].copy()
    g["axis"] = g.method.str.replace("abl_e_", "")
    g = g.sort_values("d_auprc_full_minus_method")
    y = np.arange(len(g))
    a.barh(y, g.d_auprc_full_minus_method, color=OI[5], height=0.6)
    a.errorbar(g.d_auprc_full_minus_method, y, xerr=[g.d_auprc_full_minus_method - g.d_lo,
                                                     g.d_hi - g.d_auprc_full_minus_method], fmt="none", ecolor="0.2", lw=0.8)
    a.axvline(0, color="0.5", lw=0.6)
    a.set_yticks(y); a.set_yticklabels(g.axis)
    a.set(xlabel="AUPRC loss when axis removed", title="Ablation (clade hold-out)")
    # reliability
    a = ax[1, 2]
    g = P[P.regime == "reference_clade_msc"]
    bins = np.linspace(0, 1, 11)
    for m, c, lab in [("full_gated", OI[0], "gated"), ("full_raw", OI[7], "no gates")]:
        idx = np.clip(np.digitize(g[m], bins) - 1, 0, 9)
        xs, ys, ns = [], [], []
        for b in range(10):
            s = idx == b
            if s.sum() >= 3:
                xs.append(g[m][s].mean()); ys.append(g.y[s].mean()); ns.append(s.sum())
        a.plot(xs, ys, "o-", color=c, ms=3, lw=1, label=lab)
    a.plot([0, 1], [0, 1], color="0.6", lw=0.6, ls="--")
    a.set(xlabel="Mean score in bin", ylabel="Fraction positive", title="Reliability (clade hold-out)",
          xlim=(0, 1), ylim=(0, 1))
    a.legend(fontsize=6, frameon=False, loc="upper left")
    fig.savefig(out + ".svg"); fig.savefig(out + ".png", dpi=200)


if __name__ == "__main__":
    main()
