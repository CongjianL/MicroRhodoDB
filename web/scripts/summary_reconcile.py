#!/usr/bin/env python3
"""Strict, keyed reconciliation of summary.json against the read-only v1.6.1 SQLite (PR-5a).

Every metric, distribution and crosstab in summary.json is checked:

* metrics (34): the stored SQL is replayed and must return exactly one row with the exported value;
* distributions (21 with SQL): the stored SQL is replayed and the result is compared with the exported
  items as a complete keyed mapping -- identical key sets (``None`` = missing category is a key like any
  other, never dropped or merged), identical value per key, no duplicate keys on either side, and the
  total equal to the exported total and denominator;
  ``ncbi_phylum_counted`` stores SQL that returns the raw lineage of each counted record; the stored
  derivation regex is applied to the replayed rows (one phylum per lineage at most);
* crosstabs (2): keyed on (row, col) with the same rules;
* ``tip_role`` (1, no SQL): independently derived from refpkg/MR_RT_003/tips.tsv (its stated
  source_file), keyed the same way.

Result: 57 SQL-replayed items + 1 independently derived item = 58 items. Comparing sorted value lists
(the PR-5 approach) cannot detect two categories whose counts are swapped; a keyed comparison can,
and tests/test_web_pr5a.py proves it with mutation tests.

Library use: ``reconcile(con, summary, repo)`` returns a list of dicts; ``compare_keyed`` raises nothing
and returns a list of human-readable problems (empty list = exact match).
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

PHYLUM = re.compile(r"(?:^|, )([^,]+?) \(phylum\)")
EXPECTED_SQL_ITEMS = 57
EXPECTED_DERIVED_ITEMS = 1


class DuplicateKey(ValueError):
    pass


def keyed(pairs, what: str) -> dict:
    """Build a dict from (key, value) pairs, refusing duplicate keys (which a dict would silently merge)."""
    out: dict = {}
    for k, v in pairs:
        if k in out:
            raise DuplicateKey(f"{what}: duplicate key {k!r}")
        out[k] = v
    return out


def compare_keyed(got_pairs, exp_pairs, total=None) -> list[str]:
    """Exact keyed comparison. Returns a list of problems (empty = identical)."""
    problems: list[str] = []
    try:
        got = keyed(got_pairs, "replayed")
    except DuplicateKey as e:
        return [str(e)]
    try:
        exp = keyed(exp_pairs, "exported")
    except DuplicateKey as e:
        return [str(e)]
    for k in sorted(set(got) - set(exp), key=repr):
        problems.append(f"key {k!r} replayed ({got[k]}) but not exported")
    for k in sorted(set(exp) - set(got), key=repr):
        problems.append(f"key {k!r} exported ({exp[k]}) but not replayed")
    for k in sorted(set(got) & set(exp), key=repr):
        if type(got[k]) is not type(exp[k]) or got[k] != exp[k]:
            problems.append(f"key {k!r}: replayed {got[k]!r} != exported {exp[k]!r}")
    for k, v in exp.items():
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            problems.append(f"key {k!r}: exported value {v!r} is not a non-negative integer")
    if total is not None:
        if sum(exp.values()) != total:
            problems.append(f"exported items sum to {sum(exp.values())}, not the total {total}")
        if sum(got.values()) != total:
            problems.append(f"replayed rows sum to {sum(got.values())}, not the total {total}")
    return problems


def replay_distribution(con, d) -> list[tuple]:
    rows = con.execute(d["sql"]).fetchall()
    if d["id"] == "ncbi_phylum_counted":
        # Stored SQL returns one lineage per counted record; apply the stored derivation regex.
        assert PHYLUM.pattern in d["derivation"], "derivation regex changed"
        counts: dict = {}
        for row in rows:
            if len(row) != 1:
                raise ValueError("ncbi_phylum_counted: expected one column (lineage)")
            m = PHYLUM.findall(row[0] or "")
            if len(m) > 1:
                raise ValueError(f"lineage with {len(m)} phylum ranks: {row[0]!r}")
            k = m[0] if m else None
            counts[k] = counts.get(k, 0) + 1
        return list(counts.items())
    for row in rows:
        if len(row) != 2:
            raise ValueError(f"{d['id']}: expected (key, count) rows, got {len(row)} columns")
    return [(r[0], r[1]) for r in rows]


def derive_tip_role(repo: Path) -> list[tuple]:
    """tip_role from refpkg/MR_RT_003/tips.tsv, one row per tree tip (duplicate tips are an error)."""
    path = repo / "refpkg/MR_RT_003/tips.tsv"
    seen: set = set()
    counts: dict = {}
    with path.open(newline="") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            if r["source_acc"] in seen:
                raise DuplicateKey(f"tips.tsv: duplicate tip {r['source_acc']}")
            seen.add(r["source_acc"])
            k = r["tip_role"] or None
            counts[k] = counts.get(k, 0) + 1
    return list(counts.items())


def reconcile(con, summary: dict, repo: Path) -> list[dict]:
    out: list[dict] = []
    ids: set = set()

    def add(kind, item, method, problems, total):
        if item["id"] in ids:
            problems = problems + [f"duplicate item id {item['id']}"]
        ids.add(item["id"])
        out.append({"kind": kind, "id": item["id"], "method": method, "total": total,
                    "denominator": (item.get("denominator") or {}).get("id"),
                    "denominator_value": (item.get("denominator") or {}).get("value"),
                    "ok": not problems, "problems": problems})

    dens = summary["denominators"]
    for m in summary["metrics"]:
        if not m.get("sql"):
            add("metric", m, "none", ["metric has no stored SQL"], m["value"])
            continue
        rows = con.execute(m["sql"]).fetchall()
        p = [] if len(rows) == 1 and len(rows[0]) == 1 and rows[0][0] == m["value"] and type(rows[0][0]) is type(m["value"]) \
            else [f"replayed {rows!r} != exported {m['value']!r}"]
        add("metric", m, "sql", p, m["value"])
    for d in summary["distributions"]:
        p: list[str] = []
        if d["denominator"]["value"] != d["total"] or dens[d["denominator"]["id"]]["value"] != d["total"]:
            p.append("total differs from its denominator")
        exp = [(i["key"], i["value"]) for i in d["items"]]
        if d.get("sql"):
            p += compare_keyed(replay_distribution(con, d), exp, d["total"])
            add("distribution", d, "sql", p, d["total"])
        elif d["id"] == "tip_role":
            p += compare_keyed(derive_tip_role(repo), exp, d["total"])
            add("distribution", d, "derived:refpkg/MR_RT_003/tips.tsv", p, d["total"])
        else:
            add("distribution", d, "none", p + ["no SQL and no independent derivation"], d["total"])
    for x in summary["crosstabs"]:
        tot = x["denominator"]["value"]
        p = [] if x.get("total", tot) == tot else ["total differs from its denominator"]
        rows = con.execute(x["sql"]).fetchall()
        if any(len(r) != 3 for r in rows):
            p.append("expected (row, col, count) rows")
        p += compare_keyed([((r[0], r[1]), r[2]) for r in rows], [((c["row"], c["col"]), c["value"]) for c in x["cells"]], tot)
        add("crosstab", x, "sql", p, tot)
    return out


def counts(results: list[dict]) -> tuple[int, int]:
    return (sum(r["method"] == "sql" for r in results), sum(r["method"].startswith("derived") for r in results))
