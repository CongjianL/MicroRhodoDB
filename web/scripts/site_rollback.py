#!/usr/bin/env python3
"""PR-7: rollback and recovery tooling for the MicroRhodoDB GitHub Pages site.

Sub-commands
  legacy-build   --ref SHA --out DIR    Recreate the pre-redesign production site (branch-based Pages from main,
                                        repository root, .nojekyll) as an artifact: `git archive SHA`, verified
                                        file-by-file against web/release/rollback/legacy_<sha12>.sha256.
  legacy-manifest --ref SHA             Write that manifest (done once; committed with PR-7).
  verify-served  --base URL --sums FILE [--paths P ...]
                                        Fetch files from a served site (local server or the live site) and compare
                                        them with a SHA256SUMS-style manifest. Read-only (HTTP GET).
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
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import threading
import urllib.error
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


def fetch(url: str, timeout: int = 60) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "mrdb-site-rollback", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def verify_served(base: str, sums: dict[str, str], paths: list[str] | None = None) -> dict:
    base = base if base.endswith("/") else base + "/"
    todo = paths or sorted(sums)
    bad, ok = [], 0
    for r in todo:
        if r not in sums:
            bad.append(f"{r}: not in manifest")
            continue
        status, body = fetch(base + r)
        if status != 200:
            bad.append(f"{r}: HTTP {status}")
        elif sha256_bytes(body) != sums[r]:
            bad.append(f"{r}: served bytes differ ({sha256_bytes(body)[:12]} != {sums[r][:12]})")
        else:
            ok += 1
    return {"base": base, "checked": len(todo), "ok": ok, "failed": bad}


def cmd_verify_served(a) -> int:
    res = verify_served(a.base, read_sums(a.sums), a.paths)
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
            res = verify_served(base, sums)
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
    p.add_argument("--paths", nargs="*"); p.add_argument("--json", type=Path); p.set_defaults(fn=cmd_verify_served)
    p = sub.add_parser("compare"); p.add_argument("a", type=Path); p.add_argument("b", type=Path); p.add_argument("--json", type=Path)
    p.set_defaults(fn=cmd_compare)
    p = sub.add_parser("drill"); p.add_argument("--new", type=Path, required=True); p.add_argument("--legacy", type=Path, required=True)
    p.add_argument("--legacy-ref", required=True); p.add_argument("--port", type=int, default=4340)
    p.add_argument("--work", type=Path, required=True); p.add_argument("--json", type=Path); p.set_defaults(fn=cmd_drill)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
