#!/usr/bin/env python3
"""PR-7 release-blocker gate for the MicroRhodoDB website (production deployment only).

The checklist lives in docs/website/release_blockers.json. A blocker counts as resolved only when BOTH
  (a) the JSON entry has status "resolved" with a maintainer resolution record (decided_by, decided_at, reference), and
  (b) its automated check, if it has one, passes against the repository (and, with --online, GitHub/doi.org).
A JSON entry flipped to "resolved" while its check still fails stays blocked, and a passing check without a
maintainer record also stays blocked, so a blocker cannot be waived silently in either direction.

Fail-closed rules (PR-7a):
  * The mandatory blockers (MANDATORY_BLOCKERS) always block production: deleting, duplicating or re-scoping one
    ("blocks": []) in the JSON blocks production instead of removing the blocker.
  * A resolution record is valid only with status exactly "resolved", a GitHub-login-shaped decided_by, a real
    calendar date not in the future, and an https reference that is not a placeholder or reserved example host.
  * A check passes only when it returns exactly True. A check that cannot be evaluated (offline, API error,
    unexpected exception, malformed API response) returns None and never passes.
  * Production mode requires --online and a full --sha; without them it exits 2 and nothing is evaluated as passing.
  * The JSON can never switch a check off: checks are bound to blocker IDs in code (CHECKS).

Modes:
  --mode report       print the checklist and exit 0 (local development, previews, CI validation)
  --mode production   exit 3 if any blocker is unresolved or the checklist is invalid; exit 2 without --online/--sha
                      (used only by the manual production deploy workflow)

The gate never edits metadata and never decides anything; it only reports.
Usage:
  python web/scripts/release_gate.py --mode report
  python web/scripts/release_gate.py --mode production --online --sha <commit> [--json out.json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import http.client
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BLOCKERS = Path("docs/website/release_blockers.json")
GH_API = "https://api.github.com"
OWNER_REPO = "CongjianL/MicroRhodoDB"
PLACEHOLDER = re.compile(r"<<\s*PLACEHOLDER")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
RESOLUTION_FIELDS = ("decided_by", "decided_at", "reference")
MANDATORY_BLOCKERS = ("MD-1", "MD-2", "MD-3", "MD-4", "MD-5", "RA-1", "RA-2", "OPS-1", "OPS-2", "CI-1", "VER-1", "ACC-1")
VALID_STATUS = ("open", "resolved")
GH_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
RESERVED_HOSTS = re.compile(r"(^|\.)(example\.(com|org|net)|[^.]+\.(invalid|example|test|localhost))$|^(example|localhost)$", re.I)
# Errors that make an online check undecidable (-> None, never passing). Anything else is caught in evaluate().
API_ERRORS = (urllib.error.URLError, OSError, http.client.HTTPException, ValueError, KeyError, TypeError, AttributeError)
WEB_DATA_WORKFLOW = ".github/workflows/web-data.yml"


# --------------------------------------------------------------------------------------------- helpers
def read(repo: Path, rel: str) -> str:
    p = repo / rel
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def cff_field(text: str, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", text, re.M)
    return m.group(1).strip().strip('"').strip("'") if m else None


def dataset_release(repo: Path) -> str:
    """The dataset release being deployed: the `version` field of the repository's CITATION.cff."""
    return cff_field(read(repo, "CITATION.cff"), "version") or "unknown"


def _open_json(req: urllib.request.Request):
    """The only network primitive of the gate (read-only GET); tests replace it with a synthetic API."""
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def gh_get(path: str, token: str | None):
    req = urllib.request.Request(GH_API + path, headers={"Accept": "application/vnd.github+json",
                                                         "X-GitHub-Api-Version": "2022-11-28",
                                                         "User-Agent": "mrdb-release-gate"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = _open_json(req)
    if not isinstance(data, dict):
        raise ValueError(f"unexpected GitHub API response type {type(data).__name__} for {path}")
    return data


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
    m = re.search(r"licensed under the (.+?)\(", lic.replace("\n", " "), re.I)
    data["LICENSE"] = norm_licence(m.group(1)) if m else None
    if re.search(r"Source code .*? is released under the same\s+terms", lic, re.S | re.I):
        code["LICENSE"] = data["LICENSE"]
    else:
        m = re.search(r"Source code[^.]*?released under (?:the )?([A-Za-z0-9 .-]+?)(?:\s+licen[cs]e|\.)", lic, re.S | re.I)
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
    """One release date for the dataset release (CITATION.cff version) across CITATION.cff, .zenodo.json, CHANGELOG.md,
    the release notes and (online) the GitHub Release."""
    rel = dataset_release(repo)
    dates = {"CITATION.cff": cff_field(read(repo, "CITATION.cff"), "date-released")}
    try:
        dates[".zenodo.json"] = json.loads(read(repo, ".zenodo.json") or "{}").get("publication_date")
    except json.JSONDecodeError:
        dates[".zenodo.json"] = None
    m = re.search(rf"^## \[{re.escape(rel)}\]\s*-\s*(\d{{4}}-\d{{2}}-\d{{2}})", read(repo, "CHANGELOG.md"), re.M)
    dates["CHANGELOG.md"] = m.group(1) if m else None
    m = re.search(r"\*\*Release date:\*\*\s*(\d{4}-\d{2}-\d{2})", read(repo, f"releases/v{rel}/RELEASE_NOTES_v{rel}.md"))
    dates[f"RELEASE_NOTES_v{rel}.md"] = m.group(1) if m else None
    if ctx.get("online") and ctx.get("release") is None:
        return None, f"release dates {dates}; GitHub Release not available online: {ctx.get('release_error', 'unknown error')}"
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
    res = blocker.get("resolution") if isinstance(blocker.get("resolution"), dict) else {}
    alt = res.get("alternative_citation_policy")
    alt = alt.strip() if isinstance(alt, str) and alt.strip() and not PLACEHOLDER.search(alt) else None
    if doi:
        if ctx.get("online"):
            try:
                req = urllib.request.Request(f"https://doi.org/api/handles/{urllib.parse.quote(doi, safe='/')}",
                                             headers={"User-Agent": "mrdb-release-gate"})
                code = _open_json(req).get("responseCode")
                return code == 1, f"CITATION.cff doi {doi}; doi.org handle responseCode {code}"
            except API_ERRORS as e:
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
    """Every asset BINARIES.md lists is attached to the GitHub Release of the dataset release, with the stated size."""
    dbs, archives = binaries_assets(repo)
    expected = {d["name"]: d["size"] for d in dbs}
    for a in archives:
        expected[a] = None
        expected[a + ".sha256"] = None
    rel = ctx.get("release")
    if rel is None:
        if ctx.get("online"):
            return None, f"BINARIES.md lists {len(expected)} Release assets; GitHub Release not available: {ctx.get('release_error', 'unknown error')}"
        return None, f"BINARIES.md lists {len(expected)} Release assets; not checked offline (run with --online)"
    if not expected:
        return False, "BINARIES.md lists no Release assets (cannot confirm the Release contents)"
    have = {a["name"]: a["size"] for a in rel.get("assets", [])}
    missing = sorted(n for n in expected if n not in have)
    wrong = sorted(n for n, s in expected.items() if n in have and s is not None and have[n] != s)
    ok = not missing and not wrong
    return ok, f"Release v{dataset_release(repo)} has {sorted(have)}; missing {missing}; size mismatch {wrong}"


def check_ra2_zenodo(repo: Path, ctx: dict):
    """A Zenodo deposit claimed by BINARIES.md / MAINTENANCE.md is verifiable (DOI in CITATION.cff that resolves)."""
    claims = "Zenodo" in read(repo, "BINARIES.md") or "Zenodo" in read(repo, "MAINTENANCE.md")
    if not claims:
        return True, "no Zenodo deposit is claimed"
    ok, detail = check_md3_doi(repo, {**ctx, "blocker": {}})  # an alternative citation policy does not verify a deposit
    return ok, "Zenodo deposit claimed in BINARIES.md/MAINTENANCE.md; " + detail


def check_ops1_pages_source(repo: Path, ctx: dict):
    """GitHub Pages is configured to deploy from GitHub Actions (build_type 'workflow'), which actions/deploy-pages needs."""
    if not ctx.get("online"):
        return None, "Pages source not checked offline (run with --online)"
    try:
        pages = gh_get(f"/repos/{OWNER_REPO}/pages", ctx.get("token"))
    except API_ERRORS as e:
        return None, f"GitHub Pages API failed: {e}"
    bt = pages.get("build_type")
    src = pages.get("source")
    return bt == "workflow", f"Pages build_type {bt!r} (required 'workflow'); source {src}"


def check_ops2_environment(repo: Path, ctx: dict):
    """github-pages environment: a required-reviewers rule with at least one reviewer, and deployments only from the
    branch main (custom branch policies, exactly one policy of type branch named main). Admin bypass and
    prevent-self-review are reported (maintainer decision) but not required."""
    if not ctx.get("online"):
        return None, "environment protection not checked offline (run with --online)"
    tok = ctx.get("token")
    try:
        env = gh_get(f"/repos/{OWNER_REPO}/environments/github-pages", tok)
        pol = gh_get(f"/repos/{OWNER_REPO}/environments/github-pages/deployment-branch-policies", tok)
        rules = env.get("protection_rules") or []
        types = [r.get("type") for r in rules]
        rev_rules = [r for r in rules if r.get("type") == "required_reviewers"]
        n_reviewers = sum(len(r.get("reviewers") or []) for r in rev_rules)
        dbp = env.get("deployment_branch_policy") or {}
        policies = pol.get("branch_policies") or []
        names = sorted(str(p.get("name")) for p in policies)
        kinds = sorted({str(p.get("type")) for p in policies})  # a missing type is not assumed to be "branch"
        total = pol.get("total_count", len(policies))  # an incomplete (paginated) policy list never passes
    except API_ERRORS as e:
        return None, f"GitHub environment API failed or returned an unexpected shape: {e}"
    reviewers = bool(rev_rules) and n_reviewers >= 1
    main_only = (dbp.get("custom_branch_policies") is True and dbp.get("protected_branches") is False
                 and names == ["main"] and kinds == ["branch"] and total == len(policies))
    self_review = next((r.get("prevent_self_review") for r in rev_rules), None)
    return reviewers and main_only, (f"protection rules {types}; required reviewers {n_reviewers}; deployment_branch_policy {dbp}; "
                                     f"allowed deployment branches {names} (types {kinds}); "
                                     f"can_admins_bypass {env.get('can_admins_bypass')}; prevent_self_review {self_review}")


def check_ci1_remote_ci(repo: Path, ctx: dict):
    """The web-data workflow concluded 'success' on GitHub for the commit being deployed."""
    sha = ctx.get("sha")
    if not ctx.get("online") or not sha:
        return None, "remote CI not checked (needs --online --sha <commit>)"
    try:
        runs = gh_get(f"/repos/{OWNER_REPO}/actions/runs?head_sha={sha}&per_page=100", ctx.get("token")).get("workflow_runs") or []
        # identify the workflow by its file path (a workflow name can be reused by any other file)
        ok_runs = [r for r in runs if r.get("path") == WEB_DATA_WORKFLOW and r.get("head_sha") == sha
                   and r.get("status") == "completed" and r.get("conclusion") == "success"]
    except API_ERRORS as e:
        return None, f"GitHub Actions API failed or returned an unexpected shape: {e}"
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
    "OPS-1": check_ops1_pages_source, "OPS-2": check_ops2_environment, "CI-1": check_ci1_remote_ci, "VER-1": check_ver1_version,
}


# ------------------------------------------------------------------------------------------------ gate
def resolution_problems(b: dict, today: dt.date | None = None) -> list[str]:
    """Why a blocker's resolution record is not a valid maintainer record ([] = valid). Open blockers -> ['status ...']."""
    if b.get("status") != "resolved":
        return [f"status is {b.get('status')!r}, not 'resolved'"]
    r = b.get("resolution")
    if not isinstance(r, dict):
        return ["resolution record missing"]
    probs = []
    for k in RESOLUTION_FIELDS:
        v = r.get(k)
        if not isinstance(v, str) or not v.strip():
            probs.append(f"{k} missing")
        elif PLACEHOLDER.search(v) or "<" in v or ">" in v:
            probs.append(f"{k} is a placeholder")
    if probs:
        return probs
    if not GH_LOGIN.match(r["decided_by"].strip()):
        probs.append("decided_by is not a GitHub login")
    try:
        d = dt.date.fromisoformat(r["decided_at"].strip())
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["decided_at"].strip()):
            raise ValueError
        if d > (today or dt.datetime.now(dt.timezone.utc).date()):
            probs.append("decided_at is in the future")
    except ValueError:
        probs.append("decided_at is not a YYYY-MM-DD date")
    u = urllib.parse.urlsplit(r["reference"].strip())
    if u.scheme != "https" or not u.hostname or " " in r["reference"].strip():
        probs.append("reference is not an https URL")
    elif RESERVED_HOSTS.search(u.hostname):
        probs.append(f"reference host {u.hostname} is a reserved example host")
    return probs


def checklist_problems(data) -> list[str]:
    """Structural problems of the checklist that block production (they never make a blocker disappear)."""
    if not isinstance(data, dict) or not isinstance(data.get("blockers"), list):
        return ["checklist has no 'blockers' list"]
    probs, seen = [], {}
    for b in data["blockers"]:
        if not isinstance(b, dict) or not isinstance(b.get("id"), str):
            probs.append(f"malformed blocker entry {b!r}"[:200])
            continue
        seen[b["id"]] = seen.get(b["id"], 0) + 1
        if b.get("status") not in VALID_STATUS:
            probs.append(f"{b['id']}: status {b.get('status')!r} is not one of {list(VALID_STATUS)}")
        if b["id"] in MANDATORY_BLOCKERS and "production" not in (b.get("blocks") or []):
            probs.append(f"{b['id']}: mandatory blocker re-scoped (blocks={b.get('blocks')!r}); it still blocks production")
    for i, n in seen.items():
        if n > 1:
            probs.append(f"{i}: listed {n} times")
    for i in MANDATORY_BLOCKERS:
        if i not in seen:
            probs.append(f"{i}: mandatory blocker missing from the checklist")
    return probs


def evaluate(repo: Path, online: bool = False, sha: str | None = None, token: str | None = None,
             blockers_path: Path | None = None) -> dict:
    try:
        data = json.loads((repo / (blockers_path or BLOCKERS)).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        data = {"_error": f"checklist unreadable: {e}"}
    if not isinstance(data, dict):
        data = {"_error": f"checklist is a {type(data).__name__}, not an object"}
    problems = checklist_problems(data)
    if "_error" in data:
        problems = [data["_error"]]
    ctx: dict = {"online": online, "sha": sha, "token": token, "release": None}
    if online:
        try:
            ctx["release"] = gh_get(f"/repos/{OWNER_REPO}/releases/tags/v{dataset_release(repo)}", token)
        except API_ERRORS as e:
            ctx["release_error"] = str(e)
    out = []
    raw = data.get("blockers") if isinstance(data.get("blockers"), list) else []
    entries = [b for b in raw if isinstance(b, dict) and isinstance(b.get("id"), str)]
    dup = {b["id"] for b in entries if sum(x["id"] == b["id"] for x in entries) > 1}
    for b in entries:
        fn = CHECKS.get(b["id"])
        if fn is None:
            check_ok, detail = None, "no automated check; requires a maintainer resolution record"
        else:
            try:
                check_ok, detail = fn(repo, {**ctx, "blocker": b})
            except Exception as e:  # noqa: BLE001 - an unexpected failure must never count as passing
                check_ok, detail = None, f"check raised {type(e).__name__}: {e}"
        rprobs = resolution_problems(b)
        record = not rprobs
        mandatory = b["id"] in MANDATORY_BLOCKERS
        if fn is None:
            resolved = record
        else:
            resolved = record and check_ok is True
        if b["id"] in dup or b.get("status") not in VALID_STATUS:
            resolved = False
        blocks = list(b.get("blocks") or [])
        if mandatory and "production" not in blocks:
            blocks.append("production")
        reason = ("resolved" if resolved else
                  "duplicate or invalid checklist entry" if (b["id"] in dup or b.get("status") not in VALID_STATUS) else
                  "claimed resolved but the automated check does not pass" if record else
                  ("invalid resolution record: " + "; ".join(rprobs)) if b.get("status") == "resolved" else
                  "automated check passes but no maintainer resolution record" if check_ok is True else "open")
        out.append({"id": b["id"], "title": b.get("title", ""), "category": b.get("category", ""), "blocks": blocks,
                    "mandatory": mandatory, "json_status": b.get("status"), "has_resolution_record": record,
                    "resolution_problems": rprobs, "check": check_ok, "check_detail": detail, "resolved": resolved,
                    "state": reason})
    present = {x["id"] for x in out}
    for i in MANDATORY_BLOCKERS:
        if i not in present:
            out.append({"id": i, "title": "mandatory blocker missing from the checklist", "category": "checklist",
                        "blocks": ["production"], "mandatory": True, "json_status": None, "has_resolution_record": False,
                        "resolution_problems": ["missing"], "check": None, "check_detail": "not evaluated",
                        "resolved": False, "state": "missing from the checklist"})
    unresolved = sorted({x["id"] for x in out if not x["resolved"] and "production" in x["blocks"]})
    return {"checklist_version": data.get("version"), "online": online, "sha": sha, "blockers": out,
            "checklist_problems": problems, "unresolved": unresolved,
            "production_allowed": not unresolved and not problems}


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
    if a.mode == "production" and not (a.online and a.sha):
        print("release_gate: production mode requires --online and --sha <40-hex commit> -> PRODUCTION DEPLOYMENT BLOCKED",
              file=sys.stderr)
        return 2
    res = evaluate(a.repo.resolve(), online=a.online, sha=a.sha, token=os.environ.get("GITHUB_TOKEN"))
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        a.json.write_text(json.dumps(res, indent=2, sort_keys=True) + "\n")
    print(f"MicroRhodoDB release-blocker checklist (mode={a.mode}, online={a.online})")
    for x in res["blockers"]:
        mark = "RESOLVED" if x["resolved"] else "BLOCKING"
        print(f"  [{mark:8}] {x['id']:6} {x['title']}\n             state: {x['state']}; check: {x['check']}; {x['check_detail']}")
    for pr in res["checklist_problems"]:
        print(f"  [INVALID ] checklist: {pr}")
    if res["production_allowed"]:
        print("release_gate: no unresolved production blockers")
        return 0
    msg = f"release_gate: {len(res['unresolved'])} unresolved production blocker(s): {', '.join(res['unresolved'])}"
    if res["checklist_problems"]:
        msg += f"; {len(res['checklist_problems'])} checklist problem(s)"
    if a.mode == "production":
        print(msg + " -> PRODUCTION DEPLOYMENT BLOCKED", file=sys.stderr)
        return 3
    print(msg + " (report mode: local development and previews are not blocked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
