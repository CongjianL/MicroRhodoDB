"""MicroRhodoDB v1.6.0 Python API (read-only access to a release SQLite database).

Database location, in order of precedence:
  1. the db_path argument;
  2. the MRDB_DB environment variable;
  3. releases/v1.6.0/db/microrhododb_v1.6.0.sqlite relative to the repository / extracted archive that contains
     this package (works for `pip install -e .` and for running from the archive).
The database is opened read-only (SQLite URI mode=ro). Release databases are immutable.

Changes from the v1.4.0 API (kept unchanged at releases/v1.4.0/meta/microrhododb_api_v14.py):
  - v1.5.0 membership vocabulary (typeI_member_core, ..., boundary_family) plus typeI_member_curated (v1.6.0
    curated override of 4 E1 records) and the v1.6.0 views
    (v_master, v_counted, v_typeI_member, v_typeI_candidate, v_boundary_family, v_heliorhodopsin,
    v_call_conflict, v_engineered); the v1.4 compatibility views and membership.alias_v14 were removed in v1.6.0.
  - new accessors for function evidence, call conflicts, engineered constructs, publications, the data
    dictionary, LOCO validation and the novel-family candidate layer.
"""
import os
import sqlite3
from pathlib import Path

import pandas as pd

__version__ = "1.6.0"
SCHEMA_REVISION = "v160.1"

DEFAULT_DB_PATH = (Path(__file__).resolve().parents[2] / "releases" / "v1.6.0" / "db" / "microrhododb_v1.6.0.sqlite")

MEMBER_STATUSES = ("typeI_member_core", "typeI_member_architecture_supported", "typeI_member_curated")
CANDIDATE_STATUSES = ("typeI_candidate", "typeI_candidate_architecture_supported", "typeI_candidate_unresolved")
OTHER_STATUSES = ("boundary_family", "heliorhodopsin", "decoy_or_rejected")
EVIDENCE_LEVELS = ("E1", "E2", "E3", "E4", "E5")


def _resolve(db_path):
    for p in (db_path, os.environ.get("MRDB_DB"), DEFAULT_DB_PATH):
        if p and Path(p).exists():
            return str(Path(p).resolve())
    raise FileNotFoundError(
        "MicroRhodoDB database not found. Pass db_path=..., set MRDB_DB, or run from the release archive "
        f"(expected {DEFAULT_DB_PATH}).")


class MicroRhodoDB:
    """Read-only handle on a MicroRhodoDB release database."""

    def __init__(self, db_path=None):
        self.db_path = _resolve(db_path)
        self.con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self.con.close()

    def _q(self, sql, params=()):
        return pd.read_sql(sql, self.con, params=params)

    # ---------------------------------------------------------------- release
    def version(self):
        md = dict(self.con.execute("SELECT key, value FROM release_metadata WHERE release = "
                                   "(SELECT max(release) FROM release_metadata WHERE key='version')").fetchall())
        return {"api": __version__, "schema_revision": md.get("schema_revision"), "database_release": md.get("version")}

    def release_metadata(self, release="1.6.0"):
        return self._q("SELECT key, value FROM release_metadata WHERE release = ?", (release,))

    # ---------------------------------------------------------------- records
    def master(self, include_engineered=True):
        """One row per source record (5,466) with membership, function evidence, flags and clade."""
        return self._q("SELECT * FROM v_master" if include_engineered else "SELECT * FROM v_counted")

    def counted(self):
        """Records that enter every count/statistic (engineered constructs excluded)."""
        return self._q("SELECT * FROM v_counted")

    def members(self, include_engineered=True):
        """Rows of v_typeI_member. Engineered constructs are included unless include_engineered=False."""
        sql = "SELECT * FROM v_typeI_member" + ("" if include_engineered else " WHERE is_engineered = 0")
        return self._q(sql)

    def candidates(self, include_engineered=True):
        """Rows of v_typeI_candidate. Engineered constructs are included unless include_engineered=False."""
        sql = "SELECT * FROM v_typeI_candidate" + ("" if include_engineered else " WHERE is_engineered = 0")
        return self._q(sql)

    def boundary_family(self, include_engineered=True):
        """Rows of v_boundary_family. Engineered constructs are included unless include_engineered=False."""
        sql = "SELECT * FROM v_boundary_family" + ("" if include_engineered else " WHERE is_engineered = 0")
        return self._q(sql)

    def heliorhodopsins(self, include_engineered=True):
        """Rows of v_heliorhodopsin. Engineered constructs are included unless include_engineered=False."""
        sql = "SELECT * FROM v_heliorhodopsin" + ("" if include_engineered else " WHERE is_engineered = 0")
        return self._q(sql)

    def get(self, acc):
        """Look up by UniProt source accession or MRDB accession (an MRDB accession may group several
        identical-sequence source records)."""
        return self._q("SELECT * FROM v_master WHERE source_acc = ? OR mrdb_acc = ?", (acc, acc))

    def fasta(self, accs=None):
        """FASTA text for the given source/MRDB accessions (default: all records)."""
        sql = "SELECT p.mrdb_acc, p.source_acc, p.sequence FROM protein p"
        rows = self.con.execute(sql).fetchall()
        if accs is not None:
            want = set(accs)
            rows = [r for r in rows if r[0] in want or r[1] in want]
        return "".join(f">{m} {s}\n{q}\n" for m, s, q in rows)

    # ---------------------------------------------------------------- function evidence
    def function_evidence(self, level=None, func_class=None, include_engineered=False):
        sql = "SELECT * FROM function_evidence WHERE 1=1"
        params = []
        if not include_engineered:
            sql += " AND is_engineered = 0"
        if level is not None:
            sql += " AND evidence_level = ?"
            params.append(level)
        if func_class is not None:
            sql += " AND func_class = ?"
            params.append(func_class)
        return self._q(sql, tuple(params))

    def call_conflicts(self):
        """Records whose legacy v1.4 call contradicts the helix-C motif class (downgraded E3/E4 and flagged E1/E2/rule)."""
        return self._q("SELECT * FROM v_call_conflict")

    def engineered(self):
        return self._q("SELECT * FROM v_engineered")

    def publications(self, acc=None):
        sql = ("SELECT a.source_acc, a.link_role, a.counts_as_support, a.verdict, a.caveat, p.pmid, p.doi, p.title, "
               "p.journal, p.year FROM assertion_publication a JOIN publication p USING (publication_id) "
               "WHERE a.is_active = 1")
        if acc is None:
            return self._q(sql)
        return self._q(sql + " AND (a.source_acc = ? OR a.source_acc IN "
                             "(SELECT source_acc FROM protein WHERE mrdb_acc = ?))", (acc, acc))

    # ---------------------------------------------------------------- documentation / validation
    def data_dictionary(self, object_name=None):
        if object_name is None:
            return self._q("SELECT * FROM data_dictionary ORDER BY object_type, object_name, ordinal")
        return self._q("SELECT * FROM data_dictionary WHERE object_name = ? ORDER BY ordinal", (object_name,))

    def loco_validation(self, release_set="1.6.0"):
        return self._q("SELECT * FROM loco_validation WHERE release_set = ?", (release_set,))

    def novel_family_candidates(self):
        return self._q("SELECT * FROM novel_family_candidate")

    def novel_family_funnel(self):
        return self._q("SELECT * FROM novel_family_funnel")
