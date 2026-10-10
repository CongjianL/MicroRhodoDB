#!/usr/bin/env python
"""WP4 - define MR_CLD3 clades on MR_RT_003 and test their robustness.

Clade rule (top-down): starting at the root of the (rooted) ingroup, a node becomes a clade if the branch leading
to it has UFBoot >= ufb and SH-aLRT >= alrt and it holds min..max ingroup tips; otherwise its children are visited.
Ingroup = all tips except the heliorhodopsin outgroup. Tips not inside any clade are 'backbone_unassigned'.
Rootings: outgroup (heliorhodopsins) or midpoint.

Usage:
  define_clades.py grid  tree1[,tree2,...] tips_annot.tsv outdir     # robustness grid
  define_clades.py final tree tips_annot.tsv outdir                   # primary setting + naming
"""
import sys, os, itertools
import numpy as np, pandas as pd
from ete3 import Tree
from sklearn.metrics import adjusted_rand_score

PRIMARY = dict(rooting="outgroup", min_size=5, max_size=100, ufb=95, alrt=80)
SUB = dict(min_size=3, max_size=40, ufb=95, alrt=80)   # level-2 subclades, nested in level-1 clades or on the backbone


def load(treefile, annot):
    t = Tree(treefile, format=1)
    for n in t.traverse():
        if not n.is_leaf():
            alrt = ufb = np.nan
            if n.name and "/" in n.name:
                a, b = n.name.split("/")[:2]
                alrt, ufb = float(a), float(b)
            n.add_features(alrt=alrt, ufb=ufb)
    return t


def root(t, mode, outgroup):
    t = t.copy("cpickle")
    if mode == "midpoint":
        t.set_outgroup(t.get_midpoint_outgroup())
    else:
        og = [l for l in t.get_leaves() if l.name in outgroup]
        t.set_outgroup(og[0])
        anc = t.get_common_ancestor(og)
        if anc is t:  # outgroup spans the root after first rerooting: root on the complement
            ing = [l for l in t.get_leaves() if l.name not in outgroup]
            t.set_outgroup(t.get_common_ancestor(ing))
            anc = t.get_common_ancestor(og)
        if anc is not t:
            t.set_outgroup(anc)
    return t


def clades(t, outgroup, min_size, max_size, ufb, alrt):
    out = []

    def ing(n):
        return [l.name for l in n.get_leaves() if l.name not in outgroup]

    def visit(n):
        tips = ing(n)
        if not tips:
            return
        sup = (not n.is_leaf()) and (getattr(n, "ufb", np.nan) >= ufb) and (getattr(n, "alrt", np.nan) >= alrt)
        if sup and min_size <= len(tips) <= max_size and not set(l.name for l in n.get_leaves()) & outgroup:
            out.append((tips, n.ufb, n.alrt))
            return
        for c in n.children:
            visit(c)

    visit(t)
    return out


def partition(cl, alltips):
    lab = {}
    for i, (tips, _, _) in enumerate(cl):
        for x in tips:
            lab[x] = i
    k = len(cl)
    res = []
    for x in alltips:
        if x in lab:
            res.append(lab[x])
        else:
            res.append(k); k += 1  # singleton
    return np.array(res)


def outgroup_monophyly(t, outgroup):
    t2 = root(t, "outgroup", outgroup)
    anc = t2.get_common_ancestor([l for l in t2.get_leaves() if l.name in outgroup])
    return set(l.name for l in anc.get_leaves()) == set(outgroup)


def grid(trees, annot, outdir):
    A = pd.read_csv(annot, sep="\t")
    og = set(A.loc[A.tip_role == "outgroup_heliorhodopsin", "source_acc"])
    ingroup = sorted(set(A.source_acc) - og)
    settings = []
    for ti, tf in enumerate(trees):
        t = load(tf, A)
        print(tf, "outgroup monophyletic:", outgroup_monophyly(t, og))
        for rooting in ("outgroup", "midpoint"):
            tr = root(t, rooting, og)
            for (mn, mx) in ((3, 60), (5, 100), (10, 200)):
                for (u, a) in ((95, 80), (90, 70), (99, 90)):
                    cl = clades(tr, og, mn, mx, u, a)
                    settings.append(dict(tree=os.path.basename(tf), rooting=rooting, min_size=mn, max_size=mx,
                                         ufb=u, alrt=a, n_clades=len(cl),
                                         n_tips_in_clades=sum(len(c[0]) for c in cl),
                                         part=partition(cl, ingroup), clades=cl))
    ref = [s for s in settings if s["tree"] == os.path.basename(trees[0]) and all(s[k] == v for k, v in PRIMARY.items())][0]
    rows = []
    refsets = [set(c[0]) for c in ref["clades"]]
    for s in settings:
        js = []
        for rs in refsets:
            best = max((len(rs & set(c[0])) / len(rs | set(c[0])) for c in s["clades"]), default=0)
            js.append(best)
        rows.append({k: v for k, v in s.items() if k not in ("part", "clades")} |
                    dict(ari_vs_primary=adjusted_rand_score(ref["part"], s["part"]),
                         median_best_jaccard=float(np.median(js)),
                         frac_primary_clades_recovered_j1=float(np.mean([j == 1 for j in js])),
                         frac_primary_clades_j_ge_0_8=float(np.mean([j >= 0.8 for j in js]))))
    pd.DataFrame(rows).to_csv(f"{outdir}/clade_robustness_grid.tsv", sep="\t", index=False)
    # per primary clade stability across the 3 trees under the primary setting
    per = []
    prim = [s for s in settings if all(s[k] == v for k, v in PRIMARY.items())]
    for i, rs in enumerate(refsets):
        r = dict(clade_index=i, size=len(rs))
        for s in prim:
            r[f"jaccard_{s['tree']}"] = max((len(rs & set(c[0])) / len(rs | set(c[0])) for c in s["clades"]), default=0)
        mid = [s for s in settings if s["tree"] == ref["tree"] and s["rooting"] == "midpoint"
               and s["min_size"] == 5 and s["max_size"] == 100 and s["ufb"] == 95]
        r["jaccard_midpoint"] = max((len(rs & set(c[0])) / len(rs | set(c[0])) for c in mid[0]["clades"]), default=0)
        per.append(r)
    pd.DataFrame(per).to_csv(f"{outdir}/clade_stability_primary.tsv", sep="\t", index=False)
    print(pd.DataFrame(rows).drop(columns=["tree"]).groupby(["rooting", "min_size", "ufb"]).mean(numeric_only=True)
          .round(3).to_string())


def final(tf, annot, outdir):
    A = pd.read_csv(annot, sep="\t")
    og = set(A.loc[A.tip_role == "outgroup_heliorhodopsin", "source_acc"])
    t = root(load(tf, A), PRIMARY["rooting"], og)
    t.write(format=1, outfile=f"{outdir}/MR_RT_003.rooted.treefile")
    cl = clades(t, og, PRIMARY["min_size"], PRIMARY["max_size"], PRIMARY["ufb"], PRIMARY["alrt"])
    # order clades by position in the rooted tree (deterministic ladderised leaf order)
    t.ladderize()
    order = {l.name: i for i, l in enumerate(t.get_leaves())}
    cl = sorted(cl, key=lambda c: min(order[x] for x in c[0]))
    A = A.set_index("source_acc")
    rows, mem = [], []
    for i, (tips, ufb, alrt) in enumerate(cl, 1):
        cid = f"MR_CLD3_{i:03d}"
        a = A.loc[tips]
        def dom(col):
            v = a[col].dropna()
            v = v[v != ""]
            if not len(v):
                return ("", 0.0)
            vc = v.value_counts()
            return (vc.index[0], round(vc.iloc[0] / len(v), 3))
        sf, sff = dom("subfamily_v14")
        mo, mof = dom("helixC_motif")
        dm, dmf = dom("tax_domain")
        ph, phf = dom("phylum")
        e1 = a.exp_class.dropna()
        e1c = ";".join(f"{k}x{v}" for k, v in e1.value_counts().items())
        func = e1.iloc[0] if len(e1) and e1.nunique() == 1 else ""
        anchors = ";".join(a.index[a.exp_class.notna() | a.tip_role.isin(["seed", "anchor_characterized"])])
        rows.append(dict(clade_id=cid, n_tips=len(tips), ufboot=ufb, sh_alrt=alrt, dominant_subfamily_v14=sf,
                         subfamily_fraction=sff, dominant_helixC_motif=mo, motif_fraction=mof, dominant_domain=dm,
                         domain_fraction=dmf, dominant_phylum=ph, phylum_fraction=phf, e1_classes=e1c,
                         clade_function_e1_consensus=func, n_anchors=len(anchors.split(";")) if anchors else 0,
                         anchors=anchors))
        mem += [(cid, x) for x in tips]
    C = pd.DataFrame(rows)
    C.to_csv(f"{outdir}/MR_CLD3_clades.tsv", sep="\t", index=False)
    # level 2: supported subclades strictly inside each level-1 clade, plus supported backbone groups
    tip2c = {x: cid for cid, x in mem}
    sub_all = []
    def collect(n):
        tips = [l.name for l in n.get_leaves() if l.name not in og]
        if not n.is_leaf() and getattr(n, "ufb", np.nan) >= SUB["ufb"] and getattr(n, "alrt", np.nan) >= SUB["alrt"] and SUB["min_size"] <= len(tips) <= SUB["max_size"] \
                and not set(l.name for l in n.get_leaves()) & og:
            parents = {tip2c.get(x, "backbone") for x in tips}
            if len(parents) == 1:
                p = parents.pop()
                l1 = [c for c in cl if set(c[0]) == set(tips)]
                if not l1:
                    sub_all.append((p, tips, n.ufb, n.alrt)); return
        for c in n.children:
            collect(c)
    collect(t)
    srows, smem, cnt = [], [], {}
    for p, tips, u, al in sorted(sub_all, key=lambda c: min(order[x] for x in c[1])):
        cnt[p] = cnt.get(p, 0) + 1
        sid = f"{p}.{cnt[p]:02d}" if p != "backbone" else f"MR_CLD3_B{cnt[p]:02d}"
        a = A.loc[tips]
        e1 = a.exp_class.dropna()
        srows.append(dict(subclade_id=sid, parent_clade=p, n_tips=len(tips), ufboot=u, sh_alrt=al,
                          dominant_subfamily_v14=(a.subfamily_v14.dropna().value_counts().index[0] if a.subfamily_v14.notna().any() else ""),
                          dominant_helixC_motif=(a.helixC_motif.dropna().value_counts().index[0] if a.helixC_motif.notna().any() else ""),
                          dominant_domain=(a.tax_domain.dropna().value_counts().index[0] if a.tax_domain.notna().any() else ""),
                          dominant_phylum=(a.phylum.dropna().value_counts().index[0] if a.phylum.notna().any() else ""),
                          e1_classes=";".join(f"{k}x{v}" for k, v in e1.value_counts().items()),
                          clade_function_e1_consensus=e1.iloc[0] if len(e1) and e1.nunique() == 1 else "",
                          e1_members=";".join(f"{i}:{r.protein_label}" for i, r in a[a.exp_class.notna()].iterrows())))
        smem += [(sid, x) for x in tips]
    pd.DataFrame(srows).to_csv(f"{outdir}/MR_CLD3_subclades.tsv", sep="\t", index=False)
    S = pd.DataFrame(smem, columns=["subclade_id", "source_acc"])
    M = pd.DataFrame(mem, columns=["clade_id", "source_acc"])
    allin = [x for x in A.index if x not in og]
    un = sorted(set(allin) - set(M.source_acc))
    M = pd.concat([M, pd.DataFrame({"clade_id": "backbone_unassigned", "source_acc": un})])
    M = M.merge(S, on="source_acc", how="left")
    M["subclade_id"] = M.subclade_id.fillna("")
    M.to_csv(f"{outdir}/MR_CLD3_tips.tsv", sep="\t", index=False)
    print(len(C), "clades;", int(C.n_tips.sum()), "tips in clades;", len(un), "backbone tips;", len(srows), "subclades covering",
          len(S), "tips")


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "grid":
        grid(sys.argv[2].split(","), sys.argv[3], sys.argv[4])
    else:
        final(sys.argv[2], sys.argv[3], sys.argv[4])
