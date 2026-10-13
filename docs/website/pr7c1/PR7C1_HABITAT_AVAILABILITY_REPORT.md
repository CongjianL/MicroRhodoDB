# PR-7c.1 Habitat metadata availability audit

> **Corrected by PR-7c.1a (scientific semantics correction, audit version 1.1.0).** All numbers below are
> regenerated from the preserved retrieval cache under the corrected rules: the primary grade now measures
> the **physical sampling habitat** only (`env_broad_scale`, `env_local_scale`, `env_medium`,
> `isolation_source`); `host` is reported on a separate **host-association** axis; a bare `0` in the MIxS
> environment fields is an invalid placeholder; AMBIGUOUS records carry an ambiguity class; and NOT_REPORTED
> distinguishes literature not reviewed from literature inaccessible. PR-7c.1 values are given in brackets
> where they changed. Details, transitions and validation: `PR7C1A_SCIENTIFIC_CORRECTION_REPORT.md`.

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

| Primary grade (physical habitat) | Records | % | [PR-7c.1] |
|---|---:|---:|---:|
| DIRECT_SAMPLE | 2,523 | 46.16 | [2,631] |
| VERIFIED_ISOLATE | 17 | 0.31 | |
| ORGANISM_CONTEXT_ONLY | 36 | 0.66 | |
| AMBIGUOUS | 59 | 1.08 | [137] |
| NOT_REPORTED | 2,831 | 51.79 | [2,645] |
| LOOKUP_FAILED | 0 | 0.00 | |
| NOT_SEARCHED | 0 | 0.00 | |

- **Usable physical habitat from any source** (DIRECT_SAMPLE + VERIFIED_ISOLATE): 2,540 / 5,466 (46.47%)
  [2,648, 48.44%]. AMBIGUOUS records also carry usable physical values, but they disagree under the strict rule.
- **Host association** (separate axis): REPORTED 671, AMBIGUOUS 84, NOT_REPORTED 4,711; 755 records (13.81%)
  report a host. **186 records (3.40%) report a host but no usable physical habitat** (`host_association_only`);
  in PR-7c.1 these were DIRECT_SAMPLE (171) or AMBIGUOUS (15) and are now NOT_REPORTED. 548 records have both
  usable physical habitat and a host.
- **Transitions from PR-7c.1:** DIRECT -> NOT_REPORTED 171 (host only); AMBIGUOUS -> DIRECT 63 (only the host
  disagreed; physical values agree); AMBIGUOUS -> NOT_REPORTED 15 (host-only disagreement); all other records
  unchanged. A0ABS3TAH3 and A0ABS3TE24 stay DIRECT_SAMPLE through `isolation_source = soil`; their `0`
  env_broad_scale/env_local_scale/env_medium values (12 evidence items) are now `invalid_placeholder`.
- **MRDB-accession rollup** (5,299 accessions): DIRECT 2,472 (46.65%) [2,576], VERIFIED 16, ORGANISM 30,
  AMBIGUOUS 55 [125], NOT_REPORTED 2,726 [2,552], LOOKUP_FAILED 0; 43 [44] accessions have source records
  with mixed grades.
- **NOT_REPORTED scope (2,831):** 2,796 `database_only_literature_not_reviewed` (outside the literature subset),
  23 `database_only_literature_inaccessible` (literature LOOKUP_FAILED) and 12 `database_and_literature`.
  [PR-7c.1 merged the first two as `database_chain_only`.] NOT_REPORTED never means "the organism has no
  habitat"; it means the linked sample records do not report a physical one, and for 2,819 records the
  literature was not reviewed or not accessible.

### Usable values per role (records)

| Role | Records | % | [PR-7c.1] |
|---|---:|---:|---:|
| isolation_source | 2,326 | 42.55 | |
| env_broad_scale | 862 | 15.77 | [864] |
| env_medium | 767 | 14.03 | [769] |
| env_local_scale | 623 | 11.40 | [625] |
| host (association, not physical habitat) | 755 | 13.81 | |

Reported but never graded: country 2,865 (52.41%), collection_date 2,430 (44.46%), sample_material 1,352
(24.73%), lat_lon 1,114 (20.38%), habitat_nonstandard 40 (0.73%).

### Funnel (`fig_habitat_chain_funnel.svg`)

Physical roles only (PR-7c.1a): searched 5,466 -> INSDC link found 5,448 (99.67%) -> INSDC record resolved
5,448 -> any physical habitat field present 4,013 (73.42%) [4,155] -> informative physical value 2,596 (47.49%)
[2,781] -> DIRECT_SAMPLE 2,523 (46.16%) [2,631].

The largest loss is between "field present" and "informative" (1,417 records). Contributors: 1,916 records
(35.05%) have at least one habitat role whose value is a missing-value token (`missing`, `not applicable`,
...), and 382 records (6.99%) [248] have only tissue/culture values and no physical grade
(`tissue_or_culture_only`; the increase is the host-only records whose tissue/material values were previously
masked by a DIRECT/AMBIGUOUS grade). 548 records (10.03%) have no BioSample link at all.
42 records keep a tissue `isolation_source` (e.g. `leaf`) as a usable physical value because a non-self host is
reported (`host_associated_isolation_source`); for 23 of them it is the only physical value
(`host_tissue_isolation_source_only`, a sensitivity marker).

## 2. Strata

| Stratum | Usable physical habitat (any source) [PR-7c.1] | Host reported | Host only |
|---|---|---|---|
| Bacteria (1,455) | 872 (59.93%) [902] | 112 | 38 |
| Archaea (699) | 344 (49.21%) [345] | 5 | 1 |
| Eukaryota (3,120) | 1,142 (36.60%) [1,217]; NOT_REPORTED 62.15% | 634 | 145 |
| Unassigned domain (192) | 182 (94.79%) [184]; environmental clones | 4 | 2 |
| ENVIRONMENTAL_CLONE (323) | 312 (96.59%) | 0 | 0 |
| ISOLATE_GENOME (4,383) | 2,150 (49.05%) [2,251] | 737 | 179 |
| TRANSCRIPTOME (46) | 0; all NOT_REPORTED | 0 | 0 |
| sample_type UNKNOWN (698) | 63 (9.03%) [70]; mostly no BioSample | 13 | 7 |
| reviewed (Swiss-Prot, 51) | 4 (7.84%); old entries without BioSamples | 0 | 0 |
| characterized (107) | 35 (32.71%) [36] | 3 | 1 |
| status member / candidate / boundary / outgroup / rejected / engineered | 46.26 / 48.22 / 34.58 / 56.48 / 53.40 / 0 % [48.72 / 49.46 / 36.35 / 58.81 / 50.49 / 0] | | |
| evidence level E1 / E2 / E3 / E4 / E5 | 27.47 / 26.79 / 46.72 / 47.24 / 47.39 % [28.57 / 27.68 / 46.89 / 52.95 / 48.83] | | |

Host association is concentrated in Eukaryota (634 of 755 host-reporting records; 145 of the 186 host-only
records), mostly fungal and algal genomes isolated from plant or animal hosts. The "rejected" stratum rises
(50.49 -> 53.40%) because 3 records whose only disagreement was the host now resolve to DIRECT_SAMPLE.

The best-studied proteins (Swiss-Prot, characterized, E1/E2) have the lowest database coverage, because they
predate BioSample/MIxS submission. This is the main reason literature evidence matters for the website.
Full strata (domain, phylum, status group, evidence level, sample type, release) are in
`habitat_coverage_summary.tsv` and the figures `fig_habitat_grade_by_domain.svg`,
`fig_habitat_grade_by_status_group.svg`, `fig_habitat_field_completeness.svg`.

## 3. AMBIGUOUS diagnostics (PR-7c.1a: 59 physical AMBIGUOUS records, 58 conflicting physical role instances; 84 host AMBIGUOUS)

PR-7c.1 reported 137 AMBIGUOUS records; 78 of them disagreed only on `host`, 52 only on `isolation_source`,
6 on both and 1 only against literature. Host disagreements are now on the host axis.

| `ambiguity_class` (physical, n = 59) | Records | Interpretation |
|---|---:|---|
| FORMATTING_ONLY | 9 | punctuation/separator differences only |
| NESTED_WORDING | 20 | one value contains the other's words (e.g. `sediment` vs `lake sediment`) |
| DISTINCT_SAME_SAMPLE | 19 | different wording inside one sample unit; unresolved (synonym, typo or submitter inconsistency) |
| DISTINCT_ACROSS_SAMPLES | 10 | distinct values from different samples; genuine-conflict candidates |
| LITERATURE_VS_DATABASE | 1 | A0A411LJN5 |

| `host_ambiguity_class` (host, n = 84) | Records |
|---|---:|
| FORMATTING_ONLY | 1 |
| NESTED_WORDING | 23 |
| DISTINCT_SAME_SAMPLE | 60 (mostly common vs scientific names, e.g. `apple` vs `Malus domestica`; not reconciled, no host taxonomy in the cache) |
| DISTINCT_ACROSS_SAMPLES | 0 |

- Physical scope: 48/58 role conflicts are within one sample unit, 10 across sample units. Kind: 29
  `distinct_values`, 20 `token_subset`, 9 `punctuation_only`.
- Of the 10 DISTINCT_ACROSS_SAMPLES records, 8 differ by depth or sea-ice layer within one water body
  (Lake Kinneret 2/6/12 m, sea-ice layers) or between two Great Lakes (C0K2D9, C0K2E3: Lake Erie vs Lake
  Superior); only B2D007 (Baltic Sea vs freshwater lakes) and F6LYH6 (Lake Kinneret vs Ganges River) span
  habitat types. The independent validator also noted 4 DISTINCT_SAME_SAMPLE records that differ only by a
  typo. The classes are rule-based descriptions; no value was resolved.
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
DIRECT 8; literature LOOKUP_FAILED records are NOT_REPORTED 23 (scope `database_only_literature_inaccessible`)
and DIRECT 1 [PR-7c.1: 22 and 2; one record's only database value was a host]. The literature NOT_REPORTED
records are NOT_REPORTED 12 (`database_and_literature`) and DIRECT 1.

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
- `tests/test_habitat_audit_pr7c1.py`: 102 tests after PR-7c.1a (synthetic rules and negatives, 32-record
  real-data fixture replay, failure injection, output traceability, summary recomputation, host/physical
  separation, zero placeholder, ambiguity classes, NOT_REPORTED scopes, portability, no habitat keys in the
  web export). Classifier mutation audit 22/22 killed (13 PR-7c.1 + 9 PR-7c.1a).
- PR-7c.1a round-3 independent re-implementation (`validation/round3_pr7c1a/`): all classification and
  habitat columns match on 5,466/5,466 records; 63/63 recomputed summary rows match numerator and denominator.

## 7. Repository regression (all exit 0)

frozen_baseline (fab9182 sums), refpkg SHA256SUMS, no diff since 932eb56 in `releases refpkg pipeline site`,
DB sha256, 12 release blockers unchanged (all `open`, resolution null), `web/` and `.github/` unchanged,
fresh web export contains no habitat keys, schema/types check, structure fixtures, drill-down golden sets,
reconciliation (58 items, all_ok), scientific audit 47/47, audit mutations 13/13, full `pytest`
(402 passed, 12 skipped: artifact-only tests that need a built site). Web code and workflows are unchanged,
so Playwright/E2E were not re-run.

## 8. Limitations

- Literature covers only 110 records; 5,356 records are `NOT_SEARCHED` for literature, and their
  NOT_REPORTED grade is database-only (`database_only_literature_not_reviewed`).
- The strict string rule makes AMBIGUOUS partly representational; `ambiguity_class` describes this without
  resolving values (section 3).
- Host names are not reconciled (no host taxonomy in the cache); host is an association, not a habitat.
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
`python -m tools.habitat_audit.run full --offline` after extracting the cache to `work/habitat_cache`
(or pass `--cache DIR`).
