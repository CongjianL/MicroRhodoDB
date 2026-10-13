#!/usr/bin/env python
"""Independent re-implementation of the PR-7c.1a habitat record classification (round 3).

Written from habitat_field_dictionary_v3.md only, starting from the round-2 independent
re-implementation (reimpl2_prior_independent.py). No production code was consulted.

Usage:  python reimpl3.py [BASE_DIR [OUT_DIR]]
        (or environment variables VAL_BASE / VAL_OUT; default: current directory)
BASE_DIR must contain records.json, entities.json, literature_evidence.json.
Outputs: OUT_DIR/reimpl3_records.tsv, OUT_DIR/reimpl3_evidence.tsv
"""
import hashlib
import json
import os
import re
import sys
from collections import defaultdict, OrderedDict

import pandas as pd

BASE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("VAL_BASE", ".")
OUT = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("VAL_OUT", BASE)

# --------------------------------------------------------------------------------------
# Section 4: roles
# --------------------------------------------------------------------------------------
PHYSICAL_ROLES = ["env_broad_scale", "env_local_scale", "env_medium", "isolation_source"]
HOST_ROLES = ["host"]
HABITAT_ROLES = PHYSICAL_ROLES + HOST_ROLES
MIXS_ENV_ROLES = ["env_broad_scale", "env_local_scale", "env_medium"]

ROLE_TAGS = {
    "env_broad_scale": ["env broad scale", "broad scale environmental context", "env biome",
                        "environment (biome)", "environment biome", "biome"],
    "env_local_scale": ["env local scale", "local environmental context", "local scale environmental context",
                        "env feature", "environment (feature)", "environment feature", "feature"],
    "env_medium": ["env medium", "environmental medium", "env material", "environment (material)",
                   "environment material", "material"],
    "isolation_source": ["isolation source", "isolation source host associated",
                         "isolation source non host associated"],
    "host": ["host", "specific host", "host scientific name", "nat host", "natural host"],
    "habitat_nonstandard": ["environment", "habitat", "isolation site", "source of isolate", "seabed habitat"],
    "sample_material": ["tissue", "tissue type", "cell type", "cell line", "sample material", "dev stage",
                        "tissue lib", "sample type"],
    "host_detail": ["host body site", "host tissue sampled", "host taxid", "host tax id", "host common name",
                    "host body habitat", "host description", "body site", "plant body site", "plant structure",
                    "plant struc"],
    "country": ["geo loc name", "country", "geographic location (country and/or sea)",
                "geographic location (region and locality)"],
    "lat_lon": ["lat lon", "location"],
    "lat": ["latitude", "lat", "geographic location (latitude)"],
    "lon": ["longitude", "lon", "geographic location (longitude)"],
    "collection_date": ["collection date"],
    "depth": ["depth", "geographic location (depth)"],
    "strain": ["strain", "sub strain"],
    "isolate": ["isolate"],
    "environmental_sample": ["environmental sample"],
    "metagenome_source": ["metagenome source", "metagenomic source"],
    "package": ["ncbi submission package"],
    "checklist": ["ena checklist"],
    "organism": ["organism", "scientific name"],
    "investigation_type": ["investigation type"],
    # v3 s4: sample_title / sample_description come ONLY from the XML <TITLE>/<DESCRIPTION> elements;
    # attributes are never mapped to these roles.
}
ROLE_MAP = {}
for _role, _tags in ROLE_TAGS.items():
    for _t in _tags:
        ROLE_MAP[_t] = _role

ROLE_STATUS = {
    "habitat_nonstandard": "nonstandard_context",
    "sample_material": "material",
    "country": "geography", "lat_lon": "geography", "lat": "geography", "lon": "geography",
    "collection_date": "date",
    "depth": "depth",
}
MISSING_CAPABLE = set(ROLE_STATUS)  # these roles get reported_missing; context roles always keep context

SOURCE_FEATURE_FIELDS = ["isolation_source", "host", "country", "location", "collection_date", "strain", "isolate",
                         "sub_strain", "environmental_sample", "cell_type", "cell_line", "tissue_type", "tissue_lib",
                         "metagenome_source", "scientific_name"]

ROUTE_CONF = {"cds_protein_id": "HIGH", "embl_parent_sequence": "HIGH", "wgs_set": "HIGH",
              "insdc_flatfile_biosample": "HIGH", "uniparc_embl_protein": "MEDIUM",
              "proteome_assembly": "MEDIUM", "embl_xref_unresolved": ""}


def tag_key(t):
    t = "".join(ch for ch in (t or "") if 32 <= ord(ch) < 127).lower()
    return re.sub(r"[_\-\s]+", " ", t).strip()


def vnorm(v):
    return re.sub(r"\s+", " ", (v or "").strip().lower())


# --------------------------------------------------------------------------------------
# Section 5: value status
# --------------------------------------------------------------------------------------
MISSING_RE = re.compile(r"^(missing|not collected|not applicable|not provided|not available|not determined|"
                        r"restricted access|unknown|unspecified|na|n/a|n\.a\.|none|null|nan|-|--|\.|\?)"
                        r"(\s*[:;,(].*)?$", re.I)
ZERO_RE = re.compile(r"^0+(\.0+)?$")

ENVO_RE = re.compile(r"ENVO[:_ ]?(\d{7,8})")
PLACEHOLDER_IDS = {"ENVO:00010483", "ENVO:00000428", "ENVO:01000254", "ENVO:00002297", "ENVO:01001110",
                   "ENVO:00002036", "ENVO:01000813"}
PLACEHOLDER_TEXT = {"environmental material", "environment material", "biome", "environmental feature",
                    "environment", "environmental system", "environmental sample", "other", "sample"}

CULTURE_ALTS = [
    r"(axenic |pure |unialgal |clonal |laboratory |lab |cell |stock |batch |continuous )?cultures?",
    r"culture collection", r"strain collection", r"laboratory", r"cultured cells",
    r"(laboratory|lab) (strain|stock|isolate)s?", r"(cell|tissue) lines?", r"(viral )?plaques?",
    r".*\b(agar|broth)\b.*",
    r".*\b(culture|growth|isolation) media?$",
    r"[a-z0-9][a-z0-9+-]* medium",
]
CULTURE_RE = re.compile(r"^(?:" + "|".join("(?:%s)" % a for a in CULTURE_ALTS) + r")$", re.I)
TISSUE_TERMS = {"leaf", "leaves", "root", "roots", "stem", "stems", "shoot", "shoots", "flower", "flowers", "seed",
                "seeds", "fruit", "fruiting body", "fruiting bodies", "mycelium", "mycelia", "hyphae", "spores",
                "conidia", "whole organism", "whole body", "whole plant", "whole cell", "whole cells", "cells", "cell",
                "tissue", "thallus", "sporophyte", "gametophyte", "protonema", "rhizoid", "blade", "frond"}


def strip_one_dot(vn):
    return vn[:-1] if vn.endswith(".") else vn


def is_missing(vn):
    return vn == "" or bool(MISSING_RE.match(vn))


def extract_envo(v):
    ids = []
    for d in ENVO_RE.findall(v or ""):
        i = "ENVO:%08d" % int(d)
        if i not in ids:
            ids.append(i)
    return ids


def strip_envo_text(v):
    s = ENVO_RE.sub(" ", v or "")
    s = re.sub(r"[\[\(\{]\s*[\]\)\}]", " ", s)
    s = vnorm(s)
    s = s.strip(" \t[](){}:;,.-_|/")
    return vnorm(s)


def is_culture(vn):
    return bool(CULTURE_RE.fullmatch(strip_one_dot(vn)))


def is_tissue(vn):
    return strip_one_dot(vn) in TISSUE_TERMS


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------
def sha12(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def pid_nov(pid):
    return (pid or "").split(".")[0]


WGS_RE = re.compile(r"^([A-Z]{4,6}\d{2})\d{6,}$")
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                          "nov", "dec"])}


def light_norm(v):
    s = vnorm(v)
    return re.sub(r"\s*([:,;])\s*", r"\1", s)


def date_norm(v):
    s = light_norm(v)
    m = re.match(r"^(\d{1,2})-([a-z]{3})-(\d{4})$", s)
    if m and m.group(2) in MONTHS:
        return "%s-%02d-%02d" % (m.group(3), MONTHS[m.group(2)], int(m.group(1)))
    m = re.match(r"^([a-z]{3})-(\d{4})$", s)
    if m and m.group(1) in MONTHS:
        return "%s-%02d" % (m.group(2), MONTHS[m.group(1)])
    return s


def join_vals(vals):
    return " || ".join(sorted(set(v for v in vals if v != "")))


def join_ids(vals):
    return ";".join(sorted(set(v for v in vals if v != "")))


class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def f(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def u(self, a, b):
        a, b = self.f(a), self.f(b)
        if a != b:
            self.p[b] = a


def words(s):
    return set(re.sub(r"[^0-9a-z]+", " ", s.lower()).split())


def punct_norm(s):
    return " ".join(re.sub(r"[^0-9a-z]+", " ", s.lower()).split())


def lit_evidence_id(item, acc):
    # s3: "HL" + 12 hex of SHA-256 of `pmid|doi|quote|scope` followed by the source accession.
    # Literal reading: the accession is appended (no separator) to the hashed string.
    s = "%s|%s|%s|%s" % (item.get("pmid") or "", item.get("doi") or "", item.get("quote") or "",
                         item.get("scope") or "")
    return "HL" + sha12(s + acc)


def find_conflicts(usable_items, roles, unit_fn):
    """Section 6 agreement rule. Returns list of (role, scope, kind, groups)."""
    res = []
    for role in roles:
        ri = [it for it in usable_items if it["role"] == role]
        if len(ri) < 2:
            continue
        uf = UF(len(ri))
        for a in range(len(ri)):
            for b in range(a + 1, len(ri)):
                ia, ib = ri[a], ri[b]
                if ia["value_normalized"] == ib["value_normalized"] or \
                        (ia["envo_ids"] and set(ia["envo_ids"]) == set(ib["envo_ids"])):
                    uf.u(a, b)
        groups = defaultdict(list)
        for k, it in enumerate(ri):
            groups[uf.f(k)].append(it)
        if len(groups) <= 1:
            continue
        units = {unit_fn(it) for it in ri}
        scope = "within_sample_unit" if len(units) == 1 else "across_sample_units"
        glist = list(groups.values())
        pn = {punct_norm(it["value_normalized"]) for it in ri}
        if len(pn) == 1:
            kind = "punctuation_only"
        else:
            wsets = [set().union(*[words(it["value_normalized"]) for it in g]) for g in glist]
            if any(all(o <= w for o in wsets) for w in wsets):
                kind = "token_subset"
            else:
                kind = "distinct_values"
        res.append((role, scope, kind, glist))
    return res


def ambiguity_class(conf, lit_conflict):
    """Section 6 'Ambiguity interpretation' (first match wins)."""
    if not conf:
        return "LITERATURE_VS_DATABASE" if lit_conflict else ""
    kinds = [c[2] for c in conf]
    if all(k == "punctuation_only" for k in kinds):
        return "FORMATTING_ONLY"
    if all(k in ("punctuation_only", "token_subset") for k in kinds):
        return "NESTED_WORDING"
    if all(c[1] == "within_sample_unit" for c in conf if c[2] == "distinct_values"):
        return "DISTINCT_SAME_SAMPLE"
    return "DISTINCT_ACROSS_SAMPLES"


# --------------------------------------------------------------------------------------
# main per-record classification
# --------------------------------------------------------------------------------------
def classify(rec, E, LIT):
    acc = rec["source_acc"]
    flags = set()
    failures = []
    up = E["uniprot"].get(acc, {"status": "failed"})
    ust = up.get("status")
    if ust == "failed":
        failures.append("uniprot:%s" % acc)
    if ust in ("inactive", "not_found"):
        flags.add("uniprot_inactive")

    # ---- links (section 2)
    raw_links = []
    for e in up.get("embl", []) or []:
        raw_links.append({"protein_id": e.get("protein_id") or "", "parent_accession": e.get("parent_accession") or "",
                          "embl_status": e.get("status") or "", "molecule_type": e.get("molecule_type") or "",
                          "uniparc": False})
    upc = E["uniparc"].get(acc)
    if upc is not None:
        if upc.get("status") == "failed":
            failures.append("uniparc:%s" % acc)
        for pid in upc.get("embl_protein_ids", []) or []:
            raw_links.append({"protein_id": pid, "parent_accession": "", "embl_status": "uniparc",
                              "molecule_type": "", "uniparc": True})
            flags.add("uniparc_embl_link")
    raw_links.sort(key=lambda l: (l["protein_id"], l["parent_accession"]))

    links = []
    for idx, l in enumerate(raw_links):
        L = dict(l)
        L["link_index"] = idx
        L["samples"] = []
        L["row"] = None
        L["route"] = None
        pid = l["protein_id"]
        pa = l["parent_accession"]
        has_pid = pid not in ("", "-")
        cds_status = None
        if has_pid:
            c = E["cds"].get(pid_nov(pid))
            cds_status = c.get("status") if c else None
            if cds_status == "found":
                rows = c.get("rows") or []
                if rows:
                    L["row"] = rows[0]
                if len(rows) > 1:
                    flags.add("cds_multiple_rows")
                L["route"] = "uniparc_embl_protein" if l["uniparc"] else "cds_protein_id"
            elif cds_status == "failed":
                failures.append("ena_coding:%s" % pid)
        if L["route"] is None and cds_status != "failed" and (not has_pid or cds_status == "not_found") and pa:
            s = E["sequence"].get(pa)
            sst = s.get("status") if s else None
            if sst == "found":
                rows = s.get("rows") or []
                L["row"] = rows[0] if rows else None
                L["route"] = "embl_parent_sequence"
            elif sst == "failed":
                failures.append("ena_sequence:%s" % pa)
            elif sst == "not_found":
                wst = ""
                m = WGS_RE.match(pa)
                if m:
                    w = E["wgs_set"].get(m.group(1))
                    wst = w.get("status") if w else ""
                    if wst == "found":
                        L["route"] = "wgs_set"
                        rows = w.get("rows") or []
                        L["row"] = rows[0] if rows else None
                    elif wst == "failed":
                        failures.append("ena_wgs:%s" % m.group(1))
                if L["route"] is None and wst in ("", "not_found", None):
                    ff = E["insdc_flatfile"].get(pa)
                    fst = ff.get("status") if ff else None
                    if fst == "found" and ff.get("samples"):
                        L["route"] = "insdc_flatfile_biosample"
                        L["samples"] = list(ff.get("samples"))
                    elif fst == "failed":
                        failures.append("ena_flatfile:%s" % pa)
        if L["route"] is None:
            L["route"] = "embl_xref_unresolved"
            flags.add("insdc_record_unresolved")
        if L["row"] is not None:
            sa = [x.strip() for x in (L["row"].get("sample_accession") or "").split(";") if x.strip()]
            L["samples"] = sa + [x for x in L["samples"] if x not in sa]
        links.append(L)

    if not raw_links and ust == "active":
        for p in up.get("proteomes", []) or []:
            upid = p.get("proteome") if isinstance(p, dict) else p
            pr = E["proteome"].get(upid)
            pst = pr.get("status") if pr else None
            if pst == "failed":
                failures.append("proteome:%s" % upid)
                continue
            if pst != "found":
                continue
            bs = list(pr.get("biosamples") or [])
            if not bs and pr.get("assembly"):
                a = E["assembly"].get(pr["assembly"])
                ast = a.get("status") if a else None
                if ast == "failed":
                    failures.append("ena_assembly:%s" % pr["assembly"])
                elif ast == "found":
                    rows = a.get("rows") or []
                    if rows:
                        bs = [x.strip() for x in (rows[0].get("sample_accession") or "").split(";") if x.strip()]
            links.append({"protein_id": "", "parent_accession": upid, "embl_status": "", "molecule_type": "",
                          "uniparc": False, "link_index": len(links), "samples": bs, "row": None,
                          "route": "proteome_assembly", "proteome": upid, "assembly": pr.get("assembly")})
    if not links:
        flags.add("no_insdc_link")

    all_samples = []
    for L in links:
        for s in L["samples"]:
            if s not in all_samples:
                all_samples.append(s)
    if not all_samples:
        flags.add("no_biosample_link")
    elif len(all_samples) > 1:
        flags.add("multiple_biosamples")

    # ---- evidence items (section 3)
    items = []

    def add(src, ent, L, field_original, role, value, conf_route):
        if role is None:
            return
        vo = value if value is not None else ""
        vo = str(vo)
        items.append({"source_acc": acc, "evidence_source": src, "entity_accession": ent,
                      "link_index": L["link_index"], "field_original": field_original, "role": role,
                      "value_original": vo, "value_normalized": vnorm(vo), "linkage_route": conf_route,
                      "mapping_confidence": ROUTE_CONF.get(conf_route, ""),
                      "evidence_id": "HE" + sha12("%s|%s|%s|%s|%s|%s" % (acc, src, ent, L["link_index"],
                                                                         field_original, vo))})

    seen_samples = set()
    for L in links:
        if L["row"] is not None and L["route"] in ("cds_protein_id", "embl_parent_sequence", "uniparc_embl_protein",
                                                   "wgs_set"):
            ent = L["protein_id"] if L["route"] in ("cds_protein_id", "uniparc_embl_protein") else L["parent_accession"]
            for f in SOURCE_FEATURE_FIELDS:
                v = L["row"].get(f)
                if v is None or str(v).strip() in ("", "-"):
                    continue
                if f == "scientific_name":
                    add("insdc_source_feature", ent, L, "organism", "organism", str(v), L["route"])
                else:
                    add("insdc_source_feature", ent, L, f, ROLE_MAP.get(tag_key(f)), str(v), L["route"])
        for s in L["samples"]:
            if s in seen_samples:
                continue
            seen_samples.add(s)
            se = E["sample_ena"].get(s)
            sn = E["sample_ncbi"].get(s)
            est = se.get("status") if se else None
            nst = sn.get("status") if sn else None
            if est == "failed" or est == "ambiguous_match":
                failures.append("ena_sample:%s" % s)
            if nst == "failed":
                failures.append("ncbi_sample:%s" % s)
            if est == "not_found" and nst == "not_found":
                flags.add("sample_unresolvable")
            elif est == "not_found" or nst == "not_found":
                flags.add("sample_copy_absent")
            if est == "found":
                for a in se.get("attributes", []) or []:
                    tag = a.get("tag") or ""
                    add("ena_biosample", s, L, tag, ROLE_MAP.get(tag_key(tag)), a.get("value"), L["route"])
                if se.get("title"):
                    add("ena_biosample", s, L, "sample_title", "sample_title", se.get("title"), L["route"])
                if se.get("description"):
                    add("ena_biosample", s, L, "sample_description", "sample_description", se.get("description"),
                        L["route"])
            if nst == "found":
                for a in sn.get("attributes", []) or []:
                    name = a.get("name") or ""
                    hn = a.get("harmonized_name") or ""
                    key = hn or name
                    fo = name if (not hn or hn == name) else "%s (harmonized: %s)" % (name, hn)
                    add("ncbi_biosample", s, L, fo, ROLE_MAP.get(tag_key(key)), a.get("value"), L["route"])
                if sn.get("package"):
                    add("ncbi_biosample", s, L, "package", "package", sn.get("package"), L["route"])
                if sn.get("title"):
                    add("ncbi_biosample", s, L, "sample_title", "sample_title", sn.get("title"), L["route"])
                if sn.get("description"):
                    add("ncbi_biosample", s, L, "sample_description", "sample_description", sn.get("description"),
                        L["route"])

    # ---- organism names for host_is_self
    rec_taxid = str(rec.get("organism_id") or "")
    up_taxid = str(up.get("taxon_id") or "")
    org_names = set()
    for n in [up.get("organism"), rec.get("organism")] + [it["value_original"] for it in items
                                                          if it["evidence_source"] == "insdc_source_feature"
                                                          and it["role"] == "organism"]:
        if n:
            org_names.add(vnorm(n))
    binomials = set()
    for n in org_names:
        w = n.split()
        if len(w) >= 2 and w[1] not in ("sp", "sp."):
            binomials.add(" ".join(w[:2]))
    lineage = up.get("organism_lineage") or []
    viral = bool(lineage) and lineage[0] == "Viruses"
    taxids = {t for t in (rec_taxid, up_taxid) if t}
    host_taxids_by_ent = defaultdict(set)
    for it in items:
        if it["role"] == "host_detail" and tag_key(it["field_original"].split(" (harmonized: ")[-1].rstrip(")")) \
                in ("host taxid", "host tax id"):
            host_taxids_by_ent[it["entity_accession"]].add(it["value_normalized"])

    def host_self(it):
        vn = it["value_normalized"]
        if vn in taxids or (host_taxids_by_ent[it["entity_accession"]] & taxids):
            return True
        if vn in org_names:
            return True
        if not viral:
            w = vn.split()
            if len(w) >= 2 and " ".join(w[:2]) in binomials:
                return True
        return False

    # ---- ENVO + value status (section 5)
    for it in items:
        it["envo_ids"] = []
        if it["role"] in HABITAT_ROLES or it["role"] == "habitat_nonstandard":
            kept = []
            for i in extract_envo(it["value_original"]):
                st = E["envo"].get(i, {}).get("status")
                if st == "not_found":
                    flags.add("envo_id_invalid")
                elif st == "failed":
                    flags.add("envo_lookup_failed")
                else:
                    kept.append(i)
            it["envo_ids"] = kept

    for it in items:
        vn = it["value_normalized"]
        r = it["role"]
        if r in HABITAT_ROLES:
            if is_missing(vn):
                st = "reported_missing"
            elif r in MIXS_ENV_ROLES and ZERO_RE.fullmatch(vn):
                st = "invalid_placeholder"
                flags.add("invalid_placeholder_value")
            elif r == "host" and host_self(it):
                st = "host_is_self"
                flags.add("host_is_self_ignored")
            elif (it["envo_ids"] and all(i in PLACEHOLDER_IDS for i in it["envo_ids"])) or \
                    strip_envo_text(it["value_original"]) in PLACEHOLDER_TEXT:
                st = "uninformative_placeholder"
            elif is_culture(vn):
                st = "moved_to_material"
            else:
                st = "usable"
        elif r in MISSING_CAPABLE:
            st = "reported_missing" if is_missing(vn) else ROLE_STATUS[r]
        else:
            st = "context"
        it["value_status"] = st
    # tissue rule (isolation_source only), with non-self host exemption on the same sample entity
    nonself_host_ents = {it["entity_accession"] for it in items
                         if it["role"] == "host" and it["value_status"] == "usable"}
    host_assoc_tissue = []
    for it in items:
        if it["role"] == "isolation_source" and it["value_status"] == "usable" and is_tissue(it["value_normalized"]):
            if it["entity_accession"] in nonself_host_ents:
                host_assoc_tissue.append(it)
            else:
                it["value_status"] = "moved_to_material"

    usable_all = [it for it in items if it["role"] in HABITAT_ROLES and it["value_status"] == "usable"]
    usable_phys = [it for it in usable_all if it["role"] in PHYSICAL_ROLES]
    usable_host = [it for it in usable_all if it["role"] in HOST_ROLES]
    if host_assoc_tissue:
        flags.add("host_associated_isolation_source")
        if all(it["role"] == "isolation_source" and is_tissue(it["value_normalized"]) for it in usable_phys):
            flags.add("host_tissue_isolation_source_only")

    # ---- agreement (section 6)
    link_by_idx = {L["link_index"]: L for L in links}

    def unit(it):
        if it["evidence_source"] in ("ena_biosample", "ncbi_biosample"):
            return "S:" + it["entity_accession"]
        L = link_by_idx[it["link_index"]]
        if len(L["samples"]) == 1:
            return "S:" + L["samples"][0]
        return "L:%d" % it["link_index"]

    conf_all = find_conflicts(usable_all, HABITAT_ROLES, unit)
    conf_phys = [c for c in conf_all if c[0] in PHYSICAL_ROLES]
    conf_host = [c for c in conf_all if c[0] in HOST_ROLES]
    db_conflict = bool(conf_phys)
    host_conflict = bool(conf_host)

    # ---- literature (section 9)
    lit = LIT.get(acc)
    lit_status = lit["literature_status"] if lit is not None else "NOT_SEARCHED"
    lit_iso, lit_org, lit_all = [], [], []
    if lit is not None:
        for i in lit.get("items", []):
            lit_all.append(i)
            if not i.get("parent_verified"):
                continue
            if i.get("scope") == "isolate":
                lit_iso.append(i)
            elif i.get("scope") == "organism":
                lit_org.append(i)
    lit_inconsistent = any(i.get("consistent_with_db") == "inconsistent" for i in lit_iso)
    lit_conflict = bool(usable_phys) and lit_inconsistent

    # ---- grades (section 1)
    if failures:
        db_grade = "LOOKUP_FAILED"
    elif db_conflict:
        db_grade = "AMBIGUOUS"
    elif usable_phys:
        db_grade = "DIRECT_SAMPLE"
    else:
        db_grade = "NOT_REPORTED"
    if failures:
        grade = "LOOKUP_FAILED"
    elif db_conflict or lit_conflict:
        grade = "AMBIGUOUS"
    elif usable_phys:
        grade = "DIRECT_SAMPLE"
    elif lit_iso:
        grade = "VERIFIED_ISOLATE"
    elif lit_org:
        grade = "ORGANISM_CONTEXT_ONLY"
    else:
        grade = "NOT_REPORTED"

    if failures:
        hstat = "LOOKUP_FAILED"
    elif host_conflict:
        hstat = "AMBIGUOUS"
    elif usable_host:
        hstat = "REPORTED"
    else:
        hstat = "NOT_REPORTED"

    # ---- legacy PR-7c.1 grade: host counted as habitat, 0 placeholder usable, lit conflict vs any usable value
    usable_legacy = [it for it in items if it["role"] in HABITAT_ROLES
                     and it["value_status"] in ("usable", "invalid_placeholder")]
    conf_legacy = find_conflicts(usable_legacy, HABITAT_ROLES, unit)
    lit_conflict_legacy = bool(usable_legacy) and lit_inconsistent
    if failures:
        legacy = "LOOKUP_FAILED"
    elif conf_legacy or lit_conflict_legacy:
        legacy = "AMBIGUOUS"
    elif usable_legacy:
        legacy = "DIRECT_SAMPLE"
    elif lit_iso:
        legacy = "VERIFIED_ISOLATE"
    elif lit_org:
        legacy = "ORGANISM_CONTEXT_ONLY"
    else:
        legacy = "NOT_REPORTED"

    if failures:
        chain = "INCOMPLETE"
    elif not links:
        chain = "NO_LINK"
    else:
        chain = "COMPLETE"
    nrs = ""
    if grade == "NOT_REPORTED":
        if lit_status == "NOT_SEARCHED":
            nrs = "database_only_literature_not_reviewed"
        elif lit_status == "LOOKUP_FAILED":
            nrs = "database_only_literature_inaccessible"
        elif lit_status == "NOT_REPORTED":
            nrs = "database_and_literature"
        else:
            nrs = "database_only_literature_%s" % lit_status.lower()

    amb_class = ambiguity_class(conf_phys, lit_conflict) if grade == "AMBIGUOUS" else ""
    host_amb_class = ambiguity_class(conf_host, False) if hstat == "AMBIGUOUS" else ""

    if db_conflict:
        flags.add("conflict")
    if lit_conflict:
        # ASSUMPTION: as in PR-7c.1, a literature conflict also carries the generic `conflict` flag.
        flags.add("conflict")
        flags.add("literature_conflict")
    if host_conflict:
        flags.add("host_conflict")
    if usable_host and not usable_phys:
        flags.add("host_association_only")

    if grade == "DIRECT_SAMPLE":
        nunits = len(all_samples) + sum(1 for L in links if L["route"] in ("cds_protein_id", "embl_parent_sequence",
                                                                           "uniparc_embl_protein") and not L["samples"])
        if nunits > 1:
            flags.add("multi_sample")
    countries = {light_norm(it["value_original"]) for it in items
                 if it["role"] == "country" and it["value_status"] != "reported_missing"}
    if len(countries) > 1:
        flags.add("geo_discordant")
    dates = {date_norm(it["value_original"]) for it in items
             if it["role"] == "collection_date" and it["value_status"] != "reported_missing"}
    if len(dates) > 1:
        flags.add("date_discordant")
    if not usable_all and any(it["role"] in ("sample_title", "sample_description")
                              and it["value_original"].strip() != "" for it in items):
        flags.add("free_text_context_only")
    if any(it["role"] in HABITAT_ROLES and it["value_status"] == "reported_missing" for it in items):
        flags.add("habitat_reported_missing")
    if int(rec.get("is_engineered") or 0):
        flags.add("engineered_record")
    material_vals = [it["value_original"] for it in items if it["value_status"] in ("moved_to_material", "material")]
    if material_vals and grade not in ("DIRECT_SAMPLE", "AMBIGUOUS"):
        flags.add("tissue_or_culture_only")

    # ---- sample type (section 7)
    pk = [it["value_normalized"] for it in items if it["role"] in ("package", "checklist")
          and not is_missing(it["value_normalized"])]
    orgmg = [it["value_normalized"] for it in items if it["role"] in ("organism", "metagenome_source")]
    envs = [it["value_normalized"] for it in items if it["role"] == "environmental_sample"]
    strains = [it for it in items if it["role"] == "strain" and not is_missing(it["value_normalized"])]
    moltypes = set()
    for L in links:
        if L.get("molecule_type"):
            moltypes.add(L["molecule_type"])
        if L["row"] is not None and L["row"].get("mol_type"):
            moltypes.add(L["row"]["mol_type"])
    if any(("mimag" in p or "erc000047" in p or "metagenome-assembled" in p) for p in pk):
        stype = "MAG"
    elif any(("misag" in p or "erc000048" in p) for p in pk):
        stype = "SAG"
    elif any("mims" in p for p in pk) or any("metagenome" in o for o in orgmg) or \
            any(re.search(r"\bmetagenome\b", p) for p in pk):
        stype = "METAGENOME_ASSEMBLY"
    elif any(e in ("true", "yes", "1") for e in envs):
        stype = "ENVIRONMENTAL_CLONE"
    elif any(any(x in p for x in ("migs.ba", "migs.eu", "microbe", "pathogen")) for p in pk) or \
            (strains and any(e in ("false", "no", "0") for e in envs)):
        stype = "ISOLATE_GENOME"
    elif moltypes and all(m.lower().replace("_", " ") in ("mrna", "transcribed rna") for m in moltypes):
        stype = "TRANSCRIPTOME"
    else:
        stype = "UNKNOWN"

    # ---- mapping confidence (section 8, physical axis)
    def conf_from_usable():
        return "HIGH" if any(it["mapping_confidence"] == "HIGH" for it in usable_phys) else "MEDIUM"
    if grade == "DIRECT_SAMPLE":
        mc = conf_from_usable()
    elif grade == "VERIFIED_ISOLATE":
        mc = "LITERATURE"
    elif grade == "AMBIGUOUS":
        mc = conf_from_usable() if db_conflict else "LITERATURE"
    else:
        mc = ""

    # ---- literature evidence items (section 9)
    lit_items = []
    for i in lit_all:
        sc = i.get("scope")
        if sc == "isolate":
            role, vs = "literature_isolate", "usable"
        elif sc == "organism":
            role, vs = "organism_context", "organism_context"
        else:
            role, vs = "literature_rejected", "rejected:%s" % (i.get("parent_decision_reason") or "")
        lit_items.append({"source_acc": acc, "evidence_source": "literature", "entity_accession": "",
                          "link_index": "", "field_original": "literature:%s | %s" % (sc, i.get("locator") or ""),
                          "role": role, "value_original": i.get("quote") or "",
                          "value_normalized": vnorm(i.get("habitat_text") or ""), "linkage_route": "",
                          "mapping_confidence": "", "envo_ids": [], "value_status": vs,
                          "evidence_id": lit_evidence_id(i, acc),
                          "_verified_isolate": bool(i.get("parent_verified")) and sc == "isolate"})

    out = OrderedDict()
    out["source_acc"] = acc
    out["primary_grade"] = grade
    out["pr7c1_grade"] = legacy
    out["db_habitat_status"] = db_grade
    out["db_chain_status"] = chain
    out["literature_status"] = lit_status
    out["not_reported_scope"] = nrs
    out["has_usable_habitat"] = "1" if grade in ("DIRECT_SAMPLE", "VERIFIED_ISOLATE") else "0"
    out["host_association_status"] = hstat
    out["has_host_association"] = "1" if hstat in ("REPORTED", "AMBIGUOUS") else "0"
    out["ambiguity_class"] = amb_class
    out["host_ambiguity_class"] = host_amb_class
    out["conflict_roles"] = ";".join(c[0] for c in conf_all)
    out["conflict_scope"] = ";".join("%s:%s" % (c[0], c[1]) for c in conf_all)
    out["conflict_kind"] = ";".join("%s:%s" % (c[0], c[2]) for c in conf_all)
    out["chain_failures"] = ";".join(failures)
    for role in HABITAT_ROLES:
        ri = [it for it in usable_all if it["role"] == role]
        out[role + "_original"] = join_vals([it["value_original"] for it in ri])
        out[role + "_normalized"] = join_vals([it["value_normalized"] for it in ri])
        out[role + "_envo_ids"] = join_ids([i for it in ri for i in it["envo_ids"]])
    for role in ("country", "lat_lon", "lat", "lon", "collection_date", "depth"):
        out[role] = join_vals([it["value_original"] for it in items
                               if it["role"] == role and it["value_status"] != "reported_missing"])
    out["habitat_nonstandard"] = join_vals(["%s: %s" % (it["field_original"], it["value_original"]) for it in items
                                            if it["value_status"] == "nonstandard_context"])
    out["sample_material"] = join_vals(material_vals)
    out["sample_type"] = stype
    out["molecule_types"] = join_ids(moltypes)
    out["biosamples"] = join_ids(all_samples)
    out["linkage_route"] = join_ids([L["route"] for L in links])
    out["mapping_confidence"] = mc
    out["flags"] = ";".join(sorted(flags))
    out["evidence_ids"] = join_ids([it["evidence_id"] for it in usable_all] +
                                   [li["evidence_id"] for li in lit_items if li["_verified_isolate"]])
    for li in lit_items:
        del li["_verified_isolate"]
    return out, items + lit_items


def main():
    R = json.load(open(os.path.join(BASE, "records.json")))
    E = json.load(open(os.path.join(BASE, "entities.json")))
    LIT = json.load(open(os.path.join(BASE, "literature_evidence.json")))
    rows, ev = [], []
    for rec in R:
        o, items = classify(rec, E, LIT)
        rows.append(o)
        for it in items:
            ev.append({k: (";".join(v) if isinstance(v, list) else v) for k, v in it.items()})
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "reimpl3_records.tsv"), sep="\t", index=False)
    pd.DataFrame(ev).to_csv(os.path.join(OUT, "reimpl3_evidence.tsv"), sep="\t", index=False)
    print("wrote", len(rows), "records,", len(ev), "items")


if __name__ == "__main__":
    main()
