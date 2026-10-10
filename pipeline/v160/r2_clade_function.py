#!/usr/bin/env python
"""Recompute clade_function from the v1.6.0 E1 set with the unchanged v1.5.0 consensus rule (record_clades.py).

Rule (v1.5.0, unchanged): E1 records (non-engineered, e1_eligible, exp_class mapped to v1.4 classes) vote per group;
a group has a clade function if it has >= 2 E1 records and >= 80% agree. A record takes its subclade's function if
the subclade has one, else its level-1 clade's function, else none.

Usage:
  r2_clade_function.py DB OUT_CLADE_FUNCTION_TSV OUT_RECORD_TSV
DB is read-only. The record table holds clade_function / clade_function_source for every record in record_clade.
Imported by build_v160.py (function recompute()).
"""
import sys, os, sqlite3
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mrdb_v160_lib import EXP2V14


def consensus(classes, min_n=2, min_frac=0.8):
    s = pd.Series(classes).dropna()
    if len(s) == 0:
        return None, 0, 0.0, "no_E1"
    vc = s.value_counts()
    frac = vc.iloc[0] / len(s)
    if len(s) >= min_n and frac >= min_frac:
        return vc.index[0], len(s), frac, "consensus"
    return None, len(s), frac, ("mixed" if len(vc) > 1 else "single_E1")


def recompute(rc, e1map):
    """rc: DataFrame source_acc, clade_id, subclade_id (record_clade); e1map: {source_acc: exp_class} (E1 set used).
    Returns (CF table, per-record DataFrame with clade_function, clade_function_source)."""
    R = rc[["source_acc", "clade_id", "subclade_id"]].copy().fillna("")
    R["e1_class"] = R.source_acc.map({a: EXP2V14[e] for a, e in e1map.items() if e in EXP2V14})
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
        fun.append(f); src.append(s if s else None)
    R["clade_function"] = fun
    R["clade_function_source"] = src
    return CF, R.drop(columns=["e1_class"])


def e1_from_db(con):
    cp = pd.read_sql("select source_acc, exp_class, e1_eligible from characterized_protein", con)
    eng = set(pd.read_sql("select source_acc from function_evidence where is_engineered = 1", con).source_acc)
    cp = cp[cp.exp_class.isin(EXP2V14) & (cp.e1_eligible.astype(float) == 1) & ~cp.source_acc.isin(eng)]
    return dict(zip(cp.source_acc, cp.exp_class))


if __name__ == "__main__":
    db, out_c, out_r = sys.argv[1:4]
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rc = pd.read_sql("select source_acc, clade_id, subclade_id from record_clade", con)
    CF, R = recompute(rc, e1_from_db(con))
    CF.to_csv(out_c, sep="\t", index=False)
    R.to_csv(out_r, sep="\t", index=False)
    print("records", len(R), "with clade_function", R.clade_function.notna().sum())
