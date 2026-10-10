#!/usr/bin/env python
"""WP5 - evidence ladder, publication verification integration, motif-call benchmark, spectral audit.

Inputs: v1.4 DB, membership_v150.tsv (WP2), characterized_set.tsv, pubverify outputs, all-sequence FASTA,
optional clade table (source_acc, clade_id, clade_name) from WP4 and optional function override table.
Outputs (outdir):
  characterized_v150.tsv      strict E1 set (Tier A + UniProt ECO:0000269 + full-text + published lambda-max tables)
  characterized_excluded.tsv  literature-linked records rejected as E1 (environmental surveys, abstract-only)
  publication_v150.tsv        v1.4 publications with Crossref-verified metadata
  assertion_link_v150.tsv     per-link verdicts
  motif_benchmark.tsv         v1.4 motif/function call vs experimental class, per E1 protein
  motif_benchmark_summary.tsv accuracy/coverage with Wilson CIs; motif_confusion.tsv
  spectral_audit.tsv          measured lambda-max vs v1.4 spectral prediction
  function_evidence_v150.tsv  per-record evidence level E1-E5 and v1.5 function class
"""
import argparse, os, sqlite3, subprocess
import numpy as np, pandas as pd
import hashlib
from statsmodels.stats.proportion import proportion_confint

EXP2V14 = {"proton_pump_outward": "proton_pump", "proton_pump_inward": "proton_pump_inward",
           "anion_pump": "anion_pump", "sodium_pump": "sodium_pump", "cation_channel": "light_gated_channel",
           "anion_channel": "light_gated_channel", "potassium_channel": "light_gated_channel",
           "sensory_transducer": "sensory", "enzyme": "enzyme_rhodopsin",
           # v1.5.0 curator class: characterised photoreceptor with no detectable ion transport (CryoR2 trio)
           "photoreceptor_no_transport": "photoreceptor_unassigned"}
# curator mapping for records whose class came only from a published lambda-max table label
LABEL2EXP = {"GtACR1": "anion_channel", "GtACR2": "anion_channel", "EgClR": "anion_pump", "AnClR": "anion_pump",
             "PoClR2": "anion_pump", "FR": "anion_pump", "JsNaR": "sodium_pump", "BcNaR": "sodium_pump",
             "GlNaR": "sodium_pump", "NdR2": "sodium_pump", "NdR1": "proton_pump_outward",
             "NpSRII": "sensory_transducer", "SrSRI": "sensory_transducer", "ASR": "sensory_transducer",
             "HmBRI": "proton_pump_outward", "HmBRII": "proton_pump_outward", "HtdR": "proton_pump_outward",
             "BR": "proton_pump_outward", "HwBR": "proton_pump_outward", "HxAR": "proton_pump_outward",
             "KrActR": "proton_pump_outward", "OR1": "proton_pump_outward", "DTG_PvR": "proton_pump_outward",
             "DTG_PaR": "proton_pump_outward", "DChR1": "cation_channel"}
V14_SENSORY = {"sensory", "sensory_like"}


def wilson(k, n):
    return proportion_confint(k, n, method="wilson") if n else (np.nan, np.nan)


def read_fasta(p):
    seqs, acc = {}, None
    for line in open(p):
        if line.startswith(">"):
            acc = line[1:].split()[0]; seqs[acc] = []
        elif acc:
            seqs[acc].append(line.strip())
    return {k: "".join(v) for k, v in seqs.items()}


def agree(v14, exp):
    if exp == "proton_pump_inward":
        return v14 == "proton_pump_inward"
    if exp == "sensory":
        return v14 in V14_SENSORY
    return v14 == exp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--membership", required=True)
    ap.add_argument("--charset", required=True)
    ap.add_argument("--pubverify", required=True)
    ap.add_argument("--faa", required=True)
    ap.add_argument("--clades", default=None)
    ap.add_argument("--func_override", default=None, help="tsv: source_acc, func_class_v150, rule_id, note")
    ap.add_argument("--charset_override", default=None, help="tsv: source_acc, exp_class, reason")
    ap.add_argument("--decisions", default=None, help="signed curator decisions (curation/spotcheck_decisions_v150.tsv)")
    ap.add_argument("--pub_replacements", default=None, help="curation/publication_replacements_v150.tsv")
    ap.add_argument("--link_replacements", default=None, help="curation/assertion_link_replacements_v150.tsv")
    ap.add_argument("--field_corrections", default=None, help="curation/field_corrections_v150.tsv")
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    mem = pd.read_csv(a.membership, sep="\t")
    f14 = pd.read_sql("select fa.source_acc, fa.func_class, fa.rule_id, fa.confidence from function_assignment fa "
                      "where fa.is_active=1", con)
    # motif and spectral fields are in the v_active_function view / legacy function table
    fv = pd.read_sql("select * from function", con)
    keep = [c for c in ["source_acc", "helixC_motif", "motif_class", "res_105", "spectral_class",
                        "lambda_max_pred_nm", "func_class", "func_evidence"] if c in fv.columns]
    fv = fv[keep].rename(columns={"func_class": "func_class_v14"})

    # ---------------- strict E1 set ----------------
    cs = pd.read_csv(a.charset, sep="\t")
    strict = (cs.evidence_basis.str.contains("full_text|uniprot", na=False) | cs.mapping_identity.notna()
              | cs.in_tierA.astype(bool))
    cs["exp_class"] = cs.exp_function_class
    lab = cs.exp_class.eq("other") & cs.protein_label.isin(LABEL2EXP)
    cs.loc[lab, "exp_class"] = cs.loc[lab, "protein_label"].map(LABEL2EXP)
    cs["exp_class_basis"] = np.where(lab, "curator_label_mapping", "source_record")
    if a.charset_override:
        co = pd.read_csv(a.charset_override, sep="\t").set_index("source_acc")
        hit = cs.source_acc.isin(co.index)
        cs.loc[hit, "exp_class"] = cs.loc[hit, "source_acc"].map(co.exp_class)
        cs.loc[hit, "exp_class_basis"] = "curator_override:" + cs.loc[hit, "source_acc"].map(co.reason)
    # ---------------- curator spot-check decisions (v1.5.0 sign-off) ----------------
    lv = pd.read_csv(f"{a.pubverify}/assertion_link_verification.tsv", sep="\t")
    if a.decisions:
        import curation_v150 as cur
        dec = cur.read_decisions(a.decisions)
        lv = cur.apply_link_decisions(lv, dec, pd.read_csv(a.link_replacements, sep="\t"))
        corr = pd.read_csv(a.field_corrections, sep="\t", dtype=str).fillna("")
        cs, ncorr = cur.apply_field_corrections(cs, corr, "characterized_protein", {"source_acc": "source_acc"})
        print("characterized_protein field corrections applied:", ncorr)
    e1 = cs[strict].copy()
    excl = cs[~strict].copy()
    excl["exclusion_reason"] = "abstract_only_literature_link (typically environmental diversity survey; " \
                               "no protein-level assay)"
    e1 = e1.merge(mem[["source_acc", "membership_status_v150", "ms210"]], on="source_acc", how="left")
    e1["conflict"] = ""
    e1.loc[~e1.membership_status_v150.fillna("").str.startswith("typeI_"), "conflict"] = \
        "characterised_but_not_typeI_status (check accession mapping / retinal site)"
    e1.loc[e1.exp_class.eq("other"), "conflict"] += ";function_class_unmapped"
    if a.decisions:
        e1["e1_eligible"], e1["e1_exclusion_reason"] = cur.e1_eligibility(e1, lv, dec)
        ann = dec.loc[dec.decision == "annotate_only", "source_acc"]
        e1.loc[e1.source_acc.isin(ann), "conflict"] += ";accession_mapping_conflict"
        e1["conflict"] = e1.conflict.str.lstrip(";")
        print("E1-ineligible after curation:", e1.loc[~e1.e1_eligible, ["source_acc", "e1_exclusion_reason"]].to_string())
    else:
        e1["e1_eligible"], e1["e1_exclusion_reason"] = True, ""
    e1.to_csv(f"{a.outdir}/characterized_v150.tsv", sep="\t", index=False)
    excl.to_csv(f"{a.outdir}/characterized_excluded.tsv", sep="\t", index=False)

    # ---------------- publications ----------------
    pub = pd.read_sql("select * from publication", con)
    pv = pd.read_csv(f"{a.pubverify}/publication_verification.tsv", sep="\t")
    pub = pub.merge(pv[["publication_id", "doi_resolves", "doi_corrected", "crossref_title", "crossref_journal",
                        "crossref_year", "crossref_first_author", "first_author_match", "year_match",
                        "verdict_summary", "notes"]], on="publication_id", how="left")
    pub["title_v150"] = pub.title.where(pub.title.notna() & (pub.title.astype(str) != ""), pub.crossref_title)
    pub["journal_v150"] = pub.crossref_journal.fillna(pub.journal)
    pub["year_v150"] = pub.crossref_year.fillna(pub.year)
    pub["ingestion_v150"] = np.where(pub.doi_resolves.astype(str) == "True", "agent_verified_crossref",
                                     "agent_unverified")
    if a.decisions:
        pub = cur.add_publications(pub, pd.read_csv(a.pub_replacements, sep="\t"))
    pub.to_csv(f"{a.outdir}/publication_v150.tsv", sep="\t", index=False)
    lv.to_csv(f"{a.outdir}/assertion_link_v150.tsv", sep="\t", index=False)

    # ---------------- motif benchmark ----------------
    b = e1[e1.exp_class.isin(EXP2V14) & e1.e1_eligible].merge(fv, on="source_acc", how="left")
    b["exp_v14vocab"] = b.exp_class.map(EXP2V14)
    b["motif_call"] = b.motif_class.fillna("unassigned")
    b["func_call"] = b.func_class_v14.fillna("unassigned")
    for c in ["motif_call", "func_call"]:
        b[f"{c}_assigned"] = ~b[c].isin(["unassigned", "insufficient_data"])
        b[f"{c}_correct"] = [agree(v, e) for v, e in zip(b[c], b.exp_v14vocab)]
    b.to_csv(f"{a.outdir}/motif_benchmark.tsv", sep="\t", index=False)
    rows = []
    for c in ["motif_call", "func_call"]:
        for grp, g in [("all", b)] + [(k, x) for k, x in b.groupby("exp_v14vocab")]:
            n = len(g); na = int(g[f"{c}_assigned"].sum()); k = int((g[f"{c}_assigned"] & g[f"{c}_correct"]).sum())
            lo1, hi1 = wilson(na, n); lo2, hi2 = wilson(k, na)
            rows.append(dict(call=c, exp_class=grp, n=n, n_assigned=na, coverage=na / n if n else np.nan,
                             cov_lo=lo1, cov_hi=hi1, n_correct=k, precision=k / na if na else np.nan,
                             prec_lo=lo2, prec_hi=hi2, ci_method="wilson"))
    pd.DataFrame(rows).to_csv(f"{a.outdir}/motif_benchmark_summary.tsv", sep="\t", index=False)
    pd.crosstab(b.exp_v14vocab, b.func_call).to_csv(f"{a.outdir}/motif_confusion.tsv", sep="\t")

    # ---------------- spectral audit ----------------
    sp = e1[e1.lambda_max_nm.notna() & e1.e1_eligible].merge(fv, on="source_acc", how="left")
    sp["measured_class"] = pd.cut(sp.lambda_max_nm, [0, 505, 2000], labels=["blue(<505)", "green(>=505)"])
    sp["prediction_correct"] = np.where(sp.spectral_class.isin(["green_predicted", "blue_predicted"]),
                                        ((sp.spectral_class == "green_predicted") & (sp.lambda_max_nm >= 505)) |
                                        ((sp.spectral_class == "blue_predicted") & (sp.lambda_max_nm < 505)), np.nan)
    sp.to_csv(f"{a.outdir}/spectral_audit.tsv", sep="\t", index=False)

    # ---------------- evidence ladder ----------------
    seqs = read_fasta(a.faa)
    ids = [s for s in mem.source_acc if s in seqs]
    e1ok = e1[e1.exp_class.isin(EXP2V14) & e1.e1_eligible]
    tmp = f"{a.outdir}/_mm"; os.makedirs(tmp, exist_ok=True)
    with open(f"{tmp}/q.faa", "w") as fo:
        for s in ids:
            fo.write(f">{s}\n{seqs[s]}\n")
    with open(f"{tmp}/r.faa", "w") as fo:
        for s in e1ok.source_acc:
            if s in seqs:
                fo.write(f">{s}\n{seqs[s]}\n")
    # cache keyed on the E1 reference set: re-search whenever the reference FASTA changes
    rhash = hashlib.sha256(open(f"{tmp}/r.faa", "rb").read()).hexdigest()
    stale = not os.path.exists(f"{tmp}/r.sha256") or open(f"{tmp}/r.sha256").read().strip() != rhash
    if stale or not os.path.exists(f"{tmp}/h.m8"):
        subprocess.run(["mmseqs", "easy-search", f"{tmp}/q.faa", f"{tmp}/r.faa", f"{tmp}/h.m8", f"{tmp}/tmp",
                        "-s", "7.5", "--min-seq-id", "0.9", "-c", "0.8", "--cov-mode", "0", "--threads", "8",
                        "--format-output", "query,target,fident,qcov,tcov,bits"], check=True, stdout=subprocess.DEVNULL)
        open(f"{tmp}/r.sha256", "w").write(rhash)
    h = pd.read_csv(f"{tmp}/h.m8", sep="\t", header=None, names=["q", "t", "fident", "qcov", "tcov", "bits"])
    h = h[h.q != h.t].merge(e1ok[["source_acc", "exp_class"]].rename(columns={"source_acc": "t"}), on="t")
    clades = pd.read_csv(a.clades, sep="\t") if a.clades else None
    if clades is not None:
        cm = clades.set_index("source_acc").clade_id.to_dict()
        h = h[[cm.get(q) is not None and cm.get(q) == cm.get(t) for q, t in zip(h.q, h.t)]]
    h = h.sort_values("bits", ascending=False)
    # consistent transfer only: all qualifying E1 hits must agree on class
    agg = h.groupby("q").agg(e2_ref=("t", "first"), e2_identity=("fident", "first"),
                             e2_classes=("exp_class", lambda s: ",".join(sorted(set(s))))).reset_index()
    agg = agg[~agg.e2_classes.str.contains(",")]
    ev = mem[["source_acc", "membership_status_v150"]].merge(f14, on="source_acc", how="left")
    ev = ev.merge(fv[["source_acc", "helixC_motif", "motif_class", "func_evidence"]], on="source_acc", how="left")
    ev = ev.merge(e1ok[["source_acc", "exp_class"]], on="source_acc", how="left")
    ev = ev.merge(agg.rename(columns={"q": "source_acc"}), on="source_acc", how="left")
    if a.func_override:
        ov = pd.read_csv(a.func_override, sep="\t")
        ev = ev.merge(ov[["source_acc", "func_class_v150", "rule_id"]].rename(
            columns={"func_class_v150": "override_class", "rule_id": "override_rule"}), on="source_acc", how="left")
    else:
        ev["override_class"] = np.nan; ev["override_rule"] = np.nan
    if clades is not None:
        ev = ev.merge(clades[["source_acc", "clade_id", "clade_function"]], on="source_acc", how="left")
    else:
        ev["clade_id"] = np.nan; ev["clade_function"] = np.nan
    is_mem = ev.membership_status_v150.fillna("").str.startswith("typeI_member")
    v14 = ev.override_class.fillna(ev.func_class)
    lvl, cls, basis = [], [], []
    for i, r in ev.iterrows():
        f = v14[i]
        if isinstance(r.exp_class, str):
            lvl.append("E1"); cls.append(EXP2V14[r.exp_class]); basis.append("experimental:this_protein")
        elif isinstance(r.e2_classes, str) and is_mem[i]:
            lvl.append("E2"); cls.append(EXP2V14[r.e2_classes])
            basis.append(f"experimental_ortholog:{r.e2_ref}@{r.e2_identity:.2f}" +
                         (":same_clade" if clades is not None else ""))
        elif is_mem[i] and isinstance(f, str) and f not in ("unassigned", "insufficient_data"):
            fc = r.clade_function if isinstance(r.clade_function, str) else None
            if fc is not None and agree(f, fc):
                lvl.append("E3"); basis.append(f"motif+phylogeny:{r.clade_id}")
            elif isinstance(r.override_rule, str):
                lvl.append("E4"); basis.append(f"curated_rule:{r.override_rule}:{r.helixC_motif}")
            else:
                lvl.append("E4"); basis.append(f"motif_only:{r.helixC_motif}")
            cls.append(f)
        else:
            lvl.append("E5"); cls.append("unresolved"); basis.append("insufficient")
    ev["evidence_level"] = lvl; ev["func_class_v150"] = cls; ev["function_basis_v150"] = basis
    ev.to_csv(f"{a.outdir}/function_evidence_v150.tsv", sep="\t", index=False)
    print(ev.groupby(["membership_status_v150", "evidence_level"]).size().unstack(fill_value=0))
    print(pd.read_csv(f"{a.outdir}/motif_benchmark_summary.tsv", sep="\t").round(3).to_string())
    print("spectral audit n=", len(sp), "with prediction", sp.prediction_correct.notna().sum(),
          "correct", np.nansum(sp.prediction_correct.astype(float)))


if __name__ == "__main__":
    main()
