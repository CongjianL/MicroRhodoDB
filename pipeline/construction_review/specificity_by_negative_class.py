#!/usr/bin/env python
"""Membership-scorer specificity per negative class: which negatives the score itself has to reject.

The shipped specificity (external set 345/345, clade-root holdout 209/215 at 0.70) pools negatives that never reach
the score: proteins with no PF01036/PF18761 hit fail the domain gate, and heliorhodopsins fail the helio-primary gate.
This script splits every negative by class and by the step that rejects it (domain gate, helio gate, score), and
reports specificity of `full_gated` on the negatives that reach the score.

Self-check: the pooled counts must reproduce the shipped `external_validation_operating_point` and
`holdout_operating_point` (regime reference_clade_root) rows for full_gated, or the script fails.

Holdout gates are not stored per record. Heliorhodopsin negatives (N2_heliorhodopsin_PF18761) are treated as
helio-gated; the others are labelled `score_or_domain_gate`, because the easy classes (animal opsins, GPCRs) most
likely fail the domain gate. The self-check tests this assumption. The subset `hard_not_gated` is the denominator
that tests the score itself: external negatives that pass both gates, and the holdout's hard classes other than
heliorhodopsins (synthetic fragments and frameshifts, HSP30).

Usage: python pipeline/construction_review/specificity_by_negative_class.py <release db> <out.tsv>
"""
import sqlite3
import sys

import pandas as pd
from statsmodels.stats.proportion import proportion_confint

THRESHOLDS = (0.70, 0.86, 0.90)


def wilson(k, n):
    if not n:
        return (float("nan"), float("nan"))
    lo, hi = proportion_confint(int(k), int(n), method="wilson")
    return float(lo), float(hi)


def load(db):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    ext = pd.read_sql("""SELECT negative_class AS neg_class, membership_score_frozen_scorer AS score,
                                gate_has_domain, is_helio_primary
                         FROM external_validation WHERE is_positive = 0""", con)
    ext["set"] = "external"
    ext["rejected_by"] = ["domain_gate" if not d else "helio_gate" if h else "score"
                          for d, h in zip(ext.gate_has_domain, ext.is_helio_primary)]
    # negatives are scored in every fold; the pooled metric uses each negative once, with the mean of its fold
    # scores (pipeline/v150/wp3_eval.py: pool)
    hol = pd.read_sql("""SELECT b.provenance AS neg_class, b.task, AVG(h.score_fold) AS score
                         FROM holdout_assignment h JOIN benchmark_v2 b USING(source_acc)
                         WHERE h.regime = 'reference_clade_root' AND h.role = 'eval_negative'
                         GROUP BY h.source_acc, b.provenance, b.task""", con)
    hol["set"] = "holdout_reference_clade_root"
    hol["rejected_by"] = ["helio_gate" if c == "N2_heliorhodopsin_PF18761" else "score_or_domain_gate"
                          for c in hol.neg_class]
    ext["hard_not_gated"] = ext.rejected_by.eq("score")
    hol["hard_not_gated"] = hol.task.eq("hard") & hol.rejected_by.ne("helio_gate")
    shipped = pd.concat([
        pd.read_sql("""SELECT 'external' AS "set", threshold, k, n FROM external_validation_operating_point
                       WHERE method = 'full_gated' AND metric = 'specificity'""", con),
        pd.read_sql("""SELECT 'holdout_reference_clade_root' AS "set", threshold, k, n FROM holdout_operating_point
                       WHERE regime = 'reference_clade_root' AND method = 'full_gated' AND metric = 'specificity'""",
                    con)])
    con.close()
    cols = ["set", "neg_class", "rejected_by", "hard_not_gated", "score"]
    return pd.concat([ext, hol], ignore_index=True)[cols], shipped


def table(neg):
    rows = []
    groups = [((s, "all", "all"), g) for s, g in neg.groupby("set")]
    groups += [((s, "all", "hard_not_gated"), g[g.hard_not_gated]) for s, g in neg.groupby("set")]
    groups += [((s, c, r), g) for (s, c, r), g in neg.groupby(["set", "neg_class", "rejected_by"])]
    for (s, c, r), g in groups:
        for thr in THRESHOLDS:
            fp = int((g.rejected_by.ne("helio_gate") & g.rejected_by.ne("domain_gate") & (g.score >= thr)).sum())
            n = len(g)
            lo, hi = wilson(n - fp, n)
            rows.append({"set": s, "neg_class": c, "rejected_by": r, "threshold": thr, "n": n,
                         "true_negatives": n - fp, "specificity": (n - fp) / n if n else float("nan"),
                         "ci_lo": lo, "ci_hi": hi, "ci_method": "wilson"})
    return pd.DataFrame(rows)


def check(t, shipped):
    pooled = t[t.neg_class.eq("all") & t.rejected_by.eq("all")]
    bad = []
    for r in shipped.itertuples():
        m = pooled[(pooled["set"] == r.set) & ((pooled.threshold - r.threshold).abs() < 1e-9)]
        if len(m) != 1 or int(m.true_negatives.iloc[0]) != int(r.k) or int(m.n.iloc[0]) != int(r.n):
            bad.append(f"{r.set} @{r.threshold}: shipped {r.k}/{r.n}, recomputed "
                       f"{m.true_negatives.tolist()}/{m.n.tolist()}")
    if bad:
        sys.exit("pooled counts do not reproduce the shipped operating points:\n  " + "\n  ".join(bad))


def main():
    db, out = sys.argv[1:3]
    neg, shipped = load(db)
    t = table(neg)
    check(t, shipped)
    t.to_csv(out, sep="\t", index=False, float_format="%.4f")
    print("pooled counts reproduce the shipped operating points")
    show = t[t.neg_class.eq("all")]
    print(show[["set", "rejected_by", "threshold", "n", "true_negatives", "specificity", "ci_lo"]]
          .to_string(index=False, float_format="%.3f"))


if __name__ == "__main__":
    main()
