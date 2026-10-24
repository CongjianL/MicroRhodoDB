"""PR-7c.2: habitat sidecar (data/v1.6.1/habitat/) integrated into the deterministic web export.

Display observed environmental metadata, not inferred habitats. These tests re-derive the sidecar from the accepted
PR-7c.1a audit tables with their own code (no import of tools/habitat_export/build.py constants for the checks),
and prove that the core export is byte-identical with and without the sidecar.

Missing inputs fail; nothing is skipped.
"""
import collections
import csv
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(os.environ.get("MRDB_REPO", ".")).resolve()
DB = Path(os.environ.get("MRDB_DB", REPO / "releases/v1.6.1/db/microrhododb_v1.6.1.sqlite"))
EXPORTER = REPO / "tools/export_web_data.py"
P = REPO / "docs/website/pr7c1"
REL = "v1.6.1"
CONTRACT = REPO / "tools/habitat_export/contract.json"

sys.path.insert(0, str(REPO / "tools"))
import export_web_data as ex  # noqa: E402
from habitat_export import build as hb  # noqa: E402  (only for in-process determinism / fail-closed checks)

# independent constants (deliberately not imported from the module under test)
GROUP_ROLES = {
    "physical": {"env_broad_scale", "env_local_scale", "env_medium", "isolation_source", "habitat_nonstandard",
                 "literature_isolate", "literature_rejected"},
    "host": {"host", "host_detail"},
    "collection": {"country", "lat_lon", "lat", "lon", "collection_date", "depth", "sample_material",
                   "environmental_sample", "metagenome_source"},
    "organism_context": {"organism_context"},
}
ROLE_TO_GROUP = {r: g for g, rs in GROUP_ROLES.items() for r in rs}
NO_LINK = {"A0A6I8WFQ3", "A0A6P3CW41", "A0A6P3CW42", "A0A7M4DUE4", "A0A7M4DUE9", "A0A8X6EH36", "A0A9X9ZA75",
           "A0AA82WP37", "A0AA82WPB4", "A0AAJ6N6B2", "A0ABF7PQ03", "A0ABF7PQ05", "A0ABF7PQ82", "A0ABF7PQ84",
           "A0ABF7PQA2", "A0AC62AE26", "G1K3Q0", "Q53461"}
QUARANTINE_RECORDS = {"A0A4Q4MIR8", "A0A4Q4P102", "A0A4Q4SIR6", "A0A4V1X477", "A0ACB6FSP5", "A0ACB6FST4",
                      "A0A6N7QP32"}
EXPECTED_METRICS = {
    "grade:DIRECT_SAMPLE": (2523, 5466), "grade:VERIFIED_ISOLATE": (17, 5466),
    "grade:ORGANISM_CONTEXT_ONLY": (36, 5466), "grade:AMBIGUOUS": (59, 5466), "grade:NOT_REPORTED": (2831, 5466),
    "grade:LOOKUP_FAILED": (0, 5466), "grade:NOT_SEARCHED": (0, 5466),
    "physical_habitat_usable": (2540, 5466), "has_host_association": (755, 5466),
    "host_association:REPORTED": (671, 5466), "host_association:AMBIGUOUS": (84, 5466),
    "host_association:NOT_REPORTED": (4711, 5466), "host_association_only": (186, 5466),
    "host_without_usable_physical_habitat": (207, 5466),
    "host_without_usable_physical_habitat:AMBIGUOUS": (21, 5466),
    "physical_habitat_and_host_association": (548, 5466),
    "ambiguity_class:FORMATTING_ONLY": (9, 59), "ambiguity_class:NESTED_WORDING": (20, 59),
    "ambiguity_class:DISTINCT_SAME_SAMPLE": (19, 59), "ambiguity_class:DISTINCT_ACROSS_SAMPLES": (10, 59),
    "ambiguity_class:LITERATURE_VS_DATABASE": (1, 59),
    "host_ambiguity_class:FORMATTING_ONLY": (1, 84), "host_ambiguity_class:NESTED_WORDING": (23, 84),
    "host_ambiguity_class:DISTINCT_SAME_SAMPLE": (60, 84),
    "not_reported_scope:database_only_literature_not_reviewed": (2796, 2831),
    "not_reported_scope:database_only_literature_inaccessible": (23, 2831),
    "not_reported_scope:database_and_literature": (12, 2831),
    "no_traceable_sample_link": (18, 5466), "literature_status:LOOKUP_FAILED": (24, 5466),
    "host_tissue_isolation_source_only": (23, 5466), "quarantined_values:records": (7, 5466),
    "invalid_placeholder:records": (2, 5466), "multi_source_mrdb": (129, 5299),
    "multi_source_mrdb:grades_differ": (43, 129),
}


def tsv(p):
    csv.field_size_limit(sys.maxsize)
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def sha(b):
    return hashlib.sha256(b).hexdigest()


def tree(root):
    root = Path(root)
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


# ----------------------------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def exports(tmp_path_factory):
    assert DB.is_file(), f"database missing: {DB}"
    hab, nohab = tmp_path_factory.mktemp("hab"), tmp_path_factory.mktemp("nohab")
    for out, extra in ((hab, []), (nohab, ["--no-habitat"])):
        r = subprocess.run([sys.executable, str(EXPORTER), "--repo", str(REPO), "--db", str(DB), "--out", str(out),
                            *extra], capture_output=True, text=True, cwd=str(REPO))
        assert r.returncode == 0, r.stderr
    return hab, nohab


@pytest.fixture(scope="module")
def H(exports):
    return exports[0] / REL / "habitat"


@pytest.fixture(scope="module")
def files(H):
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((H / "records").glob("*.json"))}


@pytest.fixture(scope="module")
def entries(files):
    out = {}
    for ma, f in files.items():
        for e in f["sources"]:
            assert e["source_acc"] not in out
            out[e["source_acc"]] = e
    return out


@pytest.fixture(scope="module")
def recs():
    return {r["source_acc"]: r for r in tsv(P / "habitat_record_availability.tsv")}


@pytest.fixture(scope="module")
def evs():
    return tsv(P / "habitat_evidence.tsv")


@pytest.fixture(scope="module")
def lit():
    return json.loads((P / "literature/literature_evidence.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def summary(H):
    return json.loads((H / "summary.json").read_text(encoding="utf-8"))


def all_items(e):
    return [(g, i) for g, xs in e["items"].items() for i in xs]


# ----------------------------------------------------------------------------------------------- core unchanged
def test_core_export_byte_identical_with_and_without_habitat(exports):
    hab, nohab = (tree(x) for x in exports)
    core = {k: v for k, v in hab.items() if not k.startswith(f"{REL}/habitat/")}
    assert set(core) == set(nohab)
    differ = sorted(k for k in core if core[k] != nohab[k])
    assert differ == [f"{REL}/export_manifest.json"], differ
    a = json.loads(core[f"{REL}/export_manifest.json"])
    b = json.loads(nohab[f"{REL}/export_manifest.json"])
    fa = [f for f in a["files"] if not f["path"].startswith(f"{REL}/habitat/")]
    assert fa == b["files"]
    assert a["n_files"] == b["n_files"] + 5301
    assert {k: a[k] for k in a if k not in ("files", "n_files", "total_bytes")} == \
           {k: b[k] for k in b if k not in ("files", "n_files", "total_bytes")}
    assert json.loads(core[f"{REL}/manifest.json"])["schema_version"] == "1.4.0"


def test_export_manifest_lists_every_habitat_file(exports, H):
    em = json.loads((exports[0] / REL / "export_manifest.json").read_text())
    listed = {f["path"]: f for f in em["files"] if f["path"].startswith(f"{REL}/habitat/")}
    on_disk = {str(p.relative_to(exports[0])) for p in H.rglob("*") if p.is_file()}
    assert set(listed) == on_disk and len(on_disk) == 5301
    for rel, f in listed.items():
        b = (exports[0] / rel).read_bytes()
        assert f["sha256"] == sha(b) and f["bytes"] == len(b)


def test_habitat_manifest_hashes_and_provenance(H):
    man = json.loads((H / "manifest.json").read_text())
    c = json.loads(CONTRACT.read_text())
    assert man["habitat_schema_version"] == "1.0.0"
    assert man["audit"]["audit_id"] == "PR-7c.1a" and man["audit"]["audit_version"] == "1.1.0"
    assert man["audit"]["accepted_commit"].startswith("361039e") and man["audit"]["status"] == "PR7C1_AUDIT_PARTIAL"
    assert man["retrieval"]["network_requests_during_export"] == 0
    assert man["retrieval"]["cache_sha256"] == c["retrieval_cache"]["sha256"]
    for inp in man["inputs"]:
        assert sha((REPO / inp["path"]).read_bytes()) == inp["sha256"]
    assert man["n_files"] == 5300 == len(man["files"])
    for f in man["files"]:
        b = (H.parent / f["path"]).read_bytes()
        assert f["sha256"] == sha(b) and f["bytes"] == len(b)
    assert man["evidence_id_rules"]["null_serialization"] == "None"
    assert man["evidence_id_rules"]["recomputed"] == 105750


def test_size_budget(H):
    sizes = [p.stat().st_size for p in (H / "records").glob("*.json")]
    assert len(sizes) == 5299 and max(sizes) <= 65536


# ----------------------------------------------------------------------------------------------- reconciliation
def test_counts_and_mrdb_mapping(exports, files, entries, recs):
    acc = json.loads((exports[0] / REL / "accessions.json").read_text())
    assert len(files) == 5299 and len(entries) == 5466 == len(recs)
    assert set(files) == set(acc["by_mrdb"])
    for ma, f in files.items():
        assert f["mrdb_acc"] == ma and f["n_source_records"] == len(f["sources"])
        srcs = [e["source_acc"] for e in f["sources"]]
        assert sorted(srcs) == sorted(acc["by_mrdb"][ma]["sources"])
        rep = acc["by_mrdb"][ma]["representative_source_acc"]
        assert srcs[0] == rep and [e["is_mrdb_representative"] for e in f["sources"]] == [a == rep for a in srcs]
        assert all(acc["by_source"][a] == ma == recs[a]["mrdb_acc"] for a in srcs)
        assert f["source_grades_differ"] == (len({e["grade"] for e in f["sources"]}) > 1)
    multi = [f for f in files.values() if len(f["sources"]) > 1]
    assert len(multi) == 129 and sum(len(f["sources"]) for f in multi) == 296
    assert sum(f["source_grades_differ"] for f in multi) == 43


def test_grade_fields_copied_verbatim(entries, recs):
    def o(v):
        return v if v != "" else None
    for a, e in entries.items():
        r = recs[a]
        assert e["grade"] == r["primary_grade"]
        assert e["host_association_status"] == r["host_association_status"]
        assert e["ambiguity_class"] == o(r["ambiguity_class"])
        assert e["host_ambiguity_class"] == o(r["host_ambiguity_class"])
        assert e["literature_status"] == r["literature_status"]
        assert e["not_reported_scope"] == o(r["not_reported_scope"])
        assert e["db_chain_status"] == r["db_chain_status"] and e["db_habitat_status"] == r["db_habitat_status"]
        assert e["flags"] == sorted(x for x in r["flags"].split(";") if x)
        assert e["has_usable_physical_habitat"] == (r["has_usable_habitat"] == "1")
        assert e["has_host_association"] == (r["has_host_association"] == "1")
        assert "pr7c1_grade" not in e and "normalized" not in json.dumps(e)


def test_summary_metrics_exact(summary):
    got = {m["id"]: (m["numerator"], m["denominator"]) for m in summary["metrics"]}
    for k, v in EXPECTED_METRICS.items():
        assert got[k] == v, (k, got.get(k), v)
    assert summary["audit_status"] == "PR7C1_AUDIT_PARTIAL"
    assert len(summary["cross_checked_against_audit"]) >= 20
    assert "not habitat frequencies" in summary["interpretation"]


def test_summary_cross_checks_audit_coverage_tsv(summary):
    cov = {c["metric"]: (int(c["numerator"]), int(c["denominator"])) for c in tsv(P / "habitat_coverage_summary.tsv")
           if c["unit"] == "source_record" and c["stratum_type"] == "all"}
    got = {m["id"]: (m["numerator"], m["denominator"]) for m in summary["metrics"]}
    for k in summary["cross_checked_against_audit"]:
        theirs = k.replace("grade:", "primary_grade:", 1) if k.startswith("grade:") else k
        assert cov[theirs] == got[k], k


# ----------------------------------------------------------------------------------------------- evidence
def test_every_item_resolves_to_its_evidence_row_and_back(entries, evs):
    rows = {r["evidence_id"]: r for r in evs}
    shown = {}
    for a, e in entries.items():
        for g, i in all_items(e):
            assert i["evidence_id"] not in shown
            shown[i["evidence_id"]] = (a, g, i)
    want = {r["evidence_id"] for r in evs if r["role"] in ROLE_TO_GROUP}
    assert set(shown) == want and len(want) == 59086  # nothing fabricated, nothing dropped
    for eid, (a, g, i) in shown.items():
        r = rows[eid]
        assert r["source_acc"] == a and ROLE_TO_GROUP[r["role"]] == g == ROLE_TO_GROUP[i["role"]]
        assert (i["role"], i["value_status"], i["evidence_source"], i["entity_accession"], i["field"]) == \
               (r["role"], r["value_status"], r["evidence_source"], r["entity_accession"], r["field_original"])
        assert (i["value"] if i["value"] is not None else "") == r["value_original"]
        assert i["browser_url"] == r["browser_url"] and (i["source_url"] or "") == r["source_url"]
        assert i["envo_ids"] == [x for x in r["envo_ids"].split(";") if x]
        assert (i["link_index"] if i["link_index"] is not None else "") == (int(r["link_index"]) if r["link_index"] else "")


def test_evidence_ids_recompute_including_none_doi_rule(evs, lit):
    he = hl = none_doi = 0
    for r in evs:
        if r["evidence_id"].startswith("HE"):
            key = "|".join(r[k] for k in ("source_acc", "evidence_source", "entity_accession", "link_index",
                                          "field_original", "value_original"))
            assert r["evidence_id"] == "HE" + sha(key.encode())[:12]
            he += 1
    ids = set()
    for acc, v in lit.items():
        for x in v.get("items", []):
            none_doi += x.get("doi") is None
            ids.add("HL" + sha(("|".join(str(x.get(k)) for k in ("pmid", "doi", "quote", "scope")) + acc).encode())[:12])
    hl = {r["evidence_id"] for r in evs if r["evidence_id"].startswith("HL")}
    assert he == 105659 and hl == ids and len(ids) == 91
    assert none_doi > 0  # the literal "None" rule is exercised


def test_literature_items_carry_traceable_citation(entries, lit):
    n = 0
    for a, e in entries.items():
        for g, i in all_items(e):
            if i["evidence_source"] != "literature":
                assert i["literature"] is None
                continue
            n += 1
            L = i["literature"]
            src = [x for x in lit[a]["items"] if str(x["pmid"]) == L["pmid"] and x["quote"] == i["value"]]
            assert len(src) == 1 and src[0]["scope"] == L["scope"]
            for k in ("doi", "locator", "access"):
                assert L[k] == (src[0].get(k) or None), (a, k)
            assert i["browser_url"] == f"https://pubmed.ncbi.nlm.nih.gov/{L['pmid']}/"
    assert n == 91
    assert sum(i["literature"]["doi"] is not None for e in entries.values() for g, i in all_items(e)
               if i["literature"]) > 0


def test_literature_sources_checked_copied(entries, lit):
    """Every source the literature review checked is listed on its record (PMID, DOI, title, access, outcome)."""
    n = 0
    for a, e in entries.items():
        got = e["literature_sources_checked"]
        want = sorted(({"pmid": str(s["pmid"]) if s.get("pmid") else None, "doi": s.get("doi") or None,
                        "title": s.get("title") or None, "access": s.get("access") or None,
                        "found_habitat_statement": s.get("found_habitat_statement")}
                       for s in lit.get(a, {}).get("sources_checked", [])),
                      key=lambda s: (s["pmid"] or "", s["doi"] or "", s["title"] or ""))
        assert got == want, a
        n += len(got)
    assert n == 502


def test_item_order_canonical(entries):
    """Items are in a fixed, documented order: role, source, entity, link index, evidence ID."""
    for e in entries.values():
        for g, xs in e["items"].items():
            keys = [(i["role"], i["evidence_source"], i["entity_accession"],
                     -1 if i["link_index"] is None else i["link_index"], i["evidence_id"]) for i in xs]
            assert keys == sorted(keys), (e["source_acc"], g)


# ----------------------------------------------------------------------------------------------- leakage / promotion
def test_no_host_to_physical_leakage_and_no_organism_promotion(entries):
    for a, e in entries.items():
        for g, xs in e["items"].items():
            assert {i["role"] for i in xs} <= GROUP_ROLES[g], (a, g)
        for i in e["items"]["physical"]:
            assert i["role"] not in ("host", "host_detail", "organism_context")
            if i["evidence_source"] == "literature":
                assert i["literature"]["scope"] in ("isolate", "rejected")
        for i in e["items"]["organism_context"]:
            assert i["literature"]["scope"] == "organism"
        if e["grade"] == "ORGANISM_CONTEXT_ONLY":
            assert not any(i["value_status"] == "usable" for i in e["items"]["physical"]
                           if i["role"] in ("env_broad_scale", "env_local_scale", "env_medium", "isolation_source"))


def test_host_only_records(entries):
    ho = [e for e in entries.values() if "host_association_only" in e["flags"]]
    assert len(ho) == 186
    for e in ho:
        assert e["grade"] == "NOT_REPORTED" and e["host_association_status"] in ("REPORTED", "AMBIGUOUS")
        assert not any(i["value_status"] == "usable" for i in e["items"]["physical"])
        assert any(i["value_status"] == "usable" for i in e["items"]["host"])
    hnp = [e for e in entries.values() if e["has_host_association"] and not e["has_usable_physical_habitat"]]
    assert len(hnp) == 207 and collections.Counter(e["grade"] for e in hnp) == {"NOT_REPORTED": 186, "AMBIGUOUS": 21}


def test_ambiguity_classes_preserved_and_values_not_merged(entries, recs):
    amb = [e for e in entries.values() if e["grade"] == "AMBIGUOUS"]
    assert len(amb) == 59 and all(e["ambiguity_class"] for e in amb)
    for e in amb:
        r = recs[e["source_acc"]]
        for role in ("env_broad_scale", "env_local_scale", "env_medium", "isolation_source"):
            want = sorted({v for v in r[f"{role}_original"].split(" || ") if v})
            got = sorted({i["value"] for i in e["items"]["physical"] if i["role"] == role and i["value_status"] == "usable"})
            assert got == want
    lvd = [e for e in amb if e["ambiguity_class"] == "LITERATURE_VS_DATABASE"]
    assert [e["source_acc"] for e in lvd] == ["A0A411LJN5"]


# ----------------------------------------------------------------------------------------------- special cases
def test_no_link_records_never_claim_not_reported_in_sample(entries):
    nl = {a for a, e in entries.items() if e["sample_link"] == "none"}
    assert nl == NO_LINK
    for a in nl:
        e = entries[a]
        assert e["db_chain_status"] == "NO_LINK" and "no_insdc_link" in e["flags"]
        if e["missingness"] is not None:
            assert e["missingness"]["database"] == "no_traceable_sample_link"
    for a, e in entries.items():
        if a not in nl and e["missingness"] is not None:
            assert e["missingness"]["database"] == "not_reported_in_linked_sample_records"
    assert entries["A0AAJ6N6B2"]["grade"] == "VERIFIED_ISOLATE"


def test_missingness_follows_scope(entries):
    m = {"database_only_literature_not_reviewed": "not_reviewed", "database_only_literature_inaccessible": "inaccessible",
         "database_and_literature": "reviewed_not_reported"}
    for e in entries.values():
        if e["grade"] == "NOT_REPORTED":
            assert e["missingness"]["literature"] == m[e["not_reported_scope"]]
        else:
            assert e["missingness"] is None and e["not_reported_scope"] is None


def test_quarantine(entries):
    q = [(a, i) for a, e in entries.items() for g, i in all_items(e) if i["quarantine"]]
    assert len(q) == 14 and {a for a, _ in q} == QUARANTINE_RECORDS
    for a, i in q:
        if a == "A0A6N7QP32":
            assert i["quarantine"] == "unprefixed_numeric_identifier" and i["value"].strip() == "00000316"
            assert i["role"] == "env_local_scale"
        else:
            assert i["quarantine"] == "envo_id_not_found_in_ols" and "0010003" in i["value"]
            assert "ENVO:00010003" not in i["envo_ids"] and "ENVO:0010003" not in i["envo_ids"]
    assert entries["A0A6N7QP32"]["mrdb_acc"] == "MRDB002823"


def test_invalid_placeholders_kept_not_usable(entries):
    inv = [(a, i) for a, e in entries.items() for g, i in all_items(e) if i["value_status"] == "invalid_placeholder"]
    assert len(inv) == 12 and {a for a, _ in inv} == {"A0ABS3TAH3", "A0ABS3TE24"}
    assert all(g == "physical" for a, e in entries.items() for g, i in all_items(e)
               if i["value_status"] == "invalid_placeholder")


def test_literature_lookup_failures_preserved(entries):
    lf = [e for e in entries.values() if e["literature_status"] == "LOOKUP_FAILED"]
    assert len(lf) == 24
    assert collections.Counter(e["grade"] for e in lf) == {"NOT_REPORTED": 23, "DIRECT_SAMPLE": 1}
    assert entries["A0A977XLG0"]["grade"] == "DIRECT_SAMPLE"
    assert all(e["missingness"]["literature"] == "inaccessible" for e in lf if e["grade"] == "NOT_REPORTED")


def test_host_tissue_isolation_sources(entries):
    assert sum("host_tissue_isolation_source_only" in e["flags"] for e in entries.values()) == 23


def test_accession_formats_and_urls(entries):
    for e in entries.values():
        for g, i in all_items(e):
            assert i["browser_url"].startswith("https://") and not any(c in i["browser_url"] for c in " \"'<>")
            assert i["source_url"] is None or i["source_url"].startswith("https://")


# ----------------------------------------------------------------------------------------------- determinism / safety
def _maps(exports):
    acc = json.loads((exports[0] / REL / "accessions.json").read_text())
    return acc["by_source"], {k: v["representative_source_acc"] for k, v in acc["by_mrdb"].items()}


def test_build_deterministic_and_matches_export(exports):
    by_source, rep = _maps(exports)
    a, b = hb.build(REPO, by_source, rep), hb.build(REPO, by_source, rep)
    assert a == b and len(a) == 5301
    for rel, (data, _) in a.items():
        assert (exports[0] / REL / rel).read_bytes() == data


def test_no_network_during_build(exports, monkeypatch):
    by_source, rep = _maps(exports)

    def boom(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    assert len(hb.build(REPO, by_source, rep)) == 5301


@pytest.fixture()
def fake_repo(tmp_path):
    """A repo-shaped copy holding only the habitat inputs and schema."""
    for rel in [*json.loads(CONTRACT.read_text())["inputs"], hb.SCHEMA_REL]:
        d = tmp_path / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, d)
    return tmp_path


@pytest.mark.parametrize("rel", sorted(json.loads(CONTRACT.read_text())["inputs"]))
def test_tampered_input_fails_closed(exports, fake_repo, rel):
    by_source, rep = _maps(exports)
    p = fake_repo / rel
    p.write_bytes(p.read_bytes() + b" ")
    with pytest.raises(hb.HabitatError) as e:
        hb.build(fake_repo, by_source, rep)
    assert e.value.code == "BLOCKED_HABITAT_SOURCE"
    with pytest.raises(ex.ExportError) as e2:
        ex.build_habitat(fake_repo, by_source, rep)
    assert e2.value.code == "BLOCKED_HABITAT_SOURCE" and ex.ExportError.CODES[e2.value.code] == 5


def test_missing_input_fails_closed(exports, fake_repo):
    by_source, rep = _maps(exports)
    (fake_repo / "docs/website/pr7c1/habitat_evidence.tsv").unlink()
    with pytest.raises(hb.HabitatError) as e:
        hb.build(fake_repo, by_source, rep)
    assert e.value.code == "BLOCKED_HABITAT_SOURCE"


def test_file_size_budget_enforced(exports, tmp_path, monkeypatch):
    """The per-file byte budget is enforced by the builder (real files are far below it, so lower it)."""
    by_source, rep = _maps(exports)
    c = json.loads(CONTRACT.read_text())
    c["expected"]["max_file_bytes"] = 4096
    p = tmp_path / "contract.json"
    p.write_text(json.dumps(c))
    monkeypatch.setattr(hb, "CONTRACT", p)
    with pytest.raises(hb.HabitatError, match="budget"):
        hb.build(REPO, by_source, rep)


def test_accession_map_mismatch_fails_closed(exports):
    by_source, rep = _maps(exports)
    bad = dict(by_source)
    k = sorted(bad)[0]
    bad[k] = "MRDB999999"
    with pytest.raises(hb.HabitatError):
        hb.build(REPO, bad, rep)


def test_no_wall_clock_in_habitat(H):
    import re
    iso = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
    for p in [H / "manifest.json", H / "summary.json", *sorted((H / "records").glob("*.json"))[:500]]:
        t = p.read_text(encoding="utf-8")
        assert not iso.search(t) and "/workspace" not in t and "/mnt/" not in t and "/tmp/" not in t
