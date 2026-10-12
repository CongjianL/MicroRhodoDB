"""Stage 1: frozen baseline and environmental-field completeness (offline, no network).

Produces, before any external retrieval:
  docs/website/pr7c1/PR7C1_STAGE1_BASELINE.md
  docs/website/pr7c1/stage1_field_completeness.tsv
"""
from __future__ import annotations

import collections
import json
import re
from pathlib import Path

from . import common as C

ENV_PATTERN = re.compile(
    r"(env|habitat|isolat|host|biosample|bioproject|biome|country|geo_loc|lat|lon|collection|sample|depth|material|feature)",
    re.I,
)
# Patterns searched in the exporter and in the exported production JSON.
EXPORT_KEYS = (
    "habitat", "biosample", "bioproject", "isolation_source", "env_broad", "env_local", "env_medium",
    "env_feature", "env_material", "biome", "geo_loc", "collection_date", "lat_lon", "sample_type",
)
METAGENOME_RE = re.compile(r"(metagenome|uncultured|unknown|environmental samples)", re.I)


def load_records(con=None) -> list[dict]:
    """One dict per source record (5,466), identity and stratification fields only."""
    own = con is None
    con = con or C.open_db_ro()
    sg = {r["status"]: r["status_group"] for r in con.execute("select status, status_group from status_definition")}
    chars = {r[0] for r in con.execute("select distinct source_acc from characterized_protein")}
    rel = {r[0]: r[1] for r in con.execute("select source_acc, source_release from sequence_source")}
    vm = {r["source_acc"]: r for r in con.execute(
        "select source_acc, membership_status, evidence_level, func_class, is_engineered, wild_type_acc,"
        " counts_eligible from v_master")}
    counted = {r[0] for r in con.execute("select source_acc from v_counted")}
    rows = con.execute(
        "select source_acc, mrdb_acc, organism, organism_id, tax_domain, lineage, reviewed, is_seed,"
        " sequence_sha256, exact_duplicate_of, length from protein order by source_acc").fetchall()
    sha_count = collections.Counter(r["sequence_sha256"] for r in rows)
    out = []
    for r in rows:
        acc = r["source_acc"]
        m = vm[acc]
        eng = int(m["is_engineered"] or 0)
        out.append({
            "source_acc": acc,
            "mrdb_acc": r["mrdb_acc"],
            "organism": r["organism"],
            "organism_id": r["organism_id"],
            "domain": r["tax_domain"] or "Unassigned",
            "phylum": C.phylum_from_lineage(r["lineage"]) or "Unassigned",
            "reviewed": int(r["reviewed"] or 0),
            "is_seed": int(acc in C.SEED_ACCS),
            "is_characterized": int(acc in chars),
            "membership_status": m["membership_status"],
            "status_group": sg[m["membership_status"]],
            "status_group_audit": "engineered" if eng else sg[m["membership_status"]],
            "evidence_level": m["evidence_level"],
            "is_engineered": eng,
            "wild_type_acc": m["wild_type_acc"],
            "counted": int(acc in counted),
            "source_release": rel.get(acc),
            "sequence_sha256": r["sequence_sha256"],
            "seq_group_size": sha_count[r["sequence_sha256"]],
            "exact_duplicate_of": r["exact_duplicate_of"],
            "length": r["length"],
            "organism_metagenome_like": int(bool(METAGENOME_RE.search((r["organism"] or "") + " " + (r["lineage"] or "")))),
        })
    if own:
        con.close()
    return out


def literature_subset(records: list[dict]) -> list[str]:
    return sorted(r["source_acc"] for r in records if r["is_seed"] or r["is_characterized"])


def _completeness(con, table: str) -> list[list]:
    cols = [r[1] for r in con.execute(f"pragma table_info({table})")]
    n = con.execute(f"select count(*) from {table}").fetchone()[0]
    rows = []
    for c in cols:
        k = con.execute(
            f"select count(*) from {table} where {c} is not null and trim(cast({c} as text)) != ''").fetchone()[0]
        rows.append([table, c, n, k, round(100.0 * k / n, 2) if n else 0.0,
                     "populated" if k == n else ("partial" if k else "empty"),
                     int(bool(ENV_PATTERN.search(c)))])
    return rows


def _grep_exporter() -> dict:
    text = C.EXPORTER.read_text(encoding="utf-8")
    hits = {}
    for key in EXPORT_KEYS + ("isolation",):
        lines = [i + 1 for i, line in enumerate(text.splitlines()) if key in line.lower()]
        hits[key] = lines
    return hits


def _grep_export() -> dict:
    if not C.WEB_EXPORT.exists():
        return {"present": False}
    n_files = 0
    hits = collections.Counter()
    for p in sorted(C.WEB_EXPORT.rglob("*.json")):
        n_files += 1
        t = p.read_text(encoding="utf-8", errors="replace").lower()
        for key in EXPORT_KEYS:
            if f'"{key}' in t:
                hits[key] += 1
    return {"present": True, "n_json_files": n_files, "files_with_key": dict(hits)}


def run_stage1(out_dir: Path = C.OUT_DIR) -> dict:
    assert C.sha256_file(C.DB_PATH) == C.DB_SHA256, "frozen DB checksum mismatch"
    con = C.open_db_ro()
    recs = load_records(con)
    n_acc_map = con.execute("select count(*), count(distinct source_database) from accession_map").fetchone()
    srcdb = [r[0] for r in con.execute("select distinct source_database from accession_map")]
    checks = {
        "n_records": len(recs),
        "n_counted": sum(r["counted"] for r in recs),
        "n_engineered": sum(r["is_engineered"] for r in recs),
        "n_mrdb_acc": len({r["mrdb_acc"] for r in recs}),
        "n_accession_map": n_acc_map[0],
        "accession_map_source_databases": srcdb,
        "n_literature_subset": len(literature_subset(recs)),
        "n_seed": sum(r["is_seed"] for r in recs),
        "n_characterized": sum(r["is_characterized"] for r in recs),
        "n_seq_groups_gt1": len({r["sequence_sha256"] for r in recs if r["seq_group_size"] > 1}),
        "n_records_in_seq_groups_gt1": sum(1 for r in recs if r["seq_group_size"] > 1),
        "n_exact_duplicate_of": sum(1 for r in recs if r["exact_duplicate_of"]),
    }
    expect = {"n_records": C.N_RECORDS, "n_counted": C.N_COUNTED, "n_engineered": C.N_ENGINEERED,
              "n_mrdb_acc": C.N_MRDB, "n_accession_map": C.N_RECORDS}
    for k, v in expect.items():
        assert checks[k] == v, (k, checks[k], v)
    assert checks["n_counted"] + checks["n_engineered"] == C.N_RECORDS
    strata = {
        "status_group_audit": collections.Counter(r["status_group_audit"] for r in recs),
        "membership_status": collections.Counter(r["membership_status"] for r in recs),
        "domain": collections.Counter(r["domain"] for r in recs),
        "source_release": collections.Counter(r["source_release"] for r in recs),
        "evidence_level": collections.Counter(r["evidence_level"] for r in recs),
        "reviewed": collections.Counter(r["reviewed"] for r in recs),
    }
    comp = _completeness(con, "sequence_source") + _completeness(con, "protein")
    dd = [dict(r) for r in con.execute(
        "select object_name, column_name, definition from data_dictionary where column_name is not null")]
    dd_env = [d for d in dd if re.search(r"(env|habitat|isolation|host|biosample|country|biome)", d["column_name"] or "", re.I)]
    rel_env = [dict(r) for r in con.execute(
        "select key, value from release_metadata where key like '%env%' or value like '%env%'")]
    con.close()

    C.write_tsv(out_dir / "stage1_field_completeness.tsv",
                ["table", "column", "n_rows", "n_nonempty", "pct_nonempty", "state", "environment_related_name"],
                comp)
    exp_hits = _grep_exporter()
    web_hits = _grep_export()
    seqsrc_env = [r for r in comp if r[0] == "sequence_source" and r[6]]
    lines = [
        "# PR-7c.1 Stage 1: frozen baseline and habitat-field completeness",
        "",
        "Written from the frozen release database (opened read-only, immutable URI) **before any external retrieval**.",
        "",
        f"- Database: `releases/v1.6.0/db/microrhododb_v1.6.0.sqlite`, sha256 `{C.DB_SHA256}` (verified).",
        f"- Base commit: `{C.BASE_COMMIT}`.",
        "",
        "## Record identity checks",
        "",
        "| Check | Value |",
        "|---|---|",
    ]
    for k, v in checks.items():
        lines.append(f"| {k} | {v} |")
    lines += ["", "## Strata (denominator 5,466 source records)", ""]
    for name, cnt in strata.items():
        lines.append(f"**{name}:** " + "; ".join(f"{k} {v}" for k, v in sorted(cnt.items(), key=lambda x: str(x[0]))))
        lines.append("")
    lines += [
        "## Environmental fields in the frozen database",
        "",
        "`sequence_source` columns whose names relate to sample, environment or geography:",
        "",
        "| Column | Non-empty / rows | State |",
        "|---|---|---|",
    ]
    for r in seqsrc_env:
        lines.append(f"| {r[1]} | {r[3]} / {r[2]} | {r[5]} |")
    lines += [
        "",
        "Full per-column completeness for `sequence_source` and `protein`: `stage1_field_completeness.tsv`.",
        "The `protein` table has no environment, habitat, host, isolation-source or BioSample column.",
        "",
        "Data-dictionary columns whose names match env/habitat/isolation/host/biosample/country/biome:",
        "",
    ]
    for d in dd_env:
        lines.append(f"- `{d['object_name']}.{d['column_name']}`: {d['definition']}")
    lines += ["", "Release metadata entries mentioning an environmental layer:", ""]
    for d in rel_env:
        lines.append(f"- `{d['key']}` = {d['value']}")
    lines += [
        "",
        "The supplementary v1.5.0 environmental pilot (MGnify candidates) is a separate database and is not part",
        "of the 5,466 source records; it is out of scope for this audit.",
        "",
        "## Exporter and production JSON",
        "",
        "`tools/export_web_data.py`, lines containing each key (case-insensitive):",
        "",
    ]
    for k, v in exp_hits.items():
        lines.append(f"- `{k}`: {v if v else 'none'}")
    lines += [
        "",
        "The only `isolation` hit is the Foldseek watchlist caveat key (\"Watchlist entries are not corpus records\"),",
        "which is unrelated to sample isolation.",
        "",
        f"Local web export (`web/public/data/v1.6.0`, git-ignored): {json.dumps(web_hits, sort_keys=True)}", ""]
    lines += [
        "## Conclusion",
        "",
        "No habitat, sample, BioSample, geography or collection-date value exists for any of the 5,466 records in",
        "the frozen database, the exporter or the production JSON. Every habitat value in PR-7c.1 must therefore",
        "come from external retrieval with full provenance, and the baseline for every record is 'not present in",
        "MicroRhodoDB v1.6.0'.",
        "",
    ]
    (out_dir / "PR7C1_STAGE1_BASELINE.md").write_text("\n".join(lines), encoding="utf-8")
    return {"checks": checks, "exporter_hits": exp_hits, "web_export": web_hits}


if __name__ == "__main__":
    print(json.dumps(run_stage1(), indent=2, default=str))
