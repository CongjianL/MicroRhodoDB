#!/usr/bin/env python
"""Deterministic SQLite -> static JSON exporter for the MicroRhodoDB website (dataset v1.6.0).

Implements docs/website/WEB_DATA_CONTRACT.md. Standard library only.

    python tools/export_web_data.py                       # repo root as cwd; writes web/public/data/
    python tools/export_web_data.py --db PATH --repo . --out web/public/data

Inputs (all opened read-only, all checksum-verified before anything is written):
    releases/v1.6.0/db/microrhododb_v1.6.0.sqlite      SHA-256 must equal EXPECTED_DB_SHA256
    refpkg/MR_RT_003/{tree,clades,tips.tsv}            SHA-256 must match refpkg/MR_RT_003/SHA256SUMS
    releases/*/structures/<acc>_esmfold.pdb            SHA-256 must equal PREDICTED_SHA256

Exit codes: 0 ok; 2 BLOCKED_DATA_SOURCE; 3 STRUCTURE_SOURCE_ANOMALY; 4 CONTRACT_VIOLATION.
No output file contains a wall-clock timestamp; two runs with the same inputs and exporter commit are
byte-identical (checked by tests/test_web_export.py). site/data.js is never read.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCHEMA_VERSION = "1.3.0"
DATASET_RELEASE = "1.6.0"
WEBSITE_VERSION = "2.0.0-pr4a"
DB_REL = "releases/v1.6.0/db/microrhododb_v1.6.0.sqlite"
EXPECTED_DB_SHA256 = "379a254356c6489a2b9e0600d501d76d22bc8e3ced4cfbdd5160fb00c3dce17f"
TREE_ID = "MR_RT_003"
REFPKG = "refpkg/MR_RT_003"
TREE_REL = f"{REFPKG}/tree/MR_RT_003.rooted.treefile"
EXPECTED_TREE_SHA256 = "c56196970698decea8384c1cad97545794268e6d8a2df2b195e7d35d5ded9aef"
REFPKG_INPUTS = ["tree/MR_RT_003.rooted.treefile", "tree/run1.treefile", "tips.tsv", "clades/MR_CLD3_tips.tsv",
                 "tips_annot.tsv"]  # tips_annot.tsv added in schema 1.2.0 (PR-4 explorer annotations)
# predicted_structure.pdb_file is relative to a historical release directory (releases/v1.0/)
PREDICTED_SHA256 = {
    "structures/A0A9X2L7U0_esmfold.pdb": "3089c414abb50907266fe397ca9cba925464a7129e72819194bdb2349f54198a",
    "structures/B0R633_esmfold.pdb": "e6edb5395e571c05517fd3c5d9820a3821c2551ec9579b5da04e3fabc2b29da4",
}
SUPPORT_RE = re.compile(r"^\d+(\.\d+)?/\d+(\.\d+)?$")
LEVEL1_RE = re.compile(r"^MR_CLD3_0\d\d$")
BACKBONE_GROUPS = ("MR_CLD3_B01", "MR_CLD3_B02")
# MR_CLD3 clade-definition rule, copied verbatim from pipeline/v150/define_clades.py (PRIMARY / SUB) and
# refpkg/MR_RT_003/README.md item 4. Used only to *report* whether a node's IQ-TREE run1 support meets the
# predefined support thresholds; never to redefine or reclassify clades (schema 1.1.0, PR-2).
CLADE_RULE = {
    "source": ["pipeline/v150/define_clades.py (PRIMARY, SUB)", "refpkg/MR_RT_003/README.md (item 4)"],
    "support_label_order": "SH-aLRT/UFBoot",
    "level1": {"rooting": "outgroup", "min_tips": 5, "max_tips": 100, "min_ufboot": 95, "min_sh_alrt": 80},
    "subclade": {"min_tips": 3, "max_tips": 40, "min_ufboot": 95, "min_sh_alrt": 80},
    "backbone_group": "well-supported backbone groups below the level-1 size floor (UFBoot >= 95 and SH-aLRT >= 80)",
    "support_test": "sh_alrt >= 80 and ufboot >= 95 (both inclusive), evaluated on the IQ-TREE run1 label of the "
                    "same bipartition",
}
# Index columns appended in schema 1.1.0 (PR-2) so Browse can filter on, and export, every legacy TSV field
# without fetching 5,299 record files. Values are identical to the record files (full precision).
INDEX_COLS_V11 = ["membership_group", "retinal_site_residue", "function_basis", "func_class_v14", "motif_class",
                  "call_conflict_detail", "wild_type_acc", "exact_duplicate_of", "e1_representative", "clade_name",
                  "tentative_clade_name", "gtdb_taxonomy", "afdb_model_id", "afdb_global_plddt", "e2_ref",
                  "e2_identity", "override_rule", "pocket_string_br", "status_reason", "lineage", "pdb_ids"]
CLADE_STATE_DEFINITIONS = {
    "confident": "Assigned to a level-1 clade or backbone group (v_master.clade_id).",
    "tentative": "No confident clade; v_master.tentative_clade_id set: primary-model placement assigned a clade but "
                 "pendant QC failed (distant placement, low confidence); not counted in clade coverage.",
    "reference_tip_unclustered": "Reference-tree tip on the backbone that belongs to no level-1 clade or backbone group.",
    "outgroup_reference_tip": "Heliorhodopsin outgroup tip of the reference tree (no clade_tip row).",
    "outgroup_placed": "Placed into the heliorhodopsin outgroup (placement clade_call = outgroup_heliorhodopsin).",
    "unassigned": "Placed but not assigned to a clade (placement clade_call = unassigned).",
    "distant": "Current placement clade_call = tentative with no tentative_clade_id (placement_call = distant_tentative).",
}
EVIDENCE_LEVEL_RE = re.compile(r"(E[1-5]) ([^;]+?)(?=; E[1-5] |\.?$)")
# Every (table, column) in which the DB stores '' and the explicit rule applied. Any other '' -> error.
EMPTY_STRING_RULES = {
    ("v_master", "clade_id"): "null (clade_state carries the meaning)",
    ("v_master", "subclade_id"): "null",
    ("pdb_structure", "ligands"): "[] (no ligand reported)",
    ("structure", "fusion_partner_domains"): "null",
    ("clade_function_consensus", "E1_classes"): "null",
}
CLADE_STATE_SQL = """
SELECT v.source_acc,
  CASE
    WHEN rc.source_acc IS NULL THEN 'outgroup_reference_tip'
    WHEN COALESCE(v.clade_id, '') <> '' THEN 'confident'
    WHEN COALESCE(v.tentative_clade_id, '') <> '' THEN 'tentative'
    WHEN rc.source = 'reference_tip' THEN 'reference_tip_unclustered'
    WHEN p.clade_call = 'outgroup_heliorhodopsin' THEN 'outgroup_placed'
    WHEN p.clade_call = 'unassigned' THEN 'unassigned'
    WHEN p.clade_call = 'tentative' THEN 'distant'
    ELSE 'UNMAPPED'
  END AS clade_state
FROM v_master v
LEFT JOIN record_clade rc ON rc.source_acc = v.source_acc
LEFT JOIN placement p ON p.source_acc = v.source_acc AND p.is_current = 1 AND p.tree_id = 'MR_RT_003'
"""
CLADE_STATES = ["confident", "tentative", "reference_tip_unclustered", "outgroup_reference_tip",
                "outgroup_placed", "unassigned", "distant"]
# v_master column -> path in records/<MRDB>.json SourceRecord (every v_master column is exported)
V_MASTER_FIELD_MAP = {
    "mrdb_acc": "@entry.mrdb_acc", "source_acc": "source_acc", "protein_name": "protein_name",
    "organism": "organism", "organism_id": "organism_id", "tax_domain": "tax_domain", "length": "length",
    "membership_status": "membership.status", "boundary_subtype": "membership.boundary_subtype",
    "membership_score": "membership.score", "retinal_site_residue": "motifs.retinal_site_residue",
    "func_class": "function.func_class", "evidence_level": "function.evidence_level",
    "function_basis": "function.function_basis", "func_class_v14": "function.func_class_v14",
    "helixC_motif": "motifs.helixC_motif", "motif_class": "motifs.motif_class",
    "call_conflict": "function.call_conflict", "call_conflict_detail": "function.call_conflict_detail",
    "is_engineered": "engineering.is_engineered", "wild_type_acc": "engineering.wild_type_acc",
    "counts_eligible": "engineering.counts_eligible", "exact_duplicate_of": "exact_duplicate_of",
    "e1_representative": "function.e1_representative", "clade_id": "phylogeny.clade_id",
    "subclade_id": "phylogeny.subclade_id", "clade_source": "phylogeny.clade_source",
    "clade_lwr": "phylogeny.clade_lwr", "placement_call": "phylogeny.placement_call",
    "clade_name": "phylogeny.clade_name", "tentative_clade_id": "phylogeny.tentative_clade_id",
    "tentative_clade_name": "phylogeny.tentative_clade_name", "gtdb_taxonomy": "gtdb.taxonomy",
    "afdb_model_id": "structures.afdb.model_id", "afdb_global_plddt": "structures.afdb.global_plddt",
}
BOOL_V_MASTER = {"call_conflict", "is_engineered", "counts_eligible"}


class ExportError(Exception):
    CODES = {"BLOCKED_DATA_SOURCE": 2, "STRUCTURE_SOURCE_ANOMALY": 3, "CONTRACT_VIOLATION": 4}

    def __init__(self, code, msg):
        super().__init__(f"{code}: {msg}")
        self.code = code


def require(cond, msg, code="CONTRACT_VIOLATION"):
    if not cond:
        raise ExportError(code, msg)


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def dumps(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"


def b(v):
    """0/1 integer flag -> bool (None stays None)."""
    if v is None:
        return None
    require(v in (0, 1), f"non-binary flag value {v!r}")
    return bool(v)


def as_int(v):
    if v is None:
        return None
    require(float(v) == int(float(v)), f"non-integral value {v!r}")
    return int(float(v))


def ne(v, table, col):
    """Apply the documented ''-rule for (table, col); fail on any undocumented ''."""
    if v == "":
        require((table, col) in EMPTY_STRING_RULES, f"undocumented empty string in {table}.{col}")
        return None
    return v


# ----------------------------------------------------------------------------------------------- Newick
class Node:
    __slots__ = ("name", "length", "children", "parent")

    def __init__(self):
        self.name, self.length, self.children, self.parent = "", None, [], None


def parse_newick(s, spans=None):
    """Parse Newick. If `spans` is a dict, spans[id(internal_node)] = (start, end) of the internal-node label in
    `s` (end == start when unlabelled), so labels can be replaced without re-serialising branch lengths."""
    require(s.strip().endswith(";"), "Newick does not end with ';'")
    if spans is None:
        s = s.strip()
    root = Node()
    cur, i, n = root, 0, len(s.rstrip()) - 1
    stack = []
    while i < n:
        c = s[i]
        if c == "(":
            child = Node(); child.parent = cur; cur.children.append(child)
            stack.append(cur); cur = child; i += 1
        elif c == ",":
            parent = stack[-1]
            child = Node(); child.parent = parent; parent.children.append(child)
            cur = child; i += 1
        elif c == ")":
            cur = stack.pop(); i += 1
            if spans is not None:
                spans[id(cur)] = (i, i)
        elif c == ":":
            j = i + 1
            while j < n and s[j] not in ",();":
                j += 1
            cur.length = float(s[i + 1:j]); i = j
        else:
            j = i
            while j < n and s[j] not in ",():;":
                j += 1
            cur.name = s[i:j].strip().strip("'")
            if spans is not None and cur.children:
                spans[id(cur)] = (i, j)
            i = j
    require(not stack, "unbalanced Newick")
    return root


def iter_nodes(root):
    out, st = [], [root]
    while st:
        x = st.pop(); out.append(x); st.extend(reversed(x.children))
    return out


def tips_in_order(root):
    return [x for x in iter_nodes(root) if not x.children]


def tip_sets(root):
    below = {}
    for x in reversed(iter_nodes(root)):
        below[id(x)] = frozenset([x.name]) if not x.children else frozenset().union(*[below[id(c)] for c in x.children])
    return below


def split_key(tips, all_tips, ref):
    """Canonical bipartition key: the side that does not contain the reference tip."""
    return frozenset(all_tips - tips) if ref in tips else frozenset(tips)


def support_audit(rooted, run1):
    """Compare each rooted internal-node label with the IQ-TREE run1 label of the same bipartition.
    Nodes are identified by (first_tip, last_tip) in Newick order, which is unique in a rooted tree."""
    br, b1 = tip_sets(rooted), tip_sets(run1)
    all_tips = br[id(rooted)]
    require(b1[id(run1)] == all_tips, "run1 and rooted tip sets differ")
    ref = min(all_tips)
    run1_lab = {}
    for x in iter_nodes(run1):
        if x.children and x.parent is not None:
            k = split_key(b1[id(x)], all_tips, ref)
            require(k not in run1_lab, "duplicate bipartition in run1")
            run1_lab[k] = x.name
    order = {t.name: i for i, t in enumerate(tips_in_order(rooted))}
    out = []
    for i, x in enumerate(n for n in iter_nodes(rooted) if n.children):
        t = br[id(x)]
        first, last = min(t, key=order.get), max(t, key=order.get)
        if x.parent is None:
            r1 = None
        else:
            k = split_key(t, all_tips, ref)
            require(k in run1_lab, "rooted bipartition absent from run1 (topology differs)")
            r1 = run1_lab[k]
        out.append({"preorder_index": i, "n_tips": len(t), "first_tip": first, "last_tip": last,
                    "is_root": x.parent is None, "rooted_label": x.name or None, "iqtree_run1_label": r1,
                    "agrees": (x.name or None) == r1})
    return out, run1_lab, ref, all_tips


DERIVED_NWK = "MR_RT_003.rooted.run1-support.DERIVED.nwk"
DERIVED_README = "MR_RT_003.rooted.run1-support.DERIVED.README.txt"
REPRESENTATIVE_RULE = ("Up to 12 per group, deterministic: E1 records confidently assigned to the group "
                       "(reference tips first, then by MRDB accession), then reference tips of the group by tip_role "
                       "(anchor_characterized, seed, cl0.6_representative) and accession. Display aid only.")
ROOT_SPLIT_RULE = ("The two root branches (outgroup | ingroup) are one bipartition of the unrooted IQ-TREE run1 tree "
                   "and carry one support value. It is displayed once, on the outgroup branch; the root node "
                   "itself has no support.")
SUPPORT_DISPLAY_RULE = ("Support is the SH-aLRT/UFBoot label of the same bipartition in IQ-TREE run1.treefile (the "
                        "release tree before rerooting). Topology and branch lengths are those of the frozen rooted "
                        "file. Rooted-file labels are kept as audit fields only (17 of 470 are attached to a "
                        "different bipartition because rerooting moved node-attached labels).")
PLACEMENT_RULE = ("EPA-ng placements are not tips of the reference tree. A placement is shown only as its best "
                  "reference branch (edge_map: DB tree_edge.edge_id = jplace edge_num on unrooted run1 -> rooted "
                  "node whose parent branch has the same bipartition); the position along the branch is not stored "
                  "in v1.6.0 and is never drawn. Statuses are shown exactly as stored (clade_call_qc, subclade_call).")


def derived_newick(text, root, spans, new_label):
    """`text` with every internal-node label replaced by new_label[id(node)] ('' = no label). Branch-length
    strings, tip names and topology are copied byte-for-byte from `text`."""
    edits = sorted(((spans[id(x)], new_label.get(id(x)) or "") for x in iter_nodes(root) if x.children), reverse=True)
    require(len({sp for sp, _ in edits}) == len(edits), "overlapping label spans")
    out = text
    for (a, z), lab in edits:
        out = out[:a] + lab + out[z:]
    return out


def tree_preview_svg(root, tip_level1):
    """Deterministic phylogram preview (no labels). Edges whose descendant tips all share one level-1 clade
    are coloured by that clade; everything else (backbone, outgroup) is grey."""
    palette = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#F0E442", "#000000"]
    level1 = sorted({c for c in tip_level1.values() if c})
    color_of = {c: palette[k % len(palette)] for k, c in enumerate(level1)}
    W, H, M = 600.0, 600.0, 4.0
    tips = tips_in_order(root)
    y, depth, clade = {}, {}, {}
    for k, t in enumerate(tips):
        y[id(t)] = M + k * (H - 2 * M) / (len(tips) - 1)
    for x in iter_nodes(root):
        depth[id(x)] = (depth[id(x.parent)] if x.parent else 0.0) + (x.length or 0.0) * (x.parent is not None)
    for x in reversed(iter_nodes(root)):
        if x.children:
            y[id(x)] = (y[id(x.children[0])] + y[id(x.children[-1])]) / 2
            cs = {clade[id(c)] for c in x.children}
            clade[id(x)] = cs.pop() if len(cs) == 1 else None
        else:
            clade[id(x)] = tip_level1.get(x.name)
    sx = (W - 2 * M) / max(depth.values())
    paths = defaultdict(list)
    for x in iter_nodes(root):
        if x.parent is None:
            continue
        col = color_of.get(clade[id(x)], "#9A9A9A")
        x0, x1 = M + depth[id(x.parent)] * sx, M + depth[id(x)] * sx
        paths[col].append(f"M{x0:.2f} {y[id(x)]:.2f}H{x1:.2f}")
        if x.children:
            paths[col].append(f"M{x1:.2f} {y[id(x.children[0])]:.2f}V{y[id(x.children[-1])]:.2f}")
    if root.children:
        x1 = M
        paths["#9A9A9A"].append(f"M{x1:.2f} {y[id(root.children[0])]:.2f}V{y[id(root.children[-1])]:.2f}")
    body = "".join(f'<path stroke="{c}" d="{"".join(paths[c])}"/>' for c in sorted(paths))
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600" width="600" height="600" '
            'role="img" aria-label="MR_RT_003 reference tree preview">'
            '<title>MR_RT_003 reference tree (rooted on the heliorhodopsin outgroup)</title>'
            f'<g fill="none" stroke-width="0.8" stroke-linecap="square">{body}</g></svg>\n')


# ----------------------------------------------------------------------------------------------- inputs
def verify_inputs(repo, db, expected_sha):
    if not db.is_file():
        raise ExportError("BLOCKED_DATA_SOURCE", f"database not found: {db}")
    got = sha256_file(db)
    if got != expected_sha:
        raise ExportError("BLOCKED_DATA_SOURCE", f"database SHA-256 {got} != expected {expected_sha}")
    sums_path = repo / REFPKG / "SHA256SUMS"
    if not sums_path.is_file():
        raise ExportError("BLOCKED_DATA_SOURCE", f"missing {sums_path}")
    sums = {}
    for line in sums_path.read_text().splitlines():
        if line.strip():
            h, f = line.split(None, 1)
            sums[f.strip().lstrip("*").removeprefix("./")] = h
    refpkg = {}
    for rel in REFPKG_INPUTS:
        p = repo / REFPKG / rel
        if not p.is_file():
            raise ExportError("BLOCKED_DATA_SOURCE", f"missing refpkg input {p}")
        h = sha256_file(p)
        if sums.get(rel) != h:
            raise ExportError("BLOCKED_DATA_SOURCE", f"{rel} SHA-256 {h} does not match refpkg SHA256SUMS")
        refpkg[rel] = h
    if refpkg["tree/MR_RT_003.rooted.treefile"] != EXPECTED_TREE_SHA256:
        raise ExportError("BLOCKED_DATA_SOURCE", "rooted treefile SHA-256 differs from the pinned value")
    return got, refpkg


def resolve_predicted(repo, rel):
    hits = sorted((repo / "releases").glob(f"*/{rel}"))
    require(len(hits) == 1, f"predicted_structure.pdb_file {rel!r}: {len(hits)} matches under releases/*/",
            "STRUCTURE_SOURCE_ANOMALY")
    h = sha256_file(hits[0])
    require(rel in PREDICTED_SHA256 and h == PREDICTED_SHA256[rel],
            f"{hits[0]} SHA-256 {h} does not match the frozen value", "STRUCTURE_SOURCE_ANOMALY")
    return hits[0], h


def git_state(repo):
    try:
        commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True,
                                check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True,
                                    text=True, check=True).stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = "unknown", True
    return commit, dirty


# ----------------------------------------------------------------------------------------------- summary
def metric_defs():
    """(id, label, sql, denominator_id, engineered inclusion). SQL returns one integer."""
    C = "counts_eligible = 1"
    return [
        ("records_total", "Source records", "SELECT COUNT(*) FROM v_master", "all_records", "included"),
        ("records_counted", "Counted source records (engineered constructs excluded)",
         f"SELECT COUNT(*) FROM v_master WHERE {C}", "all_records", "excluded"),
        ("records_engineered", "Engineered constructs", "SELECT COUNT(*) FROM v_master WHERE is_engineered = 1",
         "all_records", "included"),
        ("mrdb_accessions", "MRDB accessions (unique sequences)", "SELECT COUNT(*) FROM mrdb_accession",
         "mrdb_accessions", "included"),
        ("mrdb_multi_source", "MRDB accessions with more than one source accession",
         "SELECT COUNT(*) FROM mrdb_accession WHERE n_source_records > 1", "mrdb_accessions", "included"),
        ("typeI_members", "Type-I members (all member statuses)",
         "SELECT COUNT(*) FROM v_master v JOIN status_definition s ON s.status = v.membership_status "
         "WHERE s.status_group = 'member'", "all_records", "included"),
        ("typeI_candidates", "Type-I candidates",
         "SELECT COUNT(*) FROM v_master v JOIN status_definition s ON s.status = v.membership_status "
         "WHERE s.status_group = 'candidate'", "all_records", "included"),
        ("e1_counted", "E1 (direct experimental) records, counted", f"SELECT COUNT(*) FROM v_master WHERE "
         f"evidence_level = 'E1' AND {C}", "counted_records", "excluded"),
        ("e1_total", "E1 records including engineered constructs",
         "SELECT COUNT(*) FROM v_master WHERE evidence_level = 'E1'", "all_records", "included"),
        ("e1_unique_sequences", "MRDB accessions with a counted E1 record",
         f"SELECT COUNT(DISTINCT mrdb_acc) FROM v_master WHERE evidence_level = 'E1' AND {C}",
         "mrdb_accessions", "excluded"),
        ("call_conflict", "Records with a function-call conflict flag",
         "SELECT COUNT(*) FROM v_master WHERE call_conflict = 1", "all_records", "included"),
        ("publications", "Publications", "SELECT COUNT(*) FROM publication", "publications", "included"),
        ("publication_links_active", "Active record-publication links",
         "SELECT COUNT(*) FROM assertion_publication WHERE is_active = 1", "active_links", "included"),
        ("publication_links_support", "Active links that count as supporting evidence",
         "SELECT COUNT(*) FROM assertion_publication WHERE is_active = 1 AND counts_as_support = 1",
         "active_links", "included"),
        ("records_with_publications", "Source records with at least one active publication link",
         "SELECT COUNT(DISTINCT source_acc) FROM assertion_publication WHERE is_active = 1", "all_records",
         "included"),
        ("pdb_links", "Record-PDB links", "SELECT COUNT(*) FROM protein_pdb", "pdb_links", "included"),
        ("pdb_entries", "Distinct PDB entries", "SELECT COUNT(DISTINCT pdb_id) FROM protein_pdb", "pdb_entries",
         "included"),
        ("records_with_pdb", "Source records with at least one PDB entry",
         "SELECT COUNT(DISTINCT source_acc) FROM protein_pdb", "all_records", "included"),
        ("mrdb_with_pdb", "MRDB accessions with at least one PDB entry (any source record)",
         "SELECT COUNT(DISTINCT a.mrdb_acc) FROM protein_pdb p JOIN accession_map a USING (source_acc)",
         "mrdb_accessions", "included"),
        ("pdb_entries_with_retinal", "PDB entries containing retinal (RET)",
         "SELECT COUNT(*) FROM pdb_structure WHERE has_retinal = 1 AND pdb_id IN (SELECT pdb_id FROM protein_pdb)",
         "pdb_entries", "included"),
        ("records_with_afdb", "Source records with an AlphaFold DB model",
         "SELECT COUNT(*) FROM afdb_model WHERE status = 'ok'", "all_records", "included"),
        ("predicted_models", "Other predicted models (ESMCFold2)", "SELECT COUNT(*) FROM predicted_structure",
         "all_records", "included"),
        ("tree_tips", "Reference tree tips (MR_RT_003)",
         "SELECT COUNT(*) FROM tree_node WHERE tree_id = 'MR_RT_003' AND kind = 'tip'", "tree_tips", "included"),
        ("level1_clades", "Level-1 clades",
         "SELECT COUNT(*) FROM clade WHERE level = 1 AND tree_id = 'MR_RT_003' AND parent_clade_id IS NULL",
         "clade_level1_rows", "included"),
        ("backbone_groups", "Backbone groups",
         "SELECT COUNT(*) FROM clade WHERE level = 1 AND tree_id = 'MR_RT_003' AND parent_clade_id = 'backbone'",
         "clade_level1_rows", "included"),
        ("subclades", "Level-2 subclades", "SELECT COUNT(*) FROM clade WHERE level = 2 AND tree_id = 'MR_RT_003'",
         None, "included"),
        ("placements_current", "Current placements on MR_RT_003",
         "SELECT COUNT(*) FROM placement WHERE is_current = 1 AND tree_id = 'MR_RT_003'", "all_records", "included"),
        ("watchlist", "Novel-family watchlist entries (not part of the corpus)",
         "SELECT COUNT(*) FROM novel_family_candidate", "watchlist", "included"),
    ]


def distribution_defs():
    """(id, label, sql returning (key, count) rows, denominator_id). Totals must equal the denominator."""
    C = "counts_eligible = 1"
    return [
        ("membership_status", "Membership status (all records)",
         "SELECT membership_status, COUNT(*) FROM v_master GROUP BY 1 ORDER BY 1", "all_records"),
        ("membership_group", "Membership group (all records)",
         "SELECT s.status_group, COUNT(*) FROM v_master v JOIN status_definition s ON s.status = v.membership_status "
         "GROUP BY 1 ORDER BY 1", "all_records"),
        ("evidence_level_counted", "Evidence type (counted records)",
         f"SELECT evidence_level, COUNT(*) FROM v_master WHERE {C} GROUP BY 1 ORDER BY 1", "counted_records"),
        ("evidence_level_all", "Evidence type (all records)",
         "SELECT evidence_level, COUNT(*) FROM v_master GROUP BY 1 ORDER BY 1", "all_records"),
        ("func_class_counted", "Function class (counted records)",
         f"SELECT func_class, COUNT(*) FROM v_master WHERE {C} GROUP BY 1 ORDER BY 1", "counted_records"),
        ("tax_domain_counted", "Taxonomic domain (counted records)",
         f"SELECT tax_domain, COUNT(*) FROM v_master WHERE {C} GROUP BY 1 ORDER BY 1", "counted_records"),
        ("structure_coverage", "Structure coverage (all records)",
         "SELECT CASE WHEN v.source_acc IN (SELECT source_acc FROM protein_pdb) THEN 'pdb' "
         "WHEN a.status = 'ok' THEN 'afdb_only' ELSE 'none' END, COUNT(*) "
         "FROM v_master v JOIN afdb_model a USING (source_acc) GROUP BY 1 ORDER BY 1", "all_records"),
        ("afdb_status", "AlphaFold DB status (all records)",
         "SELECT status, COUNT(*) FROM afdb_model GROUP BY 1 ORDER BY 1", "all_records"),
        ("pdb_method", "Experimental method (distinct PDB entries)",
         "SELECT method, COUNT(*) FROM pdb_structure WHERE pdb_id IN (SELECT pdb_id FROM protein_pdb) "
         "GROUP BY 1 ORDER BY 1", "pdb_entries"),
        ("link_role", "Publication link role (active links)",
         "SELECT link_role, COUNT(*) FROM assertion_publication WHERE is_active = 1 GROUP BY 1 ORDER BY 1",
         "active_links"),
        ("clade_state", "Phylogenetic placement state (all records)",
         f"SELECT clade_state, COUNT(*) FROM ({CLADE_STATE_SQL}) GROUP BY 1 ORDER BY 1", "all_records"),
        ("placement_clade_call", "Current placement call",
         "SELECT clade_call, COUNT(*) FROM placement WHERE is_current = 1 AND tree_id = 'MR_RT_003' "
         "GROUP BY 1 ORDER BY 1", "placements_current"),
        ("clade_consensus_status", "Function consensus status (level-1 clades and backbone groups)",
         "SELECT consensus_status, COUNT(*) FROM clade WHERE level = 1 AND tree_id = 'MR_RT_003' GROUP BY 1 ORDER BY 1",
         "clade_level1_rows"),
        ("tip_role", "Reference tree tip role", None, "tree_tips"),
        ("watchlist_family", "Watchlist family", "SELECT family, COUNT(*) FROM novel_family_candidate GROUP BY 1 "
         "ORDER BY 1", "watchlist"),
    ]


DENOMINATORS = {
    "all_records": ("All source records", "SELECT COUNT(*) FROM v_master"),
    "counted_records": ("Counted source records", "SELECT COUNT(*) FROM v_master WHERE counts_eligible = 1"),
    "mrdb_accessions": ("MRDB accessions", "SELECT COUNT(*) FROM mrdb_accession"),
    "tree_tips": ("Reference tree tips", "SELECT COUNT(*) FROM tree_node WHERE tree_id = 'MR_RT_003' AND kind = 'tip'"),
    "pdb_entries": ("Distinct PDB entries", "SELECT COUNT(DISTINCT pdb_id) FROM protein_pdb"),
    "pdb_links": ("Record-PDB links", "SELECT COUNT(*) FROM protein_pdb"),
    "publications": ("Publications", "SELECT COUNT(*) FROM publication"),
    "active_links": ("Active publication links", "SELECT COUNT(*) FROM assertion_publication WHERE is_active = 1"),
    "placements_current": ("Current placements",
                           "SELECT COUNT(*) FROM placement WHERE is_current = 1 AND tree_id = 'MR_RT_003'"),
    "clade_level1_rows": ("Level-1 clade rows (17 clades + 2 backbone groups)",
                          "SELECT COUNT(*) FROM clade WHERE level = 1 AND tree_id = 'MR_RT_003'"),
    "watchlist": ("Watchlist entries", "SELECT COUNT(*) FROM novel_family_candidate"),
}


def build_summary(con, tip_roles):
    one = lambda sql: con.execute(sql).fetchone()[0]
    den = {k: {"id": k, "label": lab, "value": one(sql), "sql": sql} for k, (lab, sql) in DENOMINATORS.items()}
    metrics = []
    for mid, label, sql, did, eng in metric_defs():
        metrics.append({"id": mid, "label": label, "value": one(sql), "sql": sql, "dataset_release": DATASET_RELEASE,
                        "denominator": None if did is None else {"id": did, "value": den[did]["value"]},
                        "inclusion": {"engineered": eng, "watchlist": "excluded" if mid != "watchlist" else "only"}})
    dists = []
    for did_, label, sql, denid in distribution_defs():
        if sql is None:
            items = [{"key": k, "value": v} for k, v in sorted(Counter(tip_roles.values()).items())]
            src = f"{REFPKG}/tips.tsv (tip_role column)"
        else:
            items = [{"key": k, "value": v} for k, v in con.execute(sql).fetchall()]
            src = None
        total = sum(i["value"] for i in items)
        require(total == den[denid]["value"], f"distribution {did_} sums to {total}, denominator {den[denid]['value']}")
        require(all(i["key"] != "UNMAPPED" for i in items), f"distribution {did_} has UNMAPPED keys")
        dists.append({"id": did_, "label": label, "sql": sql, "source_file": src, "items": items, "total": total,
                      "denominator": {"id": denid, "value": den[denid]["value"]}, "dataset_release": DATASET_RELEASE})
    return {"schema_version": SCHEMA_VERSION, "dataset_release": DATASET_RELEASE, "denominators": den,
            "metrics": metrics, "distributions": dists,
            "notes": ["E1-E5 are evidence types, not probabilities; membership status and evidence level are separate "
                      "axes.", "Counted records exclude the engineered constructs (counts_eligible = 0)."]}


# ----------------------------------------------------------------------------------------------- export
def rows(con, sql, *args):
    cur = con.execute(sql, args)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def export(repo, db, out, expected_sha=EXPECTED_DB_SHA256):
    repo, db, out = Path(repo).resolve(), Path(db).resolve(), Path(out).resolve()
    db_sha, refpkg_sha = verify_inputs(repo, db, expected_sha)
    commit, dirty = git_state(repo)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.execute("PRAGMA query_only = 1")
    files = {}  # relative path (to out) -> bytes

    def put(rel, data, n_records):
        require(rel not in files, f"duplicate output {rel}")
        files[rel] = (data.encode("utf-8") if isinstance(data, str) else data, n_records)

    R = f"v{DATASET_RELEASE}/"
    md = dict(con.execute("SELECT key, value FROM release_metadata WHERE release = ?", (DATASET_RELEASE,)).fetchall())
    require(md.get("version") == DATASET_RELEASE, "release_metadata version mismatch", "BLOCKED_DATA_SOURCE")

    # ---------------- tree
    tree_bytes = (repo / TREE_REL).read_bytes()
    tree_text = tree_bytes.decode("utf-8")
    label_spans = {}
    root = parse_newick(tree_text, label_spans)
    nodes = iter_nodes(root)
    tip_nodes = [x for x in nodes if not x.children]
    internal = [x for x in nodes if x.children]
    support = [x.name for x in internal if SUPPORT_RE.match(x.name)]
    other_labels = sorted({x.name for x in internal if x.name and not SUPPORT_RE.match(x.name)})
    require(not other_labels, f"non-support internal labels in Newick: {other_labels[:5]}")
    tip_names = [x.name for x in tip_nodes]
    require(len(set(tip_names)) == len(tip_names), "duplicate tip names")
    tips_tsv = [l.split("\t") for l in (repo / REFPKG / "tips.tsv").read_text().splitlines()[1:] if l.strip()]
    tip_roles = {t[0]: t[1] for t in tips_tsv}
    require(set(tip_roles) == set(tip_names), "tips.tsv and treefile tip sets differ")
    db_tips = {r[0] for r in con.execute("SELECT source_acc FROM tree_node WHERE tree_id = ? AND kind = 'tip'", (TREE_ID,))}
    require(db_tips == set(tip_names), "DB tree_node tips differ from treefile tips")
    db_internal = [r[0] for r in con.execute("SELECT label FROM tree_node WHERE tree_id = ? AND kind != 'tip'", (TREE_ID,))]
    db_support = sorted(l for l in db_internal if l and SUPPORT_RE.match(l))
    require(db_support == sorted(support), "DB tree_node support-label multiset differs from rooted file")
    run1_bytes = (repo / REFPKG / "tree/run1.treefile").read_bytes()
    run1_md5 = hashlib.md5(run1_bytes).hexdigest()
    audit, run1_lab, split_ref, all_tips = support_audit(root, parse_newick(run1_bytes.decode("utf-8")))
    n_disagree = sum(1 for a in audit if not a["is_root"] and not a["agrees"])
    ref_tree = rows(con, "SELECT * FROM reference_tree WHERE tree_id = ?", TREE_ID)[0]
    require(ref_tree["treefile_md5"] == run1_md5, "reference_tree.treefile_md5 is not the md5 of run1.treefile")
    clade_tip = rows(con, "SELECT source_acc, clade_id, subclade_id, tree_id FROM clade_tip ORDER BY source_acc")
    refpkg_ct = sorted(tuple(l.split("\t")) for l in
                       (repo / REFPKG / "clades/MR_CLD3_tips.tsv").read_text().splitlines()[1:] if l.strip())
    require(sorted((r["clade_id"], r["source_acc"], r["subclade_id"] or "") for r in clade_tip) ==
            [(a, s_, (c[0] if c else "")) for a, s_, *c in refpkg_ct], "clade_tip differs from refpkg MR_CLD3_tips.tsv")
    ct_by_tip = {r["source_acc"]: r for r in clade_tip}
    corpus_mrdb = dict(con.execute("SELECT source_acc, mrdb_acc FROM v_master").fetchall())
    tips_json, tip_level1 = [], {}
    for name in sorted(tip_names):
        ct = ct_by_tip.get(name)
        l1 = ct["clade_id"] if ct and LEVEL1_RE.match(ct["clade_id"]) else None
        bb = ct["subclade_id"] if ct and ct["clade_id"] == "backbone_unassigned" and ct["subclade_id"] in BACKBONE_GROUPS else None
        if ct:
            require(l1 or ct["clade_id"] == "backbone_unassigned", f"unexpected clade_tip.clade_id {ct['clade_id']}")
        else:
            require(tip_roles[name] == "outgroup_heliorhodopsin", f"tip {name} lacks clade_tip and is not outgroup")
        tip_level1[name] = l1
        tips_json.append({"tip": name, "tip_role": tip_roles[name], "in_corpus": name in corpus_mrdb,
                          "mrdb_acc": corpus_mrdb.get(name), "level1": l1,
                          "subclade": ct["subclade_id"] if ct and l1 else None, "backbone_group": bb,
                          "unclustered_backbone": bool(ct and not l1 and not bb)})
    tree_stats = {
        "tree_id": TREE_ID, "file": "phylogeny/MR_RT_003.rooted.treefile", "source_path": TREE_REL,
        "sha256": hashlib.sha256(tree_bytes).hexdigest(), "md5": hashlib.md5(tree_bytes).hexdigest(),
        "bytes": len(tree_bytes), "n_tips": len(tip_nodes), "n_internal_incl_root": len(internal),
        "n_support_labels": len(support), "n_unlabelled_internal": sum(1 for x in internal if not x.name),
        "unlabelled_internal": [{"is_root": x.parent is None, "n_tips": len(tip_sets(x)[id(x)])}
                                for x in internal if not x.name],
        "support_label_format": "SH-aLRT/UFBoot", "support_label_regex": SUPPORT_RE.pattern,
        "root_children": len(root.children), "rooting": ref_tree["note"],
        "db_tree_node_internal": len(db_internal), "db_tree_node_support_labels": len(db_support),
        "db_tree_node_topology": "unrooted run1.treefile",
        "db_treefile_md5": ref_tree["treefile_md5"], "db_treefile_md5_refers_to": "run1.treefile",
        "method": ref_tree["method"], "model": ref_tree["model"], "log_likelihood": ref_tree["log_likelihood"],
        "display_rule": "Only internal-node labels matching support_label_regex are shown as support; "
                        "parser-generated names (e.g. phylotree's 'root') are never shown as support.",
        "support_audit": {"file": "phylogeny/support_audit.json", "reference": f"{REFPKG}/tree/run1.treefile",
                          "n_nonroot_internal": len(audit) - 1, "n_agree": len(audit) - 1 - n_disagree,
                          "n_disagree": n_disagree,
                          "finding": "Labels in the rooted file differ from the IQ-TREE run1 label of the same "
                                     "bipartition on the branches between the original Newick top node and the "
                                     "outgroup root (rerooting moved node-attached labels). Frozen files unchanged; "
                                     "display choice is an owner decision."},
    }
    put(R + "phylogeny/MR_RT_003.rooted.treefile", tree_bytes, len(tip_nodes))
    put(R + "phylogeny/tips.json", dumps({"dataset_release": DATASET_RELEASE, "tree_id": TREE_ID, "tips": tips_json}),
        len(tips_json))
    put(R + "phylogeny/clade_tips.json", dumps({"dataset_release": DATASET_RELEASE, "tree_id": TREE_ID,
                                                "source": "clade_tip (DB relation, unchanged)", "rows": clade_tip}),
        len(clade_tip))
    put(R + "phylogeny/tree_stats.json", dumps(tree_stats), 1)
    put(R + "phylogeny/support_audit.json", dumps({
        "dataset_release": DATASET_RELEASE, "tree_id": TREE_ID, "rooted_file": TREE_REL,
        "reference_file": f"{REFPKG}/tree/run1.treefile", "node_key": "first_tip,last_tip (Newick order)",
        "n_disagree": n_disagree, "nodes": audit}), len(audit))
    put(R + "phylogeny/preview.svg", tree_preview_svg(root, tip_level1), len(tip_nodes))

    # ---------------- explorer structure (schema 1.2.0, PR-4)
    pre = {id(x): k for k, x in enumerate(nodes)}
    below = tip_sets(root)
    node_by_tipset = {below[id(x)]: x for x in nodes}
    require(len(node_by_tipset) == len(nodes), "duplicate tip sets in rooted tree")
    outgroup_tips = frozenset(t for t, r in tip_roles.items() if r == "outgroup_heliorhodopsin")
    og = [c for c in root.children if below[id(c)] == outgroup_tips]
    require(len(root.children) == 2 and len(og) == 1, "heliorhodopsin outgroup is not one root child")
    og = og[0]
    ing = next(c for c in root.children if c is not og)
    tn = dict(con.execute("SELECT node_id, source_acc FROM tree_node WHERE tree_id = ? AND kind = 'tip'", (TREE_ID,)))
    te = rows(con, "SELECT edge_id, parent_node, child_node, length FROM tree_edge WHERE tree_id = ? ORDER BY edge_id",
              TREE_ID)
    kids = defaultdict(list)
    for e in te:
        kids[e["parent_node"]].append(e["child_node"])
    db_top = set(kids) - {e["child_node"] for e in te}
    require(len(db_top) == 1, "DB tree_edge does not form one tree")
    order, st = [], [db_top.pop()]
    while st:
        x = st.pop(); order.append(x); st.extend(kids.get(x, []))
    db_below = {}
    for x in reversed(order):
        db_below[x] = frozenset([tn[x]]) if x in tn else frozenset().union(*(db_below[k] for k in kids[x]))
    rooted_by_split = defaultdict(list)
    for x in nodes:
        if x.parent is not None:
            rooted_by_split[split_key(below[id(x)], all_tips, split_ref)].append(x)
    edge_map, len_diff = {}, []
    for e in te:
        k = split_key(db_below[e["child_node"]], all_tips, split_ref)
        require(k in rooted_by_split, f"DB edge {e['edge_id']} is not a bipartition of the rooted tree")
        xs = rooted_by_split[k]
        edge_map[e["edge_id"]] = sorted(pre[id(x)] for x in xs)
        len_diff.append(abs(sum(x.length for x in xs) - e["length"]))
    shared_edges = [k for k, v in edge_map.items() if len(v) > 1]
    require(len(shared_edges) == 1 and edge_map[shared_edges[0]] == sorted([pre[id(og)], pre[id(ing)]]),
            "expected exactly one DB edge for the root split")
    require(sorted(i for v in edge_map.values() for i in v) == list(range(1, len(nodes))),
            "edge_map does not cover every rooted branch exactly once")
    plc_edges = {r[0] for r in con.execute("SELECT DISTINCT best_edge FROM placement WHERE tree_id = ? AND is_current = 1",
                                           (TREE_ID,))}
    require(plc_edges <= set(edge_map), "placement best_edge not in tree_edge")
    run1_sha = hashlib.sha256(run1_bytes).hexdigest()
    put(R + "phylogeny/run1.treefile", run1_bytes, len(tip_nodes))
    new_label, changed = {}, []
    for x, a in zip(internal, audit):
        lab = None if (x.parent is None or x is ing) else a["iqtree_run1_label"]
        new_label[id(x)] = lab
        if (x.name or None) != lab:
            changed.append({"preorder_index": a["preorder_index"], "n_tips": a["n_tips"], "first_tip": a["first_tip"],
                            "last_tip": a["last_tip"], "rooted_label": x.name or None, "derived_label": lab})
    derived = derived_newick(tree_text, root, label_spans, new_label)
    derived_bytes = derived.encode("utf-8")
    put(R + "phylogeny/" + DERIVED_NWK, derived_bytes, len(tip_nodes))
    readme = "\n".join([
        f"{DERIVED_NWK}",
        "=" * len(DERIVED_NWK),
        "DERIVED FILE - NOT A FROZEN RELEASE ARTEFACT. Generated by tools/export_web_data.py "
        f"(schema {SCHEMA_VERSION}) for MicroRhodoDB v{DATASET_RELEASE}.",
        "",
        "What it is: the frozen rooted MR_RT_003 tree with its internal-node labels replaced by the IQ-TREE run1",
        "SH-aLRT/UFBoot label of the same bipartition. Topology, tip names, tip order and every branch-length",
        "string are copied byte-for-byte from the frozen file; only internal labels differ.",
        "",
        "Why: rerooting run1 on the heliorhodopsin outgroup moved node-attached labels on the path between the",
        "original top node and the new root, so 17 of the 470 non-root internal nodes of the frozen rooted file",
        "carry the label of a neighbouring bipartition (WEB_DATA_CONTRACT.md, phylogeny/support_audit.json).",
        "",
        "Rules: the root has no label. The two root branches are one unrooted bipartition; its single run1 label",
        "is written on the outgroup child only (the ingroup child is unlabelled), so no support is counted twice.",
        "No inference was run; no clade, topology, branch length or support value was re-estimated.",
        "",
        "Authoritative frozen files (unchanged):",
        f"  {TREE_REL}  sha256 {tree_stats['sha256']}",
        f"  {REFPKG}/tree/run1.treefile  sha256 {run1_sha}",
        f"This derived file: sha256 {hashlib.sha256(derived_bytes).hexdigest()}",
        "",
        f"Internal labels that differ from the frozen rooted file ({len(changed)}), preorder index over internal nodes:",
        *[f"  node {c['preorder_index']:>3} ({c['n_tips']} tips, {c['first_tip']}..{c['last_tip']}): "
          f"{c['rooted_label'] or '(none)'} -> {c['derived_label'] or '(none)'}" for c in changed],
        "",
    ])
    put(R + "phylogeny/" + DERIVED_README, readme, len(changed))

    # ---------------- per-record tables
    V = rows(con, "SELECT * FROM v_master ORDER BY mrdb_acc, source_acc")
    accs = [v["source_acc"] for v in V]
    require(len(set(accs)) == len(accs), "duplicate source_acc in v_master")
    by = lambda sql: {r["source_acc"]: r for r in rows(con, sql)}
    prot = by("SELECT source_acc, sequence, sequence_sha256, reviewed, lineage, length FROM protein")
    memb = by("SELECT * FROM membership")
    fe = by("SELECT * FROM function_evidence")
    amap = by("SELECT * FROM accession_map")
    afdb = by("SELECT * FROM afdb_model")
    struct = by("SELECT * FROM structure")
    gtdb = by("SELECT * FROM gtdb_taxonomy")
    pocket = by("SELECT * FROM retinal_pocket_summary")
    nff = by("SELECT * FROM novel_family_flag")
    rc = by("SELECT * FROM record_clade")
    plc = by(f"SELECT * FROM placement WHERE is_current = 1 AND tree_id = '{TREE_ID}'")
    cstate = dict(con.execute(CLADE_STATE_SQL).fetchall())
    require(set(cstate.values()) <= set(CLADE_STATES), "UNMAPPED clade_state")
    status_group = dict(con.execute("SELECT status, status_group FROM status_definition").fetchall())
    mrdb = {r["mrdb_acc"]: r for r in rows(con, "SELECT * FROM mrdb_accession ORDER BY mrdb_acc")}
    flags = defaultdict(list)
    for a, f in con.execute("SELECT source_acc, flag FROM protein_architecture_flag ORDER BY source_acc, flag"):
        flags[a].append(f)
    for name, tab in [("protein", prot), ("membership", memb), ("function_evidence", fe), ("accession_map", amap),
                      ("afdb_model", afdb), ("retinal_pocket_summary", pocket), ("novel_family_flag", nff)]:
        require(set(tab) == set(accs), f"{name} source_acc set differs from v_master")
    # PDB
    pdbmeta = {r["pdb_id"]: r for r in rows(con, "SELECT * FROM pdb_structure ORDER BY pdb_id")}
    links = rows(con, "SELECT source_acc, pdb_id FROM protein_pdb ORDER BY source_acc, pdb_id")
    require(len({(l["source_acc"], l["pdb_id"]) for l in links}) == len(links), "duplicate protein_pdb rows")
    pdb_by_acc, accs_by_pdb = defaultdict(list), defaultdict(list)
    for l in links:
        require(l["pdb_id"] in pdbmeta, f"protein_pdb {l['pdb_id']} has no pdb_structure row", "STRUCTURE_SOURCE_ANOMALY")
        require(re.fullmatch(r"[0-9A-Z]{4}", l["pdb_id"]) is not None, f"bad PDB ID {l['pdb_id']}")
        require(l["source_acc"] in amap, f"protein_pdb accession {l['source_acc']} not in corpus")
        pdb_by_acc[l["source_acc"]].append(l["pdb_id"]); accs_by_pdb[l["pdb_id"]].append(l["source_acc"])

    def pdb_meta(pid):
        m = pdbmeta[pid]
        res = m["resolution"]
        if res is None:
            res = "not_applicable" if m["method"] == "SOLUTION NMR" else None
        lig = ne(m["ligands"], "pdb_structure", "ligands")
        return {"pdb_id": pid, "method": m["method"], "resolution_A": res, "title": m["title"],
                "ligands": [] if lig is None else lig.split(";"), "has_retinal": b(m["has_retinal"]),
                "year": as_int(m["year"])}

    for acc, s in struct.items():
        linked = set(pdb_by_acc.get(acc, []))
        for k in ("rep_pdb_id", "highest_res_pdb_id"):
            require(s[k] is None or s[k] in linked, f"structure.{k}={s[k]} not linked for {acc}", "STRUCTURE_SOURCE_ANOMALY")
        require((s["n_pdb_structures"] or 0) == len(linked), f"structure.n_pdb_structures mismatch for {acc}",
                "STRUCTURE_SOURCE_ANOMALY")
    # predicted
    predicted = defaultdict(list)
    for p in rows(con, "SELECT * FROM predicted_structure ORDER BY source_acc"):
        src, h = resolve_predicted(repo, p["pdb_file"])
        data = src.read_bytes()
        rel = f"structures/predicted/{src.name}"
        put(R + rel, data, 1)
        predicted[p["source_acc"]].append({
            "method": p["method"], "mean_plddt": p["mean_plddt"], "file": rel,
            "source_path": str(src.relative_to(repo)), "db_pdb_file": p["pdb_file"], "sha256": h,
            "bytes": len(data), "bfactor_scale": "fraction_0_1", "subfamily": p["subfamily"], "note": p["note"]})
    # publications
    pubs = {r["publication_id"]: r for r in rows(con, "SELECT * FROM publication ORDER BY publication_id")}
    alinks = rows(con, """SELECT a.*, p.year AS _year FROM assertion_publication a JOIN publication p USING (publication_id)
                          ORDER BY a.source_acc, a.counts_as_support DESC, p.year, a.publication_id, a.assertion_id""")
    pmid = lambda x: None if x is None else str(int(x))

    def publink(a):
        p = pubs[a["publication_id"]]
        return {"assertion_id": a["assertion_id"], "publication_id": a["publication_id"], "doi": p["doi"],
                "pmid": pmid(p["pmid"]), "title": p["title"], "journal": p["journal"], "year": p["year"],
                "link_role": a["link_role"], "counts_as_support": b(a["counts_as_support"]), "verdict": a["verdict"],
                "caveat": a["caveat"], "evidence_basis": a["evidence_basis"], "assertion": a["assertion"]}
    pub_by_acc = defaultdict(list)
    for a in alinks:
        if a["is_active"] == 1:
            pub_by_acc[a["source_acc"]].append(publink(a))

    def afdb_obj(a):
        return {"model_id": a["model_id"], "status": a["status"], "version": as_int(a["version"]),
                "global_plddt": a["global_plddt"], "seq_match": b(a["seq_match"]), "seq_start": as_int(a["seq_start"]),
                "seq_end": as_int(a["seq_end"]), "model_url": a["model_url"], "model_created": a["model_created"]}

    sources_by_mrdb = defaultdict(list)
    index_rows = []
    for v in V:
        acc = v["source_acc"]
        p, m, f, g, pk, nf, s = prot[acc], memb[acc], fe[acc], gtdb.get(acc), pocket[acc], nff[acc], struct.get(acc)
        r_c, pl = rc.get(acc), plc.get(acc)
        require(p["length"] == v["length"] and len(p["sequence"]) == v["length"], f"length mismatch for {acc}")
        exp = []
        for pid in pdb_by_acc.get(acc, []):
            d = pdb_meta(pid)
            d.update(is_rep=bool(s and s["rep_pdb_id"] == pid), is_highest_res=bool(s and s["highest_res_pdb_id"] == pid),
                     shared_with=sorted(x for x in accs_by_pdb[pid] if x != acc))
            exp.append(d)
        is_rep = acc == mrdb[v["mrdb_acc"]]["representative_source_acc"]
        cs = cstate[acc]
        rec = {
            "source_acc": acc, "source_database": amap[acc]["source_database"],
            "release_added": amap[acc]["release_added"], "is_current": b(amap[acc]["is_current"]),
            "is_mrdb_representative": is_rep, "reviewed": b(p["reviewed"]),
            "protein_name": v["protein_name"], "organism": v["organism"], "organism_id": v["organism_id"],
            "tax_domain": v["tax_domain"], "lineage": p["lineage"],
            "gtdb": {"taxonomy": v["gtdb_taxonomy"], "agreement": g and g["gtdb_agreement"],
                     "match_level": g and g["gtdb_match_level"], "release": g and g["gtdb_release"],
                     "n_genomes": g and g["gtdb_n_genomes"]},
            "length": v["length"], "sequence": p["sequence"], "sequence_sha256": p["sequence_sha256"],
            "exact_duplicate_of": v["exact_duplicate_of"],
            "membership": {"status": v["membership_status"], "group": status_group[v["membership_status"]],
                           "score": v["membership_score"], "status_reason": m["status_reason"],
                           "boundary_subtype": v["boundary_subtype"], "architecture_class": m["architecture_class"],
                           "arch_route": m["arch_route"], "covers_TM7": b(m["covers_TM7"]),
                           "nearest_fulllength_homolog": m["nearest_fulllength_homolog"],
                           "homolog_identity": m["homolog_identity"], "provisional_inference": m["provisional_inference"],
                           "curated_override": ({"rationale": m["status_reason"], "source": "membership.status_reason"}
                                                if v["membership_status"] == "typeI_member_curated" else None)},
            "function": {"func_class": v["func_class"], "func_class_v14": v["func_class_v14"],
                         "evidence_level": v["evidence_level"], "function_basis": v["function_basis"],
                         "exp_class": f["exp_class"], "e1_representative": v["e1_representative"],
                         "e2_ref": f["e2_ref"], "e2_identity": f["e2_identity"], "override_rule": f["override_rule"],
                         "clade_function": f["clade_function"], "call_conflict": b(v["call_conflict"]),
                         "call_conflict_exact": b(f["call_conflict_exact"]),
                         "call_conflict_detail": v["call_conflict_detail"], "v160_change": f["v160_change"]},
            "engineering": {"is_engineered": b(v["is_engineered"]), "wild_type_acc": v["wild_type_acc"],
                            "counts_eligible": b(v["counts_eligible"])},
            "motifs": {"helixC_motif": v["helixC_motif"], "motif_class": v["motif_class"],
                       "retinal_site_residue": v["retinal_site_residue"], "pocket_string_br": pk["pocket_string_br"],
                       "n_pocket_observed": pk["n_pocket_observed"], "pocket_mean_plddt": pk["pocket_mean_plddt"],
                       "pocket_min_plddt": pk["pocket_min_plddt"]},
            "novel_family_flag": {"hit": nf["novel_family_hit"], "family_evalue": nf["family_evalue"],
                                  "family_bits": nf["family_bits"], "pf01036_bits": nf["pf01036_bits"]},
            "architecture": {"has_structure_row": s is not None, "arch_primary": s and s["arch_primary"],
                             "fusion_type": s and s["fusion_type"],
                             "fusion_partner_domains": s and ne(s["fusion_partner_domains"], "structure",
                                                                "fusion_partner_domains"),
                             "flags": flags.get(acc, [])},
            "phylogeny": {"clade_state": cs, "clade_id": ne(v["clade_id"], "v_master", "clade_id"),
                          "subclade_id": ne(v["subclade_id"], "v_master", "subclade_id"),
                          "clade_name": v["clade_name"], "tentative_clade_id": v["tentative_clade_id"],
                          "tentative_clade_name": v["tentative_clade_name"], "clade_source": v["clade_source"],
                          "clade_lwr": v["clade_lwr"], "placement_call": v["placement_call"],
                          "clade_function_source": r_c and r_c["clade_function_source"],
                          "is_reference_tip": acc in tip_roles, "tip_role": tip_roles.get(acc),
                          "placement": None if pl is None else {
                              k: pl[k] for k in ("tree_id", "model_tag", "best_edge", "best_lwr", "best_pendant",
                                                 "clade_id", "clade_lwr", "subclade_id", "subclade_lwr", "n_credible95",
                                                 "lwr_weighted_pendant", "clade_call", "subclade_call", "placement_qc",
                                                 "clade_call_qc", "track")}},
            "structures": {"experimental": exp, "afdb": afdb_obj(afdb[acc]), "predicted": predicted.get(acc, [])},
            "publications": pub_by_acc.get(acc, []),
        }
        require((cs == "confident") == bool(rec["phylogeny"]["clade_id"]), f"clade_state/clade_id mismatch {acc}")
        sources_by_mrdb[v["mrdb_acc"]].append(rec)
        index_rows.append([v["mrdb_acc"], acc, is_rep, v["protein_name"], v["organism"], v["tax_domain"], v["length"],
                           v["membership_status"], v["membership_score"], v["func_class"], v["evidence_level"],
                           b(v["call_conflict"]), b(v["is_engineered"]), b(v["counts_eligible"]), cs,
                           rec["phylogeny"]["clade_id"], rec["phylogeny"]["subclade_id"], v["tentative_clade_id"],
                           len(exp), afdb[acc]["status"] == "ok", bool(predicted.get(acc)), v["helixC_motif"],
                           nf["novel_family_hit"], b(p["reviewed"]), sum(1 for x in rec["publications"]
                                                                          if x["counts_as_support"]),
                           # schema 1.1.0 additions (INDEX_COLS_V11), same values as the record file
                           status_group[v["membership_status"]], v["retinal_site_residue"], v["function_basis"],
                           v["func_class_v14"], v["motif_class"], v["call_conflict_detail"], v["wild_type_acc"],
                           v["exact_duplicate_of"], v["e1_representative"], v["clade_name"],
                           v["tentative_clade_name"], v["gtdb_taxonomy"], v["afdb_model_id"],
                           v["afdb_global_plddt"], f["e2_ref"], f["e2_identity"], f["override_rule"],
                           pk["pocket_string_br"], m["status_reason"], p["lineage"], [x["pdb_id"] for x in exp]])
    require(set(predicted) <= set(accs), "predicted_structure accession not in corpus")
    index_cols = ["mrdb_acc", "source_acc", "is_mrdb_representative", "protein_name", "organism", "tax_domain",
                  "length", "membership_status", "membership_score", "func_class", "evidence_level", "call_conflict",
                  "is_engineered", "counts_eligible", "clade_state", "clade_id", "subclade_id", "tentative_clade_id",
                  "n_pdb", "has_afdb", "has_predicted", "helixC_motif", "novel_family_flag", "reviewed",
                  "n_support_links"] + INDEX_COLS_V11
    require(all(len(r) == len(index_cols) for r in index_rows), "records-index row width mismatch")
    put(R + "records-index.json", dumps({"dataset_release": DATASET_RELEASE, "columns": index_cols,
                                         "rows": index_rows}), len(index_rows))
    require(set(sources_by_mrdb) == set(mrdb), "MRDB accession sets differ")
    by_mrdb = {}
    for ma, srcs in sorted(sources_by_mrdb.items()):
        m = mrdb[ma]
        require(m["n_source_records"] == len(srcs), f"{ma} n_source_records mismatch")
        rep = m["representative_source_acc"]
        srcs.sort(key=lambda r: (r["source_acc"] != rep, r["source_acc"]))
        require(srcs[0]["source_acc"] == rep, f"{ma} representative not among sources")
        entry = {"mrdb_acc": ma, "dataset_release": DATASET_RELEASE, "representative_source_acc": rep,
                 "n_source_records": len(srcs), "sequence_sha256": m["sequence_sha256"],
                 "first_release": m["first_release"],
                 "pdb_union": sorted({x["pdb_id"] for r in srcs for x in r["structures"]["experimental"]}),
                 "sources": srcs}
        put(R + f"records/{ma}.json", dumps(entry), len(srcs))
        by_mrdb[ma] = {"representative_source_acc": rep, "sources": [r["source_acc"] for r in srcs],
                       "sequence_sha256": m["sequence_sha256"], "first_release": m["first_release"]}
    put(R + "accessions.json", dumps({"dataset_release": DATASET_RELEASE,
                                      "by_source": {a: r["mrdb_acc"] for a, r in sorted(amap.items())},
                                      "by_mrdb": by_mrdb}), len(amap))
    put(R + "sequences/corpus.fasta",
        "".join(f">{v['source_acc']} {v['mrdb_acc']}\n{prot[v['source_acc']]['sequence']}\n" for v in V), len(V))

    # ---------------- structures index
    pdb_index = {}
    for pid in sorted(accs_by_pdb):
        d = pdb_meta(pid)
        d.update(source_accs=sorted(accs_by_pdb[pid]),
                 mrdb_accs=sorted({amap[a]["mrdb_acc"] for a in accs_by_pdb[pid]}))
        pdb_index[pid] = d
    pred_index = [dict(source_acc=a, mrdb_acc=amap[a]["mrdb_acc"], **x) for a in sorted(predicted) for x in predicted[a]]
    put(R + "structures-index.json", dumps({"dataset_release": DATASET_RELEASE, "pdb": pdb_index,
                                            "predicted": pred_index,
                                            "afdb_url_template": "https://alphafold.ebi.ac.uk/files/AF-<acc>-F1-model_v6.pdb",
                                            "chain_mapping": "not provided in v2.0 (no PDB chain/residue to UniProt mapping is claimed)"}),
        len(pdb_index))

    # ---------------- evidence index
    recs = [r for srcs in sources_by_mrdb.values() for r in srcs]
    recs.sort(key=lambda r: r["source_acc"])
    e1 = [{"source_acc": r["source_acc"], "mrdb_acc": amap[r["source_acc"]]["mrdb_acc"],
           "func_class": r["function"]["func_class"], "function_basis": r["function"]["function_basis"],
           "counts_eligible": r["engineering"]["counts_eligible"],
           "n_support_links": sum(1 for x in r["publications"] if x["counts_as_support"])}
          for r in recs if r["function"]["evidence_level"] == "E1"]
    override = defaultdict(list)
    for r in recs:
        if r["function"]["override_rule"]:
            override[r["function"]["override_rule"]].append(r["source_acc"])
    put(R + "evidence-index.json", dumps({
        "dataset_release": DATASET_RELEASE, "e1": e1,
        "curated_overrides": [{"source_acc": r["source_acc"], "rationale": r["membership"]["status_reason"]}
                              for r in recs if r["membership"]["curated_override"]],
        "engineered": [{"source_acc": r["source_acc"], "wild_type_acc": r["engineering"]["wild_type_acc"]}
                       for r in recs if r["engineering"]["is_engineered"]],
        "call_conflict": [r["source_acc"] for r in recs if r["function"]["call_conflict"]],
        "override_rules": dict(sorted(override.items())),
        "function_conflict_rule": md.get("function_conflict_rule"), "engineered_policy": md.get("engineered_policy"),
    }), len(e1))

    # ---------------- clades
    cfc = {r["group_id"]: r for r in rows(con, "SELECT * FROM clade_function_consensus")}
    conf_n, tent_n = Counter(), Counter()
    for v in V:
        if ne(v["clade_id"], "v_master", "clade_id"):
            conf_n[v["clade_id"]] += 1
        elif v["tentative_clade_id"]:
            tent_n[v["tentative_clade_id"]] += 1
    tip_n = Counter(t["level1"] or t["backbone_group"] for t in tips_json)
    clade_tipset = defaultdict(set)
    for r in clade_tip:
        clade_tipset[r["clade_id"]].add(r["source_acc"])
        if r["subclade_id"]:
            clade_tipset[r["subclade_id"]].add(r["source_acc"])
    rooted_lab = {}
    br_ = tip_sets(root)
    for x in iter_nodes(root):
        if x.children and x.parent is not None:
            rooted_lab.setdefault(split_key(br_[id(x)], all_tips, split_ref), x.name)
    level1, sub = [], []
    mrca_of = defaultdict(list)
    vm_by_acc = {v["source_acc"]: v for v in V}
    for c in rows(con, "SELECT * FROM clade WHERE tree_id = ? ORDER BY level, clade_id", TREE_ID):
        k = split_key(frozenset(clade_tipset[c["clade_id"]]), all_tips, split_ref)
        require(len(clade_tipset[c["clade_id"]]) == c["n_tips"] and k in run1_lab, f"clade {c['clade_id']} tip set "
                "is not a bipartition of the tree")
        db_lab = f"{c['sh_alrt']:g}/{c['ufboot']:g}"
        fmt = lambda l: None if not l else "/".join(f"{float(v):g}" for v in l.split("/"))
        f = cfc.get(c["clade_id"])
        require(f is not None and f["consensus_status"] == c["consensus_status"], f"consensus mismatch {c['clade_id']}")
        d = dict(c)
        r1_sh, r1_uf = (float(x) for x in run1_lab[k].split("/"))
        d["support_audit"] = {"db_label": db_lab, "rooted_file_label": rooted_lab.get(k) or None,
                              "iqtree_run1_label": run1_lab[k], "db_matches_iqtree_run1": fmt(run1_lab[k]) == db_lab,
                              "iqtree_run1_sh_alrt": r1_sh, "iqtree_run1_ufboot": r1_uf,
                              "iqtree_run1_meets_support_thresholds":
                                  r1_sh >= CLADE_RULE["level1"]["min_sh_alrt"] and
                                  r1_uf >= CLADE_RULE["level1"]["min_ufboot"]}
        d["function_consensus"] = {k: (ne(f[k], "clade_function_consensus", k) if k == "E1_classes" else f[k])
                                   for k in ("level", "n_records", "n_E1", "top_frac", "consensus_status",
                                             "clade_function", "E1_classes")}
        # schema 1.2.0 (PR-4): position in the frozen rooted tree (MRCA of the frozen tip set) and display aids
        mx = node_by_tipset.get(frozenset(clade_tipset[c["clade_id"]]))
        require(mx is not None, f"clade {c['clade_id']} tip set is not a clade of the rooted tree")
        d["mrca_node"] = pre[id(mx)]
        mrca_of[pre[id(mx)]].append((c["level"], c["clade_id"], c["parent_clade_id"]))
        is_bb = c["level"] == 1 and c["parent_clade_id"] == "backbone"
        pc = Counter()
        for pl in plc.values():
            if c["level"] == 1 and not is_bb and pl["clade_id"] == c["clade_id"]:
                pc[pl["clade_call_qc"]] += 1
            elif (c["level"] == 2 or is_bb) and pl["subclade_id"] == c["clade_id"]:
                pc[pl["subclade_call"]] += 1
        d["placement_counts"] = {
            "basis": ("current placements with placement.subclade_id = this group, by placement.subclade_call"
                      if c["level"] == 2 or is_bb else
                      "current placements with placement.clade_id = this clade, by placement.clade_call_qc"),
            "counts": dict(sorted(pc.items()))}
        d["n_reference_tips_in_corpus"] = sum(1 for t in clade_tipset[c["clade_id"]] if t in corpus_mrdb)
        # schema 1.3.0 (PR-4a): formal assignments (record_clade, via v_master) kept apart from EPA-ng placements.
        # Rule (pipeline/v150/record_clades.py): record clade/subclade = reference-tip membership, or a primary
        # placement with call 'assigned' AND placement_qc 'ok' (LWR-weighted pendant <= 1.0); a backbone subclade
        # call without a level-1 clade becomes the record's level-1 group (B01/B02).
        cid = c["clade_id"]
        sub_level = c["level"] == 2 or is_bb
        call_f = "subclade_call" if sub_level else "clade_call"
        formal = [v for v in V if (v["subclade_id"] if c["level"] == 2 else v["clade_id"]) == cid]
        f_tip = sum(1 for v in formal if v["clade_source"] == "reference_tip")
        f_plc = sum(1 for v in formal if v["clade_source"] == "placement")
        require(f_tip + f_plc == len(formal), f"{cid}: unknown clade_source")
        require(f_tip == d["n_reference_tips_in_corpus"], f"{cid}: formal tip count != reference tips in corpus")
        gpl = [pl for pl in plc.values() if pl["subclade_id" if sub_level else "clade_id"] == cid]
        by_qc = defaultdict(Counter)
        for pl in gpl:
            by_qc[pl[call_f]][pl["placement_qc"]] += 1
        asg = dict(by_qc.get("assigned", {}))
        require(f_plc == asg.get("ok", 0), f"{cid}: formal placements != {call_f}=assigned and placement_qc=ok")
        d["placement_counts"]["call_field"] = call_f
        d["placement_counts"]["by_call_and_qc"] = {k: dict(sorted(v.items())) for k, v in sorted(by_qc.items())}
        d["assignment_counts"] = {
            "basis": ("formal v1.6.0 record assignments (v_master." + ("subclade_id" if c["level"] == 2 else "clade_id")
                      + " = this group): reference tips in the corpus plus placements with " + call_f
                      + " = assigned and placement_qc = ok (pipeline/v150/record_clades.py)"),
            "reference_tips": f_tip, "placements": f_plc, "total": len(formal),
            "placements_assigned_call_failing_qc": asg.get("long_pendant", 0)}
        if is_bb:
            # Placements whose backbone subclade call is 'assigned' but fail pendant QC: preserved as placements only.
            d["placement_only_records"] = [
                {"source_acc": pl["source_acc"], "mrdb_acc": corpus_mrdb[pl["source_acc"]],
                 "subclade_call": pl["subclade_call"], "clade_call_qc": pl["clade_call_qc"],
                 "placement_qc": pl["placement_qc"], "lwr_weighted_pendant": pl["lwr_weighted_pendant"],
                 "best_lwr": pl["best_lwr"], "subclade_lwr": pl["subclade_lwr"], "clade_state": cstate.get(pl["source_acc"])}
                for pl in sorted(gpl, key=lambda x: x["source_acc"])
                if pl["subclade_call"] == "assigned" and pl["placement_qc"] != "ok"]
        else:
            d["placement_only_records"] = None
        if c["level"] == 1:
            e1 = sorted((v for v in V if v["clade_id"] == c["clade_id"] and v["evidence_level"] == "E1"),
                        key=lambda v: (v["source_acc"] not in tip_roles, v["mrdb_acc"], v["source_acc"]))
            d["e1_anchors"] = [{"source_acc": v["source_acc"], "mrdb_acc": v["mrdb_acc"], "func_class": v["func_class"],
                                "protein_name": v["protein_name"], "organism": v["organism"],
                                "counts_eligible": b(v["counts_eligible"]), "is_engineered": b(v["is_engineered"]),
                                "is_reference_tip": v["source_acc"] in tip_roles}
                               for v in e1]
            reps = [dict(a, reason="E1 record assigned to this group") for a in d["e1_anchors"]][:12]
            seen = {r["source_acc"] for r in reps}
            role_rank = {"anchor_characterized": 0, "seed": 1, "cl0.6_representative": 2}
            for t in sorted(clade_tipset[c["clade_id"]], key=lambda t: (role_rank.get(tip_roles[t], 3), t)):
                if len(reps) >= 12:
                    break
                if t in seen or t not in vm_by_acc:
                    continue
                v = vm_by_acc[t]
                reps.append({"source_acc": t, "mrdb_acc": v["mrdb_acc"], "func_class": v["func_class"],
                             "protein_name": v["protein_name"], "organism": v["organism"],
                             "counts_eligible": b(v["counts_eligible"]), "is_engineered": b(v["is_engineered"]),
                             "is_reference_tip": True,
                             "reason": f"reference tip ({tip_roles[t]})"})
            d["representatives"] = reps
        if c["level"] == 1:
            kind = "backbone_group" if c["parent_clade_id"] == "backbone" else "clade"
            require(kind == "backbone_group" or LEVEL1_RE.match(c["clade_id"]), f"bad level-1 id {c['clade_id']}")
            reasons = []
            if c["min_cross_replicate_jaccard"] is not None and c["min_cross_replicate_jaccard"] < 0.8:
                reasons.append("min_cross_replicate_jaccard < 0.8")
            if c["consensus_status"] == "mixed":
                reasons.append("consensus_status = mixed")
            d.update(kind=kind, n_tips_in_tree=tip_n.get(c["clade_id"], 0),
                     n_records_confident=conf_n.get(c["clade_id"], 0), n_records_tentative=tent_n.get(c["clade_id"], 0),
                     robustness_caveat=bool(reasons), robustness_caveat_reasons=reasons)
            require(d["n_tips_in_tree"] == c["n_tips"], f"{c['clade_id']} n_tips {c['n_tips']} != tree {d['n_tips_in_tree']}")
            level1.append(d)
        else:
            sub.append(d)
    put(R + "clades.json", dumps({"dataset_release": DATASET_RELEASE, "tree_id": TREE_ID, "scheme": "MR_CLD3",
                                  "display": "17 level-1 clades + 2 backbone groups",
                                  "robustness_caveat_rule": "display rule only: min_cross_replicate_jaccard < 0.8 or "
                                                            "consensus_status = mixed; not a reclassification",
                                  "clade_rule": CLADE_RULE,
                                  "support_display": "Display iqtree_run1_* (IQ-TREE run1 label of the same bipartition). "
                                                     "sh_alrt/ufboot are the frozen v1.6.0 DB values; where they differ "
                                                     "from run1 (db_matches_iqtree_run1 = false) the assignment is a "
                                                     "legacy v1.6.0 assignment and is not changed here.",
                                  "representative_rule": REPRESENTATIVE_RULE,
                                  "level1": level1, "subclades": sub}), len(level1) + len(sub))

    # ---------------- explorer.json (schema 1.2.0, PR-4)
    annot_lines = (repo / REFPKG / "tips_annot.tsv").read_text().splitlines()
    ah = annot_lines[0].split("\t")
    annot = {}
    for l in annot_lines[1:]:
        if l.strip():
            r_ = dict(zip(ah, l.split("\t")))
            annot[r_["source_acc"]] = {k: (v or None) for k, v in r_.items()}
    require(set(annot) == set(tip_names), "tips_annot.tsv and treefile tip sets differ")
    require(all(annot[t]["tip_role"] == tip_roles[t] for t in tip_names), "tips_annot.tsv tip_role differs from tips.tsv")
    tj_by = {t["tip"]: t for t in tips_json}
    ex_tips = {}
    for t in tip_nodes:
        a, v, tj = annot[t.name], vm_by_acc.get(t.name), tj_by[t.name]
        ex_tips[t.name] = {
            "pre": pre[id(t)], "length": t.length, "mrdb_acc": tj["mrdb_acc"], "in_corpus": tj["in_corpus"],
            "tip_role": tj["tip_role"], "level1": tj["level1"], "subclade": tj["subclade"],
            "backbone_group": tj["backbone_group"], "unclustered_backbone": tj["unclustered_backbone"],
            "organism": v["organism"] if v else a["organism"],
            "protein_name": v["protein_name"] if v else a["protein_name"],
            "tax_domain": v["tax_domain"] if v else a["tax_domain"], "phylum": a["phylum"],
            "helixC_motif": v["helixC_motif"] if v else a["helixC_motif"],
            "func_class": v["func_class"] if v else None, "evidence_level": v["evidence_level"] if v else None,
            "clade_state": cstate.get(t.name), "func_class_v14": a["func_class_v14"],
            "subfamily_v14": a["subfamily_v14"],
            "annotation_source": "v1.6.0 v_master (phylum, *_v14: refpkg tips_annot.tsv)" if v else
                                 "refpkg tips_annot.tsv only (tip not in the v1.6.0 corpus)"}
    ex_nodes = []
    for x, a in zip(internal, audit):
        lab = a["iqtree_run1_label"]
        sh, uf = (float(z) for z in lab.split("/")) if lab else (None, None)
        groups = sorted(mrca_of.get(pre[id(x)], []))
        ex_nodes.append({
            "pre": pre[id(x)], "internal_index": a["preorder_index"],
            "parent": None if x.parent is None else pre[id(x.parent)], "length": x.length,
            "n_tips": a["n_tips"], "first_tip": a["first_tip"], "last_tip": a["last_tip"], "is_root": a["is_root"],
            "rooted_label": a["rooted_label"], "run1_label": lab, "sh_alrt": sh, "ufboot": uf,
            "label_agrees": a["agrees"], "root_split_shared": x.parent is root,
            "support_displayed": x.parent is not None and x is not ing,
            "is_outgroup_root_child": x is og,
            "clade_mrca": [g[1] for g in groups if g[0] == 1], "subclade_mrca": [g[1] for g in groups if g[0] == 2]})
    plc_status = Counter(p_["clade_call_qc"] for p_ in plc.values())
    put(R + "phylogeny/explorer.json", dumps({
        "dataset_release": DATASET_RELEASE, "tree_id": TREE_ID,
        "node_order": "rooted Newick preorder over all nodes (tips and internal); pre = position (root = 0)",
        "n_nodes": len(nodes), "n_tips": len(tip_nodes), "n_internal_incl_root": len(internal),
        "meta": {
            "tree_id": TREE_ID, "status": ref_tree["status"], "method": ref_tree["method"], "model": ref_tree["model"],
            "log_likelihood_run1": ref_tree["log_likelihood"], "release_run": "run1",
            "rooting": "heliorhodopsin outgroup (15 tips); frozen rooted file = run1 rerooted on the outgroup",
            "reference_tree_note": ref_tree["note"],
            "tip_roles": dict(sorted(Counter(tip_roles.values()).items())),
            "frozen_treefile": {"path": TREE_REL, "web_file": "phylogeny/MR_RT_003.rooted.treefile",
                                "sha256": tree_stats["sha256"]},
            "support_source": {"path": f"{REFPKG}/tree/run1.treefile", "web_file": "phylogeny/run1.treefile",
                               "sha256": run1_sha, "md5": run1_md5},
            "derived_newick": {"web_file": "phylogeny/" + DERIVED_NWK, "readme": "phylogeny/" + DERIVED_README,
                               "sha256": hashlib.sha256(derived_bytes).hexdigest(), "n_labels_changed": len(changed)},
            "support_display_rule": SUPPORT_DISPLAY_RULE, "root_split_rule": ROOT_SPLIT_RULE,
            "placement_rule": PLACEMENT_RULE, "clade_rule": CLADE_RULE,
            "n_label_disagreements": n_disagree,
            "db_edge_length_max_abs_diff": round(max(len_diff), 10),
            "db_edge_length_note": "DB tree_edge.length differs from the frozen rooted/run1 branch lengths by up to "
                                   "this value (not used for display; recorded for scientific revision).",
            "placement_status_counts": dict(sorted(plc_status.items())),
        },
        "root_split": {"edge_id": shared_edges[0], "nodes": edge_map[shared_edges[0]],
                       "displayed_on": pre[id(og)], "run1_label": audit[internal.index(og)]["iqtree_run1_label"]},
        "nodes": ex_nodes, "tips": dict(sorted(ex_tips.items())), "edge_map": edge_map}), len(nodes))
    rob = rows(con, "SELECT * FROM clade_robustness ORDER BY tree, rooting, min_size, max_size, ufb, alrt")
    put(R + "phylogeny/robustness.json", dumps({
        "dataset_release": DATASET_RELEASE, "tree_id": TREE_ID, "grid": rob,
        "per_clade": [{k: c[k] for k in ("clade_id", "kind", "jaccard_run2", "jaccard_run3", "jaccard_midpoint_rooting",
                                         "min_cross_replicate_jaccard")} for c in level1]}), len(rob))

    # ---------------- publications, watchlist
    put(R + "publications.json", dumps({
        "dataset_release": DATASET_RELEASE,
        "publications": [{"publication_id": p["publication_id"], "doi": p["doi"], "doi_corrected": p["doi_corrected"],
                          "pmid": pmid(p["pmid"]), "title": p["title"], "journal": p["journal"], "year": p["year"],
                          "verdict_summary": p["verdict_summary"]} for p in pubs.values()],
        "links": [dict(publink(a), source_acc=a["source_acc"], mrdb_acc=amap[a["source_acc"]]["mrdb_acc"])
                  for a in alinks if a["is_active"] == 1],
        "inactive_links": [dict(publink(a), source_acc=a["source_acc"], is_active=False,
                                display="audit only; never shown as support") for a in alinks if a["is_active"] != 1],
    }), len(pubs))
    wl = rows(con, "SELECT * FROM novel_family_candidate ORDER BY family, source_db, query_accession, resolved_accession, identifier")
    wl_ids = {w[k] for w in wl for k in ("query_accession", "resolved_accession") if w[k]}
    require(not (wl_ids & set(accs)), "watchlist accession found in corpus")
    put(R + "watchlist.json", dumps({
        "dataset_release": DATASET_RELEASE, "candidates": wl,
        "funnel": rows(con, "SELECT * FROM novel_family_funnel ORDER BY family"),
        "caveat": md.get("foldseek_watchlist"),
        "isolation": "Watchlist entries are not corpus records: no membership, evidence or function is assigned."}),
        len(wl))

    # ---------------- vocabulary (schema 1.1.0, PR-2): DB definitions for display labels and legends
    ev_def = con.execute("SELECT definition FROM data_dictionary WHERE object_name = 'function_evidence' "
                         "AND column_name = 'evidence_level'").fetchone()
    require(ev_def is not None, "data_dictionary lacks function_evidence.evidence_level")
    ev = EVIDENCE_LEVEL_RE.findall(ev_def[0].split(":", 1)[1].strip())
    require([e for e, _ in ev] == ["E1", "E2", "E3", "E4", "E5"], "cannot parse E1-E5 definitions")
    put(R + "vocabulary.json", dumps({
        "dataset_release": DATASET_RELEASE,
        "membership_status": [{"status": r["status"], "group": r["status_group"], "is_member": b(r["is_member"]),
                               "is_candidate": b(r["is_candidate"]), "label_v14": r["status_label_v14"],
                               "definition": r["definition"]}
                              for r in rows(con, "SELECT * FROM status_definition ORDER BY rowid")],
        "func_class": [{"func_class": r["func_class"], "definition": r["definition"]}
                       for r in rows(con, "SELECT * FROM func_class_definition ORDER BY rowid")],
        "evidence_level": [{"level": e, "definition": d.strip()} for e, d in ev],
        "evidence_level_source": {"table": "data_dictionary", "object": "function_evidence.evidence_level",
                                  "text": ev_def[0]},
        "evidence_note": "E1-E5 are evidence types, not probabilities; membership status and evidence level are "
                         "separate axes.",
        "clade_state": [{"state": k, "definition": CLADE_STATE_DEFINITIONS[k]} for k in CLADE_STATES],
        "sources": {"membership_status": "status_definition (n_records_v150 omitted: v1.5.0 counts)",
                    "func_class": "func_class_definition (counts omitted; see summary.json)",
                    "clade_state": "exporter CLADE_STATE_SQL rules (WEB_DATA_CONTRACT.md section 7.3)"},
    }), 9 + 11 + 5)

    # ---------------- summary + manifest + current
    summary = build_summary(con, tip_roles)
    put(R + "summary.json", dumps(summary), len(summary["metrics"]))
    mv = {m["id"]: m["value"] for m in summary["metrics"]}
    manifest = {
        "schema_version": SCHEMA_VERSION, "dataset_release": DATASET_RELEASE, "website_version": WEBSITE_VERSION,
        "schema_revision": md.get("schema_revision"), "release_date": md.get("release_date"), "license": md.get("license"),
        "source_db": {"file": db.name, "sha256": db_sha, "opened_read_only": True},
        "refpkg": {"id": TREE_ID, "rooted_treefile_sha256": tree_stats["sha256"], "rooted_treefile_md5": tree_stats["md5"],
                   "db_treefile_md5": ref_tree["treefile_md5"], "db_treefile_md5_refers_to": "run1.treefile",
                   "inputs_sha256": dict(sorted(refpkg_sha.items()))},
        "predicted_structure_sources": {x["source_path"]: x["sha256"] for x in pred_index},
        "exporter": {"path": "tools/export_web_data.py", "git_commit": commit, "git_dirty": dirty,
                     "python": platform.python_version()},
        "counts": {"records": mv["records_total"], "counted": mv["records_counted"], "mrdb_accessions": mv["mrdb_accessions"],
                   "tree_tips": mv["tree_tips"], "level1_clades": mv["level1_clades"], "backbone_groups": mv["backbone_groups"],
                   "pdb_links": mv["pdb_links"], "pdb_entries": mv["pdb_entries"], "publications": mv["publications"],
                   "active_links": mv["publication_links_active"], "watchlist": mv["watchlist"]},
        "timestamps": "none (deterministic export; see WEB_DATA_CONTRACT.md principle 4)",
    }
    put(R + "manifest.json", dumps(manifest), 1)
    put("current.json", dumps({"dataset_release": DATASET_RELEASE, "path": f"data/v{DATASET_RELEASE}/",
                               "schema_version": SCHEMA_VERSION}), 1)
    con.close()
    require(sha256_file(db) == db_sha, "database changed during export", "BLOCKED_DATA_SOURCE")
    em = {"schema_version": SCHEMA_VERSION, "dataset_release": DATASET_RELEASE, "source_db_sha256": db_sha,
          "exporter_git_commit": commit, "exporter_git_dirty": dirty,
          "files": [{"path": k, "sha256": hashlib.sha256(d).hexdigest(), "bytes": len(d), "records": n}
                    for k, (d, n) in sorted(files.items())]}
    em["n_files"], em["total_bytes"] = len(em["files"]), sum(f["bytes"] for f in em["files"])
    put(R + "export_manifest.json", dumps(em), len(em["files"]))

    # ---------------- write atomically
    out.mkdir(parents=True, exist_ok=True)
    stage = out / f".staging-v{DATASET_RELEASE}"
    if stage.exists():
        shutil.rmtree(stage)
    for rel, (data, _) in files.items():
        p = stage / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    target = out / f"v{DATASET_RELEASE}"
    if target.exists():
        require((target / "export_manifest.json").is_file() or not any(target.iterdir()),
                f"refusing to replace {target}: not a previous export")
        shutil.rmtree(target)
    (stage / f"v{DATASET_RELEASE}").rename(target)
    os.replace(stage / "current.json", out / "current.json")
    shutil.rmtree(stage)
    return em


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--db", default=None, help=f"default: <repo>/{DB_REL}")
    ap.add_argument("--out", default=None, help="default: <repo>/web/public/data")
    ap.add_argument("--expected-sha256", default=EXPECTED_DB_SHA256)
    a = ap.parse_args(argv)
    repo = Path(a.repo)
    try:
        em = export(repo, Path(a.db) if a.db else repo / DB_REL, Path(a.out) if a.out else repo / "web/public/data",
                    a.expected_sha256)
    except ExportError as e:
        print(str(e), file=sys.stderr)
        return ExportError.CODES[e.code]
    print(f"exported {em['n_files']} files, {em['total_bytes']:,} bytes; export_manifest sha256 "
          f"{hashlib.sha256(dumps(em).encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
