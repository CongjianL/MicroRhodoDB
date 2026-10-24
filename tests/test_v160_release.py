"""Release-gate tests for MicroRhodoDB v1.6.0.

Run from the repository root (or the extracted release archive):
    pytest -q tests/test_v160_release.py
Environment:
    MRDB_DB        database under test (default releases/v1.6.0/db/microrhododb_v1.6.0.sqlite)
    MRDB_REPO      repository / archive root (default '.')
    MRDB_IN_SNAKEMAKE=1   set by the workflow's test_v160 rule; the nested Snakemake dry-run test is then skipped
                          with an explicit reason (it is run by the top-level invocation instead).
Tests that need external binaries (HMMER + DIAMOND for the CLI, snakemake for the dry run) fail - they do not
skip - when those binaries are missing, so a green run always means the check was actually performed.
Prior-release databases (v1.5.0, v1.4.0, ...) are not committed (see BINARIES.md); tests that compare against
them, and the Snakemake dry run whose root input is the v1.5.0 database, skip with a reason when they are absent.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

REPO = os.path.abspath(os.environ.get("MRDB_REPO", "."))
DB = os.environ.get("MRDB_DB", os.path.join(REPO, "releases/v1.6.0/db/microrhododb_v1.6.0.sqlite"))
V150 = os.path.join(REPO, "releases/v1.5.0/db/microrhododb_v1.5.0.sqlite")
LEVELS = ["E1", "E2", "E3", "E4", "E5"]


@pytest.fixture(scope="module")
def con():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    yield c
    c.close()


@pytest.fixture(scope="module")
def con150():
    if not os.path.exists(V150):
        pytest.skip(f"v1.5.0 base DB not present: {os.path.relpath(V150, REPO)} (not committed; see BINARIES.md)")
    c = sqlite3.connect(f"file:{V150}?mode=ro", uri=True)
    yield c
    c.close()


def q(con, sql, *a):
    return con.execute(sql, a).fetchall()


def meta(con, key):
    return q(con, "select value from release_metadata where release='1.6.0' and key=?", key)[0][0]


# ---------------------------------------------------------------- integrity / schema
def test_integrity(con):
    assert q(con, "PRAGMA integrity_check")[0][0] == "ok"
    assert q(con, "PRAGMA foreign_key_check") == []


def test_release_identity(con):
    assert meta(con, "version") == "1.6.0"
    assert q(con, "select count(*) from protein")[0][0] == 5466


def test_alias_and_compat_views_removed(con):
    sql = " ".join(r[0] or "" for r in q(con, "select sql from sqlite_master"))
    assert "alias_v14" not in sql
    views = {r[0] for r in q(con, "select name from sqlite_master where type='view'")}
    assert not views & {"v_typeI_core", "v_typeI_candidates", "v_typeI_active", "v_rejected_or_decoy"}
    assert {"v_master", "v_counted", "v_call_conflict", "v_engineered"} <= views


def test_data_dictionary_covers_every_column(con):
    dd = {(o, c) for o, c, d in q(con, "select object_name, column_name, definition from data_dictionary")
          if d and d.strip()}
    objs = [r[0] for r in q(con, "select name from sqlite_master where type in ('table','view') "
                                 "and name not like 'sqlite_%'")]
    missing = [(o, c) for o in objs for c in [r[1] for r in q(con, f'PRAGMA table_info("{o}")')] if (o, c) not in dd]
    assert missing == [], f"{len(missing)} columns without a definition: {missing[:10]}"
    extra = {(o, c) for o, c in dd} - {(o, r[1]) for o in objs for r in q(con, f'PRAGMA table_info("{o}")')}
    assert extra == set(), f"dictionary rows for non-existent columns: {sorted(extra)[:10]}"


# ---------------------------------------------------------------- function evidence invariants
def test_one_level_per_record(con):
    assert q(con, "select count(*), count(distinct source_acc) from function_evidence")[0] == (5466, 5466)
    assert {r[0] for r in q(con, "select distinct evidence_level from function_evidence")} <= set(LEVELS)


def test_no_conflicting_E3_E4_remains(con):
    n = q(con, "select count(*) from function_evidence where evidence_level in ('E3','E4') "
               "and call_conflict=1 and override_rule is null")[0][0]
    assert n == 0


def test_conflict_downgrades(con):
    n = q(con, "select count(*) from function_evidence where evidence_level='E5' and func_class='unassigned' "
               "and basis like 'conflict:%'")[0][0]
    assert n == int(meta(con, "n_conflict_downgrades")) == 439
    # every downgraded record keeps both lines of evidence
    assert q(con, "select count(*) from function_evidence where basis like 'conflict:%' "
                  "and (func_class_v14 is null or motif_class is null)")[0][0] == 0


def test_flagged_conflicts_only_on_strong_evidence(con):
    rows = q(con, "select evidence_level, count(*) from function_evidence where call_conflict=1 "
                  "and basis not like 'conflict:%' group by 1")
    lv = dict(rows)
    assert set(lv) <= {"E1", "E2", "E4"}
    if "E4" in lv:  # only curator-signed rule overrides may stay E4 with a conflict
        assert q(con, "select count(*) from function_evidence where call_conflict=1 and evidence_level='E4' "
                      "and override_rule is null")[0][0] == 0
    assert sum(lv.values()) + 439 == int(meta(con, "n_call_conflict"))


def test_basis_renamed(con):
    assert q(con, "select count(*) from function_evidence where basis like 'motif_only:%'")[0][0] == 0


def test_e1_support(con):
    # every E1 record has an active support link (R2: A0A0P6XBM7 withdrawn from E1, A0ACE3JIR6 linked to PaR,
    # PMID 26260121; the two ADD-D deferrals of the first v1.6.0 cycle are therefore resolved)
    no_link = {r[0] for r in q(con, """select f.source_acc from function_evidence f where f.evidence_level='E1'
        and not exists (select 1 from assertion_publication a where a.source_acc=f.source_acc and a.is_active=1
                        and a.counts_as_support=1)""")}
    assert no_link == set()


def test_compilation_links_not_support(con):
    assert q(con, "select count(*) from assertion_publication where link_role='compilation' "
                  "and counts_as_support=1")[0][0] == 0
    assert q(con, "select count(*) from characterized_protein where pmid like '%0000%' "
                  "and (pmid like '%0000269%' or pmid like '%0000305%')")[0][0] == 0


# ---------------------------------------------------------------- engineered constructs / counts
def test_engineered_flags(con):
    eng = dict(q(con, "select source_acc, wild_type_acc from function_evidence where is_engineered=1"))
    assert eng == {"A0A6I8WFQ3": "A0A6P3CW41", "A0A7M4DUE4": "A0A6P3CW41", "A0A7M4DUE9": "A0A6P3CW41",
                   "A0A8X6EH36": "A0AAJ0LKB3", "A0ABF7PQ84": "A0ABF7PQ82", "A0ABF7PQA2": "A0ABF7PQ82"}


def test_engineered_excluded_from_counts(con):
    counted = dict(q(con, "select evidence_level, count(*) from v_counted group by 1"))
    assert counted == json.loads(meta(con, "evidence_level_counts_counted"))
    assert sum(counted.values()) == 5460 == int(meta(con, "n_counted_records"))
    assert q(con, "select count(*) from v_counted where is_engineered=1")[0][0] == 0
    fcd = q(con, "select sum(n_records), sum(n_records_incl_engineered) from func_class_definition")[0]
    assert fcd == (5460, 5466)


def test_engineered_excluded_from_transfer_and_benchmarks(con):
    assert q(con, "select count(*) from function_evidence f join function_evidence r on r.source_acc=f.e2_ref "
                  "where f.evidence_level='E2' and r.is_engineered=1")[0][0] == 0
    assert q(con, "select count(*) from loco_validation_record l join function_evidence f using (source_acc) "
                  "where f.is_engineered=1")[0][0] == 0
    assert q(con, "select count(*) from spectral_audit s join function_evidence f using (source_acc) "
                  "where f.is_engineered=1")[0][0] == 0


def test_e1_unique_sequences(con):
    n = q(con, """select count(distinct r.e1_representative) from redundancy r join function_evidence f
                  using (source_acc) where f.evidence_level='E1' and f.is_engineered=0""")[0][0]
    assert n == int(meta(con, "n_E1_unique_sequences")) == 76
    final = q(con, "select n from loco_validation where variant like 'FINAL%' and holdout='none' "
                   "and policy='legacy' and subset='all_E1'")
    assert final == [(76,)]


# ---------------------------------------------------------------- provenance / continuity with v1.5.0
def test_source_release_backfilled(con):
    vals = dict(q(con, "select source_release, count(*) from sequence_source group by 1"))
    assert vals == {"UniProtKB_2026_02": 5361, "UniProtKB_2026_03": 105}


CURATED = {"A0A1I3DJQ0": "40614199", "L1K1K8": "29078348", "A0A3G1I4H9": "39232582", "A0ABF7PQ82": "39181878"}


def test_membership_unchanged_except_curated_override(con, con150):
    a = dict(q(con, "select source_acc, membership_status from membership"))
    b = dict(q(con150, "select source_acc, membership_status from membership"))
    diff = {k for k in a if a[k] != b[k]}
    assert diff == set(CURATED)
    for acc, pmid in CURATED.items():
        st, reason = q(con, "select membership_status, status_reason from membership where source_acc=?", acc)[0]
        assert st == "typeI_member_curated" and b[acc].startswith("typeI_candidate")
        assert reason.startswith("curated_override") and pmid in reason
        lvl, eng = q(con, "select evidence_level, is_engineered from function_evidence where source_acc=?", acc)[0]
        assert lvl == "E1" and eng == 0
    # scores are not touched by the override
    sa = dict(q(con, "select source_acc, membership_score from membership"))
    sb = dict(q(con150, "select source_acc, membership_score from membership"))
    assert sa == sb
    assert int(meta(con, "n_typeI_member_curated")) == 4
    assert q(con, "select count(*) from v_typeI_member")[0][0] == 3089          # all records (v1.5.0: 3085)
    assert q(con, "select count(*) from v_typeI_member where is_engineered=0")[0][0] == 3085
    assert q(con, "select count(*) from v_typeI_candidate where is_engineered=0")[0][0] == 1377
    assert q(con, "select is_member from status_definition where status='typeI_member_curated'") == [(1,)]


def test_novel_layer_isolated(con):
    n = q(con, "select count(*) from novel_family_candidate")[0][0]
    assert n == int(meta(con, "n_novel_family_candidates")) == 181
    # watchlist rows are not corpus records and never enter counts
    assert q(con, """select count(*) from novel_family_candidate c join protein p
                     on p.source_acc = c.resolved_accession""")[0][0] == 0
    fam = dict(q(con, "select family, count(*) from novel_family_candidate group by family"))
    assert fam == {"viral_rhodopsin": 138, "structure_only": 23, "schizorhodopsin": 12, "bestrhodopsin": 5, "MerMAID": 3}


# ---------------------------------------------------------------- R2 referee follow-up
def test_foldseek_watchlist(con):
    assert q(con, "select count(*) from foldseek_hit")[0][0] == int(meta(con, "n_foldseek_hits")) == 786
    tiers = dict(q(con, "select watchlist_tier, count(*) from foldseek_hit group by 1"))
    assert tiers == {"pfam_detectable_sampling_gap": 605, "underrepresented_family": 155, "structure_only_no_PF01036": 26}
    assert q(con, "select sum(to_watchlist) from foldseek_hit")[0][0] == 181
    assert q(con, "select count(*) from foldseek_hit where to_watchlist=1 and watchlist_tier='pfam_detectable_sampling_gap'")[0][0] == 0
    assert q(con, "select count(*) from foldseek_query where query_id not like '%SKIPPED'")[0][0] == 10
    assert q(con, "select query_id from foldseek_query where query_id like '%SKIPPED'") == [("MerMAID_SKIPPED",)]
    # funnel survivors per query/db sum to the hit table before de-duplication across queries
    fn = pd.read_sql("select * from foldseek_funnel where query_id != 'COMBINED_unique'", con)
    capped = fn[fn.raw_hits == 1000]   # web-server cap: 9 of 10 queries are capped in both databases
    assert len(fn) == 20 and len(capped) == 18 and set(fn[fn.raw_hits < 1000].query_id) == {"BestR_A0AAE0C9L8"}
    assert q(con, "select f_length from foldseek_funnel where query_id='COMBINED_unique' and db='ALL'") == [(786,)]


def test_family_flag_table(con):
    flags = dict(q(con, "select novel_family_hit, count(*) from novel_family_flag where novel_family_hit is not null group by 1"))
    assert flags == {"xenorhodopsin": 125, "MerMAID": 9, "schizorhodopsin": 3, "bestrhodopsin": 2}
    assert q(con, "select count(*) from novel_family_flag")[0][0] == 5466 == int(meta(con, "n_novel_family_flag")) + 5327
    bad = q(con, """select count(*) from novel_family_flag where novel_family_hit is not null
                    and not (family_evalue <= 1e-10 and family_bits > coalesce(pf01036_bits, 0))""")[0][0]
    assert bad == 0
    # the flag is informational: flagged records keep their scored membership status
    assert q(con, "select novel_family_hit from novel_family_flag where source_acc='P02945'") == [(None,)]


def test_family_flag_cli(tmp_path, con):
    assert shutil.which("hmmsearch"), "hmmsearch not on PATH - activate the pinned environment"
    seqs = dict(q(con, "select source_acc, sequence from protein where source_acc in ('P02945','A0AAE0C9L8','A0AAP2RB57')"))
    faa = tmp_path / "q.faa"
    faa.write_text("".join(f">{k}\n{v}\n" for k, v in seqs.items()))
    out = tmp_path / "f.tsv"
    subprocess.run([sys.executable, os.path.join(REPO, "tools/family_flag.py"), str(faa),
                    "--release", os.path.join(REPO, "releases/v1.6.0"), "-o", str(out)], check=True, capture_output=True)
    got = pd.read_csv(out, sep="\t").set_index("query").novel_family_hit.to_dict()
    assert pd.isna(got["P02945"])
    assert got["A0AAE0C9L8"] == "bestrhodopsin" and got["A0AAP2RB57"] == "schizorhodopsin"


def test_clade_function_recomputed(con):
    # rule: >=2 non-engineered E1 records and >=80% agreement; subclade checked before clade
    cfc = pd.read_sql("select * from clade_function_consensus", con)
    ok = cfc[cfc.consensus_status == "consensus"]
    assert (ok.n_E1 >= 2).all() and (ok.top_frac >= 0.8).all() and ok.clade_function.notna().all()
    assert cfc[cfc.consensus_status != "consensus"].clade_function.isna().all()
    st = dict(zip(cfc.group_id, cfc.consensus_status))
    # v1.6.0 E1 set: clade MR_CLD3_017 drops to 3/4 = 75% (mixed), so subclade 017.01 (no E1 of its own) no longer
    # inherits proton_pump; MR_CLD3_009.01 is 2 anion / 1 proton
    assert st["MR_CLD3_017"] == "mixed" and st["MR_CLD3_017.01"] == "no_E1" and st["MR_CLD3_009.01"] == "mixed"
    assert q(con, "select count(*) from record_clade where clade_function is not null and "
                  "clade_function_source like 'MR_CLD3_017%'")[0][0] == 0
    rc = pd.read_sql("select source_acc, clade_function from record_clade", con)
    fe = pd.read_sql("select source_acc, clade_function from function_evidence", con)
    m = rc.merge(fe, on="source_acc", suffixes=("_rc", "_fe"))
    assert (m.clade_function_rc.fillna("") == m.clade_function_fe.fillna("")).all()


def test_r2_rules_and_e1_caveats(con):
    rules = dict(q(con, "select override_rule, count(*) from function_evidence where override_rule is not null group by 1"))
    assert rules["audit_rule_ASR_vs_XeR_ambiguous"] == 69 and rules["audit_rule_OpsA_like_nonpumping_lineage"] == 47
    assert rules["schizorhodopsin_family_conflict"] == 2
    bad = q(con, """select count(*) from function_evidence where override_rule in ('audit_rule_ASR_vs_XeR_ambiguous',
                    'audit_rule_OpsA_like_nonpumping_lineage','schizorhodopsin_family_conflict')
                    and not (evidence_level='E5' and func_class='unresolved')""")[0][0]
    assert bad == 0
    lv = dict(q(con, "select source_acc, evidence_level from function_evidence where source_acc in "
                     "('Q6R5N7','A0A0P6XBM7','A0ACE3JIR6','A0A0M5L0M3')"))
    assert lv["Q6R5N7"] != "E1" and lv["A0A0P6XBM7"] != "E1"
    assert lv["A0ACE3JIR6"] == "E1" and lv["A0A0M5L0M3"] == "E1"
    assert q(con, """select count(*) from assertion_publication a join publication p using (publication_id)
                     where a.source_acc='A0ACE3JIR6' and p.pmid=26260121 and a.is_active=1 and a.counts_as_support=1""")[0][0] == 1
    assert q(con, """select count(*) from assertion_publication where source_acc='Q6R5N7' and is_active=1
                     and counts_as_support=1""")[0][0] == 0
    assert q(con, "select count(*) from curation_v160_decision where row_type='r2_referee_followup' "
                  "and user_decision='APPROVE'")[0][0] == 25


def test_blind_audit_tables(con):
    au = pd.read_sql("select * from audit_blind", con)
    assert len(au) == 120 and au.audit_id.is_unique and (au.tier.value_counts() == 40).all()
    ag = pd.read_sql("select * from audit_agreement where metric='primary_exact'", con).set_index("tier")
    assert {t: (int(ag.loc[t, "n_match"]), int(ag.loc[t, "n"])) for t in ag.index} == \
        {"E2": (39, 40), "E3": (39, 40), "E4": (22, 40), "E2-E4": (100, 120)}
    assert int(au.exact_match.sum()) == 100
    # Wilson 95% interval recomputed
    z = 1.959963984540054
    for t, r in ag.iterrows():
        k, n = r.n_match, r.n; p = k / n
        c = (p + z * z / (2 * n)) / (1 + z * z / n); h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
        assert abs(r.wilson_lo - (c - h)) < 1e-6 and abs(r.wilson_hi - (c + h)) < 1e-6
    # every high-confidence blind call agreed with the DB call at audit draw
    assert au[au.confidence == "high"].exact_match.astype(int).all()


def test_v150_ladder_recorded(con, con150):
    new = pd.read_sql("select source_acc, evidence_level_v150, func_class_v150, basis_v150 from function_evidence", con)
    old = pd.read_sql("select source_acc, evidence_level, func_class, basis from function_evidence", con150)
    m = new.merge(old, on="source_acc")
    assert len(m) == 5466
    assert (m.evidence_level_v150 == m.evidence_level).all()
    assert (m.func_class_v150 == m.func_class).all()
    assert (m.basis_v150.fillna("") == m.basis.fillna("")).all()


def test_prior_release_metadata_untouched(con, con150):
    for rel in ("1.5.0", "1.4.0"):
        a = sorted(q(con, "select key, value from release_metadata where release=?", rel))
        b = sorted(q(con150, "select key, value from release_metadata where release=?", rel))
        assert a == b and len(a) > 0, rel


@pytest.mark.parametrize("rel", ["v1.5.0", "v1.4.0"])
def test_prior_release_files_untouched(rel):
    p = os.path.join(REPO, "releases", rel)
    sums = os.path.join(p, "SHA256SUMS")
    if not os.path.exists(sums):
        pytest.skip(f"releases/{rel} is not part of this checkout; the v1.6.0 archive ships it, "
                    f"so this skip only occurs in partial checkouts")
    missing_db = []
    for line in open(sums):
        h, fn = line.split()
        fn = fn.lstrip("*")
        if fn.endswith(".sqlite") and not os.path.exists(os.path.join(p, fn)):
            missing_db.append(fn)  # databases are not committed; every other listed file is still checked
            continue
        assert hashlib.sha256(open(os.path.join(p, fn), "rb").read()).hexdigest() == h, f"{rel}/{fn}"
    if missing_db:
        pytest.skip(f"other {rel} files verified; not present (see BINARIES.md): {', '.join(missing_db)}")


# ---------------------------------------------------------------- exports / CLI / workflow
def test_exports_mark_tentative_clades(con, tmp_path):
    subprocess.run([sys.executable, os.path.join(REPO, "tools/export_tables_v160.py"), DB, str(tmp_path)], check=True)
    rec = pd.read_csv(tmp_path / "records_v160.tsv", sep="\t", dtype=str)
    n_tent = q(con, "select count(*) from v_master where coalesce(clade_id,'')='' and tentative_clade_id is not null")[0][0]
    assert (rec.clade_confidence == "tentative").sum() == n_tent > 0
    assert rec.loc[rec.clade_confidence == "tentative", "clade_display"].str.startswith("TENTATIVE:").all()
    fa = open(tmp_path / "sequences_v160.fasta").read()
    assert fa.count("clade=TENTATIVE:") == n_tent and fa.count(">") == 5466


def test_cli_smoke_12_queries(tmp_path):
    for b in ("hmmscan", "hmmsearch", "diamond"):
        assert shutil.which(b), f"{b} not on PATH - activate the pinned environment (workflow/envs/mrdb.lock.yml)"
    out = tmp_path / "hits.tsv"
    subprocess.run([sys.executable, os.path.join(REPO, "tools/mrdb_search.py"),
                    os.path.join(REPO, "tests/data/cli_queries_12.faa"), "-o", str(out),
                    "--workdir", str(tmp_path / "w")], check=True, cwd=tmp_path)
    got = pd.read_csv(out, sep="\t")
    exp = pd.read_csv(os.path.join(REPO, "tests/data/cli_expected_12.tsv"), sep="\t")
    m = exp.merge(got, on="query", suffixes=("_exp", ""))
    assert len(m) == 12
    assert (m.provisional_status_exp == m.provisional_status).all()
    assert (abs(m.membership_score_exp - m.membership_score) < 1e-3).all()
    assert {"nn_call_conflict", "nn_is_engineered", "nn_function_basis"} <= set(got.columns)
    assert ((got.membership_score >= 0.70) == (got.typeI_detected_070 == "yes")).all()


def _cli_records(*ids):
    recs = {r.split(None, 1)[0]: ">" + r for r in open(os.path.join(REPO, "tests/data/cli_queries_12.faa")).read().split(">")[1:]}
    return "".join(recs[i] for i in ids)


def test_cli_queries_without_seed_hit(tmp_path):
    # neither query hits a scorer seed with DIAMOND: the empty seed-homology table used to raise KeyError
    for b in ("hmmscan", "hmmsearch", "diamond"):
        assert shutil.which(b), f"{b} not on PATH - activate the pinned environment (workflow/envs/mrdb.lock.yml)"
    qf, out = tmp_path / "q.faa", tmp_path / "hits.tsv"
    qf.write_text(_cli_records("UOK93384.1", "UOK93385.1"))
    subprocess.run([sys.executable, os.path.join(REPO, "tools/mrdb_search.py"), str(qf), "-o", str(out),
                    "--workdir", str(tmp_path / "w")], check=True, cwd=tmp_path, capture_output=True)
    got = pd.read_csv(out, sep="\t")
    exp = pd.read_csv(os.path.join(REPO, "tests/data/cli_expected_12.tsv"), sep="\t")
    m = exp.merge(got, on="query", suffixes=("_exp", ""))
    assert len(m) == 2
    assert (m.provisional_status_exp == m.provisional_status).all()
    assert (abs(m.membership_score_exp - m.membership_score) < 1e-3).all()


def test_cli_rejects_duplicate_query_ids(tmp_path):
    qf = tmp_path / "q.faa"
    qf.write_text(_cli_records("UOK93384.1") + _cli_records("UOK93384.1"))
    r = subprocess.run([sys.executable, os.path.join(REPO, "tools/mrdb_search.py"), str(qf), "-o", str(tmp_path / "h.tsv"),
                        "--workdir", str(tmp_path / "w")], cwd=tmp_path, capture_output=True, text=True)
    assert r.returncode != 0 and "duplicate sequence IDs: UOK93384.1" in r.stderr
    assert not (tmp_path / "w").exists()


def test_cli_release_index_keyed_by_database(tmp_path):
    assert shutil.which("diamond"), "diamond not on PATH - activate the pinned environment (workflow/envs/mrdb.lock.yml)"
    sys.path.insert(0, os.path.join(REPO, "tools"))
    import mrdb_search
    seq = _cli_records("UOK93384.1").split("\n", 1)[1].replace("\n", "")
    dbs = []
    for name in ("a", "b"):
        p = tmp_path / f"{name}#1.sqlite"   # '#' would end the path of an unescaped SQLite URI
        c = sqlite3.connect(p)
        c.execute("create table protein (mrdb_acc text, source_acc text, sequence text)")
        c.execute("insert into protein values (?, ?, ?)", (f"MRDB_{name}", f"SRC_{name}", seq))
        c.commit(), c.close()
        dbs.append(p)
    wd = tmp_path / "w"
    da, db_ = (mrdb_search.release_index(str(p), str(wd), "diamond") for p in dbs)
    assert da != db_ and os.path.exists(da) and os.path.exists(db_)
    assert open(os.path.join(os.path.dirname(db_), "release.faa")).read().startswith(">SRC_b MRDB_b\n")
    assert mrdb_search.release_index(str(dbs[0]), str(wd), "diamond") == da   # reused, not rebuilt
    assert not [f for f in os.listdir(os.path.dirname(da)) if ".tmp" in f]


def test_compare_db_content_float_tolerance(tmp_path):
    # last-digit float differences (pandas' CSV parser differs between platforms) match; anything else does not
    def make(name, ev, org):
        c = sqlite3.connect(tmp_path / name)
        c.execute("create table t (acc text, ev real, org text, built_at text)")
        c.execute("insert into t values ('A', ?, ?, ?)", (ev, org, name))
        c.commit(), c.close()
        return str(tmp_path / name)
    ref = make("ref.sqlite", 6.3999999999999995e-31, "x")
    cases = {"ulp.sqlite": (6.399999999999999e-31, "x", 0, "float_tolerance"),
             "num.sqlite": (6.4e-30, "x", 1, "DIFFERENT"),
             "txt.sqlite": (6.3999999999999995e-31, "y", 1, "DIFFERENT"),
             "same.sqlite": (6.3999999999999995e-31, "x", 0, "identical")}
    for name, (ev, org, code, status) in cases.items():
        new, out = make(name, ev, org), tmp_path / f"{name}.tsv"
        r = subprocess.run([sys.executable, os.path.join(REPO, "pipeline/v160/compare_db_content.py"), ref, new, str(out)],
                           capture_output=True, text=True)
        rep = pd.read_csv(out, sep="\t").set_index("object")
        assert r.returncode == code and rep.at["t", "status"] == status, (name, r.stdout)


def test_python_api_read_only():
    sys.path.insert(0, os.path.join(REPO, "src"))
    import microrhododb as m
    with m.MicroRhodoDB(DB) as db:
        assert m.__version__ == "1.6.0" and db.version()["database_release"] == "1.6.0"
        assert len(db.master()) == 5466 and len(db.counted()) == 5460
        assert len(db.engineered()) == 6
        assert len(db.function_evidence(level="E1")) == 88  # engineered excluded by default
        assert "P02945" in set(db.get("MRDB000001")["source_acc"])
        assert len(db.novel_family_candidates()) == 181
        with pytest.raises(sqlite3.OperationalError):
            db.con.execute("CREATE TABLE _x(a)")


def test_python_api_missing_path_does_not_fall_back(tmp_path, monkeypatch):
    sys.path.insert(0, os.path.join(REPO, "src"))
    import microrhododb as m
    monkeypatch.delenv("MRDB_DB", raising=False)
    with pytest.raises(FileNotFoundError, match="db_path="):
        m.MicroRhodoDB(str(tmp_path / "typo.sqlite"))
    monkeypatch.setenv("MRDB_DB", str(tmp_path / "typo.sqlite"))
    with pytest.raises(FileNotFoundError, match="MRDB_DB="):
        m.MicroRhodoDB()


def test_python_api_path_with_uri_characters(tmp_path):
    sys.path.insert(0, os.path.join(REPO, "src"))
    import microrhododb as m
    d = tmp_path / "run #1?a%20b"
    d.mkdir()
    shutil.copy(DB, d / "db.sqlite")   # a copy, not a symlink: the API resolves symlinks to the target path
    with m.MicroRhodoDB(str(d / "db.sqlite")) as db:
        assert len(db.counted()) == 5460


def test_scorer_validation_summary(tmp_path):
    out = tmp_path / "sv.tsv"
    subprocess.run([sys.executable, os.path.join(REPO, "pipeline/v160/scorer_validation_v160.py"), DB,
                    os.path.join(REPO, "curation/v160/audit_v150"), str(out)], check=True, capture_output=True)
    new = pd.read_csv(out, sep="\t", dtype=str)
    shipped = pd.read_csv(os.path.join(REPO, "releases/v1.6.0/validation/scorer_validation_v160.tsv"), sep="\t", dtype=str)
    pd.testing.assert_frame_equal(new, shipped)
    v = new.set_index(["section", "set", "method", "threshold", "metric"])["value"]
    # the rule baseline equals the score on the external set; the score ranks better on the clade-root holdout
    assert v[("A_external_auprc", "all (21/345)", "full_gated", np.nan, "auprc")] == \
        v[("A_external_auprc", "all (21/345)", "B4b_ga_retK", np.nan, "auprc")] == "0.91"
    assert v[("B_clade_root_auprc", "reference_clade_root (46/215)", "full_gated", np.nan, "auprc")] == "0.987"
    assert v[("B_clade_root_auprc", "reference_clade_root (46/215)", "B4b_ga_retK", np.nan, "auprc")] == "0.814"


def test_audit_sample_redrawable(tmp_path):
    out = tmp_path / "s.tsv"
    # drawn from the frozen pre-R2 frame (the R2 corrections changed some levels after the draw)
    frame = os.path.join(REPO, "curation/v160/audit_frame_v160_pre_r2.tsv")
    subprocess.run([sys.executable, os.path.join(REPO, "tools/draw_audit_sample.py"), "--db", DB, "--seed", "160",
                    "--n", "40", "--tiers", "E2,E3,E4", "--out", str(out), "--frame", frame], check=True, capture_output=True)
    body = lambda f: [l for l in open(f) if not l.startswith("#")]
    assert body(out) == body(os.path.join(REPO, "curation/v160/audit_sample_v160_seed160.tsv"))
    assert len(body(out)) == 121


def test_v140_release_suite(tmp_path):
    """The historical v1.4.0 suite (18 checks) still passes under the pinned environment (pandas 3)."""
    db140 = os.path.join(REPO, "releases/v1.4.0/db/microrhododb_v1.4.0.sqlite")
    needed = [db140, os.path.join(REPO, "releases/v1.3.0/db/microrhododb_v1.3.0.sqlite"),
              os.path.join(REPO, "releases/v1.0/tables/membership_assignments.tsv")]
    missing = [os.path.relpath(p, REPO) for p in needed if not os.path.exists(p)]
    if missing:
        pytest.skip("v1.4.0 suite inputs not present (all are included in the v1.6.0 archive): " + ", ".join(missing))
    r = subprocess.run([sys.executable, os.path.join(REPO, "tests/release_v140.py"), REPO, db140,
                        str(tmp_path / "v140.json")], capture_output=True, text=True)
    assert r.returncode == 0 and "=== 18/18 PASS ===" in r.stdout, r.stdout[-2000:] + r.stderr[-2000:]


def test_snakemake_dry_run():
    if os.environ.get("MRDB_IN_SNAKEMAKE") == "1":
        pytest.skip("running inside the workflow's own test rule; the dry run is the enclosing invocation")
    if not os.path.exists(V150):
        pytest.skip(f"workflow root input not present: {os.path.relpath(V150, REPO)} (not committed; see BINARIES.md)")
    smk = shutil.which("snakemake")
    assert smk, "snakemake not on PATH - activate the pinned environment"
    r = subprocess.run([smk, "-n", "-s", "workflow/Snakefile", "--nolock", "-c", "1"], cwd=REPO,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
