# PR-7c.1 independent validation

Two independent checks, both run by separate agents that did not read the production code
(`tools/habitat_audit/`) or use the production HTTP cache.

| Check | Result |
|---|---|
| Re-implementation from the dictionary, round 1 | MISMATCH: 4 primary grades, 1 mapping_confidence (spec gaps D1-D4, code deviation D5) |
| Re-implementation from the updated dictionary, round 2 | **EXACT_MATCH**: 39 columns x 5,466 records |
| Live spot-check, 100 records, seed 20261012 | **100/100** grades and usable values agree; 0 disagreements |

Artifacts: `validation/round1_reimpl/`, `validation/round2_reimpl/`, `validation/spotcheck/`,
`validation_spotcheck_sample.tsv` (reproduced exactly by `tools/habitat_audit/spotcheck_sample.py`).

## 1. Re-implementation, round 1

Input: the dictionary as it stood (`round1_reimpl/habitat_field_dictionary_round1.md`), the parsed
entities, the frozen records and the literature evidence. Spec-literal result: primary_grade 5,462/5,466.

| ID | Finding | Records | Resolution |
|---|---|---:|---|
| D1 | "Strain collection" treated as culture by production, not listed in the dictionary | 4 (e.g. A0AAW0FFT2) | dictionary s5.4 now enumerates every culture alternative verbatim |
| D2 | tissue list truncated with "..." in the dictionary; production includes "fruiting body/bodies" | 3 (e.g. A0A232LUP6) | dictionary s5.5 now lists the closed tissue set |
| D3 | "viral plaque" in production; dictionary said "plaque" | 1 (M1HVR3) | s5.4 `(viral )?plaques?` |
| D4 | `habitat_nonstandard` cell format undocumented | 40 | s8 `<field_original>: <value_original>` |
| D5 | A0A411LJN5 mapping_confidence HIGH; spec says LITERATURE for a literature-only conflict | 1 | **code fixed** (`classify.py`), regression test added |

Implicit conventions also documented: missing-value tokens are literal (12 values of `0` stay usable);
empty source-feature columns produce no item; `free_text_context_only` applies only when there is no usable
habitat item. With the five conventions applied, round 1's diagnostic run already matched all 39 columns.

After the D5 fix, two offline full runs were byte-identical, and exactly one record table cell changed
(A0A411LJN5 mapping_confidence HIGH -> LITERATURE, plus the corresponding coverage-summary rows and manifest
hashes). The fixture was rebuilt and the test suite (70 tests) and mutation audit (13/13) re-run.

## 2. Re-implementation, round 2

The validator updated its re-implementation strictly from the updated dictionary (no sensitivity mode, no
production code). Result: **EXACT_MATCH** on all 39 compared record-table columns for all 5,466 records
(`round2_reimpl/compare2.txt`).

Evidence-table cross-check (database rows; literature rows were not re-implemented): after matching rows on
content (record, source, entity, link, role, value), 0 rows are only in production and 3 only in the
re-implementation; value_normalized, envo_ids and mapping_confidence agree 100%; value_status differs on 159
rows. All differences trace to three evidence-table conventions that the dictionary did not yet state. None
changes a record-table value:

- **E1** `field_original` spelling (needed to reproduce `evidence_id`): NCBI `<name> (harmonized: <h>)`,
  literal `sample_title`/`sample_description`/`package`, `organism` for the source-feature scientific name.
- **E2** sample title/description come only from the XML title/description elements, not from attributes
  tagged `title`/`description` (the 3 extra rows: A0A2T1DCP3 / SAMN08617406 x2, A0ABM9RL04 / SAMEA1572090).
- **E3** `context` roles (strain, isolate, host_detail, investigation_type, title/description) keep `context`
  for missing-value tokens; the dictionary had said all reported roles become `reported_missing` (159 rows).

Resolution: production behaviour was kept (none of these roles is graded) and the dictionary was updated
(s3 and s4) to describe it. A third re-implementation round was not run; the record-table match is unaffected
by these documentation-only additions.

A further residual ambiguity, raised by the spot-check, concerns literature scope (s9: "paper about that
strain" vs "quote names the strain"); it is now described explicitly in s9 with the affected records
(H2BW50, A0A411LJN5 accepted through the clause; Q5V0R5/Q5V4H7 scoped organism).

## 3. Live spot-check (100 records)

Sample: fixed seed 20261012; one record per linkage route first, then grade quotas DIRECT 40, NOT_REPORTED 35,
AMBIGUOUS 15, VERIFIED_ISOLATE 5, ORGANISM_CONTEXT_ONLY 5. The reviewer re-queried UniProt, UniParc, ENA
(portal, flat file, sample XML) and NCBI BioSample live, re-implemented sections 1, 4, 5 and 6, and
re-fetched every literature quote.

- 100/100 chains completed; 76 distinct BioSamples were found at both ENA and NCBI with identical habitat-role
  values.
- Grades 100/100, usable values 100/100; literature 10/10 records, 11/11 quotes verified verbatim.
- Observations (not disagreements): AMBIGUOUS is dominated by host scientific vs common name pairs, three of
  them created by the ENA portal coding row's host rewriting; place names in habitat roles are usable by
  design; the tissue rule applies to isolation_source only; A0AAV9PSJ0 (inactive) was correctly linked through a
  same-species UniParc EMBL protein.

## 4. Scope of what was validated

- The re-implementation consumed the same parsed entities as production, so it validates classification and
  summarisation, not parsing. Parsing and linkage are validated by the live spot-check and the hand-traced
  pilot.
- Branches with no real-data occurrences (request failures, unresolvable samples, assembly fallback, ENVO
  lookup failures, `host_is_self`) are covered only by synthetic tests and failure injection in
  `tests/test_habitat_audit_pr7c1.py` and by the mutation audit.
