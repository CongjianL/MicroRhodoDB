"""Build the small committed offline fixture for tests/test_habitat_audit_pr7c1.py.

Selects a deterministic set of real records covering every grade, route and the main flags/diagnostics
(first record per criterion in pilot_order_key order), records exactly which entity-store keys the
classifier reads for them, and writes:
  tests/data/pr7c1/fixture_records.json        frozen record identity rows
  tests/data/pr7c1/fixture_entities.json       the entity-store subset those records read
  tests/data/pr7c1/fixture_literature.json     parent-verified literature for those records
  tests/data/pr7c1/fixture_expected_records.tsv expected record rows (from the committed full output)

Usage: python -m tools.habitat_audit.make_fixture <entities_full.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import baseline, classify
from . import common as C
from .summarize import RECORD_COLS


class Rec(dict):
    """dict that records the keys read through [] / get / in (one level)."""

    def __init__(self, d, log):
        super().__init__(d)
        self._log = log

    def __getitem__(self, k):
        self._log.add(k)
        return super().__getitem__(k)

    def get(self, k, default=None):
        self._log.add(k)
        return super().get(k, default)

    def __contains__(self, k):
        self._log.add(k)
        return super().__contains__(k)


CRITERIA = [
    ("grade DIRECT_SAMPLE", lambda r, f: r["primary_grade"] == "DIRECT_SAMPLE"),
    ("grade NOT_REPORTED", lambda r, f: r["primary_grade"] == "NOT_REPORTED" and r["literature_status"] == "NOT_SEARCHED"),
    ("grade AMBIGUOUS across", lambda r, f: "across_sample_units" in r["conflict_scope"]),
    ("grade AMBIGUOUS within", lambda r, f: "within_sample_unit" in r["conflict_scope"]),
    ("AMBIGUOUS punctuation", lambda r, f: "punctuation_only" in r["conflict_kind"]),
    ("grade VERIFIED_ISOLATE", lambda r, f: r["primary_grade"] == "VERIFIED_ISOLATE"),
    ("grade ORGANISM_CONTEXT_ONLY", lambda r, f: r["primary_grade"] == "ORGANISM_CONTEXT_ONLY"),
    ("literature conflict", lambda r, f: r["source_acc"] == "A0A411LJN5"),
    ("literature LOOKUP_FAILED", lambda r, f: r["literature_status"] == "LOOKUP_FAILED"),
    ("route proteome_assembly", lambda r, f: "proteome_assembly" in r["linkage_route"]),
    ("route insdc_flatfile_biosample", lambda r, f: "insdc_flatfile_biosample" in r["linkage_route"]),
    ("route uniparc_embl_protein", lambda r, f: "uniparc_embl_protein" in r["linkage_route"]),
    ("no_insdc_link", lambda r, f: "no_insdc_link" in f),
    ("multi_sample", lambda r, f: "multi_sample" in f),
    ("tissue_or_culture_only", lambda r, f: "tissue_or_culture_only" in f),
    ("host_is_self_ignored", lambda r, f: "host_is_self_ignored" in f),
    ("envo_id_invalid", lambda r, f: "envo_id_invalid" in f),
    ("habitat_nonstandard on NOT_REPORTED", lambda r, f: r["primary_grade"] == "NOT_REPORTED" and r["habitat_nonstandard"]),
    ("habitat_reported_missing", lambda r, f: "habitat_reported_missing" in f and r["primary_grade"] == "NOT_REPORTED"),
    ("geo_discordant", lambda r, f: "geo_discordant" in f),
    ("sample_copy_absent", lambda r, f: "sample_copy_absent" in f),
    ("engineered", lambda r, f: r["is_engineered"] == "1"),
    ("ENVIRONMENTAL_CLONE", lambda r, f: r["sample_type"] == "ENVIRONMENTAL_CLONE" and r["primary_grade"] == "DIRECT_SAMPLE"),
    ("MAG", lambda r, f: r["sample_type"] == "MAG"),
    ("Archaea direct", lambda r, f: r["domain"] == "Archaea" and r["primary_grade"] == "DIRECT_SAMPLE"),
    # PR-7c.1a semantics (physical habitat vs host association, placeholders, ambiguity, missingness)
    ("zero placeholder A0ABS3TAH3", lambda r, f: r["source_acc"] == "A0ABS3TAH3"),
    ("zero placeholder A0ABS3TE24", lambda r, f: r["source_acc"] == "A0ABS3TE24"),
    ("ENVO-like digits A0A6N7QP32", lambda r, f: r["source_acc"] == "A0A6N7QP32"),
    ("host only, was DIRECT", lambda r, f: "host_association_only" in f and r["pr7c1_grade"] == "DIRECT_SAMPLE"),
    ("host only, was AMBIGUOUS", lambda r, f: "host_association_only" in f and r["pr7c1_grade"] == "AMBIGUOUS"),
    ("host conflict, physical agrees", lambda r, f: r["host_association_status"] == "AMBIGUOUS" and r["primary_grade"] == "DIRECT_SAMPLE"),
    ("host and physical conflict", lambda r, f: r["host_association_status"] == "AMBIGUOUS" and r["primary_grade"] == "AMBIGUOUS"),
    ("ambiguity FORMATTING_ONLY", lambda r, f: r["ambiguity_class"] == "FORMATTING_ONLY"),
    ("ambiguity NESTED_WORDING", lambda r, f: r["ambiguity_class"] == "NESTED_WORDING"),
    ("ambiguity DISTINCT_SAME_SAMPLE", lambda r, f: r["ambiguity_class"] == "DISTINCT_SAME_SAMPLE"),
    ("ambiguity DISTINCT_ACROSS_SAMPLES", lambda r, f: r["ambiguity_class"] == "DISTINCT_ACROSS_SAMPLES"),
    ("host ambiguity NESTED_WORDING", lambda r, f: r["host_ambiguity_class"] == "NESTED_WORDING"),
    ("host ambiguity FORMATTING_ONLY", lambda r, f: r["host_ambiguity_class"] == "FORMATTING_ONLY"),
    ("NR database_and_literature", lambda r, f: r["not_reported_scope"] == "database_and_literature"),
    ("NR literature inaccessible", lambda r, f: r["not_reported_scope"] == "database_only_literature_inaccessible"),
    ("host tissue isolation_source only", lambda r, f: "host_tissue_isolation_source_only" in f),
]


def main(argv=None):
    argv = argv or sys.argv[1:]
    ent = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    out_rows = {r["source_acc"]: r for r in C.read_tsv(C.OUT_DIR / "habitat_record_availability.tsv")}
    order = sorted(out_rows, key=C.pilot_order_key)
    chosen: dict[str, str] = {}
    absent = []
    for name, fn in CRITERIA:
        for a in order:
            r = out_rows[a]
            if fn(r, set(r["flags"].split(";"))):
                chosen.setdefault(a, name)
                break
        else:
            absent.append(name)  # no real record has this property; covered by the synthetic tests
    lit_all = json.loads((C.OUT_DIR / "literature" / "literature_evidence.json").read_text(encoding="utf-8"))
    recs = {r["source_acc"]: r for r in baseline.load_records()}
    logs = {g: set() for g in ent if g != "meta"}
    wrapped = {g: Rec(v, logs[g]) for g, v in ent.items() if g != "meta"}
    rows = []
    for a in sorted(chosen):
        row, _, _ = classify.classify_record(recs[a], wrapped, lit_all.get(a), True)
        exp = out_rows[a]
        got = {k: ("" if row.get(k) is None else C._cell(row.get(k))) for k in RECORD_COLS}
        assert got == {k: exp[k] for k in RECORD_COLS}, a
        rows.append([got[k] for k in RECORD_COLS])
    sub = {g: {k: ent[g][k] for k in sorted(logs[g]) if k in ent[g]} for g in sorted(logs)}
    C.FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    C.dump_json(C.FIXTURE_DIR / "fixture_entities.json", sub)
    C.dump_json(C.FIXTURE_DIR / "fixture_records.json", [dict(recs[a], fixture_reason=chosen[a]) for a in sorted(chosen)])
    C.dump_json(C.FIXTURE_DIR / "fixture_literature.json", {a: lit_all[a] for a in sorted(chosen) if a in lit_all})
    C.write_tsv(C.FIXTURE_DIR / "fixture_expected_records.tsv", RECORD_COLS, rows)
    print(f"criteria without any real record: {absent}")
    print(f"fixture: {len(chosen)} records; entity keys: { {g: len(v) for g, v in sub.items()} }")
    for a in sorted(chosen):
        print(" ", a, chosen[a])
    return 0


if __name__ == "__main__":
    sys.exit(main())
