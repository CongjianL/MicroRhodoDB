# PR-7c.1a Scientific Semantics Correction Report

- Branch: `website/pr-7c1-habitat-audit`
- Base: PR-7c.1 commit `39f5cad` (code `9ee95ab`), itself on PR-7b `932eb56`
- PR-7c.1a commits: `c8ec5de` (code, tests, fixtures), `11f0e14` (regenerated outputs, docs, validation round 3), plus the commit adding this report
- Audit id / version: `PR-7c.1a` / `1.1.0`
- Decision: **PASS** (section 11)

## 0. Specification source

The review file `PR7C1_INDEPENDENT_REVIEW.md` named in the request was not present in the repository, the PR-7c.1 package, the project files, or any session results folder. The five findings stated in the request were therefore used verbatim as the specification. No finding was added, dropped or reinterpreted beyond what is written below.

Scope guard: no frozen science (release DB, refpkg, pipeline, baseline hashes, evidence values, release blockers) was modified; nothing was pushed, merged or deployed; PR-7c.2 was not started.

## 1. Summary of corrections

| # | Finding | Change | Primary effect |
|---|---|---|---|
| 1 | Host counted as habitat | `host` moved to a separate host-association axis; grade, `db_habitat_status`, `mapping_confidence`, `has_usable_habitat` now use the four physical roles only | 186 host-only records leave usable physical habitat (171 DIRECT_SAMPLE, 15 AMBIGUOUS -> NOT_REPORTED); usable physical habitat 2648 -> 2540 (48.44% -> 46.47%) |
| 2 | `"0"` in MIxS env fields | New value_status `invalid_placeholder` for all-zero values in `env_broad_scale`, `env_local_scale`, `env_medium` only | 12 evidence items (A0ABS3TAH3, A0ABS3TE24) invalidated; both records stay DIRECT_SAMPLE on `isolation_source = soil` |
| 3 | Ambiguity not interpreted | New `ambiguity_class` (physical) and `host_ambiguity_class` (host); raw conflicting values preserved | 59 physical AMBIGUOUS split into 9 formatting / 20 nested / 19 distinct same-sample / 10 distinct across-samples / 1 literature-vs-database |
| 4 | Missingness conflated | New `not_reported_scope` on every NOT_REPORTED record | 2796 literature not reviewed / 23 literature inaccessible / 12 database and literature; the 24 literature LOOKUP_FAILED cases preserved |
| 5 | Portability, whitespace | No machine paths in code or outputs; repo-relative defaults with env overrides; SVG trailing whitespace stripped; TSV whitespace documented via `.gitattributes` | Clean clone at a different path replays byte-identically with no flags or env vars; `git diff --check` clean |

## 2. Finding 1: physical habitat vs host association

Definitions (see `habitat_field_dictionary.md` sections 1, 4, 8):

- Physical roles: `env_broad_scale`, `env_local_scale`, `env_medium`, `isolation_source`.
- Host role: `host`. It is reported on a separate axis, `host_association_status` (LOOKUP_FAILED > AMBIGUOUS > REPORTED > NOT_REPORTED), with `has_host_association`.
- `primary_grade` is now the physical-habitat grade. The PR-7c.1 grade is preserved unchanged in a new column `pr7c1_grade` (equal to the PR-7c.1 `primary_grade` for 5466/5466 records), so the original provenance and grades remain auditable.
- Conflicts that involve only the host role no longer make a record physically AMBIGUOUS (flag `host_conflict`). A literature value disagreeing with a host-only database record is not a physical conflict (`literature_conflict` requires a usable physical value).
- Raw conflict columns (`conflict_roles`, `conflict_scope`, `conflict_kind`) still span all five roles, so no observation was discarded.

Grade transitions (source records, n = 5466):

| PR-7c.1 grade | PR-7c.1a grade | n |
|---|---|---|
| DIRECT_SAMPLE | DIRECT_SAMPLE | 2460 |
| DIRECT_SAMPLE | NOT_REPORTED | 171 |
| AMBIGUOUS | DIRECT_SAMPLE | 63 |
| AMBIGUOUS | AMBIGUOUS | 59 |
| AMBIGUOUS | NOT_REPORTED | 15 |
| VERIFIED_ISOLATE | VERIFIED_ISOLATE | 17 |
| ORGANISM_CONTEXT_ONLY | ORGANISM_CONTEXT_ONLY | 36 |
| NOT_REPORTED | NOT_REPORTED | 2645 |

The 63 AMBIGUOUS -> DIRECT_SAMPLE records were ambiguous only because host values disagreed with one another or with physical values. Their physical values are consistent, so on the physical axis they are direct. Their host disagreement is retained as `host_conflict` and `host_ambiguity_class`.

Corrected grade totals (PR-7c.1 in brackets): DIRECT_SAMPLE 2523 [2631], VERIFIED_ISOLATE 17 [17], ORGANISM_CONTEXT_ONLY 36 [36], AMBIGUOUS 59 [137], NOT_REPORTED 2831 [2645], LOOKUP_FAILED 0, NOT_SEARCHED 0.

Coverage:

| Metric | PR-7c.1a | PR-7c.1 |
|---|---|---|
| Usable physical habitat, any source | 2540 / 5466 (46.47%) | 2648 (48.44%) |
| Host association reported / ambiguous / not reported | 671 / 84 / 4711 | (not separated) |
| Any host association | 755 (13.81%) | (counted as habitat) |
| Host association only (no usable physical value) | 186 (3.40%) | (counted as habitat) |
| Physical habitat and host association | 548 (10.03%) | n/a |
| Usable `env_broad_scale` / `env_local_scale` / `env_medium` | 862 / 623 / 767 | 864 / 625 / 769 |
| Usable `isolation_source` | 2326 | 2326 |
| Funnel: habitat field present / informative / direct | 4013 / 2596 / 2523 | 4155 / 2781 / 2631 |
| MRDB rollup DIRECT / VERIFIED / ORG / AMB / NR | 2472 / 16 / 30 / 55 / 2726 | 2576 / 16 / 30 / 125 / 2552 |

Host-only records by domain: Eukaryota 145, Bacteria 38, Unassigned 2, Archaea 1. Usable physical habitat by domain: Bacteria 59.93% [61.99], Archaea 49.21%, Eukaryota 36.60% [39.01], Unassigned 94.79%. Status groups: member 46.26%, candidate 48.22%, boundary 34.58%, outgroup 56.48%, rejected 53.40% [50.49], engineered 0%.

`physical_habitat_and_host_association` is defined as `has_usable_habitat = 1 AND has_host_association = 1`. The independent validator noted that a looser reading (any usable physical item, including an ORGANISM_CONTEXT_ONLY record, plus any host) gives 569. The dictionary now states the definition explicitly.

`tissue_or_culture_only` rose from 248 to 382. This happens because the material/tissue values of host-only records were previously masked by the host value; it is a reporting consequence, not a data change.

## 3. Finding 2: invalid `"0"` placeholders

- Rule: a value matching `^0+(\.0+)?$` in a MIxS environment role (`env_broad_scale`, `env_local_scale`, `env_medium`) is `invalid_placeholder`. It is neither usable nor counted as informative in the funnel. The rule deliberately does not apply to `isolation_source` or `host`.
- Affected: A0ABS3TAH3 and A0ABS3TE24, 12 evidence items in total. Both records keep usable `isolation_source = soil` and remain DIRECT_SAMPLE. The flag `invalid_placeholder_value` = 2.
- Evidence preservation: across 105,750 evidence rows (identical IDs to PR-7c.1), exactly these 12 rows changed, and only in `value_status` (usable -> invalid_placeholder). Raw values, normalised values, provenance and literature files are byte-identical.
- ENVO-like digit strings that are not pure zeros (for example A0A6N7QP32 `env_local_scale = "00000316"`) are untouched. This one is recorded as an observation only (section 10).

## 4. Finding 3: ambiguity classes

`ambiguity_class` is assigned to physically AMBIGUOUS records and `host_ambiguity_class` to records with host conflicts. No conflicting value is resolved, merged or dropped. The class describes the kind of disagreement only.

| Class | Meaning | Physical (n = 59) | Host (n = 84) |
|---|---|---|---|
| FORMATTING_ONLY | values differ only by case, punctuation, whitespace or ENVO-label vs text form | 9 | 1 |
| NESTED_WORDING | one value is contained in another (specific vs general) | 20 | 23 |
| DISTINCT_SAME_SAMPLE | different values within one sample record | 19 | 60 |
| DISTINCT_ACROSS_SAMPLES | different values in different linked samples | 10 | 0 |
| LITERATURE_VS_DATABASE | reviewed literature disagrees with a usable physical database value | 1 (A0A411LJN5) | 0 |

FORMATTING_ONLY and NESTED_WORDING are candidates for synonym reconciliation in a future PR, but they remain AMBIGUOUS here because this PR has no curated synonym evidence.

The DISTINCT_ACROSS_SAMPLES records are B2D007, B2D030, B2D032, B2D036, B2D038 (Lake Kinneret depths; B2D007 also Baltic Sea and freshwater lakes), C0K2D9 and C0K2E3 (Lake Erie vs Lake Superior), D2Y5H4 and D2Y5K5 (sea-ice layers), and F6LYH6 (Lake Kinneret vs Ganges River). Only B2D007 and F6LYH6 span different habitat types; the other 8 differ by depth, layer or neighbouring water body.

## 5. Finding 4: missingness scope

Every NOT_REPORTED record now carries `not_reported_scope`:

| Scope | Meaning | n (of 2831) |
|---|---|---|
| database_only_literature_not_reviewed | databases report nothing; literature was not in the review set | 2796 |
| database_only_literature_inaccessible | databases report nothing; literature lookup failed | 23 |
| database_and_literature | databases and reviewed literature both report nothing | 12 |

The 24 literature LOOKUP_FAILED cases are preserved unchanged, with no annotation invented. 23 of them are NOT_REPORTED (scope `inaccessible`) and 1 is DIRECT_SAMPLE on database evidence (A0A977XLG0). In PR-7c.1 the split was 22 NR + 2 DIRECT; the shift is one host-only record. Literature NOT_REPORTED: 12 NR + 1 DIRECT.

## 6. Finding 5: portability and whitespace

- Code: `tools/habitat_audit/common.py` now resolves the cache and work directories relative to the repository (`work/habitat_cache`, `work/pr7c1_work`), with optional overrides `MRDB_HABITAT_CACHE` and `MRDB_HABITAT_WORK`. `run.py --work` uses the same default. No `/workspace` string remains in `tools/habitat_audit`, and the manifest contains no absolute paths. Both are enforced by tests and a mutation.
- Clean-clone replay: the repository was cloned at commit `11f0e14` to a different absolute path. The release DB was copied in and the retrieval-cache tarball (sha256 `02f28a9b...213a`) extracted to `work/habitat_cache`. Then `python -m tools.habitat_audit.run full --offline --out <dir>` was run with no `--cache` flag and no environment variables: 438 cache hits, 0 fetched, 0 failed, 8.5 s. All 11 outputs (6 TSV, manifest JSON, 4 SVG) are byte-identical to the committed files. In the clone the PR-7c.1 test module passes 101 with 1 skipped before the gitignored web export exists, and 102/102 after `tools/export_web_data.py`.
- Determinism: two independent in-place runs are byte-identical.
- Whitespace: SVGs are written with trailing whitespace stripped per line, so they now have 0 trailing-whitespace lines. TSV cells can legitimately end in a tab when the last column is empty, or keep whitespace from source values. These are scientific content and were not altered; `*.tsv -whitespace` is declared in `docs/website/pr7c1/.gitattributes` and `tests/data/pr7c1/.gitattributes`, as are two verbatim round-1 validator logs. `git diff --check` against both `932eb56` and `39f5cad` is clean.

## 7. Independent validation (round 3)

An independent child agent re-implemented the PR-7c.1a rules from the dictionary alone. Artifacts are in `validation/round3_pr7c1a/`. Verdict: **PASS**.

- Record table: 45 columns x 5466 records. Only 3 `evidence_ids` cells differ, because production hashes a null DOI as the string `None` for literature HL IDs. This is a specification ambiguity with no effect on classification.
- Evidence `value_status`: 0 mismatches over 105,750 rows.
- Denominators: 63/63 summary rows match.
- Findings adopted: the explicit definition of `physical_habitat_and_host_association` (section 2) and the limitations in section 10.

## 8. Tests and mutation audit

- `tests/test_habitat_audit_pr7c1.py`: 102 passed (about 20 PR-7c.1a regression tests added, 4 updated). They cover role separation, host-only, host conflict, the zero-placeholder scope (env fields only; not `isolation_source`; not ENVO-like digits), ambiguity classes, literature vs host, missingness scopes, output counts and denominators, the preserved literature cases, SVG whitespace, no machine paths, and no absolute paths in the manifest.
- Fixture: 32 records (16 new criteria) in `tests/data/pr7c1/`.
- Mutation audit (`mutation_audit.json`): 22/22 mutants killed, including 9 new ones (host counted as physical habitat, host conflict as physical conflict, literature conflict against host only, zero placeholder ignored, zero placeholder applied to `isolation_source`, formatting ambiguity collapsed, ambiguity scope collapsed, missingness scope collapsed, hardcoded machine cache path).
- Full repository suite: 434 passed, 12 skipped (PR-7c.1 baseline 402 passed, 12 skipped; +32 new tests).

## 9. Frozen-science and engineering regression

All 22 steps exited 0 (log in the package `regression/`):

| Check | Result |
|---|---|
| Frozen baseline hashes (`frozen_sha256_fab9182.txt`) | OK |
| refpkg `MR_RT_003` SHA256SUMS | OK |
| No diff in `releases`, `refpkg`, `pipeline`, `site` vs `932eb56`; also `docs/website/baseline` vs `39f5cad` | OK |
| Release DB sha256 `379a2543...e17f` | OK |
| Retrieval cache tarball sha256 `02f28a9b...213a` | OK |
| Release blockers unchanged (12, all open) | OK |
| `web`, `.github`, `tools/export_web_data.py` untouched | OK |
| Evidence preservation (only the 12 placeholder cells changed) | OK |
| Web export builds; contains no habitat keys | OK |
| Schema, structure fixtures, PR-5a golden, PR-5 reconciliation, PR-6 scientific audit and audit mutations | OK |
| `git diff --check 932eb56` | clean |
| No `/workspace` in `tools/habitat_audit` | OK |
| Habitat mutation audit 22/22; pytest all; pytest PR-7c.1 | OK |

## 10. Limitations

- No host or habitat synonym resolution is performed. FORMATTING_ONLY and NESTED_WORDING records stay AMBIGUOUS until curated synonym evidence exists.
- 4 DISTINCT_SAME_SAMPLE records differ only by typos, and 8 of 10 DISTINCT_ACROSS_SAMPLES records differ by depth, layer or neighbouring water body. The classes describe lexical and sampling structure, not ecological distance.
- `host_tissue_isolation_source_only` (23 records) is sensitive to the material-term list. These records have physical `isolation_source` values naming host tissue and are kept as physical evidence, as in PR-7c.1.
- A0A6N7QP32 `env_local_scale = "00000316"` looks like a truncated ENVO id but is not a zero placeholder. It is left usable and flagged here for curation only.
- The placeholder rule covers all-zero values only. Other non-informative tokens are handled by the existing `reported_missing` vocabulary.
- The 2796 `literature_not_reviewed` records are NOT_REPORTED in the databases only; habitat may exist in unreviewed literature.

## 11. Acceptance decision

Every scientific and engineering check passed:

- the five findings are implemented with tests and killed mutants;
- outputs were regenerated from the preserved cache and are byte-identical across runs and in a clean clone at a different path;
- independent validation round 3 passed;
- frozen DB, refpkg, original evidence values and release blockers are unchanged;
- the full test suite and whitespace checks are clean.

**PR-7c.1a is accepted: PASS.** Nothing was pushed, merged or deployed, and PR-7c.2 was not started.
