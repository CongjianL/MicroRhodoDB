#!/usr/bin/env python
"""Cell-by-cell comparison of the round-3 independent re-implementation against production.

Usage: python compare3.py REIMPL_DIR PROD_DIR
       (or env VAL_REIMPL / VAL_PROD)
REIMPL_DIR: reimpl3_records.tsv, reimpl3_evidence.tsv
PROD_DIR:   habitat_record_availability.tsv, habitat_evidence.tsv
Prints the full comparison log to stdout.
"""
import os
import sys
from collections import Counter

import pandas as pd

RE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("VAL_REIMPL", ".")
PR = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("VAL_PROD", ".")
MAXEX = 50


def read(p):
    return pd.read_csv(p, sep="\t", dtype=str, keep_default_na=False, na_filter=False)


def compare(a, b, key, label, skip=()):
    print("=" * 100)
    print("%s: reimpl rows=%d, production rows=%d" % (label, len(a), len(b)))
    ka, kb = set(a[key]), set(b[key])
    print("keys only in reimpl: %d; only in production: %d; shared: %d" % (len(ka - kb), len(kb - ka), len(ka & kb)))
    for k in sorted(ka - kb)[:20]:
        print("  only reimpl:", k)
    for k in sorted(kb - ka)[:20]:
        print("  only production:", k)
    if a[key].duplicated().any() or b[key].duplicated().any():
        print("WARNING duplicated keys: reimpl %d, production %d" % (a[key].duplicated().sum(),
                                                                     b[key].duplicated().sum()))
    shared_cols = [c for c in a.columns if c in b.columns and c != key and c not in skip]
    print("reimpl-only columns:", [c for c in a.columns if c not in b.columns])
    print("shared columns compared (%d):" % len(shared_cols), shared_cols)
    a2 = a.set_index(key)
    b2 = b.set_index(key)
    keys = sorted(ka & kb)
    a2 = a2.loc[keys]
    b2 = b2.loc[keys]
    per_col = Counter()
    examples = []
    for c in shared_cols:
        diff = a2[c] != b2[c]
        n = int(diff.sum())
        per_col[c] = n
        for k in list(diff[diff].index):
            examples.append((c, k, a2.at[k, c], b2.at[k, c]))
    total = sum(per_col.values())
    print("cells compared: %d; mismatching cells: %d" % (len(keys) * len(shared_cols), total))
    print("per-column mismatch counts:")
    for c in shared_cols:
        print("  %-32s %d" % (c, per_col[c]))
    rows_with_mismatch = len({e[1] for e in examples})
    print("rows with >=1 mismatching cell: %d of %d" % (rows_with_mismatch, len(keys)))
    print("mismatch examples (up to %d):" % MAXEX)
    for c, k, x, y in examples[:MAXEX]:
        print("  [%s] %s\n      reimpl    : %r\n      production: %r" % (c, k, x[:300], y[:300]))
    return per_col, examples


def main():
    ra = read(os.path.join(RE, "reimpl3_records.tsv"))
    rb = read(os.path.join(PR, "habitat_record_availability.tsv"))
    compare(ra, rb, "source_acc", "RECORD TABLE")

    ea = read(os.path.join(RE, "reimpl3_evidence.tsv"))
    eb = read(os.path.join(PR, "habitat_evidence.tsv"))
    compare(ea, eb, "evidence_id", "EVIDENCE TABLE")
    print("=" * 100)
    print("value_status distribution (reimpl vs production):")
    va, vb = ea["value_status"].value_counts(), eb["value_status"].value_counts()
    for s in sorted(set(va.index) | set(vb.index)):
        print("  %-60s %7d %7d" % (s, va.get(s, 0), vb.get(s, 0)))
    print("invalid_placeholder rows (production):")
    for _, r in eb[eb["value_status"] == "invalid_placeholder"].iterrows():
        print("  %s %s %s %s %r" % (r["evidence_id"], r["source_acc"], r["evidence_source"], r["role"],
                                    r["value_original"]))
    # literature rows: compare by (source_acc, value_original, field_original) independent of evidence_id
    la = ea[ea["evidence_source"] == "literature"]
    lb = eb[eb["evidence_source"] == "literature"]
    ja = set(zip(la["source_acc"], la["field_original"], la["value_original"], la["role"], la["value_status"]))
    jb = set(zip(lb["source_acc"], lb["field_original"], lb["value_original"], lb["role"], lb["value_status"]))
    print("literature rows: reimpl %d, production %d; content tuples only reimpl %d, only production %d"
          % (len(la), len(lb), len(ja - jb), len(jb - ja)))
    for t in sorted(jb - ja)[:10]:
        print("  only production:", t[0], t[1][:60], t[3], t[4])
    for t in sorted(ja - jb)[:10]:
        print("  only reimpl:", t[0], t[1][:60], t[3], t[4])

    # ---------------------------------------------------------------------------------
    # Residual analysis (does not change the raw counts above)
    # ---------------------------------------------------------------------------------
    print("=" * 100)
    print("RESIDUAL ANALYSIS")
    # 1. literature evidence ids that differ: pair by content and test the null-DOI serialization
    ka = (la["source_acc"] + "\x1f" + la["field_original"] + "\x1f" + la["value_original"])
    kb = (lb["source_acc"] + "\x1f" + lb["field_original"] + "\x1f" + lb["value_original"])
    pa = dict(zip(ka, la["evidence_id"]))
    pb = dict(zip(kb, lb["evidence_id"]))
    idmap = {pa[k]: pb[k] for k in pa if k in pb and pa[k] != pb[k]}
    print("literature rows paired by (source_acc, field_original, value_original) with different evidence_id: %d"
          % len(idmap))
    base = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("VAL_BASE", "")
    if base and os.path.exists(os.path.join(base, "literature_evidence.json")):
        import hashlib
        import json
        lit = json.load(open(os.path.join(base, "literature_evidence.json")))
        ok = 0
        for k, rid in pa.items():
            if rid not in idmap:
                continue
            acc, fo, q = k.split("\x1f")
            it = [i for i in lit[acc]["items"] if i.get("quote") == q][0]
            s = "%s|%s|%s|%s%s" % (it.get("pmid"), it.get("doi"), it.get("quote"), it.get("scope"), acc)
            h = "HL" + hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]
            note = "pmid=%r doi=%r" % (it.get("pmid"), it.get("doi"))
            print("  %s %s reimpl=%s production=%s; str(None)-serialized hash=%s match=%s (%s)"
                  % (acc, it.get("scope"), rid, idmap[rid], h, h == idmap[rid], note))
            ok += h == idmap[rid]
        print("  differing literature ids reproduced when a null pmid/doi is serialized as 'None': %d of %d"
              % (ok, len(idmap)))
    # 2. record evidence_ids after mapping the differing literature ids
    ra2 = ra.set_index("source_acc")
    rb2 = rb.set_index("source_acc")
    mapped = ra2["evidence_ids"].apply(lambda s: ";".join(sorted(idmap.get(x, x) for x in s.split(";") if x)))
    print("record evidence_ids mismatches after literature-id mapping: %d"
          % int((mapped != rb2.loc[mapped.index, "evidence_ids"]).sum()))
    # 3. per-item envo_ids order
    m = ea.merge(eb, on="evidence_id", suffixes=("_r", "_p"))
    d = m[m["envo_ids_r"] != m["envo_ids_p"]]
    srt = d["envo_ids_r"].apply(lambda s: ";".join(sorted(s.split(";"))))
    print("evidence envo_ids mismatches: %d; equal after sorting the reimpl IDs: %d"
          % (len(d), int((srt == d["envo_ids_p"]).sum())))
    # 4. literature-only columns not defined by the dictionary
    for c in ("entity_accession", "linkage_route", "mapping_confidence"):
        dd = m[(m[c + "_r"] != m[c + "_p"])]
        print("column %s mismatches: %d (evidence_source of mismatching rows: %s)"
              % (c, len(dd), dict(Counter(dd["evidence_source_r"]))))
        if len(dd):
            print("   production values for literature rows (examples):",
                  sorted(set(dd[c + "_p"]))[:5])


if __name__ == "__main__":
    main()
