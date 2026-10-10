#!/usr/bin/env python3
"""PR-0: capture baseline screenshots + simple UX metrics of the legacy v1.6.0 browser.

Usage: python legacy_screenshots.py <base_url> <out_dir>
Records per (route, viewport): load ms, transferred bytes, console errors,
horizontal overflow (scrollWidth > innerWidth) and detail-panel visibility.
"""
import json, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

base, out = sys.argv[1].rstrip("/") + "/", Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
ROUTES = {"browse": "#/", "record_MRDB000001": "#/record/MRDB000001", "search": "#/search",
          "novel": "#/novel", "about": "#/about"}
VIEWPORTS = {"375": (375, 812), "768": (768, 1024), "1440": (1440, 900)}
rows = []
with sync_playwright() as p:
    b = p.chromium.launch()
    for vk, (w, h) in VIEWPORTS.items():
        for rk, frag in ROUTES.items():
            ctx = b.new_context(viewport={"width": w, "height": h}); pg = ctx.new_page()
            errs, nbytes = [], [0]
            pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.on("response", lambda r: nbytes.__setitem__(0, nbytes[0] + int(r.headers.get("content-length", 0) or 0)))
            t0 = time.time(); pg.goto(base + frag, wait_until="networkidle"); pg.wait_for_timeout(800)
            ms = round((time.time() - t0) * 1000)
            m = pg.evaluate("""() => ({sw: document.documentElement.scrollWidth, iw: innerWidth,
                 sh: document.documentElement.scrollHeight,
                 detail: (() => {const d=document.querySelector('#detail'); if(!d) return null;
                    const r=d.getBoundingClientRect(); return {visible: r.width>0 && r.height>0, w: Math.round(r.width), x: Math.round(r.x)}})(),
                 nTableRows: document.querySelectorAll('table tbody tr').length})""")
            f = out / f"legacy_{rk}_{vk}.png"; pg.screenshot(path=str(f), full_page=False)
            rows.append({"route": frag, "viewport": vk, "load_ms": ms, "bytes_content_length": nbytes[0],
                         "console_errors": errs, "h_overflow_px": m["sw"] - m["iw"], "scroll_height": m["sh"],
                         "detail": m["detail"], "table_rows_rendered": m["nTableRows"], "png": f.name})
            ctx.close()
    b.close()
(out / "legacy_ux_metrics.json").write_text(json.dumps(rows, indent=1))
for r in rows:
    print(r["viewport"], r["route"], r["load_ms"], r["bytes_content_length"], "overflow", r["h_overflow_px"],
          "rows", r["table_rows_rendered"], "detail", r["detail"], "errs", len(r["console_errors"]))
