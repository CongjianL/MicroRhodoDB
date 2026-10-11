#!/usr/bin/env python3
"""Serve the built site exactly as GitHub Pages would lay it out, for Playwright E2E tests.

    /MicroRhodoDB/index.html   copy of the repository-root redirect (index.html -> site/)
    /MicroRhodoDB/site/        web/dist/site (vite build output, incl. data/)

Static file server only (no SPA fallback, no rewrites), so any asset or route that works here
works on a plain static host. Usage: python web/scripts/serve_e2e.py [port]

PR-6a test-only endpoints (never part of the built site; used by Playwright via route.continue({url})):
    /__test__/stall?path=<site-relative file>   headers + first 64 bytes of the file, then silence (30 s)
    /__test__/drip?path=<file>&chunks=N&gap_ms=M  the complete file in N chunks with M ms between chunks
"""
import functools
import http.server
import shutil
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

WEB = Path(__file__).resolve().parents[1]
REPO = WEB.parent
DIST = WEB / "dist" / "site"
SERVED = WEB / "tests" / "e2e" / ".served"


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4173
    if not (DIST / "index.html").is_file() or not (DIST / "data" / "current.json").is_file():
        sys.exit("web/dist/site is missing or has no data/: run the exporter and `npm run build` first")
    if SERVED.exists():
        shutil.rmtree(SERVED)
    root = SERVED / "MicroRhodoDB"
    root.mkdir(parents=True)
    shutil.copy2(REPO / "index.html", root / "index.html")
    (root / "site").symlink_to(DIST, target_is_directory=True)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):  # keep test output quiet
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self):
            u = urlsplit(self.path)
            if not u.path.startswith("/__test__/"):
                return super().do_GET()
            q = parse_qs(u.query)
            f = (DIST / q.get("path", [""])[0]).resolve()
            if DIST.resolve() not in f.parents or not f.is_file():
                return self.send_error(404)
            body = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json" if f.suffix == ".json" else "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                if u.path == "/__test__/stall":
                    self.wfile.write(body[:64])
                    self.wfile.flush()
                    time.sleep(30)  # stalled body; the browser aborts long before this
                elif u.path == "/__test__/drip":
                    n = max(1, int(q.get("chunks", ["6"])[0]))
                    gap = int(q.get("gap_ms", ["400"])[0]) / 1000
                    step = -(-len(body) // n)
                    for i in range(0, len(body), step):
                        time.sleep(gap)
                        self.wfile.write(body[i:i + step])
                        self.wfile.flush()
            except (ConnectionResetError, BrokenPipeError):
                pass

    class Server(http.server.ThreadingHTTPServer):
        def handle_error(self, request, client_address):
            # The browser legitimately aborts in-flight requests when a test closes its page;
            # ignore those resets, report anything else.
            import sys
            if isinstance(sys.exc_info()[1], (ConnectionResetError, BrokenPipeError)):
                return
            super().handle_error(request, client_address)

    handler = functools.partial(Handler, directory=str(SERVED))
    with Server(("127.0.0.1", port), handler) as httpd:
        print(f"serving {SERVED} at http://127.0.0.1:{port}/MicroRhodoDB/site/", flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    main()
