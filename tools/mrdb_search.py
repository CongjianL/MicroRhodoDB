#!/usr/bin/env python
"""mrdb_search - score query proteins with the frozen MicroRhodoDB membership scorer and find their nearest
MicroRhodoDB release records (default: the v1.6.0 release in this repository/archive).

  python tools/mrdb_search.py query.faa [--release releases/v1.6.0] -o hits.tsv [--threads 4] [--workdir tmp]

Requires HMMER 3.4 and DIAMOND (pinned env: 2.1.10) on PATH. DIAMOND is used twice: for the scorer's seed-homology
feature (part of membership_score) and for the nearest-neighbour search below.

Per query:
  * frozen v1.2 scorer (PF01036/PF18761 HMMs, retinal-lysine check at BR K216, seed homology, topology)
    -> membership_score, membership_category, gates (has_domain, not heliorhodopsin-primary, Type-I margin)
  * provisional_status: member-like (score >= 0.86, K216, gates) / candidate-like (0.40-0.86 or truncated core,
    K216) / boundary-like (PF01036 homolog, no K216) / heliorhodopsin-like / not_rhodopsin. This approximates the release
    status rules; the architecture route (route2) and curator overrides are NOT re-evaluated.
  * typeI_detected_070: "yes" if membership_score >= 0.70. 0.70 is the recommended detection threshold from v1.6.0
    (clade-root holdout sensitivity 42/46, specificity 209/215; external set sensitivity 16/21, specificity 345/345).
    The 0.86/0.90 thresholds miss most novel-family proteins (external sensitivity 10/21 and 3/21); bestrhodopsins
    score below 0.70 (0/4), so a "no" here does not exclude a distant rhodopsin family.
  * novel_family_hit / novel_family_evalue / novel_family_bits / pf01036_bits (tools/family_flag.py): the best of five
    family HMMs (viral, schizo-, xeno-, bestrhodopsin, MerMAID) if E <= 1e-10 and its bit score exceeds the PF01036
    bit score. A pointer to inspect the protein, not a membership or function call (scorer unchanged).
  * DIAMOND blastp (--more-sensitive) nearest neighbour in the release, annotated with its MRDB accession, membership
    status, MR_CLD3 clade, functional class, evidence level and (v1.6.0+) function basis, legacy v1.4 / motif classes,
    call-conflict and engineered-construct flags from v_master. If the neighbour has no confident clade
    but a distant (pendant-QC-failed) placement, nn_tentative_clade_id/name are filled and nn_tentative_clade_note says
    "distant placement, low confidence"; these are not clade assignments.
Function is NOT transferred: the nearest-neighbour annotation is reported with its identity so users can apply their own
threshold (the release uses >= 90% identity within the same clade for E2).
"""
import argparse, os, sys, sqlite3, subprocess, shutil
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "pipeline", "v150"))
sys.path.insert(0, HERE)


def ensure_release_fasta(db, fa):
    if os.path.exists(fa):
        return
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    with open(fa, "w") as f:
        for acc, src, seq in con.execute("select mrdb_acc, source_acc, sequence from protein order by mrdb_acc"):
            f.write(f">{src} {acc}\n{seq}\n")
    con.close()


def provisional(r):
    if r.get("is_helio_primary") in (True, 1, "True"):
        return "heliorhodopsin_like"
    if not r.get("gate_has_domain") in (True, 1, "True"):
        return "not_rhodopsin"
    k = r.get("has_retinal_lysine") in (True, 1, "True", 1.0)
    s = r.get("membership_score") or 0
    if k and s >= 0.86 and r.get("gate_complete_core") in (True, 1, "True"):
        return "member_like"
    if k and s >= 0.40:
        return "candidate_like"
    if s >= 0.40:
        return "boundary_or_unresolved_like"
    return "below_threshold"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query")
    ap.add_argument("--release", default=os.path.join(HERE, "..", "releases", "v1.6.0"))
    ap.add_argument("-o", "--out", default="mrdb_search_hits.tsv")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--workdir", default="mrdb_search_tmp")
    a = ap.parse_args()
    R = a.release
    import glob
    dbs = [f for f in sorted(glob.glob(os.path.join(R, "db", "microrhododb_v*.sqlite"))) if "env_pilot" not in f]
    if len(dbs) != 1:
        sys.exit(f"expected exactly one release database in {R}/db, found {dbs}")
    db = dbs[0]
    sd = os.path.join(R, "scorer")
    for f in [db, f"{sd}/seeds.faa", f"{sd}/seed_meta.tsv", f"{sd}/PF01036.25.hmm", f"{sd}/PF18761.8.hmm"]:
        if not os.path.exists(f):
            sys.exit(f"missing release file: {f}")
    os.makedirs(a.workdir, exist_ok=True)
    import score_v150 as sc
    S = sc.compute(a.query, f"{sd}/seeds.faa", f"{sd}/seed_meta.tsv", f"{sd}/PF01036.25.hmm", f"{sd}/PF18761.8.hmm",
                   os.path.join(a.workdir, "score"))
    S["membership_score"] = S.membership_score.fillna(0.0)   # no PF01036 domain -> 0 (as in the frozen release scores)
    S["provisional_status"] = [provisional(r) for r in S.to_dict("records")]
    S["typeI_detected_070"] = (S.membership_score >= 0.70).map({True: "yes", False: "no"})

    import family_flag
    F = family_flag.flags(a.query, R, workdir=os.path.join(a.workdir, "family"), threads=a.threads)
    S = S.merge(F.rename(columns={"query": "source_acc"}), on="source_acc", how="left")

    fa = os.path.join(a.workdir, "release.faa")
    ensure_release_fasta(db, fa)
    dmnd = os.path.join(a.workdir, "release.dmnd")
    dia = shutil.which("diamond") or "diamond"
    if not os.path.exists(dmnd):
        subprocess.run([dia, "makedb", "--in", fa, "-d", dmnd, "--quiet"], check=True)
    m8 = os.path.join(a.workdir, "nn.m8")
    subprocess.run([dia, "blastp", "-q", a.query, "-d", dmnd, "-o", m8, "--more-sensitive", "-k", "1", "--quiet",
                    "-p", str(a.threads), "--outfmt", "6", "qseqid", "sseqid", "pident", "qcovhsp", "scovhsp", "bitscore", "evalue"],
                   check=True)
    nn = pd.read_csv(m8, sep="\t", header=None, names=["source_acc", "nn_source_acc", "nn_identity", "nn_qcov", "nn_scov", "nn_bits", "nn_evalue"])
    nn = nn.drop_duplicates("source_acc")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    vcols = {r[1] for r in con.execute("PRAGMA table_info(v_master)")}
    V16 = ["function_basis", "func_class_v14", "motif_class", "call_conflict", "is_engineered", "wild_type_acc"]
    vm = pd.read_sql("select source_acc as nn_source_acc, mrdb_acc as nn_mrdb_acc, membership_status as nn_status, "
                     "clade_id as nn_clade_id, clade_name as nn_clade_name, "
                     "tentative_clade_id as nn_tentative_clade_id, tentative_clade_name as nn_tentative_clade_name, "
                     "func_class as nn_func_class, "
                     "evidence_level as nn_evidence_level, organism as nn_organism" +
                     ("".join(f", {c} as nn_{c}" for c in V16 if c in vcols)) + " from v_master", con)
    con.close()
    keep = ["source_acc", "length", "membership_score", "membership_category", "provisional_status", "typeI_detected_070",
            "novel_family_hit", "novel_family_evalue", "novel_family_bits", "pf01036_bits", "has_retinal_lysine",
            "gate_has_domain", "is_helio_primary", "gate_complete_core", "dom_score", "hmm_cov"]
    vm["nn_tentative_clade_note"] = vm.nn_tentative_clade_id.map(
        lambda c: "distant placement, low confidence" if isinstance(c, str) and c else None)
    out = S[[c for c in keep if c in S]].merge(nn.merge(vm, on="nn_source_acc", how="left"), on="source_acc", how="left")
    out.rename(columns={"source_acc": "query"}).to_csv(a.out, sep="\t", index=False)
    print(f"{len(out)} queries -> {a.out}")
    print(out.provisional_status.value_counts().to_string())
    print(f"typeI_detected_070 = yes: {(out.typeI_detected_070 == 'yes').sum()}/{len(out)}")
    print(f"novel_family_hit: {out.novel_family_hit.notna().sum()}/{len(out)}")


if __name__ == "__main__":
    main()
