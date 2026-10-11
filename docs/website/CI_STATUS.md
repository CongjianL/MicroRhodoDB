# GitHub CI status of the website redesign (evidence record, PR-6a)

Queried read-only from the public GitHub REST API at the time in `pr6a/evidence/QUERIED_AT_UTC.txt`.
Raw responses: `pr6a/evidence/github_actions_runs.json` and `git_ls_remote_origin.txt`.

## Remote `web-data` workflow runs

| Run ID | Branch | Head commit | Event | Conclusion | Started (UTC) |
|---|---|---|---|---|---|
| 38104338951 | `website/pr-3-protein-entry` | `7546a7a` | pull_request | **success** | 2026-10-11T02:11:26Z |
| 38058112858 | `website/pr-2-design` | `b5416b1` | pull_request | **success** | 2026-10-10T14:03:32Z |
| 38044933968 | `website/pr-1-exporter` | `4b8391c` | pull_request | **success** | 2026-10-10T10:27:01Z |

## Per-stage status

| Stage | Commit | Pushed to GitHub | Remote CI |
|---|---|---|---|
| PR-1 exporter | `4b8391c` | yes (PR #1) | **passed** (web-data run 38044933968) |
| PR-2 design | `b5416b1` | yes (PR #2) | **passed** (web-data run 38058112858) |
| PR-3 protein entry | `7546a7a` | yes (PR #4) | **passed** (web-data run 38104338951) |
| PR-3a, PR-4, PR-4a, PR-5 | local commits | no | not run |
| PR-5a | `64f8a18` | no | **not run** |
| PR-6 | `68e301b` | no | **not run** |
| PR-6a, PR-7 | this work | no | **not run**. They will be validated remotely only after the maintainer pushes them. |

## Correction of earlier wording

- Some statements are corrected here:
  - `PR6_WEB_ACCEPTANCE_REPORT.md` said "GitHub CI has never run on this branch or on any earlier redesign branch".
  - `PR5A_AUTO_ACCEPTANCE_REPORT.md` said "CI has never run" (L-4 and section 5).
  - `PR4A_AUTO_ACCEPTANCE_REPORT.md` said that the workflow "has never executed on GitHub" (L-5).
- These statements were **wrong for the project as a whole**. The `web-data` workflow ran on GitHub and passed for PR-1, PR-2 and PR-3.
- Those statements are true only of the branches that were never pushed: PR-3a onward, including PR-5a and PR-6.
- Two kinds of earlier reports differ:
  - The PR-1, PR-2 and PR-3 validation reports said that CI had not run. This was accurate when they were written, because those runs happened after the reports were written.
  - The PR-4a, PR-5a and PR-6 reports contain the incorrect project-wide wording.
- The reports keep their original text, and an erratum note has been added to each.
- The workflow steps added after PR-3 have never executed on GitHub:
  - the PR-4 G4 tests;
  - the PR-4a, PR-5 and PR-5a tests;
  - the PR-5a golden check;
  - the PR-6 audit and its mutation self-test;
  - the PR-6a tests and triggers.
- Remote success for those steps is therefore **pending**. It must not be inferred from the PR-1 to PR-3 runs.
