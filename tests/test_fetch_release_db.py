"""PR-1: Release data-source fetcher (web/scripts/fetch_release_db.py). Uses file:// mirrors; no network."""
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(os.environ.get("MRDB_REPO", ".")).resolve()
SCRIPT = REPO / "web/scripts/fetch_release_db.py"
DB = REPO / "releases/v1.6.0/db/microrhododb_v1.6.0.sqlite"
DEST = "releases/v1.6.0/db/microrhododb_v1.6.0.sqlite"


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
    mirror = tmp_path / "mirror" / "v1.6.0"
    mirror.mkdir(parents=True)
    (mirror / "microrhododb_v1.6.0.sqlite").write_bytes(b"not the database")
    r = run(repo, "--base-url", (tmp_path / "mirror").as_uri())
    assert r.returncode == 2 and "BLOCKED_DATA_SOURCE" in r.stderr and "sha256" in r.stderr
    assert not (repo / DEST).exists()


def test_verified_download(tmp_path):
    repo = fake_repo(tmp_path)
    mirror = tmp_path / "mirror" / "v1.6.0"
    mirror.mkdir(parents=True)
    os.symlink(DB, mirror / "microrhododb_v1.6.0.sqlite")
    r = run(repo, "--base-url", (tmp_path / "mirror").as_uri())
    assert r.returncode == 0 and "downloaded and verified" in r.stdout
    assert hashlib.sha256((repo / DEST).read_bytes()).hexdigest() == \
        "379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f"
