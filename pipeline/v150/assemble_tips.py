#!/usr/bin/env python
"""WP4 - assemble MR_RT_003 reference tip set.

tips = cl0.6 representatives of full-length members (eligible set)
     + experimentally characterised anchors (Tier A + characterized_set, eligible, deduplicated at 80% id)
     + Type-I seeds
     + boundary exemplars (schizorhodopsins; NCBI)
     + heliorhodopsin outgroup (full-length, cl0.4 representatives, capped)
Writes tips.faa and tips.tsv (source_acc, tip_role).
"""
import argparse, os, subprocess, sqlite3
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


def mm_cluster(seqd, ids, minid, cov, wd, threads):
    os.makedirs(wd, exist_ok=True)
    with open(f"{wd}/in.faa", "w") as f:
        for i in ids:
            f.write(f">{i}\n{seqd[i]}\n")
    subprocess.run(["mmseqs", "easy-cluster", f"{wd}/in.faa", f"{wd}/cl", f"{wd}/tmp", "--min-seq-id", str(minid),
                    "-c", str(cov), "-s", "7.5", "--threads", str(threads)], check=True, stdout=subprocess.DEVNULL)
    return pd.read_csv(f"{wd}/cl_cluster.tsv", sep="\t", header=None, names=["rep", "mem"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--treedir", required=True)
    ap.add_argument("--allfaa", required=True)
    ap.add_argument("--charset", required=True)
    ap.add_argument("--boundary_faa", required=True)
    ap.add_argument("--n_helio", type=int, default=15)
    ap.add_argument("--threads", type=int, default=16)
    a = ap.parse_args()
    T = a.treedir
    seqs = read_fasta(a.allfaa)
    elig = pd.read_csv(f"{T}/eligible.tsv", sep="\t")
    E = set(elig.source_acc)
    reps = list(read_fasta(f"{T}/cl0.6_rep_seq.fasta"))
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    tierA = set(pd.read_sql("select distinct source_acc from tier_a_assertion", con).source_acc)
    seeds = pd.read_sql("select acc, subfamily from seed", con)
    cs = pd.read_csv(a.charset, sep="\t")
    anchors = sorted((tierA | set(cs.source_acc)) & E)
    rows = [(r, "cl0.6_representative") for r in reps]
    have = set(reps)
    order = sorted(anchors, key=lambda x: (x not in tierA, x))
    acl = mm_cluster(seqs, order, 0.8, 0.8, f"{T}/_anchors", a.threads)
    for r in acl.rep.unique():
        mems = set(acl.loc[acl.rep == r, "mem"])
        if mems & have:
            continue
        pick = sorted(mems, key=lambda x: (x not in tierA, x))[0]
        rows.append((pick, "anchor_characterized"))
        have.add(pick)
    for s in seeds[seeds.subfamily != "heliorhodopsin"].acc:
        if s not in have and s in seqs:
            rows.append((s, "seed"))
            have.add(s)
    m = pd.read_sql("select m.source_acc, q.hmm_cov, p.length from membership m join qc_feature q using(source_acc) "
                    "join protein p using(source_acc) where membership_status='heliorhodopsin'", con)
    hel = m[(m.length.between(220, 320)) & (m.hmm_cov >= 0.8)].source_acc.tolist()
    hel_seed = [s for s in seeds[seeds.subfamily == "heliorhodopsin"].acc if s in seqs]
    hcl = mm_cluster(seqs, hel, 0.4, 0.8, f"{T}/_helio", a.threads)
    sizes = hcl.groupby("rep").size().sort_values(ascending=False)
    hpick = list(hel_seed)
    for r in sizes.index:
        if len(hpick) >= a.n_helio:
            break
        if r not in hpick:
            hpick.append(r)
    rows += [(h, "outgroup_heliorhodopsin") for h in hpick]
    for k, v in read_fasta(a.boundary_faa).items():
        seqs[k] = v
        rows.append((k, "boundary_schizorhodopsin"))
    tips = pd.DataFrame(rows, columns=["source_acc", "tip_role"])
    assert tips.source_acc.is_unique
    with open(f"{T}/tips.faa", "w") as f:
        for t in tips.source_acc:
            f.write(f">{t}\n{seqs[t]}\n")
    tips.to_csv(f"{T}/tips.tsv", sep="\t", index=False)
    print(tips.tip_role.value_counts().to_string(), "\ntotal", len(tips))


if __name__ == "__main__":
    main()
