#!/usr/bin/env python
"""Flat exports of a MicroRhodoDB v1.6.0 database (TSV + FASTA).

Tentative clade placements (R-M9) are made explicit in every export that carries a clade:
  clade_confidence  = confident | tentative | none
  clade_display     = <clade_id> for confident calls, 'TENTATIVE:<tentative_clade_id>' for tentative calls, '' otherwise
FASTA headers carry the same clade_display token.

Usage: python tools/export_tables_v160.py <db.sqlite> <out_dir>
"""
import os
import sqlite3
import sys

import pandas as pd


def clade_cols(df):
    conf = df.clade_id.fillna("").astype(str).str.len() > 0
    tent = ~conf & df.tentative_clade_id.notna()
    df.insert(df.columns.get_loc("clade_id"), "clade_confidence",
              ["confident" if c else ("tentative" if t else "none") for c, t in zip(conf, tent)])
    df.insert(df.columns.get_loc("clade_id"), "clade_display",
              [ci if c else (f"TENTATIVE:{ti}" if t else "") for ci, ti, c, t in
               zip(df.clade_id.fillna(""), df.tentative_clade_id, conf, tent)])
    return df


def main(db, out):
    os.makedirs(out, exist_ok=True)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rel = con.execute("SELECT value FROM release_metadata WHERE release='1.6.0' AND key='version'").fetchone()[0]
    files = {}
    rec = clade_cols(pd.read_sql("SELECT * FROM v_master ORDER BY mrdb_acc, source_acc", con))
    if con.execute("SELECT 1 FROM sqlite_master WHERE name='novel_family_flag'").fetchone():
        # precomputed family-HMM flag (R-V3; informational, does not change status)
        nff = pd.read_sql("SELECT source_acc, novel_family_hit AS novel_family_flag FROM novel_family_flag", con)
        rec = rec.merge(nff, on="source_acc", how="left", validate="1:1")
    files["records_v160.tsv"] = rec
    fe = pd.read_sql("SELECT * FROM function_evidence ORDER BY source_acc", con)
    files["function_evidence_v160.tsv"] = fe.merge(rec[["source_acc", "mrdb_acc", "clade_confidence", "clade_display"]],
                                                   on="source_acc", how="left")
    files["publication_links_v160.tsv"] = pd.read_sql(
        """SELECT a.source_acc, p2.mrdb_acc, a.link_role, a.counts_as_support, a.verdict, a.assertion, a.caveat,
                  p.publication_id, p.pmid, p.doi, p.title, p.journal, p.year, a.curator_decision, a.decided_at
           FROM assertion_publication a JOIN publication p USING (publication_id)
           LEFT JOIN protein p2 ON p2.source_acc = a.source_acc
           WHERE a.is_active = 1 ORDER BY a.source_acc, a.link_role, p.year""", con)
    files["call_conflicts_v160.tsv"] = clade_cols(pd.read_sql("SELECT * FROM v_call_conflict ORDER BY mrdb_acc", con))
    files["engineered_constructs_v160.tsv"] = pd.read_sql("SELECT * FROM v_engineered ORDER BY mrdb_acc", con)
    files["loco_validation_v160.tsv"] = pd.read_sql("SELECT * FROM loco_validation", con)
    files["novel_family_candidates_v160.tsv"] = pd.read_sql("SELECT * FROM novel_family_candidate", con)
    files["novel_family_funnel_v160.tsv"] = pd.read_sql("SELECT * FROM novel_family_funnel", con)
    for t, name in [("clade_function_consensus", "clade_function_consensus_v160.tsv"),
                    ("foldseek_hit", "foldseek_hits_v160.tsv"), ("foldseek_funnel", "foldseek_funnel_v160.tsv"),
                    ("audit_blind", "audit_blind_v160.tsv"), ("audit_agreement", "audit_agreement_v160.tsv")]:
        if con.execute("SELECT 1 FROM sqlite_master WHERE name=?", (t,)).fetchone():
            files[name] = pd.read_sql(f"SELECT * FROM {t}", con)
    files["func_class_definition_v160.tsv"] = pd.read_sql("SELECT * FROM func_class_definition", con)
    if con.execute("SELECT 1 FROM sqlite_master WHERE name='data_dictionary'").fetchone():
        files["data_dictionary_v160.tsv"] = pd.read_sql(
            "SELECT * FROM data_dictionary ORDER BY object_type, object_name, ordinal", con)
    for name, df in files.items():
        df.to_csv(os.path.join(out, name), sep="\t", index=False)
    seq = dict(con.execute("SELECT source_acc, sequence FROM protein"))
    with open(os.path.join(out, "sequences_v160.fasta"), "w") as f:
        for r in rec.itertuples():
            f.write(f">{r.mrdb_acc} {r.source_acc} status={r.membership_status} evidence={r.evidence_level} "
                    f"func={r.func_class} clade={r.clade_display or 'none'} engineered={r.is_engineered}\n")
            s = seq[r.source_acc]
            f.write("\n".join(s[i:i + 60] for i in range(0, len(s), 60)) + "\n")
    con.close()
    print(f"release {rel}: wrote {len(files) + 1} files to {out}; records={len(rec)} "
          f"tentative={int((rec.clade_confidence == 'tentative').sum())}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
