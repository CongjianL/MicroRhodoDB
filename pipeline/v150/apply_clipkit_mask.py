#!/usr/bin/env python
"""Apply a ClipKIT keep/trim column log to a (reference + query) alignment produced with mafft --keeplength.
Usage: apply_clipkit_mask.py ref_plus_q.msa.faa clipkit.log ref.msa.faa out_ref.faa out_q.faa
"""
import sys
from Bio import SeqIO


def main():
    aln, log, refmsa, oref, oq = sys.argv[1:6]
    keep = [l.split()[1] == "keep" for l in open(log) if l.strip()]
    ref = {r.id for r in SeqIO.parse(refmsa, "fasta")}
    nref = nq = 0
    with open(oref, "w") as fr, open(oq, "w") as fq:
        for r in SeqIO.parse(aln, "fasta"):
            s = str(r.seq)
            assert len(s) == len(keep), (r.id, len(s), len(keep))
            t = "".join(c for c, k in zip(s, keep) if k).upper()
            if r.id in ref:
                fr.write(f">{r.id}\n{t}\n"); nref += 1
            else:
                fq.write(f">{r.id}\n{t}\n"); nq += 1
    print("ref", nref, "queries", nq, "columns", sum(keep))


if __name__ == "__main__":
    main()
