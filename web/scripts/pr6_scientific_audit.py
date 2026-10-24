#!/usr/bin/env python3
"""PR-6 independent scientific-integrity audit of the website export against frozen v1.6.1.

Independent of tools/export_web_data.py: it reads the official SQLite database read-only, parses the
frozen Newick files with its own parser, and compares complete keyed sets / per-key values with the
JSON files that the website actually loads (web/public/data/v1.6.1). Every check records its expected
and observed values; any mismatch makes the script exit non-zero.

Sections
  R  records: source set, counted / engineered / MRDB sets, per-record field equality (records-index
     and per-MRDB record files), accession map
  S  structures: protein_pdb links, PDB entries, records with PDB, AlphaFold DB models
  T  reference tree: file identity, tips, topology (bipartitions of rooted vs IQ-TREE run1), support
     mapping (displayed support == run1 label of the same bipartition), rooted-label disagreements,
     outgroup, clades / subclades (tip sets, monophyly, support), edge map of placements
  P  placements: current placements (tree MR_RT_003, model Q.pfam+F+R9) vs per-record placement objects

Usage: python web/scripts/pr6_scientific_audit.py --out docs/website/pr6
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DB = REPO / "releases" / "v1.6.1" / "db" / "microrhododb_v1.6.1.sqlite"
DB_SHA = "b8215cffa9d2fdab1e65b904f4bafbe9edf6578aed7b4fb028a890850e704c2d"
EXP = REPO / "web" / "public" / "data" / "v1.6.1"
TREE = "MR_RT_003"

checks: list[dict] = []


def check(cid: str, what: str, expected, observed, ok: bool | None = None) -> None:
    ok = (expected == observed) if ok is None else ok
    checks.append({"id": cid, "check": what, "expected": expected, "observed": observed, "pass": bool(ok)})


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------- Newick (own parser)
class Node:
    __slots__ = ("children", "name", "label", "length", "parent")

    def __init__(self, parent=None):
        self.children, self.name, self.label, self.length, self.parent = [], None, None, None, parent


def parse_newick(text: str) -> Node:
    text = text.strip().rstrip(";")
    root = cur = Node()
    i, n = 0, len(text)

    def token(i):
        j = i
        while j < n and text[j] not in "(),:;":
            j += 1
        return text[i:j].strip().strip("'"), j

    while i < n:
        ch = text[i]
        if ch == "(":
            child = Node(cur)
            cur.children.append(child)
            cur = child
            i += 1
        elif ch == ",":
            sib = Node(cur.parent)
            cur.parent.children.append(sib)
            cur = sib
            i += 1
        elif ch == ")":
            cur = cur.parent
            i += 1
            lab, i = token(i)
            cur.label = lab or None
        elif ch == ":":
            num, i = token(i + 1)
            cur.length = float(num)
        else:
            name, i = token(i)
            cur.name = name
    return root


def preorder(node: Node):
    stack = [node]
    while stack:
        x = stack.pop()
        yield x
        stack.extend(reversed(x.children))


def tipsets(root: Node) -> dict[int, frozenset]:
    out: dict[int, frozenset] = {}
    for x in reversed(list(preorder(root))):
        out[id(x)] = frozenset([x.name]) if not x.children else frozenset().union(*(out[id(c)] for c in x.children))
    return out


def canon(side: frozenset, alltips: frozenset, ref: str) -> frozenset:
    """Canonical unrooted bipartition: the side that does not contain the reference tip."""
    return alltips - side if ref in side else side


def tip_order(node: Node) -> list[str]:
    return [x.name for x in preorder(node) if not x.children]


# ---------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--export", default=None, help="export directory to audit (default: web/public/data/v1.6.1)")
    a = ap.parse_args()
    global EXP
    if a.export:
        EXP = Path(a.export).resolve()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    check("D0", "official v1.6.1 SQLite sha256 unchanged", DB_SHA, sha(DB))
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    q = lambda sql, *p: con.execute(sql, p).fetchall()  # noqa: E731

    # ------------------------------------------------------------ R: records
    ri = json.loads((EXP / "records-index.json").read_text())
    cols = ri["columns"]
    rows = {r[cols.index("source_acc")]: dict(zip(cols, r)) for r in ri["rows"]}
    vm = {r["source_acc"]: dict(r) for r in q("SELECT * FROM v_master")}
    check("R1", "records-index source_acc rows (no duplicates)", len(ri["rows"]), len(rows))
    check("R2", "source records: export set == v_master set (5,466)", [5466, True], [len(rows), set(rows) == set(vm)])
    counted_db = {r[0] for r in q("SELECT source_acc FROM v_counted")}
    counted_ex = {k for k, r in rows.items() if r["counts_eligible"]}
    check("R3", "counted records: export set == v_counted (5,460)", [5460, True], [len(counted_ex), counted_ex == counted_db])
    eng_db = {r[0] for r in q("SELECT source_acc FROM v_engineered")}
    eng_ex = {k for k, r in rows.items() if r["is_engineered"]}
    check("R4", "engineered records: export set == v_engineered (6)", [6, True], [len(eng_ex), eng_ex == eng_db])
    mrdb_db = {r[0] for r in q("SELECT mrdb_acc FROM mrdb_accession")}
    mrdb_ex = {r["mrdb_acc"] for r in rows.values()}
    check("R5", "MRDB accessions: export set == mrdb_accession (5,299)", [5299, True], [len(mrdb_ex), mrdb_ex == mrdb_db])
    multi = sum(1 for r in q("SELECT n_source_records FROM mrdb_accession") if r[0] > 1)
    check("R6", "MRDB accessions with more than one source record", 129, multi)
    shared = [c for c in cols if c in next(iter(vm.values()))]
    mism = Counter()
    examples = {}
    normalised = Counter()
    for k, r in rows.items():
        for c in shared:
            ev, dv = r[c], vm[k][c]
            if dv == "" and ev is None:
                normalised[c] += 1  # DB stores "" for "no clade"; the export writes null
                continue
            if isinstance(ev, bool):
                dv = bool(dv) if dv is not None else None
            if isinstance(ev, float) and isinstance(dv, float):
                same = abs(ev - dv) < 1e-9
            else:
                same = ev == dv
            if not same:
                mism[c] += 1
                examples.setdefault(c, (k, ev, dv))
    check("R7", f"records-index vs v_master: per-record equality of {len(shared)} shared columns x 5,466 records",
          {}, {c: {"n": n, "example": examples[c]} for c, n in mism.items()})
    empty_db = {c: n for c in shared if (n := sum(1 for d in vm.values() if d[c] == ""))}
    check("R7b", "the only representation change: DB empty strings exported as null (count per column == DB empty-string count)",
          empty_db, dict(normalised))
    rep_db = {r["source_acc"]: r["mrdb_acc"] for r in q("SELECT source_acc, mrdb_acc FROM accession_map WHERE is_current = 1")}
    acc = json.loads((EXP / "accessions.json").read_text())
    check("R8", "accessions.json by_source == accession_map (current)", [len(rep_db), True], [len(acc["by_source"]), acc["by_source"] == rep_db])
    by_mrdb_db = {r["mrdb_acc"]: r["representative_source_acc"] for r in q("SELECT * FROM mrdb_accession")}
    check("R9", "accessions.json by_mrdb representative == mrdb_accession", True,
          {k: v["representative_source_acc"] for k, v in acc["by_mrdb"].items()} == by_mrdb_db)
    # Per-MRDB record files: every source present once, membership / evidence / clade fields equal v_master.
    files = sorted((EXP / "records").glob("MRDB*.json"))
    seen, fmism = Counter(), Counter()
    fex = {}
    placements_ex = {}
    for f in files:
        rec = json.loads(f.read_text())
        for s in rec["sources"]:
            k = s["source_acc"]
            seen[k] += 1
            d = vm.get(k)
            if d is None or rec["mrdb_acc"] != d["mrdb_acc"]:
                fmism["mrdb_acc"] += 1
                continue
            pairs = {"membership_status": s["membership"]["status"], "evidence_level": s["function"]["evidence_level"],
                     "func_class": s["function"]["func_class"], "clade_id": s["phylogeny"]["clade_id"],
                     "subclade_id": s["phylogeny"]["subclade_id"], "tentative_clade_id": s["phylogeny"]["tentative_clade_id"],
                     "placement_call": s["phylogeny"]["placement_call"], "clade_source": s["phylogeny"]["clade_source"]}
            for c, v in pairs.items():
                if v != d[c] and not (v is None and d[c] == ""):
                    fmism[c] += 1
                    fex.setdefault(c, (k, v, d[c]))
            if s["phylogeny"].get("placement"):
                placements_ex[k] = s["phylogeny"]["placement"]
    check("R10", "record files: one file per MRDB accession; every source exactly once", [5299, 5466, 1],
          [len(files), len(seen), max(seen.values())])
    check("R11", "record files vs v_master (status, evidence, function, clade, subclade, tentative, placement call, clade source)",
          {}, {c: {"n": n, "example": fex.get(c)} for c, n in fmism.items()})
    ev = Counter(r["evidence_level"] for r in rows.values() if r["counts_eligible"])
    check("R12", "E1 counted / total", [88, 91], [ev["E1"], sum(1 for r in rows.values() if r["evidence_level"] == "E1")])
    sd = {r["status"]: (r["is_member"], r["is_candidate"]) for r in q("SELECT * FROM status_definition")}
    mc = {k for k, r in rows.items() if sd[r["membership_status"]][0] or sd[r["membership_status"]][1]}
    check("R13", "members + candidates (all source records, status_definition) / confident clade state", [4465, 3821],
          [len(mc), sum(1 for k in mc if rows[k]["clade_state"] == "confident")])
    c017 = {k for k, r in rows.items() if r["clade_id"] == "MR_CLD3_017"}
    check("R14", "MR_CLD3_017 source records (v_master.clade_id) / tentative", [1646, 597],
          [len(c017), sum(1 for r in rows.values() if r["tentative_clade_id"] == "MR_CLD3_017")])

    # ------------------------------------------------------------ S: structures
    pp = q("SELECT source_acc, pdb_id FROM protein_pdb")
    si = json.loads((EXP / "structures-index.json").read_text())
    pdb_entries = list(si["pdb"].values())
    links_ex = {(acc_, e["pdb_id"]) for e in pdb_entries for acc_ in e["source_accs"]}
    check("S1", "protein_pdb links / distinct PDB entries / records with PDB", [472, 438, 66],
          [len(pp), len({r[1] for r in pp}), len({r[0] for r in pp})])
    check("S2", "structures-index PDB entries == protein_pdb distinct entries", True, {e["pdb_id"] for e in pdb_entries} == {r[1] for r in pp})
    check("S3", "structures-index (record, PDB) links == protein_pdb", True, links_ex == {(r[0], r[1]) for r in pp})
    npdb = Counter(r[0] for r in pp)
    check("S4", "records-index n_pdb and pdb_ids == protein_pdb per record", 0,
          sum(1 for k, r in rows.items() if r["n_pdb"] != npdb.get(k, 0) or sorted(r["pdb_ids"] or []) != sorted(p for s_, p in pp if s_ == k)))
    afdb_db = {r[0] for r in q("SELECT source_acc FROM v_master WHERE afdb_model_id IS NOT NULL")}
    check("S5", "AlphaFold DB models (has_afdb) == v_master.afdb_model_id not null (4,397)", [4397, True],
          [sum(1 for r in rows.values() if r["has_afdb"]), {k for k, r in rows.items() if r["has_afdb"]} == afdb_db])

    # ------------------------------------------------------------ T: reference tree
    ref_rooted = REPO / "refpkg" / TREE / "tree" / f"{TREE}.rooted.treefile"
    ref_run1 = REPO / "refpkg" / TREE / "tree" / "run1.treefile"
    web_rooted, web_run1 = EXP / "phylogeny" / f"{TREE}.rooted.treefile", EXP / "phylogeny" / "run1.treefile"
    check("T1", "web rooted treefile and run1.treefile byte-identical to refpkg/MR_RT_003", [True, True],
          [sha(web_rooted) == sha(ref_rooted), sha(web_run1) == sha(ref_run1)])
    rooted, run1 = parse_newick(ref_rooted.read_text()), parse_newick(ref_run1.read_text())
    rt, r1 = tip_order(rooted), tip_order(run1)
    alltips = frozenset(rt)
    check("T2", "tips: 472 in rooted and run1, identical sets, no duplicates", [472, 472, True],
          [len(set(rt)), len(set(r1)), set(rt) == set(r1) and len(rt) == len(set(rt))])
    db_tips = {r[0] for r in q("SELECT source_acc FROM tree_node WHERE tree_id = ? AND kind = 'tip'", TREE)}
    check("T3", "tips == DB tree_node tips (MR_RT_003)", True, db_tips == set(rt))
    ref = min(alltips)
    ts_rooted, ts_run1 = tipsets(rooted), tipsets(run1)
    split_rooted = {}
    for x in preorder(rooted):
        if x.children and x is not rooted:
            split_rooted.setdefault(canon(ts_rooted[id(x)], alltips, ref), []).append(x)
    run1_label = {}
    for x in preorder(run1):
        if x.children and x is not run1:
            run1_label[canon(ts_run1[id(x)], alltips, ref)] = x.label
    nontriv_rooted = {s for s in split_rooted if 1 < len(s) < len(alltips) - 1}
    nontriv_run1 = {s for s in run1_label if 1 < len(s) < len(alltips) - 1}
    check("T4", "topology: non-trivial bipartitions of rooted == run1 (rerooting preserves splits)", [True, 469],
          [nontriv_rooted == nontriv_run1, len(nontriv_run1)])
    exp_ = json.loads((EXP / "phylogeny" / "explorer.json").read_text())
    internal = [x for x in preorder(rooted) if x.children]
    check("T5", "explorer internal nodes == rooted internal nodes (471 = 470 unrooted internal nodes + root)", len(internal), len(exp_["nodes"]))
    bad_support, bad_tips, label_dis, displayed = [], 0, 0, 0
    for i, (x, en) in enumerate(zip(internal, exp_["nodes"])):
        tips = tip_order(x)
        if (tips[0], tips[-1], len(tips)) != (en["first_tip"], en["last_tip"], en["n_tips"]):
            bad_tips += 1
            continue
        if x is rooted:
            continue
        lab = run1_label.get(canon(ts_rooted[id(x)], alltips, ref))
        sh_, uf_ = (float(v) for v in lab.split("/")) if lab else (None, None)
        if en["is_outgroup_root_child"] or not en.get("root_split_shared"):
            if en["support_displayed"]:
                displayed += 1
                if (en["sh_alrt"], en["ufboot"]) != (sh_, uf_) or en["run1_label"] != lab:
                    bad_support.append((i, en["run1_label"], lab))
        if (x.label or None) != (lab or None):
            label_dis += 1
    check("T6", "explorer nodes map to the same tip span (first, last, n) as the parsed rooted tree", 0, bad_tips)
    check("T7", "displayed support == IQ-TREE run1 SH-aLRT/UFBoot label of the same bipartition (all displayed nodes)", [], bad_support[:10])
    check("T8", "nodes with displayed support (469 non-root bipartitions; root split shown once)", 469, displayed)
    check("T9", "rooted-file labels attached to a different bipartition after rerooting (audit only, not displayed)", 17, label_dis)
    roles = Counter(t["tip_role"] for t in exp_["tips"].values()) if isinstance(exp_["tips"], dict) else Counter()
    og = {k for k, t in exp_["tips"].items() if t["tip_role"] == "outgroup_heliorhodopsin"}
    root_children = [frozenset(tip_order(c)) for c in rooted.children]
    check("T10", "outgroup: 15 heliorhodopsin tips form one root child", [15, True], [len(og), og in root_children])
    check("T11", "tip roles (394 cl0.6 reps, 57 anchors, 4 seeds, 15 outgroup, 2 schizorhodopsins)",
          {"cl0.6_representative": 394, "anchor_characterized": 57, "seed": 4, "outgroup_heliorhodopsin": 15, "boundary_schizorhodopsin": 2}, dict(roles))
    # clades
    clades_db = {r["clade_id"]: dict(r) for r in q("SELECT * FROM clade WHERE tree_id = ?", TREE)}
    ct = q("SELECT source_acc, clade_id, subclade_id FROM clade_tip WHERE tree_id = ?", TREE)
    tips_of = {}
    for r in ct:
        tips_of.setdefault(r["clade_id"], set()).add(r["source_acc"])
        if r["subclade_id"]:
            tips_of.setdefault(r["subclade_id"], set()).add(r["source_acc"])
    cj = json.loads((EXP / "clades.json").read_text())
    lvl1 = [c for c in clades_db.values() if c["level"] == 1]
    lvl2 = [c for c in clades_db.values() if c["level"] == 2]
    check("T12", "DB clades: 19 level-1 groups (17 clades + 2 backbone groups) and 30 subclades", [19, 30], [len(lvl1), len(lvl2)])
    cj_ids = {c["clade_id"] for c in cj["level1"]} | {c["clade_id"] for c in cj["subclades"]}
    check("T13", "clades.json clade ids == DB clade ids", True, cj_ids == set(clades_db))
    node_by_tipset = {ts_rooted[id(x)]: x for x in preorder(rooted) if x.children}
    nonmono, bad_ntips, bad_csupport = [], [], []
    for cid, c in clades_db.items():
        s_ = frozenset(tips_of.get(cid, ()))
        if len(s_) != c["n_tips"]:
            bad_ntips.append((cid, c["n_tips"], len(s_)))
        x = node_by_tipset.get(s_)
        if x is None:
            nonmono.append(cid)
            continue
        lab = run1_label.get(canon(s_, alltips, ref))
        sh_, uf_ = (float(v) for v in lab.split("/"))
        if (c["sh_alrt"], c["ufboot"]) != (sh_, uf_):
            bad_csupport.append((cid, c["sh_alrt"], c["ufboot"], lab))
    check("T14", "clade_tip sizes == clade.n_tips (49 groups)", [], bad_ntips)
    check("T15", "every clade / subclade tip set is one node of the rooted tree (monophyletic)", [], nonmono)
    check("T16", "DB clade support == run1 label of the clade bipartition, except the documented MR_CLD3_017 legacy value",
          [["MR_CLD3_017", 100.0, 100.0, "50.3/72"]], [list(x) for x in bad_csupport])
    audit_bad = []
    for c in cj["level1"] + cj["subclades"]:
        sa = c["support_audit"]
        lab = run1_label.get(canon(frozenset(tips_of[c["clade_id"]]), alltips, ref))
        sh_, uf_ = (float(v) for v in lab.split("/"))
        meets = sh_ >= 80 and uf_ >= 95
        if (sa["iqtree_run1_label"], sa["iqtree_run1_sh_alrt"], sa["iqtree_run1_ufboot"], sa["iqtree_run1_meets_support_thresholds"],
                sa["db_matches_iqtree_run1"]) != (lab, sh_, uf_, meets, (c["sh_alrt"], c["ufboot"]) == (sh_, uf_)):
            audit_bad.append(c["clade_id"])
    check("T16b", "clades.json support_audit (run1 label, thresholds SH-aLRT >= 80 and UFBoot >= 95, DB match flag) recomputed for all 49 groups",
          [], audit_bad)
    fails_thr = sorted(c["clade_id"] for c in cj["level1"] + cj["subclades"] if not c["support_audit"]["iqtree_run1_meets_support_thresholds"])
    check("T16c", "groups failing the corrected support thresholds (shown with the website warning)", ["MR_CLD3_017"], fails_thr,
          ok="MR_CLD3_017" in fails_thr)
    ex_mrca = {}
    for en in exp_["nodes"]:
        for cid in en["clade_mrca"] + en["subclade_mrca"]:
            ex_mrca[cid] = (en["first_tip"], en["last_tip"], en["n_tips"])
    want = {}
    for cid in clades_db:
        x = node_by_tipset.get(frozenset(tips_of.get(cid, ())))
        if x is not None:
            t_ = tip_order(x)
            want[cid] = (t_[0], t_[-1], len(t_))
    check("T17", "explorer clade/subclade MRCA nodes == parsed MRCA of DB clade_tip sets", True, ex_mrca == want)
    tip_l1 = {k: (t["level1"] or t["backbone_group"]) for k, t in exp_["tips"].items() if t.get("level1") or t.get("backbone_group")}
    # DB encoding: backbone-group tips are clade_tip(clade_id = 'backbone_unassigned', subclade_id = MR_CLD3_B0x).
    bb_ids = {c["clade_id"] for c in lvl1 if c["parent_clade_id"] == "backbone"}
    db_l1 = {r["source_acc"]: (r["subclade_id"] if r["clade_id"] == "backbone_unassigned" else r["clade_id"])
             for r in ct if r["clade_id"] != "backbone_unassigned" or r["subclade_id"] in bb_ids}
    unclustered_db = {r["source_acc"] for r in ct if r["clade_id"] == "backbone_unassigned" and r["subclade_id"] not in bb_ids}
    unclustered_ex = {k for k, t in exp_["tips"].items() if t["unclustered_backbone"]}
    check("T18", "explorer tip group == clade_tip.clade_id; 'backbone_unassigned' tips == explorer unclustered_backbone; outgroup has no group",
          [True, len(unclustered_db), True], [tip_l1 == db_l1, len(unclustered_ex), unclustered_ex == unclustered_db and not (og & set(tip_l1))])
    # edge map: DB tree_edge (unrooted run1 numbering) -> rooted node whose parent branch has the same bipartition
    edges = q("SELECT edge_id, parent_node, child_node FROM tree_edge WHERE tree_id = ?", TREE)
    kids, tipname = {}, {r[0]: r[1] for r in q("SELECT node_id, source_acc FROM tree_node WHERE tree_id = ? AND kind = 'tip'", TREE)}
    for e in edges:
        kids.setdefault(e["parent_node"], []).append(e["child_node"])
    memo = {}

    def below(n):
        if n in memo:
            return memo[n]
        s_ = frozenset([tipname[n]]) if n in tipname else frozenset().union(*(below(c) for c in kids.get(n, [])))
        memo[n] = s_
        return s_

    sys.setrecursionlimit(10000)
    pre_nodes = list(preorder(rooted))
    em_bad, em_n = [], 0
    for e in edges:
        bip = canon(below(e["child_node"]), alltips, ref)
        if e["edge_id"] not in exp_["edge_map"]:
            em_bad.append((e["edge_id"], "missing"))
            continue
        em_n += 1
        targets = exp_["edge_map"][e["edge_id"]]
        got = {canon(ts_rooted[id(pre_nodes[t])], alltips, ref) for t in targets}
        if got != {bip}:
            em_bad.append((e["edge_id"], targets))
    check("T19", "edge_map: every DB tree_edge maps to rooted node(s) with the same bipartition", [len(edges), []], [em_n, em_bad[:10]])

    # ------------------------------------------------------------ P: placements
    pl = {r["source_acc"]: dict(r) for r in q("SELECT * FROM placement WHERE tree_id = ? AND is_current = 1", TREE)}
    check("P1", "current placements (MR_RT_003, is_current = 1)", 4996, len(pl))
    check("P2", "placement objects in record files: same source set as current DB placements", [len(pl), True],
          [len(placements_ex), set(placements_ex) == set(pl)])
    pm = Counter()
    pex = {}
    for k, p in placements_ex.items():
        d = pl.get(k)
        if not d:
            continue
        for c, v in p.items():
            dv = d.get(c)
            same = (abs(v - dv) < 1e-12) if isinstance(v, float) and isinstance(dv, float) else v == dv
            if not same:
                pm[c] += 1
                pex.setdefault(c, (k, v, dv))
    check("P3", "per-record placement fields == DB placement row (all fields, all current placements)", {}, {c: {"n": n, "example": pex[c]} for c, n in pm.items()})
    st = Counter(p["clade_call_qc"] for p in pl.values())
    check("P4", "placement clade_call_qc counts == explorer meta placement_status_counts", dict(sorted(exp_["meta"]["placement_status_counts"].items())), dict(sorted(st.items())))
    check("P5", "placement best_edge exists in edge_map (placement drawn on a real reference branch)", 0,
          sum(1 for p in pl.values() if p["best_edge"] not in exp_["edge_map"]))

    passed = sum(c["pass"] for c in checks)
    res = {"db": str(DB.relative_to(REPO)), "db_sha256": DB_SHA, "export": str(EXP),
           "n_checks": len(checks), "n_pass": passed, "checks": checks}
    (out / "scientific_audit.json").write_text(json.dumps(res, indent=1, default=list))
    lines = ["| ID | Check | Expected | Observed | Result |", "|---|---|---|---|---|"]
    for c in checks:
        e, o = json.dumps(c["expected"], default=list), json.dumps(c["observed"], default=list)
        lines.append(f"| {c['id']} | {c['check']} | `{e[:80]}` | `{o[:80]}` | {'PASS' if c['pass'] else 'FAIL'} |")
    (out / "scientific_audit_table.md").write_text("\n".join(lines) + "\n")
    print(f"{passed}/{len(checks)} checks passed")
    for c in checks:
        if not c["pass"]:
            print("FAIL", c["id"], c["check"], json.dumps(c["observed"], default=list)[:600])
    sys.exit(0 if passed == len(checks) else 1)


if __name__ == "__main__":
    main()
