#!/usr/bin/env python
"""WP2 - v1.5.0 membership-status vocabulary, boundary families, resolvability.

Inputs
  --db       v1.4.0 SQLite (read-only)
  --retcol   members_retinal_column.tsv (hmmalign --trim vs PF01036.25; residue at
             PF01036 match state 210 == BR K216; covers_TM7 == last match state >= 215)
  --faa      members.faa (sequences of all typeI* records)
  --outdir   output directory
Outputs
  status_definition.tsv     controlled vocabulary with operational definitions
  membership_v150.tsv       per-record v1.5 status, alias_v14, reason, boundary subtype
  resolvability.tsv         fate of the v1.4 typeI_candidate_unresolved records
  unresolved_homolog.tsv    nearest full-length homolog for still-unresolved records
"""
import argparse, os, sqlite3, subprocess, shutil
import pandas as pd

STATUS_DEF = [
    # status, group, is_member, is_candidate, alias_v14, definition
    ("typeI_member_core", "member", 1, 0, "typeI_core",
     "Predicted Type-I microbial rhodopsin. PF01036 (Bac_rhodopsin) is the dominant domain, the PF01036 HMM "
     "is >=60% covered (complete 7-TM core), the retinal Schiff-base lysine is aligned at PF01036 match state "
     "210 (BR K216, TM7), membership_score >=0.86 and the architecture is canonical single-domain (route1). "
     "'Member' asserts family membership plus an intact retinal-binding site; it does NOT assert that the "
     "protein is expressed, photochemically active or physiologically functional."),
    ("typeI_member_architecture_supported", "member", 1, 0, "typeI_core_architecture_supported",
     "As typeI_member_core (score >=0.86, complete core, K at match state 210) but in a non-canonical "
     "architecture (extended termini or fusion to another domain) that is supported by route2 rules."),
    ("typeI_candidate", "candidate", 0, 1, "typeI_candidate",
     "Retinal lysine present at match state 210 but membership_score 0.40-0.86 or a truncated core "
     "(hmm_cov <0.6). Family membership is probable; one quantitative criterion for member status is unmet."),
    ("typeI_candidate_architecture_supported", "candidate", 0, 1, "typeI_candidate_architecture_supported",
     "Retinal lysine present, complete core, non-canonical architecture supported by route2, but "
     "membership_score 0.40-0.86."),
    ("typeI_candidate_unresolved", "candidate", 0, 1, "typeI_candidate_unresolved",
     "PF01036 homolog (score >=0.40) for which the retinal-binding position (match state 210) is not "
     "observed in the predicted protein: the sequence ends before TM7, has an alignment gap at 210, or "
     "only partially covers TM7. Membership cannot be decided from the deposited sequence; resolution "
     "requires a corrected gene model or full-length sequence."),
    ("boundary_family", "boundary", 0, 0, None,
     "PF01036-related protein outside the Type-I member definition but retained as a named boundary set. "
     "Subtypes: retinal_site_lacking_homolog (full-length, TM7 covered, non-lysine residue at match state "
     "210; e.g. fungal opsin-related proteins / HSP30-like ORPs); schizorhodopsin (intermediate between "
     "Type-I and heliorhodopsins; external exemplars only in v1.5.0)."),
    ("heliorhodopsin", "outgroup", 0, 0, "heliorhodopsin",
     "PF18761 (Heliorhodopsin) dominant over PF01036 (inverted membrane topology family). Used as the "
     "outgroup for MR_RT_003."),
    ("decoy_or_rejected", "rejected", 0, 0, "decoy_or_rejected",
     "Fails the membership screen (score <0.40 or decoy family) and is retained only for audit."),
]

V14_TO_V15 = {
    "typeI_core": "typeI_member_core",
    "typeI_core_architecture_supported": "typeI_member_architecture_supported",
    "typeI_candidate": "typeI_candidate",
    "typeI_candidate_architecture_supported": "typeI_candidate_architecture_supported",
    "typeI_candidate_unresolved": "typeI_candidate_unresolved",
    "heliorhodopsin": "heliorhodopsin",
    "decoy_or_rejected": "decoy_or_rejected",
}


def site_state(x):
    if isinstance(x, str) and x.upper() == "K":
        return "K"
    if not isinstance(x, str) or x in ("-", "."):
        return "gap"
    return "nonK"


def read_fasta(p):
    seqs, acc = {}, None
    for line in open(p):
        if line.startswith(">"):
            acc = line[1:].split()[0]
            seqs[acc] = []
        elif acc:
            seqs[acc].append(line.strip())
    return {k: "".join(v) for k, v in seqs.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--retcol", required=True)
    ap.add_argument("--faa", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--threads", type=int, default=8)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    m = pd.read_sql("select source_acc, membership_status, membership_category, membership_score, "
                    "architecture_class, arch_route, reason_code from membership", con)
    rc = pd.read_csv(a.retcol, sep="\t")
    rc["site"] = rc.ms210.map(site_state)
    m = m.merge(rc[["source_acc", "ms210", "site", "covers_TM7", "ms_first", "ms_last", "tax_domain",
                    "phylum", "protein_name", "length"]], on="source_acc", how="left")

    m["alias_v14"] = m.membership_status
    m["membership_status_v150"] = m.membership_status.map(V14_TO_V15)
    m["status_reason"] = m.reason_code.fillna("")
    m["boundary_subtype"] = ""

    u = m.membership_status == "typeI_candidate_unresolved"
    full_nonk = u & (m.site == "nonK") & (m.covers_TM7 == True)
    m.loc[full_nonk, "membership_status_v150"] = "boundary_family"
    m.loc[full_nonk, "boundary_subtype"] = "retinal_site_lacking_homolog"
    m.loc[full_nonk, "status_reason"] = "retinal_site_nonK:" + m.loc[full_nonk, "ms210"].astype(str)
    still = u & ~full_nonk
    m.loc[still & (m.site == "gap") & (m.covers_TM7 != True), "status_reason"] = "retinal_site_not_observed"
    m.loc[still & (m.site == "gap") & (m.covers_TM7 == True), "status_reason"] = "retinal_site_gap"
    m.loc[still & (m.site == "nonK") & (m.covers_TM7 != True), "status_reason"] = "retinal_site_partial_TM7"
    m["status_reason_v14"] = m.reason_code.fillna("")

    assert (m.loc[u, "site"] != "K").all()
    mem = m.membership_status_v150.str.startswith("typeI_member")
    assert (m.loc[mem, "site"] == "K").all()

    # ---- homolog-based provisional inference for still-unresolved records (not a status change) ----
    seqs = read_fasta(a.faa)
    ref = m[(m.covers_TM7 == True) & (m.site.isin(["K", "nonK"]))]
    q = m[m.membership_status_v150 == "typeI_candidate_unresolved"]
    tmp = os.path.join(a.outdir, "_mm")
    os.makedirs(tmp, exist_ok=True)
    with open(f"{tmp}/q.faa", "w") as f:
        for s in q.source_acc:
            f.write(f">{s}\n{seqs[s]}\n")
    with open(f"{tmp}/r.faa", "w") as f:
        for s in ref.source_acc:
            f.write(f">{s}\n{seqs[s]}\n")
    subprocess.run(["mmseqs", "easy-search", f"{tmp}/q.faa", f"{tmp}/r.faa", f"{tmp}/hits.m8", f"{tmp}/tmp",
                    "-s", "7.5", "--threads", str(a.threads), "-e", "1e-10", "--max-seqs", "50",
                    "--format-output", "query,target,fident,qcov,tcov,evalue,bits"],
                   check=True, stdout=subprocess.DEVNULL)
    h = pd.read_csv(f"{tmp}/hits.m8", sep="\t", header=None,
                    names=["source_acc", "hit", "fident", "qcov", "tcov", "evalue", "bits"])
    h = h[h.source_acc != h.hit].sort_values(["source_acc", "bits"], ascending=[True, False])
    best = h.groupby("source_acc").head(1)
    best = best.merge(ref[["source_acc", "site", "ms210", "membership_status_v150"]]
                      .rename(columns={"source_acc": "hit", "site": "hit_site", "ms210": "hit_ms210",
                                       "membership_status_v150": "hit_status_v150"}), on="hit")
    best["provisional_inference"] = "no_close_fulllength_homolog"
    close = (best.fident >= 0.90) & (best.qcov >= 0.80)
    best.loc[close & (best.hit_site == "K"), "provisional_inference"] = "likely_member_if_completed"
    best.loc[close & (best.hit_site == "nonK"), "provisional_inference"] = "likely_retinal_site_lacking"
    best.to_csv(f"{a.outdir}/unresolved_homolog.tsv", sep="\t", index=False)
    shutil.rmtree(tmp, ignore_errors=True)

    m = m.merge(best[["source_acc", "hit", "fident", "provisional_inference"]]
                .rename(columns={"hit": "nearest_fulllength_homolog", "fident": "homolog_identity"}),
                on="source_acc", how="left")
    m.loc[(m.membership_status_v150 == "typeI_candidate_unresolved") & m.provisional_inference.isna(),
          "provisional_inference"] = "no_close_fulllength_homolog"

    sd = pd.DataFrame(STATUS_DEF, columns=["status", "status_group", "is_member", "is_candidate",
                                           "alias_v14", "definition"])
    sd["n_records_v150"] = sd.status.map(m.membership_status_v150.value_counts()).fillna(0).astype(int)
    sd.to_csv(f"{a.outdir}/status_definition.tsv", sep="\t", index=False)

    cols = ["source_acc", "membership_status_v150", "alias_v14", "boundary_subtype", "status_reason",
            "status_reason_v14", "membership_category", "membership_score", "architecture_class", "arch_route",
            "ms210", "covers_TM7", "nearest_fulllength_homolog", "homolog_identity", "provisional_inference"]
    m[cols].to_csv(f"{a.outdir}/membership_v150.tsv", sep="\t", index=False)

    uu = m[u].copy()
    uu["fate_v150"] = uu.membership_status_v150 + "|" + uu.status_reason.str.replace(r":.*", "", regex=True)
    res = (uu.groupby(["fate_v150", "provisional_inference"], dropna=False)
             .agg(n=("source_acc", "size"),
                  eukaryota=("tax_domain", lambda s: int((s == "Eukaryota").sum())),
                  bacteria=("tax_domain", lambda s: int((s == "Bacteria").sum())),
                  archaea=("tax_domain", lambda s: int((s == "Archaea").sum())),
                  unclassified=("tax_domain", lambda s: int(s.isna().sum())))
             .reset_index())
    res["fraction_of_v14_unresolved"] = (res.n / u.sum()).round(4)
    res.to_csv(f"{a.outdir}/resolvability.tsv", sep="\t", index=False)
    print(sd[["status", "n_records_v150"]].to_string(index=False))
    print(res.to_string(index=False))


if __name__ == "__main__":
    main()
