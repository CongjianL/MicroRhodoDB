#!/usr/bin/env python3
"""Flat-file exports of MicroRhodoDB v1.6.2.

The table exports are tools/export_tables_v160.py run on the v1.6.2 database, with the release suffix _v162 (the same
exporter reproduces every v1.6.1 table byte for byte). curation_v162_decision is exported as
construction_review_decisions_v162.tsv.

Usage: python pipeline/v162/export_v162.py <v1.6.2 db> <out dir>
"""
import os
import shutil
import sqlite3
import sys
import tempfile

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import export_tables_v160  # noqa: E402


def main(db, out):
    os.makedirs(out, exist_ok=True)
    with tempfile.TemporaryDirectory() as wd:
        export_tables_v160.main(db, wd)
        for f in sorted(os.listdir(wd)):
            shutil.copyfile(os.path.join(wd, f), os.path.join(out, f.replace("_v160", "_v162")))
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    pd.read_sql("SELECT * FROM curation_v162_decision ORDER BY decision_id", con).to_csv(
        os.path.join(out, "construction_review_decisions_v162.tsv"), sep="\t", index=False)
    con.close()
    print(f"{len(os.listdir(out))} files -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
