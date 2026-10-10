#!/usr/bin/env python
"""Generate site/data.js for the static MicroRhodoDB browser (site/index.html + site/app.js).

The data are inlined as a JavaScript file (window.MRDB = {...}) so the browser works both from
disk (file://) and from any static host (GitHub Pages, Zenodo preview, institutional server).

  python tools/build_site_v160.py releases/v1.6.0/db/microrhododb_v1.6.0.sqlite site/
"""
import json
import os
import sqlite3
import sys

import pandas as pd

COLS = ["mrdb_acc", "source_acc", "protein_name", "organism", "tax_domain", "length", "membership_status",
        "membership_score", "retinal_site_residue", "func_class", "evidence_level", "function_basis",
        "func_class_v14", "helixC_motif", "motif_class", "call_conflict", "call_conflict_detail", "is_engineered",
        "wild_type_acc", "counts_eligible", "exact_duplicate_of", "e1_representative", "clade_id", "subclade_id",
        "clade_name", "tentative_clade_id", "tentative_clade_name", "gtdb_taxonomy", "afdb_model_id",
        "afdb_global_plddt"]


def clean(df):
    return df.astype(object).where(df.notna(), None)


def main(db, out):
    os.makedirs(out, exist_ok=True)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    v = pd.read_sql(f"SELECT {', '.join(COLS)} FROM v_master ORDER BY mrdb_acc, source_acc", con)
    extra = pd.read_sql("""SELECT p.source_acc, p.reviewed, p.sequence, m.representative_source_acc,
                                  f.e2_ref, f.e2_identity, f.override_rule, r.pocket_string_br
                           FROM protein p JOIN mrdb_accession m USING (mrdb_acc)
                           JOIN function_evidence f USING (source_acc)
                           LEFT JOIN retinal_pocket_summary r USING (source_acc)""", con)
    v = v.merge(extra, on="source_acc", how="left")
    v = v.merge(pd.read_sql("SELECT source_acc, status_reason FROM membership", con), on="source_acc", how="left")
    if con.execute("SELECT 1 FROM sqlite_master WHERE name='novel_family_flag'").fetchone():
        v = v.merge(pd.read_sql("SELECT source_acc, novel_family_hit AS novel_family_flag FROM novel_family_flag", con),
                    on="source_acc", how="left", validate="1:1")
    v["is_mrdb_representative"] = (v.source_acc == v.representative_source_acc).astype(int)
    v = v.drop(columns=["representative_source_acc"])
    v["membership_score"] = v.membership_score.round(3)
    v["afdb_global_plddt"] = v.afdb_global_plddt.round(1)
    v["e2_identity"] = pd.to_numeric(v.e2_identity, errors="coerce").round(3)
    v["clade_confidence"] = ["confident" if isinstance(c, str) and c else ("tentative" if isinstance(t, str) and t else "none")
                             for c, t in zip(v.clade_id, v.tentative_clade_id)]
    seqs = v.pop("sequence").tolist()
    v = clean(v)

    pubs = pd.read_sql("""SELECT a.source_acc, p.pmid, p.doi, p.title, p.journal, p.year, a.link_role,
                                 a.counts_as_support, a.verdict, a.caveat
                          FROM assertion_publication a JOIN publication p USING (publication_id)
                          WHERE a.is_active = 1 ORDER BY a.source_acc, a.counts_as_support DESC, p.year""", con)
    pubs["pmid"] = pubs.pmid.map(lambda x: str(int(x)) if pd.notna(x) else None)
    pubs["year"] = pubs.year.map(lambda x: int(x) if pd.notna(x) else None)
    pubs = clean(pubs)
    pub_map = {}
    for r in pubs.itertuples(index=False):
        pub_map.setdefault(r.source_acc, []).append([r.pmid, r.doi, r.title, r.journal, r.year, r.link_role,
                                                     r.counts_as_support, r.verdict, r.caveat])
    md = dict(con.execute("SELECT key, value FROM release_metadata WHERE release='1.6.0'").fetchall())
    status = clean(pd.read_sql("SELECT status, status_group, definition FROM status_definition", con)).to_dict("records")
    fcd = clean(pd.read_sql("SELECT func_class, definition, n_records FROM func_class_definition", con)).to_dict("records")
    clades = clean(pd.read_sql("SELECT clade_id, level, name, n_tips FROM clade WHERE level=1 ORDER BY clade_id",
                               con)).to_dict("records")
    funnel = clean(pd.read_sql("SELECT * FROM novel_family_funnel", con))
    cand = clean(pd.read_sql("SELECT * FROM novel_family_candidate", con))
    con.close()
    meta = {k: md.get(k) for k in ("version", "release_date", "license", "n_protein_records", "n_counted_records",
                                   "n_engineered_records", "evidence_level_counts_counted", "n_call_conflict",
                                   "n_conflict_downgrades", "n_novel_family_candidates", "n_typeI_member_curated",
                                   "n_novel_family_flag", "n_foldseek_hits", "audit_agreement_primary", "scope")}
    data = dict(meta=meta, columns=list(v.columns), rows=v.values.tolist(), seqs=seqs,
                pub_columns=["pmid", "doi", "title", "journal", "year", "link_role", "counts_as_support", "verdict",
                             "caveat"], pubs=pub_map, status=status, func_classes=fcd, clades=clades,
                novel=dict(funnel_columns=list(funnel.columns), funnel=funnel.values.tolist(),
                           candidate_columns=list(cand.columns), candidates=cand.values.tolist()))
    js = "/* MicroRhodoDB v%s browser data - generated by tools/build_site_v160.py; do not edit */\nwindow.MRDB=%s;\n" % (
        md.get("version"), json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    open(os.path.join(out, "data.js"), "w", encoding="utf-8").write(js)
    print(f"site/data.js: {len(v)} records, {sum(len(x) for x in pub_map.values())} publication links, "
          f"{len(js) / 1e6:.2f} MB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
