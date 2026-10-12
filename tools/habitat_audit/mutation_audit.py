"""Mutation audit for the PR-7c.1 rule tests.

Each mutation breaks one scientific rule in a temporary copy of the audit package; the PR-7c.1 test
module must fail for every mutant (a surviving mutant means the rule is untested).
Usage: python -m tools.habitat_audit.mutation_audit [--out PATH]
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import common as C

MUTATIONS = [
    ("failure_not_graded_lookup_failed", "classify.py",
     '    if failures:\n        grade = "LOOKUP_FAILED"', '    if False:\n        grade = "LOOKUP_FAILED"'),
    ("culture_value_counted_as_habitat", "classify.py",
     "elif N.is_culture_term(v):", "elif False:"),
    ("tissue_value_counted_as_habitat", "classify.py",
     'elif role == "isolation_source" and N.is_tissue_term(v)', 'elif False and N.is_tissue_term(v)'),
    ("agreement_ignores_punctuation", "classify.py",
     'if a["value_normalized"] == b["value_normalized"] or (',
     'if _alnum(a["value_normalized"]) == _alnum(b["value_normalized"]) or ('),
    ("geography_counted_as_habitat", "normalize.py",
     'HABITAT_ROLES = ("env_broad_scale", "env_local_scale", "env_medium", "isolation_source", "host")',
     'HABITAT_ROLES = ("env_broad_scale", "env_local_scale", "env_medium", "isolation_source", "host", "country")'),
    ("ncbi_numeric_uid_mapping", "retrieve.py",
     'd = docs.get(a) or docs.get("__alias__" + a)',
     'd = docs.get(a) or docs.get("__alias__" + a) or next((x for k, x in docs.items() if not k.startswith("__") '
     'and str(x.get("uid")) == str(int("".join(ch for ch in a if ch.isdigit()) or 0))), None)'),
    ("missing_token_not_applicable_accepted", "normalize.py",
     "not collected|not applicable|", "not collected|"),
    ("unverified_literature_accepted", "classify.py",
     'iso_items = [x for x in lit_items if x.get("scope") == "isolate" and x.get("parent_verified")]',
     'iso_items = [x for x in lit_items if x.get("scope") == "isolate"]'),
    ("host_self_not_ignored", "classify.py",
     'elif role == "host" and N.host_is_self(v, names, taxids, viral=viral):',
     'elif False and N.host_is_self(v, names, taxids, viral=viral):'),
    ("placeholder_counted_as_habitat", "classify.py",
     'elif N.is_placeholder(v, it["envo_ids"]):', "elif False:"),
    ("mrdb_rollup_collapses_failure", "summarize.py",
     'MRDB_ORDER = ("DIRECT_SAMPLE", "VERIFIED_ISOLATE", "AMBIGUOUS", "ORGANISM_CONTEXT_ONLY", "LOOKUP_FAILED",\n'
     '              "NOT_SEARCHED", "NOT_REPORTED")',
     'MRDB_ORDER = ("DIRECT_SAMPLE", "VERIFIED_ISOLATE", "AMBIGUOUS", "ORGANISM_CONTEXT_ONLY", "NOT_REPORTED",\n'
     '              "LOOKUP_FAILED", "NOT_SEARCHED")'),
    ("unverified_quote_kept", "literature.py",
     "            if not found:\n", "            if False:\n"),
    ("inaccessible_literature_reported_absent", "literature.py",
     'elif any(s.get("access") == "not_accessible" for s in srcs) or rec.get("literature_status") == "LOOKUP_FAILED":',
     "elif False:"),
]


def _stage(tmp: Path) -> None:
    shutil.copytree(C.REPO / "tools" / "habitat_audit", tmp / "tools" / "habitat_audit",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (tmp / "tools" / "__init__.py").write_text("", encoding="utf-8")
    (tmp / "tests" / "data").mkdir(parents=True)
    shutil.copy(C.REPO / "tests" / "test_habitat_audit_pr7c1.py", tmp / "tests")
    shutil.copytree(C.FIXTURE_DIR, tmp / "tests" / "data" / "pr7c1")
    out = tmp / "docs" / "website" / "pr7c1"
    out.mkdir(parents=True)
    for f in ("habitat_record_availability.tsv", "habitat_evidence.tsv", "habitat_requests.tsv",
              "habitat_coverage_summary.tsv"):
        shutil.copy(C.OUT_DIR / f, out / f)
    shutil.copytree(C.OUT_DIR / "literature", out / "literature")


def _pytest(tmp: Path) -> tuple[int, str]:
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
                        str(tmp / "tests" / "test_habitat_audit_pr7c1.py")], cwd=tmp, capture_output=True, text=True)
    import re
    last = [ln for ln in p.stdout.strip().splitlines() if ln.strip()][-1:] or [""]
    return p.returncode, re.sub(r"\s+in [0-9.]+s\b.*$", "", last[0])  # drop timings (deterministic log)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=C.OUT_DIR / "mutation_audit.json")
    a = ap.parse_args(argv)
    results = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        _stage(tmp)
        rc, line = _pytest(tmp)
        results.append({"mutation": "none (baseline)", "file": "", "tests_failed": rc != 0, "pytest": line})
        if rc != 0:
            raise SystemExit(f"baseline tests fail: {line}")
        for name, fname, old, new in MUTATIONS:
            f = tmp / "tools" / "habitat_audit" / fname
            src = f.read_text(encoding="utf-8")
            if src.count(old) != 1:
                raise SystemExit(f"mutation {name}: anchor found {src.count(old)} times")
            f.write_text(src.replace(old, new), encoding="utf-8")
            rc, line = _pytest(tmp)
            f.write_text(src, encoding="utf-8")
            results.append({"mutation": name, "file": fname, "tests_failed": rc != 0, "pytest": line})
            print(f"{'KILLED ' if rc else 'SURVIVED'} {name}: {line}", flush=True)
    survived = [r["mutation"] for r in results[1:] if not r["tests_failed"]]
    C.dump_json(a.out, {"n_mutations": len(MUTATIONS), "killed": len(MUTATIONS) - len(survived),
                        "survived": survived, "results": results})
    print(f"killed {len(MUTATIONS) - len(survived)}/{len(MUTATIONS)}")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
