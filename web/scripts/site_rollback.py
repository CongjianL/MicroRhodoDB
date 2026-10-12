#!/usr/bin/env python3
"""PR-7: rollback and recovery tooling for the MicroRhodoDB GitHub Pages site.

Sub-commands
  legacy-build   --ref SHA --out DIR    Recreate the pre-redesign production site (branch-based Pages from main,
                                        repository root, .nojekyll) as an artifact: `git archive SHA`, verified
                                        file-by-file against web/release/rollback/legacy_<sha12>.sha256.
  legacy-manifest --ref SHA             Write that manifest (done once; committed with PR-7).
  verify-served  --base URL --sums FILE [--paths P ...] [--workers N --deadline S --request-timeout S
                 --retries N --round-wait S --exclude-hidden]
                                        Fetch files from a served site (local server or the live site) and compare
                                        the full SHA-256 of every body with a SHA256SUMS-style manifest. Bounded
                                        concurrency, per-request and total deadlines, per-file retries for transient
                                        errors, re-check rounds for CDN propagation. Read-only (HTTP GET).
  compare        A B                    Compare two artifacts (directories with SHA256SUMS): lists added/removed/
                                        changed files and classifies scientific-data changes (site/data/**).
                                        Exit 4 if scientific data differ while the dataset release is unchanged.
  drill          --new DIR --legacy DIR [--port N]
                                        Local deploy -> rollback -> roll-forward drill with serve_artifact.py:
                                        every file of each artifact must be served byte-identically after each switch.

Recovery paths documented in docs/website/PR7_ROLLBACK_RUNBOOK.md:
  R1 (fastest, no build): Settings > Pages > Source = "Deploy from a branch", main, / (root). main keeps the
     untouched legacy site/ and root index.html, so this restores the pre-redesign site exactly.
  R2 (Actions): deploy-site.yml with kind=legacy-rollback and source_sha=<legacy commit> deploys `legacy-build`.
  R3 (Actions): deploy-site.yml with kind=website and an earlier accepted source_sha (deterministic rebuild,
     compared with the recorded BUILD_INFO content_sha256).
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import http.client
import io
import json
import random
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROLLBACK_DIR = Path("web/release/rollback")
sys.path.insert(0, str(Path(__file__).resolve().parent))


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def read_sums(p: Path) -> dict[str, str]:
    out = {}
    for ln in p.read_text().splitlines():
        if ln.strip():
            h, r = ln.split(None, 1)
            out[r.strip().lstrip("*")] = h
    return out


def manifest_path(ref: str) -> Path:
    return REPO / ROLLBACK_DIR / f"legacy_{ref[:12]}.sha256"


def archive_members(ref: str) -> dict[str, bytes]:
    raw = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", ref], capture_output=True, check=True).stdout
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as tf:
        for m in tf.getmembers():
            if m.isfile():
                files[m.name] = tf.extractfile(m).read()
            elif m.issym() or m.islnk():
                raise SystemExit(f"legacy archive contains a link: {m.name}")
    return files


def cmd_legacy_manifest(a) -> int:
    files = archive_members(a.ref)
    p = manifest_path(a.ref)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(f"{sha256_bytes(b)}  {n}\n" for n, b in sorted(files.items())))
    print(f"wrote {p.relative_to(REPO)} ({len(files)} files)")
    return 0


def legacy_build(ref: str, out: Path) -> dict:
    full = subprocess.run(["git", "-C", str(REPO), "rev-parse", f"{ref}^{{commit}}"], capture_output=True, text=True, check=True).stdout.strip()
    man = read_sums(manifest_path(full))
    files = archive_members(full)
    errors = [f"not in manifest: {n}" for n in sorted(set(files) - set(man))]
    errors += [f"missing from archive: {n}" for n in sorted(set(man) - set(files))]
    errors += [f"hash differs: {n}" for n in sorted(set(files) & set(man)) if sha256_bytes(files[n]) != man[n]]
    for need in ("index.html", "site/index.html", "site/app.js", "site/data.js", ".nojekyll"):
        if need not in files:
            errors.append(f"legacy site file missing: {need}")
    if errors:
        raise SystemExit("LEGACY_ARTIFACT_INVALID\n  " + "\n  ".join(errors[:20]))
    if out.exists():
        shutil.rmtree(out)
    for n, b in files.items():
        p = out / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b)
    return {"ref": full, "files": len(files), "bytes": sum(len(b) for b in files.values()),
            "manifest": str(manifest_path(full).relative_to(REPO)),
            "manifest_sha256": sha256_bytes(manifest_path(full).read_bytes())}


def cmd_legacy_build(a) -> int:
    res = legacy_build(a.ref, a.out.resolve())
    print(json.dumps(res, indent=2))
    print(f"LEGACY_ARTIFACT_VERIFIED {a.out}")
    return 0


def fetch(url: str, timeout: float = 60) -> tuple[int, bytes]:
    """Simple GET used by the drill for status probes (root redirect, 404, BUILD_INFO)."""
    st, body, err = fetch_bounded(url, timeout, timeout, DEFAULT_MAX_BYTES)
    return (st if st is not None else 0), (body or b"")


# ------------------------------------------------------------------------------ served-site verification
# Post-deployment verification fetches every file of the artifact (5,373 for website 2.0) and compares the full
# SHA-256 of each body with SHA256SUMS. Bounded concurrency keeps the run short on a high-latency CDN; every
# request has its own wall-clock deadline (also while the body is streaming), the whole run has a total deadline,
# transient failures (network error, timeout, truncated body, HTTP 408/425/429/5xx) are retried per file with
# exponential backoff, and propagation failures (HTTP 404 or stale bytes) are re-checked in later rounds, only for
# the files that are still wrong. A file counts as verified only when one complete 200 response hashes to the
# manifest value; nothing else (partial body, Content-Length mismatch, deadline) is ever accepted.
DEFAULT_WORKERS = 8
DEFAULT_REQUEST_TIMEOUT = 30.0
DEFAULT_DEADLINE = 900.0
DEFAULT_RETRIES = 3
DEFAULT_ROUND_WAIT = 30.0
DEFAULT_MAX_BYTES = 256 * 1024 * 1024
TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}


def fetch_bounded(url: str, timeout: float, request_deadline: float, max_bytes: int) -> tuple[int | None, bytes | None, str | None]:
    """GET url -> (status, body, error). body is returned only for a complete response; error is set for network
    errors, timeouts, an exceeded per-request wall-clock deadline (slow-drip bodies), oversize or truncated bodies."""
    t0 = time.monotonic()
    req = urllib.request.Request(url, headers={"User-Agent": "mrdb-site-rollback", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=max(0.05, timeout)) as r:
            status, length = r.status, r.headers.get("Content-Length")
            chunks, n = [], 0
            while True:
                if time.monotonic() - t0 > request_deadline:
                    return status, None, f"request deadline ({request_deadline:.0f} s) exceeded while reading the body"
                b = r.read1(65536)  # returns after one socket read, so the deadline is re-checked during slow bodies
                if not b:
                    break
                n += len(b)
                if n > max_bytes:
                    return status, None, f"body larger than {max_bytes} bytes"
                chunks.append(b)
            body = b"".join(chunks)
            if length is not None and length.isdigit() and int(length) != len(body):
                return status, None, f"truncated body ({len(body)} of {length} bytes)"
            return status, body, None
    except urllib.error.HTTPError as e:
        return e.code, None, None
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError) as e:
        return None, None, f"network error: {type(e).__name__}: {getattr(e, 'reason', e)}"


def verify_served(base: str, sums: dict[str, str], paths: list[str] | None = None, *, workers: int = DEFAULT_WORKERS,
                  request_timeout: float = DEFAULT_REQUEST_TIMEOUT, deadline: float = DEFAULT_DEADLINE,
                  retries: int = DEFAULT_RETRIES, round_wait: float = DEFAULT_ROUND_WAIT, max_rounds: int | None = None,
                  max_bytes: int = DEFAULT_MAX_BYTES, backoff: float = 0.5) -> dict:
    base = base if base.endswith("/") else base + "/"
    todo = list(paths) if paths else sorted(sums)
    t0 = time.monotonic()
    lock = threading.Lock()
    stats = {"requests": 0, "retries": 0, "in_flight": 0, "max_in_flight": 0}

    def remaining() -> float:
        return deadline - (time.monotonic() - t0)

    def check_one(rel: str) -> tuple[bool, str]:
        reason = "not attempted"
        for attempt in range(retries + 1):
            rem = remaining()
            if rem <= 0:
                return False, f"total deadline ({deadline:.0f} s) reached; last result: {reason}"
            with lock:
                stats["requests"] += 1
                stats["in_flight"] += 1
                stats["max_in_flight"] = max(stats["max_in_flight"], stats["in_flight"])
            try:
                lim = min(request_timeout, rem)
                st, body, err = fetch_bounded(base + urllib.parse.quote(rel), lim, lim, max_bytes)
            finally:
                with lock:
                    stats["in_flight"] -= 1
            if err is None and st == 200:
                h = sha256_bytes(body)
                if h == sums[rel]:
                    return True, ""
                return False, f"served bytes differ ({h[:12]} != {sums[rel][:12]})"  # stale: re-check next round
            reason = err or f"HTTP {st}"
            if err is None and st not in TRANSIENT_STATUS:
                return False, reason  # 404/403...: propagation or a real error; re-checked next round
            if attempt < retries:
                with lock:
                    stats["retries"] += 1
                time.sleep(max(0.0, min(backoff * (2 ** attempt) * (0.5 + random.random()), remaining())))
        return False, f"{reason} (after {retries + 1} attempts)"

    failed: dict[str, str] = {r: "not in manifest" for r in todo if r not in sums}
    pending = [r for r in todo if r in sums]
    last: dict[str, str] = {}
    ok, rounds = 0, 0
    while pending and remaining() > 0 and (max_rounds is None or rounds < max_rounds):
        if rounds:
            time.sleep(max(0.0, min(round_wait, remaining())))
            if remaining() <= 0:
                break
        rounds += 1
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers))
        futs = {ex.submit(check_one, r): r for r in pending}
        done, not_done = concurrent.futures.wait(futs, timeout=max(0.0, remaining()) + 2.0)
        still = []
        for f, r in futs.items():
            if f in done:
                good, why = f.result()
                if good:
                    ok += 1
                    continue
                last[r] = why
            else:
                last[r] = f"total deadline ({deadline:.0f} s) reached during verification"
            still.append(r)
        ex.shutdown(wait=False, cancel_futures=True)
        pending = still
    for r in pending:
        failed[r] = last.get(r, f"total deadline ({deadline:.0f} s) reached before verification")
    bad = [f"{r}: {why}" for r, why in sorted(failed.items())]
    return {"base": base, "checked": len(todo), "ok": ok, "failed": bad, "rounds": rounds,
            "requests": stats["requests"], "retries": stats["retries"], "max_in_flight": stats["max_in_flight"],
            "workers": workers, "deadline_s": deadline, "elapsed_s": round(time.monotonic() - t0, 2),
            "deadline_exceeded": bool(pending) and remaining() <= 0}


def cmd_verify_served(a) -> int:
    sums = read_sums(a.sums)
    paths = a.paths
    if a.exclude_hidden:
        paths = [r for r in (paths or sorted(sums)) if not any(part.startswith(".") for part in r.split("/"))]
    res = verify_served(a.base, sums, paths, workers=a.workers, request_timeout=a.request_timeout, deadline=a.deadline,
                        retries=a.retries, round_wait=a.round_wait, max_rounds=a.max_rounds)
    print(json.dumps({**res, "failed": res["failed"][:30]}, indent=2))
    if a.json:
        a.json.write_text(json.dumps(res, indent=2) + "\n")
    print("SERVED_SITE_MATCHES" if not res["failed"] else "SERVED_SITE_DIFFERS")
    return 0 if not res["failed"] else 1


# Fields that record *where/when the export was made* rather than scientific content.
_PROV_KEYS = {"exporter_git_commit", "exporter_git_dirty", "git_commit", "git_dirty", "website_version"}


def _strip_provenance(name: str, obj):
    """Return obj without provenance-only content so that scientific content can be compared.

    manifest.json / export_manifest.json: exporter commit/dirty flags and the website version label.
    export_manifest.json additionally: the hash/size rows of the provenance-carrying files themselves.
    downloads.json: repository_documents (README, LICENSE, CITATION.cff ... link to the build commit) and the
    website version label; release_files, refpkg_files and website_derived stay and are compared.
    """
    def drop(o):
        if isinstance(o, dict):
            return {k: drop(v) for k, v in o.items() if k not in _PROV_KEYS}
        if isinstance(o, list):
            return [drop(x) for x in o]
        return o
    o = drop(obj)
    if name == "downloads.json" and isinstance(o, dict):
        o.pop("repository_documents", None)
    if name == "export_manifest.json" and isinstance(o, dict):
        o["files"] = [f for f in o.get("files", []) if Path(f.get("path", "")).name not in _PROV_FILES]
        o.pop("total_bytes", None)
    return o


_PROV_FILES = {"export_manifest.json", "manifest.json", "downloads.json"}


def _dir_sums(d: Path) -> dict[str, str]:
    """SHA256SUMS of an artifact directory; computed from the files when absent (e.g. a legacy-build output)."""
    if (d / "SHA256SUMS").is_file():
        return read_sums(d / "SHA256SUMS")
    return {p.relative_to(d).as_posix(): sha256_bytes(p.read_bytes())
            for p in sorted(d.rglob("*")) if p.is_file() and p.relative_to(d).as_posix() != "SHA256SUMS"}


def compare(a: Path, b: Path) -> dict:
    sa, sb = _dir_sums(a), _dir_sums(b)
    added = sorted(set(sb) - set(sa))
    removed = sorted(set(sa) - set(sb))
    changed = sorted(r for r in set(sa) & set(sb) if sa[r] != sb[r])

    def info(d: Path):
        p = d / "site" / "BUILD_INFO.json"
        return json.loads(p.read_text()) if p.is_file() else {}

    ia, ib = info(a), info(b)
    sci, prov_only = [], []
    for r in added + removed:
        if r.startswith("site/data/"):
            sci.append(r)
    for r in changed:
        if not r.startswith("site/data/"):
            continue
        name = Path(r).name
        if name in _PROV_FILES:
            ja, jb = (json.loads((d / r).read_text()) for d in (a, b))
            if _strip_provenance(name, ja) == _strip_provenance(name, jb):
                prov_only.append(r)
                continue
        sci.append(r)
    # None = at least one side is not a website 2.0 artifact (no BUILD_INFO.json), e.g. the legacy site.
    same_release = (ia.get("dataset_release") == ib.get("dataset_release")) if (ia and ib) else None
    return {"a": str(a), "b": str(b), "a_commit": ia.get("source_commit"), "b_commit": ib.get("source_commit"),
            "added": added, "removed": removed, "changed": changed, "identical": not (added or removed or changed),
            "scientific_data_changes": sorted(sci), "provenance_only_data_changes": sorted(prov_only),
            "same_dataset_release": same_release,
            "unexpected_scientific_change": bool(sci) and same_release is True}


def cmd_compare(a) -> int:
    res = compare(a.a.resolve(), a.b.resolve())
    short = {k: (v[:20] if isinstance(v, list) else v) for k, v in res.items()}
    print(json.dumps(short, indent=2))
    if a.json:
        a.json.write_text(json.dumps(res, indent=2) + "\n")
    if res["unexpected_scientific_change"]:
        print("UNEXPECTED_SCIENTIFIC_DATA_CHANGE: data files differ while the dataset release is unchanged", file=sys.stderr)
        return 4
    if res["identical"]:
        print("ARTIFACTS_IDENTICAL")
    elif res["same_dataset_release"] is None:
        print("ARTIFACTS_DIFFER (one side has no BUILD_INFO.json, e.g. the legacy site: scientific content not classified)")
    elif not res["same_dataset_release"]:
        print("ARTIFACTS_DIFFER (different dataset releases: data changes are expected and must be reviewed)")
    else:
        print("ARTIFACTS_DIFFER (no scientific-data change)")
    return 0


def _serve(root: Path, port: int):
    import serve_artifact  # noqa: PLC0415
    srv = serve_artifact.make_server(root, port)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def drill(new: Path, legacy: Path, port: int, work: Path) -> dict:
    """deploy(new) -> rollback(legacy) -> roll-forward(new); each stage served from a fresh 'pages' copy."""
    legacy_sums = read_sums(manifest_path(json.loads((work / "legacy_ref.json").read_text())["ref"])) \
        if (work / "legacy_ref.json").is_file() else None
    new_sums = read_sums(new / "SHA256SUMS")
    new_sums_full = {**new_sums, "SHA256SUMS": sha256_bytes((new / "SHA256SUMS").read_bytes())}
    stages = []
    for name, src, sums in (("deploy-new", new, new_sums_full), ("rollback-legacy", legacy, legacy_sums),
                            ("roll-forward-new", new, new_sums_full)):
        pages = work / "pages"
        if pages.exists():
            shutil.rmtree(pages)
        shutil.copytree(src, pages)
        srv = _serve(pages, port)
        try:
            base = f"http://127.0.0.1:{port}/MicroRhodoDB/"
            res = verify_served(base, sums, max_rounds=1, retries=1, deadline=600)  # local: no propagation delay
            st, root_html = fetch(base)
            st2, _ = fetch(f"http://127.0.0.1:{port}/MicroRhodoDB/site/")
            st3, _ = fetch(base + "does-not-exist.html")
            bi_status, bi = fetch(base + "site/BUILD_INFO.json")
            stages.append({"stage": name, "served_files_checked": res["checked"], "served_files_ok": res["ok"],
                           "failed": res["failed"][:20], "root_redirect": b"url=site/" in root_html and st == 200,
                           "site_index_200": st2 == 200, "missing_path_404": st3 == 404,
                           "build_info_commit": json.loads(bi).get("source_commit") if bi_status == 200 else None})
        finally:
            srv.shutdown()
            srv.server_close()
    ok = all(not s["failed"] and s["served_files_ok"] == s["served_files_checked"] and s["root_redirect"]
             and s["site_index_200"] and s["missing_path_404"] for s in stages)
    ok = ok and stages[1]["build_info_commit"] is None and stages[0]["build_info_commit"] == stages[2]["build_info_commit"]
    return {"ok": ok, "stages": stages}


def cmd_drill(a) -> int:
    work = a.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    (work / "legacy_ref.json").write_text(json.dumps({"ref": a.legacy_ref}))
    res = drill(a.new.resolve(), a.legacy.resolve(), a.port, work)
    print(json.dumps(res, indent=2))
    if a.json:
        a.json.write_text(json.dumps(res, indent=2) + "\n")
    print("ROLLBACK_DRILL_PASS" if res["ok"] else "ROLLBACK_DRILL_FAIL")
    return 0 if res["ok"] else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("legacy-manifest"); p.add_argument("--ref", required=True); p.set_defaults(fn=cmd_legacy_manifest)
    p = sub.add_parser("legacy-build"); p.add_argument("--ref", required=True); p.add_argument("--out", type=Path, required=True)
    p.set_defaults(fn=cmd_legacy_build)
    p = sub.add_parser("verify-served"); p.add_argument("--base", required=True); p.add_argument("--sums", type=Path, required=True)
    p.add_argument("--paths", nargs="*"); p.add_argument("--json", type=Path)
    p.add_argument("--exclude-hidden", action="store_true", help="skip manifest paths with a dot-file/dot-directory component")
    p.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="concurrent requests (bounded)")
    p.add_argument("--request-timeout", type=float, default=DEFAULT_REQUEST_TIMEOUT, help="per-request wall-clock limit, s")
    p.add_argument("--deadline", type=float, default=DEFAULT_DEADLINE, help="total wall-clock limit for the whole run, s")
    p.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="per-file retries for transient failures")
    p.add_argument("--round-wait", type=float, default=DEFAULT_ROUND_WAIT, help="wait before re-checking files still wrong (CDN propagation), s")
    p.add_argument("--max-rounds", type=int, default=None)
    p.set_defaults(fn=cmd_verify_served)
    p = sub.add_parser("compare"); p.add_argument("a", type=Path); p.add_argument("b", type=Path); p.add_argument("--json", type=Path)
    p.set_defaults(fn=cmd_compare)
    p = sub.add_parser("drill"); p.add_argument("--new", type=Path, required=True); p.add_argument("--legacy", type=Path, required=True)
    p.add_argument("--legacy-ref", required=True); p.add_argument("--port", type=int, default=4340)
    p.add_argument("--work", type=Path, required=True); p.add_argument("--json", type=Path); p.set_defaults(fn=cmd_drill)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
