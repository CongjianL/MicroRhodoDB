"""PR-7c.2: build the versioned habitat sidecar (data/v<release>/habitat/) from the accepted PR-7c.1a outputs.

Principle: display observed environmental metadata, not inferred habitats. This module copies grades, states and
verbatim values from the PR-7c.1a audit tables. It never reclassifies, normalises free text, maps to ENVO, reads
the SQLite database or makes network requests.

Inputs (pinned by SHA-256 in contract.json; any mismatch -> BLOCKED_HABITAT_SOURCE):
  habitat_record_availability.tsv  one row per source record (grades, states, flags, accessions)
  habitat_evidence.tsv             one row per evidence item (stable evidence_id, verbatim value, provenance URLs)
  habitat_coverage_summary.tsv     release-level counts (cross-checked against the recomputed summary)
  habitat_retrieval_manifest.json  audit provenance
  literature/literature_evidence.json  literature items (PMID, DOI, quote, locator) and the sources checked

Outputs (relative to the release directory):
  habitat/manifest.json            provenance, evidence-ID rules, counts, SHA-256 of every other habitat file
  habitat/summary.json             release-level availability counts with explicit denominators
  habitat/records/<MRDB>.json      one file per MRDB accession; one entry per source record (5,299 files / 5,466)

Evidence IDs are recomputed for every item and must equal the audit IDs:
  HE = "HE" + sha256("source_acc|evidence_source|entity_accession|link_index|field_original|value_original")[:12]
  HL = "HL" + sha256("pmid|doi|quote|scope" + source_acc)[:12], where a null field is serialised as the literal
       string "None" (Python str(None)); this is the formal specification of the PR-7c.1a behaviour.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HABITAT_SCHEMA_VERSION = "1.0.0"
CONTRACT = Path(__file__).resolve().parent / "contract.json"
SCHEMA_REL = "web/src/data/schemas/habitat.schema.json"
PR7C1 = "docs/website/pr7c1/"
REC_TSV = PR7C1 + "habitat_record_availability.tsv"
EV_TSV = PR7C1 + "habitat_evidence.tsv"
COV_TSV = PR7C1 + "habitat_coverage_summary.tsv"
RET_JSON = PR7C1 + "habitat_retrieval_manifest.json"
LIT_JSON = PR7C1 + "literature/literature_evidence.json"

GRADES = ("DIRECT_SAMPLE", "VERIFIED_ISOLATE", "ORGANISM_CONTEXT_ONLY", "AMBIGUOUS", "NOT_REPORTED", "LOOKUP_FAILED",
          "NOT_SEARCHED")
HOST_STATUSES = ("REPORTED", "AMBIGUOUS", "NOT_REPORTED", "LOOKUP_FAILED", "NOT_SEARCHED")
AMBIGUITY_CLASSES = ("FORMATTING_ONLY", "NESTED_WORDING", "DISTINCT_SAME_SAMPLE", "DISTINCT_ACROSS_SAMPLES",
                     "LITERATURE_VS_DATABASE")
LIT_STATUSES = ("NOT_SEARCHED", "ORGANISM_CONTEXT", "ISOLATE_EVIDENCE", "LOOKUP_FAILED", "NOT_REPORTED")
NR_SCOPES = {"database_only_literature_not_reviewed": "not_reviewed",
             "database_only_literature_inaccessible": "inaccessible",
             "database_and_literature": "reviewed_not_reported"}
LIT_TO_MISSING = {"NOT_SEARCHED": "not_reviewed", "LOOKUP_FAILED": "inaccessible", "NOT_REPORTED": "reviewed_not_reported"}

# Display groups. Grading roles (PR-7c.1a physical axis) are the first four PHYSICAL roles.
GRADING_PHYSICAL = ("env_broad_scale", "env_local_scale", "env_medium", "isolation_source")
GROUPS = {
    "physical": GRADING_PHYSICAL + ("habitat_nonstandard", "literature_isolate", "literature_rejected"),
    "host": ("host", "host_detail"),
    "collection": ("country", "lat_lon", "lat", "lon", "collection_date", "depth", "sample_material",
                   "environmental_sample", "metagenome_source"),
    "organism_context": ("organism_context",),
}
ROLE_GROUP = {r: g for g, rs in GROUPS.items() for r in rs}
MIXS_ENV = ("env_broad_scale", "env_local_scale", "env_medium")

ENVO_IN_VALUE = re.compile(r"ENVO[:_ ]?(\d{7,8})", re.I)
UNPREFIXED_ID = re.compile(r"^\s*\d{5,8}\s*$")
ENVO_ID = re.compile(r"^ENVO:\d{8}$")
ACC_PATTERNS = {
    "biosamples": re.compile(r"^SAM[NED][A-Z]?\d+$"),
    "bioprojects": re.compile(r"^PRJ[NED][A-Z]\d+$"),
    "insdc": re.compile(r"^[A-Z]{1,6}\d{5,12}(\.\d+)?$"),
    "embl_protein_ids": re.compile(r"^[A-Z]{3}\d{5,7}(\.\d+)?$"),
    "proteomes": re.compile(r"^UP\d{9}$"),
    "assemblies": re.compile(r"^GC[AF]_\d{9}\.\d+$"),
}
URL_RE = re.compile(r"^https://[A-Za-z0-9.-]+/\S*$")


class HabitatError(Exception):
    def __init__(self, code: str, msg: str):
        super().__init__(f"{code}: {msg}")
        self.code = code


def need(cond, msg, code="CONTRACT_VIOLATION"):
    if not cond:
        raise HabitatError(code, msg)


def dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def read_tsv(p: Path) -> list[dict]:
    csv.field_size_limit(sys.maxsize)
    with p.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def split(v: str, sep: str = ";") -> list[str]:
    return [x for x in v.split(sep) if x] if v else []


def opt(v: str):
    return v if v != "" else None


def he_id(r: dict) -> str:
    return "HE" + sha256_bytes("|".join(r[k] for k in ("source_acc", "evidence_source", "entity_accession", "link_index",
                                                         "field_original", "value_original")).encode())[:12]


def hl_id(x: dict, acc: str) -> str:
    return "HL" + sha256_bytes("|".join(str(x.get(k)) for k in ("pmid", "doi", "quote", "scope")).encode() + acc.encode())[:12]


def load_inputs(repo: Path, contract: dict) -> dict[str, bytes]:
    data = {}
    for rel, sha in contract["inputs"].items():
        p = repo / rel
        need(p.is_file(), f"missing habitat input {rel}", "BLOCKED_HABITAT_SOURCE")
        b = p.read_bytes()
        need(sha256_bytes(b) == sha, f"SHA-256 mismatch for {rel}", "BLOCKED_HABITAT_SOURCE")
        data[rel] = b
    return data


def quarantine_reason(r: dict) -> str | None:
    """Values kept verbatim but excluded from any standardized ontology display or facet."""
    role, v = r["role"], r["value_original"]
    if ROLE_GROUP.get(role) != "physical" or role.startswith("literature"):
        return None
    verified = set(split(r["envo_ids"]))
    written = {"ENVO:" + m.zfill(8) for m in ENVO_IN_VALUE.findall(v)}
    if written - verified:
        return "envo_id_not_found_in_ols"
    if role in MIXS_ENV and UNPREFIXED_ID.match(v):
        return "unprefixed_numeric_identifier"
    return None


def make_item(r: dict, lit: dict | None) -> dict:
    envo = split(r["envo_ids"])
    need(all(ENVO_ID.match(e) for e in envo), f"{r['evidence_id']}: malformed ENVO id")
    need(URL_RE.match(r["browser_url"]) is not None, f"{r['evidence_id']}: browser_url not https")
    need(r["source_url"] == "" or URL_RE.match(r["source_url"]) is not None, f"{r['evidence_id']}: source_url not https")
    it = {
        "evidence_id": r["evidence_id"],
        "evidence_source": r["evidence_source"],
        "entity_accession": r["entity_accession"],
        "link_index": int(r["link_index"]) if r["link_index"] != "" else None,
        "field": r["field_original"],
        "role": r["role"],
        "value_status": r["value_status"],
        "value": opt(r["value_original"]),  # null = the field is present with an empty value (contract: no "")
        "envo_ids": envo,
        "linkage_route": r["linkage_route"],
        "mapping_confidence": opt(r["mapping_confidence"]),
        "browser_url": r["browser_url"],
        "source_url": opt(r["source_url"]),
        "quarantine": quarantine_reason(r),
        "literature": None,
    }
    if r["evidence_source"] == "literature":
        need(lit is not None, f"{r['evidence_id']}: literature item not found")
        need(lit["quote"] == r["value_original"] and str(lit["pmid"]) == r["entity_accession"],
             f"{r['evidence_id']}: literature quote/PMID differ from the evidence row")
        it["literature"] = {"pmid": str(lit["pmid"]), "doi": lit.get("doi") or None,
                            "locator": lit.get("locator") or None, "scope": lit["scope"],
                            "access": lit.get("access") or None,
                            "consistent_with_db": lit.get("consistent_with_db") or None,
                            "source_sha256": lit.get("source_sha256") or None}
    else:
        need(r["link_index"] != "", f"{r['evidence_id']}: database item without link_index")
    return it


def build(repo, mrdb_of_source: dict[str, str], representative: dict[str, str],
          release: str = "1.6.1") -> dict[str, tuple[bytes, int]]:
    """Return {path relative to data/v<release>/: (bytes, n_records)} for every habitat file."""
    repo = Path(repo).resolve()
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    exp = contract["expected"]
    raw = load_inputs(repo, contract)
    ret = json.loads(raw[RET_JSON])
    need(ret["audit_id"] == contract["audit"]["audit_id"] and ret["audit_version"] == contract["audit"]["audit_version"],
         "retrieval manifest audit id/version differ from the contract", "BLOCKED_HABITAT_SOURCE")
    for rel in (REC_TSV, EV_TSV, COV_TSV):
        need(ret["outputs"][rel.rsplit("/", 1)[1]] == contract["inputs"][rel],
             f"retrieval manifest does not list {rel} with the pinned SHA-256", "BLOCKED_HABITAT_SOURCE")
    need(ret["literature_sha256"] == contract["inputs"][LIT_JSON], "literature SHA-256 differs from the retrieval manifest",
         "BLOCKED_HABITAT_SOURCE")

    recs = read_tsv(repo / REC_TSV)
    evs = read_tsv(repo / EV_TSV)
    cov = read_tsv(repo / COV_TSV)
    lit_all = json.loads(raw[LIT_JSON])
    need(len(recs) == exp["source_records"], f"expected {exp['source_records']} source records, got {len(recs)}")
    need(len(evs) == exp["evidence_rows"], f"expected {exp['evidence_rows']} evidence rows, got {len(evs)}")
    by_src = {r["source_acc"]: r for r in recs}
    need(len(by_src) == len(recs), "duplicate source_acc in record table")

    # ---- MRDB relationships: the audit's mrdb_acc must equal the web export's accession map
    need(set(mrdb_of_source) == set(by_src), "habitat source records differ from accessions.json by_source")
    bad = [a for a, r in by_src.items() if mrdb_of_source[a] != r["mrdb_acc"]]
    need(not bad, f"MRDB mismatch vs accessions.json for {bad[:5]}")
    mrdbs = defaultdict(list)
    for r in recs:
        mrdbs[r["mrdb_acc"]].append(r["source_acc"])
    need(len(mrdbs) == exp["mrdb_accessions"], f"expected {exp['mrdb_accessions']} MRDB accessions, got {len(mrdbs)}")

    # ---- literature items keyed by recomputed HL id
    lit_by_id = {}
    for acc, v in lit_all.items():
        for x in v.get("items", []):
            h = hl_id(x, acc)
            need(h not in lit_by_id, f"duplicate HL id {h}")
            lit_by_id[h] = (acc, x)

    # ---- evidence: recompute every id, group display roles per source record
    items_by_src = defaultdict(lambda: {g: [] for g in GROUPS})
    seen = set()
    n_disp = 0
    for r in evs:
        eid = r["evidence_id"]
        need(eid not in seen, f"duplicate evidence_id {eid}")
        seen.add(eid)
        need(r["source_acc"] in by_src, f"{eid}: unknown source_acc {r['source_acc']}")
        if eid.startswith("HE"):
            need(he_id(r) == eid, f"{eid}: evidence id does not recompute")
            lit = None
        else:
            need(eid.startswith("HL") and eid in lit_by_id, f"{eid}: literature evidence id does not recompute")
            acc, lit = lit_by_id[eid]
            need(acc == r["source_acc"], f"{eid}: literature item belongs to {acc}")
        g = ROLE_GROUP.get(r["role"])
        if g is None:
            continue
        items_by_src[r["source_acc"]][g].append(make_item(r, lit))
        n_disp += 1
    need(set(lit_by_id) <= seen, "literature items missing from the evidence table")
    for groups in items_by_src.values():
        for g in groups:
            groups[g].sort(key=lambda i: (i["role"], i["evidence_source"], i["entity_accession"],
                                          i["link_index"] if i["link_index"] is not None else -1, i["evidence_id"]))

    # ---- source entries
    entries = {}
    for acc, r in by_src.items():
        grade = r["primary_grade"]
        need(grade in GRADES, f"{acc}: unknown grade {grade}")
        need(r["host_association_status"] in HOST_STATUSES, f"{acc}: unknown host status")
        need(r["literature_status"] in LIT_STATUSES, f"{acc}: unknown literature status")
        need(r["ambiguity_class"] in AMBIGUITY_CLASSES + ("",), f"{acc}: unknown ambiguity class")
        need(r["host_ambiguity_class"] in AMBIGUITY_CLASSES + ("",), f"{acc}: unknown host ambiguity class")
        need((grade == "AMBIGUOUS") == (r["ambiguity_class"] != ""), f"{acc}: ambiguity class without AMBIGUOUS grade")
        need((r["host_association_status"] == "AMBIGUOUS") == (r["host_ambiguity_class"] != ""),
             f"{acc}: host ambiguity class without AMBIGUOUS host status")
        need(r["db_chain_status"] in ("COMPLETE", "NO_LINK"), f"{acc}: unknown db_chain_status")
        no_link = r["db_chain_status"] == "NO_LINK"
        need(no_link == ("no_insdc_link" in split(r["flags"])), f"{acc}: NO_LINK and no_insdc_link flag disagree")
        missing = None
        if grade == "NOT_REPORTED":
            need(r["not_reported_scope"] in NR_SCOPES, f"{acc}: NOT_REPORTED without a scope")
            lit_axis = LIT_TO_MISSING.get(r["literature_status"])
            need(lit_axis == NR_SCOPES[r["not_reported_scope"]], f"{acc}: literature status and NR scope disagree")
            missing = {"database": "no_traceable_sample_link" if no_link else "not_reported_in_linked_sample_records",
                       "literature": lit_axis}
        else:
            need(r["not_reported_scope"] == "", f"{acc}: NR scope on a {grade} record")
        conflict = []
        roles, scopes, kinds = split(r["conflict_roles"]), split(r["conflict_scope"]), split(r["conflict_kind"])
        need(len(roles) == len(scopes) == len(kinds), f"{acc}: conflict columns misaligned")
        for role, sc, kd in zip(roles, scopes, kinds):
            need(sc.split(":", 1)[0] == role and kd.split(":", 1)[0] == role, f"{acc}: conflict role order")
            conflict.append({"role": role, "scope": sc.split(":", 1)[1], "kind": kd.split(":", 1)[1]})
        accs = {"biosamples": split(r["biosamples"]), "bioprojects": split(r["bioprojects"]),
                "insdc": split(r["insdc_accessions"]), "embl_protein_ids": split(r["embl_protein_ids"]),
                "proteomes": split(r["proteomes"]), "assemblies": split(r["assemblies"])}
        for k, vs in accs.items():
            bad = [v for v in vs if not ACC_PATTERNS[k].match(v)]
            need(not bad, f"{acc}: malformed {k} {bad}")
        lit = lit_all.get(acc)
        need((lit is None) == (r["literature_status"] == "NOT_SEARCHED"), f"{acc}: literature file vs status")
        checked = []
        for s in (lit or {}).get("sources_checked", []):
            checked.append({"pmid": opt(str(s.get("pmid") or "")), "doi": s.get("doi") or None,
                            "title": s.get("title") or None, "access": s.get("access") or None,
                            "found_habitat_statement": s.get("found_habitat_statement")})
        checked.sort(key=lambda s: (s["pmid"] or "", s["doi"] or "", s["title"] or ""))
        items = items_by_src[acc]
        # integrity: grading values = the audit's usable physical/host values, verbatim
        for role in GRADING_PHYSICAL + ("host",):
            g = ROLE_GROUP[role]
            got = sorted({i["value"] for i in items[g] if i["role"] == role and i["value_status"] == "usable"})
            want = sorted(set(split(r[f"{role}_original"], " || ")))
            need(got == want, f"{acc}: {role} usable values differ from the record table")
        has_phys = r["has_usable_habitat"] == "1"
        need(has_phys == (grade in ("DIRECT_SAMPLE", "VERIFIED_ISOLATE")), f"{acc}: has_usable_habitat")
        has_host = r["has_host_association"] == "1"
        need(has_host == (r["host_association_status"] in ("REPORTED", "AMBIGUOUS")), f"{acc}: has_host_association")
        entries[acc] = {
            "source_acc": acc,
            "mrdb_acc": r["mrdb_acc"],
            "is_mrdb_representative": representative[r["mrdb_acc"]] == acc,
            "grade": grade,
            "db_habitat_status": r["db_habitat_status"],
            "db_chain_status": r["db_chain_status"],
            "sample_link": "none" if no_link else "traceable",
            "literature_status": r["literature_status"],
            "not_reported_scope": opt(r["not_reported_scope"]),
            "missingness": missing,
            "has_usable_physical_habitat": has_phys,
            "ambiguity_class": opt(r["ambiguity_class"]),
            "host_association_status": r["host_association_status"],
            "has_host_association": has_host,
            "host_ambiguity_class": opt(r["host_ambiguity_class"]),
            "conflicts": conflict,
            "flags": sorted(split(r["flags"])),
            "linkage": {"route": opt(r["linkage_route"]), "mapping_confidence": opt(r["mapping_confidence"]),
                        "sample_type": r["sample_type"], "molecule_types": split(r["molecule_types"])},
            "accessions": accs,
            "literature_sources_checked": checked,
            "record_evidence_ids": sorted(split(r["evidence_ids"])),
            "items": items,
        }
        need(set(entries[acc]["record_evidence_ids"]) <= seen, f"{acc}: record evidence id not in the evidence table")

    # ---- files per MRDB
    out: dict[str, tuple[bytes, int]] = {}
    grades_differ = 0
    for ma in sorted(mrdbs):
        srcs = sorted(mrdbs[ma])
        rep = representative.get(ma)
        need(rep in srcs, f"{ma}: representative {rep} not among habitat sources")
        srcs.sort(key=lambda a: (a != rep, a))
        differ = len({entries[a]["grade"] for a in srcs}) > 1
        grades_differ += differ
        doc = {"habitat_schema_version": HABITAT_SCHEMA_VERSION, "dataset_release": release, "mrdb_acc": ma,
               "audit_id": contract["audit"]["audit_id"], "n_source_records": len(srcs),
               "source_grades_differ": differ, "sources": [entries[a] for a in srcs]}
        b = dumps(doc).encode("utf-8")
        need(len(b) <= exp["max_file_bytes"], f"habitat/records/{ma}.json is {len(b)} bytes (> budget)")
        out[f"habitat/records/{ma}.json"] = (b, len(srcs))
    multi = sum(1 for v in mrdbs.values() if len(v) > 1)

    # ---- summary (recomputed from entries, cross-checked against the audit coverage summary)
    E = list(entries.values())
    N = len(E)

    def pct(n, d):
        return round(100.0 * n / d, 2) if d else 0.0

    metrics = []

    def m(mid, num, den, desc):
        metrics.append({"id": mid, "numerator": num, "denominator": den, "percent": pct(num, den), "definition": desc})

    gc = Counter(e["grade"] for e in E)
    for g in GRADES:
        m(f"grade:{g}", gc[g], N, f"source records whose physical-habitat evidence grade is {g}")
    n_phys = sum(e["has_usable_physical_habitat"] for e in E)
    m("physical_habitat_usable", n_phys, N, "source records with a usable, traceable physical-habitat value "
      "(grade DIRECT_SAMPLE or VERIFIED_ISOLATE; physical-AMBIGUOUS records are excluded)")
    hc = Counter(e["host_association_status"] for e in E)
    for s in HOST_STATUSES:
        m(f"host_association:{s}", hc[s], N, f"source records whose host-association status is {s}")
    n_host = sum(e["has_host_association"] for e in E)
    m("has_host_association", n_host, N, "source records with a reported or ambiguous host value")
    host_only = [e for e in E if "host_association_only" in e["flags"]]
    m("host_association_only", len(host_only), N, "strict host-only: host value(s) reported (host status "
      "REPORTED or AMBIGUOUS), no usable value in any physical role (physical grade NOT_REPORTED)")
    # host metadata present but no usable physical habitat (has_usable_habitat = 0)
    host_no_res = [e for e in E if e["has_host_association"] and not e["has_usable_physical_habitat"]]
    m("host_without_usable_physical_habitat", len(host_no_res), N, "host metadata present (host REPORTED or "
      "AMBIGUOUS) and no usable physical habitat (grade not DIRECT_SAMPLE or VERIFIED_ISOLATE)")
    m("host_without_usable_physical_habitat:AMBIGUOUS", sum(e["grade"] == "AMBIGUOUS" for e in host_no_res), N,
      "of which the physical grade is AMBIGUOUS")
    m("physical_habitat_and_host_association", sum(e["has_usable_physical_habitat"] and e["has_host_association"]
                                                   for e in E), N, "usable physical habitat and host metadata")
    amb = [e for e in E if e["grade"] == "AMBIGUOUS"]
    ac = Counter(e["ambiguity_class"] for e in amb)
    for c in AMBIGUITY_CLASSES:
        m(f"ambiguity_class:{c}", ac[c], len(amb), f"physically AMBIGUOUS records of class {c}")
    hamb = [e for e in E if e["host_association_status"] == "AMBIGUOUS"]
    hac = Counter(e["host_ambiguity_class"] for e in hamb)
    for c in AMBIGUITY_CLASSES:
        m(f"host_ambiguity_class:{c}", hac[c], len(hamb), f"host-AMBIGUOUS records of class {c}")
    nr = [e for e in E if e["grade"] == "NOT_REPORTED"]
    sc = Counter(e["not_reported_scope"] for e in nr)
    for s in NR_SCOPES:
        m(f"not_reported_scope:{s}", sc[s], len(nr), f"NOT_REPORTED records with missingness scope {s}")
    m("no_traceable_sample_link", sum(e["sample_link"] == "none" for e in E), N,
      "no traceable INSDC or sample link; sample records could not be checked")
    m("no_traceable_sample_link:NOT_REPORTED", sum(e["sample_link"] == "none" for e in nr), len(nr),
      "NOT_REPORTED records without a traceable sample link")
    lc = Counter(e["literature_status"] for e in E)
    for s in LIT_STATUSES:
        m(f"literature_status:{s}", lc[s], N, f"source records with literature status {s}")
    m("host_tissue_isolation_source_only", sum("host_tissue_isolation_source_only" in e["flags"] for e in E), N,
      "isolation source names host tissue only (sampling context; no broad habitat inferred)")
    q_items = [i for e in E for g in e["items"].values() for i in g if i["quarantine"]]
    q_recs = {e["source_acc"] for e in E for g in e["items"].values() for i in g if i["quarantine"]}
    m("quarantined_values:records", len(q_recs), N, "records with a value excluded from standardized ontology displays")
    inv = [i for e in E for g in e["items"].values() for i in g if i["value_status"] == "invalid_placeholder"]
    inv_recs = {e["source_acc"] for e in E for g in e["items"].values() for i in g
                if i["value_status"] == "invalid_placeholder"}
    m("invalid_placeholder:records", len(inv_recs), N,
      "records with an invalid all-zero MIxS environment placeholder")
    m("multi_source_mrdb", multi, len(mrdbs), "MRDB accessions with more than one source record")
    m("multi_source_mrdb:grades_differ", grades_differ, multi, "multi-source MRDB accessions whose source records "
      "have different physical-habitat grades (no MRDB-level habitat is asserted)")

    # cross-check against the audit coverage summary (unit source_record, stratum all)
    audit = {(c["metric"]): (int(c["numerator"]), int(c["denominator"])) for c in cov
             if c["unit"] == "source_record" and c["stratum_type"] == "all"}
    xmap = {"has_host_association": "has_host_association", "host_association_only": "host_association_only",
            "physical_habitat_and_host_association": "physical_habitat_and_host_association"}
    for g in GRADES:
        xmap[f"grade:{g}"] = f"primary_grade:{g}"
    for s in HOST_STATUSES:
        xmap[f"host_association:{s}"] = f"host_association:{s}"
    for c in AMBIGUITY_CLASSES:
        xmap[f"ambiguity_class:{c}"] = f"ambiguity_class:{c}"
        xmap[f"host_ambiguity_class:{c}"] = f"host_ambiguity_class:{c}"
    for s in NR_SCOPES:
        xmap[f"not_reported_scope:{s}"] = f"not_reported_scope:{s}"
    byid = {x["id"]: x for x in metrics}
    checked_metrics = []
    for mine, theirs in sorted(xmap.items()):
        if theirs in audit:
            need((byid[mine]["numerator"], byid[mine]["denominator"]) == audit[theirs],
                 f"summary {mine} {byid[mine]['numerator']}/{byid[mine]['denominator']} != audit {theirs} {audit[theirs]}")
            checked_metrics.append(mine)
    need(len(checked_metrics) >= 20, f"too few metrics cross-checked against the audit ({len(checked_metrics)})")

    # contract expectations
    expect = {
        "physical_habitat_usable": n_phys, "has_host_association": n_host, "host_association_only": len(host_only),
        "host_without_usable_physical_habitat": len(host_no_res), "physical_ambiguous": len(amb),
        "host_ambiguous": len(hamb), "no_traceable_sample_link": byid["no_traceable_sample_link"]["numerator"],
        "literature_lookup_failed": lc["LOOKUP_FAILED"], "multi_source_mrdb": multi,
        "multi_source_grades_differ": grades_differ,
        "host_tissue_isolation_source_only": byid["host_tissue_isolation_source_only"]["numerator"],
        "quarantined_items": len(q_items), "quarantined_records": len(q_recs), "invalid_placeholder_items": len(inv),
    }
    for k, v in expect.items():
        need(v == exp[k], f"{k}: {v} != contract {exp[k]}")
    need(dict(gc) == {g: n for g, n in exp["grades"].items() if n}, f"grade totals {dict(gc)} != contract")

    summary = {"habitat_schema_version": HABITAT_SCHEMA_VERSION, "dataset_release": release,
               "audit_id": contract["audit"]["audit_id"], "audit_status": contract["audit"]["status"],
               "audit_status_reason": contract["audit"]["status_reason"],
               "denominators": {"source_records": N, "mrdb_accessions": len(mrdbs)},
               "metrics": metrics, "cross_checked_against_audit": checked_metrics,
               "interpretation": "Counts describe metadata availability in linked sample records and reviewed "
                                 "literature. They are not habitat frequencies, enrichment, ecological adaptation or "
                                 "biogeography."}
    out["habitat/summary.json"] = (dumps(summary).encode("utf-8"), len(metrics))

    files = [{"path": k, "sha256": sha256_bytes(b), "bytes": len(b), "records": n} for k, (b, n) in sorted(out.items())]
    man = {"habitat_schema_version": HABITAT_SCHEMA_VERSION, "dataset_release": release,
           "schema": SCHEMA_REL,
           "audit": {k: contract["audit"][k] for k in ("audit_id", "audit_version", "accepted_commit", "base_commit",
                                                        "status", "status_reason")},
           "inputs": [{"path": k, "sha256": v} for k, v in sorted(contract["inputs"].items())],
           "retrieval": {"cache_sha256": contract["retrieval_cache"]["sha256"],
                         "uniprot_release_headers": ret.get("uniprot_release_headers"),
                         "n_requests": ret.get("n_requests"), "database_sha256": ret.get("database_sha256"),
                         "network_requests_during_export": 0},
           "evidence_id_rules": {
               "HE": "HE + first 12 hex of sha256(source_acc|evidence_source|entity_accession|link_index|"
                     "field_original|value_original)",
               "HL": "HL + first 12 hex of sha256(pmid|doi|quote|scope followed by source_acc, no separator)",
               "null_serialization": "None",
               "empty_value": "an item value of null denotes a field present with an empty string; the HE hash uses "
                              "the empty string",
               "recomputed": len(seen)},
           "counts": {"source_records": N, "mrdb_accessions": len(mrdbs), "display_items": n_disp,
                      "multi_source_mrdb": multi, "multi_source_grades_differ": grades_differ},
           "display_groups": {g: list(rs) for g, rs in GROUPS.items()},
           "files": files, "n_files": len(files), "total_bytes": sum(f["bytes"] for f in files)}
    out["habitat/manifest.json"] = (dumps(man).encode("utf-8"), len(files))
    validate(repo, out, release)
    return out


def validate(repo: Path, out: dict[str, tuple[bytes, int]], release: str = "1.6.1") -> None:
    """JSON Schema (2020-12) validation of every habitat file; fails closed."""
    import jsonschema
    schema = json.loads((repo / SCHEMA_REL).read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    import fnmatch
    vals = {}
    for rel, (b, _) in out.items():
        pats = [p for p in schema["x-files"] if fnmatch.fnmatch(f"v{release}/{rel}", p)]
        need(len(pats) == 1, f"{rel}: no unique schema pattern")
        name = schema["x-files"][pats[0]]
        if name not in vals:
            vals[name] = jsonschema.Draft202012Validator({"$schema": schema["$schema"], "$defs": schema["$defs"],
                                                          "$ref": f"#/$defs/{name}"})
        err = next(iter(vals[name].iter_errors(json.loads(b))), None)
        need(err is None, f"{rel}: schema violation: {err.message if err else ''}")
