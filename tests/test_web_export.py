"""PR-1 gate G1: deterministic SQLite -> static web data export (tools/export_web_data.py).

Run from the repository root:
    pytest -q tests/test_web_export.py
Environment:
    MRDB_DB    database under test (default releases/v1.6.1/db/microrhododb_v1.6.1.sqlite)
    MRDB_REPO  repository root (default '.')

The exporter is run twice into fresh temporary directories through its CLI. Every expected value below is
recomputed from SQLite / refpkg with code that is independent of the exporter (pandas or plain SQL written
here), except where a test explicitly compares against a frozen baseline number from WEB_BASELINE_AUDIT.md
section 1.3. The legacy site/data.js is read only as a regression oracle (WEB_DATA_CONTRACT.md section 9.1).
Missing inputs fail; nothing is skipped.
"""
import collections
import fnmatch
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(os.environ.get("MRDB_REPO", ".")).resolve()
DB = Path(os.environ.get("MRDB_DB", REPO / "releases/v1.6.1/db/microrhododb_v1.6.1.sqlite"))
DB_SHA256 = "b8215cffa9d2fdab1e65b904f4bafbe9edf6578aed7b4fb028a890850e704c2d"
EXPORTER = REPO / "tools/export_web_data.py"
SCHEMA = REPO / "web/src/data/schemas/web-data.schema.json"
HABITAT_SCHEMA = REPO / "web/src/data/schemas/habitat.schema.json"
FROZEN = REPO / "docs/website/baseline/frozen_sha256_fab9182.txt"
TREE = REPO / "refpkg/MR_RT_003/tree/MR_RT_003.rooted.treefile"
RUN1 = REPO / "refpkg/MR_RT_003/tree/run1.treefile"
REL = "v1.6.1"
SUPPORT_RE = re.compile(r"^\d+(\.\d+)?/\d+(\.\d+)?$")
ISO_TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")

sys.path.insert(0, str(REPO / "tools"))
import export_web_data as ex  # noqa: E402  (constants only: field map and empty-string rules)


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def run_exporter(out, *extra):
    return subprocess.run([sys.executable, str(EXPORTER), "--repo", str(REPO), "--db", str(DB), "--out", str(out),
                           *extra], capture_output=True, text=True, cwd=str(REPO))


def all_files(root):
    return sorted(str(p.relative_to(root)) for p in Path(root).rglob("*") if p.is_file())


# ----------------------------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def db_sha_before():
    assert DB.is_file(), f"database missing: {DB}"
    return sha256(DB)


@pytest.fixture(scope="module")
def exports(tmp_path_factory, db_sha_before):
    a, b = tmp_path_factory.mktemp("export_a"), tmp_path_factory.mktemp("export_b") / "nested" / "out"
    for out in (a, b):
        r = run_exporter(out)
        assert r.returncode == 0, r.stderr
    return a, b


@pytest.fixture(scope="module")
def out(exports):
    return exports[0]


@pytest.fixture(scope="module")
def D(out):
    return out / REL


@pytest.fixture(scope="module")
def con():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    yield c
    c.close()


def sql_df(con, q):
    return pd.read_sql_query(q, con)


def load(D, rel):
    return json.loads((D / rel).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def records(D):
    """source_acc -> (entry, source record) over every records/MRDB*.json."""
    out = {}
    for p in sorted((D / "records").glob("MRDB*.json")):
        e = json.loads(p.read_text(encoding="utf-8"))
        assert p.stem == e["mrdb_acc"]
        for s in e["sources"]:
            assert s["source_acc"] not in out
            out[s["source_acc"]] = (e, s)
    return out


@pytest.fixture(scope="module")
def entries(D):
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((D / "records").glob("MRDB*.json"))}


def path_get(entry, src, path):
    if path.startswith("@entry."):
        return entry[path[len("@entry."):]]
    v = src
    for k in path.split("."):
        v = v[k]
    return v


# ----------------------------------------------------------------------------------------------- G1.8 determinism
def test_second_export_byte_identical(exports):
    a, b = exports
    fa, fb = all_files(a), all_files(b)
    assert fa == fb
    diff = [f for f in fa if (a / f).read_bytes() != (b / f).read_bytes()]
    assert diff == []


def test_no_wall_clock_or_absolute_paths(out, con):
    allowed = {r[0] for r in con.execute("SELECT model_created FROM afdb_model WHERE model_created IS NOT NULL")}
    tmp = str(out)
    for f in all_files(out):
        if not f.endswith((".json", ".svg", ".fasta", ".treefile", ".pdb")):
            continue
        t = (out / f).read_text(encoding="utf-8")
        assert tmp not in t and "/workspace" not in t and "/home/" not in t, f
        if f.endswith(".json"):
            for m in ISO_TS.finditer(t):
                stamp = t[m.start():t.index('"', m.start())]
                assert stamp in allowed, (f, stamp)
    for f in ("current.json", f"{REL}/manifest.json", f"{REL}/export_manifest.json", f"{REL}/summary.json"):
        keys = json.dumps(json.loads((out / f).read_text()))
        assert not re.search(r'"(built|generated|exported|created)_at(_utc)?"', keys), f


def test_export_manifest_covers_every_file(out, D):
    em = load(D, "export_manifest.json")
    listed = {e["path"]: e for e in em["files"]}
    actual = [f for f in all_files(out) if f != f"{REL}/export_manifest.json"]
    assert sorted(listed) == actual
    for f in actual:
        p = out / f
        assert listed[f]["bytes"] == p.stat().st_size and listed[f]["sha256"] == sha256(p), f
    assert em["n_files"] == len(actual)
    assert em["total_bytes"] == sum((out / f).stat().st_size for f in actual)
    assert em["source_db_sha256"] == DB_SHA256


def test_json_canonical_encoding(out):
    for f in all_files(out):
        if f.endswith(".json"):
            t = (out / f).read_text(encoding="utf-8")
            obj = json.loads(t)
            assert t == json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                   allow_nan=False) + "\n", f


def test_current_and_manifest(out, D, con):
    cur = json.loads((out / "current.json").read_text())
    assert cur == {"dataset_release": "1.6.1", "path": "data/v1.6.1/", "schema_version": cur["schema_version"]}
    m = load(D, "manifest.json")
    meta = dict(con.execute("SELECT key, value FROM release_metadata WHERE release = '1.6.1'"))
    assert m["dataset_release"] == "1.6.1"
    assert m["release_date"] == meta["release_date"]
    assert m["source_db"]["sha256"] == DB_SHA256 and m["source_db"]["opened_read_only"] is True
    assert m["refpkg"]["rooted_treefile_sha256"] == sha256(TREE)
    assert m["refpkg"]["inputs_sha256"]["tree/run1.treefile"] == sha256(RUN1)
    assert re.fullmatch(r"[0-9a-f]{40}", m["exporter"]["git_commit"])


# ----------------------------------------------------------------------------------------------- G1.1 / G1.2 accessions
def test_source_set_and_accessions(D, con, records, entries):
    vm = sql_df(con, "SELECT source_acc, mrdb_acc, counts_eligible FROM v_master")
    assert len(vm) == 5466 and vm.source_acc.is_unique
    assert set(records) == set(vm.source_acc)
    assert len(entries) == vm.mrdb_acc.nunique() == 5299
    assert int(vm.counts_eligible.sum()) == 5460
    for acc, mrdb in zip(vm.source_acc, vm.mrdb_acc):
        assert records[acc][0]["mrdb_acc"] == mrdb

    acc = load(D, "accessions.json")
    am = sql_df(con, "SELECT * FROM accession_map")
    assert acc["by_source"] == dict(zip(am.source_acc, am.mrdb_acc))
    ma = sql_df(con, "SELECT * FROM mrdb_accession").set_index("mrdb_acc")
    assert set(acc["by_mrdb"]) == set(ma.index)
    for k, e in acc["by_mrdb"].items():
        row = ma.loc[k]
        assert e["representative_source_acc"] == row.representative_source_acc
        assert e["sequence_sha256"] == row.sequence_sha256 and e["first_release"] == row.first_release
        assert sorted(e["sources"]) == sorted(am.source_acc[am.mrdb_acc == k])
        assert e["sources"][0] == row.representative_source_acc
        ent = entries[k]
        assert ent["representative_source_acc"] == row.representative_source_acc
        assert ent["n_source_records"] == int(row.n_source_records) == len(ent["sources"])
        assert ent["sequence_sha256"] == row.sequence_sha256
    for a, (e, s) in records.items():
        assert s["is_mrdb_representative"] is (a == ma.loc[e["mrdb_acc"]].representative_source_acc)
        r = am[am.source_acc == a].iloc[0]
        assert s["source_database"] == r.source_database and s["release_added"] == r.release_added
        assert s["is_current"] is bool(r.is_current)
        assert hashlib.sha256(s["sequence"].encode()).hexdigest() == s["sequence_sha256"] == e["sequence_sha256"]


def test_records_index_matches_records(D, records):
    ri = load(D, "records-index.json")
    cols = ri["columns"]
    assert len(ri["rows"]) == 5466
    order = [(r[0], r[1]) for r in ri["rows"]]
    assert order == sorted(order)
    for row in ri["rows"]:
        r = dict(zip(cols, row))
        e, s = records[r["source_acc"]]
        assert r["mrdb_acc"] == e["mrdb_acc"]
        assert r["membership_status"] == s["membership"]["status"]
        assert r["evidence_level"] == s["function"]["evidence_level"]
        assert r["clade_state"] == s["phylogeny"]["clade_state"]
        assert r["n_pdb"] == len(s["structures"]["experimental"])
        assert r["has_afdb"] is (s["structures"]["afdb"]["status"] == "ok")
        assert r["has_predicted"] is bool(s["structures"]["predicted"])
        assert r["n_support_links"] == sum(p["counts_as_support"] for p in s["publications"])
        # schema 1.1.0 (PR-2) columns: identical to the record file, full precision
        for c in ex.INDEX_COLS_V11:
            if c == "membership_group":
                n = s["membership"]["group"]
            elif c == "status_reason":
                n = s["membership"]["status_reason"]
            elif c in ("e2_ref", "e2_identity", "override_rule"):
                n = s["function"][c]
            elif c == "pocket_string_br":
                n = s["motifs"]["pocket_string_br"]
            elif c == "lineage":
                n = s["lineage"]
            elif c == "pdb_ids":
                n = [x["pdb_id"] for x in s["structures"]["experimental"]]
            else:
                n = path_get(e, s, ex.V_MASTER_FIELD_MAP[c])
            assert r[c] == n and type(r[c]) is type(n), (r["source_acc"], c)


def test_records_index_v11_columns_cover_legacy_tsv():
    """Every legacy TSV column is either an index column or derivable (clade_confidence <- clade_state)."""
    ri_cols = set(ex.INDEX_COLS_V11) | {"mrdb_acc", "source_acc", "is_mrdb_representative", "protein_name", "organism",
                                         "tax_domain", "length", "membership_status", "membership_score", "func_class",
                                         "evidence_level", "call_conflict", "is_engineered", "counts_eligible",
                                         "clade_state", "clade_id", "subclade_id", "tentative_clade_id", "n_pdb",
                                         "has_afdb", "has_predicted", "helixC_motif", "novel_family_flag", "reviewed",
                                         "n_support_links"}
    assert set(LEGACY_PATH) - ri_cols == {"clade_confidence"}


def test_vocabulary(D, con):
    v = load(D, "vocabulary.json")
    sd = sql_df(con, "SELECT * FROM status_definition ORDER BY rowid")
    assert [x["status"] for x in v["membership_status"]] == list(sd.status)
    assert [x["definition"] for x in v["membership_status"]] == list(sd.definition)
    assert [x["group"] for x in v["membership_status"]] == list(sd.status_group)
    fd = sql_df(con, "SELECT * FROM func_class_definition ORDER BY rowid")
    assert [(x["func_class"], x["definition"]) for x in v["func_class"]] == list(zip(fd.func_class, fd.definition))
    assert [x["level"] for x in v["evidence_level"]] == ["E1", "E2", "E3", "E4", "E5"]
    src = v["evidence_level_source"]["text"]
    for x in v["evidence_level"]:
        assert f"{x['level']} {x['definition']}" in src
    assert [x["state"] for x in v["clade_state"]] == ex.CLADE_STATES


def test_sequences_fasta(D, records):
    seqs, cur = {}, None
    for line in (D / "sequences/corpus.fasta").read_text().splitlines():
        if line.startswith(">"):
            cur = line[1:].split()[0]
            seqs[cur] = ""
        else:
            seqs[cur] += line
    ids = {k.split("|")[0] if "|" in k else k for k in seqs}
    assert len(seqs) == 5466 and ids == set(records)


# ----------------------------------------------------------------------------------------------- G1.3 structures
def test_pdb_associations_per_record(D, con, records, entries):
    pp = sql_df(con, "SELECT source_acc, pdb_id FROM protein_pdb")
    assert len(pp) == 472 and pp.pdb_id.nunique() == 438 and pp.source_acc.nunique() == 66
    want = pp.groupby("source_acc").pdb_id.apply(set).to_dict()
    for a, (e, s) in records.items():
        got = [x["pdb_id"] for x in s["structures"]["experimental"]]
        assert len(got) == len(set(got))
        assert set(got) == want.get(a, set()), a
    am = sql_df(con, "SELECT source_acc, mrdb_acc FROM accession_map")
    union = pp.merge(am, on="source_acc").groupby("mrdb_acc").pdb_id.apply(set).to_dict()
    for k, e in entries.items():
        assert e["pdb_union"] == sorted(union.get(k, set())), k
    assert len(entries["MRDB000001"]["pdb_union"]) == 175
    assert sum(1 for e in entries.values() if e["pdb_union"]) == 58


def test_pdb_metadata(D, con, records):
    ps = sql_df(con, "SELECT * FROM pdb_structure WHERE pdb_id IN (SELECT pdb_id FROM protein_pdb)").set_index("pdb_id")
    st = sql_df(con, "SELECT source_acc, rep_pdb_id, highest_res_pdb_id FROM structure").set_index("source_acc")
    idx = load(D, "structures-index.json")["pdb"]
    assert set(idx) == set(ps.index)
    pp = sql_df(con, "SELECT source_acc, pdb_id FROM protein_pdb")
    am = dict(con.execute("SELECT source_acc, mrdb_acc FROM accession_map"))

    def expect(pid):
        r = ps.loc[pid]
        res = r.resolution
        if pd.isna(res):
            res = "not_applicable" if r.method == "SOLUTION NMR" else None
        lig = [x for x in r.ligands.split(";") if x] if r.ligands else []
        return {"pdb_id": pid, "method": r.method, "resolution_A": None if res is None else
                (res if isinstance(res, str) else float(res)), "title": r.title, "ligands": lig,
                "has_retinal": bool(r.has_retinal), "year": int(r.year)}

    for pid, e in idx.items():
        exp = expect(pid)
        accs = sorted(pp.source_acc[pp.pdb_id == pid])
        exp.update(source_accs=accs, mrdb_accs=sorted({am[a] for a in accs}))
        assert e == exp, pid
    for a, (_, s) in records.items():
        for x in s["structures"]["experimental"]:
            base = {k: v for k, v in x.items() if k not in ("is_rep", "is_highest_res", "shared_with")}
            assert base == expect(x["pdb_id"])
            srow = st.loc[a] if a in st.index else None  # some PDB-linked records lack a structure row
            assert x["is_rep"] is bool(srow is not None and srow.rep_pdb_id == x["pdb_id"])
            assert x["is_highest_res"] is bool(srow is not None and srow.highest_res_pdb_id == x["pdb_id"])
            assert x["shared_with"] == sorted(set(pp.source_acc[pp.pdb_id == x["pdb_id"]]) - {a})
    methods = collections.Counter(ps.method)
    assert methods == {"X-RAY DIFFRACTION": 393, "ELECTRON MICROSCOPY": 32, "SOLUTION NMR": 7,
                       "ELECTRON CRYSTALLOGRAPHY": 6}


def test_afdb_metadata(con, records):
    af = sql_df(con, "SELECT * FROM afdb_model").set_index("source_acc")
    assert collections.Counter(af.status) == {"ok": 4397, "no_model": 1069}
    for a, (_, s) in records.items():
        x, r = s["structures"]["afdb"], af.loc[a]
        assert x["status"] == r.status and x["model_id"] == (None if pd.isna(r.model_id) else r.model_id)
        for k in ("version", "seq_start", "seq_end"):
            assert x[k] == (None if pd.isna(r[k]) else int(r[k])) and (x[k] is None or type(x[k]) is int)
        assert x["global_plddt"] == (None if pd.isna(r.global_plddt) else float(r.global_plddt))
        assert x["seq_match"] == (None if pd.isna(r.seq_match) else bool(r.seq_match))


def test_predicted_structures(out, D, con, records):
    frozen = {l.split(None, 1)[1].strip(): l.split()[0] for l in FROZEN.read_text().splitlines() if l.strip()}
    ps = sql_df(con, "SELECT * FROM predicted_structure").set_index("source_acc")
    assert set(ps.index) == {"A0A9X2L7U0", "B0R633"}
    pred = {p["source_acc"]: p for p in load(D, "structures-index.json")["predicted"]}
    assert set(pred) == set(ps.index)
    for a, p in pred.items():
        src = f"releases/v1.0/{ps.loc[a].pdb_file}"
        assert p["source_path"] == src and p["db_pdb_file"] == ps.loc[a].pdb_file
        assert p["sha256"] == frozen[src] == sha256(REPO / src)
        assert (D / p["file"]).read_bytes() == (REPO / src).read_bytes()
        assert p["bytes"] == (REPO / src).stat().st_size
        assert p["method"] == ps.loc[a].method == "ESMCFold2 (full)"
        assert p["mean_plddt"] == ps.loc[a].mean_plddt
        bf = [float(l[60:66]) for l in (REPO / src).read_text().splitlines() if l.startswith("ATOM")]
        assert p["bfactor_scale"] == "fraction_0_1" and 0 < min(bf) and max(bf) <= 1.0
        rec_pred = records[a][1]["structures"]["predicted"]
        assert rec_pred == [{k: v for k, v in p.items() if k not in ("source_acc", "mrdb_acc")}]
        assert p["mrdb_acc"] == records[a][0]["mrdb_acc"]
    assert sum(bool(s["structures"]["predicted"]) for _, s in records.values()) == 2


# ----------------------------------------------------------------------------------------------- G1.4 phylogeny
def test_tree_file_and_stats(D):
    nwk = TREE.read_text().strip()
    assert (D / "phylogeny/MR_RT_003.rooted.treefile").read_bytes() == TREE.read_bytes()
    labels = re.findall(r"\)([^,();:]*)", nwk)
    ts = load(D, "phylogeny/tree_stats.json")
    assert nwk.count("(") == len(labels) == ts["n_internal_incl_root"] == 471
    assert sum(bool(SUPPORT_RE.match(l)) for l in labels) == ts["n_support_labels"] == 469
    assert sum(l == "" for l in labels) == ts["n_unlabelled_internal"] == 2
    assert ts["n_tips"] == 472 and ts["root_children"] == 2
    assert sorted(ts["unlabelled_internal"], key=lambda x: -x["n_tips"]) == \
        [{"is_root": True, "n_tips": 472}, {"is_root": False, "n_tips": 25}]
    assert ts["sha256"] == sha256(TREE)
    assert ts["support_audit"]["n_agree"] == 453 and ts["support_audit"]["n_disagree"] == 17


def _bipartitions(nwk):
    """Independent minimal parser: list of (tipset, label) for every internal node."""
    stack, out, i, tips, cur = [], [], 0, [], None
    while i < len(nwk):
        c = nwk[i]
        if c == "(":
            stack.append(set())
            i += 1
        elif c in ",);":
            if c == ")":
                s = stack.pop()
                j = i + 1
                while j < len(nwk) and nwk[j] not in ",():;":
                    j += 1
                out.append((frozenset(s), nwk[i + 1:j]))
                if stack:
                    stack[-1] |= s
                i = j
                while i < len(nwk) and nwk[i] == ":":  # skip branch length
                    i += 1
                    while i < len(nwk) and nwk[i] not in ",();":
                        i += 1
            else:
                i += 1
        else:
            j = i
            while nwk[j] not in ",():;":
                j += 1
            name = nwk[i:j]
            tips.append(name)
            stack[-1].add(name)
            i = j
            if nwk[i] == ":":
                while nwk[i] not in ",();":
                    i += 1
    return out, tips


def test_support_audit_against_iqtree(D, con):
    rooted, tips = _bipartitions(TREE.read_text().strip())
    run1, tips1 = _bipartitions(RUN1.read_text().strip())
    allt = frozenset(tips)
    assert allt == frozenset(tips1) and len(allt) == 472
    ref = sorted(allt)[0]

    def key(s):
        return s if ref not in s else allt - s

    r1 = {key(s): l for s, l in run1 if 0 < len(s) < len(allt)}
    disagree = [(len(s), l, r1.get(key(s))) for s, l in rooted if len(s) < len(allt) and r1.get(key(s)) != (l or None)]
    sizes = sorted(n for n, _, _ in disagree)
    assert sizes == sorted([457, 452, 416, 391, 268, 266, 260, 141, 126, 116, 114, 110, 109, 100, 48, 47, 25])
    sa = load(D, "phylogeny/support_audit.json")
    assert sa["n_disagree"] == 17
    nodes = [n for n in sa["nodes"] if not n["is_root"]]
    assert len(nodes) == 470 and sum(not n["agrees"] for n in nodes) == 17
    assert sorted(n["n_tips"] for n in nodes if not n["agrees"]) == sizes
    # DB tree_node (unrooted run1 topology) labels equal run1
    db_labels = sorted(l for (l,) in con.execute(
        "SELECT label FROM tree_node WHERE tree_id='MR_RT_003' AND kind!='tip' AND label IS NOT NULL AND label!=''"))
    assert db_labels == sorted(l for s, l in run1 if l)
    cl = {c["clade_id"]: c for c in load(D, "clades.json")["level1"]}
    a17 = cl["MR_CLD3_017"]["support_audit"]
    assert a17["db_label"] == "100/100" and a17["iqtree_run1_label"] == "50.3/72"
    assert a17["db_matches_iqtree_run1"] is False
    assert [k for k, c in cl.items() if c["kind"] == "clade" and not c["support_audit"]["db_matches_iqtree_run1"]] == \
        ["MR_CLD3_017"]


def test_tips(D, con):
    tsv = pd.read_csv(REPO / "refpkg/MR_RT_003/tips.tsv", sep="\t")
    ct = pd.read_csv(REPO / "refpkg/MR_RT_003/clades/MR_CLD3_tips.tsv", sep="\t", keep_default_na=False)
    tips = load(D, "phylogeny/tips.json")["tips"]
    assert len(tips) == 472 and {t["tip"] for t in tips} == set(tsv.source_acc)
    role = dict(zip(tsv.source_acc, tsv.tip_role))
    assert all(t["tip_role"] == role[t["tip"]] for t in tips)
    assert collections.Counter(role.values()) == {"cl0.6_representative": 394, "anchor_characterized": 57,
                                                  "seed": 4, "outgroup_heliorhodopsin": 15,
                                                  "boundary_schizorhodopsin": 2}
    cmap = {r.source_acc: r for r in ct.itertuples()}
    cat = collections.Counter()
    for t in tips:
        r = cmap.get(t["tip"])
        if r is None:
            assert t["tip_role"] == "outgroup_heliorhodopsin" and t["level1"] is None
            cat["outgroup"] += 1
        elif r.clade_id == "backbone_unassigned" and r.subclade_id in ex.BACKBONE_GROUPS:
            # refpkg encodes the 2 backbone groups as clade_id=backbone_unassigned, subclade_id=MR_CLD3_B0x
            assert t["backbone_group"] == r.subclade_id and t["level1"] is None
            assert t["unclustered_backbone"] is False
            cat["backbone_group"] += 1
        elif r.clade_id == "backbone_unassigned":
            assert t["unclustered_backbone"] is True and t["level1"] is None
            cat["unclustered"] += 1
        else:
            assert t["level1"] == r.clade_id and (t["subclade"] or "") == r.subclade_id
            cat["level1"] += 1
    assert cat == {"level1": 422, "backbone_group": 8, "unclustered": 27, "outgroup": 15}
    corpus = {a for (a,) in con.execute("SELECT source_acc FROM v_master")}
    assert sorted(t["tip"] for t in tips if not t["in_corpus"]) == ["QBQ84355", "QBQ84358"]
    assert all(t["in_corpus"] == (t["tip"] in corpus) for t in tips)
    rows = load(D, "phylogeny/clade_tips.json")["rows"]
    assert sorted((r["clade_id"], r["source_acc"], r["subclade_id"] or "") for r in rows) == \
        sorted(zip(ct.clade_id, ct.source_acc, ct.subclade_id))


def test_clade_state(con, records):
    got = collections.Counter(s["phylogeny"]["clade_state"] for _, s in records.values())
    assert got == {"confident": 4139, "tentative": 720, "reference_tip_unclustered": 27,
                   "outgroup_reference_tip": 15, "outgroup_placed": 456, "unassigned": 105, "distant": 4}
    assert sum(got.values()) == 5466
    vm = {r[0]: r[1:] for r in con.execute("SELECT source_acc, clade_id, tentative_clade_id FROM v_master")}
    rc = dict(con.execute("SELECT source_acc, source FROM record_clade"))
    pl_rows = con.execute("SELECT source_acc, clade_call FROM placement WHERE is_current=1 AND tree_id='MR_RT_003'")
    pl = dict(pl_rows.fetchall())
    assert len(pl) == 4996
    for a, (_, s) in records.items():
        st = s["phylogeny"]["clade_state"]
        if a not in rc:
            assert st == "outgroup_reference_tip"
        elif vm[a][0]:
            assert st == "confident"
        elif vm[a][1]:
            assert st == "tentative"
        elif rc[a] == "reference_tip":
            assert st == "reference_tip_unclustered"
        else:
            assert st == {"outgroup_heliorhodopsin": "outgroup_placed", "unassigned": "unassigned",
                          "tentative": "distant"}[pl[a]]


def test_clades(D, con):
    c = load(D, "clades.json")
    assert c["display"] == "17 level-1 clades + 2 backbone groups"
    db = sql_df(con, "SELECT * FROM clade WHERE tree_id='MR_RT_003'")
    l1, l2 = db[db.level == 1], db[db.level == 2]
    assert len(l1) == 19 and len(l2) == 30
    assert [x["clade_id"] for x in c["level1"]] == sorted(l1.clade_id)
    assert [x["clade_id"] for x in c["subclades"]] == sorted(l2.clade_id)
    kinds = collections.Counter(x["kind"] for x in c["level1"])
    assert kinds == {"clade": 17, "backbone_group": 2}
    assert {x["clade_id"] for x in c["level1"] if x["kind"] == "backbone_group"} == set(ex.BACKBONE_GROUPS)
    cols = [k for k in db.columns if k not in ("level",)]
    for x in c["level1"] + c["subclades"]:
        r = db[db.clade_id == x["clade_id"]].iloc[0]
        for k in cols:
            v = r[k]
            v = None if (v is None or (isinstance(v, float) and np.isnan(v))) else v
            v = v.item() if hasattr(v, "item") else v
            assert x[k] == v, (x["clade_id"], k)
    cf = sql_df(con, "SELECT * FROM clade_function_consensus")
    assert len(cf) == 49
    for x in c["level1"] + c["subclades"]:
        r = cf[cf.group_id == x["clade_id"]].iloc[0]
        assert x["function_consensus"]["level"] == r.level
        assert x["function_consensus"]["consensus_status"] == r.consensus_status == x["consensus_status"]
        assert x["function_consensus"]["E1_classes"] == (r.E1_classes or None)
    # schema 1.1.0 (PR-2): run1 support parsed + predefined-threshold test, rule copied from define_clades.py
    src = (REPO / "pipeline/v150/define_clades.py").read_text()
    assert 'PRIMARY = dict(rooting="outgroup", min_size=5, max_size=100, ufb=95, alrt=80)' in src
    assert "SUB = dict(min_size=3, max_size=40, ufb=95, alrt=80)" in src
    r = c["clade_rule"]
    assert r["level1"] == {"rooting": "outgroup", "min_tips": 5, "max_tips": 100, "min_ufboot": 95, "min_sh_alrt": 80}
    assert r["subclade"] == {"min_tips": 3, "max_tips": 40, "min_ufboot": 95, "min_sh_alrt": 80}
    failing = []
    for x in c["level1"] + c["subclades"]:
        sa = x["support_audit"]
        sh, uf = (float(t) for t in sa["iqtree_run1_label"].split("/"))
        assert (sa["iqtree_run1_sh_alrt"], sa["iqtree_run1_ufboot"]) == (sh, uf)
        assert sa["iqtree_run1_meets_support_thresholds"] is (sh >= 80 and uf >= 95)
        if not sa["iqtree_run1_meets_support_thresholds"]:
            failing.append(x["clade_id"])
    assert failing == ["MR_CLD3_017"]
    c17 = next(x for x in c["level1"] if x["clade_id"] == "MR_CLD3_017")
    assert c17["support_audit"]["iqtree_run1_label"] == "50.3/72"
    assert (c17["sh_alrt"], c17["ufboot"]) == (100.0, 100.0)  # frozen DB values unchanged


# ----------------------------------------------------------------------------------------------- v_master cells
def test_every_v_master_cell(con, records):
    cur = con.execute("SELECT * FROM v_master")
    cols = [d[0] for d in cur.description]
    assert set(cols) == set(ex.V_MASTER_FIELD_MAP) and len(cols) == 35
    empty = {c for (t, c) in ex.EMPTY_STRING_RULES if t == "v_master"}
    bad = collections.Counter()
    for row in cur:
        d = dict(zip(cols, row))
        e, s = records[d["source_acc"]]
        for c, path in ex.V_MASTER_FIELD_MAP.items():
            want = d[c]
            if want == "":
                assert c in empty, (d["source_acc"], c)
                want = None
            if c in ex.BOOL_V_MASTER:
                want = bool(want)
            got = path_get(e, s, path)
            if got != want or type(got) is not type(want):
                bad[c] += 1
    assert not bad, bad


def test_empty_strings_never_exported(out):
    for f in all_files(out):
        if f.endswith(".json"):
            assert ':""' not in (out / f).read_text(encoding="utf-8"), f


# ----------------------------------------------------------------------------------------------- G1.6 legacy oracle
LEGACY_PATH = {
    "mrdb_acc": "@entry.mrdb_acc", "source_acc": "source_acc", "protein_name": "protein_name",
    "organism": "organism", "tax_domain": "tax_domain", "length": "length",
    "membership_status": "membership.status", "membership_score": "membership.score",
    "retinal_site_residue": "motifs.retinal_site_residue", "func_class": "function.func_class",
    "evidence_level": "function.evidence_level", "function_basis": "function.function_basis",
    "func_class_v14": "function.func_class_v14", "helixC_motif": "motifs.helixC_motif",
    "motif_class": "motifs.motif_class", "call_conflict": "function.call_conflict",
    "call_conflict_detail": "function.call_conflict_detail", "is_engineered": "engineering.is_engineered",
    "wild_type_acc": "engineering.wild_type_acc", "counts_eligible": "engineering.counts_eligible",
    "exact_duplicate_of": "exact_duplicate_of", "e1_representative": "function.e1_representative",
    "clade_id": "phylogeny.clade_id", "subclade_id": "phylogeny.subclade_id", "clade_name": "phylogeny.clade_name",
    "tentative_clade_id": "phylogeny.tentative_clade_id", "tentative_clade_name": "phylogeny.tentative_clade_name",
    "gtdb_taxonomy": "gtdb.taxonomy", "afdb_model_id": "structures.afdb.model_id",
    "afdb_global_plddt": "structures.afdb.global_plddt", "reviewed": "reviewed", "e2_ref": "function.e2_ref",
    "e2_identity": "function.e2_identity", "override_rule": "function.override_rule",
    "pocket_string_br": "motifs.pocket_string_br", "status_reason": "membership.status_reason",
    "novel_family_flag": "novel_family_flag.hit", "is_mrdb_representative": "is_mrdb_representative",
    "clade_confidence": "phylogeny.clade_state",
}
T1 = {"membership_score": 3, "afdb_global_plddt": 1, "e2_identity": 3}
T2 = {"call_conflict", "is_engineered", "counts_eligible", "reviewed", "is_mrdb_representative"}
T3 = {"clade_id", "subclade_id"}
T4 = {"confident": {"confident"}, "tentative": {"tentative"},
      "none": {"outgroup_reference_tip", "reference_tip_unclustered", "outgroup_placed", "unassigned", "distant"}}


@pytest.fixture(scope="module")
def legacy():
    t = (REPO / "site/data.js").read_text(encoding="utf-8")
    return json.loads(t[t.index("{"):t.rindex("}") + 1])


def test_legacy_oracle_cells(legacy, records, con):
    # The legacy browser (site/data.js) was built from v1.6.0. The only cells allowed to differ are the fields that the
    # signed v1.6.1 decisions changed (curation_v161_decision); every other cell must still match exactly.
    v161 = {(a, {"basis": "function_basis"}.get(f, f)) for a, f in
            con.execute("SELECT source_acc, field FROM curation_v161_decision")} if REL != "v1.6.0" else set()
    cols = legacy["columns"]
    assert cols == list(LEGACY_PATH) and len(cols) == 39
    rows = legacy["rows"]
    assert len(rows) == 5466
    keys = [(r[0], r[1]) for r in rows]
    assert keys == sorted(keys)  # T6
    assert {r[1] for r in rows} == set(records)
    bad = collections.Counter()
    for r in rows:
        L = dict(zip(cols, r))
        e, s = records[L["source_acc"]]
        for c in cols:
            l, n = L[c], path_get(e, s, LEGACY_PATH[c])
            if c in T1:
                ok = (l is None) == (n is None) and (n is None or (type(l) is float and l == float(np.round(float(n), T1[c]))))
            elif c in T2:
                ok = l in (0, 1) and type(l) is int and type(n) is bool and bool(l) is n
            elif c in T3:
                ok = (l == "" and n is None) or (l != "" and l == n and type(l) is type(n))
            elif c == "clade_confidence":
                ok = n in T4[l]
            else:
                ok = l == n and type(l) is type(n)
            if not ok and (L["source_acc"], c) not in v161:
                bad[c] += 1
    assert not bad, bad


def test_legacy_oracle_publications(legacy, records, con):
    pc = legacy["pub_columns"]
    assert pc == ["pmid", "doi", "title", "journal", "year", "link_role", "counts_as_support", "verdict", "caveat"]
    with_pubs = {a for a, (_, s) in records.items() if s["publications"]}
    assert with_pubs == set(legacy["pubs"])
    for a, lst in legacy["pubs"].items():
        new = records[a][1]["publications"]
        conv = [tuple(p[k] if k != "counts_as_support" else int(p[k]) for k in pc) for p in new]
        assert collections.Counter(map(tuple, lst)) == collections.Counter(conv), a
        assert [(-x[6], x[4]) for x in lst] == [(-x[6], x[4]) for x in conv], a  # T7 order key
        assert all(type(x[0]) in (str, type(None)) and type(x[4]) is int for x in lst)
    n_active = con.execute("SELECT COUNT(*) FROM assertion_publication WHERE is_active=1").fetchone()[0]
    assert sum(len(s["publications"]) for _, s in records.values()) == n_active == 255


def test_publications_file(D, con):
    p = load(D, "publications.json")
    assert len(p["publications"]) == con.execute("SELECT COUNT(*) FROM publication").fetchone()[0] == 121
    assert len(p["links"]) == 255
    inactive = sql_df(con, "SELECT assertion_id, publication_id, link_role FROM assertion_publication WHERE is_active=0")
    assert len(p["inactive_links"]) == len(inactive) == 7
    assert all(x["counts_as_support"] is False and x["is_active"] is False for x in p["inactive_links"])
    assert {x["link_role"] for x in p["inactive_links"]} <= {"dropped", "replaced"}
    assert sorted((x["assertion_id"], x["publication_id"]) for x in p["inactive_links"]) == \
        sorted(zip(inactive.assertion_id, inactive.publication_id))


# ----------------------------------------------------------------------------------------------- G1.5 summary
def _independent_metrics(con):
    t = {n: pd.read_sql_query(f"SELECT * FROM {n}", con) for n in
         ("v_master", "mrdb_accession", "status_definition", "publication", "assertion_publication", "protein_pdb",
          "pdb_structure", "afdb_model", "predicted_structure", "tree_node", "clade", "placement",
          "novel_family_candidate", "accession_map", "novel_family_flag", "foldseek_hit")}
    v, ap, pp = t["v_master"], t["assertion_publication"], t["protein_pdb"]
    grp = v.membership_status.map(dict(zip(t["status_definition"].status, t["status_definition"].status_group)))
    act = ap[ap.is_active == 1]
    cl = t["clade"][t["clade"].tree_id == "MR_RT_003"]
    pl = t["placement"]
    return {
        "records_total": len(v), "records_counted": int((v.counts_eligible == 1).sum()),
        "records_engineered": int((v.is_engineered == 1).sum()), "mrdb_accessions": len(t["mrdb_accession"]),
        "mrdb_multi_source": int((t["mrdb_accession"].n_source_records > 1).sum()),
        "typeI_members": int((grp == "member").sum()), "typeI_candidates": int((grp == "candidate").sum()),
        "e1_counted": int(((v.evidence_level == "E1") & (v.counts_eligible == 1)).sum()),
        "e1_total": int((v.evidence_level == "E1").sum()),
        "e1_unique_sequences": v[(v.evidence_level == "E1") & (v.counts_eligible == 1)].mrdb_acc.nunique(),
        "call_conflict": int((v.call_conflict == 1).sum()), "publications": len(t["publication"]),
        "publication_links_active": len(act), "publication_links_support": int((act.counts_as_support == 1).sum()),
        "records_with_publications": act.source_acc.nunique(), "pdb_links": len(pp),
        "pdb_entries": pp.pdb_id.nunique(), "records_with_pdb": pp.source_acc.nunique(),
        "mrdb_with_pdb": pp.merge(t["accession_map"], on="source_acc").mrdb_acc.nunique(),
        "pdb_entries_with_retinal": int(t["pdb_structure"][t["pdb_structure"].pdb_id.isin(pp.pdb_id)].has_retinal.sum()),
        "records_with_afdb": int((t["afdb_model"].status == "ok").sum()),
        "predicted_models": len(t["predicted_structure"]),
        "tree_tips": int(((t["tree_node"].tree_id == "MR_RT_003") & (t["tree_node"].kind == "tip")).sum()),
        "level1_clades": int(((cl.level == 1) & cl.parent_clade_id.isna()).sum()),
        "backbone_groups": int(((cl.level == 1) & (cl.parent_clade_id == "backbone")).sum()),
        "subclades": int((cl.level == 2).sum()),
        "placements_current": int(((pl.is_current == 1) & (pl.tree_id == "MR_RT_003")).sum()),
        "watchlist": len(t["novel_family_candidate"]),
        # schema 1.4.0 (PR-5)
        "members_candidates": int(grp.isin(["member", "candidate"]).sum()),
        "clade_confident_members_candidates": int((grp.isin(["member", "candidate"])
                                                   & v.clade_id.fillna("").ne("")).sum()),
        "records_with_afdb_counted": int(v[v.counts_eligible == 1].source_acc.isin(
            t["afdb_model"][t["afdb_model"].status == "ok"].source_acc).sum()),
        "records_with_pdb_counted": int(v[v.counts_eligible == 1].source_acc.isin(pp.source_acc).sum()),
        "novel_family_flag": int(t["novel_family_flag"].novel_family_hit.notna().sum()),
        "foldseek_hits": len(t["foldseek_hit"]),
    }, t


BASELINE = {"records_total": 5466, "records_counted": 5460, "records_engineered": 6, "mrdb_accessions": 5299,
            "mrdb_multi_source": 129, "e1_unique_sequences": 76, "call_conflict": 480, "pdb_links": 472,
            "pdb_entries": 438, "records_with_pdb": 66, "mrdb_with_pdb": 58, "records_with_afdb": 4397,
            "predicted_models": 2, "tree_tips": 472, "level1_clades": 17, "backbone_groups": 2, "subclades": 30,
            "placements_current": 4996, "watchlist": 181, "publications": 121, "publication_links_active": 255,
            # v1.6.1 release notes: 3,821 / 4,465 (85.6%) confident-clade coverage of members + candidates
            "members_candidates": 4465, "clade_confident_members_candidates": 3821, "novel_family_flag": 139}


def test_summary_metrics_recomputed(D, con):
    s = load(D, "summary.json")
    exp, t = _independent_metrics(con)
    got = {m["id"]: m["value"] for m in s["metrics"]}
    assert set(got) == set(exp)
    assert got == exp
    for k, v in BASELINE.items():
        assert got[k] == v, k
    dens = {k: d["value"] for k, d in s["denominators"].items()}
    for m in s["metrics"]:
        if m["denominator"] is not None:
            assert m["denominator"]["value"] == dens[m["denominator"]["id"]] >= m["value"]
    for m in s["metrics"] + s["distributions"]:
        if m.get("sql"):
            assert re.match(r"^\s*SELECT\b", m["sql"], re.I) and ";" not in m["sql"]


def test_summary_distributions_recomputed(D, con, records):
    s = load(D, "summary.json")
    _, t = _independent_metrics(con)
    v = t["v_master"]
    cnt = v[v.counts_eligible == 1]
    pp, ps = t["protein_pdb"], t["pdb_structure"]
    act = t["assertion_publication"][t["assertion_publication"].is_active == 1]
    sd = dict(zip(t["status_definition"].status, t["status_definition"].status_group))
    pl = t["placement"][(t["placement"].is_current == 1) & (t["placement"].tree_id == "MR_RT_003")]
    cl = t["clade"][(t["clade"].tree_id == "MR_RT_003") & (t["clade"].level == 1)]
    af = t["afdb_model"].set_index("source_acc").status
    cov = ["pdb" if a in set(pp.source_acc) else ("afdb_only" if af[a] == "ok" else "none") for a in v.source_acc]
    tips = pd.read_csv(REPO / "refpkg/MR_RT_003/tips.tsv", sep="\t")

    def vc(series):
        c = collections.Counter(None if (x is None or (isinstance(x, float) and np.isnan(x))) else x for x in series)
        return c

    exp = {
        "membership_status": vc(v.membership_status), "membership_group": vc(v.membership_status.map(sd)),
        "evidence_level_counted": vc(cnt.evidence_level), "evidence_level_all": vc(v.evidence_level),
        "func_class_counted": vc(cnt.func_class), "tax_domain_counted": vc(cnt.tax_domain),
        "structure_coverage": vc(cov), "afdb_status": vc(t["afdb_model"].status),
        "pdb_method": vc(ps[ps.pdb_id.isin(pp.pdb_id)].method), "link_role": vc(act.link_role),
        "clade_state": vc(s_["phylogeny"]["clade_state"] for _, s_ in records.values()),
        "placement_clade_call": vc(pl.clade_call), "clade_consensus_status": vc(cl.consensus_status),
        "tip_role": vc(tips.tip_role), "watchlist_family": vc(t["novel_family_candidate"].family),
    }
    # schema 1.4.0 (PR-5): recomputed in pandas/Python, independently of the exporter SQL
    lin = pd.read_sql_query("SELECT source_acc, lineage FROM protein", con).set_index("source_acc").lineage

    def phylum(acc):
        hits = re.findall(r"(?:^|, )([^,]+?) \(phylum\)", lin.get(acc) or "")
        assert len(hits) <= 1
        return hits[0] if hits else None

    def lbin(n):
        if n < 200:
            return "<200"
        if n >= 450:
            return ">=450"
        lo = 200 + (n - 200) // 25 * 25
        return f"{lo}-{lo + 24}"

    def basis(b):
        b = b or ""
        if b.startswith("identical_sequence:") and "|" in b:  # v1.6.1: categorised by the identical twin's basis
            b = b.split("|", 1)[1]
        for pre, key in (("experimental_ortholog:", "experimental_ortholog"), ("motif+phylogeny:", "motif+phylogeny"),
                         ("legacy_v14_concordant_motif:", "legacy_v14_concordant_motif"),
                         ("legacy_v14_motif_untestable:", "legacy_v14_motif_untestable"),
                         ("curated_rule:", "curated_rule"), ("audit_rule_", "audit_rule"),
                         ("family_hmm_", "family_hmm_conflict"), ("conflict:", "conflict")):
            if b.startswith(pre):
                return key
        return {"experimental:this_protein": "experimental:this_protein", "insufficient": "insufficient"}.get(b, "UNMAPPED")

    mc = set(v.source_acc[v.membership_status.map(sd).isin(["member", "candidate"])])
    exp.update({
        "membership_status_counted": vc(cnt.membership_status),
        "ncbi_phylum_counted": vc(phylum(a) for a in cnt.source_acc),
        "motif_class_counted": vc(cnt.motif_class), "helixC_motif_counted": vc(cnt.helixC_motif),
        "length_bin_counted": vc(lbin(int(n)) for n in cnt.length),
        "function_basis_category_counted": vc(basis(b) for b in cnt.function_basis),
        "clade_state_members_candidates": vc(s_["phylogeny"]["clade_state"] for a, (_, s_) in records.items()
                                             if a in mc),
    })
    assert exp["function_basis_category_counted"]["UNMAPPED"] == 0
    assert exp["clade_state_members_candidates"]["confident"] == 3821
    got = {d["id"]: d for d in s["distributions"]}
    assert set(got) == set(exp)
    for k, d in got.items():
        assert {i["key"]: i["value"] for i in d["items"]} == dict(exp[k]), k
        assert d["total"] == sum(exp[k].values()) == d["denominator"]["value"], k
    assert dict(exp["structure_coverage"]) == {"pdb": 66, "afdb_only": 4336, "none": 1064}


# ----------------------------------------------------------------------------------------------- G1.7 watchlist
def test_watchlist_disjoint(D, con, records):
    w = load(D, "watchlist.json")
    nfc = sql_df(con, "SELECT * FROM novel_family_candidate")
    assert len(w["candidates"]) == len(nfc) == 181
    assert collections.Counter(c["family"] for c in w["candidates"]) == \
        {"viral_rhodopsin": 138, "structure_only": 23, "schizorhodopsin": 12, "bestrhodopsin": 5, "MerMAID": 3}
    ids = {c["resolved_accession"] for c in w["candidates"]} | {c["identifier"] for c in w["candidates"]}
    assert not (ids & set(records))
    seqs = {s["sequence_sha256"] for _, s in records.values()}
    assert w.get("isolation") is not None and seqs  # isolation statement present


# ----------------------------------------------------------------------------------------------- schema / types
def test_json_schema_all_payloads(out):
    import jsonschema
    schema = json.loads(SCHEMA.read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    # PR-7c.2: the habitat sidecar (v1.6.1/habitat/**) has its own schema; every other file uses the core schema.
    hschema = json.loads(HABITAT_SCHEMA.read_text())
    jsonschema.Draft202012Validator.check_schema(hschema)
    validators = {}
    files = [f for f in all_files(out) if f.endswith(".json")]
    seen = collections.Counter()
    errors = []
    for f in files:
        sch = hschema if f.startswith(f"{REL}/habitat/") else schema
        pats = [p for p in sch["x-files"] if fnmatch.fnmatch(f, p)]
        assert len(pats) == 1, (f, pats)
        name = sch["x-files"][pats[0]]
        if name not in validators:
            validators[name] = jsonschema.Draft202012Validator(
                {"$schema": sch["$schema"], "$defs": sch["$defs"], "$ref": f"#/$defs/{name}"})
        errs = list(validators[name].iter_errors(json.loads((out / f).read_text(encoding="utf-8"))))
        if errs:
            errors.append((f, errs[0].message))
        seen[pats[0]] += 1
    assert not errors, errors[:5]
    assert set(seen) == set(schema["x-files"]) | set(hschema["x-files"])
    assert len(files) == 5318 + 5301  # 5,315 in schema 1.0.0 + vocabulary.json (1.1.0) + phylogeny/explorer.json (1.2.0) + downloads.json (1.4.0); + habitat sidecar (PR-7c.2: 5,299 records + summary + manifest)


def test_typescript_types_up_to_date():
    r = subprocess.run([sys.executable, str(REPO / "web/scripts/schema_to_ts.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ----------------------------------------------------------------------------------------------- G1.9 frozen inputs
def test_frozen_files_and_db_unchanged(exports, db_sha_before):
    assert db_sha_before == DB_SHA256 == sha256(DB)
    bad = []
    for line in FROZEN.read_text().splitlines():
        if line.strip():
            h, f = line.split(None, 1)
            if sha256(REPO / f.strip()) != h:
                bad.append(f)
    assert bad == [] and sum(1 for l in FROZEN.read_text().splitlines() if l.strip()) == 176


# ----------------------------------------------------------------------------------------------- failure modes
def test_wrong_db_checksum_is_blocked(tmp_path):
    r = run_exporter(tmp_path / "o", "--expected-sha256", "0" * 64)
    assert r.returncode == 2 and "BLOCKED_DATA_SOURCE" in r.stderr
    assert not (tmp_path / "o" / REL).exists()


def test_missing_db_is_blocked(tmp_path):
    r = subprocess.run([sys.executable, str(EXPORTER), "--repo", str(REPO), "--db", str(tmp_path / "absent.sqlite"),
                        "--out", str(tmp_path / "o")], capture_output=True, text=True)
    assert r.returncode == 2 and "BLOCKED_DATA_SOURCE" in r.stderr


def test_refuses_to_replace_foreign_directory(tmp_path):
    (tmp_path / REL).mkdir()
    (tmp_path / REL / "keep.txt").write_text("not an export")
    r = run_exporter(tmp_path)
    assert r.returncode == 4 and "CONTRACT_VIOLATION" in r.stderr
    assert (tmp_path / REL / "keep.txt").read_text() == "not an export"
