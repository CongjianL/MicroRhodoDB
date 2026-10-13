# PR-7c.2 Ecology & Habitat record integration: report

Status: **PR7C2_LOCAL_ACCEPTED** (local only; nothing pushed, merged or deployed).

| | |
|---|---|
| Branch | `website/pr-7c2-habitat-ui` |
| Base | `361039ea1d87184092b38ffb584e816332994cf0` (accepted PR-7c.1a) |
| Commits | `e39a3df` (exporter, sidecar, UI, tests, mutation audit, contract); `76f5e6d` (regression fixes and display wording from the independent review; last code commit); a third commit adds only `docs/website/pr7c2/` (this report, logs, screenshots, perf, mutation and independent-verification outputs). Exact final hash: `FINAL_COMMIT.txt` in the delivery package. |
| Plan | approved PR-7c.2 plan (decisions summarised in section 1) |

**Specification.** `PR7C1_INDEPENDENT_REVIEW.md` does not exist in the repository or in the delivered packages. The
explicit requirements of the PR-7c.2 request and the approved plan are therefore the specification. The UI follows
`docs/website/pr7c1/PR7C2_HABITAT_DESIGN_RECOMMENDATIONS.md`.

**Principle.** The website displays observed environmental metadata, not inferred habitats. Every value shown is
copied verbatim from one item of the accepted PR-7c.1a audit tables. Nothing is reclassified, merged, normalised,
ranked, mapped to an ontology or resolved.

## 1. Decisions (approved plan)

- **Integrated, additive export.** `tools/export_web_data.py` calls `tools/habitat_export/build.py`, which writes
  `data/v1.6.0/habitat/`. `--no-habitat` omits it. The core schema stays 1.4.0.
- **Multi-source MRDB accessions.** The section lists every source record of the accession with its own grade and
  host status. Choosing a row navigates the whole page to `#/record/<source>?section=habitat`, so habitat, function
  and phylogeny always describe the same source record. No MRDB-level habitat is asserted.
- **HL identifiers with a missing DOI.** The PR-7c.1a behaviour (null serialised as the literal `None`) is now a
  formal rule in `habitat_field_dictionary.md` section 3 (additive note; no identifier changed). The exporter
  recomputes all 105,659 HE and 91 HL identifiers and fails closed on a mismatch.
- **Sidecar scope.** Display roles only (physical, host, collection, organism context), including reported-missing,
  invalid, uninformative and rejected items. Sample titles, descriptions, strain, package and checklist fields are
  not exported; each item links to its BioSample, INSDC or PubMed page.
- **Placement.** Protein Entry page only. No Browse/Search facet, and no change to Statistics, Methods or Downloads.
- **ENVO.** Values verbatim. Only IDs that the PR-7c.1a OLS check found are linked
  (`https://purl.obolibrary.org/obo/ENVO_xxxxxxxx`). No term labels are added. Quarantined items are never linked.
- **Release coverage.** A collapsed "About these data" panel reads `habitat/summary.json` on demand.

## 2. Habitat sidecar

Files under `data/v1.6.0/habitat/`, canonical JSON (sorted keys, no timestamps), JSON Schema 2020-12
(`web/src/data/schemas/habitat.schema.json`, habitat schema 1.0.0; TypeScript types generated into
`web/src/data/habitatTypes.ts` by `schema_to_ts.py`, `--check` clean):

| File | Count | Bytes |
|---|---|---|
| `records/<MRDB>.json` (one per MRDB accession; one entry per source record, representative first) | 5,299 files / 5,466 entries | 31,019,084 (median 6,141; max 46,735) |
| `summary.json` (release-level counts with explicit denominators) | 1 | 8,753 |
| `manifest.json` (audit provenance, pinned input hashes, evidence-ID rules, SHA-256 of every other file) | 1 | 765,808 |
| Total | 5,301 | 31,793,645 |

- **Inputs.** Only the accepted PR-7c.1a outputs in `docs/website/pr7c1/` (record availability, evidence, coverage
  summary, retrieval manifest, literature evidence), SHA-256-pinned in `tools/habitat_export/contract.json` with the
  audit id `PR-7c.1a`, version 1.1.0, commit 361039e and status `PR7C1_AUDIT_PARTIAL`. A missing or changed input
  stops the export with `BLOCKED_HABITAT_SOURCE` (exit code 5). The SQLite database and the network are not used.
- **Items.** 59,086 display items in four groups: `physical`, `host`, `collection`, `organism_context`. Each keeps
  evidence ID, evidence source, entity accession, field, role, value status, verbatim value, OLS-verified ENVO IDs,
  browser URL and source URL; literature items also keep PMID, DOI, locator, scope and access.
- **Integrity checks in the builder (fail closed).** Every HE and HL ID recomputed (105,750); every grading value
  equals the record table; grade/host/link/scope consistency; source records equal `accessions.json`; representative
  among sources; per-file budget 64 KiB; contract counts; summary cross-checked against
  `habitat_coverage_summary.tsv` (all source-record metrics present in both); schema validation of every file.
- **Counts (all equal to PR-7c.1a).** Grades DIRECT_SAMPLE 2523, VERIFIED_ISOLATE 17, ORGANISM_CONTEXT_ONLY 36,
  AMBIGUOUS 59, NOT_REPORTED 2831 (of 5,466). Usable physical habitat 2540/5466 (46.47%). Host REPORTED 671,
  AMBIGUOUS 84, NOT_REPORTED 4711; host-only 186; host without usable physical habitat 207 (21 physically
  AMBIGUOUS). Not-reported scopes 2796 / 23 / 12. No traceable sample link 18. Literature lookups failed 24.
  Multi-source MRDB accessions 129 (43 with differing grades). Quarantined values 14 items in 7 records; invalid
  all-zero placeholders 12 items in 2 records; host-tissue isolation sources 23.

## 3. Ecology & Habitat section

`web/src/features/entry/HabitatSection.tsx` (rendered after Evidence on the Protein Entry page; section id
`habitat`, deep link `?section=habitat`) and the pure view model `web/src/lib/habitat.ts`:

- Badges, each with its own label: "Physical habitat evidence:" [grade, neutral wording per grade] and "Host
  association:" [host status]; plus a "no traceable sample link" badge. For the 18 records without a traceable sample
  link the host label reads "Host not reported (no sample link)" (`hostLabel()` in `habitat.ts`; also used in the
  source table), so an unchecked host is never presented as a checked negative.
- VERIFIED_ISOLATE records state only what the audit established: "A reviewed publication contains a statement about
  where the source isolate of this record was obtained (quoted below, with its wording unchanged); no usable physical
  habitat value is available from linked sample records."
- Multi-source accessions: a table of all source records with grade and host status, the current one marked with
  `aria-current`; a note when grades differ ("no MRDB-level habitat is asserted"). Selecting a row navigates the
  whole page to that source record.
- Physical habitat card: usable values grouped by reporting record (never merged), ambiguity class explanation,
  literature isolation statements with PMID/DOI/locator, non-standard habitat fields, values not used (reported
  missing, invalid placeholder, uninformative, moved to sample material), quarantined values flagged "not an
  ontology term", rejected literature statements.
- Missingness wording follows the audit scope and link status: "Physical habitat not reported in the linked sample
  records; literature not reviewed / not accessible / not reported in the reviewed literature either", or, for the
  18 no-link records, "No traceable INSDC or sample link; sample records could not be checked; ...".
- Host association card (separate; "A host is a host association, not a physical habitat"), collection metadata
  card, organism ecological context card ("Organism-level context, not the sampling habitat of this sequence"),
  literature-reviewed disclosure, and a collapsed "About these data" panel that loads `summary.json` only on open.
- Each item has a Provenance disclosure: evidence ID, source, record (linked only if https on an allowlisted host),
  field, role, status, "Linkage route" and a separate "Mapping confidence" row. The collection card shows the linkage
  route and "Physical-habitat mapping confidence" (HIGH / MEDIUM / LITERATURE, from the audit).
- Lead text: "... No value is inferred, normalised or mapped to an ontology; the evidence grades, statuses and linkage
  labels come from the PR-7c.1a metadata audit."
- Defence in depth in the browser: items in the wrong group, with an unknown role or a malformed evidence ID are
  dropped; a file whose MRDB accession or source-record set differs from the record is rejected. Any load or check
  failure shows "Habitat metadata unavailable in this build. The rest of this record is not affected."
- Safe links only: ENVO PURLs for well-formed, verified, non-quarantined IDs; accession, PubMed and DOI links only
  from validated patterns; sidecar URLs only if https on www.ebi.ac.uk, www.ncbi.nlm.nih.gov,
  pubmed.ncbi.nlm.nih.gov, pmc.ncbi.nlm.nih.gov or eutils.ncbi.nlm.nih.gov.
- Screenshots: `docs/website/pr7c2/screenshots/` (24 PNG, 128-colour quantised, 3.8 MB; 9 representative cases at
  1440 px; 5 records at 375/768/1440 px), taken from the final UI (commit 76f5e6d).

## 4. Tests

All counts are from the final regression at 76f5e6d (`logs/regression/`).

| Suite | Result |
|---|---|
| `tests/test_web_pr7c2.py` (exporter, sidecar, contract, reconciliation with PR-7c.1a) | 34 passed |
| `tests/test_habitat_audit_pr7c1.py` (PR-7c.1a audit) | 102 passed |
| Full pytest (`tests/`) | 468 passed, 12 skipped, 0 failed |
| Vitest (18 files; includes `tests/unit/pr7c2.test.ts`) | 245 passed |
| Playwright, PR-7c.2 spec (`tests/e2e/pr7c2.spec.ts`: cases, multi-source navigation, deep link, keyboard, axe WCAG A/AA serious/critical, no page overflow at 375/768/1440 px, fail-closed loading, no habitat requests on other routes) | 37 passed |
| Playwright, full suite | 287 passed, 1 skipped |
| `npm run typecheck`, `schema_to_ts.py --check` (types.ts and habitatTypes.ts) | clean |

Reconciliation tests compare the sidecar with the PR-7c.1a tables value by value: every grade, host status, link
status and scope; every display item and its verbatim value; empty values exported as `null` (19 items); no
non-display row exported (46,664 excluded); summary metrics equal to `habitat_coverage_summary.tsv`.

## 5. Mutation audit

`tools/habitat_export/mutation_audit.py` re-introduces one weakness at a time into a temporary copy of the
repository and runs `tests/test_web_pr7c2.py` (exporter mutants E1-E20) or Vitest `tests/unit/pr7c2.test.ts` (view
model mutants U1-U16). Result: **MUTATION_AUDIT_PASS, 36/36 detected** (final run inside the regression at 76f5e6d), both baselines pass
(`docs/website/pr7c2/mutation_audit_pr7c2.json`, log in `logs/mutation_audit.log`).

- Exporter: representative flag, ENVO and bare-number quarantine, empty value replaced by text, HE field order, HL
  `None` rule, SHA-256 pin, multi-source grade difference, host routed into physical, literature DOI dropped, no-link
  missingness, representative order, per-file budget, MRDB mapping check, ENVO IDs dropped, host flags dropped,
  literature sources checked dropped, item order, exporter omitting the sidecar, `--no-habitat` ignored.
  Seven exporter mutants (E2, E3, E5, E6, E8, E9, E16) are detected because the builder's own fail-closed checks
  (recomputed IDs, contract counts, schema) stop the export; the others are detected by the independent tests.
- View model: loose evidence-ID pattern, quarantined values linked, http or non-allowlisted record URLs, wrong-MRDB
  or merged-source files accepted, missingness scope swapped or no-link wording lost, organism-context filter removed,
  wrong-group items accepted, non-usable values shown as habitat, unvalidated BioSample/DOI/ENVO links, host-only
  wording missing, no-link records labelled with a checked "Host not reported" (U16, added with `hostLabel()`).
- The first run found 5 surviving mutants (E10 DOI, E17 sources checked, E18 item order, U12 BioSample pattern, U13
  DOI pattern) plus one mutant with a syntax error (E16). Tests were strengthened (literature citation fields,
  `test_literature_sources_checked_copied`, `test_item_order_canonical`, `test_file_size_budget_enforced`, negative
  DOI/accession cases) and E16 was corrected; the full audit was then re-run (35/35), and again with U16 (36/36).
- Not mutation-tested: guards that are unreachable with the SHA-256-pinned inputs (coverage cross-check, literature
  quote/PMID check, malformed accession checks) would be equivalent mutants; React component behaviour is covered by
  the Playwright suite, not by this audit.

## 6. Performance and accessibility

Lab measurements with `web/scripts/pr6_perf_audit.py` (3 runs, loopback with DevTools throttling) on the 361039e
build and the PR-7c.2 build (`docs/website/pr7c2/perf/`). They were taken before the wording changes of 76f5e6d;
the RecordPage chunk was re-measured on the final build.

| Metric | 361039e | PR-7c.2 |
|---|---|---|
| RecordPage chunk, gzip | 13,611 B | 20,606 B (final build: 20,787 B) |
| Initial JS+CSS, gzip | 64,360 B | 64,445 B |
| Record P02945 (desktop): transfer / data | 465,381 / 364,322 B | 476,300 / 368,102 B (+1 file: `habitat/records/MRDB000001.json`) |
| Record P02945: DOM nodes | 3,336 | 4,372 |
| Record P02945 mobile: ready / LCP / CLS | 6,621 / 6,460 ms / - | 6,577 / 6,348 ms / 0.021 |
| Home and Browse | - | no habitat requests; transfer +89 to +91 B (bundle) |

- The habitat file is fetched only on the Protein Entry page; `summary.json` only when "About these data" is opened.
- Contrast audit (all 20 routes at 375/768/1440 px): 0 failures; minimum active ratio on record pages 5.53.
- Axe (WCAG A/AA, serious/critical) on the expanded habitat section for 5 records at 3 widths: 0 violations.
- At 375 px the multi-source table scrolls horizontally inside a focusable, labelled region (`role="region"`,
  `tabIndex=0`); the page itself never overflows (tested).

## 7. Regression and frozen science

Final regression: `logs/regression/SUMMARY.txt` (36 gates on HEAD 76f5e6d).

- Frozen science unchanged: SQLite SHA-256 `379a2543...dce17f`; refpkg checksums; frozen baseline files; no diff
  versus 361039e under `releases/`, `refpkg/`, `pipeline/`, `site/`; 12 production release blockers, all still open
  (release gate report mode); PR-7c.1a mutation audit 22/22; PR-7a mutation audit 25/25; PR-6 scientific audit 47/47
  and its mutation self-test; PR-5 reconciliation 58/58; drilldown golden and structure fixtures unchanged.
- PR-7c.1a outputs unchanged except the additive HL `None`-rule note in `habitat_field_dictionary.md` (6 lines added,
  0 removed). The habitat cache tarball is unchanged (`02f28a9b...6213a`).
- Core export unchanged: the `--no-habitat` export equals the 361039e exporter output byte for byte; the default
  export differs only by `habitat/` and `export_manifest.json`.
- Changed paths are inside the PR-7c.2 allowlist (24 files; `git diff --name-only 361039e..76f5e6d`).
- Site artifact: build and `verify_site_artifact.py` pass (ARTIFACT_VERIFIED, V1-V11).
- **One gate failed on the first pass and passed on re-run:** `export_matches_public` compared a fresh export with
  `web/public/data`, which had been exported from the dirty tree before 76f5e6d was committed; only commit-dependent
  fields differed (exporter commit and `git_dirty` in `manifest.json`/`export_manifest.json`, commit-pinned URLs in
  `downloads.json`). The later `site_artifact_build` gate re-exports `web/public/data` at HEAD; a re-run then gave
  `EXPORT_MATCHES_PUBLIC` (`logs/regression/export_matches_public_rerun.log`). No code or data changed between the
  two runs. The exported `export_manifest.json` hash is commit-dependent (at 76f5e6d: `ee9b6e3d...4a637f` dirty
  tree, `db432f7a...6ae01e` clean clone); every data file, including `habitat/`, is identical across these exports.

Fixes made after the first regression (commit 76f5e6d), each re-verified:

- `verify_site_artifact.py` V6 validated every JSON file against the core schema and rejected `habitat/**`. V6 now
  validates `habitat/**` against `habitat.schema.json` and everything else against the core schema as before. A
  negative check (grade tampered to `INFERRED_HABITAT`) is rejected.
- `tests/test_habitat_audit_pr7c1.py::test_no_production_habitat_keys` scanned all exported files for habitat keys
  and failed on the new, intended sidecar. It now skips only `v1.6.0/habitat/` and still checks every core file
  (gate `test_pr7c1_change_scoped` confirms nothing else in that file changed).
- CI (user-approved minimal `.github` edit): `tests/test_web_pr7c2.py` added to the pytest line of `web-data.yml`
  and `deploy-site.yml`; `tools/habitat_export/**` added to both path filters of `web-data.yml`; plus one comment line
  in the `web-data.yml` header describing the change (gate `github_diff_minimal`: 5 added, 2 removed lines). The
  existing CI-guard tests (`test_web_pr6a.py`, `test_web_pr7.py`) pass. `docs/website/pr7c1/**` was already covered
  by `docs/website/**`.

## 8. Independent verification and offline replay

**Independent re-derivation** (`docs/website/pr7c2/independent/`): a separate agent re-derived the sidecar from
the PR-7c.1a tables with its own code (`independent_rederive.py`), without using the exporter. Verdict
**INDEPENDENT_PASS, 10/10 checks, 0 discrepancies**, on the e39a3df export and again on the final export
(`independent_checks_76f5e6d.json`): 105,659 HE and 91 HL IDs recomputed (6 HL with the `None` rule); 59,086 display
items, 46,664 non-display rows excluded, 19 empty values as `null`; quarantine 14 items in 7 records; 55
organism-context items; 43 summary metrics; 59,177 URLs all https on allowlisted hosts; manifest hashes and sizes.
Its UI review led to the 76f5e6d wording fixes (separate host badge, no-link host label, verified-isolate wording,
confidence labels, "normalised" in the lead, the strict host-only definition in `summary.json`).

**Offline replay** at 76f5e6d in a clean clone (`logs/replay_76f5e6d.log`): with the SQLite database and the
PR-7c.1a cache tarball only, `python -m tools.habitat_audit.run full --offline` used 438 cache hits and 0 network
requests (11 s); all 7 PR-7c.1a tables and 4 figures are byte-identical to `docs/website/pr7c1/`. The clone's
export has a byte-identical `habitat/` and identical data files (only `git_dirty` differs); the habitat and audit
tests pass in the clone (135 passed, 1 skipped). REPLAY_PASS.

## 9. Deviations from the plan and caveats

- **Specification source.** `PR7C1_INDEPENDENT_REVIEW.md` is absent; the request and the approved plan were used.
- **Sidecar size.** 31.8 MB (5,301 files), above the plan estimate of 15-20 MB, because all display roles and all
  not-used values are exported with full provenance. Only one file (median 6.1 KB, max 46.7 KB, budget 64 KiB) is
  fetched per record view. Total site data is 60.9 MB.
- **Empty values** in the audit tables are exported as `null`, never as text (19 items).
- **`has_usable_habitat`** in the sidecar is the audit definition (grade DIRECT_SAMPLE or VERIFIED_ISOLATE, 2540).
- **URL allowlist.** Sidecar URLs must be https on 5 EBI/NCBI hosts; anything else is not linked (none occur).
- **CI.** One header comment line in `web-data.yml` beyond the three functional edits. `site-preview.yml` path
  filters do not include `tools/habitat_export/**` or `docs/website/pr7c1/**` (left unchanged, out of scope).
- **Performance** was measured before the 76f5e6d wording changes (RecordPage chunk re-measured: +181 B).
- **Findings from the independent review that this PR does not change** (they come from the accepted PR-7c.1a audit;
  the website shows them verbatim, as required):
  - A0AAJ6N6B2 is graded VERIFIED_ISOLATE on a hedged statement ("These features may reflect that Nodosilinea
    nodulosa PCC 7104 harboring P7104R is isolated from the ocean"). Candidate for curation in PR-7c.3.
  - A0A411LJN5 shows the host description "Not applicable" verbatim as host detail.
  - Host-tissue isolation sources count as physical habitat per the audit rules (23 items; e.g. A0A4Q4MIR8
    "infected leaves", host apple); the UI labels the host separately.
  - The evidence TSV requires standard CSV quote handling; checked-source entries omit url/step/note/added_by by
    design.
- Screenshots are 128-colour quantised to keep the repository small.

## 10. Acceptance decision

**PR7C2_LOCAL_ACCEPTED.** Every gate passes at 76f5e6d (one gate after re-running against a refreshed, ignored
`web/public/data`; reason documented above); mutation audit 36/36; independent re-derivation 10/10; offline replay
byte-identical; frozen science, core export and release blockers unchanged. Nothing was pushed, merged or deployed;
no Pages change; PR-7c.3 not started.
