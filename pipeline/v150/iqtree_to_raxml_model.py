#!/usr/bin/env python
"""Translate an IQ-TREE Q.PFAM(+F)(+G/+R) fit into an EPA-ng/RAxML-ng model string with fixed parameters.

EPA-ng 0.3.8 does not ship Q.PFAM; the exchangeabilities are taken from IQ-TREE 2 (model/modelprotein.cpp, PAML
lower-triangular order A R N D C Q E G H I L K M F P S T W Y V) and written as PROTGTR{...} in RAxML upper-triangle
row-major order. Frequencies: +FC (empirical, IQ-TREE '+F'). Rate heterogeneity: FreeRate categories (rates and
weights) or Gamma alpha copied from the .iqtree report.
Usage: iqtree_to_raxml_model.py run.iqtree modelprotein.cpp  -> prints model string
"""
import re, sys
import numpy as np


def qpfam(cpp):
    txt = open(cpp).read()
    blk = txt.split("model Q.PFAM=")[1].split(";")[0]
    v = [float(x) for x in blk.split()]
    tri = v[:190]
    M = np.zeros((20, 20)); k = 0
    for i in range(1, 20):
        for j in range(i):
            M[i, j] = M[j, i] = tri[k]; k += 1
    return [M[i, j] for i in range(20) for j in range(i + 1, 20)]


def main():
    iq, cpp = sys.argv[1:3]
    rep = open(iq).read()
    best = re.search(r"Best-fit model: (\S+)", rep) or re.search(r"Model of substitution: (\S+)", rep)
    model = best.group(1)
    base = model.split("+")[0].upper()
    if base == "Q.PFAM":
        s = "PROTGTR{" + "/".join(f"{x:.9f}" for x in qpfam(cpp)) + "}"
    elif base in ("LG", "WAG", "JTT"):
        s = base
    else:
        raise SystemExit(f"unsupported model {model}")
    if "+F" in model:
        s += "+FC"
    m = re.search(r"\+R(\d+)", model)
    if m:
        n = int(m.group(1))
        sec = rep.split("Category  Relative_rate  Proportion")[1]
        rows = re.findall(r"^\s+(\d+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)", sec, flags=re.M)[:n]
        rates = [r[1] for r in rows]; w = [r[2] for r in rows]
        s += f"+R{n}{{{'/'.join(rates)}}}{{{'/'.join(w)}}}"
    g = re.search(r"\+G(\d*)", model)
    if g:
        a = re.search(r"Gamma shape alpha: ([\d.]+)", rep).group(1)
        s += f"+G{g.group(1) or 4}{{{a}}}"
    print(s)


if __name__ == "__main__":
    main()
