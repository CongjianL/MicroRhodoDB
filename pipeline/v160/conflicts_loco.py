"""Stage 1 / R-F1 + R-V2: function-call conflict flag, downgrade proposals and out-of-sample E1 evaluation.

Conflict rule (compatibility-aware, primary):
  motif missing/unassigned            -> not testable (no conflict)
  motif == call                       -> agree
  motif sensory_like                  -> conflicts only with a pump call (proton/anion/sodium pump);
                                         compatible with sensory, sensory_like, channel, enzyme, inward pump,
                                         photoreceptor_unassigned (the motif just says "no pump motif")
  motif is a pump class               -> conflicts with any different call
Exact rule (secondary, reported): call != motif_class whenever motif is defined.

Policy: E3/E4 with conflict -> E5 'unassigned' (basis 'conflict: v14=<X>; motif=<Y>');
        E2 and curated_rule conflicts -> flagged only.
E1 evaluation: three call policies (legacy v1.4 label, flag-and-downgrade, motif only) on the E1 records,
plus simulated tier (E3 vs E4) with the record (LOO) or its whole level-1 clade (LOCO) hidden when
computing the clade-function consensus.
"""
import os as _os
_REPO = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
_W160 = _os.environ.get("MRDB_V160_WORK", _os.path.join(_REPO, "work", "v160_stage1"))  # Stage-1 scratch dir
import sqlite3, os
import numpy as np, pandas as pd
from statsmodels.stats.proportion import proportion_confint

DB = _os.path.join(_REPO, "releases/v1.5.0/db/microrhododb_v1.5.0.sqlite")
OUT = _os.path.join(_W160, "stage1/out"); os.makedirs(OUT, exist_ok=True)
PUMPS = {"proton_pump", "anion_pump", "sodium_pump"}
EXP2V14 = {"proton_pump_outward": "proton_pump", "proton_pump_inward": "proton_pump_inward", "anion_pump": "anion_pump",
           "sodium_pump": "sodium_pump", "cation_channel": "light_gated_channel", "anion_channel": "light_gated_channel",
           "potassium_channel": "light_gated_channel", "sensory_transducer": "sensory", "enzyme": "enzyme_rhodopsin",
           "photoreceptor_no_transport": "photoreceptor_unassigned"}
UNASSIGNED = {"unassigned", "unresolved", "insufficient_data", None, ""}


def conflict(call, motif):
    if not isinstance(motif, str) or motif in UNASSIGNED or not isinstance(call, str) or call in UNASSIGNED:
        return 0
    if motif == call:
        return 0
    if motif == "sensory_like":
        return int(call in PUMPS)
    if call == "sensory_like" and motif in PUMPS:
        return 1
    return 1


def conflict_exact(call, motif):
    if not isinstance(motif, str) or motif in UNASSIGNED or not isinstance(call, str) or call in UNASSIGNED:
        return 0
    return int(call != motif)


def agree(call, exp):
    if not isinstance(call, str) or call in UNASSIGNED:
        return np.nan
    if exp == "sensory":
        return float(call in {"sensory", "sensory_like"})
    return float(call == exp)


def wilson(k, n):
    return proportion_confint(k, n, method="wilson") if n else (np.nan, np.nan)


c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
fe = pd.read_sql("select * from function_evidence", c)
rc = pd.read_sql("select source_acc, clade_id as rc_clade, subclade_id, clade_function_source from record_clade", c)
prot = pd.read_sql("select source_acc, mrdb_acc, protein_name, organism from protein", c)
fe = fe.merge(rc, on="source_acc", how="left").merge(prot, on="source_acc", how="left")
fe["call_conflict"] = [conflict(a, b) for a, b in zip(fe.func_class, fe.motif_class)]
fe["call_conflict_exact"] = [conflict_exact(a, b) for a, b in zip(fe.func_class, fe.motif_class)]
fe["basis_type"] = fe.basis.str.split(":").str[0]

# ---- summary of conflicts by tier/basis ----
summ = (fe.groupby(["evidence_level", "basis_type"])
          .agg(n=("source_acc", "size"), conflict=("call_conflict", "sum"), conflict_exact=("call_conflict_exact", "sum"))
          .reset_index())
summ.to_csv(f"{OUT}/conflict_summary_by_tier.tsv", sep="\t", index=False)
pairs = (fe[fe.call_conflict == 1].groupby(["evidence_level", "func_class", "motif_class"]).size()
           .rename("n").reset_index().sort_values("n", ascending=False))
pairs.to_csv(f"{OUT}/conflict_pairs.tsv", sep="\t", index=False)

# ---- proposals ----
prop = fe[(fe.call_conflict == 1) & fe.evidence_level.isin(["E2", "E3", "E4"])].copy()
down = prop.evidence_level.isin(["E3", "E4"]) & (prop.basis_type != "curated_rule")
prop["action"] = np.where(down, "downgrade_to_E5", "flag_only")
prop["group"] = np.where(down, "F1_downgrade_" + prop.evidence_level, "F1_flag_" + prop.evidence_level + "_" + prop.basis_type)
prop["new_evidence_level"] = np.where(down, "E5", prop.evidence_level)
prop["new_func_class"] = np.where(down, "unassigned", prop.func_class)
prop["new_basis"] = np.where(down, "conflict: v14=" + prop.func_class + "; motif=" + prop.motif_class.astype(str), prop.basis)
prop["in_fungal_clade_MR_CLD3_017"] = (prop.clade_id == "MR_CLD3_017").astype(int)
cols = ["group", "action", "source_acc", "mrdb_acc", "protein_name", "organism", "evidence_level", "basis", "func_class",
        "helixC_motif", "motif_class", "clade_id", "clade_function", "new_evidence_level", "new_func_class", "new_basis",
        "in_fungal_clade_MR_CLD3_017"]
prop[cols].sort_values(["group", "clade_id", "source_acc"]).to_csv(f"{OUT}/proposals_F1_conflicts.tsv", sep="\t", index=False)
fe[["source_acc", "call_conflict", "call_conflict_exact"]].to_csv(f"{OUT}/call_conflict_all.tsv", sep="\t", index=False)

# ---- E1 evaluation ----
e1 = fe[(fe.evidence_level == "E1") & fe.exp_class.isin(EXP2V14)].copy()
e1["exp"] = e1.exp_class.map(EXP2V14)
e1["v14"] = e1.func_class_v14
e1["conf"] = [conflict(a, b) for a, b in zip(e1.v14, e1.motif_class)]
e1["call_legacy"] = e1.v14
e1["call_downgrade"] = np.where(e1.conf == 1, "unassigned", e1.v14)
e1["call_motif"] = e1.motif_class


def consensus(group_ids, exclude):
    """E1 class consensus among E1 records in the given groups (subclade or clade), excluding a set of accessions."""
    pool = e1[(~e1.source_acc.isin(exclude)) & (e1.subclade_id.isin(group_ids) | e1.rc_clade.isin(group_ids))]
    u = pool.exp.unique()
    return u[0] if len(u) == 1 else None


tiers = {"LOO": [], "LOSO": [], "LOCO": []}
for r in e1.itertuples():
    grp = r.clade_function_source if isinstance(r.clade_function_source, str) else r.rc_clade
    for mode in tiers:
        if mode == "LOO":
            excl = {r.source_acc}
        elif mode == "LOSO":  # hide every E1 record in the same subclade (fallback: same clade_function_source group)
            key = r.subclade_id if isinstance(r.subclade_id, str) and r.subclade_id else grp
            excl = {r.source_acc} | set(e1[(e1.subclade_id == key) | (e1.clade_function_source == key)].source_acc)
        else:
            excl = set(e1[e1.rc_clade == r.rc_clade].source_acc) if isinstance(r.rc_clade, str) else {r.source_acc}
        cf = consensus([grp, r.rc_clade], excl) if isinstance(grp, str) else None
        v = r.v14
        if not isinstance(v, str) or v in UNASSIGNED:
            tiers[mode].append("E5")
        elif cf is not None and agree(v, cf) == 1:
            tiers[mode].append("E3")
        else:
            tiers[mode].append("E4")
e1["sim_tier_LOO"] = tiers["LOO"]; e1["sim_tier_LOSO"] = tiers["LOSO"]; e1["sim_tier_LOCO"] = tiers["LOCO"]
e1[["source_acc", "mrdb_acc", "protein_name", "exp_class", "exp", "v14", "helixC_motif", "motif_class", "conf", "rc_clade",
    "subclade_id", "clade_function_source", "sim_tier_LOO", "sim_tier_LOSO", "sim_tier_LOCO", "call_legacy", "call_downgrade", "call_motif"]
   ].to_csv(f"{OUT}/loco_e1_records.tsv", sep="\t", index=False)

rows = []
for subset_name, mode, tier in [("all_E1", None, None), ("sim_E3", "LOO", "E3"), ("sim_E4", "LOO", "E4"),
                                ("sim_E3", "LOSO", "E3"), ("sim_E4", "LOSO", "E4"),
                                ("sim_E3", "LOCO", "E3"), ("sim_E4", "LOCO", "E4")]:
    s = e1 if mode is None else e1[e1[f"sim_tier_{mode}"] == tier]
    for pol in ["legacy", "downgrade", "motif"]:
        ok = [agree(cv, ex) for cv, ex in zip(s[f"call_{pol}"], s.exp)]
        ok = pd.Series(ok, dtype=float)
        na = int(ok.notna().sum()); k = int(ok.fillna(0).sum()); n = len(s)
        plo, phi = wilson(k, na); clo, chi = wilson(na, n)
        rows.append(dict(subset=subset_name, holdout=mode or "none", policy=pol, n=n, n_assigned=na, coverage=na / n if n else np.nan,
                         cov_lo=clo, cov_hi=chi, n_correct=k, precision=k / na if na else np.nan, prec_lo=plo, prec_hi=phi,
                         ci_method="wilson"))
loco = pd.DataFrame(rows)
loco.to_csv(f"{OUT}/loco_validation.tsv", sep="\t", index=False)
pd.set_option("display.width", 200)
print(summ.to_string()); print(pairs.head(15).to_string())
print(prop.group.value_counts().to_string()); print("fungal in downgrade:", prop[down].in_fungal_clade_MR_CLD3_017.sum())
print(loco.round(3).to_string())
