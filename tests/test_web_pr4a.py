"""PR-4a regression tests: formal assignments vs EPA-ng placements, the MR_CLD3_009 E1 note, schema 1.3.0.

Run from the repository root:
    pytest -q tests/test_web_pr4a.py

Every expected value is recomputed from the read-only v1.6.0 SQLite (tables placement, record_clade, clade,
v_master) with the rule of pipeline/v150/record_clades.py restated here, independently of the exporter:
    formal assignment = reference tip of the group, or a current MR_RT_003 placement whose call
    (clade_call for level-1 clades, subclade_call for subclades and backbone groups) is 'assigned'
    AND placement_qc is 'ok' (LWR-weighted pendant <= 1.0).
"""
import collections
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(os.environ.get("MRDB_REPO", ".")).resolve()
DB = Path(os.environ.get("MRDB_DB", REPO / "releases/v1.6.0/db/microrhododb_v1.6.0.sqlite"))
REL = "v1.6.0"
PENDANT_MAX = 1.0
B02_PLACEMENT_ONLY = ["A0A2P6MQ02", "A0A2P6NAG6", "A0A2P6NFX8"]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    o = tmp_path_factory.mktemp("export_pr4a")
    before = sha(DB)
    r = subprocess.run([sys.executable, str(REPO / "tools/export_web_data.py"), "--repo", str(REPO), "--db", str(DB),
                        "--out", str(o)], capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, r.stderr
    assert sha(DB) == before
    return o / REL


@pytest.fixture(scope="module")
def clades(out):
    c = json.loads((out / "clades.json").read_text())
    return {x["clade_id"]: x for x in c["level1"] + c["subclades"]}


@pytest.fixture(scope="module")
def con():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


@pytest.fixture(scope="module")
def plc(con):
    return [dict(r) for r in con.execute("SELECT * FROM placement WHERE is_current = 1 AND tree_id = 'MR_RT_003'")]


@pytest.fixture(scope="module")
def groups(con):
    return {r["clade_id"]: dict(r) for r in con.execute("SELECT * FROM clade WHERE tree_id = 'MR_RT_003'")}


def is_backbone(g):
    return g["level"] == 1 and g["parent_clade_id"] == "backbone"


def recompute(con, plc, cid, g):
    """Independent formal/placement counts for one group."""
    sub = g["level"] == 2 or is_backbone(g)
    key, call = ("subclade_id", "subclade_call") if sub else ("clade_id", "clade_call")
    gp = [p for p in plc if p[key] == cid]
    by = collections.defaultdict(collections.Counter)
    for p in gp:
        by[p[call]][p["placement_qc"]] += 1
    rc_key = "subclade_id" if g["level"] == 2 else "clade_id"
    rc = collections.Counter(r["source"] for r in con.execute(f"SELECT source FROM record_clade WHERE {rc_key} = ?", (cid,)))
    vm = con.execute(f"SELECT COUNT(*) FROM v_master WHERE {rc_key} = ?", (cid,)).fetchone()[0]
    return gp, by, rc, vm


def test_schema_version_is_1_3_0(out):
    em = json.loads((out / "export_manifest.json").read_text())
    assert em["schema_version"] == "1.3.0"
    assert json.loads((out / "manifest.json").read_text())["schema_version"] == "1.3.0"


def test_placement_qc_rule_matches_pendant_threshold(plc):
    # placement_qc is a pure function of the LWR-weighted pendant (PENDANT_MAX = 1.0, placement_assign.py)
    assert {p["placement_qc"] for p in plc} == {"ok", "long_pendant"}
    for p in plc:
        assert (p["placement_qc"] == "ok") == (p["lwr_weighted_pendant"] <= PENDANT_MAX), p["source_acc"]


def test_every_group_formal_counts_reconcile_with_db(con, plc, groups, clades):
    assert len(groups) == 49 and set(groups) == set(clades)
    for cid, g in groups.items():
        c = clades[cid]
        gp, by, rc, vm = recompute(con, plc, cid, g)
        ac, pc = c["assignment_counts"], c["placement_counts"]
        # formal = record_clade rows = v_master rows; split by source
        assert ac["total"] == vm == sum(rc.values()), cid
        assert ac["reference_tips"] == rc.get("reference_tip", 0) == c["n_reference_tips_in_corpus"], cid
        assert ac["placements"] == rc.get("placement", 0) == by["assigned"]["ok"], cid
        assert ac["placements_assigned_call_failing_qc"] == by["assigned"]["long_pendant"], cid
        assert pc["by_call_and_qc"] == {k: dict(v) for k, v in by.items() if v}, cid
        assert pc["call_field"] == ("subclade_call" if g["level"] == 2 or is_backbone(g) else "clade_call"), cid
        if g["level"] == 2 or is_backbone(g):
            assert ac["total"] == g["n_records_assigned"], cid
        else:
            assert ac["total"] == c["n_records_confident"], cid
            assert ac["placements_assigned_call_failing_qc"] == c["n_records_tentative"], cid
        assert sum(sum(v.values()) for v in pc["by_call_and_qc"].values()) == len(gp), cid


def test_backbone_97_placements_vs_94_formal(con, plc, clades):
    bb = [p for p in plc if p["subclade_id"] in ("MR_CLD3_B01", "MR_CLD3_B02")]
    assert len(bb) == 97
    assert all(p["subclade_call"] == "assigned" and p["clade_call_qc"] == "unassigned" for p in bb)
    ok = [p for p in bb if p["placement_qc"] == "ok"]
    assert len(ok) == 94
    assert collections.Counter(p["subclade_id"] for p in ok) == {"MR_CLD3_B01": 93, "MR_CLD3_B02": 1}
    n_formal_plc = con.execute("SELECT COUNT(*) FROM record_clade WHERE source = 'placement' AND clade_id IN "
                               "('MR_CLD3_B01', 'MR_CLD3_B02')").fetchone()[0]
    assert n_formal_plc == 94
    b1, b2 = clades["MR_CLD3_B01"], clades["MR_CLD3_B02"]
    assert (b1["assignment_counts"]["reference_tips"], b1["assignment_counts"]["placements"], b1["assignment_counts"]["total"]) == (4, 93, 97)
    assert (b2["assignment_counts"]["reference_tips"], b2["assignment_counts"]["placements"], b2["assignment_counts"]["total"]) == (4, 1, 5)
    assert b1["placement_only_records"] == []


def test_b02_placement_only_records_are_preserved_without_assignment(con, plc, clades):
    b2 = clades["MR_CLD3_B02"]
    only = b2["placement_only_records"]
    assert [r["source_acc"] for r in only] == B02_PLACEMENT_ONLY
    pmap = {p["source_acc"]: p for p in plc}
    for r in only:
        p = pmap[r["source_acc"]]
        assert p["subclade_id"] == "MR_CLD3_B02" and p["subclade_call"] == "assigned"
        assert p["placement_qc"] == r["placement_qc"] == "long_pendant"
        assert p["lwr_weighted_pendant"] == r["lwr_weighted_pendant"] > PENDANT_MAX
        assert p["clade_call_qc"] == r["clade_call_qc"] == "unassigned"
        v = con.execute("SELECT mrdb_acc, clade_id, subclade_id, tentative_clade_id, counts_eligible FROM v_master "
                        "WHERE source_acc = ?", (r["source_acc"],)).fetchone()
        assert v["mrdb_acc"] == r["mrdb_acc"]
        assert not v["clade_id"] and not v["subclade_id"]  # no invented formal assignment (NULL / empty)
        assert r["clade_state"] == "unassigned"
    assert {r["mrdb_acc"] for r in only} == {"MRDB002347", "MRDB002348", "MRDB002350"}
    # the one formal B02 placement
    nrh4 = con.execute("SELECT clade_id FROM v_master WHERE source_acc = 'A0A2P6NRH4'").fetchone()
    assert nrh4["clade_id"] == "MR_CLD3_B02" and pmap["A0A2P6NRH4"]["placement_qc"] == "ok"
    # level-1 groups other than backbone groups never carry a placement-only list
    for cid, c in clades.items():
        if c.get("kind") != "backbone_group":
            assert c["placement_only_records"] is None, cid


def test_subclade_long_pendant_placements_are_not_formal(con, plc, clades):
    subs = {cid for cid, c in clades.items() if c["level"] == 2}
    assert len(subs) == 30
    lp = [p for p in plc if p["subclade_id"] in subs and p["subclade_call"] == "assigned" and p["placement_qc"] == "long_pendant"]
    assert len(lp) == 354
    # + the 3 B02 placement-only records = 357 long-pendant placements with an assigned subclade/backbone call
    bb = [p for p in plc if p["subclade_id"] in ("MR_CLD3_B01", "MR_CLD3_B02") and p["placement_qc"] == "long_pendant"]
    assert sorted(p["source_acc"] for p in bb) == B02_PLACEMENT_ONLY
    for p in lp[:50] + lp[-50:]:
        v = con.execute("SELECT subclade_id FROM v_master WHERE source_acc = ?", (p["source_acc"],)).fetchone()
        assert not v["subclade_id"], p["source_acc"]
    s = clades["MR_CLD3_017.02"]
    assert s["assignment_counts"]["total"] == 311
    assert s["placement_counts"]["by_call_and_qc"]["assigned"] == {"ok": 289, "long_pendant": 191}


def test_mr_cld3_009_e1_excluded_engineered(con, clades):
    c = clades["MR_CLD3_009"]
    rows = con.execute("SELECT source_acc, mrdb_acc, is_engineered, counts_eligible FROM v_master "
                       "WHERE clade_id = 'MR_CLD3_009' AND evidence_level = 'E1'").fetchall()
    assert len(rows) == len(c["e1_anchors"]) == 12
    eligible = [r for r in rows if r["counts_eligible"] == 1]
    assert len(eligible) == 11 == c["function_consensus"]["n_E1"]
    excl = [r for r in rows if r["counts_eligible"] != 1]
    assert [(r["source_acc"], r["mrdb_acc"], r["is_engineered"]) for r in excl] == [("A0A8X6EH36", "MRDB003178", 1)]
    a = {e["source_acc"]: e for e in c["e1_anchors"]}["A0A8X6EH36"]
    assert a["counts_eligible"] is False and a["is_engineered"] is True
    # every other level-1 group: anchors == counted E1
    for cid, x in clades.items():
        if x["level"] == 1 and cid != "MR_CLD3_009":
            assert len(x["e1_anchors"]) == x["function_consensus"]["n_E1"], cid
            assert all(e["is_engineered"] is False for e in x["e1_anchors"]), cid
