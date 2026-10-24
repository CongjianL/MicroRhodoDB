"""Release-gate tests for MicroRhodoDB v1.6.1 (correction release on top of the immutable v1.6.0).

Environment:
    MRDB_DB161     database under test (default releases/v1.6.1/db/microrhododb_v1.6.1.sqlite)
    MRDB_REPO      repository / archive root (default '.')
"""
import hashlib
import os
import sqlite3

import pandas as pd
import pytest

REPO = os.path.abspath(os.environ.get("MRDB_REPO", "."))
DB = os.environ.get("MRDB_DB161", os.path.join(REPO, "releases/v1.6.1/db/microrhododb_v1.6.1.sqlite"))
V160 = os.path.join(REPO, "releases/v1.6.0/db/microrhododb_v1.6.0.sqlite")
V160_SHA256 = "379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f"
VAL = os.path.join(REPO, "releases/v1.6.1/validation")


@pytest.fixture(scope="module")
def con():
    if not os.path.exists(DB):
        pytest.skip(f"v1.6.1 DB not present: {os.path.relpath(DB, REPO)} (not committed; see BINARIES.md)")
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    yield c
    c.close()


def q(con, sql, *a):
    return con.execute(sql, a).fetchall()


def meta(con, key):
    return q(con, "select value from release_metadata where release='1.6.1' and key=?", key)[0][0]


def test_integrity_and_identity(con):
    assert q(con, "PRAGMA integrity_check")[0][0] == "ok"
    assert q(con, "PRAGMA foreign_key_check") == []
    assert meta(con, "version") == "1.6.1" and meta(con, "schema_revision") == "v161.1"
    assert meta(con, "base_release").startswith("1.6.0")


def test_v160_untouched():
    if not os.path.exists(V160):
        pytest.skip("v1.6.0 DB not present")
    h = hashlib.sha256(open(V160, "rb").read()).hexdigest()
    assert h == V160_SHA256


def test_corpus_unchanged(con):
    assert q(con, "select count(*) from membership")[0][0] == 5466
    assert q(con, "select count(*) from v_counted")[0][0] == 5460


def test_identical_sequences_one_status_one_call(con):
    """R1-1: byte-identical non-engineered records share membership tier, status, function class and evidence level
    (E1 records may coexist with E2 twins of the same class)."""
    df = pd.read_sql("""select p.sequence_sha256 h, m.membership_status st, s.status_group tier, f.func_class fc,
                               f.evidence_level ev from protein p join membership m using(source_acc)
                        join status_definition s on s.status=m.membership_status
                        join function_evidence f using(source_acc)
                        where coalesce(f.is_engineered,0)=0 and p.sequence_sha256 is not null""", con)
    g = df.groupby("h")
    assert (g.tier.nunique() > 1).sum() == 0
    assert (g.st.nunique() > 1).sum() == 0
    assert (g.fc.nunique() > 1).sum() == 0
    lv = g.ev.agg(lambda s: frozenset(s))
    assert all(len(x) == 1 or x == frozenset({"E1", "E2"}) for x in lv)


def test_decisions_recorded(con):
    d = pd.read_sql("select * from curation_v161_decision", con)
    assert len(d) == 107 and d.source_acc.nunique() == 23
    assert set(d.rule) == {"M1", "M2", "F1", "F2", "F3", "F4", "F5"}
    assert (d.decided_by == "CongJian Li").all() and (d.decided_at == "2026-10-24").all()
    ch = q(con, "select count(*) from function_evidence where v161_change like 'identical_sequence_%'")[0][0]
    assert ch == 23


def test_expected_deltas(con):
    tiers = dict(q(con, """select s.status_group, count(*) from membership m join status_definition s
                           on s.status=m.membership_status group by 1"""))
    assert tiers == {"member": 3091, "candidate": 1374, "boundary": 509, "outgroup": 386, "rejected": 106}
    ev = dict(q(con, "select evidence_level, count(*) from v_counted group by 1"))
    assert ev == {"E1": 88, "E2": 111, "E3": 1143, "E4": 1045, "E5": 3073}
    assert q(con, "select count(*) from function_evidence where call_conflict=1")[0][0] == 480
    # HSP30 copies follow the curated decoys; CryoR1 / GtCCR2 twins follow the curated members
    st = dict(q(con, "select source_acc, membership_status from membership where source_acc in "
                     "('B3LU93','A0A6C1DPQ8','B3LGN3','A0ABY1EHF9','A0A0C3UE61')"))
    assert st == {"B3LU93": "decoy_or_rejected", "A0A6C1DPQ8": "decoy_or_rejected", "B3LGN3": "decoy_or_rejected",
                  "A0ABY1EHF9": "typeI_member_curated", "A0A0C3UE61": "typeI_member_curated"}
    e2 = dict(q(con, "select source_acc, e2_ref from function_evidence where source_acc in ('A0ABY1EHF9','A0A0C3UE61')"))
    assert e2 == {"A0ABY1EHF9": "A0A1I3DJQ0", "A0A0C3UE61": "L1K1K8"}


def test_candidate_policy(con):
    # candidates are never called (stated in release_metadata and the data dictionary)
    assert q(con, """select count(*) from v_counted v join status_definition s on s.status=v.membership_status
                     where s.status_group='candidate' and v.evidence_level<>'E5'""")[0][0] == 0
    assert "receive no function call" in meta(con, "candidate_function_policy")
    d = q(con, "select definition from data_dictionary where object_name='function_evidence' and column_name='evidence_level'")
    assert "E5 by policy" in d[0][0]
    assert "AI assistant" in meta(con, "curation_assistance")


def test_clade_names(con):
    prov = {r[0] for r in q(con, "select clade_id from clade where name_basis_type='provisional_motif_taxonomy'")}
    assert prov == {"MR_CLD3_002", "MR_CLD3_005", "MR_CLD3_008", "MR_CLD3_014", "MR_CLD3_015", "MR_CLD3_B02"}
    assert q(con, "select count(*) from clade where level=1 and name_basis_type is null")[0][0] == 0
    b = q(con, "select naming_basis from clade where clade_id='MR_CLD3_017'")[0][0]
    assert "re-tiered to E4" in b and "E1 LR (Q9HGT7)" in b


def test_curation_decider_view(con):
    rows = q(con, "select release, count(*), sum(decider is null or decider=''), sum(decided_on is null or decided_on='') "
                  "from v_curation_decision group by 1")
    assert dict((r[0], r[1]) for r in rows) == {"1.6.0": 622, "1.6.1": 107}
    assert all(r[2] == 0 and r[3] == 0 for r in rows)


def test_data_dictionary_complete(con):
    objs = {r[0] for r in q(con, "select name from sqlite_master where type in ('table','view') "
                                 "and name not like 'sqlite_%' and name<>'data_dictionary'")}
    dd = {r[0] for r in q(con, "select distinct object_name from data_dictionary")}
    assert objs <= dd
    assert {r[0] for r in q(con, "select distinct release from data_dictionary")} == {"1.6.1"}


def test_revision_analyses():
    hn = pd.read_csv(os.path.join(VAL, "hard_negative_specificity_v161.tsv"), sep="\t")
    h70 = hn[(hn.threshold == 0.7) & hn.negative_set.str.startswith("hard")].set_index("method")
    assert h70.loc["score_only", "false_positives"] == 25 and h70.loc["full_rule", "false_positives"] == 0
    nb = pd.read_csv(os.path.join(VAL, "nearest_e1_baseline_v161.tsv"), sep="\t")
    loco = nb[(nb.holdout == "LOCO") & (nb.method == "nearest_E1_any")].iloc[0]
    assert loco.n_called == 76 and loco.n_correct == 36
    e3 = pd.read_csv(os.path.join(VAL, "e3_replicate_robustness_v161.tsv"), sep="\t")
    assert e3.n_E3_calls.sum() == 1143 and e3.retained_all_runs.all()
