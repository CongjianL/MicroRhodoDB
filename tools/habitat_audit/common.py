"""Shared paths, frozen-baseline constants and small deterministic helpers."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DB_PATH = REPO / "releases" / "v1.6.0" / "db" / "microrhododb_v1.6.0.sqlite"
DB_SHA256 = "379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f"
BASE_COMMIT = "932eb567a199f9eef25f7e04ac2aaa745e17156c"
OUT_DIR = REPO / "docs" / "website" / "pr7c1"
FIXTURE_DIR = REPO / "tests" / "data" / "pr7c1"
EXPORTER = REPO / "tools" / "export_web_data.py"
WEB_EXPORT = REPO / "web" / "public" / "data" / "v1.6.0"
RELEASE_BLOCKERS = REPO / "docs" / "website" / "release_blockers.json"

# Repository-relative defaults (gitignored work/ directory); override the cache with MRDB_HABITAT_CACHE
# or --cache. No absolute machine-specific path is hardcoded (PR-7c.1a portability fix).
WORK_ROOT = REPO / "work"
DEFAULT_CACHE = Path(os.environ.get("MRDB_HABITAT_CACHE") or (WORK_ROOT / "habitat_cache"))
WORK_DIR = Path(os.environ.get("MRDB_HABITAT_WORK") or (WORK_ROOT / "pr7c1_work"))

N_RECORDS = 5466
N_COUNTED = 5460
N_ENGINEERED = 6
N_MRDB = 5299

SEED_ACCS = (
    "P02945", "P0DMH7", "P0DMH8", "P42196", "Q9F7P4", "Q2S2F8", "N0DKS8", "W8VZW3",
    "Q8RUT8", "H2EZZ6", "A0ACD6B968", "A0A060H1D7", "A0A089ZH82", "A0A0W0GG67", "A0A143YUX7",
)

HOST_STATUSES = ("REPORTED", "AMBIGUOUS", "NOT_REPORTED", "LOOKUP_FAILED", "NOT_SEARCHED")
AMBIGUITY_CLASSES = ("FORMATTING_ONLY", "NESTED_WORDING", "DISTINCT_SAME_SAMPLE", "DISTINCT_ACROSS_SAMPLES",
                     "LITERATURE_VS_DATABASE")
GRADES = (
    "DIRECT_SAMPLE", "VERIFIED_ISOLATE", "ORGANISM_CONTEXT_ONLY", "AMBIGUOUS",
    "NOT_REPORTED", "LOOKUP_FAILED", "NOT_SEARCHED",
)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def open_db_ro(path: Path = DB_PATH) -> sqlite3.Connection:
    """Open the frozen release DB strictly read-only (immutable URI)."""
    con = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    con.row_factory = sqlite3.Row
    return con


def pilot_order_key(acc: str) -> str:
    return hashlib.sha256((acc + "pr7c1").encode()).hexdigest()


def write_tsv(path: Path, header: list[str], rows: list[list]) -> None:
    """Deterministic TSV: LF line endings, no quoting surprises, None -> ''."""
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    w.writerow(header)
    for r in rows:
        w.writerow(["" if v is None else _cell(v) for v in r])
    path.write_text(buf.getvalue(), encoding="utf-8")


def _cell(v) -> str:
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        return f"{v:.4f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))
    s = str(v)
    # tabs/newlines inside source values are collapsed so the TSV stays one-record-per-line
    return re.sub(r"[\t\r\n]+", " ", s)


def read_tsv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def dump_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


PHYLUM_RE = re.compile(r"([^,]+?) \(phylum\)")


def phylum_from_lineage(lineage: str | None) -> str | None:
    if not lineage:
        return None
    m = PHYLUM_RE.search(lineage)
    return m.group(1).strip() if m else None
