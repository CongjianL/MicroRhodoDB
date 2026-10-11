#!/usr/bin/env python3
"""PR-6 performance, bundle and contrast audit.

1. Bundle inventory of web/dist/site/assets: raw, gzip -9 and brotli -11 bytes per file, the initial
   (Home) JS/CSS set and lazily loaded chunks.
2. Throttled cold-load measurements (scripts/pr6_perf.mjs "perf" mode) for desktop and mobile profiles
   against scripts/serve_perf.py (gzip like GitHub Pages, no-store): web-vitals FCP/LCP/CLS/TTFB/INP,
   ready time, long tasks, TBT proxy, JS heap, transferred bytes, interaction timings.
3. WCAG text-contrast scan (pr6_perf.mjs "contrast" mode) for every route at 375/768/1440 px,
   including SVG text and text in horizontally scrolled regions.

Loopback server with DevTools throttling: lab numbers for comparison, not field (CrUX) data. INP is
derived from scripted interactions only.

Usage: python scripts/pr6_perf_audit.py --out ../docs/website/pr6 [--runs 3] [--port 4180]
"""
from __future__ import annotations

import argparse
import gzip
import json
import platform
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import brotli

WEB = Path(__file__).resolve().parent.parent
DIST = WEB / "dist" / "site"


def wait_up(url: str, timeout: float = 30) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            urllib.request.urlopen(url, timeout=2).read()
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError(f"server did not start: {url}")


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 3) if xs else None


def bundle_inventory() -> dict:
    rows = []
    for p in sorted((DIST / "assets").iterdir()):
        if p.suffix not in (".js", ".css"):
            continue
        b = p.read_bytes()
        rows.append({"file": p.name, "raw": len(b), "gzip": len(gzip.compress(b, 9, mtime=0)),
                     "brotli": len(brotli.compress(b, quality=11))})
    html = (DIST / "index.html").read_text()
    initial = [r for r in rows if r["file"] in html]
    tot = lambda rs, k: sum(r[k] for r in rs)  # noqa: E731
    return {"files": rows, "initial_from_index_html": [r["file"] for r in initial],
            "initial_totals": {k: tot(initial, k) for k in ("raw", "gzip", "brotli")},
            "all_totals": {k: tot(rows, k) for k in ("raw", "gzip", "brotli")}}


def rel(url: str) -> str:
    p = urlparse(url)
    if p.hostname != "127.0.0.1":
        return url
    path = p.path
    return path.split("/MicroRhodoDB/site/", 1)[-1] or "index.html"


def summarise_perf(cap: dict) -> list[dict]:
    out = []
    for r in cap["routes"]:
        ok = [x for x in r["runs"] if "failed" not in x]
        failed = [x["failed"] for x in r["runs"] if "failed" in x]
        reqs = ok[0]["requests"] if ok else []
        local = [q for q in reqs if not q["url"].startswith("https://")]
        js = [q for q in local if rel(q["url"]).endswith(".js")]
        data = [q for q in local if rel(q["url"]).startswith("data/")]
        inter = {}
        for x in ok:
            for i in x["interactions"]:
                inter.setdefault(i["name"], []).append(i)
        out.append({
            "profile": r["profile"], "id": r["id"], "hash": r["hash"], "runs_ok": len(ok), "failed": failed,
            "ready_ms": med([x["readyMs"] for x in ok]), "idle_ms": med([x["idleMs"] for x in ok]),
            "fcp_ms": med([x["fcp"] for x in ok]), "lcp_ms": med([x["lcp"] for x in ok]),
            "cls": med([x["cls"] for x in ok]), "ttfb_ms": med([x["ttfb"] for x in ok]),
            "inp_ms": med([x["inp"] for x in ok]) if any(x["inpReported"] for x in ok) else None,
            "tbt_proxy_ms": med([x["tbtProxyMs"] for x in ok]), "max_long_task_ms": med([x["maxLongTaskMs"] for x in ok]),
            "heap_mb": med([x["heapMB"] for x in ok]), "dom_nodes": med([x["domNodes"] for x in ok]),
            "requests": len(local), "transfer_bytes": sum(q["encoded"] for q in local),
            "js_transfer_bytes": sum(q["encoded"] for q in js), "data_transfer_bytes": sum(q["encoded"] for q in data),
            "data_files": sorted({rel(q["url"]) for q in data}),
            "external": sorted({q["url"] for q in reqs if q["url"].startswith("https://")}),
            "errors": sorted({e for x in ok for e in x["errors"]}),
            "interactions": {k: {"ms": med([i["ms"] for i in v]), "long_tasks": med([i["longTasks"] for i in v]),
                                 "max_long_task_ms": med([i["maxLongTaskMs"] for i in v])} for k, v in inter.items()},
        })
    return out


def kib(n):
    return f"{n / 1024:,.1f}"


def cls_s(x):
    return "n/a" if x is None else f"{x:.3f}"


def ms(x):
    return "n/a" if x is None else f"{x:,.0f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--port", type=int, default=4180)
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not (DIST / "index.html").exists():
        sys.exit("run `npm run build` first")
    base = f"http://127.0.0.1:{a.port}/MicroRhodoDB/site/"
    tmp = WEB / "test-results"
    tmp.mkdir(exist_ok=True)
    perf_raw, con_raw = tmp / "pr6_perf_raw.json", tmp / "pr6_contrast_raw.json"
    server = subprocess.Popen([sys.executable, str(WEB / "scripts" / "serve_perf.py"), str(a.port)], cwd=WEB)
    try:
        wait_up(base)
        subprocess.run(["node", "scripts/pr6_perf.mjs", base, "contrast", "1", str(con_raw)], cwd=WEB, check=True)
        subprocess.run(["node", "scripts/pr6_perf.mjs", base, "perf", str(a.runs), str(perf_raw)], cwd=WEB, check=True)
    finally:
        server.terminate()
        server.wait(timeout=10)
    perf, con = json.loads(perf_raw.read_text()), json.loads(con_raw.read_text())
    bundles = bundle_inventory()
    routes = summarise_perf(perf)
    contrast = [{"width": r["width"], "id": r["id"], "text_nodes": sum(c["count"] for c in r["contrast"]),
                 "svg_text_nodes": sum(c["count"] for c in r["contrast"] if c["svg"]),
                 "min_ratio_active": min((c["ratio"] for c in r["contrast"] if not c["inactive"]), default=None),
                 "inactive_below_aa": [c for c in r["contrast"] if c["inactive"] and c["ratio"] < c["need"]],
                 "failures": r["failures"]} for r in con["routes"]]
    env = {**perf["env"], "python": platform.python_version(), "platform": platform.platform(),
           "server": "scripts/serve_perf.py (gzip level 6 for text, Cache-Control: no-store, HTTP/1.1, loopback)"}
    (out / "performance_audit.json").write_text(json.dumps(
        {"env": env, "bundles": bundles, "routes": routes, "contrast": contrast}, indent=1))
    (out / "raw").mkdir(exist_ok=True)
    (out / "raw" / "pr6_perf_raw.json").write_text(json.dumps(perf))
    (out / "raw" / "pr6_contrast_raw.json").write_text(json.dumps(con))

    md = ["# PR-6 performance audit (generated by web/scripts/pr6_perf_audit.py)", "",
          f"Chromium {env['chromium']}, {a.runs} cold runs per route and profile (median shown), {env['platform']}.",
          "Profiles: desktop 1440x900, RTT 40 ms, 10 Mbit/s, CPU 1x; mobile 375x812 DPR 2, RTT 562.5 ms, "
          "1.47 Mbit/s down, CPU 4x (DevTools throttling). Server: gzip, no-store, loopback. Lab values, not field data.",
          "Web Vitals thresholds (good): LCP <= 2,500 ms, CLS <= 0.1, INP <= 200 ms. "
          "INP only where a scripted interaction ran (Event Timing threshold 16 ms); 'n/a' = no interaction measured.", "",
          "## Bundles (web/dist/site/assets)", "",
          f"Initial JS+CSS referenced by index.html: {kib(bundles['initial_totals']['raw'])} KiB raw, "
          f"{kib(bundles['initial_totals']['gzip'])} KiB gzip, {kib(bundles['initial_totals']['brotli'])} KiB brotli "
          f"({', '.join(bundles['initial_from_index_html'])}).", "",
          "| File | Raw KiB | gzip KiB | brotli KiB |", "|---|---:|---:|---:|"]
    for f in sorted(bundles["files"], key=lambda r: -r["raw"]):
        md.append(f"| {f['file']} | {kib(f['raw'])} | {kib(f['gzip'])} | {kib(f['brotli'])} |")
    for prof in ("desktop", "mobile"):
        md += ["", f"## Cold loads, {prof}", "",
               "| Route | Ready ms | FCP | LCP | CLS | INP | TBT proxy | Max LT | Heap MB | Req | Transfer KiB | JS KiB | Data KiB |",
               "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for r in routes:
            if r["profile"] != prof:
                continue
            md.append(f"| `{r['hash']}` | {ms(r['ready_ms'])} | {ms(r['fcp_ms'])} | {ms(r['lcp_ms'])} | "
                      f"{cls_s(r['cls'])} | {ms(r['inp_ms'])} | {ms(r['tbt_proxy_ms'])} | "
                      f"{ms(r['max_long_task_ms'])} | {r['heap_mb']} | {r['requests']} | {kib(r['transfer_bytes'])} | "
                      f"{kib(r['js_transfer_bytes'])} | {kib(r['data_transfer_bytes'])} |"
                      + (f" FAILED {len(r['failed'])}" if r["failed"] else ""))
        md += ["", f"Interactions ({prof}):", "", "| Route | Interaction | ms | Long tasks | Max long task ms |", "|---|---|---:|---:|---:|"]
        for r in routes:
            if r["profile"] == prof:
                for k, v in r["interactions"].items():
                    md.append(f"| {r['id']} | {k} | {ms(v['ms'])} | {v['long_tasks']} | {ms(v['max_long_task_ms'])} |")
    errs = sorted({e for r in routes for e in r["errors"]})
    md += ["", f"Console errors / page errors during all perf runs: {len(errs)}" + ("" if not errs else ": " + "; ".join(errs[:10])), "",
           "## WCAG 2.x text contrast (all routes x 375/768/1440, HTML and SVG text)", "",
           f"Text nodes scanned: {sum(c['text_nodes'] for c in contrast):,} (SVG: {sum(c['svg_text_nodes'] for c in contrast):,}); "
           f"failures (active text below AA): {sum(len(c['failures']) for c in contrast)}; "
           f"lowest active ratio: {min(c['min_ratio_active'] for c in contrast if c['min_ratio_active'])}.",
           f"Disabled controls below 4.5:1 (exempt under WCAG 1.4.3): "
           f"{sorted({(x['sample'], x['ratio']) for c in contrast for x in c['inactive_below_aa']})}."]
    (out / "performance_audit_generated.md").write_text("\n".join(md) + "\n")
    print(f"wrote {out / 'performance_audit.json'}; contrast failures={sum(len(c['failures']) for c in contrast)}; errors={len(errs)}")


if __name__ == "__main__":
    main()
