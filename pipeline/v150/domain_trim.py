#!/usr/bin/env python
"""Trim each sequence to its 7-TM rhodopsin domain envelope (+/- flank aa) before MSA.

Uses hmmsearch domtblout against PF01036 and PF18761; for each sequence the highest-scoring domain hit
(either HMM) defines the envelope. Sequences with no hit are kept full-length and reported.
Usage: domain_trim.py in.faa PF01036.hmm PF18761.hmm out.faa out_coords.tsv [flank]
"""
import sys, subprocess, tempfile, os
import pandas as pd


def read_fasta(p):
    seqs, acc = {}, None
    for line in open(p):
        if line.startswith(">"):
            acc = line[1:].split()[0]
            seqs[acc] = []
        elif acc:
            seqs[acc].append(line.strip())
    return {k: "".join(v) for k, v in seqs.items()}


def main():
    faa, h1, h2, out, coords = sys.argv[1:6]
    flank = int(sys.argv[6]) if len(sys.argv) > 6 else 15
    seqs = read_fasta(faa)
    rows = []
    with tempfile.TemporaryDirectory() as td:
        for h in (h1, h2):
            dt = os.path.join(td, "d.tbl")
            subprocess.run(["hmmsearch", "--domtblout", dt, "-E", "1e-3", "--cpu", "8", h, faa],
                           check=True, stdout=subprocess.DEVNULL)
            for line in open(dt):
                if line.startswith("#"):
                    continue
                f = line.split()
                rows.append((f[0], f[3], float(f[13]), int(f[19]), int(f[20])))
    d = pd.DataFrame(rows, columns=["acc", "hmm", "dom_bits", "env_from", "env_to"])
    best = d.sort_values("dom_bits", ascending=False).groupby("acc").head(1).set_index("acc")
    rec = []
    with open(out, "w") as fo:
        for k, s in seqs.items():
            if k in best.index:
                b = best.loc[k]
                st = max(1, int(b.env_from) - flank)
                en = min(len(s), int(b.env_to) + flank)
                rec.append((k, len(s), b.hmm, b.dom_bits, st, en))
            else:
                st, en = 1, len(s)
                rec.append((k, len(s), "none", None, st, en))
            fo.write(f">{k}\n{s[st - 1:en]}\n")
    r = pd.DataFrame(rec, columns=["acc", "length", "hmm", "dom_bits", "trim_start", "trim_end"])
    r.to_csv(coords, sep="\t", index=False)
    print("no_hit", (r.hmm == "none").sum(), "trimmed_len_median", int((r.trim_end - r.trim_start + 1).median()),
          "max", int((r.trim_end - r.trim_start + 1).max()))


if __name__ == "__main__":
    main()
