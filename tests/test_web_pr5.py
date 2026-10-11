"""PR-5 / Gate G5 scientific regression tests for the Statistics, Evidence, Watchlist, Search and Downloads pages.

Run from the repository root:
    pytest -q tests/test_web_pr5.py

Every statistic the website charts is read from web/public/data/v1.6.0 (the files the browser loads) and
re-derived here from the read-only v1.6.0 SQLite, with independent hand-written queries for the frozen G5
targets. Nothing is recomputed by the website itself: these tests guard the exporter and the committed copy.
"""
import collections
import hashlib
import re
import json
import os
import sqlite3
from pathlib import Path

import pytest

REPO = Path(os.environ.get("MRDB_REPO", ".")).resolve()
DB = Path(os.environ.get("MRDB_DB", REPO / "releases/v1.6.0/db/microrhododb_v1.6.0.sqlite"))
DATA = REPO / "web/public/data/v1.6.0"
DB_SHA = "379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(name):
    return json.loads((DATA / name).read_text())


@pytest.fixture(scope="module")
def con():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def summary():
    return load("summary.json")


def one(con, sql, *a):
    return con.execute(sql, a).fetchone()[0]


def test_database_is_the_frozen_release():
    assert sha(DB) == DB_SHA


def test_frozen_g5_targets(con, summary):
    m = {x["id"]: x["value"] for x in summary["metrics"]}
    # independent queries, not the stored SQL
    assert one(con, "SELECT COUNT(*) FROM v_master") == m["records_total"] == 5466
    assert one(con, "SELECT COUNT(*) FROM v_master WHERE counts_eligible = 1") == m["records_counted"] == 5460
    assert one(con, "SELECT COUNT(*) FROM v_master WHERE is_engineered = 1") == m["records_engineered"] == 6
    assert one(con, "SELECT COUNT(DISTINCT mrdb_acc) FROM v_master") == m["mrdb_accessions"] == 5299
    assert one(con, "SELECT COUNT(*) FROM v_master WHERE evidence_level = 'E1' AND counts_eligible = 1") == m["e1_counted"] == 88
    assert one(con, "SELECT COUNT(*) FROM v_master WHERE evidence_level = 'E1'") == m["e1_total"] == 91
    assert one(con, "SELECT COUNT(*) FROM novel_family_candidate") == m["watchlist"] == 181
    assert m["members_candidates"] == 4468 and m["clade_confident_members_candidates"] == 3821
    assert m["typeI_members"] + m["typeI_candidates"] == m["members_candidates"]


@pytest.mark.parametrize("kind", ["metrics", "distributions", "crosstabs"])
def test_every_stored_sql_reproduces_the_exported_value(con, summary, kind):
    """The 'How this is counted' SQL shown on each chart reproduces the charted numbers exactly."""
    checked = 0
    for x in summary[kind]:
        sql = x.get("sql")
        if not sql:
            continue
        rows = con.execute(sql).fetchall()
        if kind == "metrics":
            assert rows[0][0] == x["value"], x["id"]
        elif kind == "distributions" and x.get("derivation") and len(rows[0]) == 1:
            # SQL returns the raw input; apply the stated derivation independently (NCBI phylum tag)
            assert x["id"] == "ncbi_phylum_counted"
            got = collections.Counter()
            for (lin,) in rows:
                m = re.findall(r"(?:^|, )([^,]+?) \(phylum\)", lin or "")
                assert len(m) <= 1
                got[m[0] if m else None] += 1
            exp = {i["key"]: i["value"] for i in x["items"]}
            assert dict(got) == exp and sum(got.values()) == x["total"] == 5460
        elif kind == "distributions":
            got = {str(r[0]) if r[0] is not None else None: r[-1] for r in rows}
            exp = {i["key"]: i["value"] for i in x["items"]}
            assert sum(got.values()) == sum(exp.values()) == x["total"], x["id"]
            assert sorted(got.values()) == sorted(exp.values()), x["id"]
        else:
            got = collections.Counter({(str(r[0]), str(r[1])): r[2] for r in rows})
            exp = collections.Counter({(c["row"], c["col"]): c["value"] for c in x["cells"]})
            assert sum(got.values()) == sum(exp.values()) == x["denominator"]["value"], x["id"]
            assert sorted(got.values()) == sorted(exp.values()), x["id"]
        checked += 1
    assert checked > 0


def test_distributions_sum_to_their_denominators(summary):
    dens = summary["denominators"]
    for d in summary["distributions"]:
        tot = sum(i["value"] for i in d["items"])
        assert tot == d["total"] == d["denominator"]["value"], d["id"]
        assert dens[d["denominator"]["id"]]["value"] == d["denominator"]["value"], d["id"]
    for x in summary["crosstabs"]:
        assert sum(c["value"] for c in x["cells"]) == x["denominator"]["value"] == 5460, x["id"]


def test_evidence_and_membership_are_separate_axes(con, summary):
    """Among counted records, members carry E1-E5 and non-members are E5 only. Evidence never upgrades
    membership: the two engineered constructs that are E1 remain typeI_candidate (not members)."""
    x = next(c for c in summary["crosstabs"] if c["id"] == "evidence_by_membership_group_counted")
    by_row = collections.defaultdict(dict)
    for c in x["cells"]:
        by_row[c["row"]][c["col"]] = c["value"]
    assert by_row["member"]["E1"] == 88
    for row, cols in by_row.items():
        if row != "member":
            assert set(cols) == {"E5"}, row
    assert one(con, """SELECT COUNT(*) FROM v_master v JOIN status_definition s ON s.status = v.membership_status
                       WHERE s.status_group <> 'member' AND v.evidence_level <> 'E5' AND v.counts_eligible = 1""") == 0
    eng = con.execute("""SELECT v.source_acc, v.membership_status FROM v_master v JOIN status_definition s
                         ON s.status = v.membership_status WHERE s.status_group <> 'member' AND v.evidence_level = 'E1'
                         ORDER BY 1""").fetchall()
    assert eng == [("A0ABF7PQ84", "typeI_candidate"), ("A0ABF7PQA2", "typeI_candidate")]
    assert one(con, "SELECT SUM(is_engineered) FROM v_master WHERE source_acc IN ('A0ABF7PQ84', 'A0ABF7PQA2')") == 2


def test_watchlist_is_isolated(con):
    w = load("watchlist.json")
    assert len(w["candidates"]) == 181
    forbidden = {"membership_status", "membership_score", "evidence_level", "mrdb_acc", "func_class", "clade_id"}
    for c in w["candidates"]:
        assert not (forbidden & set(c)), c["identifier"]
    corpus = {r[0] for r in con.execute("SELECT source_acc FROM v_master")}
    resolved = {c["resolved_accession"] for c in w["candidates"] if c.get("resolved_accession")}
    assert not (resolved & corpus), sorted(resolved & corpus)[:5]
    # watchlist entries never appear in the records index the corpus pages use
    idx = load("records-index.json")
    cols = idx["columns"] if isinstance(idx, dict) and "columns" in idx else None
    rows = idx["rows"] if cols else idx
    accs = {r[cols.index("source_acc")] if cols else r["source_acc"] for r in rows}
    assert len(accs) == 5466 and not (resolved & accs)


def test_downloads_checksums_match_files_on_disk():
    d = load("downloads.json")
    assert len(d["release_files"]) == 39
    not_in_git = [f["path"] for f in d["release_files"] if not f["in_git_at_tag"]]
    assert not_in_git == ["db/microrhododb_v1.6.0.sqlite"]
    for f in d["release_files"]:
        p = REPO / "releases/v1.6.0" / f["path"]
        assert p.is_file(), f["path"]
        assert sha(p) == f["sha256"], f["path"]
        assert p.stat().st_size == f["bytes"], f["path"]
    for f in d["refpkg_files"]:
        assert sha(REPO / "refpkg/MR_RT_003" / f["path"]) == f["sha256"], f["path"]
    for f in d["repository_documents"]:
        assert sha(REPO / f["path"]) == f["sha256"], f["path"]
    for f in d["website_derived"]:
        assert (DATA / f["path"]).exists(), f["path"]
    assert d["citation"].get("doi") in (None, "")


def test_sequence_search_golden_is_pinned_to_the_frozen_legacy_search():
    """The golden file was generated from the unmodified legacy site/app.js + site/data.js. Regenerating it
    (node web/scripts/legacy_seqsearch_golden.mjs --check, slow) is a manual validation step; the browser
    worker is compared case by case against this file in web/tests/unit/seqsearch.test.ts."""
    g = json.loads((REPO / "tests/data/web_seqsearch_golden_v160.json").read_text())
    assert g["site_app_js_sha256"] == sha(REPO / "site/app.js")
    assert g["site_data_js_sha256"] == sha(REPO / "site/data.js")
    assert len(g["cases"]) == 13
    top = next(c for c in g["cases"] if c["query_id"] == "P02945")["hits"][0]
    assert top["source_acc"] == "P02945" and top["identity"] == 1.0


def test_browser_never_claims_the_official_score():
    """Search/Methods/Help state that the browser search does not compute the membership score."""
    src = (REPO / "web/src/pages/SearchPage.tsx").read_text()
    assert "does not compute the official membership score" in src
    for p in (REPO / "web/src").rglob("*.tsx"):
        t = p.read_text().lower()
        # negated statements ("never computes", "does not compute") are allowed; affirmative claims are not
        assert not re.search(r"(?<!never )(?<!not )computes the official membership score", t), p
