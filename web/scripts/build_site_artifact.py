#!/usr/bin/env python3
"""PR-7: deterministic production build of the MicroRhodoDB GitHub Pages artifact.

Steps (any failure stops the build with a non-zero exit):
  1. Provenance: source commit, clean/dirty working tree, SOURCE_DATE_EPOCH = commit time.
     --production refuses a dirty tree.
  2. Inputs: the official SQLite database and the frozen reference tree must match
     web/release/release_contract.json (SHA-256 and size), else BLOCKED_DATA_SOURCE.
  3. Export: web/public/data is deleted and regenerated with tools/export_web_data.py (read-only on the DB).
  4. Frontend: `npm run build` (tsc + Vite, base /MicroRhodoDB/site/) with SOURCE_DATE_EPOCH, TZ=UTC and the
     build commit/date injected for the footer.
  5. Assemble OUT/: index.html (the repository root redirect, byte copy), site/ (= web/dist/site),
     site/BUILD_INFO.json (provenance), SHA256SUMS (every other file, sorted by path).
  6. Optional deterministic tarball (--tarball): sorted entries, mtime = SOURCE_DATE_EPOCH, uid/gid 0, gzip mtime 0.
  7. verify_site_artifact.py on OUT (with --repo, --expect-commit; --require-clean in production).

Two builds of the same commit with the same toolchain produce byte-identical artifacts and tarballs
(checked by tests/test_web_pr7.py and docs/website/pr7/logs).

Usage:
  python web/scripts/build_site_artifact.py --out /tmp/mrdb-site [--production] [--tarball /tmp/mrdb-site.tar.gz]
         [--skip-export] [--skip-npm]
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "web"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_site_artifact as V  # noqa: E402


class BuildError(RuntimeError):
    pass


def run(cmd: list[str], cwd: Path, env: dict | None = None) -> str:
    print("+", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=str(cwd), env=env, text=True, capture_output=True)
    if r.returncode != 0:
        sys.stdout.write(r.stdout[-4000:])
        sys.stderr.write(r.stderr[-4000:])
        raise BuildError(f"command failed ({r.returncode}): {' '.join(cmd)}")
    return r.stdout


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=True).stdout.strip()


def tool_version(cmd: list[str]) -> str | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def provenance() -> dict:
    commit = git("rev-parse", "HEAD")
    dirty = bool(git("status", "--porcelain", "--untracked-files=normal"))
    epoch = int(git("log", "-1", "--format=%ct", commit))
    return {"commit": commit, "clean": not dirty, "epoch": epoch}


def check_inputs(contract: dict) -> None:
    db = REPO / contract["source_db"]["path"]
    if not db.is_file():
        raise BuildError(f"BLOCKED_DATA_SOURCE: {contract['source_db']['path']} is missing "
                         "(python web/scripts/fetch_release_db.py downloads and verifies it)")
    if db.stat().st_size != contract["source_db"]["bytes"] or V.sha256(db) != contract["source_db"]["sha256"]:
        raise BuildError("BLOCKED_DATA_SOURCE: the SQLite database differs from the release contract")
    tree = REPO / contract["reference_tree"]["path"]
    if not tree.is_file() or V.sha256(tree) != contract["reference_tree"]["sha256"]:
        raise BuildError("frozen reference tree differs from the release contract")


def write_sums(out: Path) -> dict[str, str]:
    sums = {}
    for p in sorted(out.rglob("*")):
        if p.is_file():
            r = p.relative_to(out).as_posix()
            if r != "SHA256SUMS":
                sums[r] = V.sha256(p)
    (out / "SHA256SUMS").write_text("".join(f"{h}  {r}\n" for r, h in sorted(sums.items())))
    return sums


def deterministic_tar(src: Path, dest: Path, epoch: int) -> str:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
        for p in sorted(src.rglob("*"), key=lambda q: q.relative_to(src).as_posix()):
            ti = tarfile.TarInfo(p.relative_to(src).as_posix())
            ti.mtime, ti.uid, ti.gid, ti.uname, ti.gname = epoch, 0, 0, "", ""
            if p.is_dir():
                ti.type, ti.mode = tarfile.DIRTYPE, 0o755
                tf.addfile(ti)
            else:
                ti.size, ti.mode = p.stat().st_size, 0o644
                with p.open("rb") as f:
                    tf.addfile(ti, f)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as gz:
        gz.write(buf.getvalue())
    return V.sha256(dest)


def build(out: Path, production: bool, tarball: Path | None, skip_export: bool, skip_npm: bool) -> dict:
    contract = json.loads((REPO / V.CONTRACT).read_text())
    prov = provenance()
    if production and not prov["clean"]:
        raise BuildError("--production requires a clean working tree (commit or stash local changes)")
    print(f"source commit {prov['commit']} clean={prov['clean']} SOURCE_DATE_EPOCH={prov['epoch']}")
    check_inputs(contract)

    py = sys.executable
    if not skip_export:
        shutil.rmtree(WEB / "public" / "data", ignore_errors=True)
        run([py, "tools/export_web_data.py", "--repo", ".", "--out", "web/public/data"], REPO)
    date = dt.datetime.fromtimestamp(prov["epoch"], dt.timezone.utc).strftime("%Y-%m-%d")
    env = {**os.environ, "SOURCE_DATE_EPOCH": str(prov["epoch"]), "TZ": "UTC",
           "MRDB_BUILD_COMMIT": prov["commit"], "MRDB_BUILD_DATE": date}
    if not skip_npm:
        run(["npm", "run", "build"], WEB, env)
    dist = WEB / "dist" / "site"
    if not (dist / "index.html").is_file():
        raise BuildError("web/dist/site/index.html missing (npm run build)")

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copyfile(REPO / "index.html", out / "index.html")
    shutil.copytree(dist, out / "site")

    ver = contract["dataset_release"]
    em_rel = f"site/data/v{ver}/export_manifest.json"
    em = json.loads((out / em_rel).read_text())
    pkg = json.loads((WEB / "package.json").read_text())
    pre = write_sums(out)  # temporary, to compute the content digest without BUILD_INFO
    content = [f"{h}  {r}" for r, h in pre.items()]
    info = {
        "artifact_format": 1,
        "website_version": pkg["version"],
        "dataset_release": ver,
        "schema_version": em["schema_version"],
        "source_commit": prov["commit"],
        "source_tree_clean": prov["clean"],
        "source_date_epoch": prov["epoch"],
        "build_date_utc": date,
        "base_path": contract["base_path"],
        "pages_url": contract["pages_url"],
        "source_db": dict(contract["source_db"]),
        "reference_tree": dict(contract["reference_tree"]),
        "export_manifest": {"path": em_rel, "sha256": V.sha256(out / em_rel), "n_files": em["n_files"],
                            "total_bytes": em["total_bytes"], "exporter_git_commit": em["exporter_git_commit"],
                            "exporter_git_dirty": em["exporter_git_dirty"]},
        "content_sha256": V.content_digest(content),
        "n_files": len(content),
        "toolchain": {"node": tool_version(["node", "--version"]), "npm": tool_version(["npm", "--version"]),
                      "python": platform.python_version(),
                      "package_lock_sha256": V.sha256(WEB / "package-lock.json")},
        "verification": "python web/scripts/verify_site_artifact.py <artifact> --repo . --expect-commit <source_commit>",
    }
    (out / "site" / "BUILD_INFO.json").write_text(json.dumps(info, indent=2, sort_keys=True) + "\n")
    write_sums(out)

    res = {"out": str(out), "build_info": info, "sha256sums_sha256": V.sha256(out / "SHA256SUMS")}
    if tarball:
        res["tarball"] = str(tarball)
        res["tarball_sha256"] = deterministic_tar(out, tarball, prov["epoch"])
        tarball.with_name(tarball.name + ".sha256").write_text(f"{res['tarball_sha256']}  {tarball.name}\n")

    rep = V.verify(out, REPO, prov["commit"], require_clean=production)
    for c in rep.checks:
        print(f"{'PASS' if c['ok'] else 'FAIL'} {c['id']:4} {c['name']}" + (f" ({c['info']})" if c["info"] else ""))
        for x in c["errors"][:10]:
            print(f"       - {x}")
    if not rep.ok:
        raise BuildError("artifact verification failed")
    print(f"ARTIFACT_VERIFIED {out} commit={prov['commit']} files={info['n_files'] + 1} "
          f"content_sha256={info['content_sha256']}" + (f" tarball_sha256={res.get('tarball_sha256')}" if tarball else ""))
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True, help="artifact directory (deleted and recreated)")
    ap.add_argument("--production", action="store_true", help="require a clean tree and a clean export")
    ap.add_argument("--tarball", type=Path, help="also write a deterministic .tar.gz (+ .sha256)")
    ap.add_argument("--skip-export", action="store_true", help="reuse web/public/data (development only)")
    ap.add_argument("--skip-npm", action="store_true", help="reuse web/dist/site (development only)")
    ap.add_argument("--json", type=Path, help="write the build summary as JSON")
    a = ap.parse_args(argv)
    if a.production and (a.skip_export or a.skip_npm):
        print("build_site_artifact: --production cannot be combined with --skip-export/--skip-npm", file=sys.stderr)
        return 2
    out = a.out.resolve()
    if out == REPO or REPO in out.parents and not str(out).startswith(str(REPO / "web" / "dist")):
        print("build_site_artifact: --out must be outside the repository (or under web/dist)", file=sys.stderr)
        return 2
    try:
        res = build(out, a.production, a.tarball.resolve() if a.tarball else None, a.skip_export, a.skip_npm)
    except BuildError as e:
        print(f"BUILD_FAILED: {e}", file=sys.stderr)
        return 1
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(res, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
