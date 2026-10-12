# PR-7c.1 LIVE habitat spot-check (100 records)

Independent reviewer re-query of the public services (retrieval 2026-10-12); the audit's production code
(`tools/`, `tests/`) and HTTP cache were not read or used. Own cache: private scratch; raw per-record bundles in `raw/`.

## Method
1. `spotcheck_fetch.py`: UniProtKB REST JSON -> EMBL xrefs (protein_id, parent); inactive entries -> UniParc (`extraAttributes.uniParcId`
   -> `/uniparc/{UPI}/databases`, EMBL xrefs restricted to the deleted entry's taxon); no EMBL xref -> UniProt proteome -> BioSample
   (ENA assembly fallback). ENA portal `result=coding` by protein accession (rows[0]); fallback `result=sequence` on the parent, then the
   ENA EMBL flat file `DR BioSample` lines. Flat-file source features were also fetched for every parent as a cross-check.
   Each BioSample read from ENA (`browser/api/xml`) and NCBI (`esearch [accn]` -> `efetch`, returned accession verified equal).
   NCBI <=3 req/s with tool/email.
2. `spotcheck_eval.py`: independent re-implementation of dictionary s4 (tag-key normalization + role map), s5 (missing tokens,
   host_is_self, ENVO placeholders, culture, tissue-in-isolation_source), s6 (union-find on normalized value / same ENVO set, conflict
   per role), s1 precedence. Output compared to the audit's grade and per-role usable value sets.
3. `spotcheck_litverify.py`: every literature item for the 10 literature-graded records re-fetched live from its `source_url`; quote and
   habitat_text verified after normalization; strain designations searched in the source; scope judged manually.
4. `spotcheck_finalize.py`: builds this report and `spotcheck_results.tsv`.

All 100 chains completed without lookup failure (ENA and NCBI BioSample copies found for all 76 distinct linked BioSamples (81 record-sample links);
ENA and NCBI habitat-role values identical for every sample).

## Agreement
- Grade agreement: **100/100**; audit usable values (per role, normalized sets) confirmed: **100/100**.

| Stratum | agree / n |
|---|---|
| AMBIGUOUS | 15/15 |
| DIRECT_SAMPLE | 40/40 |
| NOT_REPORTED | 35/35 |
| ORGANISM_CONTEXT_ONLY | 5/5 |
| VERIFIED_ISOLATE | 5/5 |

Literature: 10/10 records, 11/11 items: quote found verbatim in the live source and habitat_text inside the quote. Isolate scope
justified for all 5 VERIFIED_ISOLATE (strain named: PS1; PCC 7104; DSW-6T = DSM 17205, the record BioSample's culture collection;
ATCC 50818, the BioSample's culture collection; SG1, also in the X70291 source feature). Organism scope justified for A0A060H1D7,
A0A0D1E071, G1K3Q0 (species-level statements). Database part of all 10 has no usable value (confirmed).

## Disagreements
None.

## Observations (rule interpretation, not disagreements)
1. **AMBIGUOUS is dominated by synonym/format conflicts.** 15/15 sampled AMBIGUOUS records are reproduced under the strict rule, but
   10 are `host` scientific-vs-common-name pairs (Mangifera indica/Mango x3, Malus domestica/apple x3, Heterodera glycines/soybean cyst
   nematode, Ailanthus altissima/altissimus, Actinemys marmorata/+common name, banana/banana (Musa ...)). In 3 of these
   (A0A0F8A5R8, A0AAF0DL47, N1RG29) the differing value is produced by the **ENA portal coding row**, which normalizes `host`;
   the INSDC flat file itself carries the same text as the BioSample. Others are truncation (H2BR49 'Lake Fryxel'), token subset
   (A0A4U6XBC4 'leaves' vs 'Tanacetum ... leaves'; A0A9W6BEJ7 'fresh water' vs 'small freshwater lake'). Only B2D036 (2 m vs 12 m
   depth, two CDS links) and D2Y5H4 (middle vs bottom sea ice) are genuine within-role differences. Consumers should treat AMBIGUOUS
   as 'has habitat values, not string-identical', and the conflict_kind diagnostics are important; consider reading `host` from the
   flat file rather than the portal row.
2. **Location-like isolation_source counted as habitat** (by design): 'Red Sea' (A0A1Q9CRJ3), 'Lake Kinneret', 'Lake Superior',
   '150 km offshore' (M9RSC0). These are submitter habitat-role values, so usable under the rules, but are weak habitat descriptors.
3. **Tissue rule only for isolation_source**: A0A3D8RJI5 'leaf' is moved to material in isolation_source but usable in env_medium;
   A0A9X0AZX4 env_local_scale 'root' usable; A0A9P5BFI1 env_medium 'Agapanthus praecox' (a plant name) usable. Rule-consistent.
4. **Q5V0R5 / Q5V4H7 organism scope is conservative**: AY596297 is from the genome paper (PMID 15520287) that calls the sequenced organism
   'a halophilic archaeal isolate from the Dead Sea'. The s9 parent rule (strain not named in quoted sentence -> demote) makes
   ORGANISM_CONTEXT_ONLY correct; the s9 'paper about that strain' clause would support VERIFIED_ISOLATE. Ambiguity in the rules (C),
   audit result rule-consistent.
5. A0AAV9PSJ0 (inactive): UniParc holds 20 identical EMBL proteins from several Exophiala strains (isolation_source 'motor vehicle'/'rock');
   following all would yield AMBIGUOUS. Only the same-taxon xref (KAK5528741) is the record's own sequence; the audit did this correctly.
6. NOT_REPORTED records: 35/35 have only missing tokens, culture descriptions, geography, titles or no BioSample; C4L4S1 has only
   habitat_nonstandard 'Yellowstone National Park' (correctly not graded). No usable value was missed.

SPOTCHECK_AGREE_ALL
