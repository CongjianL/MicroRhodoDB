#!/usr/bin/env python3
"""PR-7 release-blocker gate for the MicroRhodoDB website (production deployment only).

The checklist lives in docs/website/release_blockers.json. A blocker counts as resolved only when BOTH
  (a) the JSON entry has status "resolved" with a maintainer resolution record (decided_by, decided_at, reference), and
  (b) its automated check, if it has one, passes against the repository (and, with --online, GitHub/doi.org).
A JSON entry flipped to "resolved" while its check still fails stays blocked, and a passing check without a
maintainer record also stays blocked, so a blocker cannot be waived silently in either direction.

Modes:
  --mode report       print the checklist and exit 0 (local development, previews, CI validation)
  --mode production   exit 3 if any blocker is unresolved (used only by the manual production deploy workflow)

The gate never edits metadata and never decides anything; it only reports.
Usage:
  python web/scripts/release_gate.py --mode report
  python web/scripts/release_gate.py --mode production --online --sha <commit> [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BLOCKERS = Path("docs/website/release_blockers.json")
GH_API = "https://api.github.com"
OWNER_REPO = "CongjianL/MicroRhodoDB"
PLACEHOLDER = re.compile(r"<<\s*PLACEHOLDER")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
RESOLUTION_FIELDS = ("decided_by", "decided_at", "reference")


# --------------------------------------------------------------------------------------------- helpers
def read(repo: Path, rel: str) -> str:
    p = repo / rel
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def cff_field(text: str, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", text, re.M)
    return m.group(1).strip().strip('"').strip("'") if m else None


def gh_get(path: str, token: str | None):
    req = urllib.request.Request(GH_API + path, headers={"Accept": "application/vnd.github+json",
                                                         "X-GitHub-Api-Version": "2022-11-28",
                                                         "User-Agent": "mrdb-release-gate"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def norm_licence(s: str | None) -> str | None:
    if not s:
        return None
    t = s.upper().replace("_", "-").replace(" ", "-")
    if "CC-BY-4.0" in t or "CC-BY-4" in t or "ATTRIBUTION-4.0" in t:
        return "CC-BY-4.0"
    if re.search(r"\bMIT\b", t):
        return "MIT"
    return s.strip()


# ---------------------------------------------------------------------------------------------- checks
# Each check returns (ok: bool | None, detail: str). None = cannot be decided here (counts as not passing).

def check_md1_licence(repo: Path, ctx: dict):
    """Data and code licence statements agree across LICENSE, README, CITATION.cff, .zenodo.json and web/package.json."""
    lic = read(repo, "LICENSE")
    readme = read(repo, "README.md")
    data, code = {}, {}
    m = re.search(r"licensed under the (.+?)\(", lic.replace("\n", " "))
    data["LICENSE"] = norm_licence(m.group(1)) if m else None
    if re.search(r"Source code .*? is released under the same\s+terms", lic, re.S):
        code["LICENSE"] = data["LICENSE"]
    else:
        m = re.search(r"Source code[^.]*?released under (?:the )?([A-Za-z0-9 .-]+?)(?:\s+licen[cs]e|\.)", lic, re.S)
        code["LICENSE"] = norm_licence(m.group(1)) if m else None
    # "Data: CC BY 4.0. Code: MIT." - licence names may contain periods (4.0, Apache-2.0); a README without the
    # statement counts as missing (None), never as agreeing.
    m = re.search(r"Data:\s*(.+?)\.\s+Code:\s*(.+?)\.?(?:\s|$)", readme, re.M)
    data["README.md"], code["README.md"] = (norm_licence(m.group(1)), norm_licence(m.group(2))) if m else (None, None)
    data["CITATION.cff"] = norm_licence(cff_field(read(repo, "CITATION.cff"), "license"))
    try:
        data[".zenodo.json"] = norm_licence(json.loads(read(repo, ".zenodo.json") or "{}").get("license"))
    except json.JSONDecodeError:
        data[".zenodo.json"] = None
    try:
        code["web/package.json"] = norm_licence(json.loads(read(repo, "web/package.json")).get("license"))
    except (json.JSONDecodeError, FileNotFoundError):
        code["web/package.json"] = None
    dv = {k: v for k, v in data.items()}
    cv = {k: v for k, v in code.items()}
    ok = None not in dv.values() and None not in cv.values() and len(set(dv.values())) == 1 and len(set(cv.values())) == 1
    return ok, f"data licence statements {dv}; code licence statements {cv}"


def check_md2_dates(repo: Path, ctx: dict):
    """One v1.6.0 release date across CITATION.cff, .zenodo.json, CHANGELOG.md, release notes and (online) the GitHub Release."""
    dates = {"CITATION.cff": cff_field(read(repo, "CITATION.cff"), "date-released")}
    try:
        dates[".zenodo.json"] = json.loads(read(repo, ".zenodo.json") or "{}").get("publication_date")
    except json.JSONDecodeError:
        dates[".zenodo.json"] = None
    m = re.search(r"^## \[1\.6\.0\]\s*-\s*(\d{4}-\d{2}-\d{2})", read(repo, "CHANGELOG.md"), re.M)
    dates["CHANGELOG.md"] = m.group(1) if m else None
    m = re.search(r"\*\*Release date:\*\*\s*(\d{4}-\d{2}-\d{2})", read(repo, "releases/v1.6.0/RELEASE_NOTES_v1.6.0.md"))
    dates["RELEASE_NOTES_v1.6.0.md"] = m.group(1) if m else None
    if ctx.get("release") is not None:
        dates["GitHub Release published_at (UTC)"] = (ctx["release"].get("published_at") or "")[:10] or None
    ok = None not in dates.values() and len(set(dates.values())) == 1
    return ok, f"release dates {dates}"


def check_md3_doi(repo: Path, ctx: dict):
    """CITATION.cff has a DOI, or the maintainer approved an alternative citation policy (resolution record)."""
    cff = read(repo, "CITATION.cff")
    doi = cff_field(cff, "doi")
    m = re.search(r"^\s*-?\s*type:\s*doi\s*\n\s*value:\s*(\S+)", cff, re.M)
    doi = doi or (m.group(1) if m else None)
    blocker = ctx["blocker"]
    alt = (blocker.get("resolution") or {}).get("alternative_citation_policy")
    if doi:
        if ctx.get("online"):
            try:
                req = urllib.request.Request(f"https://doi.org/api/handles/{doi}", headers={"User-Agent": "mrdb-release-gate"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    code = json.loads(r.read().decode()).get("responseCode")
                return code == 1, f"CITATION.cff doi {doi}; doi.org handle responseCode {code}"
            except (urllib.error.URLError, TimeoutError, ValueError) as e:
                return None, f"CITATION.cff doi {doi}; doi.org lookup failed: {e}"
        return None, f"CITATION.cff doi {doi}; not resolved offline (run with --online)"
    if alt:
        return True, f"no DOI; maintainer-approved alternative citation policy: {alt}"
    return False, "CITATION.cff has no DOI and no maintainer-approved alternative citation policy is recorded"


def check_md4_contact(repo: Path, ctx: dict):
    """A public support/contact channel is stated (no placeholder on the MAINTENANCE.md contact line)."""
    lines = [ln for ln in read(repo, "MAINTENANCE.md").splitlines() if ln.strip().lower().startswith("- contact")]
    if not lines:
        return False, "MAINTENANCE.md has no 'Contact' line"
    bad = [ln for ln in lines if PLACEHOLDER.search(ln)]
    return not bad, ("contact line still a placeholder: " + bad[0].strip()) if bad else f"contact line: {lines[0].strip()}"


def check_md5_maintenance(repo: Path, ctx: dict):
    """No <<PLACEHOLDER>> remains in MAINTENANCE.md (cadence, hosting term, DOI, funding, succession)."""
    hits = [ln.strip() for ln in read(repo, "MAINTENANCE.md").splitlines() if PLACEHOLDER.search(ln)]
    return not hits, f"{len(hits)} placeholder line(s) in MAINTENANCE.md" + (": " + " | ".join(hits) if hits else "")


def binaries_assets(repo: Path) -> tuple[list[dict], list[str]]:
    rows = re.findall(r"^\|\s*`([^`]+)`\s*\|\s*(\d+)\s*\|\s*`([0-9a-f]{64})`\s*\|", read(repo, "BINARIES.md"), re.M)
    dbs = [{"name": Path(p).name, "path": p, "size": int(n), "sha256": h} for p, n, h in rows]
    archives = sorted(set(re.findall(r"`(MicroRhodoDB_v[\d.]+\.tar\.gz)`", read(repo, "BINARIES.md"))))
    return dbs, archives


def check_ra1_release_assets(repo: Path, ctx: dict):
    """Every asset BINARIES.md says is attached to the v1.6.0 GitHub Release is attached, with the stated size."""
    dbs, archives = binaries_assets(repo)
    expected = {d["name"]: d["size"] for d in dbs}
    for a in archives:
        expected[a] = None
        expected[a + ".sha256"] = None
    rel = ctx.get("release")
    if rel is None:
        return None, f"BINARIES.md lists {len(expected)} Release assets; not checked offline (run with --online)"
    have = {a["name"]: a["size"] for a in rel.get("assets", [])}
    missing = sorted(n for n in expected if n not in have)
    wrong = sorted(n for n, s in expected.items() if n in have and s is not None and have[n] != s)
    ok = not missing and not wrong
    return ok, f"Release v1.6.0 has {sorted(have)}; missing {missing}; size mismatch {wrong}"


def check_ra2_zenodo(repo: Path, ctx: dict):
    """A Zenodo deposit claimed by BINARIES.md / MAINTENANCE.md is verifiable (DOI in CITATION.cff that resolves)."""
    claims = "Zenodo" in read(repo, "BINARIES.md") or "Zenodo" in read(repo, "MAINTENANCE.md")
    if not claims:
        return True, "no Zenodo deposit is claimed"
    ok, detail = check_md3_doi(repo, {**ctx, "blocker": {}})  # an alternative citation policy does not verify a deposit
    return ok, "Zenodo deposit claimed in BINARIES.md/MAINTENANCE.md; " + detail


def check_ops2_environment(repo: Path, ctx: dict):
    """github-pages environment: deployments only from main and at least one required reviewer."""
    if not ctx.get("online"):
        return None, "environment protection not checked offline (run with --online)"
    tok = ctx.get("token")
    try:
        env = gh_get(f"/repos/{OWNER_REPO}/environments/github-pages", tok)
        pol = gh_get(f"/repos/{OWNER_REPO}/environments/github-pages/deployment-branch-policies", tok)
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return None, f"GitHub environment API failed: {e}"
    types = [r.get("type") for r in env.get("protection_rules", [])]
    reviewers = any(t == "required_reviewers" for t in types)
    names = sorted(p.get("name") for p in pol.get("branch_policies", []))
    main_only = names == ["main"] and (env.get("deployment_branch_policy") or {}).get("custom_branch_policies") is True
    return reviewers and main_only, f"protection rules {types}; allowed deployment branches {names}"


def check_ci1_remote_ci(repo: Path, ctx: dict):
    """The web-data workflow concluded 'success' on GitHub for the commit being deployed."""
    sha = ctx.get("sha")
    if not ctx.get("online") or not sha:
        return None, "remote CI not checked (needs --online --sha <commit>)"
    try:
        runs = gh_get(f"/repos/{OWNER_REPO}/actions/runs?head_sha={sha}&per_page=100", ctx.get("token")).get("workflow_runs", [])
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        return None, f"GitHub Actions API failed: {e}"
    ok_runs = [r for r in runs if r.get("name") == "web-data" and r.get("conclusion") == "success"]
    return bool(ok_runs), (f"web-data success run {ok_runs[0].get('id')}" if ok_runs else
                           f"no successful web-data run for {sha} ({len(runs)} run(s) found)")


def check_ver1_version(repo: Path, ctx: dict):
    """web/package.json version is a final release version (no pre-release suffix) equal to the exporter's WEBSITE_VERSION."""
    try:
        pkg = json.loads(read(repo, "web/package.json")).get("version")
    except json.JSONDecodeError:
        pkg = None
    m = re.search(r'^WEBSITE_VERSION\s*=\s*"([^"]+)"', read(repo, "tools/export_web_data.py"), re.M)
    exp = m.group(1) if m else None
    final = bool(pkg) and re.fullmatch(r"\d+\.\d+\.\d+", pkg) is not None
    return final and pkg == exp, f"web/package.json version {pkg}; exporter WEBSITE_VERSION {exp}"


CHECKS = {
    "MD-1": check_md1_licence, "MD-2": check_md2_dates, "MD-3": check_md3_doi, "MD-4": check_md4_contact,
    "MD-5": check_md5_maintenance, "RA-1": check_ra1_release_assets, "RA-2": check_ra2_zenodo,
    "OPS-2": check_ops2_environment, "CI-1": check_ci1_remote_ci, "VER-1": check_ver1_version,
}


# ------------------------------------------------------------------------------------------------ gate
def has_record(b: dict) -> bool:
    r = b.get("resolution") or {}
    return b.get("status") == "resolved" and all(str(r.get(k) or "").strip() for k in RESOLUTION_FIELDS)


def evaluate(repo: Path, online: bool = False, sha: str | None = None, token: str | None = None,
             blockers_path: Path | None = None) -> dict:
    data = json.loads((repo / (blockers_path or BLOCKERS)).read_text(encoding="utf-8"))
    ctx: dict = {"online": online, "sha": sha, "token": token, "release": None}
    if online:
        try:
            ctx["release"] = gh_get(f"/repos/{OWNER_REPO}/releases/tags/v1.6.0", token)
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            ctx["release_error"] = str(e)
    out = []
    for b in data["blockers"]:
        fn = CHECKS.get(b["id"])
        check_ok, detail = (None, "no automated check; requires a maintainer resolution record") if fn is None else fn(repo, {**ctx, "blocker": b})
        record = has_record(b)
        if fn is None:
            resolved = record
        else:
            resolved = record and check_ok is True
        reason = ("resolved" if resolved else
                  "claimed resolved but the automated check does not pass" if record else
                  "automated check passes but no maintainer resolution record" if check_ok is True else "open")
        out.append({"id": b["id"], "title": b["title"], "category": b["category"], "blocks": b.get("blocks", ["production"]),
                    "json_status": b.get("status"), "has_resolution_record": record, "check": check_ok,
                    "check_detail": detail, "resolved": resolved, "state": reason})
    unresolved = [x["id"] for x in out if not x["resolved"] and "production" in x["blocks"]]
    return {"checklist_version": data.get("version"), "online": online, "sha": sha, "blockers": out,
            "unresolved": unresolved, "production_allowed": not unresolved}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["report", "production"], default="report")
    ap.add_argument("--repo", type=Path, default=REPO)
    ap.add_argument("--online", action="store_true", help="also query GitHub (Release assets, environment, CI) and doi.org")
    ap.add_argument("--sha", help="commit to be deployed (for the remote-CI check)")
    ap.add_argument("--json", type=Path, help="write the evaluation as JSON")
    a = ap.parse_args(argv)
    if a.sha and not SHA40.match(a.sha):
        print(f"release_gate: --sha must be a full 40-character commit SHA, got {a.sha!r}", file=sys.stderr)
        return 2
    res = evaluate(a.repo.resolve(), online=a.online, sha=a.sha, token=os.environ.get("GITHUB_TOKEN"))
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(res, indent=2, sort_keys=True) + "\n")
    print(f"MicroRhodoDB release-blocker checklist (mode={a.mode}, online={a.online})")
    for x in res["blockers"]:
        mark = "RESOLVED" if x["resolved"] else "BLOCKING"
        print(f"  [{mark:8}] {x['id']:6} {x['title']}\n             state: {x['state']}; check: {x['check']}; {x['check_detail']}")
    if res["production_allowed"]:
        print("release_gate: no unresolved production blockers")
        return 0
    msg = f"release_gate: {len(res['unresolved'])} unresolved production blocker(s): {', '.join(res['unresolved'])}"
    if a.mode == "production":
        print(msg + " -> PRODUCTION DEPLOYMENT BLOCKED", file=sys.stderr)
        return 3
    print(msg + " (report mode: local development and previews are not blocked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
