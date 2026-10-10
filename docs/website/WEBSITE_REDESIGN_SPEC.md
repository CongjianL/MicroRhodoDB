# MicroRhodoDB Website Redesign & Scientific Portal Upgrade
## Complete Implementation Plan and Technical Specification

**Status:** APPROVED FOR IMPLEMENTATION PLANNING (website redesign; not a scientific database release change)  
**Specification date:** 2026-10-10  
**Current website:** https://congjianl.github.io/MicroRhodoDB/site/#/  
**Source repository:** https://github.com/CongjianL/MicroRhodoDB  
**`main` commit inspected:** `fab9182044c45670c869c8778fd8d48932bd35b8` (recheck `HEAD` before implementation)  
**Scientific data baseline:** MicroRhodoDB **v1.6.0** (schema `v160.1`), read-only and immutable.  
**Document purpose:** An actionable requirements specification, implementation plan, scientific-constraints document, and acceptance contract for Codex or another development agent.  
**Delivery policy:** Use small, independently verifiable pull requests. Preserve data and existing behavior before replacing the interface. A website redesign must not be represented as a new scientific data release.

---

## 0. Project Objectives and Immutable Boundaries

### 0.1 Overall objective

Transform the current lightweight static data browser into a **MicroRhodoDB Scientific Portal** that supports readers of scientific papers and researchers conducting real analyses. End users should be able to:

1. Understand the database's scope, version, size, reference phylogeny, and evidence system from the homepage.
2. Find a protein and open its complete, directly shareable, standalone **Protein Entry** page.
3. Explore the protein's sequence, membrane-spanning regions, motifs, functional evidence, publications, experimental PDB structures, and predicted structures.
4. Browse the actual MR_RT_003 reference phylogeny and navigate from tree tips and clades to individual entries.
5. Explore membership, evidence, functional class, taxonomy, and structure-coverage statistics with explicitly correct denominators.
6. Filter records, perform sequence-similarity searches, download results, and trace each annotation back to its source.
7. Reliably distinguish direct experimental findings, homology-based transfer, inference, unknown assignments, and conflicting evidence.

### 0.2 Success criteria

- A typical user can find a protein, its associated PDB entries, FASTA sequence, and supporting literature from the homepage in approximately two or three ordinary interactions.
- The homepage communicates the scientific content of the database rather than beginning with an unstructured table of 5,466 records.
- Protein Entry pages work as standalone pages, including direct links and opening in new tabs; they are no longer side drawers.
- Every displayed statistic is reproducible from the **official v1.6.0 SQLite database**; no manually entered metric may disagree with the database.
- The phylogeny viewer renders the genuine MR_RT_003 topology, not a decorative or fabricated tree, and never treats EPA-ng placements as reconstructed reference tips.
- Existing CLI tools, Python APIs, scientific workflows, frozen releases, and checksums remain intact.
- The current GitHub Pages address and existing deep links to protein records continue to work.

### 0.3 Out of scope for this website redesign

- Do not modify any frozen file under `releases/v1.6.0/` or any earlier `releases/` directory.
- Do not recalculate membership scores, change thresholds or E1–E5 evidence rules, relabel functional classes, or modify tree topology.
- Do not initiate large-scale sequence acquisition, fresh tree inference, structure prediction, or new manual literature curation.
- Do not describe the browser's Smith–Waterman similarity search as equivalent to the complete membership scorer.
- Do not promise browser-based execution of HMMER, DIAMOND, EPA-ng, or other server-side workloads using static GitHub Pages hosting alone.
- Do not include `novel_family_candidate` watchlist entries in official corpus counts.
- Do not create a new scientific data release (for example, v1.7.0) solely for interface changes. Track the website build version separately from the data release version.

---

## 1. Reviewed Baseline, Available Assets, and Key Issues

### 1.1 Existing implementation

| File / location | Current state | Required action |
|---|---|---|
| `site/index.html` | Four navigation destinations; Browse doubles as Home; `aside#detail` renders entries | Replace with independent Home, Browse, Record, and other routes |
| `site/style.css` | Approximately 2.4 KB; black/yellow navigation, 12–13px text, fixed side panel | Establish a responsive design system |
| `site/app.js` | Approximately 20.8 KB; custom routing, filters, side panel, Smith–Waterman | Refactor into modules without silently changing verified search semantics |
| `site/data.js` | Approximately 4.35 MB; all metadata and sequences loaded/executed together | Split into summary, search index, entry details, and on-demand sequence payloads |
| `tools/build_site_v160.py` | Exports selected SQLite fields but omits PDB links and important structure metadata | Create a schema-validated, manifest-backed exporter |
| `tests/browser_walkthrough_v160.py` | Playwright checks for legacy routes, filters, search, downloads, and scientific boundaries | Preserve as a migration baseline; add new-site end-to-end tests |
| `refpkg/MR_RT_003/` | Includes the 472-tip tree, clade tables, annotations, and robustness results | Use as the sole authoritative reference-tree source |
| `releases/v1.6.0/db/` | Official SQLite database is a GitHub Release binary, not a Git-tracked file | Retrieve or mount and verify before building; never fabricate a replacement |

### 1.2 Current deficiencies by priority

**P0 — Critical:**

- No standalone homepage.
- Entry details are shown in a fixed side panel. Closing a directly linked entry calls `history.back()`, which can produce incorrect navigation behavior.
- The underlying database contains PDB information, but the website export loses relationships and fields from `protein_pdb`, `pdb_structure`, and `structure`.
- The actual MR_RT_003 reference tree and scientifically meaningful aggregate statistics do not appear on the homepage.
- No explicit, validated contract ensures consistency between the official scientific database and the fields published by the website.

**P1 — High:**

- Dense filter controls, internal column names in tables, and poorly organized evidence/publication details.
- Main-thread sequence search with a 3-mer prefilter limited to the first 300 candidates; inadequate explanation and progress/error handling.
- Scattered explanations of E1–E5, membership status, and tentative clade assignments.
- Missing advanced tree viewer, structure viewer, Evidence Explorer, and Statistics pages.
- Clicking a table row is not a substitute for a semantic, keyboard-accessible link.
- Numeric sorting, shareable filter states, and loading/empty/error states require deliberate testing.

**P2 — Medium:**

- A monolithic JavaScript data file imposes an unnecessary initial-load burden.
- The About page mostly exposes raw internal metadata rather than researcher-oriented documentation.
- Citation, maintenance, and release information includes unresolved placeholders and presentation problems.
- The novel-family watchlist is not yet properly integrated into navigation and database semantics.

### 1.3 Official v1.6.0 baseline facts (verify again against SQLite during implementation)

| Metric | Baseline | Denominator / interpretation |
|---|---:|---|
| All source records | 5,466 | Includes engineered constructs |
| Counted records | 5,460 | Excludes 6 engineered constructs |
| Stable MRDB accessions | 5,299 | Identical sequences may share an MRDB accession; distinct from source-record counts |
| Type-I members | 3,089 | Includes 4 evidence-supported curated membership overrides |
| Candidates | 1,379 | Official membership category |
| Boundary family | 509 | Not equivalent to confirmed Type-I membership |
| Heliorhodopsins | 386 | Related family/outgroup, not confirmed Type-I members |
| Decoy/rejected | 103 | Visible for audit but excluded from Type-I membership |
| Counted E1 | 88 | **Counted records**; 91 E1 records in total |
| Counted E2 / E3 / E4 / E5 | 109 / 1,143 / 1,050 / 3,070 | Counted records; E1–E5 are evidence levels, not accuracy estimates |
| Publications | 121 | Unique publication entities, not links |
| Active record–publication links | 255 | Distinct from the 121 publications |
| Novel-family watchlist | 181 | Excluded from the corpus |
| Reference-tree tips | 472 | MR_RT_003 reference tips, not all 5,466 records |
| Level-1 clades | 17 | Must reconcile with reference-tree/clade tables |

**Mandatory requirement:** Do not hard-code these numbers into React components. This table provides acceptance baselines only; all statistics and charts must be generated deterministically from the same official database release.

---

## 2. Information Architecture and Route Contract

### 2.1 Navigation hierarchy

**Recommended primary navigation:** `Home`, `Browse`, `Phylogeny`, `Structures`, `Search`, `Downloads`, `About`.

Additional destinations: `Statistics`, `Evidence Explorer`, `Clade`, `Watchlist`, `Methods`, `Citation`, and `Help`. They may be grouped under Explore or another secondary menu; avoid crowding them into a single navigation row. A complete mobile navigation menu is required.

| Page | Route (hash-based; safe for the existing GitHub Pages host) | Primary purpose |
|---|---|---|
| Home | `#/` | Database purpose, universal search, authentic tree overview, statistics, shortcuts |
| Browse | `#/browse` | Clearly scoped record exploration, combined filters, sorting, downloads |
| Protein Entry | `#/record/:accession` | Full standalone entry supporting MRDB and source accessions |
| Phylogeny | `#/phylogeny` | Official 472-tip reference tree |
| Clade | `#/clade/:clade_id` | Clade membership, robustness, evidence, representative proteins |
| Structures | `#/structures` | Experimental and predicted structure browser |
| Evidence Explorer | `#/evidence` | E1–E5, function basis, conflicts, curated membership |
| Statistics | `#/statistics` | Database composition and annotation coverage |
| Sequence Search | `#/search` | Sequence-similarity search |
| Novel Watchlist | `#/watchlist` | Separate research-candidate layer; redirect legacy `#/novel` |
| Downloads | `#/downloads` | Releases, TSV, FASTA, SQLite, reference tree, tools |
| About / Methods / Citation / Help | `#/about`, `#/methods`, `#/citation`, `#/help` | Scope, methodology, license, citation, maintenance, FAQ |

### 2.2 Route behavior

1. `#/record/MRDB000001` opens the canonical entry for that stable accession.
2. `#/record/P02945` opens or resolves to the corresponding MRDB entry while clearly focusing the source accession `P02945`.
3. If multiple source accessions share one MRDB accession, show the representative and all source records; never incorrectly mix source-specific structure or publication associations.
4. All existing `#/record/<accession>` deep links must keep working after migration.
5. Closing an overlay (if any), returning to Browse, and browser Back/Forward must restore the appropriate navigation and filter state deterministically. Do not indiscriminately call `history.back()` to simulate closing a record page.
6. Unknown accessions show a useful Not Found page with a search action; no blank screen or stale entry content.
7. Store Browse filters in shareable hash-route query parameters, for example `#/browse?evidence=E1&status=member`.
8. Update the page `<title>`, available description metadata, and semantic headings based on routes; do not exaggerate search-engine indexing capabilities of a hash-routed GitHub Pages SPA.
9. Preserve the existing root-level `index.html` redirect to `site/`.
10. Do not switch to history routes that cause GitHub Pages refreshes to return 404 unless a separately verified fallback/SSG solution is introduced.

---

## 3. User Interface and Design System

### 3.1 Visual identity

- Design for a modern life-sciences database, not a generic SaaS dashboard or dense developer debugging interface.
- Reference: UniProt for standalone records; InterPro for sequence features; RCSB PDB for structure inspection; GPCRdb for specialized molecular workflows; MicRhoDE for combining rhodopsin search and phylogeny.
- Prefer a light theme: neutral white/light-gray canvas, deep-blue text, restrained blue/teal accents.
- Do not use color as an assertion of scientific accuracy. Show E1–E5 with text labels and definitions, not color alone.
- Avoid excessive shadows, gradients, or decorative 3D graphics; prioritize scientific data density and legibility.

### 3.2 Suggested design tokens

These are an initial proposal and may be adjusted after a visual review.

```text
canvas:             #F8FAFC
surface:            #FFFFFF
primary-text:       #142238
secondary-text:     #526175
accent-blue:        #1665B5
accent-teal:        #087F78
border:             #DEE5EC
danger/conflict:    #B45309
font:               system-ui / Inter-like sans-serif (subject to license compliance)
body:               16px, line-height >=1.5
table/text-small:   >=13px on desktop; avoid dense small text on mobile
max-content-width:  1280–1440px depending on page
tap-target:         >=44 x 44 CSS px where practical
```

### 3.3 Reusable components

`SiteHeader`, `GlobalSearch`, `Navigation`, `Breadcrumbs`, `PageTitle`, `StatCard`, `DefinitionTooltip`, `EvidenceBadge`, `MembershipBadge`, `CladeBadge`, `FilterPanel`, `FilterChip`, `DataTable`, `Pagination`, `EmptyState`, `LoadingSkeleton`, `ErrorState`, `DownloadMenu`, `CitationCard`, `SequenceViewer`, `PhylogenyViewer`, `MoleculeViewer`, `ProvenancePanel`, `SiteFooter`.

Define these through a shared design system before reusing them across Home, Record, Tree, and Statistics. Prioritize a smaller number of complete, polished pages over many incomplete pages.

### 3.4 Usability and accessibility

- Maintain clear information hierarchy on desktop, tablet, and phone. At minimum, test at 375px, 768px, and 1440px widths.
- Use real `<a>` elements for navigation and `<button>` elements for actions; do not use `<tr onclick>` as the sole interaction mechanism.
- Give every filter explicit labels; support Tab/Enter/Escape, and show keyboard focus clearly.
- Provide screen-reader-friendly table headers and sort states; supply textual summaries or accessible data tables for charts.
- Target WCAG 2.2 AA color contrast; avoid faint gray body text.
- Respect `prefers-reduced-motion`; document keyboard controls and focus handling in interactive tree/structure viewers.
- Distinguish `Not available`, `Not reported`, and `Not applicable` when warranted rather than silently rendering ambiguous blank fields.

---

## 4. Home Page Specification

### 4.1 Hero section

- Logo and `MicroRhodoDB` identity.
- Main heading: **Explore the diversity of microbial rhodopsins**.
- Subtitle: **An evidence-aware knowledgebase integrating sequences, phylogeny, structures and functional evidence**.
- Universal search for MRDB ID, UniProt accession, protein, organism, clade, PDB ID, and motif.
- Primary actions: `Browse proteins`, `Explore phylogeny`, `Sequence search`.
- Clearly display `Data release v1.6.0`, release date, dataset scope, and license link.

### 4.2 Main statistics cards

Recommended six cards: **Total records 5,466; Type-I members 3,089; experimentally characterized E1 88 counted records; reference-tree tips 472; publications 121; novel-family watchlist 181.**

The Statistics section should also expose 5,460 counted records, 5,299 unique MRDB accessions, 1,379 candidates, and other contextual metrics.

Each card must describe its counting policy. Corpus, tree, and watchlist populations must not be conflated. The exporter owns all metric values; UI components must not hard-code them.

### 4.3 Reference-tree overview (required)

Display a real visual summary of MR_RT_003, not an abstract or randomly generated decorative tree. Optionally color by clade or functional class and link to `Explore tree`. On narrow screens, show a lightweight overview without all 472 tip labels to preserve readability.

### 4.4 Statistical overview (required)

Show at least two charts on the homepage: membership composition and E1–E5 evidence composition. Move detailed taxonomy, function, and structure analysis into Statistics. Clearly label whether engineered constructs are included and which release is being summarized.

### 4.5 Quick exploration

Provide function-based exploration of proton pumps, anion pumps, sodium pumps, ion channels, sensory rhodopsins, enzyme rhodopsins, and other valid classes. Each category must open Browse with an accurate filter. Do not silently merge official functional categories when the mapping is ambiguous.

### 4.6 Scientific transparency

Include a concise note:

> Membership status is distinct from functional evidence level. E1–E5 describe evidence types, not calibrated probabilities of correctness.

Link to Methods instead of placing the complete validation audit on the homepage.

---

## 5. Browse: Record Exploration and Combined Filtering

### 5.1 Default population

Use **Type-I members** as the suggested default primary view, with explicit, one-click alternatives: `All records`, `Candidates`, `Boundary families`, `Heliorhodopsins`, and `Decoys`. Hide engineered constructs by default but offer a visible inclusion toggle. If members are the default, the page heading must say so; users must not infer that the entire database contains only 3,089 records.

All official records, including candidates and excluded groups, must remain accessible and exportable. A UI default must never cause data loss.

### 5.2 Searchable and filterable fields

- MRDB accession, source accession, protein name, organism, and taxonomic lineage.
- Membership status.
- Functional class.
- E1–E5 evidence level.
- Clade and subclade.
- Confident, tentative, or unassigned placement.
- Taxonomic domain (Bacteria, Archaea, Eukaryota, Viruses).
- Helix-C motif and retinal-site residue.
- Availability of experimental PDB structures.
- Availability of AlphaFold DB models.
- Function-call conflicts and curated membership overrides.
- Engineered construct status.
- Sequence-length interval.
- Publication support (presence of a supporting publication).

All filters must share a single validated search index and consistent data semantics. Do not treat missing `counts_eligible` or similar fields as an implicit `true` value.

### 5.3 Results table

Recommended columns: **MRDB accession, Source accession, Protein, Organism, Length, Membership, Function, Evidence, Clade, Experimental PDB, Structure availability.**

Support show/hide columns, proper numeric sorting, pagination (or carefully controlled virtual scrolling), visible entry links, and both total and filtered record counts.

### 5.4 Download contract

- Support `Download filtered TSV` and `Download filtered FASTA`.
- Downloaded records must match the active filters. Where one sequence has multiple source accessions, explicitly distinguish downloading source records from unique MRDB sequences.
- FASTA headers must preserve at least MRDB accession, source accession, status, and evidence semantics from the current implementation.
- Include release, date, and filter conditions in a safe filename or accompanying metadata manifest.
- Validate filename safety, Unicode, escaping, newlines, and TSV encoding/quoting. Never concatenate arbitrary user input into an unsafe path or filename.

---
## 6. Protein Entry: Standalone Record Page (Highest Priority)

### 6.1 Page structure

Top area: `Home / Browse / Protein entry` breadcrumbs; protein name; MRDB accession; source-accession selector; membership, functional-class, and E1–E5 evidence badges; `Copy link`, `Download FASTA`, and `Export record` actions.

Recommended six tabs:

1. **Overview**
2. **Sequence & Features**
3. **Structures**
4. **Phylogeny**
5. **Function & Evidence**
6. **Publications**

Tabs are sections of a full record page, not fixed drawers over a different page. On small screens, use anchor navigation or horizontally scrollable tabs.

### 6.2 Overview tab

- Protein accession and name, organism, taxonomic classification, and sequence length.
- Membership status and membership score presented separately; curated overrides must include a reason.
- Functional class and evidence level presented separately.
- Engineered status and related wild-type accession, if applicable.
- Representative accession and all identical-sequence source records.
- Concise cross-references to UniProt, PDB, AlphaFold DB, clade, and supporting publications.
- Provenance: database release, source-data release, and applicable curator rule/evidence basis.

### 6.3 Sequence & Features tab

- Complete FASTA sequence with Copy/Download actions.
- Auditable features shown at original sequence coordinates when available, including transmembrane segments, domains, and conserved sites.
- Helix-C motif (BR reference positions 85/89/96), retinal lysine (BR K216 reference), and retinal-pocket string.
- **Bacteriorhodopsin reference numbering is not automatically the residue index in the current protein.** Place residue markers at specific sequence positions only when a validated residue-number mapping exists.
- If no mapping exists, display `BR-reference annotation / position mapping not available` rather than inventing coordinates.
- Display domain architecture and fusion partners for fusion proteins; do not assume that the entire protein consists solely of a canonical seven-transmembrane-helix core.
- Provide bidirectional links between engineered variants and their wild-type records.

### 6.4 Structures tab: restore PDB IDs and visualize genuine structures

**Authoritative source tables:**

| Table / relationship | Key fields | Purpose |
|---|---|---|
| `protein_pdb` | `source_acc`, `pdb_id` | All experimental PDB entries associated with a source protein; do not keep only a representative |
| `pdb_structure` | `pdb_id`, `method`, `resolution`, `title`, `ligands`, `has_retinal`, `year` | Experimental method, structural evidence, and ligand information |
| `structure` | `rep_pdb_id`, `n_pdb_structures`, `rep_method`, `rep_resolution_A`, `highest_res_pdb_id`, `rep_has_retinal` | Representative structure summary and consistency checks |
| `afdb_model` | `model_id`, `status`, `global_plddt`, `seq_match`, `seq_start`, `seq_end`, `model_url` | Predicted structure metadata and sequence matching |
| `predicted_structure` | `method`, `mean_plddt`, `pdb_file` | Other models provided with the release, when actual files are available |

**Required export and display rules:**

- Use left joins or separate queries to construct an **array of structures per `source_acc`**, then attach these data to the appropriate MRDB entry with source attribution.
- Join `protein_pdb` to `pdb_structure` without multiplying or corrupting the number of protein records in the main index.
- Show **all** associated PDB IDs. Identify representative and highest-resolution entries without hiding alternatives.
- If an experimental PDB structure is available, prefer a verified structure as the default viewer selection.
- Provide RCSB links in the form `https://www.rcsb.org/structure/<PDB_ID>` and favor mmCIF for experimental-coordinate downloads.
- Lazily load Mol*. Support selecting a PDB, cartoon/surface representations, retinal or other ligands, rotation, image capture where supported, and access to original coordinate files.
- Separate **Experimental structures** from **Predicted structures** visually and semantically. Never describe AlphaFold pLDDT as experimental structure resolution.
- `has_retinal = 1` means that a particular PDB entry contains a retinal ligand; it does not, by itself, establish every functional state or condition of the protein.
- An accession-level PDB association is **not** a verified chain-level mapping. Precise residue highlighting requires validated polymer-entity/chain/residue correspondence. Disable residue-specific highlighting when this correspondence is unavailable; do not simulate a successful mapping.
- Load AlphaFold models only when `status = ok` and the model ID/URL are valid. Flag `seq_match` mismatches explicitly.
- For absent structures, show `No experimental PDB linked` and/or `No predicted model available`; never substitute an unrelated model.
- Handle network, CORS, and third-party service failures with clear error messages, retry options, and accessible RCSB/AlphaFold external links.

**Structure-integrity gate:** For every source accession, the PDB ID set exported to the website must exactly equal the set obtained by joining the authoritative SQLite tables. The displayed count must equal the number of distinct linked PDB IDs. If `rep_pdb_id` is non-null, verify that it belongs to the linked set; if not, report a source-data anomaly rather than silently rewriting the frozen database.

### 6.5 Phylogeny tab

- Show the MR_RT_003 tree ID, clade/subclade, and confidence information.
- If the protein belongs to the 472 reference tips, highlight that actual tip in the reference tree.
- For non-reference-tip proteins, show the current EPA-ng placement's best edge, likelihood weight ratio (LWR), credible set, and pendant-length quality control, explicitly stating **a placement is not a reconstructed tree leaf**.
- Distinguish low-confidence, tentative, and distant placements visually and textually.
- Provide `Explore this clade` and `View in reference tree` links that preserve the correct accession/clade identifiers.

### 6.6 Function & Evidence tab

- Clearly separate functional prediction/inference from measured experimental findings; display `func_class`, `function_basis`, and `evidence_level`.
- Distinguish supporting and contextual publications using `link_role`, `counts_as_support`, `verdict`, and `caveat`.
- For E2, show `e2_ref`, sequence identity, and transfer relationship. For E3/E4, explain motifs, clade support, and inherited legacy-class reasoning where applicable.
- Treat E5 as unassigned or uncertain, not as evidence proving absence of function.
- For `call_conflict = 1`, display the original conflict rationale and current handling.
- For `typeI_member_curated`, display the supporting curator override rationale.
- Do not present E1–E5 as arbitrary calibrated probabilities such as 100% or 80% certainty.
- Never render an unmeasured transport direction or absorption maximum as experimentally established.

### 6.7 Publications tab

- Publication title, year, journal, DOI, and PMID.
- Link-role labels such as `support`, `context`, and `compilation`.
- Emphasize direct E1 experimental support and explain how it differs from background literature.
- Do not turn a general review mentioning a protein into an assertion of direct experimental support.
- Use stable ordering and deduplicate repeated DOI entries for display without destroying separate assertion-to-publication relationships.

---

## 7. Phylogeny Explorer

### 7.1 Sole authoritative reference source

- `refpkg/MR_RT_003/tree/MR_RT_003.rooted.treefile`
- `refpkg/MR_RT_003/tips.tsv`
- `refpkg/MR_RT_003/tips_annot.tsv`
- `refpkg/MR_RT_003/clades/MR_CLD3_clades.tsv`
- `refpkg/MR_RT_003/clades/MR_CLD3_subclades.tsv`
- `refpkg/MR_RT_003/clades/MR_CLD3_tips.tsv`
- `refpkg/MR_RT_003/clades/clade_stability_primary_replicates.tsv`
- Link to SQLite `reference_tree`, `tree_node`, `tree_edge`, `placement`, and `record_clade` when needed.

Do not construct ad-hoc star trees, invent missing tips, or render reference tips and EPA-ng placements as equally supported reconstructed branches.

### 7.2 Viewer requirements

- Rectangular and radial layouts; toggles for proportional branch lengths versus uniform visualization.
- Zoom, pan, collapse/expand, and tip search.
- Coloring by taxonomic domain, clade, functional class, evidence level, or tip role.
- Separate legend for heliorhodopsin outgroups.
- Parse internal labels containing `SH-aLRT/UFBoot` correctly from the authoritative Newick. Allow users to toggle support labels or set display thresholds.
- Hover/click information panel: accession, organism, function, evidence, clade, and a link to Protein Entry.
- Offer an unmodified `Download Newick` and accurately rendered SVG/PNG downloads.
- Clearly state the tree model, tree ID, rooting approach, 472-tip scope, tree version, and provenance.
- The homepage tree preview and complete Tree Explorer must use the same underlying phylogenetic source and not generate inconsistent trees independently.

### 7.3 Scientific constraints on placements and clades

- Reference tips, EPA-ng placements, and confidence-gated clade assignments are distinct entities.
- Preserve `assigned`, `tentative`, `distant_assigned`, `distant_tentative`, and `unassigned` statuses precisely; never coerce them into a single categorical clade assignment.
- Use `best_lwr`, `clade_lwr`, and pendant-length QC to explain placement uncertainty.
- This release may show the 472-tip reference tree and a separate placement information panel. It is **not required** to append all 5,466 records to the topology.
- Expose clade robustness information. MR_RT_003 has 17 level-1 clades, some unstable across independent ML searches. In particular, retain the caveat associated with `MR_CLD3_017` rather than presenting all clade boundaries as unconditionally certain.

### 7.4 Clade Entry pages

Display clade ID, number of reference tips, node support, dominant taxonomic/motif/functional annotations, E1 anchors, confident versus tentative assignment counts, relevant subtree, and filtered Browse links. **Functional consensus must come from the official v1.6.0 clade-function consensus, not from superseded v1.5.0 labels.**

---

## 8. Statistics: Validated Metrics and Scientific Denominators

### 8.1 Required charts

1. Membership-status pie/bar chart (default denominator: all 5,466 source records unless explicitly changed to counted records).
2. E1–E5 composition (default denominator: 5,460 counted records).
3. Functional-class distribution, explicitly retaining unknown/unassigned values.
4. Taxonomic domain and major phylum distribution.
5. Clade coverage: confident, tentative, and unassigned placements from MR_RT_003.
6. Number of distinct experimental PDB entries, number of proteins with PDB associations, and number of available AlphaFold models. Compute these from the current database; do not copy structural counts from historical releases.
7. Motif-frequency and sequence-length distributions.
8. Watchlist category composition in a **separate** panel; never merge watchlist records into corpus totals.

### 8.2 Denominator integrity

Each exported metric must include:

- `metric_key`
- `value`
- `denominator` and/or `denominator_scope`
- `inclusion_policy` (including engineered-construct and membership rules)
- `release`
- `source_query_id` or equivalent SQL provenance

Tooltips, chart captions, and downloads must reuse the same counting semantics. Do not put metrics with incompatible denominators on a shared scale or imply that they are directly comparable.

### 8.3 Data sources

Build static `summary.json` and aggregate tables from read-only `v_master`, `v_counted`, and the authoritative structure/function/tree tables. The `data_dictionary` table may supply field definitions. Do not display analyses for which no validated source table or query exists.

---

## 9. Search: Text Queries and Sequence Similarity

### 9.1 Universal text search

Support MRDB/source accession, protein name, organism, taxonomy, PDB, motif, and clade identifiers. Show which field matched each result. Offer representative examples and useful suggestions, and route selections to the proper Protein Entry. PDB searches must be backed by `protein_pdb`; never invent or infer PDB identifiers from protein names.

### 9.2 Preserve the scientific limits of sequence search

The current implementation uses a **3-mer prefilter that retains 300 candidates, followed by Smith–Waterman local alignment (BLOSUM62; gap-open penalty 11, gap-extension penalty 1)**. Only the prefiltered candidates receive full alignment scores, and the UI shows the top 10 hits. This is neither an exhaustive local-alignment search nor full membership scoring.

For this redesign:

- Preserve and verify the current algorithm's scientific semantics. If the method changes, give it a new explicit method version and regenerate golden tests.
- Move expensive computation to a Web Worker. Provide progress, cancellation, and error recovery.
- Validate a single FASTA/plain-protein-sequence query, accepted amino-acid symbols, input length, and explanations for excessively long inputs.
- Display rank, identity, query/subject coverage, alignment score, and preferably an interpretable aligned region.
- Disclose prefiltering, top-N truncation, and search limitations. The absence of a result from the top 10 is not proof of sequence absence.
- Point users to `tools/mrdb_search.py` for the **full membership scorer (CLI)**; never fabricate an authoritative membership classification in the browser.
- If in-browser computation fails or the device is underpowered, provide useful fallback guidance and access to downloadable sequences/CLI instructions.

### 9.3 Optional future services (not a release blocker)

Exhaustive DIAMOND/BLAST search, hosted HMMER membership scoring, and online EPA-ng placement require their own infrastructure projects with compute resources, operating costs, security controls, and queueing policies. Static GitHub Pages cannot serve these workloads by itself.

---

## 10. Structure Explorer, Evidence Explorer, Watchlist, and Downloads

### 10.1 Structure Explorer

- Index source records with experimental PDB associations; filter by PDB ID, experimental method, resolution, retinal ligand, functional class, and evidence level.
- Display all PDB associations and allow a representative structure to be selected.
- Link to every associated Protein Entry.
- Include AlphaFold models as a separate predicted-structure filter.
- Keep three different statistics distinct: **unique PDB entries**, **proteins with PDB associations**, and **protein–PDB links**.
- Load Mol* only when a user opens or requests an actual structure view.

### 10.2 Evidence Explorer

- Explore E1–E5, experimental/transfer/inferred/unassigned basis, curated overrides, and function-call conflicts.
- Show evidence basis, PMID/DOI, E2 transfer reference, and relevant flags.
- Explain that E3/E4 functional labels may be inherited and are not calibrated probabilities.
- For conflicting annotations, display `original / decision / caveat`, not only a warning color.
- Provide links to Evidence Methods, LOCO validation, and blind-audit methodology/results.

### 10.3 Novel-family Watchlist

- Preserve the 181 v1.6.0 candidate rows and label them prominently **not admitted to the corpus**.
- Display candidate source, family-HMM flags, Foldseek provenance, screening funnel, and study limitations.
- The Foldseek web-service query lists were capped at 1,000 hits; do not characterize this watchlist as an exhaustive discovery census.
- Redirect or alias the old `#/novel` route.
- Do not add unreviewed membership or evidence annotations to watchlist entries.

### 10.4 Downloads and developer resources

- Provide direct access to the official GitHub Release, verified SQLite archive, TSV/FASTA exports, tree Newick, and reference package.
- Provide `CITATION.cff`, License, methods, data dictionary, CLI/API usage, SHA-256 manifests, and release history.
- Treat missing institutional email, DOI, hosting term, or maintenance details in `README.md`/`MAINTENANCE.md` as `not supplied / pending confirmation` rather than inventing values.
- Validate public download URLs and associate each with the correct release.
- Explain how to cite a specific data release. Never mislabel the website build version as the scientific release version.

---
## 11. Technical Architecture and Data-Build Contract

### 11.1 Recommended technology stack

| Layer | Recommended approach | Rationale |
|---|---|---|
| Frontend | Vite + React + TypeScript | Modular UI, static deployment, strong types |
| Routing | Hash router with a typed route contract | Compatible with `/MicroRhodoDB/site/` |
| Styling / components | Tailwind CSS + accessible base primitives | Responsive design system |
| Data tables | TanStack Table | Sorting, filtering, column selection, pagination |
| Charts | Apache ECharts | Home previews and Statistics |
| Tree viewer | phylotree.js (validate compatibility with a prototype first) | Newick parsing, rectangular/radial layouts, tip interaction |
| Structure viewer | Mol* Viewer (version pinned) | On-demand PDB/AlphaFold visualization |
| Data generation | Python + read-only SQLite SQL | Deterministic JSON, FASTA, tree outputs |
| Unit / E2E tests | Vitest + Playwright + Python pytest | UI behavior and scientific invariants |
| Hosting | GitHub Pages + GitHub Actions | Retain the publicly accessible static website |

If a proposed dependency does not work correctly with the selected React/Vite environment, the agent must document a proof of concept and provide evidence for an alternative. Do not silently replace the approved architecture with another large framework.

### 11.2 Recommended repository layout

```text
MicroRhodoDB/
├── web/                            # New frontend source, separated from scientific data
│   ├── package.json
│   ├── package-lock.json
│   ├── vite.config.ts
│   ├── index.html
│   ├── src/
│   │   ├── app/                    # Router, providers, layout
│   │   ├── components/             # Shared UI, badges, tables
│   │   ├── pages/                  # Home, Browse, Record, Phylogeny, ...
│   │   ├── features/               # Tree, structure, sequence, evidence
│   │   ├── data/                   # Schemas, loaders, validators
│   │   ├── styles/                 # Tokens and design system
│   │   └── workers/                # Sequence search
│   ├── scripts/                    # Website-specific export and build validation
│   └── tests/                      # Vitest + Playwright
├── tools/
│   ├── build_site_v160.py          # Preserve for historical/compatibility purposes
│   └── export_web_data.py          # New version-independent web-data exporter
├── docs/
│   └── WEBSITE_REDESIGN.md         # Implementation, route, data and maintenance guidance
├── refpkg/MR_RT_003/              # Read-only authoritative reference tree
├── releases/                      # Fully immutable
├── site/                          # Published site path required by existing URL
├── index.html                     # Compatible root redirect to site/
└── .github/workflows/deploy-site.yml
```

**Build-artifact policy:** `web/` is the maintained source, and deployment assets are generated separately. Do not allow `site/` to become a second hand-maintained implementation. Keep a documented fallback to the previous browser source or archive it with clear rollback instructions, and define the authoritative new deployment output.

### 11.3 Proposed static data layout and contract

```text
data/v1.6.0/
├── manifest.json                  # Source-release SHA, builder commit, schema, counts
├── summary.json                   # Metrics, denominators, provenance
├── records-index.json             # Lightweight searchable index
├── accessions.json                # MRDB/source mapping and representatives
├── records/
│   └── MRDB000001.json            # Representative/source records, evidence, PDB list
├── sequences/                     # On-demand or chunked sequences
├── structures-index.json
├── evidence-index.json
├── clades.json
├── phylogeny/
│   ├── MR_RT_003.rooted.treefile
│   ├── tips.json
│   ├── clades.json
│   └── robustness.json
├── watchlist.json
└── export_manifest.json
```

Define TypeScript types and JSON Schema (or equivalent runtime validators) for every payload, including required fields, nullable fields, enumerations, data release, IDs, and array uniqueness. Do not conflate `""`, `undefined`, `null`, and a literal `"none"` when they mean different things.

**Performance strategy:** Home initially loads only manifest, summary, and a lightweight tree preview. Browse loads the search index when needed. Protein Entry loads full records and sequences on demand. Structures loads Mol* only when requested. Sequence Search loads its sequence corpus or optimized search index only when visited. Cache and invalidate resources by data release so mixed versions cannot appear.

### 11.4 Required experimental-structure extraction from official SQLite

```sql
-- Illustrative query. Confirm exact schema and add SQL/JSON tests.
SELECT
    pp.source_acc,
    pp.pdb_id,
    ps.method,
    ps.resolution,
    ps.title,
    ps.ligands,
    ps.has_retinal,
    ps.year
FROM protein_pdb AS pp
LEFT JOIN pdb_structure AS ps
  ON ps.pdb_id = pp.pdb_id
ORDER BY pp.source_acc, pp.pdb_id;
```

Also read `structure`, `afdb_model`, and `predicted_structure`. Serialize source-record PDB associations as arrays in per-entry data files. **Restoring only `rep_pdb_id` does not fulfill the requirement to recover missing PDB information.**

### 11.5 Reproducible build requirements

The official SQLite database is not directly tracked in Git. Therefore:

1. Obtain the official database from the v1.6.0 GitHub Release, a verified archive, or an explicitly supplied local path.
2. Verify the official SHA-256 recorded in `BINARIES.md`:
   `379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f`.
3. Open SQLite in **read-only** mode.
4. Generate the static website data from the official release DB and MR_RT_003 reference package.
5. Validate record counts, structure joins, tree tips, statistics denominators, data-release provenance, and record links.
6. Record the input SHA, exporter commit, output manifest, and checksums.
7. Only then build the frontend and deploy to GitHub Pages.

If the authorized official database cannot be obtained, stop the relevant data-build stage and report `BLOCKED_DATA_SOURCE`. Do not reverse-engineer missing PDB fields from stale `site/data.js` and never deploy fake production data.

### 11.6 GitHub Pages URL and artifact layout

Preserve the production URL:

`https://congjianl.github.io/MicroRhodoDB/site/`

The correct Vite asset base is:

`/MicroRhodoDB/site/`

**Not** the common example `/MicroRhodoDB/`. The final Pages artifact must actually contain the `/site/` directory. A root-level `dist/index.html` may preserve the redirect to `site/`.

Recommended procedure:

- Develop in `web/`; produce deployment files under `dist/site/`.
- Publish the `dist/` artifact with GitHub Actions.
- Before changing GitHub Pages from its present deployment source to Actions, verify every relative path with local preview and PR-build artifacts.
- Keep a rollback path to the old site or the previous successful deployment artifact.
- Never overwrite production directly during a PR and never force-push `main` as an unreviewed deployment mechanism.

---

## 12. Implementation Stages and Pull Request Contract

**Mandatory order:** PR-0 through PR-7. Each PR has a bounded scope, deliverables, acceptance evidence, and a review gate. Do not start the next PR until the previous one has been reviewed and accepted.

### PR-0 — Baseline, Data Audit & Architecture Freeze

**Tasks:**

- Verify `HEAD`, current uncommitted user changes, and the live GitHub Pages deployment source.
- Inspect the legacy browser, data-export scripts, existing tests, and v1.6.0 release documentation.
- Locate official SQLite assets, check SHA-256, and record all input/output version identifiers.
- Execute feasible baseline Playwright/release tests and representative source-field comparisons.
- Read-only audit of PDB joins, MRDB-to-source many-to-one mapping, AFDB, reference tree, and clades.
- Finalize this implementation specification, explicit data contracts, and test/acceptance strategy.
- Run limited proofs of concept demonstrating that Mol* and the selected tree library can load **real** assets in the target browser/build environment.
- Do not modify scientific data or deploy the new site.

**Deliverables:** `WEB_BASELINE_AUDIT.md`, `WEB_DATA_CONTRACT.md`, initial snapshots, test inventory, baseline commit.

**Gate G0:** Provenance is identified, official data are verifiable, baseline test status is recorded honestly, missing dependencies are explicit, and all frozen releases remain untouched.

### PR-1 — Deterministic Website Data Export

**Tasks:**

- Implement a new read-only exporter with types, schemas, and validators.
- Export summary, records/accessions, full PDB associations, AFDB, publications, reference tree/clades, and watchlist.
- Validate source-level versus MRDB-level semantics, nullable fields, and many-to-one mapping.
- Generate manifest, provenance, and reproducible outputs.
- Preserve the legacy exporter for regression comparison; avoid ad-hoc aggregation in the browser.
- Prioritize structural and scientific consistency before visual development.

**Deliverables:** `tools/export_web_data.py`, schema/types, golden tests, export documentation, reproducible build commands.

**Gate G1:** Exactly 5,466 source records, 5,299 MRDB accessions, and 5,460 counted records, reconciled against SQLite. PDB sets agree record-by-record; no fabricated structure links; every website field is traceable to v1.6.0.

### PR-2 — Design System, Routing, Home & Browse

**Tasks:**

- Create the React/Vite application and shared UI components under `web/`.
- Implement responsive navigation, homepage hero, universal search, real lightweight tree preview, and statistical overview.
- Implement Browse, filters, proper sorting, semantic record links, and TSV/FASTA exports.
- Maintain hash-route and legacy-site-entry compatibility.
- Perform initial visual QA and semantic-HTML checks.

**Deliverables:** Locally runnable Home and Browse, route tests, desktop/mobile screenshots, UI usage notes.

**Gate G2:** The homepage is coherent, filtering/downloads work correctly, the old `#/` entry resolves appropriately, and core UI flows work with a keyboard and supported viewport widths.

### PR-3 — Standalone Protein Entry & PDB Restoration

**Tasks:**

- Implement standalone Protein Entry pages and all six tabs.
- Correctly represent MRDB/source relationships, WT/engineered variants, curated overrides, and E1–E5 evidence.
- Show every associated PDB ID, PDB metadata, external links, and a lazily loaded Mol* viewer.
- Separate predicted models from experimental structures; handle mismatched and unavailable models explicitly.
- Display complete supporting publications and DOI/PMID associations.
- Regress all existing record permalinks and direct-entry URLs.

**Deliverables:** Complete Record page, PDB/Mol* interactions, HTML/TSV/SQLite reconciliation tests.

**Gate G3:** No PDB IDs are lost. P02945 and all sampled records resolve correctly. Multiple-PDB, no-PDB, predicted-only, engineered, and curated cases behave correctly. No fictitious chain-level residue mapping.

### PR-4 — Phylogeny & Clade Explorer

**Tasks:**

- Render the authentic MR_RT_003 tree.
- Provide rectangular/radial views, search, coloring, tip-to-Record navigation, and subtree/clade pages.
- Show support values, outgroups, and clade robustness caveats.
- Display placement data without portraying them as inferred reference-tree branches.
- Offer real Newick and SVG downloads; reuse the source data for the homepage tree preview.

**Deliverables:** Phylogeny/Clade pages, scientific legends, 472-tip reconciliation, topology and annotation mapping tests.

**Gate G4:** All 472 tips, all 17 level-1 clades, and support annotations reconcile with authoritative sources. Reference tips and placements are never confused.

### PR-5 — Statistics, Evidence, Structures, Watchlist & Search

**Tasks:**

- Implement complete Statistics with metric denominators and provenance.
- Implement Evidence Explorer and Structure Explorer.
- Provide the correctly isolated Novel-family Watchlist.
- Build a unified text-search index.
- Move sequence search to a Worker and improve method warnings, error handling, and result presentations.
- Complete Downloads, Methods, Citation, and Help pages.

**Deliverables:** Real pages for every navigation destination, statistical snapshots, and scientific-boundary tests.

**Gate G5:** Chart totals match source data, watchlist records stay isolated, search golden cases remain valid, and the browser never claims to compute the official complete membership score.

### PR-6 — Accessibility, Performance, Regression & Scientific Audit

**Tasks:**

- Run whole-site Playwright tests, multi-viewport screenshots, keyboard checks, and WCAG AA contrast reviews.
- Verify lazy loading of page data and Mol*; eliminate unnecessary homepage downloads.
- Handle loading, unknown routes, empty states, and third-party failure scenarios gracefully.
- Audit escaping, URL parsing, external-link `rel` attributes, and practical CSP protections.
- Demonstrate zero scientific data drift, and report both legacy and new test results.
- Check links and align `README.md`, `MAINTENANCE.md`, `CITATION.cff`, and website release information.

**Deliverables:** `WEB_ACCEPTANCE_REPORT.md`, E2E results, performance report, scientific-invariant reconciliation, screenshots.

**Gate G6:** Zero open P0/P1 release blockers, zero known production uncaught JavaScript exceptions, direct navigation to all mandatory routes, and unchanged official scientific data checksums.

### PR-7 — Deployment, Rollback & UI Freeze

**Tasks:**

- Configure and validate the deployment workflow.
- Review PR build artifacts and/or a staging preview before publication.
- Merge and deploy only after user approval.
- Smoke-test the publicly accessible homepage, representative entries, PDB links/viewer, Phylogeny, Statistics, FASTA downloads, and Not Found handling.
- Document rollback and long-term site maintenance.
- Report final commit, production URL, test results, and known limitations.

**Deliverables:** Publicly accessible redesigned site, deployment record, rollback instructions.

**Gate G7:** The production site is accessible, existing `#/record/...` permalinks still work, static assets do not return 404, and scientific release contents remain unmodified.

**Stage discipline:** Complete PR-0 → PR-7 in order. Each PR must stay within its defined scope and report evidence, tests, and differences before requesting acceptance. Do not repeatedly overturn accepted designs without evidence. Any new research capability beyond the specification requires a separately scoped change.

---
## 13. Automated Tests and Acceptance Matrix

### 13.1 Data integrity

- The exported `source_acc` set exactly matches the official v1.6.0 database; no silent additions or omissions.
- Every MRDB-to-source accession mapping, including many-to-one relationships, matches SQLite.
- `counts_eligible`, engineered status, curated membership, and E1–E5 denominators are correct.
- The exported PDB links for each source record exactly match `protein_pdb`.
- PDB method, resolution, ligand, retinal-presence flag, and year come from `pdb_structure`.
- Experimental and predicted structures remain separate and never reuse each other's field meanings.
- The rooted MR_RT_003 tree has 472 tips; tip, clade, and annotation data reconcile exactly.
- All 17 level-1 clades are accounted for, without orphan tree/clade/source mappings.
- The 181 watchlist candidates are excluded from the 5,466-record corpus.

### 13.2 Fixed, real-world regression samples

| Test accession / object | Primary checks |
|---|---|
| `MRDB000001` / `P02945` | MRDB/source routes, structure links, publications, FASTA, example sequence search |
| `A0A1I3DJQ0` (CryoR1) | E1 evidence, curated membership override, references |
| `L1K1K8` (GtCCR2) | E1 evidence, curated membership, functional explanation |
| `A0A3G1I4H9` (GtCCR4) | Curated membership and direct evidence |
| `A0ABF7PQ82` (exoKCR1) | Wild type versus engineered construct, E1 evidence |
| `A0ABF7PQA2` (engineered) | Engineered exclusion and wild-type links |
| `A0AAP2RB57` | Schizorhodopsin family flag, conflict, and unassigned semantics |
| `MR_CLD3_017` | Confident/tentative distinctions, functional consensus, robustness caveat |
| DB-selected multi-PDB / no-PDB / AFDB-only entries | Structure arrays, failure handling, missing states |

**Do not** hard-code an assertion that a particular accession must have a particular PDB ID without first checking the official database. Generate structural golden fixtures directly from SQLite.

### 13.3 UI end-to-end testing

- The homepage displays real statistics and a real MR_RT_003 overview.
- Home accession search opens an entry; selecting a reference tip in the tree opens that entry.
- Refreshing any `#/record/...` route produces a full standalone Protein Entry page.
- Browser Back/Forward restores appropriate Browse filters.
- MRDB and source URLs resolve consistently, with the selected source accession clearly identified.
- Multi-PDB selection, successful/failed Mol* loading, external links, and predicted-model loading.
- Clade → filtered Browse → Back navigation.
- Positive sequence-search example: P02945 returns 100% identity; long/invalid inputs and cancellation are handled.
- Filtered TSV/FASTA row counts and content agree with the active filter.
- No page-level horizontal overflow at 375px, 768px, and 1440px; critical interactions remain accessible.
- Citation copying/printing and metadata downloads work as intended.
- Mobile menus, screen-reader labels, keyboard focus, and textual chart alternatives work.

### 13.4 Performance and stability

**Performance targets are goals to be measured in a fixed, documented test environment, not universal guarantees:**

- The initial Home load does not download the full sequence corpus or the Mol* package.
- Target LCP ≤ 2.5s, CLS ≤ 0.1, and INP ≤ 200ms; document the device and network conditions for all measurements.
- Initial JS/CSS/summary transfer size is materially lower than the current monolithic ~4.35 MB JavaScript data payload; report real gzip/brotli sizes and a loading waterfall.
- Search computation must not continuously block main-thread UI interactions.
- Failure of a background or third-party data request must not disable already loaded parts of the site.
- Pin third-party dependencies; do not depend on unversioned CDN `latest` assets.

### 13.5 Fail-fast scientific acceptance blockers

Any of the following conditions is a **BLOCKER**:

1. A frozen database, scientific release artifact, reference package, or threshold has been modified.
2. The website invents functional labels, PDB IDs, experimental properties, or phylogenetic topology on visual or heuristic grounds.
3. Reference-tree reconstruction is conflated with sequence placement.
4. Membership status is conflated with evidence level.
5. Counted E1 versus total E1, or watchlist versus corpus, has an incorrect denominator.
6. Existing record permalinks break, or FASTA/TSV download functionality regresses.
7. Stable URLs map source accessions to the wrong proteins.
8. Missing official SQLite inputs cause an undocumented fallback to stale `site/data.js`.
9. The 3-mer plus Smith–Waterman browser search is presented as an exhaustive database membership detector or official classifier.

---

## 14. GitHub Pages Deployment, Rollback, and Maintenance

1. Verify the existing Pages source (branch/root or Actions), custom-domain/CNAME status, and root `index.html` redirect.
2. Set Vite `base` to `/MicroRhodoDB/site/`, and ensure the deployment artifact contains assets at that exact `site/` path.
3. Suggested GitHub Actions sequence: `npm ci` → validate locked dependencies → obtain/read authenticated or otherwise verified static inputs → pass exporter integrity gates → `npm run build` → Playwright smoke tests → publish Pages artifact.
4. If GitHub Actions cannot securely retrieve the official GitHub Release binary, include **provenance-bearing pre-generated static data** in the versioned deployment artifact, rather than fabricating fields at runtime. Document the precise build-data dependency.
5. Provide screenshots, a static preview URL, or an inspectable artifact before merging. Do not switch production without user approval.
6. Preserve a rollback build of the old website; after deploying, smoke-test the fixed real accessions and structure links.
7. Every future scientific database release must trigger fresh data export, checksum verification, and all website data-consistency tests.
8. Complete the About, Methods, Citation, License, Contact, and Maintenance information. Never invent a DOI, institutional email, hosting term, or other unresolved metadata.

### Development invariants

- Preserve all existing uncommitted work in the repository.
- Keep all official scientific releases and original reference-package files byte-identical.
- Each PR must report its commit(s), changed files, test results, UI screenshots when applicable, and unresolved issues.
- Do not automatically upgrade website or tool dependencies to untested versions.
- Do not add unsupported functional predictions or measurements merely to make a page appear richer.
- A new UI version may be called `website 2.0` while explicitly retaining `dataset v1.6.0`; the two version numbers have different meanings.

---

## 15. Required Deliverables

```text
docs/website/
  WEBSITE_REDESIGN_SPEC.md
  IA_AND_ROUTES.md
  DESIGN_SYSTEM.md
  WEB_DATA_CONTRACT.md
  PDB_STRUCTURE_MAPPING.md
  PHYLOGENY_DISPLAY_SPEC.md
  EVIDENCE_AND_STATISTICS_DENOMINATORS.md
  WEB_BUILD_AND_DEPLOY.md
  WEB_ACCEPTANCE_REPORT.md
  WEB_KNOWN_LIMITATIONS.md

web/
  # React/Vite/TypeScript application, components, types, tests, build configuration

tools/export_web_data.py

.github/workflows/deploy-site.yml
```

The implementation may consolidate related documentation into fewer files to match established repository conventions, but it must retain the equivalent substance. The root `README.md` must contain executable commands covering **development, local preview, build, validation, and deployment**.

**The agent's final acceptance response must include at least:**

- Baseline commit, final commit, branch and/or PR identifiers.
- Production website URL and complete route list.
- Source SQLite SHA-256, tree checksum, and data release.
- Verification that original releases and reference-package sources remain unchanged.
- Implementation-status matrix: `done`, `deferred`, or `blocked`.
- Critical data reconciliation: PDB links, MRDB/source accessions, 472 reference tips, and statistical denominators.
- Unit tests, Playwright, browser console, performance, and accessibility results.
- Known limitations and production rollback instructions.
- Representative screenshots or working preview links.

---

## 16. Master Instruction for Codex / Development Agents

> Read `docs/website/WEBSITE_REDESIGN_SPEC.md` and treat it as the approved implementation contract for a full MicroRhodoDB website redesign. The underlying scientific dataset is the immutable MicroRhodoDB v1.6.0 SQLite release, and the authoritative phylogeny is MR_RT_003. First perform PR-0 as a read-only baseline and data-contract audit: inspect the current repository, GitHub Pages routing, current test coverage, authoritative release binaries and SHA-256, PDB tables, MRDB/source accession mapping, tree/refpkg and existing UI. Report missing dependencies and preserve all user work. Implement the new website through isolated PRs, in the exact stage order PR-0 to PR-7, stopping for review after each stage. Build a professional, responsive scientific database portal with a real Home page, independent Protein Entry routes, complete PDB and AlphaFold structure handling, Mol* structure viewer, MR_RT_003 phylogeny explorer, validated statistics, evidence explorer, advanced Browse, search, downloads and documentation. Use a reproducible, read-only SQLite-to-static-data export pipeline and explicit scientific integrity tests. Do not modify frozen releases, scientific annotations, membership thresholds, functions, phylogeny, or source records. Preserve existing record permalinks and GitHub Pages `/MicroRhodoDB/site/` URL. Do not invent PDB structures, functional measurements, placement branches or evidence confidence. Produce a per-PR evidence report, tests and screenshots; promote to production only after final acceptance.

**Immediate next action:** Execute **PR-0 only**. Produce the baseline audit and architecture/data contracts, then stop and request review. Do not begin PR-1 automatically.

---

## 17. Official Technical Resources and Design References

- MicroRhodoDB repository: https://github.com/CongjianL/MicroRhodoDB
- Current MicroRhodoDB website: https://congjianl.github.io/MicroRhodoDB/site/#/
- Current data model: https://github.com/CongjianL/MicroRhodoDB/blob/main/docs/DATA_MODEL.md
- MR_RT_003 reference package: https://github.com/CongjianL/MicroRhodoDB/tree/main/refpkg/MR_RT_003
- MicroRhodoDB binary-release policy: https://github.com/CongjianL/MicroRhodoDB/blob/main/BINARIES.md
- Vite / GitHub Pages static deployment: https://vite.dev/guide/static-deploy.html
- Mol* embedding: https://molstar.org/docs/plugin/instance/
- phylotree.js: https://github.com/veg/phylotree.js/
- InterPro sequence viewer: https://interpro-documentation.readthedocs.io/en/latest/protein_viewer.html
- RCSB sequence-coordinate mapping: https://github.com/rcsb/rcsb-sequence-coordinates
- UniProt: https://www.uniprot.org/
- InterPro: https://www.ebi.ac.uk/interpro/
- RCSB PDB: https://www.rcsb.org/
- GPCRdb: https://gpcrdb.org/

**Overall implementation conclusion:** Restore scientifically complete data export and standalone Protein Entries first; build a genuine Home/Phylogeny/Statistics experience next; and develop integrated sequence–structure–function and evidence exploration as the defining research features of MicroRhodoDB.
