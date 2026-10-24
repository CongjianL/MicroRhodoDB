"""PR-1: Release data-source fetcher (web/scripts/fetch_release_db.py). Uses file:// mirrors; no network."""
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(os.environ.get("MRDB_REPO", ".")).resolve()
SCRIPT = REPO / "web/scripts/fetch_release_db.py"
DB = REPO / "releases/v1.6.1/db/microrhododb_v1.6.1.sqlite"
DEST = "releases/v1.6.1/db/microrhododb_v1.6.1.sqlite"


def run(repo, *extra):
    return subprocess.run([sys.executable, str(SCRIPT), "--repo", str(repo), *extra], capture_output=True, text=True)


def fake_repo(tmp):
    r = tmp / "repo"
    r.mkdir()
    shutil.copy(REPO / "BINARIES.md", r / "BINARIES.md")
    return r


def test_existing_verified_db_is_accepted():
    r = run(REPO)
    assert r.returncode == 0 and "already present" in r.stdout


def test_missing_release_is_blocked(tmp_path):
    repo = fake_repo(tmp_path)
    r = run(repo, "--base-url", (tmp_path / "empty_mirror").as_uri())
    assert r.returncode == 2 and "BLOCKED_DATA_SOURCE" in r.stderr
    assert not (repo / DEST).exists()
    assert list((repo / DEST).parent.glob(".fetch-*")) == []


def test_checksum_mismatch_is_blocked(tmp_path):
    repo = fake_repo(tmp_path)
    mirror = tmp_path / "mirror" / "v1.6.1"
    mirror.mkdir(parents=True)
    (mirror / "microrhododb_v1.6.1.sqlite").write_bytes(b"not the database")
    r = run(repo, "--base-url", (tmp_path / "mirror").as_uri())
    assert r.returncode == 2 and "BLOCKED_DATA_SOURCE" in r.stderr and "sha256" in r.stderr
    assert not (repo / DEST).exists()


def test_verified_download(tmp_path):
    repo = fake_repo(tmp_path)
    mirror = tmp_path / "mirror" / "v1.6.1"
    mirror.mkdir(parents=True)
    os.symlink(DB, mirror / "microrhododb_v1.6.1.sqlite")
    r = run(repo, "--base-url", (tmp_path / "mirror").as_uri())
    assert r.returncode == 0 and "downloaded and verified" in r.stdout
    assert hashlib.sha256((repo / DEST).read_bytes()).hexdigest() == \
        "b8215cffa9d2fdab1e65b904f4bafbe9edf6578aed7b4fb028a890850e704c2d"


# ---------------------------------------------------------------- HTTP 404 (private repository) -> gh fallback
def _http_404_server():
    import http.server
    import threading

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_error(404)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _fake_gh(tmp, body):
    gh = tmp / "gh"
    gh.write_text(f"#!/bin/sh\n# args: release download TAG -R REPO --pattern ASSET -D DIR\n{body}\n")
    gh.chmod(0o755)
    return gh


def run_gh(repo, gh, base):
    env = {**os.environ, "MRDB_GH": str(gh)}
    return subprocess.run([sys.executable, str(SCRIPT), "--repo", str(repo), "--base-url", base],
                          capture_output=True, text=True, env=env)


def test_http_404_falls_back_to_gh_and_verifies(tmp_path):
    repo = fake_repo(tmp_path)
    gh = _fake_gh(tmp_path, f'cp "{DB}" "$9/$7"')
    srv, base = _http_404_server()
    try:
        r = run_gh(repo, gh, base)
    finally:
        srv.shutdown()
    assert r.returncode == 0 and "downloaded and verified" in r.stdout and "via gh" in r.stdout, r.stderr
    assert hashlib.sha256((repo / DEST).read_bytes()).hexdigest() == \
        "b8215cffa9d2fdab1e65b904f4bafbe9edf6578aed7b4fb028a890850e704c2d"
    assert [p.name for p in (repo / DEST).parent.iterdir()] == ["microrhododb_v1.6.1.sqlite"]


def test_gh_fallback_copy_is_checksum_verified(tmp_path):
    repo = fake_repo(tmp_path)
    gh = _fake_gh(tmp_path, 'printf "not the database" > "$9/$7"')
    srv, base = _http_404_server()
    try:
        r = run_gh(repo, gh, base)
    finally:
        srv.shutdown()
    assert r.returncode == 2 and "BLOCKED_DATA_SOURCE" in r.stderr and "gh release download" in r.stderr
    assert list((repo / DEST).parent.iterdir()) == []


def test_http_404_without_gh_explains_private_repository(tmp_path):
    repo = fake_repo(tmp_path)
    gh = _fake_gh(tmp_path, 'echo "HTTP 404 https://example.invalid/asset?sig=SECRET&jwt=TOKEN" >&2; exit 1')
    srv, base = _http_404_server()
    try:
        r = run_gh(repo, gh, base)
    finally:
        srv.shutdown()
    assert r.returncode == 2 and "private and refuses anonymous downloads" in r.stderr and "gh auth login" in r.stderr
    assert "SECRET" not in r.stderr and "TOKEN" not in r.stderr
    assert list((repo / DEST).parent.iterdir()) == []
