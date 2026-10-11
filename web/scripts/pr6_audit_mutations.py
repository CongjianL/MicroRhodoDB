#!/usr/bin/env python3
"""Adversarial self-test of pr6_scientific_audit.py: each mutation corrupts one scientific fact in a
copy of the export; the audit must exit non-zero for every mutation (and zero for the unmodified copy).

Usage: python web/scripts/pr6_audit_mutations.py --out docs/website/pr6
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXP = REPO / "web" / "public" / "data" / "v1.6.0"
AUDIT = REPO / "web" / "scripts" / "pr6_scientific_audit.py"


def edit(path: Path, fn) -> None:
    d = json.loads(path.read_text())
    fn(d)
    path.write_text(json.dumps(d))


def ri_set(col, acc, value):
    def f(d):
        ci, si = d["columns"].index(col), d["columns"].index("source_acc")
        for r in d["rows"]:
            if r[si] == acc:
                r[ci] = value
    return f


def swap_support(d):  # swap displayed support of two internal nodes
    a, b = d["nodes"][5], d["nodes"][9]
    a["sh_alrt"], b["sh_alrt"] = b["sh_alrt"], a["sh_alrt"]


def drop_row(d):
    d["rows"].pop(17)


def place_edge(d):
    for s in d["sources"]:
        if s["phylogeny"].get("placement"):
            s["phylogeny"]["placement"]["best_edge"] = "E0001"


def tip_group(d):
    k = next(k for k, t in d["tips"].items() if t["level1"] == "MR_CLD3_007")
    d["tips"][k]["level1"] = "MR_CLD3_004"


def audit_017(d):
    c = next(c for c in d["level1"] if c["clade_id"] == "MR_CLD3_017")
    c["support_audit"]["iqtree_run1_meets_support_thresholds"] = True


def pdb_link(d):
    d["pdb"]["1AP9"]["source_accs"] = ["B0R5N9"]


def acc_map(d):
    d["by_source"]["B0R5N9"] = "MRDB000002"


def edge_map(d):
    k = sorted(d["edge_map"])[100]
    d["edge_map"][k] = [d["edge_map"][k][0] + 1]


def first_placed(exp: Path) -> Path:
    for f in sorted((exp / "records").glob("MRDB*.json"))[100:]:
        if any(s["phylogeny"].get("placement") for s in json.loads(f.read_text())["sources"]):
            return f
    raise RuntimeError("no placed record")


MUTATIONS = [
    ("evidence level of P02945 E1 -> E2 (records-index)", "records-index.json", ri_set("evidence_level", "P02945", "E2")),
    ("membership status swapped to candidate (records-index)", "records-index.json", ri_set("membership_status", "P02945", "typeI_candidate")),
    ("clade_id of a placed record changed (records-index)", "records-index.json", ri_set("clade_id", "B0R5N9", "MR_CLD3_017")),
    ("engineered flag cleared for A0ABF7PQA2", "records-index.json", ri_set("is_engineered", "A0ABF7PQA2", False)),
    ("one source record dropped", "records-index.json", drop_row),
    ("SH-aLRT values of two tree nodes swapped", "phylogeny/explorer.json", swap_support),
    ("tip moved to another level-1 clade", "phylogeny/explorer.json", tip_group),
    ("edge map points to the wrong rooted node", "phylogeny/explorer.json", edge_map),
    ("MR_CLD3_017 marked as meeting the support thresholds", "clades.json", audit_017),
    ("PDB 1AP9 linked to the wrong source record", "structures-index.json", pdb_link),
    ("accession map points to the wrong MRDB record", "accessions.json", acc_map),
    ("placement best edge changed in a record file", None, place_edge),
]


def run(exp: Path, out: Path) -> int:
    return subprocess.run([sys.executable, str(AUDIT), "--export", str(exp), "--out", str(out)],
                          capture_output=True, text=True).returncode


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    res = []
    with tempfile.TemporaryDirectory(dir="/workspace") as td:
        base = Path(td) / "v1.6.0"
        shutil.copytree(EXP, base)
        scratch = Path(td) / "o"
        res.append({"mutation": "none (unmodified copy)", "exit": run(base, scratch), "expected": 0})
        for name, rel, fn in MUTATIONS:
            work = Path(td) / "m"
            if work.exists():
                shutil.rmtree(work)
            shutil.copytree(base, work)
            edit(work / rel if rel else first_placed(work), fn)
            res.append({"mutation": name, "exit": run(work, scratch), "expected": 1})
    for r in res:
        r["detected"] = (r["exit"] != 0) == (r["expected"] != 0)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "scientific_audit_mutations.json").write_text(json.dumps(res, indent=1))
    ok = sum(r["detected"] for r in res)
    print(f"{ok}/{len(res)} as expected")
    for r in res:
        print(("OK  " if r["detected"] else "MISS"), r["mutation"], r["exit"])
    sys.exit(0 if ok == len(res) else 1)


if __name__ == "__main__":
    main()
