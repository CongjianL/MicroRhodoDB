#!/usr/bin/env python3
"""Fetch the official MicroRhodoDB SQLite database from the GitHub Release and verify its SHA-256.

The expected size and SHA-256 are read from BINARIES.md (the committed source of truth), never from the
download itself. Exit codes:
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
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE = "https://github.com/CongjianL/MicroRhodoDB/releases/download"


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
    try:
        try:
            with urllib.request.urlopen(url, timeout=a.timeout) as r, open(tmp, "wb") as f:
                for blk in iter(lambda: r.read(1 << 20), b""):
                    f.write(blk)
        except urllib.error.HTTPError as e:
            return blocked(f"{url}: HTTP {e.code} (Release {a.tag} or asset {a.asset} not published)")
        except (urllib.error.URLError, OSError) as e:
            return blocked(f"{url}: {e}")
        got, n = sha256(tmp), tmp.stat().st_size
        if got != want or n != size:
            return blocked(f"{url}: sha256 {got} ({n} bytes) != BINARIES.md {want} ({size} bytes)")
        os.replace(tmp, dest)
        print(f"OK (downloaded and verified): {a.dest} sha256 {got}")
        return 0
    finally:
        if tmp.exists():
            tmp.unlink()


if __name__ == "__main__":
    sys.exit(main())
