#!/usr/bin/env python3
"""Build MicroRhodoDB v1.6.2 from the immutable v1.6.1 database.

v1.6.2 is a correction release from the construction review (pipeline/construction_review/). It does not change the
corpus, the scorer, its thresholds, the tree, the placements or the clade assignments.

  1  verify the v1.6.1 checksum and copy it (v1.6.1 is opened read-only and never modified)
  2  new columns record_clade.placement_qc_flag and function_evidence.v162_change; v_master gains placement_qc_flag
  3  apply curation/v162/curation_v162_signed.tsv (rules MOTIF1, PLACE1, E2M1); every row is applied only if the
     current value equals the recorded old value
  4  function_evidence.v162_change, table curation_v162_decision, view v_curation_decision extended to v1.6.2
  5  release_metadata rows for 1.6.2
  6  data dictionary (100% coverage) from curation/v162 definitions; integrity and foreign-key checks

Usage: python pipeline/v162/build_v162.py --base <v1.6.1 db> --decisions <tsv> --tdefs <tsv> --cdefs <tsv>
                                          --out-db <db> --dict-tsv <tsv> --log <txt>
"""
import argparse
import os
import sqlite3
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "v160"))
sys.path.insert(0, os.path.join(HERE, "..", "v161"))
import data_dictionary_v160 as ddict                         # noqa: E402
from build_v161 import apply_decisions as _apply, sha256     # noqa: E402
import build_v161                                            # noqa: E402

V161_SHA256 = "b8215cffa9d2fdab1e65b904f4bafbe9edf6578aed7b4fb028a890850e704c2d"
RELEASE, RELEASE_DATE, SCHEMA = "1.6.2", "2026-11-25", "v162.1"
MASTER_TAIL = "a.model_id AS afdb_model_id, a.global_plddt AS afdb_global_plddt"

log_lines = []


def log(msg):
    print(msg)
    log_lines.append(msg)


def apply_decisions(con, d):
    build_v161.TABLE_KEY["record_clade"] = "source_acc"
    build_v161.log_lines = log_lines
    _apply(con, d)   # INTEGER/REAL column affinity converts the text values written by the v1.6.1 applier


def main():
    ap = argparse.ArgumentParser()
    for a in ("--base", "--decisions", "--tdefs", "--cdefs", "--out-db", "--dict-tsv", "--log"):
        ap.add_argument(a, required=True)
    a = ap.parse_args()

    # 1. verify and copy
    got = sha256(a.base)
    if got != V161_SHA256:
        sys.exit(f"base database checksum {got} != v1.6.1 {V161_SHA256}")
    os.makedirs(os.path.dirname(a.out_db) or ".", exist_ok=True)
    tmp = a.out_db + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    src = sqlite3.connect(f"file:{a.base}?mode=ro", uri=True)
    con = sqlite3.connect(tmp)
    src.backup(con)
    src.close()
    log(f"copied v1.6.1 ({V161_SHA256[:16]}...) read-only")

    d = pd.read_csv(a.decisions, sep="\t", dtype=str, keep_default_na=False)
    if (d.decided_by == "UNSIGNED").any():
        log("WARNING: decisions are UNSIGNED (decided_by); the v1.6.2 release test fails until they are signed")

    # 2. columns and v_master
    con.execute("ALTER TABLE record_clade ADD COLUMN placement_qc_flag TEXT")
    con.execute("ALTER TABLE function_evidence ADD COLUMN v162_change TEXT")
    master = con.execute("SELECT sql FROM sqlite_master WHERE name = 'v_master'").fetchone()[0]
    if master.count(MASTER_TAIL) != 1:
        sys.exit("v_master select list not as expected")
    con.execute("DROP VIEW v_master")
    con.execute(master.replace(MASTER_TAIL, MASTER_TAIL + ", rc.placement_qc_flag"))
    log("record_clade.placement_qc_flag and function_evidence.v162_change added; v_master gains placement_qc_flag")

    # 3. decisions
    apply_decisions(con, d)

    # 4. change column, decision table, decider view
    for acc, rules in d.groupby("source_acc").rule.agg(lambda s: ";".join(sorted(set(s)))).items():
        con.execute("UPDATE function_evidence SET v162_change = ? WHERE source_acc = ?", (rules, acc))
    d.to_sql("curation_v162_decision", con, index=False)
    view = con.execute("SELECT sql FROM sqlite_master WHERE name = 'v_curation_decision'").fetchone()[0]
    con.execute("DROP VIEW v_curation_decision")
    con.execute(view + """
        UNION ALL
        SELECT '1.6.2', decision_id, rule, source_acc, mrdb_acc, table_name || '.' || field, old_value, new_value,
               'APPROVE', decided_by, decided_at
        FROM curation_v162_decision""")
    log(f"function_evidence.v162_change set on {d.source_acc.nunique()} records; curation_v162_decision {len(d)} rows; "
        "v_curation_decision extended")

    # 5. release metadata
    q = lambda s: con.execute(s).fetchone()[0]  # noqa: E731
    ev_cnt = dict(con.execute("SELECT evidence_level, COUNT(*) FROM v_counted GROUP BY 1").fetchall())
    ev_all = dict(con.execute("SELECT evidence_level, COUNT(*) FROM function_evidence GROUP BY 1").fetchall())
    tiers = dict(con.execute("""SELECT s.status_group, COUNT(*) FROM membership m
                                JOIN status_definition s ON s.status = m.membership_status GROUP BY 1""").fetchall())
    flags = dict(con.execute("""SELECT placement_qc_flag, COUNT(*) FROM record_clade
                                WHERE placement_qc_flag IS NOT NULL GROUP BY 1""").fetchall())
    fmt = lambda dct: "{" + ", ".join(f'"{k}": {dct[k]}' for k in sorted(dct)) + "}"  # noqa: E731
    by_rule = d.groupby("rule").source_acc.nunique().to_dict()
    meta = [
        ("version", RELEASE), ("release_date", RELEASE_DATE), ("database_release", RELEASE),
        ("schema_revision", SCHEMA), ("base_release", "1.6.1 (immutable; opened read-only and copied)"),
        ("changes", f"Construction review (curation_v162_decision, {len(d)} field changes on "
                    f"{d.source_acc.nunique()} records): MOTIF1 helix-C motif for the {by_rule.get('MOTIF1', 0)} "
                    "records without one; PLACE1 record_clade.placement_qc_flag for "
                    f"{by_rule.get('PLACE1', 0)} Type-I records placed in the heliorhodopsin outgroup; E2M1 E2 "
                    f"withdrawn for {by_rule.get('E2M1', 0)} record whose helix-C motif differs from its E1 "
                    "reference. v_master gains placement_qc_flag."),
        ("helixc_motif_method", "tools/helixc_motif.py: residues at BR D85/T89/D96 match states of an hmmalign "
                                "alignment against PF01036.25; reproduces the stored motif and motif_class for all "
                                "5,361 UniProtKB 2026_02 records (pipeline/construction_review/)"),
        ("e2_motif_policy", "An E2 call is kept only when the record's helix-C motif equals that of its E1 reference "
                            "(non-engineered records); otherwise the record is E5 unresolved."),
        ("placement_qc_flag_counts", fmt(flags)),
        ("n_protein_records", q("SELECT COUNT(*) FROM membership")),
        ("n_counted_records", q("SELECT COUNT(*) FROM v_counted")),
        ("membership_tier_counts_all", fmt(tiers)),
        ("evidence_level_counts_counted", fmt(ev_cnt)), ("evidence_level_counts_all", fmt(ev_all)),
        ("n_call_conflict", q("SELECT COUNT(*) FROM function_evidence WHERE call_conflict = 1")),
        ("n_missing_helixc_motif", q("SELECT COUNT(*) FROM function_evidence WHERE helixC_motif IS NULL")),
        ("license", "CC BY 4.0 (data); MIT (code)"),
    ]
    con.executemany("INSERT INTO release_metadata (release, key, value) VALUES (?, ?, ?)",
                    [(RELEASE, k, str(v)) for k, v in meta])
    con.commit()
    log("release_metadata 1.6.2: " + "; ".join(f"{k}={v}" for k, v in meta
                                               if k.startswith(("n_", "evidence", "membership", "placement"))))
    con.close()

    # 6. data dictionary, checks
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
    log(f"v1.6.2 database {a.out_db} sha256 {sha256(a.out_db)}")
    with open(a.log, "w") as f:
        f.write(f"MicroRhodoDB v{RELEASE} build log ({RELEASE_DATE})\n" + "\n".join(log_lines) + "\n")


if __name__ == "__main__":
    main()
