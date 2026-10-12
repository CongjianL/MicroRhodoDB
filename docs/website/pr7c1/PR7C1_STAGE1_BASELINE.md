# PR-7c.1 Stage 1: frozen baseline and habitat-field completeness

Written from the frozen release database (opened read-only, immutable URI) **before any external retrieval**.

- Database: `releases/v1.6.0/db/microrhododb_v1.6.0.sqlite`, sha256 `379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f` (verified).
- Base commit: `932eb567a199f9eef25f7e04ac2aaa745e17156c`.

## Record identity checks

| Check | Value |
|---|---|
| n_records | 5466 |
| n_counted | 5460 |
| n_engineered | 6 |
| n_mrdb_acc | 5299 |
| n_accession_map | 5466 |
| accession_map_source_databases | ['UniProt'] |
| n_literature_subset | 110 |
| n_seed | 15 |
| n_characterized | 107 |
| n_seq_groups_gt1 | 129 |
| n_records_in_seq_groups_gt1 | 296 |
| n_exact_duplicate_of | 6 |

## Strata (denominator 5,466 source records)

**status_group_audit:** boundary 509; candidate 1377; engineered 6; member 3085; outgroup 386; rejected 103

**membership_status:** boundary_family 509; decoy_or_rejected 103; heliorhodopsin 386; typeI_candidate 209; typeI_candidate_architecture_supported 273; typeI_candidate_unresolved 897; typeI_member_architecture_supported 381; typeI_member_core 2704; typeI_member_curated 4

**domain:** Archaea 699; Bacteria 1455; Eukaryota 3120; Unassigned 192

**source_release:** UniProtKB_2026_02 5361; UniProtKB_2026_03 105

**evidence_level:** E1 91; E2 112; E3 1143; E4 1050; E5 3070

**reviewed:** 0 5415; 1 51

## Environmental fields in the frozen database

`sequence_source` columns whose names relate to sample, environment or geography:

| Column | Non-empty / rows | State |
|---|---|---|
| sample_id | 0 / 5466 | empty |
| sample_type | 0 / 5466 | empty |
| bioproject | 0 / 5466 | empty |
| biosample | 0 / 5466 | empty |
| biome | 0 / 5466 | empty |
| env_feature | 0 / 5466 | empty |
| env_material | 0 / 5466 | empty |
| latitude | 0 / 5466 | empty |
| longitude | 0 / 5466 | empty |
| collection_date | 0 / 5466 | empty |

Full per-column completeness for `sequence_source` and `protein`: `stage1_field_completeness.tsv`.
The `protein` table has no environment, habitat, host, isolation-source or BioSample column.

Data-dictionary columns whose names match env/habitat/isolation/host/biosample/country/biome:

- `sequence_source.biosample`: INSDC BioSample accession (environmental field; empty).
- `sequence_source.biome`: Biome annotation (environmental field; empty).
- `sequence_source.env_feature`: Environmental feature annotation (environmental field; empty).
- `sequence_source.env_material`: Environmental material annotation (environmental field; empty).

Release metadata entries mentioning an environmental layer:

- `environmental_layer` = microrhododb_v1.5.0_env_pilot.sqlite (supplementary)
- `environmental_pilot` = PR13.6 2026-09-24: 976 marine + 376 soil MGnify candidates; frozen v1.2.0 scores; source-aware admission only

The supplementary v1.5.0 environmental pilot (MGnify candidates) is a separate database and is not part
of the 5,466 source records; it is out of scope for this audit.

## Exporter and production JSON

`tools/export_web_data.py`, lines containing each key (case-insensitive):

- `habitat`: none
- `biosample`: none
- `bioproject`: none
- `isolation_source`: none
- `env_broad`: none
- `env_local`: none
- `env_medium`: none
- `env_feature`: none
- `env_material`: none
- `biome`: none
- `geo_loc`: none
- `collection_date`: none
- `lat_lon`: none
- `sample_type`: none
- `isolation`: [1512]

The only `isolation` hit is the Foldseek watchlist caveat key ("Watchlist entries are not corpus records"),
which is unrelated to sample isolation.

Local web export (`web/public/data/v1.6.0`, git-ignored): {"files_with_key": {}, "n_json_files": 5317, "present": true}

## Conclusion

No habitat, sample, BioSample, geography or collection-date value exists for any of the 5,466 records in
the frozen database, the exporter or the production JSON. Every habitat value in PR-7c.1 must therefore
come from external retrieval with full provenance, and the baseline for every record is 'not present in
MicroRhodoDB v1.6.0'.
