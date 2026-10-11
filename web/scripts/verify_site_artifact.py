#!/usr/bin/env python3
"""PR-7: offline verification of a MicroRhodoDB GitHub Pages deployment artifact.

The artifact is the directory that becomes https://congjianl.github.io/MicroRhodoDB/ :

  index.html            repository-root redirect to site/ (byte-identical to the repository's index.html)
  SHA256SUMS            SHA-256 of every other file in the artifact
  site/index.html       website 2.0 entry point (Vite base /MicroRhodoDB/site/)
  site/assets/...       hashed JS/CSS/WASM/font assets
  site/data/...         the exporter output (export_manifest.json lists every data file with SHA-256)
  site/BUILD_INFO.json  provenance: source commit, dataset release, source DB, tree, export manifest, toolchain

Checks (all must pass; the report names each one):
  V1  layout, no hidden files / symlinks / forbidden files (upload-pages-artifact drops dot-files)
  V2  SHA256SUMS covers exactly the artifact files and every hash matches
  V3  BUILD_INFO.json provenance agrees with web/release/release_contract.json, the export and SHA256SUMS
  V4  base path: every asset referenced by site/index.html and by JS/CSS exists under /MicroRhodoDB/site/
  V5  data: the files under site/data are exactly export_manifest.json (+ itself), hashes and sizes match,
      dataset release / schema / source DB SHA-256 equal the release contract
  V6  every data JSON parses and validates against the web-data JSON Schema (x-files mapping)
  V7  reference tree byte-identical to the frozen refpkg tree (contract SHA-256)
  V8  downloads.json: website-derived files exist; repository documents link to the build commit with the
      shipped SHA-256 (and, with --repo, equal the file at that commit); release/refpkg hashes equal the repo
  V9  security: CSP meta present; no localhost / test-server / sandbox paths in shipped text files
  V10 GitHub Pages limits (file < 100 MB, total < 1 GB)
  V11 (with --repo) the official SQLite database matches the contract SHA-256 and size

Usage:
  python web/scripts/verify_site_artifact.py ARTIFACT_DIR [--repo .] [--expect-commit SHA] [--require-clean] [--json report.json]
Exit 0 = all checks pass, 1 = at least one check failed, 2 = usage error.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

REPO = Path(__file__).resolve().parents[2]
CONTRACT = Path("web/release/release_contract.json")
TEXT_EXT = {".html", ".js", ".css", ".json", ".txt", ".fasta", ".tsv", ".md", ".svg", ".treefile", ".nwk"}
FORBIDDEN_NAMES = re.compile(r"(^|/)(node_modules|\.git|\.env[^/]*|__pycache__)(/|$)|\.map$|\.pyc$")
LEAK = re.compile(r"(localhost:\d|127\.0\.0\.1|/__test__/|/workspace/|/mnt/|file:///)")
ASSET_REF = re.compile(r"""["'`(](?:\./|/MicroRhodoDB/site/assets/|assets/)([A-Za-z0-9_.-]+-[A-Za-z0-9_-]{6,}\.(?:js|mjs|css|wasm|woff2?|ttf|otf|svg|png|jpg|webp))["'`)?#]""")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def content_digest(lines: list[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(lines)) + "\n").encode()).hexdigest()


class Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs: list[str] = []
        self.csp: str | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for k in ("src", "href"):
            if a.get(k):
                self.refs.append(a[k])
        if tag == "meta" and (a.get("http-equiv") or "").lower() == "content-security-policy":
            self.csp = a.get("content")


class Report:
    def __init__(self):
        self.checks: list[dict] = []

    def add(self, cid: str, name: str, errors: list[str], info: str = ""):
        self.checks.append({"id": cid, "name": name, "ok": not errors, "errors": errors[:50],
                            "n_errors": len(errors), "info": info})

    @property
    def ok(self) -> bool:
        return all(c["ok"] for c in self.checks)


def git_show(repo: Path, commit: str, path: str) -> bytes | None:
    r = subprocess.run(["git", "-C", str(repo), "show", f"{commit}:{path}"], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def verify(art: Path, repo: Path | None = None, expect_commit: str | None = None, require_clean: bool = False,
           contract_path: Path | None = None) -> Report:
    rep = Report()
    contract = json.loads(((repo or REPO) / (contract_path or CONTRACT)).read_text())
    base = contract["base_path"]                     # /MicroRhodoDB/site/
    site = art / "site"
    files = sorted(p for p in art.rglob("*") if p.is_file() or p.is_symlink())
    rel = [p.relative_to(art).as_posix() for p in files]

    # V1 layout
    e = []
    for need in ("index.html", "SHA256SUMS", "site/index.html", "site/BUILD_INFO.json", "site/data/current.json"):
        if not (art / need).is_file():
            e.append(f"missing {need}")
    for p, r in zip(files, rel):
        if p.is_symlink():
            e.append(f"symlink {r}")
        if any(part.startswith(".") for part in Path(r).parts):
            e.append(f"hidden path (dropped by upload-pages-artifact) {r}")
        if FORBIDDEN_NAMES.search(r):
            e.append(f"forbidden file {r}")
    top = sorted({Path(r).parts[0] for r in rel})
    if set(top) - {"index.html", "SHA256SUMS", "site"}:
        e.append(f"unexpected top-level entries {sorted(set(top) - {'index.html', 'SHA256SUMS', 'site'})}")
    root_html = (art / "index.html").read_text(errors="replace") if (art / "index.html").is_file() else ""
    if 'url=site/' not in root_html:
        e.append("root index.html does not redirect to site/")
    if repo is not None and (art / "index.html").is_file():
        commit = expect_commit
        if commit is None and (site / "BUILD_INFO.json").is_file():
            try:
                commit = json.loads((site / "BUILD_INFO.json").read_text()).get("source_commit")
            except json.JSONDecodeError:
                commit = None
        want = git_show(repo, commit, "index.html") if commit else None
        if want is not None and want != (art / "index.html").read_bytes():
            e.append("root index.html differs from the repository index.html at the source commit")
    rep.add("V1", "artifact layout", e, f"{len(rel)} files")

    # V2 SHA256SUMS
    e = []
    sums: dict[str, str] = {}
    if (art / "SHA256SUMS").is_file():
        for ln in (art / "SHA256SUMS").read_text().splitlines():
            m = re.fullmatch(r"([0-9a-f]{64})  (.+)", ln)
            if not m:
                e.append(f"malformed SHA256SUMS line {ln[:80]!r}")
                continue
            sums[m.group(2)] = m.group(1)
        listed = set(sums)
        actual = set(rel) - {"SHA256SUMS"}
        e += [f"not in SHA256SUMS: {x}" for x in sorted(actual - listed)]
        e += [f"listed but missing: {x}" for x in sorted(listed - actual)]
        for r in sorted(listed & actual):
            if sha256(art / r) != sums[r]:
                e.append(f"hash mismatch {r}")
        if list((art / "SHA256SUMS").read_text().splitlines()) != sorted((art / "SHA256SUMS").read_text().splitlines(), key=lambda s: s[66:]):
            e.append("SHA256SUMS is not sorted by path")
    rep.add("V2", "SHA256SUMS", e, f"{len(sums)} entries")

    # V3 BUILD_INFO
    e = []
    bi: dict = {}
    try:
        bi = json.loads((site / "BUILD_INFO.json").read_text())
    except (OSError, json.JSONDecodeError) as x:
        e.append(f"BUILD_INFO.json unreadable: {x}")
    if bi:
        for k in ("artifact_format", "website_version", "dataset_release", "schema_version", "source_commit",
                  "source_tree_clean", "source_date_epoch", "base_path", "source_db", "reference_tree",
                  "export_manifest", "content_sha256", "n_files", "toolchain"):
            if k not in bi:
                e.append(f"BUILD_INFO missing {k}")
        if not re.fullmatch(r"[0-9a-f]{40}", str(bi.get("source_commit", ""))):
            e.append("source_commit is not a 40-hex commit")
        if expect_commit and bi.get("source_commit") != expect_commit:
            e.append(f"source_commit {bi.get('source_commit')} != expected {expect_commit}")
        if require_clean and bi.get("source_tree_clean") is not True:
            e.append("built from a dirty working tree (production requires a clean checkout)")
        if bi.get("base_path") != base:
            e.append(f"base_path {bi.get('base_path')} != {base}")
        if bi.get("dataset_release") != contract["dataset_release"]:
            e.append("dataset_release differs from the contract")
        if bi.get("schema_version") != contract["schema_version"]:
            e.append("schema_version differs from the contract")
        db = bi.get("source_db") or {}
        if db.get("sha256") != contract["source_db"]["sha256"] or db.get("bytes") != contract["source_db"]["bytes"]:
            e.append("source_db SHA-256/size differ from the contract")
        if (bi.get("reference_tree") or {}).get("sha256") != contract["reference_tree"]["sha256"]:
            e.append("reference_tree SHA-256 differs from the contract")
        em = bi.get("export_manifest") or {}
        emp = art / str(em.get("path", ""))
        if not emp.is_file() or sha256(emp) != em.get("sha256"):
            e.append("export_manifest path/SHA-256 in BUILD_INFO do not match the artifact")
        content = [f"{h}  {r}" for r, h in sums.items() if r != "site/BUILD_INFO.json"]
        if sums and bi.get("content_sha256") != content_digest(content):
            e.append("content_sha256 does not match SHA256SUMS (excluding BUILD_INFO.json)")
        if sums and bi.get("n_files") != len(content):
            e.append(f"n_files {bi.get('n_files')} != {len(content)}")
    rep.add("V3", "BUILD_INFO provenance", e, f"commit {bi.get('source_commit')}")

    # V4 base path and assets
    e = []
    n_refs = 0
    if (site / "index.html").is_file():
        pr = Refs()
        pr.feed((site / "index.html").read_text())
        for ref in pr.refs:
            if re.match(r"^(https?:)?//", ref) or ref.startswith(("#", "data:", "mailto:")):
                continue
            n_refs += 1
            url = urljoin(base, ref)  # relative references resolve against the served page /MicroRhodoDB/site/
            if not url.startswith(base) or "/../" in url:
                e.append(f"site/index.html reference outside base path: {ref}")
                continue
            target = site / url[len(base):].split("?")[0].split("#")[0]
            if not target.is_file():
                e.append(f"site/index.html references missing file {ref}")
        rep_csp = pr.csp
    else:
        rep_csp = None
    assets = site / "assets"
    names = {p.name for p in assets.rglob("*") if p.is_file()} if assets.is_dir() else set()
    if not names:
        e.append("no site/assets")
    for p in sorted(assets.rglob("*")) if assets.is_dir() else []:
        if p.suffix in (".js", ".mjs", ".css") and p.is_file():
            for m in ASSET_REF.finditer(p.read_text(errors="replace")):
                n_refs += 1
                if m.group(1) not in names:
                    e.append(f"{p.relative_to(art)} references missing asset {m.group(1)}")
    for p in sorted(site.rglob("*.html")) if site.is_dir() else []:
        txt = p.read_text(errors="replace")
        for m in re.finditer(r"""(?:src|href)=["'](/[^"']+)["']""", txt):
            if not m.group(1).startswith(base):
                e.append(f"{p.relative_to(art)}: absolute reference outside {base}: {m.group(1)}")
    rep.add("V4", "base path and asset references", e, f"{n_refs} references checked, {len(names)} asset files")

    # V5 data vs export manifest
    e = []
    data = site / "data"
    cur = {}
    try:
        cur = json.loads((data / "current.json").read_text())
    except (OSError, json.JSONDecodeError) as x:
        e.append(f"current.json: {x}")
    ver = contract["dataset_release"]
    if cur and (cur.get("dataset_release") != ver or cur.get("path") != f"data/v{ver}/"):
        e.append(f"current.json points to {cur}")
    emp = data / f"v{ver}" / "export_manifest.json"
    man = {}
    try:
        man = json.loads(emp.read_text())
    except (OSError, json.JSONDecodeError) as x:
        e.append(f"export_manifest.json: {x}")
    if man:
        if man.get("dataset_release") != ver or man.get("schema_version") != contract["schema_version"]:
            e.append("export manifest release/schema differ from the contract")
        if man.get("source_db_sha256") != contract["source_db"]["sha256"]:
            e.append("export manifest source_db_sha256 differs from the contract")
        listed = {f["path"]: f for f in man.get("files", [])}
        actual = {p.relative_to(data).as_posix() for p in data.rglob("*") if p.is_file()} if data.is_dir() else set()
        actual.discard(f"v{ver}/export_manifest.json")
        e += [f"data file not in export manifest: {x}" for x in sorted(actual - set(listed))][:20]
        e += [f"export manifest file missing: {x}" for x in sorted(set(listed) - actual)][:20]
        bad = [x for x in sorted(set(listed) & actual)
               if sha256(data / x) != listed[x]["sha256"] or (data / x).stat().st_size != listed[x]["bytes"]]
        e += [f"data file differs from export manifest: {x}" for x in bad[:20]]
        if man.get("n_files") != len(listed):
            e.append("export manifest n_files mismatch")
        if repo is not None and bi.get("source_commit") and man.get("exporter_git_commit") != bi.get("source_commit"):
            e.append("export was produced at a different commit than the build")
        if require_clean and man.get("exporter_git_dirty") is not False:
            e.append("export was produced from a dirty working tree")
    rep.add("V5", "data files vs export manifest", e, f"{len(man.get('files', []))} manifest files")

    # V6 JSON schema
    e = []
    n_json = 0
    try:
        import jsonschema  # noqa: PLC0415
    except ImportError:
        jsonschema = None
        e.append("jsonschema is not installed (required for V6)")
    schema_p = (repo or REPO) / "web/src/data/schemas/web-data.schema.json"
    if jsonschema is not None and data.is_dir():
        schema = json.loads(schema_p.read_text())
        validators = {}
        for p in sorted(data.rglob("*.json")):
            r = p.relative_to(data).as_posix()
            n_json += 1
            try:
                obj = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError as x:
                e.append(f"{r}: invalid JSON ({x})")
                continue
            pats = [k for k in schema["x-files"] if fnmatch.fnmatch(r, k)]
            if len(pats) != 1:
                e.append(f"{r}: {len(pats)} schema patterns match")
                continue
            name = schema["x-files"][pats[0]]
            if name not in validators:
                validators[name] = jsonschema.Draft202012Validator(
                    {"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": f"#/$defs/{name}"})
            err = next(iter(validators[name].iter_errors(obj)), None)
            if err is not None:
                e.append(f"{r}: schema {name}: {err.message[:200]}")
    rep.add("V6", "JSON integrity and schema", e, f"{n_json} JSON files")

    # V7 reference tree
    e = []
    tree = art / contract["reference_tree"]["artifact_path"]
    if not tree.is_file():
        e.append(f"missing {contract['reference_tree']['artifact_path']}")
    elif sha256(tree) != contract["reference_tree"]["sha256"]:
        e.append("reference tree differs from the frozen refpkg tree")
    if repo is not None and (repo / contract["reference_tree"]["path"]).is_file() and tree.is_file():
        if tree.read_bytes() != (repo / contract["reference_tree"]["path"]).read_bytes():
            e.append("reference tree is not byte-identical to the repository refpkg file")
    rep.add("V7", "reference tree", e)

    # V8 downloads
    e = []
    try:
        dl = json.loads((data / f"v{ver}" / "downloads.json").read_text())
    except (OSError, json.JSONDecodeError) as x:
        dl = None
        e.append(f"downloads.json: {x}")
    if dl:
        for f in dl.get("website_derived", []):
            if not (data / f"v{ver}" / f["path"]).is_file():
                e.append(f"website-derived download missing: {f['path']}")
        commit = bi.get("source_commit")
        for f in dl.get("repository_documents", []):
            want_url = f"{contract['repository_url']}/blob/{commit}/{f['path']}"
            if f.get("url") != want_url:
                e.append(f"repository document {f['path']} links to {f.get('url')} (expected {want_url})")
            if repo is not None and commit:
                blob = git_show(repo, commit, f["path"])
                if blob is None:
                    e.append(f"repository document {f['path']} absent at {commit}")
                elif hashlib.sha256(blob).hexdigest() != f["sha256"] or len(blob) != f["bytes"]:
                    e.append(f"repository document {f['path']}: shipped SHA-256/size differ from the file at {commit[:12]}")
        dbrow = [f for f in dl.get("release_files", []) if f["path"].endswith(".sqlite")]
        if len(dbrow) != 1 or dbrow[0]["sha256"] != contract["source_db"]["sha256"] or dbrow[0]["bytes"] != contract["source_db"]["bytes"]:
            e.append("downloads.json release database row differs from the contract")
        if repo is not None:
            for f in dl.get("release_files", []):
                p = repo / "releases" / f"v{ver}" / f["path"]
                if f.get("in_git_at_tag") and (not p.is_file() or sha256(p) != f["sha256"]):
                    e.append(f"release file {f['path']} differs from the repository")
            for f in dl.get("refpkg_files", []):
                p = repo / "refpkg/MR_RT_003" / f["path"]
                if not p.is_file() or sha256(p) != f["sha256"]:
                    e.append(f"refpkg file {f['path']} differs from the repository")
    rep.add("V8", "download paths and checksums", e)

    # V9 security / leakage
    e = []
    if not rep_csp or "default-src 'self'" not in rep_csp:
        e.append("Content-Security-Policy meta tag missing or without default-src 'self'")
    for p, r in zip(files, rel):
        if p.suffix in TEXT_EXT and not r.startswith("site/data/") and p.stat().st_size < 20_000_000:
            m = LEAK.search(p.read_text(errors="replace"))
            if m:
                e.append(f"{r}: contains {m.group(1)!r}")
    rep.add("V9", "security and leakage", e)

    # V10 Pages limits
    e = []
    total = 0
    for p, r in zip(files, rel):
        s = p.stat().st_size
        total += s
        if s >= contract["limits"]["max_file_bytes"]:
            e.append(f"{r} is {s} bytes")
    if total >= contract["limits"]["max_total_bytes"]:
        e.append(f"total {total} bytes")
    rep.add("V10", "GitHub Pages size limits", e, f"{total} bytes")

    # V11 official DB
    if repo is not None:
        e = []
        dbp = repo / contract["source_db"]["path"]
        if not dbp.is_file():
            e.append(f"BLOCKED_DATA_SOURCE: {contract['source_db']['path']} not present")
        elif dbp.stat().st_size != contract["source_db"]["bytes"] or sha256(dbp) != contract["source_db"]["sha256"]:
            e.append("official SQLite database SHA-256/size differ from the contract")
        rep.add("V11", "official SQLite database", e)
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("artifact", type=Path)
    ap.add_argument("--repo", type=Path, help="repository checkout for cross-checks (V1 root page, V7, V8, V11)")
    ap.add_argument("--expect-commit")
    ap.add_argument("--require-clean", action="store_true")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    if not a.artifact.is_dir():
        print(f"verify_site_artifact: {a.artifact} is not a directory", file=sys.stderr)
        return 2
    rep = verify(a.artifact.resolve(), a.repo.resolve() if a.repo else None, a.expect_commit, a.require_clean)
    for c in rep.checks:
        print(f"{'PASS' if c['ok'] else 'FAIL'} {c['id']:4} {c['name']}" + (f" ({c['info']})" if c["info"] else ""))
        for x in c["errors"][:10]:
            print(f"       - {x}")
    print("ARTIFACT_VERIFIED" if rep.ok else "ARTIFACT_VERIFICATION_FAILED")
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps({"artifact": str(a.artifact), "ok": rep.ok, "checks": rep.checks}, indent=2) + "\n")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    sys.exit(main())
