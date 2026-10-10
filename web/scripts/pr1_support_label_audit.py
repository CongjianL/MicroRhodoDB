#!/usr/bin/env python
"""PR-1 evidence: support labels of MR_RT_003.rooted.treefile vs IQ-TREE run1.treefile, and the impact on the
MR_CLD3 level-1 clade rule. Read-only; writes one JSON file. Nothing in releases/ or refpkg/ is modified.

  python web/scripts/pr1_support_label_audit.py <repo_root> <out_json>

The clade rule re-implemented here is the one in pipeline/v150/define_clades.py (PRIMARY: outgroup rooting,
5-100 ingroup tips, UFBoot >= 95, SH-aLRT >= 80, top-down). It is run twice on the rooted topology:
  A. with the labels as stored in the rooted file (must reproduce the 17 DB level-1 clades exactly);
  B. with each branch's label taken from run1.treefile for the same bipartition.
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import export_web_data as E  # noqa: E402

PRIMARY = dict(min_size=5, max_size=100, ufb=95.0, alrt=80.0)


def sup(label):
    if not label or "/" not in label:
        return float("nan"), float("nan")
    a, b = label.split("/")[:2]
    return float(a), float(b)


def main(repo, out):
    repo = Path(repo)
    rooted = E.parse_newick((repo / E.TREE_REL).read_text())
    run1 = E.parse_newick((repo / E.REFPKG / "tree/run1.treefile").read_text())
    audit, run1_lab, ref, all_tips = E.support_audit(rooted, run1)
    og = {l.split("\t")[0] for l in (repo / E.REFPKG / "tips.tsv").read_text().splitlines()[1:]
          if l.split("\t")[1:2] == ["outgroup_heliorhodopsin"]}
    below = E.tip_sets(rooted)

    def label_rooted(n):
        return n.name

    def label_run1(n):
        return run1_lab.get(E.split_key(below[id(n)], all_tips, ref)) if n.parent is not None else ""

    def clades(label_of):
        found = []

        def visit(n):
            tips = [t for t in below[id(n)] if t not in og]
            if not tips:
                return
            a, u = sup(label_of(n)) if n.children else (float("nan"), float("nan"))
            if n.children and u >= PRIMARY["ufb"] and a >= PRIMARY["alrt"] and \
                    PRIMARY["min_size"] <= len(tips) <= PRIMARY["max_size"] and not below[id(n)] & og:
                found.append((frozenset(tips), label_of(n)))
                return
            for c in n.children:
                visit(c)
        visit(rooted)
        return found

    con = sqlite3.connect(f"file:{repo / E.DB_REL}?mode=ro", uri=True)
    db = {}
    for acc, cid in con.execute("SELECT source_acc, clade_id FROM clade_tip WHERE clade_id LIKE 'MR_CLD3_0%'"):
        db.setdefault(cid, set()).add(acc)
    db_by_set = {frozenset(v): k for k, v in db.items()}
    n_records = dict(con.execute("SELECT clade_id, n_records_assigned FROM clade WHERE level = 1"))
    A, B = clades(label_rooted), clades(label_run1)
    setsA, setsB = {s for s, _ in A}, {s for s, _ in B}
    R = {
        "rooted_file": E.TREE_REL, "reference_file": f"{E.REFPKG}/tree/run1.treefile",
        "rule": "pipeline/v150/define_clades.py PRIMARY " + json.dumps(PRIMARY, sort_keys=True),
        "n_nonroot_internal": len(audit) - 1,
        "n_label_disagreements": sum(1 for a in audit if not a["is_root"] and not a["agrees"]),
        "disagreements": [a for a in audit if not a["is_root"] and not a["agrees"]],
        "pattern": "each disagreeing rooted node carries the run1 label of its child on the path towards the "
                   "original Newick top node (shift by one node), as produced by rerooting node-attached labels",
        "A_rooted_labels_reproduce_db_level1": setsA == set(db_by_set), "A_n_clades": len(A),
        "B_iqtree_labels_n_clades": len(B),
        "B_db_clades_unchanged": sorted(db_by_set[s] for s in setsA & setsB),
        "B_db_clades_not_recovered": [{"clade_id": db_by_set[s], "n_tips": len(s), "n_records_assigned":
                                       n_records.get(db_by_set[s]),
                                       "iqtree_run1_label": run1_lab[E.split_key(s, all_tips, ref)]}
                                      for s in setsA - setsB],
        "B_new_clades": sorted(({"n_tips": len(s), "iqtree_run1_label": lab,
                                 "overlap_with_db_clades": {db_by_set[d]: len(d & s) for d in db_by_set if d & s}}
                                for s, lab in B if s not in setsA), key=lambda x: -x["n_tips"]),
        "scope_note": "Level-2 subclades and the clade_robustness grid were produced with the same code and may be "
                      "affected as well; not re-derived here. No DB, refpkg or classification value was changed.",
    }
    con.close()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(R, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: R[k] for k in ("n_label_disagreements", "A_rooted_labels_reproduce_db_level1",
                                        "B_iqtree_labels_n_clades", "B_db_clades_not_recovered", "B_new_clades")},
                     indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
