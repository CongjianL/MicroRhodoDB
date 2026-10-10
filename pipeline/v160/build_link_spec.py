"""Addendum step 2: labelling spec for compilation links.
Every characterized_protein row that cites one of the two lambda-max compilations gets an explicit
assertion_publication row with link_role='compilation' and counts_as_support=0, so a compilation can never
count as functional support. Records with no verified primary functional paper are additionally marked
curator_decision='deferred'. Spec only: applied in the Stage 2 build after approval."""
import os as _os
_REPO = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
_W160 = _os.environ.get("MRDB_V160_WORK", _os.path.join(_REPO, "work", "v160_stage1"))  # Stage-1 scratch dir
import sqlite3
import pandas as pd

DB = _os.path.join(_REPO, "releases/v1.5.0/db/microrhododb_v1.5.0.sqlite")
W = _os.path.join(_W160, "addendum")
c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
add = pd.read_csv(f"{W}/curation_v160_addendum_citations.tsv", sep="\t", dtype=str)
cp = pd.read_sql("select source_acc, protein_label, pmid, doi from characterized_protein", c)
fe = pd.read_sql("select source_acc, evidence_level from function_evidence", c)
prot = pd.read_sql("select source_acc, mrdb_acc from protein", c)
ap = pd.read_sql("select source_acc, count(*) n_links, sum(counts_as_support) n_support from assertion_publication where is_active=1 group by source_acc", c)
COMP = {"30349080": ("30349075", "10.1038/s41598-018-33984-w", "Karasuyama 2018 Sci Rep"),
        "33741996": ("33742139", "10.1038/s42003-021-01878-9", "Inoue 2021 Commun Biol")}

grp = {}
for r in add.itertuples():
    for a in str(r.source_acc).split(";"):
        if not a.startswith("["):
            grp.setdefault(a, r.group_id)
targets = set(pd.read_csv(f"{W}/targets.tsv", sep="\t").source_acc)

rows = []
for r in cp.itertuples():
    toks = [x for x in str(r.pmid).split(";") if x]
    for w, (pm, doi, cite) in COMP.items():
        if w not in toks:
            continue
        g = grp.get(r.source_acc, "")
        if r.source_acc in targets:
            if g in ("ADD-A_primary_found", "ADD-B_duplicate_inherit"):
                dec, status = "spectral_source_only", "resolved_primary_added"
            elif g == "ADD-C_no_primary_retier":
                dec, status = "deferred", "no_primary_found (E1 withdrawn if RETIER approved)"
            elif g == "ADD-D_unverified_manual":
                dec, status = "deferred", "candidate_primary_unverified"
            else:
                dec, status = "deferred", "unresolved"
        else:
            other = [x for x in toks if x not in COMP and x != "0000269"] + \
                    [x for x in str(r.doi).split(";") if x and x != "None" and x not in {v[1] for v in COMP.values()}]
            dec, status = ("spectral_source_only", "non_target_has_other_citation") if other else \
                          ("spectral_source_only", "non_target_compilation_only (lambda-max only; function tier from pipeline, not E1)")
        rows.append(dict(source_acc=r.source_acc, protein_label=r.protein_label, publication_pmid=pm, publication_doi=doi,
                         publication=cite, link_role="compilation", counts_as_support=0, is_active=1,
                         curator_decision=dec, record_status=status, addendum_group=g,
                         curator_note=f"Lambda-max compilation (no per-protein reference); PMID corrected from {w}. Not functional evidence."))
spec = pd.DataFrame(rows).merge(prot, on="source_acc", how="left").merge(fe, on="source_acc", how="left").merge(ap, on="source_acc", how="left")
spec[["n_links", "n_support"]] = spec[["n_links", "n_support"]].fillna(0).astype(int)
spec = spec[["source_acc", "mrdb_acc", "protein_label", "evidence_level", "publication_pmid", "publication_doi", "publication",
             "link_role", "counts_as_support", "is_active", "curator_decision", "record_status", "addendum_group",
             "n_links", "n_support", "curator_note"]].sort_values(["curator_decision", "evidence_level", "source_acc"])
spec.to_csv(f"{W}/link_labelling_spec_v160.tsv", sep="\t", index=False)

rec = spec.drop_duplicates("source_acc")
summ = []
summ.append(("compilation link rows to add", len(spec)))
summ.append(("records citing a compilation", rec.source_acc.nunique()))
for lvl, n in rec.evidence_level.value_counts().sort_index().items():
    summ.append((f"  of which function evidence {lvl}", n))
summ.append(("records with no functional support link before addendum (n_support=0)", int((rec.n_support == 0).sum())))
for k, n in rec.drop_duplicates("source_acc").record_status.value_counts().items():
    summ.append((f"record_status: {k}", n))
e1d = rec[(rec.evidence_level == "E1") & (rec.curator_decision == "deferred")]
summ.append(("E1 records left deferred after addendum (if RETIER rejected)", len(e1d)))
summ.append(("E1 records left deferred after addendum (if RETIER approved)", int((e1d.addendum_group == "ADD-D_unverified_manual").sum())))
summ.append(("plus O74870 (P026, outside this pass) stays DEFER", 1))
s = pd.DataFrame(summ, columns=["item", "n"])
s.to_csv(f"{W}/link_labelling_counts_v160.tsv", sep="\t", index=False)
print(s.to_string(index=False))
