-- MicroRhodoDB v1.5.0 authoritative schema (curated build, curator sign-off 2026-10-06)
CREATE TABLE "accession_map" (
"mrdb_acc" TEXT,
  "source_acc" TEXT,
  "source_database" TEXT,
  "release_added" TEXT,
  "is_current" INTEGER
);

CREATE TABLE "afdb_model" (
"source_acc" TEXT,
  "model_id" TEXT,
  "status" TEXT,
  "version" REAL,
  "global_plddt" REAL,
  "seq_match" INTEGER,
  "seq_start" REAL,
  "seq_end" REAL,
  "model_url" TEXT,
  "model_created" TEXT
);

CREATE TABLE "assertion_publication" (
"assertion_id" INTEGER,
  "publication_id" INTEGER,
  "source_acc" TEXT,
  "assertion" TEXT,
  "verdict" TEXT,
  "corrected_field" TEXT,
  "corrected_value" TEXT,
  "evidence_basis" TEXT,
  "snippet" TEXT,
  "checked_at" TEXT,
  "caveat" TEXT,
  "snippet_verified_in_retrieved_text" INTEGER,
  "is_active" INTEGER,
  "counts_as_support" INTEGER,
  "link_role" TEXT,
  "curator_decision" TEXT,
  "curator_note" TEXT,
  "decided_by" TEXT,
  "decided_at" TEXT,
  "replaces_publication_id" TEXT
);

CREATE TABLE benchmark_v2 (
    source_acc  TEXT NOT NULL,
    is_positive INTEGER CHECK(is_positive IN (0,1)),
    provenance  TEXT,
    task        TEXT,
    score_full  REAL,
    score_loco  REAL,
    score_loso  REAL,
    cluster     TEXT
);

CREATE TABLE "build_provenance" (
"table_name" TEXT,
  "source_data" TEXT,
  "script" TEXT,
  "algorithm" TEXT,
  "params" TEXT,
  "upstream_deps" TEXT,
  "release" TEXT,
  "built_at" TEXT
);

CREATE TABLE "characterized_protein" (
"source_acc" TEXT,
  "organism" TEXT,
  "protein_label" TEXT,
  "exp_function_class" TEXT,
  "ion" TEXT,
  "direction" TEXT,
  "assay_type" TEXT,
  "lambda_max_nm" REAL,
  "lambda_max_conditions" TEXT,
  "photocycle_note" TEXT,
  "doi" TEXT,
  "pmid" TEXT,
  "evidence_basis" TEXT,
  "snippet" TEXT,
  "mapping_identity" TEXT,
  "in_tierA" INTEGER,
  "exp_class" TEXT,
  "exp_class_basis" TEXT,
  "v150_corrected_fields" TEXT,
  "v150_original_values" TEXT,
  "v150_curation_note" TEXT,
  "membership_status_v150" TEXT,
  "ms210" TEXT,
  "conflict" TEXT,
  "e1_eligible" INTEGER,
  "e1_exclusion_reason" TEXT
);

CREATE TABLE citation (
    ref_id      INTEGER PRIMARY KEY,
    citation    TEXT,
    doi         TEXT,
    context     TEXT
);

CREATE TABLE "clade" (
"clade_id" TEXT,
  "level" INTEGER,
  "parent_clade_id" TEXT,
  "n_tips" INTEGER,
  "ufboot" REAL,
  "sh_alrt" REAL,
  "dominant_subfamily_v14" TEXT,
  "dominant_helixC_motif" TEXT,
  "dominant_domain" TEXT,
  "dominant_phylum" TEXT,
  "e1_classes_tips" TEXT,
  "name" TEXT,
  "naming_basis" TEXT,
  "n_records_assigned" INTEGER,
  "n_E1" INTEGER,
  "top_frac" REAL,
  "consensus_status" TEXT,
  "e1_function_consensus" TEXT,
  "e1_classes_records" TEXT,
  "tree_id" TEXT,
  "scheme" TEXT,
  "jaccard_run2" REAL,
  "jaccard_run3" REAL,
  "jaccard_midpoint_rooting" REAL,
  "min_cross_replicate_jaccard" REAL
);

CREATE TABLE "clade_crosswalk" (
"clade_id" TEXT,
  "scheme" TEXT,
  "other_id" TEXT,
  "n_shared" INTEGER,
  "frac_of_mr_cld3" REAL,
  "frac_of_other" REAL,
  "level" TEXT,
  "parent_clade_id" TEXT
);

CREATE TABLE "clade_robustness" (
"tree" TEXT,
  "rooting" TEXT,
  "min_size" INTEGER,
  "max_size" INTEGER,
  "ufb" INTEGER,
  "alrt" INTEGER,
  "n_clades" INTEGER,
  "n_tips_in_clades" INTEGER,
  "ari_vs_primary" REAL,
  "median_best_jaccard" REAL,
  "frac_primary_clades_recovered_j1" REAL,
  "frac_primary_clades_j_ge_0_8" REAL
);

CREATE TABLE "clade_tip" (
"source_acc" TEXT,
  "clade_id" TEXT,
  "subclade_id" TEXT,
  "tree_id" TEXT
);

CREATE TABLE "curator_spotcheck_decision" (
"row_id" INTEGER,
  "batch" INTEGER,
  "item_type" TEXT,
  "source_acc" TEXT,
  "assertion_id" REAL,
  "publication_id" REAL,
  "sheet_verdict" TEXT,
  "decision" TEXT,
  "field" TEXT,
  "new_value" TEXT,
  "curator_note" TEXT,
  "decided_by" TEXT,
  "decided_at" TEXT,
  "approval" TEXT
);

CREATE TABLE extension_delta (
    accession   TEXT PRIMARY KEY,
    delta_class TEXT NOT NULL CHECK(delta_class IN ('new','sequence_changed','demoted_or_merged')),
    family_hint TEXT,
    detail      TEXT
);

CREATE TABLE "external_validation" (
"ext_acc" TEXT,
  "database" TEXT,
  "organism" TEXT,
  "protein_label" TEXT,
  "family" TEXT,
  "function_desc" TEXT,
  "evidence" TEXT,
  "deposition_or_pub_year" REAL,
  "length" INTEGER,
  "is_partial" INTEGER,
  "sequence_sha256" TEXT,
  "nearest_corpus_acc" TEXT,
  "max_identity_to_corpus" REAL,
  "query_cov" REAL,
  "distance_class" TEXT,
  "inclusion_rationale" TEXT,
  "is_positive" INTEGER,
  "negative_class" TEXT,
  "freeze_sha256" TEXT,
  "mr_rt_003_clade_id" TEXT,
  "mr_rt_003_subclade_id" TEXT,
  "clade_lwr" REAL,
  "mr_rt_003_call" TEXT,
  "lwr_weighted_pendant" REAL,
  "membership_score_frozen_scorer" REAL,
  "gate_has_domain" INTEGER,
  "is_helio_primary" INTEGER
);

CREATE TABLE "external_validation_metric" (
"set" TEXT,
  "method" TEXT,
  "n_pos" INTEGER,
  "n_neg" INTEGER,
  "auprc" REAL,
  "auprc_lo" REAL,
  "auprc_hi" REAL,
  "roc_auc" REAL,
  "d_auprc_full_minus_method" REAL,
  "d_lo" REAL,
  "d_hi" REAL,
  "brier" REAL,
  "ece10" REAL
);

CREATE TABLE "external_validation_operating_point" (
"set" TEXT,
  "method" TEXT,
  "threshold" REAL,
  "metric" TEXT,
  "k" INTEGER,
  "n" INTEGER,
  "value" REAL,
  "ci_lo" REAL,
  "ci_hi" REAL,
  "ci_method" TEXT
);

CREATE TABLE "external_validation_stratum" (
"cls" TEXT,
  "stratum" TEXT,
  "threshold" REAL,
  "metric" TEXT,
  "k" INTEGER,
  "n" INTEGER,
  "value" REAL,
  "ci_lo" REAL,
  "ci_hi" REAL
);

CREATE TABLE "func_class_definition" (
"func_class" TEXT,
  "definition" TEXT,
  "n_records" INTEGER
);

CREATE TABLE "function_evidence" (
"source_acc" TEXT,
  "func_class" TEXT,
  "evidence_level" TEXT,
  "basis" TEXT,
  "helixC_motif" TEXT,
  "motif_class" TEXT,
  "exp_class" TEXT,
  "e2_ref" TEXT,
  "e2_identity" REAL,
  "clade_id" TEXT,
  "clade_function" TEXT,
  "override_rule" TEXT,
  "func_class_v14" TEXT
);

CREATE TABLE "gtdb_taxonomy" (
"source_acc" TEXT,
  "organism" TEXT,
  "organism_id" INTEGER,
  "tax_domain" TEXT,
  "gtdb_taxonomy" TEXT,
  "gtdb_agreement" REAL,
  "gtdb_n_genomes" INTEGER,
  "gtdb_match_level" TEXT,
  "gtdb_release" TEXT,
  "gtdb_d" TEXT,
  "gtdb_p" TEXT,
  "gtdb_c" TEXT,
  "gtdb_o" TEXT,
  "gtdb_f" TEXT,
  "gtdb_g" TEXT,
  "gtdb_s" TEXT
);

CREATE TABLE holdout_assignment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    regime TEXT NOT NULL,              -- random5 | std_90 | intermediate_65 | taxonomic_phylum | reference_clade
    fold_id TEXT NOT NULL,             -- cluster id / phylum name / random fold label
    source_acc TEXT NOT NULL,
    role TEXT NOT NULL,                -- held_out_positive | eval_negative
    excluded_seeds TEXT,               -- JSON list of seeds removed from the seed set in this fold
    score_full REAL,                   -- frozen-model score with the full 15-seed set
    score_fold REAL,                   -- score under this fold's reduced seed set
    e_hom_full REAL,
    e_hom_fold REAL,
    UNIQUE(regime, fold_id, source_acc)
);

CREATE TABLE "holdout_metric" (
"regime" TEXT,
  "method" TEXT,
  "n_pos" INTEGER,
  "n_neg" INTEGER,
  "auprc" REAL,
  "auprc_lo" REAL,
  "auprc_hi" REAL,
  "roc_auc" REAL,
  "d_auprc_full_minus_method" REAL,
  "d_lo" REAL,
  "d_hi" REAL,
  "brier" REAL,
  "ece10" REAL
);

CREATE TABLE "holdout_operating_point" (
"regime" TEXT,
  "method" TEXT,
  "threshold" REAL,
  "metric" TEXT,
  "k" INTEGER,
  "n" INTEGER,
  "value" REAL,
  "ci_lo" REAL,
  "ci_hi" REAL,
  "ci_method" TEXT
);

CREATE TABLE "legacy_active_population_v14" (
            source_acc TEXT PRIMARY KEY REFERENCES protein(source_acc),
            membership_status TEXT NOT NULL,
            policy_class TEXT NOT NULL,
            is_active INTEGER NOT NULL CHECK(is_active IN (0,1)),
            is_core INTEGER NOT NULL CHECK(is_core IN (0,1)),
            is_candidate INTEGER NOT NULL CHECK(is_candidate IN (0,1))
        );

CREATE TABLE "legacy_assertion_publication_v14" (
    assertion_id   INTEGER NOT NULL REFERENCES tier_a_assertion(assertion_id),
    publication_id INTEGER NOT NULL REFERENCES "legacy_publication_v14"(publication_id),
    PRIMARY KEY (assertion_id, publication_id)
);

CREATE TABLE "legacy_external_validation_metric_v14" (
"metric_id" INTEGER,
  "stratum" TEXT,
  "threshold" REAL,
  "metric" TEXT,
  "value" REAL,
  "ci_lo" REAL,
  "ci_hi" REAL,
  "ci_method" TEXT,
  "n_pos" INTEGER,
  "n_neg" INTEGER,
  "note" TEXT
);

CREATE TABLE "legacy_external_validation_v14" (
    ext_id               INTEGER PRIMARY KEY,
    source_acc           TEXT NOT NULL,           -- INSDC/UniProt accession (may be external to protein table)
    sequence_sha256      TEXT NOT NULL,           -- exact-sequence hash (exposure audit key)
    stratum              TEXT NOT NULL CHECK(stratum IN ('E1','E2','EXT_NEG')),
    is_positive          INTEGER NOT NULL CHECK(is_positive IN (0,1)),
    negative_class       TEXT,                    -- for negatives: animal_typeII_opsin / GPCR_classA / etc.
    family               TEXT,                    -- for positives: GHR / schizorhodopsin / etc.
    motif                TEXT,                    -- TM3 motif where known
    function_desc        TEXT,                    -- experimentally demonstrated function
    evidence_level       TEXT,                    -- experimental_assay / experimental_structure
    assay_type           TEXT,
    doi                  TEXT,
    pmid                 TEXT,
    deposition_date      TEXT,                    -- ISO date of deposition/publication
    organism             TEXT,
    length               INTEGER,
    is_partial           INTEGER CHECK(is_partial IN (0,1)),
    is_edge_case         INTEGER CHECK(is_edge_case IN (0,1)),
    -- exposure audit (eligibility): all must demonstrate independence
    nearest_corpus_acc   TEXT,                    -- nearest v1.2 corpus neighbour (MMseqs2)
    max_identity_to_corpus REAL,                  -- % identity to that neighbour (recorded, not auto-excluding)
    distance_class       TEXT CHECK(distance_class IN ('distant','moderate','near_duplicate') OR distance_class IS NULL),
    exposure_audit_json  TEXT NOT NULL,           -- machine-readable audit: which dev sets checked, all clear
    ever_exposed_flag    INTEGER NOT NULL DEFAULT 0 CHECK(ever_exposed_flag IN (0,1)),
    inclusion_rationale  TEXT,
    frozen_at            TEXT,                    -- ISO timestamp; record is immutable after this
    -- frozen-model output (scored with the unchanged v1.2 model)
    membership_score     REAL,
    membership_category  TEXT
);

CREATE TABLE "legacy_function_assignment_v14" (
    assignment_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    source_acc       TEXT NOT NULL REFERENCES protein(source_acc),
    func_class       TEXT,
    rule_id          TEXT,
    motif_support    INTEGER CHECK(motif_support IN (0,1)),
    phylogenetic_support INTEGER CHECK(phylogenetic_support IN (0,1)),
    structural_support INTEGER CHECK(structural_support IN (0,1)),
    experimental_support INTEGER CHECK(experimental_support IN (0,1)),
    discordance      INTEGER CHECK(discordance IN (0,1)),
    confidence       TEXT,
    is_active        INTEGER NOT NULL CHECK(is_active IN (0,1)),
    basis            TEXT,
    annotation_version TEXT
);

CREATE TABLE "legacy_function_v14" (
    source_acc          TEXT PRIMARY KEY REFERENCES protein(source_acc),
    res_D85 TEXT, res_T89 TEXT, res_D96 TEXT,
    helixC_motif        TEXT,
    motif_complete      INTEGER CHECK(motif_complete IN (0,1)),
    res_K216            TEXT,
    has_retinal_lysine_qc INTEGER,
    res_105             TEXT,
    func_class          TEXT,
    func_confidence     TEXT,
    func_evidence       TEXT,
    motif_class         TEXT,
    motif_agrees        INTEGER CHECK(motif_agrees IN (0,1)),
    func_basis          TEXT,
    function_is_inferred INTEGER CHECK(function_is_inferred IN (0,1)),
    spectral_class      TEXT,
    lambda_max_pred_nm  REAL,
    lambda_max_is_predicted INTEGER CHECK(lambda_max_is_predicted IN (0,1)),
    lambda_max_measured_nm REAL,
    spectral_confidence TEXT,
    spectral_basis      TEXT
);

CREATE TABLE "legacy_holdout_metric_v14" (
"id" INTEGER,
  "regime" TEXT,
  "level" TEXT,
  "fold_id" TEXT,
  "metric" TEXT,
  "value" REAL,
  "ci_lo" REAL,
  "ci_hi" REAL,
  "n_pos" INTEGER,
  "n_neg" INTEGER,
  "tp" REAL,
  "fp" REAL,
  "fn" REAL,
  "tn" REAL,
  "adequate" INTEGER,
  "note" TEXT,
  "ci_method" TEXT
);

CREATE TABLE "legacy_membership_v14" (
    source_acc          TEXT PRIMARY KEY REFERENCES protein(source_acc),
    membership_category TEXT,
    membership_score    REAL CHECK(membership_score BETWEEN 0 AND 1),
    module              TEXT,  -- DEPRECATED: never controls membership/active status
    membership_status   TEXT NOT NULL CHECK(membership_status IN (
        'typeI_core','typeI_core_architecture_supported','typeI_candidate',
        'typeI_candidate_architecture_supported','typeI_candidate_unresolved',
        'heliorhodopsin','decoy_or_rejected')),
    architecture_class  TEXT,
    arch_route          TEXT,
    reason_code         TEXT
);

CREATE TABLE "legacy_placement_rt001" (
    source_acc     TEXT NOT NULL REFERENCES protein(source_acc),
    track          TEXT CHECK(track IN ('primary','exploratory')),
    best_edge      TEXT,
    best_lwr       REAL CHECK(best_lwr BETWEEN 0 AND 1),
    n_credible     INTEGER,
    dispersion     REAL,
    pendant_length REAL,
    distal_length  REAL,
    placement_status TEXT,
    can_generate_active_label INTEGER NOT NULL CHECK(can_generate_active_label IN (0,1)),
    clade_id       TEXT
);

CREATE TABLE "legacy_placement_rt002" (
    id               INTEGER PRIMARY KEY,
    source_acc       TEXT NOT NULL,
    tree_id          TEXT NOT NULL REFERENCES reference_tree(tree_id),
    best_edge        TEXT,
    best_lwr         REAL,
    n_credible       INTEGER,
    dispersion       REAL,
    pendant_length   REAL,
    distal_length    REAL,
    placement_status TEXT,
    clade_id         TEXT
);

CREATE TABLE "legacy_publication_v14" (
    publication_id INTEGER PRIMARY KEY AUTOINCREMENT,
    doi       TEXT,
    pmid      TEXT,
    title     TEXT,
    journal   TEXT,
    year      TEXT,
    raw_ref   TEXT
, ingestion TEXT
    CHECK (ingestion IN ('parsed_heuristic', 'manual_verified', 'structured_id')));

CREATE TABLE "legacy_reference_backbone_rt001" (
    representative   TEXT PRIMARY KEY,
    cluster          TEXT,
    n_members        INTEGER,
    n_taxdom         INTEGER,
    n_arch           INTEGER,
    diversity_retained INTEGER CHECK(diversity_retained >= 0),
    is_anchor        INTEGER CHECK(is_anchor IN (0,1))
);

CREATE TABLE "legacy_reference_clade_cld2" (
    clade_id        TEXT PRIMARY KEY,
    n_tips          INTEGER,
    n_tierA_anchors INTEGER,
    anchor_members  TEXT,  -- DEPRECATED free text; normalized into reference_clade_member
    tree_node_id    TEXT,
    edge_id         TEXT,
    parent_clade_id TEXT
);

CREATE TABLE "legacy_reference_clade_member_cld2" (
    clade_id   TEXT NOT NULL REFERENCES "legacy_reference_clade_cld2"(clade_id),
    source_acc TEXT NOT NULL,
    PRIMARY KEY (clade_id, source_acc)
);

CREATE TABLE "legacy_reference_clade_tip_cld2" (
    clade_id TEXT, source_acc TEXT, PRIMARY KEY (clade_id, source_acc));

CREATE TABLE "legacy_subfamily_assignment_v14" (
    assignment_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    source_acc       TEXT NOT NULL REFERENCES protein(source_acc),
    subfamily        TEXT,
    method           TEXT,
    track            TEXT CHECK(track IN ('primary','exploratory')),
    confidence       TEXT,
    best_lwr         REAL CHECK(best_lwr BETWEEN 0 AND 1),
    clade_id         TEXT,
    nearest_neighbor_distance REAL,
    is_active        INTEGER NOT NULL CHECK(is_active IN (0,1)),
    annotation_version TEXT,
    created_at       TEXT
);

CREATE TABLE "legacy_subfamily_v14" (
    source_acc          TEXT PRIMARY KEY REFERENCES protein(source_acc),
    subfamily           TEXT,
    assignment_method   TEXT,
    assignment_basis    TEXT,
    best_lwr            REAL CHECK(best_lwr BETWEEN 0 AND 1),
    edge_subfamily_purity REAL,
    tree_discordant     INTEGER CHECK(tree_discordant IN (0,1))
);

CREATE TABLE "membership" (
"source_acc" TEXT,
  "membership_status" TEXT,
  "alias_v14" TEXT,
  "boundary_subtype" TEXT,
  "status_reason" TEXT,
  "status_reason_v14" TEXT,
  "score_category_v14" TEXT,
  "membership_score" REAL,
  "architecture_class" TEXT,
  "arch_route" TEXT,
  "retinal_site_residue" TEXT,
  "covers_TM7" INTEGER,
  "nearest_fulllength_homolog" TEXT,
  "homolog_identity" REAL,
  "provisional_inference" TEXT,
  "mrdb_acc" TEXT
);

CREATE TABLE "motif_benchmark" (
"call" TEXT,
  "exp_class" TEXT,
  "n" INTEGER,
  "n_assigned" INTEGER,
  "coverage" REAL,
  "cov_lo" REAL,
  "cov_hi" REAL,
  "n_correct" INTEGER,
  "precision" REAL,
  "prec_lo" REAL,
  "prec_hi" REAL,
  "ci_method" TEXT
);

CREATE TABLE "mrdb_accession" (
"mrdb_acc" TEXT,
  "sequence_sha256" TEXT,
  "representative_source_acc" TEXT,
  "first_release" TEXT,
  "n_source_records" INTEGER
);

CREATE TABLE pdb_structure (
    pdb_id      TEXT PRIMARY KEY,
    method      TEXT,
    resolution  REAL,
    title       TEXT,
    ligands     TEXT,
    has_retinal INTEGER CHECK(has_retinal IN (0,1)),
    year        TEXT
);

CREATE TABLE "placement" (
"tree_id" TEXT,
  "source_acc" TEXT,
  "model_tag" TEXT,
  "best_edge" TEXT,
  "best_lwr" REAL,
  "best_pendant" REAL,
  "clade_id" TEXT,
  "clade_lwr" REAL,
  "subclade_id" TEXT,
  "subclade_lwr" REAL,
  "n_credible95" INTEGER,
  "lwr_weighted_pendant" REAL,
  "clade_call" TEXT,
  "subclade_call" TEXT,
  "placement_qc" TEXT,
  "clade_call_qc" TEXT,
  "is_current" INTEGER,
  "track" TEXT
);

CREATE TABLE "placement_model_sensitivity" (
"primary" TEXT,
  "alternative" TEXT,
  "n" INTEGER,
  "frac_same_best_edge" REAL,
  "frac_same_clade_all" REAL,
  "n_assigned_either" INTEGER,
  "frac_same_clade_among_assigned" REAL,
  "n_clade_changed_among_assigned" INTEGER,
  "frac_same_subclade" REAL
);

CREATE TABLE predicted_structure (
    source_acc      TEXT PRIMARY KEY REFERENCES protein(source_acc),
    method          TEXT,
    mean_plddt      REAL,
    pdb_file        TEXT,
    subfamily       TEXT,
    note            TEXT
);

CREATE TABLE protein (
    source_acc      TEXT PRIMARY KEY,
    sequence        TEXT NOT NULL,
    length          INTEGER CHECK(length > 0),
    organism        TEXT,
    organism_id     INTEGER,
    tax_domain      TEXT,
    lineage         TEXT,
    protein_name    TEXT,
    reviewed        INTEGER CHECK(reviewed IN (0,1)),
    is_seed         INTEGER CHECK(is_seed IN (0,1)),
    pfam            TEXT,
    pdb             TEXT,
    kegg            TEXT,
    refseq          TEXT
, mrdb_acc TEXT, sequence_sha256 TEXT);

CREATE TABLE protein_architecture_flag (
    source_acc  TEXT NOT NULL REFERENCES protein(source_acc),
    flag        TEXT NOT NULL,
    PRIMARY KEY (source_acc, flag)
);

CREATE TABLE protein_pdb (
    source_acc  TEXT NOT NULL REFERENCES protein(source_acc),
    pdb_id      TEXT NOT NULL REFERENCES pdb_structure(pdb_id),
    PRIMARY KEY (source_acc, pdb_id)
);

CREATE TABLE "publication" (
"publication_id" INTEGER,
  "doi" TEXT,
  "pmid" REAL,
  "title" TEXT,
  "journal" TEXT,
  "year" INTEGER,
  "raw_ref" TEXT,
  "ingestion" TEXT,
  "doi_resolves" INTEGER,
  "doi_corrected" TEXT,
  "crossref_title" TEXT,
  "crossref_journal" TEXT,
  "crossref_year" REAL,
  "crossref_first_author" TEXT,
  "first_author_match" INTEGER,
  "year_match" INTEGER,
  "verdict_summary" TEXT,
  "notes" TEXT,
  "title_v150" TEXT,
  "journal_v150" TEXT,
  "year_v150" INTEGER,
  "ingestion_v150" TEXT
);

CREATE TABLE qc_feature (
    source_acc      TEXT PRIMARY KEY REFERENCES protein(source_acc),
    hmm_cov         REAL CHECK(hmm_cov BETWEEN 0 AND 1),
    has_retinal_lysine INTEGER CHECK(has_retinal_lysine IN (0,1)),
    complete_core   INTEGER CHECK(complete_core IN (0,1)),
    arch_primary    TEXT,
    arch_flags      TEXT  -- DEPRECATED free-text; normalized into protein_architecture_flag
);

CREATE TABLE qc_feature_tool (
    source_acc TEXT PRIMARY KEY REFERENCES qc_feature(source_acc),
    tool       TEXT NOT NULL,
    version    TEXT NOT NULL,
    note       TEXT
);

CREATE TABLE "record_clade" (
"source_acc" TEXT,
  "clade_id" TEXT,
  "subclade_id" TEXT,
  "source" TEXT,
  "clade_lwr" REAL,
  "clade_call" TEXT,
  "e1_class_this_record" TEXT,
  "clade_function" TEXT,
  "clade_function_source" TEXT
);

CREATE TABLE redundancy (
    source_acc          TEXT PRIMARY KEY REFERENCES protein(source_acc),
    module              TEXT,
    exact_nr_cluster    TEXT, exact_nr_is_rep INTEGER CHECK(exact_nr_is_rep IN (0,1)),
    std_90_cluster      TEXT, std_90_is_rep INTEGER CHECK(std_90_is_rep IN (0,1)),
    intermediate_cluster TEXT, intermediate_is_rep INTEGER CHECK(intermediate_is_rep IN (0,1)),
    backbone_cluster    TEXT, backbone_is_rep INTEGER CHECK(backbone_is_rep IN (0,1))
);

CREATE TABLE "reference_tree" (
"tree_id" TEXT,
  "n_tips" INTEGER,
  "method" TEXT,
  "model" TEXT,
  "log_likelihood" REAL,
  "treefile_md5" TEXT,
  "unrooted" INTEGER,
  "status" TEXT,
  "note" TEXT
);

CREATE TABLE "release_metadata" (
"release" TEXT,
  "key" TEXT,
  "value" TEXT
);

CREATE TABLE "retinal_pocket" (
"source_acc" TEXT,
  "br_position" INTEGER,
  "pf01036_match_state" INTEGER,
  "residue" TEXT,
  "seq_position" REAL,
  "afdb_plddt" REAL
);

CREATE TABLE "retinal_pocket_summary" (
"source_acc" TEXT,
  "pocket_string_br" TEXT,
  "n_pocket_observed" INTEGER,
  "has_afdb_model" INTEGER,
  "pocket_mean_plddt" REAL,
  "pocket_min_plddt" REAL
);

CREATE TABLE "route3_candidate_support" (
"source_acc" TEXT,
  "membership_status_v150" TEXT,
  "alias_v14" TEXT,
  "boundary_subtype" REAL,
  "status_reason" REAL,
  "status_reason_v14" REAL,
  "membership_category" TEXT,
  "membership_score" REAL,
  "architecture_class" TEXT,
  "arch_route" TEXT,
  "ms210" TEXT,
  "covers_TM7" INTEGER,
  "nearest_fulllength_homolog" REAL,
  "homolog_identity" REAL,
  "provisional_inference" REAL,
  "clade_call_qc" TEXT,
  "clade_id" TEXT,
  "clade_lwr" REAL,
  "lwr_weighted_pendant" REAL,
  "placement_supports_membership" INTEGER,
  "strict_subset_154" INTEGER,
  "basis" TEXT
);

CREATE TABLE seed (
    acc          TEXT PRIMARY KEY,
    subfamily    TEXT,
    func_class   TEXT
);

CREATE TABLE sequence_source (
    source_acc       TEXT PRIMARY KEY REFERENCES protein(source_acc),
    source_database  TEXT NOT NULL,        -- UniProt | MGnify | GEM (future)
    source_release   TEXT,
    source_accession TEXT,
    study_id         TEXT,
    sample_id        TEXT,
    assembly_id      TEXT,
    contig_id        TEXT,
    contig_start     INTEGER,
    contig_end       INTEGER,
    gene_caller      TEXT,
    sample_type      TEXT CHECK(sample_type IN ('isolate','MAG','metagenome') OR sample_type IS NULL),
    taxonomy         TEXT,
    bioproject       TEXT,
    biosample        TEXT,
    biome            TEXT,
    env_feature      TEXT,
    env_material     TEXT,
    latitude         REAL,
    longitude        REAL,
    collection_date  TEXT,
    sequence_sha256  TEXT NOT NULL,
    length           INTEGER,
    is_partial       INTEGER CHECK(is_partial IN (0,1) OR is_partial IS NULL),
    provenance_note  TEXT
);

CREATE TABLE "spectral_audit" (
"source_acc" TEXT,
  "organism" TEXT,
  "protein_label" TEXT,
  "exp_function_class" TEXT,
  "ion" TEXT,
  "direction" TEXT,
  "assay_type" TEXT,
  "lambda_max_nm" REAL,
  "lambda_max_conditions" TEXT,
  "photocycle_note" TEXT,
  "doi" TEXT,
  "pmid" TEXT,
  "evidence_basis" TEXT,
  "snippet" TEXT,
  "mapping_identity" TEXT,
  "in_tierA" INTEGER,
  "exp_class" TEXT,
  "exp_class_basis" TEXT,
  "v150_corrected_fields" TEXT,
  "v150_original_values" TEXT,
  "v150_curation_note" TEXT,
  "membership_status_v150" TEXT,
  "ms210" TEXT,
  "conflict" TEXT,
  "e1_eligible" INTEGER,
  "e1_exclusion_reason" REAL,
  "helixC_motif" TEXT,
  "motif_class" TEXT,
  "res_105" TEXT,
  "spectral_class" TEXT,
  "lambda_max_pred_nm" REAL,
  "func_class_v14" TEXT,
  "func_evidence" TEXT,
  "measured_class" TEXT,
  "prediction_correct" REAL
);

CREATE TABLE "status_definition" (
"status" TEXT,
  "status_group" TEXT,
  "is_member" INTEGER,
  "is_candidate" INTEGER,
  "alias_v14" TEXT,
  "definition" TEXT,
  "n_records_v150" INTEGER
);

CREATE TABLE structure (
    source_acc          TEXT PRIMARY KEY REFERENCES protein(source_acc),
    arch_primary        TEXT,
    fusion_type         TEXT,
    fusion_partner_domains TEXT,
    has_experimental_structure INTEGER CHECK(has_experimental_structure IN (0,1)),
    n_pdb_structures    INTEGER,
    rep_pdb_id          TEXT,
    rep_method          TEXT,
    rep_resolution_A    REAL,
    rep_has_retinal     INTEGER CHECK(rep_has_retinal IN (0,1)),
    n_structures_with_retinal INTEGER,
    highest_res_pdb_id  TEXT,
    highest_res_A       REAL
);

CREATE TABLE tier_a_assertion (
    assertion_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_acc   TEXT NOT NULL REFERENCES protein(source_acc),
    assertion    TEXT,
    assay_type   TEXT,
    transported_ion TEXT,
    transport_direction TEXT,
    evidence_strength TEXT
, "v150_corrected_fields" TEXT, "v150_original_values" TEXT, "v150_curation_note" TEXT);

CREATE TABLE tier_a_evidence (
    source_acc        TEXT NOT NULL REFERENCES protein(source_acc),
    evidence_subtype  TEXT,
    supported_assertion TEXT,
    assay_type        TEXT,
    transported_ion   TEXT,
    transport_direction TEXT,
    evidence_ref      TEXT,  -- DEPRECATED free text; normalized into publication/assertion_publication
    pdb_id            TEXT,
    db_version        TEXT,
    curator           TEXT,
    curation_date     TEXT,
    notes             TEXT
, assertion_id INTEGER, "v150_corrected_fields" TEXT, "v150_original_values" TEXT, "v150_curation_note" TEXT);

CREATE TABLE tier_a_holdout (
    source_acc    TEXT PRIMARY KEY REFERENCES protein(source_acc),
    designation   TEXT,
    domain        TEXT,
    function_class TEXT,
    rationale     TEXT,
    note          TEXT
);

CREATE TABLE tree_edge (
    edge_id TEXT, tree_id TEXT, parent_node TEXT, child_node TEXT, length REAL,
    PRIMARY KEY (tree_id, edge_id));

CREATE TABLE tree_node (
    node_id TEXT, tree_id TEXT, kind TEXT, label TEXT, source_acc TEXT,
    sh_alrt REAL, ufboot REAL, branch_length REAL, PRIMARY KEY (tree_id, node_id));

CREATE INDEX idx_extval_acc ON "legacy_external_validation_v14"(source_acc);

CREATE INDEX idx_extval_hash ON "legacy_external_validation_v14"(sequence_sha256);

CREATE INDEX idx_extval_stratum ON "legacy_external_validation_v14"(stratum);

CREATE INDEX idx_func_assign_acc ON "legacy_function_assignment_v14"(source_acc);

CREATE INDEX idx_holdout_assign ON holdout_assignment(regime, fold_id);

CREATE INDEX idx_placement_acc ON "legacy_placement_rt001"(source_acc);

CREATE INDEX idx_placement_track ON "legacy_placement_rt001"(track);

CREATE INDEX idx_subfam_assign_acc ON "legacy_subfamily_assignment_v14"(source_acc);

CREATE INDEX idx_subfam_assign_active ON "legacy_subfamily_assignment_v14"(is_active);

CREATE INDEX ix_placement_acc ON placement (source_acc, tree_id);

CREATE UNIQUE INDEX ux_accession_map_source_acc ON "accession_map" (source_acc);

CREATE UNIQUE INDEX ux_afdb_model_source_acc ON "afdb_model" (source_acc);

CREATE UNIQUE INDEX ux_assertion_publication_assertion_id_publication_id ON "assertion_publication" (assertion_id, publication_id);

CREATE UNIQUE INDEX ux_characterized_protein_source_acc ON "characterized_protein" (source_acc);

CREATE UNIQUE INDEX ux_clade_clade_id ON "clade" (clade_id);

CREATE UNIQUE INDEX ux_curator_spotcheck_decision_row_id ON "curator_spotcheck_decision" (row_id);

CREATE UNIQUE INDEX ux_external_validation_ext_acc ON "external_validation" (ext_acc);

CREATE UNIQUE INDEX ux_func_class_definition_func_class ON "func_class_definition" (func_class);

CREATE UNIQUE INDEX ux_function_evidence_source_acc ON "function_evidence" (source_acc);

CREATE UNIQUE INDEX ux_gtdb_taxonomy_source_acc ON "gtdb_taxonomy" (source_acc);

CREATE UNIQUE INDEX ux_membership_source_acc ON "membership" (source_acc);

CREATE UNIQUE INDEX ux_mrdb_accession_mrdb_acc ON "mrdb_accession" (mrdb_acc);

CREATE UNIQUE INDEX ux_publication_publication_id ON "publication" (publication_id);

CREATE UNIQUE INDEX ux_record_clade_source_acc ON "record_clade" (source_acc);

CREATE UNIQUE INDEX ux_reference_tree_tree_id ON "reference_tree" (tree_id);

CREATE UNIQUE INDEX ux_retinal_pocket_summary_source_acc ON "retinal_pocket_summary" (source_acc);

CREATE UNIQUE INDEX ux_route3_candidate_support_source_acc ON "route3_candidate_support" (source_acc);

CREATE UNIQUE INDEX ux_status_definition_status ON "status_definition" (status);

CREATE VIEW v_boundary_family AS SELECT * FROM v_master WHERE membership_status='boundary_family';

CREATE VIEW v_heliorhodopsin AS SELECT * FROM v_master WHERE membership_status='heliorhodopsin';

CREATE VIEW v_master AS SELECT p.mrdb_acc, p.source_acc, p.protein_name, p.organism, p.organism_id, p.tax_domain, p.length,
                m.membership_status, m.alias_v14, m.boundary_subtype, m.membership_score, m.retinal_site_residue,
                f.func_class, f.evidence_level, rc.clade_id, rc.subclade_id, rc.source AS clade_source,
                pl.clade_lwr, pl.clade_call_qc AS placement_call, c.name AS clade_name,
                CASE WHEN COALESCE(rc.clade_id, '') = '' AND pl.clade_call = 'assigned'
                      AND pl.clade_call_qc = 'distant_assigned' AND COALESCE(pl.clade_id, '') NOT IN ('', 'outgroup_heliorhodopsin')
                     THEN pl.clade_id END AS tentative_clade_id,
                CASE WHEN COALESCE(rc.clade_id, '') = '' AND pl.clade_call = 'assigned'
                      AND pl.clade_call_qc = 'distant_assigned' AND COALESCE(pl.clade_id, '') NOT IN ('', 'outgroup_heliorhodopsin')
                     THEN tc.name END AS tentative_clade_name,
                g.gtdb_taxonomy, a.model_id AS afdb_model_id, a.global_plddt AS afdb_global_plddt
                FROM protein p JOIN membership m USING (source_acc)
                LEFT JOIN function_evidence f USING (source_acc)
                LEFT JOIN record_clade rc USING (source_acc)
                LEFT JOIN clade c ON c.clade_id = rc.clade_id
                LEFT JOIN (SELECT * FROM placement WHERE tree_id='MR_RT_003' AND is_current=1) pl USING (source_acc)
                LEFT JOIN clade tc ON tc.clade_id = pl.clade_id
                LEFT JOIN gtdb_taxonomy g USING (source_acc)
                LEFT JOIN (SELECT * FROM afdb_model WHERE status='ok') a USING (source_acc);

CREATE VIEW v_rejected_or_decoy AS SELECT p.* FROM protein p JOIN membership m USING(source_acc) WHERE m.membership_status='decoy_or_rejected';

CREATE VIEW v_typeI_active AS SELECT p.* FROM protein p JOIN membership m USING(source_acc) WHERE m.alias_v14 LIKE 'typeI_c%';

CREATE VIEW v_typeI_candidate AS SELECT * FROM v_master WHERE membership_status LIKE 'typeI_candidate%';

CREATE VIEW v_typeI_candidates AS SELECT p.* FROM protein p JOIN membership m USING(source_acc) WHERE m.alias_v14 LIKE 'typeI_candidate%';

CREATE VIEW v_typeI_core AS SELECT p.* FROM protein p JOIN membership m USING(source_acc) WHERE m.alias_v14 IN ('typeI_core','typeI_core_architecture_supported');

CREATE VIEW v_typeI_member AS SELECT * FROM v_master WHERE membership_status LIKE 'typeI_member%';

