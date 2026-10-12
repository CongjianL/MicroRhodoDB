#!/usr/bin/env python3
"""PR-7a independent end-to-end check of the release gate's positive and negative production paths.

Independent of tests/test_web_pr7.py: fixtures are built here, and every scenario runs release_gate.py as a separate
process. The gate talks over real HTTP sockets to a local synthetic GitHub API / doi.org server; the only
substitution is the host (api.github.com and doi.org are redirected to 127.0.0.1 by a tiny bootstrap that wraps
urllib.request.urlopen in the child process). No production code path is changed or bypassed and nothing is sent to
GitHub.

Usage: python web/scripts/pr7a_gate_independent_check.py [--json out.json]
"""
from __future__ import annotations

import argparse
import copy
import http.server
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "web" / "scripts"
SHA = "c" * 40
MANDATORY = ["MD-1", "MD-2", "MD-3", "MD-4", "MD-5", "RA-1", "RA-2", "OPS-1", "OPS-2", "CI-1", "VER-1", "ACC-1"]
RECORD = {"decided_by": "CongjianL", "decided_at": "2026-09-30",
          "reference": "https://github.com/CongjianL/MicroRhodoDB/pull/99"}
ROOT = "/repos/CongjianL/MicroRhodoDB"

GOOD = {
    ROOT + "/releases/tags/v1.6.0": {"published_at": "2026-10-10T10:00:00Z", "assets": [
        {"name": "microrhododb_v1.6.0.sqlite", "size": 33464320},
        {"name": "MicroRhodoDB_v1.6.0.tar.gz", "size": 1234}, {"name": "MicroRhodoDB_v1.6.0.tar.gz.sha256", "size": 95}]},
    ROOT + "/pages": {"build_type": "workflow"},
    ROOT + "/environments/github-pages": {
        "protection_rules": [{"type": "required_reviewers", "reviewers": [{"type": "User", "reviewer": {"login": "r"}}]}],
        "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True}, "can_admins_bypass": True},
    ROOT + "/environments/github-pages/deployment-branch-policies": {"branch_policies": [{"name": "main", "type": "branch"}]},
    ROOT + "/actions/runs": {"workflow_runs": [{"id": 7, "name": "web-data", "path": ".github/workflows/web-data.yml",
                                                "head_sha": SHA, "status": "completed", "conclusion": "success"}]},
    "/api/handles/10.5281/zenodo.9999999": {"responseCode": 1},
}

BOOT = r"""
import sys, urllib.request, urllib.parse, runpy
port = int(sys.argv.pop(1))
_orig = urllib.request.urlopen
def _local(req, *a, **k):
    u = urllib.parse.urlsplit(req.full_url)
    if u.hostname not in ("api.github.com", "doi.org"):
        raise RuntimeError("unexpected host " + str(u.hostname))
    req.full_url = urllib.parse.urlunsplit(("http", f"127.0.0.1:{port}", u.path, u.query, ""))
    return _orig(req, *a, **k)
urllib.request.urlopen = _local
sys.argv[0] = sys.argv[1]; del sys.argv[1]
runpy.run_path(sys.argv[0], run_name="__main__")
"""


class Api:
    def __init__(self):
        self.routes = copy.deepcopy(GOOD)
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                path = self.path.split("?")[0]
                v = outer.routes.get(path)
                if isinstance(v, int):
                    self.send_response(v); self.send_header("Content-Length", "0"); self.end_headers(); return
                if v is None:
                    self.send_response(404); self.send_header("Content-Length", "0"); self.end_headers(); return
                b = json.dumps(v).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()


def make_repo(root: Path, blockers: list[dict], **over) -> Path:
    files = {
        "LICENSE": "Licensed under the Creative Commons Attribution 4.0 International (CC BY 4.0).\n"
                   "Source code is released under the MIT License.\n",
        "README.md": "Data: CC BY 4.0. Code: MIT.\n",
        "CITATION.cff": "cff-version: 1.2.0\ndate-released: 2026-10-10\nlicense: CC-BY-4.0\ndoi: 10.5281/zenodo.9999999\n",
        ".zenodo.json": json.dumps({"license": "CC-BY-4.0", "publication_date": "2026-10-10"}),
        "CHANGELOG.md": "## [1.6.0] - 2026-10-10\n",
        "releases/v1.6.0/RELEASE_NOTES_v1.6.0.md": "**Release date:** 2026-10-10\n",
        "web/package.json": json.dumps({"license": "MIT", "version": "2.0.0"}),
        "tools/export_web_data.py": 'WEBSITE_VERSION = "2.0.0"\n',
        "MAINTENANCE.md": "- Contact: issues on GitHub\nArchive: Zenodo\n",
        "BINARIES.md": "Archive `MicroRhodoDB_v1.6.0.tar.gz`\n| `releases/v1.6.0/db/microrhododb_v1.6.0.sqlite` | 33464320 | `"
                       + "f" * 64 + "` |\n",
        "docs/website/release_blockers.json": json.dumps({"version": 1, "blockers": blockers}),
    }
    files.update(over)
    for k, v in files.items():
        p = root / k
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(v)
    return root


def blockers(**changes) -> list[dict]:
    out = []
    for i in MANDATORY:
        b = {"id": i, "title": i, "category": "x", "blocks": ["production"], "status": "resolved",
             "resolution": dict(RECORD), "evidence": "e", "required_decision": "d"}
        if i in changes:
            ch = changes[i]
            if ch is None:
                continue
            b.update(ch)
        out.append(b)
    return out


def run_gate(api: Api, repo: Path, *args: str) -> int:
    cmd = [sys.executable, "-c", BOOT, str(api.port), str(SCRIPTS / "release_gate.py"), "--repo", str(repo), *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120).returncode


PROD = ("--mode", "production", "--online", "--sha", SHA)

SCENARIOS = [
    # name, blocker changes, file overrides, api overrides, args, expected exit
    ("positive: all mandatory blockers resolved + authorised, all checks pass", {}, {}, {}, PROD, 0),
    ("ACC-1 authorisation missing", {"ACC-1": {"status": "open", "resolution": None}}, {}, {}, PROD, 3),
    ("OPS-1 decision missing", {"OPS-1": {"status": "open", "resolution": None}}, {}, {}, PROD, 3),
    ("MD-1 record with future date", {"MD-1": {"resolution": {**RECORD, "decided_at": "2999-12-31"}}}, {}, {}, PROD, 3),
    ("MD-3 record with template reference", {"MD-3": {"resolution": {**RECORD, "reference": "<issue/PR/commit URL>"}}}, {}, {}, PROD, 3),
    ("status 'waived' instead of resolved", {"MD-5": {"status": "waived"}}, {}, {}, PROD, 3),
    ("ACC-1 deleted from the checklist", {"ACC-1": None}, {}, {}, PROD, 3),
    ("MD-2 re-scoped out of production", {"MD-2": {"blocks": []}}, {}, {}, PROD, 3),
    ("MD-2 dates disagree (valid record)", {}, {"CHANGELOG.md": "## [1.6.0] - 2026-10-09\n"}, {}, PROD, 3),
    ("VER-1 pre-release version (valid record)", {}, {"web/package.json": json.dumps({"license": "MIT", "version": "2.0.0-pr7"})}, {}, PROD, 3),
    ("OPS-1 Pages source still legacy", {}, {}, {ROOT + "/pages": {"build_type": "legacy"}}, PROD, 3),
    ("OPS-1 Pages API 403", {}, {}, {ROOT + "/pages": 403}, PROD, 3),
    ("OPS-1 Pages API 404 (as seen unauthenticated today)", {}, {}, {ROOT + "/pages": 404}, PROD, 3),
    ("OPS-2 no required reviewers", {}, {}, {ROOT + "/environments/github-pages": {
        **GOOD[ROOT + "/environments/github-pages"], "protection_rules": [{"type": "branch_policy"}]}}, PROD, 3),
    ("OPS-2 PR branches allowed", {}, {}, {ROOT + "/environments/github-pages/deployment-branch-policies": {
        "branch_policies": [{"name": "main", "type": "branch"}, {"name": "website/pr-3-protein-entry", "type": "branch"}]}}, PROD, 3),
    ("OPS-2 environment API 500", {}, {}, {ROOT + "/environments/github-pages": 500}, PROD, 3),
    ("CI-1 web-data failed", {}, {}, {ROOT + "/actions/runs": {"workflow_runs": [
        {**GOOD[ROOT + "/actions/runs"]["workflow_runs"][0], "conclusion": "failure"}]}}, PROD, 3),
    ("RA-1 Release asset missing", {}, {}, {ROOT + "/releases/tags/v1.6.0": {
        "published_at": "2026-10-10T10:00:00Z", "assets": [{"name": "microrhododb_v1.6.0.sqlite", "size": 33464320}]}}, PROD, 3),
    ("RA-2/MD-3 DOI does not resolve", {}, {}, {"/api/handles/10.5281/zenodo.9999999": {"responseCode": 100}}, PROD, 3),
    ("production without --online", {}, {}, {}, ("--mode", "production", "--sha", SHA), 2),
    ("production without --sha", {}, {}, {}, ("--mode", "production", "--online"), 2),
    ("report mode with every blocker open", {i: {"status": "open", "resolution": None} for i in MANDATORY}, {}, {},
     ("--mode", "report", "--online", "--sha", SHA), 0),
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    results, ok = [], True
    with tempfile.TemporaryDirectory(prefix="pr7a_gate_") as td:
        for n, (name, bch, files, api_over, args, expected) in enumerate(SCENARIOS):
            api = Api()
            api.routes.update(api_over)
            repo = make_repo(Path(td) / f"s{n:02d}", blockers(**bch), **files)
            rc = run_gate(api, repo, *args)
            api.srv.shutdown()
            good = rc == expected
            ok &= good
            print(f"{'PASS' if good else 'FAIL'}  exit={rc} expected={expected}  {name}")
            results.append({"scenario": name, "exit": rc, "expected": expected, "ok": good})
        # API server unreachable: the port of a closed server
        api = Api()
        api.srv.shutdown(); api.srv.server_close()
        rc = run_gate(api, make_repo(Path(td) / "down", blockers()), *PROD)
        good = rc == 3
        ok &= good
        print(f"{'PASS' if good else 'FAIL'}  exit={rc} expected=3  GitHub API unreachable (connection refused)")
        results.append({"scenario": "GitHub API unreachable", "exit": rc, "expected": 3, "ok": good})
    if a.json:
        a.json.write_text(json.dumps(results, indent=2) + "\n")
    print(f"{'GATE_INDEPENDENT_CHECK_PASS' if ok else 'GATE_INDEPENDENT_CHECK_FAIL'}: "
          f"{sum(r['ok'] for r in results)}/{len(results)} scenarios as expected")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
