#!/usr/bin/env python3
"""PR-4a adversarial acceptance audit of the PR-4 Phylogeny & Clade Explorer data and the PR-4a corrections.

Written independently of tools/export_web_data.py and of the pytest suites: its own Newick tokenizer,
bipartition code and SQL. Reads the frozen refpkg, the read-only v1.6.0 SQLite and an export directory.

    python web/scripts/pr4a_acceptance_audit.py --repo . --export web/public/data/v1.6.0 \
        [--baseline-export /path/to/pr4/export/v1.6.0] --out audit.json

Exit code 0 only if every check passes. Prints one line per check.
"""
import argparse
import collections
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append({"check": name, "pass": bool(ok), "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def tsv(p):
    lines = Path(p).read_text().splitlines()
    head = lines[0].split("\t")
    return [dict(zip(head, ln.split("\t"))) for ln in lines[1:] if ln]


# --------------------------------------------------------------------------------------------- Newick
TOK = re.compile(r"[(),;]|:[^(),;]*|[^(),:;]+")


def tree(text):
    """-> list of nodes in preorder; node = dict(name, length_str, kids, parent)."""
    nodes, stack, cur, last = [], [], None, None
    root = {"name": "", "len": None, "kids": [], "parent": None}
    nodes.append(root)
    cur = root
    for t in TOK.findall(text.strip()):
        if t == "(":
            n = {"name": "", "len": None, "kids": [], "parent": cur}
            cur["kids"].append(n); nodes.append(n); stack.append(cur); cur = n; last = n
        elif t == ",":
            parent = stack[-1]
            n = {"name": "", "len": None, "kids": [], "parent": parent}
            parent["kids"].append(n); nodes.append(n); cur = n; last = n
        elif t == ")":
            cur = stack.pop(); last = cur
        elif t == ";":
            break
        elif t.startswith(":"):
            last["len"] = t[1:]
        else:
            last["name"] = t
    return nodes


def tipsets(nodes):
    ts = {}
    for n in reversed(nodes):
        ts[id(n)] = frozenset([n["name"]]) if not n["kids"] else frozenset().union(*(ts[id(k)] for k in n["kids"]))
    return ts


def strip_internal_labels(text):
    # remove the label that follows a ')' (before ':' or ',' or ')' or ';')
    return re.sub(r"\)[^(),:;]+", ")", text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--export", default="web/public/data/v1.6.0")
    ap.add_argument("--baseline-export", default=None, help="PR-4 (ded4a84) export dir, for the drift check")
    ap.add_argument("--baseline-commit", default="7546a7a")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    R = Path(a.repo).resolve(); X = Path(a.export).resolve()
    RP = R / "refpkg/MR_RT_003"
    DB = R / "releases/v1.6.0/db/microrhododb_v1.6.0.sqlite"
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); con.row_factory = sqlite3.Row
    ex = json.loads((X / "phylogeny/explorer.json").read_text())
    cj = json.loads((X / "clades.json").read_text())
    groups = {c["clade_id"]: c for c in cj["level1"] + cj["subclades"]}

    # ---------------------------------------------------------------- 1. tips
    rooted_txt = (RP / "tree/MR_RT_003.rooted.treefile").read_text()
    rn = tree(rooted_txt); rts = tipsets(rn)
    leaves = [n["name"] for n in rn if not n["kids"]]
    roles = {r["source_acc"]: r["tip_role"] for r in tsv(RP / "tips.tsv")}
    check("1.1 rooted tree has 472 unique tips", len(leaves) == len(set(leaves)) == 472, f"{len(leaves)} leaves")
    check("1.2 tip set = tips.tsv = explorer.json tips", set(leaves) == set(roles) == set(ex["tips"]))
    og = sorted(t for t, r in roles.items() if r == "outgroup_heliorhodopsin")
    check("1.3 exactly 15 heliorhodopsin outgroup tips, all on one root child", len(og) == 15 and
          any(rts[id(k)] == frozenset(og) for k in rn[0]["kids"]), f"{len(og)} outgroup")
    check("1.4 explorer tip roles = tips.tsv", all(ex["tips"][t]["tip_role"] == roles[t] for t in roles))

    # ---------------------------------------------------------------- 2. topology and branch lengths
    order = [n["name"] if not n["kids"] else None for n in rn]
    ok_len = ok_top = True
    pre_of = {id(n): i for i, n in enumerate(rn)}
    nodes_by_pre = {n["pre"]: n for n in ex["nodes"]}
    for i, n in enumerate(rn):
        if n["kids"]:
            e = nodes_by_pre.get(i)
            if e is None or e["n_tips"] != len(rts[id(n)]):
                ok_top = False; continue
            if e["parent"] != (pre_of[id(n["parent"])] if n["parent"] else None):
                ok_top = False
            if i and (e["length"] is None or float(n["len"]) != e["length"]):
                ok_len = False
        else:
            t = ex["tips"][n["name"]]
            if t["pre"] != i or float(n["len"]) != t["length"]:
                ok_len = False
    check("2.1 explorer node table = rooted preorder topology (parents, tip counts)", ok_top and len(ex["nodes"]) == 471 and ex["n_nodes"] == 943)
    check("2.2 explorer branch lengths = frozen rooted file (exact float of the string)", ok_len)
    served = X / "phylogeny/MR_RT_003.rooted.treefile"
    check("2.3 served rooted Newick byte-identical to refpkg", served.read_bytes() == (RP / "tree/MR_RT_003.rooted.treefile").read_bytes())
    der = (X / "phylogeny/MR_RT_003.rooted.run1-support.DERIVED.nwk").read_text()
    check("2.4 DERIVED Newick: identical to frozen file once internal labels are removed (topology, names, length strings)",
          strip_internal_labels(der.strip()) == strip_internal_labels(rooted_txt.strip()))

    # ---------------------------------------------------------------- 3. run1 support by bipartition
    run1 = tree((RP / "tree/run1.treefile").read_text()); r1ts = tipsets(run1)
    U = frozenset(leaves); anchor = min(U)

    def bip(s):
        return s if anchor not in s else U - s
    lab = {}
    for n in run1[1:]:
        if n["kids"]:
            lab[bip(r1ts[id(n)])] = n["name"] or None
    bad = []; n_checked = 0; n_disagree = 0
    for i, n in enumerate(rn):
        if not n["kids"] or i == 0:
            continue
        b = bip(rts[id(n)]); e = nodes_by_pre[i]
        if b not in lab:
            bad.append((i, "bipartition missing in run1")); continue
        l1 = lab[b]; n_checked += 1
        if e["run1_label"] != l1:
            bad.append((i, e["run1_label"], l1)); continue
        if l1:
            sh, uf = (float(x) for x in l1.split("/"))
            if (e["sh_alrt"], e["ufboot"]) != (sh, uf):
                bad.append((i, "numbers"))
        if (n["name"] or None) != l1:
            n_disagree += 1
    check("3.1 every rooted non-root bipartition exists in run1 and carries the run1 label/numbers", not bad and n_checked == 470, f"{n_checked} nodes, {len(bad)} bad")
    check("3.2 frozen rooted-file labels disagree with run1 on 17 nodes (regression of the known shift)", n_disagree == 17, f"{n_disagree}")
    root = nodes_by_pre[0]
    disp = [k for k in rn[0]["kids"] if nodes_by_pre.get(pre_of[id(k)], {}).get("support_displayed")]
    check("3.3 root has no support; root split displayed on exactly one root child", root["sh_alrt"] is None and len(disp) == 1)

    # ---------------------------------------------------------------- 4. clades
    ct = tsv(RP / "clades/MR_CLD3_tips.tsv")
    l1sets = collections.defaultdict(set); subsets = collections.defaultdict(set)
    for r in ct:
        if r["clade_id"].startswith("MR_CLD3_"):
            l1sets[r["clade_id"]].add(r["source_acc"])
        if r.get("subclade_id"):
            subsets[r["subclade_id"]].add(r["source_acc"])
    bbs = sorted(k for k in subsets if "_B" in k); subs = sorted(k for k in subsets if "_B" not in k)
    lv1 = [c for c in cj["level1"] if c["kind"] == "clade"]; bbg = [c for c in cj["level1"] if c["kind"] == "backbone_group"]
    check("4.1 17 level-1 clades, 2 backbone groups, 30 subclades (refpkg = clades.json)",
          len(l1sets) == 17 and bbs == ["MR_CLD3_B01", "MR_CLD3_B02"] and len(subs) == 30 and
          sorted(c["clade_id"] for c in lv1) == sorted(l1sets) and sorted(c["clade_id"] for c in bbg) == bbs and
          sorted(c["clade_id"] for c in cj["subclades"]) == subs)
    setmap = {**l1sets, **subsets}
    mono_bad = []
    for cid, s in setmap.items():
        hits = [i for i, n in enumerate(rn) if n["kids"] and rts[id(n)] == frozenset(s)]
        if len(hits) != 1 or groups[cid]["mrca_node"] != hits[0]:
            mono_bad.append(cid)
    check("4.2 every group's frozen tip set is exactly one rooted clade and mrca_node points to it", not mono_bad, ",".join(mono_bad))
    fails = [c["clade_id"] for c in lv1 if not c["support_audit"]["iqtree_run1_meets_support_thresholds"]]
    a17 = groups["MR_CLD3_017"]["support_audit"]
    dbrow = con.execute("SELECT ufboot, sh_alrt FROM clade WHERE clade_id = 'MR_CLD3_017'").fetchone()
    m17 = nodes_by_pre[groups["MR_CLD3_017"]["mrca_node"]]
    check("4.3 MR_CLD3_017 flagged: run1 SH-aLRT 50.3 / UFBoot 72 at its MRCA; the only failing level-1 clade; DB 100/100 unchanged",
          fails == ["MR_CLD3_017"] and (a17["iqtree_run1_sh_alrt"], a17["iqtree_run1_ufboot"]) == (50.3, 72.0) and
          (m17["sh_alrt"], m17["ufboot"]) == (50.3, 72.0) and (dbrow["sh_alrt"], dbrow["ufboot"]) == (100.0, 100.0) and m17["n_tips"] == 100)
    sub_ok = all(nodes_by_pre[groups[s]["mrca_node"]]["sh_alrt"] >= 80 and nodes_by_pre[groups[s]["mrca_node"]]["ufboot"] >= 95 for s in subs)
    check("4.4 all 30 subclades meet SH-aLRT >= 80 and UFBoot >= 95 under run1 support", sub_ok)

    # ---------------------------------------------------------------- 5. placements vs formal assignments
    plc = [dict(r) for r in con.execute("SELECT * FROM placement WHERE is_current = 1 AND tree_id = 'MR_RT_003'")]
    vm = {r["source_acc"]: dict(r) for r in con.execute("SELECT source_acc, mrdb_acc, clade_id, subclade_id, clade_source FROM v_master")}
    check("5.1 placement_qc == (lwr_weighted_pendant <= 1.0) for all current placements",
          all((p["placement_qc"] == "ok") == (p["lwr_weighted_pendant"] <= 1.0) for p in plc), f"{len(plc)} placements")
    bad5 = []
    for cid, c in groups.items():
        sub = c["level"] == 2 or c.get("kind") == "backbone_group"
        k, call = ("subclade_id", "subclade_call") if sub else ("clade_id", "clade_call")
        gp = [p for p in plc if p[k] == cid]
        fk = "subclade_id" if c["level"] == 2 else "clade_id"
        formal = [v for v in vm.values() if v[fk] == cid]
        f_ok = sum(1 for p in gp if p[call] == "assigned" and p["placement_qc"] == "ok")
        f_lp = sum(1 for p in gp if p[call] == "assigned" and p["placement_qc"] == "long_pendant")
        ac = c["assignment_counts"]
        exp = (len(formal), sum(v["clade_source"] == "reference_tip" for v in formal), f_ok, f_lp)
        got = (ac["total"], ac["reference_tips"], ac["placements"], ac["placements_assigned_call_failing_qc"])
        if exp != got or sum(v["clade_source"] == "placement" for v in formal) != f_ok:
            bad5.append(f"{cid}:{exp}!={got}")
        # every formal placement record really is an assigned+ok placement into this group
        pm = {p["source_acc"]: p for p in gp}
        for v in formal:
            if v["clade_source"] == "placement":
                p = pm.get(v["source_acc"])
                if not p or p[call] != "assigned" or p["placement_qc"] != "ok":
                    bad5.append(f"{cid}:{v['source_acc']}")
    check("5.2 all 49 groups: formal = tips + placements(call assigned, QC ok); long-pendant placements never formal", not bad5 and len(groups) == 49, ";".join(bad5[:5]))
    bbp = [p for p in plc if p["subclade_id"] in ("MR_CLD3_B01", "MR_CLD3_B02")]
    bbf = [p for p in bbp if p["placement_qc"] == "ok"]
    only = groups["MR_CLD3_B02"]["placement_only_records"]
    check("5.3 backbone: 97 placements, 94 formal; B02 placement-only = A0A2P6MQ02, A0A2P6NAG6, A0A2P6NFX8 (no v_master clade)",
          len(bbp) == 97 and len(bbf) == 94 and [r["source_acc"] for r in only] == ["A0A2P6MQ02", "A0A2P6NAG6", "A0A2P6NFX8"] and
          all(not vm[r["source_acc"]]["clade_id"] for r in only) and groups["MR_CLD3_B01"]["assignment_counts"]["total"] == 97 and
          groups["MR_CLD3_B02"]["assignment_counts"]["total"] == 5)
    e9 = con.execute("SELECT source_acc, is_engineered, counts_eligible FROM v_master WHERE clade_id = 'MR_CLD3_009' AND evidence_level = 'E1'").fetchall()
    n_e1 = con.execute("SELECT n_E1 FROM clade WHERE clade_id = 'MR_CLD3_009'").fetchone()[0]
    check("5.4 MR_CLD3_009: 12 E1 source records, 11 counted (= clade.n_E1), excluded = engineered A0A8X6EH36",
          len(e9) == 12 and n_e1 == 11 == sum(r["counts_eligible"] for r in e9) and
          [(r["source_acc"], r["is_engineered"]) for r in e9 if not r["counts_eligible"]] == [("A0A8X6EH36", 1)])
    psc = collections.Counter(p["clade_call_qc"] for p in plc)
    check("5.5 explorer placement status counts = DB clade_call_qc counts", ex["meta"]["placement_status_counts"] == dict(psc) or
          ex["meta"]["placement_status_counts"].get("clade_call_qc") == dict(psc), json.dumps(dict(psc)))

    # ---------------------------------------------------------------- 6. downloads, provenance, navigation
    check("6.1 served run1.treefile byte-identical to refpkg", (X / "phylogeny/run1.treefile").read_bytes() == (RP / "tree/run1.treefile").read_bytes())
    m = ex["meta"]
    check("6.2 provenance SHA-256s in explorer.json match the files", m["frozen_treefile"]["sha256"] == sha(RP / "tree/MR_RT_003.rooted.treefile") and
          m["support_source"]["sha256"] == sha(RP / "tree/run1.treefile") and m["derived_newick"]["sha256"] == sha(X / "phylogeny/MR_RT_003.rooted.run1-support.DERIVED.nwk"))
    readme = (X / "phylogeny/MR_RT_003.rooted.run1-support.DERIVED.README.txt").read_text()
    check("6.3 DERIVED README names both source SHA-256s and its own", all(h in readme for h in (m["frozen_treefile"]["sha256"], m["support_source"]["sha256"], m["derived_newick"]["sha256"])))
    em = json.loads((X / "export_manifest.json").read_text())
    mism = [f["path"] for f in em["files"] if sha(X.parent / f["path"]) != f["sha256"]]
    on_disk = ({str(p.relative_to(X.parent)) for p in X.parent.rglob("*") if p.is_file()}
               - {f"{X.name}/export_manifest.json"})  # current.json (data root) + the release directory
    check("6.4 export_manifest lists every exported file (no more, no less) with matching SHA-256", not mism and
          {f["path"] for f in em["files"]} == on_disk, f"{len(em['files'])} files listed, {len(on_disk)} on disk, {len(mism)} mismatches")
    nav_bad = []
    for t, info in ex["tips"].items():
        if info["in_corpus"]:
            p = X / f"records/{info['mrdb_acc']}.json"
            if not p.exists() or vm.get(t, {}).get("mrdb_acc") != info["mrdb_acc"]:
                nav_bad.append(t)
        elif t in vm:
            nav_bad.append(t)
    absent = sorted(t for t, i in ex["tips"].items() if not i["in_corpus"])
    check("6.5 every in-corpus tip (470, incl. the 15 outgroup) resolves to its record file; only QBQ84355, QBQ84358 are not in the corpus",
          not nav_bad and absent == ["QBQ84355", "QBQ84358"] and sum(i["in_corpus"] for i in ex["tips"].values()) == 470, f"{len(nav_bad)} bad")
    check("6.6 edge_map covers 941 DB edges; exactly one maps to two branches (root split)",
          len(ex["edge_map"]) == 941 and sum(len(v) == 2 for v in ex["edge_map"].values()) == 1)

    # ---------------------------------------------------------------- 7. no drift
    def git(*args):
        return subprocess.run(["git", "-C", str(R), *args], capture_output=True, text=True).stdout
    d = git("diff", a.baseline_commit, "--", "releases", "refpkg", "pipeline", "site") + git("status", "--porcelain", "--", "releases", "refpkg", "pipeline", "site")
    check(f"7.1 git diff {a.baseline_commit} -- releases refpkg pipeline site is empty (incl. uncommitted)", d.strip() == "")
    fz = R / "docs/website/baseline/frozen_sha256_fab9182.txt"
    rows = [ln.split(None, 1) for ln in fz.read_text().splitlines() if ln.strip()]
    fz_bad = [p for h, p in rows if sha(R / p.strip().lstrip("*")) != h]
    check("7.2 frozen baseline checksums (frozen_sha256_fab9182.txt)", not fz_bad, f"{len(rows)} files, {len(fz_bad)} bad")
    rows = [ln.split(None, 1) for ln in (RP / "SHA256SUMS").read_text().splitlines() if ln.strip()]
    rp_bad = [p for h, p in rows if sha(RP / p.strip().lstrip("*")) != h]
    check("7.3 refpkg/MR_RT_003/SHA256SUMS", not rp_bad, f"{len(rows)} files, {len(rp_bad)} bad")
    check("7.4 v1.6.0 SQLite SHA-256 unchanged", sha(DB) == "379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f")
    if a.baseline_export:
        B = Path(a.baseline_export).resolve()
        bf = {str(p.relative_to(B)) for p in B.rglob("*") if p.is_file()}
        xf = {str(p.relative_to(X)) for p in X.rglob("*") if p.is_file()}
        changed = sorted(f for f in bf & xf if (B / f).read_bytes() != (X / f).read_bytes())
        allowed = {"clades.json", "manifest.json", "export_manifest.json"}
        # files whose only change is the embedded schema version string
        ver_only = sorted(f for f in changed if f not in allowed and
                          (B / f).read_text().replace("1.2.0", "1.3.0") == (X / f).read_text())
        check("7.5 export vs PR-4 export: same file set; only clades.json, manifest.json, export_manifest.json differ "
              "beyond the schema-version string", bf == xf and set(changed) - set(ver_only) <= allowed,
              f"{len(xf)} files; changed: {','.join(changed)}; schema-version string only: {','.join(ver_only)}")
        # clades.json: every PR-4 field unchanged (new 1.3.0 fields only)
        bc = json.loads((B / "clades.json").read_text()); xc = json.loads((X / "clades.json").read_text())
        new = {"assignment_counts", "placement_only_records"}

        def strip(o, path=""):
            if isinstance(o, dict):
                return {k: strip(v, path + "/" + k) for k, v in o.items()
                        if k not in new and not (k in ("call_field", "by_call_and_qc") and path.endswith("placement_counts"))
                        and not (k == "is_engineered" and ("e1_anchors" in path or "representatives" in path))}
            if isinstance(o, list):
                return [strip(v, path) for v in o]
            return o
        check("7.6 clades.json: all PR-4 (1.2.0) fields and values unchanged; only additive 1.3.0 fields", strip(bc) == strip(xc))
        bm = json.loads((B / "manifest.json").read_text()); xm = json.loads((X / "manifest.json").read_text())
        diffk = sorted(k for k in set(bm) | set(xm) if bm.get(k) != xm.get(k))
        check("7.7 manifest.json differs only in schema_version, website_version, exporter commit/dirty flag",
              set(diffk) <= {"schema_version", "website_version", "exporter"} and bm["counts"] == xm["counts"], ",".join(diffk))
    n_fail = sum(not c["pass"] for c in CHECKS)
    print(f"\n{len(CHECKS) - n_fail}/{len(CHECKS)} checks passed")
    if a.out:
        Path(a.out).write_text(json.dumps({"checks": CHECKS, "n_pass": len(CHECKS) - n_fail, "n_fail": n_fail}, indent=1) + "\n")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
