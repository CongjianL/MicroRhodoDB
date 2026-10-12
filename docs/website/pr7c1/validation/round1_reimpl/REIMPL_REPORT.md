# PR-7c.1 habitat grading — independent re-implementation report

**Verdict: MISMATCH.** 5,462/5,466 records match on `primary_grade`. All remaining differences fall into
5 discrepancy classes. Four are spec omissions or ambiguities, class (b). One is an apparent production
deviation from the literal spec text, class (c). No implementation bugs (a) remain. With those 5 conventions
switched on in a separate diagnostic run, all 39 compared columns match for all 5,466 records. That run is
not the deliverable.

## Method

- `reimpl.py` was written from `habitat_field_dictionary.md` only. No production code or tests were read.
  It takes these inputs: `records.json`, `entities.json` and `literature_evidence.json`. Production output was
  used only in `compare.py`, after classification.
- Per record, the script does the following:
  - **Links (§2):** builds the UniProt EMBL and UniParc links, sorted by `(protein_id, parent_accession)`.
  - **Resolution chain:** CDS, then parent sequence, then WGS set, then INSDC flat file. Unresolved links get
    `embl_xref_unresolved`. Entries with no EMBL link use the proteome-assembly fallback.
  - **Samples:** collects samples from the ENA row, the flat file and proteome BioSamples. It reads ENA and
    NCBI BioSample copies and records failures.
  - **Evidence items (§3):** creates source-feature items and ENA/NCBI attribute items. Each BioSample is
    attached once, to its first link.
  - **Roles (§4):** maps tags with the specified tag-key normalization.
  - **Value status (§5):** applies missing, host_is_self, placeholder, culture, then tissue (with the
    same-entity non-self-host exception).
  - **ENVO:** checks IDs against `entities.envo`. Invalid IDs are dropped and set `envo_id_invalid`.
  - **Agreement (§6):** union-find on equal `value_normalized` or an equal non-empty ENVO set, per role. It
    derives `conflict_kind` (punctuation_only, then token_subset, then distinct_values) and `conflict_scope`.
    A source-feature item belongs to the BioSample of its link when the link has exactly one.
  - **Flags:** multi_sample, geo/date discordance, free_text_context_only, habitat_reported_missing,
    tissue_or_culture_only and engineered_record.
  - **Sample type (§7).**
  - **Literature (§9):** parent_verified isolate/organism items, plus an `inconsistent` isolate item when a
    usable DB value exists.
  - **Grade precedence and companion columns (§1), and mapping_confidence (§8).**
- `compare.py` compares cells. List cells are compared as sets: on `;` for ID/flag/role lists and on ` || `
  for value cells. Exact raw-string equality was also checked. For the list columns it gives the same counts,
  including role order `isolation_source;host`.
- Runtime is about 20 s. In this full run there were no lookup failures, so the LOOKUP_FAILED/INCOMPLETE branches
  are implemented but were never exercised.

## Final per-column agreement (spec-literal implementation, `reimpl_records.tsv`)

| column | match / 5466 |
|---|---|
| `primary_grade` | 5462/5466 |
| `db_habitat_status` | 5462/5466 |
| `db_chain_status` | 5466/5466 |
| `literature_status` | 5466/5466 |
| `not_reported_scope` | 5462/5466 |
| `has_usable_habitat` | 5462/5466 |
| `conflict_roles` | 5466/5466 |
| `conflict_scope` | 5466/5466 |
| `conflict_kind` | 5466/5466 |
| `linkage_route` | 5466/5466 |
| `mapping_confidence` | 5461/5466 |
| `sample_type` | 5466/5466 |
| `flags` | 5462/5466 |
| `env_broad_scale_normalized` | 5462/5466 |
| `env_local_scale_normalized` | 5462/5466 |
| `env_medium_normalized` | 5466/5466 |
| `isolation_source_normalized` | 5462/5466 |
| `host_normalized` | 5466/5466 |
| `sample_material` | 5458/5466 |
| `habitat_nonstandard` | 5426/5466 |
| `biosamples` | 5466/5466 |
| `chain_failures` | 5466/5466 |
| `env_broad_scale_original` | 5462/5466 |
| `env_local_scale_original` | 5462/5466 |
| `env_medium_original` | 5466/5466 |
| `isolation_source_original` | 5462/5466 |
| `host_original` | 5466/5466 |
| `env_broad_scale_envo_ids` | 5466/5466 |
| `env_local_scale_envo_ids` | 5466/5466 |
| `env_medium_envo_ids` | 5466/5466 |
| `isolation_source_envo_ids` | 5466/5466 |
| `host_envo_ids` | 5466/5466 |
| `country` | 5466/5466 |
| `lat_lon` | 5466/5466 |
| `lat` | 5466/5466 |
| `lon` | 5466/5466 |
| `collection_date` | 5466/5466 |
| `depth` | 5466/5466 |
| `molecule_types` | 5466/5466 |

Columns 1–21 are the required list; the rest are additional columns that were also compared.
The diagnostic run (`REIMPL_SENSITIVITY=1`, `reimpl_records_sensitivity.tsv`) gives 5466/5466 for every column (see `compare_sensitivity.txt`).

## Grade confusion matrix (rows = production, columns = reimpl)

| production \ reimpl | AMBIGUOUS | DIRECT_SAMPLE | NOT_REPORTED | ORGANISM_CONTEXT_ONLY | VERIFIED_ISOLATE |
|:--|--:|--:|--:|--:|--:|
| AMBIGUOUS | 137 | 0 | 0 | 0 | 0 |
| DIRECT_SAMPLE | 0 | 2631 | 0 | 0 | 0 |
| NOT_REPORTED | 0 | **4** | 2641 | 0 | 0 |
| ORGANISM_CONTEXT_ONLY | 0 | 0 | 0 | 36 | 0 |
| VERIFIED_ISOLATE | 0 | 0 | 0 | 0 | 17 |

## Remaining discrepancy classes

### D1 (b): "Strain collection" counted as a culture description. 4 records
Examples: A0AAW0FFT2, A0AAW0GV67, A0AAW0GVD9 (also A0AAW0GVT7).

- **Evidence:** BioSample SAMN34136931 has `env_broad_scale` = `env_local_scale` = "Strain collection" in both
  ENA and NCBI. Every other habitat attribute is `missing`.
- **Spec §5.4:** "the whole value is a culture/laboratory description (axenic/pure/lab ... culture, culture
  collection, laboratory strain, cell line, plaque, anything containing "agar"/"broth", "<x> medium",
  "culture/growth/isolation media")".
- **Ambiguity:** "strain collection" is not in the list. Production treats it as `moved_to_material`. The
  reimpl, following the literal list, keeps it usable.
- **Production result:** grade NOT_REPORTED, `sample_material` = "Strain collection", flags
  `free_text_context_only` and `tissue_or_culture_only`, empty env columns and mapping_confidence.
- **Reimpl result:** DIRECT_SAMPLE, HIGH.
- **Columns affected:** primary_grade, db_habitat_status, has_usable_habitat, not_reported_scope,
  mapping_confidence, flags, env_broad_scale_*, env_local_scale_*, sample_material.

### D2 (b): "fruiting body/bodies" in the tissue list. 3 records
Examples: A0A232LUP6, A0A317SUC3, A0ACC0U1V3.

- **Spec §5.5:** "a tissue/organism-part term (leaf, root, stem, mycelium, spores, thallus, whole organism,
  cells, ...)".
- **Ambiguity:** the list is open-ended. Production includes "fruiting body"/"fruiting bodies", and these
  records have no host. The value moves from `isolation_source` to `sample_material`.
- **Grade:** unchanged (DIRECT_SAMPLE from env_* values).
- **Columns affected:** isolation_source_original/normalized and sample_material.

### D3 (b): "viral plaque" counted as a culture. 1 record
Example: M1HVR3.

- **Evidence:** BioSample SAMN42953864 has `isolation_source` = "viral plaque".
- **Spec:** lists the whole value "plaque" and says "A culture mentioned inside a longer habitat description is
  not matched". Production also matches "viral plaque".
- **Grade:** unchanged (usable source-feature host "Micractinium conductrix").
- **Columns affected:** isolation_source_*, sample_material.

### D4 (b): `habitat_nonstandard` cell format. 40 records
Examples: A0AAI8YRG3 (prod "habitat: Pine tree forest" vs reimpl "Pine tree forest"), A0ABP1D9G7, A0A7U4E450.

- **Spec §8:** "Multiple distinct values in one cell are sorted and joined by ` || `". It does not say that
  the source tag is included.
- **Production:** writes `<field_original>: <value_original>`, so ENA "Isolation Site" and NCBI "isolation
  site" give two entries. When rebuilt in that form from the reimpl evidence items, all 40 match exactly.
- **Effect:** no grade effect.

### D5 (c, or a spec wording error): mapping_confidence for a literature-only conflict. 1 record
Example: A0A411LJN5.

- **Evidence:** the DB is consistent (production `conflict_roles` is empty, db_habitat_status DIRECT_SAMPLE,
  isolation_source "International Space Station"). The verified literature isolate item ("cleanroom floor") is
  `consistent_with_db = inconsistent`, which makes the grade AMBIGUOUS.
- **Spec §8:** "AMBIGUOUS = HIGH/MEDIUM by the same rule, or LITERATURE when only a literature conflict exists".
- **Reimpl:** LITERATURE.
- **Production:** HIGH.
- **Why the production reading looks wrong:** §9 says a literature conflict can only cause AMBIGUOUS when a
  usable DB value exists. If HIGH/MEDIUM applied whenever usable DB items exist, the LITERATURE branch could
  never be reached.
- **Effect:** no grade effect. The fix is either code or spec wording.

## Spec ambiguities and assumptions

These are assumptions the reimpl made. "Matches production" means the reimpl and production agree on every record.

1. **Missing-value regex (§5.1).** It contains unescaped `.` and `?` and cannot be taken literally (`?` alone is
   invalid, and `.` would match any single character). Assumed literal tokens ('.', '?', 'n.a.'). This
   discriminates: 12 env_broad_scale items "0" (A0ABS3TAH3, A0ABS3TE24) stay usable. Matches production.
2. **Empty source-feature columns** in the ENA coding row are treated as absent qualifiers, not
   `reported_missing` items. Otherwise almost every record would get `habitat_reported_missing`. Matches production.
3. **Empty BioSample attribute values** (77 ENA) become `reported_missing` items ("each attribute becomes one
   evidence item"). Matches production.
4. **`sample_title`/`sample_description` tags.** The spec says "sample title/description". Mapped the tags
   "sample title"/"sample description" and the ENA/NCBI `title`/`description` fields. Matches production.
5. **`free_text_context_only` "no usable value"** read as no usable *database* habitat value. This
   discriminates: 38 VERIFIED_ISOLATE/ORGANISM_CONTEXT_ONLY records carry the flag in production. Matches production.
6. **`habitat_reported_missing`** read as any of the 5 usable habitat roles with value_status
   `reported_missing` (empty values included). Matches production.
7. **environmental_sample values** 'TRUE'/'1'/'No' are read as true/false (true/yes/1, false/no/0). Not
   discriminating in this run (CDS rows give the same answer).
8. **"Same sample entity" for the tissue exception** taken as the same `entity_accession` (ENA and NCBI copies
   of one BioSample, or one protein id for source-feature items). Exercised for 87 items (e.g. A0A2G7FQV6
   "leaf"). Matches production.
9. **host_is_self taxid rule.** Interpreted as the host value equal to the record taxid, or a `host taxid`
   attribute in the same entity equal to it. Viral status taken from UniProt lineage[0] == "Viruses". Never
   triggered (0 records in both).
10. **Culture regex details** (word-boundary agar/broth, "<x> medium" as a value ending in " medium") and the
    open tissue list are a judgement call. D1–D3 are where they differ from production.
11. **`conflict_scope`** "disagreeing items" taken as all usable items of the conflicting role. **`conflict_kind`**
    word set of a group taken as the union over its items. Role order follows the §4 table. Matches production.
12. **When UniParc is queried** is not specified. Used whatever UniParc entry is present. The proteome route is
    used only when there are no EMBL or UniParc links. Matches production.
13. **ENVO IDs** were checked for habitat roles and habitat_nonstandard. A placeholder test uses the IDs that
    remain after invalid ones are dropped. Matches production.
14. **Not exercised in this run:** chain failures (no `failed` statuses in entities.json), `sample_unresolvable`,
    `cds_multiple_rows`, `embl_xref_unresolved`, `wgs_set` found, the assembly fallback and `envo_lookup_failed`.
    These are implemented as specified but not validated.

Verdict: **MISMATCH**. 4 primary_grade differences (D1, class b). Remaining column mismatches come from D1–D4
(class b) and D5 (class c). There are no unresolved implementation bugs, and every residual is explained (the
sensitivity run gives an exact match on all columns).
