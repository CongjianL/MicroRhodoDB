#!/usr/bin/env python3
"""Static server for the PR-6 performance audit: same layout as serve_e2e.py, plus gzip.

GitHub Pages serves text assets gzip-compressed, so throttled transfer times measured against an
uncompressed loopback server would be pessimistic. This server compresses text responses
(HTML, JS, CSS, JSON, SVG, FASTA, TSV, TXT, Markdown, Newick) with gzip level 6 when the request
accepts gzip, caches the compressed bytes in memory, and sends ``Cache-Control: no-store`` so every
fresh browser context measures a cold load. Range requests are not supported (not used by the site).

Usage: python web/scripts/serve_perf.py [port]
"""
from __future__ import annotations

import gzip
import http.server
import mimetypes
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

WEB = Path(__file__).resolve().parents[1]
REPO = WEB.parent
DIST = WEB / "dist" / "site"
SERVED = WEB / "test-results" / ".served-perf"
TEXT = {".html", ".js", ".mjs", ".css", ".json", ".svg", ".fasta", ".fa", ".tsv", ".txt", ".md", ".nwk", ".treefile", ".cff", ".map"}
_cache: dict[Path, bytes] = {}


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4180
    if not (DIST / "index.html").is_file():
        sys.exit("web/dist/site is missing: run the exporter and `npm run build` first")
    if SERVED.exists():
        shutil.rmtree(SERVED)
    root = SERVED / "MicroRhodoDB"
    root.mkdir(parents=True)
    shutil.copy2(REPO / "index.html", root / "index.html")
    (root / "site").symlink_to(DIST, target_is_directory=True)

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_GET(self):
            rel = unquote(urlsplit(self.path).path).lstrip("/")
            p = (SERVED / rel).resolve() if rel else SERVED
            if p.is_dir():
                p = p / "index.html"
            # stay inside the served tree (the site/ symlink resolves into web/dist/site)
            if not (str(p).startswith(str(SERVED.resolve())) or str(p).startswith(str(DIST.resolve()))) or not p.is_file():
                body = b"not found"
                self.send_response(404)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            if p.suffix == ".mjs":
                ctype = "text/javascript"
            gz = p.suffix.lower() in TEXT and "gzip" in (self.headers.get("Accept-Encoding") or "")
            if gz:
                body = _cache.get(p)
                if body is None:
                    body = _cache[p] = gzip.compress(p.read_bytes(), compresslevel=6, mtime=0)
            else:
                body = p.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            if gz:
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Vary", "Accept-Encoding")
            self.end_headers()
            self.wfile.write(body)

    class Server(http.server.ThreadingHTTPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):
            if isinstance(sys.exc_info()[1], (ConnectionResetError, BrokenPipeError)):
                return
            super().handle_error(request, client_address)

    with Server(("127.0.0.1", port), Handler) as httpd:
        print(f"serving {SERVED} (gzip) at http://127.0.0.1:{port}/MicroRhodoDB/site/", flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    main()
