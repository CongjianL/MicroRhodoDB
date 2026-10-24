#!/usr/bin/env python
"""Compare the content of two MicroRhodoDB SQLite files table by table.

Timestamps written at build time (columns named built_at, checked_at) are excluded; every other
column of every table and view is compared as an order-independent multiset of rows (SHA-256 of
the sorted row representations). Both files are opened read-only.

An object whose digests differ is compared again value by value with floating-point values allowed
to differ by a relative 1e-12 (all other values must be equal). It is then reported as
'float_tolerance' (counts as a match, with the number of differing values and the largest relative
difference) instead of 'DIFFERENT'. This covers last-digit differences from pandas' CSV float
parser, which is not correctly rounded and differs between platforms: a macOS arm64 rebuild
differs from the Linux-built release in 22 novel_family_flag.family_evalue values, e.g.
6.3999999999999995e-31 vs 6.399999999999999e-31.

Usage: python compare_db_content.py <reference.sqlite> <rebuilt.sqlite> <report.tsv>
Exit status 0 when all objects match (identical or within float tolerance), 1 otherwise.
"""
import hashlib
import math
import sqlite3
import sys
from pathlib import Path

VOLATILE = {"built_at", "checked_at"}
REL_TOL = 1e-12


def rows(con, name):
    cols = [r[1] for r in con.execute(f'PRAGMA table_info("{name}")') if r[1] not in VOLATILE]
    sel = ", ".join(f'"{c}"' for c in cols)
    return cols, list(con.execute(f'SELECT {sel} FROM "{name}"'))


def digest(rs):
    return hashlib.sha256("\n".join(sorted(repr(r) for r in rs)).encode()).hexdigest()


def _coarse(r):
    # sort key that is unchanged by last-digit float differences, so both sides pair up row by row
    return repr(tuple(float(f"{v:.10e}") if isinstance(v, float) else v for v in r))


def float_tolerant_diff(ra, rb):
    """(n_float_values_differing, max_relative_difference), or None if the rows differ beyond tolerance."""
    if len(ra) != len(rb):
        return None
    n, worst = 0, 0.0
    for x, y in zip(sorted(ra, key=_coarse), sorted(rb, key=_coarse)):
        if len(x) != len(y):
            return None
        for u, v in zip(x, y):
            if u == v:
                continue
            if isinstance(u, float) and isinstance(v, float) and math.isclose(u, v, rel_tol=REL_TOL, abs_tol=0.0):
                n += 1
                worst = max(worst, abs(u - v) / max(abs(u), abs(v)))
                continue
            return None
    return n, worst


def connect_ro(p):
    return sqlite3.connect(Path(p).resolve().as_uri() + "?mode=ro", uri=True)


def main(ref, new, out):
    a, b = connect_ro(ref), connect_ro(new)
    q = "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'"
    oa, ob = dict(a.execute(q).fetchall()), dict(b.execute(q).fetchall())
    lines, bad, tol = ["object\ttype\tstatus\tn_ref\tn_new\tsha_ref\tsha_new\tnote"], 0, 0
    for name in sorted(set(oa) | set(ob)):
        if name not in oa or name not in ob:
            bad += 1
            lines.append(f"{name}\t{oa.get(name, ob.get(name))}\tmissing_in_{'ref' if name not in oa else 'new'}\t\t\t\t\t")
            continue
        (ca, ra), (cb, rb) = rows(a, name), rows(b, name)
        ha, hb = digest(ra), digest(rb)
        status, note = "identical", ""
        if ca != cb:
            status, note = "DIFFERENT", "columns differ"
        elif ha != hb:
            d = float_tolerant_diff(ra, rb)
            if d is None:
                status = "DIFFERENT"
            else:
                status, note = "float_tolerance", f"{d[0]} float values differ; max relative difference {d[1]:.1e}"
                tol += 1
        bad += status == "DIFFERENT"
        lines.append(f"{name}\t{oa[name]}\t{status}\t{len(ra)}\t{len(rb)}\t{ha[:16]}\t{hb[:16]}\t{note}")
    open(out, "w").write("\n".join(lines) + "\n")
    print(f"{len(lines) - 1} objects compared; {len(lines) - 1 - bad - tol} identical, {tol} equal within float "
          f"tolerance (rel {REL_TOL:g}), {bad} differ -> {out}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main(*sys.argv[1:4])
