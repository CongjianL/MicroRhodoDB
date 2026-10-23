"""Release-gate tests for MicroRhodoDB v1.5.0.  Run: MRDB_DB=path/to/microrhododb_v1.5.0.sqlite pytest -q tests/

The v1.5.0 databases are not committed (see BINARIES.md); tests that need one skip when it is absent."""
import os, sqlite3, hashlib, json
import pytest

DB = os.environ.get("MRDB_DB", "releases/v1.5.0/db/microrhododb_v1.5.0.sqlite")
ENV = os.environ.get("MRDB_ENV_DB", DB.replace(".sqlite", "_env_pilot.sqlite"))
REPO = os.environ.get("MRDB_REPO", ".")
FREEZE = "da634bfd1432a1cb5e9d47b101f0257efdcfe71ec2d9f65a3f9cab946076ab35"
MEMBER_STATUSES = {"typeI_member_core", "typeI_member_architecture_supported", "typeI_candidate",
                   "typeI_candidate_architecture_supported", "typeI_candidate_unresolved", "boundary_family",
                   "heliorhodopsin", "decoy_or_rejected"}


def require_db(path):
    if not os.path.exists(path):
        pytest.skip(f"{path} not present in this checkout (not committed; see BINARIES.md)")


@pytest.fixture(scope="module")
def con():
    require_db(DB)
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    yield c
    c.close()


def q(con, sql):
    return con.execute(sql).fetchall()


def test_integrity(con):
    assert q(con, "PRAGMA integrity_check")[0][0] == "ok"
    assert q(con, "PRAGMA foreign_key_check") == []


def test_corpus_counts(con):
    assert q(con, "select count(*) from protein")[0][0] == 5466
    assert q(con, "select count(*) from sequence_source where source_database='MGnify'")[0][0] == 0
    assert q(con, "select count(distinct mrdb_acc) from protein")[0][0] == q(con, "select count(*) from mrdb_accession")[0][0]
    assert q(con, "select count(*) from protein where mrdb_acc is null")[0][0] == 0


def test_env_pilot_separate():
    require_db(ENV)
    e = sqlite3.connect(f"file:{ENV}?mode=ro", uri=True)
    assert e.execute("select count(*) from protein").fetchone()[0] == 1352
    e.close()


def test_one_status_per_record(con):
    assert q(con, "select count(*) from membership")[0][0] == 5466
    assert q(con, "select count(*) from (select source_acc from membership group by 1 having count(*)>1)")[0][0] == 0
    st = {r[0] for r in q(con, "select distinct membership_status from membership")}
    assert st <= MEMBER_STATUSES
    defined = {r[0] for r in q(con, "select status from status_definition")}
    assert st <= defined
    # status counts match status_definition
    for s, n in q(con, "select status, n_records_v150 from status_definition"):
        assert q(con, f"select count(*) from membership where membership_status='{s}'")[0][0] == n


def test_member_definition(con):
    # every member has K at match state 210 and score >= 0.86
    bad = q(con, "select count(*) from membership where membership_status like 'typeI_member%' "
                 "and (retinal_site_residue!='K' or membership_score<0.86)")[0][0]
    assert bad == 0
    # boundary records never have K
    assert q(con, "select count(*) from membership where membership_status='boundary_family' and retinal_site_residue='K'")[0][0] == 0


def test_one_evidence_level(con):
    assert q(con, "select count(*) from function_evidence")[0][0] == 5466
    lv = {r[0] for r in q(con, "select distinct evidence_level from function_evidence")}
    assert lv <= {"E1", "E2", "E3", "E4", "E5"}
    # non-members can only be E1 (characterized) or E5
    assert q(con, "select count(*) from function_evidence f join membership m using(source_acc) "
                  "where m.membership_status not like 'typeI_member%' and f.evidence_level in ('E2','E3','E4')")[0][0] == 0


def test_tree_and_clades(con):
    assert q(con, "select count(*) from tree_node where tree_id='MR_RT_003' and kind='tip'")[0][0] == 472
    assert q(con, "select count(*) from tree_edge where tree_id='MR_RT_003'")[0][0] == 941
    # every current placement edge exists in tree_edge
    assert q(con, "select count(*) from placement p left join tree_edge e on e.tree_id=p.tree_id and e.edge_id=p.best_edge "
                  "where p.tree_id='MR_RT_003' and e.edge_id is null")[0][0] == 0
    # every record clade exists in clade table
    assert q(con, "select count(*) from record_clade r left join clade c using(clade_id) "
                  "where r.clade_id!='' and c.clade_id is null")[0][0] == 0
    # one current placement per record
    assert q(con, "select count(*) from (select source_acc from placement where tree_id='MR_RT_003' and is_current=1 "
                  "group by 1 having count(*)>1)")[0][0] == 0


def test_external_freeze(con):
    shas = {r[0] for r in q(con, "select distinct freeze_sha256 from external_validation")}
    assert shas == {FREEZE}
    assert q(con, "select count(*) from external_validation")[0][0] == 366
    # positives are corpus-absent by sequence
    assert q(con, "select count(*) from external_validation x join protein p on p.sequence_sha256=x.sequence_sha256 "
                  "where x.is_positive=1")[0][0] == 0


def test_views(con):
    for v in ["v_master", "v_typeI_member", "v_typeI_candidate", "v_boundary_family", "v_heliorhodopsin",
              "v_typeI_core", "v_typeI_candidates", "v_typeI_active", "v_rejected_or_decoy"]:
        q(con, f"select * from {v} limit 1")
    assert q(con, "select count(*) from v_master")[0][0] == 5466
    assert q(con, "select count(*) from v_typeI_core")[0][0] == 2704 + 381


def test_ci_method(con):
    for t in ["external_validation_operating_point", "holdout_operating_point"]:
        cols = [r[1] for r in q(con, f"pragma table_info({t})")]
        if "ci_method" in cols:
            assert {r[0] for r in q(con, f"select distinct ci_method from {t}")} <= {"wilson"}


def test_v140_untouched():
    p = os.path.join(REPO, "releases/v1.4.0")
    sums = os.path.join(p, "SHA256SUMS")
    if not os.path.exists(sums):
        pytest.skip("no v1.4.0 SHA256SUMS")
    missing_db = []
    for line in open(sums):
        h, fn = line.split()
        fn = fn.lstrip("*")
        if fn.endswith(".sqlite") and not os.path.exists(os.path.join(p, fn)):
            missing_db.append(fn)  # databases are not committed; every other listed file is still checked
            continue
        assert hashlib.sha256(open(os.path.join(p, fn), "rb").read()).hexdigest() == h, fn
    if missing_db:
        pytest.skip(f"other files verified; not present (see BINARIES.md): {', '.join(missing_db)}")


# ---------------------------------------------------------------- v1.5.0 curator sign-off / curated rebuild
def test_spotcheck_signed_off(con):
    rows = q(con, "select decision, decided_by, decided_at from curator_spotcheck_decision")
    assert len(rows) == 65
    assert all(d and by and at for d, by, at in rows)
    assert {d for d, _, _ in rows} <= {"approve", "approve_with_correction", "drop_link", "replace_link", "downgrade_E1",
                                       "annotate_only", "annotate_conflict", "keep_unresolvable", "reject"}
    # every spot-checked link carries the curator decision; replacements are verified and active
    assert q(con, "select count(*) from assertion_publication where curator_decision=''")[0][0] == 0
    assert q(con, "select count(*) from assertion_publication a join publication p using(publication_id) "
                  "where p.ingestion_v150='curator_replacement_verified' and (a.is_active!=1 or a.verdict!='verified')")[0][0] == 0
    assert q(con, "select count(*) from publication where ingestion_v150='curator_replacement_verified'")[0][0] == 3


def test_no_E1_without_support(con):
    # E1 records that have publication links must have >=1 active link counted as support
    bad = q(con, "select f.source_acc from function_evidence f where f.evidence_level='E1' "
                 "and f.source_acc in (select source_acc from assertion_publication) "
                 "and f.source_acc not in (select source_acc from assertion_publication where is_active=1 and counts_as_support=1)")
    assert bad == []
    # E1 only for E1-eligible characterized records
    assert q(con, "select count(*) from function_evidence f left join characterized_protein c using(source_acc) "
                  "where f.evidence_level='E1' and (c.source_acc is null or c.e1_eligible not in (1,'True'))")[0][0] == 0
    # curator-downgraded records are not E1
    assert q(con, "select count(*) from function_evidence f join curator_spotcheck_decision d using(source_acc) "
                  "where d.decision='downgrade_E1' and f.evidence_level='E1'")[0][0] == 0


def test_D2RRQ8_not_E1(con):
    lv, = q(con, "select evidence_level from function_evidence where source_acc='D2RRQ8'")[0]
    assert lv != "E1"
    st, = q(con, "select membership_status from membership where source_acc='D2RRQ8'")[0]
    assert st == "boundary_family"
    lam, conflict = q(con, "select lambda_max_nm, conflict from characterized_protein where source_acc='D2RRQ8'")[0]
    assert lam == 547 and "accession_mapping_conflict" in conflict


def test_identical_sequences_consistent(con):
    trio = ("A0ABF7PQ03", "A0ABF7PQ05", "A0AC62AE26")
    r = q(con, f"select distinct p.sequence_sha256, f.func_class, f.evidence_level, c.exp_class from protein p "
               f"join function_evidence f using(source_acc) join characterized_protein c using(source_acc) "
               f"where p.source_acc in {trio}")
    assert r == [(r[0][0], "photoreceptor_unassigned", "E1", "photoreceptor_no_transport")]
    # generic: identical sequences with E1 on more than one record carry one experimental class
    assert q(con, "select count(*) from (select p.sequence_sha256 from protein p join function_evidence f using(source_acc) "
                  "where f.evidence_level='E1' group by 1 having count(distinct f.func_class)>1)")[0][0] == 0
    assert q(con, "select count(*) from function_evidence f left join func_class_definition d using(func_class) "
                  "where d.func_class is null")[0][0] == 0


def test_clade_cache_consistent(con):
    bad = q(con, "select c.clade_id from clade c where c.level=1 and c.n_records_assigned != "
                 "(select count(*) from record_clade r where r.clade_id=c.clade_id)")
    bad += q(con, "select c.clade_id from clade c where c.level=2 and c.n_records_assigned != "
                  "(select count(*) from record_clade r where r.subclade_id=c.clade_id)")
    assert bad == []


def test_tentative_clade_rules(con):
    # tentative only when the confident clade is blank and the primary placement is assigned but pendant-QC-failed
    assert q(con, "select count(*) from v_master where tentative_clade_id is not null and coalesce(clade_id,'')!=''")[0][0] == 0
    assert q(con, "select count(*) from v_master where tentative_clade_id='outgroup_heliorhodopsin'")[0][0] == 0
    assert q(con, "select count(*) from v_master v join placement p on p.source_acc=v.source_acc and p.tree_id='MR_RT_003' "
                  "and p.is_current=1 where v.tentative_clade_id is not null and (p.clade_call!='assigned' "
                  "or p.clade_call_qc!='distant_assigned' or p.clade_id!=v.tentative_clade_id)")[0][0] == 0
    # complete: every eligible record gets one
    assert q(con, "select count(*) from v_master v join placement p on p.source_acc=v.source_acc and p.tree_id='MR_RT_003' "
                  "and p.is_current=1 where coalesce(v.clade_id,'')='' and p.clade_call='assigned' and "
                  "p.clade_call_qc='distant_assigned' and coalesce(p.clade_id,'') not in ('','outgroup_heliorhodopsin') "
                  "and v.tentative_clade_id is null")[0][0] == 0
    # confident member coverage meets the >=90% acceptance criterion
    n, k = q(con, "select count(*), sum(coalesce(clade_id,'')!='') from v_master where membership_status like 'typeI_member%'")[0]
    assert k / n >= 0.90
