"""Deterministic, re-drawable audit sample of function-evidence records (R-B1).

The v1.5.0 audit-B sample (seed 150) was frozen by SHA-256 but the command that drew it was not saved, so it
can be re-checked but not re-drawn. From v1.6.0 every audit sample is drawn with this script and the exact
command line is written into the output header, so anyone can regenerate it byte-for-byte.

Procedure (fully specified): for each tier, take the counted records (is_engineered = 0) at that evidence
level, sort by source_acc, draw n indices without replacement with numpy.random.default_rng(seed + tier_index)
(tier_index = position of the tier in --tiers, starting at 0), and output the drawn rows sorted by tier then
source_acc.

The v1.6.0 R2 sample was drawn before the R2 corrections changed some evidence levels. The function_evidence
frame it was drawn from is frozen in curation/v160/audit_frame_v160_pre_r2.tsv; pass it with --frame to re-draw
the sample byte-for-byte (the --db is then used only for the release label).

usage:
  python tools/draw_audit_sample.py --db releases/v1.6.0/db/microrhododb_v1.6.0.sqlite \
      --seed 160 --n 40 --tiers E2,E3,E4 --out curation/v160/audit_sample_v160_seed160.tsv \
      [--frame curation/v160/audit_frame_v160_pre_r2.tsv]
"""
import argparse
import hashlib
import sqlite3
import sys

import numpy as np


def draw(db, seed, n, tiers, frame=None):
    if frame:
        import pandas as pd
        con = sqlite3.connect(":memory:")
        pd.read_csv(frame, sep="\t", comment="#", dtype={"call_conflict": "Int64", "is_engineered": int}) \
            .to_sql("function_evidence", con, index=False)
    else:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out = []
    for i, tier in enumerate(tiers):
        accs = [r[0] for r in con.execute(
            "SELECT source_acc FROM function_evidence WHERE evidence_level = ? AND is_engineered = 0 "
            "ORDER BY source_acc", (tier,))]
        if n > len(accs):
            raise SystemExit(f"tier {tier}: requested {n} > available {len(accs)}")
        idx = np.random.default_rng(seed + i).choice(len(accs), size=n, replace=False)
        rows = con.execute(
            f"SELECT source_acc, evidence_level, func_class, call_conflict FROM function_evidence "
            f"WHERE source_acc IN ({','.join('?' * n)}) ORDER BY source_acc", [accs[j] for j in idx]).fetchall()
        out += rows
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--tiers", default="E2,E3,E4")
    ap.add_argument("--out", required=True)
    ap.add_argument("--frame", help="frozen function_evidence TSV to draw from instead of the DB")
    a = ap.parse_args(argv)
    tiers = a.tiers.split(",")
    rows = draw(a.db, a.seed, a.n, tiers, a.frame)
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    rel = con.execute("SELECT value FROM release_metadata WHERE key='version' ORDER BY release DESC").fetchone()[0]
    lines = [f"# drawn by: python tools/draw_audit_sample.py --db <microrhododb_v{rel}.sqlite> --seed {a.seed} "
             f"--n {a.n} --tiers {a.tiers} --out <file>  (numpy {np.__version__})",
             "source_acc\tevidence_level\tfunc_class\tcall_conflict"]
    lines += ["\t".join(str(x) for x in r) for r in rows]
    text = "\n".join(lines) + "\n"
    with open(a.out, "w") as fh:
        fh.write(text)
    # the hash covers the data rows only (the header records the numpy version, which may differ)
    h = hashlib.sha256("\n".join(lines[1:]).encode()).hexdigest()
    print(f"{len(rows)} records -> {a.out}; sha256(data rows) = {h}")
    return h


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
