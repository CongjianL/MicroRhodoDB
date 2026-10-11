#!/usr/bin/env python3
"""PR-5a adversarial mutation audit of the implementation (not of the data).

Each mutant re-introduces one of the reviewed defects (or a close variant) into the source code, runs
the regression tests that are supposed to catch it, and restores the file. A mutant must be KILLED
(tests fail). Writes docs/website/pr5a/mutation_audit.{json,md}. Exit 1 if any mutant survives.

Usage (repository root, PATH must provide node/npx and the mrdb python):
    python web/scripts/pr5a_mutation_audit.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "web"
OUT = REPO / "docs/website/pr5a"

VITEST = ["npx", "vitest", "run", "tests/unit/pr5a.test.ts"]
PYTEST = [sys.executable, "-m", "pytest", "-q", "-x", "tests/test_web_pr5a.py", "tests/test_web_pr5.py"]

MUTANTS = [
    ("D4", "clade-state population silently widened to all records (the PR-5 bug)", "web/src/lib/drilldown.ts",
     'members_candidates: { group: "member_candidate", eng: true }', 'members_candidates: { group: "all", eng: true }', VITEST, WEB),
    ("D4", "members+candidates group filter admits boundary records", "web/src/lib/browse.ts",
     'if (g === "member_candidate") return mg === "member" || mg === "candidate";',
     'if (g === "member_candidate") return mg === "member" || mg === "candidate" || mg === "boundary";', VITEST, WEB),
    ("D1", "membership-status drilldown loses group=all (Browse member default; the PR-5 bug)", "web/src/lib/drilldown.ts",
     'membership_status: (k) => (k ? { status: k as BrowseState["status"] } : undefined),',
     'membership_status: (k) => (k ? { status: k as BrowseState["status"], group: "member" } : undefined),', VITEST, WEB),
    ("D1", "all-records population drops engineered constructs", "web/src/lib/drilldown.ts",
     'all_records: { group: "all", eng: true }', 'all_records: { group: "all", eng: false }', VITEST, WEB),
    ("D1", "counted population includes engineered constructs", "web/src/lib/drilldown.ts",
     'counted_records: { group: "all", eng: false }', 'counted_records: { group: "all", eng: true }', VITEST, WEB),
    ("D1", "domain drilldown maps the null category to all domains", "web/src/lib/drilldown.ts",
     'tax_domain_counted: (k) => ({ domain: (k ?? "none") as BrowseState["domain"] }),',
     'tax_domain_counted: (k) => ({ domain: (k ?? "") as BrowseState["domain"] }),', VITEST, WEB),
    ("D2", "clade ID searched with the Browse free-text filter (the PR-5 bug)", "web/src/features/search/textSearch.ts",
     'cands.push([`clade=${qu}`, `Formal assignments to clade ${qu}`]);',
     'cands.push([`q=${qu}`, `Formal assignments to clade ${qu}`]);', VITEST, WEB),
    ("D2", "'same records' claimed on equal counts instead of equal sets", "web/src/features/search/textSearch.ts",
     'same: both === keys.size && both === sel.length,', 'same: sel.length === keys.size,', VITEST, WEB),
    ("D2", "PDB ID mapped to free text", "web/src/features/search/textSearch.ts",
     'cands.push([`pdbid=${qu}`, `Records linked to PDB entry ${qu}`]);',
     'cands.push([`q=${qu}`, `Records linked to PDB entry ${qu}`]);', VITEST, WEB),
    ("D3", "browser reconcile ignores duplicate keys", "web/src/lib/stats.ts",
     "if (exp.has(i.key)) duplicates.push(i.key);", "if (exp.has(i.key)) void 0;", VITEST, WEB),
    ("D3", "browser reconcile treats a key missing on one side as 0", "web/src/lib/stats.ts",
     "if (a === undefined || b === undefined || a !== b)", "if ((a ?? 0) !== (b ?? 0))", VITEST, WEB),
    ("D3", "Python reconcile compares sorted values (the PR-5 approach)", "web/scripts/summary_reconcile.py",
     "        if type(got[k]) is not type(exp[k]) or got[k] != exp[k]:",
     "        if sorted(got.values()) != sorted(exp.values()):", PYTEST, REPO),
    ("D3", "Python reconcile merges duplicate keys silently", "web/scripts/summary_reconcile.py",
     '            raise DuplicateKey(f"{what}: duplicate key {k!r}")', "            pass", PYTEST, REPO),
    ("D3", "Python reconcile drops the null category", "web/scripts/summary_reconcile.py",
     "    for k in sorted(set(exp) - set(got), key=repr):", "    for k in sorted(set(exp) - set(got) - {None, 'None'}, key=repr):", PYTEST, REPO),
    ("D3", "tip_role not derived (skipped)", "web/scripts/summary_reconcile.py",
     '        elif d["id"] == "tip_role":', '        elif d["id"] == "tip_role_disabled":', PYTEST, REPO),
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for defect, desc, rel, old, new, cmd, cwd in MUTANTS:
        path = REPO / rel
        src = path.read_text()
        if src.count(old) != 1:
            results.append({"defect": defect, "mutant": desc, "file": rel, "status": "INVALID (anchor not found once)"})
            continue
        t0 = time.time()
        try:
            path.write_text(src.replace(old, new))
            p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=900)
        finally:
            path.write_text(src)
        tail = [ln for ln in (p.stdout + p.stderr).splitlines() if ln.strip()][-3:]
        results.append({"defect": defect, "mutant": desc, "file": rel, "command": " ".join(cmd),
                        "status": "KILLED" if p.returncode != 0 else "SURVIVED", "seconds": round(time.time() - t0, 1), "tail": tail})
        print(f"[{results[-1]['status']}] {defect} {desc}", flush=True)
    ok = all(r["status"] == "KILLED" for r in results)
    (OUT / "mutation_audit.json").write_text(json.dumps({"all_killed": ok, "mutants": results}, indent=1) + "\n")
    md = ["# PR-5a mutation audit (implementation mutants)", "",
          "Generated by `web/scripts/pr5a_mutation_audit.py`. Each mutant re-introduces a reviewed defect or a close variant "
          "into the source, runs the regression tests that must catch it, and restores the file.", "",
          f"**{sum(r['status'] == 'KILLED' for r in results)} of {len(results)} mutants killed.**", "",
          "| Defect | Mutant | File | Result |", "|---|---|---|---|"]
    md += [f"| {r['defect']} | {r['mutant']} | `{r['file']}` | {r['status']} |" for r in results]
    (OUT / "mutation_audit.md").write_text("\n".join(md) + "\n")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
