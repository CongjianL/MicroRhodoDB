#!/usr/bin/env python
"""Column-by-column comparison of reimpl_records.tsv against production habitat_record_availability.tsv."""
import os
import sys
import pandas as pd

OUT = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(OUT)
P = pd.read_csv(os.path.join(BASE, "habitat_record_availability.tsv"), sep="\t", dtype=str, keep_default_na=False)
M = pd.read_csv(os.path.join(OUT, os.environ.get("REIMPL_FILE", "reimpl_records.tsv")), sep="\t", dtype=str, keep_default_na=False)
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


def compare():
    res = []
    for c in COLS:
        a = P[c].map(lambda v: norm(c, v))
        b = M[c].map(lambda v: norm(c, v))
        eq = a == b
        res.append((c, int(eq.sum()), len(P), list(P.index[~eq][:5])))
    return res


if __name__ == "__main__":
    for c, n, N, ex in compare():
        print("%-32s %5d/%d %s" % (c, n, N, "" if n == N else ex))
    if len(sys.argv) > 1:
        c = sys.argv[1]
        a = P[c].map(lambda v: norm(c, v))
        b = M[c].map(lambda v: norm(c, v))
        bad = P.index[a != b]
        k = int(sys.argv[2]) if len(sys.argv) > 2 else 15
        for acc in bad[:k]:
            print("--", acc, "| PROD:", P.at[acc, c], "| REIMPL:", M.at[acc, c])
