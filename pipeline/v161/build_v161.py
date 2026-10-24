#!/usr/bin/env python3
"""Build MicroRhodoDB v1.6.1 from the immutable v1.6.0 database.

v1.6.1 is a correction release answering the simulated NAR review of 2026-10-24. It does not change the corpus, the
scorer, its thresholds, the tree or the clade assignments.

  1  verify the v1.6.0 checksum and copy it (v1.6.0 is opened read-only and never modified)
  2  apply curation/v161/curation_v161_identical_signed.tsv: one decision per unique sequence (R1-1); every row is
     applied only if the current value equals the recorded old value
  3  function_evidence.v161_change (rules applied per record) and table curation_v161_decision
  4  clade.name_basis_type (characterised_member | provisional_motif_taxonomy) and the MR_CLD3_017 naming basis (R1-2, R1-3)
  5  view v_curation_decision: one decider/date per curation decision across v1.6.0 and v1.6.1 (R2-6)
  6  release_metadata rows for 1.6.1, incl. the candidate-call policy (R1-5) and the curation-assistance statement (E-3)
  7  data dictionary (100% coverage) from curation/v161 definitions; integrity and foreign-key checks

Usage: python pipeline/v161/build_v161.py --base <v1.6.0 db> --decisions <tsv> --tdefs <tsv> --cdefs <tsv>
                                          --out-db <db> --dict-tsv <tsv> --log <txt>
"""
import argparse
import hashlib
import os
import shutil
import sqlite3
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "v160"))
import data_dictionary_v160 as ddict  # noqa: E402

V160_SHA256 = "379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f"
RELEASE, RELEASE_DATE, SCHEMA = "1.6.1", "2026-10-24", "v161.1"
TABLE_KEY = {"membership": "source_acc", "function_evidence": "source_acc"}
CLADE_017_BASIS = ("E1 LR (Q9HGT7); named also after CarO (Q70LL3), whose E1 annotation was re-tiered to E4 by signed "
                   "override in v1.6.0; Ascomycota/Basidiomycota")
CURATION_ASSISTANCE = (
    "Curation recommendations (v1.6.0 sign-off sheets) and the blind re-annotation of the 120-record E2-E4 audit "
    "sample were drafted with an AI assistant; every decision was reviewed and signed by the curator (CongJian Li). "
    "The blind audit is therefore an independent automated re-annotation, not a second human curator.")
CANDIDATE_POLICY = (
    "Records in the candidate tier (status_group = candidate) receive no function call: their evidence_level is E5 "
    "by policy, because family membership is not established. Of the E5 records, the candidate tier accounts for "
    "{n_cand_e5} of {n_e5} counted records.")

log_lines = []


def log(msg):
    print(msg)
    log_lines.append(msg)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def norm(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(v) if not str(v).endswith(".0") else str(v)
    return str(v)


def same(a, b):
    a, b = norm(a), norm(b)
    if a == b:
        return True
    try:
        return float(a) == float(b)
    except ValueError:
        return False


def apply_decisions(con, d):
    for r in d.itertuples():
        key = TABLE_KEY[r.table_name]
        cur = con.execute(f'SELECT "{r.field}" FROM {r.table_name} WHERE {key} = ?', (r.source_acc,)).fetchall()
        if len(cur) != 1:
            sys.exit(f"{r.decision_id}: expected one {r.table_name} row for {r.source_acc}, found {len(cur)}")
        if not same(cur[0][0], r.old_value):
            sys.exit(f"{r.decision_id}: {r.table_name}.{r.field} of {r.source_acc} is {cur[0][0]!r}, "
                     f"decision expects {r.old_value!r}")
        new = None if r.new_value == "" else r.new_value
        if r.field in ("call_conflict",) and new is not None:
            new = int(float(new))
        if r.field == "e2_identity" and new is not None:
            new = float(new)
        con.execute(f'UPDATE {r.table_name} SET "{r.field}" = ? WHERE {key} = ?', (new, r.source_acc))
    log(f"applied {len(d)} field changes on {d.source_acc.nunique()} records")


def main():
    ap = argparse.ArgumentParser()
    for a in ("--base", "--decisions", "--tdefs", "--cdefs", "--out-db", "--dict-tsv", "--log"):
        ap.add_argument(a, required=True)
    a = ap.parse_args()

    # 1. verify and copy
    got = sha256(a.base)
    if got != V160_SHA256:
        sys.exit(f"base database checksum {got} != v1.6.0 {V160_SHA256}")
    os.makedirs(os.path.dirname(a.out_db) or ".", exist_ok=True)
    tmp = a.out_db + ".tmp"
    src = sqlite3.connect(f"file:{a.base}?mode=ro", uri=True)
    dst = sqlite3.connect(tmp)
    src.backup(dst)
    src.close()
    log(f"copied v1.6.0 ({V160_SHA256[:16]}...) read-only")
    con = dst

    # 2. decisions
    d = pd.read_csv(a.decisions, sep="\t", dtype=str, keep_default_na=False)
    apply_decisions(con, d)

    # 3. change column and decision table
    con.execute("ALTER TABLE function_evidence ADD COLUMN v161_change TEXT")
    for acc, rules in d.groupby("source_acc").rule.agg(lambda s: ";".join(sorted(set(s)))).items():
        con.execute("UPDATE function_evidence SET v161_change = ? WHERE source_acc = ?",
                    (f"identical_sequence_{rules}", acc))
    d.to_sql("curation_v161_decision", con, index=False)
    log(f"function_evidence.v161_change set on {d.source_acc.nunique()} records; curation_v161_decision {len(d)} rows")

    # 4. clade naming
    con.execute("ALTER TABLE clade ADD COLUMN name_basis_type TEXT")
    con.execute("""UPDATE clade SET name_basis_type = CASE
                     WHEN naming_basis LIKE '%no characterized member%' THEN 'provisional_motif_taxonomy'
                     ELSE 'characterised_member' END WHERE level = 1""")
    n = con.execute("UPDATE clade SET naming_basis = ? WHERE clade_id = 'MR_CLD3_017' AND naming_basis LIKE '%Q70LL3%'",
                    (CLADE_017_BASIS,)).rowcount
    if n != 1:
        sys.exit("MR_CLD3_017 naming basis not found")
    prov = con.execute("SELECT group_concat(clade_id) FROM clade WHERE name_basis_type='provisional_motif_taxonomy'").fetchone()[0]
    log(f"clade.name_basis_type: provisional names {prov}; MR_CLD3_017 naming basis updated")

    # 5. unified decider view
    con.execute("""CREATE VIEW v_curation_decision AS
        SELECT '1.6.0' AS release, CAST(decision_id AS TEXT) AS decision_id, group_id, source_acc, mrdb_acc,
               COALESCE(field_changed, '') AS field, old_value, new_value,
               COALESCE(user_decision, action, '') AS decision,
               COALESCE(NULLIF(signed_by, ''), decided_by) AS decider,
               COALESCE(NULLIF(signed_date, ''), decided_at) AS decided_on
        FROM curation_v160_decision
        UNION ALL
        SELECT '1.6.1', decision_id, rule, source_acc, mrdb_acc, table_name || '.' || field, old_value, new_value,
               'APPROVE', decided_by, decided_at
        FROM curation_v161_decision""")

    # 6. release metadata
    q = lambda s: con.execute(s).fetchone()[0]  # noqa: E731
    ev_cnt = dict(con.execute("SELECT evidence_level, COUNT(*) FROM v_counted GROUP BY 1").fetchall())
    ev_all = dict(con.execute("SELECT evidence_level, COUNT(*) FROM function_evidence GROUP BY 1").fetchall())
    tiers = dict(con.execute("""SELECT s.status_group, COUNT(*) FROM membership m
                                JOIN status_definition s ON s.status = m.membership_status GROUP BY 1""").fetchall())
    n_cand_e5 = q("""SELECT COUNT(*) FROM v_counted v JOIN status_definition s ON s.status = v.membership_status
                     WHERE s.status_group = 'candidate' AND v.evidence_level = 'E5'""")
    fmt = lambda dct: "{" + ", ".join(f'"{k}": {dct[k]}' for k in sorted(dct)) + "}"  # noqa: E731
    meta = [
        ("version", RELEASE), ("release_date", RELEASE_DATE), ("database_release", RELEASE),
        ("schema_revision", SCHEMA), ("base_release", "1.6.0 (immutable; opened read-only and copied)"),
        ("changes", "One decision per unique sequence (23 records, curation_v161_decision); clade.name_basis_type; "
                    "MR_CLD3_017 naming basis; v_curation_decision; candidate-call policy and curation-assistance "
                    "statements; CLI typeI_detected_070 now applies the full_gated gates (heliorhodopsins excluded)."),
        ("identical_sequence_policy", "Byte-identical non-engineered records share one membership status and one "
                                      "function call; rules M1, M2, F1-F5 in pipeline/v161/identical_sequences_v161.py"),
        ("candidate_function_policy", CANDIDATE_POLICY.format(n_cand_e5=n_cand_e5, n_e5=ev_cnt.get("E5", 0))),
        ("curation_assistance", CURATION_ASSISTANCE),
        ("n_protein_records", q("SELECT COUNT(*) FROM membership")),
        ("n_counted_records", q("SELECT COUNT(*) FROM v_counted")),
        ("membership_tier_counts_all", fmt(tiers)),
        ("evidence_level_counts_counted", fmt(ev_cnt)), ("evidence_level_counts_all", fmt(ev_all)),
        ("n_call_conflict", q("SELECT COUNT(*) FROM function_evidence WHERE call_conflict = 1")),
        ("license", "CC BY 4.0 (data); MIT (code)"),
    ]
    con.executemany("INSERT INTO release_metadata (release, key, value) VALUES (?, ?, ?)",
                    [(RELEASE, k, str(v)) for k, v in meta])
    con.commit()
    log("release_metadata 1.6.1: " + "; ".join(f"{k}={v}" for k, v in meta if k.startswith(("n_", "evidence", "membership"))))
    con.close()

    # 7. data dictionary, checks
    ddict.build(tmp, a.tdefs, a.cdefs, a.dict_tsv)
    con = sqlite3.connect(tmp)
    con.execute("UPDATE data_dictionary SET release = ?", (RELEASE,))
    con.commit()
    dd = pd.read_sql("SELECT * FROM data_dictionary ORDER BY object_name, ordinal", con)
    dd.to_csv(a.dict_tsv, sep="\t", index=False)
    ic = con.execute("PRAGMA integrity_check").fetchone()[0]
    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    con.execute("VACUUM")
    con.close()
    if ic != "ok" or fk:
        sys.exit(f"integrity {ic}; foreign-key violations {len(fk)}")
    os.replace(tmp, a.out_db)
    log(f"data_dictionary {len(dd)} rows; integrity ok; foreign keys ok")
    log(f"v1.6.1 database {a.out_db} sha256 {sha256(a.out_db)}")
    with open(a.log, "w") as f:
        f.write(f"MicroRhodoDB v{RELEASE} build log ({RELEASE_DATE})\n" + "\n".join(log_lines) + "\n")


if __name__ == "__main__":
    main()
