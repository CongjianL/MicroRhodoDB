#!/usr/bin/env python
"""Retinal-pocket residues in BR numbering for every record, with AlphaFold DB pLDDT.

Pocket = residues within 4.5 A of retinal (RET) in PDB 1C3W (19 positions) + D85 (counter-ion) = 20 positions,
BR mature numbering. Mapping: hmmalign (A2M, untrimmed) of all sequences + P02945 against PF01036; for each
pocket position the P02945 residue (precursor index = BR + 13) defines a PF01036 match state; the residue of every
other sequence at that match state is reported (gap -> '-').
Usage: pocket_map.py seqs.faa PF01036.hmm afdb_models.tsv afdb_plddt_dir out_long.tsv out_summary.tsv
"""
import sys, os, subprocess, gzip
import pandas as pd

POCKET_BR = [83, 85, 86, 89, 90, 93, 118, 119, 122, 138, 141, 142, 145, 182, 185, 186, 189, 212, 215, 216]
BR_OFFSET = 13  # P02945 precursor index = mature BR number + 13


def read_a2m(p):
    seqs, acc = {}, None
    for line in open(p):
        if line.startswith(">"):
            acc = line[1:].split()[0]; seqs[acc] = []
        elif acc:
            seqs[acc].append(line.strip())
    return {k: "".join(v) for k, v in seqs.items()}


def match_map(a2m):
    """return dict match_state(1-based) -> (residue, seq_pos 1-based or None)"""
    ms, pos, out = 0, 0, {}
    for ch in a2m:
        if ch == "-":
            ms += 1; out[ms] = ("-", None)
        elif ch.isupper():
            ms += 1; pos += 1; out[ms] = (ch, pos)
        elif ch.islower():
            pos += 1
    return out


def main():
    faa, hmm, models, pdir, out_long, out_sum = sys.argv[1:7]
    a2m = out_long + ".a2m"
    subprocess.run(["hmmalign", "--outformat", "A2M", "-o", a2m, hmm, faa], check=True)
    al = read_a2m(a2m)
    br = match_map(al["P02945"])
    pos2ms = {p: m for m, (r, p) in br.items() if p is not None}
    pocket_ms = {b: pos2ms[b + BR_OFFSET] for b in POCKET_BR}
    for b in (85, 216):
        assert br[pocket_ms[b]][0] == ("D" if b == 85 else "K"), (b, br[pocket_ms[b]])
    md = pd.read_csv(models, sep="\t").set_index("source_acc")
    rows, summ = [], []
    for acc, s in al.items():
        mm = match_map(s)
        pl = None
        if acc in md.index and md.loc[acc, "status"] == "ok":
            f = os.path.join(pdir, f"{acc}.tsv.gz")
            if os.path.exists(f):
                t = pd.read_csv(f, sep="\t")
                off = int(md.loc[acc, "seq_start"]) - 1
                pl = dict(zip(t.resnum + off, t.plddt))
        vals = []
        for b in POCKET_BR:
            r, p = mm.get(pocket_ms[b], ("-", None))
            v = pl.get(p) if (pl is not None and p is not None) else None
            rows.append((acc, b, pocket_ms[b], r, p, v))
            if v is not None:
                vals.append(v)
        pocket = "".join(mm.get(pocket_ms[b], ("-", None))[0] for b in POCKET_BR)
        summ.append((acc, pocket, sum(c != "-" for c in pocket), pl is not None,
                     round(sum(vals) / len(vals), 2) if vals else None, min(vals) if vals else None))
    pd.DataFrame(rows, columns=["source_acc", "br_position", "pf01036_match_state", "residue", "seq_position",
                                "afdb_plddt"]).to_csv(out_long, sep="\t", index=False)
    S = pd.DataFrame(summ, columns=["source_acc", "pocket_string_br", "n_pocket_observed", "has_afdb_model",
                                    "pocket_mean_plddt", "pocket_min_plddt"])
    S.to_csv(out_sum, sep="\t", index=False)
    os.remove(a2m)
    print("pocket match states", pocket_ms)
    print(S.describe(include="all").T[["count", "mean"]])


if __name__ == "__main__":
    main()
