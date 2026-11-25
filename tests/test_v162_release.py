"""Release-gate tests for MicroRhodoDB v1.6.2 (construction-review release on top of the immutable v1.6.1).

Environment:
    MRDB_DB162     database under test (default releases/v1.6.2/db/microrhododb_v1.6.2.sqlite)
    MRDB_REPO      repository / archive root (default '.')
"""
import hashlib
import os
import sqlite3
import sys

import pandas as pd
import pytest

REPO = os.path.abspath(os.environ.get("MRDB_REPO", "."))
DB = os.environ.get("MRDB_DB162", os.path.join(REPO, "releases/v1.6.2/db/microrhododb_v1.6.2.sqlite"))
V161 = os.path.join(REPO, "releases/v1.6.1/db/microrhododb_v1.6.1.sqlite")
V161_SHA256 = "b8215cffa9d2fdab1e65b904f4bafbe9edf6578aed7b4fb028a890850e704c2d"
FLAG = "typeI_status_in_heliorhodopsin_outgroup"
sys.path.insert(0, os.path.join(REPO, "tools"))
import helixc_motif as hm  # noqa: E402


@pytest.fixture(scope="module")
def con():
    if not os.path.exists(DB):
        pytest.skip(f"v1.6.2 DB not present: {os.path.relpath(DB, REPO)} (not committed; see BINARIES.md)")
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def base():
    if not os.path.exists(V161):
        pytest.skip("v1.6.1 DB not present")
    c = sqlite3.connect(f"file:{V161}?mode=ro", uri=True)
    yield c
    c.close()


def q(con, sql, *a):
    return con.execute(sql, a).fetchall()


def meta(con, key):
    return q(con, "select value from release_metadata where release='1.6.2' and key=?", key)[0][0]


def test_integrity_and_identity(con):
    assert q(con, "PRAGMA integrity_check")[0][0] == "ok"
    assert q(con, "PRAGMA foreign_key_check") == []
    assert meta(con, "version") == "1.6.2" and meta(con, "schema_revision") == "v162.1"
    assert meta(con, "base_release").startswith("1.6.1")


def test_v161_untouched():
    if not os.path.exists(V161):
        pytest.skip("v1.6.1 DB not present")
    assert hashlib.sha256(open(V161, "rb").read()).hexdigest() == V161_SHA256


def test_decisions_signed(con):
    d = pd.read_sql("select * from curation_v162_decision", con)
    assert len(d) == 270 and d.source_acc.nunique() == 157
    assert set(d.rule) == {"MOTIF1", "PLACE1", "E2M1"}
    assert (d.decided_at == "2026-11-25").all()
    assert (d.decided_by == "CongJian Li").all()


def test_only_decided_cells_changed(con, base):
    d = pd.read_sql("select * from curation_v162_decision", con)
    for table in ("function_evidence", "record_clade"):
        new = pd.read_sql(f"select * from {table} order by source_acc", con).set_index("source_acc")
        old = pd.read_sql(f"select * from {table} order by source_acc", base).set_index("source_acc")
        assert list(new.index) == list(old.index)
        cols = [c for c in old.columns]
        decided = {(r.source_acc, r.field) for r in d[d.table_name == table].itertuples()}
        for c in cols:
            a, b = old[c].astype(object).where(old[c].notna(), None), new[c].astype(object).where(new[c].notna(), None)
            changed = {acc for acc in old.index if a[acc] != b[acc]}
            assert changed == {acc for acc, f in decided if f == c}, (table, c)
        for r in d[d.table_name == table].itertuples():
            v = new.at[r.source_acc, r.field]
            assert ("" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)) in (r.new_value, r.new_value + ".0")


def test_every_record_has_a_motif_and_a_consistent_class(con):
    rows = q(con, "select helixC_motif, motif_class from function_evidence")
    assert all(m is not None for m, _ in rows)
    assert all((hm.motif_class(m) or "") == (c or "") for m, c in rows)
    assert meta(con, "n_missing_helixc_motif") == "0"


def test_identical_sequences_share_motif_and_flag(con):
    df = pd.read_sql("""select p.sequence_sha256 h, f.helixC_motif m, coalesce(rc.placement_qc_flag, '') fl
                        from protein p join function_evidence f using(source_acc)
                        left join record_clade rc using(source_acc) where p.sequence_sha256 is not null""", con)
    assert (df.groupby("h").m.nunique() > 1).sum() == 0
    assert (df.groupby("h").fl.nunique() > 1).sum() == 0


def test_placement_flag(con):
    flagged = set(r[0] for r in q(con, "select source_acc from record_clade where placement_qc_flag is not null"))
    expected = set(r[0] for r in q(con, """select m.source_acc from membership m join record_clade rc using(source_acc)
                                           where m.membership_status like 'typeI_%'
                                           and rc.clade_call = 'outgroup_heliorhodopsin'"""))
    assert flagged == expected and len(flagged) == 51
    kinds = dict(q(con, "select placement_qc_flag, count(*) from record_clade where placement_qc_flag is not null group by 1"))
    assert kinds == {f"{FLAG}:mr_rt_003_sampling_gap": 26, f"{FLAG}:model_sensitive": 16,
                     f"{FLAG}:consistent_outgroup_placement": 9}
    assert q(con, "select count(*) from v_master where placement_qc_flag is not null")[0][0] == 51
    # the flag annotates; placement and clade calls are not changed
    assert q(con, "select count(*) from record_clade where clade_call='outgroup_heliorhodopsin'")[0][0] == 456


def test_e2_motif_policy(con):
    bad = q(con, """select q.source_acc from function_evidence q join function_evidence r on r.source_acc = q.e2_ref
                    where q.evidence_level = 'E2' and coalesce(q.is_engineered, 0) = 0
                    and q.helixC_motif is not r.helixC_motif""")
    assert bad == []
    r = q(con, "select evidence_level, func_class, e2_ref, override_rule, call_conflict from function_evidence "
               "where source_acc = 'A0AAE0MU22'")[0]
    assert r == ("E5", "unresolved", None, "e2_motif_mismatch_v162", 0)


def test_par_conflict_flag_only(con):
    r = q(con, "select evidence_level, func_class, helixC_motif, motif_class, call_conflict, call_conflict_detail "
               "from function_evidence where source_acc = 'A0ACE3JIR6'")[0]
    assert r == ("E1", "proton_pump", "DTG", "sensory_like", 1, "v14=proton_pump; motif=sensory_like; action=flag_only_E1")


def test_expected_counts(con, base):
    ev = dict(q(con, "select evidence_level, count(*) from v_counted group by 1"))
    assert ev == {"E1": 88, "E2": 110, "E3": 1143, "E4": 1045, "E5": 3074}
    assert q(con, "select count(*) from function_evidence where call_conflict=1")[0][0] == 480
    tiers = dict(q(con, """select s.status_group, count(*) from membership m join status_definition s
                           on s.status=m.membership_status group by 1"""))
    assert tiers == {"member": 3091, "candidate": 1374, "boundary": 509, "outgroup": 386, "rejected": 106}
    assert q(con, "select * from membership order by source_acc") == q(base, "select * from membership order by source_acc")


def test_curation_decider_view(con):
    rows = dict(q(con, "select release, count(*) from v_curation_decision group by 1"))
    assert rows == {"1.6.0": 622, "1.6.1": 107, "1.6.2": 270}


def test_data_dictionary_complete(con):
    objs = {r[0] for r in q(con, "select name from sqlite_master where type in ('table','view') "
                                 "and name not like 'sqlite_%' and name<>'data_dictionary'")}
    dd = {r[0] for r in q(con, "select distinct object_name from data_dictionary")}
    assert objs <= dd
    assert {r[0] for r in q(con, "select distinct release from data_dictionary")} == {"1.6.2"}
    for obj, col in (("record_clade", "placement_qc_flag"), ("v_master", "placement_qc_flag"),
                     ("function_evidence", "v162_change")):
        assert q(con, "select count(*) from data_dictionary where object_name=? and column_name=?", obj, col)[0][0] == 1


def test_python_api_defaults_to_v162(con, monkeypatch):
    sys.path.insert(0, os.path.join(REPO, "src"))
    import microrhododb as m
    monkeypatch.delenv("MRDB_DB", raising=False)
    if os.path.realpath(DB) != os.path.realpath(m.DEFAULT_DB_PATH):
        pytest.skip("MRDB_DB162 points away from the repository's v1.6.2 database")
    with m.MicroRhodoDB() as db:
        assert m.__version__ == "1.6.2" and m.SCHEMA_REVISION == "v162.1"
        assert db.version() == {"api": "1.6.2", "schema_revision": "v162.1", "database_release": "1.6.2"}
        md = dict(db.release_metadata().itertuples(index=False))
        assert md["version"] == "1.6.2"
        assert len(db.members()) == 3091 and len(db.candidates()) == 1374 and len(db.call_conflicts()) == 480
