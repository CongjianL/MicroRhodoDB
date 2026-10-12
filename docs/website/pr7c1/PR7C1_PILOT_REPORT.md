# PR-7c.1 Pilot report (stratified 122-record pilot)

Audit: PR-7c.1 Habitat Metadata Availability Audit, tool version 1.0.0.
Base commit: 932eb567a199f9eef25f7e04ac2aaa745e17156c. Frozen database SHA-256 unchanged.
UniProt release served during retrieval: 2026_03.

The pilot was run before the full retrieval to exercise every route of the source chain
on a deliberately heterogeneous sample, hand-trace each record against the raw cached
responses, and fix the classifier before any full-scale numbers existed. All fixes below
were made **before** the full 5,466-record run; none were tuned on full-run results.

## 1. Pilot selection

Deterministic: within each stratum records are ordered by `sha256(accession + "pr7c1")`.
Strata overlap; the union is 122 records.

| Stratum | Records |
|---|---|
| status group x domain (up to 3 per cell; 21 non-empty cells) | 3 per cell (fewer where the cell is smaller) |
| all engineered records | 6 |
| all seed records | 15 |
| Swiss-Prot (reviewed) | 5 |
| source release 2026_03 | 5 |
| metagenome-like organism names | 15 |
| exact-duplicate pairs (both members) | 12 |
| two largest sequence groups | 13 |
| records without any EMBL cross-reference | 10 |
| **Union** | **122** |

## 2. Final pilot result (after fixes; offline replay)

| primary_grade | Records |
|---|---|
| DIRECT_SAMPLE | 52 |
| NOT_REPORTED | 69 |
| AMBIGUOUS | 1 |
| LOOKUP_FAILED | 0 |

Chain status: COMPLETE 115, NO_LINK 7 (all 6 engineered records plus one PDB-derived mutant
sequence, A0A6P3CW42). Offline replay from the cache reproduced the outputs with 0 network
fetches. The pilot did not include the literature step; the literature fields were
NOT_SEARCHED during the pilot.

## 3. Hand trace and fixes

Every pilot record was traced by hand from UniProt cross-references through the ENA coding
record, parent sequence, BioSample (ENA XML and NCBI) to the classified row. Defects found and
fixed:

1. **Legacy ENA tags unmapped.** ENA sample XML uses bare `feature` / `material` / `biome`
   tags in older submissions. Mapped to env_local_scale / env_medium / env_broad_scale
   (the MIxS legacy mapping agreed in the plan).
2. **NCBI `sample_type`** (values such as "pure culture", "cell culture", "water") was
   unmapped. Now mapped to `sample_material`; it is never counted as habitat.
3. **`investigation_type`** is now captured as a sample-type input (reported, not habitat).
4. **host_is_self false positives on viruses.** The binomial host==self rule wrongly
   discarded the host of Emiliania huxleyi virus 86 (Q4A355, Q4A378) and Phaeocystis globosa
   virus (A0AC59EXE7), whose names begin with their host's binomial. The binomial rule is now
   skipped for viral organisms; exact name or taxid matches still apply.
5. **UniParc route.** UniParc search JSON does not carry cross-references, so the
   `/uniparc/{upi}/databases` endpoint is used. A0ACC2JG09 (UniProt entry deleted, "Not part
   of a reference proteome") now resolves via protein KAJ8126158 to SAMN32166878 and is graded
   DIRECT_SAMPLE with MEDIUM link confidence and flag `uniparc_embl_link`.
6. **Culture vocabulary.** Added growth-medium values ("R2A medium", anything containing
   "agar"/"broth", "culture/growth/isolation medium"), "strain collection" and "(viral)
   plaque". A0A3B7RPS8 ("R2A medium") and A0AAW0GV67 ("Strain collection") moved from
   DIRECT_SAMPLE to NOT_REPORTED with `tissue_or_culture_only`; M1HVR3 ("viral plaque") keeps
   DIRECT_SAMPLE through its reported host *Micractinium conductrix*.
7. **Root-ENVO placeholders.** Values that only carry a root ENVO class (e.g. M1HVR3 env_medium
   "Environmental Material [ENVO:00010483]") are `uninformative_placeholder`, not usable.
8. **Spurious geo/date discordance.** Format differences ("2016-04" vs "Apr-2016") raised
   `date_discordant`; comparison keys are now normalized. These flags never affect the grade.
9. **`free_text_context_only`** is now raised only for records without any usable habitat.
10. **Multi-value separator** changed from "|" to " || " because one value (A0ACG3RPU1)
    contains a literal "|".

## 4. Observations kept as findings (no rule change)

- **B2D030 is genuinely AMBIGUOUS**: two environmental clones from "Lake Kinneret at 2m depth"
  and "6m depth". The strict rule (normalized string equality or identical explicit ENVO-ID
  sets) treats these as disagreeing sample units.
- **A0A6P3CW42** (member, *Mastigocladopsis repens*) is a PDB-derived N63A/P118A mutant
  sequence with no INSDC link, but it is not flagged as engineered in the frozen database.
  Recorded as an observation for curators; the database was not changed.
- **All 6 engineered records** have no INSDC link and are NOT_REPORTED with `no_insdc_link`
  and `engineered_record`.
- **SAMN32343746** is absent from ENA (browser 404, empty portal result) while present at
  NCBI: flagged `sample_copy_absent`, not a lookup failure.
- Many JGI fungal BioSamples (e.g. *Aspergillus*) report "missing" in every habitat field
  (`habitat_reported_missing`). Several model or seed organisms (*Polarella* SAMEA5987284,
  *Halobacterium* NRC-1 SAMN02604216) have BioSamples with no habitat fields.
- Environmental clones without a BioSample (e.g. EBAC31A08 / Q9F7P4 "seawater"; Q6J4G7 Red
  Sea 60 m) are DIRECT_SAMPLE through INSDC source-feature qualifiers.
- No formatting-only conflicts between INSDC source features and BioSample attributes were
  seen, so the strict normalization rule (lower case, whitespace collapsed) was kept.

## 5. Safety checks exercised in the pilot

- **NCBI UID pitfall**: `efetch id=SAMEA5987284` returns SAMN05987284 (numeric UID collision).
  BioSamples are mapped only by accession through `esearch "<acc>[accn]"` and verified against
  the returned accession / Ids; a negative test covers this.
- Failures are cached as failures and are never reported as NOT_REPORTED.
- Offline mode raises on any cache miss, so replay cannot silently fetch.

## 6. Final vocabularies (frozen for the full run)

Defined in `tools/habitat_audit/normalize.py` and documented in `habitat_field_dictionary.md`:
`ROLE_MAP` (tag to role), `MISSING_RE` (reported-missing values), `TISSUE_TERMS`
(isolation_source only, unless a non-self host is reported), `CULTURE_RE` (whole-value
culture/laboratory descriptions; all habitat roles), `PLACEHOLDER_ENVO` / `PLACEHOLDER_TEXT`,
and the virus-aware `host_is_self` rule.

## 7. Addendum after the full run (written at the end of PR-7c.1)

The pilot (122 records: DIRECT 52, NOT_REPORTED 69, AMBIGUOUS 1) froze the vocabularies above. The
full run and validation then changed or added the following. Pilot numbers are not re-stated as final;
the final figures are in `PR7C1_HABITAT_AVAILABILITY_REPORT.md`.

- **INSDC flat-file route.** 27 parent sequences had no ENA portal sequence row. They are now resolved from
  the ENA flat file (`insdc_flatfile`), whose `DR BioSample` cross-reference supplies the sample link
  (28 records gained a BioSample this way). The ENA `wgs_set` route was attempted for 16 sets and returned
  no usable data (all `not_found`); it is retained for traceability only.
- **UniParc extension.** 6 inactive or EMBL-less UniProt entries are linked through UniParc to an EMBL
  protein of the same species (route `uniparc_embl_protein`, MEDIUM confidence, flag `uniparc_embl_link`).
- **ENA HTTP 400 = not_found.** The ENA portal returns 400 for an empty result on some queries; these 84
  requests are recorded as `not_found`, never as failures and never as NOT_REPORTED without a complete chain.
- **`habitat_nonstandard` role.** Non-MIxS tags (environment, habitat, isolation site, source of isolate,
  seabed habitat; 40 records) are reported as `<tag>: <value>` and never graded.
- **Conflict diagnostics.** Contrary to the pilot observation in section 4, the full run found formatting-only
  conflicts: 10 of 142 conflicting role instances are `punctuation_only` and 43 are `token_subset`. 132/142
  are within one sample unit (an INSDC source feature vs its own BioSample). The strict rule was kept as
  agreed; see `PR7C2_HABITAT_DESIGN_RECOMMENDATIONS.md`.
- **Literature.** The 110-record subset (107 characterized + seeds) was reviewed; see the main report.
- **Specification completeness.** The independent re-implementation exposed vocabulary items that existed
  in code but were not enumerated in the dictionary (strain collection, viral plaque, fruiting body/bodies,
  the `habitat_nonstandard` cell format). The dictionary now lists the vocabularies verbatim; no rule changed.
