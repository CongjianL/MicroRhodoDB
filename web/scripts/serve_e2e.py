#!/usr/bin/env python3
"""Serve the built site exactly as GitHub Pages would lay it out, for Playwright E2E tests.

    /MicroRhodoDB/index.html   copy of the repository-root redirect (index.html -> site/)
    /MicroRhodoDB/site/        web/dist/site (vite build output, incl. data/)

Static file server only (no SPA fallback, no rewrites), so any asset or route that works here
works on a plain static host. Usage: python web/scripts/serve_e2e.py [port]
"""
import functools
import http.server
import shutil
import sys
from pathlib import Path

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
