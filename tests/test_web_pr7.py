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
    assert perms["preflight"] == {"contents": "read", "actions": "read"}
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
def test_gate_blocks_production_now_and_never_blocks_report_mode(capsys):
    assert G.main(["--mode", "report"]) == 0
    assert G.main(["--mode", "production"]) == 3
    res = G.evaluate(REPO)
    ids = {b["id"] for b in json.loads((REPO / G.BLOCKERS).read_text())["blockers"]}
    assert {"MD-1", "MD-2", "MD-3", "MD-4", "MD-5", "RA-1", "RA-2", "OPS-1", "OPS-2", "CI-1", "VER-1", "ACC-1"} <= ids
    assert set(res["unresolved"]) == ids and res["production_allowed"] is False


def test_checklist_is_open_and_resolution_only_by_maintainer():
    data = json.loads((REPO / G.BLOCKERS).read_text())
    for b in data["blockers"]:
        assert b["status"] == "open" and b["resolution"] is None, b["id"]
        assert b["evidence"] and b["required_decision"] and b["blocks"] == ["production"]


def _fake(monkeypatch, tmp_path, blockers, checks):
    p = tmp_path / "blockers.json"
    p.write_text(json.dumps({"version": 1, "blockers": blockers}))
    monkeypatch.setattr(G, "CHECKS", checks)
    return G.evaluate(REPO, blockers_path=p)


REC = {"decided_by": "maintainer", "decided_at": "2026-10-12", "reference": "https://example.invalid/issue/1"}


def _b(i, status="open", resolution=None):
    return {"id": i, "title": i, "category": "t", "blocks": ["production"], "status": status, "resolution": resolution}


def test_gate_requires_record_and_passing_check(monkeypatch, tmp_path):
    checks = {"A": lambda r, c: (True, "ok"), "B": lambda r, c: (False, "fails"), "C": lambda r, c: (True, "ok"),
              "E": lambda r, c: (None, "offline")}
    res = _fake(monkeypatch, tmp_path, [_b("A", "resolved", REC), _b("B", "resolved", REC), _b("C"),
                                        _b("D", "resolved", REC), _b("E", "resolved", REC),
                                        _b("F", "resolved", {**REC, "reference": ""})], checks)
    st = {b["id"]: (b["resolved"], b["state"]) for b in res["blockers"]}
    assert st["A"] == (True, "resolved")
    assert st["B"] == (False, "claimed resolved but the automated check does not pass")
    assert st["C"] == (False, "automated check passes but no maintainer resolution record")
    assert st["D"] == (True, "resolved")          # manual-only blocker with a complete record
    assert st["E"][0] is False                    # undecidable check (offline) never counts as passing
    assert st["F"][0] is False                    # incomplete record
    assert res["unresolved"] == ["B", "C", "E", "F"]


def test_gate_allows_production_only_when_everything_resolved(monkeypatch, tmp_path):
    p = tmp_path / "blockers.json"
    p.write_text(json.dumps({"version": 1, "blockers": [_b("A", "resolved", REC)]}))
    monkeypatch.setattr(G, "CHECKS", {"A": lambda r, c: (True, "ok")})
    monkeypatch.setattr(G, "BLOCKERS", p)
    assert G.main(["--mode", "production"]) == 0
    monkeypatch.setattr(G, "CHECKS", {"A": lambda r, c: (False, "regressed")})
    assert G.main(["--mode", "production"]) == 3


def _meta_repo(tmp_path: Path, **over) -> Path:
    r = tmp_path / "repo"
    (r / "web").mkdir(parents=True)
    (r / "tools").mkdir()
    (r / "releases/v1.6.0").mkdir(parents=True)
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
    bad = _meta_repo(tmp_path / "b", **{"README.md": "Data: CC BY 4.0. Code: Apache-2.0.\n",
                                        "CITATION.cff": "version: 1.6.0\ndate-released: 2026-10-09\nlicense: CC-BY-4.0\n",
                                        "MAINTENANCE.md": "- Contact: <<PLACEHOLDER: e-mail>>\n",
                                        "web/package.json": json.dumps({"license": "MIT", "version": "2.0.0-pr7"})})
    assert G.check_md1_licence(bad, ctx)[0] is False
    assert G.check_md2_dates(bad, ctx)[0] is False
    assert G.check_md4_contact(bad, ctx)[0] is False
    assert G.check_md5_maintenance(bad, ctx)[0] is False
    assert G.check_ver1_version(bad, ctx)[0] is False


def test_current_repository_metadata_checks_fail_for_the_documented_reasons():
    ctx = {"online": False, "blocker": {}}
    ok, detail = G.check_md1_licence(REPO, ctx)
    assert ok is False and "MIT" in detail and "CC-BY-4.0" in detail
    ok, detail = G.check_md2_dates(REPO, ctx)
    assert ok is False and "2026-10-09" in detail and "2026-10-10" in detail
    assert G.check_md3_doi(REPO, ctx)[0] is False
    assert G.check_md4_contact(REPO, ctx)[0] is False
    assert G.check_md5_maintenance(REPO, ctx)[0] is False
    assert G.check_ver1_version(REPO, ctx)[0] is False
    ok, detail = G.check_ra1_release_assets(REPO, ctx)
    assert ok is None and "not checked offline" in detail
    ok, detail = G.check_ra1_release_assets(REPO, {**ctx, "release": {"assets": [{"name": "microrhododb_v1.6.0.sqlite", "size": 33464320}]}})
    assert ok is False and "MicroRhodoDB_v1.6.0.tar.gz" in detail and "microrhododb_v1.5.0.sqlite" in detail


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
