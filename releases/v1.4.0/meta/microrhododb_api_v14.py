"""MicroRhodoDB v1.4.0 public API.

Authoritative membership = membership.membership_status (NOT the deprecated
`module` column). Use the query_* helpers, which are built on the public
views and never return decoy/rejected records as active.

Changes from v1.3.0:
  - __version__ = "1.4.0"; SCHEMA_REVISION = "v140.1"
  - v1.4.0 extends v1.3.0 append-only: +105 UniProtKB 2026_03 delta accessions
    (96 PF01036-primary, 9 PF18761-primary), scored with the frozen v1.2 scorer
    (0-difference gate on all 5,361 frozen records).
  - MR_RT_002 (278-tip backbone) promoted to canonical_release; new content:
    tree_node/tree_edge (MR_RT_002), reference_clade MR_CLD2_* (55 clades),
    placement_v140 (4,335 EPA-ng placements on MR_RT_002).
  - new: query_placement_v140(tree_id=None) — v1.4.0 placement layer.
  - new: query_extension_delta() — the 111-row UniProtKB delta log.
  - fix: query_clade_provenance() now joins tree_node/tree_edge with the
    correct tree_id per clade namespace (MR_CLD_* -> MR_RT_001,
    MR_CLD2_* -> MR_RT_002); node/edge ids are only unique within a tree.

The API opens the frozen v1.4.0 release database inside this repository by
default; pass an explicit db_path to override. Release DBs are immutable.
"""
import sqlite3
from pathlib import Path

import pandas as pd

__version__ = "1.4.0"
SCHEMA_REVISION = "v140.1"

# Convenience default: the frozen v1.4.0 release database shipped in this
# repository. Pass an explicit db_path to override; the release database is
# immutable.
DEFAULT_DB_PATH = (
    Path(__file__).resolve().parents[2]
    / "releases" / "v1.4.0" / "db" / "microrhododb_v1.4.0.sqlite"
)

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

# clade namespace -> reference tree
_CLADE_TREE_CASE = (
    "CASE WHEN rc.clade_id LIKE 'MR_CLD2_%' THEN 'MR_RT_002' ELSE 'MR_RT_001' END"
)


class MicroRhodoDB:
    def __init__(self, db_path=None):
        self.db_path = str(db_path) if db_path is not None else str(DEFAULT_DB_PATH)
        self.con = sqlite3.connect(self.db_path)
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
        """Frozen v1.x phylogenetic placements on MR_RT_001.
        track=None (all) | 'primary' | 'exploratory'.
        For the v1.4.0 placement layer on MR_RT_002 use query_placement_v140."""
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
        """Reference clades with their reference-tree node/edge provenance.
        Joins carry the correct tree_id per clade namespace (node/edge ids are
        only unique within a tree)."""
        return self._q(
            "SELECT rc.*, tn.tree_id, tn.kind AS node_kind, te.length AS edge_length "
            "FROM reference_clade rc "
            f"JOIN tree_node tn ON tn.node_id = rc.tree_node_id AND tn.tree_id = {_CLADE_TREE_CASE} "
            f"LEFT JOIN tree_edge te ON te.edge_id = rc.edge_id AND te.tree_id = {_CLADE_TREE_CASE} "
            "ORDER BY rc.clade_id")

    # ---- new in v1.4.0 ----
    def query_placement_v140(self, tree_id=None):
        """v1.4.0 EPA-ng placement layer (placement_v140). Currently MR_RT_002
        only: 4,335 eligible active members (complete core, non-reference-tip).
        The frozen v1.x placement table (MR_RT_001) is unchanged and remains
        available via query_placements()."""
        if tree_id is None:
            return self._q("SELECT * FROM placement_v140")
        return self._q("SELECT * FROM placement_v140 WHERE tree_id = ?", (tree_id,))

    def query_extension_delta(self):
        """UniProtKB 2026_03 delta log: 105 admitted new accessions plus
        6 demoted/merged accessions (logged only; frozen rows untouched)."""
        return self._q("SELECT * FROM extension_delta ORDER BY delta_class, accession")
