# PR-7 release blockers (production only)

Machine-readable checklist: `release_blockers.json`. Gate: `web/scripts/release_gate.py`.

```bash
python web/scripts/release_gate.py --mode report                         # always exit 0; prints every blocker
python web/scripts/release_gate.py --mode report --online --sha <sha>    # adds GitHub Release / environment / CI checks (read-only API)
python web/scripts/release_gate.py --mode production --online --sha <sha> --json gate.json   # exit 3 while any blocker is unresolved
```

Rules:

- Blockers stop **production deployment of website 2.0 only**. Local development, tests, `web-data`,
  `site-preview` and the legacy rollback are never blocked.
- A blocker is resolved only when BOTH (a) the maintainer sets `status: resolved` with a `resolution` record
  (`decided_by`, `decided_at`, `reference`) and (b) its automated check passes. A check that cannot be
  evaluated (offline, API error) counts as not passing. Manual-only blockers (OPS-1, ACC-1) need the record.
- The tooling never edits the checklist, never waives a blocker and never decides licence or metadata
  questions. No DOI, e-mail, hosting term, funding or successor is invented anywhere in the repository.

## Status at PR-7 (all open)

Online evidence: `pr7/evidence/release_gate_online.{txt,json}` (queried at `pr7/evidence/QUERIED_AT_UTC.txt`).

| ID | Blocker | Current evidence | Required maintainer decision | Automated check |
|---|---|---|---|---|
| MD-1 | licence statements inconsistent | LICENSE: data CC BY 4.0 and code "released under the same terms"; README: "Data: CC BY 4.0. Code: MIT."; web/package.json MIT; CITATION.cff / .zenodo.json CC-BY-4.0 | choose the code licence (and coverage of `web/`) and make LICENSE, README, package.json agree | data and code licence statements each agree across all files (README parsed; a missing statement fails) |
| MD-2 | release date conflict | CITATION.cff 2026-10-09; .zenodo.json, CHANGELOG, release notes 2026-10-10; GitHub Release published 2026-10-10 | confirm the date and correct the disagreeing file | all dates equal (online: includes the Release) |
| MD-3 | no DOI | CITATION.cff has no `doi`; Citation page shows "not supplied (pending confirmation by the maintainer)" | add a real DOI, or approve an alternative citation policy (`resolution.alternative_citation_policy`) | DOI present or policy recorded |
| MD-4 | no public contact | MAINTENANCE.md contact placeholder | supply the contact or state that GitHub issues are the only channel | no placeholder on the contact line |
| MD-5 | maintenance undecided | 7 placeholder lines in MAINTENANCE.md (cadence, hosting term, DOI, funding, successor) | fill each with a truthful statement | no `<<PLACEHOLDER` left |
| RA-1 | Release assets differ from BINARIES.md | Release v1.6.0 has only `microrhododb_v1.6.0.sqlite`; missing: `MicroRhodoDB_v1.6.0.tar.gz` (+ `.sha256`), v1.5.0, v1.5.0_env_pilot, v1.4.0, v1.3.0, v1.0 databases | upload the five databases from verified local copies (their SHA-256 match BINARIES.md) and/or correct BINARIES.md; the tar.gz has no recorded checksum and must not be re-created under the original name without documentation | every BINARIES.md asset present on the Release with matching size (online) |
| RA-2 | Zenodo deposit unverified | BINARIES.md / MAINTENANCE.md claim a deposit; no DOI | confirm and record the DOI, or remove the claim | DOI recorded |
| OPS-1 | Pages source | legacy branch deployment (main / root) | switch to GitHub Actions at deployment time | manual record |
| OPS-2 | environment protection | `github-pages`: branch policy only, policies `None`, `main`, `website/pr-1-exporter`, `website/pr-3-protein-entry`; no reviewers; admin bypass on | main-only branches, required reviewer, prevent self-review | online: reviewers present, only `main` allowed |
| CI-1 | no remote CI for the code to deploy | PR-1..PR-3 passed on GitHub; PR-3a..PR-7 never pushed (`CI_STATUS.md`) | push, open PR, obtain a successful `web-data` run on the deploy commit | online: successful web-data run for `--sha` |
| VER-1 | pre-release version label | `2.0.0-pr7` in web/package.json and the exporter | choose the release label (e.g. 2.0.0) and set both | plain `X.Y.Z`, both equal |
| ACC-1 | final authorisation | none given | review the preview artifact and record the authorisation | manual record |

## Release-asset audit detail (RA-1)

| BINARIES.md asset | On Release v1.6.0 | Local verified copy |
|---|---|---|
| `microrhododb_v1.6.0.sqlite` | yes, 33,464,320 B, SHA-256 `379a2543...ce17f` | yes |
| `microrhododb_v1.5.0.sqlite` | no | yes, SHA-256 `d715baf8...` matches BINARIES.md |
| `microrhododb_v1.5.0_env_pilot.sqlite` | no | yes, `2fd572a8...` matches |
| `microrhododb_v1.4.0.sqlite` | no | yes, `21342d94...` matches |
| `microrhododb_v1.3.0.sqlite` | no | yes, `09ce3920...` matches |
| `microrhododb_v1.0.sqlite` | no | yes, `f15033ca...` matches |
| `MicroRhodoDB_v1.6.0.tar.gz`, `.sha256` | no | **no copy and no recorded checksum anywhere** |

Website impact: the Downloads page links only to the v1.6.0 database asset (present) and to git files;
it does not link the missing assets. The gap is a publication-integrity issue for `BINARIES.md`.

## Recording a resolution (example; values must come from the maintainer)

```json
{"id": "MD-2", "status": "resolved",
 "resolution": {"decided_by": "<github login>", "decided_at": "<YYYY-MM-DD>", "reference": "<issue/PR/commit URL>", "notes": "<optional>"}}
```
