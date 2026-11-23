#!/usr/bin/env python
"""Re-derive the helix-C motif and motif class of every release record and compare them with the stored values.

`function_evidence.helixC_motif` / `motif_class` were carried from the v1.1 `function` table; the code that produced
them is not in the repository, and the v1.6.0 conflict rule (motif vs called class) depends on them. The motif is
re-derived from sequence by tools/helixc_motif.py (hmmalign against PF01036.25, BR D85/T89/D96 match states).

Checks
  - the stored motif_class is a function of the stored motif, and tools/helixc_motif.motif_class reproduces it;
  - re-derived motif and class against the stored ones, per UniProtKB source release;
  - the K216 residue read here against qc_feature.has_retinal_lysine, for non-heliorhodopsin records (the scorer
    reads heliorhodopsins on PF18761, not PF01036);
  - the v1.6.0 conflict rule (pipeline/v160/mrdb_v160_lib.conflict) applied with the re-derived motif to records
    whose stored motif is missing: which calls it would flag.

Usage: python pipeline/construction_review/helixc_motif.py <release db> <PF01036.hmm> <outdir>
"""
import os
import sqlite3
import sys
import tempfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
sys.path.insert(0, os.path.join(HERE, "..", "v160"))
import helixc_motif as hm          # noqa: E402
from mrdb_v160_lib import conflict  # noqa: E402


def main():
    db, hmm, outdir = sys.argv[1:4]
    os.makedirs(outdir, exist_ok=True)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rec = pd.read_sql("""SELECT p.source_acc, p.sequence, f.helixC_motif AS stored_motif, f.motif_class AS stored_class,
                                f.func_class, f.evidence_level, f.call_conflict,
                                q.has_retinal_lysine AS stored_lys, m.membership_status, s.source_release
                         FROM protein p JOIN function_evidence f USING(source_acc)
                         JOIN membership m USING(source_acc)
                         LEFT JOIN qc_feature q USING(source_acc)
                         LEFT JOIN (SELECT source_acc, MIN(source_release) AS source_release FROM sequence_source
                                    GROUP BY source_acc) s USING(source_acc)""", con)
    con.close()

    stored = rec.dropna(subset=["stored_motif"])
    n_cls = stored.groupby("stored_motif").stored_class.agg(lambda s: s.fillna("").nunique())
    if (n_cls > 1).any():
        sys.exit(f"stored motif_class is not a function of the motif: {n_cls[n_cls > 1].index.tolist()}")
    bad = stored[stored.stored_motif.map(hm.motif_class).fillna("") != stored.stored_class.fillna("")]
    if len(bad):
        sys.exit(f"motif -> class mapping disagrees with {len(bad)} stored records, e.g. "
                 f"{bad[['stored_motif', 'stored_class']].drop_duplicates().head().to_dict('records')}")

    seqs = {a: s.upper().replace("*", "") for a, s in zip(rec.source_acc, rec.sequence)}
    br = seqs[hm.BR_ACC]
    with tempfile.TemporaryDirectory() as wd:
        d = hm.derive(seqs, hmm, br, wd)
    rec = rec.drop(columns="sequence").merge(d, on="source_acc", how="left")
    rec["motif_match"] = rec.helixC_motif.fillna("") == rec.stored_motif.fillna("")
    rec["class_match"] = rec.motif_class.fillna("") == rec.stored_class.fillna("")
    rec["lysine_match"] = rec.res_K216.eq("K").astype(int) == rec.stored_lys.fillna(-1).astype(int)
    rec["conflict_with_rederived_motif"] = [conflict(c, m) for c, m in zip(rec.func_class, rec.motif_class)]

    out = ["source_acc", "source_release", "membership_status", "evidence_level", "func_class", "stored_motif",
           "helixC_motif", "stored_class", "motif_class", "res_K216", "stored_lys", "motif_match", "class_match",
           "lysine_match", "call_conflict", "conflict_with_rederived_motif"]
    rec[out].to_csv(f"{outdir}/helixc_motif_rederived.tsv", sep="\t", index=False)
    rec.loc[rec.stored_motif.isna(), out].to_csv(f"{outdir}/helixc_motif_missing_in_release.tsv", sep="\t", index=False)

    rows = []
    for rel, g in [("all", rec)] + list(rec.groupby("source_release")):
        rows += [dict(records=rel, check="stored motif present", k=int(g.stored_motif.notna().sum()), n=len(g)),
                 dict(records=rel, check="re-derived motif identical to stored", k=int(g.motif_match.sum()), n=len(g)),
                 dict(records=rel, check="re-derived motif_class identical to stored", k=int(g.class_match.sum()),
                      n=len(g))]
    nonhelio = rec[rec.membership_status.ne("heliorhodopsin") & rec.stored_lys.notna()]
    rows.append(dict(records="non-heliorhodopsin", check="K216 read agrees with qc_feature.has_retinal_lysine",
                     k=int(nonhelio.lysine_match.sum()), n=len(nonhelio)))
    summary = pd.DataFrame(rows)
    summary["fraction"] = (summary.k / summary.n).round(4)
    summary.to_csv(f"{outdir}/helixc_motif_summary.tsv", sep="\t", index=False)

    missing = rec[rec.stored_motif.isna()]
    print(summary.to_string(index=False))
    print(f"\nrecords without a stored motif: {len(missing)}; re-derived class:")
    print(missing.motif_class.fillna("(empty: deletion)").value_counts().to_string())
    called = missing[missing.evidence_level != "E5"]
    print(f"\ncalled records (E1-E4) among them, with the v1.6.0 conflict rule applied to the re-derived motif:")
    print(called[["source_acc", "evidence_level", "func_class", "helixC_motif", "motif_class",
                  "conflict_with_rederived_motif"]].to_string(index=False))


if __name__ == "__main__":
    main()
