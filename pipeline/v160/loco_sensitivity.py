"""Addendum step 3: sensitivity of the E1 out-of-sample validation (LOO / LOSO / LOCO) to the E1 set.
Logic identical to stage1/conflicts_loco.py; only the E1 set (evaluation set AND consensus pool) changes.
  V0  baseline: all E1 records with a mappable exp_class
  V1  drop the 25 records whose function call rested only on the two lambda-max compilations
  V1b V1 + the 17 records resolved in the addendum (primary paper found or exact duplicate of a primary-cited sibling)
  V2a V1  + one record per exact-sequence cluster + engineered HcKCR1 mutants removed
  V2b V1b + one record per exact-sequence cluster + engineered HcKCR1 mutants removed  (expected post-addendum set)
"""
import os as _os
_REPO = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".."))
_W160 = _os.environ.get("MRDB_V160_WORK", _os.path.join(_REPO, "work", "v160_stage1"))  # Stage-1 scratch dir
import sqlite3, sys
import numpy as np, pandas as pd

sys.path.insert(0, _os.path.join(_W160, "stage1"))
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # conflicts_loco.py ships alongside
DB = _os.path.join(_REPO, "releases/v1.5.0/db/microrhododb_v1.5.0.sqlite")
W = _os.path.join(_W160, "addendum")
from statsmodels.stats.proportion import proportion_confint

PUMPS = {"proton_pump", "anion_pump", "sodium_pump"}
EXP2V14 = {"proton_pump_outward": "proton_pump", "proton_pump_inward": "proton_pump_inward", "anion_pump": "anion_pump",
           "sodium_pump": "sodium_pump", "cation_channel": "light_gated_channel", "anion_channel": "light_gated_channel",
           "potassium_channel": "light_gated_channel", "sensory_transducer": "sensory", "enzyme": "enzyme_rhodopsin",
           "photoreceptor_no_transport": "photoreceptor_unassigned"}
UNASSIGNED = {"unassigned", "unresolved", "insufficient_data", None, ""}
ENGINEERED = {"A0ABF7PQ84", "A0ABF7PQA2"}


def conflict(call, motif):
    if not isinstance(motif, str) or motif in UNASSIGNED or not isinstance(call, str) or call in UNASSIGNED:
        return 0
    if motif == call:
        return 0
    if motif == "sensory_like":
        return int(call in PUMPS)
    return 1


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
red = pd.read_sql("select source_acc, exact_nr_cluster from redundancy", c)
fe = fe.merge(rc, on="source_acc", how="left").merge(red, on="source_acc", how="left")
E1 = fe[(fe.evidence_level == "E1") & fe.exp_class.isin(EXP2V14)].copy()
E1["exp"] = E1.exp_class.map(EXP2V14)
E1["v14"] = E1.func_class_v14
E1["conf"] = [conflict(a, b) for a, b in zip(E1.v14, E1.motif_class)]
E1["call_legacy"] = E1.v14
E1["call_downgrade"] = np.where(E1.conf == 1, "unassigned", E1.v14)
E1["call_motif"] = E1.motif_class

targets = set(pd.read_csv(f"{W}/targets.tsv", sep="\t").source_acc)
compilation_only = targets - {"A0ABF7PQ05"}  # CryoR2 had a primary link already
add = pd.read_csv(f"{W}/curation_v160_addendum_citations.tsv", sep="\t", dtype=str)
resolved = set(add[add.group_id.isin(["ADD-A_primary_found", "ADD-B_duplicate_inherit"])].source_acc) & compilation_only
assert len(compilation_only) == 25 and len(resolved) == 17, (len(compilation_only), len(resolved))


def dedup(df):
    # one record per exact-sequence cluster; prefer records that were never compilation-only, then accession order
    d = df.assign(_pri=df.source_acc.isin(compilation_only).astype(int)).sort_values(["exact_nr_cluster", "_pri", "source_acc"])
    return d.drop_duplicates("exact_nr_cluster").drop(columns="_pri")


V = {}
V["V0_baseline"] = E1
V["V1_no_compilation_only"] = E1[~E1.source_acc.isin(compilation_only)]
V["V1b_plus_resolved"] = E1[~E1.source_acc.isin(compilation_only - resolved)]
V["V2a_V1_dedup_noeng"] = dedup(V["V1_no_compilation_only"][~V["V1_no_compilation_only"].source_acc.isin(ENGINEERED)])
V["V2b_V1b_dedup_noeng"] = dedup(V["V1b_plus_resolved"][~V["V1b_plus_resolved"].source_acc.isin(ENGINEERED)])


def evaluate(e1):
    def consensus(group_ids, exclude):
        pool = e1[(~e1.source_acc.isin(exclude)) & (e1.subclade_id.isin(group_ids) | e1.rc_clade.isin(group_ids))]
        u = pool.exp.unique()
        return u[0] if len(u) == 1 else None
    e1 = e1.copy()
    tiers = {"LOO": [], "LOSO": [], "LOCO": []}
    for r in e1.itertuples():
        grp = r.clade_function_source if isinstance(r.clade_function_source, str) else r.rc_clade
        for mode in tiers:
            if mode == "LOO":
                excl = {r.source_acc}
            elif mode == "LOSO":
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
    for m in tiers:
        e1[f"sim_tier_{m}"] = tiers[m]
    rows = []
    for subset_name, mode, tier in [("all_E1", None, None), ("sim_E3", "LOO", "E3"), ("sim_E4", "LOO", "E4"),
                                    ("sim_E3", "LOSO", "E3"), ("sim_E4", "LOSO", "E4"),
                                    ("sim_E3", "LOCO", "E3"), ("sim_E4", "LOCO", "E4")]:
        s = e1 if mode is None else e1[e1[f"sim_tier_{mode}"] == tier]
        for pol in ["legacy", "downgrade", "motif"]:
            ok = pd.Series([agree(cv, ex) for cv, ex in zip(s[f"call_{pol}"], s.exp)], dtype=float)
            na = int(ok.notna().sum()); k = int(ok.fillna(0).sum()); n = len(s)
            plo, phi = wilson(k, na); clo, chi = wilson(na, n)
            rows.append(dict(subset=subset_name, holdout=mode or "none", policy=pol, n=n, n_assigned=na,
                             coverage=na / n if n else np.nan, cov_lo=clo, cov_hi=chi, n_correct=k,
                             precision=k / na if na else np.nan, prec_lo=plo, prec_hi=phi))
    return pd.DataFrame(rows), e1


res, recs = [], []
for name, df in V.items():
    r, e = evaluate(df)
    r.insert(0, "variant", name); r.insert(1, "n_E1", len(df)); r.insert(2, "n_clades", df.rc_clade.nunique())
    res.append(r); recs.append(e.assign(variant=name)[["variant", "source_acc", "exp", "v14", "motif_class", "rc_clade",
                                                       "sim_tier_LOO", "sim_tier_LOSO", "sim_tier_LOCO"]])
res = pd.concat(res); res.to_csv(f"{W}/loco_sensitivity_v160.tsv", sep="\t", index=False)
pd.concat(recs).to_csv(f"{W}/loco_sensitivity_records_v160.tsv", sep="\t", index=False)

# baseline reproduces stage 1
base = pd.read_csv(_os.path.join(_W160, "stage1/out/loco_validation.tsv"), sep="\t")
b0 = res[res.variant == "V0_baseline"].reset_index(drop=True)
assert np.allclose(b0[["n", "n_assigned", "n_correct"]].values, base[["n", "n_assigned", "n_correct"]].values), "V0 != stage-1 output"
print("V0 reproduces stage-1 loco_validation.tsv exactly")
pd.set_option("display.width", 220)
show = res[(res.subset == "all_E1") | (res.holdout == "LOCO")]
print(show.assign(prec=lambda d: d.apply(lambda r: f"{r.n_correct}/{r.n_assigned} = {r.precision:.3f} [{r.prec_lo:.2f}-{r.prec_hi:.2f}]", axis=1),
                  cov=lambda d: d.apply(lambda r: f"{r.n_assigned}/{r.n} = {r.coverage:.2f}", axis=1))
      [["variant", "n_E1", "n_clades", "subset", "holdout", "policy", "cov", "prec"]].to_string(index=False))
