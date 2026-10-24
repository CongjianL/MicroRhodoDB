#!/usr/bin/env python3
"""MicroRhodoDB v1.6.1 validation analyses requested in the simulated NAR review (2026-10-24).

  A  hard_negative_specificity_v161.tsv   specificity of the frozen scorer on the external set, split into easy
                                          negatives (no PF01036 domain) and hard negatives, score alone vs the
                                          full rule (gates of full_gated) (R2-1)
  B  nearest_e1_baseline_v161.tsv         nearest-characterised-protein transfer on the 76 unique E1 sequences at the
                                          leave-one-out / -subfamily-out / -clade-out levels, for comparison with the
                                          shipped legacy policy (R2-3)
  C  e3_replicate_robustness_v161.tsv     for each E1-consensus group used by E3 calls: are its reference tips still a
                                          clade, and does its consensus survive, in the two independent replicate IQ-TREE
                                          searches (run2, run3; run1 is the release tree)? plus the E3 calls affected (R1-7)

Usage: python pipeline/v161/analyses_v161.py <v1.6.1 db> <refpkg dir> <out dir>
"""
import math
import os
import sqlite3
import sys
from collections import Counter

import pandas as pd
from Bio import Align, Phylo
from Bio.Align import substitution_matrices

Z = 1.959964


def wilson(k, n):
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return p, c - h, c + h


# ------------------------------------------------------------------ A
def hard_negatives(con):
    ev = pd.read_sql("""SELECT is_positive, negative_class, membership_score_frozen_scorer AS s, gate_has_domain AS dom,
                               is_helio_primary AS helio FROM external_validation""", con)
    neg = ev[ev.is_positive == 0].copy()
    neg["kind"] = neg.dom.map({1: "hard (PF01036/PF18761 domain present)", 0: "easy (no domain; score 0)"})
    rows = []
    for t in (0.70, 0.86, 0.90):
        for kind, g in [("all", neg)] + list(neg.groupby("kind")) + list(neg[neg.dom == 1].groupby("negative_class")):
            fp_score = int((g.s >= t).sum())
            fp_rule = int(((g.s >= t) & (g.dom == 1) & (g.helio == 0)).sum())
            for method, fp in (("score_only", fp_score), ("full_rule", fp_rule)):
                p, lo, hi = wilson(len(g) - fp, len(g))
                rows.append(dict(threshold=t, negative_set=kind, n=len(g), method=method, false_positives=fp,
                                 specificity=round(p, 4), ci_lo=round(lo, 4), ci_hi=round(hi, 4)))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ B
def aligner():
    a = Align.PairwiseAligner()
    a.mode = "local"
    a.substitution_matrix = substitution_matrices.load("BLOSUM62")
    a.open_gap_score, a.extend_gap_score = -11, -1
    return a


def identity(al, x, y):
    aln = al.align(x, y)[0]
    c = aln.counts()
    L = c.identities + c.mismatches + c.gaps
    return c.identities / L if L else 0.0


def nearest_e1(con):
    rec = pd.read_sql("""SELECT l.source_acc, l.exp, l.rc_clade, COALESCE(NULLIF(r.subclade_id, ''), l.rc_clade) AS subfam,
                                p.sequence FROM loco_validation_record l JOIN protein p USING(source_acc)
                         LEFT JOIN record_clade r USING(source_acc)""", con)
    al = aligner()
    seqs = dict(zip(rec.source_acc, rec.sequence))
    accs = list(rec.source_acc)
    ident = {}
    for i, a in enumerate(accs):
        for b in accs[i + 1:]:
            ident[(a, b)] = ident[(b, a)] = identity(al, seqs[a], seqs[b])
    r = rec.set_index("source_acc")
    rows = []
    for hold, key in (("LOO", None), ("LOSO", "subfam"), ("LOCO", "rc_clade")):
        preds = []
        for a in accs:
            pool = [b for b in accs if b != a and (key is None or r.at[b, key] != r.at[a, key])]
            best = max(pool, key=lambda b: ident[(a, b)])
            preds.append((a, r.at[best, "exp"], ident[(a, best)], r.at[a, "exp"]))
        for thr in (0.0, 0.3, 0.5):
            called = [(p, t) for _, p, idv, t in preds if idv >= thr]
            k = sum(p == t for p, t in called)
            p_, lo, hi = wilson(k, len(called))
            rows.append(dict(holdout=hold, method=f"nearest_E1_identity>={thr:.1f}" if thr else "nearest_E1_any",
                             n_records=len(accs), n_called=len(called), coverage=round(len(called) / len(accs), 4),
                             n_correct=k, precision=round(p_, 4), ci_lo=round(lo, 4), ci_hi=round(hi, 4),
                             median_identity=round(pd.Series([idv for _, _, idv, _ in preds]).median(), 4)))
    loco = pd.read_sql("SELECT * FROM loco_validation WHERE release_set='1.6.0' AND subset='all_E1'", con)
    for t in loco.itertuples():
        rows.append(dict(holdout="LOCO (shipped)", method=f"shipped_{t.policy}", n_records=t.n, n_called=t.n_assigned,
                         coverage=round(t.coverage, 4), n_correct=t.n_correct, precision=round(t.precision, 4),
                         ci_lo=round(t.prec_lo, 4), ci_hi=round(t.prec_hi, 4), median_identity=None))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ C
TIP_CLASS = {"proton_pump_outward": "proton_pump", "sensory_transducer": "sensory", "anion_channel": "light_gated_channel",
             "cation_channel": "light_gated_channel", "enzyme": "enzyme_rhodopsin"}


def consensus(classes):
    c = Counter(classes)
    n = sum(c.values())
    if n < 2:
        return None
    cls, k = c.most_common(1)[0]
    return cls if k / n >= 0.8 else None


def e3_robustness(con, refpkg):
    tips = pd.read_csv(os.path.join(refpkg, "clades", "MR_CLD3_tips.tsv"), sep="\t")
    ann = pd.read_csv(os.path.join(refpkg, "tips_annot.tsv"), sep="\t", dtype=str, keep_default_na=False)
    helio = list(ann[ann.tip_role == "outgroup_heliorhodopsin"].source_acc)
    anchors = {r.source_acc: TIP_CLASS.get(r.exp_class, r.exp_class) for r in ann.itertuples()
               if r.exp_class and r.tip_role in ("anchor_characterized", "seed")}
    groups = pd.read_sql("SELECT level, group_id, n_E1, clade_function, E1_classes FROM clade_function_consensus "
                         "WHERE consensus_status='consensus'", con)
    e3 = pd.read_sql("""SELECT r.clade_function_source AS g, COUNT(*) AS n FROM record_clade r
                        JOIN v_counted v USING(source_acc) WHERE v.evidence_level='E3' GROUP BY 1""", con)
    e3n = dict(zip(e3.g, e3.n))
    tipset = {}
    for g in groups.itertuples():
        # backbone groups (MR_CLD3_B0x) are recorded in the subclade column under clade 'backbone_unassigned'
        col = "subclade_id" if g.level == "subclade" or g.group_id.startswith("MR_CLD3_B") else "clade_id"
        tipset[g.group_id] = set(tips[tips[col] == g.group_id].source_acc)
    rows = []
    # run1 (seed 1501) is the release tree itself, so only run2 and run3 are independent replicates
    for run in ("run2", "run3"):
        t = Phylo.read(os.path.join(refpkg, "tree", f"{run}.treefile"), "newick")
        t.root_with_outgroup(helio[0])
        names = {c.name for c in t.get_terminals()}
        for g in groups.itertuples():
            T = tipset[g.group_id] & names
            base = [c for c in (x.split(":")[0] for x in g.E1_classes.split(";")) for _ in
                    range(int([x for x in g.E1_classes.split(";") if x.startswith(c + ":")][0].split(":")[1]))]
            if len(T) < 2:
                rows.append(dict(run=run, group_id=g.group_id, level=g.level, n_tips=len(T), jaccard=None,
                                 intruding_anchor_classes="", consensus_primary=g.clade_function,
                                 consensus_replicate=g.clade_function, retained=True,
                                 note="group with <2 tips: membership of its E1 records is unchanged"))
                continue
            mrca = t.common_ancestor(list(T))
            C = {c.name for c in mrca.get_terminals()}
            intr = [anchors[x] for x in C - T if x in anchors]
            cons = consensus(base + intr)
            rows.append(dict(run=run, group_id=g.group_id, level=g.level, n_tips=len(T),
                             jaccard=round(len(T & C) / len(T | C), 4), intruding_anchor_classes=";".join(sorted(intr)),
                             consensus_primary=g.clade_function, consensus_replicate=cons or "none",
                             retained=cons == g.clade_function, note=""))
    df = pd.DataFrame(rows)
    summ = df.groupby("group_id").agg(level=("level", "first"), consensus=("consensus_primary", "first"),
                                     min_jaccard=("jaccard", "min"), retained_all_runs=("retained", "all")).reset_index()
    summ["n_E3_calls"] = summ.group_id.map(e3n).fillna(0).astype(int)
    return df, summ


if __name__ == "__main__":
    db, refpkg, out = sys.argv[1:4]
    os.makedirs(out, exist_ok=True)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    a = hard_negatives(con)
    a.to_csv(os.path.join(out, "hard_negative_specificity_v161.tsv"), sep="\t", index=False)
    b = nearest_e1(con)
    b.to_csv(os.path.join(out, "nearest_e1_baseline_v161.tsv"), sep="\t", index=False)
    c, cs = e3_robustness(con, refpkg)
    c.to_csv(os.path.join(out, "e3_replicate_robustness_runs_v161.tsv"), sep="\t", index=False)
    cs.to_csv(os.path.join(out, "e3_replicate_robustness_v161.tsv"), sep="\t", index=False)
    tot = int(cs.n_E3_calls.sum())
    kept = int(cs[cs.retained_all_runs].n_E3_calls.sum())
    print(f"E3 calls whose consensus group is retained in both independent replicate trees: {kept}/{tot}")
