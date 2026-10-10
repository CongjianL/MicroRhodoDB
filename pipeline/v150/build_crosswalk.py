#!/usr/bin/env python3
"""
build_crosswalk.py - MR_CLD3 <-> MR_CLD2 <-> MicRhoDE cluster crosswalk, at both the clade and
subclade level.

Plan WP4 requires: "Outputs: a `subfamily_name` column and an MR_CLD3 <-> MR_CLD2 <-> MicRhoDE
cluster crosswalk, including a finer PR subclade level." This script produces that table at BOTH
granularities in one pass: one row per (new-scheme clade or subclade, old-scheme other_id) pair
that shares >=1 member, with the member-overlap fractions in both directions.

Method: intersect record_clade_v150's `source_acc` membership (per clade_id, and separately per
subclade_id where assigned) against (a) the v1.4.0 release's `placement_v140.clade_id` (MR_CLD2
scheme) and (b) the MicRhoDE-to-MRDB accession mapping's supercluster|cluster label, restricted to
>=90% identity hits (the same confidence threshold used elsewhere in this release for ortholog
transfer, e.g. function_evidence_level E2).

Usage:
  python build_crosswalk.py --record_clade /workspace/v150/clades/record_clades.tsv \
      --v140_db /workspace/MicroRhodoDB/releases/v1.4.0/db/microrhododb_v1.4.0.sqlite \
      --micrhode_map /mnt/results/micrhode_comparison/micrhode_to_mrdb_mapping.tsv \
      --out /workspace/v150/clades/clade_crosswalk.tsv

Output columns: clade_id (clade_id for level=clade rows, subclade_id for level=subclade rows),
scheme (MR_CLD2 | MicRhoDE_cluster), other_id, n_shared, frac_of_mr_cld3 (n_shared / size of the
MR_CLD3 clade_id or subclade_id), frac_of_other (n_shared / size of other_id), level (clade |
subclade), parent_clade_id (always the top-level MR_CLD3_0XX clade, for both levels).
"""
import argparse
import sqlite3

import pandas as pd


def crosswalk_rows(membership: pd.DataFrame, other: pd.DataFrame, scheme: str) -> list[dict]:
    """membership: columns [source_acc, clade_id] (clade_id may hold a clade_id or subclade_id
    value depending on the granularity being crosswalked). other: columns [source_acc, other_id]."""
    j = membership.merge(other, on="source_acc")
    n3 = j.groupby("clade_id").size()
    no = j.groupby("other_id").size()
    rows = []
    for (a, b), n in j.groupby(["clade_id", "other_id"]).size().items():
        rows.append(
            dict(
                clade_id=a,
                scheme=scheme,
                other_id=b,
                n_shared=int(n),
                frac_of_mr_cld3=round(n / n3[a], 3),
                frac_of_other=round(n / no[b], 3),
            )
        )
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--record_clade", required=True, help="record_clade TSV with source_acc, clade_id, subclade_id columns")
    ap.add_argument("--v140_db", required=True, help="path to the immutable v1.4.0 release sqlite (opened read-only)")
    ap.add_argument("--micrhode_map", required=True, help="micrhode_to_mrdb_mapping.tsv (bestUP_sseqid/bestUP_pident/best_sseqid/best_pident/supercluster/cluster columns)")
    ap.add_argument("--out", required=True, help="output clade_crosswalk.tsv path")
    ap.add_argument("--min_pident", type=float, default=90.0, help="minimum %% identity for a MicRhoDE ortholog match to count (default 90, matching E2 ortholog-transfer threshold elsewhere in this release)")
    args = ap.parse_args()

    rc = pd.read_csv(args.record_clade, sep="\t")

    con = sqlite3.connect(f"file:{args.v140_db}?mode=ro", uri=True)
    c2 = pd.read_sql("select source_acc, clade_id as other_id from placement_v140 where clade_id is not null", con)
    con.close()

    md = pd.read_csv(args.micrhode_map, sep="\t", low_memory=False)
    md = md[md.best_pident >= args.min_pident].copy()
    md["source_acc"] = md.bestUP_sseqid.where(md.bestUP_pident >= args.min_pident, md.best_sseqid)
    mc = md.assign(other_id=md.supercluster.fillna("") + " | " + md.cluster.fillna(""))[["source_acc", "other_id"]]

    sources = [("MR_CLD2", c2), ("MicRhoDE_cluster", mc)]

    # clade level
    rc_clade = rc[rc.clade_id.notna() & (rc.clade_id != "")][["source_acc", "clade_id"]]
    clade_rows = []
    for scheme, o in sources:
        clade_rows += crosswalk_rows(rc_clade, o, scheme)
    CW = pd.DataFrame(clade_rows)
    CW["level"] = "clade"
    CW["parent_clade_id"] = CW.clade_id

    # subclade level (finer PR / general subclade resolution)
    rc_sub = rc[rc.subclade_id.notna() & (rc.subclade_id.astype(str) != "")][["source_acc", "subclade_id"]].rename(
        columns={"subclade_id": "clade_id"}
    )
    sub_rows = []
    for scheme, o in sources:
        sub_rows += crosswalk_rows(rc_sub, o, scheme)
    SUBCW = pd.DataFrame(sub_rows)
    SUBCW["level"] = "subclade"
    SUBCW["parent_clade_id"] = SUBCW.clade_id.str.slice(0, 11)  # "MR_CLD3_0XX" is always 11 chars

    OUT = pd.concat([CW, SUBCW], ignore_index=True).sort_values(
        ["level", "scheme", "clade_id", "n_shared"], ascending=[True, True, True, False]
    )
    OUT.to_csv(args.out, sep="\t", index=False)
    print(
        f"wrote {args.out}: {len(OUT)} rows "
        f"(clade-level {(OUT.level == 'clade').sum()}, subclade-level {(OUT.level == 'subclade').sum()}; "
        f"{OUT.parent_clade_id.nunique()} distinct parent clades, {OUT.clade_id.nunique()} distinct clade/subclade ids)"
    )


if __name__ == "__main__":
    main()
