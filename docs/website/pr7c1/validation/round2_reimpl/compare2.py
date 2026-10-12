#!/usr/bin/env python
"""Round 2: column-by-column comparison of reimpl2_records.tsv against production round2/habitat_record_availability.tsv,
plus an evidence-row check against round2/habitat_evidence.tsv. Writes compare2.txt."""
import os
import sys
import pandas as pd

OUT = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(OUT)  # .../validation/round2 (production round-2 outputs)
P = pd.read_csv(os.path.join(BASE, "habitat_record_availability.tsv"), sep="\t", dtype=str, keep_default_na=False)
M = pd.read_csv(os.path.join(OUT, "reimpl2_records.tsv"), sep="\t", dtype=str, keep_default_na=False)
P = P.set_index("source_acc")
M = M.set_index("source_acc").loc[P.index]

COLS = ["primary_grade", "db_habitat_status", "db_chain_status", "literature_status", "not_reported_scope",
        "has_usable_habitat", "conflict_roles", "conflict_scope", "conflict_kind", "linkage_route",
        "mapping_confidence", "sample_type", "flags", "env_broad_scale_normalized", "env_local_scale_normalized",
        "env_medium_normalized", "isolation_source_normalized", "host_normalized", "sample_material",
        "habitat_nonstandard", "biosamples",
        # extra columns also compared (beyond the required list)
        "chain_failures", "env_broad_scale_original", "env_local_scale_original", "env_medium_original",
        "isolation_source_original", "host_original", "env_broad_scale_envo_ids", "env_local_scale_envo_ids",
        "env_medium_envo_ids", "isolation_source_envo_ids", "host_envo_ids", "country", "lat_lon", "lat", "lon",
        "collection_date", "depth", "molecule_types"]
SEMI = {"conflict_roles", "conflict_scope", "conflict_kind", "linkage_route", "flags", "biosamples",
        "chain_failures", "molecule_types"} | {c for c in COLS if c.endswith("_envo_ids")}


def norm(c, v):
    if c in SEMI:
        return frozenset(x for x in v.split(";") if x)
    if " || " in v or c not in ("primary_grade",):
        return frozenset(x for x in v.split(" || ") if x) if v else frozenset()
    return v


def compare(lines):
    total_bad = set()
    bad_cols = []
    lines.append("== Record table: %d production records, %d reimpl records, %d columns compared" % (len(P), len(M), len(COLS)))
    for c in COLS:
        a = P[c].map(lambda v: norm(c, v))
        b = M[c].map(lambda v: norm(c, v))
        eq = a == b
        n = int(eq.sum())
        lines.append("%-32s %5d/%d %s" % (c, n, len(P), "MATCH" if n == len(P) else "MISMATCH"))
        if n != len(P):
            bad_cols.append(c)
            for acc in P.index[~eq]:
                total_bad.add(acc)
    lines.append("")
    lines.append("== Mismatching cells (every record)")
    for c in bad_cols:
        a = P[c].map(lambda v: norm(c, v))
        b = M[c].map(lambda v: norm(c, v))
        for acc in P.index[a != b]:
            lines.append("-- %s | %s | PROD: %r | REIMPL: %r" % (c, acc, P.at[acc, c], M.at[acc, c]))
    lines.append("")
    lines.append("Columns with mismatches: %d; records with any mismatch: %d" % (len(bad_cols), len(total_bad)))
    return bad_cols, total_bad


def compare_evidence(lines):
    """Evidence check. evidence_id hashes field_original, whose presentation for NCBI harmonized attributes and for
    title/description/package/scientific_name is not specified in the dictionary, so rows are matched on the
    content key (source_acc, evidence_source, entity_accession, link_index, role, value_original)."""
    from collections import Counter
    pe = pd.read_csv(os.path.join(BASE, "habitat_evidence.tsv"), sep="\t", dtype=str, keep_default_na=False)
    me = pd.read_csv(os.path.join(OUT, "reimpl2_evidence.tsv"), sep="\t", dtype=str, keep_default_na=False)
    pe = pe[pe.evidence_source != "literature"]
    lines.append("")
    lines.append("== Evidence rows (database items only; literature rows are not re-implemented)")
    lines.append("production DB rows: %d; reimpl rows: %d" % (len(pe), len(me)))
    ids_same = len(set(pe.evidence_id) & set(me.evidence_id))
    lines.append("identical evidence_id: %d (ids differ where field_original presentation differs)" % ids_same)
    K = ["source_acc", "evidence_source", "entity_accession", "link_index", "role", "value_original"]
    cp = Counter(map(tuple, pe[K].values))
    cm = Counter(map(tuple, me[K].values))
    dp, dm = cp - cm, cm - cp
    lines.append("content-key multiset: rows only in production %d; rows only in reimpl %d"
                 % (sum(dp.values()), sum(dm.values())))
    for k, v in dp.items():
        lines.append("   PROD-only x%d %r" % (v, k))
    for k, v in dm.items():
        lines.append("   REIMPL-only x%d %r" % (v, k))
    # field_original presentation differences (summary)
    fo = pe.merge(me, on=K, suffixes=("_p", "_m"))
    fo = fo[fo.field_original_p != fo.field_original_m]
    pat = Counter()
    for a, b in zip(fo.field_original_p, fo.field_original_m):
        a2 = "<name> (harmonized: <h>)" if "(harmonized:" in a else a
        pat[(a2, b if a2 != a else b)] += 1
    lines.append("field_original presentation differences on content-matched rows: %d" % len(fo))
    agg = Counter()
    for (a, b), n in pat.items():
        agg[a if a.startswith("<name>") else "%s <- reimpl %s" % (a, b)] += n
    for k, n in agg.most_common():
        lines.append("   %6d  PROD %s" % (n, k))
    # field values on content-key-unique rows
    pu = pe[pe.duplicated(K, keep=False) == False].set_index(K)
    mu = me[me.duplicated(K, keep=False) == False].set_index(K)
    common = pu.index.intersection(mu.index)
    nbad = 0
    for c in ["value_status", "value_normalized", "envo_ids", "mapping_confidence"]:
        a = pu.loc[common, c]
        b = mu.loc[common, c]
        if c == "envo_ids":
            a = a.map(lambda v: frozenset(x for x in v.split(";") if x))
            b = b.map(lambda v: frozenset(x for x in v.split(";") if x))
        eq = (a.values == b.values)
        lines.append("  %-20s %6d/%d" % (c, int(eq.sum()), len(common)))
        if not eq.all():
            bad = [(k, a.iloc[n], b.iloc[n]) for n, k in enumerate(common) if not eq[n]]
            nbad += len(bad)
            summ = Counter((k[4], k[5].strip().lower(), pa, pb) for k, pa, pb in bad)
            lines.append("     summary (role, value, PROD, REIMPL): count")
            for t, n in summ.most_common():
                lines.append("       %r: %d" % (t, n))
            for k, pa, pb in bad:
                lines.append("     %s %s %s %s %r | PROD: %r | REIMPL: %r" % (k[0], k[1], k[2], k[4], k[5], pa, pb))
    return sum(dp.values()), sum(dm.values()), nbad


if __name__ == "__main__":
    lines = []
    bad_cols, bad_recs = compare(lines)
    op, om, nb = compare_evidence(lines)
    verdict = "EXACT_MATCH" if not bad_cols else "MISMATCH"
    lines.append("")
    lines.append("VERDICT (record table, %d columns): %s" % (len(COLS), verdict))
    lines.append("Evidence (content key): %d prod-only rows, %d reimpl-only rows, %d field-value mismatches" % (op, om, nb))
    txt = "\n".join(lines) + "\n"
    open(os.path.join(OUT, "compare2.txt"), "w").write(txt)
    print(txt)
