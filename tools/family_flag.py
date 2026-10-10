#!/usr/bin/env python
"""family_flag - novel-family pointer for MicroRhodoDB v1.6.0 (referee point R-V3).

Five family HMMs (viral rhodopsin, schizorhodopsin, xenorhodopsin, bestrhodopsin, MerMAID; built with MAFFT +
hmmbuild from 2-6 published sequences each, shipped in releases/v1.6.0/scorer/family_hmms/) are searched against
the query proteins with hmmsearch, together with Pfam PF01036.

E-values use a fixed search space (-Z 5466, the corpus size), so a query's flag does not depend on how many
sequences are searched together.

Rule: novel_family_hit = the best-scoring family HMM (full-sequence bit score) if
  (1) its full-sequence E-value <= 1e-10, and
  (2) its bit score is higher than the query's PF01036 full-sequence bit score (0 if PF01036 does not hit).
Condition (2) is needed because the family HMMs also hit ordinary Type-I rhodopsins at E <= 1e-10 (the
xenorhodopsin HMM hits most of the corpus); the flag marks proteins that look more like one of the five
families than like the generic Pfam rhodopsin model.

The flag is a pointer to inspect a protein, not a membership call and not a function call. The scorer and the
typeI_detected_070 call are unchanged. The family HMM seeds overlap the external validation positives, so flag rates
on those positives are circular.

  python tools/family_flag.py query.faa [--release releases/v1.6.0] -o flags.tsv
"""
import argparse, glob, os, shutil, subprocess, sys, tempfile
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
FAMILIES = ["MerMAID", "bestrhodopsin", "schizorhodopsin", "viral_rhodopsin", "xenorhodopsin"]
EVALUE_MAX = 1e-10
Z_FIXED = 5466   # E-values computed for a fixed search space (corpus size) so a flag does not depend on batch size
COLS = ["query", "novel_family_hit", "novel_family_evalue", "novel_family_bits", "pf01036_bits"]


def _tbl(path):
    rows = [l.split()[:6] for l in open(path) if l.strip() and not l.startswith("#")]
    d = pd.DataFrame(rows, columns=["query", "t_acc", "model", "m_acc", "evalue", "bits"])
    d["evalue"] = d.evalue.astype(float)
    d["bits"] = d.bits.astype(float)
    return d


def flags(query_fa, release, workdir=None, threads=2):
    hmm_dir = os.path.join(release, "scorer", "family_hmms")
    pf = os.path.join(release, "scorer", "PF01036.25.hmm")
    hs = shutil.which("hmmsearch") or "hmmsearch"
    wd = workdir or tempfile.mkdtemp(prefix="famflag_")
    os.makedirs(wd, exist_ok=True)
    fam = os.path.join(wd, "family5.hmm")
    with open(fam, "w") as out:
        for f in FAMILIES:
            out.write(open(os.path.join(hmm_dir, f + ".hmm")).read())
    run = lambda h, t: subprocess.run([hs, "--cpu", str(threads), "-Z", str(Z_FIXED), "-E", "1e-5", "--tblout", t, "-o", os.devnull, h, query_fa],
                                      check=True)
    tf, tp = os.path.join(wd, "family.tbl"), os.path.join(wd, "pf01036.tbl")
    run(fam, tf)
    run(pf, tp)
    ids = [l[1:].split()[0] for l in open(query_fa) if l.startswith(">")]
    f, p = _tbl(tf), _tbl(tp)
    f["model"] = f.model.str.replace(r"\.aln$", "", regex=True)
    best = f.sort_values(["bits", "model"], ascending=[False, True]).drop_duplicates("query").set_index("query")
    pfb = p.groupby("query").bits.max()
    out = []
    for q in ids:
        pb = float(pfb.get(q, 0.0))
        hit, ev, bits = None, None, None
        if q in best.index:
            b = best.loc[q]
            ev, bits = float(b.evalue), float(b.bits)
            if ev <= EVALUE_MAX and bits > pb:
                hit = b.model
        out.append(dict(query=q, novel_family_hit=hit, novel_family_evalue=ev, novel_family_bits=bits, pf01036_bits=pb))
    return pd.DataFrame(out, columns=COLS)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query")
    ap.add_argument("--release", default=os.path.join(HERE, "..", "releases", "v1.6.0"))
    ap.add_argument("-o", "--out", default="family_flags.tsv")
    ap.add_argument("--threads", type=int, default=2)
    a = ap.parse_args()
    d = flags(a.query, a.release, threads=a.threads)
    d.to_csv(a.out, sep="\t", index=False)
    print(f"{len(d)} queries -> {a.out}; flagged {d.novel_family_hit.notna().sum()}")


if __name__ == "__main__":
    main()
