#!/usr/bin/env python
"""Build the MicroRhodoDB v1.5.0 release databases from the immutable v1.4.0 database plus v1.5 work products.

Outputs
  microrhododb_v1.5.0.sqlite           UniProt-derived corpus (5,466 records) - the release
  microrhododb_v1.5.0_env_pilot.sqlite  MGnify environmental pilot (1,352 records) - supplementary, not part of the release counts

Principles
  * v1.4.0 file is opened read-only and copied; it is never modified.
  * superseded v1.4 tables are kept with a legacy_ prefix; old names that users query are kept as compatibility VIEWS.
  * every proportion CI is Wilson (ci_method column); v1.4 CIs are recomputed where counts are available.
Usage: build_v150.py config.json
"""
import json, sys, os, sqlite3, shutil, hashlib, datetime
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from statsmodels.stats.proportion import proportion_confint

LEGACY = {  # v1.4 table -> v1.5 legacy name
    "membership": "legacy_membership_v14", "active_population": "legacy_active_population_v14",
    "subfamily": "legacy_subfamily_v14", "subfamily_assignment": "legacy_subfamily_assignment_v14",
    "function": "legacy_function_v14", "function_assignment": "legacy_function_assignment_v14",
    "placement": "legacy_placement_rt001", "placement_v140": "legacy_placement_rt002",
    "reference_clade": "legacy_reference_clade_cld2", "reference_clade_member": "legacy_reference_clade_member_cld2",
    "reference_clade_tip": "legacy_reference_clade_tip_cld2", "reference_backbone": "legacy_reference_backbone_rt001",
    "external_validation": "legacy_external_validation_v14", "external_validation_metric": "legacy_external_validation_metric_v14",
    "holdout_metric": "legacy_holdout_metric_v14", "publication": "legacy_publication_v14",
    "assertion_publication": "legacy_assertion_publication_v14",
}
DROP_VIEWS = ["v_active_function", "v_active_subfamily", "v_master", "v_rejected_or_decoy", "v_typeI_active",
              "v_typeI_candidates", "v_typeI_core"]


def wilson(k, n):
    if not n or pd.isna(n) or n == 0:
        return (np.nan, np.nan)
    lo, hi = proportion_confint(int(k), int(n), method="wilson")
    return float(lo), float(hi)


def sha(s):
    return hashlib.sha256(s.upper().replace("*", "").encode()).hexdigest()


def put(con, df, name, pk=None):
    df.to_sql(name, con, index=False, if_exists="replace")
    if pk:
        con.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS ux_{name}_{"_".join(pk)} ON "{name}" ({", ".join(pk)})')


def main():
    C = json.load(open(sys.argv[1]))
    out, env_out = C["out_db"], C["out_env_db"]
    for p in (out, env_out):
        if os.path.exists(p):
            os.remove(p)
    src = sqlite3.connect(f"file:{C['v140_db']}?mode=ro", uri=True)
    dst = sqlite3.connect(out)
    src.backup(dst)
    src.close()
    con = dst
    con.execute("PRAGMA foreign_keys=OFF")
    now = datetime.date.today().isoformat()
    prov = []

    # ---------- 1. environmental layer -> separate pilot DB ----------
    mg = pd.read_sql("select source_acc from sequence_source where source_database='MGnify'", con).source_acc
    env = sqlite3.connect(env_out)
    for t in ("protein", "sequence_source", "environmental_admission"):
        d = pd.read_sql(f'select * from "{t}"', con)
        d = d[d.source_acc.isin(set(mg))]
        d.to_sql(t, env, index=False)
    pd.DataFrame([("database", "MicroRhodoDB v1.5.0 environmental pilot (supplementary)"),
                  ("n_records", str(len(mg))),
                  ("status", "supplementary; not part of release counts; frozen v1.2.0 classifier scores"),
                  ("caveat", "v1.4 classifier_score could not be reproduced for ~194 records (max |delta| 0.32); scores are archival"),
                  ("built", now)], columns=["key", "value"]).to_sql("release_metadata", env, index=False)
    env.commit(); env.close()
    for t in ("protein", "sequence_source"):
        con.execute(f"DELETE FROM {t} WHERE source_acc IN (select source_acc from environmental_admission)")
    con.execute("DROP TABLE environmental_admission")
    prov.append(("(env pilot)", "v1.4 MGnify rows", "build_v150.py", "moved to microrhododb_v1.5.0_env_pilot.sqlite", "", ""))

    # ---------- 2. legacy renames ----------
    for v in DROP_VIEWS:
        con.execute(f"DROP VIEW IF EXISTS {v}")
    for old, new in LEGACY.items():
        con.execute(f'ALTER TABLE "{old}" RENAME TO "{new}"')

    # ---------- 3. stable accessions ----------
    prot = pd.read_sql("select rowid as rid, * from protein", con)
    prot["sequence_sha256"] = prot.sequence.map(sha)
    first = prot.sort_values("rid").drop_duplicates("sequence_sha256")
    first = first.assign(mrdb_acc=[f"MRDB{i:06d}" for i in range(1, len(first) + 1)])
    acc = first[["mrdb_acc", "sequence_sha256", "source_acc"]].rename(columns={"source_acc": "representative_source_acc"})
    acc["first_release"] = "1.5.0"
    acc["n_source_records"] = acc.sequence_sha256.map(prot.sequence_sha256.value_counts())
    prot = prot.merge(acc[["mrdb_acc", "sequence_sha256"]], on="sequence_sha256")
    amap = prot[["mrdb_acc", "source_acc"]].assign(source_database="UniProt", release_added="<=1.4.0", is_current=1)
    put(con, acc, "mrdb_accession", ["mrdb_acc"])
    put(con, amap, "accession_map", ["source_acc"])
    con.execute("ALTER TABLE protein ADD COLUMN mrdb_acc TEXT")
    con.execute("ALTER TABLE protein ADD COLUMN sequence_sha256 TEXT")
    con.executemany("UPDATE protein SET mrdb_acc=?, sequence_sha256=? WHERE source_acc=?",
                    prot[["mrdb_acc", "sequence_sha256", "source_acc"]].values.tolist())
    prov.append(("mrdb_accession", "protein.sequence", "build_v150.py",
                 "MRDB + 6 digits, one per unique sequence sha256 (uppercase, '*' stripped), ordered by first v1.4 protein rowid; never reused", "", "protein"))

    # ---------- 4. membership v1.5 ----------
    sd = pd.read_csv(C["status_definition"], sep="\t")
    put(con, sd, "status_definition", ["status"])
    m = pd.read_csv(C["membership"], sep="\t")
    m = m.rename(columns={"membership_status_v150": "membership_status", "membership_category": "score_category_v14",
                          "ms210": "retinal_site_residue"})
    m = m.merge(prot[["source_acc", "mrdb_acc"]], on="source_acc", how="left")
    put(con, m, "membership", ["source_acc"])
    prov.append(("membership", "legacy_membership_v14 + WP2", "wp2_status.py",
                 "member = PF01036 family + K at match state 210 (BR K216) + score>=0.86; candidate 0.40-0.86; boundary_family = TM7-covering, non-K", "", "status_definition"))

    # ---------- 5. MR_RT_003 tree, clades, placements ----------
    rt = pd.read_sql("select * from reference_tree", con)
    rt["status"] = rt.status.replace({"canonical_release": "legacy"})
    rt = pd.concat([rt, pd.DataFrame([C["mr_rt_003"]])], ignore_index=True)
    put(con, rt, "reference_tree", ["tree_id"])
    nodes, edges = C["mr_rt_003_nodes"], C["mr_rt_003_edges"]
    nd = pd.read_csv(nodes, sep="\t"); ed = pd.read_csv(edges, sep="\t")
    nd.to_sql("tree_node", con, index=False, if_exists="append")
    ed.to_sql("tree_edge", con, index=False, if_exists="append")
    cl = pd.read_csv(C["clades"], sep="\t")
    put(con, cl, "clade", ["clade_id"])
    put(con, pd.read_csv(C["clade_tips"], sep="\t"), "clade_tip")
    rcl = pd.read_csv(C["record_clade"], sep="\t").fillna({"clade_id": "", "subclade_id": ""})
    rcl = rcl[rcl.source_acc.isin(set(prot.source_acc))]
    put(con, rcl, "record_clade", ["source_acc"])
    # n_records_assigned is recomputed from the release record_clade table (corpus records only; the WP4 consensus
    # table also counted external/boundary placements, which caused 5 level-1 cache mismatches in the pre-curation build)
    n1 = rcl[rcl.clade_id != ""].clade_id.value_counts()
    n2 = rcl[rcl.subclade_id != ""].subclade_id.value_counts()
    cl["n_records_assigned"] = [int(n1.get(c, 0)) if lv == 1 else int(n2.get(c, 0)) for c, lv in zip(cl.clade_id, cl.level)]
    put(con, cl, "clade", ["clade_id"])
    pl = pd.read_csv(C["placements"], sep="\t")
    pl = pl[pl.source_acc.isin(set(prot.source_acc))]          # corpus only; external set placements live in external_validation
    pl["best_edge"] = pl.best_edge.map(lambda e: f"E{int(e):04d}")
    pl.insert(0, "tree_id", "MR_RT_003")
    # unified placement table: v1.5 placements + v1.4 legacy placements re-expressed with tree_id
    l1 = pd.read_sql("select source_acc, best_edge, best_lwr, n_credible, dispersion, pendant_length, clade_id, placement_status, track "
                     "from legacy_placement_rt001", con).assign(tree_id="MR_RT_001", model_tag="Q.PFAM+F+R6(tree)/LG+G(placement)")
    l2 = pd.read_sql("select source_acc, best_edge, best_lwr, n_credible, dispersion, pendant_length, clade_id, placement_status "
                     "from legacy_placement_rt002", con).assign(tree_id="MR_RT_002", model_tag="Q.PFAM+F+R6(tree)/LG+G(placement)")
    leg = pd.concat([l1, l2]).rename(columns={"n_credible": "n_credible95", "dispersion": "lwr_weighted_pendant",
                                               "pendant_length": "best_pendant", "placement_status": "clade_call"})
    leg["is_current"] = 0
    pl["is_current"] = (pl.model_tag == C["primary_model_tag"]).astype(int)
    put(con, pd.concat([pl, leg], ignore_index=True), "placement")
    con.execute("CREATE INDEX ix_placement_acc ON placement (source_acc, tree_id)")
    put(con, pd.read_csv(C["model_sensitivity"], sep="\t"), "placement_model_sensitivity")
    put(con, pd.read_csv(C["clade_robustness"], sep="\t"), "clade_robustness")
    put(con, pd.read_csv(C["clade_crosswalk"], sep="\t"), "clade_crosswalk")
    r3 = pd.read_csv(C["route3"], sep="\t")
    put(con, r3[r3.source_acc.isin(set(prot.source_acc))], "route3_candidate_support", ["source_acc"])

    # ---------- 6. function evidence, characterized set, publications ----------
    fe = pd.read_csv(C["function_evidence"], sep="\t")
    keep = ["source_acc", "func_class_v150", "evidence_level", "function_basis_v150", "helixC_motif", "motif_class",
            "exp_class", "e2_ref", "e2_identity", "clade_id", "clade_function", "override_rule", "func_class"]
    fe = fe[[c for c in keep if c in fe.columns]].rename(columns={"func_class_v150": "func_class", "func_class": "func_class_v14",
                                                                   "function_basis_v150": "basis"})
    put(con, fe, "function_evidence", ["source_acc"])
    put(con, pd.read_csv(C["characterized"], sep="\t"), "characterized_protein", ["source_acc"])
    put(con, pd.read_csv(C["publication"], sep="\t"), "publication", ["publication_id"])
    put(con, pd.read_csv(C["assertion_link"], sep="\t"), "assertion_publication", ["assertion_id", "publication_id"])
    # curator spot-check sign-off: decisions table + field corrections to the carried Tier-A tables
    import curation_v150 as cur
    put(con, pd.read_csv(C["spotcheck_decisions"], sep="\t"), "curator_spotcheck_decision", ["row_id"])
    corr = pd.read_csv(C["field_corrections"], sep="\t", dtype=str).fillna("")
    # corrections are written with UPDATE / ADD COLUMN so the carried v1.4 table definitions (PKs, FKs) are preserved
    ta = pd.read_sql("select rowid as _rid, * from tier_a_assertion", con)
    te = pd.read_sql("select rowid as _rid, * from tier_a_evidence", con)
    assert (ta.source_acc.values == te.source_acc.values).all() and (ta.assertion.values == te.supported_assertion.values).all()
    con.execute("ALTER TABLE tier_a_evidence ADD COLUMN assertion_id INTEGER")   # rows are 1:1, same order (asserted above)
    con.executemany("UPDATE tier_a_evidence SET assertion_id=? WHERE rowid=?", list(zip(ta.assertion_id.astype(int), te._rid)))
    te["assertion_id"] = ta.assertion_id.values
    for tbl, df0 in (("tier_a_assertion", ta), ("tier_a_evidence", te)):
        df1, n_c = cur.apply_field_corrections(df0, corr, tbl, {"source_acc": "source_acc", "assertion_id": "assertion_id"})
        for col in [c for c in df1.columns if c not in df0.columns]:
            con.execute(f'ALTER TABLE {tbl} ADD COLUMN "{col}" TEXT')
        changed = [c for c in df1.columns if c != "_rid" and (c not in df0.columns or
                   not df1[c].astype(object).where(df1[c].notna(), None).equals(df0[c].astype(object).where(df0[c].notna(), None)))]
        touched = df1[(df1.v150_corrected_fields.fillna("") != "") | (df1.get("v150_curation_note", pd.Series("", index=df1.index)).fillna("") != "")]
        for _, r in touched.iterrows():   # only curated rows are rewritten; all other rows keep their v1.4 values byte-for-byte
            vals = [None if (isinstance(r[c], float) and np.isnan(r[c])) or r[c] == "" else r[c] for c in changed]
            con.execute(f"UPDATE {tbl} SET " + ", ".join(f'"{c}"=?' for c in changed) + " WHERE rowid=?", vals + [int(r._rid)])
        print(f"{tbl}: {n_c} field corrections applied; columns touched: {changed}")
    fcd = pd.DataFrame([
        ("proton_pump", "light-driven outward H+ pump"), ("proton_pump_inward", "light-driven inward H+ pump (e.g. xenorhodopsins)"),
        ("anion_pump", "light-driven inward anion (Cl-) pump"), ("sodium_pump", "light-driven outward Na+ pump"),
        ("light_gated_channel", "light-gated ion channel (cation, anion or K+ selective)"),
        ("sensory", "sensory rhodopsin signalling via a transducer"), ("sensory_like", "curated rule: sensory-like lineage, no characterised member"),
        ("enzyme_rhodopsin", "rhodopsin fused to an enzymatic domain (cyclase, phosphodiesterase)"),
        ("photoreceptor_unassigned", "characterised photoreceptor with no detectable ion transport and no assigned signalling "
                                     "partner (new in v1.5.0; exp class photoreceptor_no_transport, e.g. the CryoR2 UV sensor)"),
        ("unresolved", "no function call (E5)")], columns=["func_class", "definition"])
    fcd["n_records"] = fcd.func_class.map(fe.func_class.value_counts()).fillna(0).astype(int)
    assert set(fe.func_class) <= set(fcd.func_class), set(fe.func_class) - set(fcd.func_class)
    put(con, fcd, "func_class_definition", ["func_class"])
    put(con, pd.read_csv(C["motif_benchmark_summary"], sep="\t"), "motif_benchmark")
    put(con, pd.read_csv(C["spectral_audit"], sep="\t"), "spectral_audit")

    # ---------- 7. structures / taxonomy ----------
    af = pd.read_csv(C["afdb"], sep="\t")
    put(con, af, "afdb_model", ["source_acc"])
    put(con, pd.read_csv(C["pocket_long"], sep="\t"), "retinal_pocket")
    put(con, pd.read_csv(C["pocket_summary"], sep="\t"), "retinal_pocket_summary", ["source_acc"])
    put(con, pd.read_csv(C["gtdb"], sep="\t"), "gtdb_taxonomy", ["source_acc"])

    # ---------- 8. validation ----------
    xp = pd.read_csv(C["ext_pos"], sep="\t").assign(is_positive=1)
    xn = pd.read_csv(C["ext_neg"], sep="\t").assign(is_positive=0)
    xs = pd.concat([xp, xn], ignore_index=True)
    xs["freeze_sha256"] = open(C["ext_freeze"]).read().split()[0]
    xpl = pd.read_csv(C["ext_placement"], sep="\t").drop_duplicates("ext_acc")
    xs = xs.merge(xpl[["ext_acc", "clade_id", "subclade_id", "clade_lwr", "clade_call_qc", "lwr_weighted_pendant"]]
                  .rename(columns={"clade_id": "mr_rt_003_clade_id", "subclade_id": "mr_rt_003_subclade_id",
                                   "clade_call_qc": "mr_rt_003_call"}), on="ext_acc", how="left")
    xsc = pd.read_csv(C["ext_scores"], sep="\t")[["source_acc", "membership_score", "gate_has_domain", "is_helio_primary"]]
    xs = xs.merge(xsc.rename(columns={"source_acc": "ext_acc", "membership_score": "membership_score_frozen_scorer"}),
                  on="ext_acc", how="left")
    put(con, xs, "external_validation", ["ext_acc"])
    for k, t in [("ext_metrics", "external_validation_metric"), ("ext_ops", "external_validation_operating_point"),
                 ("ext_strata", "external_validation_stratum"), ("hold_metrics", "holdout_metric"),
                 ("hold_ops", "holdout_operating_point")]:
        put(con, pd.read_csv(C[k], sep="\t"), t)

    # ---------- 9. Wilson recompute of legacy proportion CIs ----------
    hm = pd.read_sql("select * from legacy_holdout_metric_v14", con)
    rec = []
    for _, r in hm.iterrows():
        k = n = None
        base = str(r.metric).split("@")[0]
        if base in ("sensitivity", "recall") and pd.notna(r.tp): k, n = r.tp, r.tp + r.fn
        elif base == "specificity" and pd.notna(r.tn): k, n = r.tn, r.tn + r.fp
        elif base == "precision" and pd.notna(r.tp): k, n = r.tp, r.tp + r.fp
        lo, hi = wilson(k, n) if k is not None else (r.ci_lo, r.ci_hi)
        rec.append((lo, hi, "wilson" if k is not None else "as_released"))
    hm[["ci_lo", "ci_hi", "ci_method"]] = rec
    put(con, hm, "legacy_holdout_metric_v14")
    em = pd.read_sql("select * from legacy_external_validation_metric_v14", con)
    rec = []
    for _, r in em.iterrows():
        n = r.n_pos if r.metric in ("sensitivity", "recall") else r.n_neg if r.metric == "specificity" else None
        if n and pd.notna(r.value):
            lo, hi = wilson(round(r.value * n), n); rec.append((lo, hi, "wilson"))
        else:
            rec.append((r.ci_lo, r.ci_hi, r.ci_method))
    em[["ci_lo", "ci_hi", "ci_method"]] = rec
    put(con, em, "legacy_external_validation_metric_v14")

    # ---------- 10. views ----------
    V = {
        "v_master": """SELECT p.mrdb_acc, p.source_acc, p.protein_name, p.organism, p.organism_id, p.tax_domain, p.length,
                m.membership_status, m.alias_v14, m.boundary_subtype, m.membership_score, m.retinal_site_residue,
                f.func_class, f.evidence_level, rc.clade_id, rc.subclade_id, rc.source AS clade_source,
                pl.clade_lwr, pl.clade_call_qc AS placement_call, c.name AS clade_name,
                CASE WHEN COALESCE(rc.clade_id, '') = '' AND pl.clade_call = 'assigned'
                      AND pl.clade_call_qc = 'distant_assigned' AND COALESCE(pl.clade_id, '') NOT IN ('', 'outgroup_heliorhodopsin')
                     THEN pl.clade_id END AS tentative_clade_id,
                CASE WHEN COALESCE(rc.clade_id, '') = '' AND pl.clade_call = 'assigned'
                      AND pl.clade_call_qc = 'distant_assigned' AND COALESCE(pl.clade_id, '') NOT IN ('', 'outgroup_heliorhodopsin')
                     THEN tc.name END AS tentative_clade_name,
                g.gtdb_taxonomy, a.model_id AS afdb_model_id, a.global_plddt AS afdb_global_plddt
                FROM protein p JOIN membership m USING (source_acc)
                LEFT JOIN function_evidence f USING (source_acc)
                LEFT JOIN record_clade rc USING (source_acc)
                LEFT JOIN clade c ON c.clade_id = rc.clade_id
                LEFT JOIN (SELECT * FROM placement WHERE tree_id='MR_RT_003' AND is_current=1) pl USING (source_acc)
                LEFT JOIN clade tc ON tc.clade_id = pl.clade_id
                LEFT JOIN gtdb_taxonomy g USING (source_acc)
                LEFT JOIN (SELECT * FROM afdb_model WHERE status='ok') a USING (source_acc)""",
        "v_typeI_member": "SELECT * FROM v_master WHERE membership_status LIKE 'typeI_member%'",
        "v_typeI_candidate": "SELECT * FROM v_master WHERE membership_status LIKE 'typeI_candidate%'",
        "v_boundary_family": "SELECT * FROM v_master WHERE membership_status='boundary_family'",
        "v_heliorhodopsin": "SELECT * FROM v_master WHERE membership_status='heliorhodopsin'",
        # compatibility views (v1.4 names; deprecated, removed in v1.6)
        "v_typeI_core": "SELECT p.* FROM protein p JOIN membership m USING(source_acc) WHERE m.alias_v14 IN ('typeI_core','typeI_core_architecture_supported')",
        "v_typeI_candidates": "SELECT p.* FROM protein p JOIN membership m USING(source_acc) WHERE m.alias_v14 LIKE 'typeI_candidate%'",
        "v_typeI_active": "SELECT p.* FROM protein p JOIN membership m USING(source_acc) WHERE m.alias_v14 LIKE 'typeI_c%'",
        "v_rejected_or_decoy": "SELECT p.* FROM protein p JOIN membership m USING(source_acc) WHERE m.membership_status='decoy_or_rejected'",
    }
    for k, q in V.items():
        con.execute(f"CREATE VIEW {k} AS {q}")

    # ---------- 11. metadata + provenance ----------
    md = pd.read_sql("select * from release_metadata", con)
    md.insert(0, "release", "1.4.0")
    new = pd.DataFrame(C["release_metadata"].items(), columns=["key", "value"]).assign(release="1.5.0")
    put(con, pd.concat([new[["release", "key", "value"]], md.rename(columns={})], ignore_index=True), "release_metadata")
    bp = pd.read_sql("select * from build_provenance", con)
    for t, sdat, scr, alg, par, dep in prov + C.get("provenance_rows", []):
        bp.loc[len(bp)] = dict(table_name=t, source_data=sdat, script=scr, algorithm=alg, params=par, upstream_deps=dep,
                               release="1.5.0", built_at=now)
    put(con, bp, "build_provenance")
    con.commit()
    con.execute("VACUUM")
    con.close()
    print("built", out, env_out)


if __name__ == "__main__":
    main()
