"""PR-5a scientific regression tests (Python side).

Run from the repository root:
    pytest -q tests/test_web_pr5a.py

* D3: summary.json is reconciled against the frozen v1.6.1 SQLite with a keyed comparison
  (57 SQL-replayed items + 1 independently derived item), and adversarial mutations of the exported
  distributions, crosstabs and metrics -- swapped category counts, swapped crosstab cells, renamed
  null categories, duplicate keys, extra zero categories -- are each rejected.
* D1/D2/D4: the DB-derived drilldown accession sets (tests/data/web_drilldown_golden_v161.json) are
  regenerated from the frozen SQLite and must be identical; every set size equals the exported value.
  tests/unit/pr5a.test.ts requires the website's Browse filters to reproduce each set exactly.
"""
import copy
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

REPO = Path(os.environ.get("MRDB_REPO", ".")).resolve()
sys.path.insert(0, str(REPO / "web/scripts"))
import pr5a_drilldown_golden as G  # noqa: E402
import summary_reconcile as R  # noqa: E402

DB = REPO / "releases/v1.6.1/db/microrhododb_v1.6.1.sqlite"
DATA = REPO / "web/public/data/v1.6.1"
DB_SHA = "b8215cffa9d2fdab1e65b904f4bafbe9edf6578aed7b4fb028a890850e704c2d"
GOLDEN = REPO / "tests/data/web_drilldown_golden_v161.json"


@pytest.fixture(scope="module")
def con():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def summary():
    return json.loads((DATA / "summary.json").read_text())


def bad_ids(con, s):
    return {r["id"] for r in R.reconcile(con, s, REPO) if not r["ok"]}


def test_database_is_frozen():
    assert hashlib.sha256(DB.read_bytes()).hexdigest() == DB_SHA


# ---------------------------------------------------------------- D3 keyed reconciliation

def test_keyed_reconciliation_57_sql_plus_1_derived(con, summary):
    res = R.reconcile(con, summary, REPO)
    assert len(res) == 58
    assert R.counts(res) == (57, 1)
    assert [r["id"] for r in res if r["method"].startswith("derived")] == ["tip_role"]
    assert all(r["ok"] for r in res), [(r["id"], r["problems"]) for r in res if not r["ok"]]
    # 34 metrics + 21 SQL distributions + 2 crosstabs = 57
    kinds = [r["kind"] for r in res if r["method"] == "sql"]
    assert (kinds.count("metric"), kinds.count("distribution"), kinds.count("crosstab")) == (34, 21, 2)


def _dist(s, i):
    return next(d for d in s["distributions"] if d["id"] == i)


def test_mutation_swapped_category_counts_detected(con, summary):
    for did, a, b in [("evidence_level_counted", "E1", "E2"), ("membership_status", "typeI_member_core", "boundary_family"),
                      ("clade_state_members_candidates", "confident", "tentative"), ("tax_domain_counted", "Archaea", None)]:
        s = copy.deepcopy(summary)
        it = {i["key"]: i for i in _dist(s, did)["items"]}
        it[a]["value"], it[b]["value"] = it[b]["value"], it[a]["value"]
        assert sorted(i["value"] for i in _dist(s, did)["items"]) == sorted(i["value"] for i in _dist(summary, did)["items"])
        assert bad_ids(con, s) == {did}, did


def test_mutation_swapped_phylum_and_tip_role_counts_detected(con, summary):
    for did in ["ncbi_phylum_counted", "tip_role"]:
        s = copy.deepcopy(summary)
        items = sorted(_dist(s, did)["items"], key=lambda i: -i["value"])
        items[0]["value"], items[1]["value"] = items[1]["value"], items[0]["value"]
        assert bad_ids(con, s) == {did}, did


def test_mutation_swapped_crosstab_cells_detected(con, summary):
    for xid in ["evidence_by_membership_group_counted", "evidence_by_basis_category_counted"]:
        s = copy.deepcopy(summary)
        x = next(c for c in s["crosstabs"] if c["id"] == xid)
        cells = sorted(x["cells"], key=lambda c: -c["value"])
        cells[0]["value"], cells[1]["value"] = cells[1]["value"], cells[0]["value"]
        assert bad_ids(con, s) == {xid}, xid
        # swapping the labels of two cells (row/col) instead of the values
        s = copy.deepcopy(summary)
        x = next(c for c in s["crosstabs"] if c["id"] == xid)
        c0, c1 = sorted(x["cells"], key=lambda c: -c["value"])[:2]
        c0["col"], c1["col"] = c1["col"], c0["col"]
        c0["row"], c1["row"] = c1["row"], c0["row"]
        assert bad_ids(con, s) == {xid}, xid


def test_mutation_null_category_and_duplicates_detected(con, summary):
    s = copy.deepcopy(summary)
    next(i for i in _dist(s, "helixC_motif_counted")["items"] if i["key"] is None)["key"] = "None"
    assert bad_ids(con, s) == {"helixC_motif_counted"}
    s = copy.deepcopy(summary)
    d = _dist(s, "func_class_counted")
    d["items"].append({"key": d["items"][0]["key"], "value": 0})
    assert bad_ids(con, s) == {"func_class_counted"}
    s = copy.deepcopy(summary)
    _dist(s, "evidence_level_counted")["items"].append({"key": None, "value": 0})  # spurious missing category
    assert bad_ids(con, s) == {"evidence_level_counted"}
    s = copy.deepcopy(summary)
    _dist(s, "membership_group")["items"].append({"key": "invented", "value": 0})
    assert bad_ids(con, s) == {"membership_group"}
    s = copy.deepcopy(summary)
    x = next(c for c in s["crosstabs"] if c["id"] == "evidence_by_membership_group_counted")
    x["cells"].append(dict(x["cells"][0], value=0))
    assert bad_ids(con, s) == {"evidence_by_membership_group_counted"}


def test_duplicate_keys_in_replayed_rows_are_rejected():
    assert R.compare_keyed([("a", 1), ("a", 1)], [("a", 2)], 2)[0].startswith("replayed: duplicate key")
    assert R.compare_keyed([(None, 1)], [(None, 1)], 1) == []
    assert R.compare_keyed([(None, 1)], [("None", 1)], 1) != []
    assert R.compare_keyed([("a", 1)], [("a", 1), (None, 0)], 1) != []
    assert R.compare_keyed([("a", 1), (None, 0)], [("a", 1)], 1) != []
    assert R.compare_keyed([("a", 1), ("b", 2)], [("a", 2), ("b", 1)], 3) != []


def test_mutation_metric_value_detected(con, summary):
    s = copy.deepcopy(summary)
    next(m for m in s["metrics"] if m["id"] == "members_candidates")["value"] = 5466
    assert bad_ids(con, s) == {"members_candidates"}


def test_frozen_denominators_unchanged(summary):
    d = {k: v["value"] for k, v in summary["denominators"].items()}
    assert (d["all_records"], d["counted_records"], d["mrdb_accessions"], d["members_candidates"]) == (5466, 5460, 5299, 4465)


# ---------------------------------------------------------------- D1/D2/D4 drilldown accession sets

def test_drilldown_golden_regenerates_identically():
    assert GOLDEN.read_text() == json.dumps(G.build(), indent=1, ensure_ascii=False) + "\n"


def test_drilldown_golden_sizes_equal_exported_values(summary):
    g = json.loads(GOLDEN.read_text())
    assert g["db_sha256"] == DB_SHA
    dists = {d["id"]: {i["key"]: i["value"] for i in d["items"]} for d in summary["distributions"]}
    cells = {x["id"]: {(c["row"], c["col"]): c["value"] for c in x["cells"]} for x in summary["crosstabs"]}
    metrics = {m["id"]: m["value"] for m in summary["metrics"]}
    pops = {d["id"]: d["denominator"]["id"] for d in summary["distributions"]}
    n = 0
    for it in g["items"]:
        if it["kind"] == "distribution":
            assert it["n"] == dists[it["id"]][it["key"]], (it["id"], it["key"])
            assert it["population"] == pops[it["id"]]
        elif it["kind"] == "crosstab":
            assert it["n"] == cells[it["id"]][tuple(it["key"])]
        elif it["kind"] == "metric":
            assert it["n"] == metrics[it["id"]]
        n += 1
    assert n == len(g["items"]) > 400


def test_clade_state_members_candidates_population(con):
    g = json.loads(GOLDEN.read_text())
    mc = [i for i in g["items"] if i["id"] == "clade_state_members_candidates"]
    assert all(i["population"] == "members_candidates" for i in mc)
    assert sum(i["n"] for i in mc) == 4465
    assert next(i for i in mc if i["key"] == "confident")["n"] == 3821
    allr = {i["key"]: i for i in g["items"] if i["id"] == "clade_state"}
    # the all-records sets differ: the two charts must not share drilldown targets
    assert any(allr[i["key"]]["sha256"] != i["sha256"] for i in mc)


def test_mr_cld3_017_sets(con):
    g = {i["key"]: i for i in json.loads(GOLDEN.read_text())["items"] if i["kind"] == "search"}
    assert g["formal"]["n"] == 1646
    accs = sorted(r[0] for r in con.execute("SELECT source_acc FROM v_master WHERE clade_id = 'MR_CLD3_017'"))
    assert hashlib.sha256("\n".join(accs).encode()).hexdigest() == g["formal"]["sha256"]
    assert one_count(con, "SELECT COUNT(*) FROM v_master WHERE clade_id = 'MR_CLD3_017' AND is_engineered = 1") == 0
    assert g["formal_or_tentative"]["n"] == g["text_search_hits"]["n"] == 1646 + 597


def one_count(con, sql):
    return con.execute(sql).fetchone()[0]
