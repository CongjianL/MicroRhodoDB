#!/usr/bin/env python3
"""PR-4 performance audit (Phylogeny explorer and Clade Explorer pages).

Same method as scripts/pr2_perf_audit.py / pr3_perf_audit.py (static server, Playwright Chromium,
cold cache per run, 1440x900, exact bytes per requested file with gzip -9), using the "pr4" route
set of scripts/perf_capture.mjs, which adds timed explorer interactions (layout switch, colour
mode, support markers on 469 branches, collapse/expand all, zoom).

Timings come from a loopback server without throttling; they are relative, not field latency.

Usage: python scripts/pr4_perf_audit.py --out ../docs/website/pr4 [--runs 5] [--baseline ../docs/website/pr3/perf_audit.json]
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pr2_perf_audit import BASE, DATA, DIST, HEAVY, WEB, sizes, wait_up  # noqa: E402
from pr3_perf_audit import MOL, file_rows, med, totals  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--baseline", default=str(WEB.parent / "docs" / "website" / "pr3" / "perf_audit.json"))
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not (DIST / "index.html").exists() or not DATA.exists():
        sys.exit("run `npm run build` and the exporter first")

    raw_capture = WEB / "test-results" / "perf_capture_pr4.json"
    raw_capture.parent.mkdir(parents=True, exist_ok=True)
    server = subprocess.Popen([sys.executable, str(WEB / "scripts" / "serve_e2e.py")], cwd=WEB)
    try:
        wait_up(BASE)
        subprocess.run(["node", "scripts/perf_capture.mjs", BASE, str(a.runs), str(raw_capture), "pr4"], cwd=WEB, check=True)
    finally:
        server.terminate()
        server.wait(timeout=10)
    cap = json.loads(raw_capture.read_text())

    base = {}
    if Path(a.baseline).exists():
        base = {r["id"]: r for r in json.loads(Path(a.baseline).read_text())["routes"]}

    routes = []
    for r in cap["routes"]:
        runs = r["runs"]
        files = file_rows([u for run in runs for u in run["requests"]])
        data_rel = [f["file"][len("data/v1.6.0/"):] for f in files.values() if f["file"].startswith("data/v1.6.0/")]
        row = {
            "id": r["id"], "hash": r["hash"],
            "files": sorted(files.values(), key=lambda f: (-f["raw"], f["file"])),
            "totals": totals(files),
            "molstar_chunk_loaded": any(MOL.search(f) for f in files),
            "heavy_data_files": sorted(x for x in data_rel if any(re.match(h, x) for h in HEAVY)),
            "timing_ms_median": {"fcp": med(x["fcp"] for x in runs), "dom_content_loaded": med(x["dcl"] for x in runs),
                                 "load": med(x["load"] for x in runs), "ready": med(x["readyMs"] for x in runs)},
            "timing_ms_ready_all_runs": [round(x["readyMs"], 1) for x in runs],
            "console_errors": sum(len(x["errors"]) for x in runs),
            "contrast": r["contrast"],
            "contrast_failures": [c for c in (r["contrast"] or []) if c["ratio"] < c["need"]],
        }
        if runs and runs[0].get("interactions"):
            names = [s["name"] for s in runs[0]["interactions"]]
            row["interactions_ms"] = {
                n: {"median": med(next(s["ms"] for s in run["interactions"] if s["name"] == n) for run in runs),
                    "max": max(next(s["ms"] for s in run["interactions"] if s["name"] == n) for run in runs),
                    "all_runs": [next(s["ms"] for s in run["interactions"] if s["name"] == n) for run in runs]}
                for n in names
            }
        b = base.get(r["id"])
        if b:
            bt = b.get("totals_before_viewer") or b.get("totals")
            row["pr3_baseline"] = {"total_gzip": bt["all"]["gzip"], "ready_ms_median": b["timing_ms_median"]["ready"]}
        routes.append(row)

    chunks = []
    for p in sorted((DIST / "assets").iterdir()):
        raw, gz = sizes(p)
        chunks.append({"file": "assets/" + p.name, "raw": raw, "gzip": gz})

    report = {
        "generated_by": "web/scripts/pr4_perf_audit.py",
        "environment": {
            "machine": f"{platform.system()} {platform.machine()}, {os.cpu_count()} logical CPUs (sandbox)",
            "python": platform.python_version(), "browser": f"Chromium {cap['env']['chromium']} (Playwright headless)",
            "server": "scripts/serve_e2e.py (loopback, no compression, Cache-Control: no-store)",
            "viewport": "1440x900", "runs_per_route": a.runs, "cache": "cold (new browser context per run)", "throttling": "none",
        },
        "routes": routes, "chunks": chunks,
    }
    (out / "perf_audit.json").write_text(json.dumps(report, indent=1) + "\n")

    kb = lambda n: f"{n / 1024:,.1f}"  # noqa: E731
    md = ["# PR-4 performance audit (Phylogeny explorer and Clade Explorer)", "",
          "Generated by `web/scripts/pr4_perf_audit.py` (method as in PR-2/PR-3). Bytes are exact for the files each route requested; "
          "gzip -9 sizes are computed because GitHub Pages serves gzip and the local server does not. Timings are medians of "
          "cold-cache runs on a loopback server without throttling: relative, not field latency.", "", "## Environment", ""]
    md += [f"- {k}: {v}" for k, v in report["environment"].items()]
    md += ["", "## Page load, KiB", "",
           "| Route | JS raw / gzip | Data raw / gzip | Total raw / gzip | PR-3 total gzip | Mol* chunk | Heavy data files | Ready ms (median) | PR-3 ready ms |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in routes:
        t = r["totals"]
        b = r.get("pr3_baseline")
        md.append(f"| `{r['hash']}` | {kb(t['js']['raw'])} / {kb(t['js']['gzip'])} | {kb(t['data']['raw'])} / {kb(t['data']['gzip'])} | "
                  f"{kb(t['all']['raw'])} / {kb(t['all']['gzip'])} | {kb(b['total_gzip']) if b else 'n/a'} | "
                  f"{'yes' if r['molstar_chunk_loaded'] else 'no'} | {', '.join(r['heavy_data_files']) or 'none'} | "
                  f"{r['timing_ms_median']['ready']} | {b['ready_ms_median'] if b else 'n/a'} |")
    md += ["", "## Explorer interactions on the full 472-tip tree (ms, click to painted)", "", "| Interaction | Median | Max | All runs |", "|---|---|---|---|"]
    for r in routes:
        for n, v in (r.get("interactions_ms") or {}).items():
            md.append(f"| {n} | {v['median']} | {v['max']} | {', '.join(map(str, v['all_runs']))} |")
    md += ["", "## Data files requested per route", ""]
    for r in routes:
        df = [f for f in r["files"] if f["kind"] == "data"]
        md.append(f"- `{r['hash']}`: " + ", ".join(f"{f['file'][len('data/v1.6.0/'):]} ({kb(f['raw'])})" for f in df))
    md += ["", "## JS/CSS chunks (KiB)", "", "| File | Raw | gzip |", "|---|---|---|"]
    md += [f"| `{c['file']}` | {kb(c['raw'])} | {kb(c['gzip'])} |" for c in chunks]
    md += ["", "## WCAG 2.1 text contrast (computed styles of HTML text, 1440 px; SVG text not scanned)", "",
           "| Route | Distinct colour pairs | Text nodes | Minimum ratio | Pairs below AA |", "|---|---|---|---|---|"]
    for r in routes:
        c = r["contrast"]
        if c:
            md.append(f"| `{r['hash']}` | {len(c)} | {sum(x['count'] for x in c)} | {min(x['ratio'] for x in c)} | {len(r['contrast_failures'])} |")
    (out / "perf_audit.md").write_text("\n".join(md) + "\n")
    fails = sum(len(r["contrast_failures"]) for r in routes)
    errs = sum(r["console_errors"] for r in routes)
    mol = [r["id"] for r in routes if r["molstar_chunk_loaded"]]
    print(f"wrote {out / 'perf_audit.json'} and perf_audit.md; contrast failures={fails}; console errors={errs}; Mol* loaded on={mol}")


if __name__ == "__main__":
    main()
