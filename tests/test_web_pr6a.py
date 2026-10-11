"""PR-6a regression tests.

1. The PR-6 mutation audit (web/scripts/pr6_audit_mutations.py) runs when /workspace does not exist: it is run
   under a Python audit hook (installed in every child process via sitecustomize) that makes any path under
   /workspace other than the repository checkout and the running Python installation behave as missing, and that
   rejects writes outside the test's scratch directory. A synthetic copy of the PR-6 defect (TemporaryDirectory(dir="/workspace")) must fail
   under the same hook, proving the hook would catch a regression.
2. The web-data workflow parses, keeps every scientific / frontend gate, keeps minimal permissions, and its path
   filters (GitHub glob semantics) cover the repository metadata the exporter publishes on the website and the
   frozen inputs it reads, so documentation-only changes trigger validation.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WF = REPO / ".github" / "workflows" / "web-data.yml"
MUT = REPO / "web" / "scripts" / "pr6_audit_mutations.py"
EXP = REPO / "web" / "public" / "data" / "v1.6.0"
DB = REPO / "releases" / "v1.6.0" / "db" / "microrhododb_v1.6.0.sqlite"

METADATA = ["README.md", "LICENSE", "CITATION.cff", "MAINTENANCE.md", "BINARIES.md", "CHANGELOG.md", "index.html"]


# ----------------------------------------------------------------------------------------------- helpers
def gh_glob(pattern: str) -> re.Pattern:
    """GitHub Actions path-filter glob: ** = any chars incl. '/', * = any chars except '/', ? = one char."""
    out, i = "", 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
            if pattern.startswith("/", i) and out.endswith(".*"):
                out = out[:-2] + "(?:.*/)?"
                i += 1
            continue
        out += {"*": "[^/]*", "?": "[^/]"}.get(c, re.escape(c))
        i += 1
    return re.compile(rf"^{out}$")


def triggered(paths: list[str], changed: str) -> bool:
    inc = [p for p in paths if not p.startswith("!")]
    exc = [p[1:] for p in paths if p.startswith("!")]
    return any(gh_glob(p).match(changed) for p in inc) and not any(gh_glob(p).match(changed) for p in exc)


def workflow() -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(WF.read_text())


def on_block(wf: dict) -> dict:
    return wf.get("on", wf.get(True))  # PyYAML (YAML 1.1) reads the key `on` as boolean True


def run_strings(wf: dict) -> str:
    return "\n".join(s.get("run", "") for j in wf["jobs"].values() for s in j["steps"])


HOOK = textwrap.dedent(
    r'''
    import os, sys, threading
    _REPO = os.environ["PR6A_REPO"]
    _ALLOW_W = os.environ["PR6A_ALLOW_WRITE"]
    _LOG = os.environ["PR6A_LOG"]
    _g = threading.local()
    _W = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
    # The checkout and the Python installation running the test are the only paths that may live under
    # /workspace (in this development sandbox both do; on GitHub runners neither does).
    _KEEP = [_REPO] + sorted({os.path.realpath(x) for x in (sys.prefix, sys.base_prefix, sys.exec_prefix)} |
                             {x for x in (sys.prefix, sys.base_prefix, sys.exec_prefix)})

    def _norm(p):
        if isinstance(p, int) or p is None:
            return None
        try:
            p = os.fsdecode(os.fspath(p))
        except TypeError:
            return None
        return os.path.abspath(p)

    def _under(p, root):
        return p == root or p.startswith(root.rstrip("/") + "/")

    def _log(msg):
        fd = os.open(_LOG, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (msg + "\n").encode())
        finally:
            os.close(fd)

    def _hook(event, args):
        if getattr(_g, "busy", False):
            return
        items = []  # (path, is_write)
        if event == "open":
            mode, flags = args[1], args[2]
            w = (isinstance(mode, str) and any(c in mode for c in "wax+")) or (mode is None and bool((flags or 0) & _W))
            items = [(args[0], w)]
        elif event in ("os.mkdir", "os.rmdir", "os.remove", "shutil.rmtree", "os.chmod", "os.utime", "os.symlink"):
            items = [(args[0], True)]
        elif event in ("os.rename", "shutil.move"):
            items = [(args[0], True), (args[1], True)]
        elif event in ("shutil.copytree", "shutil.copyfile"):
            items = [(args[0], False), (args[1], True)]
        elif event in ("tempfile.mkdtemp", "tempfile.mkstemp"):
            items = [(args[0], True)]
        elif event in ("os.listdir", "os.scandir", "os.chdir"):
            items = [(args[0], False)]
        else:
            return
        _g.busy = True
        try:
            for raw, write in items:
                p = _norm(raw)
                if p is None:
                    continue
                if _under(p, "/workspace") and not any(_under(p, k) for k in _KEEP):
                    _log(f"MISSING_WORKSPACE {event} {p}")
                    raise FileNotFoundError(2, "simulated: /workspace does not exist", p)
                if write and not (_under(p, _ALLOW_W) or p == os.devnull):
                    _log(f"WRITE_OUTSIDE_SCRATCH {event} {p}")
                    raise PermissionError(13, "write outside the test scratch directory", p)
        finally:
            _g.busy = False

    _log(f"HOOK_ACTIVE pid={os.getpid()}")
    sys.addaudithook(_hook)
    '''
)


def run_under_hook(tmp_path: Path, script: Path, extra_args: list[str] | None = None, timeout: int = 900):
    hook_dir = tmp_path / "hook"
    hook_dir.mkdir()
    (hook_dir / "sitecustomize.py").write_text(HOOK)
    scratch = tmp_path / "scratch"
    sys_tmp = scratch / "systmp"
    sys_tmp.mkdir(parents=True)
    out = scratch / "out"
    log = tmp_path / "hook.log"
    env = {k: v for k, v in os.environ.items() if k not in ("RUNNER_TEMP", "PYTHONSTARTUP")}
    env.update(PYTHONPATH=str(hook_dir), PYTHONDONTWRITEBYTECODE="1", TMPDIR=str(sys_tmp), TEMP=str(sys_tmp),
               TMP=str(sys_tmp), PR6A_REPO=str(REPO), PR6A_ALLOW_WRITE=str(scratch), PR6A_LOG=str(log))
    p = subprocess.run([sys.executable, str(script), "--out", str(out), *(extra_args or [])], env=env,
                       capture_output=True, text=True, timeout=timeout, cwd=str(scratch))
    lines = log.read_text().splitlines() if log.exists() else []
    return p, lines, out, sys_tmp


needs_data = pytest.mark.skipif(not (EXP / "records-index.json").exists() or not DB.exists(),
                                reason="needs the v1.6.0 export (tools/export_web_data.py) and the release DB")


# ------------------------------------------------------------------------------ 1. mutation-audit portability
def test_no_hardcoded_workspace_paths_in_ci_scripts():
    offenders = []
    for f in sorted((REPO / "web" / "scripts").glob("*.py")) + [REPO / "tools" / "export_web_data.py"]:
        for node in ast.walk(ast.parse(f.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.search(r"(^|[\s\"'=(])/workspace\b", node.value):
                offenders.append(f"{f.relative_to(REPO)}:{node.lineno}")
    for f in sorted((REPO / "web" / "scripts").glob("*.mjs")):
        for i, ln in enumerate(f.read_text().splitlines(), 1):
            if re.search(r"[\"'`]/workspace\b", ln):
                offenders.append(f"{f.relative_to(REPO)}:{i}")
    assert offenders == [], offenders


def test_scratch_root_is_portable(monkeypatch, tmp_path):
    sys.path.insert(0, str(MUT.parent))
    try:
        import importlib
        m = importlib.import_module("pr6_audit_mutations")
    finally:
        sys.path.pop(0)
    monkeypatch.delenv("RUNNER_TEMP", raising=False)
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    import tempfile
    monkeypatch.setattr(tempfile, "tempdir", None)  # re-read TMPDIR
    assert m.scratch_root(None) == tmp_path
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    assert m.scratch_root(None) == tmp_path / "runner"  # GitHub Actions
    assert m.scratch_root(str(tmp_path / "explicit")) == tmp_path / "explicit"
    assert (tmp_path / "explicit").is_dir()


@needs_data
def test_mutation_audit_runs_without_workspace(tmp_path):
    p, log, out, sys_tmp = run_under_hook(tmp_path, MUT)
    assert p.returncode == 0, p.stdout[-2000:] + p.stderr[-2000:]
    assert [ln for ln in log if not ln.startswith("HOOK_ACTIVE")] == [], log
    # the hook really was active in the runner and in every audit child process (1 + 13 runs)
    assert sum(ln.startswith("HOOK_ACTIVE") for ln in log) >= 14
    res = json.loads((out / "scientific_audit_mutations.json").read_text())
    assert len(res) == 13 and all(r["detected"] for r in res)
    assert res[0]["expected"] == 0 and res[0]["exit"] == 0 and res[0]["failed_checks"] == []
    assert all(r["exit"] == 1 and r["failed_checks"] for r in res[1:])  # detected by a check, not by a crash
    assert list(sys_tmp.iterdir()) == []  # scratch copies removed


@needs_data
def test_pr6_workspace_defect_is_caught_by_the_hook(tmp_path):
    """Positive control: the PR-6 defect, re-created in a copy of the script, must fail under the same hook."""
    src = MUT.read_text()
    assert 'dir=scratch_root(a.tmp_root)' in src
    mutant = src.replace('dir=scratch_root(a.tmp_root)', 'dir="/workspace"').replace(
        'REPO = Path(__file__).resolve().parents[2]', f'REPO = Path({str(REPO)!r})')
    f = tmp_path / "pr6_audit_mutations_pr6_defect.py"
    f.write_text(mutant)
    p, log, _, _ = run_under_hook(tmp_path, f, timeout=300)
    assert p.returncode != 0
    assert any(ln.startswith("MISSING_WORKSPACE") for ln in log), log


# ------------------------------------------------------------------------------------ 2. workflow validation
def test_glob_matcher_semantics():
    assert triggered(["web/**"], "web/src/a/b.ts")
    assert triggered(["tests/test_web_*.py"], "tests/test_web_pr6a.py")
    assert not triggered(["tests/test_web_*.py"], "tests/sub/test_web_x.py")
    assert triggered(["README.md"], "README.md") and not triggered(["README.md"], "docs/README.md")
    assert not triggered(["web/**", "!web/**/*.md"], "web/x/notes.md")


def test_workflow_triggers_cover_published_metadata_and_frozen_inputs():
    on = on_block(workflow())
    assert set(on) >= {"pull_request", "push", "workflow_dispatch"}
    assert "pull_request_target" not in on  # never run untrusted PR code with a write token
    assert on["push"]["branches"] == ["main"]
    must = list(METADATA)
    # data-driven: every repository document the exporter embeds in downloads.json
    if (EXP / "downloads.json").exists():
        must += [d["path"] for d in json.loads((EXP / "downloads.json").read_text())["repository_documents"]]
    # frozen inputs read by the exporter / release fetcher
    must += ["refpkg/MR_RT_003/SHA256SUMS", "refpkg/MR_RT_003/tree/MR_RT_003.rooted.treefile",
             "refpkg/MR_RT_003/clades/MR_CLD3_tips.tsv", "releases/v1.6.0/SHA256SUMS",
             "tools/export_web_data.py", "web/scripts/fetch_release_db.py", "web/src/data/fetchText.ts",
             "tests/test_web_pr6a.py", "tests/data/web_drilldown_golden_v160.json",
             "docs/website/PR6A_AUTO_ACCEPTANCE_REPORT.md", ".github/workflows/web-data.yml"]
    for event in ("pull_request", "push"):
        paths = on[event]["paths"]
        assert "paths-ignore" not in on[event]
        missing = [f for f in must if not triggered(paths, f)]
        assert missing == [], f"{event}: changes to {missing} would not trigger validation"
    # sanity: the filter is not a catch-all
    assert not triggered(on["pull_request"]["paths"], "src/microrhododb/api.py")


def test_exporter_repository_reads_are_covered():
    """Every literal repository path the exporter reads (repo / "X") must be in the trigger paths."""
    src = (REPO / "tools" / "export_web_data.py").read_text()
    lits = set(re.findall(r'repo / "([^"]+)"', src))
    lits |= set(re.findall(r'\("([A-Z][A-Za-z_]+\.(?:md|cff)|LICENSE)",', src))
    assert {"CITATION.cff", "MAINTENANCE.md", "README.md", "LICENSE", "CHANGELOG.md"} <= lits
    paths = on_block(workflow())["pull_request"]["paths"]
    probe = [l if "." in l.split("/")[-1] or l == "LICENSE" else f"{l}/x" for l in lits]
    assert [l for l in probe if not triggered(paths, l)] == []


def test_workflow_keeps_all_validation_gates():
    wf = workflow()
    runs = run_strings(wf)
    for cmd in ["web/scripts/fetch_release_db.py", "tools/export_web_data.py", "pr5a_drilldown_golden.py --check",
                "pr6_scientific_audit.py", "pr6_audit_mutations.py", "schema_to_ts.py --check",
                "fetch_structure_fixtures.py --check", "npm ci", "npm run build", "npx vitest run",
                "npx playwright install --with-deps chromium", "npx playwright test"]:
        assert cmd in runs, cmd
    pytest_line = next(l for l in runs.splitlines() if "python -m pytest" in l)
    for t in sorted(REPO.glob("tests/test_web_*.py")) + [REPO / "tests" / "test_fetch_release_db.py"]:
        assert f"tests/{t.name}" in pytest_line, f"{t.name} is not run by the workflow"
    order = [runs.index(c) for c in ["fetch_release_db.py", "export_web_data.py", "python -m pytest", "npm run build", "npx playwright test"]]
    assert order == sorted(order)


def test_workflow_permissions_are_minimal():
    wf = workflow()
    assert wf["permissions"] == {"contents": "read"}
    text = WF.read_text()
    assert "secrets." not in text and "pages: write" not in text and "id-token" not in text
    assert "deploy-pages" not in text and "upload-pages-artifact" not in text  # validation only
    for job in wf["jobs"].values():
        assert set((job.get("permissions") or {}).values()) <= {"read", "none"}
        assert job.get("timeout-minutes")
        for st in job["steps"]:
            if "uses" in st:
                ref = st["uses"].split("@")[-1]
                assert ref not in ("main", "master", "latest") and "@" in st["uses"], st["uses"]
        checkout = next(s for s in job["steps"] if s.get("uses", "").startswith("actions/checkout@"))
        assert checkout.get("with", {}).get("persist-credentials") is False
    assert wf.get("concurrency", {}).get("cancel-in-progress") is True
