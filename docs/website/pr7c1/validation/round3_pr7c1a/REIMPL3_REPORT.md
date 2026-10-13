# PR-7c.1a independent re-implementation validation (round 3)

Verdict: **PASS**. All classification and habitat columns match production on all 5,466 records. The
only differences are 3 serialization/ID cells, explained under Discrepancies; none affects a grade, flag,
value status, count or denominator.

## Method
- `reimpl3.py` was written from `habitat_field_dictionary_v3.md`. It starts from the round-2
  independent script (`reimpl2_prior_independent.py`) and adds the v3 changes:
  - physical roles (`env_broad_scale`, `env_local_scale`, `env_medium`, `isolation_source`) are separated
    from the host axis (`host`), giving `host_association_status`, `has_host_association` and
    `host_ambiguity_class`;
  - the `invalid_placeholder` status (`^0+(\.0+)?$`, MIxS env roles only, applied after `reported_missing`);
  - `ambiguity_class` (section 6, first match wins);
  - the new `not_reported_scope` values;
  - `pr7c1_grade`, recomputed with the legacy rules (host counted as habitat, `0` counted as usable,
    literature conflict against any usable value);
  - the new flags;
  - `field_original` as defined in section 3 (NCBI `name (harmonized: h)`, literal `sample_title`,
    `sample_description`, `package` and `organism`);
  - literature evidence rows (section 9);
  - `evidence_ids` = usable DB items in all 5 roles plus verified literature isolate items.
- Inputs: frozen `records.json`, `entities.json` and `literature_evidence.json`. Base and output directories
  come from arguments or `VAL_BASE`/`VAL_OUT`.
- `compare3.py` compares every shared column cell by cell (45 record-table columns × 5,466 records; 12
  evidence columns × shared evidence ids), then runs a residual analysis.
- `denominators3.py` uses its own pandas code on the production tables only. It recomputes the coverage
  summary rows, compares the table with the 39f5cad (PR-7c.1) table, and runs the spot checks.

## Independence statement
I did not open the production package (`tools/habitat_audit/` in the repository) and modified nothing in the repository.
No network was used. I read the production outputs only after `reimpl3.py` had produced its outputs.
After that, `reimpl3.py` was **not changed**; only the residual-analysis section of `compare3.py` was added.
One choice was not settled by the spec text: whether a literature conflict also sets the generic
`conflict` flag. I decided it before the comparison (yes, as in PR-7c.1), and it matches production.

## Record table (`habitat_record_availability.tsv`)
- 5,466/5,466 keys; 45 shared columns; 245,970 cells compared; **3 mismatching cells**, all in
  `evidence_ids` (A0A0M5L0M3, A0A0P6XBM7, A0A411LJN5). After mapping the differing literature IDs
  (Discrepancy 1), 0 remain.
- Every one of these columns has 0 mismatches:
  - grade and status columns: `primary_grade`, `pr7c1_grade`, `db_habitat_status`, `db_chain_status`,
    `literature_status`, `not_reported_scope`, `has_usable_habitat`, `mapping_confidence`;
  - host axis: `host_association_status`, `has_host_association`;
  - ambiguity and conflicts: `ambiguity_class`, `host_ambiguity_class`, `conflict_roles`, `conflict_scope`,
    `conflict_kind`, `chain_failures`;
  - all 15 `<role>_original/_normalized/_envo_ids` columns;
  - `country`, `lat_lon`, `lat`, `lon`, `collection_date`, `depth`, `habitat_nonstandard`, `sample_material`,
    `sample_type`, `molecule_types`, `biosamples`, `linkage_route`, `flags`.
- Production columns not derived here (identity, UniProt metadata and literature text columns) were not
  compared.

## Evidence table (`habitat_evidence.tsv`)
- 105,750 rows on both sides; 105,744 evidence ids shared. The 6 non-shared ids are literature `HL` ids
  (Discrepancy 1). All 91 literature rows match on (source_acc, field_original, value_original, role,
  value_status).
- `value_status`: **0 mismatches**; the distribution is identical for all 14 statuses, including
  `invalid_placeholder` = 12 (A0ABS3TAH3 and A0ABS3TE24: 3 env roles × ENA/NCBI each).
- Also 0 mismatches in `source_acc`, `evidence_source`, `link_index`, `field_original`, `role`,
  `value_original` and `value_normalized`.
- Remaining mismatches, all format-level:
  - `envo_ids`: 8 cells (Discrepancy 2);
  - `entity_accession` and `linkage_route`: 85 cells each, literature rows only (Discrepancy 3);
  - `mapping_confidence`: 29 cells, literature rows only (Discrepancy 3).

## Denominators (`habitat_coverage_summary.tsv`, unit=source_record, stratum=all)
- 63 in-scope rows: **63/63 match numerator, denominator and percent**. In scope: grade:*,
  usable_habitat_any_source, usable_field:<4 physical roles>, host_field:host, host_association:*,
  has_host_association, host_association_only, physical_habitat_and_host_association, ambiguity_class:*,
  host_ambiguity_class:*, not_reported_scope:*, pr7c1_grade_transition:* and every flag:*.
- No non-zero metric computed here is missing from the summary.
- Denominators are 5,466 for the record-level metrics, 59 for ambiguity_class, 84 for
  host_ambiguity_class and 2,831 for not_reported_scope.
- `physical_habitat_and_host_association` = 548 = `has_usable_habitat=1` AND `has_host_association=1`.
  The alternative definition, any usable physical value AND host, would give 569 because physical-AMBIGUOUS
  records with a host are excluded. The dictionary does not define this metric precisely (minor spec gap).
- `pr7c1_grade` equals the 39f5cad `primary_grade` for **5,466/5,466** records.
- Transitions:

  | Transition | Records |
  |---|---|
  | DS→DS | 2,460 |
  | DS→NR | 171 |
  | AMB→AMB | 59 |
  | AMB→DS | 63 |
  | AMB→NR | 15 |
  | NR→NR | 2,645 |
  | OCO→OCO | 36 |
  | VI→VI | 17 |

- 39f5cad vs current, changed columns (records). All are explained; 0 unexplained:

  | Column | Records | Explanation |
  |---|---|---|
  | `primary_grade`, `db_habitat_status` | 249 each | host separation: 171 DS→NR, 63 AMB→DS, 15 AMB→NR |
  | `has_usable_habitat` | 234 | 171 + 63 of the above |
  | `mapping_confidence` | 186 | records that became NR (171 + 15) |
  | `not_reported_scope` | 2,819 | 2,611 renamed `database_chain_only`→`database_only_literature_not_reviewed`; 22 →`database_only_literature_inaccessible`; 186 new NR after host separation (185 not_reviewed, 1 inaccessible) |
  | `env_{broad_scale,local_scale,medium}_{original,normalized}` | 2 each | the two zero-placeholder records (`0` → empty) |
  | `evidence_ids` | 2 | the same two records (6 zero items each removed) |
  | `flags` | 294 | see the flag changes below |

  Flag changes in the 294 records:
  - added: host_association_only 186, host_conflict 84, host_associated_isolation_source 42,
    host_tissue_isolation_source_only 23, literature_conflict 1, invalid_placeholder_value 2, and
    tissue_or_culture_only 134 (follows from the DS→NR grade change);
  - removed: `conflict` 78 (= 63 + 15 host-only conflicts).

  All other shared columns are unchanged: the `*_envo_ids` columns, isolation_source*, host*, the conflict_*
  columns and the identity columns.

## Spot checks
- (a) 186 records have a usable host and no usable physical value. All 186 carry `host_association_only`
  and are now NOT_REPORTED. Their 39f5cad grades: **171 DIRECT_SAMPLE** and 15 AMBIGUOUS. This matches the
  expected 186/171.
- (b) A0ABS3TAH3 and A0ABS3TE24: 6 zero items each are `invalid_placeholder` (env_broad_scale,
  env_local_scale and env_medium × ENA/NCBI) and are not listed in `evidence_ids`. `isolation_source = soil`
  stays usable from 3 sources. Grade is DIRECT_SAMPLE (pr7c1 DIRECT_SAMPLE) with flag
  `invalid_placeholder_value`. Each record also has 2 `depth = 0` items; these keep status `depth`, as the
  spec requires.
- (c) A0A6N7QP32: env_local_scale `00000316` (2 items) is still `usable`, the same as in 39f5cad.
  Grade is DIRECT_SAMPLE.
- (d) The 24 literature LOOKUP_FAILED records have 0 literature evidence rows, no HL id in `evidence_ids`,
  and empty literature text columns.
  - 23 are NOT_REPORTED with scope `database_only_literature_inaccessible`.
  - 1 (A0A977XLG0, isolation_source `freshwater`) is DIRECT_SAMPLE.
  - In 39f5cad: 22 had `database_chain_only` and 2 had no scope. One of these was DIRECT_SAMPLE via host and
    is now NR/inaccessible.
- (e) Ambiguity class distributions:

  | Axis | FORMATTING_ONLY | NESTED_WORDING | DISTINCT_SAME_SAMPLE | DISTINCT_ACROSS_SAMPLES | LITERATURE_VS_DATABASE |
  |---|---|---|---|---|---|
  | Physical AMBIGUOUS (n=59) | 9 | 20 | 19 | 10 | 1 |
  | Host AMBIGUOUS (n=84) | 1 | 23 | 60 | 0 | 0 |

  The raw values for 3 examples per class are in `denominators3.txt`, section C(e). My judgement of the
  examples:

  | Class (axis) | Examples (raw values) | Judgement |
  |---|---|---|
  | FORMATTING_ONLY (physical) | A0A133UED7/UK53/UKC1: "single cell amplified by MDA deep sea brine" vs "...MDA; deep sea brine" | Correct: punctuation only. |
  | NESTED_WORDING (physical) | A0A0H4J240: "...Red Sea at 20 m depth" vs "...Red Sea (Saudi Arabia) at 20 m depth"; A0A139X2U3: "a limestone cave" vs "Crystal Cave, a limestone cave"; A0A178F9M5: "hair" vs "human hair" | Correct. |
  | DISTINCT_SAME_SAMPLE (physical) | A0A021VMW3/VV84: "iron mining powder" vs "iron mine of Hongshan"; A0A178ZEC0: "spine of Smilax japicanga" vs "spine of Japecanga plant (Smilax species, Smilacaceae)" | Correct by rule: wording or synonym difference within one sample. Of all 19, 4 differ only by a typo ("amplfied", "Fryxel"; A0A9Q8TYU3, H2BR49, H2BW50, H2BW54), so they are formatting in substance. The rule has no fuzzy matching, which makes this a conservative label, not a spec deviation. |
  | DISTINCT_ACROSS_SAMPLES (physical) | B2D007: Baltic Sea vs Lake Kinneret vs Lake L658; B2D030/B2D032: "Lake Kinneret at 2m depth" vs "at 6m depth" | Correct by rule. Scientifically, 6 of the 10 differ only by depth or sea-ice layer within one water body (B2D030, B2D032, B2D036, B2D038, D2Y5H4, D2Y5K5). C0K2D9/C0K2E3 are two different lakes (Lake Erie vs Lake Superior). Only B2D007 (brackish Baltic vs freshwater lakes) and F6LYH6 (Lake Kinneret vs Ganges River) span habitat types. "Candidate genuine conflict" fits these; for the depth-only cases it overstates. |
  | LITERATURE_VS_DATABASE (physical) | A0A411LJN5: DB "International Space Station" vs literature isolate "KSC-PHSF a cleanroom floor" (marked inconsistent); a second isolate quote says ISS | Correct by rule. The item rests on the "paper about that strain" (Table 1) clause, which is the spec's acknowledged residual ambiguity. |
  | FORMATTING_ONLY (host) | A0ABR1H522: "Liriodendron tulipifera [tulip-poplar]" vs "Liriodendron tulipifera tulip-poplar" | Correct. |
  | NESTED_WORDING (host) | A0A0D2IC59/IWV0/KBA2: "Syagrus romanzoffiana" vs "Syagrus romanzoffiana (palm)" | Correct. |
  | DISTINCT_SAME_SAMPLE (host) | A0A0A2J7B6: "apple" vs "Malus domestica"; A0A0F8A5E4/A5R8: "soybean cyst nematode" vs "Heterodera glycines" | Correct by rule. These are common-name vs scientific-name synonyms, left unresolved because host taxonomy is not used (as the spec states). |

  No conflict was resolved.

## Discrepancies and classification
1. **Literature evidence_id when DOI is null.** 6 HL ids (4 isolate items, which cause the 3 record
   `evidence_ids` cells, and 2 organism items) differ.
   - Production hashes a null DOI as the string `None`, which is Python `str(None)`; my code used an empty
     string. With `None` serialization, all 6 production ids are reproduced exactly.
   - Otherwise the spec's literal reading matches production: hash of `pmid|doi|quote|scope` with the
     accession appended, no separator.
   - Classification: **spec ambiguity** (null serialization undefined). The `None` literal is a minor
     production wart. Cosmetic: the IDs are opaque and stable.
   - Suggested fix: state "null fields are written as `None`", or use empty strings.
2. **Per-item `envo_ids` order.** 8 cells in 4 records with two ENVO IDs. Production sorts IDs within an
   evidence item; my code kept the written order. They are equal after sorting.
   - Classification: **spec ambiguity** (sorting is defined for record cells only).
3. **Literature-row `entity_accession` (PMID), `linkage_route` (`literature`) and `mapping_confidence`
   (`LITERATURE` for isolate items).** Section 3/9 do not define these for literature rows; my code left them
   empty.
   - Classification: **spec gap**; production values are reasonable.
4. `physical_habitat_and_host_association` definition: see Denominators. **Minor spec gap**; production is
   self-consistent.

None of these are reimplementation logic errors or production deviations from a stated rule.
