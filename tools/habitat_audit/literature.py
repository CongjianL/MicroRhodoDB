"""Merge reviewer literature results, apply parent verification and decisions (PR-7c.1).

Inputs : reviewer JSON files (first pass parts, optional retry that supersedes listed records),
         the parent quote-verification JSON produced by litverify.py, and the explicit parent
         decisions in PARENT_DECISIONS below.
Output : docs/website/pr7c1/literature/literature_evidence.json (classifier input) and
         docs/website/pr7c1/literature/literature_parent_verification.tsv (one row per item).

Rules
- An item counts only when its quote was found verbatim in the re-fetched source
  (parent_verified = true). Unverified items are kept with scope 'rejected'.
- Isolate scope additionally requires the parent to accept the strain match; the decisions below
  demote or reject reviewer isolate calls that rest on cross-sentence inference, a different strain,
  or geography only (geography is never habitat).
- Final literature_status is recomputed from the accepted items:
  ISOLATE_EVIDENCE > ORGANISM_CONTEXT > (LOOKUP_FAILED if any in-scope source was not accessible,
  else NOT_REPORTED). Inaccessible sources are never NOT_REPORTED.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import common as C

LIT_DIR = C.OUT_DIR / "literature"

# key: (source_acc, habitat_text) -> (decision, reason). decision in
# {"demote_organism", "reject"}; anything not listed keeps the reviewer scope if verified.
PARENT_DECISIONS = {
    ("P02945", "the Red Sea"): ("demote_organism", "different_strain_SG1_not_NRC-1"),
    ("P69051", "Western Australia"): ("reject", "geography_only"),
    ("Q53496", "Andes heights"): ("reject", "geography_only"),
    ("I0YUS5", "arctic freshwater alga"): ("demote_organism", "descriptive_epithet_not_isolation_statement"),
    ("Q18DH5", "solar saltern"): ("demote_organism", "strain_not_named_in_quoted_sentence"),
    ("Q18DH8", "solar saltern"): ("demote_organism", "strain_not_named_in_quoted_sentence"),
    ("S5DM51", "Mediterranean deep chlorophyll maximum"): ("demote_organism", "clone_id_not_named"),
    ("Q9AFF7", "Pacific Ocean near Hawaii at a depth of 75 m"): ("demote_organism", "clone_id_not_named_exactly"),
    ("Q6J4G7", "the Red Sea"): ("reject", "geography_only_dataset_level_not_per_clone"),
    ("A0A089ZH82", "full-scale agricultural biogas plants"): ("demote_organism", "strain_not_named_in_quoted_sentence"),
}


def merge(parts: list[Path], retry: Path | None, additions: Path | None = None) -> dict:
    lit: dict = {}
    for p in parts:
        lit.update(json.loads(p.read_text(encoding="utf-8")))
    if retry and retry.exists():
        r = json.loads(retry.read_text(encoding="utf-8"))
        for a, v in r.items():
            v = dict(v)
            v["notes"] = ("[second pass] " + (v.get("notes") or "")).strip()
            lit[a] = v
    if additions and additions.exists():
        add = json.loads(additions.read_text(encoding="utf-8"))
        for a in sorted(k for k in add if not k.startswith("_")):
            v = dict(lit[a])
            spec = add[a]
            v["items"] = list(v.get("items", [])) + [dict(x, added_by="parent") for x in spec.get("items", [])]
            repl = {x["title"]: dict(x, added_by="parent") for x in spec.get("replace_sources", [])}
            srcs = [repl.pop(sx.get("title"), sx) for sx in v.get("sources_checked", [])]
            if repl:
                raise ValueError(f"{a}: replace_sources titles not found: {sorted(repl)}")
            v["sources_checked"] = srcs + [dict(x, added_by="parent") for x in spec.get("add_sources", [])]
            v["notes"] = ((v.get("notes") or "") + " | [parent step-3] see literature_parent_additions.json").strip()
            lit[a] = v
    return lit


def apply(lit: dict, verification: dict, decisions: dict = PARENT_DECISIONS) -> tuple[dict, list[list]]:
    out, rows = {}, []
    for acc in sorted(lit):
        rec = lit[acc]
        items = []
        for i, it in enumerate(rec.get("items", [])):
            it = dict(it)
            v = verification.get(f"{acc}#{i}", {})
            found = bool(v.get("quote_found_in_source")) and bool(v.get("habitat_text_in_quote"))
            reviewer_scope = it.get("scope")
            dec, reason = decisions.get((acc, it.get("habitat_text")), (None, ""))
            if not found:
                it["scope"], it["parent_verified"], reason = "rejected", False, "quote_not_found_in_source"
            elif dec == "reject":
                it["scope"], it["parent_verified"] = "rejected", False
            elif dec == "demote_organism":
                it["scope"], it["parent_verified"] = "organism", True
                it["consistent_with_db"] = "not_applicable"
            else:
                it["parent_verified"] = True
                reason = reason or "accepted"
            it["reviewer_scope"] = reviewer_scope
            it["parent_decision_reason"] = reason
            it["verify_request_key"] = v.get("request_key", "")
            it["source_sha256"] = v.get("source_sha256")
            items.append(it)
            rows.append([acc, i, reviewer_scope, it["scope"], int(it["parent_verified"]), reason,
                         int(found), it.get("pmid") or "", it.get("doi") or "", it.get("locator") or "",
                         it.get("habitat_text") or "", it.get("strain_named") or "", it.get("consistent_with_db") or "",
                         it.get("access") or "", it.get("source_url") or "", v.get("source_sha256") or ""])
        acc_items = [x for x in items if x["parent_verified"]]
        srcs = rec.get("sources_checked", [])
        if any(x["scope"] == "isolate" for x in acc_items):
            status = "ISOLATE_EVIDENCE"
        elif any(x["scope"] == "organism" for x in acc_items):
            status = "ORGANISM_CONTEXT"
        elif any(s.get("access") == "not_accessible" for s in srcs) or rec.get("literature_status") == "LOOKUP_FAILED":
            status = "LOOKUP_FAILED"
        else:
            status = "NOT_REPORTED"
        out[acc] = {"literature_status": status, "reviewer_literature_status": rec.get("literature_status"),
                    "items": items, "sources_checked": srcs, "notes": rec.get("notes", "")}
    return out, rows


VERIF_COLS = ["source_acc", "item_index", "reviewer_scope", "final_scope", "parent_verified", "parent_decision_reason",
              "quote_found_in_source", "pmid", "doi", "locator", "habitat_text", "strain_named", "consistent_with_db",
              "access", "source_url", "source_sha256"]


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--parts", type=Path, nargs="+", required=True)
    ap.add_argument("--retry", type=Path, default=None)
    ap.add_argument("--additions", type=Path, default=LIT_DIR / "literature_parent_additions.json")
    ap.add_argument("--verification", type=Path, required=True)
    ap.add_argument("--merged-out", type=Path, default=None, help="write merged reviewer JSON (for litverify)")
    a = ap.parse_args(argv)
    lit = merge(a.parts, a.retry, a.additions)
    if a.merged_out:
        C.dump_json(a.merged_out, lit)
        print(f"merged {len(lit)} records -> {a.merged_out}")
        return 0
    ver = json.loads(a.verification.read_text(encoding="utf-8"))
    final, rows = apply(lit, ver)
    C.dump_json(LIT_DIR / "literature_evidence.json", final)
    C.write_tsv(LIT_DIR / "literature_parent_verification.tsv", VERIF_COLS, rows)
    import collections
    print(collections.Counter(v["literature_status"] for v in final.values()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
