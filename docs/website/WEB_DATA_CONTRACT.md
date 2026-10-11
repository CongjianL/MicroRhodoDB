# MicroRhodoDB website 2.0: static data contract (dataset v1.6.0)

Status: PR-0, corrected after owner review (CONDITIONAL PASS; see `WEB_BASELINE_AUDIT.md` sections 8-9); implemented in PR-1 by `tools/export_web_data.py`. **Normative payload shapes are the JSON Schema `web/src/data/schemas/web-data.schema.json`** (and the TypeScript types generated from it, `web/src/data/types.ts`); where the prose of sections 3-8 differs, section 10 lists the as-built deviations and the schema wins.
This document covers the topics that plan section 15 assigns to `WEB_DATA_CONTRACT.md`, `PDB_STRUCTURE_MAPPING.md`, `PHYLOGENY_DISPLAY_SPEC.md` and `EVIDENCE_AND_STATISTICS_DENOMINATORS.md`. They are consolidated here (sections 6-8) and may be split later. All counts quoted are from `baseline/pr0_db_audit.json`.

## 1. Principles

1. **Single source.** Every value shown by the website comes from:
   - the official v1.6.0 SQLite file, opened read-only, SHA-256 `379a2543...dce17f`
   - the files in `refpkg/MR_RT_003/` and the two ESMCFold2 files in `releases/v1.0/structures/` (byte-identical copies only)

   The browser does no scientific aggregation. Every count shown is precomputed by the exporter, and its SQL is recorded.
2. **Fail closed.** If the DB is missing or its SHA-256 differs, the exporter exits non-zero with `BLOCKED_DATA_SOURCE`. It never reads `site/data.js` as a data source. `site/data.js` is used only as a regression oracle in tests.
3. **No invention.** The exporter emits PDB IDs only from `protein_pdb`, functions only from `v_master` / `function_evidence`, and topology only from the treefile. Missing values stay missing, with an explicit reason.
4. **Determinism.** The same inputs and the same exporter commit produce byte-identical outputs: sorted keys, stable row order (`mrdb_acc, source_acc`), fixed float formatting and **no wall-clock timestamps in any exported file** (there is no `built_at_utc`). Provenance is carried by content-derived values only: the input SHA-256 values, the exporter git commit and a `git_dirty` flag. `export_manifest.json` lists every other output file with its SHA-256, byte size and record count; it is itself deterministic, so two runs must produce byte-identical `export_manifest.json` files. Build time, if wanted, belongs in CI logs, not in the data.
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
    structures/predicted/    # A0A9X2L7U0_esmfold.pdb, B0R633_esmfold.pdb: byte copies from releases/v1.0/structures/ (6)
    evidence-index.json      # per E-level / function basis / conflict / curated lists (8)
    clades.json              # 19 level-1 entries (17 clades + 2 backbone groups) + 30 subclades (7)
    phylogeny/
      MR_RT_003.rooted.treefile   # byte copy, SHA-256 c5619697...d5ded9aef
      tips.json                   # 472 tips (7.2)
      clade_tips.json             # tip -> clade/subclade/backbone membership (7.2)
      robustness.json             # clade_robustness (54 rows) + per-clade Jaccard columns
      tree_stats.json             # node census: 472 tips, 471 internal (incl. root), 469 support labels (7.1)
      preview.svg                 # static homepage preview drawn from the same Newick (no phylotree on Home)
    publications.json        # 121 publications + 255 active links (inactive links excluded; see 4.6)
    watchlist.json           # 181 novel_family_candidate + funnel; never merged with records (4.7)
    export_manifest.json     # sha256 + bytes + row counts for every file above (not itself); no timestamps
```

Estimated sizes (raw):
- `records-index.json`: about 0.8-1.2 MB columnar. It is loaded by Browse only.
- `corpus.fasta`: about 1.9 MB.
- Record files: 1-60 KB each. P02945 is the largest because of 174 PDB entries.

Home loads only `current.json`, `manifest.json`, `summary.json` and `preview.svg`. **PR-2 as built:** Home draws the preview from the Newick itself and also loads `clades.json`, `phylogeny/tips.json`, `phylogeny/MR_RT_003.rooted.treefile` and `vocabulary.json` (about 186 KiB raw / 25 KiB gzip of data in total); it still never loads `records-index.json`, `accessions.json`, record files or sequences. See section 11.

## 4. Payload contracts

### 4.1 `manifest.json`

```ts
interface Manifest {
  schema_version: "1.1.0";              // "1.0.0" in PR-1; additive 1.1.0 in PR-2 (section 11)
  dataset_release: "1.6.0";
  website_version: string;               // e.g. "2.0.0-pr2"
  source_db: { file: "microrhododb_v1.6.0.sqlite"; sha256: string; opened_read_only: true };
  refpkg: { id: "MR_RT_003"; rooted_treefile_sha256: string; rooted_treefile_md5: string;
            db_treefile_md5: string; db_treefile_md5_refers_to: "run1.treefile" };
  exporter: { path: "tools/export_web_data.py"; git_commit: string; git_dirty: boolean; python: string };
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
interface PredictedModel { method: string;            // "ESMCFold2 (full)"
                          mean_plddt: number;        // 0-100 (DB predicted_structure.mean_plddt)
                          file: string;              // export path, e.g. "structures/predicted/B0R633_esmfold.pdb"
                          source_path: string;       // "releases/v1.0/structures/B0R633_esmfold.pdb" (resolved from DB pdb_file)
                          sha256: string;            // equals the frozen manifest and the copied file
                          bytes: number;
                          bfactor_scale: "fraction_0_1"; // per-residue pLDDT stored in B-factor as 0-1
                          note: string | null }
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
- Predicted models (`predicted_structure`, 2 rows, ESMCFold2 (full), A0A9X2L7U0 and B0R633) are shown in a separate "Other predicted models" block and are loadable in Mol*.
  - Path resolution: the DB `pdb_file` (`structures/<acc>_esmfold.pdb`) is relative to the historical release directory. The exporter globs `releases/*/<pdb_file>` and requires **exactly one** match (today `releases/v1.0/`); zero or several matches fail with `STRUCTURE_SOURCE_ANOMALY`.
  - The file's SHA-256 must equal the frozen manifest (`3089c414...198a` and `e6edb539...a4b4`); otherwise the export fails.
  - The file is byte-copied to `data/v1.6.0/structures/predicted/<acc>_esmfold.pdb`; the original is opened read-only and never modified.
  - Labelling: "Predicted model (ESMCFold2), not experimental". B-factors hold pLDDT as a 0-1 fraction.
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
- Node census of the rooted file: 472 tips, **471 internal nodes including the root**, **469 genuine support labels**. The 2 unlabelled internal nodes are the root and a non-root 25-tip node (the former top node of `run1.treefile`); both root children are labelled (corrected in PR-1; `WEB_BASELINE_AUDIT.md` section 10.1). DB `tree_node` stores the unrooted `run1` topology (470 internal nodes, the same 469-label multiset).
- **Support provenance.** On 17 of 470 non-root internal nodes the rooted file attaches a label to a different bipartition than IQ-TREE `run1.treefile` (rerooting moved node-attached labels; `WEB_BASELINE_AUDIT.md` section 10.2). The exporter therefore also emits `phylogeny/support_audit.json` (keyed by first/last tip in Newick order) and `tree_stats.json` → `support_audit`. Which label is displayed is an owner decision for PR-4; until then no UI may present a rooted-file label on a disagreeing node without the audit caveat. **Decided in PR-4 (section 12.2): the website displays the IQ-TREE run1 label of the same bipartition on every node; rooted-file labels are audit fields only.**
- A label is shown as statistical support **only** if it is a Newick internal-node label matching `^\d+(\.\d+)?/\d+(\.\d+)?$`; it is exported unchanged and displayed as "SH-aLRT x / UFBoot y". Unlabelled nodes show no support. Parser-generated names (phylotree 2.6.0 names the root `"root"`, which is why the PoC counted 470 "named" internal nodes) are never displayed as support. `phylogeny/tree_stats.json` records 471 / 469 / 2 and the tests check it.
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
- PR-4 amendment (owner decision, section 12.3): for one record at a time (`#/phylogeny?placement=MRDB…`) the explorer may highlight the record's current `placement.best_edge` reference branch. No tip or branch is added and no position along the branch is drawn.
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
6. Every legacy `site/data.js` column that maps to the new export (39) agrees cell by cell under the exact rules of section 9.1. This is a regression oracle, read only in tests.
7. The watchlist and the corpus are disjoint.
8. JSON Schema validation runs on every payload. A second export (same inputs, same commit) into a fresh directory reproduces every output file, including `export_manifest.json`, byte for byte. No exported file contains a wall-clock timestamp.
9. Frozen files (`releases/**`, `refpkg/MR_RT_003/**`) are unchanged against `baseline/frozen_sha256_fab9182.txt`, and the DB SHA-256 is unchanged after export.

### 9.1 Legacy oracle: exact allowed transformations

Default rule: **strict equality of value and type** (string = string, int = int). This applies without exception to accession identifiers (`mrdb_acc`, `source_acc`, `wild_type_acc`, `exact_duplicate_of`, `e1_representative`, `e2_ref`, `afdb_model_id`), categorical assignments (`membership_status`, `func_class`, `func_class_v14`, `evidence_level`, `motif_class`, `tax_domain`, clade and subclade IDs and names) and scientifically discrete fields (`length`, `retinal_site_residue`, `helixC_motif`, `pocket_string_br`, `call_conflict_detail`, `function_basis`, `status_reason`, `override_rule`, `novel_family_flag`, `gtdb_taxonomy`, `protein_name`, `organism`). There is no numeric tolerance and no generic blank/NULL equivalence.

The only permitted transformations between the legacy value `L` and the new export value `N`:

| # | Columns | Rule |
|---|---|---|
| T1 | `membership_score` (k=3), `afdb_global_plddt` (k=1), `e2_identity` (k=3) | `L == float(numpy.round(N, k))` (legacy used pandas `Series.round`; for `e2_identity` the DB value is first coerced with `float()`). `N` is the full-precision DB value. `L is None` iff `N is None` |
| T2 | 0/1 integer flags: `call_conflict`, `is_engineered`, `counts_eligible`, `reviewed`, `is_mrdb_representative` | `L in (0, 1)` and `bool(L) == N` when the new field is boolean; otherwise strict |
| T3 | `clade_id`, `subclade_id` (the only columns where the DB holds `''`: 1,312 and 1,741 cells) | `L == ''` iff `N is None`; non-empty values strictly equal |
| T4 | `clade_confidence` (legacy-only) vs new `clade_state` | `confident`→`confident`, `tentative`→`tentative`, `none`→ any of `outgroup_reference_tip`, `reference_tip_unclustered`, `outgroup_placed`, `unassigned`, `distant` |
| T5 | `is_mrdb_representative` | `L == int(source_acc == mrdb_accession.representative_source_acc)` and equals the new `is_representative` |
| T6 | Row order | Legacy order is `ORDER BY mrdb_acc, source_acc`; records are matched by `source_acc`, and the set must be equal |
| T7 | Publications | Legacy `pubs[source_acc]` lists equal the new active links in order (`source_acc`, `counts_as_support DESC`, `year`), with `pmid` as the string of the integer and `year` as int |

Any other difference fails the test. PR-0a strict check: 0 mismatched cells (`baseline/pr0a_corrections.json`).

## 10. PR-1 as-built deviations from the PR-0 prose

All deviations are additive or make a type explicit; none changes a scientific value. Each is enforced by the schema and by `tests/test_web_export.py`.

| Area | PR-0 prose | As built (PR-1) | Reason |
|---|---|---|---|
| Empty strings | generic missing-value rules | `EMPTY_STRING_RULES` in the exporter lists every DB column holding `''`: `v_master.clade_id`/`subclade_id` → `null` (meaning carried by `clade_state`), `pdb_structure.ligands` → `[]`, `structure.fusion_partner_domains` → `null`, `clade_function_consensus.E1_classes` → `null`. Any other `''` aborts the export (`CONTRACT_VIOLATION`); no exported JSON contains `""` | fail closed |
| `PdbLink.year` | text | integer parsed from `pdb_structure.year` | typed |
| `PdbLink` / `PdbIndexEntry` | — | `ligands` is a list split on `;`; NMR `resolution_A` = `"not_applicable"`; `is_rep`, `is_highest_res` from `structure.rep_pdb_id` / `highest_res_pdb_id` (`false` when a PDB-linked record has no `structure` row); `shared_with` = other source accessions linked to the same PDB ID | explicit |
| `gtdb.agreement` | string | number (DB REAL) | typed |
| `architecture` | nullable | always an object with `has_structure_row` | records without a `structure` row are explicit |
| `membership.curated_override` | free text | `{rationale: membership.status_reason, source}` for the 4 `typeI_member_curated` records; `function.override_rule` stays as in the DB (null for these 4) | no invention |
| Publication order | by role | `counts_as_support DESC, year, publication_id, assertion_id` (legacy order plus deterministic tie-breaks) | determinism; legacy oracle T7 compares per-source multisets and the (support, year) key order |
| `LinkRole` enum | active roles | adds `dropped`, `replaced`, used only in `publications.json` → `inactive_links` (7 links, never support) | audit trail |
| Record fields | — | added `release_added`, `is_current`, `lineage`, `novel_family_flag` object (`hit`, bits, e-value), `phylogeny.placement` object, `clade_function_source`, `function.v160_change`, `call_conflict_exact`, `exp_class`, `clade_function` | complete v_master/DB coverage |
| UniProt cross-reference strings | — | `protein.pdb`/`kegg`/`refseq` are **not** exported; PDB IDs come only from `protein_pdb` | principle 3 |
| Floats | "fixed formatting" | full-precision DB value, Python `repr` (shortest round-trip); rounding is a display concern | lossless, deterministic |
| New files | — | `phylogeny/support_audit.json`, `phylogeny/tree_stats.json` (support census and audit counts), `phylogeny/preview.svg` | section 7.1 |
| `export_manifest.json` | — | every other file under the output root (path, sha256, bytes, records), exporter commit and `git_dirty`, DB SHA-256; no timestamps | principle 4 |
| Exit codes | `BLOCKED_DATA_SOURCE` | 2 `BLOCKED_DATA_SOURCE` (DB missing/SHA mismatch, refpkg input mismatch), 3 `STRUCTURE_SOURCE_ANOMALY` (predicted file not uniquely resolved or SHA mismatch), 4 `CONTRACT_VIOLATION` (any invariant, including refusing to replace a directory that is not a previous export) | fail closed |

## 11. Schema 1.1.0 (PR-2, additive)

PR-2 needed three things the 1.0.0 export did not provide. All changes are additive; no 1.0.0 field changed name,
type or value, and no scientific value changed. `tests/test_web_export.py` (33 tests) and the JSON Schema enforce them.

| Area | 1.0.0 | 1.1.0 | Reason |
|---|---|---|---|
| `records-index.json` columns | 25 | 46: 21 columns appended after the 1.0.0 columns, same order: `membership_group`, `retinal_site_residue`, `function_basis`, `func_class_v14`, `motif_class`, `call_conflict_detail`, `wild_type_acc`, `exact_duplicate_of`, `e1_representative`, `clade_name`, `tentative_clade_name`, `gtdb_taxonomy`, `afdb_model_id`, `afdb_global_plddt`, `e2_ref`, `e2_identity`, `override_rule`, `pocket_string_br`, `status_reason`, `lineage`, `pdb_ids` (list of source-level PDB IDs) | Browse must filter on and export every legacy TSV field (39 legacy columns) without fetching 5,299 record files. Values are identical to the record files, full precision (`test_records_index_v11_columns_cover_legacy_tsv`) |
| `clades.json` → `level1[].support_audit` | `db_label`, `rooted_file_label`, `iqtree_run1_label`, `db_matches_iqtree_run1` | adds `iqtree_run1_sh_alrt`, `iqtree_run1_ufboot` (numbers parsed from the run1 label of the same bipartition) and `iqtree_run1_meets_support_thresholds` | The UI displays corrected support from numbers, never from the rooted-file labels; the threshold flag is computed once in the exporter |
| `clades.json` top level | — | `clade_rule` (the MR_CLD3 rule copied from `pipeline/v150/define_clades.py` PRIMARY/SUB and `refpkg/MR_RT_003/README.md` item 4: level-1 5-100 tips, subclade 3-40 tips, SH-aLRT >= 80 and UFBoot >= 95, both inclusive) and `support_display` (which field to show and why) | Reporting only. The rule is never used to redefine or reclassify clades. With it, exactly one level-1 clade fails: MR_CLD3_017, run1 SH-aLRT 50.3 / UFBoot 72 (frozen DB label 100/100), retained as a legacy v1.6.0 assignment |
| New file `vocabulary.json` | — | `membership_status` (9 rows from `status_definition`: status, group, is_member, is_candidate, v1.4 label, definition), `func_class` (11 rows from `func_class_definition`), `evidence_level` (E1-E5 parsed from `data_dictionary` `function_evidence.evidence_level`, with the source text), `clade_state` (7 exporter definitions, section 7.3), `evidence_note` | Labels and definitions shown in the UI come from the DB, not from UI literals. Counts are omitted (they live in `summary.json`) |
| `manifest.website_version` | `2.0.0-pr1` | `2.0.0-pr2` | Release label |

Not changed: record files, `accessions.json`, `summary.json` metrics and distributions, sequences, structures,
publications, watchlist, phylogeny files, `export_manifest.json` format, determinism rules, exit codes.

## 12. Schema 1.2.0 (PR-4, additive)

PR-4 (Phylogeny & Clade Explorer) needed the full node table of the rooted tree with corrected support, the mapping
from DB edges to rooted branches, and per-clade display aids. All changes are additive; no 1.1.0 field changed name,
type or value, and no scientific value changed. No inference was run and no clade was re-derived.
`tests/test_web_phylogeny.py` (gate G4, 21 tests, independent Newick parser and bipartition code),
`tests/test_web_export.py` (33 tests) and the JSON Schema enforce them.

### 12.1 New and extended files

| File / field | Content | Source |
|---|---|---|
| `phylogeny/explorer.json` | `nodes[]` (471 internal nodes incl. root, in rooted preorder over all 943 nodes: `pre`, `internal_index`, `parent`, `length`, `n_tips`, `first_tip`, `last_tip`, `is_root`, `rooted_label`, `run1_label`, `sh_alrt`, `ufboot`, `label_agrees`, `root_split_shared`, `support_displayed`, `is_outgroup_root_child`, `clade_mrca[]`, `subclade_mrca[]`); `tips{}` (472, keyed by accession: `pre`, `length`, `mrdb_acc`, `in_corpus`, `tip_role`, `level1`, `subclade`, `backbone_group`, `unclustered_backbone`, `organism`, `protein_name`, `tax_domain`, `phylum`, `helixC_motif`, `func_class`, `evidence_level`, `clade_state`, `func_class_v14`, `subfamily_v14`, `annotation_source`); `edge_map{}` (941 DB `tree_edge.edge_id` → rooted preorder indices); `root_split`; `meta` (tree id, method, model, run1 log-likelihood, rooting, tip-role counts, file SHA-256s, display rules, placement status counts, DB edge-length deviation) | frozen rooted treefile (topology, lengths), `run1.treefile` (support), `tips.tsv`, `tips_annot.tsv`, `MR_CLD3_tips.tsv`, DB `tree_node`/`tree_edge`/`placement`, `v_master` |
| `phylogeny/run1.treefile` | byte copy of `refpkg/MR_RT_003/tree/run1.treefile` (SHA-256 `a7fe22920c6d663a8eeee04678ae5a336760c7d38b0ea4bd9af1f37a8913db0e`, also in `explorer.json` → `meta.support_source`; byte equality is tested) | refpkg |
| `phylogeny/MR_RT_003.rooted.run1-support.DERIVED.nwk` | the frozen rooted Newick with internal-node labels replaced by the run1 label of the same bipartition. Topology, tip names, tip order and every branch-length string are copied byte-for-byte; the root and the ingroup root child are unlabelled. 17 labels differ from the frozen file | derived; never authoritative |
| `phylogeny/MR_RT_003.rooted.run1-support.DERIVED.README.txt` | what the derived file is, why, the rules, both source SHA-256s, its own SHA-256 and the 17 changed nodes | derived |
| `clades.json` → `level1[]` and `subclades[]` | `mrca_node` (preorder index of the MRCA of the frozen tip set; the exporter fails if the tip set is not a clade of the rooted tree), `placement_counts` (`basis` + counts of current placements by `clade_call_qc`, or by `subclade_call` for subclades and backbone groups), `n_reference_tips_in_corpus` | DB `placement`, refpkg TSVs |
| `clades.json` → `level1[]` only | `e1_anchors[]` (E1 records with `v_master.clade_id` = this group; reference tips first, then MRDB accession), `representatives[]` (up to 12; deterministic rule in top-level `representative_rule`; display aid only) | `v_master`, `tips.tsv` |
| `manifest.website_version` | `2.0.0-pr4` | release label |

The refpkg input list now includes `tips_annot.tsv` (checked against the treefile tip set and `tips.tsv` roles).

### 12.2 Support decision (owner-approved)

- Displayed support for an internal node = the SH-aLRT/UFBoot label of the **same bipartition** in IQ-TREE
  `run1.treefile` (the release tree before rerooting). Topology and branch lengths are those of the frozen rooted file.
- On 17 of 470 non-root internal nodes the frozen rooted-file label belongs to a neighbouring bipartition (a one-step
  shift along the path from the outgroup root to the former run1 top node). These labels are kept as audit fields
  (`rooted_label`, `label_agrees = false`) and are never displayed as support.
- The two root branches form one unrooted bipartition (DB edge `E0397`). Its run1 label (98.8/100) is displayed once,
  on the outgroup root child (`support_displayed`); the ingroup root child and the root show no support.
- MR_CLD3_017 (MRCA preorder 744, internal index 372, 100 tips): run1 SH-aLRT 50.3 / UFBoot 72, below the
  SH-aLRT >= 80 / UFBoot >= 95 rule. The frozen DB and rooted-file label 100/100 is unchanged and shown as an audit
  field. Membership is retained as a legacy v1.6.0 assignment; the rule is reported, never applied.
- All 30 subclades meet the rule under run1 support (minimum SH-aLRT 82.2, MR_CLD3_009.01; minimum UFBoot 96,
  MR_CLD3_006.02).

### 12.3 Placements on the explorer

- `edge_map` maps every DB `tree_edge.edge_id` (= jplace `edge_num` on unrooted run1) to the rooted node(s) whose
  parent branch has the same bipartition: 941 entries, 0 missing, exactly one (the root split) mapping to two branches.
- A placement is displayed only as the highlight of its `best_edge` branch, with its stored statuses unchanged
  (`clade_call_qc`, `subclade_call`). The position along the branch (`distal_length`) is not stored in v1.6.0 and is
  never drawn. Placements are never added as tips.
- DB `tree_edge.length` differs from the frozen/run1 branch lengths by up to 0.0039705737
  (`meta.db_edge_length_max_abs_diff`); DB lengths are not used for display.

Not changed: record files, `accessions.json`, `records-index.json`, `summary.json`, `vocabulary.json`, sequences,
structures, publications, watchlist, the existing phylogeny files, `export_manifest.json` format, determinism rules,
exit codes.

## 13. Schema 1.3.0 (PR-4a, additive)

PR-4 showed `placement_counts` on clade pages next to "records assigned". For subclades and backbone groups the
placement counts grouped by `subclade_call` mixed placements that passed pendant QC with placements that did not, so a
reader could take, for example, 480 placements in MR_CLD3_017.02 for 480 members (the formal count is 311). PR-4a adds
the formal assignment counts, the breakdown by call and QC, and the backbone placement-only records. All changes are
additive; no 1.2.0 field changed name, type or value (the old `placement_counts.counts` is kept), and no scientific value
changed. `tests/test_web_pr4a.py` recomputes everything from the read-only DB.

### 13.1 Formal assignment rule (restated from `pipeline/v150/record_clades.py`)

A record's clade (`record_clade` / `v_master.clade_id`) is either reference-tip membership, or a current MR_RT_003
placement whose `clade_call` is `assigned` (LWR >= 0.9) **and** whose `placement_qc` is `ok` (LWR-weighted pendant <= 1.0,
`PENDANT_MAX` in `placement_assign.py`). Subclades use `subclade_call` the same way. A backbone subclade call (B01/B02)
without a level-1 clade becomes the record's level-1 group. A placement with call `assigned` but
`placement_qc = long_pendant` is a placement only: at level 1 it is the tentative record (`clade_call_qc =
distant_assigned`, `tentative_clade_id`); for subclades and backbone groups it has no formal assignment.

### 13.2 New fields

| File / field | Content |
|---|---|
| `clades.json` → `level1[]`, `subclades[]` → `assignment_counts` | `basis`, `reference_tips`, `placements` (call assigned and QC ok), `total` (= `v_master` rows with this `clade_id`, or `subclade_id` for subclades), `placements_assigned_call_failing_qc` |
| `… → placement_counts.call_field` | `clade_call` (level-1 clades) or `subclade_call` (subclades, backbone groups) |
| `… → placement_counts.by_call_and_qc` | `{call: {placement_qc: n}}` over current placements in the group |
| `… → placement_only_records` | backbone groups: list of placements with `subclade_call = assigned` that fail pendant QC (`source_acc`, `mrdb_acc`, `subclade_call`, `clade_call_qc`, `placement_qc`, `lwr_weighted_pendant`, `best_lwr`, `subclade_lwr`, `clade_state`); `null` for every other group |
| `clades.json` → `level1[].e1_anchors[]`, `representatives[]` → `is_engineered` | `v_master.is_engineered`, so the UI can say why an E1 record is not counted |
| `manifest.website_version` | `2.0.0-pr4a` |

The exporter fails if, for any group, the formal tip count differs from `n_reference_tips_in_corpus` or the formal
placement count differs from the number of placements with call `assigned` and `placement_qc = ok`.

### 13.3 The two reconciliations PR-4 left open

- **Backbone groups, 97 placements vs 94 formal placement assignments.** 97 current placements have `subclade_id`
  B01 (93) or B02 (4); all have `subclade_call = assigned` and `clade_call_qc = unassigned`. 94 pass pendant QC
  (B01 93, B02 1: A0A2P6NRH4) and are formal assignments. The other 3 (B02: A0A2P6MQ02 / MRDB002347, A0A2P6NAG6 /
  MRDB002348, A0A2P6NFX8 / MRDB002350; LWR-weighted pendants 1.734, 1.424, 2.111) are `long_pendant` and have no
  record clade (`clade_state = unassigned`). They are listed on the B02 page as placement-only records; no assignment
  is invented. Formal totals: B01 97 = 4 tips + 93; B02 5 = 4 tips + 1.
- **MR_CLD3_009, 12 E1 source records vs 11 counted.** All 12 have `v_master.clade_id = MR_CLD3_009` and
  `evidence_level = E1`; A0A8X6EH36 (MRDB003178) is an engineered construct (`is_engineered = 1`,
  `counts_eligible = 0`) and is excluded from `clade.n_E1` = 11, like every engineered construct in official counts.
  Every other group has as many E1 records as its `n_E1`.

Not changed: record files, `accessions.json`, `records-index.json`, `summary.json`, `vocabulary.json`, sequences,
structures, publications, watchlist, phylogeny files, `export_manifest.json` format, file count (5,317 exported files
plus the manifest), determinism rules, exit codes.

## 14. Schema 1.4.0 (PR-5, additive)

PR-5 adds the data behind the Statistics, Evidence, Downloads, Methods and Citation pages. All changes are additive:
no 1.3.0 field changed name, type or value, no metric or distribution value changed, and no classification, function,
clade or membership score changed. Compared with the PR-4a export, exactly one file was added (`downloads.json`) and four
files changed only by additions or version strings (`summary.json`, `evidence-index.json`, `manifest.json`,
`export_manifest.json`; the derived-tree README now says schema 1.4.0). `tests/test_web_pr5.py` replays every stored SQL
against the read-only DB.

### 14.1 New fields

| File / field | Content |
|---|---|
| `summary.json` → `metrics[]` | `members_candidates` (4,468), `clade_confident_members_candidates` (3,821), `records_with_afdb_counted` (4,391), `records_with_pdb_counted` (61), `novel_family_flag`, `foldseek_hits` (786) |
| `summary.json` → `distributions[]` | `membership_status_counted`, `ncbi_phylum_counted`, `motif_class_counted`, `helixC_motif_counted`, `length_bin_counted` (25-residue bins), `function_basis_category_counted`, `clade_state_members_candidates` |
| `summary.json` → `distributions[].derivation` | Optional. Present only when the stored SQL returns raw input that is reduced in Python; currently only `ncbi_phylum_counted` (phylum = the lineage name tagged `(phylum)`; `null` = no phylum-ranked taxon) |
| `summary.json` → `crosstabs[]` (new key) | `evidence_by_membership_group_counted`, `evidence_by_basis_category_counted`: `{id, label, row_field, col_field, sql, cells[{row, col, value}], total, denominator, dataset_release}`; each sums to `counted_records` (5,460) |
| `evidence-index.json` → `validation` | The stored LOCO / audit tables shown on the Evidence and Methods pages |
| `downloads.json` (new file) | `release` (tag, URL, `release_date`, `license` exactly as stored), `release_files[]` (39: path, sha256, bytes, `in_git_at_tag`, URL, distribution; only the SQLite DB is not in git), `refpkg_files[]` (37, from `refpkg/MR_RT_003/SHA256SUMS`), `repository_documents[]`, `website_derived[]`, `citation` (parsed from `CITATION.cff`; `doi` is null), `maintenance_placeholders[]`, `release_history[]`, `version_note` |
| `manifest.website_version` | `2.0.0-pr5` |

The exporter fails if any distribution or crosstab does not sum to its denominator or a crosstab has an `UNMAPPED` key.
`export_manifest.json` is linked from Downloads but never loaded by the browser.

### 14.2 Licence and date fields are copied, not reconciled

`release.license` is the stored string "CC BY 4.0 (data); MIT (code)". The repository `LICENSE` file contains only
CC BY 4.0 and `CITATION.cff` says `CC-BY-4.0`. `release.release_date` (DB metadata) is 2026-10-10, while
`CITATION.cff` `date-released` is 2026-10-09. The website shows both values with their sources and does not pick one;
reconciling them is a maintainer decision.
