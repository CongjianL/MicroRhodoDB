#!/usr/bin/env python
"""Compare the content of two MicroRhodoDB SQLite files table by table.

Timestamps written at build time (columns named built_at, checked_at) are excluded; every other
column of every table and view is compared as an order-independent multiset of rows (SHA-256 of
the sorted row representations). Both files are opened read-only.

Usage: python compare_db_content.py <reference.sqlite> <rebuilt.sqlite> <report.tsv>
Exit status 0 when all objects match, 1 otherwise.
"""
import hashlib
import sqlite3
import sys

VOLATILE = {"built_at", "checked_at"}


def digest(con, name):
    cols = [r[1] for r in con.execute(f'PRAGMA table_info("{name}")') if r[1] not in VOLATILE]
    sel = ", ".join(f'"{c}"' for c in cols)
    rows = sorted(repr(r) for r in con.execute(f'SELECT {sel} FROM "{name}"'))
    return len(rows), ",".join(cols), hashlib.sha256("\n".join(rows).encode()).hexdigest()


def main(ref, new, out):
    a = sqlite3.connect(f"file:{ref}?mode=ro", uri=True)
    b = sqlite3.connect(f"file:{new}?mode=ro", uri=True)
    q = "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'"
    oa, ob = dict(a.execute(q).fetchall()), dict(b.execute(q).fetchall())
    lines, bad = ["object\ttype\tstatus\tn_ref\tn_new\tsha_ref\tsha_new"], 0
    for name in sorted(set(oa) | set(ob)):
        if name not in oa or name not in ob:
            bad += 1
            lines.append(f"{name}\t{oa.get(name, ob.get(name))}\tmissing_in_{'ref' if name not in oa else 'new'}\t\t\t\t")
            continue
        na, ca, ha = digest(a, name)
        nb, cb, hb = digest(b, name)
        ok = (ca == cb) and (ha == hb)
        bad += not ok
        lines.append(f"{name}\t{oa[name]}\t{'identical' if ok else 'DIFFERENT'}\t{na}\t{nb}\t{ha[:16]}\t{hb[:16]}")
    open(out, "w").write("\n".join(lines) + "\n")
    print(f"{len(lines) - 1} objects compared; {bad} differ -> {out}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main(*sys.argv[1:4])
