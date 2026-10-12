"""Fixed-seed stratified 100-record sample for the live independent spot-check (PR-7c.1).

One record from each non-default linkage route (proteome_assembly, insdc_flatfile_biosample,
uniparc_embl_protein, no link) is drawn first; the grade quotas are then filled by simple random
sampling within grade. Seed 20261012. Records sorted by source_acc before sampling.
Usage: python -m tools.habitat_audit.spotcheck_sample [OUT_TSV]
"""
from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

from . import common as C

SEED = 20261012
QUOTA = {"DIRECT_SAMPLE": 40, "NOT_REPORTED": 35, "AMBIGUOUS": 15, "VERIFIED_ISOLATE": 5, "ORGANISM_CONTEXT_ONLY": 5}
ROUTES = ["proteome_assembly", "insdc_flatfile_biosample", "uniparc_embl_protein", ""]
COLS = ["source_acc", "primary_grade", "db_habitat_status", "literature_status", "env_broad_scale_original",
        "env_local_scale_original", "env_medium_original", "isolation_source_original", "host_original",
        "habitat_nonstandard", "sample_material", "conflict_roles", "biosamples", "embl_protein_ids",
        "insdc_accessions", "proteomes", "linkage_route", "flags", "literature_isolate_text",
        "literature_isolate_refs", "organism_context_text", "organism_context_refs", "uniprot_organism", "domain",
        "status_group_audit"]


def draw(rows: list[dict]) -> list[dict]:
    rows = sorted(rows, key=lambda r: r["source_acc"])
    quota = dict(QUOTA)
    rng = random.Random(SEED)
    sel = []
    for route in ROUTES:
        pool = [r for r in rows if r["linkage_route"] == route and quota.get(r["primary_grade"], 0) > 0]
        p = rng.choice(pool)
        sel.append(p)
        quota[p["primary_grade"]] -= 1
    for g, n in quota.items():
        pool = [r for r in rows if r["primary_grade"] == g and r not in sel]
        sel += rng.sample(pool, n)
    return sorted(sel, key=lambda r: r["source_acc"])


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    out = Path(argv[0]) if argv else C.OUT_DIR / "validation_spotcheck_sample.tsv"
    csv.field_size_limit(1 << 30)
    sel = draw(C.read_tsv(C.OUT_DIR / "habitat_record_availability.tsv"))
    C.write_tsv(out, COLS, [[r[c] for c in COLS] for r in sel])
    print(f"{len(sel)} records -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
