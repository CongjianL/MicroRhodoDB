# PR-7c.1 habitat audit: round-2 independent re-implementation

The re-implementation was derived only from `round2/habitat_field_dictionary_v2.md`. No production code was read.
Production files compared: `round2/habitat_record_availability.tsv` and `round2/habitat_evidence.tsv`.

## Spec edits applied (reimpl.py -> reimpl2.py)

| # | Change | Dictionary v2 section |
|---|---|---|
| 1 | Removed the round-1 sensitivity mode (`REIMPL_SENSITIVITY`) entirely. Spec-literal is now the only mode. | n/a |
| 2 | Missing-value regex is copied verbatim from v2, with `n\.a\.`, `\.` and `\?` as literals. Behaviour is unchanged from the round-1 assumption. | §5.1 |
| 3 | Culture rule rewritten as one full-match regex built from the v2 alternatives, applied after removing one trailing `.`. The alternatives cover axenic/pure/unialgal/clonal/laboratory/lab/cell/stock/batch/continuous culture(s), culture collection, **strain collection**, laboratory, cultured cells, lab/laboratory strain/stock/isolate(s), cell/tissue line(s), **(viral )?plaque(s)**, words agar/broth, `.*\b(culture\|growth\|isolation) media?$`, and a single token followed by ` medium`. Round 1 used substring matching for "culture collection" and accepted any multi-word "<x> medium". Both are now full-match as specified. | §5.4 |
| 4 | Tissue rule uses the exact closed list, including **fruiting body/bodies**, shoot, flower, seed, fruit, hyphae, conidia, whole body/plant/cell(s), tissue, sporophyte, gametophyte, protonema, rhizoid, blade and frond (round 1 also had `spore`, which v2 does not list). It is applied with one trailing `.` removed, rather than round 1's `strip(" .;,")`. Scope is `isolation_source` only, with the non-self-host exception per entity. | §5.5 |
| 5 | Source-feature columns that are empty, `-` or absent produce no item. Round 1 skipped empty columns only. | §3 |
| 6 | `free_text_context_only` is set when there is no usable DB habitat-role item and at least one **non-empty** `sample_title`/`sample_description` item exists. Round 1 required a status other than `reported_missing`. | §6 |
| 7 | `habitat_nonstandard` cell = distinct `<field_original>: <value_original>` of the `nonstandard_context` items, joined by ` \|\| `. | §8 |
| 8 | `sample_material` = distinct `value_original` of the `material` and `moved_to_material` items. This was already implemented and is unchanged. | §8 |
| 9 | AMBIGUOUS `mapping_confidence` = LITERATURE when only a literature conflict exists (no DB conflict), else HIGH/MEDIUM. This is the round-1 spec-literal rule, now without the sensitivity override. | §8 (D5) |

`compare2.py` reads production from `round2/`. It compares the same 39 columns as `compare.py`, lists every
mismatching cell, and adds an evidence-row check.

## Record-table result (5,466 records x 39 columns)

All 39 columns match on 5,466/5,466 records. There are 0 mismatching records and 0 mismatching columns.
The round-1 discrepancy classes are closed:
- **D1** ("Strain collection"): fixed by §5.4.
- **D2** (fruiting body): fixed by §5.5.
- **D3** (viral plaque): fixed by §5.4.
- **D4** (habitat_nonstandard format): fixed by §8.
- **D5** (A0A411LJN5 mapping_confidence): production now gives LITERATURE, matching §8.

**Verdict: EXACT_MATCH** (record table).

## Evidence-row check (database items; literature rows were not re-implemented)

- **Row counts:** production has 105,659 DB rows and the reimpl has 105,662.
- **Matching method:** `evidence_id` agrees for 79,819 rows. It differs elsewhere only because `field_original` is presented differently (see E1). Rows were therefore matched on the content key (source_acc, evidence_source, entity_accession, link_index, role, value_original).
- **Content-key multiset:** 0 rows are production-only and 3 rows are reimpl-only (E2).
- **value_status:** 159 differences among the 104,053 content-unique rows (263 by evidence_id), all from E3. value_normalized, envo_ids and mapping_confidence match 100%.
- **Record table:** none of E1-E3 changes it. They are evidence-table or spec-wording issues only.

## Remaining spec ambiguities (evidence table only)

- **E1: `field_original` presentation is unspecified (§3/§4), so `evidence_id` (§3) cannot be reproduced from the spec.**
  Production writes:
  - `sample_title`, `sample_description` and `package` for the XML title, description and NCBI package;
  - `<name> (harmonized: <harmonized_name>)` for NCBI attributes that have a harmonized name (4,859 rows);
  - `organism` for the source-feature `scientific_name`.

  The reimpl used the raw tag or harmonized name. The `organism`/`scientific_name`, `host_description`/`host_tissue_sampled` and `tissue`/`dev_stage` swaps in `compare2.txt` are cross-product artifacts of the content-key merge, where one entity has the same value under two tags. They are not real disagreements.

  This also creates a latent risk for §8 `habitat_nonstandard`. If an NCBI nonstandard tag ever had a harmonized name, it is unclear whether "the submitted tag, unmodified" means the raw name or the production field_original. No case occurs in this run.
- **E2: Attribute-level `sample title` / `sample description` tags (§4 "sample title/description").**
  Production builds these roles only from the XML title/description fields. A BioSample attribute tagged `sample title` or `Sample Description` is not mapped. This accounts for the 3 reimpl-only rows: A0A2T1DCP3/SAMN08617406 (ENA and NCBI) and A0ABM9RL04/SAMEA1572090 (an empty value). The spec does not say whether these tags are mapped.
- **E3: Missing-value status of `context` roles (§4).**
  The §4 text says "Any of these with a missing value (section 5) gets `reported_missing` instead". Production applies this to geography, date, depth, material and nonstandard roles. It never applies it to `context` roles: strain, isolate, host_detail and investigation_type with values such as `missing`/`not applicable`/`n/a`/empty stay `context`. That is 159 content-unique rows (263 by evidence_id).

  This is a production-vs-spec deviation, or a spec wording gap. Either the spec should exempt `context` roles, or production should mark these items `reported_missing`.

  It does not affect the record table. §7 "non-missing strain" gives the same sample_type in all 5,466 records either way.
- **Minor: regex `media?` in §5.4** also matches "...culture medi" (singular `medium` is excluded, as intended). This is harmless; no value is affected.
