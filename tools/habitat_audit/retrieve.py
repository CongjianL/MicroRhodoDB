"""Stage 2: accession-chain retrieval into the content-addressed cache, and the
derived per-entity store (entities.json) used by classification.

Chain: UniProtKB -> EMBL CDS (ENA coding, by protein_id) -> parent sequence
(ENA sequence / wgs_set, only when the CDS row is absent) -> BioSample (ENA
browser XML + NCBI BioSample via esearch[accn] -> efetch by UID, accession
verified) -> BioProject (ENA study). Records with no EMBL CDS link use the
UniProt Proteome -> assembly/BioSample route (MEDIUM confidence). Explicit
ENVO IDs are validated with OLS4. Nothing is inferred.
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .http_cache import HttpCache, cache_key

UNIPROT_BATCH = "https://rest.uniprot.org/uniprotkb/accessions"
UNIPROT_ENTRY = "https://rest.uniprot.org/uniprotkb/{acc}"
UNIPARC_SEARCH = "https://rest.uniprot.org/uniparc/search"
PROTEOME = "https://rest.uniprot.org/proteomes/{up}"
ENA_SEARCH = "https://www.ebi.ac.uk/ena/portal/api/search"
ENA_XML = "https://www.ebi.ac.uk/ena/browser/api/xml/{accs}"
NCBI_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
OLS_TERM = "https://www.ebi.ac.uk/ols4/api/ontologies/envo/terms"
ENA_EMBL_TEXT = "https://www.ebi.ac.uk/ena/browser/api/embl/{acc}"

UNIPROT_FIELDS = ("accession,id,organism_name,organism_id,xref_embl,xref_proteomes,xref_refseq,"
                  "lit_pubmed_id,sequence,reviewed,protein_existence")
SOURCE_FIELDS = ("isolation_source,country,location,collection_date,host,strain,isolate,sub_strain,"
                 "environmental_sample,mol_type,cell_type,cell_line,tissue_type,tissue_lib,lab_host,"
                 "bio_material,cultivar,scientific_name,tax_id")
CODING_FIELDS = "accession,protein_id,parent_accession,sample_accession,study_accession," + SOURCE_FIELDS
SEQUENCE_FIELDS = ("accession,sample_accession,secondary_sample_accession,study_accession,assembly_accession,"
                   "metagenome_source," + SOURCE_FIELDS)
WGS_FIELDS = "accession,sample_accession,study_accession,scientific_name,tax_id"
ASSEMBLY_FIELDS = "assembly_accession,sample_accession,study_accession,assembly_type,assembly_level,scientific_name"
STUDY_FIELDS = "study_accession,secondary_study_accession,study_title,study_name,project_name"

B_UNIPROT, B_ENA, B_XML, B_NCBI_SEARCH, B_NCBI_FETCH = 500, 200, 50, 100, 200
ENVO_RE = re.compile(r"ENVO[:_ ]?(\d{7,8})", re.I)


def _chunks(items, n):
    items = sorted(set(items))
    return [items[i:i + n] for i in range(0, len(items), n)]


def _pmap(fn, jobs, workers=4):
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, jobs))


def strip_version(pid: str) -> str:
    return pid.split(".")[0]


# ====================================================================== UniProt
def parse_uniprot_entry(e: dict) -> dict:
    xrefs = e.get("uniProtKBCrossReferences", []) or []
    embl, proteomes, refseq = [], [], []
    for x in xrefs:
        props = {p["key"]: p["value"] for p in x.get("properties", []) or []}
        if x["database"] == "EMBL":
            embl.append({"parent_accession": x["id"], "protein_id": props.get("ProteinId", "-"),
                         "status": props.get("Status", "-"), "molecule_type": props.get("MoleculeType", "-")})
        elif x["database"] == "Proteomes":
            proteomes.append({"proteome": x["id"], "component": props.get("Component")})
        elif x["database"] == "RefSeq":
            refseq.append(x["id"])
    refs = []
    for rf in e.get("references", []) or []:
        cit = rf.get("citation", {}) or {}
        ids = {c["database"]: c["id"] for c in cit.get("citationCrossReferences", []) or []}
        strains = []
        for rc in rf.get("referenceComments", []) or []:
            if rc.get("type") in ("STRAIN", "TISSUE", "PLASMID"):
                strains.append({"type": rc["type"], "value": rc.get("value"),
                                "evidence_ids": sorted({ev.get("id") for ev in rc.get("evidences", []) or [] if ev.get("id")})})
        refs.append({"pubmed": ids.get("PubMed"), "doi": ids.get("DOI"), "title": cit.get("title"),
                     "citation_type": cit.get("citationType"), "comments": strains})
    seq = (e.get("sequence") or {}).get("value", "")
    org = e.get("organism") or {}
    return {
        "accession": e["primaryAccession"], "entry_type": e.get("entryType"),
        "organism": org.get("scientificName"), "taxon_id": org.get("taxonId"),
        "organism_lineage": org.get("lineage"),
        "sequence_sha256": hashlib.sha256(seq.encode()).hexdigest() if seq else None,
        "embl": embl, "proteomes": proteomes, "refseq": sorted(refseq), "references": refs,
    }


def fetch_uniprot(cache: HttpCache, accs: list[str]) -> dict:
    out: dict[str, dict] = {}

    def job(batch):
        return batch, cache.get(UNIPROT_BATCH, {"accessions": ",".join(batch), "fields": UNIPROT_FIELDS,
                                                "format": "json", "size": "500"})
    for batch, ent in _pmap(job, _chunks(accs, B_UNIPROT)):
        key = cache_key("GET", UNIPROT_BATCH, {"accessions": ",".join(batch), "fields": UNIPROT_FIELDS,
                                               "format": "json", "size": "500"})
        if not ent["ok"] or ent["status"] != 200:
            for a in batch:
                out[a] = {"status": "failed", "request_key": key}
            continue
        rel = ent["headers"].get("X-UniProt-Release") or ent["headers"].get("x-uniprot-release")
        got = {e["primaryAccession"]: e for e in json.loads(ent["text"])["results"]}
        for a in batch:
            if a in got:
                out[a] = {"status": "active", "request_key": key, "uniprot_release": rel, **parse_uniprot_entry(got[a])}
            else:
                out[a] = {"status": "absent_from_batch", "request_key": key}
    # Per-accession lookup for anything not returned by the batch (inactive / merged / demerged / secondary).
    missing = sorted(a for a, v in out.items() if v["status"] == "absent_from_batch")

    def one(a):
        return a, cache.get(UNIPROT_ENTRY.format(acc=a), {"format": "json"})
    for a, ent in _pmap(one, missing):
        key = cache_key("GET", UNIPROT_ENTRY.format(acc=a), {"format": "json"})
        if not ent["ok"]:
            out[a] = {"status": "failed", "request_key": key}
            continue
        if ent["status"] != 200:
            out[a] = {"status": "not_found", "request_key": key, "http_status": ent["status"]}
            continue
        e = json.loads(ent["text"])
        if e.get("entryType") == "Inactive":
            out[a] = {"status": "inactive", "request_key": key, "inactive_reason": e.get("inactiveReason"),
                      "embl": [], "proteomes": [], "refseq": [], "references": []}
        else:  # e.g. secondary accession resolved to a different primary accession
            out[a] = {"status": "active_secondary", "request_key": key, **parse_uniprot_entry(e)}
    return out


UNIPARC_DBS = "https://rest.uniprot.org/uniparc/{upi}/databases"


def fetch_uniparc(cache: HttpCache, accs: list[str], taxids: dict | None = None) -> dict:
    """Inactive/deleted UniProt entries, and active entries with neither EMBL nor proteome
    cross-references: UniParc (sequence-identical) cross-references to active
    INSDC protein IDs, restricted to the frozen record's own taxon ID."""
    out = {}
    taxids = taxids or {}
    for a in sorted(accs):
        params = {"query": f"dbid:{a}", "format": "json", "size": "5"}
        ent = cache.get(UNIPARC_SEARCH, params)
        key = cache_key("GET", UNIPARC_SEARCH, params)
        if not ent["ok"] or ent["status"] != 200:
            out[a] = {"status": "failed" if not ent["ok"] else "not_found", "request_key": key}
            continue
        upis = sorted(u.get("uniParcId") for u in json.loads(ent["text"]).get("results", []) if u.get("uniParcId"))
        pids, keys, failed = [], [key], False
        for upi in upis:
            p2 = {"format": "json", "size": "500"}
            e2 = cache.get(UNIPARC_DBS.format(upi=upi), p2)
            keys.append(cache_key("GET", UNIPARC_DBS.format(upi=upi), p2))
            if not e2["ok"] or e2["status"] != 200:
                failed = True
                continue
            for x in json.loads(e2["text"]).get("results", []):
                if (x.get("database") in ("EMBL", "EMBLWGS", "EMBL_CON", "EMBL_TPA") and x.get("active")
                        and x.get("id") and str((x.get("organism") or {}).get("taxonId")) == str(taxids.get(a))):
                    pids.append(x["id"])
        out[a] = {"status": "failed" if failed else ("found" if upis else "not_found"), "request_key": key,
                  "request_keys": keys, "upi": upis, "embl_protein_ids": sorted(set(pids))}
    return out


# ====================================================================== ENA portal
def _ena_tsv(text: str) -> list[dict]:
    lines = [l for l in (text or "").split("\n") if l.strip()]
    if not lines:
        return []
    hdr = lines[0].split("\t")
    return [dict(zip(hdr, l.split("\t"))) for l in lines[1:]]


def ena_portal(cache: HttpCache, result: str, ids: list[str], fields: str, idcol: str,
               batch: int = B_ENA, match=None) -> dict:
    """Batched POST search; 400 on a batch is split recursively so one bad ID cannot hide others."""
    out: dict[str, dict] = {}
    match = match or (lambda row: [row.get(idcol, "")])

    def run(chunk):
        data = {"result": result, "includeAccessions": ",".join(chunk), "fields": fields,
                "format": "tsv", "limit": "0"}
        ent = cache.post(ENA_SEARCH, data)
        key = cache_key("POST", ENA_SEARCH, None, data)
        if ent["ok"] and ent["status"] == 400 and len(chunk) > 1:
            mid = len(chunk) // 2
            return run(chunk[:mid]) + run(chunk[mid:])
        return [(chunk, ent, key)]

    results = []
    for res in _pmap(run, _chunks(ids, batch)):
        results.extend(res)
    for chunk, ent, key in results:
        if not ent["ok"]:
            for i in chunk:
                out[i] = {"status": "failed", "request_key": key}
            continue
        if ent["status"] in (400, 404) and len(chunk) == 1:
            out[chunk[0]] = {"status": "not_found", "request_key": key, "http_status": ent["status"]}
            continue
        rows = _ena_tsv(ent["text"]) if ent["status"] == 200 else []
        by = {}
        for r in rows:
            for k in sorted(set(match(r))):
                if k:
                    by.setdefault(k, []).append(r)
        for i in chunk:
            if i in by:
                uniq = {json.dumps(r, sort_keys=True): r for r in by[i]}
                out[i] = {"status": "found", "request_key": key, "rows": [uniq[k] for k in sorted(uniq)]}
            else:
                out[i] = {"status": "not_found", "request_key": key}
    return out


# ====================================================================== ENA browser XML
def _parse_ena_sample_xml(text: str) -> list[dict]:
    root = ET.fromstring(text)
    out = []
    for s in root.iter("SAMPLE"):
        ids = s.find("IDENTIFIERS")
        prim = ids.findtext("PRIMARY_ID") if ids is not None else None
        sec = [e.text for e in ids.findall("SECONDARY_ID")] if ids is not None else []
        ext = [e.text for e in ids.findall("EXTERNAL_ID")] if ids is not None else []
        name = s.find("SAMPLE_NAME")
        attrs = []
        for a in s.iter("SAMPLE_ATTRIBUTE"):
            attrs.append({"tag": (a.findtext("TAG") or "").strip(), "value": (a.findtext("VALUE") or "").strip(),
                          "units": (a.findtext("UNITS") or "").strip() or None})
        out.append({
            "accession": s.get("accession"), "primary_id": prim, "secondary_ids": sec, "external_ids": ext,
            "alias": s.get("alias"), "broker": s.get("broker_name"), "center": s.get("center_name"),
            "title": (s.findtext("TITLE") or "").strip() or None,
            "description": (s.findtext("DESCRIPTION") or "").strip() or None,
            "taxon_id": name.findtext("TAXON_ID") if name is not None else None,
            "scientific_name": name.findtext("SCIENTIFIC_NAME") if name is not None else None,
            "attributes": attrs,
        })
    return out


def fetch_ena_samples(cache: HttpCache, accs: list[str]) -> dict:
    out: dict[str, dict] = {}

    def run(chunk):
        url = ENA_XML.format(accs=",".join(chunk))
        ent = cache.get(url)
        key = cache_key("GET", url)
        if ent["ok"] and ent["status"] != 200 and len(chunk) > 1:
            mid = len(chunk) // 2
            return run(chunk[:mid]) + run(chunk[mid:])
        return [(chunk, ent, key)]

    results = []
    for res in _pmap(run, _chunks(accs, B_XML)):
        results.extend(res)
    for chunk, ent, key in results:
        if not ent["ok"]:
            for a in chunk:
                out[a] = {"status": "failed", "request_key": key}
            continue
        if ent["status"] != 200:
            for a in chunk:
                out[a] = {"status": "not_found", "request_key": key, "http_status": ent["status"]}
            continue
        docs = _parse_ena_sample_xml(ent["text"])
        for a in chunk:
            hit = [d for d in docs if a == d["accession"] or a == d["primary_id"] or a in d["secondary_ids"]
                   or a in d["external_ids"]]
            if len(hit) == 1:
                out[a] = {"status": "found", "request_key": key, **hit[0]}
            elif not hit:
                out[a] = {"status": "not_found", "request_key": key}
            else:
                out[a] = {"status": "ambiguous_match", "request_key": key, "matches": [d["accession"] for d in hit]}
    return out


# ====================================================================== NCBI BioSample
def _parse_ncbi_biosample_xml(text: str) -> list[dict]:
    root = ET.fromstring(text)
    out = []
    for b in root.iter("BioSample"):
        ids = [{"db": i.get("db"), "id": (i.text or "").strip(), "label": i.get("db_label")}
               for i in b.findall("./Ids/Id")]
        desc = b.find("Description")
        org = desc.find("Organism") if desc is not None else None
        paras = [(p.text or "").strip() for p in b.findall("./Description/Comment/Paragraph")]
        attrs = [{"name": a.get("attribute_name"), "harmonized_name": a.get("harmonized_name"),
                  "value": (a.text or "").strip()} for a in b.findall("./Attributes/Attribute")]
        out.append({
            "uid": b.get("id"), "accession": b.get("accession"), "ids": ids,
            "title": desc.findtext("Title") if desc is not None else None,
            "description": " ".join(p for p in paras if p) or None,
            "taxon_id": org.get("taxonomy_id") if org is not None else None,
            "organism": org.get("taxonomy_name") if org is not None else None,
            "package": (b.findtext("Package") or "").strip() or None,
            "attributes": attrs,
        })
    return out


def fetch_ncbi_biosamples(cache: HttpCache, accs: list[str]) -> dict:
    """esearch '<acc>[accn]' -> UIDs -> efetch by UID; mapping is ALWAYS by returned accession/Ids,
    never by the numeric part of the requested accession (SAMEA5987284 != SAMN05987284)."""
    out: dict[str, dict] = {}
    search_results = []
    for chunk in _chunks(accs, B_NCBI_SEARCH):
        data = {"db": "biosample", "term": " OR ".join(f"{a}[accn]" for a in chunk), "retmax": "1000",
                "retmode": "json"}
        ent = cache.post(NCBI_ESEARCH, data)
        key = cache_key("POST", NCBI_ESEARCH, None, data)
        search_results.append((chunk, ent, key))
    uids, uid_req = [], {}
    for chunk, ent, key in search_results:
        if not ent["ok"] or ent["status"] != 200:
            for a in chunk:
                out[a] = {"status": "failed", "request_key": key}
            continue
        try:
            js = json.loads(ent["text"])
            ids = js["esearchresult"]["idlist"]
        except (ValueError, KeyError):
            for a in chunk:
                out[a] = {"status": "failed", "request_key": key, "error": "esearch parse"}
            continue
        for u in ids:
            uids.append(u)
            uid_req[u] = key
        for a in chunk:
            out.setdefault(a, {"status": "pending", "search_key": key})
    docs, fetch_failed = {}, set()
    for chunk in _chunks(uids, B_NCBI_FETCH):
        data = {"db": "biosample", "id": ",".join(chunk), "retmode": "xml"}
        ent = cache.post(NCBI_EFETCH, data)
        key = cache_key("POST", NCBI_EFETCH, None, data)
        if not ent["ok"] or ent["status"] != 200:
            fetch_failed.add(key)
            for u in chunk:
                docs.setdefault("__failed__", []).append((u, key))
            continue
        for d in _parse_ncbi_biosample_xml(ent["text"]):
            d["request_key"] = key
            docs[d["accession"]] = d
            for i in d["ids"]:
                docs.setdefault("__alias__" + i["id"], d)
    for a, v in list(out.items()):
        if v["status"] != "pending":
            continue
        d = docs.get(a) or docs.get("__alias__" + a)
        if d is not None:
            out[a] = {"status": "found", "search_key": v["search_key"], **d}
        elif fetch_failed:
            out[a] = {"status": "failed", "search_key": v["search_key"], "error": "efetch batch failed"}
        else:
            out[a] = {"status": "not_found", "search_key": v["search_key"]}
    return out


# ====================================================================== proteomes, OLS
def fetch_proteomes(cache: HttpCache, ups: list[str]) -> dict:
    out = {}

    def one(up):
        return up, cache.get(PROTEOME.format(up=up), {"format": "json"})
    for up, ent in _pmap(one, sorted(set(ups))):
        key = cache_key("GET", PROTEOME.format(up=up), {"format": "json"})
        if not ent["ok"]:
            out[up] = {"status": "failed", "request_key": key}
            continue
        if ent["status"] != 200:
            out[up] = {"status": "not_found", "request_key": key}
            continue
        j = json.loads(ent["text"])
        bios, gacc = set(), set()
        for c in j.get("components", []) or []:
            for x in c.get("proteomeCrossReferences", []) or []:
                if x.get("database") == "Biosample":
                    bios.add(x["id"])
                if x.get("database") == "GenomeAccession":
                    gacc.add(x["id"])
        ga = j.get("genomeAssembly") or {}
        out[up] = {"status": "found", "request_key": key, "proteome_type": j.get("proteomeType"),
                   "assembly": ga.get("assemblyId"), "assembly_source": ga.get("source"),
                   "biosamples": sorted(bios), "genome_accessions": sorted(gacc),
                   "taxon_id": (j.get("taxonomy") or {}).get("taxonId")}
    return out


def fetch_envo(cache: HttpCache, ids: list[str]) -> dict:
    out = {}
    for i in sorted(set(ids)):
        params = {"obo_id": i}
        ent = cache.get(OLS_TERM, params)
        key = cache_key("GET", OLS_TERM, params)
        if not ent["ok"]:
            out[i] = {"status": "failed", "request_key": key}
            continue
        terms = (json.loads(ent["text"]).get("_embedded") or {}).get("terms", []) if ent["status"] == 200 else []
        if terms:
            t = terms[0]
            out[i] = {"status": "found", "request_key": key, "label": t.get("label"), "is_obsolete": bool(t.get("is_obsolete"))}
        else:
            out[i] = {"status": "not_found", "request_key": key}
    return out


def envo_ids_in(text: str | None) -> list[str]:
    return sorted({f"ENVO:{m.group(1).zfill(8)}" for m in ENVO_RE.finditer(text or "")})


DR_BIOSAMPLE_RE = re.compile(r"^DR   BioSample; ([A-Z0-9]+)\.?\s*$", re.M)
PR_PROJECT_RE = re.compile(r"^PR   Project:([A-Z0-9]+);?\s*$", re.M)


def fetch_insdc_flatfile(cache: HttpCache, parents: list[str]) -> dict:
    """Last-resort explicit link for INSDC parent records that no portal result resolved: the ENA
    flat-file header (for a WGS contig ENA serves the WGS set master) and its 'DR   BioSample;' and
    'PR   Project:' lines. Only explicit cross-references are used."""
    out = {}
    for a in sorted(parents):
        url = ENA_EMBL_TEXT.format(acc=a)
        params = {"lineLimit": "200"}
        e = cache.get(url, params)
        key = cache_key("GET", url, params)
        if not e["ok"]:
            out[a] = {"status": "failed", "request_key": key}
            continue
        txt = e["text"] or "" if e["status"] == 200 else ""
        if not txt.startswith("ID   "):
            out[a] = {"status": "not_found", "request_key": key}
            continue
        head = txt.split("\nFH ")[0].split("\nSQ ")[0]
        idline = head.split("\n", 1)[0]
        out[a] = {"status": "found", "request_key": key, "id_line": idline,
                  "samples": sorted(set(DR_BIOSAMPLE_RE.findall(head))),
                  "studies": sorted(set(PR_PROJECT_RE.findall(head)))}
    return out


# ====================================================================== orchestration
def retrieve_all(cache: HttpCache, accs: list[str], log=print, taxids: dict | None = None) -> dict:
    ent: dict[str, dict] = {"meta": {}}
    log(f"[uniprot] {len(accs)} accessions")
    up = fetch_uniprot(cache, accs)
    ent["uniprot"] = up
    inactive = [a for a, v in up.items() if v["status"] in ("inactive", "not_found")]
    unlinked = [a for a, v in up.items() if v["status"] in ("active", "active_secondary")
                and not (v.get("embl") or []) and not (v.get("proteomes") or [])]
    up_q = sorted(set(inactive) | set(unlinked))
    ent["uniparc"] = fetch_uniparc(cache, up_q, taxids) if up_q else {}
    rels = sorted({v.get("uniprot_release") for v in up.values() if v.get("uniprot_release")})
    ent["meta"]["uniprot_release"] = rels

    pids, parents, no_embl_ups = set(), set(), set()
    for a, v in up.items():
        embl = v.get("embl") or []
        for x in embl:
            if x["protein_id"] not in ("-", "", None):
                pids.add(strip_version(x["protein_id"]))
        for p in ent["uniparc"].get(a, {}).get("embl_protein_ids", []):
            pids.add(strip_version(p))
        if not embl and v["status"] in ("active", "active_secondary"):
            for p in v.get("proteomes") or []:
                no_embl_ups.add(p["proteome"])
    log(f"[ena coding] {len(pids)} protein ids")
    ent["cds"] = ena_portal(cache, "coding", sorted(pids), CODING_FIELDS, "protein_id",
                            match=lambda r: [strip_version(r.get("protein_id", "")), strip_version(r.get("accession", ""))])
    # Parent sequences for xrefs whose CDS row is absent, or with no protein_id.
    for a, v in up.items():
        for x in v.get("embl") or []:
            pid = strip_version(x["protein_id"]) if x["protein_id"] not in ("-", "", None) else None
            if pid is None or ent["cds"].get(pid, {}).get("status") == "not_found":
                parents.add(strip_version(x["parent_accession"]))
    log(f"[ena sequence] {len(parents)} parent accessions")
    ent["sequence"] = ena_portal(cache, "sequence", sorted(parents), SEQUENCE_FIELDS, "accession",
                                 match=lambda r: [strip_version(r.get("accession", ""))])
    wgs = sorted({m.group(1) for p, s in ent["sequence"].items()
                  if s["status"] == "not_found" and (m := re.match(r"^([A-Z]{4,6}\d{2})\d{6,}$", p))})
    ent["wgs_set"] = ena_portal(cache, "wgs_set", wgs, WGS_FIELDS, "accession",
                                match=lambda r: [re.sub(r"^([A-Z]{4,6}\d{2}).*$", lambda m: m.group(1), r.get("accession", ""))]) if wgs else {}
    unresolved = sorted({p for p, sq in ent["sequence"].items() if sq["status"] == "not_found"
                         and ent["wgs_set"].get((re.match(r"^([A-Z]{4,6}\d{2})\d{6,}$", p) or [None, None])[1] or "",
                                                {"status": "not_found"})["status"] == "not_found"})
    log(f"[insdc flatfile] {len(unresolved)} unresolved parent records")
    ent["insdc_flatfile"] = fetch_insdc_flatfile(cache, unresolved)
    log(f"[proteome] {len(no_embl_ups)} proteomes (records without EMBL xrefs)")
    ent["proteome"] = fetch_proteomes(cache, sorted(no_embl_ups))
    asm = sorted({p["assembly"] for p in ent["proteome"].values() if p.get("assembly") and not p.get("biosamples")})
    ent["assembly"] = ena_portal(cache, "assembly", asm, ASSEMBLY_FIELDS, "assembly_accession",
                                 match=lambda r: [r.get("assembly_accession", ""), strip_version(r.get("assembly_accession", ""))]) if asm else {}

    samples, studies = set(), set()
    for group in ("cds", "sequence", "wgs_set", "assembly"):
        for v in ent[group].values():
            for r in v.get("rows", []) or []:
                for s in (r.get("sample_accession") or "").split(";"):
                    if s.strip():
                        samples.add(s.strip())
                for s in (r.get("study_accession") or "").split(";"):
                    if s.strip():
                        studies.add(s.strip())
    for p in ent["proteome"].values():
        samples.update(p.get("biosamples") or [])
    for f in ent["insdc_flatfile"].values():
        samples.update(f.get("samples") or [])
        studies.update(f.get("studies") or [])
    log(f"[samples] {len(samples)} sample accessions (ENA XML + NCBI)")
    ent["sample_ena"] = fetch_ena_samples(cache, sorted(samples))
    ent["sample_ncbi"] = fetch_ncbi_biosamples(cache, sorted(samples))
    log(f"[studies] {len(studies)} study accessions")
    ent["study"] = ena_portal(cache, "study", sorted(studies), STUDY_FIELDS, "study_accession",
                              match=lambda r: [r.get("study_accession", ""), r.get("secondary_study_accession", "")])
    envo = set()
    for grp in ("sample_ena", "sample_ncbi"):
        for v in ent[grp].values():
            for a in v.get("attributes") or []:
                envo.update(envo_ids_in(a.get("value")))
    for group in ("cds", "sequence"):
        for v in ent[group].values():
            for r in v.get("rows", []) or []:
                envo.update(envo_ids_in(r.get("isolation_source")))
    log(f"[ols] {len(envo)} explicit ENVO ids")
    ent["envo"] = fetch_envo(cache, sorted(envo))
    return ent


def save_entities(ent: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ent, sort_keys=True, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
