# PR-7c.1 habitat field dictionary

This document is the normative specification of the PR-7c.1 habitat metadata availability audit.
It is written so that the classification can be re-implemented independently from two inputs:

1. the frozen record identity (5,466 v1.6.0 source protein records; `tools/habitat_audit/baseline.py`), and
2. the entity store `entities.json` (parsed responses from the raw HTTP cache; `tools/habitat_audit/retrieve.py`)
   plus the parent-verified literature file `literature/literature_evidence.json`.

Nothing in this audit infers habitat. No ENVO ID is assigned that was not written by the submitter.
Taxonomy, organism name, sequence similarity and geography are never used to derive a habitat value.
A lookup failure or an unsearched source is never reported as NOT_REPORTED.

## 1. Evidence grades (`primary_grade`)

| Grade | Meaning |
|---|---|
| `DIRECT_SAMPLE` | At least one usable value in a usable habitat role, from an INSDC source feature or a BioSample linked to the record's own sequence/assembly, and no disagreement (section 6). |
| `VERIFIED_ISOLATE` | No usable database value; a parent-verified literature quote states where the same strain/isolate/clone was isolated. |
| `ORGANISM_CONTEXT_ONLY` | No usable database value and no isolate-level quote; a parent-verified quote describes the habitat of the species/organism in general. Not a sample habitat. |
| `AMBIGUOUS` | Usable values disagree within a habitat role (strict rule, section 6), or a verified literature isolate quote is marked inconsistent with the database value. |
| `NOT_REPORTED` | The chain completed without failure and no usable habitat value exists (and no literature isolate/organism item applies). |
| `LOOKUP_FAILED` | At least one required lookup in the chain failed (network/HTTP error, unparseable response, ambiguous sample match). |
| `NOT_SEARCHED` | The record was not searched in this run (pilot mode only; the full run searched all 5,466 records). |

Grade precedence for one record (first match wins):
`LOOKUP_FAILED` > `AMBIGUOUS` > `DIRECT_SAMPLE` > `VERIFIED_ISOLATE` > `ORGANISM_CONTEXT_ONLY` > `NOT_REPORTED`.

`has_usable_habitat` = 1 iff grade is `DIRECT_SAMPLE` or `VERIFIED_ISOLATE`.

Companion columns:
- `db_habitat_status`: the database-only grade (`LOOKUP_FAILED` > `AMBIGUOUS` (DB conflict only) > `DIRECT_SAMPLE` > `NOT_REPORTED`).
- `db_chain_status`: `INCOMPLETE` (any failure), `NO_LINK` (no link of any kind), else `COMPLETE`.
- `literature_status`: `NOT_SEARCHED` for records outside the literature subset (110 records = 107 characterized
  union 15 seeds); otherwise the final status in `literature_evidence.json` (section 9).
- `not_reported_scope` (only when grade is `NOT_REPORTED`): `database_and_literature` when `literature_status`
  is `NOT_REPORTED`; otherwise `database_chain_only` (the literature was not searched, or was searched but
  a source could not be accessed).

## 2. Source chain and linkage routes

For each record the chain is followed in this order. Links are ordered by `(protein_id, parent_accession)`
and numbered `link_index` from 0.

1. UniProtKB entry (`uniprot[acc]`). Status `failed` is a failure. `inactive`/`not_found` sets `uniprot_inactive`.
2. EMBL cross-references of the entry. UniParc (`uniparc[acc].embl_protein_ids`) adds extra links with
   `embl_status = "uniparc"`, mapping confidence MEDIUM, flag `uniparc_embl_link`. A UniParc failure is a failure.
3. For each EMBL link:
   - `cds_protein_id` (HIGH): `cds[protein_id without version]` found. Uses `rows[0]`; >1 row sets `cds_multiple_rows`.
     For a UniParc link the route is called `uniparc_embl_protein` (MEDIUM). `failed` is a failure (`ena_coding:<pid>`).
   - `embl_parent_sequence` (HIGH): only if no protein id or the CDS was `not_found`; `sequence[parent]` found.
     `failed` is a failure (`ena_sequence:<pa>`).
   - `wgs_set` (HIGH): only if the sequence was `not_found` and the parent matches `^[A-Z]{4,6}\d{2}\d{6,}$`;
     `wgs_set[prefix]` found. (All 16 queried prefixes returned `not_found` in this run.)
   - `insdc_flatfile_biosample` (HIGH): only if the sequence was `not_found` and the WGS status is empty or
     `not_found`; `insdc_flatfile[parent]` found with at least one `DR   BioSample;` line. Its BioSamples and
     `PR   Project:` studies become the link's samples/studies. `failed` is a failure (`ena_flatfile:<pa>`).
   - otherwise `embl_xref_unresolved`, flag `insdc_record_unresolved`.
4. Only when the entry has no EMBL link at all and is active: `proteome_assembly` (MEDIUM) for each proteome:
   the proteome's BioSamples; if none, the ENA assembly row. Failures: `proteome:<UP>`, `ena_assembly:<GCA>`.
5. No links at all: flag `no_insdc_link`.
6. Samples of a link = `sample_accession` of the resolved ENA row (split on `;`) plus flat-file/proteome samples.
   No samples overall: `no_biosample_link`; more than one: `multiple_biosamples`.
7. Each BioSample is read from both ENA (`sample_ena`) and NCBI (`sample_ncbi`). Either `failed` is a failure;
   ENA `ambiguous_match` is a failure. Both `not_found`: `sample_unresolvable`; one `not_found`: `sample_copy_absent`.
   NCBI BioSample IDs are resolved only through `esearch <acc>[accn]` and verified to return the same accession
   (an `efetch` by UID can silently return a different sample, e.g. SAMEA5987284 vs SAMN05987284).
8. BioProject/study rows are context only; a study failure sets `study_lookup_failed` and is not a grade input.

`linkage_route` lists the distinct routes of a record (sorted, `;`-joined).

## 3. Evidence items

Each attribute becomes one evidence item with: `source_acc, evidence_source, entity_accession, link_index,
field_original, role, value_original, value_normalized, envo_ids, request_key, linkage_route, mapping_confidence,
value_status, evidence_id`.

| `evidence_source` | Origin | Fields |
|---|---|---|
| `insdc_source_feature` | resolved ENA coding/sequence row (routes `cds_protein_id`, `embl_parent_sequence`, `uniparc_embl_protein`) | `isolation_source, host, country, location, collection_date, strain, isolate, sub_strain, environmental_sample, cell_type, cell_line, tissue_type, tissue_lib, metagenome_source` and `scientific_name` (role `organism`) |
| `ena_biosample` | ENA sample XML | every attribute whose tag maps to a role; plus `title`, `description` (roles `sample_title`, `sample_description`) |
| `ncbi_biosample` | NCBI BioSample XML | every attribute whose `harmonized_name` (else `name`) maps to a role; `package`; title and description |
| `literature` | parent-verified literature (section 9) | quote and locator |

Each BioSample's items are attached once, to the first link (in `link_index` order) that lists it.
`entity_accession` is the BioSample for sample items, the protein id (CDS route) or parent accession
(sequence route) for source-feature items.

`evidence_id` = `"HE"` + first 12 hex of SHA-256 of
`source_acc|evidence_source|entity_accession|link_index|field_original|value_original`.
Literature: `"HL"` + 12 hex of SHA-256 of `pmid|doi|quote|scope` followed by the source accession.

## 4. Roles (`normalize.ROLE_MAP`)

Tag key: remove characters outside printable ASCII, lower case, collapse runs of `_`, `-` and whitespace to one space.

**Usable habitat roles** (the only roles that can make a record `DIRECT_SAMPLE`):

| Role | Tags |
|---|---|
| `env_broad_scale` | env broad scale; broad scale environmental context; env biome; environment (biome); environment biome; biome |
| `env_local_scale` | env local scale; local environmental context; local scale environmental context; env feature; environment (feature); environment feature; feature |
| `env_medium` | env medium; environmental medium; env material; environment (material); environment material; material |
| `isolation_source` | isolation source; isolation source host associated; isolation source non host associated |
| `host` | host; specific host; host scientific name; nat host; natural host |

Legacy MIxS `env_biome`/`env_feature`/`env_material` are mapped to the current triad as shown.

**Reported, never graded:**

| Role | Tags | value_status |
|---|---|---|
| `habitat_nonstandard` | environment; habitat; isolation site; source of isolate; seabed habitat | `nonstandard_context` |
| `sample_material` | tissue; tissue type; cell type; cell line; sample material; dev stage; tissue lib; sample type | `material` |
| `host_detail` | host body site; host tissue sampled; host taxid; host tax id; host common name; host body habitat; host description; body site; plant body site; plant structure; plant struc | `context` |
| `country` | geo loc name; country; geographic location (country and/or sea); geographic location (region and locality) | `geography` |
| `lat_lon` / `lat` / `lon` | lat lon; location / latitude; lat; geographic location (latitude) / longitude; lon; geographic location (longitude) | `geography` |
| `collection_date` | collection date | `date` |
| `depth` | depth; geographic location (depth) | `depth` |
| identity/type | strain, sub strain (`strain`); isolate; environmental sample; metagenome source, metagenomic source; ncbi submission package (`package`); ena checklist (`checklist`); organism, scientific name (`organism`); investigation type | `context` |
| `sample_title`, `sample_description` | sample title/description | `context` |

Any of these with a missing value (section 5) gets `reported_missing` instead.
Tags that map to no role are not recorded as evidence (they appear only in the attribute inventory).

## 5. Value status of habitat-role items

Applied in this order (first match wins):

1. `reported_missing`: normalized value empty or matching
   `^(missing|not collected|not applicable|not provided|not available|not determined|restricted access|unknown|unspecified|na|n/a|n.a.|none|null|nan|-|--|.|?)(\s*[:;,(].*)?$` (case-insensitive).
2. `host_is_self` (role `host` only): the host equals the record's own organism: the host taxid equals the
   record taxid; or the normalized host equals a normalized organism name (UniProt organism, DB organism,
   source-feature `scientific_name`); or, for non-viral organisms only, the first two words match a
   two-word organism binomial that does not end with `sp`/`sp.`. Sets flag `host_is_self_ignored`.
3. `uninformative_placeholder`: all explicit ENVO IDs are root/placeholder classes
   (ENVO:00010483, 00000428, 01000254, 00002297, 01001110, 00002036, 01000813), or the value with ENVO IDs
   removed is one of: environmental material, environment material, biome, environmental feature,
   environment, environmental system, environmental sample, other, sample.
4. `moved_to_material` (culture): the whole value is a culture/laboratory description (axenic/pure/lab ...
   culture, culture collection, laboratory strain, cell line, plaque, anything containing "agar"/"broth",
   "<x> medium", "culture/growth/isolation media"). A culture mentioned inside a longer habitat
   description is not matched.
5. `moved_to_material` (tissue; role `isolation_source` only): the whole value is a tissue/organism-part term
   (leaf, root, stem, mycelium, spores, thallus, whole organism, cells, ...), unless the same sample entity also
   reports a non-self host (then the tissue is a host-associated isolation source and stays usable).
6. `usable`.

`moved_to_material` and `material` values are listed in `sample_material`; when such a value exists and the
grade is not `DIRECT_SAMPLE`/`AMBIGUOUS`, flag `tissue_or_culture_only` is set.

**ENVO IDs**: only IDs written in the value (`ENVO[:_ ]?\d{7,8}`, zero-padded to 8). Each is checked in OLS:
`not_found` sets `envo_id_invalid` and the ID is dropped from the item; `failed` sets `envo_lookup_failed`
(not a grade failure; the ID is dropped). The text value itself is kept.

`value_normalized` = lower case, leading/trailing whitespace removed, internal whitespace collapsed to one space.

## 6. Agreement rule and conflicts

Within each usable habitat role, usable items are grouped by union-find: two items agree when their
`value_normalized` strings are equal, or both have the same non-empty explicit ENVO-ID set. More than one group
in any role is a conflict: grade `AMBIGUOUS`, flag `conflict`, the role listed in `conflict_roles`.
Roles are evaluated independently (an `isolation_source` and an `env_medium` value never conflict).

Descriptive diagnostics (never change the grade):
- `conflict_kind` per role: `punctuation_only` (groups identical after replacing non-alphanumerics with spaces),
  `token_subset` (one group's word set contains every other group's words), else `distinct_values`.
- `conflict_scope` per role: `within_sample_unit` when all disagreeing items belong to one sample unit
  (a source-feature item belongs to its link's BioSample when the link has exactly one), else `across_sample_units`.

`multi_sample` (DIRECT_SAMPLE only): more than one evidence unit, where units are the record's BioSamples plus
each CDS/sequence/UniParc link that has no BioSample.

Other flags: `geo_discordant` / `date_discordant` when more than one distinct country / collection date exists
after light normalization (whitespace around `:`,`,`,`;` removed; `DD-Mon-YYYY` and `Mon-YYYY` dates converted
to ISO); `free_text_context_only` when there is no usable value but a sample title/description exists;
`habitat_reported_missing` when a habitat role carries a missing-value token; `engineered_record`.

## 7. Sample type (`sample_type`, explicit fields only)

First match: `MAG` (package/checklist contains mimag, ERC000047 or metagenome-assembled); `SAG` (misag, ERC000048);
`METAGENOME_ASSEMBLY` (mims, organism/metagenome_source containing "metagenome", or the word metagenome in the
package); `ENVIRONMENTAL_CLONE` (environmental_sample = true); `ISOLATE_GENOME` (package contains migs.ba, migs.eu,
microbe or pathogen, or a non-missing strain with environmental_sample = false); `TRANSCRIPTOME` (all molecule
types mRNA/transcribed RNA); else `UNKNOWN`.

## 8. Record-table cells

Multiple distinct values in one cell are sorted and joined by ` || `; ID lists by `;`.
Habitat columns (`<role>_original`, `<role>_normalized`, `<role>_envo_ids`) contain usable values only.
`mapping_confidence`: DIRECT_SAMPLE = HIGH if any usable item is HIGH else MEDIUM; VERIFIED_ISOLATE = LITERATURE;
AMBIGUOUS = HIGH/MEDIUM by the same rule, or LITERATURE when only a literature conflict exists; otherwise empty.

## 9. Literature (110-record subset)

- Reviewers searched the record's DB publications, UniProt references and strain identifiers in
  open-access full text and abstracts, and returned verbatim quotes with a locator and scope
  (`isolate`: the quote names the same strain/isolate/clone, or is in a paper about that strain;
  `organism`: species/organism-level habitat only).
- The parent re-fetched every quoted source through the audit HTTP cache (`litverify.py`) and checked the
  quote verbatim after normalization (HTML unescape, tag removal, NFKC, typographic quotes/dashes,
  whitespace-insensitive), and that `habitat_text` occurs inside the quote. An unverified quote is
  scope `rejected`.
- Parent decisions (in `literature.py`) demote or reject reviewer isolate calls that rest on a different strain,
  an epithet, a strain not named in the quoted sentence, or geography only. Geography is never habitat.
- `literature_status`: `ISOLATE_EVIDENCE` > `ORGANISM_CONTEXT` > `LOOKUP_FAILED` (any source not accessible, or
  the reviewer could not complete the search) > `NOT_REPORTED`.
- Consistency between a literature isolate quote and the DB value is a reviewer semantic judgement
  (`consistent`, `inconsistent` only for a genuine contradiction, `not_applicable`), because prose has no
  normalized form. This is a deliberate deviation from the strict string rule of section 6. An `inconsistent`
  verified isolate item makes the record `AMBIGUOUS` only when the record also has a usable DB value.
- Parent step-3 searches (after the reviewer passes) are recorded in `literature_parent_additions.json`; their
  items go through the same quote verification and parent decisions as reviewer items.
- Literature evidence rows have role `literature_isolate`, `organism_context` or `literature_rejected`;
  value_status `usable`, `organism_context` or `rejected:<reason>`; `field_original` =
  `literature:<scope> | <locator>`; `value_original` = the quote; `value_normalized` = normalized `habitat_text`.

## 10. MRDB-accession rollup

Per MRDB accession, the first grade present in
`DIRECT_SAMPLE, VERIFIED_ISOLATE, AMBIGUOUS, ORGANISM_CONTEXT_ONLY, LOOKUP_FAILED, NOT_SEARCHED, NOT_REPORTED`;
`NOT_REPORTED` only when every source record is `NOT_REPORTED`.

## 11. Coverage summary (`habitat_coverage_summary.tsv`)

Long format: `unit, stratum_type, stratum, metric, numerator, denominator, percent` (percent to 2 decimals).
Units `source_record`, `mrdb_accession`. Strata: all, status_group_audit, domain, phylum, source_release,
evidence_level, reviewed, counted, is_characterized, literature_subset, sample_type, mapping_confidence.

Metrics: `grade:<G>`; `usable_habitat_any_source` and `_of_searched`; `usable_field:<role>`;
`reported_field:<habitat_nonstandard|country|collection_date|lat_lon|sample_material>`; `funnel:<stage>`;
`flag:<flag>`; `literature_status:<S>`; `ambiguous_role_conflict_scope:<scope>` and
`ambiguous_role_conflict_kind:<kind>` (denominator = conflicting role instances);
`ambiguous_all_roles_punctuation_only`; `ambiguous_all_roles_within_sample_unit`;
`not_reported_with_nonstandard_habitat_tag`; `mrdb_mixed_source_grades`; `mrdb_multiple_source_records`.

Funnel stages (monotone): `searched` -> `insdc_link_found` (no `no_insdc_link`) -> `insdc_record_resolved`
(no `insdc_record_unresolved` and no coding/sequence/UniParc/proteome failure) -> `habitat_field_present`
(any DB habitat-role item) -> `informative_habitat_value` (any habitat-role item that is not
`reported_missing`/`uninformative_placeholder`) -> `direct_sample`.

## 12. Output tables

- `habitat_record_availability.tsv`: one row per source record (5,466).
- `habitat_provenance_links.tsv`: one row per link with per-step statuses, samples, studies and request keys.
- `habitat_evidence.tsv`: one row per evidence item (database and literature) with `request_key`, `browser_url`
  and, for literature rows, `source_url`.
- `habitat_requests.tsv`: one row per HTTP request (`purpose` = `database` or `literature_verification`): method,
  full URL, request body, HTTP status, ok, attempts, retrieval time, response SHA-256 and UniProt release header.
  Evidence, link and record rows reference requests by `request_key`. ENA portal HTTP 400 responses with an
  empty result for an accession query are recorded as `not_found`, not as failures.
- `habitat_coverage_summary.tsv`: section 11.
- `habitat_retrieval_manifest.json`: request counts by host/outcome, retrieval window, UniProt release headers,
  entity counts, literature file SHA-256, rule identifiers and SHA-256 of every output.
