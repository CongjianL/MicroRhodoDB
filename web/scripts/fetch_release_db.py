#!/usr/bin/env python3
"""Fetch the official MicroRhodoDB SQLite database from the GitHub Release and verify its SHA-256.

The expected size and SHA-256 are read from BINARIES.md (the committed source of truth), never from the
download itself.

While the repository is private, GitHub refuses anonymous Release downloads (HTTP 404). On HTTP 401/403/404
the script therefore retries with the GitHub CLI (`gh release download`, authenticated with `gh auth login`),
and verifies that copy the same way. Set MRDB_GH to the gh executable to use (default: gh on PATH).
Exit codes:
    0  database present and verified (already in place, or downloaded and verified)
    2  BLOCKED_DATA_SOURCE: Release/asset missing (e.g. HTTP 404), network failure, or checksum/size mismatch

    python web/scripts/fetch_release_db.py                      # v1.6.0 into releases/v1.6.0/db/
    python web/scripts/fetch_release_db.py --base-url file:///some/mirror   # tests / mirrors
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GH_REPO = "CongjianL/MicroRhodoDB"
DEFAULT_BASE = f"https://github.com/{GH_REPO}/releases/download"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def expected_from_binaries(binaries: Path, rel_path: str):
    pat = re.compile(r"^\|\s*`(?P<path>[^`]+)`\s*\|\s*(?P<bytes>\d+)\s*\|\s*`(?P<sha>[0-9a-f]{64})`\s*\|\s*$")
    for line in binaries.read_text().splitlines():
        m = pat.match(line)
        if m and m["path"] == rel_path:
            return int(m["bytes"]), m["sha"]
    raise SystemExit(f"BLOCKED_DATA_SOURCE: {rel_path} not listed in {binaries}")


def gh_download(tag: str, asset: str, into: Path):
    """Download one Release asset with the authenticated GitHub CLI into the directory `into`.
    Returns (path, None) on success or (None, reason)."""
    gh = os.environ.get("MRDB_GH") or shutil.which("gh")
    if not gh:
        return None, "GitHub CLI (gh) not found"
    r = subprocess.run([gh, "release", "download", tag, "-R", GH_REPO, "--pattern", asset, "-D", str(into)],
                       capture_output=True, text=True)
    got = into / asset
    if r.returncode != 0 or not got.is_file():
        msg = (r.stderr or r.stdout).strip() or f"exit {r.returncode}"
        msg = re.sub(r"\?[^\s\"']*", "?...", msg)   # drop signed query strings (sig=, jwt=) of asset URLs
        return None, f"gh release download failed: {msg}"
    return got, None


def blocked(msg: str) -> int:
    print(f"BLOCKED_DATA_SOURCE: {msg}", file=sys.stderr)
    return 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=str(ROOT))
    ap.add_argument("--tag", default="v1.6.0")
    ap.add_argument("--asset", default="microrhododb_v1.6.0.sqlite")
    ap.add_argument("--dest", default="releases/v1.6.0/db/microrhododb_v1.6.0.sqlite",
                    help="destination relative to --repo (must be listed in BINARIES.md)")
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument("--timeout", type=float, default=120)
    a = ap.parse_args(argv)
    repo = Path(a.repo)
    size, want = expected_from_binaries(repo / "BINARIES.md", a.dest)
    dest = repo / a.dest
    if dest.is_file():
        got = sha256(dest)
        if got == want and dest.stat().st_size == size:
            print(f"OK (already present): {a.dest} sha256 {got}")
            return 0
        return blocked(f"existing {a.dest} has sha256 {got}, expected {want}; refusing to overwrite")
    url = f"{a.base_url.rstrip('/')}/{a.tag}/{a.asset}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".fetch-", dir=dest.parent)
    os.close(fd)
    tmp = Path(tmp)
    ghdir = None
    try:
        source = url
        try:
            with urllib.request.urlopen(url, timeout=a.timeout) as r, open(tmp, "wb") as f:
                for blk in iter(lambda: r.read(1 << 20), b""):
                    f.write(blk)
        except urllib.error.HTTPError as e:
            if e.code not in (401, 403, 404):
                return blocked(f"{url}: HTTP {e.code}")
            # 404 also means "private repository" for anonymous requests: retry authenticated with gh
            ghdir = Path(tempfile.mkdtemp(prefix=".fetch-gh-", dir=dest.parent))
            got_path, why = gh_download(a.tag, a.asset, ghdir)
            if got_path is None:
                return blocked(f"{url}: HTTP {e.code}. Either Release {a.tag} has no asset {a.asset}, or the "
                               f"repository {GH_REPO} is private and refuses anonymous downloads. Retry with the "
                               f"GitHub CLI also failed ({why}); run `gh auth login` with an account that can read "
                               f"the repository and try again")
            os.replace(got_path, tmp)
            source = f"gh release download {a.tag} -R {GH_REPO} ({a.asset})"
        except (urllib.error.URLError, OSError) as e:
            return blocked(f"{url}: {e}")
        got, n = sha256(tmp), tmp.stat().st_size
        if got != want or n != size:
            return blocked(f"{source}: sha256 {got} ({n} bytes) != BINARIES.md {want} ({size} bytes)")
        os.replace(tmp, dest)
        print(f"OK (downloaded and verified): {a.dest} sha256 {got}" + ("" if source == url else " via gh"))
        return 0
    finally:
        if tmp.exists():
            tmp.unlink()
        if ghdir is not None:
            shutil.rmtree(ghdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
