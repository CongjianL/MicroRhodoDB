#!/usr/bin/env python3
"""PR-7c.2 mutation audit: independent check that the habitat tests guard the behaviour they claim to guard.

Each mutation re-introduces one specific weakness into a temporary copy of the repository and runs the relevant
tests against that copy:
  E*  exporter (tools/habitat_export/build.py, tools/export_web_data.py) -> pytest tests/test_web_pr7c2.py
  U*  browser view model (web/src/lib/habitat.ts)                        -> vitest tests/unit/pr7c2.test.ts
The audit passes only when the unmutated copy passes and every mutation is detected (the tests fail). The working
tree is never modified.

Mutants whose code path is unreachable with the pinned inputs (for example the coverage cross-check or the
literature quote check, which can only fire if an input changes, and any input change is first rejected by the
SHA-256 pin) are not listed: they would be equivalent mutants.

Usage: python tools/habitat_export/mutation_audit.py [--json out.json] [--only E1,U3]
Environment: MRDB_DB (default releases/v1.6.0/db/microrhododb_v1.6.0.sqlite in this repository).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
B = "tools/habitat_export/build.py"
X = "tools/export_web_data.py"
H = "web/src/lib/habitat.ts"

EXPORTER = [
    # (id, file, old, new, weakness re-introduced)
    ("E1", B, '"is_mrdb_representative": representative[r["mrdb_acc"]] == acc,', '"is_mrdb_representative": True,',
     "every source record marked as the MRDB representative"),
    ("E2", B, '    if written - verified:\n        return "envo_id_not_found_in_ols"',
     '    if False:\n        return "envo_id_not_found_in_ols"', "unverified ENVO IDs not quarantined"),
    ("E3", B, '    if role in MIXS_ENV and UNPREFIXED_ID.match(v):', '    if False:',
     "bare numeric env_* values not quarantined"),
    ("E4", B, '"value": opt(r["value_original"]),', '"value": r["value_original"] or "(empty)",',
     "empty values replaced by an invented string"),
    ("E5", B, 'for k in ("source_acc", "evidence_source", "entity_accession", "link_index",\n',
     'for k in ("evidence_source", "source_acc", "entity_accession", "link_index",\n', "HE evidence-ID field order changed"),
    ("E6", B, 'str(x.get(k)) for k in ("pmid", "doi", "quote", "scope")', '(x.get(k) or "") for k in ("pmid", "doi", "quote", "scope")',
     "HL None-serialisation rule changed (null -> empty string)"),
    ("E7", B, '        need(sha256_bytes(b) == sha, f"SHA-256 mismatch for {rel}", "BLOCKED_HABITAT_SOURCE")\n', "",
     "input SHA-256 pin not enforced"),
    ("E8", B, '        differ = len({entries[a]["grade"] for a in srcs}) > 1\n',
     '        differ = len({entries[a]["grade"] for a in srcs}) > 1 and len(srcs) > 2\n',
     "multi-source grade difference under-reported"),
    ("E9", B, '        g = ROLE_GROUP.get(r["role"])\n',
     '        g = "physical" if r["role"] == "host" else ROLE_GROUP.get(r["role"])\n', "host values routed into physical habitat"),
    ("E10", B, '"doi": lit.get("doi") or None,', '"doi": None,', "literature DOI dropped from citations"),
    ("E11", B, '"database": "no_traceable_sample_link" if no_link else "not_reported_in_linked_sample_records"',
     '"database": "not_reported_in_linked_sample_records"', "no-link records claim 'not reported in linked samples'"),
    ("E12", B, "        srcs.sort(key=lambda a: (a != rep, a))\n", "", "representative no longer listed first"),
    ("E13", B, '        need(len(b) <= exp["max_file_bytes"], f"habitat/records/{ma}.json is {len(b)} bytes (> budget)")\n',
     "", "per-file byte budget not enforced"),
    ("E14", B, '    need(not bad, f"MRDB mismatch vs accessions.json for {bad[:5]}")\n', "",
     "audit MRDB mapping not checked against accessions.json"),
    ("E15", B, '"envo_ids": envo,', '"envo_ids": [],', "verified ENVO IDs dropped"),
    ("E16", B, '"flags": sorted(split(r["flags"])),', '"flags": sorted(f for f in split(r["flags"]) if not f.startswith("host")),',
     "host flags (host-only, host-tissue) dropped"),
    ("E17", B, '            "literature_sources_checked": checked,', '            "literature_sources_checked": [],',
     "literature sources checked dropped"),
    ("E18", B, '            groups[g].sort(key=lambda i: (i["role"], i["evidence_source"], i["entity_accession"],',
     '            groups[g].sort(reverse=True, key=lambda i: (i["role"], i["evidence_source"], i["entity_accession"],',
     "item order changed"),
    ("E19", X, "    if habitat:  # PR-7c.2 sidecar", "    if False:  # PR-7c.2 sidecar", "exporter silently omits the sidecar"),
    ("E20", X, "habitat=not a.no_habitat)", "habitat=True)", "--no-habitat ignored"),
]

UI = [
    ("U1", H, "const EVIDENCE_ID_RE = /^H[EL][0-9a-f]{12}$/;", "const EVIDENCE_ID_RE = /^H[EL]/;",
     "malformed evidence IDs accepted"),
    ("U2", H, "  if (i.quarantine) return [];\n", "", "quarantined values linked as ENVO terms"),
    ("U3", H, 'x.protocol === "https:" && ITEM_URL_HOSTS', '(x.protocol === "https:" || x.protocol === "http:") && ITEM_URL_HOSTS',
     "http record URLs linked"),
    ("U4", H, "ITEM_URL_HOSTS.has(x.host) && ", "", "record URLs to any host linked"),
    ("U5", H, '  if (file.mrdb_acc !== mrdbAcc) return { ok: false, reason: "mrdb_mismatch" };\n', "",
     "habitat file of another MRDB accession accepted"),
    ("U6", H, "got.length !== sourceAccs.length || ", "", "habitat file with extra (merged) source records accepted"),
    ("U7", H, '    not_reviewed: "literature not reviewed",\n    inaccessible: "literature not accessible",',
     '    not_reviewed: "literature not accessible",\n    inaccessible: "literature not reviewed",',
     "missingness literature scope swapped"),
    ("U8", H, 'const db = e.missingness.database === "no_traceable_sample_link"', 'const db = false',
     "no-link records say 'not reported in the linked sample records'"),
    ("U9", H, '.filter((i) => i.evidence_source === "literature" && i.literature?.scope === "organism")', "",
     "organism context shown without the literature/organism-scope check"),
    ("U10", H, "GROUP_OF.get(i.role) === group && ", "", "items in the wrong display group accepted"),
    ("U11", H, 'const usable = phys.filter((i) => grading.has(i.role) && i.value_status === "usable");',
     "const usable = phys.filter((i) => grading.has(i.role));", "non-usable values shown as physical habitat"),
    ("U12", H, '  biosamples: [/^SAM[NED][A-Z]?\\d+$/,', "  biosamples: [/SAM/,", "unvalidated BioSample accessions linked"),
    ("U13", H, '(doi && /^10\\.\\d{4,9}\\/\\S+$/.test(doi)', "(doi && /^10\\./.test(doi)", "unvalidated DOIs linked"),
    ("U14", H, '  return e.flags.includes("host_association_only") ? "Physical habitat not reported; host reported." : null;',
     "  return null;", "host-only wording missing"),
    ("U16", H, 'return status === "NOT_REPORTED" && sampleLink === "none" ?', 'return false ?',
     "no-link records labelled with a checked 'Host not reported'"),
    ("U15", H, 'const ENVO_RE = /^ENVO:(\\d{8})$/;', "const ENVO_RE = /ENVO:(\\d+)/;", "malformed ENVO IDs linked"),
]

SKIP = shutil.ignore_patterns(".git", "node_modules", "dist", "test-results", "__pycache__", ".pytest_cache")


def make_copy(dst: Path) -> None:
    shutil.copytree(REPO, dst, ignore=lambda d, names: (
        set(SKIP(d, names)) | ({"public"} if Path(d) == REPO / "web" else set())))
    os.symlink(REPO / "web/node_modules", dst / "web/node_modules")
    os.symlink(REPO / "web/public", dst / "web/public")


def run_pytest(root: Path, db: Path) -> tuple[int, str]:
    env = {**os.environ, "MRDB_REPO": str(root), "MRDB_DB": str(db)}
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "tests/test_web_pr7c2.py"],
                       cwd=root, env=env, capture_output=True, text=True, timeout=1800)
    return r.returncode, (r.stdout.strip().splitlines() or [""])[-1]


def run_vitest(root: Path) -> tuple[int, str]:
    r = subprocess.run(["npx", "vitest", "run", "tests/unit/pr7c2.test.ts"], cwd=root / "web", capture_output=True,
                       text=True, timeout=900)
    lines = [ln.strip() for ln in (r.stdout + r.stderr).splitlines() if "Tests" in ln and ("passed" in ln or "failed" in ln)]
    return r.returncode, (lines[-1] if lines else (r.stdout.strip().splitlines() or [""])[-1])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--only", default="")
    a = ap.parse_args(argv)
    only = set(filter(None, a.only.split(",")))
    db = Path(os.environ.get("MRDB_DB", REPO / "releases/v1.6.0/db/microrhododb_v1.6.0.sqlite")).resolve()
    suites = (("pytest", EXPORTER, lambda root: run_pytest(root, db)), ("vitest", UI, run_vitest))
    results, ok, n_mut, n_killed = [], True, 0, 0
    with tempfile.TemporaryDirectory(prefix="pr7c2_mut_") as td:
        root = Path(td) / "repo"
        make_copy(root)
        for label, muts, run in suites:
            muts = [m for m in muts if not only or m[0] in only]
            if not muts:
                continue
            rc, tail = run(root)
            print(f"BASELINE {label} rc={rc} {tail}", flush=True)
            results.append({"id": f"BASELINE-{label}", "rc": rc, "tail": tail, "expected": "pass", "ok": rc == 0})
            ok &= rc == 0
            for mid, rel, old, new, what in muts:
                n_mut += 1
                f = root / rel
                src = f.read_text()
                if src.count(old) != 1:
                    print(f"{mid}: mutation anchor found {src.count(old)} times in {rel}", flush=True)
                    results.append({"id": mid, "file": rel, "weakness": what, "ok": False, "error": "anchor not unique"})
                    ok = False
                    continue
                try:
                    f.write_text(src.replace(old, new))
                    rc, tail = run(root)
                finally:
                    f.write_text(src)
                killed = rc != 0
                n_killed += killed
                ok &= killed
                print(f"{mid:4} {'KILLED ' if killed else 'SURVIVED'} rc={rc} {what} :: {tail}", flush=True)
                results.append({"id": mid, "suite": label, "file": rel, "weakness": what, "rc": rc, "tail": tail,
                                "killed": killed, "ok": killed})
    if a.json:
        a.json.write_text(json.dumps(results, indent=2) + "\n")
    print(f"{'MUTATION_AUDIT_PASS' if ok else 'MUTATION_AUDIT_FAIL'}: {n_killed}/{n_mut} mutations detected")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
