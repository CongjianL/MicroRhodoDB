"""PR-4 gate G4: phylogeny explorer data (schema 1.2.0, current export 1.3.0) reconciles with the frozen refpkg and SQLite.

Run from the repository root:
    pytest -q tests/test_web_phylogeny.py

The exporter is run once into a temporary directory. Every expected value is recomputed here from
refpkg/MR_RT_003 and the read-only v1.6.1 database with a Newick parser and bipartition code written
independently of tools/export_web_data.py. Includes the regression tests for the 17 rooted-file support-label
discrepancies and for MR_CLD3_017 (legacy assignment, corrected run1 support 50.3/72).
"""
import collections
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(os.environ.get("MRDB_REPO", ".")).resolve()
DB = Path(os.environ.get("MRDB_DB", REPO / "releases/v1.6.1/db/microrhododb_v1.6.1.sqlite"))
REFPKG = REPO / "refpkg/MR_RT_003"
TREE = REFPKG / "tree/MR_RT_003.rooted.treefile"
RUN1 = REFPKG / "tree/run1.treefile"
REL = "v1.6.1"
LABEL_RE = re.compile(r"^(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)$")

# (internal preorder index, n_tips, frozen rooted-file label, IQ-TREE run1 label of the same bipartition).
# All 17 have last tip A0A3E2H811 (path from the outgroup root to the former run1 top node).
DISCREPANCIES = [
    (15, 457, "92.1/96", "98.8/100"), (20, 452, "82.2/82", "92.1/96"), (56, 416, "76.7/84", "82.2/82"),
    (81, 391, "64.9/67", "76.7/84"), (204, 268, "61.4/84", "64.9/67"), (206, 266, "73.3/76", "61.4/84"),
    (212, 260, "98.7/81", "73.3/76"), (331, 141, "18.9/64", "98.7/81"), (346, 126, "87.6/88", "18.9/64"),
    (356, 116, "75.3/86", "87.6/88"), (358, 114, "11.1/62", "75.3/86"), (362, 110, "93.9/89", "11.1/62"),
    (363, 109, "50.3/72", "93.9/89"), (372, 100, "100/100", "50.3/72"), (424, 48, "87.1/98", "100/100"),
    (425, 47, "40/51", "87.1/98"), (447, 25, None, "40/51"),
]


# ----------------------------------------------------------------------------------------------- parser
class N:
    def __init__(self, parent=None):
        self.parent, self.kids, self.label, self.blen = parent, [], "", None


TOKEN = re.compile(r"\(|\)|,|;|:[^,();]+|[^,():;]+")


def parse(text):
    """Independent tokenising Newick parser -> list of nodes in preorder (root first)."""
    root = N(); cur = root; stack = []
    for tok in TOKEN.findall(text.strip()):
        if tok == "(":
            stack.append(cur); n = N(cur); cur.kids.append(n); cur = n
        elif tok == ",":
            n = N(stack[-1]); stack[-1].kids.append(n); cur = n
        elif tok == ")":
            cur = stack.pop()
        elif tok == ";":
            break
        elif tok.startswith(":"):
            cur.blen = tok[1:]
        else:
            cur.label = tok.strip()
    assert not stack
    order, st = [], [root]
    while st:
        x = st.pop(); order.append(x); st.extend(reversed(x.kids))
    return order


def tipsets(order):
    ts = {}
    for x in reversed(order):
        ts[id(x)] = frozenset([x.label]) if not x.kids else frozenset().union(*(ts[id(k)] for k in x.kids))
    return ts


def bip(s, universe):
    """Canonical unrooted split: the side without the lexicographically smallest tip."""
    ref = min(universe)
    return frozenset(universe - s) if ref in s else frozenset(s)


def strip_internal_labels(text):
    return re.sub(r"\)[^,():;]+", ")", text)


def sha(p_or_b):
    return hashlib.sha256(p_or_b if isinstance(p_or_b, bytes) else Path(p_or_b).read_bytes()).hexdigest()


def tsv(p):
    lines = Path(p).read_text().splitlines()
    h = lines[0].split("\t")
    return [dict(zip(h, l.split("\t"))) for l in lines[1:] if l.strip()]


# ----------------------------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def out(tmp_path_factory):
    o = tmp_path_factory.mktemp("export_pr4")
    db_before = sha(DB)
    r = subprocess.run([sys.executable, str(REPO / "tools/export_web_data.py"), "--repo", str(REPO), "--db", str(DB),
                        "--out", str(o)], capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, r.stderr
    assert sha(DB) == db_before
    return o / REL


@pytest.fixture(scope="module")
def ex(out):
    return json.loads((out / "phylogeny/explorer.json").read_text())


@pytest.fixture(scope="module")
def clades(out):
    return json.loads((out / "clades.json").read_text())


@pytest.fixture(scope="module")
def rooted():
    order = parse(TREE.read_text())
    return order, tipsets(order)


@pytest.fixture(scope="module")
def run1_support():
    order = parse(RUN1.read_text())
    ts = tipsets(order)
    universe = ts[id(order[0])]
    lab = {}
    for x in order[1:]:
        if x.kids:
            k = bip(ts[id(x)], universe)
            assert k not in lab
            lab[k] = x.label or None
    return lab, universe


@pytest.fixture(scope="module")
def con():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    yield c
    c.close()


# ----------------------------------------------------------------------------------------------- tips
def test_472_unique_tips_reconcile(ex, rooted, run1_support):
    order, ts = rooted
    tips = [x.label for x in order if not x.kids]
    assert len(tips) == len(set(tips)) == 472
    assert set(tips) == {r["source_acc"] for r in tsv(REFPKG / "tips.tsv")} == set(ex["tips"]) == run1_support[1]
    assert ex["n_tips"] == 472 and ex["n_nodes"] == len(order) == 943 and ex["n_internal_incl_root"] == 471
    roles = collections.Counter(t["tip_role"] for t in ex["tips"].values())
    assert roles == {"cl0.6_representative": 394, "anchor_characterized": 57, "outgroup_heliorhodopsin": 15,
                     "seed": 4, "boundary_schizorhodopsin": 2}
    assert ex["meta"]["tip_roles"] == dict(sorted(roles.items()))


def test_absent_and_outgroup_tips(ex, con):
    corpus = {r[0]: r[1] for r in con.execute("SELECT source_acc, mrdb_acc FROM v_master")}
    absent = sorted(t for t, v in ex["tips"].items() if not v["in_corpus"])
    assert absent == ["QBQ84355", "QBQ84358"]
    for t in absent:
        v = ex["tips"][t]
        assert t not in corpus and v["mrdb_acc"] is None and v["tip_role"] == "boundary_schizorhodopsin"
        assert v["func_class"] is None and v["evidence_level"] is None and v["clade_state"] is None
        assert "not in the v1.6.1 corpus" in v["annotation_source"]
    for t, v in ex["tips"].items():
        if v["in_corpus"]:
            assert v["mrdb_acc"] == corpus[t]
    og = sorted(t for t, v in ex["tips"].items() if v["tip_role"] == "outgroup_heliorhodopsin")
    assert len(og) == 15
    for t in og:
        v = ex["tips"][t]
        assert v["in_corpus"] and v["clade_state"] == "outgroup_reference_tip"
        assert v["level1"] is None and v["backbone_group"] is None and v["subclade"] is None


def test_tip_annotations_match_db(ex, con):
    con.row_factory = sqlite3.Row
    vm = {r["source_acc"]: r for r in con.execute("SELECT * FROM v_master")}
    con.row_factory = None
    annot = {r["source_acc"]: r for r in tsv(REFPKG / "tips_annot.tsv")}
    for t, v in ex["tips"].items():
        a = annot[t]
        assert v["phylum"] == (a["phylum"] or None) and v["func_class_v14"] == (a["func_class_v14"] or None)
        if t in vm:
            for k in ("organism", "protein_name", "tax_domain", "helixC_motif", "func_class", "evidence_level"):
                assert v[k] == vm[t][k], (t, k)


# ----------------------------------------------------------------------------------------------- topology
def test_nodes_align_with_frozen_rooted_preorder(ex, rooted):
    order, ts = rooted
    pre = {id(x): i for i, x in enumerate(order)}
    internal = [x for x in order if x.kids]
    tip_order = {x.label: i for i, x in enumerate(x for x in order if not x.kids)}
    assert len(ex["nodes"]) == len(internal) == 471
    for k, (x, n) in enumerate(zip(internal, ex["nodes"])):
        s = ts[id(x)]
        assert n["internal_index"] == k and n["pre"] == pre[id(x)]
        assert n["parent"] == (None if x.parent is None else pre[id(x.parent)])
        assert n["n_tips"] == len(s) and n["is_root"] == (x.parent is None)
        assert n["first_tip"] == min(s, key=tip_order.get) and n["last_tip"] == max(s, key=tip_order.get)
        assert n["rooted_label"] == (x.label or None)
        assert (n["length"] is None and x.blen is None) or n["length"] == float(x.blen)
    for x in order:
        if not x.kids:
            assert ex["tips"][x.label]["pre"] == pre[id(x)] and ex["tips"][x.label]["length"] == float(x.blen)


def test_every_rooted_bipartition_exists_in_run1(rooted, run1_support):
    order, ts = rooted
    lab, universe = run1_support
    splits = collections.Counter(bip(ts[id(x)], universe) for x in order[1:] if x.kids)
    assert all(k in lab for k in splits)
    # the root's two children are the same unrooted split (outgroup | ingroup); nothing else repeats
    assert sorted(splits.values(), reverse=True)[:2] == [2, 1]
    assert len(lab) == 469 and sum(1 for v in lab.values() if v) == 469


# ----------------------------------------------------------------------------------------------- support
def test_all_support_values_equal_run1_by_bipartition(ex, rooted, run1_support):
    order, ts = rooted
    lab, universe = run1_support
    internal = [x for x in order if x.kids]
    for x, n in zip(internal, ex["nodes"]):
        if x.parent is None:
            assert n["run1_label"] is None and n["sh_alrt"] is None and n["ufboot"] is None
            assert not n["support_displayed"]
            continue
        want = lab[bip(ts[id(x)], universe)]
        sh, uf = (float(v) for v in LABEL_RE.match(want).groups())
        assert n["run1_label"] == want and n["sh_alrt"] == sh and n["ufboot"] == uf
        assert n["label_agrees"] == ((x.label or None) == want)


def test_17_support_label_discrepancies_regression(ex):
    got = [(n["internal_index"], n["n_tips"], n["rooted_label"], n["run1_label"])
           for n in ex["nodes"] if not n["is_root"] and not n["label_agrees"]]
    assert got == DISCREPANCIES
    assert all(n["last_tip"] == "A0A3E2H811" for n in ex["nodes"] if not n["is_root"] and not n["label_agrees"])
    assert ex["meta"]["n_label_disagreements"] == 17
    assert sum(1 for n in ex["nodes"] if not n["is_root"] and n["label_agrees"]) == 453


def test_support_audit_file_consistent(out, ex):
    sa = json.loads((out / "phylogeny/support_audit.json").read_text())
    assert sa["n_disagree"] == 17
    for a, n in zip(sa["nodes"], ex["nodes"]):
        assert (a["preorder_index"], a["n_tips"], a["first_tip"], a["last_tip"], a["rooted_label"],
                a["iqtree_run1_label"]) == (n["internal_index"], n["n_tips"], n["first_tip"], n["last_tip"],
                                            n["rooted_label"], n["run1_label"])


def test_root_split_shown_once(ex, rooted):
    order, ts = rooted
    root = order[0]
    assert len(root.kids) == 2
    by_pre = {n["pre"]: n for n in ex["nodes"]}
    kids = [by_pre[n["pre"]] for n in ex["nodes"] if n["parent"] == 0]
    og = [k for k in kids if k["n_tips"] == 15]
    ing = [k for k in kids if k["n_tips"] == 457]
    assert len(og) == 1 and len(ing) == 1
    og, ing = og[0], ing[0]
    assert og["root_split_shared"] and ing["root_split_shared"]
    assert og["is_outgroup_root_child"] and not ing["is_outgroup_root_child"]
    assert og["support_displayed"] and not ing["support_displayed"]
    assert og["run1_label"] == ing["run1_label"] == "98.8/100"
    assert ex["root_split"] == {"edge_id": ex["root_split"]["edge_id"], "nodes": sorted([og["pre"], ing["pre"]]),
                                "displayed_on": og["pre"], "run1_label": "98.8/100"}
    assert sum(1 for n in ex["nodes"] if n["root_split_shared"]) == 2
    assert sum(1 for n in ex["nodes"] if n["support_displayed"]) == 469
    between = {v["tip_role"] for v in ex["tips"].values() if og["pre"] < v["pre"] < ing["pre"]}
    assert between == {"outgroup_heliorhodopsin"}


def test_node_447_unlabelled_in_rooted_file_gets_run1_support(ex):
    n = ex["nodes"][447]
    assert n["n_tips"] == 25 and n["rooted_label"] is None and n["run1_label"] == "40/51"
    assert n["support_displayed"]


# ----------------------------------------------------------------------------------------------- MR_CLD3_017
def test_mr_cld3_017_legacy_assignment(ex, clades, con, rooted):
    order, ts = rooted
    c = next(x for x in clades["level1"] if x["clade_id"] == "MR_CLD3_017")
    sa = c["support_audit"]
    assert (sa["iqtree_run1_sh_alrt"], sa["iqtree_run1_ufboot"]) == (50.3, 72.0)
    assert sa["iqtree_run1_label"] == "50.3/72" and sa["rooted_file_label"] == "100/100" and sa["db_label"] == "100/100"
    assert sa["iqtree_run1_meets_support_thresholds"] is False and sa["db_matches_iqtree_run1"] is False
    n = next(n for n in ex["nodes"] if n["pre"] == c["mrca_node"])
    assert n["internal_index"] == 372 and n["n_tips"] == 100 and n["first_tip"] == "A0AAV9X7P9"
    assert n["clade_mrca"] == ["MR_CLD3_017"] and (n["sh_alrt"], n["ufboot"]) == (50.3, 72.0)
    assert n["sh_alrt"] < 80 and n["ufboot"] < 95
    # historical membership retained: frozen TSV, DB clade_tip, exported tips and the MRCA tip set all agree
    tsv_tips = {r["source_acc"] for r in tsv(REFPKG / "clades/MR_CLD3_tips.tsv") if r["clade_id"] == "MR_CLD3_017"}
    db_tips = {r[0] for r in con.execute("SELECT source_acc FROM clade_tip WHERE clade_id = 'MR_CLD3_017'")}
    ex_tips = {t for t, v in ex["tips"].items() if v["level1"] == "MR_CLD3_017"}
    node = next(x for i, x in enumerate(order) if i == c["mrca_node"])
    assert len(tsv_tips) == 100 and tsv_tips == db_tips == ex_tips == ts[id(node)]
    # frozen DB values unchanged; record assignments unchanged
    assert con.execute("SELECT sh_alrt, ufboot, n_tips FROM clade WHERE clade_id = 'MR_CLD3_017'").fetchone() == \
        (100.0, 100.0, 100)
    n_conf = con.execute("SELECT COUNT(*) FROM v_master WHERE clade_id = 'MR_CLD3_017'").fetchone()[0]
    assert c["n_records_confident"] == n_conf == 1646
    assert c["jaccard_run2"] == 0.52 and c["robustness_caveat"] is True
    # it is the only level-1 group failing the rule on corrected support
    assert [x["clade_id"] for x in clades["level1"]
            if not x["support_audit"]["iqtree_run1_meets_support_thresholds"]] == ["MR_CLD3_017"]


# ----------------------------------------------------------------------------------------------- clades
def test_clades_17_plus_2_and_30_subclades_reconcile(clades, ex, rooted, con):
    order, ts = rooted
    lv = clades["level1"]
    assert sorted(x["clade_id"] for x in lv if x["kind"] == "clade") == [f"MR_CLD3_{i:03d}" for i in range(1, 18)]
    assert sorted(x["clade_id"] for x in lv if x["kind"] == "backbone_group") == ["MR_CLD3_B01", "MR_CLD3_B02"]
    assert len(clades["subclades"]) == 30
    ct = collections.defaultdict(set)
    for r in tsv(REFPKG / "clades/MR_CLD3_tips.tsv"):
        ct[r["clade_id"]].add(r["source_acc"])
        if r.get("subclade_id"):
            ct[r["subclade_id"]].add(r["source_acc"])
    sub_tsv = {r["subclade_id"]: r for r in tsv(REFPKG / "clades/MR_CLD3_subclades.tsv")}
    assert set(sub_tsv) | {"MR_CLD3_B01", "MR_CLD3_B02"} >= {s["clade_id"] for s in clades["subclades"]}
    mrca_nodes = collections.defaultdict(list)
    for x in lv + clades["subclades"]:
        node = order[x["mrca_node"]]
        assert ts[id(node)] == ct[x["clade_id"]], x["clade_id"]
        assert len(ct[x["clade_id"]]) == x["n_tips"]
        mrca_nodes[x["mrca_node"]].append(x["clade_id"])
    for n in ex["nodes"]:
        assert sorted(n["clade_mrca"] + n["subclade_mrca"]) == sorted(mrca_nodes.get(n["pre"], []))
    for s in clades["subclades"]:
        assert s["parent_clade_id"] in {x["clade_id"] for x in lv} | {"backbone"} or s["parent_clade_id"]
        if s["clade_id"] in sub_tsv:
            assert s["parent_clade_id"] == sub_tsv[s["clade_id"]]["parent_clade"]
            assert s["n_tips"] == int(sub_tsv[s["clade_id"]]["n_tips"])


def test_subclade_and_clade_support_are_run1(clades, rooted, run1_support):
    order, ts = rooted
    lab, universe = run1_support
    for x in clades["level1"] + clades["subclades"]:
        want = lab[bip(ts[id(order[x["mrca_node"]])], universe)]
        sh, uf = (float(v) for v in want.split("/"))
        sa = x["support_audit"]
        assert sa["iqtree_run1_label"] == want and (sa["iqtree_run1_sh_alrt"], sa["iqtree_run1_ufboot"]) == (sh, uf)
        assert sa["iqtree_run1_meets_support_thresholds"] == (sh >= 80 and uf >= 95)


def test_function_consensus_is_official_v160(clades, con):
    con.row_factory = sqlite3.Row
    cfc = {r["group_id"]: r for r in con.execute("SELECT * FROM clade_function_consensus")}
    con.row_factory = None
    for x in clades["level1"] + clades["subclades"]:
        f, r = x["function_consensus"], cfc[x["clade_id"]]
        assert (f["clade_function"], f["consensus_status"], f["n_E1"], f["n_records"], f["top_frac"]) == \
            (r["clade_function"], r["consensus_status"], r["n_E1"], r["n_records"], r["top_frac"])


def test_e1_anchors_and_representatives(clades, con):
    for x in clades["level1"]:
        want = {r[0] for r in con.execute("SELECT source_acc FROM v_master WHERE clade_id = ? AND evidence_level = 'E1'",
                                          (x["clade_id"],))}
        assert {a["source_acc"] for a in x["e1_anchors"]} == want
        # the official consensus counts counts-eligible E1 records only (e.g. MR_CLD3_009: 12 listed, 11 counted)
        assert x["function_consensus"]["n_E1"] == sum(1 for a in x["e1_anchors"] if a["counts_eligible"])
        reps = x["representatives"]
        ref_in_corpus = {r[0] for r in con.execute(
            "SELECT ct.source_acc FROM clade_tip ct JOIN v_master v USING (source_acc) "
            "WHERE ct.clade_id = ? OR ct.subclade_id = ?", (x["clade_id"], x["clade_id"]))}
        assert len(ref_in_corpus) == x["n_reference_tips_in_corpus"]
        assert len(reps) == min(12, len(want | ref_in_corpus))
        assert len({r["source_acc"] for r in reps}) == len(reps)
        assert reps[:min(12, len(want))] == [dict(a, reason="E1 record assigned to this group")
                                             for a in x["e1_anchors"]][:12]


def test_placement_counts_match_db(clades, ex, con):
    q = lambda sql, *a: dict(con.execute(sql, a).fetchall())
    assert ex["meta"]["placement_status_counts"] == {"assigned": 3617, "distant_assigned": 720,
                                                     "distant_tentative": 4, "outgroup_heliorhodopsin": 456,
                                                     "unassigned": 199}
    for x in clades["level1"] + clades["subclades"]:
        if x["level"] == 1 and x["kind"] == "clade":
            want = q("SELECT clade_call_qc, COUNT(*) FROM placement WHERE is_current = 1 AND tree_id = 'MR_RT_003' "
                     "AND clade_id = ? GROUP BY 1", x["clade_id"])
        else:
            want = q("SELECT subclade_call, COUNT(*) FROM placement WHERE is_current = 1 AND tree_id = 'MR_RT_003' "
                     "AND subclade_id = ? GROUP BY 1", x["clade_id"])
        assert x["placement_counts"]["counts"] == want, x["clade_id"]


# ----------------------------------------------------------------------------------------------- placements
def test_edge_map_matches_db_tree_edge_bipartitions(ex, rooted, con):
    order, ts = rooted
    universe = ts[id(order[0])]
    tip_acc = dict(con.execute("SELECT node_id, source_acc FROM tree_node WHERE tree_id = 'MR_RT_003' AND kind = 'tip'"))
    edges = con.execute("SELECT edge_id, parent_node, child_node FROM tree_edge WHERE tree_id = 'MR_RT_003'").fetchall()
    kids = collections.defaultdict(list)
    for _, p, c in edges:
        kids[p].append(c)
    memo = {}

    def below(n):
        st = [(n, False)]
        while st:
            x, done = st.pop()
            if x in memo:
                continue
            if x in tip_acc:
                memo[x] = frozenset([tip_acc[x]])
            elif done:
                memo[x] = frozenset().union(*(memo[k] for k in kids[x]))
            else:
                st.append((x, True)); st.extend((k, False) for k in kids[x])
        return memo[n]
    by_split = collections.defaultdict(list)
    for i, x in enumerate(order[1:], 1):
        by_split[bip(ts[id(x)], universe)].append(i)
    assert len(edges) == len(ex["edge_map"]) == 941
    for e, _, c in edges:
        assert ex["edge_map"][e] == sorted(by_split[bip(below(c), universe)])
    shared = [e for e, v in ex["edge_map"].items() if len(v) == 2]
    assert shared == [ex["root_split"]["edge_id"]]
    best = {r[0] for r in con.execute("SELECT best_edge FROM placement WHERE is_current = 1 AND tree_id = 'MR_RT_003'")}
    assert best <= set(ex["edge_map"])


def test_placements_are_not_tips(ex, con):
    placed = {r[0] for r in con.execute("SELECT source_acc FROM placement WHERE is_current = 1 AND tree_id = 'MR_RT_003'")}
    assert len(placed) == 4996 and not (placed & set(ex["tips"]))


# ----------------------------------------------------------------------------------------------- files
def test_frozen_copies_byte_identical(out):
    assert (out / "phylogeny/MR_RT_003.rooted.treefile").read_bytes() == TREE.read_bytes()
    assert (out / "phylogeny/run1.treefile").read_bytes() == RUN1.read_bytes()
    assert sha(TREE) == "c56196970698decea8384c1cad97545794268e6d8a2df2b195e7d35d5ded9aef"


def test_derived_newick_only_relabels_internal_nodes(out, ex, rooted, run1_support):
    text = (out / "phylogeny/MR_RT_003.rooted.run1-support.DERIVED.nwk").read_text()
    frozen = TREE.read_text()
    assert strip_internal_labels(text) == strip_internal_labels(frozen)
    d = parse(text)
    order, ts = rooted
    lab, universe = run1_support
    assert [x.blen for x in d] == [x.blen for x in order]
    assert [x.label for x in d if not x.kids] == [x.label for x in order if not x.kids]
    dint, rint = [x for x in d if x.kids], [x for x in order if x.kids]
    changed = 0
    for x, n, r in zip(dint, ex["nodes"], rint):
        if n["is_root"] or (n["root_split_shared"] and not n["is_outgroup_root_child"]):
            assert x.label == ""
        else:
            assert x.label == n["run1_label"] == lab[bip(ts[id(r)], universe)]
        changed += x.label != r.label
    assert changed == 17 == ex["meta"]["derived_newick"]["n_labels_changed"]
    assert sorted(x.label for x in dint if x.label) == sorted(v for v in lab.values() if v)
    readme = (out / "phylogeny/MR_RT_003.rooted.run1-support.DERIVED.README.txt").read_text()
    assert readme.startswith("MR_RT_003.rooted.run1-support.DERIVED.nwk") and "DERIVED FILE" in readme
    assert sha(TREE) in readme and sha(RUN1) in readme and sha(text.encode()) in readme
    assert ex["meta"]["derived_newick"]["sha256"] == sha(text.encode())


def test_export_manifest_lists_phylogeny_files(out):
    em = json.loads((out / "export_manifest.json").read_text())
    files = {f["path"]: f for f in em["files"]}
    for rel in ("phylogeny/explorer.json", "phylogeny/run1.treefile", "phylogeny/MR_RT_003.rooted.treefile",
                "phylogeny/MR_RT_003.rooted.run1-support.DERIVED.nwk",
                "phylogeny/MR_RT_003.rooted.run1-support.DERIVED.README.txt"):
        f = files[f"{REL}/{rel}"]
        assert f["sha256"] == sha(out / rel)
    assert em["schema_version"] in ("1.3.0", "1.4.0")  # 1.2.0 in PR-4; 1.3.0 PR-4a; 1.4.0 PR-5 (additive)
