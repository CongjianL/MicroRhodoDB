#!/usr/bin/env python3
"""PR-2 performance and contrast audit.

Builds nothing; expects `npm run build` and the PR-1 export (web/public/data) to exist.
1. Starts scripts/serve_e2e.py (same static layout as the E2E tests, base /MicroRhodoDB/site/).
2. Runs scripts/perf_capture.mjs (Playwright Chromium, cold cache per run, 1440x900).
3. Maps every requested URL to its file on disk and reports raw bytes and gzip -9 bytes
   (GitHub Pages serves gzip; the local test server does not compress, so gzip is computed).
4. Writes JSON (machine-readable) and Markdown tables.

Timings come from a local loopback server with no network throttling: they measure client-side
parse/render cost on this machine, not real-world latency. Byte counts are the portable result.

Usage: python scripts/pr2_perf_audit.py --out ../docs/website/pr2 [--runs 5]
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

WEB = Path(__file__).resolve().parent.parent
DIST = WEB / "dist" / "site"
DATA = WEB / "public" / "data"
BASE = "http://127.0.0.1:4173/MicroRhodoDB/site/"
HEAVY = [r"^records-index\.json$", r"^accessions\.json$", r"^records/", r"^sequences/",
         r"^publications\.json$", r"^structures-index\.json$", r"^evidence-index\.json$"]


def local_file(url: str) -> Path | None:
    path = urlparse(url).path
    if path in ("/MicroRhodoDB/site/", "/MicroRhodoDB/site"):
        return DIST / "index.html"
    m = re.match(r"^/MicroRhodoDB/site/(.+)$", path)
    if not m:
        return None
    rel = m.group(1)
    if rel.startswith("data/"):
        return DATA / rel[len("data/"):]
    return DIST / rel


def sizes(p: Path) -> tuple[int, int]:
    b = p.read_bytes()
    return len(b), len(gzip.compress(b, compresslevel=9, mtime=0))


def kind(rel: str) -> str:
    if rel.startswith("data/"):
        return "data"
    if rel.endswith(".js"):
        return "js"
    if rel.endswith(".css"):
        return "css"
    return "other"


def wait_up(url: str, timeout: float = 20) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            urllib.request.urlopen(url, timeout=2).read()
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"server did not start: {url}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--runs", type=int, default=5)
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not (DIST / "index.html").exists() or not DATA.exists():
        sys.exit("run `npm run build` and the PR-1 exporter first")

    raw_capture = WEB / "test-results" / "perf_capture.json"
    raw_capture.parent.mkdir(parents=True, exist_ok=True)
    server = subprocess.Popen([sys.executable, str(WEB / "scripts" / "serve_e2e.py")], cwd=WEB)
    try:
        wait_up(BASE)
        subprocess.run(["node", "scripts/perf_capture.mjs", BASE, str(a.runs), str(raw_capture)], cwd=WEB, check=True)
    finally:
        server.terminate()
        server.wait(timeout=10)
    cap = json.loads(raw_capture.read_text())

    routes = []
    for r in cap["routes"]:
        files: dict[str, dict] = {}
        for run in r["runs"]:
            for u in run["requests"]:
                p = local_file(u)
                if p is None or not p.is_file():
                    continue
                rel = str(p.relative_to(DIST)) if p.is_relative_to(DIST) else "data/" + str(p.relative_to(DATA))
                if rel not in files:
                    raw, gz = sizes(p)
                    files[rel] = {"file": rel, "kind": kind(rel), "raw": raw, "gzip": gz}
        tot = {k: {"raw": sum(f["raw"] for f in files.values() if f["kind"] == k),
                   "gzip": sum(f["gzip"] for f in files.values() if f["kind"] == k)}
               for k in ("js", "css", "data", "other")}
        tot["all"] = {"raw": sum(f["raw"] for f in files.values()), "gzip": sum(f["gzip"] for f in files.values())}
        data_rel = [f["file"][len("data/v1.6.0/"):] for f in files.values() if f["file"].startswith("data/v1.6.0/")]
        heavy = sorted(x for x in data_rel if any(re.match(h, x) for h in HEAVY))
        med = lambda key: round(statistics.median(x[key] for x in r["runs"] if x[key] is not None), 1) if any(x[key] is not None for x in r["runs"]) else None
        routes.append({
            "id": r["id"], "hash": r["hash"], "ready_selector": r["ready"],
            "files": sorted(files.values(), key=lambda f: (-f["raw"], f["file"])),
            "totals": tot, "heavy_data_files": heavy,
            "n_record_files": sum(1 for x in data_rel if x.startswith("records/")),
            "timing_ms_median": {"fcp": med("fcp"), "dom_content_loaded": med("dcl"), "load": med("load"),
                                 "ready": med("readyMs"), "secondary_ready": med("alsoMs")},
            "timing_ms_ready_all_runs": [round(x["readyMs"], 1) for x in r["runs"]],
            "console_errors": sum(len(x["errors"]) for x in r["runs"]),
            "contrast": r["contrast"],
            "contrast_failures": [c for c in r["contrast"] if c["ratio"] < c["need"]],
        })

    chunks = []
    for p in sorted((DIST / "assets").iterdir()):
        raw, gz = sizes(p)
        chunks.append({"file": "assets/" + p.name, "raw": raw, "gzip": gz})
    full_db = sum(sizes(p)[0] for p in (DATA / "v1.6.0").rglob("*") if p.is_file())
    legacy = WEB.parent / "site" / "data.js"
    legacy_sizes = sizes(legacy) if legacy.exists() else None

    report = {
        "generated_by": "web/scripts/pr2_perf_audit.py",
        "environment": {
            "machine": f"{platform.system()} {platform.machine()}, {os.cpu_count()} logical CPUs (sandbox)",
            "python": platform.python_version(), "browser": f"Chromium {cap['env']['chromium']} (Playwright headless)",
            "server": "scripts/serve_e2e.py (Python ThreadingHTTPServer, loopback, no compression, Cache-Control: no-store)",
            "viewport": "1440x900", "runs_per_route": a.runs, "cache": "cold (new browser context per run)",
            "throttling": "none",
        },
        "routes": routes, "chunks": chunks,
        "export_total_raw_bytes": full_db,
        "legacy_data_js": {"raw": legacy_sizes[0], "gzip": legacy_sizes[1]} if legacy_sizes else None,
    }
    (out / "perf_audit.json").write_text(json.dumps(report, indent=1) + "\n")

    kb = lambda n: f"{n / 1024:,.1f}"
    md = ["# PR-2 performance and contrast audit", "",
          "Generated by `web/scripts/pr2_perf_audit.py`. Byte counts are exact for the files each route requested; "
          "gzip sizes are computed with gzip -9 (GitHub Pages serves gzip, the local test server does not). "
          "Timings: local loopback server, no throttling, medians of cold-cache runs; they are relative, not field latency.", "",
          "## Environment", ""]
    md += [f"- {k}: {v}" for k, v in report["environment"].items()]
    md += ["", "## Transfer per route (KiB)", "",
           "| Route | JS raw / gzip | CSS raw / gzip | Data raw / gzip | Total raw / gzip | Record files | Heavy data files |",
           "|---|---|---|---|---|---|---|"]
    for r in routes:
        t = r["totals"]
        md.append(f"| `{r['hash']}` | {kb(t['js']['raw'])} / {kb(t['js']['gzip'])} | {kb(t['css']['raw'])} / {kb(t['css']['gzip'])} | "
                  f"{kb(t['data']['raw'])} / {kb(t['data']['gzip'])} | {kb(t['all']['raw'])} / {kb(t['all']['gzip'])} | "
                  f"{r['n_record_files']} | {', '.join(r['heavy_data_files']) or 'none'} |")
    if legacy_sizes:
        md += ["", f"Reference: legacy monolithic `site/data.js` = {kb(legacy_sizes[0])} KiB raw / {kb(legacy_sizes[1])} KiB gzip, "
                   f"loaded on every legacy page. Full PR-1 export on disk = {kb(full_db)} KiB raw (never downloaded as a whole)."]
    md += ["", "## Timing per route (ms, median)", "",
           "| Route | FCP | DOMContentLoaded | load | Ready element | Ready (all runs) |", "|---|---|---|---|---|---|"]
    for r in routes:
        t = r["timing_ms_median"]
        ready = f"{t['ready']}" + (f" (tree drawn {t['secondary_ready']})" if t["secondary_ready"] else "")
        md.append(f"| `{r['hash']}` | {t['fcp']} | {t['dom_content_loaded']} | {t['load']} | {ready} | {', '.join(map(str, r['timing_ms_ready_all_runs']))} |")
    md += ["", "## Data files requested per route", ""]
    for r in routes:
        df = [f for f in r["files"] if f["kind"] == "data"]
        md.append(f"- `{r['hash']}`: " + ", ".join(f"{f['file'][len('data/v1.6.0/'):] if f['file'].startswith('data/v1.6.0/') else f['file']} ({kb(f['raw'])})" for f in df))
    md += ["", "## JS/CSS chunks (KiB)", "", "| File | Raw | gzip |", "|---|---|---|"]
    md += [f"| `{c['file']}` | {kb(c['raw'])} | {kb(c['gzip'])} |" for c in chunks]
    md += ["", "## WCAG 2.1 text contrast (computed styles, 1440 px)", "",
           "Every visible HTML text node was checked against the first opaque ancestor background "
           "(SVG/canvas chart text is excluded). AA thresholds: 4.5:1 normal, 3:1 large text.", "",
           "| Route | Distinct colour pairs | Text nodes | Minimum ratio | Pairs below AA |", "|---|---|---|---|---|"]
    for r in routes:
        c = r["contrast"]
        md.append(f"| `{r['hash']}` | {len(c)} | {sum(x['count'] for x in c)} | {min(x['ratio'] for x in c)} | {len(r['contrast_failures'])} |")
    allpairs: dict[str, dict] = {}
    for r in routes:
        for c in r["contrast"]:
            allpairs.setdefault(f"{c['fg']}|{c['bg']}|{c['large']}", c)
    md += ["", "Lowest-contrast colour pairs across all routes:", "", "| Foreground | Background | Large text | Ratio | Required | Sample |", "|---|---|---|---|---|---|"]
    for c in sorted(allpairs.values(), key=lambda x: x["ratio"])[:12]:
        md.append(f"| {c['fg']} | {c['bg']} | {c['large']} | {c['ratio']} | {c['need']} | {c['sample'].replace('|', '/')} |")
    (out / "perf_audit.md").write_text("\n".join(md) + "\n")
    fails = sum(len(r["contrast_failures"]) for r in routes)
    errs = sum(r["console_errors"] for r in routes)
    print(f"wrote {out / 'perf_audit.json'} and perf_audit.md; contrast failures={fails}; console errors={errs}")


if __name__ == "__main__":
    main()
