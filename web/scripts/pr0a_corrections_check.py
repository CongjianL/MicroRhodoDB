#!/usr/bin/env python
"""PR-0a evidence for the PR-0 documentation corrections (read-only; writes one JSON file).

  python web/scripts/pr0a_corrections_check.py <repo_root> <out_json>

Checks:
  1. ESMCFold2 coordinate files referenced by predicted_structure.pdb_file (release-relative paths)
     resolve under releases/*/ and match the frozen SHA-256 manifest.
  2. Support-label census of refpkg/MR_RT_003/tree/MR_RT_003.rooted.treefile vs DB tree_node.
  3. Strict legacy fidelity of site/data.js (39 columns) under the exact allowed transformations.
"""
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np

SUPPORT_RE = re.compile(r"^\d+(\.\d+)?/\d+(\.\d+)?$")
DB_REL = "releases/v1.6.0/db/microrhododb_v1.6.0.sqlite"
ROUNDED = {"membership_score": 3, "afdb_global_plddt": 1, "e2_identity": 3}


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def newick_internal_labels(s):
    """Return the list of labels (possibly '') of every internal node, root included."""
    labels, i, n = [], 0, len(s)
    while i < n:
        if s[i] == ")":
            j = i + 1
            while j < n and s[j] not in ":,);":
                j += 1
            labels.append(s[i + 1:j].strip().strip("'"))
            i = j
        else:
            i += 1
    return labels


def main(repo, out):
    repo = Path(repo)
    con = sqlite3.connect(f"file:{repo / DB_REL}?mode=ro", uri=True)
    frozen = dict(reversed(l.split(None, 1)) for l in
                  (repo / "docs/website/baseline/frozen_sha256_fab9182.txt").read_text().splitlines() if l.strip())
    frozen = {k.strip().lstrip("*"): v for k, v in frozen.items()}
    R = {}

    # 1. predicted structures
    pred = []
    for acc, method, plddt, rel in con.execute(
            "SELECT source_acc, method, mean_plddt, pdb_file FROM predicted_structure ORDER BY source_acc"):
        hits = sorted(str(p.relative_to(repo)) for p in (repo / "releases").glob(f"*/{rel}"))
        e = {"source_acc": acc, "method": method, "mean_plddt": plddt, "db_pdb_file": rel, "resolved": hits}
        if len(hits) == 1:
            p = repo / hits[0]
            b = p.read_bytes()
            e.update(sha256=sha256(p), bytes=len(b), frozen_sha256=frozen.get(hits[0]),
                     matches_frozen=frozen.get(hits[0]) == sha256(p),
                     n_atom=sum(1 for l in b.decode().splitlines() if l.startswith("ATOM")),
                     bfactor_range=[min(bf := [float(l[60:66]) for l in b.decode().splitlines() if l.startswith("ATOM")]),
                                    max(bf)])
        pred.append(e)
    R["predicted_structures"] = pred

    # 2. support labels
    nwk = (repo / "refpkg/MR_RT_003/tree/MR_RT_003.rooted.treefile").read_text().strip()
    labs = newick_internal_labels(nwk)
    genuine = [l for l in labs if SUPPORT_RE.match(l)]
    db_labs = [r[0] for r in con.execute(
        "SELECT label FROM tree_node WHERE tree_id='MR_RT_003' AND kind!='tip'")]
    db_internal = con.execute("SELECT COUNT(*) FROM tree_node WHERE tree_id='MR_RT_003' AND kind!='tip'").fetchone()[0]
    db_genuine = [l for l in db_labs if l and SUPPORT_RE.match(l)]
    R["support_labels"] = {
        "rooted_treefile_sha256": sha256(repo / "refpkg/MR_RT_003/tree/MR_RT_003.rooted.treefile"),
        "rooted_internal_nodes_incl_root": len(labs),
        "rooted_open_parens": nwk.count("("), "rooted_close_parens": nwk.count(")"),
        "rooted_genuine_support_labels": len(genuine),
        "rooted_unlabelled_internal_nodes": sum(1 for l in labs if l == ""),
        "rooted_other_labels": sorted({l for l in labs if l and not SUPPORT_RE.match(l)}),
        "root_label": labs[-1],
        "db_tree_node_internal": db_internal, "db_genuine_support_labels": len(db_genuine),
        "db_label_multiset_equals_rooted": sorted(db_genuine) == sorted(genuine),
        "phylotree_note": "phylotree 2.6.0 newickParser names the root node 'root'; PoC counted 469 + 1 = 470 named internal nodes",
    }

    # 3. strict legacy fidelity
    t = (repo / "site/data.js").read_text()
    M = json.loads(t[t.index("{"):t.rindex("}") + 1])
    lc = M["columns"]
    q = """SELECT v.*, p.reviewed AS x_reviewed, f.e2_ref AS x_e2_ref, f.e2_identity AS x_e2_identity,
                  f.override_rule AS x_override_rule, r.pocket_string_br AS x_pocket_string_br,
                  mb.status_reason AS x_status_reason, nf.novel_family_hit AS x_novel_family_flag,
                  (v.source_acc = m.representative_source_acc) AS x_is_mrdb_representative
           FROM v_master v JOIN protein p USING (source_acc) JOIN mrdb_accession m ON m.mrdb_acc = v.mrdb_acc
           JOIN function_evidence f USING (source_acc) LEFT JOIN retinal_pocket_summary r USING (source_acc)
           LEFT JOIN membership mb USING (source_acc) LEFT JOIN novel_family_flag nf USING (source_acc)
           ORDER BY v.mrdb_acc, v.source_acc"""
    cur = con.execute(q)
    names = [d[0] for d in cur.description]
    mism, empties, n = {}, {}, 0
    for lr, dr in zip(M["rows"], cur.fetchall()):
        n += 1
        a_row, d_row = dict(zip(lc, lr)), dict(zip(names, dr))
        for c in lc:
            a = a_row[c]
            if c == "clade_confidence":
                v = "confident" if d_row["clade_id"] else ("tentative" if d_row["tentative_clade_id"] else "none")
            else:
                v = d_row[c] if c in d_row else d_row["x_" + c]
                if v == "":
                    empties[c] = empties.get(c, 0) + 1
                if c in ROUNDED and v is not None:
                    try:
                        v = float(np.round(float(v), ROUNDED[c]))
                    except ValueError:
                        v = None
            if a != v or type(a) is not type(v):
                mism[c] = mism.get(c, 0) + 1
    R["legacy_strict"] = {"rows": n, "columns": len(lc), "mismatched_cells_by_column": mism,
                          "db_empty_string_cells_by_column": empties,
                          "rounding": "numpy.round(value, k) as in tools/build_site_v160.py (pandas Series.round)",
                          "rounded_columns": ROUNDED}
    con.close()
    Path(out).write_text(json.dumps(R, indent=1, sort_keys=True) + "\n")
    print(json.dumps(R, indent=1, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
