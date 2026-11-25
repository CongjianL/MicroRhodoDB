#!/usr/bin/env python
"""helixc_motif - helix-C motif (BR D85/T89/D96) and motif class from sequence.

The release field `function_evidence.helixC_motif` and its `motif_class` were carried from the v1.1 `function` table,
whose code is not in the repository. This module re-derives both with the machinery of the frozen scorer's
retinal-lysine read (pipeline/v140/features_v140.py): CLI hmmalign against PF01036.25 and the residue at a match-state
column. It reproduces the stored motif and class for all 5,361 UniProtKB 2026_02 records
(pipeline/construction_review/helixc_motif.py).

  - The positions are BR (P02945) D85, T89, D96 and K216 in mature numbering, i.e. precursor ordinals 98, 102, 109
    and 229 (13-residue propeptide). They are mapped to PF01036 match states through a P02945 row aligned together
    with the queries, so no alignment column is hard-coded.
  - helixC_motif is the three residues at those match states, '-' where the query has a deletion; it is empty when
    the query does not align to PF01036 at all.
  - motif_class is a function of the motif (recovered from the stored data, where no motif maps to two classes):
        proton_pump   DTD DTE DSD DSE
        anion_pump    NTN NTQ NSN
        sodium_pump   NDQ NCQ
        sensory_like  D[TS]x for any other residue x
        (empty)       any position deleted
        unassigned    everything else
    The class is a motif reading, not a function call: v1.6.0 uses it only to test called classes for conflicts.

  python tools/helixc_motif.py query.faa [--release releases/v1.6.2] -o motifs.tsv
"""
import argparse, os, re, shutil, sqlite3, sys, tempfile
from pathlib import Path
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline", "v140"))

BR_ACC = "P02945"
BR_ROW = "__mrdb_reference_P02945__"   # alignment row name that cannot collide with a query ID
BR_ORDINALS = {"D85": 98, "T89": 102, "D96": 109, "K216": 229}
BR_RESIDUES = {"D85": "D", "T89": "T", "D96": "D", "K216": "K"}
CLASS_OF = {**{m: "proton_pump" for m in ("DTD", "DTE", "DSD", "DSE")},
            **{m: "anion_pump" for m in ("NTN", "NTQ", "NSN")},
            **{m: "sodium_pump" for m in ("NDQ", "NCQ")}}
COLUMNS = ["source_acc", "res_D85", "res_T89", "res_D96", "res_K216", "helixC_motif", "motif_class"]


def motif_class(motif):
    if not isinstance(motif, str) or len(motif) != 3 or "-" in motif:
        return None
    if motif in CLASS_OF:
        return CLASS_OF[motif]
    if re.fullmatch("D[TS].", motif):
        return "sensory_like"
    return "unassigned"


def br_sequence(db):
    con = sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True)
    row = con.execute("select upper(sequence) from protein where source_acc = ?", (BR_ACC,)).fetchone()
    con.close()
    if not row:
        sys.exit(f"{BR_ACC} (bacteriorhodopsin) is not in {db}")
    return row[0]


def br_columns(br_row):
    """Alignment column of each BR position; each must be a match state carrying the BR residue."""
    want = {v: k for k, v in BR_ORDINALS.items()}
    cols, n = {}, 0
    for i, c in enumerate(br_row):
        if c.isalpha():
            n += 1
            if n in want:
                if not c.isupper():
                    sys.exit(f"BR ordinal {n} ({want[n]}) is an insert state in the PF01036 alignment")
                cols[want[n]] = i
    got = {k: br_row[i] for k, i in cols.items()}
    if got != BR_RESIDUES:
        sys.exit(f"BR residues at the mapped columns are {got}, expected {BR_RESIDUES}")
    return cols


def derive(seqs, hmm, br_seq, workdir, hmmer_bin=None):
    """seqs: {id: sequence}. Returns a DataFrame with COLUMNS, one row per input ID."""
    import features_v140 as fx
    hmmer_bin = hmmer_bin or os.path.dirname(shutil.which("hmmalign") or "hmmalign")
    os.makedirs(workdir, exist_ok=True)
    aln, _ = fx.run_hmmalign(hmmer_bin, hmm, {BR_ROW: br_seq, **seqs}, workdir, "helixc_pf01036")
    cols = br_columns(aln[BR_ROW])
    rows = []
    for a in seqs:
        row = aln.get(a)
        r = {"source_acc": a}
        for pos in BR_ORDINALS:
            c = row[cols[pos]] if row else ""
            r[f"res_{pos}"] = c if c.isalpha() else ("-" if row else "")
        r["helixC_motif"] = r["res_D85"] + r["res_T89"] + r["res_D96"] if row else ""
        r["motif_class"] = motif_class(r["helixC_motif"])
        rows.append(r)
    return pd.DataFrame(rows, columns=COLUMNS)


def read_fasta(p):
    seqs, k = {}, None
    for line in open(p):
        line = line.strip()
        if not line:
            continue
        if line[0] == ">":
            k = line[1:].split()[0]
            seqs[k] = []
        elif k is not None:
            seqs[k].append(line)
    return {a: "".join(v).upper().replace("*", "") for a, v in seqs.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query")
    ap.add_argument("--release", default=os.path.join(HERE, "..", "releases", "v1.6.2"))
    ap.add_argument("-o", "--out", default="helixc_motifs.tsv")
    a = ap.parse_args()
    import glob
    dbs = [f for f in sorted(glob.glob(os.path.join(a.release, "db", "microrhododb_v*.sqlite"))) if "env_pilot" not in f]
    if len(dbs) != 1:
        sys.exit(f"expected exactly one release database in {a.release}/db, found {dbs}")
    with tempfile.TemporaryDirectory() as wd:
        out = derive(read_fasta(a.query), os.path.join(a.release, "scorer", "PF01036.25.hmm"), br_sequence(dbs[0]), wd)
    out.to_csv(a.out, sep="\t", index=False)
    print(f"{len(out)} queries -> {a.out}")


if __name__ == "__main__":
    main()
