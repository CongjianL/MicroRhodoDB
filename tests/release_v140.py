#!/usr/bin/env python3
"""release_v140.py — MicroRhodoDB v1.4.0 release validation suite.

Validates the v1.4.0 build DB against the frozen v1.3.0 release and the
v1.4.0 extension invariants. Series:
  F  frozen-layer carry integrity (row-hash v1.3.0 == v1.4.0 for carried rows)
  E  extension invariants (counts, FK, vocabularies, policy consistency)
  S  scorer gate (rosetta->scorer->frozen 0-diff; 105-row extension artifact)
  T  MR_RT_002 promotion gates (tree storage conventions, clade monophyly,
     placement coverage/integrity)

Usage:
  python release_v140.py <repo_root> <v140_db_path> [out_json]
Exit code 0 iff all tests pass.
"""
import hashlib
import json
import os
import sqlite3
import sys
from collections import defaultdict

import pandas as pd

RESULTS = []


def record(name, ok, detail=""):
    RESULTS.append({"test": name, "status": "PASS" if ok else "FAIL", "detail": str(detail)})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


def connect_ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def rows_hash(con, table, cols, where=None, order=None):
    sql = f"SELECT {','.join(cols)} FROM {table}"
    if where:
        sql += f" WHERE {where}"
    if order:
        sql += f" ORDER BY {order}"
    h = hashlib.sha256()
    n = 0
    for row in con.execute(sql):
        h.update(repr(tuple(row)).encode())
        n += 1
    return h.hexdigest(), n


def table_cols(con, table):
    return [c[1] for c in con.execute(f"PRAGMA table_info({table})").fetchall()]


def main():
    root = sys.argv[1]
    v140_path = sys.argv[2]
    out_json = sys.argv[3] if len(sys.argv) > 3 else None
    v13 = connect_ro(os.path.join(root, "releases/v1.3.0/db/microrhododb_v1.3.0.sqlite"))
    v14 = connect_ro(v140_path)

    # ------------------------------------------------------------------ F: frozen carry
    # Extended tables: frozen rows selected by key membership in v1.3.0.
    # v1.3.0 contains ONLY frozen rows, so the v13-side hash needs no WHERE.
    EXT_KEY = {"protein": "source_acc", "membership": "source_acc", "qc_feature": "source_acc",
               "active_population": "source_acc", "redundancy": "source_acc",
               "sequence_source": "source_acc"}
    frozen_specs = [(t, f"{k} IN (SELECT {k} FROM v13.{t})", k) for t, k in EXT_KEY.items()]
    frozen_specs += [
        ("placement", None, "source_acc"),
        ("reference_clade", "clade_id NOT LIKE 'MR_CLD2_%'", "clade_id"),
        ("reference_clade_tip", "clade_id NOT LIKE 'MR_CLD2_%'", "clade_id, source_acc"),
        ("tree_node", "tree_id='MR_RT_001'", "node_id"),
        ("tree_edge", "tree_id='MR_RT_001'", "edge_id"),
        ("seed", None, "acc"),
        ("tier_a_assertion", None, "assertion_id"),
        ("tier_a_evidence", None, "rowid"),
        ("tier_a_holdout", None, "source_acc"),
        ("reference_backbone", None, "representative"),
        ("reference_clade_member", None, "clade_id, source_acc"),
        ("subfamily", None, "source_acc"),
        ("subfamily_assignment", None, "source_acc"),
        ("environmental_admission", None, "source_acc"),
        ("external_validation", None, "rowid"),
        ("holdout_assignment", None, "rowid"),
        ("benchmark_v2", None, "rowid"),
        ("function", None, "rowid"),
        ("function_assignment", None, "rowid"),
        ("publication", None, "rowid"),
        ("citation", None, "rowid"),
        ("assertion_publication", None, "rowid"),
        ("pdb_structure", None, "rowid"),
        ("protein_pdb", None, "rowid"),
        ("predicted_structure", None, "rowid"),
        ("structure", None, "rowid"),
        ("external_validation_metric", None, "rowid"),
        ("holdout_metric", None, "rowid"),
        ("protein_architecture_flag", None, "rowid"),
    ]
    v14.execute(f"ATTACH DATABASE '{os.path.join(root, 'releases/v1.3.0/db/microrhododb_v1.3.0.sqlite')}' AS v13")
    n_pass_f, fails_f = 0, []
    for t, whr, order in frozen_specs:
        if t not in table_cols(v13, t) and t not in [r[0] for r in v13.execute("SELECT name FROM sqlite_master WHERE type='table'")]:
            fails_f.append((t, "missing in v1.3.0"))
            continue
        cols = table_cols(v13, t)
        h13, n13 = rows_hash(v13, t, cols, None, order)
        h14, n14 = rows_hash(v14, t, cols, whr, order)
        ok = (h13 == h14) and (n13 == n14)
        n_pass_f += ok
        if not ok:
            fails_f.append((t, n13, n14))
    record("F_frozen_layer_row_hashes", n_pass_f == len(frozen_specs),
           f"{n_pass_f}/{len(frozen_specs)} frozen tables byte-identical; failures={fails_f}")

    # reference_tree: identical except the documented MR_RT_002 status transition
    rt13 = pd.read_sql("SELECT * FROM reference_tree", v13).set_index("tree_id")
    rt14 = pd.read_sql("SELECT * FROM reference_tree", v14).set_index("tree_id")
    diffs = [(tid, c, rt13.loc[tid, c], rt14.loc[tid, c])
             for tid in rt13.index for c in rt13.columns
             if str(rt13.loc[tid, c]) != str(rt14.loc[tid, c])]
    record("F_reference_tree_status_only",
           diffs == [("MR_RT_002", "status", "orphaned_candidate", "canonical_release")],
           f"diffs={diffs}")

    # release_metadata: non-identity keys identical; identity keys updated; additions only
    rm13 = dict(pd.read_sql("SELECT key, value FROM release_metadata", v13).values)
    rm14 = dict(pd.read_sql("SELECT key, value FROM release_metadata", v14).values)
    identity = {"database_release", "schema_revision", "base_release"}
    common_ok = all(rm14.get(k) == v for k, v in rm13.items() if k not in identity)
    added = sorted(set(rm14) - set(rm13))
    record("F_release_metadata",
           common_ok and rm14["database_release"] == "1.4.0" and rm14["schema_revision"] == "v140.1"
           and rm14["base_release"].startswith("1.3.0"),
           f"common_ok={common_ok}, added={added}")

    # ------------------------------------------------------------------ E: extension invariants
    n_mem = v14.execute("SELECT COUNT(*) FROM membership").fetchone()[0]
    n_new = v14.execute("SELECT COUNT(*) FROM extension_delta WHERE delta_class='new'").fetchone()[0]
    n_dem = v14.execute("SELECT COUNT(*) FROM extension_delta WHERE delta_class='demoted_or_merged'").fetchone()[0]
    new_in_mem = v14.execute("""SELECT COUNT(*) FROM membership WHERE source_acc IN
                                (SELECT accession FROM extension_delta WHERE delta_class='new')""").fetchone()[0]
    record("E1_membership_extension", n_mem == 5466 and n_new == 105 and new_in_mem == 105 and n_dem == 6,
           f"membership={n_mem} (5361+105), new={n_new} all admitted, demoted={n_dem} logged-only")

    n_prot = v14.execute("SELECT COUNT(*) FROM protein").fetchone()[0]
    n_ss = v14.execute("SELECT COUNT(*) FROM sequence_source").fetchone()[0]
    record("E2_protein_sequence_source", n_prot == 6818 and n_ss == 6818,
           f"protein={n_prot}, sequence_source={n_ss} (6713+105)")

    n_qc = v14.execute("SELECT COUNT(*) FROM qc_feature").fetchone()[0]
    qc_missing = v14.execute("""SELECT COUNT(*) FROM membership m LEFT JOIN qc_feature q USING(source_acc)
                                WHERE q.source_acc IS NULL""").fetchone()[0]
    record("E3_qc_feature_complete", n_qc == 5466 and qc_missing == 0,
           f"qc_feature={n_qc}, membership rows missing qc={qc_missing}")

    ap = pd.read_sql("SELECT * FROM active_population", v14)
    mem_status = dict(pd.read_sql("SELECT source_acc, membership_status FROM membership", v14).values)
    POLICY = {"typeI_core": ("core", 1, 1, 0), "typeI_core_architecture_supported": ("core", 1, 1, 0),
              "typeI_candidate": ("candidate", 1, 0, 1),
              "typeI_candidate_architecture_supported": ("candidate", 1, 0, 1),
              "typeI_candidate_unresolved": ("candidate", 1, 0, 1),
              "heliorhodopsin": ("heliorhodopsin", 0, 0, 0), "decoy_or_rejected": ("rejected", 0, 0, 0)}
    bad = sum(1 for r in ap.itertuples()
              if (r.policy_class, r.is_active, r.is_core, r.is_candidate) != POLICY[r.membership_status]
              or r.membership_status != mem_status.get(r.source_acc))
    record("E4_active_population_policy", bad == 0 and len(ap) == 5466,
           f"rows={len(ap)}, policy violations={bad}")

    vocab = tuple(POLICY)
    bad_vocab = v14.execute(f"SELECT COUNT(*) FROM membership WHERE membership_status NOT IN {vocab}").fetchone()[0]
    score_bad = v14.execute("SELECT COUNT(*) FROM membership WHERE membership_score < 0 OR membership_score > 1").fetchone()[0]
    record("E5_vocab_and_score_range", bad_vocab == 0 and score_bad == 0,
           f"bad_status={bad_vocab}, score_out_of_range={score_bad}")

    integ = v14.execute("PRAGMA integrity_check").fetchone()[0]
    fk = v14.execute("PRAGMA foreign_key_check").fetchall()
    record("E6_sqlite_integrity_fk", integ == "ok" and len(fk) == 0,
           f"integrity={integ}, fk_violations={len(fk)}")

    helio = v14.execute("""SELECT COUNT(*) FROM membership WHERE source_acc IN
                           (SELECT accession FROM extension_delta WHERE delta_class='new')
                           AND membership_status='heliorhodopsin'""").fetchone()[0]
    record("E7_new_helio_routing", helio == 9, f"new heliorhodopsin-status rows={helio} (expect 9)")

    red_new = pd.read_sql("""SELECT * FROM redundancy WHERE source_acc IN
                             (SELECT accession FROM extension_delta WHERE delta_class='new')""", v14)
    exnr_ok = red_new.exact_nr_cluster.str.startswith("EXNR_").all()
    record("E8_redundancy_extension", len(red_new) == 105 and exnr_ok,
           f"rows={len(red_new)}, EXNR prefix ok={exnr_ok}")

    # ------------------------------------------------------------------ S: scorer gate
    sys.path.insert(0, os.path.join(root, "pipeline", "v140"))
    import scorer_v140 as sv  # noqa: E402

    ros = pd.read_csv(os.path.join(root, "releases/v1.0/tables/membership_assignments.tsv"), sep="\t")
    ev = sv.evidence_vector(ros)
    s_unr, s_round = sv.score_from_evidence(ev)
    score_diffs = int((s_round != ros["membership_score"]).sum())
    cat = [sv.categorize(s_unr.loc[i], bool(r["gate_has_domain"]), bool(r["is_helio_primary"]),
                         bool(r["gate_retinal_lysine"]), bool(r["gate_complete_core"]),
                         bool(r["gate_positive_typeI_margin"]), bool(r["has_pdb_xref"]))
           for i, r in ros.iterrows()]
    cat_diffs = int((pd.Series(cat) != ros["membership_category"]).sum())
    record("S1_scorer_gate_frozen", score_diffs == 0 and cat_diffs == 0,
           f"rosetta->scorer->frozen: score diffs {score_diffs}/5361, category diffs {cat_diffs}/5361")

    ext_path = os.path.join(os.path.dirname(v140_path), "membership_assignments_v140_ext.tsv")
    if not os.path.exists(ext_path):
        ext_path = os.path.join(root, "releases/v1.4.0/tables/membership_assignments_v140_ext.tsv")
    ext = pd.read_csv(ext_path, sep="\t")
    ev_e = sv.evidence_vector(ext)
    su_e, sr_e = sv.score_from_evidence(ev_e)
    s2_score = int((sr_e != ext["membership_score"]).sum())
    cat_e = [sv.categorize(su_e.loc[i], bool(r["gate_has_domain"]), bool(r["is_helio_primary"]),
                           bool(r["gate_retinal_lysine"]), bool(r["gate_complete_core"]),
                           bool(r["gate_positive_typeI_margin"]), bool(r["has_pdb_xref"]))
             for i, r in ext.iterrows()]
    s2_cat = int((pd.Series(cat_e) != ext["membership_category"]).sum())
    memb_new = pd.read_sql("""SELECT source_acc, membership_score, membership_category FROM membership
                              WHERE source_acc IN (SELECT accession FROM extension_delta WHERE delta_class='new')""", v14)
    mrg = ext.merge(memb_new, on="source_acc", suffixes=("", "_db"))
    db_ok = bool((mrg.membership_score == mrg.membership_score_db).all()
                 and (mrg.membership_category == mrg.membership_category_db).all())
    record("S2_scorer_gate_extension", s2_score == 0 and s2_cat == 0 and db_ok,
           f"105-row artifact: score diffs={s2_score}, category diffs={s2_cat}, DB agrees={db_ok}")

    # ------------------------------------------------------------------ T: MR_RT_002 gates
    tn = pd.read_sql("SELECT * FROM tree_node WHERE tree_id='MR_RT_002'", v14)
    te = pd.read_sql("SELECT * FROM tree_edge WHERE tree_id='MR_RT_002'", v14)
    tips = tn[tn.kind == "tip"]
    ints = tn[tn.kind == "internal"]
    children = set(te.child_node)
    roots = [n for n in tn.node_id if n not in children]
    root_deg = len(te[te.parent_node == roots[0]]) if len(roots) == 1 else -1
    record("T1_tree_counts",
           len(tn) == 554 and len(te) == 553 and len(tips) == 278 and len(ints) == 276
           and roots == ["N001"] and root_deg == 3,
           f"nodes={len(tn)}, edges={len(te)}, tips={len(tips)}, internal={len(ints)}, root={roots}, degree={root_deg}")

    cmap = defaultdict(list)
    for r in te.sort_values("edge_id").itertuples():
        cmap[r.parent_node].append((r.edge_id, r.child_node))
    seq_n, seq_t, seq_e = [], [], []

    def rec(node):
        (seq_n if node.startswith("N") else seq_t).append(node)
        for eid, ch in cmap[node]:
            seq_e.append(eid)
        for eid, ch in cmap[node]:
            rec(ch)
    rec("N001")
    conv_ok = (seq_n == [f"N{i:03d}" for i in range(1, 277)]
               and seq_t == [f"T{i:03d}" for i in range(1, 279)]
               and seq_e == [f"E{i:03d}" for i in range(1, 554)])
    record("T2_tree_id_conventions", conv_ok,
           "DFS preorder T/N counters + edges-at-parent-visit sequential (MR_RT_001 conventions)")

    rc2 = pd.read_sql("SELECT * FROM reference_clade WHERE clade_id LIKE 'MR_CLD2_%'", v14)
    rct2 = pd.read_sql("SELECT * FROM reference_clade_tip WHERE clade_id LIKE 'MR_CLD2_%'", v14)
    tipsets_db = rct2.groupby("clade_id").source_acc.apply(frozenset).to_dict()
    child_map = defaultdict(list)
    for r in te.itertuples():
        child_map[r.parent_node].append(r.child_node)
    node_src = tn.set_index("node_id").source_acc.to_dict()

    def desc(nid):
        out, stack = [], [nid]
        while stack:
            x = stack.pop()
            if x.startswith("T"):
                out.append(node_src[x])
            else:
                stack.extend(child_map[x])
        return frozenset(out)

    mono = sum(1 for r in rc2.itertuples() if desc(r.tree_node_id) == tipsets_db.get(r.clade_id))
    in_edge = {r.child_node: r.edge_id for r in te.itertuples()}
    edge_ok = sum(1 for r in rc2.itertuples() if in_edge.get(r.tree_node_id) == r.edge_id)
    par_ok = sum(1 for r in rc2.itertuples()
                 if pd.isna(r.parent_clade_id) or tipsets_db[r.clade_id] < tipsets_db[r.parent_clade_id])
    record("T3_clade_monophyly", mono == 55 and edge_ok == 55 and par_ok == 55 and len(rc2) == 55,
           f"clades={len(rc2)}, monophyletic={mono}, edge=incoming={edge_ok}, parentage_ok={par_ok}")

    pv = pd.read_sql("SELECT * FROM placement_v140", v14)
    elig = v14.execute("""SELECT COUNT(*) FROM membership m JOIN qc_feature q USING(source_acc)
                          WHERE m.membership_status IN ('typeI_core','typeI_core_architecture_supported','typeI_candidate',
                                                        'typeI_candidate_architecture_supported','typeI_candidate_unresolved')
                          AND q.complete_core=1
                          AND m.source_acc NOT IN (SELECT source_acc FROM tree_node
                                                   WHERE tree_id='MR_RT_002' AND kind='tip')""").fetchone()[0]
    lwr_ok = bool(pv.best_lwr.between(0, 1).all())
    want_status = pd.Series(pd.Series("placed_ambiguous", index=pv.index)
                            .mask(pv.best_lwr >= 0.5, "placed_clade_compatible")
                            .mask(pv.best_lwr >= 0.9, "placed_high_confidence"))
    status_rule = bool((want_status == pv.placement_status).all())
    ref_ok = bool(pv.best_edge.isin(set(te.edge_id)).all()
                  and pv.clade_id.dropna().isin(set(rc2.clade_id)).all())
    record("T4_placement_v140",
           len(pv) == 4335 and len(pv) == elig and lwr_ok and status_rule and ref_ok,
           f"rows={len(pv)}, eligible={elig} (coverage {len(pv)/max(elig,1):.4f}), "
           f"lwr_ok={lwr_ok}, status_rule={status_rule}, refs_ok={ref_ok}")

    rt_status = dict(v14.execute("SELECT tree_id, status FROM reference_tree").fetchall())
    record("T5_canonical_tree_recorded",
           rt_status.get("MR_RT_002") == "canonical_release" and "MR_RT_002" in rm14.get("canonical_tree_id", ""),
           f"status={rt_status}, canonical_tree_id recorded={'canonical_tree_id' in rm14}")

    # ------------------------------------------------------------------ summary
    n_pass = sum(1 for r in RESULTS if r["status"] == "PASS")
    out = {"release": "1.4.0", "db": v140_path, "n_pass": n_pass, "n_total": len(RESULTS),
           "results": RESULTS}
    if out_json:
        with open(out_json, "w") as fh:
            json.dump(out, fh, indent=1)
    print(f"\n=== {n_pass}/{len(RESULTS)} PASS ===")
    sys.exit(0 if n_pass == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
