#!/usr/bin/env python3
"""PR-7a mutation audit: independent check that the release-gate and post-deployment-verifier tests actually guard
the behaviour they claim to guard.

Each mutation re-introduces one specific weakness (a fail-open gate path or an unbounded / partial verifier) into a
temporary copy of the repository, then runs the relevant subset of tests/test_web_pr7.py against that copy. The
audit passes only when every mutation is detected (pytest fails) and the unmutated copy passes. The working tree is
never modified.

Usage: python web/scripts/pr7a_mutation_audit.py [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GATE = "web/scripts/release_gate.py"
ROLL = "web/scripts/site_rollback.py"
GATE_K = "gate or checklist or report_mode or offline or real_checklist or real_repository or metadata or binaries"
VERIFY_K = "verifier or verify_served"

MUTATIONS = [
    # (id, file, old, new, test selection, weakness re-introduced)
    ("G2", GATE, "        record = not rprobs\n", "        record = b.get('status') == 'resolved'\n", GATE_K,
     "resolution record not validated"),
    ("G3", GATE, "            resolved = record and check_ok is True", "            resolved = record and check_ok is not False",
     GATE_K, "undecidable check (None) counts as passing"),
    ("G4", GATE, '"production_allowed": not unresolved and not problems}', '"production_allowed": not unresolved}', GATE_K,
     "checklist problems ignored"),
    ("G5", GATE, "    for i in MANDATORY_BLOCKERS:\n        if i not in present:", "    for i in ():\n        if i not in present:",
     GATE_K, "deleted mandatory blocker not re-added"),
    ("G6", GATE, 'if a.mode == "production" and not (a.online and a.sha):', "if False:", GATE_K,
     "production allowed offline / without --sha"),
    ("G7", GATE, 'return None, f"GitHub Pages API failed: {e}"', 'return True, f"GitHub Pages API failed: {e}"', GATE_K,
     "OPS-1 passes on API error"),
    ("G8", GATE, '    return bt == "workflow", f"Pages', '    return bt in ("workflow", None), f"Pages', GATE_K,
     "OPS-1 passes when build_type is missing"),
    ("G9", GATE, "    return reviewers and main_only, (", "    return main_only, (", GATE_K, "OPS-2 ignores required reviewers"),
    ("G10", GATE, 'and names == ["main"] and kinds == ["branch"] and total == len(policies))', 'and "main" in names)', GATE_K,
     "OPS-2 accepts extra deployment branches / tag policies"),
    ("G16", GATE, 'kinds == ["branch"] and total == len(policies))', 'kinds in (["branch"], ["None"]))', GATE_K,
     "OPS-2 assumes a policy without a type is a branch and ignores pagination"),
    ("G11", GATE, "r.get(\"path\") == WEB_DATA_WORKFLOW", "r.get(\"name\") == \"web-data\"", GATE_K,
     "CI-1 trusts the workflow name"),
    ("G12", GATE, "        if d > (today", "        if False and d > (today", GATE_K, "future decision dates accepted"),
    ("G13", GATE, "    elif RESERVED_HOSTS.search(u.hostname):", "    elif False:", GATE_K, "example/reserved reference hosts accepted"),
    ("G14", GATE, "    if ctx.get(\"online\") and ctx.get(\"release\") is None:\n        return None, f\"release dates",
     "    if False:\n        return None, f\"release dates", GATE_K, "MD-2 passes online when the Release cannot be read"),
    ("G15", GATE, "        except Exception as e:  # noqa: BLE001", "        except ZeroDivisionError as e:  # noqa: BLE001",
     GATE_K, "unexpected exception in a check not contained"),
    ("V1", ROLL, "                h = sha256_bytes(body)\n", "                h = sha256_bytes(body[:65536])\n", VERIFY_K,
     "only a prefix of each file hashed"),
    ("V2", ROLL, "            if length is not None and length.isdigit() and int(length) != len(body):",
     "            if False:", VERIFY_K, "truncated bodies accepted"),
    ("V3", ROLL, "                if time.monotonic() - t0 > request_deadline:", "                if False:", VERIFY_K,
     "no per-request wall-clock deadline (slow-drip bodies)"),
    ("V4", ROLL, "                b = r.read1(65536)", "                b = r.read(65536)", VERIFY_K,
     "blocking read defeats the body deadline"),
    ("V5", ROLL, "max_workers=max(1, workers)", "max_workers=64", VERIFY_K, "unbounded concurrency"),
    ("V6", ROLL, "max_workers=max(1, workers)", "max_workers=1", VERIFY_K, "sequential verification"),
    ("V7", ROLL, "                lim = min(request_timeout, rem)", "                lim = request_timeout", VERIFY_K,
     "per-request limit not capped by the total deadline"),
    ("V8", ROLL, "        for attempt in range(retries + 1):", "        for attempt in range(1):", VERIFY_K,
     "no per-file retries for transient failures"),
    ("V9", ROLL, "        pending = still\n", "        pending = pending if still else still\n", VERIFY_K,
     "every file re-fetched in every propagation round"),
    ("V10", ROLL, "    while pending and remaining() > 0 and (max_rounds is None or rounds < max_rounds):",
     "    while pending and remaining() > 0 and rounds < 1:", VERIFY_K, "no propagation re-check rounds"),
]

COPY = [".github", "tests/test_web_pr7.py", "web/scripts", "web/release", "docs/website/release_blockers.json",
        "LICENSE", "README.md", "CITATION.cff", ".zenodo.json", "CHANGELOG.md", "MAINTENANCE.md", "BINARIES.md",
        "releases/v1.6.0/RELEASE_NOTES_v1.6.0.md", "web/package.json", "tools/export_web_data.py"]


def make_copy(dst: Path) -> None:
    for rel in COPY:
        src = REPO / rel
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, out, ignore=shutil.ignore_patterns("__pycache__"))
        elif src.is_file():
            shutil.copy2(src, out)


def run_tests(root: Path, k: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "tests/test_web_pr7.py",
                        "-k", k], cwd=root, capture_output=True, text=True, timeout=900)
    tail = (r.stdout.strip().splitlines() or [""])[-1]
    return r.returncode, tail


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    results, ok = [], True
    with tempfile.TemporaryDirectory(prefix="pr7a_mut_") as td:
        base = Path(td) / "base"
        make_copy(base)
        for k, label in ((GATE_K, "gate"), (VERIFY_K, "verifier")):
            rc, tail = run_tests(base, k)
            print(f"BASELINE {label:8} rc={rc} {tail}")
            results.append({"id": f"BASELINE-{label}", "rc": rc, "tail": tail, "expected": "pass", "ok": rc == 0})
            ok &= rc == 0
        for mid, rel, old, new, k, what in MUTATIONS:
            work = Path(td) / mid
            shutil.copytree(base, work)
            f = work / rel
            src = f.read_text()
            if src.count(old) != 1:
                print(f"{mid}: mutation anchor not found exactly once in {rel}")
                results.append({"id": mid, "weakness": what, "ok": False, "error": "anchor not unique"})
                ok = False
                continue
            f.write_text(src.replace(old, new))
            rc, tail = run_tests(work, k)
            killed = rc != 0
            ok &= killed
            print(f"{mid:4} {'KILLED ' if killed else 'SURVIVED'} rc={rc} {what} :: {tail}")
            results.append({"id": mid, "file": rel, "weakness": what, "rc": rc, "tail": tail, "killed": killed, "ok": killed})
            shutil.rmtree(work)
    if a.json:
        a.json.write_text(json.dumps(results, indent=2) + "\n")
    n = sum(1 for r in results if r.get("killed"))
    print(f"{'MUTATION_AUDIT_PASS' if ok else 'MUTATION_AUDIT_FAIL'}: {n}/{len(MUTATIONS)} mutations detected")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
