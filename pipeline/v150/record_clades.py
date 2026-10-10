#!/usr/bin/env python
"""Per-record MR_CLD3 clade assignment + clade E1 functional consensus (input for wp5_evidence --clades).

Record clade = reference-tip clade (tips) or primary-model placement with clade_call == 'assigned' (LWR >= 0.9)
and placement_qc == 'ok' (LWR-weighted pendant <= 1.0).
Subclade analogously (subclade_call == 'assigned').
Clade function consensus (from E1 records, mapped to v1.4 func classes via EXP2V14):
  level used = subclade if it has >= 2 E1 records with >= 80% agreement, else level-1 clade under the same rule,
  else none ('mixed' / 'no_E1'). clade_id column = level-1 clade (used by E2 same-clade check).

Usage: record_clades.py MR_CLD3_tips.tsv placements_all_models.tsv primary_tag characterized_v150.tsv \
       func_class_overrides.tsv out_records.tsv out_clade_function.tsv
"""
import sys, os
import pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
from wp5_evidence import EXP2V14


def consensus(classes, min_n=2, min_frac=0.8):
    s = pd.Series(classes).dropna()
    if len(s) == 0:
        return None, 0, 0.0, "no_E1"
    vc = s.value_counts()
    frac = vc.iloc[0] / len(s)
    if len(s) >= min_n and frac >= min_frac:
        return vc.index[0], len(s), frac, "consensus"
    return None, len(s), frac, ("mixed" if len(vc) > 1 else "single_E1")


def main():
    tipsf, plf, prim, charf, ovf, out_r, out_c = sys.argv[1:8]
    T = pd.read_csv(tipsf, sep="\t").fillna("")
    T = T.assign(clade_id=T.clade_id.where(T.clade_id != "backbone_unassigned", ""), source="reference_tip")
    P = pd.read_csv(plf, sep="\t").fillna("")
    P = P[P.model_tag == prim]
    ok = P.placement_qc == "ok"
    P = P.assign(clade_id=P.clade_id.where((P.clade_call == "assigned") & ok, ""),
                 subclade_id=P.subclade_id.where((P.subclade_call == "assigned") & ok, ""), source="placement")
    P = P[~P.source_acc.isin(T.source_acc)]
    R = pd.concat([T[["source_acc", "clade_id", "subclade_id", "source"]],
                   P[["source_acc", "clade_id", "subclade_id", "source", "clade_lwr", "clade_call"]]], ignore_index=True)
    R.loc[R.clade_id == "outgroup_heliorhodopsin", ["clade_id", "subclade_id"]] = ""
    # backbone named groups (MR_CLD3_Bnn) are top-level groups: promote to clade_id
    bb = (R.clade_id == "") & R.subclade_id.astype(str).str.contains("_B")
    R.loc[bb, "clade_id"] = R.loc[bb, "subclade_id"]
    R.loc[bb, "subclade_id"] = ""
    C = pd.read_csv(charf, sep="\t")
    C = C[C.exp_class.isin(EXP2V14)]
    if "e1_eligible" in C:   # v1.5.0 curator sign-off: downgraded records do not contribute to clade consensus
        C = C[C.e1_eligible.astype(str).isin(["True", "1"])]
    e1 = dict(zip(C.source_acc, C.exp_class.map(EXP2V14)))
    R["e1_class"] = R.source_acc.map(e1)
    rows = []
    for lvl, col in (("subclade", "subclade_id"), ("clade", "clade_id")):
        for g, d in R[R[col] != ""].groupby(col):
            f, n, fr, st = consensus(d.e1_class)
            rows.append(dict(level=lvl, group_id=g, n_records=len(d), n_E1=n, top_frac=round(fr, 3),
                             consensus_status=st, clade_function=f,
                             E1_classes=";".join(f"{k}:{v}" for k, v in d.e1_class.value_counts().items())))
    CF = pd.DataFrame(rows)
    fmap = {(r.level, r.group_id): r.clade_function for r in CF.itertuples()}
    fun, src = [], []
    for r in R.itertuples():
        f = fmap.get(("subclade", r.subclade_id)) if r.subclade_id else None
        s = r.subclade_id if f else ""
        if f is None and r.clade_id:
            f = fmap.get(("clade", r.clade_id)); s = r.clade_id if f else ""
        fun.append(f); src.append(s)
    R["clade_function"] = fun
    R["clade_function_source"] = src
    R.to_csv(out_r, sep="\t", index=False)
    CF.to_csv(out_c, sep="\t", index=False)
    print("records", len(R), "with clade", (R.clade_id != "").sum(), "with clade_function", R.clade_function.notna().sum())
    print(CF[CF.level == "clade"].to_string(index=False))


if __name__ == "__main__":
    main()
