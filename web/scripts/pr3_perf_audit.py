#!/usr/bin/env python3
"""PR-3 performance audit (Protein Entry page and structure viewer).

Same method as scripts/pr2_perf_audit.py (static server, Playwright Chromium, cold cache per run,
1440x900, exact bytes per requested file with gzip -9), using the "pr3" route set of
scripts/perf_capture.mjs, which adds record types and structure-viewer timings:

- bytes requested before the viewer is started (the Mol* chunk must not be among them);
- bytes requested after "Load 3D viewer" (Mol* chunk + coordinates);
- click-to-rendered time with RCSB / AlphaFold DB answered from committed fixtures ("mocked"),
  and optionally over the network ("live", set PERF_LIVE=1).

Timings come from a loopback server without throttling; they are relative, not field latency.

Usage: python scripts/pr3_perf_audit.py --out ../docs/website/pr3 [--runs 5] [--baseline ../docs/website/pr2/perf_audit.json]
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pr2_perf_audit import BASE, DATA, DIST, HEAVY, WEB, kind, local_file, sizes, wait_up  # noqa: E402

MOL = re.compile(r"assets/molstarViewer-[^/]+\.js$")


def file_rows(urls: list[str]) -> dict[str, dict]:
    files: dict[str, dict] = {}
    for u in urls:
        p = local_file(u)
        if p is None or not p.is_file():
            continue
        rel = str(p.relative_to(DIST)) if p.is_relative_to(DIST) else "data/" + str(p.relative_to(DATA))
        if rel not in files:
            raw, gz = sizes(p)
            files[rel] = {"file": rel, "kind": kind(rel), "raw": raw, "gzip": gz}
    return files


def totals(files: dict[str, dict]) -> dict:
    t = {k: {"raw": sum(f["raw"] for f in files.values() if f["kind"] == k),
             "gzip": sum(f["gzip"] for f in files.values() if f["kind"] == k)} for k in ("js", "css", "data", "other")}
    t["all"] = {"raw": sum(f["raw"] for f in files.values()), "gzip": sum(f["gzip"] for f in files.values())}
    return t


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--baseline", default=str(WEB.parent / "docs" / "website" / "pr2" / "perf_audit.json"))
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not (DIST / "index.html").exists() or not DATA.exists():
        sys.exit("run `npm run build` and the exporter first")

    raw_capture = WEB / "test-results" / "perf_capture_pr3.json"
    raw_capture.parent.mkdir(parents=True, exist_ok=True)
    server = subprocess.Popen([sys.executable, str(WEB / "scripts" / "serve_e2e.py")], cwd=WEB)
    try:
        wait_up(BASE)
        subprocess.run(["node", "scripts/perf_capture.mjs", BASE, str(a.runs), str(raw_capture), "pr3"], cwd=WEB, check=True)
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
        if r["viewer"]:
            before = file_rows([u for run in runs for u in run["viewer"]["requestsBeforeClick"]])
            allf = file_rows([u for run in runs for u in run["requests"]])
        else:
            before = allf = file_rows([u for run in runs for u in run["requests"]])
        after = {k: v for k, v in allf.items() if k not in before}
        data_rel = [f["file"][len("data/v1.6.0/"):] for f in before.values() if f["file"].startswith("data/v1.6.0/")]
        row = {
            "id": r["id"], "hash": r["hash"], "viewer": r["viewer"],
            "files_before_viewer": sorted(before.values(), key=lambda f: (-f["raw"], f["file"])),
            "totals_before_viewer": totals(before),
            "molstar_chunk_before_viewer": any(MOL.search(f) for f in before),
            "heavy_data_files": sorted(x for x in data_rel if any(re.match(h, x) for h in HEAVY)),
            "timing_ms_median": {"fcp": med(x["fcp"] for x in runs), "dom_content_loaded": med(x["dcl"] for x in runs),
                                 "load": med(x["load"] for x in runs), "ready": med(x["readyMs"] for x in runs)},
            "timing_ms_ready_all_runs": [round(x["readyMs"], 1) for x in runs],
            "console_errors": sum(len(x["errors"]) for x in runs),
            "contrast": r["contrast"],
            "contrast_failures": [c for c in (r["contrast"] or []) if c["ratio"] < c["need"]],
        }
        if r["viewer"]:
            ext = {}
            for run in runs:
                for e in run["viewer"]["external"]:
                    ext.setdefault(e["url"], e)
            row["viewer_result"] = {
                "mode": r["viewer"],
                "phases": [run["viewer"]["phase"] for run in runs],
                "click_to_ready_ms_median": med(run["viewer"]["clickToReadyMs"] for run in runs),
                "click_to_ready_ms_all_runs": [run["viewer"]["clickToReadyMs"] for run in runs],
                "files_after_click": sorted(after.values(), key=lambda f: (-f["raw"], f["file"])),
                "totals_after_click_local": totals(after),
                "external_responses": list(ext.values()),
                "status_last_run": runs[-1]["viewer"]["status"],
                "phase_transitions_ms": [run["viewer"]["phases"] for run in runs],
                "init_ms_median": med(next((t for ph, t in run["viewer"]["phases"] if ph == "loading"), None) for run in runs),
            }
        b = base.get(r["id"])
        if b:
            row["pr2_baseline"] = {"totals": b["totals"], "ready_ms_median": b["timing_ms_median"]["ready"],
                                   "files": sorted(f["file"] for f in b["files"])}
        routes.append(row)

    chunks = []
    for p in sorted((DIST / "assets").iterdir()):
        raw, gz = sizes(p)
        chunks.append({"file": "assets/" + p.name, "raw": raw, "gzip": gz})

    report = {
        "generated_by": "web/scripts/pr3_perf_audit.py",
        "environment": {
            "machine": f"{platform.system()} {platform.machine()}, {os.cpu_count()} logical CPUs (sandbox)",
            "python": platform.python_version(), "browser": f"Chromium {cap['env']['chromium']} (Playwright headless, SwiftShader WebGL)",
            "server": "scripts/serve_e2e.py (loopback, no compression, Cache-Control: no-store)",
            "viewport": "1440x900", "runs_per_route": a.runs, "cache": "cold (new browser context per run)", "throttling": "none",
            "live_viewer_runs": bool(os.environ.get("PERF_LIVE")),
        },
        "routes": routes, "chunks": chunks,
    }
    (out / "perf_audit.json").write_text(json.dumps(report, indent=1) + "\n")

    kb = lambda n: f"{n / 1024:,.1f}"
    md = ["# PR-3 performance audit (Protein Entry and structure viewer)", "",
          "Generated by `web/scripts/pr3_perf_audit.py` (method as in PR-2). Bytes are exact for the files each route requested; "
          "gzip -9 sizes are computed because GitHub Pages serves gzip and the local server does not. Timings are medians of "
          "cold-cache runs on a loopback server without throttling: relative, not field latency.", "", "## Environment", ""]
    md += [f"- {k}: {v}" for k, v in report["environment"].items()]
    md += ["", "## Page load (before any viewer interaction), KiB", "",
           "| Route | JS raw / gzip | Data raw / gzip | Total raw / gzip | PR-2 total gzip | Mol* chunk loaded | Ready ms (median) | PR-2 ready ms |",
           "|---|---|---|---|---|---|---|---|"]
    for r in routes:
        if r["viewer"]:
            continue
        t = r["totals_before_viewer"]
        b = r.get("pr2_baseline")
        md.append(f"| `{r['hash']}` | {kb(t['js']['raw'])} / {kb(t['js']['gzip'])} | {kb(t['data']['raw'])} / {kb(t['data']['gzip'])} | "
                  f"{kb(t['all']['raw'])} / {kb(t['all']['gzip'])} | {kb(b['totals']['all']['gzip']) if b else 'n/a'} | "
                  f"{'yes' if r['molstar_chunk_before_viewer'] else 'no'} | {r['timing_ms_median']['ready']} | {b['ready_ms_median'] if b else 'n/a'} |")
    md += ["", "## Structure viewer (click on Load 3D viewer to rendered)", "",
           "| Route | Mode | Before click: total gzip KiB (Mol* loaded?) | After click: local JS/data raw / gzip KiB | External coordinates (bytes) | Mol* chunk + init ms (median) | Click to rendered ms (median; all runs) | Phases |",
           "|---|---|---|---|---|---|---|---|"]
    for r in routes:
        v = r.get("viewer_result")
        if not v:
            continue
        ta = v["totals_after_click_local"]
        ext = "; ".join(f"{e['url'].split('/')[2]} {e['status']} {e['bytes']}" for e in v["external_responses"]) or "none (release file served locally)"
        md.append(f"| `{r['hash']}` | {v['mode']} | {kb(r['totals_before_viewer']['all']['gzip'])} ({'yes' if r['molstar_chunk_before_viewer'] else 'no'}) | "
                  f"{kb(ta['all']['raw'])} / {kb(ta['all']['gzip'])} | {ext} | {v['init_ms_median']} | {v['click_to_ready_ms_median']}; {', '.join(map(str, v['click_to_ready_ms_all_runs']))} | {', '.join(sorted(set(v['phases'])))} |")
    md += ["", "Files fetched after the click:", ""]
    for r in routes:
        v = r.get("viewer_result")
        if v:
            md.append(f"- `{r['hash']}` ({v['mode']}): " + ", ".join(f"{f['file']} ({kb(f['raw'])} raw / {kb(f['gzip'])} gzip)" for f in v["files_after_click"]))
    md += ["", "## Data files requested per route (before viewer)", ""]
    for r in routes:
        if r["viewer"]:
            continue
        df = [f for f in r["files_before_viewer"] if f["kind"] == "data"]
        md.append(f"- `{r['hash']}`: " + ", ".join(f"{f['file'][len('data/v1.6.0/'):]} ({kb(f['raw'])})" for f in df))
    md += ["", "## JS/CSS chunks (KiB)", "", "| File | Raw | gzip |", "|---|---|---|"]
    md += [f"| `{c['file']}` | {kb(c['raw'])} | {kb(c['gzip'])} |" for c in chunks]
    md += ["", "## WCAG 2.1 text contrast (computed styles, 1440 px; viewer routes not scanned)", "",
           "| Route | Distinct colour pairs | Text nodes | Minimum ratio | Pairs below AA |", "|---|---|---|---|---|"]
    for r in routes:
        c = r["contrast"]
        if c:
            md.append(f"| `{r['hash']}` | {len(c)} | {sum(x['count'] for x in c)} | {min(x['ratio'] for x in c)} | {len(r['contrast_failures'])} |")
    (out / "perf_audit.md").write_text("\n".join(md) + "\n")
    fails = sum(len(r["contrast_failures"]) for r in routes)
    errs = sum(r["console_errors"] for r in routes)
    mol_before = [r["id"] for r in routes if r["molstar_chunk_before_viewer"]]
    print(f"wrote {out / 'perf_audit.json'} and perf_audit.md; contrast failures={fails}; console errors={errs}; Mol* before click={mol_before}")


if __name__ == "__main__":
    main()
