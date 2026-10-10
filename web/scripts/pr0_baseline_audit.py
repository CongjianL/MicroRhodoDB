#!/usr/bin/env python3
"""PR-0 read-only baseline audit of the official MicroRhodoDB v1.6.0 SQLite.

Usage: python pr0_baseline_audit.py <repo_root> <out_dir>
Opens the DB with mode=ro; never writes to the repository.
Every metric is recorded together with the SQL that produced it.
"""
import hashlib, json, re, sqlite3, sys
from pathlib import Path

repo = Path(sys.argv[1]); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
DB = repo / "releases/v1.6.0/db/microrhododb_v1.6.0.sqlite"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
R = {"db": str(DB.relative_to(repo)), "db_sha256": hashlib.sha256(DB.read_bytes()).hexdigest()}
errors = {}

def q(sql, *a):
    return con.execute(sql, a).fetchall()

def metric(key, sql, expect=None):
    try:
        v = q(sql)
        v = v[0][0] if len(v) == 1 and len(v[0]) == 1 else [list(r) for r in v]
        R.setdefault("metrics", {})[key] = {"value": v, "sql": sql, "expected_plan_1_3": expect,
                                             "match": (None if expect is None else v == expect)}
    except Exception as e:
        errors[key] = f"{e} :: {sql}"

def cols(t):
    return [r[1] for r in q(f"PRAGMA table_info({t})")]

# ---------- 1.3 headline metrics ----------
metric("records", "SELECT COUNT(*) FROM v_master", 5466)
metric("counted", "SELECT COUNT(*) FROM v_counted", 5460)
metric("mrdb_accessions", "SELECT COUNT(*) FROM mrdb_accession", 5299)
metric("mrdb_accessions_in_map", "SELECT COUNT(DISTINCT mrdb_acc) FROM accession_map", 5299)
metric("members", "SELECT COUNT(*) FROM v_typeI_member", 3089)
metric("candidates", "SELECT COUNT(*) FROM v_typeI_candidate", 1379)
metric("boundary", "SELECT COUNT(*) FROM v_boundary_family", 509)
metric("helio", "SELECT COUNT(*) FROM v_heliorhodopsin", 386)
metric("engineered", "SELECT COUNT(*) FROM v_engineered", 6)
metric("membership_status_all", "SELECT membership_status, COUNT(*) FROM v_master GROUP BY 1 ORDER BY 2 DESC")
metric("membership_status_counted", "SELECT membership_status, COUNT(*) FROM v_counted GROUP BY 1 ORDER BY 2 DESC")
metric("decoy", "SELECT COUNT(*) FROM v_master WHERE membership_status LIKE '%decoy%'", 103)
metric("evidence_counted", "SELECT evidence_level, COUNT(*) FROM v_counted GROUP BY 1 ORDER BY 1")
metric("evidence_all", "SELECT evidence_level, COUNT(*) FROM v_master GROUP BY 1 ORDER BY 1")
metric("e1_total", "SELECT COUNT(*) FROM v_master WHERE evidence_level='E1'", 91)
metric("e1_counted", "SELECT COUNT(*) FROM v_counted WHERE evidence_level='E1'", 88)
metric("publications", "SELECT COUNT(*) FROM publication", 121)
metric("active_links", "SELECT COUNT(*) FROM assertion_publication WHERE is_active=1", 255)
metric("novel_watchlist", "SELECT COUNT(*) FROM novel_family_candidate", 181)
metric("func_class_counted", "SELECT func_class, COUNT(*) FROM v_counted GROUP BY 1 ORDER BY 2 DESC")
metric("tax_domain_counted", "SELECT tax_domain, COUNT(*) FROM v_counted GROUP BY 1 ORDER BY 2 DESC")
metric("is_engineered_counted", "SELECT is_engineered, counts_eligible, COUNT(*) FROM v_master GROUP BY 1,2")

# ---------- v_master columns ----------
R["v_master_columns"] = cols("v_master")
for t in ["assertion_publication", "publication", "novel_family_candidate", "mrdb_accession", "clade_tip",
          "clade_robustness", "foldseek_hit", "retinal_pocket_summary", "gtdb_taxonomy"]:
    try: R.setdefault("schemas", {})[t] = cols(t)
    except Exception as e: errors[f"schema_{t}"] = str(e)

# ---------- accession mapping ----------
metric("map_rows", "SELECT COUNT(*) FROM accession_map")
metric("map_current", "SELECT is_current, COUNT(*) FROM accession_map GROUP BY 1")
metric("map_multiplicity", "SELECT n, COUNT(*) FROM (SELECT mrdb_acc, COUNT(*) n FROM accession_map GROUP BY 1) GROUP BY n ORDER BY n")
metric("map_source_db", "SELECT source_database, COUNT(*) FROM accession_map GROUP BY 1")
metric("map_release_added", "SELECT release_added, COUNT(*) FROM accession_map GROUP BY 1")
metric("map_source_not_in_master", "SELECT COUNT(*) FROM accession_map WHERE source_acc NOT IN (SELECT source_acc FROM v_master)", 0)
metric("master_source_not_in_map", "SELECT COUNT(*) FROM v_master WHERE source_acc NOT IN (SELECT source_acc FROM accession_map)", 0)
metric("master_mrdb_mismatch", "SELECT COUNT(*) FROM v_master m JOIN accession_map a USING(source_acc) WHERE m.mrdb_acc<>a.mrdb_acc", 0)
metric("map_examples_multi", "SELECT mrdb_acc, group_concat(source_acc, ';') FROM accession_map GROUP BY 1 HAVING COUNT(*)>1 ORDER BY 1 LIMIT 10")
metric("mrdb_rep_flag", "SELECT (m.source_acc=a.representative_source_acc), COUNT(*) FROM v_master m JOIN mrdb_accession a USING(mrdb_acc) GROUP BY 1")
metric("exact_dup_nonnull", "SELECT COUNT(*) FROM v_master WHERE exact_duplicate_of IS NOT NULL AND exact_duplicate_of<>''")
metric("source_acc_unique_master", "SELECT COUNT(*)-COUNT(DISTINCT source_acc) FROM v_master", 0)

# ---------- PDB ----------
metric("protein_pdb_links", "SELECT COUNT(*) FROM protein_pdb")
metric("protein_pdb_distinct_pairs", "SELECT COUNT(*) FROM (SELECT DISTINCT source_acc, pdb_id FROM protein_pdb)")
metric("protein_pdb_distinct_ids", "SELECT COUNT(DISTINCT pdb_id) FROM protein_pdb")
metric("protein_pdb_distinct_acc", "SELECT COUNT(DISTINCT source_acc) FROM protein_pdb")
metric("protein_pdb_acc_in_master", "SELECT COUNT(DISTINCT source_acc) FROM protein_pdb WHERE source_acc IN (SELECT source_acc FROM v_master)")
metric("protein_pdb_acc_outside_master", "SELECT group_concat(DISTINCT source_acc) FROM protein_pdb WHERE source_acc NOT IN (SELECT source_acc FROM v_master)")
metric("pdb_ids_missing_meta", "SELECT COUNT(DISTINCT pdb_id) FROM protein_pdb WHERE pdb_id NOT IN (SELECT pdb_id FROM pdb_structure)")
metric("pdb_meta_unlinked", "SELECT COUNT(*) FROM pdb_structure WHERE pdb_id NOT IN (SELECT pdb_id FROM protein_pdb)")
metric("pdb_id_format_bad", "SELECT COUNT(*) FROM protein_pdb WHERE pdb_id NOT GLOB '[0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9]'")
metric("pdb_case", "SELECT SUM(pdb_id=upper(pdb_id)), SUM(pdb_id=lower(pdb_id)) FROM protein_pdb")
metric("pdb_methods", "SELECT method, COUNT(*) FROM pdb_structure GROUP BY 1 ORDER BY 2 DESC")
metric("pdb_has_retinal", "SELECT has_retinal, COUNT(*) FROM pdb_structure GROUP BY 1")
metric("pdb_resolution_null", "SELECT COUNT(*) FROM pdb_structure WHERE resolution IS NULL OR resolution=''")
metric("pdb_links_per_acc", "SELECT n, COUNT(*) FROM (SELECT source_acc, COUNT(DISTINCT pdb_id) n FROM protein_pdb GROUP BY 1) GROUP BY n ORDER BY n")
metric("pdb_shared_ids", "SELECT n, COUNT(*) FROM (SELECT pdb_id, COUNT(DISTINCT source_acc) n FROM protein_pdb GROUP BY 1) GROUP BY n ORDER BY n")
metric("structure_rows", "SELECT COUNT(*) FROM structure")
metric("structure_has_exp", "SELECT has_experimental_structure, COUNT(*) FROM structure GROUP BY 1")
metric("structure_n_pdb_mismatch",
       "SELECT COUNT(*) FROM structure s LEFT JOIN (SELECT source_acc, COUNT(DISTINCT pdb_id) n FROM protein_pdb GROUP BY 1) p USING(source_acc) "
       "WHERE COALESCE(s.n_pdb_structures,0)<>COALESCE(p.n,0)")
metric("structure_n_pdb_mismatch_examples",
       "SELECT s.source_acc, s.n_pdb_structures, p.n FROM structure s LEFT JOIN (SELECT source_acc, COUNT(DISTINCT pdb_id) n FROM protein_pdb GROUP BY 1) p USING(source_acc) "
       "WHERE COALESCE(s.n_pdb_structures,0)<>COALESCE(p.n,0) LIMIT 10")
metric("rep_pdb_not_linked",
       "SELECT COUNT(*) FROM structure s WHERE rep_pdb_id IS NOT NULL AND rep_pdb_id<>'' AND NOT EXISTS "
       "(SELECT 1 FROM protein_pdb p WHERE p.source_acc=s.source_acc AND upper(p.pdb_id)=upper(s.rep_pdb_id))", 0)
metric("highres_pdb_not_linked",
       "SELECT COUNT(*) FROM structure s WHERE highest_res_pdb_id IS NOT NULL AND highest_res_pdb_id<>'' AND NOT EXISTS "
       "(SELECT 1 FROM protein_pdb p WHERE p.source_acc=s.source_acc AND upper(p.pdb_id)=upper(s.highest_res_pdb_id))", 0)
metric("pdb_acc_without_structure_row", "SELECT COUNT(DISTINCT source_acc) FROM protein_pdb WHERE source_acc NOT IN (SELECT source_acc FROM structure)")
metric("master_without_structure_row", "SELECT COUNT(*) FROM v_master WHERE source_acc NOT IN (SELECT source_acc FROM structure)")
metric("master_without_structure_by_status", "SELECT membership_status, COUNT(*) FROM v_master WHERE source_acc NOT IN (SELECT source_acc FROM structure) GROUP BY 1")
metric("pdb_acc_by_status", "SELECT membership_status, COUNT(DISTINCT p.source_acc) FROM protein_pdb p JOIN v_master m USING(source_acc) GROUP BY 1")
metric("pdb_links_P02945_B0R5N9", "SELECT source_acc, COUNT(*) FROM protein_pdb WHERE source_acc IN ('P02945','B0R5N9') GROUP BY 1")
metric("pdb_links_via_mrdb_MRDB000001",
       "SELECT COUNT(DISTINCT p.pdb_id) FROM protein_pdb p JOIN accession_map a USING(source_acc) WHERE a.mrdb_acc='MRDB000001'")
metric("pdb_links_master_vs_mrdb_union",
       "SELECT COUNT(*) FROM (SELECT a.mrdb_acc FROM protein_pdb p JOIN accession_map a USING(source_acc) GROUP BY 1)")
metric("structure_arch", "SELECT arch_primary, COUNT(*) FROM structure GROUP BY 1 ORDER BY 2 DESC")

# ---------- AFDB ----------
metric("afdb_rows", "SELECT COUNT(*) FROM afdb_model")
metric("afdb_status", "SELECT status, COUNT(*) FROM afdb_model GROUP BY 1")
metric("afdb_seq_match", "SELECT seq_match, COUNT(*) FROM afdb_model GROUP BY 1")
metric("afdb_version", "SELECT version, COUNT(*) FROM afdb_model GROUP BY 1")
metric("afdb_url_examples", "SELECT model_id, model_url FROM afdb_model WHERE model_url IS NOT NULL AND model_url<>'' LIMIT 3")
metric("afdb_url_nonnull", "SELECT COUNT(*) FROM afdb_model WHERE model_url IS NOT NULL AND model_url<>''")
metric("afdb_model_id_nonnull", "SELECT COUNT(*) FROM afdb_model WHERE model_id IS NOT NULL AND model_id<>''")
metric("afdb_only_no_pdb",
       "SELECT COUNT(*) FROM afdb_model a WHERE model_id IS NOT NULL AND model_id<>'' AND source_acc NOT IN (SELECT source_acc FROM protein_pdb)")
metric("no_pdb_no_afdb",
       "SELECT COUNT(*) FROM v_master m WHERE source_acc NOT IN (SELECT source_acc FROM protein_pdb) AND source_acc NOT IN "
       "(SELECT source_acc FROM afdb_model WHERE model_id IS NOT NULL AND model_id<>'')")
metric("master_afdb_disagree",
       "SELECT COUNT(*) FROM v_master m JOIN afdb_model a USING(source_acc) WHERE COALESCE(m.afdb_model_id,'')<>COALESCE(a.model_id,'')")
metric("predicted_structure", "SELECT * FROM predicted_structure")

# ---------- tree / clades ----------
metric("reference_tree", "SELECT tree_id, n_tips, method, model, treefile_md5, unrooted, status FROM reference_tree")
metric("tree_node_kinds", "SELECT tree_id, kind, COUNT(*) FROM tree_node GROUP BY 1,2")
metric("tree_edges", "SELECT tree_id, COUNT(*) FROM tree_edge GROUP BY 1")
metric("clade_levels", "SELECT tree_id, scheme, level, COUNT(*) FROM clade GROUP BY 1,2,3")
metric("clade_level1", "SELECT clade_id, name, n_tips, ufboot, sh_alrt, consensus_status, n_records_assigned, min_cross_replicate_jaccard FROM clade WHERE level=1 ORDER BY clade_id")
metric("clade_tip_by_clade_level", "SELECT c.level, COUNT(*), COUNT(DISTINCT ct.rowid) FROM clade_tip ct JOIN clade c USING(clade_id) GROUP BY 1")
metric("placement_current_track", "SELECT is_current, track, tree_id, COUNT(*) FROM placement GROUP BY 1,2,3")
metric("placement_clade_call_current", "SELECT clade_call, COUNT(*) FROM placement WHERE is_current=1 GROUP BY 1 ORDER BY 2 DESC")
metric("placement_current_per_acc", "SELECT n, COUNT(*) FROM (SELECT source_acc, COUNT(*) n FROM placement WHERE is_current=1 GROUP BY 1) GROUP BY 1")
metric("record_clade_source", "SELECT source, COUNT(*) FROM record_clade GROUP BY 1")
metric("record_clade_call", "SELECT clade_call, COUNT(*) FROM record_clade GROUP BY 1 ORDER BY 2 DESC")
metric("master_without_record_clade_by_status",
       "SELECT membership_status, COUNT(*) FROM v_master WHERE source_acc NOT IN (SELECT source_acc FROM record_clade) GROUP BY 1")
metric("master_without_record_clade_list",
       "SELECT source_acc, membership_status FROM v_master WHERE source_acc NOT IN (SELECT source_acc FROM record_clade)")
metric("master_clade_id_counted", "SELECT clade_id, COUNT(*) FROM v_counted GROUP BY 1 ORDER BY 1")
metric("master_tentative_nonblank", "SELECT COUNT(*) FROM v_master WHERE tentative_clade_id IS NOT NULL AND tentative_clade_id<>''")
metric("MR_CLD3_017", "SELECT clade_id, name, level, consensus_status, n_records_assigned, n_E1, min_cross_replicate_jaccard FROM clade WHERE clade_id='MR_CLD3_017'")
metric("clade_robustness_cols", "SELECT * FROM clade_robustness LIMIT 2")

# ---------- publications ----------
metric("active_link_distinct_acc", "SELECT COUNT(DISTINCT source_acc) FROM assertion_publication WHERE is_active=1")
metric("all_link_distinct_acc", "SELECT COUNT(DISTINCT source_acc) FROM assertion_publication")
metric("active_link_roles", "SELECT link_role, counts_as_support, COUNT(*) FROM assertion_publication WHERE is_active=1 GROUP BY 1,2")
metric("active_link_acc_not_in_master",
       "SELECT COUNT(DISTINCT source_acc) FROM assertion_publication WHERE is_active=1 AND source_acc NOT IN (SELECT source_acc FROM v_master)")
metric("link_verdicts", "SELECT is_active, verdict, COUNT(*) FROM assertion_publication GROUP BY 1,2")

# ---------- watchlist ----------
nfc = cols("novel_family_candidate")
acc_col = next((c for c in nfc if "acc" in c.lower()), nfc[0])
R["watchlist_acc_col"] = acc_col
metric("watchlist_in_corpus", f"SELECT COUNT(*) FROM novel_family_candidate WHERE {acc_col} IN (SELECT source_acc FROM v_master)", 0)

# ---------- fixtures ----------
FIX = ["P02945", "B0R5N9", "A0A1I3DJQ0", "L1K1K8", "A0A3G1I4H9", "A0ABF7PQ82", "A0ABF7PQA2", "A0ABF7PQ84", "A0AAP2RB57"]
fx = {}
for a in FIX:
    r = q("SELECT mrdb_acc, source_acc, protein_name, membership_status, evidence_level, func_class, clade_id, "
          "tentative_clade_id, is_engineered, counts_eligible, afdb_model_id FROM v_master WHERE source_acc=?", a)
    pdb = [x[0] for x in q("SELECT DISTINCT pdb_id FROM protein_pdb WHERE source_acc=? ORDER BY 1", a)]
    fx[a] = {"master": r[0] if r else None, "n_pdb": len(pdb), "pdb_ids": pdb[:12],
             "in_map": [list(x) for x in q("SELECT mrdb_acc FROM accession_map WHERE source_acc=?", a)]}
# DB-selected structure fixtures
fx["_multi_pdb_top"] = [list(x) for x in q("SELECT source_acc, COUNT(DISTINCT pdb_id) n FROM protein_pdb GROUP BY 1 ORDER BY n DESC, source_acc LIMIT 5")]
fx["_multi_pdb_counted_member"] = [list(x) for x in q(
    "SELECT p.source_acc, COUNT(DISTINCT pdb_id) n FROM protein_pdb p JOIN v_counted m USING(source_acc) "
    "WHERE m.membership_status LIKE '%member%' GROUP BY 1 HAVING n BETWEEN 2 AND 6 ORDER BY 1 LIMIT 3")]
fx["_afdb_only"] = [list(x) for x in q(
    "SELECT m.source_acc, m.mrdb_acc, a.model_id, a.global_plddt FROM v_counted m JOIN afdb_model a USING(source_acc) "
    "WHERE a.model_id<>'' AND m.source_acc NOT IN (SELECT source_acc FROM protein_pdb) ORDER BY a.global_plddt DESC LIMIT 3")]
fx["_no_pdb_no_afdb"] = [list(x) for x in q(
    "SELECT source_acc, mrdb_acc, membership_status FROM v_master WHERE source_acc NOT IN (SELECT source_acc FROM protein_pdb) "
    "AND source_acc NOT IN (SELECT source_acc FROM afdb_model WHERE model_id IS NOT NULL AND model_id<>'') ORDER BY 1 LIMIT 3")]
R["fixtures"] = fx

# ---------- refpkg tree ----------
rp = repo / "refpkg/MR_RT_003"
tf = rp / "tree/MR_RT_003.rooted.treefile"
nwk = tf.read_text().strip()
tips = re.findall(r"[(,]\s*([^():,;]+?)\s*:", nwk)
R["refpkg_tree"] = {"file": str(tf.relative_to(repo)), "md5": hashlib.md5(tf.read_bytes()).hexdigest(),
                    "sha256": hashlib.sha256(tf.read_bytes()).hexdigest(), "bytes": tf.stat().st_size,
                    "n_tips_regex": len(tips), "n_unique_tips": len(set(tips)), "tip_examples": tips[:5],
                    "internal_label_examples": re.findall(r"\)([^():,;]+):", nwk)[:8]}
try:
    tsv = (rp / "tips.tsv").read_text().splitlines()
    hdr = tsv[0].split("\t"); first = [l.split("\t")[0] for l in tsv[1:] if l.strip()]
    R["refpkg_tree"]["tips_tsv_header"] = hdr; R["refpkg_tree"]["tips_tsv_n"] = len(first)
    R["refpkg_tree"]["tips_tsv_col0_matches_tree"] = len(set(first) & set(tips))
    dbtips = {x[0] for x in q("SELECT label FROM tree_node WHERE tree_id='MR_RT_003' AND kind='tip'")}
    R["refpkg_tree"]["db_tip_labels_n"] = len(dbtips); R["refpkg_tree"]["db_tip_labels_match_tree"] = len(dbtips & set(tips))
except Exception as e:
    errors["refpkg_tips"] = str(e)
cl = (rp / "clades/MR_CLD3_clades.tsv").read_text().splitlines()
R["refpkg_clades"] = {"header": cl[0].split("\t"), "n_rows": len(cl) - 1}
sc = (rp / "clades/MR_CLD3_subclades.tsv").read_text().splitlines()
R["refpkg_subclades"] = {"header": sc[0].split("\t"), "n_rows": len(sc) - 1}
ct = (rp / "clades/MR_CLD3_tips.tsv").read_text().splitlines()
R["refpkg_clade_tips"] = {"header": ct[0].split("\t"), "n_rows": len(ct) - 1}

dbsub = {r[0] for r in q("SELECT clade_id FROM clade WHERE level=2")}
rpsub = {l.split("\t")[0] for l in sc[1:]}
R["refpkg_subclades"].update({"refpkg_only": sorted(rpsub - dbsub), "db_only": sorted(dbsub - rpsub)})
tips_rows = [l.split("\t") for l in tsv[1:] if l.strip()]
outg = {t[0] for t in tips_rows if t[1].startswith("outgroup")}
corpus = {r[0] for r in q("SELECT source_acc FROM v_master")}
no_rc = {r[0] for r in q("SELECT source_acc FROM v_master WHERE source_acc NOT IN (SELECT source_acc FROM record_clade)")}
dbtip_acc = {r[0] for r in q("SELECT source_acc FROM tree_node WHERE tree_id='MR_RT_003' AND kind='tip'")}
R["tree_reconciliation"] = {
    "tip_roles": {k: sum(1 for t in tips_rows if t[1] == k) for k in sorted({t[1] for t in tips_rows})},
    "tips_not_in_corpus": sorted(t[0] for t in tips_rows if t[0] not in corpus),
    "outgroup_tips_equal_records_without_record_clade": outg == no_rc,
    "db_tree_node_tip_source_acc_match_treefile": len(dbtip_acc & set(tips)),
    "clade_tip_by_clade": [list(r) for r in q("SELECT clade_id, subclade_id IS NULL, COUNT(*) FROM clade_tip GROUP BY 1,2 ORDER BY 1")],
    "backbone_unassigned_subclades": [list(r) for r in q("SELECT subclade_id, COUNT(*) FROM clade_tip WHERE clade_id='backbone_unassigned' GROUP BY 1")],
    "reference_tree_md5_matches_file": {f.name: hashlib.md5(f.read_bytes()).hexdigest() for f in (rp / "tree").glob("*.treefile")},
}
# legacy data.js fidelity
try:
    t = (repo / "site/data.js").read_text(); M = json.loads(t[t.index("{"):t.rindex("}") + 1])
    lc = M["columns"]; vm = R["v_master_columns"]; common = [c for c in lc if c in vm]
    cur = q(f"SELECT {','.join(common)} FROM v_master ORDER BY mrdb_acc, source_acc"); mism = {}
    for lr, dr in zip(M["rows"], cur):
        d = dict(zip(lc, lr))
        for c, v in zip(common, dr):
            a = d[c]
            if a in ("", None) and v in ("", None): continue
            if isinstance(v, float) and isinstance(a, (int, float)) and abs(a - v) < 0.051: continue
            if str(a) != str(v): mism.setdefault(c, 0); mism[c] += 1
    R["legacy_data_js"] = {"sha256": hashlib.sha256(t.encode()).hexdigest(), "n_rows": len(M["rows"]),
                           "n_columns": len(lc), "common_with_v_master": len(common),
                           "legacy_only_columns": [c for c in lc if c not in vm], "mismatched_cells_by_column": mism,
                           "pubs_accessions": len(M["pubs"]), "pubs_rows": sum(len(v) for v in M["pubs"].values()),
                           "has_pdb_fields": any("pdb" in c.lower() for c in lc), "meta_keys": list(M["meta"])}
except Exception as e:
    errors["legacy_data_js"] = str(e)

R["errors"] = errors
(out / "pr0_db_audit.json").write_text(json.dumps(R, indent=1, default=str))
print(json.dumps({k: v["value"] for k, v in R.get("metrics", {}).items()}, default=str)[:200])
print("errors:", json.dumps(errors, indent=1))
