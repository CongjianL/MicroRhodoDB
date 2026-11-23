"""Tests for the construction-review checks (pipeline/construction_review/, tools/helixc_motif.py).

They run against the current release database and do not change it.

Environment:
    MRDB_DB161     database under test (default releases/v1.6.1/db/microrhododb_v1.6.1.sqlite)
    MRDB_REPO      repository / archive root (default '.')
"""
import os
import shutil
import sqlite3
import subprocess
import sys

import pandas as pd
import pytest

REPO = os.path.abspath(os.environ.get("MRDB_REPO", "."))
DB = os.environ.get("MRDB_DB161", os.path.join(REPO, "releases/v1.6.1/db/microrhododb_v1.6.1.sqlite"))
HMM = os.path.join(REPO, "releases/v1.6.1/scorer/PF01036.25.hmm")
REVIEW = os.path.join(REPO, "pipeline/construction_review")
sys.path.insert(0, os.path.join(REPO, "tools"))
import helixc_motif as hm  # noqa: E402


@pytest.fixture(scope="module")
def con():
    if not os.path.exists(DB):
        pytest.skip(f"v1.6.1 DB not present: {os.path.relpath(DB, REPO)} (not committed; see BINARIES.md)")
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    yield c
    c.close()


def test_motif_class_mapping_matches_stored(con):
    # the stored motif_class is a function of the stored motif, and helixc_motif.motif_class reproduces it
    rows = con.execute("select distinct helixC_motif, motif_class from function_evidence "
                       "where helixC_motif is not null").fetchall()
    assert len({m for m, _ in rows}) == len(rows)
    assert all((hm.motif_class(m) or "") == (c or "") for m, c in rows)


def test_rederived_motif_matches_stored(con, tmp_path):
    assert shutil.which("hmmalign"), "hmmalign not on PATH - activate the pinned environment"
    recs = con.execute("select f.source_acc, upper(p.sequence), f.helixC_motif from function_evidence f "
                       "join protein p using(source_acc) where f.helixC_motif is not null "
                       "order by f.source_acc").fetchall()
    sample = recs[::25]   # every 25th record; the full comparison is pipeline/construction_review/helixc_motif.py
    got = hm.derive({a: s for a, s, _ in sample}, HMM, hm.br_sequence(DB), str(tmp_path)).set_index("source_acc")
    assert all(got.at[a, "helixC_motif"] == m for a, _, m in sample)


def test_specificity_script_reproduces_shipped_operating_points(con, tmp_path):
    # the script exits non-zero unless its pooled counts equal the shipped operating-point rows
    out = tmp_path / "spec.tsv"
    subprocess.run([sys.executable, os.path.join(REVIEW, "specificity_by_negative_class.py"), DB, str(out)],
                   check=True, capture_output=True)
    t = pd.read_csv(out, sep="\t")
    hard = t[(t.neg_class == "all") & (t.rejected_by == "hard_not_gated") & (t.threshold == 0.70)].set_index("set")
    assert (hard.at["external", "true_negatives"], hard.at["external", "n"]) == (30, 30)
    assert (hard.at["holdout_reference_clade_root", "true_negatives"],
            hard.at["holdout_reference_clade_root", "n"]) == (39, 45)


def test_placement_membership_disagreements_are_long_pendant(con, tmp_path):
    subprocess.run([sys.executable, os.path.join(REVIEW, "consistency_checks.py"), DB, str(tmp_path)],
                   check=True, capture_output=True)
    pm = pd.read_csv(tmp_path / "placement_vs_membership.tsv", sep="\t")
    assert len(pm) == 51
    assert (pm.placement_qc == "long_pendant").all()
    assert {"L1K1K8", "A0A0C3UE61"} <= set(pm.source_acc)
