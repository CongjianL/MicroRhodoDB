#!/usr/bin/env python
"""Export MR_RT_003 tree_node / tree_edge tables from the EPA-ng jplace reference tree.

edge_id = 'E%04d' % jplace edge_num, so placement.best_edge joins tree_edge directly.
The serialized (unrooted) topology is stored as-is; the biological root (heliorhodopsin outgroup)
is recorded in reference_tree.note. Internal labels 'SH-aLRT/UFBoot' are split into numeric columns.

Usage: export_tree_tables.py placements.jplace TREE_ID nodes.tsv edges.tsv
"""
import sys, json, re
from ete3 import Tree


def main():
    jp, tid, nout, eout = sys.argv[1:5]
    j = json.load(open(jp))
    nwk = re.sub(r"([^(),:;]*):([0-9.eE+-]+)\{(\d+)\}", lambda m: f"{m.group(1)}@E{m.group(3)}:{m.group(2)}", j["tree"])
    t = Tree(nwk, format=1)
    nid, ti, ni = {}, 0, 0
    nodes, edges = [], []
    for n in t.traverse("preorder"):
        raw = n.name or ""
        if "@E" in raw:
            lab, enum = raw.split("@E")
        else:
            lab, enum = raw, None
        bl = n.dist if enum is not None else ""
        if n.is_leaf():
            ti += 1; nid[n] = f"T{ti:04d}"
            nodes.append([nid[n], tid, "tip", "", lab, "", "", bl])
        else:
            ni += 1; nid[n] = f"N{ni:04d}"
            sh = uf = ""
            if "/" in lab:
                sh, uf = lab.split("/")[:2]
            nodes.append([nid[n], tid, "internal", lab, "", sh, uf, bl])
        if enum is not None:
            edges.append([f"E{int(enum):04d}", tid, nid[n.up], nid[n], n.dist])
    with open(nout, "w") as f:
        f.write("node_id\ttree_id\tkind\tlabel\tsource_acc\tsh_alrt\tufboot\tbranch_length\n")
        for r in nodes:
            f.write("\t".join(map(str, r)) + "\n")
    with open(eout, "w") as f:
        f.write("edge_id\ttree_id\tparent_node\tchild_node\tlength\n")
        for r in edges:
            f.write("\t".join(map(str, r)) + "\n")
    print(f"{tid}: {ti} tips, {ni} internal, {len(edges)} edges")


if __name__ == "__main__":
    main()
