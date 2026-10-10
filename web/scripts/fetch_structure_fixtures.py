#!/usr/bin/env python3
"""Download real structure files used as Playwright network mocks (PR-3).

The E2E tests intercept requests to models.rcsb.org, files.rcsb.org and alphafold.ebi.ac.uk
and answer them with these committed files, so CI does not depend on external services.
A separate @live smoke test exercises the real endpoints.

Usage:  python web/scripts/fetch_structure_fixtures.py [--check]
  --check   verify the committed files against SHA256SUMS without downloading.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "structures"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

FIXTURES = {
    # MRDB000001 / P02945 default (representative) entry, BinaryCIF then mmCIF fallback
    "5zim.bcif": "https://models.rcsb.org/v1/5zim/full?encoding=bcif",
    "5ZIM.cif": "https://files.rcsb.org/download/5ZIM.cif",
    # MRDB000001 / B0R5N9 (union-only entry)
    "4y9h.bcif": "https://models.rcsb.org/v1/4y9h/full?encoding=bcif",
    # AlphaFold DB models (pLDDT in B-factor, 0-100)
    "AF-P02945-F1-model_v6.pdb": "https://alphafold.ebi.ac.uk/files/AF-P02945-F1-model_v6.pdb",
    "AF-Q5V4H7-F1-model_v6.pdb": "https://alphafold.ebi.ac.uk/files/AF-Q5V4H7-F1-model_v6.pdb",
}


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    sums = OUT / "SHA256SUMS"
    if a.check:
        bad = 0
        for line in sums.read_text().splitlines():
            h, name = line.split(maxsplit=1)
            ok = (OUT / name).exists() and sha256(OUT / name) == h
            bad += not ok
            print(("OK   " if ok else "FAIL ") + name)
        return 1 if bad else 0
    OUT.mkdir(parents=True, exist_ok=True)
    lines = []
    for name, url in FIXTURES.items():
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        (OUT / name).write_bytes(data)
        lines.append(f"{hashlib.sha256(data).hexdigest()}  {name}")
        print(f"{name}: {len(data)} bytes from {url}")
    sums.write_text("\n".join(lines) + "\n")
    (OUT / "SOURCES.txt").write_text(
        "Real structure files served by the Playwright network mocks (tests/e2e/record.spec.ts).\n"
        "Downloaded by web/scripts/fetch_structure_fixtures.py; PDB data CC0 (wwPDB), AlphaFold DB CC BY 4.0.\n\n"
        + "\n".join(f"{n}\t{u}" for n, u in FIXTURES.items()) + "\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
