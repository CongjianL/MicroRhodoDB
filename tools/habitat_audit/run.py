"""CLI: python -m tools.habitat_audit.run {pilot,full} [--offline] [--retry-failed] [--cache DIR] [--work DIR]

pilot : deterministic stratified pilot set (records outside it are NOT_SEARCHED)
full  : all 5,466 source records
Outputs (tables, figures, manifest) are written by summarize.write_outputs.
"""
from __future__ import annotations

import argparse
import collections
import json
import time
from pathlib import Path

from . import baseline, classify, retrieve, summarize
from . import common as C
from .http_cache import HttpCache


def select_pilot(records: list[dict], uniprot: dict) -> dict[str, list[str]]:
    """Deterministic strata; order within a stratum by sha256(source_acc + 'pr7c1')."""
    key = C.pilot_order_key
    by = lambda rs: sorted(rs, key=lambda r: key(r["source_acc"]))
    strata: dict[str, list[str]] = collections.OrderedDict()
    combos = collections.defaultdict(list)
    for r in records:
        combos[(r["status_group_audit"], r["domain"])].append(r)
    for (g, d), rs in sorted(combos.items()):
        strata[f"group_domain:{g}:{d}"] = [r["source_acc"] for r in by(rs)[:3]]
    strata["engineered"] = [r["source_acc"] for r in by([r for r in records if r["is_engineered"]])]
    strata["seed"] = [r["source_acc"] for r in by([r for r in records if r["is_seed"]])]
    strata["swissprot"] = [r["source_acc"] for r in by([r for r in records if r["reviewed"]])[:5]]
    strata["release_2026_03"] = [r["source_acc"] for r in by([r for r in records if r["source_release"] == "UniProtKB_2026_03"])[:5]]
    strata["metagenome_like"] = [r["source_acc"] for r in by([r for r in records if r["organism_metagenome_like"]])[:15]]
    dup_pairs = [r for r in records if r["exact_duplicate_of"]]
    strata["exact_duplicate_pairs"] = sorted({r["source_acc"] for r in dup_pairs} | {r["exact_duplicate_of"] for r in dup_pairs})
    sizes = collections.Counter(r["sequence_sha256"] for r in records)
    top = [s for s, n in sizes.most_common(2)]
    strata["largest_seq_groups"] = sorted(r["source_acc"] for r in records if r["sequence_sha256"] in top)
    no_embl = [r for r in records if not (uniprot.get(r["source_acc"], {}).get("embl"))]
    strata["no_embl_xref"] = [r["source_acc"] for r in by(no_embl)[:10]]
    return strata


def load_literature(path: Path) -> dict:
    if path and path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["pilot", "full"])
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--retry-failed", action="store_true")
    ap.add_argument("--cache", type=Path, default=C.DEFAULT_CACHE)
    ap.add_argument("--work", type=Path, default=Path("/workspace/pr7c1_work"))
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--literature", type=Path, default=C.OUT_DIR / "literature" / "literature_evidence.json")
    ap.add_argument("--no-figures", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    cache = HttpCache(a.cache, offline=a.offline, retry_failed=a.retry_failed)
    records = baseline.load_records()
    all_accs = [r["source_acc"] for r in records]
    up_all = retrieve.fetch_uniprot(cache, all_accs)  # cheap (11 batches); needed for pilot strata
    if a.mode == "pilot":
        strata = select_pilot(records, up_all)
        accs = sorted({x for v in strata.values() for x in v})
    else:
        strata, accs = None, all_accs
    print(f"[run] mode={a.mode} records={len(accs)} offline={a.offline}", flush=True)
    ent = retrieve.retrieve_all(cache, accs, log=lambda m: print(m, flush=True),
                                taxids={r["source_acc"]: r["organism_id"] for r in records})
    ent["meta"]["mode"] = a.mode
    ent["meta"]["n_records_searched"] = len(accs)
    if strata:
        ent["meta"]["pilot_strata"] = strata
    ent["meta"]["requests"] = {k: _req_meta(cache, k) for k in sorted(cache.used_keys)}
    lit = load_literature(a.literature)
    lit_keys = {x.get("verify_request_key") for v in lit.values() for x in v.get("items", [])} - {None, ""}
    ent["meta"]["literature_requests"] = {k: _req_meta(cache, k) for k in sorted(lit_keys)}
    a.work.mkdir(parents=True, exist_ok=True)
    retrieve.save_entities(ent, a.work / f"entities_{a.mode}.json")
    searched = set(accs)
    rows, links, ev = [], [], []
    for r in records:
        row, ls, it = classify.classify_record(r, ent, lit.get(r["source_acc"]), r["source_acc"] in searched)
        rows.append(row)
        links.extend(ls)
        ev.extend(it)
    out = a.out or (a.work / f"out_{a.mode}")
    summarize.write_outputs(out, rows, links, ev, ent, mode=a.mode, figures=not a.no_figures,
                            literature_path=a.literature)
    print(f"[run] done in {time.time() - t0:.1f}s cache={cache.stats}", flush=True)
    return rows


def _req_meta(cache: HttpCache, key: str) -> dict:
    e = cache.load(key) or {}
    return {"method": e.get("method"), "url": e.get("url") or "", "request_body": e.get("body") or "", "body_sha256_request":
            C.sha256_bytes((e.get("body") or "").encode()), "status": e.get("status"), "ok": e.get("ok"),
            "error": e.get("error"), "attempts": e.get("attempts"), "retrieved_at": e.get("retrieved_at"),
            "response_sha256": e.get("body_sha256"),
            "uniprot_release": (e.get("headers") or {}).get("X-UniProt-Release")}


if __name__ == "__main__":
    main()
