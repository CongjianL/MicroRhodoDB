"""PR-7c.1 / PR-7c.1a habitat metadata availability audit: rule tests, fixture replay and output integrity.

Offline and self-contained:
- synthetic rule tests build minimal entity stores and exercise every grading rule, including the
  negative cases (culture/tissue/missing/placeholder/host-self/virus, failure never NOT_REPORTED,
  geography never habitat, NCBI UID pitfall);
- the committed pilot fixture (tests/data/pr7c1) re-classifies real records from their parsed entities and
  must reproduce the committed expected rows exactly;
- integrity tests read the committed audit outputs in docs/website/pr7c1.
No network access, no frozen DB required (the DB-dependent checks are in baseline.py / the Stage-1 report).
"""
from __future__ import annotations

import collections
import copy
import csv
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from tools.habitat_audit import classify as K  # noqa: E402
from tools.habitat_audit import literature as LIT  # noqa: E402
from tools.habitat_audit import litverify as LV  # noqa: E402
from tools.habitat_audit import normalize as N  # noqa: E402
from tools.habitat_audit import retrieve as R  # noqa: E402
from tools.habitat_audit import summarize as S  # noqa: E402

OUT = REPO / "docs" / "website" / "pr7c1"
FIX = REPO / "tests" / "data" / "pr7c1"
csv.field_size_limit(1 << 30)


# --------------------------------------------------------------------------- builders
def rec(acc="X00001", **kw):
    r = dict(source_acc=acc, mrdb_acc="MRDB999999", organism="Foo bar", organism_id=1, domain="Bacteria",
             phylum="Pseudomonadota", reviewed=0, is_seed=0, is_characterized=0, membership_status="m",
             status_group="member", status_group_audit="member", evidence_level="E4", is_engineered=0,
             counted=1, source_release="UniProtKB_2026_02", sequence_sha256="s", seq_group_size=1,
             exact_duplicate_of=None)
    r.update(kw)
    return r


def ent_empty():
    return {k: {} for k in ("uniprot", "uniparc", "cds", "sequence", "wgs_set", "insdc_flatfile", "proteome",
                            "assembly", "sample_ena", "sample_ncbi", "study", "envo")}


def source_row(sample="SAMN00000001", **fields):
    r = {f: "" for f in K.SOURCE_FEATURE_FIELDS}
    r.update(sample_accession=sample, study_accession="PRJNA1", scientific_name="Foo bar", mol_type="genomic DNA")
    r.update(fields)
    return r


def ent_cds(acc="X00001", organism="Foo bar", row=None, embl=None, lineage=("Bacteria",)):
    e = ent_empty()
    e["uniprot"][acc] = {"status": "active", "organism": organism, "taxon_id": 1, "request_key": "kU",
                         "organism_lineage": list(lineage), "proteomes": [],
                         "embl": embl if embl is not None else [
                             {"parent_accession": "PA000001", "protein_id": "PID00001.1", "status": "-",
                              "molecule_type": "Genomic_DNA"}]}
    if embl is None:
        e["cds"]["PID00001"] = {"status": "found", "request_key": "kC", "rows": [row or source_row(sample="")]}
    e["study"]["PRJNA1"] = {"status": "found", "request_key": "kS"}
    return e


def add_sample(e, s, ena=None, ncbi=None, ena_status="found", ncbi_status="found"):
    e["sample_ena"][s] = {"status": ena_status, "request_key": "kE" + s,
                          "attributes": [{"tag": t, "value": v} for t, v in (ena or [])]}
    e["sample_ncbi"][s] = {"status": ncbi_status, "request_key": "kN" + s,
                           "attributes": [{"name": t, "harmonized_name": t, "value": v} for t, v in (ncbi or [])]}


def grade(r, e, lit=None, searched=True):
    return K.classify_record(r, e, lit, searched)


def flags(row):
    return set(filter(None, row["flags"].split(";")))


def one_sample(ena=None, ncbi=None, **kw):
    e = ent_cds(row=source_row(sample="SAMN00000001", **kw))
    add_sample(e, "SAMN00000001", ena, ncbi)
    return e


# --------------------------------------------------------------------------- normalization
def test_tag_key_and_roles():
    assert N.tag_key("isolation source non-host-associated\ufffd") == "isolation source non host associated"
    assert N.role_for("isolation_source_non-host-associated\ufffd") == "isolation_source"
    assert N.role_for("env_biome") == "env_broad_scale"
    assert N.role_for("env_feature") == "env_local_scale"
    assert N.role_for("env_material") == "env_medium"
    assert N.role_for("Habitat") == "habitat_nonstandard"
    assert N.role_for("geo_loc_name") == "country"
    assert N.role_for("tissue") == "sample_material"
    assert N.role_for("host_body_site") == "host_detail"
    assert N.role_for("some_random_tag") is None
    assert set(N.HABITAT_ROLES) == {"env_broad_scale", "env_local_scale", "env_medium", "isolation_source", "host"}


@pytest.mark.parametrize("v", ["missing", "Not Applicable", "not collected", "N/A", "unknown", "-", "",
                               "missing: control sample", "restricted access"])
def test_missing_tokens(v):
    assert N.is_missing(v)


@pytest.mark.parametrize("v", ["seawater", "soil", "hot spring", "unknown lake sediment"])
def test_not_missing(v):
    assert not N.is_missing(v)


def test_culture_rule_whole_value_only():
    assert N.is_culture_term("pure culture")
    assert N.is_culture_term("Marine Broth 2216")
    assert N.is_culture_term("f/2 medium") or N.is_culture_term("f2 medium")
    assert not N.is_culture_term("enrichment culture from lake sediment")


def test_envo_ids_explicit_only():
    assert R.envo_ids_in("sea water [ENVO:00002149]") == ["ENVO:00002149"]
    assert R.envo_ids_in("ENVO_1000301") == ["ENVO:01000301"]
    assert R.envo_ids_in("seawater") == []  # never inferred


# --------------------------------------------------------------------------- grades
def test_direct_sample_basic():
    row, links, items = grade(rec(), one_sample(ena=[("env_medium", "sea water")], ncbi=[("env_medium", "Sea  Water")]))
    assert row["primary_grade"] == "DIRECT_SAMPLE"
    assert row["env_medium_normalized"] == "sea water"
    assert row["has_usable_habitat"] == 1
    assert row["linkage_route"] == "cds_protein_id"
    assert row["mapping_confidence"] == "HIGH"
    assert "conflict" not in flags(row)


def test_source_feature_isolation_source_is_direct():
    e = ent_cds(row=source_row(sample="", isolation_source="hot spring microbial mat"))
    row, _, _ = grade(rec(), e)
    assert row["primary_grade"] == "DIRECT_SAMPLE"
    assert "no_biosample_link" in flags(row)


def test_culture_only_is_not_habitat():
    row, _, items = grade(rec(), one_sample(ena=[("isolation_source", "pure culture")]))
    assert row["primary_grade"] == "NOT_REPORTED"
    assert "tissue_or_culture_only" in flags(row)
    assert row["sample_material"] == "pure culture"
    assert row["isolation_source_original"] == ""


def test_tissue_without_host_moves_to_material_with_host_stays():
    row, _, _ = grade(rec(), one_sample(ena=[("isolation_source", "leaf")]))
    assert row["primary_grade"] == "NOT_REPORTED" and "tissue_or_culture_only" in flags(row)
    row, _, _ = grade(rec(), one_sample(ena=[("isolation_source", "leaf"), ("host", "Zea mays")]))
    assert row["primary_grade"] == "DIRECT_SAMPLE"
    assert row["isolation_source_original"] == "leaf" and row["host_original"] == "Zea mays"


def test_tissue_tag_is_material_never_habitat():
    row, _, _ = grade(rec(), one_sample(ena=[("tissue", "gill")]))
    assert row["primary_grade"] == "NOT_REPORTED" and row["sample_material"] == "gill"


def test_missing_value_is_not_reported_and_flagged():
    row, _, _ = grade(rec(), one_sample(ncbi=[("env_broad_scale", "not applicable"), ("isolation_source", "missing")]))
    assert row["primary_grade"] == "NOT_REPORTED"
    assert "habitat_reported_missing" in flags(row)
    assert row["not_reported_scope"] == "database_only_literature_not_reviewed"


@pytest.mark.parametrize("v", ["environmental material", "biome", "ENVO:00010483", "environment [ENVO:01000254]"])
def test_placeholder_is_not_usable(v):
    e = one_sample(ncbi=[("env_medium", v)])
    e["envo"] = {"ENVO:00010483": {"status": "found"}, "ENVO:01000254": {"status": "found"}}
    row, _, items = grade(rec(), e)
    assert row["primary_grade"] == "NOT_REPORTED"
    assert any(i["value_status"] == "uninformative_placeholder" for i in items)


def test_host_is_self_ignored():
    row, _, _ = grade(rec(organism="Foo bar"), one_sample(ncbi=[("host", "Foo bar strain X")]))
    assert row["primary_grade"] == "NOT_REPORTED" and "host_is_self_ignored" in flags(row)


def test_virus_host_binomial_not_self():
    org = "Emiliania huxleyi virus 86"
    e = ent_cds(organism=org, lineage=("Viruses",), row=source_row(sample="", host="Emiliania huxleyi",
                                                                   scientific_name=org))
    row, _, _ = grade(rec(organism=org), e)
    # the host is kept (not self) but is host association, not a physical habitat (PR-7c.1a)
    assert row["host_original"] == "Emiliania huxleyi" and row["host_association_status"] == "REPORTED"
    assert row["primary_grade"] == "NOT_REPORTED" and row["pr7c1_grade"] == "DIRECT_SAMPLE"


def test_geography_is_never_habitat():
    row, _, _ = grade(rec(), one_sample(ncbi=[("geo_loc_name", "Japan: Okinawa"), ("lat_lon", "26.2 N 127.6 E"),
                                              ("collection_date", "2019-05-01"), ("depth", "200 m")]))
    assert row["primary_grade"] == "NOT_REPORTED"
    assert row["country"] == "Japan: Okinawa" and row["lat_lon"] == "26.2 N 127.6 E" and row["depth"] == "200 m"
    assert row["has_usable_habitat"] == 0


def test_nonstandard_habitat_tag_reported_not_graded():
    row, _, _ = grade(rec(), one_sample(ena=[("habitat", "soil")]))
    assert row["primary_grade"] == "NOT_REPORTED"
    assert row["habitat_nonstandard"] == "habitat: soil"


def test_free_text_title_is_not_habitat():
    e = one_sample()
    e["sample_ncbi"]["SAMN00000001"]["title"] = "Isolate from deep-sea sediment"
    row, _, _ = grade(rec(), e)
    assert row["primary_grade"] == "NOT_REPORTED" and "free_text_context_only" in flags(row)


# --------------------------------------------------------------------------- failures
@pytest.mark.parametrize("where", ["uniprot", "cds", "ena_sample", "ncbi_sample", "uniparc"])
def test_failure_is_never_not_reported(where):
    e = one_sample(ena=[("env_medium", "soil")])
    if where == "uniprot":
        e["uniprot"]["X00001"] = {"status": "failed", "request_key": "kU"}
    elif where == "cds":
        e["cds"]["PID00001"] = {"status": "failed", "request_key": "kC"}
    elif where == "ena_sample":
        e["sample_ena"]["SAMN00000001"] = {"status": "failed", "request_key": "kE"}
    elif where == "ncbi_sample":
        e["sample_ncbi"]["SAMN00000001"] = {"status": "failed", "request_key": "kN"}
    elif where == "uniparc":
        e["uniparc"]["X00001"] = {"status": "failed", "request_key": "kP", "embl_protein_ids": []}
    row, _, _ = grade(rec(), e)
    assert row["primary_grade"] == "LOOKUP_FAILED"
    assert row["db_chain_status"] == "INCOMPLETE" and row["chain_failures"]
    assert "chain_incomplete" in flags(row)


def test_missing_entity_counts_as_failure():
    e = ent_cds()
    del e["cds"]["PID00001"]
    row, _, _ = grade(rec(), e)
    assert row["primary_grade"] == "LOOKUP_FAILED"


def test_ambiguous_sample_match_is_failure():
    e = one_sample(ena=[("env_medium", "soil")])
    e["sample_ena"]["SAMN00000001"] = {"status": "ambiguous_match", "request_key": "kE", "matches": ["A", "B"]}
    row, _, _ = grade(rec(), e)
    assert row["primary_grade"] == "LOOKUP_FAILED"


def test_no_link_is_not_reported_with_flag():
    row, _, _ = grade(rec(), ent_cds(embl=[]))
    assert row["primary_grade"] == "NOT_REPORTED" and "no_insdc_link" in flags(row)
    assert row["db_chain_status"] == "NO_LINK"


def test_not_searched():
    row, links, items = grade(rec(), ent_empty(), searched=False)
    assert row["primary_grade"] == "NOT_SEARCHED" and links == [] and items == []


def test_flatfile_route():
    e = ent_cds(embl=[{"parent_accession": "ABCD01000123", "protein_id": "-", "status": "-",
                       "molecule_type": "Genomic_DNA"}])
    e["sequence"]["ABCD01000123"] = {"status": "not_found", "request_key": "kQ"}
    e["wgs_set"]["ABCD01"] = {"status": "not_found", "request_key": "kW"}
    e["insdc_flatfile"]["ABCD01000123"] = {"status": "found", "request_key": "kF", "samples": ["SAMN00000009"],
                                           "studies": ["PRJNA9"]}
    add_sample(e, "SAMN00000009", ncbi=[("isolation_source", "rice paddy soil")])
    row, links, _ = grade(rec(), e)
    assert links[0]["route"] == "insdc_flatfile_biosample"
    assert row["primary_grade"] == "DIRECT_SAMPLE"
    e["insdc_flatfile"]["ABCD01000123"] = {"status": "failed", "request_key": "kF"}
    row, _, _ = grade(rec(), e)
    assert row["primary_grade"] == "LOOKUP_FAILED" and "ena_flatfile:ABCD01000123" in row["chain_failures"]


def test_ncbi_uid_pitfall_maps_by_returned_accession_only():
    """efetch by the numeric part of SAMEA5987284 returns SAMN05987284; it must NOT be accepted."""
    xml = ('<BioSampleSet><BioSample id="5987284" accession="SAMN05987284"><Ids>'
           '<Id db="BioSample">SAMN05987284</Id></Ids><Description><Title>t</Title></Description>'
           '<Attributes><Attribute attribute_name="isolation_source" harmonized_name="isolation_source">'
           'wrong sample</Attribute></Attributes></BioSample></BioSampleSet>')

    class FakeCache:
        def post(self, url, data):
            if url == R.NCBI_ESEARCH:
                return {"ok": True, "status": 200, "text": json.dumps({"esearchresult": {"idlist": ["5987284"]}})}
            return {"ok": True, "status": 200, "text": xml}

    out = R.fetch_ncbi_biosamples(FakeCache(), ["SAMEA5987284"])
    assert out["SAMEA5987284"]["status"] == "not_found"
    out = R.fetch_ncbi_biosamples(FakeCache(), ["SAMN05987284"])
    assert out["SAMN05987284"]["status"] == "found"


def test_ncbi_search_failure_is_failed():
    class FailCache:
        def post(self, url, data):
            return {"ok": False, "status": 503, "text": ""}

    out = R.fetch_ncbi_biosamples(FailCache(), ["SAMN00000001"])
    assert out["SAMN00000001"]["status"] == "failed"


# --------------------------------------------------------------------------- agreement / conflict
def two_samples(v1, v2, role="env_medium", envo=None):
    e = ent_cds(embl=[{"parent_accession": "PA1", "protein_id": "PID00001.1", "status": "-", "molecule_type": "x"},
                      {"parent_accession": "PA2", "protein_id": "PID00002.1", "status": "-", "molecule_type": "x"}])
    e["cds"]["PID00001"] = {"status": "found", "request_key": "k1", "rows": [source_row(sample="SAMN00000001")]}
    e["cds"]["PID00002"] = {"status": "found", "request_key": "k2", "rows": [source_row(sample="SAMN00000002")]}
    add_sample(e, "SAMN00000001", ncbi=[(role, v1)])
    add_sample(e, "SAMN00000002", ncbi=[(role, v2)])
    e["envo"] = envo or {}
    return e


def test_multi_sample_agreement_case_whitespace():
    row, _, _ = grade(rec(), two_samples("Marine  Sediment", "marine sediment"))
    assert row["primary_grade"] == "DIRECT_SAMPLE" and "multi_sample" in flags(row)


def test_multi_sample_disagreement_is_ambiguous_across():
    row, _, _ = grade(rec(), two_samples("marine sediment", "seawater"))
    assert row["primary_grade"] == "AMBIGUOUS"
    assert row["conflict_roles"] == "env_medium"
    assert row["conflict_scope"] == "env_medium:across_sample_units"
    assert row["conflict_kind"] == "env_medium:distinct_values"


def test_identical_envo_sets_agree_despite_text():
    envo = {"ENVO:00002149": {"status": "found"}}
    row, _, _ = grade(rec(), two_samples("sea water [ENVO:00002149]", "seawater (ENVO:00002149)", envo=envo))
    assert row["primary_grade"] == "DIRECT_SAMPLE"


def test_punctuation_difference_is_still_ambiguous_strict_rule():
    row, _, _ = grade(rec(), two_samples("sea-water", "sea water"))
    assert row["primary_grade"] == "AMBIGUOUS" and row["conflict_kind"] == "env_medium:punctuation_only"


def test_within_sample_unit_conflict():
    e = ent_cds(row=source_row(sample="SAMN00000001", isolation_source="apple"))
    add_sample(e, "SAMN00000001", ncbi=[("isolation_source", "Malus domestica")])
    row, _, _ = grade(rec(), e)
    assert row["primary_grade"] == "AMBIGUOUS"
    assert row["conflict_scope"] == "isolation_source:within_sample_unit"


def test_different_roles_never_conflict():
    row, _, _ = grade(rec(), one_sample(ncbi=[("env_medium", "sediment"), ("isolation_source", "lake")]))
    assert row["primary_grade"] == "DIRECT_SAMPLE"


def test_invalid_envo_flagged_and_dropped():
    e = one_sample(ncbi=[("env_medium", "soil [ENVO:99999999]")])
    e["envo"] = {"ENVO:99999999": {"status": "not_found"}}
    row, _, _ = grade(rec(), e)
    assert "envo_id_invalid" in flags(row) and row["env_medium_envo_ids"] == ""
    assert row["primary_grade"] == "DIRECT_SAMPLE"


# --------------------------------------------------------------------------- literature
def lit(scope="isolate", verified=True, consistent="not_applicable", status=None):
    st = status or {"isolate": "ISOLATE_EVIDENCE", "organism": "ORGANISM_CONTEXT"}.get(scope, "NOT_REPORTED")
    return {"literature_status": st, "items": [{"scope": scope, "parent_verified": verified, "pmid": "1",
                                                "quote": "strain X was isolated from a salt marsh",
                                                "habitat_text": "salt marsh", "consistent_with_db": consistent,
                                                "locator": "Abstract", "source_url": "u"}]}


def test_verified_isolate_without_db():
    row, _, ev = grade(rec(is_characterized=1), one_sample(), lit())
    assert row["primary_grade"] == "VERIFIED_ISOLATE" and row["mapping_confidence"] == "LITERATURE"
    assert row["has_usable_habitat"] == 1
    assert any(i["role"] == "literature_isolate" and i["value_status"] == "usable" for i in ev)


def test_unverified_literature_is_ignored():
    row, _, ev = grade(rec(is_characterized=1), one_sample(), lit(verified=False))
    assert row["primary_grade"] == "NOT_REPORTED"
    assert any(i["value_status"].startswith("rejected") for i in ev)


def test_organism_context_is_not_usable():
    row, _, _ = grade(rec(is_seed=1), one_sample(), lit(scope="organism"))
    assert row["primary_grade"] == "ORGANISM_CONTEXT_ONLY" and row["has_usable_habitat"] == 0


def test_literature_inconsistent_with_db_is_ambiguous():
    row, _, _ = grade(rec(is_characterized=1), one_sample(ncbi=[("isolation_source", "soil")]),
                      lit(consistent="inconsistent"))
    assert row["primary_grade"] == "AMBIGUOUS" and row["db_habitat_status"] == "DIRECT_SAMPLE"
    # dictionary s.8: a literature-only conflict gives mapping_confidence LITERATURE (validation finding D5)
    assert row["conflict_roles"] == "" and row["mapping_confidence"] == "LITERATURE"


def test_db_conflict_keeps_db_mapping_confidence():
    row, _, _ = grade(rec(), one_sample(ncbi=[("isolation_source", "soil")], ena=[("isolation_source", "lake")]))
    assert row["primary_grade"] == "AMBIGUOUS" and row["mapping_confidence"] in ("HIGH", "MEDIUM")


def test_db_direct_takes_precedence_over_literature():
    row, _, _ = grade(rec(is_characterized=1), one_sample(ncbi=[("isolation_source", "salt marsh")]),
                      lit(consistent="consistent"))
    assert row["primary_grade"] == "DIRECT_SAMPLE" and row["literature_status"] == "ISOLATE_EVIDENCE"


def test_literature_outside_subset_is_not_searched():
    row, _, ev = grade(rec(), one_sample(), lit())
    assert row["primary_grade"] == "NOT_REPORTED" and row["literature_status"] == "NOT_SEARCHED"
    assert row["not_reported_scope"] == "database_only_literature_not_reviewed"
    assert not any(i["evidence_source"] == "literature" for i in ev)


def test_literature_lookup_failed_keeps_database_chain_scope():
    row, _, _ = grade(rec(is_seed=1), one_sample(), {"literature_status": "LOOKUP_FAILED", "items": []})
    assert row["primary_grade"] == "NOT_REPORTED" and row["not_reported_scope"] == "database_only_literature_inaccessible"
    assert row["literature_status"] == "LOOKUP_FAILED"  # preserved, no annotation invented
    row, _, _ = grade(rec(is_seed=1), one_sample(), {"literature_status": "NOT_REPORTED", "items": []})
    assert row["not_reported_scope"] == "database_and_literature"


def test_literature_apply_rules():
    raw = {"A1": {"literature_status": "ISOLATE_EVIDENCE", "sources_checked": [],
                  "items": [{"scope": "isolate", "quote": "q", "habitat_text": "h"}]},
           "A2": {"literature_status": "NOT_REPORTED", "sources_checked": [{"access": "not_accessible"}], "items": []},
           "P69051": {"literature_status": "ISOLATE_EVIDENCE", "sources_checked": [],
                      "items": [{"scope": "isolate", "quote": "q", "habitat_text": "Western Australia"}]},
           "Q18DH5": {"literature_status": "ISOLATE_EVIDENCE", "sources_checked": [],
                      "items": [{"scope": "isolate", "quote": "q", "habitat_text": "solar saltern"}]}}
    ok = {"quote_found_in_source": True, "habitat_text_in_quote": True}
    ver = {"A1#0": {"quote_found_in_source": False, "habitat_text_in_quote": True}, "P69051#0": ok, "Q18DH5#0": ok}
    out, rows = LIT.apply(raw, ver)
    assert out["A1"]["literature_status"] == "NOT_REPORTED"  # unverified quote rejected
    assert out["A1"]["items"][0]["scope"] == "rejected"
    assert out["A2"]["literature_status"] == "LOOKUP_FAILED"  # inaccessible is never NOT_REPORTED
    assert out["P69051"]["items"][0]["scope"] == "rejected"  # geography only
    assert out["Q18DH5"]["literature_status"] == "ORGANISM_CONTEXT"  # demoted
    assert len(rows) == 3


def test_litverify_normalization():
    a = LV.norm_text("strain DSW-6<sup>T</sup> was isolated from \u201cdeep\u2013sea\u201d  water [ 12 ]")
    b = LV.norm_text('Strain DSW-6T was isolated from "deep-sea" water [12]')
    assert a == b


# --------------------------------------------------------------------------- MRDB rollup
def test_mrdb_rollup_never_collapses_failure_to_not_reported():
    rows = [dict(source_acc="A", mrdb_acc="M1", primary_grade="NOT_REPORTED"),
            dict(source_acc="B", mrdb_acc="M1", primary_grade="LOOKUP_FAILED"),
            dict(source_acc="C", mrdb_acc="M2", primary_grade="NOT_REPORTED"),
            dict(source_acc="D", mrdb_acc="M3", primary_grade="AMBIGUOUS"),
            dict(source_acc="E", mrdb_acc="M3", primary_grade="DIRECT_SAMPLE")]
    g = {d["mrdb_acc"]: d["primary_grade"] for d in S.mrdb_rollup(rows)}
    assert g == {"M1": "LOOKUP_FAILED", "M2": "NOT_REPORTED", "M3": "DIRECT_SAMPLE"}


# --------------------------------------------------------------------------- fixture replay
def _fixture():
    if not (FIX / "fixture_entities.json").exists():
        pytest.skip("pilot fixture not present")
    ent = json.loads((FIX / "fixture_entities.json").read_text(encoding="utf-8"))
    recs = json.loads((FIX / "fixture_records.json").read_text(encoding="utf-8"))
    litf = json.loads((FIX / "fixture_literature.json").read_text(encoding="utf-8"))
    with open(FIX / "fixture_expected_records.tsv", encoding="utf-8", newline="") as fh:
        exp = {r["source_acc"]: r for r in csv.DictReader(fh, delimiter="\t")}
    return ent, recs, litf, exp


def _cell(v):
    return "" if v is None else str(v)


def test_fixture_replay_matches_expected():
    ent, recs, litf, exp = _fixture()
    assert set(exp) == {r["source_acc"] for r in recs}
    for r in recs:
        row, _, _ = K.classify_record(r, ent, litf.get(r["source_acc"]), True)
        e = exp[r["source_acc"]]
        diff = {k: (_cell(row.get(k)), e[k]) for k in e if _cell(row.get(k)) != e[k]}
        assert not diff, (r["source_acc"], diff)


def test_fixture_covers_grades_and_routes():
    _, _, _, exp = _fixture()
    grades = {r["primary_grade"] for r in exp.values()}
    assert {"DIRECT_SAMPLE", "NOT_REPORTED", "AMBIGUOUS"} <= grades
    routes = {x for r in exp.values() for x in r["linkage_route"].split(";") if x}
    assert {"cds_protein_id", "proteome_assembly", "insdc_flatfile_biosample", "uniparc_embl_protein"} <= routes


def test_fixture_failure_injection():
    """Removing any sample a fixture record depends on must turn it into LOOKUP_FAILED, never NOT_REPORTED."""
    ent, recs, litf, exp = _fixture()
    n = 0
    for r in recs:
        row, links, _ = K.classify_record(r, ent, litf.get(r["source_acc"]), True)
        samples = [s for L in links for s in L["samples"]]
        if not samples:
            continue
        e2 = copy.deepcopy(ent)
        e2["sample_ncbi"].pop(samples[0], None)
        row2, _, _ = K.classify_record(r, e2, litf.get(r["source_acc"]), True)
        assert row2["primary_grade"] == "LOOKUP_FAILED", r["source_acc"]
        n += 1
    assert n >= 5


# --------------------------------------------------------------------------- committed outputs
def _read(name):
    p = OUT / name
    if not p.exists():
        pytest.skip(f"{name} not present")
    with open(p, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def test_output_every_record_once():
    rows = _read("habitat_record_availability.tsv")
    accs = [r["source_acc"] for r in rows]
    assert len(accs) == 5466 and len(set(accs)) == 5466
    c = collections.Counter((r["counted"], r["is_engineered"]) for r in rows)
    assert c[("1", "0")] == 5460 and c[("0", "1")] == 6
    assert len({r["mrdb_acc"] for r in rows if r["mrdb_acc"]}) == 5299
    assert {r["primary_grade"] for r in rows} <= {"DIRECT_SAMPLE", "VERIFIED_ISOLATE", "ORGANISM_CONTEXT_ONLY",
                                                  "AMBIGUOUS", "NOT_REPORTED", "LOOKUP_FAILED", "NOT_SEARCHED"}


def test_output_evidence_traceability():
    rows = _read("habitat_record_availability.tsv")
    ev = {e["evidence_id"]: e for e in _read("habitat_evidence.tsv")}
    req = {q["request_key"]: q for q in _read("habitat_requests.tsv")}
    for r in rows:
        ids = [x for x in r["evidence_ids"].split(";") if x]
        if r["primary_grade"] in ("DIRECT_SAMPLE", "VERIFIED_ISOLATE"):
            assert ids, r["source_acc"]
        for i in ids:
            e = ev[i]
            assert e["source_acc"] == r["source_acc"] and e["value_status"] == "usable"
            q = req[e["request_key"]]  # every usable value traces to a recorded, successful request
            assert q["url"] and q["ok"] in ("1", "True") and q["status"] == "200", i
            if e["evidence_source"] == "literature":
                assert q["purpose"] == "literature_verification" and e["source_url"], i
        if r["primary_grade"] == "DIRECT_SAMPLE":  # physical habitat only (host never suffices, PR-7c.1a)
            assert any(ev[i]["role"] in N.PHYSICAL_ROLES for i in ids), r["source_acc"]
        if r["primary_grade"] == "LOOKUP_FAILED":
            assert r["chain_failures"]
        if r["primary_grade"] == "NOT_REPORTED":
            assert not r["chain_failures"]


def test_output_no_habitat_from_non_habitat_roles():
    for e in _read("habitat_evidence.tsv"):
        if e["value_status"] == "usable" and e["evidence_source"] != "literature":
            assert e["role"] in N.HABITAT_ROLES, e["evidence_id"]


def test_output_summary_recomputes():
    rows = _read("habitat_record_availability.tsv")
    summ = _read("habitat_coverage_summary.tsv")
    c = collections.Counter(r["primary_grade"] for r in rows)
    dom = collections.Counter((r["domain"], r["primary_grade"]) for r in rows)
    n = 0
    for s in summ:
        if s["unit"] != "source_record" or not s["metric"].startswith("grade:"):
            continue
        g = s["metric"].split(":", 1)[1]
        if s["stratum_type"] == "all":
            assert int(s["numerator"]) == c.get(g, 0) and int(s["denominator"]) == 5466
            n += 1
        elif s["stratum_type"] == "domain":
            assert int(s["numerator"]) == dom.get((s["stratum"], g), 0)
            n += 1
    assert n > 0


def test_no_production_habitat_keys():
    """PR-7c.1 must not add habitat values to the production web export.

    PR-7c.2 adds the habitat sidecar under v1.6.0/habitat/ (its own schema and tests in tests/test_web_pr7c2.py);
    habitat keys must stay confined to it, so every core export file is still checked."""
    exp = REPO / "web" / "public" / "data" / "v1.6.0"
    if not exp.exists():
        pytest.skip("web export not present")
    for p in sorted(exp.rglob("*.json")):
        if p.relative_to(exp).parts[0] == "habitat":
            continue
        txt = p.read_text(encoding="utf-8")
        for k in ("env_broad_scale", "env_medium", "isolation_source", "primary_grade", "habitat_evidence"):
            assert f'"{k}"' not in txt, (p.name, k)


def test_dictionary_listed_material_terms():
    # validation findings D1-D3: terms now enumerated in the dictionary (section 5)
    for v in ("Strain collection", "viral plaque", "plaques", "culture medium", "BG-11 medium", "marine agar 2216"):
        assert N.is_culture_term(v), v
    for v in ("liquid culture medium", "enrichment culture from lake sediment", "culture medi um"):
        assert not N.is_culture_term(v), v
    for v in ("fruiting body", "Fruiting bodies.", "frond"):
        assert N.is_tissue_term(v), v
    assert not N.is_missing("0") and N.is_missing("not applicable: control")


# --------------------------------------------------------------------------- PR-7c.1a scientific semantics
def test_roles_physical_vs_host():
    assert N.PHYSICAL_ROLES == ("env_broad_scale", "env_local_scale", "env_medium", "isolation_source")
    assert N.HOST_ROLES == ("host",)
    assert set(N.PHYSICAL_ROLES) | set(N.HOST_ROLES) == set(N.HABITAT_ROLES)
    assert not set(N.PHYSICAL_ROLES) & set(N.HOST_ROLES)


def test_host_only_is_not_physical_habitat():
    row, _, ev = grade(rec(), one_sample(ncbi=[("host", "Homo sapiens")]))
    assert row["primary_grade"] == "NOT_REPORTED" and row["has_usable_habitat"] == 0
    assert row["host_association_status"] == "REPORTED" and row["has_host_association"] == 1
    assert "host_association_only" in flags(row)
    assert row["pr7c1_grade"] == "DIRECT_SAMPLE"  # legacy view preserved for transition tables
    assert row["db_habitat_status"] == "NOT_REPORTED" and row["mapping_confidence"] == ""
    assert row["host_original"] == "Homo sapiens"  # provenance preserved
    assert [i["value_status"] for i in ev if i["role"] == "host"] == ["usable"]


def test_host_plus_physical_is_direct_and_reported():
    row, _, _ = grade(rec(), one_sample(ncbi=[("host", "Zea mays"), ("isolation_source", "rhizosphere soil")]))
    assert row["primary_grade"] == "DIRECT_SAMPLE" and row["host_association_status"] == "REPORTED"
    assert "host_association_only" not in flags(row)


def test_host_conflict_with_agreeing_physical_is_direct():
    row, _, _ = grade(rec(), one_sample(ena=[("host", "Mus musculus"), ("isolation_source", "gut")],
                                        ncbi=[("host", "Rattus norvegicus"), ("isolation_source", "gut")]))
    assert row["primary_grade"] == "DIRECT_SAMPLE" and row["host_association_status"] == "AMBIGUOUS"
    assert row["pr7c1_grade"] == "AMBIGUOUS" and row["ambiguity_class"] == ""
    assert row["host_ambiguity_class"] == "DISTINCT_SAME_SAMPLE"
    assert "host_conflict" in flags(row) and "conflict" not in flags(row)
    assert row["conflict_roles"] == "host"  # raw observation preserved
    assert "Mus musculus" in row["host_original"] and "Rattus norvegicus" in row["host_original"]


def test_host_only_conflict_is_not_reported_physically():
    row, _, _ = grade(rec(), one_sample(ena=[("host", "Mus musculus")], ncbi=[("host", "Rattus norvegicus")]))
    assert row["primary_grade"] == "NOT_REPORTED" and row["pr7c1_grade"] == "AMBIGUOUS"
    assert row["host_association_status"] == "AMBIGUOUS"


@pytest.mark.parametrize("v,exp", [("0", True), ("00", True), ("0.0", True), (" 0 ", True),
                                   ("00000316", False), ("ENVO:00000316", False), ("10", False), ("soil", False)])
def test_zero_placeholder_rule(v, exp):
    assert N.is_zero_placeholder(v, "env_local_scale") is exp
    assert N.is_zero_placeholder(v, "isolation_source") is False  # MIxS env fields only
    assert N.is_zero_placeholder(v, "host") is False


def test_zero_placeholder_keeps_isolation_source_soil():
    e = one_sample(ena=[("env_broad_scale", "0"), ("env_local_scale", "0"), ("env_medium", "0")],
                   ncbi=[("env_broad_scale", "0"), ("env_local_scale", "0"), ("env_medium", "0"),
                         ("isolation_source", "soil")])
    row, _, ev = grade(rec(), e)
    zero = [i for i in ev if i["value_original"] == "0"]
    assert len(zero) == 6 and {i["value_status"] for i in zero} == {"invalid_placeholder"}
    assert row["primary_grade"] == "DIRECT_SAMPLE" and row["isolation_source_original"] == "soil"
    assert row["env_broad_scale_original"] == row["env_local_scale_original"] == row["env_medium_original"] == ""
    assert "invalid_placeholder_value" in flags(row)
    assert row["pr7c1_grade"] == "DIRECT_SAMPLE"


def test_zero_only_env_is_not_reported():
    row, _, _ = grade(rec(), one_sample(ncbi=[("env_medium", "0")]))
    assert row["primary_grade"] == "NOT_REPORTED" and row["pr7c1_grade"] == "DIRECT_SAMPLE"


def test_envo_like_digits_unchanged():
    row, _, ev = grade(rec(), one_sample(ncbi=[("env_local_scale", "00000316")]))
    assert row["primary_grade"] == "DIRECT_SAMPLE" and row["env_local_scale_original"] == "00000316"


@pytest.mark.parametrize("ena,ncbi,cls", [
    ([("isolation_source", "sea-water")], [("isolation_source", "sea water")], "FORMATTING_ONLY"),
    ([("isolation_source", "lake sediment")], [("isolation_source", "sediment")], "NESTED_WORDING"),
    ([("isolation_source", "hot spring")], [("isolation_source", "sea water")], "DISTINCT_SAME_SAMPLE"),
])
def test_ambiguity_classes_within_sample(ena, ncbi, cls):
    row, _, _ = grade(rec(), one_sample(ena=ena, ncbi=ncbi))
    assert row["primary_grade"] == "AMBIGUOUS" and row["ambiguity_class"] == cls
    assert row["isolation_source_original"].count(K.SEP) == 1  # both raw values preserved, none chosen


def test_ambiguity_class_across_samples():
    e = ent_cds(embl=[{"parent_accession": "PA1", "protein_id": "P1.1", "status": "-", "molecule_type": "g"},
                      {"parent_accession": "PA2", "protein_id": "P2.1", "status": "-", "molecule_type": "g"}])
    e["cds"]["P1"] = {"status": "found", "request_key": "k1", "rows": [source_row(sample="SAMN1")]}
    e["cds"]["P2"] = {"status": "found", "request_key": "k2", "rows": [source_row(sample="SAMN2")]}
    add_sample(e, "SAMN1", ncbi=[("isolation_source", "hot spring")])
    add_sample(e, "SAMN2", ncbi=[("isolation_source", "sea water")])
    row, _, _ = grade(rec(), e)
    assert row["primary_grade"] == "AMBIGUOUS" and row["ambiguity_class"] == "DISTINCT_ACROSS_SAMPLES"


def test_ambiguity_class_literature_vs_database():
    row, _, _ = grade(rec(is_seed=1), one_sample(ncbi=[("isolation_source", "salt marsh")]), lit(consistent="inconsistent"))
    assert row["primary_grade"] == "AMBIGUOUS" and row["ambiguity_class"] == "LITERATURE_VS_DATABASE"
    assert "literature_conflict" in flags(row) and row["mapping_confidence"] == "LITERATURE"


def test_literature_inconsistent_with_host_only_is_not_physical_conflict():
    row, _, _ = grade(rec(is_seed=1), one_sample(ncbi=[("host", "Homo sapiens")]), lit(consistent="inconsistent"))
    assert row["primary_grade"] == "VERIFIED_ISOLATE" and row["pr7c1_grade"] == "AMBIGUOUS"


@pytest.mark.parametrize("ls,scope", [("NOT_SEARCHED", "database_only_literature_not_reviewed"),
                                      ("LOOKUP_FAILED", "database_only_literature_inaccessible"),
                                      ("NOT_REPORTED", "database_and_literature")])
def test_not_reported_scope_values(ls, scope):
    assert K.not_reported_scope("NOT_REPORTED", ls) == scope
    assert K.not_reported_scope("DIRECT_SAMPLE", ls) == ""


EXPECTED_PR7C1 = {"DIRECT_SAMPLE": 2631, "VERIFIED_ISOLATE": 17, "ORGANISM_CONTEXT_ONLY": 36, "AMBIGUOUS": 137,
                  "NOT_REPORTED": 2645}
EXPECTED_PR7C1A = {"DIRECT_SAMPLE": 2523, "VERIFIED_ISOLATE": 17, "ORGANISM_CONTEXT_ONLY": 36, "AMBIGUOUS": 59,
                   "NOT_REPORTED": 2831}


def test_output_pr7c1_grade_preserved_and_corrected_counts():
    rows = _read("habitat_record_availability.tsv")
    assert dict(collections.Counter(r["pr7c1_grade"] for r in rows)) == EXPECTED_PR7C1
    assert dict(collections.Counter(r["primary_grade"] for r in rows)) == EXPECTED_PR7C1A
    ho = [r for r in rows if "host_association_only" in r["flags"].split(";")]
    assert len(ho) == 186 and sum(r["pr7c1_grade"] == "DIRECT_SAMPLE" for r in ho) == 171
    assert not any(r["primary_grade"] in ("DIRECT_SAMPLE", "AMBIGUOUS") for r in ho)
    assert collections.Counter(r["primary_grade"] for r in ho) == {"NOT_REPORTED": 186}
    assert collections.Counter(r["host_association_status"] for r in rows) == {"NOT_REPORTED": 4711, "REPORTED": 671,
                                                                              "AMBIGUOUS": 84}
    for r in rows:
        if r["primary_grade"] == "DIRECT_SAMPLE":
            assert any(r[f"{ro}_original"] for ro in N.PHYSICAL_ROLES), r["source_acc"]
        assert (r["ambiguity_class"] != "") == (r["primary_grade"] == "AMBIGUOUS"), r["source_acc"]
        assert (r["host_ambiguity_class"] != "") == (r["host_association_status"] == "AMBIGUOUS")
        assert (r["not_reported_scope"] != "") == (r["primary_grade"] == "NOT_REPORTED")


def test_output_zero_placeholders():
    rows = {r["source_acc"]: r for r in _read("habitat_record_availability.tsv")}
    for a in ("A0ABS3TAH3", "A0ABS3TE24"):
        r = rows[a]
        assert r["primary_grade"] == "DIRECT_SAMPLE" and r["isolation_source_original"] == "soil"
        assert r["env_broad_scale_original"] == r["env_local_scale_original"] == r["env_medium_original"] == ""
    ev = [e for e in _read("habitat_evidence.tsv") if e["value_status"] == "invalid_placeholder"]
    assert len(ev) == 12 and {e["source_acc"] for e in ev} == {"A0ABS3TAH3", "A0ABS3TE24"}
    assert all(e["value_original"] == "0" and e["role"] in N.MIXS_ENV_ROLES for e in ev)
    assert rows["A0A6N7QP32"]["env_local_scale_original"] == "00000316"  # observation only, unchanged


def test_output_literature_unresolved_preserved():
    rows = _read("habitat_record_availability.tsv")
    lf = [r for r in rows if r["literature_status"] == "LOOKUP_FAILED"]
    assert len(lf) == 24
    assert not any(r["literature_isolate_text"] or r["organism_context_text"] for r in lf)
    nr = [r for r in lf if r["primary_grade"] == "NOT_REPORTED"]
    assert all(r["not_reported_scope"] == "database_only_literature_inaccessible" for r in nr)
    lit_ev = [e for e in _read("habitat_evidence.tsv") if e["evidence_source"] == "literature"]
    assert not {e["source_acc"] for e in lit_ev} & {r["source_acc"] for r in lf}


def test_output_ambiguity_and_scope_denominators():
    rows = _read("habitat_record_availability.tsv")
    summ = {(s["metric"]): s for s in _read("habitat_coverage_summary.tsv")
            if s["unit"] == "source_record" and s["stratum_type"] == "all"}
    amb = [r for r in rows if r["primary_grade"] == "AMBIGUOUS"]
    for c in ("FORMATTING_ONLY", "NESTED_WORDING", "DISTINCT_SAME_SAMPLE", "DISTINCT_ACROSS_SAMPLES",
              "LITERATURE_VS_DATABASE"):
        s = summ[f"ambiguity_class:{c}"]
        assert int(s["denominator"]) == len(amb) == 59
        assert int(s["numerator"]) == sum(r["ambiguity_class"] == c for r in amb)
    nr = [r for r in rows if r["primary_grade"] == "NOT_REPORTED"]
    tot = 0
    for k, s in summ.items():
        if k.startswith("not_reported_scope:"):
            assert int(s["denominator"]) == len(nr)
            tot += int(s["numerator"])
    assert tot == len(nr)
    assert int(summ["host_association_only"]["numerator"]) == 186
    assert "usable_field:host" not in summ and int(summ["host_field:host"]["numerator"]) == 755


def test_generated_svgs_have_no_trailing_whitespace():
    for p in sorted((OUT / "figures").glob("*.svg")):
        for i, line in enumerate(p.read_text(encoding="utf-8").split("\n")):
            assert line == line.rstrip(), (p.name, i)


def test_no_hardcoded_machine_paths():
    root = REPO / "tools" / "habitat_audit"
    for p in sorted(root.glob("*.py")):
        if p.name == "mutation_audit.py":
            continue  # holds the hardcoded-path mutation string on purpose
        assert "/workspace" not in p.read_text(encoding="utf-8"), p.name
    from tools.habitat_audit import common as C
    assert C.DEFAULT_CACHE.is_absolute() and (C.DEFAULT_CACHE == C.WORK_ROOT / "habitat_cache" or
                                             __import__("os").environ.get("MRDB_HABITAT_CACHE"))
    assert str(C.WORK_DIR).startswith(str(C.REPO)) or __import__("os").environ.get("MRDB_HABITAT_WORK")


def test_manifest_has_no_absolute_paths():
    m = json.loads((OUT / "habitat_retrieval_manifest.json").read_text(encoding="utf-8"))
    txt = json.dumps(m)
    assert "/workspace" not in txt and "/mnt/" not in txt and "/home/" not in txt
    assert m["audit_id"] == "PR-7c.1a" and m["rules"]["host_association_roles"] == ["host"]
