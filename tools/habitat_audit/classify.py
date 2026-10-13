"""Stage 3: deterministic per-record evidence assembly and grading.

Input: frozen record identity (baseline.load_records), the entity store derived
from the raw cache (retrieve.retrieve_all) and the parent-verified literature
evidence. Output: record rows, provenance-link rows and evidence rows.
Rules are documented in docs/website/pr7c1/habitat_field_dictionary.md.
"""
from __future__ import annotations

import hashlib
import re

from . import normalize as N
from .retrieve import envo_ids_in, strip_version

SOURCE_FEATURE_FIELDS = (  # ENA coding / sequence columns copied from the INSDC source feature
    "isolation_source", "host", "country", "location", "collection_date", "strain", "isolate", "sub_strain",
    "environmental_sample", "cell_type", "cell_line", "tissue_type", "tissue_lib", "metagenome_source",
)
GEO_ROLES = ("country", "lat_lon", "lat", "lon")
SEP = " || "  # separator between distinct alternative values in record-table cells


def _browser_url(kind: str, acc: str) -> str:
    if kind == "ncbi_biosample":
        return f"https://www.ncbi.nlm.nih.gov/biosample/{acc}"
    if kind == "uniprot":
        return f"https://www.uniprot.org/uniprotkb/{acc}/entry"
    if kind == "proteome":
        return f"https://www.uniprot.org/proteomes/{acc}"
    return f"https://www.ebi.ac.uk/ena/browser/view/{acc}"


class _UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, i):
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def distinct_groups(items: list[dict]) -> list[list[dict]]:
    """Agreement rule: same normalized string, or identical non-empty explicit ENVO-ID sets."""
    uf = _UF(len(items))
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            if a["value_normalized"] == b["value_normalized"] or (
                    a["envo_ids"] and a["envo_ids"] == b["envo_ids"]):
                uf.union(i, j)
    groups: dict[int, list] = {}
    for i, it in enumerate(items):
        groups.setdefault(uf.find(i), []).append(it)
    return sorted(groups.values(), key=lambda g: sorted(x["value_normalized"] for x in g))


def _alnum(v: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-z]+", " ", (v or "").lower())).strip()


def conflict_kind(groups: list[list[dict]]) -> str:
    """Descriptive diagnostic only (never changes the grade):
    punctuation_only  - groups become identical when punctuation is ignored;
    token_subset      - one group's word set contains every other group's words;
    distinct_values   - anything else."""
    forms = {_alnum(g[0]["value_normalized"]) for g in groups}
    if len(forms) == 1:
        return "punctuation_only"
    toks = [set(f.split()) for f in forms]
    if any(all(t <= big for t in toks) for big in toks):
        return "token_subset"
    return "distinct_values"


def conflict_scope(role_items: list[dict], link_samples: dict) -> str:
    """within_sample_unit when every disagreeing value belongs to the same sample unit (an INSDC
    source feature counts as part of its linked BioSample when the link has exactly one)."""
    units = set()
    for it in role_items:
        if it["evidence_source"] == "insdc_source_feature":
            ss = link_samples.get(it["link_index"], [])
            units.add(ss[0] if len(ss) == 1 else f"link{it['link_index']}")
        else:
            units.add(it["entity_accession"])
    return "within_sample_unit" if len(units) == 1 else "across_sample_units"


def ambiguity_class(diag: list[tuple[str, str, str]], lit_conflict: bool) -> str:
    """Interpretation of an AMBIGUOUS axis (PR-7c.1a). Descriptive only; never resolves a value.
    diag holds (role, conflict_scope, conflict_kind) for the conflicting roles of ONE axis.
    FORMATTING_ONLY          every conflict is punctuation_only (case/whitespace already ignored);
    NESTED_WORDING           every conflict is punctuation_only or token_subset (one value nests the other);
    DISTINCT_SAME_SAMPLE     distinct wording, but every distinct-value conflict lies within one sample unit
                             (possible synonym or submitter inconsistency; not resolved without evidence);
    DISTINCT_ACROSS_SAMPLES  distinct values from different sample units (genuine environmental-conflict candidate);
    LITERATURE_VS_DATABASE   no database-internal conflict; a verified isolate-scope literature statement is
                             inconsistent with the database value."""
    if not diag:
        return "LITERATURE_VS_DATABASE" if lit_conflict else ""
    kinds = {k for _, _, k in diag}
    if kinds == {"punctuation_only"}:
        return "FORMATTING_ONLY"
    if kinds <= {"punctuation_only", "token_subset"}:
        return "NESTED_WORDING"
    scopes = {sc for _, sc, k in diag if k == "distinct_values"}
    return "DISTINCT_SAME_SAMPLE" if scopes == {"within_sample_unit"} else "DISTINCT_ACROSS_SAMPLES"


def not_reported_scope(grade: str, lit_status: str) -> str:
    """Why a record is NOT_REPORTED (PR-7c.1a): database-level absence is always established; the
    literature side is distinguished as not reviewed (outside the seed/characterized subset),
    inaccessible (lookup failed) or reviewed-and-absent."""
    if grade != "NOT_REPORTED":
        return ""
    return {"NOT_SEARCHED": "database_only_literature_not_reviewed",
            "LOOKUP_FAILED": "database_only_literature_inaccessible",
            "NOT_REPORTED": "database_and_literature"}.get(lit_status, f"database_only_literature_{lit_status.lower()}")


def _item(acc, source, entity, link_index, field, value, request_key, route, confidence):
    role = N.role_for(field)
    return {"source_acc": acc, "evidence_source": source, "entity_accession": entity, "link_index": link_index,
            "field_original": field, "role": role, "value_original": value,
            "value_normalized": N.norm_value(value), "envo_ids": envo_ids_in(value),
            "request_key": request_key, "linkage_route": route, "mapping_confidence": confidence,
            "value_status": None}


def _sample_items(acc, s_acc, link_index, route, conf, ena, ncbi) -> list[dict]:
    out = []
    if ena and ena.get("status") == "found":
        for a in ena.get("attributes", []):
            if N.role_for(a["tag"]):
                out.append(_item(acc, "ena_biosample", s_acc, link_index, a["tag"], a["value"], ena["request_key"], route, conf))
        for fld, val in (("sample_title", ena.get("title")), ("sample_description", ena.get("description"))):
            if val:
                it = _item(acc, "ena_biosample", s_acc, link_index, fld, val, ena["request_key"], route, conf)
                it["role"] = fld
                out.append(it)
    if ncbi and ncbi.get("status") == "found":
        key = ncbi.get("request_key")
        for a in ncbi.get("attributes", []):
            name = a.get("harmonized_name") or a.get("name")
            if N.role_for(name):
                it = _item(acc, "ncbi_biosample", s_acc, link_index, name, a["value"], key, route, conf)
                it["field_original"] = a.get("name") if a.get("name") == name else f"{a.get('name')} (harmonized: {name})"
                it["role"] = N.role_for(name)
                out.append(it)
        if ncbi.get("package"):
            it = _item(acc, "ncbi_biosample", s_acc, link_index, "package", ncbi["package"], key, route, conf)
            it["role"] = "package"
            out.append(it)
        for fld, val in (("sample_title", ncbi.get("title")), ("sample_description", ncbi.get("description"))):
            if val:
                it = _item(acc, "ncbi_biosample", s_acc, link_index, fld, val, key, route, conf)
                it["role"] = fld
                out.append(it)
    return out


def _sample_type(items: list[dict], mol_types: list[str]) -> str:
    """Explicit fields only (package, ENA checklist, environmental_sample flag, metagenome organism, molecule type)."""
    pk = " ".join(i["value_normalized"] for i in items if i["role"] in ("package", "checklist", "investigation_type"))
    org = " ".join(i["value_normalized"] for i in items if i["role"] in ("organism", "metagenome_source"))
    env = {i["value_normalized"] for i in items if i["role"] == "environmental_sample"}
    if "mimag" in pk or "erc000047" in pk or "metagenome-assembled" in pk:
        return "MAG"
    if "misag" in pk or "erc000048" in pk:
        return "SAG"
    if "mims" in pk or "metagenome" in org or re.search(r"\bmetagenome\b", pk):
        return "METAGENOME_ASSEMBLY"
    if "true" in env:
        return "ENVIRONMENTAL_CLONE"
    has_strain = any(i["role"] in ("strain",) and not N.is_missing(i["value_original"]) for i in items)
    if any(p in pk for p in ("migs.ba", "migs.eu", "microbe", "pathogen")) or (has_strain and "false" in env):
        return "ISOLATE_GENOME"
    mt = {m.lower() for m in mol_types if m and m != "-"}
    if mt and all(m in ("mrna", "transcribed rna") for m in mt):
        return "TRANSCRIPTOME"
    return "UNKNOWN"


def classify_record(rec: dict, ent: dict, lit: dict | None, searched: bool) -> tuple[dict, list[dict], list[dict]]:
    acc = rec["source_acc"]
    row = {k: rec[k] for k in ("source_acc", "mrdb_acc", "counted", "is_engineered", "membership_status",
                               "status_group", "status_group_audit", "evidence_level", "domain", "phylum", "reviewed",
                               "source_release", "sequence_sha256", "seq_group_size", "exact_duplicate_of",
                               "is_seed", "is_characterized")}
    in_lit_subset = bool(rec["is_seed"] or rec["is_characterized"])
    flags: set[str] = set()
    if not searched:
        row.update(primary_grade="NOT_SEARCHED", pr7c1_grade="NOT_SEARCHED", db_chain_status="NOT_SEARCHED",
                   literature_status="NOT_SEARCHED", host_association_status="NOT_SEARCHED",
                   has_usable_habitat=0, has_host_association=0, flags="", not_reported_scope="")
        return row, [], []

    failures: list[str] = []
    links: list[dict] = []
    items: list[dict] = []
    up = ent["uniprot"].get(acc, {"status": "failed", "request_key": None})
    row["uniprot_status"] = up["status"]
    row["uniprot_organism"] = up.get("organism")
    row["uniprot_taxon_id"] = up.get("taxon_id")
    if up["status"] == "failed":
        failures.append("uniprot")
    if up["status"] in ("inactive", "not_found"):
        flags.add("uniprot_inactive")
    if up.get("sequence_sha256") and up["sequence_sha256"] != rec["sequence_sha256"]:
        flags.add("uniprot_sequence_changed")
    if up["status"] == "active_secondary":
        flags.add("uniprot_secondary_accession")

    embl = list(up.get("embl") or [])
    for pid in ent.get("uniparc", {}).get(acc, {}).get("embl_protein_ids", []):
        embl.append({"parent_accession": None, "protein_id": pid, "status": "uniparc", "molecule_type": "-"})
        flags.add("uniparc_embl_link")
    if ent.get("uniparc", {}).get(acc, {}).get("status") == "failed":
        failures.append("uniparc")

    for li, x in enumerate(sorted(embl, key=lambda x: (x["protein_id"] or "", x["parent_accession"] or ""))):
        L = {"source_acc": acc, "link_index": li, "route": None, "mapping_confidence": "HIGH",
             "embl_parent": x["parent_accession"], "protein_id": x["protein_id"], "embl_status": x["status"],
             "molecule_type": x["molecule_type"], "cds_status": "", "sequence_status": "", "wgs_status": "", "flatfile_status": "",
             "proteome": "", "proteome_status": "", "assembly": "", "assembly_status": "",
             "samples": [], "studies": [], "request_keys": [], "_row": None}
        if x["status"] == "uniparc":
            L["mapping_confidence"] = "MEDIUM"
        pid = strip_version(x["protein_id"]) if x["protein_id"] not in ("-", "", None) else None
        if pid:
            c = ent["cds"].get(pid, {"status": "failed"})
            L["cds_status"] = c["status"]
            L["request_keys"].append(c.get("request_key"))
            if c["status"] == "failed":
                failures.append(f"ena_coding:{pid}")
            elif c["status"] == "found":
                L["route"], L["_row"] = ("uniparc_embl_protein" if x["status"] == "uniparc" else "cds_protein_id"), c["rows"][0]
                if len(c["rows"]) > 1:
                    flags.add("cds_multiple_rows")
        if L["route"] is None and x["parent_accession"] and (not pid or L["cds_status"] == "not_found"):
            pa = strip_version(x["parent_accession"])
            s = ent["sequence"].get(pa, {"status": "failed"})
            L["sequence_status"] = s["status"]
            L["request_keys"].append(s.get("request_key"))
            if s["status"] == "failed":
                failures.append(f"ena_sequence:{pa}")
            elif s["status"] == "found":
                L["route"], L["_row"] = "embl_parent_sequence", s["rows"][0]
            else:
                m = re.match(r"^([A-Z]{4,6}\d{2})\d{6,}$", pa)
                if m:
                    w = ent.get("wgs_set", {}).get(m.group(1), {"status": "failed"})
                    L["wgs_status"] = w["status"]
                    L["request_keys"].append(w.get("request_key"))
                    if w["status"] == "failed":
                        failures.append(f"ena_wgs_set:{m.group(1)}")
                    elif w["status"] == "found":
                        L["route"], L["_row"] = "wgs_set", w["rows"][0]
            if L["route"] is None and L["sequence_status"] == "not_found" and L["wgs_status"] in ("", "not_found"):
                ff = ent.get("insdc_flatfile", {}).get(pa)
                if ff is not None:
                    L["flatfile_status"] = ff["status"]
                    L["request_keys"].append(ff.get("request_key"))
                    if ff["status"] == "failed":
                        failures.append(f"ena_flatfile:{pa}")
                    elif ff["status"] == "found" and ff.get("samples"):
                        L["route"] = "insdc_flatfile_biosample"
                        L["samples"] = list(ff["samples"])
                        L["studies"] = list(ff.get("studies") or [])
        if L["route"] is None:
            L["route"] = "embl_xref_unresolved"
            flags.add("insdc_record_unresolved")
        links.append(L)

    if not embl and up["status"] in ("active", "active_secondary"):
        for p in sorted(up.get("proteomes") or [], key=lambda p: p["proteome"]):
            pr = ent["proteome"].get(p["proteome"], {"status": "failed"})
            L = {"source_acc": acc, "link_index": len(links), "route": "proteome_assembly",
                 "mapping_confidence": "MEDIUM", "embl_parent": "", "protein_id": "", "embl_status": "",
                 "molecule_type": "", "cds_status": "", "sequence_status": "", "wgs_status": "",
                 "flatfile_status": "", "proteome": p["proteome"], "proteome_status": pr["status"], "assembly": pr.get("assembly") or "",
                 "assembly_status": "", "samples": [], "studies": [], "request_keys": [pr.get("request_key")],
                 "_row": None}
            if pr["status"] == "failed":
                failures.append(f"proteome:{p['proteome']}")
            elif pr["status"] == "found":
                L["samples"] = list(pr.get("biosamples") or [])
                if not L["samples"] and pr.get("assembly"):
                    a = ent["assembly"].get(pr["assembly"], {"status": "failed"})
                    L["assembly_status"] = a["status"]
                    L["request_keys"].append(a.get("request_key"))
                    if a["status"] == "failed":
                        failures.append(f"ena_assembly:{pr['assembly']}")
                    elif a["status"] == "found":
                        L["_row"] = a["rows"][0]
            links.append(L)

    if not links:
        flags.add("no_insdc_link")
    mol_types = [L["molecule_type"] for L in links]
    for L in links:
        r = L["_row"]
        if r:
            for s in (r.get("sample_accession") or "").split(";"):
                if s.strip() and s.strip() not in L["samples"]:
                    L["samples"].append(s.strip())
            L["studies"] = sorted({s.strip() for s in (r.get("study_accession") or "").split(";") if s.strip()})
            if r.get("mol_type"):
                mol_types.append(r["mol_type"])
            if L["route"] in ("cds_protein_id", "embl_parent_sequence", "uniparc_embl_protein"):
                ent_acc = L["embl_parent"] if L["route"] == "embl_parent_sequence" else L["protein_id"]
                for f in SOURCE_FEATURE_FIELDS:
                    v = r.get(f)
                    if v:
                        it = _item(acc, "insdc_source_feature", ent_acc, L["link_index"], f, v,
                                   L["request_keys"][-1], L["route"], L["mapping_confidence"])
                        items.append(it)
                if r.get("scientific_name"):
                    it = _item(acc, "insdc_source_feature", ent_acc, L["link_index"], "organism",
                               r["scientific_name"], L["request_keys"][-1], L["route"], L["mapping_confidence"])
                    items.append(it)
        L["samples"] = sorted(set(L["samples"]))

    samples = sorted({s for L in links for s in L["samples"]})
    if not samples:
        flags.add("no_biosample_link")
    if len(samples) > 1:
        flags.add("multiple_biosamples")
    sample_status = {}
    for s in samples:
        e = ent["sample_ena"].get(s, {"status": "failed"})
        n = ent["sample_ncbi"].get(s, {"status": "failed"})
        sample_status[s] = (e["status"], n["status"])
        if e["status"] == "failed":
            failures.append(f"ena_sample:{s}")
        if n["status"] == "failed":
            failures.append(f"ncbi_biosample:{s}")
        if e["status"] == "not_found" and n["status"] == "not_found":
            flags.add("sample_unresolvable")
        elif "not_found" in (e["status"], n["status"]):
            flags.add("sample_copy_absent")
        if e["status"] == "ambiguous_match":
            failures.append(f"ena_sample_ambiguous:{s}")
        for L in links:
            if s in L["samples"]:
                items.extend(_sample_items(acc, s, L["link_index"], L["route"], L["mapping_confidence"],
                                           e, n if n.get("status") == "found" else None))
                break
    for L in links:
        for st in L["studies"]:
            sv = ent["study"].get(st, {"status": "failed"})
            if sv["status"] == "failed":
                flags.add("study_lookup_failed")  # BioProject titles are context only; not a grade input

    # ---------------------------------------------------------------- value status
    names = [up.get("organism"), rec.get("organism")] + [i["value_original"] for i in items if i["role"] == "organism"]
    taxids = [up.get("taxon_id"), rec.get("organism_id")]
    viral = "Viruses" in (up.get("organism_lineage") or [])
    host_by_sample: dict[str, bool] = {}
    for it in items:
        if it["role"] == "host" and not N.is_missing(it["value_original"]) and not N.host_is_self(it["value_original"], names, taxids, viral=viral):
            host_by_sample[it["entity_accession"]] = True
    for it in items:
        role, v = it["role"], it["value_original"]
        if role in N.HABITAT_ROLES:
            if N.is_missing(v):
                it["value_status"] = "reported_missing"
            elif N.is_zero_placeholder(v, role):
                it["value_status"] = "invalid_placeholder"  # PR-7c.1a: "0" in a MIxS env field
            elif role == "host" and N.host_is_self(v, names, taxids, viral=viral):
                it["value_status"] = "host_is_self"
            elif N.is_placeholder(v, it["envo_ids"]):
                it["value_status"] = "uninformative_placeholder"
            elif N.is_culture_term(v):
                it["value_status"] = "moved_to_material"
            elif role == "isolation_source" and N.is_tissue_term(v) and not host_by_sample.get(it["entity_accession"]):
                it["value_status"] = "moved_to_material"
            else:
                it["value_status"] = "usable"
        elif role == "habitat_nonstandard":
            it["value_status"] = "reported_missing" if N.is_missing(v) else "nonstandard_context"
        elif role == "sample_material":
            it["value_status"] = "reported_missing" if N.is_missing(v) else "material"
        elif role in GEO_ROLES:
            it["value_status"] = "reported_missing" if N.is_missing(v) else "geography"
        elif role == "collection_date":
            it["value_status"] = "reported_missing" if N.is_missing(v) else "date"
        elif role == "depth":
            it["value_status"] = "reported_missing" if N.is_missing(v) else "depth"
        else:
            it["value_status"] = "context"
        if it["envo_ids"]:
            bad = [e for e in it["envo_ids"] if ent["envo"].get(e, {}).get("status") != "found"]
            if any(ent["envo"].get(e, {}).get("status") == "failed" for e in it["envo_ids"]):
                flags.add("envo_lookup_failed")
            if any(ent["envo"].get(e, {}).get("status") == "not_found" for e in it["envo_ids"]):
                flags.add("envo_id_invalid")
            it["envo_ids"] = [e for e in it["envo_ids"] if e not in bad]

    usable = [i for i in items if i["value_status"] == "usable"]  # all five roles (raw observations)
    usable_phys = [i for i in usable if i["role"] in N.PHYSICAL_ROLES]  # primary physical-habitat axis
    usable_host = [i for i in usable if i["role"] in N.HOST_ROLES]  # host-association axis
    if any(i["value_status"] == "host_is_self" for i in items):
        flags.add("host_is_self_ignored")
    if any(i["value_status"] == "invalid_placeholder" for i in items):
        flags.add("invalid_placeholder_value")
    if usable_host and not usable_phys:
        flags.add("host_association_only")
    if any(i["role"] == "isolation_source" and N.is_tissue_term(i["value_original"]) for i in usable_phys):
        flags.add("host_associated_isolation_source")
        if all(i["role"] == "isolation_source" and N.is_tissue_term(i["value_original"]) for i in usable_phys):
            flags.add("host_tissue_isolation_source_only")  # sensitivity: physical value is only a host tissue term
    conflict_roles, conflict_diag = [], []  # raw, over all five roles (preserved observation)
    link_samples = {L["link_index"]: list(L["samples"]) for L in links}
    for role in N.HABITAT_ROLES:
        ri = [i for i in usable if i["role"] == role]
        g = distinct_groups(ri)
        if len(g) > 1:
            conflict_roles.append(role)
            conflict_diag.append((role, conflict_scope(ri, link_samples), conflict_kind(g)))
    phys_conflicts = [r for r in conflict_roles if r in N.PHYSICAL_ROLES]
    phys_diag = [d for d in conflict_diag if d[0] in N.PHYSICAL_ROLES]
    host_diag = [d for d in conflict_diag if d[0] in N.HOST_ROLES]
    if host_diag:
        flags.add("host_conflict")
    # Legacy PR-7c.1 view (host counted as habitat, "0" counted as usable) - kept for transition tables only.
    legacy_usable = [i for i in items if i["value_status"] in ("usable", "invalid_placeholder")]
    legacy_conflict = [r for r in N.HABITAT_ROLES
                       if len(distinct_groups([i for i in legacy_usable if i["role"] == r])) > 1]
    for role, flag, fn in (("country", "geo_discordant", N.geo_key), ("collection_date", "date_discordant", N.date_key)):
        vals = {fn(i["value_original"]) for i in items if i["role"] == role and i["value_status"] in ("geography", "date")}
        if len(vals) > 1:
            flags.add(flag)
    if not usable and any(i["role"] in ("sample_title", "sample_description") for i in items):
        flags.add("free_text_context_only")
    if any(i["value_status"] == "reported_missing" and i["role"] in N.HABITAT_ROLES for i in items):
        flags.add("habitat_reported_missing")

    # ---------------------------------------------------------------- literature
    lit = lit or {}
    if not in_lit_subset:
        lit_status = "NOT_SEARCHED"
    else:
        lit_status = lit.get("literature_status", "NOT_SEARCHED")
    lit_items = lit.get("items", []) if in_lit_subset else []
    iso_items = [x for x in lit_items if x.get("scope") == "isolate" and x.get("parent_verified")]
    org_items = [x for x in lit_items if x.get("scope") == "organism" and x.get("parent_verified")]
    lit_inconsistent = any(x.get("consistent_with_db") == "inconsistent" for x in iso_items)
    lit_conflict = lit_inconsistent and bool(usable_phys)
    legacy_lit_conflict = lit_inconsistent and bool(legacy_usable)
    if lit_conflict:
        flags.add("literature_conflict")

    # ---------------------------------------------------------------- grade
    if failures:
        db_status = "INCOMPLETE"
    elif not links:
        db_status = "NO_LINK"
    else:
        db_status = "COMPLETE"
    if failures:
        legacy_grade = "LOOKUP_FAILED"
    elif legacy_conflict or legacy_lit_conflict:
        legacy_grade = "AMBIGUOUS"
    elif legacy_usable:
        legacy_grade = "DIRECT_SAMPLE"
    elif iso_items:
        legacy_grade = "VERIFIED_ISOLATE"
    elif org_items:
        legacy_grade = "ORGANISM_CONTEXT_ONLY"
    else:
        legacy_grade = "NOT_REPORTED"
    if failures:
        host_status = "LOOKUP_FAILED"
    elif host_diag:
        host_status = "AMBIGUOUS"
    elif usable_host:
        host_status = "REPORTED"
    else:
        host_status = "NOT_REPORTED"

    if failures:
        grade = "LOOKUP_FAILED"
        flags.add("chain_incomplete")
    elif phys_conflicts or lit_conflict:
        grade = "AMBIGUOUS"
        flags.add("conflict")
    elif usable_phys:
        grade = "DIRECT_SAMPLE"
        units = set(samples) | {f"link{L['link_index']}" for L in links
                                if not L["samples"] and L["route"] in ("cds_protein_id", "embl_parent_sequence", "uniparc_embl_protein")}
        n_ev = len(units)
        if n_ev > 1:
            flags.add("multi_sample")
    elif iso_items:
        grade = "VERIFIED_ISOLATE"
    elif org_items:
        grade = "ORGANISM_CONTEXT_ONLY"
    else:
        grade = "NOT_REPORTED"
    if grade not in ("DIRECT_SAMPLE", "AMBIGUOUS") and not failures and any(
            i["value_status"] == "moved_to_material" or i["value_status"] == "material" for i in items):
        flags.add("tissue_or_culture_only")
    if rec["is_engineered"]:
        flags.add("engineered_record")

    if grade == "DIRECT_SAMPLE":
        conf = "HIGH" if any(i["mapping_confidence"] == "HIGH" for i in usable_phys) else "MEDIUM"
    elif grade == "VERIFIED_ISOLATE":
        conf = "LITERATURE"
    elif grade == "AMBIGUOUS":
        if lit_conflict and not phys_conflicts:
            conf = "LITERATURE"  # spec s.8: conflict exists only between literature and DB
        else:
            conf = "HIGH" if any(i["mapping_confidence"] == "HIGH" for i in usable_phys) else ("MEDIUM" if usable_phys else "LITERATURE")
    else:
        conf = ""
    routes = sorted({L["route"] for L in links})

    # ---------------------------------------------------------------- evidence ids
    for it in items:
        h = hashlib.sha256("|".join(str(it[k]) for k in ("source_acc", "evidence_source", "entity_accession",
                                                         "link_index", "field_original", "value_original")).encode()).hexdigest()
        it["evidence_id"] = "HE" + h[:12]
    for x in lit_items:
        h = hashlib.sha256("|".join(str(x.get(k)) for k in ("pmid", "doi", "quote", "scope")).encode()
                           + acc.encode()).hexdigest()
        x["evidence_id"] = "HL" + h[:12]

    def vals(role, attr):
        return SEP.join(sorted({str(i[attr]) for i in usable if i["role"] == role}))

    for role in N.HABITAT_ROLES:
        row[f"{role}_original"] = vals(role, "value_original")
        row[f"{role}_normalized"] = vals(role, "value_normalized")
        row[f"{role}_envo_ids"] = ";".join(sorted({e for i in usable if i["role"] == role for e in i["envo_ids"]}))
    row["habitat_nonstandard"] = SEP.join(sorted({f"{i['field_original']}: {i['value_original']}" for i in items
                                                  if i["value_status"] == "nonstandard_context"}))
    row["sample_material"] = SEP.join(sorted({i["value_original"] for i in items if i["value_status"] in ("material", "moved_to_material")}))
    for role, col in (("country", "country"), ("lat_lon", "lat_lon"), ("collection_date", "collection_date"), ("depth", "depth")):
        ok = ("geography",) if role in GEO_ROLES else (("date",) if role == "collection_date" else ("depth",))
        row[col] = SEP.join(sorted({i["value_original"] for i in items if i["role"] == role and i["value_status"] in ok}))
    row["lat"] = SEP.join(sorted({i["value_original"] for i in items if i["role"] == "lat" and i["value_status"] == "geography"}))
    row["lon"] = SEP.join(sorted({i["value_original"] for i in items if i["role"] == "lon" and i["value_status"] == "geography"}))
    row["sample_type"] = _sample_type(items, mol_types)
    row["molecule_types"] = ";".join(sorted({m for m in mol_types if m and m != "-"}))
    row["embl_protein_ids"] = ";".join(sorted({L["protein_id"] for L in links if L["protein_id"] and L["protein_id"] != "-"}))
    row["insdc_accessions"] = ";".join(sorted({L["embl_parent"] for L in links if L["embl_parent"]}))
    row["proteomes"] = ";".join(sorted({L["proteome"] for L in links if L["proteome"]}))
    row["assemblies"] = ";".join(sorted({L["assembly"] for L in links if L["assembly"]}))
    row["biosamples"] = ";".join(samples)
    row["bioprojects"] = ";".join(sorted({s for L in links for s in L["studies"]}))
    row["linkage_route"] = ";".join(routes)
    row["mapping_confidence"] = conf
    row["primary_grade"] = grade
    row["pr7c1_grade"] = legacy_grade
    row["db_chain_status"] = db_status
    row["db_habitat_status"] = ("LOOKUP_FAILED" if failures else "AMBIGUOUS" if phys_conflicts else
                                "DIRECT_SAMPLE" if usable_phys else "NOT_REPORTED")
    row["literature_status"] = lit_status
    row["not_reported_scope"] = not_reported_scope(grade, lit_status)
    row["has_usable_habitat"] = int(grade in ("DIRECT_SAMPLE", "VERIFIED_ISOLATE"))
    row["host_association_status"] = host_status
    row["has_host_association"] = int(host_status in ("REPORTED", "AMBIGUOUS"))
    row["ambiguity_class"] = (ambiguity_class(phys_diag, lit_conflict) if grade == "AMBIGUOUS" else "")
    row["host_ambiguity_class"] = ambiguity_class(host_diag, False) if host_status == "AMBIGUOUS" else ""
    row["conflict_roles"] = ";".join(conflict_roles)
    row["conflict_scope"] = ";".join(f"{r}:{sc}" for r, sc, _ in conflict_diag)
    row["conflict_kind"] = ";".join(f"{r}:{k}" for r, _, k in conflict_diag)
    row["chain_failures"] = ";".join(sorted(set(failures)))
    row["organism_context_text"] = SEP.join(x.get("habitat_text", "") for x in org_items)
    row["organism_context_refs"] = ";".join(sorted({str(x.get("pmid") or x.get("doi")) for x in org_items}))
    row["literature_isolate_text"] = SEP.join(x.get("habitat_text", "") for x in iso_items)
    row["literature_isolate_refs"] = ";".join(sorted({str(x.get("pmid") or x.get("doi")) for x in iso_items}))
    row["flags"] = ";".join(sorted(flags))
    row["evidence_ids"] = ";".join(sorted({i["evidence_id"] for i in items if i["value_status"] == "usable"} |
                                          {x["evidence_id"] for x in iso_items}))
    for L in links:
        L["sample_status"] = ";".join(f"{s}:{sample_status[s][0]}/{sample_status[s][1]}" for s in L["samples"])
        L.pop("_row", None)
    lit_rows = []
    for x in lit_items:
        sc = x.get("scope")
        verified = bool(x.get("parent_verified"))
        lit_rows.append({"source_acc": acc, "evidence_source": "literature", "entity_accession": x.get("pmid") or x.get("doi"),
                         "link_index": "", "field_original": f"literature:{sc} | {x.get('locator') or ''}",
                         "role": {"isolate": "literature_isolate", "organism": "organism_context"}.get(sc, "literature_rejected"),
                         "value_original": x.get("quote"), "value_normalized": N.norm_value(x.get("habitat_text")),
                         "envo_ids": [], "request_key": x.get("verify_request_key") or "", "linkage_route": "literature",
                         "mapping_confidence": "LITERATURE" if sc == "isolate" and verified else "",
                         "value_status": ("usable" if sc == "isolate" and verified else
                                          "organism_context" if sc == "organism" and verified else
                                          f"rejected:{x.get('parent_decision_reason') or 'unverified'}"),
                         "api_url": x.get("source_url") or "",
                         "evidence_id": x["evidence_id"]})
    return row, links, items + lit_rows
