"""Stage 1 (novel-family candidate layer), step 1: align seeds, find the conserved retinal-Schiff-base
Lys column from each seed alignment, build an HMM per family."""
import subprocess, os
import numpy as np
from Bio import AlignIO

FAMS = ["viral_rhodopsin", "schizorhodopsin", "xenorhodopsin", "bestrhodopsin", "MerMAID"]
BASE = "/workspace/v160/novel"

summary = []
for fam in FAMS:
    faa = f"{BASE}/seeds/fasta/{fam}.faa"
    aln = f"{BASE}/seeds/fasta/{fam}.aln.fasta"
    hmm = f"{BASE}/seeds/fasta/{fam}.hmm"
    subprocess.run(f"mafft --auto --thread 4 {faa} > {aln}", shell=True, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    aln_obj = AlignIO.read(aln, "fasta")
    arr = np.array([list(str(r.seq)) for r in aln_obj])
    n, L = arr.shape
    k_freq = (arr == "K").mean(axis=0)
    best_col = int(np.argmax(k_freq))
    summary.append(dict(family=fam, n_seeds=n, aln_len=L, retinalK_col=best_col,
                         retinalK_frac=round(float(k_freq[best_col]), 3),
                         retinalK_col_2nd=int(np.argsort(k_freq)[-2]), retinalK_2nd_frac=round(float(np.sort(k_freq)[-2]), 3)))
    subprocess.run(["/workspace/.conda/mrdb/bin/hmmbuild", "--amino", hmm, aln], check=True,
                   stdout=subprocess.DEVNULL)
    print(fam, "n_seeds", n, "aln_len", L, "retinalK_col", best_col, "frac", round(float(k_freq[best_col]), 3))

import pandas as pd
pd.DataFrame(summary).to_csv(f"{BASE}/seeds/retinalK_column_summary.tsv", sep="\t", index=False)
print(pd.DataFrame(summary).to_string())
