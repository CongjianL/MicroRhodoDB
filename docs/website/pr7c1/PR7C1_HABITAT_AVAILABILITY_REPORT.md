# PR-7c.1 Habitat metadata availability audit

**Status: PR7C1_AUDIT_PARTIAL**

The database chain is complete for every record (0 LOOKUP_FAILED of 5,466), both validations agree, and
every repository regression check passes. The status is PARTIAL only because the literature subset is
incomplete: 24 of the 110 literature-subset records (21.8%) remain literature `LOOKUP_FAILED`
(paywalled, scanned-only or supplement-only sources). This is the plan's PARTIAL criterion
"the literature subset is incomplete". No grade was derived from a failure.

This is an evidence-availability audit, not an enrichment. No habitat value was inferred from taxonomy,
organism name, sequence similarity or geography, no ENVO ID was inferred, and nothing was written to the
frozen database, the exporter, the production JSON or the UI.

Base commit `932eb567a199f9eef25f7e04ac2aaa745e17156c`; frozen DB `microrhododb_v1.6.0.sqlite`
(sha256 `379a2543...dce17f`); UniProt release 2026_03; retrieval window 2026-10-12 10:11-10:24 UTC
(final pass; earlier passes were cached and replayed). Rules: `habitat_field_dictionary.md`.

## 1. Headline numbers (5,466 v1.6.0 source protein records)

| Primary grade | Records | % |
|---|---:|---:|
| DIRECT_SAMPLE | 2,631 | 48.13 |
| VERIFIED_ISOLATE | 17 | 0.31 |
| ORGANISM_CONTEXT_ONLY | 36 | 0.66 |
| AMBIGUOUS | 137 | 2.51 |
| NOT_REPORTED | 2,645 | 48.39 |
| LOOKUP_FAILED | 0 | 0.00 |
| NOT_SEARCHED | 0 | 0.00 |

- **Usable habitat from any source** (DIRECT_SAMPLE + VERIFIED_ISOLATE): 2,648 / 5,466 (48.44%).
  AMBIGUOUS records also carry usable values, but they disagree under the strict rule.
- **MRDB-accession rollup** (5,299 accessions): DIRECT 2,576 (48.61%), VERIFIED 16, ORGANISM 30,
  AMBIGUOUS 125, NOT_REPORTED 2,552, LOOKUP_FAILED 0; 44 accessions have source records with mixed grades.
- **NOT_REPORTED scope:** 2,633 `database_chain_only` (literature not searched or literature lookup failed)
  and 12 `database_and_literature`. NOT_REPORTED never means "the organism has no habitat"; it means the
  linked sample records do not report one.

### Usable values per role (records)

| Role | Records | % |
|---|---:|---:|
| isolation_source | 2,326 | 42.55 |
| env_broad_scale | 864 | 15.81 |
| env_medium | 769 | 14.07 |
| host | 755 | 13.81 |
| env_local_scale | 625 | 11.43 |

Reported but never graded: country 2,865 (52.41%), collection_date 2,430 (44.46%), sample_material 1,352
(24.73%), lat_lon 1,114 (20.38%), habitat_nonstandard 40 (0.73%).

### Funnel (`fig_habitat_chain_funnel.svg`)

searched 5,466 -> INSDC link found 5,448 (99.67%) -> INSDC record resolved 5,448 -> any habitat field present
4,155 (76.02%) -> informative habitat value 2,781 (50.88%) -> DIRECT_SAMPLE 2,631 (48.13%).

The largest loss is between "field present" and "informative" (1,374 records). Contributors: 1,916 records
(35.05%) have at least one habitat role whose value is a missing-value token (`missing`, `not applicable`,
...), and 248 records (4.54%) have only tissue/culture values (`tissue_or_culture_only`). 548 records (10.03%) have no BioSample link at all.

## 2. Strata

| Stratum | Usable (any source) | Notes |
|---|---|---|
| Bacteria (1,455) | 902 (61.99%) | |
| Archaea (699) | 345 (49.36%) | |
| Eukaryota (3,120) | 1,217 (39.01%) | NOT_REPORTED 57.50% |
| Unassigned domain (192) | 184 (95.83%) | environmental clones |
| ENVIRONMENTAL_CLONE (323) | 312 (96.59%) | |
| ISOLATE_GENOME (4,383) | 2,251 (51.36%) | |
| TRANSCRIPTOME (46) | 0 | all NOT_REPORTED |
| sample_type UNKNOWN (698) | 70 (10.03%) | mostly no BioSample |
| reviewed (Swiss-Prot, 51) | 4 (7.84%) | old entries without BioSamples |
| characterized (107) | 36 (33.64%) | |
| status member / candidate / boundary / outgroup / rejected / engineered | 48.72 / 49.46 / 36.35 / 58.81 / 50.49 / 0 % | |
| evidence level E1 / E2 / E3 / E4 / E5 | 28.57 / 27.68 / 46.89 / 52.95 / 48.83 % | |

The best-studied proteins (Swiss-Prot, characterized, E1/E2) have the lowest database coverage, because they
predate BioSample/MIxS submission. This is the main reason literature evidence matters for the website.
Full strata (domain, phylum, status group, evidence level, sample type, release) are in
`habitat_coverage_summary.tsv` and the figures `fig_habitat_grade_by_domain.svg`,
`fig_habitat_grade_by_status_group.svg`, `fig_habitat_field_completeness.svg`.

## 3. AMBIGUOUS diagnostics (137 records, 142 conflicting role instances)

- Scope: 132/142 role conflicts (92.96%) are **within one sample unit** (an INSDC source feature vs its own
  BioSample, or two representations of one BioSample); only 10 are across sample units. 126/137 records
  are AMBIGUOUS only through within-unit conflicts.
- Kind: 89 `distinct_values`, 43 `token_subset`, 10 `punctuation_only`.
- The live spot-check found that 10 of its 15 AMBIGUOUS records are host scientific vs common name pairs; in 3
  (A0A0F8A5R8, A0AAF0DL47, N1RG29) the ENA portal coding row rewrites the host name while the INSDC flat file
  matches the BioSample. Only B2D036 (2 m vs 12 m) and D2Y5H4 (sea-ice layers) were genuinely different values.
- One record (A0A411LJN5) is AMBIGUOUS only because a parent-verified literature quote is inconsistent
  with its database value (`mapping_confidence` LITERATURE).

The strict agreement rule was kept as agreed. Most AMBIGUOUS records are representational, not scientific,
disagreements; recommendations are in `PR7C2_HABITAT_DESIGN_RECOMMENDATIONS.md`.

## 4. Literature subset (110 records = 107 characterized + seeds)

| literature_status | Records |
|---|---:|
| ISOLATE_EVIDENCE | 29 |
| ORGANISM_CONTEXT | 44 |
| NOT_REPORTED | 13 |
| LOOKUP_FAILED | 24 |
| NOT_SEARCHED (outside the subset) | 5,356 |

Cross-tab with the primary grade: ISOLATE_EVIDENCE gives VERIFIED_ISOLATE 17, DIRECT_SAMPLE 10 (database
takes precedence, quote consistent) and AMBIGUOUS 2; ORGANISM_CONTEXT gives ORGANISM_CONTEXT_ONLY 36 and
DIRECT 8; literature LOOKUP_FAILED records are NOT_REPORTED 22 (scope `database_chain_only`) and DIRECT 2.

- One reviewer pass (split into two parallel parts) plus a retry pass for lookup failures, then parent
  searches and decisions in `literature.py`. Every one of
  the 91 accepted quotes was re-fetched and verified verbatim by the parent through the audit cache
  (`literature_quote_verification.json`, 62 verification requests, all HTTP 200).
- Parent decisions demoted or rejected reviewer isolate calls that rested on a different strain, an
  epithet, a strain not named in the quoted sentence, or geography only (e.g. Q6J4G7 "the Red Sea" rejected:
  dataset-level, not per clone; A0A089ZH82 demoted to organism context: strain not named in the quoted
  sentence). Geography is never habitat.
- The literature consistency call (`consistent_with_db`) is a reviewer semantic judgement, a documented
  deviation from the strict string rule used for database values.
- Remaining literature LOOKUP_FAILED (24): A0A3G1I4H9, A0A495RAM9, A0A977XLG0, A0A9X9ZA75, A0AA82WPB4,
  A0ABR7ZCQ4, A0ABY3LD08, A0ACD6B968, A7WQE8, I4DST7, L1K1K8, M0JSR0, P0DMH7, P0DMH8, P15647, P29563, P42196,
  P96787, Q48314, Q48315, Q6R5N7, Q8RUT8, Q93WP2, Q9UW81. Causes: paywalled or bot-blocked full text
  (Nature 2023, NSMB 2023, Mol Cell 2024, DNA Research 2001 and older JBC/ABB/BBA/JMB/Biochemistry/Science
  articles), scanned-only PMC pages (P0DMH8, P42196), and per-strain tables only in unread supplements
  (A0ABR7ZCQ4, M0JSR0, A7WQE8). These need institutional access or manual curation.

## 5. Retrieval

- 419 database requests (UniProt 70, ENA 311, NCBI E-utilities 38): 334 HTTP 200, 84 ENA HTTP 400 (empty
  result, recorded as `not_found`), 1 HTTP 404. No request failed after retries. Every request is listed in
  `habitat_requests.tsv` with URL, body, status, attempts, timestamp and response SHA-256; every evidence row
  carries its `request_key`.
- Entities: 5,466 UniProt entries, 5,777 ENA coding rows, 27 sequence rows + 27 INSDC flat files, 7 proteomes,
  24 UniParc entries, 2,414 BioSamples (each fetched from both ENA and NCBI), 1,979 studies, 112 explicit
  ENVO IDs checked in OLS (6 records carry an invalid ENVO ID, flag `envo_id_invalid`).
- The raw response cache (`habitat_cache.tar.gz`) allows a fully offline replay. Two offline replays were
  byte-identical (all tables, figures and the manifest).

## 6. Validation and tests (details in `PR7C1_INDEPENDENT_VALIDATION.md`)

- Independent re-implementation from the dictionary alone: round 1 found 4 grade differences and 1
  confidence difference (spec gaps D1-D4, code deviation D5). After the dictionary was completed and D5 fixed
  in code, round 2 matched **all 39 columns for all 5,466 records** (EXACT_MATCH).
- Live 100-record spot-check (seed 20261012) against ENA, NCBI and UniProt web records: 100/100 grades and
  values agree.
- `tests/test_habitat_audit_pr7c1.py`: 70 tests (synthetic rules and negatives, 23-record real-data fixture
  replay, failure injection, output traceability, summary recomputation, no habitat keys in the web export).
  Classifier mutation audit 13/13 killed.

## 7. Repository regression (all exit 0)

frozen_baseline (fab9182 sums), refpkg SHA256SUMS, no diff since 932eb56 in `releases refpkg pipeline site`,
DB sha256, 12 release blockers unchanged (all `open`, resolution null), `web/` and `.github/` unchanged,
fresh web export contains no habitat keys, schema/types check, structure fixtures, drill-down golden sets,
reconciliation (58 items, all_ok), scientific audit 47/47, audit mutations 13/13, full `pytest`
(402 passed, 12 skipped: artifact-only tests that need a built site). Web code and workflows are unchanged,
so Playwright/E2E were not re-run.

## 8. Limitations

- Literature covers only 110 records; 5,356 records are `NOT_SEARCHED` for literature, and their
  NOT_REPORTED grade is database-chain-only.
- The strict string rule makes AMBIGUOUS mostly representational (section 3).
- Values are reported as submitted; no ontology mapping was attempted for free text, and only explicit ENVO
  IDs are carried.
- The independent re-implementation consumes the same parsed entities, so it validates classification, not
  parsing; parsing is validated by the live spot-check (100 records) and the hand-traced pilot.
- Some evidence-table conventions (E1-E3 in the validation report) were documented after round 2; they do not
  affect any record-table value.
- Untested on real data (no occurrences): request failures, unresolvable samples, assembly fallback, ENVO
  lookup failures, `host_is_self` (covered by synthetic tests only).

## 9. Database mapping observations (report only, nothing changed)

Reviewers noticed records whose UniProt/DB publication links point to papers that do not describe the
organism: A0A517QXI7, A0A4P9TF16, A0A495RAM9, citations of software papers (Coot, MEGA7), the W8VZW3 DOI,
Phaeosphaeria PMID 25379341, H2EZZ6 (the JBC 2013 paper is about *Platymonas*), A0ABF7PQA2 (DOI is the 1995
particle-mesh Ewald methods paper). A0A6P3CW42 is a PDB mutant not flagged as engineered. A0A089ZH82 has
database env_medium "soil" while the strain's paper describes biogas-plant isolates. These are candidates
for a curation follow-up, outside PR-7c.1.

## 10. Files

Tables: `habitat_record_availability.tsv` (one row per source record), `habitat_evidence.tsv` (105,750
evidence rows incl. 91 literature rows), `habitat_provenance_links.tsv`, `habitat_requests.tsv`,
`habitat_attribute_inventory.tsv`, `habitat_coverage_summary.tsv`, `habitat_retrieval_manifest.json`.
Figures: `figures/*.svg`. Literature: `literature/`. Validation: `validation/`, `mutation_audit.json`,
`validation_spotcheck_sample.tsv`. Code: `tools/habitat_audit/`; reproduce offline with
`python -m tools.habitat_audit.run full --offline` after extracting the cache.
