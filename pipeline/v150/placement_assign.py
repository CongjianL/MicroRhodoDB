#!/usr/bin/env python
"""WP4 - summarise EPA-ng placements on MR_RT_003 and assign MR_CLD3 clades / subclades.

For each query: best edge, best LWR, number of edges in the 95% LWR credible set, EDPL-like dispersion
(LWR-weighted mean pendant length), and clade support = summed LWR over edges inside a clade (all edges whose
child-side tips are a subset of the clade, including the clade stem edge; tree rooted on the heliorhodopsin outgroup).
Clade call: LWR_clade >= 0.90 -> 'assigned'; 0.50-0.90 -> 'tentative'; otherwise 'unassigned'.
Outgroup placement (LWR summed over outgroup edges >= 0.5) -> 'outgroup_heliorhodopsin'.
clade_call_qc: assigned/tentative calls with LWR-weighted pendant > 1.0 become distant_assigned / distant_tentative.

Usage: placement_assign.py tips_annot.tsv MR_CLD3_tips.tsv out_prefix tag1=file1.jplace [tag2=file2.jplace ...]
The first tag is the primary model; the others are model-sensitivity runs.
"""
import sys, json, re
import numpy as np, pandas as pd
from ete3 import Tree

PENDANT_MAX = 1.0


def parse_jplace(fn):
    j = json.load(open(fn))
    nwk = re.sub(r"([^(),:;]*):([0-9.eE+-]+)\{(\d+)\}", lambda m: f"{m.group(1)}@E{m.group(3)}:{m.group(2)}", j["tree"])
    t = Tree(nwk, format=1)
    fields = j["fields"]
    rows = []
    for p in j["placements"]:
        names = [n if isinstance(n, str) else n[0] for n in p.get("n", p.get("nm", []))]
        for nm in names:
            for r in p["p"]:
                d = dict(zip(fields, r))
                rows.append((nm, int(d["edge_num"]), float(d["like_weight_ratio"]), float(d["pendant_length"])))
    return t, pd.DataFrame(rows, columns=["q", "edge", "lwr", "pendant"])


def edge_sets(t, outgroup):
    """Child-side tip set of every jplace edge in the outgroup-rooted sense, computed WITHOUT rerooting
    (ete3 rerooting does not move custom node features with their branches).
    Each edge splits the tips into (below, rest); the child side is the half without outgroup tips.
    Edges where one half is entirely outgroup are returned as that outgroup subset."""
    leaves = t.get_leaves()
    for l in leaves:
        l.add_feature("tip", l.name.split("@E")[0])
    alltips = frozenset(l.tip for l in leaves)
    es = {}
    for n in t.traverse():
        if "@E" not in (n.name or ""):
            continue
        e = int(n.name.split("@E")[1])
        below = frozenset(l.tip for l in n.get_leaves())
        rest = alltips - below
        if below <= outgroup:
            es[e] = below
        elif rest <= outgroup:
            es[e] = rest
        elif not (below & outgroup):
            es[e] = below
        elif not (rest & outgroup):
            es[e] = rest
        else:
            raise ValueError(f"outgroup not monophyletic across edge {e}")
    return es


def assign(P, es, groups, outgroup):
    """groups: dict name -> set(tips). Returns per-query best group and its LWR."""
    edge2grp = {}
    for e, tips in es.items():
        if tips <= outgroup:
            edge2grp[e] = ["__outgroup__"]
            continue
        edge2grp[e] = [g for g, s in groups.items() if tips <= s]
    rows = []
    for q, g in P.groupby("q"):
        acc = {}
        for e, w in zip(g.edge, g.lwr):
            for gg in edge2grp.get(e, []):
                acc[gg] = acc.get(gg, 0) + w
        if acc:
            # most specific group with max support: groups are nested-free within one level
            best = max(acc.items(), key=lambda kv: kv[1])
        else:
            best = ("", 0.0)
        rows.append((q, best[0], best[1]))
    return pd.DataFrame(rows, columns=["q", "group", "group_lwr"])


def call(gr, lwr):
    if gr == "__outgroup__" and lwr >= 0.5:
        return "outgroup_heliorhodopsin"
    if gr and gr != "__outgroup__" and lwr >= 0.9:
        return "assigned"
    if gr and gr != "__outgroup__" and lwr >= 0.5:
        return "tentative"
    return "unassigned"


def main():
    annot, tipsf, out = sys.argv[1:4]
    runs = [a.split("=", 1) for a in sys.argv[4:]]
    A = pd.read_csv(annot, sep="\t")
    og = frozenset(A.loc[A.tip_role == "outgroup_heliorhodopsin", "source_acc"])
    T = pd.read_csv(tipsf, sep="\t").fillna("")
    L1 = {c: set(g.source_acc) for c, g in T[T.clade_id != "backbone_unassigned"].groupby("clade_id")}
    L2 = {c: set(g.source_acc) for c, g in T[T.subclade_id != ""].groupby("subclade_id")}
    res = []
    for tag, fn in runs:
        t, P = parse_jplace(fn)
        es = edge_sets(t, og)
        P = P.sort_values(["q", "lwr"], ascending=[True, False])
        best = P.groupby("q").first().reset_index()
        cs = P.assign(c=P.groupby("q").lwr.cumsum())
        ncred = cs.groupby("q").apply(lambda g: int((g.c.shift(fill_value=0) < 0.95).sum()), include_groups=False)
        edpl = P.groupby("q").apply(lambda g: float((g.lwr * g.pendant).sum() / g.lwr.sum()), include_groups=False)
        a1 = assign(P, es, L1, og).rename(columns={"group": "clade_id", "group_lwr": "clade_lwr"})
        a2 = assign(P, es, L2, og).rename(columns={"group": "subclade_id", "group_lwr": "subclade_lwr"})
        r = best.rename(columns={"edge": "best_edge", "lwr": "best_lwr", "pendant": "best_pendant"}) \
            .merge(a1, on="q").merge(a2, on="q")
        r["n_credible95"] = r.q.map(ncred)
        r["lwr_weighted_pendant"] = r.q.map(edpl)
        r["clade_call"] = [call(g, w) for g, w in zip(r.clade_id, r.clade_lwr)]
        r["subclade_call"] = [call(g, w) for g, w in zip(r.subclade_id, r.subclade_lwr)]
        r.loc[r.clade_call == "outgroup_heliorhodopsin", ["clade_id"]] = "outgroup_heliorhodopsin"
        r.loc[r.clade_id == "__outgroup__", "clade_id"] = ""
        r.loc[r.subclade_id == "__outgroup__", "subclade_id"] = ""
        # pendant QC: LWR is conditional on the query belonging on the tree; long pendants flag distant /
        # non-homologous queries (members p99 = 0.57; non-homologous 7TM negatives min 2.17)
        r["placement_qc"] = np.where(r.lwr_weighted_pendant > PENDANT_MAX, "long_pendant", "ok")
        r["clade_call_qc"] = np.where((r.placement_qc == "long_pendant") & r.clade_call.isin(["assigned", "tentative"]),
                                      "distant_" + r.clade_call, r.clade_call)
        r.insert(1, "model_tag", tag)
        res.append(r.rename(columns={"q": "source_acc"}))
        print(tag, len(r), r.clade_call.value_counts().to_dict(), flush=True)
    R = pd.concat(res, ignore_index=True)
    R.to_csv(f"{out}_placements_all_models.tsv", sep="\t", index=False)
    prim = runs[0][0]
    p = R[R.model_tag == prim].set_index("source_acc")
    rows = []
    for tag, _ in runs[1:]:
        o = R[R.model_tag == tag].set_index("source_acc").reindex(p.index)
        same_edge = (o.best_edge == p.best_edge)
        c1 = p.clade_call.isin(["assigned"]) | o.clade_call.isin(["assigned"])
        same_clade = (o.clade_id == p.clade_id)
        rows.append(dict(primary=prim, alternative=tag, n=len(p), frac_same_best_edge=same_edge.mean(),
                         frac_same_clade_all=same_clade.mean(),
                         n_assigned_either=int(c1.sum()), frac_same_clade_among_assigned=same_clade[c1].mean(),
                         n_clade_changed_among_assigned=int((~same_clade[c1]).sum()),
                         frac_same_subclade=(o.subclade_id == p.subclade_id).mean()))
    pd.DataFrame(rows).to_csv(f"{out}_model_sensitivity.tsv", sep="\t", index=False)
    print(pd.DataFrame(rows).round(4).to_string())


if __name__ == "__main__":
    main()
