# PR-7c.1 habitat field dictionary (revised by PR-7c.1a)

This document is the normative specification of the PR-7c.1 habitat metadata availability audit, as
corrected by PR-7c.1a (audit version 1.1.0). PR-7c.1a separates the **physical sampling habitat** (where
the sample was taken: `env_broad_scale`, `env_local_scale`, `env_medium`, `isolation_source`) from
**host association** (`host`), treats a bare `0` in the MIxS environment fields as an invalid placeholder,
classifies ambiguity, and distinguishes database-level absence from literature that was not reviewed or
was inaccessible. The PR-7c.1 grade is kept per record as `pr7c1_grade` (transition tables only).
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
| `DIRECT_SAMPLE` | At least one usable value in a **physical** habitat role (`env_broad_scale`, `env_local_scale`, `env_medium`, `isolation_source`), from an INSDC source feature or a BioSample linked to the record's own sequence/assembly, and no physical-role disagreement (section 6). A usable `host` alone never makes a record `DIRECT_SAMPLE`. |
| `VERIFIED_ISOLATE` | No usable physical database value; a parent-verified literature quote states where the same strain/isolate/clone was isolated. |
| `ORGANISM_CONTEXT_ONLY` | No usable database value and no isolate-level quote; a parent-verified quote describes the habitat of the species/organism in general. Not a sample habitat. |
| `AMBIGUOUS` | Usable values disagree within a physical habitat role (strict rule, section 6), or a verified literature isolate quote is marked inconsistent with the database value while a usable physical DB value exists. A disagreement in `host` only is reported on the host axis (`host_association_status = AMBIGUOUS`), not here. |
| `NOT_REPORTED` | The chain completed without failure and no usable physical habitat value exists (and no literature isolate/organism item applies). The record may still report a host (`host_association_only`). |
| `LOOKUP_FAILED` | At least one required lookup in the chain failed (network/HTTP error, unparseable response, ambiguous sample match). |
| `NOT_SEARCHED` | The record was not searched in this run (pilot mode only; the full run searched all 5,466 records). |

Grade precedence for one record (first match wins):
`LOOKUP_FAILED` > `AMBIGUOUS` > `DIRECT_SAMPLE` > `VERIFIED_ISOLATE` > `ORGANISM_CONTEXT_ONLY` > `NOT_REPORTED`.

`primary_grade` is the physical-habitat grade. `has_usable_habitat` = 1 iff grade is `DIRECT_SAMPLE` or
`VERIFIED_ISOLATE` (physical habitat only).

**Host-association axis** (PR-7c.1a; independent of `primary_grade`):
- `host_association_status`: `LOOKUP_FAILED` (any chain failure) > `AMBIGUOUS` (usable `host` values disagree,
  section 6) > `REPORTED` (at least one usable `host` value) > `NOT_REPORTED`; `NOT_SEARCHED` for unsearched records.
- `has_host_association` = 1 iff `host_association_status` is `REPORTED` or `AMBIGUOUS`.
- `host_ambiguity_class`: section 6, computed on `host` conflicts only (empty unless host `AMBIGUOUS`).
- Host taxonomy is not in the retrieval cache, so host names are **not** reconciled as synonyms; a host
  disagreement stays `AMBIGUOUS` with both raw values in `host_original`.

**Legacy grade** `pr7c1_grade`: the PR-7c.1 grade computed exactly as before (all five roles usable, `host`
counted as habitat, the `0` placeholder counted as usable, literature conflict against any usable value).
It equals the committed PR-7c.1 `primary_grade` for every record and is used only for transition tables.

Companion columns:
- `db_habitat_status`: the database-only physical grade (`LOOKUP_FAILED` > `AMBIGUOUS` (physical DB conflict only) > `DIRECT_SAMPLE` > `NOT_REPORTED`).
- `db_chain_status`: `INCOMPLETE` (any failure), `NO_LINK` (no link of any kind), else `COMPLETE`.
- `literature_status`: `NOT_SEARCHED` for records outside the literature subset (110 records = 107 characterized
  union 15 seeds); otherwise the final status in `literature_evidence.json` (section 9).
- `not_reported_scope` (only when grade is `NOT_REPORTED`; the database chain always completed without
  failure and gave no usable physical value):
  - `database_only_literature_not_reviewed`: `literature_status = NOT_SEARCHED` (record outside the 110-record
    literature subset; literature absence is **not** established);
  - `database_only_literature_inaccessible`: `literature_status = LOOKUP_FAILED` (literature reviewed but a
    source was inaccessible or the search was incomplete; absence **not** established; no annotation is added);
  - `database_and_literature`: `literature_status = NOT_REPORTED` (absent in both);
  - any other literature status `S`: `database_only_literature_<s>` (lower case; does not occur in this run).
  PR-7c.1 used `database_chain_only` for both of the first two cases.

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

`field_original` is written as follows: ENA BioSample attributes, the submitted tag unmodified; NCBI BioSample
attributes, the attribute `name` when it equals the `harmonized_name` (or no harmonized name exists), otherwise
`<name> (harmonized: <harmonized_name>)` (role mapping uses the harmonized name); the sample XML title and
description, the literal `sample_title` / `sample_description`; the NCBI package, the literal `package`;
INSDC source-feature columns, the ENA portal column name (e.g. `isolation_source`), and `organism` for the
`scientific_name` column; literature items, `literature:<scope> | <locator>`.

Source-feature columns that are empty (or `-`/absent in the ENA portal row) produce no item; every
non-empty column produces exactly one item (including literal values such as `0`, see section 5).
Each BioSample's items are attached once, to the first link (in `link_index` order) that lists it.
`entity_accession` is the BioSample for sample items, the protein id (CDS route) or parent accession
(sequence route) for source-feature items.

`evidence_id` = `"HE"` + first 12 hex of SHA-256 of
`source_acc|evidence_source|entity_accession|link_index|field_original|value_original`.
Literature: `"HL"` + 12 hex of SHA-256 of `pmid|doi|quote|scope` followed by the source accession.
Serialization rule (formal specification added in PR-7c.2; no identifier changed): each of `pmid`, `doi`,
`quote` and `scope` is rendered with Python `str()` of the stored value, so a null field (for example a missing
DOI) contributes the literal four characters `None`; the source accession follows `scope` with no separator. For
`"HE"` identifiers every field is the TSV string as written (an empty `link_index` or `value_original` contributes
the empty string). `tools/habitat_export/build.py` recomputes all 105,659 HE and 91 HL identifiers with these rules
and fails closed on any mismatch.

## 4. Roles (`normalize.ROLE_MAP`)

Tag key: remove characters outside printable ASCII, lower case, collapse runs of `_`, `-` and whitespace to one space.

**Value-checked habitat roles** (`HABITAT_ROLES`; section 5 applies to all five). Only the four
**physical** roles (`PHYSICAL_ROLES`: `env_broad_scale`, `env_local_scale`, `env_medium`, `isolation_source`)
can make a record `DIRECT_SAMPLE`; `host` (`HOST_ROLES`) is the host-association axis. The three MIxS
environment roles (`MIXS_ENV_ROLES`: `env_broad_scale`, `env_local_scale`, `env_medium`) are subject to the
zero-placeholder rule (section 5).

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
| `sample_title`, `sample_description` | the `<TITLE>`/`<DESCRIPTION>` elements of the ENA and NCBI sample XML only (attributes tagged e.g. `title` or `description` are not mapped and produce no item) | `context` |

Roles `habitat_nonstandard`, `sample_material`, `country`, `lat_lon`/`lat`/`lon`, `collection_date` and `depth`
with a missing value (section 5) get `reported_missing` instead. The `context` roles (`host_detail`,
identity/type roles and `sample_title`/`sample_description`) always keep `context`, even when the value is a
missing-value token; they never affect grades, and `sample_type` (section 7) excludes missing strains itself.
Tags that map to no role are not recorded as evidence (they appear only in the attribute inventory).

## 5. Value status of habitat-role items

Applied in this order (first match wins):

1. `reported_missing`: normalized value empty or matching (case-insensitive; `.` and `?` are literal characters)
   `^(missing|not collected|not applicable|not provided|not available|not determined|restricted access|unknown|unspecified|na|n/a|n\.a\.|none|null|nan|-|--|\.|\?)(\s*[:;,(].*)?$`.
   The list is literal: other placeholder-like tokens (e.g. `0`, `no`) are not missing and are evaluated by the
   following rules.
2. `invalid_placeholder` (PR-7c.1a; roles `env_broad_scale`, `env_local_scale`, `env_medium` only): the
   normalized value fully matches `^0+(\.0+)?$` (e.g. `0`, `00`, `0.0`). Sets flag `invalid_placeholder_value`.
   The value is kept in the evidence table (provenance) but is not usable. ENVO-like digit strings such as
   `00000316` do not match and are unchanged; the rule is not applied to `isolation_source` or `host`.
   In the full run exactly 12 items match (A0ABS3TAH3 and A0ABS3TE24: env_broad_scale, env_local_scale and
   env_medium `0`, each in the ENA and NCBI copy of the BioSample); both records keep their usable
   `isolation_source = soil` and stay `DIRECT_SAMPLE`.
3. `host_is_self` (role `host` only): the host equals the record's own organism: the host taxid equals the
   record taxid; or the normalized host equals a normalized organism name (UniProt organism, DB organism,
   source-feature `scientific_name`); or, for non-viral organisms only, the first two words match a
   two-word organism binomial that does not end with `sp`/`sp.`. Sets flag `host_is_self_ignored`.
4. `uninformative_placeholder`: all explicit ENVO IDs are root/placeholder classes
   (ENVO:00010483, 00000428, 01000254, 00002297, 01001110, 00002036, 01000813), or the value with ENVO IDs
   removed is one of: environmental material, environment material, biome, environmental feature,
   environment, environmental system, environmental sample, other, sample.
5. `moved_to_material` (culture): the normalized value, with one trailing `.` removed, fully matches
   (case-insensitive) any of these alternatives (`normalize.CULTURE_RE`):
   - `(axenic |pure |unialgal |clonal |laboratory |lab |cell |stock |batch |continuous )?cultures?`
   - `culture collection`; `strain collection`; `laboratory`; `cultured cells`
   - `(laboratory|lab) (strain|stock|isolate)s?`; `(cell|tissue) lines?`; `(viral )?plaques?`
   - any value containing the word `agar` or `broth`
   - any value ending in the words `culture media`, `growth media` or `isolation media` (regex
     `\b(culture|growth|isolation) media?$`; the plural form only; `medium` is NOT covered by this alternative)
   - a whole value of one token `[a-z0-9][a-z0-9-+]*` followed by ` medium` (e.g. `bg-11 medium`,
     `culture medium`); multi-word prefixes such as `liquid culture medium` are not matched.
   A culture mentioned inside a longer habitat description (e.g. "enrichment culture from lake sediment")
   is not matched.
6. `moved_to_material` (tissue; role `isolation_source` only): the normalized value, with one trailing `.`
   removed, equals one of exactly these terms (`normalize.TISSUE_TERMS`): leaf, leaves, root, roots, stem, stems,
   shoot, shoots, flower, flowers, seed, seeds, fruit, fruiting body, fruiting bodies, mycelium, mycelia, hyphae,
   spores, conidia, whole organism, whole body, whole plant, whole cell, whole cells, cells, cell, tissue,
   thallus, sporophyte, gametophyte, protonema, rhizoid, blade, frond; unless the same sample entity also
   reports a non-self host (then the tissue is a host-associated isolation source and stays usable as a
   physical value; flag `host_associated_isolation_source`, and `host_tissue_isolation_source_only` when such
   tissue terms are the record's only usable physical values, as a sensitivity marker).
   The tissue rule does not apply to `env_broad_scale`, `env_local_scale` or `env_medium` (e.g. env_medium
   `leaf` stays usable).
7. `usable`.

`moved_to_material` and `material` values are listed in `sample_material`; when such a value exists and the
physical grade is not `DIRECT_SAMPLE`/`AMBIGUOUS`, flag `tissue_or_culture_only` is set.

**ENVO IDs**: only IDs written in the value (`ENVO[:_ ]?\d{7,8}`, zero-padded to 8). Each is checked in OLS:
`not_found` sets `envo_id_invalid` and the ID is dropped from the item; `failed` sets `envo_lookup_failed`
(not a grade failure; the ID is dropped). The text value itself is kept.

`value_normalized` = lower case, leading/trailing whitespace removed, internal whitespace collapsed to one space.

## 6. Agreement rule and conflicts

Within each of the five habitat roles, usable items are grouped by union-find: two items agree when their
`value_normalized` strings are equal, or both have the same non-empty explicit ENVO-ID set. More than one group
in a role is a conflict, listed in `conflict_roles` (raw observation over all five roles, with `conflict_scope`
and `conflict_kind`). A conflict in a **physical** role makes the grade `AMBIGUOUS` (flag `conflict`); a
conflict in `host` makes `host_association_status = AMBIGUOUS` (flag `host_conflict`) and does not change the
physical grade. Roles are evaluated independently (an `isolation_source` and an `env_medium` value never
conflict). No conflicting value is ever chosen, merged or dropped: all distinct usable values stay in the
`<role>_original` cell joined by ` || `.

Descriptive diagnostics (never change the grade):
- `conflict_kind` per role: `punctuation_only` (groups identical after replacing non-alphanumerics with spaces),
  `token_subset` (one group's word set contains every other group's words), else `distinct_values`.
- `conflict_scope` per role: `within_sample_unit` when all disagreeing items belong to one sample unit
  (a source-feature item belongs to its link's BioSample when the link has exactly one), else `across_sample_units`.

**Ambiguity interpretation** (PR-7c.1a; descriptive, never resolves a value). `ambiguity_class` (physical
axis, set iff grade `AMBIGUOUS`) and `host_ambiguity_class` (host axis, set iff host `AMBIGUOUS`) are computed
from that axis's conflicting roles, first match wins:
1. `LITERATURE_VS_DATABASE`: no database-internal conflict on the axis; a verified isolate literature item is
   `inconsistent` with the database (physical axis only; flag `literature_conflict`).
2. `FORMATTING_ONLY`: every conflicting role is `punctuation_only` (case and whitespace are already ignored by
   the agreement rule, so the values differ only in punctuation/separators).
3. `NESTED_WORDING`: every conflicting role is `punctuation_only` or `token_subset` (one value's words contain
   the other's, e.g. `sediment` vs `lake sediment`).
4. `DISTINCT_SAME_SAMPLE`: some role is `distinct_values`, and every `distinct_values` role is
   `within_sample_unit`: different wording inside one sample unit (e.g. ENA vs NCBI copy, or source feature vs
   its BioSample). This may be a synonym or a submitter inconsistency; it is **not** resolved, because no
   synonym resource is applied.
5. `DISTINCT_ACROSS_SAMPLES`: some `distinct_values` role spans more than one sample unit: a genuine
   environmental-conflict candidate (e.g. the same protein sequenced from different samples).
Classes 2-3 are formatting differences; 4 is unresolved wording or synonym difference; 5 (and 1) are
candidate genuine conflicts. The grade stays `AMBIGUOUS` for every class.

`multi_sample` (DIRECT_SAMPLE only): more than one evidence unit, where units are the record's BioSamples plus
each CDS/sequence/UniParc link that has no BioSample.

Other flags: `geo_discordant` / `date_discordant` when more than one distinct country / collection date exists
after light normalization (whitespace around `:`,`,`,`;` removed; `DD-Mon-YYYY` and `Mon-YYYY` dates converted
to ISO); `free_text_context_only` when the record has no usable item in any of the five habitat roles
(including `host`; meaning unchanged from PR-7c.1; database chain only) but at least one
non-empty `sample_title` or `sample_description` item exists;
`habitat_reported_missing` when a habitat role carries a missing-value token; `invalid_placeholder_value`
(section 5); `host_association_only` when the record has a usable `host` and no usable physical value;
`host_conflict`, `literature_conflict` (above); `engineered_record`.

## 7. Sample type (`sample_type`, explicit fields only)

First match: `MAG` (package/checklist contains mimag, ERC000047 or metagenome-assembled); `SAG` (misag, ERC000048);
`METAGENOME_ASSEMBLY` (mims, organism/metagenome_source containing "metagenome", or the word metagenome in the
package); `ENVIRONMENTAL_CLONE` (environmental_sample = true); `ISOLATE_GENOME` (package contains migs.ba, migs.eu,
microbe or pathogen, or a non-missing strain with environmental_sample = false); `TRANSCRIPTOME` (all molecule
types mRNA/transcribed RNA); else `UNKNOWN`.

## 8. Record-table cells

Multiple distinct values in one cell are sorted and joined by ` || `; ID lists by `;`.
Habitat columns (`<role>_original`, `<role>_normalized`, `<role>_envo_ids`) contain usable values only; the
`host_*` columns are the host-association values (not physical habitat).
`habitat_nonstandard` lists each distinct `nonstandard_context` item as `<field_original>: <value_original>`
(the submitted tag, unmodified, then a colon and a space); `sample_material` lists the distinct `value_original`
of `material` and `moved_to_material` items.
`mapping_confidence` (physical axis): DIRECT_SAMPLE = HIGH if any usable physical item is HIGH else MEDIUM;
VERIFIED_ISOLATE = LITERATURE; AMBIGUOUS = HIGH/MEDIUM by the same rule, or LITERATURE when only a literature
conflict exists; otherwise empty.
`evidence_ids`: every `usable` database item (all five roles, so host evidence stays traceable) plus verified
literature isolate items; `invalid_placeholder` items are not listed.
New PR-7c.1a columns: `ambiguity_class`, `host_association_status`, `has_host_association`,
`host_ambiguity_class`, `pr7c1_grade` (section 1 and 6).

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
  The "paper about that strain" clause is a reviewer judgement and is the one residual ambiguity of this
  section. 30 of the 33 isolate items name the record's designation inside the quote (which may span
  consecutive sentences, e.g. F2TZN0 / ATCC 50818). Three were accepted through the clause: H2BW50 ("The strain
  was isolated from a microbial mat in Lake Fryxell", in the genome announcement of type strain R-8282T) and two
  A0A411LJN5 items (strain FKI-L5-BR-P1 identified through Table 1 of the paper). Conversely, Q5V0R5/Q5V4H7
  ("a halophilic archaeal isolate from the Dead Sea", genome paper of the sequenced organism) were scoped
  `organism` by the reviewer because no designation is given; the live spot-check judged both readings
  defensible. Per-item decisions are listed in `literature_parent_verification.tsv` (`strain_named`).
- `literature_status`: `ISOLATE_EVIDENCE` > `ORGANISM_CONTEXT` > `LOOKUP_FAILED` (any source not accessible, or
  the reviewer could not complete the search) > `NOT_REPORTED`.
- Consistency between a literature isolate quote and the DB value is a reviewer semantic judgement
  (`consistent`, `inconsistent` only for a genuine contradiction, `not_applicable`), because prose has no
  normalized form. This is a deliberate deviation from the strict string rule of section 6. An `inconsistent`
  verified isolate item makes the record `AMBIGUOUS` only when the record also has a usable physical DB value
  (PR-7c.1a; a usable `host` alone is not a habitat the literature can contradict).
- The 24 records with `literature_status = LOOKUP_FAILED` keep that status and carry no literature item;
  no annotation is invented for them (23 are `NOT_REPORTED` with scope `database_only_literature_inaccessible`,
  1 is `DIRECT_SAMPLE` from its database value).
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

Metrics: `grade:<G>` (physical grade); `usable_habitat_any_source` and `_of_searched` (physical habitat);
`usable_field:<role>` (four physical roles only); `host_field:host`;
`reported_field:<habitat_nonstandard|country|collection_date|lat_lon|sample_material>`; `funnel:<stage>`;
`flag:<flag>`; `literature_status:<S>`; `ambiguous_role_conflict_scope:<scope>` and
`ambiguous_role_conflict_kind:<kind>` (denominator = conflicting role instances);
`ambiguous_all_roles_punctuation_only`; `ambiguous_all_roles_within_sample_unit`;
`not_reported_with_nonstandard_habitat_tag`; `mrdb_mixed_source_grades`; `mrdb_multiple_source_records`.
The `ambiguous_role_*` and `ambiguous_all_roles_*` diagnostics count physical roles of physical-`AMBIGUOUS`
records only.

PR-7c.1a metrics (source_record unit): `host_association:<status>` (denominator = records in the stratum),
`has_host_association`, `host_association_only` (flag of that name), `physical_habitat_and_host_association`
(`has_usable_habitat = 1` and `has_host_association = 1`, so VERIFIED_ISOLATE counts and physical-`AMBIGUOUS`
does not);
(stratum `all` only) `ambiguity_class:<C>` (denominator = physical `AMBIGUOUS` records),
`host_ambiguity_class:<C>` (denominator = host `AMBIGUOUS` records), `not_reported_scope:<S>`
(denominator = `NOT_REPORTED` records), `pr7c1_grade_transition:<old>-><new>` (denominator = all records).

Funnel stages (monotone): `searched` -> `insdc_link_found` (no `no_insdc_link`) -> `insdc_record_resolved`
(no `insdc_record_unresolved` and no coding/sequence/UniParc/proteome failure) -> `habitat_field_present`
(any DB physical-role item) -> `informative_habitat_value` (any physical-role item that is not
`reported_missing`/`uninformative_placeholder`/`invalid_placeholder`) -> `direct_sample`. (PR-7c.1 counted
`host` items in the funnel.)

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

**Generated-file whitespace.** TSV rows whose last column is empty end with a tab: this is a structural empty
field, not trailing whitespace, and is declared with `*.tsv -whitespace` in `.gitattributes`. SVG figures
are written with trailing whitespace stripped per line (matplotlib emits path data such as `M 0 0 `); geometry
and text are unchanged.

**Paths.** No absolute machine path is used. The cache defaults to `<repo>/work/habitat_cache` (override with
`MRDB_HABITAT_CACHE` or `--cache`); the work directory to `<repo>/work/pr7c1_work` (`MRDB_HABITAT_WORK` or
`--work`). `work/` is gitignored. Offline replay: `python -m tools.habitat_audit.run full --offline
[--cache DIR] --out DIR`.
