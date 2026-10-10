"""Shared rules for the MicroRhodoDB v1.6.0 build (conflict rule, agreement, E-ladder, LOCO evaluation).

These functions are the single source of truth for v1.6.0; build_v160.py, loco_final_v160.py and the tests
import them so the rule documented in docs/DATA_MODEL.md is the rule that was executed.
"""
import os
import subprocess
import hashlib
import numpy as np
import pandas as pd
from statsmodels.stats.proportion import proportion_confint

PUMPS = {"proton_pump", "anion_pump", "sodium_pump"}
EXP2V14 = {"proton_pump_outward": "proton_pump", "proton_pump_inward": "proton_pump_inward", "anion_pump": "anion_pump",
           "sodium_pump": "sodium_pump", "cation_channel": "light_gated_channel", "anion_channel": "light_gated_channel",
           "potassium_channel": "light_gated_channel", "sensory_transducer": "sensory", "enzyme": "enzyme_rhodopsin",
           "photoreceptor_no_transport": "photoreceptor_unassigned"}
UNASSIGNED = {"unassigned", "unresolved", "insufficient_data", None, ""}
V14_SENSORY = {"sensory", "sensory_like"}
EXP2ASSERTION = {"proton_pump_outward": "light-driven outward proton pump",
                 "proton_pump_inward": "light-driven inward proton pump",
                 "anion_pump": "light-driven inward anion (chloride) pump",
                 "sodium_pump": "light-driven outward sodium pump",
                 "cation_channel": "light-gated cation channel",
                 "anion_channel": "light-gated anion channel",
                 "potassium_channel": "light-gated potassium channel",
                 "sensory_transducer": "sensory phototaxis receptor",
                 "enzyme": "light-regulated enzyme rhodopsin",
                 "photoreceptor_no_transport": "photoreceptor without detectable ion transport"}
# class-specific keywords used to decide whether a curator-approved link is verifiable in the retrieved abstract
EXP2KEYWORDS = {"proton_pump_outward": ["proton pump", "proton-pump", "pumps proton", "proton transport", "h+ pump",
                                        "h(+) pump", "proton translocation", "outward proton", "pumping"],
                "proton_pump_inward": ["inward proton", "inward h", "proton"],
                "anion_pump": ["chloride pump", "anion pump", "anion-pump", "chloride ion pump", "cl- pump",
                               "cl(-) pump", "halorhodopsin", "chloride transport", "anion transport"],
                "sodium_pump": ["sodium pump", "na+ pump", "na(+) pump", "sodium ion pump", "na(+) transport", "sodium"],
                "cation_channel": ["cation channel", "channelrhodopsin", "channel"],
                "anion_channel": ["anion channel", "channel"],
                "potassium_channel": ["potassium", "k+", "k(+)", "kalium"],
                "sensory_transducer": ["sensory rhodopsin", "phototaxis", "transducer", "photosensor", "sensory"],
                "enzyme": ["cyclase", "phosphodiesterase", "kinase", "enzyme"],
                "photoreceptor_no_transport": ["does not pump", "no ion transport", "not pump", "no transport",
                                               "photoreceptor", "sensory", "photocycle"]}


def is_unassigned(x):
    return (not isinstance(x, str)) or x in UNASSIGNED


def conflict(call, motif):
    """Compatibility-aware conflict rule (primary).
    motif missing/unassigned -> not testable (0); motif == call -> 0;
    motif sensory_like -> conflicts only with a pump call; motif is a pump class -> conflicts with any other call."""
    if is_unassigned(motif) or is_unassigned(call):
        return 0
    if motif == call:
        return 0
    if motif == "sensory_like":
        return int(call in PUMPS)
    return 1


def conflict_exact(call, motif):
    """Exact rule (secondary, reported): call != motif whenever both are assigned."""
    if is_unassigned(motif) or is_unassigned(call):
        return 0
    return int(call != motif)


def motif_testable(motif):
    return not is_unassigned(motif)


def agree_v14(v14, exp_v14vocab):
    """wp5 agreement used for E3 clade consensus (v1.5 rule, unchanged)."""
    if exp_v14vocab == "proton_pump_inward":
        return v14 == "proton_pump_inward"
    if exp_v14vocab == "sensory":
        return v14 in V14_SENSORY
    return v14 == exp_v14vocab


def agree_eval(call, exp):
    """Agreement used in the LOCO evaluation (NaN when the call is unassigned)."""
    if is_unassigned(call):
        return np.nan
    if exp == "sensory":
        return float(call in V14_SENSORY)
    return float(call == exp)


def wilson(k, n):
    if not n:
        return (np.nan, np.nan)
    lo, hi = proportion_confint(int(k), int(n), method="wilson")
    return float(lo), float(hi)


def norm_clade(x):
    return x if isinstance(x, str) and x != "" else None


def e2_search(seqs, query_ids, ref_ids, workdir, mmseqs="mmseqs", threads=8):
    """MMseqs2 easy-search of all records against the E1 reference set (v1.5 parameters, unchanged).
    Returns the hit table (query, target, fident, qcov, tcov, bits). Cached on the sha256 of both FASTAs."""
    os.makedirs(workdir, exist_ok=True)
    q, r, h = f"{workdir}/q.faa", f"{workdir}/r.faa", f"{workdir}/h.m8"
    with open(q, "w") as fo:
        for s in query_ids:
            fo.write(f">{s}\n{seqs[s]}\n")
    with open(r, "w") as fo:
        for s in sorted(ref_ids):
            fo.write(f">{s}\n{seqs[s]}\n")
    key = hashlib.sha256(open(q, "rb").read() + open(r, "rb").read()).hexdigest()
    kf = f"{workdir}/key.sha256"
    if not (os.path.exists(h) and os.path.exists(kf) and open(kf).read().strip() == key):
        subprocess.run([mmseqs, "easy-search", q, r, h, f"{workdir}/tmp", "-s", "7.5", "--min-seq-id", "0.9",
                        "-c", "0.8", "--cov-mode", "0", "--threads", str(threads),
                        "--format-output", "query,target,fident,qcov,tcov,bits"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        open(kf, "w").write(key)
    return pd.read_csv(h, sep="\t", header=None, names=["q", "t", "fident", "qcov", "tcov", "bits"])


def e2_assign(hits, ref_exp, clade_of, prefer=None):
    """E2 transfer (v1.5 rule): non-self hit, same level-1 clade, all qualifying E1 hits agree on class.
    ref_exp: dict ref_acc -> exp_class. clade_of: dict acc -> clade_id ('' treated as missing).
    Reported reference = best-bitscore hit. v1.5.0 broke bitscore ties by pandas quicksort order (implementation
    dependent); v1.6.0 breaks ties deterministically: keep the previously reported reference (prefer: q -> ref) if it
    is among the tied best hits, else highest identity, then accession."""
    prefer = prefer or {}
    ref = pd.DataFrame({"t": list(ref_exp.keys()), "exp_class": list(ref_exp.values())})
    h = hits[hits.q != hits.t].merge(ref, on="t")
    keep = [norm_clade(clade_of.get(a)) is not None and norm_clade(clade_of.get(a)) == norm_clade(clade_of.get(b))
            for a, b in zip(h.q, h.t)]
    h = h[keep]
    if h.empty:
        return pd.DataFrame(columns=["source_acc", "e2_ref", "e2_identity", "e2_classes", "e2_n_tied_best"])
    rows = []
    for q, g in h.groupby("q"):
        classes = sorted(set(g.exp_class))
        if len(classes) > 1:
            continue
        top = g[g.bits == g.bits.max()]
        p = prefer.get(q)
        best = top[top.t == p].iloc[0] if p in set(top.t) else top.sort_values(["fident", "t"], ascending=[False, True]).iloc[0]
        rows.append(dict(source_acc=q, e2_ref=best.t, e2_identity=best.fident, e2_classes=classes[0], e2_n_tied_best=len(top)))
    return pd.DataFrame(rows)


def ladder_row(exp_class, e2_class, e2_ref, e2_id, is_member, v14, clade_id, clade_function, override_rule, motif):
    """v1.5 E-ladder for one record; returns (level, func_class, basis_v15style)."""
    if isinstance(exp_class, str):
        return "E1", EXP2V14[exp_class], "experimental:this_protein"
    if isinstance(e2_class, str) and is_member:
        return "E2", EXP2V14[e2_class], f"experimental_ortholog:{e2_ref}@{e2_id:.2f}:same_clade"
    if is_member and not is_unassigned(v14):
        fc = clade_function if isinstance(clade_function, str) and clade_function else None
        if fc is not None and agree_v14(v14, fc):
            return "E3", v14, f"motif+phylogeny:{clade_id}"
        if isinstance(override_rule, str) and override_rule:
            return "E4", v14, f"curated_rule:{override_rule}:{motif}"
        return "E4", v14, f"motif_only:{motif}"
    return "E5", "unresolved", "insufficient"


def loco_evaluate(e1):
    """LOO / LOSO / LOCO simulated-tier evaluation (identical logic to stage1/conflicts_loco.py and
    addendum loco_sensitivity.py). e1 needs: source_acc, exp, v14, motif_class, rc_clade, subclade_id,
    clade_function_source."""
    e1 = e1.copy()
    e1["conf"] = [conflict(a, b) for a, b in zip(e1.v14, e1.motif_class)]
    e1["call_legacy"] = e1.v14
    e1["call_downgrade"] = np.where(e1.conf == 1, "unassigned", e1.v14)
    e1["call_motif"] = e1.motif_class

    def consensus(group_ids, exclude):
        pool = e1[(~e1.source_acc.isin(exclude)) & (e1.subclade_id.isin(group_ids) | e1.rc_clade.isin(group_ids))]
        u = pool.exp.unique()
        return u[0] if len(u) == 1 else None

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
            if is_unassigned(v):
                tiers[mode].append("E5")
            elif cf is not None and agree_eval(v, cf) == 1:
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
            ok = pd.Series([agree_eval(cv, ex) for cv, ex in zip(s[f"call_{pol}"], s.exp)], dtype=float)
            na = int(ok.notna().sum()); k = int(ok.fillna(0).sum()); n = len(s)
            plo, phi = wilson(k, na); clo, chi = wilson(na, n)
            rows.append(dict(subset=subset_name, holdout=mode or "none", policy=pol, n=n, n_assigned=na,
                             coverage=na / n if n else np.nan, cov_lo=clo, cov_hi=chi, n_correct=k,
                             precision=k / na if na else np.nan, prec_lo=plo, prec_hi=phi, ci_method="wilson"))
    return pd.DataFrame(rows), e1
