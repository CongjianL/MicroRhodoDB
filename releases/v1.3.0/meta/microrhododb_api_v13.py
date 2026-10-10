"""MicroRhodoDB v1.3.0 public API.

Authoritative membership = membership.membership_status (NOT the deprecated
`module` column). Use the query_* helpers, which are built on the public
views and never return decoy/rejected records as active.

Changes from v1.2.0:
  - __version__ = "1.3.0"; SCHEMA_REVISION = "v130.1"
  - new: query_environmental(biome=None, state=None)  — MGnify pilot records
         (environmental_admission joined to sequence_source + frozen score).
         Environmental records are NEVER part of membership/active views.
  - new: query_external_validation() — independent external validation set
         (106 records, provenance-audited, ever_exposed_flag=0).
  - new: query_clade_provenance() — reference clades with tree node/edge links.
  - all v1.2.0 accessors unchanged; v1.2.0 membership is byte-identical.
"""
import sqlite3
import pandas as pd

__version__ = "1.3.0"
SCHEMA_REVISION = "v130.1"

ACTIVE_STATUSES = (
    "typeI_core", "typeI_core_architecture_supported", "typeI_candidate",
    "typeI_candidate_architecture_supported", "typeI_candidate_unresolved",
)
CORE_STATUSES = ("typeI_core", "typeI_core_architecture_supported")
CANDIDATE_STATUSES = (
    "typeI_candidate", "typeI_candidate_architecture_supported",
    "typeI_candidate_unresolved",
)
ENV_STATES = ("environmental_candidate", "environmental_unresolved")


class MicroRhodoDB:
    def __init__(self, db_path):
        self.db_path = db_path
        self.con = sqlite3.connect(db_path)
        self.con.execute("PRAGMA foreign_keys = ON;")

    def close(self):
        self.con.close()

    def _q(self, sql, params=()):
        return pd.read_sql(sql, self.con, params=params)

    def version(self):
        return {"api": __version__, "schema_revision": SCHEMA_REVISION,
                "database_release": self._q(
                    "SELECT value FROM release_metadata WHERE key='database_release'"
                ).iloc[0, 0]}

    # ---- native accessors (unchanged from v1.2.0) ----
    def query_active_typeI(self):
        """All active Type-I rhodopsins (core + candidate). Never includes decoys."""
        return self._q("SELECT * FROM v_typeI_active")

    def query_core(self):
        """Active Type-I core (typeI_core + architecture-supported)."""
        return self._q("SELECT * FROM v_typeI_core")

    def query_candidates(self):
        """Candidate / unresolved Type-I (three candidate states)."""
        return self._q("SELECT * FROM v_typeI_candidates")

    def query_rejected(self):
        """Decoy/rejected records (incl. HSP30) kept for benchmark/audit only."""
        return self._q("SELECT * FROM v_rejected_or_decoy")

    def query_subfamily(self, active_only=True):
        """Subfamily assignments. active_only=True (default) returns only labels
        supported by an independent allowed evidence path (is_active=1)."""
        if active_only:
            return self._q("SELECT * FROM v_active_subfamily")
        return self._q("SELECT * FROM subfamily_assignment")

    def query_placements(self, track=None):
        """Phylogenetic placements. track=None (all) | 'primary' | 'exploratory'."""
        if track is None:
            return self._q("SELECT * FROM placement")
        return self._q("SELECT * FROM placement WHERE track = ?", (track,))

    def query_master(self, module=None, status=None):
        """Backward-compatible master join. WARNING: includes ALL proteins
        regardless of status. `module` is deprecated and does NOT imply active;
        use `status` or query_active_typeI for the active set."""
        sql = "SELECT * FROM v_master WHERE 1=1"
        params = []
        if module is not None:
            sql += " AND module = ?"
            params.append(module)
        if status is not None:
            sql += " AND membership_status = ?"
            params.append(status)
        return self._q(sql, tuple(params))

    def get_protein(self, acc):
        return self._q("SELECT * FROM v_master WHERE source_acc = ?", (acc,))

    # ---- new in v1.3.0 ----
    def query_environmental(self, biome=None, state=None):
        """MGnify environmental pilot records: environmental_admission joined to
        sequence_source provenance. biome: 'marine' | 'soil'; state:
        'environmental_candidate' | 'environmental_unresolved'.
        These records are isolated from membership/active_population by design."""
        sql = ("SELECT ea.source_acc, ea.admission_state, ea.classifier_score, "
               "ea.classifier_release, ea.score_band, s.biome, s.study_id, "
               "s.sample_id, s.assembly_id, s.sequence_sha256, s.length, "
               "s.is_partial, s.latitude, s.longitude, s.collection_date "
               "FROM environmental_admission ea "
               "JOIN sequence_source s ON s.source_acc = ea.source_acc WHERE 1=1")
        params = []
        if biome is not None:
            sql += " AND s.biome = ?"
            params.append(biome)
        if state is not None:
            sql += " AND ea.admission_state = ?"
            params.append(state)
        return self._q(sql, tuple(params))

    def query_external_validation(self):
        """Independent external validation set (never used for any v1.x decision;
        ever_exposed_flag=0 for all records)."""
        return self._q("SELECT * FROM external_validation")

    def query_clade_provenance(self):
        """Reference clades with their reference-tree node/edge provenance."""
        return self._q(
            "SELECT rc.*, tn.tree_id, tn.kind AS node_kind, te.length AS edge_length "
            "FROM reference_clade rc "
            "JOIN tree_node tn ON tn.node_id = rc.tree_node_id "
            "LEFT JOIN tree_edge te ON te.edge_id = rc.edge_id "
            "ORDER BY rc.clade_id")
