#!/usr/bin/env python3
"""Independent re-derivation and verification of the PR-7c.2 habitat sidecar.

Written from WEB_DATA_CONTRACT.md section 16, habitat.schema.json, contract.json and
habitat_field_dictionary.md only (no code from tools/habitat_export/build.py or tests).
Read-only with respect to the repository and the sidecar under test.

Usage: python independent_rederive.py [--repo R] [--export E] [--out OUT_JSON]
"""
import argparse
import collections
import csv
import hashlib
import json
import os
import re
import sys
from urllib.parse import urlparse

csv.field_size_limit(sys.maxsize)

GROUPS = {
    "physical": ["env_broad_scale", "env_local_scale", "env_medium", "isolation_source",
                 "habitat_nonstandard", "literature_isolate", "literature_rejected"],
    "host": ["host", "host_detail"],
    "collection": ["country", "lat_lon", "lat", "lon", "collection_date", "depth",
                   "sample_material", "environmental_sample", "metagenome_source"],
    "organism_context": ["organism_context"],
}
ROLE2GROUP = {r: g for g, rs in GROUPS.items() for r in rs}
GRADES = ["DIRECT_SAMPLE", "VERIFIED_ISOLATE", "ORGANISM_CONTEXT_ONLY", "AMBIGUOUS",
          "NOT_REPORTED", "LOOKUP_FAILED", "NOT_SEARCHED"]
HOST_STATUSES = ["REPORTED", "AMBIGUOUS", "NOT_REPORTED", "LOOKUP_FAILED", "NOT_SEARCHED"]
AMB_CLASSES = ["FORMATTING_ONLY", "NESTED_WORDING", "DISTINCT_SAME_SAMPLE",
               "DISTINCT_ACROSS_SAMPLES", "LITERATURE_VS_DATABASE"]
NR_SCOPES = ["database_only_literature_not_reviewed", "database_only_literature_inaccessible",
             "database_and_literature"]
LIT_STATUSES = ["NOT_SEARCHED", "ORGANISM_CONTEXT", "ISOLATE_EVIDENCE", "LOOKUP_FAILED", "NOT_REPORTED"]
ALLOWED_HOSTS = {"www.ebi.ac.uk", "www.ncbi.nlm.nih.gov", "pubmed.ncbi.nlm.nih.gov",
                 "pmc.ncbi.nlm.nih.gov", "eutils.ncbi.nlm.nih.gov"}
MIXS_ENV = {"env_broad_scale", "env_local_scale", "env_medium"}
ENVO_RE = re.compile(r"ENVO[:_ ]?(\d{7,8})")
ENVO_RE_I = re.compile(r"ENVO[:_ ]?(\d{7,8})", re.I)
BARE_DIGITS = re.compile(r"^\d{5,8}$")
INPUTS = ["docs/website/pr7c1/habitat_record_availability.tsv",
          "docs/website/pr7c1/habitat_evidence.tsv",
          "docs/website/pr7c1/habitat_coverage_summary.tsv",
          "docs/website/pr7c1/habitat_retrieval_manifest.json",
          "docs/website/pr7c1/literature/literature_evidence.json"]


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def nz(s):
    """empty string -> None"""
    return None if s is None or s == "" else s


def split_semi(s):
    return [x for x in s.split(";")] if s else []


class Check:
    def __init__(self, name):
        self.name = name
        self.counts = collections.Counter()
        self.errors = collections.Counter()
        self.examples = collections.defaultdict(list)
        self.notes = []

    def err(self, kind, ex):
        self.errors[kind] += 1
        if len(self.examples[kind]) < 5:
            self.examples[kind].append(ex)

    def result(self):
        return {"status": "PASS" if not self.errors else "FAIL",
                "counts": dict(self.counts), "errors": dict(self.errors),
                "examples": {k: v for k, v in self.examples.items()}, "notes": self.notes}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--export", default="web/public/data/v1.6.0")
    ap.add_argument("--out", default="independent_checks.json")
    a = ap.parse_args()
    P = os.path.join(a.repo, "docs/website/pr7c1")
    HAB = os.path.join(a.export, "habitat")

    # ---------------- load inputs ----------------
    # TSVs are Python csv "excel-tab" dialect (fields containing '"' are quoted with doubled quotes)
    recs = list(csv.DictReader(open(os.path.join(P, "habitat_record_availability.tsv"), newline=""),
                               delimiter="\t"))
    rec = {r["source_acc"]: r for r in recs}
    ev = list(csv.DictReader(open(os.path.join(P, "habitat_evidence.tsv"), newline=""),
                             delimiter="\t"))
    cov = list(csv.DictReader(open(os.path.join(P, "habitat_coverage_summary.tsv"), newline=""),
                              delimiter="\t"))
    lit = json.load(open(os.path.join(P, "literature/literature_evidence.json")))
    acc = json.load(open(os.path.join(a.export, "accessions.json")))
    by_mrdb, by_source = acc["by_mrdb"], acc["by_source"]
    contract = json.load(open(os.path.join(a.repo, "tools/habitat_export/contract.json")))

    # ---------------- load sidecar ----------------
    rec_dir = os.path.join(HAB, "records")
    files = sorted(os.listdir(rec_dir))
    side = {}
    for f in files:
        side[f[:-5]] = json.load(open(os.path.join(rec_dir, f)))
    summary = json.load(open(os.path.join(HAB, "summary.json")))
    manifest = json.load(open(os.path.join(HAB, "manifest.json")))

    side_src = {}  # source_acc -> (mrdb, index, source dict)
    dup_src = []
    for m, d in side.items():
        for i, s in enumerate(d["sources"]):
            if s["source_acc"] in side_src:
                dup_src.append(s["source_acc"])
            side_src[s["source_acc"]] = (m, i, s)
    side_items = {}  # evidence_id -> list of (source_acc, group, item)
    for sa, (m, i, s) in side_src.items():
        for g, its in s["items"].items():
            for it in its:
                side_items.setdefault(it["evidence_id"], []).append((sa, g, it))

    results = {}

    # ======== Check 1: file set ========
    c = Check("1_file_set")
    c.counts["mrdb_in_accessions"] = len(by_mrdb)
    c.counts["record_files"] = len(files)
    c.counts["source_records_in_table"] = len(rec)
    c.counts["source_entries_in_sidecar"] = sum(len(d["sources"]) for d in side.values())
    for m in set(by_mrdb) - set(side):
        c.err("missing_file", m)
    for m in set(side) - set(by_mrdb):
        c.err("extra_file", m)
    for sa in dup_src:
        c.err("duplicate_source", sa)
    for sa in set(rec) - set(side_src):
        c.err("source_missing", sa)
    for sa in set(side_src) - set(rec):
        c.err("source_not_in_table", sa)
    n_multi = n_differ = 0
    for m, d in side.items():
        info = by_mrdb.get(m)
        if info is None:
            continue
        exp_sources = sorted(sa for sa, mm in by_source.items() if mm == m)
        got = [s["source_acc"] for s in d["sources"]]
        if sorted(got) != exp_sources:
            c.err("source_set_mismatch", {"mrdb": m, "expected": exp_sources, "got": got})
        tab_sources = sorted(sa for sa, r in rec.items() if r["mrdb_acc"] == m)
        if tab_sources != exp_sources:
            c.err("table_vs_accessions_mrdb_mismatch", m)
        if got and got[0] != info["representative_source_acc"]:
            c.err("representative_not_first", {"mrdb": m, "rep": info["representative_source_acc"], "first": got[0]})
        for s in d["sources"]:
            if s["mrdb_acc"] != m:
                c.err("source_mrdb_acc_field", s["source_acc"])
            if s["is_mrdb_representative"] != (s["source_acc"] == info["representative_source_acc"]):
                c.err("is_mrdb_representative", s["source_acc"])
        if d.get("mrdb_acc") != m:
            c.err("file_mrdb_acc", m)
        if d["n_source_records"] != len(exp_sources):
            c.err("n_source_records", m)
        grades = {rec[sa]["primary_grade"] for sa in exp_sources if sa in rec}
        differ = len(grades) > 1
        if d["source_grades_differ"] != differ:
            c.err("source_grades_differ", {"mrdb": m, "grades": sorted(grades), "got": d["source_grades_differ"]})
        if len(exp_sources) > 1:
            n_multi += 1
            n_differ += differ
        if info.get("sources") and got != info["sources"]:
            c.counts["order_differs_from_accessions_sources_list"] += 1
    c.counts["multi_source_mrdb"] = n_multi
    c.counts["multi_source_grades_differ"] = n_differ
    results[c.name] = c.result()

    # ======== Check 2: per source record ========
    c = Check("2_per_source")
    lit_axis = {"database_only_literature_not_reviewed": "not_reviewed",
                "database_only_literature_inaccessible": "inaccessible",
                "database_and_literature": "reviewed_not_reported"}
    for sa, r in rec.items():
        if sa not in side_src:
            continue
        s = side_src[sa][2]
        c.counts["checked"] += 1
        pairs = [("grade", "primary_grade"), ("host_association_status", "host_association_status"),
                 ("ambiguity_class", "ambiguity_class"), ("host_ambiguity_class", "host_ambiguity_class"),
                 ("literature_status", "literature_status"), ("not_reported_scope", "not_reported_scope"),
                 ("db_chain_status", "db_chain_status"), ("db_habitat_status", "db_habitat_status")]
        for k, col in pairs:
            if s[k] != nz(r[col]):
                c.err("field:" + k, {"source": sa, "table": r[col], "sidecar": s[k]})
        if set(s["flags"]) != set(split_semi(r["flags"])) or len(s["flags"]) != len(set(s["flags"])):
            c.err("flags", {"source": sa, "table": r["flags"], "sidecar": s["flags"]})
        hu = r["has_usable_habitat"] == "1"
        if s["has_usable_physical_habitat"] != hu:
            c.err("has_usable_physical_habitat", sa)
        if hu != (r["primary_grade"] in ("DIRECT_SAMPLE", "VERIFIED_ISOLATE")):
            c.err("table_has_usable_vs_grade", sa)
        if s["has_usable_physical_habitat"] != (s["grade"] in ("DIRECT_SAMPLE", "VERIFIED_ISOLATE")):
            c.err("sidecar_has_usable_vs_grade", sa)
        if s["has_host_association"] != (r["has_host_association"] == "1"):
            c.err("has_host_association", sa)
        nolink = r["db_chain_status"] == "NO_LINK"
        if (s["sample_link"] == "none") != nolink:
            c.err("sample_link", {"source": sa, "chain": r["db_chain_status"], "sample_link": s["sample_link"]})
        c.counts["sample_link:" + str(s["sample_link"])] += 1
        if r["primary_grade"] == "NOT_REPORTED":
            exp = {"database": "no_traceable_sample_link" if nolink else "not_reported_in_linked_sample_records",
                   "literature": lit_axis.get(r["not_reported_scope"], "UNMAPPED:" + r["not_reported_scope"])}
            if s["missingness"] != exp:
                c.err("missingness", {"source": sa, "expected": exp, "got": s["missingness"]})
            c.counts["missingness_present"] += 1
            if nolink:
                c.counts["missingness_no_traceable_sample_link"] += 1
        elif s["missingness"] is not None:
            c.err("missingness_not_null_for_non_NR", {"source": sa, "grade": r["primary_grade"], "got": s["missingness"]})
        # extra: record_evidence_ids, accessions, linkage
        if s["record_evidence_ids"] != split_semi(r["evidence_ids"]):
            if sorted(s["record_evidence_ids"]) == sorted(split_semi(r["evidence_ids"])):
                c.counts["record_evidence_ids_order_only"] += 1
            else:
                c.err("record_evidence_ids", sa)
        accmap = {"assemblies": "assemblies", "bioprojects": "bioprojects", "biosamples": "biosamples",
                  "embl_protein_ids": "embl_protein_ids", "insdc": "insdc_accessions", "proteomes": "proteomes"}
        for k, col in accmap.items():
            if sorted(s["accessions"][k]) != sorted(set(split_semi(r[col]))):
                c.err("accessions:" + k, {"source": sa, "table": r[col], "sidecar": s["accessions"][k]})
        if s["linkage"]["sample_type"] != nz(r["sample_type"]):
            c.err("linkage.sample_type", sa)
        if s["linkage"]["mapping_confidence"] != nz(r["mapping_confidence"]):
            c.err("linkage.mapping_confidence", sa)
        if s["linkage"]["route"] != nz(r["linkage_route"]):
            c.err("linkage.route", {"source": sa, "table": r["linkage_route"], "sidecar": s["linkage"]["route"]})
        if s["linkage"]["molecule_types"] != split_semi(r["molecule_types"]):
            c.err("linkage.molecule_types", sa)
    results[c.name] = c.result()

    # ======== Check 3: items ========
    c = Check("3_items")
    ev_ids = collections.Counter(e["evidence_id"] for e in ev)
    c.counts["evidence_rows"] = len(ev)
    c.counts["duplicate_evidence_ids_in_tsv"] = sum(1 for v in ev_ids.values() if v > 1)
    if c.counts["duplicate_evidence_ids_in_tsv"]:
        c.err("duplicate_evidence_ids_in_tsv", c.counts["duplicate_evidence_ids_in_tsv"])
    exp_display = 0
    ev_by_id = {}
    for e in ev:
        ev_by_id[e["evidence_id"]] = e
        role = e["role"]
        g = ROLE2GROUP.get(role)
        hits = side_items.get(e["evidence_id"], [])
        if g is None:
            c.counts["non_display_rows"] += 1
            if hits:
                c.err("non_display_role_exported", {"id": e["evidence_id"], "role": role})
            continue
        exp_display += 1
        if len(hits) != 1:
            c.err("item_count_not_1", {"id": e["evidence_id"], "n": len(hits)})
            continue
        sa, grp, it = hits[0]
        if sa != e["source_acc"]:
            c.err("wrong_source", {"id": e["evidence_id"], "expected": e["source_acc"], "got": sa})
        if grp != g:
            c.err("wrong_group", {"id": e["evidence_id"], "role": role, "group": grp})
        exp_item = {
            "evidence_id": e["evidence_id"], "evidence_source": e["evidence_source"],
            "entity_accession": e["entity_accession"], "field": e["field_original"], "role": role,
            "value_status": e["value_status"], "value": nz(e["value_original"]),
            "envo_ids": split_semi(e["envo_ids"]), "browser_url": e["browser_url"],
            "source_url": nz(e["source_url"]), "linkage_route": e["linkage_route"],
            "mapping_confidence": nz(e["mapping_confidence"]),
            "link_index": int(e["link_index"]) if e["link_index"] != "" else None,
        }
        for k, v in exp_item.items():
            if it.get(k) != v:
                c.err("field:" + k, {"id": e["evidence_id"], "expected": v, "got": it.get(k)})
        if e["value_original"] == "":
            c.counts["empty_value_rows_exported_as_null"] += 1
        if isinstance(it.get("value"), str) and it["value"] == "":
            c.err("empty_string_value_exported", e["evidence_id"])
        if (e["evidence_source"] == "literature") != (it["literature"] is not None):
            c.err("literature_block_presence", e["evidence_id"])
    side_total = sum(len(v) for v in side_items.values())
    for eid in set(side_items) - set(ev_by_id):
        c.err("item_not_in_tsv", eid)
    c.counts["expected_display_items"] = exp_display
    c.counts["sidecar_items"] = side_total
    c.counts["manifest_display_items"] = manifest["counts"]["display_items"]
    if not (exp_display == side_total == manifest["counts"]["display_items"] == 59086):
        c.err("display_item_total", {"expected": exp_display, "sidecar": side_total,
                                     "manifest": manifest["counts"]["display_items"]})
    pg = collections.Counter(g for v in side_items.values() for (_, g, _) in v)
    c.notes.append({"items_per_group": dict(pg)})
    results[c.name] = c.result()

    # ======== Check 4: evidence IDs ========
    c = Check("4_evidence_ids")
    for e in ev:
        if e["evidence_id"].startswith("HE"):
            key = "|".join([e["source_acc"], e["evidence_source"], e["entity_accession"], e["link_index"],
                            e["field_original"], e["value_original"]])
            h = "HE" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
            c.counts["HE_recomputed"] += 1
            if h != e["evidence_id"]:
                c.err("HE_mismatch", {"id": e["evidence_id"], "recomputed": h})
    hl_tsv = {e["evidence_id"]: e for e in ev if e["evidence_id"].startswith("HL")}
    hl_json = {}
    for sa, v in lit.items():
        for x in v["items"]:
            key = "|".join(str(x.get(k)) for k in ("pmid", "doi", "quote", "scope")) + sa
            h = "HL" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
            c.counts["HL_recomputed"] += 1
            if h in hl_json:
                c.err("HL_collision", h)
            hl_json[h] = (sa, x)
            if x.get("doi") is None:
                c.counts["HL_with_null_doi(None rule)"] += 1
    for h in set(hl_json) - set(hl_tsv):
        c.err("HL_json_not_in_tsv", h)
    for h in set(hl_tsv) - set(hl_json):
        c.err("HL_tsv_not_recomputable", h)
    c.counts["HL_in_tsv"] = len(hl_tsv)
    c.counts["total_recomputed"] = c.counts["HE_recomputed"] + c.counts["HL_recomputed"]
    c.counts["manifest_recomputed"] = manifest["evidence_id_rules"]["recomputed"]
    if c.counts["manifest_recomputed"] != c.counts["total_recomputed"]:
        c.err("manifest_recomputed_count", c.counts["manifest_recomputed"])
    for eid in side_items:
        if eid.startswith("HL") and eid not in hl_json:
            c.err("sidecar_HL_not_recomputable", eid)
    results[c.name] = c.result()

    # ======== Check 5: quarantine ========
    c = Check("5_quarantine")
    exp_q = {}
    case_diff = []
    for e in ev:
        g = ROLE2GROUP.get(e["role"])
        if g != "physical" or e["evidence_source"] == "literature":
            continue
        v = e["value_original"]
        envo = set(split_semi(e["envo_ids"]))
        ids = {"ENVO:" + d.zfill(8) for d in ENVO_RE.findall(v)}
        ids_i = {"ENVO:" + d.zfill(8) for d in ENVO_RE_I.findall(v)}
        if ids != ids_i:
            case_diff.append(e["evidence_id"])
        q = None
        if ids - envo:
            q = "envo_id_not_found_in_ols"
        elif e["role"] in MIXS_ENV and BARE_DIGITS.match(v.strip()):
            q = "unprefixed_numeric_identifier"
        if q:
            exp_q[e["evidence_id"]] = q
    got_q = {}
    for eid, hits in side_items.items():
        for sa, g, it in hits:
            if it["quarantine"] is not None:
                got_q[eid] = it["quarantine"]
    for eid in set(exp_q) | set(got_q):
        if exp_q.get(eid) != got_q.get(eid):
            c.err("quarantine_mismatch", {"id": eid, "expected": exp_q.get(eid), "got": got_q.get(eid),
                                          "value": ev_by_id[eid]["value_original"] if eid in ev_by_id else None})
    c.counts["expected_items"] = len(exp_q)
    c.counts["expected_records"] = len({ev_by_id[e]["source_acc"] for e in exp_q})
    c.counts["sidecar_items"] = len(got_q)
    c.counts["sidecar_records"] = len({side_items[e][0][0] for e in got_q})
    c.counts["case_insensitive_extra_matches"] = len(case_diff)
    for kind in set(exp_q.values()):
        c.counts["expected:" + kind] = sum(1 for v in exp_q.values() if v == kind)
    if c.counts["expected_items"] != 14 or c.counts["expected_records"] != 7:
        c.err("expected_14_in_7", dict(c.counts))
    for eid in got_q:
        for sa, g, it in side_items[eid]:
            if it["envo_ids"]:
                c.notes.append({"quarantined_item_with_verified_envo_ids": eid, "envo_ids": it["envo_ids"]})
    c.notes.append({"records": sorted({ev_by_id[e]["source_acc"] for e in exp_q})})
    results[c.name] = c.result()

    # ======== Check 6: host leakage ========
    c = Check("6_host_leakage")
    for eid, hits in side_items.items():
        for sa, g, it in hits:
            c.counts["items_checked"] += 1
            if it["role"] in ("host", "host_detail") and g != "host":
                c.err("host_role_outside_host", {"id": eid, "group": g})
            if g == "host":
                c.counts["host_group_items"] += 1
                if it["role"] not in ("host", "host_detail"):
                    c.err("non_host_role_in_host", eid)
            if it["role"] == "organism_context" and g != "organism_context":
                c.err("organism_context_outside_group", eid)
            if g == "organism_context":
                c.counts["organism_context_items"] += 1
                if it["evidence_source"] != "literature" or not it["literature"] or it["literature"]["scope"] != "organism":
                    c.err("organism_context_not_literature_organism", eid)
            if g == "physical" and it["role"] in ("host", "host_detail"):
                c.err("host_in_physical", eid)
            if it["role"] not in GROUPS[g]:
                c.err("role_group_mismatch", {"id": eid, "role": it["role"], "group": g})
            if it["literature"] and it["literature"]["scope"] == "organism" and g != "organism_context":
                c.err("organism_scope_literature_outside_organism_context", eid)
    results[c.name] = c.result()

    # ======== Check 7: literature ========
    c = Check("7_literature")
    for eid, hits in side_items.items():
        for sa, g, it in hits:
            if it["evidence_source"] != "literature":
                continue
            c.counts["literature_items"] += 1
            if eid not in hl_json:
                c.err("not_in_literature_json", eid)
                continue
            jsa, x = hl_json[eid]
            if jsa != sa:
                c.err("wrong_source", eid)
            L = it["literature"]
            for k in ("pmid", "doi", "locator", "scope", "access", "consistent_with_db", "source_sha256"):
                if L.get(k) != nz(x.get(k)):
                    c.err("lit:" + k, {"id": eid, "expected": x.get(k), "got": L.get(k)})
            if it["value"] != nz(x["quote"]):
                c.err("value_vs_quote", eid)
            if it["browser_url"] != "https://pubmed.ncbi.nlm.nih.gov/%s/" % x["pmid"]:
                c.err("browser_url", {"id": eid, "got": it["browser_url"]})
            if it["source_url"] != nz(x.get("source_url")):
                c.err("source_url", eid)
            if it["entity_accession"] != x["pmid"]:
                c.err("entity_accession", eid)
            if it["field"] != "literature:%s | %s" % (x["scope"], x["locator"]):
                c.err("field", eid)
            exp_role = {"organism": "organism_context", "isolate": "literature_isolate",
                        "rejected": "literature_rejected"}[x["scope"]]
            if it["role"] != exp_role:
                c.err("role_vs_scope", eid)
    url_dropped = 0
    for sa, (m, i, s) in side_src.items():
        got = s["literature_sources_checked"]
        if sa in lit:
            exp = lit[sa]["sources_checked"]
            if s["literature_status"] != lit[sa]["literature_status"]:
                c.err("literature_status_vs_json", sa)
            c.counts["records_with_review"] += 1
            keys = set(k for d in got for k in d) if got else {"access", "doi", "found_habitat_statement", "pmid", "title"}
            norm = lambda d: json.dumps({k: d.get(k) for k in sorted(keys)}, sort_keys=True)
            if sorted(map(norm, exp)) != sorted(map(norm, got)):
                c.err("sources_checked_mismatch", {"source": sa, "n_expected": len(exp), "n_got": len(got)})
            if len(exp) != len(got):
                c.err("sources_checked_count", sa)
            c.counts["sources_checked_entries"] += len(got)
            dropped = set(k for d in exp for k in d) - keys
            if dropped:
                url_dropped += 1
                c.counts["dropped_keys:" + ",".join(sorted(dropped))] += 1
        elif got:
            c.err("sources_checked_for_unreviewed_record", sa)
    c.counts["records_sources_checked_with_dropped_keys"] = url_dropped
    if len([1 for sa in lit if sa in side_src]) != len(lit):
        c.err("literature_record_missing_in_sidecar", len(lit))
    c.counts["literature_json_items"] = len(hl_json)
    if c.counts["literature_items"] != len(hl_json):
        c.err("literature_item_total", {"sidecar": c.counts["literature_items"], "json": len(hl_json)})
    results[c.name] = c.result()

    # ======== Check 8: summary ========
    c = Check("8_summary")
    N = len(recs)
    G = collections.Counter(r["primary_grade"] for r in recs)
    H = collections.Counter(r["host_association_status"] for r in recs)
    flags = {r["source_acc"]: set(split_semi(r["flags"])) for r in recs}
    usable = lambda r: r["primary_grade"] in ("DIRECT_SAMPLE", "VERIFIED_ISOLATE")
    hashost = lambda r: r["host_association_status"] in ("REPORTED", "AMBIGUOUS")
    nNR = G["NOT_REPORTED"]
    exp = {}
    for g in GRADES:
        exp["grade:" + g] = (G[g], N)
    exp["physical_habitat_usable"] = (sum(usable(r) for r in recs), N)
    for h in HOST_STATUSES:
        exp["host_association:" + h] = (H[h], N)
    exp["has_host_association"] = (sum(r["has_host_association"] == "1" for r in recs), N)
    exp["host_association_only"] = (sum("host_association_only" in flags[r["source_acc"]] for r in recs), N)
    exp["host_without_usable_physical_habitat"] = (sum(hashost(r) and not usable(r) for r in recs), N)
    exp["host_without_usable_physical_habitat:AMBIGUOUS"] = (
        sum(hashost(r) and r["primary_grade"] == "AMBIGUOUS" for r in recs), N)
    exp["physical_habitat_and_host_association"] = (
        sum(r["has_usable_habitat"] == "1" and r["has_host_association"] == "1" for r in recs), N)
    for cl in AMB_CLASSES:
        exp["ambiguity_class:" + cl] = (sum(r["ambiguity_class"] == cl for r in recs), G["AMBIGUOUS"])
        exp["host_ambiguity_class:" + cl] = (sum(r["host_ambiguity_class"] == cl for r in recs), H["AMBIGUOUS"])
    for sc in NR_SCOPES:
        exp["not_reported_scope:" + sc] = (sum(r["not_reported_scope"] == sc for r in recs), nNR)
    exp["no_traceable_sample_link"] = (sum(r["db_chain_status"] == "NO_LINK" for r in recs), N)
    exp["no_traceable_sample_link:NOT_REPORTED"] = (
        sum(r["db_chain_status"] == "NO_LINK" and r["primary_grade"] == "NOT_REPORTED" for r in recs), nNR)
    for ls in LIT_STATUSES:
        exp["literature_status:" + ls] = (sum(r["literature_status"] == ls for r in recs), N)
    exp["host_tissue_isolation_source_only"] = (
        sum("host_tissue_isolation_source_only" in flags[r["source_acc"]] for r in recs), N)
    exp["quarantined_values:records"] = (results["5_quarantine"]["counts"]["expected_records"], N)
    exp["invalid_placeholder:records"] = (
        len({e["source_acc"] for e in ev if e["value_status"] == "invalid_placeholder"}), N)
    mrdb_sources = collections.defaultdict(list)
    for r in recs:
        mrdb_sources[r["mrdb_acc"]].append(r["primary_grade"])
    multi = [m for m, v in mrdb_sources.items() if len(v) > 1]
    exp["multi_source_mrdb"] = (len(multi), len(mrdb_sources))
    exp["multi_source_mrdb:grades_differ"] = (sum(len(set(mrdb_sources[m])) > 1 for m in multi), len(multi))
    c.counts["sanity:has_host_and_grade_NOT_REPORTED"] = sum(
        hashost(r) and r["primary_grade"] == "NOT_REPORTED" for r in recs)
    c.counts["sanity:host_REPORTED_and_grade_NOT_REPORTED"] = sum(
        r["host_association_status"] == "REPORTED" and r["primary_grade"] == "NOT_REPORTED" for r in recs)
    c.counts["sanity:no_link_records_not_NOT_REPORTED"] = sum(
        r["db_chain_status"] == "NO_LINK" and r["primary_grade"] != "NOT_REPORTED" for r in recs)
    sm = {m["id"]: m for m in summary["metrics"]}
    for k, (n, d) in exp.items():
        if k not in sm:
            c.err("metric_missing_in_summary", k)
            continue
        if sm[k]["numerator"] != n or sm[k]["denominator"] != d:
            c.err("metric_mismatch", {"id": k, "expected": [n, d], "got": [sm[k]["numerator"], sm[k]["denominator"]]})
        else:
            c.counts["metrics_matched"] += 1
        pct = round(100.0 * n / d, 2) if d else 0.0
        if abs(sm[k].get("percent", pct) - pct) > 0.005:
            c.err("percent_mismatch", {"id": k, "expected": pct, "got": sm[k].get("percent")})
    c.counts["summary_metrics_total"] = len(sm)
    for k in set(sm) - set(exp):
        c.counts["summary_metrics_not_recomputed"] += 1
        c.notes.append({"not_recomputed": k})
    if summary["denominators"] != {"mrdb_accessions": len(mrdb_sources), "source_records": N}:
        c.err("denominators", summary["denominators"])
    key_targets = {"physical_habitat_usable": (2540, 5466), "has_host_association": (755, 5466),
                   "host_association_only": (186, 5466), "host_without_usable_physical_habitat": (207, 5466),
                   "not_reported_scope:database_only_literature_not_reviewed": (2796, 2831),
                   "not_reported_scope:database_only_literature_inaccessible": (23, 2831),
                   "not_reported_scope:database_and_literature": (12, 2831),
                   "no_traceable_sample_link": (18, 5466), "multi_source_mrdb": (129, 5299),
                   "multi_source_mrdb:grades_differ": (43, 129)}
    for k, v in key_targets.items():
        if exp[k] != v:
            c.err("brief_target_mismatch", {"id": k, "recomputed": exp[k], "target": v})
    covm = {r["metric"]: (int(r["numerator"]), int(r["denominator"])) for r in cov
            if r["unit"] == "source_record" and r["stratum_type"] == "all"}
    covmr = {r["metric"]: (int(r["numerator"]), int(r["denominator"])) for r in cov
             if r["unit"] == "mrdb_accession" and r["stratum_type"] == "all"}
    alias = {"physical_habitat_usable": "usable_habitat_any_source",
             "host_tissue_isolation_source_only": "flag:host_tissue_isolation_source_only",
             "invalid_placeholder:records": "flag:invalid_placeholder_value",
             "no_traceable_sample_link": "flag:no_insdc_link"}
    for k, (n, d) in exp.items():
        ck = k if k in covm else alias.get(k)
        if ck and ck in covm:
            c.counts["compared_to_coverage"] += 1
            if covm[ck] != (n, d):
                c.err("coverage_mismatch", {"id": k, "coverage_metric": ck, "recomputed": [n, d], "coverage": covm[ck]})
            if k in sm and (sm[k]["numerator"], sm[k]["denominator"]) != covm[ck]:
                c.err("summary_vs_coverage", {"id": k, "summary": [sm[k]["numerator"], sm[k]["denominator"]], "coverage": covm[ck]})
    if covmr.get("mrdb_multiple_source_records", (None,))[0] != exp["multi_source_mrdb"][0]:
        c.err("coverage_mrdb_multiple", covmr.get("mrdb_multiple_source_records"))
    if covmr.get("mrdb_mixed_source_grades", (None,))[0] != exp["multi_source_mrdb:grades_differ"][0]:
        c.err("coverage_mrdb_mixed", covmr.get("mrdb_mixed_source_grades"))
    c.counts["compared_to_coverage"] += 2
    # flag:envo_id_invalid (6) + unprefixed record (1) should give the 7 quarantined records
    c.counts["coverage_flag_envo_id_invalid"] = covm.get("flag:envo_id_invalid", (None,))[0]
    ce = contract["expected"]
    for k, v in ce["grades"].items():
        if G[k] != v:
            c.err("contract_grade", k)
    results[c.name] = c.result()

    # ======== Check 9: manifest ========
    c = Check("9_manifest")
    listed = {f["path"]: f for f in manifest["files"]}
    actual = set()
    for root, _, fs in os.walk(HAB):
        for f in fs:
            actual.add(os.path.relpath(os.path.join(root, f), a.export))
    c.counts["listed_files"] = len(listed)
    c.counts["actual_files_incl_manifest"] = len(actual)
    if manifest["n_files"] != len(listed):
        c.err("n_files", manifest["n_files"])
    for p in actual - set(listed) - {"habitat/manifest.json"}:
        c.err("unlisted_file", p)
    tot = 0
    for p, f in listed.items():
        fp = os.path.join(a.export, p)
        if not os.path.exists(fp):
            c.err("listed_missing", p)
            continue
        b = os.path.getsize(fp)
        tot += b
        if b != f["bytes"]:
            c.err("bytes", p)
        if sha256_file(fp) != f["sha256"]:
            c.err("sha256", p)
        if b > contract["expected"]["max_file_bytes"]:
            c.err("file_exceeds_max_bytes", {"path": p, "bytes": b})
        if p.startswith("habitat/records/"):
            m = os.path.basename(p)[:-5]
            if f.get("records") != len(side[m]["sources"]):
                c.err("records_count", p)
        c.counts["verified_files"] += 1
    if manifest["total_bytes"] != tot:
        c.err("total_bytes", {"manifest": manifest["total_bytes"], "actual": tot})
    mins = {i["path"]: i["sha256"] for i in manifest["inputs"]}
    if set(mins) != set(INPUTS):
        c.err("input_set", sorted(mins))
    for p in INPUTS:
        actual_sha = sha256_file(os.path.join(a.repo, p))
        if mins.get(p) != actual_sha:
            c.err("input_sha256_vs_file", p)
        if contract["inputs"].get(p) != actual_sha:
            c.err("input_sha256_vs_contract", p)
        c.counts["inputs_verified"] += 1
    rm = json.load(open(os.path.join(P, "habitat_retrieval_manifest.json")))
    if manifest["retrieval"]["database_sha256"] != rm.get("database_sha256"):
        c.err("database_sha256", None)
    if manifest["retrieval"]["n_requests"] != rm.get("n_requests"):
        c.err("n_requests", None)
    if manifest["retrieval"]["cache_sha256"] != contract["retrieval_cache"]["sha256"]:
        c.err("cache_sha256", None)
    if manifest["audit"] != contract["audit"]:
        c.err("audit_block", None)
    bad_path = re.compile(r"/workspace|/mnt/|/tmp\b|/home/|/root/")
    ts_re = re.compile(r"\b20\d\d-\d\d-\d\d[T ]\d\d:\d\d(:\d\d)?")
    ts_key = re.compile(r"(generated|timestamp|created|exported|built|_at$|time)", re.I)

    def walk(o, path, hits):
        if isinstance(o, dict):
            for k, v in o.items():
                if ts_key.search(k):
                    hits.append(path + "." + k)
                walk(v, path + "." + k, hits)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, path + "[%d]" % i, hits)
    for p in sorted(actual):
        fp = os.path.join(a.export, p)
        raw = open(fp, encoding="utf-8").read()
        for mm in bad_path.finditer(raw):
            c.err("path_string", {"file": p, "context": raw[max(0, mm.start() - 40):mm.end() + 20]})
        obj = json.loads(raw)
        hits = []
        walk(obj, "", hits)
        for h in hits:
            c.err("timestamp_like_key", {"file": p, "key": h})
        if not p.startswith("habitat/records/"):
            for mm in ts_re.finditer(raw):
                c.err("timestamp_in_metadata_file", {"file": p, "match": mm.group(0)})
        else:
            for s in obj["sources"]:
                for g, its in s["items"].items():
                    for it in its:
                        if it["value"] and ts_re.search(it["value"]):
                            c.counts["iso_datetime_in_submitted_item_values"] += 1
                        it["value"] = None
            for mm in ts_re.finditer(json.dumps(obj)):
                c.err("timestamp_outside_item_values", {"file": p, "match": mm.group(0)})
        c.counts["files_scanned"] += 1
    results[c.name] = c.result()

    # ======== Check 10: URLs ========
    c = Check("10_urls")
    hosts = collections.Counter()
    for eid, hits in side_items.items():
        for sa, g, it in hits:
            for k in ("browser_url", "source_url"):
                u = it[k]
                if u is None:
                    if k == "browser_url":
                        c.err("browser_url_null", eid)
                    continue
                pu = urlparse(u)
                hosts[(k, pu.netloc)] += 1
                c.counts["urls"] += 1
                if pu.scheme != "https":
                    c.err("not_https", {"id": eid, "url": u})
                if pu.netloc not in ALLOWED_HOSTS:
                    c.err("host_not_allowed", {"id": eid, "url": u})
                if re.search(r"\s", u):
                    c.err("whitespace_in_url", eid)
    c.notes.append({"host_counts": {"%s %s" % k: v for k, v in sorted(hosts.items())}})
    results[c.name] = c.result()

    overall = "INDEPENDENT_PASS" if all(r["status"] == "PASS" for r in results.values()) else "INDEPENDENT_FAIL"
    out = {"verdict_data_checks": overall, "checks": results,
           "inputs": {"export": a.export, "repo_inputs": INPUTS}}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump(out, open(a.out, "w"), indent=1, sort_keys=True, default=str)
    for k, r in results.items():
        print(k, r["status"], json.dumps(r["counts"], default=str)[:900])
        if r["errors"]:
            print("   ERRORS", json.dumps(r["errors"])[:800])
            for kind, exs in r["examples"].items():
                print("     ", kind, json.dumps(exs, default=str)[:600])
        for n in r["notes"][:3]:
            print("   NOTE", json.dumps(n, default=str)[:900])
    print(overall)


if __name__ == "__main__":
    main()
