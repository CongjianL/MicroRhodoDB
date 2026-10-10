#!/usr/bin/env python3
"""MicroRhodoDB v1.6.0 data dictionary.

Introspects every table and view column of the v1.6.0 SQLite database, merges curated
definitions and writes (i) the `data_dictionary` table into the database and (ii) a flat TSV.

Usage:
  python data_dictionary_v160.py <db> profile <out_profile.tsv>
      -> per-column profile (type, row count, non-null, distinct, examples) for drafting definitions
  python data_dictionary_v160.py <db> build <table_defs.tsv> <column_defs.tsv> <out_dictionary.tsv>
      -> writes data_dictionary into <db>; fails (exit 1) unless coverage is 100%

Column definition lookup order: (table, column) exact row, then ('*', column) shared row.
For views, a column without its own row inherits the definition of the same column name
in the view's source tables (resolved through the shared '*' rows or v_master).
"""
import sqlite3
import sys

import pandas as pd

SKIP = {"sqlite_sequence", "data_dictionary"}


def objects(con):
    q = "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY type, name"
    return [(n, t) for n, t in con.execute(q) if n not in SKIP and not n.startswith("sqlite_")]


def columns(con, name):
    return [(r[1], r[2] or "", r[5]) for r in con.execute(f'PRAGMA table_info("{name}")')]


def profile(db, out):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = []
    for name, typ in objects(con):
        n = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        for pos, (col, dtype, pk) in enumerate(columns(con, name), 1):
            nn, nd = con.execute(f'SELECT COUNT("{col}"), COUNT(DISTINCT "{col}") FROM "{name}"').fetchone()
            ex = [str(r[0])[:60] for r in con.execute(
                f'SELECT DISTINCT "{col}" FROM "{name}" WHERE "{col}" IS NOT NULL LIMIT 5')]
            rows.append(dict(object_name=name, object_type=typ, n_rows=n, ordinal=pos, column_name=col,
                             declared_type=dtype, n_nonnull=nn, n_distinct=nd, examples=" | ".join(ex)))
    pd.DataFrame(rows).to_csv(out, sep="\t", index=False)
    print(f"profile: {len(rows)} columns in {len(objects(con))} objects -> {out}")


def build(db, tdefs, cdefs, out):
    td = pd.read_csv(tdefs, sep="\t", dtype=str, keep_default_na=False)
    cd = pd.read_csv(cdefs, sep="\t", dtype=str, keep_default_na=False)
    exact = {(r.table_name, r.column_name): r for r in cd.itertuples() if r.table_name != "*"}
    shared = {r.column_name: r for r in cd.itertuples() if r.table_name == "*"}
    tdesc = dict(zip(td.table_name, td.description))
    tgroup = dict(zip(td.table_name, td.get("group", pd.Series([""] * len(td)))))
    con = sqlite3.connect(db)
    rows, missing_t, missing_c = [], [], []
    for name, typ in objects(con):
        n = con.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        if not tdesc.get(name):
            missing_t.append(name)
        for pos, (col, dtype, pk) in enumerate(columns(con, name), 1):
            r = exact.get((name, col)) or shared.get(col)
            if typ == "view" and r is None:
                r = exact.get(("v_master", col))
            if r is None or not r.definition.strip():
                missing_c.append(f"{name}.{col}")
                continue
            rows.append(dict(object_name=name, object_type=typ, object_group=tgroup.get(name, ""),
                             object_description=tdesc.get(name, ""), n_rows=n, ordinal=pos, column_name=col,
                             declared_type=dtype, is_primary_key=int(pk > 0), definition=r.definition.strip(),
                             units_or_values=getattr(r, "units_or_values", "").strip(),
                             definition_scope="table" if (name, col) in exact else "shared", release="1.6.0"))
    if missing_t or missing_c:
        print(f"MISSING table descriptions ({len(missing_t)}): {missing_t}")
        print(f"MISSING column definitions ({len(missing_c)}): {missing_c[:200]}")
        sys.exit(1)
    dd = pd.DataFrame(rows)
    con.execute("DROP TABLE IF EXISTS data_dictionary")
    con.execute("""CREATE TABLE data_dictionary (object_name TEXT NOT NULL, object_type TEXT NOT NULL,
        object_group TEXT, object_description TEXT, n_rows INTEGER, ordinal INTEGER, column_name TEXT NOT NULL,
        declared_type TEXT, is_primary_key INTEGER, definition TEXT NOT NULL, units_or_values TEXT,
        definition_scope TEXT, release TEXT, PRIMARY KEY (object_name, column_name))""")
    dd.to_sql("data_dictionary", con, if_exists="append", index=False)
    # self-describe the dictionary table
    selfdesc = [
        ("object_name", "Table or view name."), ("object_type", "'table' or 'view'."),
        ("object_group", "Functional group of the object (core, membership, function, phylogeny, validation, provenance, legacy...)."),
        ("object_description", "One-sentence description of the table or view."),
        ("n_rows", "Row count of the object in this release."), ("ordinal", "1-based column position."),
        ("column_name", "Column name."), ("declared_type", "SQLite declared type (may be empty for view expressions)."),
        ("is_primary_key", "1 if the column is part of the declared primary key."),
        ("definition", "Curated definition of the column."), ("units_or_values", "Units, controlled vocabulary or value range."),
        ("definition_scope", "'table' = table-specific definition; 'shared' = definition shared by all objects with this column name."),
        ("release", "Release the dictionary describes."),
    ]
    n_rows_dd = len(dd) + len(selfdesc)
    con.executemany("INSERT INTO data_dictionary VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [
        ("data_dictionary", "table", "documentation", "Column-level data dictionary for every table and view in this release.",
         n_rows_dd, i, c, "TEXT" if c not in ("n_rows", "ordinal", "is_primary_key") else "INTEGER",
         int(c in ("object_name", "column_name")), d, "", "table", "1.6.0") for i, (c, d) in enumerate(selfdesc, 1)])
    con.commit()
    full = pd.read_sql("SELECT * FROM data_dictionary ORDER BY object_type, object_name, ordinal", con)
    con.close()
    full.to_csv(out, sep="\t", index=False)
    print(f"data_dictionary: {len(full)} rows, {full.object_name.nunique()} objects, coverage 100% -> {out}")


if __name__ == "__main__":
    db, mode = sys.argv[1], sys.argv[2]
    if mode == "profile":
        profile(db, sys.argv[3])
    else:
        build(db, sys.argv[3], sys.argv[4], sys.argv[5])
