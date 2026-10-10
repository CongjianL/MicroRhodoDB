#!/usr/bin/env python
"""Map prokaryotic NCBI taxids to GTDB taxonomy.

For each protein.organism_id (NCBI taxid): collect GTDB genomes with ncbi_taxid == taxid (level 'strain_or_exact');
if none, genomes with ncbi_species_taxid == taxid or with ncbi_species_taxid equal to the species taxid of the
exact-matched genomes (level 'species_taxid'). The assigned GTDB taxonomy is the majority string; the agreement
fraction and the number of genomes are reported. Representative genomes are not required.
Usage: gtdb_map.py db.sqlite gtdb_dir out.tsv
"""
import sys, sqlite3, os
import pandas as pd


def main():
    db, gdir, out = sys.argv[1:4]
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    p = pd.read_sql("select source_acc, organism, organism_id, tax_domain from protein "
                    "where tax_domain in ('Bacteria','Archaea')", con)
    cols = ["accession", "gtdb_taxonomy", "ncbi_taxid", "ncbi_species_taxid", "gtdb_representative"]
    g = pd.concat([pd.read_csv(os.path.join(gdir, f), sep="\t", usecols=lambda c: c in cols, low_memory=False)
                   for f in ("ar53_metadata.tsv.gz", "bac120_metadata.tsv.gz")], ignore_index=True)
    ver = open(os.path.join(gdir, "VERSION.txt")).read().strip().splitlines()[0]
    g["ncbi_taxid"] = pd.to_numeric(g.ncbi_taxid, errors="coerce")
    g["ncbi_species_taxid"] = pd.to_numeric(g.ncbi_species_taxid, errors="coerce")

    def consensus(sub):
        vc = sub.gtdb_taxonomy.value_counts()
        return vc.index[0], vc.iloc[0] / vc.sum(), int(vc.sum())

    ex = {t: s for t, s in g.groupby("ncbi_taxid")}
    sp = {t: s for t, s in g.groupby("ncbi_species_taxid")}
    rows = []
    for t in p.organism_id.dropna().astype(int).unique():
        if t in ex:
            tax, fr, n = consensus(ex[t]); lvl = "exact_taxid"
        elif t in sp:
            tax, fr, n = consensus(sp[t]); lvl = "species_taxid"
        else:
            tax, fr, n, lvl = None, None, 0, "unmapped"
        rows.append((t, tax, fr, n, lvl))
    m = pd.DataFrame(rows, columns=["organism_id", "gtdb_taxonomy", "gtdb_agreement", "gtdb_n_genomes", "gtdb_match_level"])
    m["gtdb_release"] = ver
    r = p.merge(m, on="organism_id", how="left")
    r.loc[r.gtdb_match_level.isna(), "gtdb_match_level"] = "no_taxid"
    for i, k in enumerate(["d", "p", "c", "o", "f", "g", "s"]):
        r[f"gtdb_{k}"] = r.gtdb_taxonomy.str.split(";").str[i].str[3:]
    r.to_csv(out, sep="\t", index=False)
    print(ver, r.gtdb_match_level.value_counts().to_dict(), "agreement<1:", int((r.gtdb_agreement < 1).sum()))


if __name__ == "__main__":
    main()
