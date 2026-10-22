"""PR-7 regression tests: deployment workflows, release-blocker gate, artifact verifier, rollback tooling.

Workflow audits (static, always run):
  deploy-site.yml is workflow_dispatch-only, has no top-level permissions, grants pages/id-token write only to the
  deploy job, uses the protected github-pages environment, never cancels an in-flight deployment, pins every action
  by commit SHA, never persists checkout credentials, checks the confirmation string and the main ref, and runs the
  production release gate for website deployments. site-preview.yml is read-only and never deploys.
Release gate (offline): blockers stay blocked unless BOTH a maintainer record exists AND the automated check passes.
Artifact verifier: a real artifact (MRDB_SITE_ARTIFACT, built by build_site_artifact.py) passes; targeted, resealed
  mutations fail exactly the check that guards them. Skipped when no artifact is available unless
  MRDB_REQUIRE_ARTIFACT=1 (set in CI after the build step), so the tests can never be skipped silently in CI.
Rollback: the committed legacy manifest reproduces the pre-redesign site from git; compare() separates provenance-only
  changes from scientific-data changes; serve_artifact behaves like Pages (301/404).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WFD = REPO / ".github" / "workflows"
SCRIPTS = REPO / "web" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import release_gate as G  # noqa: E402
import serve_artifact as S  # noqa: E402
import site_rollback as R  # noqa: E402
import verify_site_artifact as V  # noqa: E402

CONTRACT = json.loads((REPO / "web/release/release_contract.json").read_text())
LEGACY = CONTRACT["rollback"]["legacy_commit"]
SHA_PIN = re.compile(r"^[\w.-]+/[\w.-]+(/[\w./-]+)?@[0-9a-f]{40}$")


def load_wf(name: str) -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load((WFD / name).read_text())


def on_block(wf: dict) -> dict:
    return wf.get("on", wf.get(True))  # PyYAML parses the key `on` as boolean True


def all_steps(wf: dict):
    for jid, job in wf["jobs"].items():
        for st in job.get("steps", []):
            yield jid, st


# ------------------------------------------------------------------------------------- workflow audits
def test_deploy_workflow_is_manual_dispatch_only():
    on = on_block(load_wf("deploy-site.yml"))
    assert set(on) == {"workflow_dispatch"}
    inputs = on["workflow_dispatch"]["inputs"]
    assert set(inputs) == {"kind", "source_sha", "confirm", "reason"}
    assert inputs["kind"]["options"] == ["website", "legacy-rollback"]
    assert all(inputs[k]["required"] for k in inputs)


def test_deploy_workflow_permissions_are_minimal_and_job_scoped():
    wf = load_wf("deploy-site.yml")
    assert wf["permissions"] == {}
    perms = {jid: job.get("permissions") for jid, job in wf["jobs"].items()}
    assert perms["preflight"] == {"contents": "read", "actions": "read", "pages": "read"}
    assert perms["build"] == {"contents": "read"}
    assert perms["deploy"] == {"pages": "write", "id-token": "write"}
    assert perms["verify-live"] == {"contents": "read"}
    writes = {jid for jid, p in perms.items() if p and "write" in p.values()}
    assert writes == {"deploy"}
    text = (WFD / "deploy-site.yml").read_text()
    assert "secrets." not in text            # only the automatic GITHUB_TOKEN, passed explicitly to the gate
    assert "pull_request_target" not in text and "contents: write" not in text


def test_deploy_job_uses_protected_environment_and_ordered_needs():
    wf = load_wf("deploy-site.yml")
    jobs = wf["jobs"]
    assert jobs["deploy"]["environment"]["name"] == "github-pages"
    assert jobs["build"]["needs"] == "preflight"
    assert set(jobs["deploy"]["needs"]) == {"preflight", "build"}
    assert set(jobs["verify-live"]["needs"]) == {"preflight", "deploy"}
    assert wf["concurrency"] == {"group": "pages-production", "cancel-in-progress": False}
    # only the deploy job publishes, with the official action
    pub = [(jid, st["uses"]) for jid, st in all_steps(wf) if "deploy-pages" in st.get("uses", "")]
    assert [j for j, _ in pub] == ["deploy"]
    for jid, job in jobs.items():
        assert job.get("timeout-minutes"), jid


def test_deploy_preflight_checks_authorisation_and_provenance():
    wf = load_wf("deploy-site.yml")
    pre = "\n".join(st.get("run", "") for st in wf["jobs"]["preflight"]["steps"])
    assert 'test "$EVENT" = "workflow_dispatch"' in pre
    assert 'test "$REF" = "refs/heads/main"' in pre
    assert "^[0-9a-f]{40}$" in pre
    assert 'test "$CONFIRM" = "deploy $KIND $SHA"' in pre
    assert "merge-base --is-ancestor" in pre
    gate = next(st for st in wf["jobs"]["preflight"]["steps"] if "release_gate.py" in st.get("run", ""))
    assert gate["if"] == "inputs.kind == 'website'"
    assert "--mode production" in gate["run"] and "--online" in gate["run"] and '--sha "$SHA"' in gate["run"]
    assert "|| true" not in pre  # no swallowed failures


def test_deploy_build_runs_every_gate_before_upload():
    wf = load_wf("deploy-site.yml")
    steps = wf["jobs"]["build"]["steps"]
    runs = "\n".join(st.get("run", "") for st in steps)
    for cmd in ["fetch_release_db.py", "npm ci", "build_site_artifact.py --production", "python -m pytest",
                "tests/test_web_pr7.py", "pr5a_drilldown_golden.py --check", "pr6_scientific_audit.py",
                "pr6_audit_mutations.py", "schema_to_ts.py --check", "fetch_structure_fixtures.py --check",
                "npx vitest run", "playwright.smoke.config.ts", "verify_site_artifact.py", "--require-clean"]:
        assert cmd in runs, cmd
    pytest_line = next(l for l in runs.splitlines() if "python -m pytest" in l)
    for t in sorted(REPO.glob("tests/test_web_*.py")):
        assert f"tests/{t.name}" in pytest_line, t.name
    names = [st.get("name", st.get("uses", "")) for st in steps]
    up = next(i for i, st in enumerate(steps) if "upload-pages-artifact" in st.get("uses", "") and st.get("if") == "inputs.kind == 'website'")
    for must in ("Smoke tests", "Re-verify", "Scientific integrity gates", "Unit tests"):
        assert any(must in n for n in names[:up]), must


def test_all_actions_are_pinned_and_credentials_not_persisted():
    for name in ("deploy-site.yml", "site-preview.yml", "web-data.yml"):
        wf = load_wf(name)
        for jid, st in all_steps(wf):
            if "uses" in st:
                assert SHA_PIN.match(st["uses"]), f"{name}/{jid}: {st['uses']} is not pinned to a commit SHA"
                if st["uses"].startswith("actions/checkout@"):
                    assert st["with"]["persist-credentials"] is False


def test_preview_workflow_is_read_only_and_never_deploys():
    wf = load_wf("site-preview.yml")
    assert wf["permissions"] == {"contents": "read"}
    on = on_block(wf)
    assert set(on) == {"pull_request", "workflow_dispatch"} and "push" not in on
    text = (WFD / "site-preview.yml").read_text()
    for bad in ("deploy-pages", "upload-pages-artifact", "pages: write", "id-token", "environment:", "secrets.", "--production", "--mode production"):
        assert bad not in text, bad
    for job in wf["jobs"].values():
        assert not job.get("permissions") or set(job["permissions"].values()) <= {"read", "none"}
    runs = "\n".join(st.get("run", "") for _, st in all_steps(wf))
    assert "release_gate.py --mode report" in runs and "playwright.smoke.config.ts" in runs and "build_site_artifact.py" in runs


def test_no_workflow_deploys_automatically():
    for p in sorted(WFD.glob("*.yml")):
        wf = load_wf(p.name)
        text = p.read_text()
        if "deploy-pages" in text or "pages: write" in text:
            assert p.name == "deploy-site.yml", p.name
            assert set(on_block(wf)) == {"workflow_dispatch"}


def test_actionlint_if_available():
    exe = os.environ.get("ACTIONLINT") or shutil.which("actionlint") or ("/workspace/bin/actionlint" if Path("/workspace/bin/actionlint").exists() else None)
    if not exe:
        pytest.skip("actionlint not installed (run in the local PR-7 validation; see PR7_VALIDATION_REPORT.md)")
    r = subprocess.run([exe, "-no-color", *map(str, sorted(WFD.glob("*.yml")))], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_web_data_runs_artifact_tests_after_build():
    wf = load_wf("web-data.yml")
    runs = "\n".join(st.get("run", "") for _, st in all_steps(wf))
    assert "build_site_artifact.py" in runs and "MRDB_REQUIRE_ARTIFACT" in (WFD / "web-data.yml").read_text()
    assert runs.index("npm run build") < runs.index("build_site_artifact.py")


# --------------------------------------------------------------------------------------- release gate
# PR-7a: every gate test is independent of the CURRENT state of release_blockers.json and of the repository
# metadata. The real checklist is only validated structurally; positive and negative production paths run on
# synthetic repositories with a synthetic, offline GitHub/doi.org API, so the suite keeps passing (and keeps
# guarding the gate) after the maintainers resolve the blockers.
GATE_SHA = "a" * 40
REC = {"decided_by": "CongjianL", "decided_at": "2026-10-01",
       "reference": "https://github.com/CongjianL/MicroRhodoDB/issues/1"}


def _b(i, status="open", resolution=None):
    return {"id": i, "title": i, "category": "t", "blocks": ["production"], "status": status, "resolution": resolution,
            "evidence": "synthetic", "required_decision": "synthetic"}


def _fake(monkeypatch, tmp_path, blockers, checks):
    p = tmp_path / "blockers.json"
    p.write_text(json.dumps({"version": 1, "blockers": blockers}))
    monkeypatch.setattr(G, "CHECKS", checks)
    monkeypatch.setattr(G, "MANDATORY_BLOCKERS", ())
    return G.evaluate(REPO, blockers_path=p)


def test_gate_requires_record_and_passing_check(monkeypatch, tmp_path):
    checks = {"A": lambda r, c: (True, "ok"), "B": lambda r, c: (False, "fails"), "C": lambda r, c: (True, "ok"),
              "E": lambda r, c: (None, "offline"), "G": lambda r, c: ("yes", "truthy but not True")}
    res = _fake(monkeypatch, tmp_path, [_b("A", "resolved", REC), _b("B", "resolved", REC), _b("C"),
                                        _b("D", "resolved", REC), _b("E", "resolved", REC),
                                        _b("F", "resolved", {**REC, "reference": ""}), _b("G", "resolved", REC)], checks)
    st = {b["id"]: (b["resolved"], b["state"]) for b in res["blockers"]}
    assert st["A"] == (True, "resolved")
    assert st["B"] == (False, "claimed resolved but the automated check does not pass")
    assert st["C"] == (False, "automated check passes but no maintainer resolution record")
    assert st["D"] == (True, "resolved")          # manual-only blocker with a complete record
    assert st["E"][0] is False                    # undecidable check (offline) never counts as passing
    assert st["F"][0] is False and st["F"][1].startswith("invalid resolution record")
    assert st["G"][0] is False                    # only exactly True passes
    assert res["unresolved"] == ["B", "C", "E", "F", "G"]


# ---- synthetic repository + synthetic online API for end-to-end production-path tests
DB_ROW = "| `releases/v1.6.0/db/microrhododb_v1.6.0.sqlite` | 33464320 | `" + "3" * 64 + "` |\n"


def _meta_repo(tmp_path: Path, **over) -> Path:
    r = tmp_path / "repo"
    (r / "web").mkdir(parents=True)
    (r / "tools").mkdir()
    (r / "releases/v1.6.0").mkdir(parents=True)
    (r / "docs/website").mkdir(parents=True)
    files = {
        "LICENSE": "The content is licensed under the Creative Commons Attribution 4.0 International (CC BY 4.0).\n"
                   "Source code under src/ is released under the MIT License.\n",
        "README.md": "## Licence\nData: CC BY 4.0. Code: MIT.\n",
        "CITATION.cff": "cff-version: 1.2.0\nversion: 1.6.0\ndate-released: 2026-10-10\nlicense: CC-BY-4.0\n",
        ".zenodo.json": json.dumps({"license": "CC-BY-4.0", "publication_date": "2026-10-10"}),
        "CHANGELOG.md": "## [1.6.0] - 2026-10-10\n",
        "releases/v1.6.0/RELEASE_NOTES_v1.6.0.md": "**Release date:** 2026-10-10\n",
        "web/package.json": json.dumps({"license": "MIT", "version": "2.0.0"}),
        "tools/export_web_data.py": 'WEBSITE_VERSION = "2.0.0"\n',
        "MAINTENANCE.md": "- Contact: rhodopsin-db@example.org\n",
        "BINARIES.md": "",
    }
    files.update(over)
    for k, v in files.items():
        (r / k).write_text(v)
    return r


def _release_ready_repo(tmp_path: Path, blockers=None, **over) -> Path:
    """Synthetic repository in which every mandatory blocker is correctly resolved (all metadata consistent)."""
    files = {"CITATION.cff": "cff-version: 1.2.0\nversion: 1.6.0\ndate-released: 2026-10-10\nlicense: CC-BY-4.0\n"
                             "doi: 10.5281/zenodo.0000001\n",
             "BINARIES.md": "Archive `MicroRhodoDB_v1.6.0.tar.gz` (Zenodo).\n\n" + DB_ROW,
             "MAINTENANCE.md": "- Contact: GitHub issues\n- Archive: Zenodo\n"}
    files.update(over)
    r = _meta_repo(tmp_path, **files)
    if blockers is None:
        blockers = [_b(i, "resolved", dict(REC)) for i in G.MANDATORY_BLOCKERS]
    (r / G.BLOCKERS).write_text(json.dumps({"version": 1, "blockers": blockers}))
    return r


def _good_api():
    return {
        "/releases/tags/v1.6.0": {"published_at": "2026-10-10T08:00:00Z", "assets": [
            {"name": "microrhododb_v1.6.0.sqlite", "size": 33464320},
            {"name": "MicroRhodoDB_v1.6.0.tar.gz", "size": 10}, {"name": "MicroRhodoDB_v1.6.0.tar.gz.sha256", "size": 92}]},
        "/environments/github-pages": {
            "protection_rules": [{"type": "required_reviewers", "prevent_self_review": False,
                                  "reviewers": [{"type": "User", "reviewer": {"login": "CongjianL"}}]},
                                 {"type": "branch_policy"}],
            "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True},
            "can_admins_bypass": False},
        "/environments/github-pages/deployment-branch-policies": {"branch_policies": [{"name": "main", "type": "branch"}]},
        "/pages": {"build_type": "workflow", "source": None},
        "/actions/runs": {"workflow_runs": [{"id": 1, "name": "web-data", "path": ".github/workflows/web-data.yml",
                                             "head_sha": GATE_SHA, "status": "completed", "conclusion": "success"}]},
        "doi": {"responseCode": 1},
    }


def _install_api(monkeypatch, api: dict):
    prefix = f"{G.GH_API}/repos/{G.OWNER_REPO}"
    calls = []

    def fake(req):
        url = req.full_url
        calls.append(url)
        key = "doi" if url.startswith("https://doi.org/") else url[len(prefix):].split("?")[0] if url.startswith(prefix) else None
        if key not in api:
            raise urllib.error.URLError(f"synthetic API: no route for {url}")
        v = api[key]
        if isinstance(v, BaseException):
            raise v
        return json.loads(json.dumps(v))
    monkeypatch.setattr(G, "_open_json", fake)
    monkeypatch.setattr(G.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("real network used")))
    return calls


def _prod(repo: Path, *extra) -> int:
    return G.main(["--mode", "production", "--online", "--sha", GATE_SHA, "--repo", str(repo), *extra])


def test_gate_positive_path_fully_resolved_and_authorised_allows_production(monkeypatch, tmp_path, capsys):
    repo = _release_ready_repo(tmp_path)
    calls = _install_api(monkeypatch, _good_api())
    res = G.evaluate(repo, online=True, sha=GATE_SHA)
    assert res["checklist_problems"] == [] and res["unresolved"] == [] and res["production_allowed"] is True
    assert {b["id"] for b in res["blockers"] if b["resolved"]} == set(G.MANDATORY_BLOCKERS)
    assert {b["id"]: b["check"] for b in res["blockers"]} == {**{i: True for i in G.CHECKS}, "ACC-1": None}
    assert _prod(repo, "--json", str(tmp_path / "gate.json")) == 0
    assert json.loads((tmp_path / "gate.json").read_text())["production_allowed"] is True
    assert "no unresolved production blockers" in capsys.readouterr().out
    assert any(u.endswith("/pages") for u in calls) and any("/actions/runs?head_sha=" + GATE_SHA in u for u in calls)


@pytest.mark.parametrize("bid", ["MD-1", "MD-2", "MD-3", "MD-4", "MD-5", "RA-1", "RA-2", "OPS-1", "OPS-2", "CI-1", "VER-1", "ACC-1"])
def test_gate_missing_maintainer_decision_blocks(monkeypatch, tmp_path, bid):
    bl = [_b(i, "resolved", dict(REC)) if i != bid else _b(i) for i in G.MANDATORY_BLOCKERS]
    repo = _release_ready_repo(tmp_path, blockers=bl)
    _install_api(monkeypatch, _good_api())
    assert _prod(repo) == 3
    res = G.evaluate(repo, online=True, sha=GATE_SHA)
    assert res["unresolved"] == [bid] and res["production_allowed"] is False


INVALID_RESOLUTIONS = {
    "status-not-exactly-resolved": ("Resolved", REC),
    "status-waived": ("waived", REC),
    "no-record": ("resolved", None),
    "record-not-a-dict": ("resolved", "approved"),
    "missing-decided_by": ("resolved", {**REC, "decided_by": ""}),
    "template-decided_by": ("resolved", {**REC, "decided_by": "<github login>"}),
    "decided_by-not-a-login": ("resolved", {**REC, "decided_by": "the maintainers"}),
    "template-date": ("resolved", {**REC, "decided_at": "YYYY-MM-DD"}),
    "impossible-date": ("resolved", {**REC, "decided_at": "2026-02-30"}),
    "future-date": ("resolved", {**REC, "decided_at": "2999-01-01"}),
    "missing-reference": ("resolved", {**REC, "reference": "   "}),
    "placeholder-reference": ("resolved", {**REC, "reference": "<<PLACEHOLDER: issue URL>>"}),
    "http-reference": ("resolved", {**REC, "reference": "http://github.com/CongjianL/MicroRhodoDB/issues/1"}),
    "not-a-url": ("resolved", {**REC, "reference": "approved in a call"}),
    "reserved-host": ("resolved", {**REC, "reference": "https://example.invalid/issue/1"}),
    "example-host": ("resolved", {**REC, "reference": "https://www.example.org/x"}),
}


@pytest.mark.parametrize("case", sorted(INVALID_RESOLUTIONS))
@pytest.mark.parametrize("bid", ["MD-4", "OPS-1", "ACC-1"])  # automated check / online check / manual-only
def test_gate_invalid_resolution_blocks(monkeypatch, tmp_path, case, bid):
    status, rec = INVALID_RESOLUTIONS[case]
    bl = [_b(i, "resolved", dict(REC)) if i != bid else _b(i, status, rec) for i in G.MANDATORY_BLOCKERS]
    repo = _release_ready_repo(tmp_path, blockers=bl)
    _install_api(monkeypatch, _good_api())
    assert _prod(repo) == 3
    res = G.evaluate(repo, online=True, sha=GATE_SHA)
    assert res["unresolved"] == [bid]
    entry = next(b for b in res["blockers"] if b["id"] == bid)
    assert entry["resolved"] is False and entry["has_resolution_record"] is False


def _api_with(**changes):
    api = _good_api()
    for k, v in changes.items():
        api[k.replace("__", "/").replace("_DASH_", "-")] = v
    return api


FAILED_CHECKS = {
    # id: (file overrides, api overrides)
    "MD-1": ({"README.md": "Data: CC BY 4.0. Code: Apache-2.0.\n"}, {}),
    "MD-2": ({"CITATION.cff": "version: 1.6.0\ndate-released: 2026-10-09\nlicense: CC-BY-4.0\ndoi: 10.5281/zenodo.0000001\n"}, {}),
    "MD-2/github-release-date": ({}, {"/releases/tags/v1.6.0": {**_good_api()["/releases/tags/v1.6.0"], "published_at": "2026-10-11T00:00:00Z"}}),
    "MD-4": ({"MAINTENANCE.md": "- Contact: <<PLACEHOLDER: e-mail>>\n- Archive: Zenodo\n"}, {}),
    "MD-5": ({"MAINTENANCE.md": "- Contact: GitHub issues\n- Archive: Zenodo `<<PLACEHOLDER: hosting term>>`\n"}, {}),
    "RA-1": ({}, {"/releases/tags/v1.6.0": {"published_at": "2026-10-10T08:00:00Z", "assets": [{"name": "microrhododb_v1.6.0.sqlite", "size": 33464320}]}}),
    "RA-1/size-mismatch": ({}, {"/releases/tags/v1.6.0": {**_good_api()["/releases/tags/v1.6.0"], "assets": [
        {"name": "microrhododb_v1.6.0.sqlite", "size": 1}, {"name": "MicroRhodoDB_v1.6.0.tar.gz", "size": 10},
        {"name": "MicroRhodoDB_v1.6.0.tar.gz.sha256", "size": 92}]}}),
    "RA-2": ({}, {"doi": {"responseCode": 100}}),
    "OPS-1": ({}, {"/pages": {"build_type": "legacy", "source": {"branch": "main", "path": "/"}}}),
    "OPS-1/missing-build_type": ({}, {"/pages": {}}),
    "OPS-2": ({}, {"/environments/github-pages": {**_good_api()["/environments/github-pages"], "protection_rules": [{"type": "branch_policy"}]}}),
    "OPS-2/reviewer-rule-without-reviewers": ({}, {"/environments/github-pages": {**_good_api()["/environments/github-pages"],
                                                   "protection_rules": [{"type": "required_reviewers", "reviewers": []}]}}),
    "OPS-2/extra-branch": ({}, {"/environments/github-pages/deployment-branch-policies": {"branch_policies": [
        {"name": "main", "type": "branch"}, {"name": "website/pr-1-exporter", "type": "branch"}]}}),
    "OPS-2/tag-named-main": ({}, {"/environments/github-pages/deployment-branch-policies": {"branch_policies": [{"name": "main", "type": "tag"}]}}),
    "OPS-2/policy-type-missing": ({}, {"/environments/github-pages/deployment-branch-policies": {"branch_policies": [{"name": "main"}]}}),
    "OPS-2/policy-list-incomplete": ({}, {"/environments/github-pages/deployment-branch-policies": {
        "total_count": 2, "branch_policies": [{"name": "main", "type": "branch"}]}}),
    "OPS-2/all-branches": ({}, {"/environments/github-pages": {**_good_api()["/environments/github-pages"], "deployment_branch_policy": None}}),
    "OPS-2/protected-branches": ({}, {"/environments/github-pages": {**_good_api()["/environments/github-pages"],
                                      "deployment_branch_policy": {"protected_branches": True, "custom_branch_policies": False}}}),
    "CI-1": ({}, {"/actions/runs": {"workflow_runs": [{**_good_api()["/actions/runs"]["workflow_runs"][0], "conclusion": "failure"}]}}),
    "CI-1/impostor-workflow-name": ({}, {"/actions/runs": {"workflow_runs": [{**_good_api()["/actions/runs"]["workflow_runs"][0],
                                                                              "path": ".github/workflows/fake.yml"}]}}),
    "CI-1/other-commit": ({}, {"/actions/runs": {"workflow_runs": [{**_good_api()["/actions/runs"]["workflow_runs"][0], "head_sha": "b" * 40}]}}),
    "CI-1/no-runs": ({}, {"/actions/runs": {"workflow_runs": []}}),
    "VER-1": ({"web/package.json": json.dumps({"license": "MIT", "version": "2.0.0-rc1"})}, {}),
}


@pytest.mark.parametrize("case", sorted(FAILED_CHECKS))
def test_gate_failed_automated_check_blocks_despite_valid_record(monkeypatch, tmp_path, case):
    files, api_over = FAILED_CHECKS[case]
    bid = case.split("/")[0]
    repo = _release_ready_repo(tmp_path, **files)
    api = _good_api()
    api.update(api_over)
    _install_api(monkeypatch, api)
    assert _prod(repo) == 3
    res = G.evaluate(repo, online=True, sha=GATE_SHA)
    entry = next(b for b in res["blockers"] if b["id"] == bid)
    assert bid in res["unresolved"] and entry["has_resolution_record"] is True and entry["check"] is False, entry


API_FAILURES = [
    urllib.error.URLError("connection refused"),
    urllib.error.HTTPError("https://api.github.com/x", 403, "rate limited", {}, None),
    urllib.error.HTTPError("https://api.github.com/x", 404, "Not Found", {}, None),
    ConnectionResetError("reset by peer"),
    TimeoutError("timed out"),
    ValueError("invalid JSON"),
]


@pytest.mark.parametrize("route,bids", [("/releases/tags/v1.6.0", {"RA-1", "MD-2"}), ("/pages", {"OPS-1"}),
                                        ("/environments/github-pages", {"OPS-2"}),
                                        ("/environments/github-pages/deployment-branch-policies", {"OPS-2"}),
                                        ("/actions/runs", {"CI-1"}), ("doi", {"MD-3", "RA-2"})])
@pytest.mark.parametrize("err", API_FAILURES, ids=lambda e: type(e).__name__ + str(getattr(e, "code", "")))
def test_gate_api_failure_is_fail_closed(monkeypatch, tmp_path, route, bids, err):
    repo = _release_ready_repo(tmp_path)
    api = _good_api()
    api[route] = err
    _install_api(monkeypatch, api)
    assert _prod(repo) == 3
    res = G.evaluate(repo, online=True, sha=GATE_SHA)
    assert set(res["unresolved"]) == bids
    assert all(b["check"] is None for b in res["blockers"] if b["id"] in bids)


@pytest.mark.parametrize("route", ["/releases/tags/v1.6.0", "/pages", "/environments/github-pages",
                                   "/environments/github-pages/deployment-branch-policies", "/actions/runs"])
@pytest.mark.parametrize("payload", [[], "ok", {"unexpected": True}], ids=["list", "str", "empty-shape"])
def test_gate_malformed_api_response_is_fail_closed(monkeypatch, tmp_path, route, payload):
    repo = _release_ready_repo(tmp_path)
    api = _good_api()
    api[route] = payload
    _install_api(monkeypatch, api)
    assert _prod(repo) == 3


def test_gate_unexpected_exception_in_a_check_blocks(monkeypatch, tmp_path):
    repo = _release_ready_repo(tmp_path)
    _install_api(monkeypatch, _good_api())

    def boom(r, c):
        raise RuntimeError("bug")
    monkeypatch.setitem(G.CHECKS, "VER-1", boom)
    assert _prod(repo) == 3
    e = next(b for b in G.evaluate(repo, online=True, sha=GATE_SHA)["blockers"] if b["id"] == "VER-1")
    assert e["check"] is None and "RuntimeError" in e["check_detail"]


def _tamper(kind):
    bl = [_b(i, "resolved", dict(REC)) for i in G.MANDATORY_BLOCKERS]
    if kind == "delete-mandatory":
        bl = [b for b in bl if b["id"] != "ACC-1"]
    elif kind == "duplicate":
        bl.append(_b("ACC-1"))
    elif kind == "duplicate-both-resolved":
        bl.append(_b("ACC-1", "resolved", dict(REC)))
    elif kind == "rescope-blocks-empty":
        bl[0]["blocks"] = []
    elif kind == "rescope-preview-only":
        bl[0]["blocks"] = ["preview"]
    elif kind == "rename-id":
        bl[0]["id"] = "MD-1-waived"
    return bl


@pytest.mark.parametrize("kind", ["delete-mandatory", "duplicate", "duplicate-both-resolved", "rename-id",
                                  "rescope-blocks-empty", "rescope-preview-only"])
def test_gate_checklist_tampering_cannot_remove_a_blocker(monkeypatch, tmp_path, kind):
    repo = _release_ready_repo(tmp_path, blockers=_tamper(kind))
    _install_api(monkeypatch, _good_api())
    res = G.evaluate(repo, online=True, sha=GATE_SHA)
    assert res["production_allowed"] is False and res["checklist_problems"]
    assert _prod(repo) == 3


@pytest.mark.parametrize("content", ["", "{not json", json.dumps({"blockers": "none"}), json.dumps([])])
def test_gate_unreadable_checklist_blocks(monkeypatch, tmp_path, content):
    repo = _release_ready_repo(tmp_path)
    (repo / G.BLOCKERS).write_text(content)
    _install_api(monkeypatch, _good_api())
    assert _prod(repo) == 3
    assert set(G.evaluate(repo, online=True, sha=GATE_SHA)["unresolved"]) == set(G.MANDATORY_BLOCKERS)


def test_gate_production_requires_online_and_full_sha(monkeypatch, tmp_path):
    repo = _release_ready_repo(tmp_path)
    _install_api(monkeypatch, _good_api())
    assert G.main(["--mode", "production", "--repo", str(repo)]) == 2
    assert G.main(["--mode", "production", "--online", "--repo", str(repo)]) == 2
    assert G.main(["--mode", "production", "--sha", GATE_SHA, "--repo", str(repo)]) == 2
    assert G.main(["--mode", "production", "--online", "--sha", "abc1234", "--repo", str(repo)]) == 2
    assert _prod(repo) == 0  # the same repository passes once the prerequisites are given


def test_offline_evaluation_can_never_allow_production(tmp_path):
    """Even with every blocker of the REAL checklist marked resolved, the online-only checks stay undecided offline."""
    data = json.loads((REPO / G.BLOCKERS).read_text())
    for b in data["blockers"]:
        b["status"], b["resolution"] = "resolved", dict(REC)
    p = tmp_path / "all_resolved.json"
    p.write_text(json.dumps(data))
    res = G.evaluate(REPO, online=False, blockers_path=p)
    assert res["production_allowed"] is False
    assert {"RA-1", "OPS-1", "OPS-2", "CI-1"} <= set(res["unresolved"])


@pytest.mark.parametrize("resolved", [True, False])
def test_report_mode_never_blocks(monkeypatch, tmp_path, resolved):
    bl = None if resolved else [_b(i) for i in G.MANDATORY_BLOCKERS]
    repo = _release_ready_repo(tmp_path, blockers=bl)
    _install_api(monkeypatch, _good_api())
    assert G.main(["--mode", "report", "--repo", str(repo)]) == 0
    assert G.main(["--mode", "report", "--online", "--sha", GATE_SHA, "--repo", str(repo)]) == 0
    assert G.main(["--mode", "report"]) == 0  # the real repository, whatever its current state


def test_real_checklist_is_well_formed_whatever_its_state():
    data = json.loads((REPO / G.BLOCKERS).read_text())
    assert G.checklist_problems(data) == []
    ids = [b["id"] for b in data["blockers"]]
    assert set(G.MANDATORY_BLOCKERS) <= set(ids) and len(ids) == len(set(ids))
    for b in data["blockers"]:
        assert b["status"] in G.VALID_STATUS and b["blocks"] == ["production"], b["id"]
        assert b["evidence"] and b["required_decision"] and b["title"], b["id"]
        if b["status"] == "open":
            assert b["resolution"] is None, b["id"]
        else:
            assert G.resolution_problems(b) == [], (b["id"], G.resolution_problems(b))
    assert set(data["resolution_template"]) >= set(G.RESOLUTION_FIELDS)


def test_real_repository_checks_are_well_formed_whatever_their_result():
    ctx = {"online": False, "blocker": {}, "release": None}
    for bid, fn in G.CHECKS.items():
        ok, detail = fn(REPO, {**ctx, "blocker": {"id": bid}})
        assert ok in (True, False, None) and isinstance(detail, str) and detail, bid
    for bid in ("RA-1", "OPS-1", "OPS-2", "CI-1"):  # online-only checks are undecided offline
        assert G.CHECKS[bid](REPO, ctx)[0] is None, bid


def test_metadata_checks_on_synthetic_repositories(tmp_path):
    good = _meta_repo(tmp_path)
    ctx = {"online": False, "blocker": {}}
    assert G.check_md1_licence(good, ctx)[0] is True
    assert G.check_md2_dates(good, ctx)[0] is True
    assert G.check_md4_contact(good, ctx)[0] is True
    assert G.check_md5_maintenance(good, ctx)[0] is True
    assert G.check_ver1_version(good, ctx)[0] is True
    assert G.check_md3_doi(good, ctx)[0] is False
    assert G.check_md3_doi(good, {**ctx, "blocker": {"resolution": {"alternative_citation_policy": "cite tag + URL"}}})[0] is True
    assert G.check_md3_doi(good, {**ctx, "blocker": {"resolution": {"alternative_citation_policy": "<<PLACEHOLDER>>"}}})[0] is False
    assert G.check_md2_dates(good, {**ctx, "online": True, "release": None, "release_error": "HTTP 403"})[0] is None
    bad = _meta_repo(tmp_path / "b", **{"README.md": "Data: CC BY 4.0. Code: Apache-2.0.\n",
                                        "CITATION.cff": "version: 1.6.0\ndate-released: 2026-10-09\nlicense: CC-BY-4.0\n",
                                        "MAINTENANCE.md": "- Contact: <<PLACEHOLDER: e-mail>>\n",
                                        "web/package.json": json.dumps({"license": "MIT", "version": "2.0.0-pr7"})})
    assert G.check_md1_licence(bad, ctx)[0] is False
    assert G.check_md2_dates(bad, ctx)[0] is False
    assert G.check_md4_contact(bad, ctx)[0] is False
    assert G.check_md5_maintenance(bad, ctx)[0] is False
    assert G.check_ver1_version(bad, ctx)[0] is False
    assert G.check_md1_licence(_meta_repo(tmp_path / "c", **{"README.md": "no statement\n"}), ctx)[0] is False
    capital = _meta_repo(tmp_path / "d", **{"LICENSE": "Licensed under the Creative Commons Attribution 4.0 International "
                                                       "(CC BY 4.0).\nSource code is released under the MIT License.\n"})
    assert G.check_md1_licence(capital, ctx)[0] is True  # sentence case must not block a correct resolution


def test_binaries_assets_are_compared_with_the_release(tmp_path):
    repo = _release_ready_repo(tmp_path)
    ctx = {"online": True, "blocker": {}}
    assert G.check_ra1_release_assets(repo, {**ctx, "release": _good_api()["/releases/tags/v1.6.0"]})[0] is True
    ok, detail = G.check_ra1_release_assets(repo, {**ctx, "release": {"assets": [{"name": "microrhododb_v1.6.0.sqlite", "size": 33464320}]}})
    assert ok is False and "MicroRhodoDB_v1.6.0.tar.gz" in detail
    assert G.check_ra1_release_assets(repo, {**ctx, "release": None, "release_error": "HTTP 500"})[0] is None
    assert G.check_ra1_release_assets(repo, {"online": False, "release": None})[0] is None
    empty = _release_ready_repo(tmp_path / "e", **{"BINARIES.md": ""})
    assert G.check_ra1_release_assets(empty, {**ctx, "release": {"assets": []}})[0] is False


# ---------------------------------------------------------------------------------- contract / exporter
def test_release_contract_matches_frozen_inputs():
    assert CONTRACT["dataset_release"] == "1.6.0" and CONTRACT["schema_version"] == "1.4.0"
    assert CONTRACT["base_path"] == "/MicroRhodoDB/site/"
    assert CONTRACT["pages_url"] == "https://congjianl.github.io/MicroRhodoDB/site/"
    assert CONTRACT["source_db"] == {"path": "releases/v1.6.0/db/microrhododb_v1.6.0.sqlite",
                                     "sha256": "379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f",
                                     "bytes": 33464320}
    binaries = (REPO / "BINARIES.md").read_text()
    assert CONTRACT["source_db"]["sha256"] in binaries
    tree = CONTRACT["reference_tree"]
    assert V.sha256(REPO / tree["path"]) == tree["sha256"]
    assert tree["sha256"] in (REPO / "refpkg/MR_RT_003/SHA256SUMS").read_text()
    assert re.fullmatch(r"[0-9a-f]{40}", LEGACY)
    vite = (REPO / "web/vite.config.ts").read_text()
    assert f'base: "{CONTRACT["base_path"]}"' in vite


def test_website_version_is_single_sourced():
    pkg = json.loads((REPO / "web/package.json").read_text())["version"]
    m = re.search(r'^WEBSITE_VERSION = "([^"]+)"', (REPO / "tools/export_web_data.py").read_text(), re.M)
    assert m and m.group(1) == pkg
    man = REPO / "web/public/data/v1.6.0/manifest.json"
    if man.exists():
        assert json.loads(man.read_text())["website_version"] == pkg


def test_repository_documents_link_to_the_export_commit():
    d = REPO / "web/public/data/v1.6.0"
    if not (d / "downloads.json").exists():
        pytest.skip("export not present")
    dl = json.loads((d / "downloads.json").read_text())
    em = json.loads((d / "export_manifest.json").read_text())
    commit = em["exporter_git_commit"]
    assert re.fullmatch(r"[0-9a-f]{40}", commit)
    for f in dl["repository_documents"]:
        assert f["url"] == f"{CONTRACT['repository_url']}/blob/{commit}/{f['path']}"
        if not em["exporter_git_dirty"]:
            blob = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{f['path']}"], capture_output=True, check=True).stdout
            assert V.hashlib.sha256(blob).hexdigest() == f["sha256"], f["path"]


# ----------------------------------------------------------------------------------- artifact verifier
def _artifact() -> Path | None:
    p = os.environ.get("MRDB_SITE_ARTIFACT")
    if p and (Path(p) / "SHA256SUMS").is_file():
        return Path(p)
    if os.environ.get("MRDB_REQUIRE_ARTIFACT") == "1":
        pytest.fail("MRDB_REQUIRE_ARTIFACT=1 but MRDB_SITE_ARTIFACT does not point to a built artifact")
    return None


@pytest.fixture(scope="module")
def artifact():
    a = _artifact()
    if a is None:
        pytest.skip("no built artifact (set MRDB_SITE_ARTIFACT=<dir from build_site_artifact.py>)")
    return a


def _reseal(art: Path) -> None:
    """Recompute SHA256SUMS and BUILD_INFO digests so that only the targeted check can detect a mutation."""
    sums = {p.relative_to(art).as_posix(): V.sha256(p) for p in sorted(art.rglob("*")) if p.is_file() and p.name != "SHA256SUMS"
            and p.relative_to(art).as_posix() != "site/BUILD_INFO.json"}
    bi_p = art / "site/BUILD_INFO.json"
    bi = json.loads(bi_p.read_text())
    bi["content_sha256"] = V.content_digest([f"{h}  {r}" for r, h in sums.items()])
    bi["n_files"] = len(sums)
    bi_p.write_text(json.dumps(bi, indent=2, sort_keys=True) + "\n")
    sums["site/BUILD_INFO.json"] = V.sha256(bi_p)
    (art / "SHA256SUMS").write_text("".join(f"{h}  {r}\n" for r, h in sorted(sums.items())))


def _failed(art: Path) -> set[str]:
    commit = json.loads((art / "site/BUILD_INFO.json").read_text())["source_commit"]
    rep = V.verify(art, REPO, None)
    return {c["id"] for c in rep.checks if not c["ok"]}, commit


def test_real_artifact_passes_every_check(artifact):
    bad, _ = _failed(artifact)
    assert bad == set()


def _first(art: Path, pattern: str) -> Path:
    return next(p for p in sorted(art.rglob(pattern)) if p.is_file())


MUTATIONS = {
    "V1": lambda a: (a / "site/.env").write_text("X=1\n"),
    "V3": lambda a: (lambda p, d: p.write_text(json.dumps({**d, "dataset_release": "1.5.0"}, indent=2, sort_keys=True)))(
        a / "site/BUILD_INFO.json", json.loads((a / "site/BUILD_INFO.json").read_text())),
    "V4": lambda a: _first(a, "site/assets/*.css").unlink(),
    "V5": lambda a: (a / "site/data/v1.6.0/summary.json").write_text(
        (a / "site/data/v1.6.0/summary.json").read_text().replace("5466", "5467", 1)),
    "V6": lambda a: (a / "site/data/v1.6.0/vocabulary.json").write_text("{\"not\": \"the schema\"}"),
    "V7": lambda a: (a / CONTRACT["reference_tree"]["artifact_path"]).write_bytes(
        (a / CONTRACT["reference_tree"]["artifact_path"]).read_bytes().replace(b":", b";", 1)),
    "V8": lambda a: (a / "site/data/v1.6.0/downloads.json").write_text(
        re.sub(r"/blob/[0-9a-f]{40}/", "/blob/v1.6.0/", (a / "site/data/v1.6.0/downloads.json").read_text())),
    "V9": lambda a: _first(a, "site/assets/index-*.js").write_text(_first(a, "site/assets/index-*.js").read_text() + "\n//http://localhost:5173/\n"),
}


@pytest.mark.parametrize("check", sorted(MUTATIONS))
def test_targeted_mutation_is_caught_by_its_check(artifact, tmp_path, check):
    art = tmp_path / "art"
    shutil.copytree(artifact, art)
    MUTATIONS[check](art)
    _reseal(art)
    bad, _ = _failed(art)
    assert check in bad, f"{check} did not detect its mutation (failed: {sorted(bad)})"


def test_unsealed_tampering_is_caught_by_sha256sums(artifact, tmp_path):
    art = tmp_path / "art"
    shutil.copytree(artifact, art)
    p = art / "site/data/v1.6.0/clades.json"
    p.write_bytes(p.read_bytes() + b" ")
    bad, _ = _failed(art)
    assert {"V2", "V5"} <= bad


def test_build_info_records_provenance(artifact):
    bi = json.loads((artifact / "site/BUILD_INFO.json").read_text())
    em = json.loads((artifact / bi["export_manifest"]["path"]).read_text())
    assert bi["export_manifest"]["exporter_git_commit"] == em["exporter_git_commit"] == bi["source_commit"]
    assert bi["source_db"] == CONTRACT["source_db"]
    assert bi["dataset_release"] == "1.6.0" and bi["base_path"] == CONTRACT["base_path"]
    assert bi["website_version"] == json.loads((REPO / "web/package.json").read_text())["version"]
    js = "".join(p.read_text(errors="replace") for p in (artifact / "site/assets").glob("index-*.js"))
    assert bi["source_commit"] in js  # footer build stamp is the same commit


def test_artifact_compare_classifies_changes(artifact, tmp_path):
    b = tmp_path / "b"
    shutil.copytree(artifact, b)
    assert R.compare(artifact, b)["identical"] is True
    em = b / "site/data/v1.6.0/export_manifest.json"
    d = json.loads(em.read_text())
    d["exporter_git_commit"] = "0" * 40
    em.write_text(json.dumps(d))
    _reseal(b)
    res = R.compare(artifact, b)
    assert res["provenance_only_data_changes"] == ["site/data/v1.6.0/export_manifest.json"]
    assert res["unexpected_scientific_change"] is False
    s = b / "site/data/v1.6.0/summary.json"
    s.write_text(s.read_text().replace("5466", "5467", 1))
    _reseal(b)
    res = R.compare(artifact, b)
    assert "site/data/v1.6.0/summary.json" in res["scientific_data_changes"] and res["unexpected_scientific_change"] is True
    dl = b / "site/data/v1.6.0/downloads.json"
    dd = json.loads(dl.read_text())
    dd["release_files"][0]["sha256"] = "f" * 64
    dl.write_text(json.dumps(dd))
    _reseal(b)
    assert "site/data/v1.6.0/downloads.json" in R.compare(artifact, b)["scientific_data_changes"]


# --------------------------------------------------------------------------------------------- rollback
def test_compare_handles_directories_without_sha256sums(tmp_path):
    """A legacy-build output has no SHA256SUMS/BUILD_INFO: compare hashes files itself and does not classify."""
    a, b = tmp_path / "a", tmp_path / "b"
    for d, txt in ((a, "old"), (b, "new")):
        (d / "site/data").mkdir(parents=True)
        (d / "index.html").write_text("<meta http-equiv=refresh content='0; url=site/'>")
        (d / "site/data/x.json").write_text(txt)
    res = R.compare(a, b)
    assert res["changed"] == ["site/data/x.json"] and res["same_dataset_release"] is None
    assert res["unexpected_scientific_change"] is False
    assert R.compare(a, a)["identical"] is True


def test_legacy_manifest_reproduces_the_pre_redesign_site(tmp_path):
    man = R.manifest_path(LEGACY)
    assert man.is_file(), "legacy manifest must be committed with PR-7"
    sums = R.read_sums(man)
    for need in ("index.html", "site/index.html", "site/app.js", "site/data.js", "site/style.css", ".nojekyll"):
        assert need in sums
    res = R.legacy_build(LEGACY, tmp_path / "legacy")
    assert res["files"] == len(sums)
    assert (tmp_path / "legacy/site/data.js").stat().st_size == 4_350_576
    assert (tmp_path / "legacy/index.html").read_bytes() == subprocess.run(
        ["git", "-C", str(REPO), "show", f"{LEGACY}:index.html"], capture_output=True, check=True).stdout


def test_legacy_build_rejects_a_tampered_manifest(tmp_path, monkeypatch):
    fake = tmp_path / "rollback"
    fake.mkdir()
    src = R.manifest_path(LEGACY).read_text().splitlines()
    src[0] = "0" * 64 + src[0][64:]
    (fake / R.manifest_path(LEGACY).name).write_text("\n".join(src) + "\n")
    monkeypatch.setattr(R, "manifest_path", lambda ref: fake / f"legacy_{ref[:12]}.sha256")
    with pytest.raises(SystemExit, match="LEGACY_ARTIFACT_INVALID"):
        R.legacy_build(LEGACY, tmp_path / "out")


def test_serve_artifact_behaves_like_pages(tmp_path):
    (tmp_path / "site").mkdir()
    (tmp_path / "index.html").write_text('<meta http-equiv="refresh" content="0; url=site/">')
    (tmp_path / "site/index.html").write_text("ok")
    srv = S.make_server(tmp_path, 0)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    op = urllib.request.build_opener(NoRedirect)

    def get(path):
        try:
            with op.open(f"http://127.0.0.1:{port}{path}") as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            return e.code, b"", e.headers
    try:
        assert get("/MicroRhodoDB/")[0:2] == (200, (tmp_path / "index.html").read_bytes())
        st, _, h = get("/MicroRhodoDB")
        assert st == 301 and h["Location"] == "/MicroRhodoDB/"
        assert get("/MicroRhodoDB/site")[0] == 301
        assert get("/MicroRhodoDB/site/")[1] == b"ok"
        assert get("/MicroRhodoDB/missing.json")[0] == 404
        assert get("/MicroRhodoDB/../etc/passwd")[0] == 404
        assert get("/other/")[0] == 404
        assert get("/MicroRhodoDB/__test__/stall?path=index.html")[0] == 404
    finally:
        srv.shutdown()
        srv.server_close()


# ------------------------------------------------------------------- post-deployment verifier (PR-7a)
class _FaultServer:
    """Local HTTP server with injectable latency and faults, standing in for GitHub Pages / its CDN.

    files: path -> current bytes. old: path -> stale bytes served until `propagate_at[path]` (monotonic time);
    missing_until: path -> serve 404 until that time. faults: path -> list of per-request modes consumed in order
    ('503', 'reset', 'truncate', 'stall', 'drip', 'ok'); 'always:<mode>' repeats forever.
    """

    def __init__(self, files, latency=0.0, stall=5.0, drip_interval=0.2):
        import http.server
        self.files, self.latency, self.stall, self.drip_interval = files, latency, stall, drip_interval
        self.old, self.propagate_at, self.missing_until, self.faults = {}, {}, {}, {}
        self.lock = threading.Lock()
        self.in_flight = self.max_in_flight = self.requests = 0
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def do_GET(self):
                with outer.lock:
                    outer.requests += 1
                    outer.in_flight += 1
                    outer.max_in_flight = max(outer.max_in_flight, outer.in_flight)
                try:
                    outer.handle(self)
                finally:
                    with outer.lock:
                        outer.in_flight -= 1

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.srv.daemon_threads = True
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}/MicroRhodoDB/"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def mode(self, rel):
        with self.lock:
            q = self.faults.get(rel)
            if not q:
                return "ok"
            if q[0].startswith("always:"):
                return q[0].split(":", 1)[1]
            return q.pop(0)

    def handle(self, h):
        import time as _t
        from urllib.parse import unquote, urlsplit
        if self.latency:
            _t.sleep(self.latency)
        rel = unquote(urlsplit(h.path).path)[len("/MicroRhodoDB/"):]
        m = self.mode(rel)
        now = _t.monotonic()
        if m == "reset":
            h.close_connection = True
            return
        if m == "stall":
            _t.sleep(self.stall)
        if m == "503" or rel not in self.files or now < self.missing_until.get(rel, 0):
            code = 503 if m == "503" else 404
            h.send_response(code)
            h.send_header("Content-Length", "0")
            h.end_headers()
            return
        body = self.old[rel] if now < self.propagate_at.get(rel, 0) else self.files[rel]
        h.send_response(200)
        h.send_header("Content-Length", str(len(body)))
        h.end_headers()
        if m == "truncate":
            h.wfile.write(body[: len(body) // 2])
            h.wfile.flush()
            h.close_connection = True
            return
        if m == "drip":
            for i in range(len(body)):
                h.wfile.write(body[i:i + 1])
                h.wfile.flush()
                _t.sleep(self.drip_interval)
            return
        h.wfile.write(body)

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


def _site(n, size=64):
    files = {f"site/data/f{i:04d}.json": (f'{{"i": {i}, "pad": "' + "x" * size + '"}').encode() for i in range(n)}
    return files, {k: R.sha256_bytes(v) for k, v in files.items()}


@pytest.fixture
def fault_server():
    servers = []

    def make(files, **kw):
        s = _FaultServer(files, **kw)
        servers.append(s)
        return s
    yield make
    for s in servers:
        s.close()


def test_verifier_uses_bounded_concurrency_on_a_delayed_network(fault_server, monkeypatch):
    import time as _t
    files, sums = _site(240)
    srv = fault_server(files, latency=0.05)  # 50 ms per request: sequential would take >= 12 s

    # Measure active CLIENT requests independently of verify_served's own stats.
    # Server handlers may still be unwinding after the client has read the full
    # response and started another request, so server-side handler counts can
    # transiently exceed the number of simultaneous client requests.
    measure_lock = threading.Lock()
    active_client_requests = 0
    peak_client_requests = 0
    original_fetch = R.fetch_bounded

    def measured_fetch(*args, **kwargs):
        nonlocal active_client_requests, peak_client_requests
        with measure_lock:
            active_client_requests += 1
            peak_client_requests = max(peak_client_requests, active_client_requests)
        try:
            return original_fetch(*args, **kwargs)
        finally:
            with measure_lock:
                active_client_requests -= 1

    monkeypatch.setattr(R, "fetch_bounded", measured_fetch)
    t0 = _t.monotonic()
    res = R.verify_served(srv.base, sums, workers=12, deadline=60, round_wait=0.1)
    elapsed = _t.monotonic() - t0
    assert res["failed"] == [] and res["ok"] == 240 and res["rounds"] == 1 and res["requests"] == 240
    assert 1 < peak_client_requests <= 12
    assert 1 < res["max_in_flight"] <= 12
    assert srv.max_in_flight > 1  # Independent evidence of actual network concurrency.
    assert active_client_requests == 0
    assert elapsed < 6, elapsed


def test_verifier_retries_transient_failures_per_file(fault_server):
    files, sums = _site(20)
    srv = fault_server(files, stall=3.0)
    names = sorted(files)
    srv.faults = {names[0]: ["503", "503"], names[1]: ["reset"], names[2]: ["truncate"], names[3]: ["stall"]}
    res = R.verify_served(srv.base, sums, workers=4, request_timeout=1.0, retries=3, backoff=0.05, deadline=30,
                          max_rounds=1)
    assert res["failed"] == [] and res["ok"] == 20 and res["rounds"] == 1
    assert res["retries"] == 5 and res["requests"] == 25


def test_verifier_never_accepts_a_truncated_or_partial_body(fault_server):
    files, sums = _site(3, size=200_000)
    srv = fault_server(files)
    srv.faults = {sorted(files)[0]: ["always:truncate"]}
    res = R.verify_served(srv.base, sums, workers=2, retries=2, backoff=0.01, deadline=20, max_rounds=1)
    assert res["ok"] == 2 and len(res["failed"]) == 1 and "truncated body" in res["failed"][0]


def test_verifier_hashes_the_full_file(fault_server):
    big = bytes(range(256)) * 8192  # 2 MiB
    files = {"site/big.bin": big[:-1] + b"\x00"}  # differs only in the last byte
    srv = fault_server(files)
    res = R.verify_served(srv.base, {"site/big.bin": R.sha256_bytes(big)}, deadline=10, round_wait=0.1, max_rounds=2)
    assert res["ok"] == 0 and "served bytes differ" in res["failed"][0] and res["requests"] == 2


def test_verifier_slow_drip_body_hits_the_per_request_deadline(fault_server):
    import time as _t
    files, sums = _site(1, size=200)
    srv = fault_server(files, drip_interval=0.1)  # a byte every 100 ms: no socket timeout ever fires
    srv.faults = {next(iter(files)): ["always:drip"]}
    t0 = _t.monotonic()
    res = R.verify_served(srv.base, sums, request_timeout=0.6, retries=1, backoff=0.01, deadline=20, max_rounds=1)
    assert res["ok"] == 0 and "request deadline" in res["failed"][0]
    assert _t.monotonic() - t0 < 4


def test_verifier_total_deadline_bounds_a_hanging_cdn(fault_server):
    import time as _t
    files, sums = _site(40)
    srv = fault_server(files, stall=20.0)
    srv.faults = {k: ["always:stall"] for k in files}
    t0 = _t.monotonic()
    res = R.verify_served(srv.base, sums, workers=8, request_timeout=10, retries=3, deadline=1.5, round_wait=0.1)
    elapsed = _t.monotonic() - t0
    assert res["ok"] == 0 and len(res["failed"]) == 40 and res["deadline_exceeded"] is True
    assert elapsed < 1.5 + 3.0, elapsed
    assert all("deadline" in f or "timeout" in f.lower() or "timed out" in f for f in res["failed"]), res["failed"][:3]


def test_verify_served_process_exits_promptly_at_the_total_deadline(fault_server, tmp_path):
    """The CLI process (not only the function) must end near the deadline: no worker may keep a request open
    beyond the remaining total time, otherwise interpreter shutdown waits for it."""
    import time as _t
    files, sums = _site(16)
    srv = fault_server(files, stall=30.0)
    srv.faults = {k: ["always:stall"] for k in files}
    man = tmp_path / "SHA256SUMS"
    man.write_text("".join(f"{h}  {p}\n" for p, h in sorted(sums.items())))
    t0 = _t.monotonic()
    r = subprocess.run([sys.executable, str(SCRIPTS / "site_rollback.py"), "verify-served", "--base", srv.base,
                        "--sums", str(man), "--workers", "4", "--request-timeout", "20", "--deadline", "1.5"],
                       capture_output=True, text=True, timeout=60)
    elapsed = _t.monotonic() - t0
    assert r.returncode == 1 and "SERVED_SITE_DIFFERS" in r.stdout
    assert elapsed < 1.5 + 4.0, elapsed


def test_verifier_rechecks_only_unpropagated_files_until_the_cdn_converges(fault_server):
    import time as _t
    files, sums = _site(60)
    srv = fault_server(files)
    names = sorted(files)
    now = _t.monotonic()
    for k in names[:10]:   # stale copy still at the edge
        srv.old[k] = b'{"stale": true}'
        srv.propagate_at[k] = now + 1.0
    for k in names[10:15]:  # new file not yet at the edge
        srv.missing_until[k] = now + 1.0
    res = R.verify_served(srv.base, sums, workers=8, deadline=30, round_wait=0.4)
    assert res["failed"] == [] and res["ok"] == 60 and res["rounds"] >= 2
    # later rounds re-request only the 15 lagging files, never the 45 already verified
    assert res["requests"] <= 60 + 15 * (res["rounds"] - 1)


def test_verifier_partial_propagation_that_never_converges_fails_at_the_deadline(fault_server):
    import time as _t
    files, sums = _site(30)
    srv = fault_server(files)
    names = sorted(files)
    for k in names[:3]:
        srv.old[k] = b"old deployment"
        srv.propagate_at[k] = float("inf")
    srv.missing_until[names[3]] = float("inf")
    t0 = _t.monotonic()
    res = R.verify_served(srv.base, sums, workers=8, deadline=2.0, round_wait=0.3)
    assert _t.monotonic() - t0 < 2.0 + 3.0
    assert res["ok"] == 26 and res["deadline_exceeded"] is True and res["rounds"] >= 3
    failed = dict(f.split(": ", 1) for f in res["failed"])
    assert set(failed) == set(names[:4])
    assert all("served bytes differ" in failed[k] for k in names[:3]) and "HTTP 404" in failed[names[3]]


def test_verify_served_cli_exit_codes_and_manifest_paths(fault_server, tmp_path, capsys):
    files, sums = _site(5)
    files["site/.hidden"] = b"h"
    sums["site/.hidden"] = R.sha256_bytes(b"h")
    srv = fault_server(files)
    man = tmp_path / "SHA256SUMS"
    man.write_text("".join(f"{h}  {p}\n" for p, h in sorted(sums.items())))
    common = ["verify-served", "--base", srv.base, "--sums", str(man), "--deadline", "10", "--round-wait", "0.1"]
    assert R.main(common) == 0
    assert R.main(common + ["--exclude-hidden", "--json", str(tmp_path / "v.json")]) == 0
    assert json.loads((tmp_path / "v.json").read_text())["checked"] == 5
    assert R.main(common + ["--paths", "site/not-in-manifest.json", "--max-rounds", "1"]) == 1
    srv.files[sorted(files)[0]] = b"tampered"
    assert R.main(common + ["--max-rounds", "1"]) == 1
    assert "SERVED_SITE_DIFFERS" in capsys.readouterr().out


def test_deploy_workflow_live_verification_is_bounded_and_covers_every_file():
    wf = load_wf("deploy-site.yml")
    steps = [st for st in wf["jobs"]["verify-live"]["steps"] if "verify-served" in st.get("run", "")]
    assert len(steps) == 2
    for st in steps:
        run = st["run"]
        for flag in ("--workers 16", "--request-timeout 30", "--retries 3", "--round-wait 30", "--deadline 900"):
            assert flag in run, flag
        assert "--paths" not in run and "for i in" not in run and "sleep" not in run  # no unbounded shell loop
    assert wf["jobs"]["verify-live"]["timeout-minutes"] * 60 > 900


def test_release_blocker_resolutions_cannot_skip_mandatory_validation():
    """The gate only decides whether preflight passes; every validation step in build/verify-live is unconditional
    for website deployments (no step reads the gate result, nothing is continue-on-error)."""
    wf = load_wf("deploy-site.yml")
    text = (WFD / "deploy-site.yml").read_text()
    assert "continue-on-error" not in text and "release_gate.json" not in text.split("verify-live:")[0].split("build:")[1]
    allowed_if = {None, "inputs.kind == 'website'", "inputs.kind == 'legacy-rollback'", "always() && inputs.kind == 'website'",
                  "failure()"}
    for jid in ("build", "deploy", "verify-live"):
        for st in wf["jobs"][jid]["steps"]:
            assert st.get("if") in allowed_if, (jid, st.get("name"), st.get("if"))
    gate = next(st for st in wf["jobs"]["preflight"]["steps"] if "release_gate.py" in st.get("run", ""))
    assert gate["if"] == "inputs.kind == 'website'" and "continue-on-error" not in gate
    assert wf["jobs"]["build"]["needs"] == "preflight"
