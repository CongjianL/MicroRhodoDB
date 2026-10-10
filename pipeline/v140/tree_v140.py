"""tree_v140.py — MR_RT_002 promotion: tree_node/tree_edge/reference_clade(_tip) build.

Conventions reverse-engineered from frozen MR_RT_001 rows (v1.3.0 DB) and verified:
  - tree_node/tree_edge store the AS-PARSED unrooted treefile (Bio.Phylo read;
    trifurcating root = N001). Verified: MR_RT_001 root N001 has 3 children,
    368 nodes / 367 edges = 2n-2 / 2n-3 for n=185 tips.
  - Node ids: DFS preorder from root; tips numbered T001.. in a separate counter
    from internals N001.. (verified: both sequences exactly numeric on MR_RT_001).
  - Edge ids: E001.. assigned at PARENT visit (all child edges of a node numbered
    in child order before recursing) — verified sequential on MR_RT_001.
  - tree_node.branch_length == incoming edge length (root NULL); internal label
    'sh_alrt/ufboot' parsed to REAL columns; root label NULL.
  - Clade enumeration (v1 algorithm, reproduced stored MR_CLD_001..060 exactly in
    v1.3-era probe): fresh parse -> root_at_midpoint() -> find_clades(order='level'),
    keep 3<=n_tips<=60, assign ids PRE-dedup (kept ids retain gaps), then
    drop_duplicates(subset=['n_tips','n_tierA_anchors'], keep='first').
  - Anchors: v1 used 24 is_anchor representatives (all tier-A holdouts) from
    backbone_selection.tsv (does not survive; only 6/24 are among MR_RT_002 tips).
    v1.4.0 uses tier-A accessions (tier_a_assertion/tier_a_evidence) present among
    the tree tips (17/46) — the DB-grounded generalization of the same concept.
  - reference_clade.tree_node_id = as-parsed internal node whose descendant tip set
    equals the clade tip set; edge_id = its incoming edge (verified 60/60 on MR_RT_001).
  - parent_clade_id = smallest strictly-containing KEPT clade by tip set
    (verified 60/60 on MR_RT_001).
  - Root-side complement clades (midpoint-root artifacts whose tip set is the
    COMPLEMENT of an as-parsed subtree) are not representable in the as-parsed
    orientation and are excluded from storage; recorded in provenance
    (MR_RT_002: 4 such clades — MR_CLD2_018/027/040/057, nested sets of 51/40/38/8
    tips containing the two singleton root-adjacent tips A0A060H1D7 + F2TZN0).
"""
from Bio import Phylo
import pandas as pd

NS_CLADE = 'MR_CLD2'
TREE_ID = 'MR_RT_002'
MIN_TIPS, MAX_TIPS = 3, 60


def build_tree_rows(treefile, tree_id=TREE_ID):
    """Parse as-is; return (node_rows, edge_rows, id_of, desc_tips)."""
    tree = Phylo.read(treefile, 'newick')
    node_rows, edge_rows, id_of = [], [], {}
    counters = {'tip': 0, 'int': 0, 'edge': 0}

    def visit(clade):
        if clade.is_terminal():
            counters['tip'] += 1
            nid = f"T{counters['tip']:03d}"
            node_rows.append(dict(node_id=nid, tree_id=tree_id, kind='tip', label=None,
                                  source_acc=clade.name, sh_alrt=None, ufboot=None,
                                  branch_length=clade.branch_length))
        else:
            counters['int'] += 1
            nid = f"N{counters['int']:03d}"
            if clade.name and '/' in clade.name:
                sh, uf = clade.name.split('/')
                label, sh_v, uf_v = clade.name, float(sh), float(uf)
            else:
                label, sh_v, uf_v = None, None, None
            node_rows.append(dict(node_id=nid, tree_id=tree_id, kind='internal', label=label,
                                  source_acc=None, sh_alrt=sh_v, ufboot=uf_v,
                                  branch_length=clade.branch_length))
        id_of[clade] = nid
        for ch in clade.clades:  # edges numbered at parent visit, child order
            counters['edge'] += 1
            edge_rows.append(dict(edge_id=f"E{counters['edge']:03d}", tree_id=tree_id,
                                  parent_node=nid, child_node=None, length=ch.branch_length,
                                  _child=ch))
        for ch in clade.clades:
            visit(ch)

    visit(tree.root)
    for e in edge_rows:
        e['child_node'] = id_of[e.pop('_child')]

    desc_tips = {}

    def collect(clade):
        ts = frozenset(t.name for t in clade.get_terminals())
        if not clade.is_terminal():
            desc_tips[id_of[clade]] = ts
        for ch in clade.clades:
            collect(ch)

    collect(tree.root)
    return node_rows, edge_rows, id_of, desc_tips


def enumerate_clades(treefile, anchor_set, ns=NS_CLADE):
    """Midpoint-root a fresh parse; enumerate level-order; pre-dedup ids; dedup."""
    tree = Phylo.read(treefile, 'newick')
    tree.root_at_midpoint()
    out = []
    cid = 0
    for cl in tree.find_clades(order='level'):
        terms = cl.get_terminals()
        if MIN_TIPS <= len(terms) <= MAX_TIPS:
            names = [t.name for t in terms]
            cid += 1
            anch = [n for n in names if n in anchor_set]
            out.append(dict(clade_id=f'{ns}_{cid:03d}', n_tips=len(names),
                            n_tierA_anchors=len(anch),
                            anchor_members=';'.join(anch) if anch else None,
                            tip_set=frozenset(names)))
    raw = pd.DataFrame(out)
    kept = raw.drop_duplicates(subset=['n_tips', 'n_tierA_anchors'], keep='first').reset_index(drop=True)
    return kept


def map_clades(kept, desc_tips, edge_rows):
    """Attach tree_node_id/edge_id; drop root-side complement clades; parentage."""
    tipset2node = {ts: nid for nid, ts in desc_tips.items()}
    in_edge = {e['child_node']: e['edge_id'] for e in edge_rows}
    kept['tree_node_id'] = kept.tip_set.map(tipset2node)
    kept['edge_id'] = kept.tree_node_id.map(lambda n: in_edge.get(n) if pd.notna(n) else None)
    dropped = kept[kept.tree_node_id.isna()].copy()
    stored = kept[kept.tree_node_id.notna()].reset_index(drop=True)
    sets = {r.clade_id: r.tip_set for r in stored.itertuples()}

    def parent_of(cid):
        mine = sets[cid]
        cands = [(len(ts), o) for o, ts in sets.items() if o != cid and mine < ts]
        return min(cands)[1] if cands else None

    stored['parent_clade_id'] = stored.clade_id.map(parent_of)
    return stored, dropped
