"""Stage 3/4 outputs: record/provenance/evidence TSVs, coverage summary, manifest, SVG figures.

Every summary number is recomputed from the record table (habitat_record_availability.tsv).
"""
from __future__ import annotations

import collections
from pathlib import Path

from . import common as C
from . import normalize as N

RECORD_COLS = [
    "source_acc", "mrdb_acc", "counted", "is_engineered", "membership_status", "status_group", "status_group_audit",
    "evidence_level", "domain", "phylum", "reviewed", "source_release", "sequence_sha256", "seq_group_size",
    "exact_duplicate_of", "is_seed", "is_characterized",
    "primary_grade", "db_chain_status", "db_habitat_status", "literature_status", "not_reported_scope",
    "has_usable_habitat", "ambiguity_class",
    "host_association_status", "has_host_association", "host_ambiguity_class", "pr7c1_grade",
    "conflict_roles", "conflict_scope", "conflict_kind", "chain_failures",
] + [f"{r}_{s}" for r in N.HABITAT_ROLES for s in ("original", "normalized", "envo_ids")] + [
    "habitat_nonstandard", "sample_material", "country", "lat_lon", "lat", "lon", "collection_date", "depth", "sample_type", "molecule_types",
    "uniprot_status", "uniprot_organism", "uniprot_taxon_id",
    "embl_protein_ids", "insdc_accessions", "proteomes", "assemblies", "biosamples", "bioprojects",
    "linkage_route", "mapping_confidence", "flags",
    "organism_context_text", "organism_context_refs", "literature_isolate_text", "literature_isolate_refs",
    "evidence_ids",
]
LINK_COLS = ["source_acc", "link_index", "route", "mapping_confidence", "embl_parent", "protein_id", "embl_status",
             "molecule_type", "cds_status", "sequence_status", "wgs_status", "flatfile_status", "proteome", "proteome_status",
             "assembly", "assembly_status", "samples", "sample_status", "studies", "request_keys"]
EVID_COLS = ["evidence_id", "source_acc", "evidence_source", "entity_accession", "link_index", "field_original",
             "role", "value_status", "value_original", "value_normalized", "envo_ids", "linkage_route",
             "mapping_confidence", "request_key", "browser_url", "source_url"]
REQ_COLS = ["request_key", "purpose", "method", "url", "request_body", "status", "ok", "error", "attempts",
            "retrieved_at", "response_sha256", "uniprot_release"]


def _browser(src: str, acc: str) -> str:
    if not acc:
        return ""
    if src == "ncbi_biosample":
        return f"https://www.ncbi.nlm.nih.gov/biosample/{acc}"
    if src == "literature":
        return f"https://pubmed.ncbi.nlm.nih.gov/{acc}/" if str(acc).isdigit() else f"https://doi.org/{acc}"
    return f"https://www.ebi.ac.uk/ena/browser/view/{acc}"


def write_tables(out: Path, rows, links, ev, ent) -> None:
    rows = sorted(rows, key=lambda r: r["source_acc"])
    C.write_tsv(out / "habitat_record_availability.tsv", RECORD_COLS, [[r.get(c, "") for c in RECORD_COLS] for r in rows])
    lrows = []
    for L in sorted(links, key=lambda L: (L["source_acc"], L["link_index"])):
        d = dict(L)
        d["samples"] = ";".join(L["samples"])
        d["studies"] = ";".join(L["studies"])
        d["request_keys"] = ";".join(k for k in L["request_keys"] if k)
        lrows.append([d.get(c, "") for c in LINK_COLS])
    C.write_tsv(out / "habitat_provenance_links.tsv", LINK_COLS, lrows)
    erows = []
    for it in sorted(ev, key=lambda i: (i["source_acc"], i["evidence_id"])):
        d = dict(it)
        d["envo_ids"] = ";".join(it.get("envo_ids") or [])
        d["source_url"] = it.get("api_url", "") if it["evidence_source"] == "literature" else ""
        d["browser_url"] = _browser(it["evidence_source"], it["entity_accession"])
        erows.append([d.get(c, "") for c in EVID_COLS])
    C.write_tsv(out / "habitat_evidence.tsv", EVID_COLS, erows)
    # one row per HTTP request (database retrieval and literature quote verification); evidence, link and
    # record rows reference requests by request_key (sha256 of method, canonical URL and canonical body)
    rq = []
    for purpose, grp in (("database", ent["meta"].get("requests", {})),
                         ("literature_verification", ent["meta"].get("literature_requests", {}))):
        for k in sorted(grp):
            m = dict(grp[k], request_key=k, purpose=purpose)
            rq.append([("" if m.get(c) is None else m.get(c)) for c in REQ_COLS])
    C.write_tsv(out / "habitat_requests.tsv", REQ_COLS, rq)


def attribute_inventory(ent: dict) -> list[list]:
    """Every attribute tag seen in retrieved BioSamples (ENA and NCBI) with its assigned role."""
    cnt = collections.Counter()
    for grp, tagk in (("sample_ena", "tag"), ("sample_ncbi", "harmonized_name")):
        for v in ent.get(grp, {}).values():
            for a in v.get("attributes", []) or []:
                t = a.get(tagk) or a.get("name") or ""
                cnt[(grp, t)] += 1
    return [[g, t, n, N.role_for(t) or ""] for (g, t), n in sorted(cnt.items())]


# --------------------------------------------------------------------------- coverage summary
SUMMARY_COLS = ["unit", "stratum_type", "stratum", "metric", "numerator", "denominator", "percent"]
STRATA = ("all", "status_group_audit", "domain", "phylum", "source_release", "evidence_level", "reviewed",
          "counted", "is_characterized", "literature_subset", "sample_type", "mapping_confidence")
# Aggregation of source-record grades to one grade per MRDB accession. NOT_REPORTED only when every
# source record is NOT_REPORTED; a failure or an unsearched record is never collapsed to NOT_REPORTED.
MRDB_ORDER = ("DIRECT_SAMPLE", "VERIFIED_ISOLATE", "AMBIGUOUS", "ORGANISM_CONTEXT_ONLY", "LOOKUP_FAILED",
              "NOT_SEARCHED", "NOT_REPORTED")
FUNNEL = ("searched", "insdc_link_found", "insdc_record_resolved", "habitat_field_present",
          "informative_habitat_value", "direct_sample")


def _pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.2f}" if d else ""


def _stratum_value(r: dict, st: str) -> str:
    if st == "all":
        return "all"
    if st == "literature_subset":
        return "1" if (str(r.get("is_seed")) == "1" or str(r.get("is_characterized")) == "1") else "0"
    v = r.get(st, "")
    return str(v) if v not in (None, "") else "(none)"


def record_funnel_stage(r: dict, hab_status: dict) -> dict:
    """Monotone chain-attrition stages for one record (searched records only)."""
    flags = set(filter(None, str(r.get("flags", "")).split(";")))
    st = hab_status.get(r["source_acc"], set())
    s = {"searched": r["primary_grade"] != "NOT_SEARCHED"}
    s["insdc_link_found"] = s["searched"] and "no_insdc_link" not in flags
    s["insdc_record_resolved"] = s["insdc_link_found"] and "insdc_record_unresolved" not in flags and \
        not str(r.get("chain_failures", "")).startswith(("ena_coding", "ena_sequence", "uniparc", "proteome"))
    s["habitat_field_present"] = s["insdc_record_resolved"] and bool(st)
    s["informative_habitat_value"] = s["habitat_field_present"] and bool(
        st - {"reported_missing", "uninformative_placeholder", "invalid_placeholder"})
    s["direct_sample"] = s["informative_habitat_value"] and r["primary_grade"] == "DIRECT_SAMPLE"
    return s


def habitat_status_by_record(ev) -> dict:
    """value_status set per record over the four PHYSICAL habitat roles (host excluded, PR-7c.1a)."""
    d = collections.defaultdict(set)
    for it in ev:
        if it.get("role") in N.PHYSICAL_ROLES and it.get("evidence_source") != "literature":
            d[it["source_acc"]].add(it["value_status"])
    return d


def mrdb_rollup(rows) -> list[dict]:
    by = collections.defaultdict(list)
    for r in rows:
        if r.get("mrdb_acc"):
            by[r["mrdb_acc"]].append(r)
    out = []
    for m, rs in sorted(by.items()):
        grades = {r["primary_grade"] for r in rs}
        g = next(x for x in MRDB_ORDER if x in grades) if grades != {"NOT_REPORTED"} else "NOT_REPORTED"
        base = sorted(rs, key=lambda r: r["source_acc"])[0]
        d = {k: base.get(k, "") for k in STRATA if k not in ("all", "literature_subset", "sample_type", "mapping_confidence")}
        d.update(mrdb_acc=m, primary_grade=g, n_source_records=len(rs),
                 is_seed=int(any(str(r.get("is_seed")) == "1" for r in rs)),
                 is_characterized=int(any(str(r.get("is_characterized")) == "1" for r in rs)),
                 sample_type=";".join(sorted({r.get("sample_type", "") for r in rs})),
                 mapping_confidence=";".join(sorted({r.get("mapping_confidence", "") for r in rs if r.get("mapping_confidence")})),
                 mixed_grades=int(len(grades) > 1))
        out.append(d)
    return out


def coverage_summary(rows, ev) -> list[list]:
    """Long-format coverage table with explicit numerators and denominators."""
    out = []
    hab = habitat_status_by_record(ev)
    roles_by_rec = {r["source_acc"]: {ro for ro in N.HABITAT_ROLES if r.get(f"{ro}_original")} for r in rows}
    transitions = collections.Counter((r.get("pr7c1_grade", ""), r["primary_grade"]) for r in rows)
    units = (("source_record", rows), ("mrdb_accession", mrdb_rollup(rows)))
    for unit, rs in units:
        for st in STRATA:
            groups = collections.defaultdict(list)
            for r in rs:
                groups[_stratum_value(r, st)].append(r)
            for val in sorted(groups):
                g = groups[val]
                n = len(g)
                cnt = collections.Counter(r["primary_grade"] for r in g)
                for gr in C.GRADES:
                    out.append([unit, st, val, f"grade:{gr}", cnt.get(gr, 0), n, _pct(cnt.get(gr, 0), n)])
                searched = [r for r in g if r["primary_grade"] != "NOT_SEARCHED"]
                u = sum(1 for r in g if r["primary_grade"] in ("DIRECT_SAMPLE", "VERIFIED_ISOLATE"))
                out.append([unit, st, val, "usable_habitat_any_source", u, n, _pct(u, n)])
                out.append([unit, st, val, "usable_habitat_any_source_of_searched", u, len(searched), _pct(u, len(searched))])
                if unit == "source_record" and st in ("all", "status_group_audit", "domain"):
                    for ro in N.PHYSICAL_ROLES:
                        k = sum(1 for r in searched if ro in roles_by_rec[r["source_acc"]])
                        out.append([unit, st, val, f"usable_field:{ro}", k, len(searched), _pct(k, len(searched))])
                    for ro in N.HOST_ROLES:  # host association: reported separately, never physical habitat
                        k = sum(1 for r in searched if ro in roles_by_rec[r["source_acc"]])
                        out.append([unit, st, val, f"host_field:{ro}", k, len(searched), _pct(k, len(searched))])
                if unit == "source_record":
                    # host-association axis (PR-7c.1a), separate from the physical-habitat primary grade
                    hc = collections.Counter(r.get("host_association_status", "") for r in g)
                    for hs in C.HOST_STATUSES:
                        out.append([unit, st, val, f"host_association:{hs}", hc.get(hs, 0), n, _pct(hc.get(hs, 0), n)])
                    k = sum(1 for r in g if str(r.get("has_host_association")) == "1")
                    out.append([unit, st, val, "has_host_association", k, n, _pct(k, n)])
                    k = sum(1 for r in g if "host_association_only" in str(r.get("flags", "")).split(";"))
                    out.append([unit, st, val, "host_association_only", k, n, _pct(k, n)])
                    k = sum(1 for r in g if str(r.get("has_host_association")) == "1" and str(r.get("has_usable_habitat")) == "1")
                    out.append([unit, st, val, "physical_habitat_and_host_association", k, n, _pct(k, n)])
                    for col in ("habitat_nonstandard", "country", "collection_date", "lat_lon", "sample_material"):
                        k = sum(1 for r in searched if r.get(col))
                        out.append([unit, st, val, f"reported_field:{col}", k, len(searched), _pct(k, len(searched))])
                if unit == "source_record" and st == "all":
                    stages = [record_funnel_stage(r, hab) for r in g]
                    for f in FUNNEL:
                        k = sum(1 for s in stages if s[f])
                        out.append([unit, st, val, f"funnel:{f}", k, n, _pct(k, n)])
                    for flag in sorted({f for r in g for f in str(r.get("flags", "")).split(";") if f}):
                        k = sum(1 for r in g if flag in str(r.get("flags", "")).split(";"))
                        out.append([unit, st, val, f"flag:{flag}", k, n, _pct(k, n)])
                    amb = [r for r in g if r["primary_grade"] == "AMBIGUOUS"]
                    hamb = [r for r in g if r.get("host_association_status") == "AMBIGUOUS"]
                    for axis, pool, col in (("ambiguity_class", amb, "ambiguity_class"),
                                            ("host_ambiguity_class", hamb, "host_ambiguity_class")):
                        cc = collections.Counter(r.get(col, "") for r in pool)
                        for c in C.AMBIGUITY_CLASSES:
                            out.append([unit, st, val, f"{axis}:{c}", cc.get(c, 0), len(pool), _pct(cc.get(c, 0), len(pool))])
                    nr = [r for r in g if r["primary_grade"] == "NOT_REPORTED"]
                    sc = collections.Counter(r.get("not_reported_scope", "") for r in nr)
                    for s_ in sorted(sc):
                        out.append([unit, st, val, f"not_reported_scope:{s_}", sc[s_], len(nr), _pct(sc[s_], len(nr))])
                    for (old, new) in sorted(transitions):
                        out.append([unit, st, val, f"pr7c1_grade_transition:{old}->{new}", transitions[(old, new)], n,
                                    _pct(transitions[(old, new)], n)])
                    for col in ("conflict_scope", "conflict_kind"):
                        # physical-habitat roles only (host conflicts are on the host axis)
                        vals = collections.Counter(x.split(":", 1)[1] for r in amb for x in str(r.get(col, "")).split(";")
                                                   if x and x.split(":", 1)[0] in N.PHYSICAL_ROLES)
                        for v in sorted(vals):
                            out.append([unit, st, val, f"ambiguous_role_{col}:{v}", vals[v], sum(vals.values()),
                                        _pct(vals[v], sum(vals.values()))])
                    # Sensitivity (descriptive): AMBIGUOUS records whose every conflicting role is punctuation-only.
                    def _phys(x):
                        return [y for y in str(x or "").split(";") if y and y.split(":", 1)[0] in N.PHYSICAL_ROLES]
                    k = sum(1 for r in amb if _phys(r.get("conflict_kind")) and all(x.endswith(":punctuation_only") for x in _phys(r["conflict_kind"])))
                    out.append([unit, st, val, "ambiguous_all_roles_punctuation_only", k, len(amb), _pct(k, len(amb))])
                    k = sum(1 for r in amb if _phys(r.get("conflict_scope")) and all(x.endswith(":within_sample_unit") for x in _phys(r["conflict_scope"])))
                    out.append([unit, st, val, "ambiguous_all_roles_within_sample_unit", k, len(amb), _pct(k, len(amb))])
                    k = sum(1 for r in g if r["primary_grade"] == "NOT_REPORTED" and r.get("habitat_nonstandard"))
                    out.append([unit, st, val, "not_reported_with_nonstandard_habitat_tag", k,
                                sum(1 for r in g if r["primary_grade"] == "NOT_REPORTED"),
                                _pct(k, sum(1 for r in g if r["primary_grade"] == "NOT_REPORTED"))])
                    for ls in sorted({r.get("literature_status", "") for r in g}):
                        k = sum(1 for r in g if r.get("literature_status", "") == ls)
                        out.append([unit, st, val, f"literature_status:{ls or '(none)'}", k, n, _pct(k, n)])
                if unit == "mrdb_accession" and st == "all":
                    k = sum(1 for r in g if r["mixed_grades"])
                    out.append([unit, st, val, "mrdb_mixed_source_grades", k, n, _pct(k, n)])
                    k = sum(1 for r in g if r["n_source_records"] > 1)
                    out.append([unit, st, val, "mrdb_multiple_source_records", k, n, _pct(k, n)])
    return out


# --------------------------------------------------------------------------- figures (SVG)
GRADE_COLORS = {"DIRECT_SAMPLE": "#0072B2", "VERIFIED_ISOLATE": "#56B4E9", "ORGANISM_CONTEXT_ONLY": "#009E73",
                "AMBIGUOUS": "#E69F00", "NOT_REPORTED": "#BBBBBB", "LOOKUP_FAILED": "#D55E00",
                "NOT_SEARCHED": "#F0F0F0"}


def _mpl():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    matplotlib.rcParams.update({"font.family": ["Liberation Sans", "Arimo", "DejaVu Sans"], "svg.fonttype": "none",
                                "svg.hashsalt": "pr7c1", "font.size": 9, "axes.spines.top": False,
                                "axes.spines.right": False})
    return plt


def _save(fig, path: Path):
    """Deterministic SVG; trailing whitespace that matplotlib leaves in path data ("M 0 0 ") is stripped
    per line (geometry and text are unchanged)."""
    import io
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", metadata={"Date": None, "Creator": None})
    path.write_text("\n".join(line.rstrip() for line in buf.getvalue().split("\n")), encoding="utf-8")


def _stacked(plt, rows, col, order, path, title):
    groups = [g for g in order if any(r[col] == g for r in rows)]
    fig, ax = plt.subplots(figsize=(7.2, 0.45 * len(groups) + 1.4))
    left = [0.0] * len(groups)
    for gr in C.GRADES:
        vals = []
        for g in groups:
            sub = [r for r in rows if r[col] == g]
            vals.append(100.0 * sum(1 for r in sub if r["primary_grade"] == gr) / len(sub))
        if any(vals):
            ax.barh(range(len(groups)), vals, left=left, color=GRADE_COLORS[gr], edgecolor="white", linewidth=0.4,
                    label=gr)
            left = [a + b for a, b in zip(left, vals)]
    labels = [f"{g} (n={sum(1 for r in rows if r[col] == g)})" for g in groups]
    ax.set_yticks(range(len(groups)), labels)
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Source records (%)")
    ax.set_title(title, loc="left")
    ax.legend(ncol=3, fontsize=7, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.18))
    _save(fig, path)
    plt.close(fig)


def write_figures(fig_dir: Path, rows, ev) -> list[str]:
    plt = _mpl()
    fig_dir.mkdir(parents=True, exist_ok=True)
    made = []
    _stacked(plt, rows, "status_group_audit", ["member", "candidate", "boundary", "outgroup", "rejected", "engineered"],
             fig_dir / "fig_habitat_grade_by_status_group.svg", "Physical habitat evidence grade by status group")
    _stacked(plt, rows, "domain", ["Bacteria", "Archaea", "Eukaryota", "Unassigned"],
             fig_dir / "fig_habitat_grade_by_domain.svg", "Physical habitat evidence grade by domain")
    made += ["fig_habitat_grade_by_status_group.svg", "fig_habitat_grade_by_domain.svg"]
    searched = [r for r in rows if r["primary_grade"] != "NOT_SEARCHED"]
    n = len(searched) or 1
    labels, vals, cols = [], [], []
    for ro in N.PHYSICAL_ROLES:
        labels.append(ro); vals.append(100.0 * sum(1 for r in searched if r.get(f"{ro}_original")) / n); cols.append("#0072B2")
    for ro in N.HOST_ROLES:
        labels.append(f"{ro} (association)"); vals.append(100.0 * sum(1 for r in searched if r.get(f"{ro}_original")) / n)
        cols.append("#CC79A7")
    for col in ("country", "collection_date", "lat_lon", "sample_material"):
        labels.append(col); vals.append(100.0 * sum(1 for r in searched if r.get(col)) / n); cols.append("#999999")
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.barh(range(len(labels)), vals, color=cols)
    for i, v in enumerate(vals):
        ax.text(v + 0.5, i, f"{v:.1f}%", va="center", fontsize=7)
    ax.set_yticks(range(len(labels)), labels)
    ax.invert_yaxis()
    ax.set_xlim(0, max(vals + [1]) * 1.15)
    ax.set_xlabel(f"Searched source records with value (%, n={len(searched)})")
    ax.set_title("Field completeness (blue: physical habitat; pink: host; grey: context)", loc="left")
    _save(fig, fig_dir / "fig_habitat_field_completeness.svg")
    plt.close(fig)
    hab = habitat_status_by_record(ev)
    stages = [record_funnel_stage(r, hab) for r in rows]
    counts = [sum(1 for s in stages if s[f]) for f in FUNNEL]
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    ax.barh(range(len(FUNNEL)), counts, color="#0072B2")
    for i, v in enumerate(counts):
        ax.text(v + 30, i, f"{v:,}", va="center", fontsize=7)
    ax.set_yticks(range(len(FUNNEL)), [f.replace("_", " ") for f in FUNNEL])
    ax.invert_yaxis()
    ax.set_xlim(0, max(counts + [1]) * 1.15)
    ax.set_xlabel("Source records")
    ax.set_title("Source-chain attrition", loc="left")
    _save(fig, fig_dir / "fig_habitat_chain_funnel.svg")
    plt.close(fig)
    return made + ["fig_habitat_field_completeness.svg", "fig_habitat_chain_funnel.svg"]


# --------------------------------------------------------------------------- manifest
def build_manifest(out: Path, rows, ent: dict, mode: str, literature_path: Path | None, files: list[str]) -> dict:
    req = ent["meta"].get("requests", {})
    by_host = collections.Counter()
    status = collections.Counter()
    ts = []
    rels = collections.Counter()
    for k, m in req.items():
        url = m.get("url") or ""
        host = url.split("/")[2] if "://" in url else ""
        by_host[host] += 1
        status[f"{host} {m.get('status')} ok={m.get('ok')}"] += 1
        if m.get("retrieved_at"):
            ts.append(m["retrieved_at"])
        if m.get("uniprot_release"):
            rels[m["uniprot_release"]] += 1
    import platform
    man = {
        "audit_id": __import__("tools.habitat_audit", fromlist=["AUDIT_ID"]).AUDIT_ID, "audit_version": __import__("tools.habitat_audit", fromlist=["AUDIT_VERSION"]).AUDIT_VERSION,
        "mode": mode, "base_commit": C.BASE_COMMIT, "database": str(C.DB_PATH.relative_to(C.REPO)),
        "database_sha256": C.DB_SHA256, "n_source_records": len(rows),
        "n_searched": sum(1 for r in rows if r["primary_grade"] != "NOT_SEARCHED"),
        "grades": dict(sorted(collections.Counter(r["primary_grade"] for r in rows).items())),
        "pr7c1_grades": dict(sorted(collections.Counter(r.get("pr7c1_grade", "") for r in rows).items())),
        "host_association": dict(sorted(collections.Counter(r.get("host_association_status", "") for r in rows).items())),
        "uniprot_release_headers": dict(sorted(rels.items())),
        "retrieval_window_utc": [min(ts) if ts else None, max(ts) if ts else None],
        "n_literature_verification_requests": len(ent["meta"].get("literature_requests", {})),
        "n_requests": len(req), "requests_by_host": dict(sorted(by_host.items())),
        "request_outcomes": dict(sorted(status.items())),
        "entity_counts": {k: len(v) for k, v in sorted(ent.items()) if k != "meta"},
        "literature_file": str(literature_path.resolve().relative_to(C.REPO)) if literature_path and literature_path.exists() else None,
        "literature_sha256": C.sha256_file(literature_path) if literature_path and literature_path.exists() else None,
        "python": platform.python_version(),
        "rules": {"physical_habitat_roles": list(N.PHYSICAL_ROLES), "host_association_roles": list(N.HOST_ROLES),
                  "value_checked_roles": list(N.HABITAT_ROLES),
                  "invalid_placeholder": "whole-value zero (^0+(\\.0+)?$) in env_broad_scale/env_local_scale/env_medium",
                  "multi_value_separator": " || ",
                  "agreement": "normalized string equality (lower case, whitespace collapsed) or identical explicit ENVO-ID sets",
                  "no_inference": "no habitat or ENVO ID is inferred from taxonomy, organism name, similarity or geography"},
        "outputs": {f: C.sha256_file(out / f) for f in sorted(files) if (out / f).exists()},
    }
    return man


def write_outputs(out: Path, rows, links, ev, ent, mode: str, figures: bool = True,
                  literature_path: Path | None = None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    write_tables(out, rows, links, ev, ent)
    C.write_tsv(out / "habitat_attribute_inventory.tsv", ["source", "attribute", "n_samples", "role"],
                attribute_inventory(ent))
    C.write_tsv(out / "habitat_coverage_summary.tsv", SUMMARY_COLS, coverage_summary(rows, ev))
    files = ["habitat_record_availability.tsv", "habitat_provenance_links.tsv", "habitat_evidence.tsv", "habitat_requests.tsv",
             "habitat_attribute_inventory.tsv", "habitat_coverage_summary.tsv"]
    if figures:
        files += ["figures/" + f for f in write_figures(out / "figures", rows, ev)]
    C.dump_json(out / "habitat_retrieval_manifest.json", build_manifest(out, rows, ent, mode, literature_path, files))
