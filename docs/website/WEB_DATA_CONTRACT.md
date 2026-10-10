# MicroRhodoDB website 2.0: static data contract (dataset v1.6.0)

Status: PR-0 draft for review. PR-1 implements it in `tools/export_web_data.py` together with TypeScript types and JSON Schemas (`web/src/data/schemas/`).
This document covers the topics that plan section 15 assigns to `WEB_DATA_CONTRACT.md`, `PDB_STRUCTURE_MAPPING.md`, `PHYLOGENY_DISPLAY_SPEC.md` and `EVIDENCE_AND_STATISTICS_DENOMINATORS.md`. They are consolidated here (sections 6-8) and may be split later. All counts quoted are from `baseline/pr0_db_audit.json`.

## 1. Principles

1. **Single source.** Every value shown by the website comes from:
   - the official v1.6.0 SQLite file, opened read-only, SHA-256 `379a2543...dce17f`
   - the files in `refpkg/MR_RT_003/` (byte-identical copies only)
   
   The browser does no scientific aggregation. Every count shown is precomputed by the exporter, and its SQL is recorded.
2. **Fail closed.** If the DB is missing or its SHA-256 differs, the exporter exits non-zero with `BLOCKED_DATA_SOURCE`. It never reads `site/data.js` as a data source. `site/data.js` is used only as a regression oracle in tests.
3. **No invention.** The exporter emits PDB IDs only from `protein_pdb`, functions only from `v_master` / `function_evidence`, and topology only from the treefile. Missing values stay missing, with an explicit reason.
4. **Determinism.** The same inputs produce byte-identical outputs: sorted keys, stable row order (`mrdb_acc, source_acc`), fixed float formatting, and no timestamps except the build stamp in `manifest.json`. A second run must reproduce every checksum in `export_manifest.json`.
5. **Release-scoped URLs.** All payloads live under `data/v1.6.0/`. The frontend reads `data/current.json` → `{ "dataset_release": "1.6.0", "path": "data/v1.6.0/" }`, and caches are keyed by release so versions cannot mix.

## 2. Missing-value conventions

The DB uses `NULL`, `''` and sometimes literal strings with different meanings. The exporter normalizes them as follows:

| JSON form | Meaning | Example |
|---|---|---|
| `null` | Not available in the source DB for this record | `afdb_global_plddt` when `afdb_model.status='no_model'` |
| explicit enum value | A state that the DB encodes implicitly | `clade_state: "outgroup_reference_tip"` instead of `clade_id: NULL` |
| `"not_applicable"` (only in enum-typed fields) | The property does not exist for this object | resolution of a solution-NMR entry |
| field absent | Never used for payload fields. Schemas mark every field as required, with nullability declared | |

`''` from the DB is never emitted. Each column that contains `''` gets a rule in the exporter's column map, and the rule is tested.

UI copy maps these to "Not available" / "Not applicable" / "Not reported" (plan 3.3).

## 3. Layout

```text
data/
  current.json
  v1.6.0/
    manifest.json            # provenance, schema version, headline counts (section 4.1)
    summary.json             # all metrics with denominators + SQL ids (section 8)
    records-index.json       # columnar, 5,466 rows, lightweight Browse/search fields (4.3)
    accessions.json          # source_acc -> mrdb_acc, representatives (4.4)
    records/MRDB000001.json  # 5,299 files: MRDB entry with all source records (4.5)
    sequences/corpus.fasta   # 5,466 sequences, header ">source_acc mrdb_acc"; lazy (Search, bulk FASTA)
    structures-index.json    # pdb_id -> metadata + [source_acc]; AFDB/predicted summary (6)
    evidence-index.json      # per E-level / function basis / conflict / curated lists (8)
    clades.json              # 19 level-1 entries (17 clades + 2 backbone groups) + 30 subclades (7)
    phylogeny/
      MR_RT_003.rooted.treefile   # byte copy, SHA-256 c5619697...d5ded9aef
      tips.json                   # 472 tips (7.2)
      clade_tips.json             # tip -> clade/subclade/backbone membership (7.2)
      robustness.json             # clade_robustness (54 rows) + per-clade Jaccard columns
      preview.svg                 # static homepage preview drawn from the same Newick (no phylotree on Home)
    publications.json        # 121 publications + 255 active links (inactive links excluded; see 4.6)
    watchlist.json           # 181 novel_family_candidate + funnel; never merged with records (4.7)
    export_manifest.json     # sha256 + bytes + row counts for every file above
```

Estimated sizes (raw):
- `records-index.json`: about 0.8-1.2 MB columnar. It is loaded by Browse only.
- `corpus.fasta`: about 1.9 MB.
- Record files: 1-60 KB each. P02945 is the largest because of 174 PDB entries.

Home loads only `current.json`, `manifest.json`, `summary.json` and `preview.svg`.

## 4. Payload contracts

### 4.1 `manifest.json`

```ts
interface Manifest {
  schema_version: "1.0.0";
  dataset_release: "1.6.0";
  website_version: string;               // e.g. "2.0.0-pr1"
  source_db: { file: "microrhododb_v1.6.0.sqlite"; sha256: string; opened_read_only: true };
  refpkg: { id: "MR_RT_003"; rooted_treefile_sha256: string; rooted_treefile_md5: string;
            db_treefile_md5: string; db_treefile_md5_refers_to: "run1.treefile" };
  exporter: { path: "tools/export_web_data.py"; git_commit: string; git_dirty: boolean; python: string };
  built_at_utc: string;                  // the only non-deterministic field; excluded from reproducibility hash
  counts: { records: 5466; counted: 5460; mrdb_accessions: 5299; tree_tips: 472; level1_clades: 17;
            backbone_groups: 2; pdb_links: 472; pdb_entries: 438; publications: 121; active_links: 255; watchlist: 181 };
}
```

The literal numbers are validator expectations for v1.6.0, held in a test fixture. The UI never hard-codes them. It reads them from `summary.json`.

### 4.2 Enumerations (closed sets; validators reject anything else)

| Enum | Values (v1.6.0) | Source |
|---|---|---|
| `membership_status` (9) | `typeI_member_core`, `typeI_member_architecture_supported`, `typeI_member_curated`, `typeI_candidate`, `typeI_candidate_architecture_supported`, `typeI_candidate_unresolved`, `boundary_family`, `heliorhodopsin`, `decoy_or_rejected` | `status_definition` |
| `membership_group` | `member`, `candidate`, `boundary`, `outgroup`, `rejected` | `status_definition.status_group` |
| `evidence_level` | `E1`-`E5` | `v_master` |
| `func_class` (11) | `proton_pump`, `proton_pump_inward`, `anion_pump`, `sodium_pump`, `light_gated_channel`, `sensory`, `sensory_like`, `enzyme_rhodopsin`, `photoreceptor_unassigned`, `unassigned`, `unresolved` | `func_class_definition` |
| `tax_domain` | `Archaea`, `Bacteria`, `Eukaryota`, `null` (192 counted records) | `v_master` |
| `clade_state` | `confident`, `tentative`, `reference_tip_unclustered`, `outgroup_reference_tip`, `outgroup_placed`, `unassigned`, `distant` | Derived (section 7.3) |
| `link_role` | `support`, `compilation`, `context`, `conflicting_evidence`, `unresolvable_not_counted` | `assertion_publication` (active rows) |
| `afdb_status` | `ok`, `no_model` | `afdb_model.status` |
| `pdb_method` | `X-RAY DIFFRACTION`, `ELECTRON MICROSCOPY`, `SOLUTION NMR`, `ELECTRON CRYSTALLOGRAPHY` | `pdb_structure.method` |

### 4.3 `records-index.json` (Browse, universal search)

This is a columnar object, `{columns: string[], rows: any[][]}`, with one row per source record (5,466). The order is `mrdb_acc, source_acc`.

| Field | Type | Source |
|---|---|---|
| `mrdb_acc` | `string` `^MRDB\d{6}$` | `v_master` |
| `source_acc` | `string` (unique) | `v_master` |
| `is_mrdb_representative` | `boolean` | `source_acc = mrdb_accession.representative_source_acc` |
| `protein_name`, `organism` | `string` | `v_master` |
| `tax_domain` | enum or `null` | `v_master` |
| `length` | `int` | `v_master` |
| `membership_status` | enum | `v_master` |
| `membership_score` | `number` or `null` | `v_master` (shown separately from status) |
| `func_class` | enum | `v_master` |
| `evidence_level` | enum | `v_master` |
| `call_conflict` | `boolean` | `v_master` (468 true) |
| `is_engineered` | `boolean` | `v_master` |
| `counts_eligible` | `boolean` | `v_master` |
| `clade_state` | enum | Section 7.3 |
| `clade_id` | `string` or `null` | Confident clade only |
| `tentative_clade_id` | `string` or `null` | `v_master` (720 set) |
| `n_pdb` | `int` | `COUNT(DISTINCT pdb_id)` from `protein_pdb` for this `source_acc` |
| `has_afdb` | `boolean` | `afdb_model.status='ok'` |
| `helixC_motif` | `string` or `null` | `v_master` |
| `novel_family_flag` | `string` or `null` | `novel_family_flag.novel_family_hit` |

Browse "Experimental PDB" counts **source-level** links. The record page also shows the MRDB-level union and states which one is shown.

### 4.4 `accessions.json`

```ts
{ by_source: Record<string, string>;                 // 5,466 entries, source_acc -> mrdb_acc
  by_mrdb: Record<string, { representative_source_acc: string; sources: string[] /* sorted, repr first */;
                            sequence_sha256: string; first_release: string }> }   // 5,299 entries
```

Routing rules:
- `#/record/<MRDB>` focuses `representative_source_acc`.
- `#/record/<source_acc>` focuses that source and shows its MRDB siblings.
- An unknown ID shows a Not-found state.

These match the legacy `site/app.js` behavior, which the existing permalinks rely on.

### 4.5 `records/<MRDB>.json` (Protein Entry)

```ts
interface MrdbEntry {
  mrdb_acc: string; dataset_release: "1.6.0";
  representative_source_acc: string; n_source_records: number;
  pdb_union: string[];                                // distinct PDB IDs over all sources (MRDB000001: 175)
  sources: SourceRecord[];                            // representative first, then by source_acc
}
interface SourceRecord {
  // identity
  source_acc: string; source_database: "UniProt"; reviewed: boolean | null;
  protein_name: string; organism: string; organism_id: number | null; tax_domain: TaxDomain | null;
  gtdb: { taxonomy: string | null; agreement: string | null; match_level: string | null; release: string | null };
  length: number; sequence: string;                   // from protein.sequence
  exact_duplicate_of: string | null;
  // membership (kept separate from evidence)
  membership: { status: MembershipStatus; group: MembershipGroup; score: number | null;
                status_reason: string | null; boundary_subtype: string | null;
                curated_override: { rule: string | null; rationale: string | null } | null };  // only for typeI_member_curated
  // function and evidence
  function: { func_class: FuncClass; func_class_v14: string | null; evidence_level: "E1"|"E2"|"E3"|"E4"|"E5";
              function_basis: string | null; e1_representative: string | null;
              e2_ref: string | null; e2_identity: number | null; override_rule: string | null;
              call_conflict: boolean; call_conflict_detail: string | null };
  engineering: { is_engineered: boolean; wild_type_acc: string | null; counts_eligible: boolean };
  motifs: { helixC_motif: string | null; motif_class: string | null; retinal_site_residue: string | null;
            pocket_string_br: string | null; pocket_mean_plddt: number | null };
  architecture: { arch_primary: string | null; fusion_type: string | null; fusion_partner_domains: string | null;
                  flags: string[] } | null;              // null when no `structure` row (580 records)
  phylogeny: { clade_state: CladeState; clade_id: string | null; subclade_id: string | null;
               tentative_clade_id: string | null; clade_lwr: number | null; placement_call: string | null;
               is_reference_tip: boolean; tip_role: string | null };
  structures: { experimental: PdbLink[]; afdb: AfdbModel | null; predicted: PredictedModel[] };
  publications: PubLink[];                             // active links only, ordered support > compilation > context > other
}
interface PdbLink { pdb_id: string; method: PdbMethod; resolution_A: number | "not_applicable" | null;
                    title: string; ligands: string[]; has_retinal: boolean; year: number;
                    is_rep: boolean; is_highest_res: boolean; shared_with: string[] }   // other source_acc linked to the same PDB ID
interface AfdbModel { model_id: string | null; status: "ok" | "no_model"; version: number | null;
                      global_plddt: number | null; seq_match: boolean | null;
                      seq_start: number | null; seq_end: number | null; model_url: string | null }
interface PredictedModel { method: string; mean_plddt: number; file: string | null /* null if coordinates are not shipped */; note: string }
interface PubLink { publication_id: string; doi: string | null; pmid: string | null; title: string; journal: string | null;
                    year: number | null; link_role: LinkRole; counts_as_support: boolean; verdict: string;
                    caveat: string | null; evidence_basis: string | null }
```

The column-to-field map and the SQL for every field are written into the exporter and covered by golden tests against SQLite (section 9).

### 4.6 Publications

`publications.json` holds the 121 `publication` rows and the 255 active `assertion_publication` rows, with `link_role`, `counts_as_support`, `verdict` and `caveat`.
- The 7 inactive rows (`is_active=0`: 6 `not_supported`, 1 `verified_with_correction`) are not shown as support.
- They are kept in the export for audit but are filtered by default.
- Only `counts_as_support=1` rows (141) may be described as supporting evidence.

### 4.7 Watchlist isolation

`watchlist.json` = the 181 `novel_family_candidate` rows (viral_rhodopsin 138, structure_only 23, schizorhodopsin 12, bestrhodopsin 5, MerMAID 3) plus `novel_family_funnel`. Rules:
- No watchlist ID may appear in `accessions.json`. This was checked against the DB: 0 overlaps.
- No membership, evidence or function fields are attached to watchlist entries.
- The 786 `foldseek_hit` rows are not exported in PR-1. A caveat is shown: Foldseek returns at most 1,000 hits per query and database, and 9 of 10 queries hit that cap.

## 5. Sequence search contract (unchanged semantics)

The search runs in a Web Worker, reads `sequences/corpus.fasta`, and keeps exactly the legacy parameters:
- 3-mer prefilter retaining 300 candidates
- Smith-Waterman with BLOSUM62, gap open 11, gap extend 1
- top 10 hits

Golden cases are generated with the legacy `site/app.js` on the 12 CLI queries plus P02945, and the new worker must reproduce the scores and hit order. The UI labels this "similarity search over prefiltered candidates, not a membership classifier" and points to `tools/mrdb_search.py`.

## 6. Experimental and predicted structures (PDB_STRUCTURE_MAPPING)

Source SQL (authoritative). It is one link per row, and the per-record list is the array of rows for that `source_acc`:

```sql
SELECT pp.source_acc, pp.pdb_id, ps.method, ps.resolution, ps.title, ps.ligands, ps.has_retinal, ps.year
FROM protein_pdb pp JOIN pdb_structure ps ON ps.pdb_id = pp.pdb_id   -- 0 unmatched ids, so INNER = LEFT
ORDER BY pp.source_acc, pp.pdb_id;
```

Rules:
- Experimental presence = at least one `protein_pdb` row. It is **not** `structure.has_experimental_structure`, because A0A2R4S913 has PDB links but no `structure` row.
- `is_rep` / `is_highest_res` flags come from `structure.rep_pdb_id` / `highest_res_pdb_id`. If either one is ever outside the linked set, the exporter fails with `STRUCTURE_SOURCE_ANOMALY`. It does not rewrite the value. In v1.6.0 there are 0 such cases.
- `ligands` is split on `;`. RET presence is `has_retinal` from the DB. It is not inferred from the ligand string.
- Resolution `NULL` with method `SOLUTION NMR` → `"not_applicable"`. Resolution `NULL` with any other method → `null` ("Not reported").
- **No chain or residue mapping** between a PDB entry and the UniProt sequence is claimed in v2.0. Bacteriorhodopsin reference numbering is shown only where the DB provides it (`pocket_string_br`, helix-C motif).
- AFDB model: `afdb_model` only. The record shows status, version, global pLDDT, `seq_match`, residue range and `model_url`. A `no_model` record shows "No AlphaFold DB model".
- Predicted models (`predicted_structure`, 2 rows, ESMCFold2) are shown in a separate "Other predicted models" block. Their coordinate files are not in the repository, so `file` is `null` until the owner provides them.
- Mol* viewer:
  - Lazily imported on the structure tab only.
  - Experimental structures load from `https://models.rcsb.org/v1/<id>/full?encoding=bcif`, falling back to `https://files.rcsb.org/download/<ID>.cif`.
  - AFDB structures load from `model_url`.
  - On failure, an error state is shown with direct links. The rest of the page keeps working.

`structures-index.json`:

```ts
{ pdb: Record<string, PdbMeta & { source_accs: string[] }>;       // 438 keys
  coverage: { pdb_source_records: 66; pdb_mrdb_entries: 58; afdb_ok: 4397; afdb_only: 4336; neither: 1064 } }
```

These counts are recomputed at export time and validated, not typed in.

**Structure-integrity gate (PR-1 G1, blocking):** for every `source_acc`, `set(record.structures.experimental[].pdb_id)` must equal the set from `protein_pdb` in SQLite. `n_pdb` must equal the size of that set. `pdb_union` must equal the union over sources. All 5,466 records are checked, not a sample.

## 7. Phylogeny and clades (PHYLOGENY_DISPLAY_SPEC)

### 7.1 Tree

- The Newick is the rooted file, byte-copied and verified by SHA-256. The root is the heliorhodopsin outgroup.
- Internal labels are parsed as `SH-aLRT/UFBoot`. They are exported unchanged and displayed as "SH-aLRT x / UFBoot y".
- Topology and branch lengths are never edited in the browser. Collapsing a clade is a display-only operation.

### 7.2 Tips and clade membership

`tips.json` has 472 entries:

```ts
{ tip: string; tip_role: "cl0.6_representative"|"anchor_characterized"|"seed"|"outgroup_heliorhodopsin"|"boundary_schizorhodopsin";
  in_corpus: boolean; mrdb_acc: string | null;          // false/null for QBQ84355, QBQ84358
  level1: string | null; subclade: string | null; backbone_group: "MR_CLD3_B01"|"MR_CLD3_B02"|null }
```

Membership is built from `clade_tip` (457 rows) and `tips.tsv`:
- `level1` = `clade_tip.clade_id` when it matches `MR_CLD3_0\d\d`
- `backbone_unassigned` → `level1 = null`, and `backbone_group = subclade_id` if it is B01/B02
- The 15 outgroup tips have no `clade_tip` row → `level1 = null`, `tip_role = outgroup_heliorhodopsin`

Validators require:
- 472 tips
- 422 tips in the 17 level-1 clades
- 8 tips in backbone groups
- 27 unclustered backbone tips
- 15 outgroup tips

### 7.3 Records vs tips (placement is not a tip)

`clade_state` per source record:

| clade_state | Rule (applied in order) | PR-0 count (all records) |
|---|---|---|
| `outgroup_reference_tip` | No `record_clade` row (the 15 heliorhodopsin outgroup tips) | 15 |
| `confident` | `v_master.clade_id` non-empty | 4,139 |
| `tentative` | `clade_id` empty and `tentative_clade_id` set | 720 |
| `reference_tip_unclustered` | `record_clade.source='reference_tip'`, no level-1 clade (backbone tips) | 27 |
| `outgroup_placed` | current `placement.clade_call='outgroup_heliorhodopsin'` | 456 |
| `unassigned` | current `placement.clade_call='unassigned'` | 105 |
| `distant` | current `placement.clade_call='tentative'` with no `tentative_clade_id` (`placement_call='distant_tentative'`) | 4 |
| **Total** | | **5,466** |

The PR-0 counts come from a read-only probe. The exporter recomputes them and checks the sum.

Display rules:
- Placed records (`record_clade.source='placement'`, 4,996) are never drawn as tips.
- The tree may show them only as an aggregated "N placed records" annotation on a clade, with a link to filtered Browse.
- Only `placement.is_current=1` (MR_RT_003) is used.

### 7.4 `clades.json`

There are 19 level-1 entries, each with `kind: "clade" | "backbone_group"`, and 30 level-2 subclades.

Level-1 fields from `clade`:
- `name`, `naming_basis`, `n_tips`, `ufboot`, `sh_alrt`
- the `dominant_*` columns
- `e1_classes_tips`, `n_records_assigned`, `n_E1`
- `consensus_status`, `e1_function_consensus` (v1.6.0 recomputed, plan 8.3)
- `jaccard_run2/3`, `jaccard_midpoint_rooting`, `min_cross_replicate_jaccard`
- confident and tentative record counts (computed)

UI copy: "17 level-1 clades and 2 backbone groups". A robustness caveat is shown when `min_cross_replicate_jaccard < 0.8` or `consensus_status='mixed'` (MR_CLD3_017: mixed, Jaccard 0.52). The threshold is a display rule. It is not a scientific reclassification.

## 8. Statistics and denominators (EVIDENCE_AND_STATISTICS_DENOMINATORS)

Each metric in `summary.json` has the form:

```ts
{ id: string; label: string; value: number; denominator: { id: "all_records"|"counted_records"|"mrdb_accessions"|"tree_tips"|"pdb_entries"|"watchlist"; value: number };
  inclusion: { engineered: "included"|"excluded"; watchlist: "excluded" }; sql: string; dataset_release: "1.6.0" }
```

Default denominators:
- Membership composition: all 5,466 records (plan 10.1).
- Evidence composition: counted records (5,460, engineered excluded), with a toggle for the 5,466 total. Example: E1 = 88 counted / 91 total.
- Function and taxonomy: counted records.
- Structure coverage: source records and MRDB entries, reported separately.
- E1-E5 are labeled evidence types, never probabilities. Membership status and evidence level are never combined into one scale.

## 9. Validation required in PR-1 (Gate G1)

1. The `source_acc` set equals `v_master`: 5,466, no additions or omissions. `mrdb_acc` values number 5,299. Counted records number 5,460.
2. `accessions.json` equals `accession_map` row for row. The representatives equal `mrdb_accession`.
3. The structure-integrity gate (section 6) passes on all records. PDB metadata equals `pdb_structure`.
4. The 472 tips, the 7.2 tallies, `clade_state` summing to 5,466, and the 19 + 30 clade rows all match the DB and refpkg.
5. Every `summary.json` value is recomputed independently in pytest from SQLite. Section 1.3 baselines are fixtures.
6. Every legacy `site/data.js` column that maps to the new export (39) agrees cell by cell. This is a regression oracle, read only in tests.
7. The watchlist and the corpus are disjoint.
8. JSON Schema validation runs on every payload. A second export reproduces `export_manifest.json` byte for byte.
9. Frozen files (`releases/**`, `refpkg/MR_RT_003/**`) are unchanged against `baseline/frozen_sha256_fab9182.txt`, and the DB SHA-256 is unchanged after export.
