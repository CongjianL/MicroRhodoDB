#!/usr/bin/env python3
"""
wp7_usecase_figures.py - WP7 worked-use-case figures for the v1.5.0 response document.

Plan WP7 requires: "Worked use case: eukaryotic (fungal/algal) rhodopsin diversity absent from
MicRhoDE (86% unrepresented), shown through named subfamilies x evidence levels x taxonomy. A
second short example covers the xenorhodopsin addition."

This script reproduces both figures directly from the release database (plus the external
validation placement table for figure 2), rather than from ad hoc notebook cells. Everything
that is a *number* is queried fresh; only cosmetic/curatorial display labels (organism
nicknames for two external accessions, resolved in the response document from literature and a
direct NCBI efetch lookup -- see RESPONSE_TO_REVIEWERS.md) are hardcoded, since no DB table
stores an organism name for an external validation record.

Figure 1 (eukaryotic diversity): for every active (typeI_* or boundary_family) Eukaryota record
in v_master, extracts kingdom/phylum from protein.lineage (an NCBI-style rank-tagged lineage
string; gtdb_taxonomy does not cover Eukaryota), bins into a 5-category taxon_group, and plots
clade_name x evidence_level and clade_name x taxon_group as two horizontal stacked bar panels.

Figure 2 (xenorhodopsin addition): compares the two corpus Bacillus coahuilensis xenorhodopsin
(BcXeR) members (A0AA82WPB4, E1; A0AA82WP37, E2) against two external-validation-set xenorhodopsin
exemplars (WP_051881467.1, 6EYU_A/NsXeR) by membership_score and, for the external pair, by
placement pendant branch length and clade-call QC (illustrating that membership confidence and
placement/clade-assignment confidence are tracked as distinct signals).

Usage:
  python wp7_usecase_figures.py --db /workspace/v150/build/db/microrhododb_v1.5.0.sqlite \
      --external_placement /workspace/v150/place/external_set_placement.tsv \
      --outdir /mnt/results/v150_usecase
"""
import argparse
import os
import re
import sqlite3

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

matplotlib.rcParams["font.family"] = ["Liberation Sans", "Arimo", "DejaVu Sans"]
matplotlib.rcParams["svg.fonttype"] = "none"

TAXON_COLORS = {
    "Fungi: Ascomycota": "#0072B2",
    "Fungi: Basidiomycota": "#56B4E9",
    "Fungi: other phyla": "#009E73",
    "Algae (Viridiplantae)": "#E69F00",
    "Other protists / eukaryotes": "#CC79A7",
}
SHORT_CLADE_LABEL = {
    "Eukaryotic ETK rhodopsins (enzyme-rhodopsin-like)": "Eukaryotic ETK rhodopsins",
    "Eukaryotic enzyme rhodopsins (Rh-GC and relatives)": "Eukaryotic enzyme rhodopsins (Rh-GC)",
    "Xanthorhodopsin / NDQ-NTQ ion-pump superclade": "Xanthorhodopsin / NDQ-NTQ superclade",
    "Fungal rhodopsins (CarO / LR / NOP-1-like)": "Fungal rhodopsins (CarO/LR/NOP-1-like)",
    "Amoebozoan (Evosea) DTE rhodopsins (backbone group)": "Amoebozoan (Evosea) DTE rhodopsins",
    "Archaeal sensory rhodopsins (SRI/SRII/SRIII)": "Archaeal sensory rhodopsins (SRI/II/III)",
}
# Organism display nicknames for the two external xenorhodopsin exemplars: not stored in any DB
# table (external_set_placement.tsv carries no organism column); resolved from literature/NCBI
# efetch and documented in RESPONSE_TO_REVIEWERS.md.
EXT_ORGANISM_LABEL = {
    "WP_051881467.1": "Parvularcula oceani",
    "6EYU_A": "Ca. Nanosalina J07AB43",
}


def rank_extract(lin, rank):
    if not isinstance(lin, str):
        return None
    m = re.search(rf"([^,]+) \({rank}\)", lin)
    return m.group(1).strip() if m else None


def taxon_group(phylum):
    if phylum == "Ascomycota":
        return "Fungi: Ascomycota"
    if phylum == "Basidiomycota":
        return "Fungi: Basidiomycota"
    if phylum in ("Chytridiomycota", "Blastocladiomycota"):
        return "Fungi: other phyla"
    if phylum in ("Chlorophyta", "Streptophyta"):
        return "Algae (Viridiplantae)"
    return "Other protists / eukaryotes"


def build_figure1(con, outdir):
    vm = pd.read_sql("select * from v_master where tax_domain='Eukaryota'", con)
    lin = pd.read_sql("select source_acc, lineage from protein where tax_domain='Eukaryota'", con)
    euk = vm.merge(lin, on="source_acc", how="left")
    euk["phylum"] = euk.lineage.apply(lambda s: rank_extract(s, "phylum"))

    active_statuses = [s for s in euk.membership_status.unique() if s.startswith("typeI_") or s == "boundary_family"]
    active = euk[euk.membership_status.isin(active_statuses)].copy()
    active["taxon_group"] = active.phylum.apply(taxon_group)

    ev_ct = pd.crosstab(active.clade_name.fillna("(unassigned to a named clade)"), active.evidence_level)
    for c in ["E1", "E2", "E3", "E4", "E5"]:
        if c not in ev_ct.columns:
            ev_ct[c] = 0
    ev_ct = ev_ct[["E1", "E2", "E3", "E4", "E5"]]
    ev_ct["total"] = ev_ct.sum(axis=1)
    ev_ct = ev_ct.sort_values("total", ascending=True)

    tax_ct = pd.crosstab(active.clade_name.fillna("(unassigned to a named clade)"), active.taxon_group)
    for c in TAXON_COLORS:
        if c not in tax_ct.columns:
            tax_ct[c] = 0
    tax_ct = tax_ct[list(TAXON_COLORS)].loc[ev_ct.index]

    n_active = len(active)
    assert ev_ct["total"].sum() == n_active
    assert tax_ct.sum(axis=1).equals(ev_ct["total"])

    ylabels = [SHORT_CLADE_LABEL.get(n, n) for n in ev_ct.index]
    y = np.arange(len(ev_ct))

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(13, 6.2), sharey=True)

    ev_cmap = plt.cm.viridis(np.linspace(0.08, 0.92, 5))
    ev_colors = {lvl: ev_cmap[i] for i, lvl in enumerate(["E1", "E2", "E3", "E4", "E5"])}
    left = np.zeros(len(ev_ct))
    for lvl in ["E1", "E2", "E3", "E4", "E5"]:
        vals = ev_ct[lvl].values
        axL.barh(y, vals, left=left, color=ev_colors[lvl], edgecolor="white", linewidth=0.4, label=lvl, height=0.72)
        left += vals
    for yi, tot in zip(y, ev_ct["total"].values):
        axL.text(tot + max(ev_ct["total"]) * 0.012, yi, f"{tot:,}", va="center", ha="left", fontsize=8)
    axL.set_yticks(y)
    axL.set_yticklabels(ylabels, fontsize=9)
    axL.set_xlabel("Records (count)")
    axL.set_title("A. Evidence level", fontsize=11, loc="left")
    axL.legend(title="Evidence", loc="lower right", fontsize=8, title_fontsize=8, frameon=False)
    axL.spines[["top", "right"]].set_visible(False)
    axL.set_xlim(0, max(ev_ct["total"]) * 1.12)

    left = np.zeros(len(tax_ct))
    for grp in TAXON_COLORS:
        vals = tax_ct[grp].values
        axR.barh(y, vals, left=left, color=TAXON_COLORS[grp], edgecolor="white", linewidth=0.4, label=grp, height=0.72)
        left += vals
    axR.set_xlabel("Records (count)")
    axR.set_title("B. Taxonomic group", fontsize=11, loc="left")
    axR.legend(loc="lower right", fontsize=8, frameon=False)
    axR.spines[["top", "right"]].set_visible(False)
    axR.set_xlim(0, max(ev_ct["total"]) * 1.12)

    fig.suptitle(f"Eukaryotic Type-I rhodopsin diversity in MicroRhodoDB v1.5.0 (n={n_active:,} active records)", fontsize=12, y=1.0)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(os.path.join(outdir, "fig_wp7_eukaryotic_diversity.svg"), bbox_inches="tight")
    fig.savefig(os.path.join(outdir, "fig_wp7_eukaryotic_diversity.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"Figure 1: n_active={n_active}, {len(ev_ct)} clade_name rows, sum check ok")
    return ev_ct, tax_ct


def build_figure2(con, external_placement_path, outdir):
    corpus = pd.read_sql(
        "select source_acc, membership_status, evidence_level, func_class, clade_id, membership_score "
        "from v_master where source_acc in ('A0AA82WPB4','A0AA82WP37')",
        con,
    ).set_index("source_acc")
    clade_names = pd.read_sql("select clade_id, name from clade", con).set_index("clade_id")["name"].to_dict()

    ext = pd.read_csv(external_placement_path, sep="\t")
    ext_rows = ext[ext["set"].isin(["positive", "boundary_exemplar"]) & ext.ext_acc.isin(["WP_051881467.1", "6EYU_A"])]
    ext_rows = ext_rows.drop_duplicates("ext_acc").set_index("ext_acc")

    records = [
        (f"A0AA82WPB4 ({corpus.loc['A0AA82WPB4','evidence_level']})", corpus.loc["A0AA82WPB4", "membership_score"], corpus.loc["A0AA82WPB4", "clade_id"]),
        (f"A0AA82WP37 ({corpus.loc['A0AA82WP37','evidence_level']})", corpus.loc["A0AA82WP37", "membership_score"], corpus.loc["A0AA82WP37", "clade_id"]),
        (f"WP_051881467.1\n(external, +)", ext_rows.loc["WP_051881467.1", "membership_score"], ext_rows.loc["WP_051881467.1", "clade_id"]),
        (f"6EYU_A / NsXeR\n(external, +)", ext_rows.loc["6EYU_A", "membership_score"], ext_rows.loc["6EYU_A", "clade_id"]),
    ]
    clade_color = {corpus.loc["A0AA82WPB4", "clade_id"]: "#0072B2", ext_rows.loc["6EYU_A", "clade_id"]: "#D55E00"}

    fig, (axA, axB) = plt.subplots(1, 2, figsize=(12.5, 5.8))

    xpos = [0, 1.0, 2.4, 3.4]
    for x, (lbl, score, cl) in zip(xpos, records):
        axA.bar(x, score, width=0.75, color=clade_color[cl], edgecolor="black", linewidth=0.5)
        axA.text(x, score + 0.015, f"{score:.3f}", ha="center", fontsize=9)
    axA.axhline(0.40, color="grey", linestyle="--", linewidth=1)
    axA.text(1.7, 0.15, "Type-I membership\nthreshold (0.40)", fontsize=7.5, color="grey", ha="center", va="center")
    axA.set_xticks(xpos)
    axA.set_xticklabels([r[0] for r in records], fontsize=8.8)
    axA.text(0.5, -0.145, "BcXeR (corpus members)", ha="center", fontsize=8, style="italic", transform=axA.get_xaxis_transform())
    axA.set_ylabel("Membership score")
    axA.set_ylim(0, 1.04)
    axA.set_title("A. Membership score", fontsize=11, loc="left")
    axA.spines[["top", "right"]].set_visible(False)

    ext2 = [
        (f"WP_051881467.1\n({EXT_ORGANISM_LABEL['WP_051881467.1']})", ext_rows.loc["WP_051881467.1", "lwr_weighted_pendant"], ext_rows.loc["WP_051881467.1", "clade_call_qc"], ext_rows.loc["WP_051881467.1", "clade_id"]),
        (f"6EYU_A / NsXeR\n({EXT_ORGANISM_LABEL['6EYU_A']})", ext_rows.loc["6EYU_A", "lwr_weighted_pendant"], ext_rows.loc["6EYU_A", "clade_call_qc"], ext_rows.loc["6EYU_A", "clade_id"]),
    ]
    for i, (lbl, pend, qc, cl) in enumerate(ext2):
        axB.bar(i, pend, width=0.5, color=clade_color[cl], edgecolor="black", linewidth=0.5)
        axB.text(i, pend + 0.08, f"{pend:.2f} ({qc})", ha="center", fontsize=8.8)
    axB.set_xticks([0, 1])
    axB.set_xticklabels([r[0] for r in ext2], fontsize=8.8)
    axB.set_ylabel("Placement pendant branch length (substitutions/site)")
    axB.set_ylim(0, max(r[1] for r in ext2) * 1.2)
    axB.set_title("B. Placement branch length", fontsize=11, loc="left")
    axB.spines[["top", "right"]].set_visible(False)

    from matplotlib.patches import Patch

    legend_handles = [Patch(color=c, label=f"{cid}: {clade_names.get(cid, cid)}") for cid, c in clade_color.items()]
    fig.legend(handles=legend_handles, loc="lower center", ncol=1, fontsize=8.8, frameon=False, bbox_to_anchor=(0.5, -0.1))

    fig.suptitle("Xenorhodopsin addition: corpus members and external-validation placement (MicroRhodoDB v1.5.0)", fontsize=11.5, y=1.01)
    fig.tight_layout(rect=[0, 0.07, 1, 0.96])
    fig.savefig(os.path.join(outdir, "fig_wp7_xenorhodopsin_addition.svg"), bbox_inches="tight")
    fig.savefig(os.path.join(outdir, "fig_wp7_xenorhodopsin_addition.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("Figure 2: corpus + external records resolved from DB/TSV, saved")
    return records, ext2


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True, help="path to the v1.5.0 release sqlite (opened read-only)")
    ap.add_argument("--external_placement", required=True, help="external_set_placement.tsv path")
    ap.add_argument("--outdir", required=True, help="output directory for the two figures (svg+png each)")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    build_figure1(con, args.outdir)
    build_figure2(con, args.external_placement, args.outdir)
    con.close()


if __name__ == "__main__":
    main()
