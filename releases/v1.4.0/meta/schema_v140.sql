-- MicroRhodoDB v1.4.0 authoritative schema
CREATE TABLE active_population (
            source_acc TEXT PRIMARY KEY REFERENCES protein(source_acc),
            membership_status TEXT NOT NULL,
            policy_class TEXT NOT NULL,
            is_active INTEGER NOT NULL CHECK(is_active IN (0,1)),
            is_core INTEGER NOT NULL CHECK(is_core IN (0,1)),
            is_candidate INTEGER NOT NULL CHECK(is_candidate IN (0,1))
        );

CREATE TABLE assertion_publication (
    assertion_id   INTEGER NOT NULL REFERENCES tier_a_assertion(assertion_id),
    publication_id INTEGER NOT NULL REFERENCES publication(publication_id),
    PRIMARY KEY (assertion_id, publication_id)
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

CREATE TABLE build_provenance (
    table_name   TEXT PRIMARY KEY,
    source_data  TEXT,
    script       TEXT,
    algorithm    TEXT,
    params       TEXT,
    upstream_deps TEXT,
    release      TEXT,
    built_at     TEXT
);

CREATE TABLE citation (
    ref_id      INTEGER PRIMARY KEY,
    citation    TEXT,
    doi         TEXT,
    context     TEXT
);

CREATE TABLE environmental_admission (
    source_acc         TEXT PRIMARY KEY REFERENCES protein(source_acc),
    admission_state    TEXT NOT NULL CHECK(admission_state IN
                           ('environmental_candidate','environmental_unresolved')),
    classifier_score   REAL CHECK(classifier_score BETWEEN 0 AND 1),
    classifier_release TEXT,               -- e.g. '1.2.0-frozen'
    score_band         TEXT CHECK(score_band IN
                           ('below_0.40','0.40_0.70','0.70_0.86','0.86_0.90','ge_0.90')
                           OR score_band IS NULL),
    note               TEXT
);

CREATE TABLE extension_delta (
    accession   TEXT PRIMARY KEY,
    delta_class TEXT NOT NULL CHECK(delta_class IN ('new','sequence_changed','demoted_or_merged')),
    family_hint TEXT,
    detail      TEXT
);

CREATE TABLE external_validation (
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

CREATE TABLE external_validation_metric (
    metric_id    INTEGER PRIMARY KEY,
    stratum      TEXT NOT NULL,        -- E1 | E2 | EXT_NEG | E1+E2 | combined
    threshold    REAL,                 -- frozen v1.2 threshold evaluated (NULL for threshold-free ranking metrics)
    metric       TEXT NOT NULL,        -- sensitivity/specificity/precision/npv/roc_auc/pr_auc/brier/...
    value        REAL,
    ci_lo        REAL,
    ci_hi        REAL,
    ci_method    TEXT,                 -- clopper_pearson / bootstrap / NA
    n_pos        INTEGER,
    n_neg        INTEGER,
    note         TEXT
);

CREATE TABLE function (
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

CREATE TABLE function_assignment (
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

CREATE TABLE holdout_metric (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    regime TEXT NOT NULL,
    level TEXT NOT NULL,               -- fold | pooled
    fold_id TEXT,                      -- NULL for pooled
    metric TEXT NOT NULL,              -- sensitivity@0.86, roc_auc, brier, ...
    value REAL,
    ci_lo REAL, ci_hi REAL,            -- Clopper-Pearson 95% where applicable
    n_pos INTEGER, n_neg INTEGER,
    tp INTEGER, fp INTEGER, fn INTEGER, tn INTEGER,
    adequate INTEGER,                  -- adequacy gate (fold n_pos >= 10); pooled: regime-level flag
    note TEXT
);

CREATE TABLE membership (
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

CREATE TABLE pdb_structure (
    pdb_id      TEXT PRIMARY KEY,
    method      TEXT,
    resolution  REAL,
    title       TEXT,
    ligands     TEXT,
    has_retinal INTEGER CHECK(has_retinal IN (0,1)),
    year        TEXT
);

CREATE TABLE placement (
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

CREATE TABLE placement_v140 (
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
);

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

CREATE TABLE publication (
    publication_id INTEGER PRIMARY KEY AUTOINCREMENT,
    doi       TEXT,
    pmid      TEXT,
    title     TEXT,
    journal   TEXT,
    year      TEXT,
    raw_ref   TEXT
, ingestion TEXT
    CHECK (ingestion IN ('parsed_heuristic', 'manual_verified', 'structured_id')));

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

CREATE TABLE redundancy (
    source_acc          TEXT PRIMARY KEY REFERENCES protein(source_acc),
    module              TEXT,
    exact_nr_cluster    TEXT, exact_nr_is_rep INTEGER CHECK(exact_nr_is_rep IN (0,1)),
    std_90_cluster      TEXT, std_90_is_rep INTEGER CHECK(std_90_is_rep IN (0,1)),
    intermediate_cluster TEXT, intermediate_is_rep INTEGER CHECK(intermediate_is_rep IN (0,1)),
    backbone_cluster    TEXT, backbone_is_rep INTEGER CHECK(backbone_is_rep IN (0,1))
);

CREATE TABLE reference_backbone (
    representative   TEXT PRIMARY KEY,
    cluster          TEXT,
    n_members        INTEGER,
    n_taxdom         INTEGER,
    n_arch           INTEGER,
    diversity_retained INTEGER CHECK(diversity_retained >= 0),
    is_anchor        INTEGER CHECK(is_anchor IN (0,1))
);

CREATE TABLE reference_clade (
    clade_id        TEXT PRIMARY KEY,
    n_tips          INTEGER,
    n_tierA_anchors INTEGER,
    anchor_members  TEXT,  -- DEPRECATED free text; normalized into reference_clade_member
    tree_node_id    TEXT,
    edge_id         TEXT,
    parent_clade_id TEXT
);

CREATE TABLE reference_clade_member (
    clade_id   TEXT NOT NULL REFERENCES reference_clade(clade_id),
    source_acc TEXT NOT NULL,
    PRIMARY KEY (clade_id, source_acc)
);

CREATE TABLE reference_clade_tip (
    clade_id TEXT, source_acc TEXT, PRIMARY KEY (clade_id, source_acc));

CREATE TABLE reference_tree (
    tree_id TEXT PRIMARY KEY, n_tips INTEGER, method TEXT, model TEXT,
    log_likelihood REAL, treefile_md5 TEXT, unrooted INTEGER, status TEXT, note TEXT);

CREATE TABLE release_metadata (
            key TEXT PRIMARY KEY,
            value TEXT
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

CREATE TABLE subfamily (
    source_acc          TEXT PRIMARY KEY REFERENCES protein(source_acc),
    subfamily           TEXT,
    assignment_method   TEXT,
    assignment_basis    TEXT,
    best_lwr            REAL CHECK(best_lwr BETWEEN 0 AND 1),
    edge_subfamily_purity REAL,
    tree_discordant     INTEGER CHECK(tree_discordant IN (0,1))
);

CREATE TABLE subfamily_assignment (
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

CREATE TABLE tier_a_assertion (
    assertion_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_acc   TEXT NOT NULL REFERENCES protein(source_acc),
    assertion    TEXT,
    assay_type   TEXT,
    transported_ion TEXT,
    transport_direction TEXT,
    evidence_strength TEXT
);

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
);

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

CREATE INDEX idx_extmetric_stratum ON external_validation_metric(stratum);

CREATE INDEX idx_extval_acc ON external_validation(source_acc);

CREATE INDEX idx_extval_hash ON external_validation(sequence_sha256);

CREATE INDEX idx_extval_stratum ON external_validation(stratum);

CREATE INDEX idx_func_assign_acc ON function_assignment(source_acc);

CREATE INDEX idx_holdout_assign ON holdout_assignment(regime, fold_id);

CREATE INDEX idx_holdout_metric ON holdout_metric(regime, level);

CREATE INDEX idx_placement_acc ON placement(source_acc);

CREATE INDEX idx_placement_track ON placement(track);

CREATE INDEX idx_subfam_assign_acc ON subfamily_assignment(source_acc);

CREATE INDEX idx_subfam_assign_active ON subfamily_assignment(is_active);

CREATE VIEW v_active_function AS
SELECT * FROM function_assignment WHERE is_active = 1;

CREATE VIEW v_active_subfamily AS
SELECT * FROM subfamily_assignment WHERE is_active = 1;

CREATE VIEW v_master AS
SELECT p.source_acc, p.sequence, p.length, p.organism, p.organism_id, p.tax_domain,
       p.lineage, p.protein_name, p.reviewed, p.is_seed,
       m.membership_category, m.membership_score, m.module, m.membership_status,
       m.architecture_class, m.arch_route, m.reason_code,
       q.hmm_cov, q.has_retinal_lysine, q.complete_core, q.arch_primary,
       f.func_class, f.func_confidence, f.spectral_class, f.lambda_max_pred_nm,
       s.subfamily, s.assignment_method
FROM protein p
LEFT JOIN membership m USING(source_acc)
LEFT JOIN qc_feature q USING(source_acc)
LEFT JOIN function f USING(source_acc)
LEFT JOIN subfamily s USING(source_acc);

CREATE VIEW v_rejected_or_decoy AS
SELECT p.*, m.membership_status, m.membership_category, m.membership_score, m.reason_code
FROM protein p JOIN membership m USING(source_acc)
WHERE m.membership_status = 'decoy_or_rejected';

CREATE VIEW v_typeI_active AS
SELECT p.*, m.membership_status, m.membership_category, m.membership_score,
       m.architecture_class, m.arch_route, m.reason_code
FROM protein p JOIN membership m USING(source_acc)
WHERE m.membership_status IN (
    'typeI_core','typeI_core_architecture_supported','typeI_candidate',
    'typeI_candidate_architecture_supported','typeI_candidate_unresolved');

CREATE VIEW v_typeI_candidates AS
SELECT p.*, m.membership_status, m.membership_category, m.membership_score,
       m.architecture_class, m.arch_route, m.reason_code
FROM protein p JOIN membership m USING(source_acc)
WHERE m.membership_status IN (
    'typeI_candidate','typeI_candidate_architecture_supported','typeI_candidate_unresolved');

CREATE VIEW v_typeI_core AS
SELECT p.*, m.membership_status, m.membership_category, m.membership_score,
       m.architecture_class, m.arch_route, m.reason_code
FROM protein p JOIN membership m USING(source_acc)
WHERE m.membership_status IN ('typeI_core','typeI_core_architecture_supported');

