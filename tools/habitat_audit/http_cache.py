"""Content-addressed HTTP cache with per-host pacing and bounded retries.

Every request (success or final failure) is stored as one gzipped JSON object:
  <cache>/objects/<key[:2]>/<key>.json.gz
  key = sha256(method + "\n" + canonical_url + "\n" + canonical_body)
Fields: method, url, params, body, status, ok, error, attempts, retrieved_at,
headers (subset), body_sha256, text.

--offline replays strictly from the cache; a cache miss is an error (never a
silent NOT_REPORTED). Final failures are cached too, so replays reproduce
LOOKUP_FAILED exactly. `retry_failed=True` re-attempts cached failures once
(the plan's final retry pass) and overwrites them only on success.
"""
from __future__ import annotations

import datetime as _dt
import gzip
import hashlib
import json
import random
import threading
import time
import urllib.parse
from pathlib import Path

import requests

USER_AGENT = "MicroRhodoDB-habitat-audit/1.0 (PR-7c.1; https://github.com/CongjianL/MicroRhodoDB)"
NCBI_TOOL = "mrdb_habitat_audit"
NCBI_EMAIL = "CongjianL@users.noreply.github.com"
KEEP_HEADERS = ("content-type", "x-uniprot-release", "x-uniprot-release-date", "x-total-results", "retry-after")
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 4
# Statuses that are definitive answers (not lookup failures); interpretation is per step.
DEFINITIVE_STATUS = {200, 204, 400, 404, 410}

HOST_LIMITS = {  # host -> (max concurrent, min seconds between request starts)
    "rest.uniprot.org": (4, 0.0),
    "www.ebi.ac.uk": (4, 0.0),
    "eutils.ncbi.nlm.nih.gov": (1, 0.34),
}


class CacheMiss(RuntimeError):
    pass


def canonical(method: str, url: str, params: dict | None, data: dict | None) -> tuple[str, str]:
    q = urllib.parse.urlencode(sorted((params or {}).items()), doseq=True)
    full = url + ("?" + q if q else "")
    body = urllib.parse.urlencode(sorted((data or {}).items()), doseq=True) if data else ""
    return full, body


def cache_key(method: str, url: str, params: dict | None = None, data: dict | None = None) -> str:
    full, body = canonical(method, url, params, data)
    return hashlib.sha256(f"{method.upper()}\n{full}\n{body}".encode()).hexdigest()


class _Pacer:
    def __init__(self, conc: int, gap: float):
        self.sem = threading.BoundedSemaphore(conc)
        self.gap = gap
        self.lock = threading.Lock()
        self.last = 0.0

    def __enter__(self):
        self.sem.acquire()
        if self.gap:
            with self.lock:
                wait = self.last + self.gap - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                self.last = time.monotonic()
        return self

    def __exit__(self, *a):
        self.sem.release()


class HttpCache:
    def __init__(self, root: Path, offline: bool = False, retry_failed: bool = False, timeout: float = 120.0,
                 sleep=time.sleep):
        self.root = Path(root)
        self.offline = offline
        self.retry_failed = retry_failed
        self.timeout = timeout
        self.sleep = sleep
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.pacers = {h: _Pacer(*v) for h, v in HOST_LIMITS.items()}
        self.default_pacer = _Pacer(2, 0.2)
        self.stats = {"hit": 0, "fetched": 0, "failed": 0, "retried_ok": 0}
        self._lock = threading.Lock()
        self.used_keys: set[str] = set()

    # ------------------------------------------------------------------ storage
    def path(self, key: str) -> Path:
        return self.root / "objects" / key[:2] / f"{key}.json.gz"

    def load(self, key: str) -> dict | None:
        p = self.path(key)
        if not p.exists():
            return None
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            return json.load(fh)

    def store(self, key: str, entry: dict) -> None:
        p = self.path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        raw = json.dumps(entry, sort_keys=True, ensure_ascii=False).encode("utf-8")
        with open(tmp, "wb") as fh:  # mtime=0 -> byte-stable gzip
            with gzip.GzipFile(fileobj=fh, mode="wb", mtime=0) as gz:
                gz.write(raw)
        tmp.replace(p)

    # ------------------------------------------------------------------ requests
    def get(self, url: str, params: dict | None = None) -> dict:
        return self.request("GET", url, params=params)

    def post(self, url: str, data: dict) -> dict:
        return self.request("POST", url, data=data)

    def request(self, method: str, url: str, params: dict | None = None, data: dict | None = None) -> dict:
        if "eutils.ncbi.nlm.nih.gov" in url:
            target = data if data is not None else params
            if target is not None:
                target.setdefault("tool", NCBI_TOOL)
                target.setdefault("email", NCBI_EMAIL)
        key = cache_key(method, url, params, data)
        with self._lock:
            self.used_keys.add(key)
        cached = self.load(key)
        if cached is not None and (cached["ok"] or self.offline or not self.retry_failed):
            with self._lock:
                self.stats["hit"] += 1
            return cached
        if self.offline:
            raise CacheMiss(f"offline cache miss: {method} {canonical(method, url, params, data)[0][:200]}")
        entry = self._fetch(method, url, params, data)
        if cached is not None and not cached["ok"] and not entry["ok"]:
            entry["attempts"] += cached.get("attempts", 0)
        if cached is not None and not cached["ok"] and entry["ok"]:
            with self._lock:
                self.stats["retried_ok"] += 1
        self.store(key, entry)
        return entry

    def _fetch(self, method, url, params, data) -> dict:
        host = urllib.parse.urlparse(url).netloc
        pacer = self.pacers.get(host, self.default_pacer)
        full, body = canonical(method, url, params, data)
        attempts, status, err, text, headers = 0, None, None, None, {}
        for attempt in range(MAX_RETRIES + 1):
            attempts += 1
            retry_after = None
            try:
                with pacer:
                    r = self.session.request(method, url, params=params, data=data, timeout=self.timeout)
                status, text = r.status_code, r.text
                headers = {k: r.headers[k] for k in r.headers if k.lower() in KEEP_HEADERS}
                err = None
                if status in RETRY_STATUS:
                    err = f"HTTP {status}"
                    ra = r.headers.get("Retry-After")
                    retry_after = float(ra) if ra and ra.replace(".", "", 1).isdigit() else None
                else:
                    break
            except requests.RequestException as e:  # timeouts, connection resets
                status, text, err = None, None, f"{type(e).__name__}: {e}"[:500]
            if attempt < MAX_RETRIES:
                delay = retry_after if retry_after is not None else min(60.0, 2.0 ** attempt) + random.uniform(0, 1)
                self.sleep(delay)
        ok = status in DEFINITIVE_STATUS and err is None
        with self._lock:
            self.stats["fetched" if ok else "failed"] += 1
        b = (text or "").encode("utf-8")
        return {
            "method": method.upper(), "url": full, "body": body, "status": status, "ok": ok, "error": err,
            "attempts": attempts, "retrieved_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "headers": headers, "body_sha256": hashlib.sha256(b).hexdigest(), "text": text,
        }

    # ------------------------------------------------------------------ manifest
    def iter_entries(self):
        for p in sorted((self.root / "objects").glob("*/*.json.gz")):
            with gzip.open(p, "rt", encoding="utf-8") as fh:
                yield p.name[:-8], json.load(fh)
