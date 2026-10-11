#!/usr/bin/env python3
"""PR-7: serve a deployment artifact the way GitHub Pages serves the project site.

  http://127.0.0.1:PORT/MicroRhodoDB/          -> ARTIFACT/index.html (directory index)
  http://127.0.0.1:PORT/MicroRhodoDB           -> 301 to /MicroRhodoDB/
  http://127.0.0.1:PORT/MicroRhodoDB/site/...  -> ARTIFACT/site/...
  anything missing                              -> 404 (no SPA fallback; the website uses hash routing)

Static files only, confined to ARTIFACT, no test endpoints. Used by the smoke tests (playwright.smoke.config.ts),
the rollback drill and for manual local preview of a built artifact.

Usage: python web/scripts/serve_artifact.py ARTIFACT_DIR PORT [--prefix /MicroRhodoDB/]
"""
from __future__ import annotations

import argparse
import mimetypes
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("text/plain; charset=utf-8", ".fasta")
mimetypes.add_type("text/plain; charset=utf-8", ".treefile")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, root: Path, prefix: str, **kw):
        self.root, self.prefix = root, prefix
        super().__init__(*a, directory=str(root), **kw)

    def log_message(self, fmt, *args):  # quiet
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _resolve(self) -> Path | None:
        path = unquote(urlsplit(self.path).path)
        if path == self.prefix.rstrip("/"):
            self.send_response(301)
            self.send_header("Location", self.prefix)
            self.end_headers()
            return None
        if not path.startswith(self.prefix):
            self.send_error(404)
            return None
        rel = path[len(self.prefix):]
        target = (self.root / rel).resolve()
        if target != self.root and self.root not in target.parents:
            self.send_error(404)
            return None
        if target.is_dir():
            if not path.endswith("/"):
                self.send_response(301)
                self.send_header("Location", path + "/")
                self.end_headers()
                return None
            target = target / "index.html"
        if not target.is_file():
            self.send_error(404)
            return None
        return target

    def _serve(self, head: bool):
        t = self._resolve()
        if t is None:
            return
        data = t.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(t.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if not head:
            self.wfile.write(data)

    def do_GET(self):
        self._serve(False)

    def do_HEAD(self):
        self._serve(True)


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # Browsers legitimately abort in-flight requests when a page is closed; do not print tracebacks for that.
        if isinstance(sys.exc_info()[1], (ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def make_server(root: Path, port: int, prefix: str = "/MicroRhodoDB/") -> ThreadingHTTPServer:
    root = root.resolve()
    if not root.is_dir():
        raise SystemExit(f"serve_artifact: {root} is not a directory")
    return Server(("127.0.0.1", port), partial(Handler, root=root, prefix=prefix))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("artifact", type=Path)
    ap.add_argument("port", type=int)
    ap.add_argument("--prefix", default="/MicroRhodoDB/")
    a = ap.parse_args(argv)
    srv = make_server(a.artifact, a.port, a.prefix)
    print(f"serving {a.artifact} at http://127.0.0.1:{a.port}{a.prefix}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
