#!/usr/bin/env python3
"""DB-derived golden accession sets for every Statistics/Home drilldown and the Search -> Browse clade
mapping (PR-5a).

For each drillable category, the set of source accessions the statistic counts is computed directly
from the read-only v1.6.0 SQLite with hand-written SQL (population predicate AND category predicate),
and stored as (n, SHA-256 of the sorted accessions). The Vitest suite (tests/unit/pr5a.test.ts) applies
the website's actual Browse filter for the generated drilldown link and must reproduce each set exactly;
tests/test_web_pr5a.py regenerates this file and requires it to be identical, and requires every n to
equal the value exported in summary.json.

Usage (repository root):
    python web/scripts/pr5a_drilldown_golden.py            # write tests/data/web_drilldown_golden_v160.json
    python web/scripts/pr5a_drilldown_golden.py --check    # exit 1 if the committed file differs
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DB = REPO / "releases/v1.6.0/db/microrhododb_v1.6.0.sqlite"
OUT = REPO / "tests/data/web_drilldown_golden_v160.json"
PHYLUM = re.compile(r"(?:^|, )([^,]+?) \(phylum\)")
MOTIF_LINKABLE = re.compile(r"^[A-Z-]{1,5}$")

# One row per source record with every field a drilldown can filter on. clade_state is the
# per-record CASE expression that defines the clade_state statistics.
BASE = """
SELECT v.source_acc, v.membership_status, s.status_group, v.evidence_level, v.func_class, v.tax_domain,
       v.helixC_motif, v.counts_eligible, v.is_engineered, v.clade_id, v.subclade_id, v.tentative_clade_id,
       pr.lineage,
       CASE
         WHEN rc.source_acc IS NULL THEN 'outgroup_reference_tip'
         WHEN COALESCE(v.clade_id, '') <> '' THEN 'confident'
         WHEN COALESCE(v.tentative_clade_id, '') <> '' THEN 'tentative'
         WHEN rc.source = 'reference_tip' THEN 'reference_tip_unclustered'
         WHEN p.clade_call = 'outgroup_heliorhodopsin' THEN 'outgroup_placed'
         WHEN p.clade_call = 'unassigned' THEN 'unassigned'
         WHEN p.clade_call = 'tentative' THEN 'distant'
         ELSE 'UNMAPPED'
       END AS clade_state
FROM v_master v
JOIN status_definition s ON s.status = v.membership_status
JOIN protein pr ON pr.source_acc = v.source_acc
LEFT JOIN record_clade rc ON rc.source_acc = v.source_acc
LEFT JOIN placement p ON p.source_acc = v.source_acc AND p.is_current = 1 AND p.tree_id = 'MR_RT_003'
"""

POP = {
    "all_records": lambda r: True,
    "counted_records": lambda r: r["counts_eligible"] == 1,
    "members_candidates": lambda r: r["status_group"] in ("member", "candidate"),
}


def phylum(r):
    m = PHYLUM.findall(r["lineage"] or "")
    return m[0] if m else None


# distribution id -> (population, per-record category, linkable(key))
DISTS = {
    "membership_status": ("all_records", lambda r: r["membership_status"], lambda k: True),
    "membership_status_counted": ("counted_records", lambda r: r["membership_status"], lambda k: True),
    "membership_group": ("all_records", lambda r: r["status_group"], lambda k: True),
    "evidence_level_counted": ("counted_records", lambda r: r["evidence_level"], lambda k: True),
    "evidence_level_all": ("all_records", lambda r: r["evidence_level"], lambda k: True),
    "func_class_counted": ("counted_records", lambda r: r["func_class"], lambda k: True),
    "tax_domain_counted": ("counted_records", lambda r: r["tax_domain"], lambda k: True),
    "ncbi_phylum_counted": ("counted_records", phylum, lambda k: k is not None),
    "clade_state": ("all_records", lambda r: r["clade_state"], lambda k: True),
    "clade_state_members_candidates": ("members_candidates", lambda r: r["clade_state"], lambda k: True),
    "helixC_motif_counted": ("counted_records", lambda r: r["helixC_motif"],
                             lambda k: k is not None and bool(MOTIF_LINKABLE.match(k))),
}
CROSSTABS = {"evidence_by_membership_group_counted": ("counted_records", lambda r: (r["status_group"], r["evidence_level"]))}
METRICS = {  # Home stat cards that link to Browse
    "records_total": ("all_records", lambda r: True),
    "typeI_members": ("all_records", lambda r: r["status_group"] == "member"),
    "e1_counted": ("counted_records", lambda r: r["evidence_level"] == "E1"),
}


def digest(accs) -> dict:
    s = sorted(accs)
    if len(s) != len(set(s)):
        raise ValueError("duplicate source accessions in a drilldown set")
    return {"n": len(s), "sha256": hashlib.sha256("\n".join(s).encode()).hexdigest()}


def build() -> dict:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(BASE)]
    if len(rows) != 5466 or len({r["source_acc"] for r in rows}) != 5466:
        raise SystemExit("base query must return the 5,466 source records once each")
    items = []
    for did, (pop, cat, linkable) in DISTS.items():
        groups: dict = {}
        for r in rows:
            if POP[pop](r):
                groups.setdefault(cat(r), []).append(r["source_acc"])
        for k in sorted(groups, key=lambda x: (x is None, x)):
            if linkable(k):
                items.append({"kind": "distribution", "id": did, "key": k, "population": pop, **digest(groups[k])})
    for xid, (pop, cat) in CROSSTABS.items():
        groups = {}
        for r in rows:
            if POP[pop](r):
                groups.setdefault(cat(r), []).append(r["source_acc"])
        for k in sorted(groups):
            items.append({"kind": "crosstab", "id": xid, "key": list(k), "population": pop, **digest(groups[k])})
    for mid, (pop, pred) in METRICS.items():
        items.append({"kind": "metric", "id": mid, "key": None, "population": pop,
                      **digest(r["source_acc"] for r in rows if POP[pop](r) and pred(r))})
    # Search -> Browse for a level-1 clade ID (MR_CLD3_017 carries a scientific caveat on the website).
    c = "MR_CLD3_017"
    items.append({"kind": "search", "id": c, "key": "formal", "population": "all_records",
                  **digest(r["source_acc"] for r in rows if r["clade_id"] == c)})
    items.append({"kind": "search", "id": c, "key": "formal_or_tentative", "population": "all_records",
                  **digest(r["source_acc"] for r in rows if r["clade_id"] == c or (r["clade_state"] == "tentative" and r["tentative_clade_id"] == c))})
    items.append({"kind": "search", "id": c, "key": "text_search_hits", "population": "all_records",
                  **digest(r["source_acc"] for r in rows if r["clade_id"] == c or r["tentative_clade_id"] == c
                           or (r["subclade_id"] or "").startswith(c))})
    db_sha = hashlib.sha256(DB.read_bytes()).hexdigest()
    return {"db_sha256": db_sha, "description": __doc__.strip().splitlines()[0], "accession_hash": "sha256 of sorted source_acc joined by newline",
            "items": items}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text = json.dumps(build(), indent=1, ensure_ascii=False) + "\n"
    if a.check:
        ok = OUT.exists() and OUT.read_text() == text
        print("drilldown golden", "OK" if ok else "DIFFERS")
        sys.exit(0 if ok else 1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(REPO)} ({len(json.loads(text)['items'])} items)")


if __name__ == "__main__":
    main()
