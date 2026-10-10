#!/usr/bin/env python3
"""PR-0 PoC verification: serve dist/ under /MicroRhodoDB/site/ and check, in headless Chromium, that
phylotree.js renders the real MR_RT_003 rooted tree and Mol* loads a real PDB entry and AFDB model.
Usage: python verify_poc.py <dist_dir> <out_dir>"""
import functools, http.server, json, os, socketserver, sys, tempfile, threading
from pathlib import Path
from playwright.sync_api import sync_playwright

dist, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
root = Path(tempfile.mkdtemp()); (root / "MicroRhodoDB").mkdir(); os.symlink(dist / "site", root / "MicroRhodoDB/site")
H = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
H.log_message = lambda *a: None
srv = socketserver.TCPServer(("127.0.0.1", 0), H); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{port}/MicroRhodoDB/site/"
res = {"base": base}
with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    for name, frag, key, wait in [("tree_rect", "#/tree", "tree", 60000), ("tree_radial", "#/tree/radial", "tree", 60000),
                                  ("structure_pdb", "#/structure/pdb", "structure", 120000),
                                  ("structure_afdb", "#/structure/afdb", "structure", 120000)]:
        pg = b.new_page(viewport={"width": 1000, "height": 800}); errs = []; reqs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("requestfinished", lambda r: reqs.append(r.url))
        pg.goto(base + frag)
        try:
            pg.wait_for_function(f"() => window.__poc && (window.__poc.{key} || window.__poc.{key}Error)", timeout=wait)
        except Exception as e:
            errs.append("timeout: " + str(e)[:200])
        pg.wait_for_timeout(1500)
        r = pg.evaluate("() => window.__poc")
        r["errors"] = errs[:10]
        r["mol_chunks_requested"] = sorted({u.rsplit('/', 1)[-1] for u in reqs if '/assets/' in u})
        res[name] = r
        pg.screenshot(path=str(out / f"poc_{name}.png"))
        pg.close()
    b.close()
srv.shutdown()
res["bundle"] = {f.name: f.stat().st_size for f in sorted((dist / "site/assets").iterdir())}
(out / "poc_results.json").write_text(json.dumps(res, indent=1))
print(json.dumps(res, indent=1)[:4000])
