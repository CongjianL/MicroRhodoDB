"""
MicroRhodoDB v1.0 - Python query API
====================================

A lightweight, dependency-minimal (stdlib sqlite3 + pandas) interface to the
MicroRhodoDB relational database of Type-I microbial rhodopsins.

The database is a normalized SQLite file with a universal key ``source_acc``
(UniProt accession) linking one central ``protein`` table to satellite tables:
membership, qc_feature, redundancy, subfamily, function, structure,
predicted_structure, plus a protein<->PDB junction and reference tables
(pdb_structure, seed, citation). A denormalized ``v_master`` view joins them all.

IMPORTANT interpretation notes (read before using functional/spectral fields):
  * ``function_is_inferred`` is TRUE for every functional call - functions are
    inferred from active-site chemistry + phylogeny, NOT experimentally measured
    for the individual sequence.
  * ``lambda_max_is_predicted`` marks predicted absorption maxima;
    ``lambda_max_measured_nm`` is reserved for experimental values (currently all
    NULL - none are imputed).
  * Spectral predictions are emitted ONLY for proteorhodopsins (position-105 L/Q
    switch); other subfamilies record the residue but no color call.
  * ``motif_agrees`` = 0 flags sequences where the active-site motif and the
    phylogenetic subfamily disagree; the functional call then follows the motif
    chemistry (conservative). These are surfaced, not hidden.
  * Membership categories: confirmed_type_I, high_confidence_type_I,
    putative_type_I, rhodopsin_like, ambiguous, rejected. Heliorhodopsins are a
    SEPARATE module (``module='heliorhodopsin'``), never a Type-I subfamily.

Example
-------
>>> from microrhododb_api import MicroRhodoDB
>>> db = MicroRhodoDB("microrhododb_v1.0.sqlite")
>>> db.summary()
>>> df = db.query_master(module="type_I", func_class="proton_pump")
>>> br = db.get_protein("P02945")           # full annotation for one accession
>>> pr = db.subfamily("proteorhodopsin")    # all proteorhodopsins
>>> st = db.structures_for("P02945")        # experimental PDB list
>>> db.fasta(["P02945", "Q9F7P4"], "out.faa")
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
import pandas as pd

__version__ = "1.0"


class MicroRhodoDB:
    """Read-only convenience wrapper over the MicroRhodoDB SQLite file."""

    def __init__(self, db_path: str):
        self.db_path = str(Path(db_path).expanduser())
        # read-only URI connection; check_same_thread False for notebook use
        self._uri = f"file:{self.db_path}?mode=ro"

    # ---- low level -------------------------------------------------------
    def _con(self):
        return sqlite3.connect(self._uri, uri=True)

    def sql(self, query: str, params: tuple | list | None = None) -> pd.DataFrame:
        """Run an arbitrary read-only SQL query, return a DataFrame."""
        with self._con() as con:
            return pd.read_sql(query, con, params=params)

    def tables(self) -> list[str]:
        return self.sql(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view') ORDER BY type DESC, name"
        )["name"].tolist()

    def columns(self, table: str) -> list[str]:
        return self.sql(f"PRAGMA table_info({table})")["name"].tolist()

    # ---- high level ------------------------------------------------------
    def summary(self) -> pd.DataFrame:
        """Print and return a compact database summary."""
        counts = {}
        for t in ["protein", "membership", "subfamily", "function", "structure",
                  "pdb_structure", "predicted_structure", "seed", "citation"]:
            counts[t] = self.sql(f"SELECT COUNT(*) n FROM {t}")["n"].iloc[0]
        print(f"MicroRhodoDB v{__version__}  ({self.db_path})")
        print("  rows:", ", ".join(f"{k}={v}" for k, v in counts.items()))
        mem = self.sql("SELECT membership_category c, COUNT(*) n FROM membership "
                       "GROUP BY c ORDER BY n DESC")
        print("\n  membership_category:")
        for _, r in mem.iterrows():
            print(f"    {r.c:24s} {r.n}")
        return mem

    def query_master(self, **filters) -> pd.DataFrame:
        """Query the denormalized v_master view with equality filters.

        Example: query_master(module='type_I', func_class='proton_pump',
                              tax_domain='Bacteria')
        """
        where, params = [], []
        for k, v in filters.items():
            where.append(f"{k} = ?")
            params.append(v)
        q = "SELECT * FROM v_master"
        if where:
            q += " WHERE " + " AND ".join(where)
        return self.sql(q, params)

    def get_protein(self, acc: str) -> pd.Series | None:
        """Return the full denormalized annotation row for one accession."""
        df = self.sql("SELECT * FROM v_master WHERE source_acc = ?", (acc,))
        if df.empty:
            return None
        return df.iloc[0]

    def sequence(self, acc: str) -> str | None:
        df = self.sql("SELECT sequence FROM protein WHERE source_acc = ?", (acc,))
        return None if df.empty else df["sequence"].iloc[0]

    def subfamily(self, name: str) -> pd.DataFrame:
        """All proteins assigned to a given subfamily (with master annotations)."""
        return self.sql("SELECT * FROM v_master WHERE subfamily = ?", (name,))

    def function_class(self, name: str) -> pd.DataFrame:
        """All proteins with a given functional class."""
        return self.sql("SELECT * FROM v_master WHERE func_class = ?", (name,))

    def structures_for(self, acc: str) -> pd.DataFrame:
        """Experimental PDB structures mapped to an accession."""
        return self.sql(
            "SELECT pd.* FROM protein_pdb j JOIN pdb_structure pd ON j.pdb_id=pd.pdb_id "
            "WHERE j.source_acc = ? ORDER BY pd.has_retinal DESC, pd.resolution", (acc,))

    def with_experimental_structure(self) -> pd.DataFrame:
        return self.sql("SELECT * FROM v_master WHERE has_experimental_structure = 1")

    def predicted_structures(self) -> pd.DataFrame:
        return self.sql("SELECT * FROM predicted_structure")

    def spectral_predictions(self) -> pd.DataFrame:
        """Proteins with a predicted absorption maximum (currently proteorhodopsins)."""
        return self.sql("SELECT source_acc, spectral_class, lambda_max_pred_nm, "
                        "spectral_confidence, spectral_basis FROM function "
                        "WHERE lambda_max_pred_nm IS NOT NULL")

    def representatives(self, tier: str = "backbone") -> pd.DataFrame:
        """Representative sequences for a redundancy tier.

        tier in {'std_90','intermediate','backbone'}.
        """
        col = f"{tier}_is_rep"
        return self.sql(f"SELECT p.source_acc, p.organism, m.membership_category, "
                        f"s.subfamily FROM redundancy r "
                        f"JOIN protein p ON r.source_acc=p.source_acc "
                        f"LEFT JOIN membership m ON r.source_acc=m.source_acc "
                        f"LEFT JOIN subfamily s ON r.source_acc=s.source_acc "
                        f"WHERE r.{col} = 1")

    def seeds(self) -> pd.DataFrame:
        return self.sql("SELECT * FROM seed")

    def citations(self) -> pd.DataFrame:
        return self.sql("SELECT * FROM citation ORDER BY ref_id")

    def fasta(self, accs, out_path: str) -> int:
        """Write sequences for a list of accessions to a FASTA file. Returns count."""
        if isinstance(accs, str):
            accs = [accs]
        placeholders = ",".join("?" * len(accs))
        df = self.sql(
            f"SELECT p.source_acc, p.organism, s.subfamily, p.sequence "
            f"FROM protein p LEFT JOIN subfamily s ON p.source_acc=s.source_acc "
            f"WHERE p.source_acc IN ({placeholders})", tuple(accs))
        n = 0
        with open(out_path, "w") as fh:
            for _, r in df.iterrows():
                sf = r.subfamily if pd.notna(r.subfamily) else "unassigned"
                fh.write(f">{r.source_acc} {sf} | {r.organism}\n{r.sequence}\n")
                n += 1
        return n


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "microrhododb_v1.0.sqlite"
    db = MicroRhodoDB(path)
    db.summary()
