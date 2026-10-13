# PR-7c.2 habitat display: design recommendations (from the PR-7c.1 audit)

These are recommendations only. PR-7c.2 is not implemented, and nothing here has been applied to the
production JSON or UI. Numbers are from `PR7C1_HABITAT_AVAILABILITY_REPORT.md` as corrected by PR-7c.1a
(physical habitat separated from host association; see `PR7C1A_SCIENTIFIC_CORRECTION_REPORT.md`).

## 1. What the data can support

- Slightly under half of the records (2,540 / 5,466; 46.47%) have a usable, traceable physical habitat value.
  The rest is overwhelmingly NOT_REPORTED (2,831), not failed; 186 of those report only a host. A habitat facet would therefore be empty for half the
  database; the UI must present "not reported by the linked sample record" as a first-class state, never as
  blank or "unknown habitat".
- Coverage is lowest for the best-studied proteins (Swiss-Prot 7.84%, characterized 32.71%, E1/E2 ~27%).
  Literature evidence is essential for these, and it is currently available for only the 110-record subset.
- Free-text `isolation_source` dominates (2,326 records); MIxS triad values are sparser (11-16% each) and
  explicit ENVO IDs are rare (112 distinct IDs). A controlled-vocabulary facet would need a separate,
  reviewed mapping step; it cannot be built from explicit IDs alone.

## 2. Recommended display model

0. **Physical habitat and host are separate facts.** Display `host` (host association; 755 records) in its
   own block, never as the habitat and never inside a habitat facet. A record with only a host
   (`host_association_only`, 186) is "physical habitat not reported; host reported".

1. **Show the evidence grade, not just the value.** Badge per record: Direct sample / Verified isolate
   (literature) / Organism context only / Conflicting records / Not reported. Organism-context literature
   must be visually distinct and never used as a filterable habitat.
2. **Show values verbatim with provenance.** Each value links to its source record (BioSample, INSDC entry,
   or paper with quote and locator), using `browser_url` / `source_url` from `habitat_evidence.tsv`.
3. **Keep geography separate.** Country, coordinates and dates are context, not habitat; show them in a
   separate "collection" block.
4. **Sample material.** Tissue/culture values (`sample_material`, flag `tissue_or_culture_only`) should be
   shown as "sample material", not habitat.
5. **MRDB-accession pages** should show per-source-record grades when they differ (43 accessions).
6. **Missingness wording** should follow `not_reported_scope`: "not reported in the linked sample records;
   literature not reviewed" (2,796), "... literature not accessible" (23), "not reported in sample records or
   the reviewed literature" (12).

## 3. Before exposing AMBIGUOUS records

After PR-7c.1a there are 59 physical AMBIGUOUS records (`ambiguity_class`: FORMATTING_ONLY 9, NESTED_WORDING 20,
DISTINCT_SAME_SAMPLE 19, DISTINCT_ACROSS_SAMPLES 10, LITERATURE_VS_DATABASE 1) and 84 host AMBIGUOUS records
(mostly host scientific vs common name pairs). The class can drive the display wording ("formatting
differences" vs "conflicting sample records") without changing the grade.
Options (each needs an explicit decision and a re-run of the PR-7c.1 tests):

- **Per-sample canonical value**: treat the BioSample as authoritative and the INSDC source feature as a copy
  when both describe the same sample unit; report the copy only if it adds information.
- **Use the INSDC flat-file host** rather than the ENA portal coding row, which rewrites some host names.
- **Relaxed comparison for display only**: punctuation-insensitive and token-subset agreement; keep the
  strict grade in the data files so the stricter audit remains reproducible.
- Leave across-sample-unit conflicts (10 instances, e.g. different depths or sea-ice layers) as genuinely
  ambiguous and show all values.

## 4. Data contract suggestions

- Add habitat to the web export only as a separate, versioned file (e.g. `habitat_v1.json`) generated from
  `habitat_record_availability.tsv`, with the audit version, base commit, cache SHA-256 and UniProt release in
  its header, so the frozen v1.6.0 science files stay untouched.
- Fields: `grade` (physical), `values[]` (`role`, `value_original`, `envo_ids`, `evidence_id`),
  `host_association_status`, `host_values[]`, `ambiguity_class`, `literature_status`, `not_reported_scope`,
  `flags`. Do not export `pr7c1_grade` (transition bookkeeping only). Do not export `value_normalized` as a display value.
- Add a schema test that the export contains no inferred values: every value must resolve to an
  `evidence_id` in `habitat_evidence.tsv`.

## 5. Coverage improvements worth considering (separate PRs)

- Finish the 24 literature LOOKUP_FAILED records with institutional access or manual curation (supplementary
  tables for A0ABR7ZCQ4, M0JSR0, A7WQE8 likely contain the strain isolation sources).
- Extend literature review beyond the 110-record subset, prioritising Swiss-Prot and E1/E2 records.
- Culture-collection catalogues (ATCC, DSMZ, NIES, CCAP) often state the isolation source of type strains;
  this would be a new, separately graded evidence source and needs its own rules (catalogue entry must name the
  same strain).
- A reviewed free-text-to-ENVO mapping for `isolation_source`, kept as a separate, clearly labelled layer.
- A reviewed host-name reconciliation (NCBI Taxonomy) for the host axis, as a separate layer; the audit does
  not reconcile host synonyms.
- Observation: A0A6N7QP32 has env_local_scale `00000316`, which looks like a bare ENVO number without prefix;
  it was left as submitted (usable free text) and could be reviewed in curation.
- Report the database mapping observations (section 9 of the main report) to curation.
