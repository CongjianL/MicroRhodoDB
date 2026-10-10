"""Audit A (fresh-referee re-review, v1.5.0): benchmark leakage / circularity.

Inputs (all frozen v1.5.0 artefacts):
  ext_v2.faa (freeze v2, sha256 da634bfd...), DIAMOND m8 vs seeds/bench/corpus/tips (cell-6cb716b53098),
  wp3_external_scores.tsv (366 per-record scores used for the published external metrics),
  release DB (external_validation, holdout_assignment, benchmark_v2, membership, seed),
  E1_set.tsv (85 E1 records).
Outputs -> /mnt/results/v150_review/audit/auditA_*.tsv, fig_auditA_identity_filter.svg
"""
import json, os, subprocess, sqlite3, sys
import numpy as np, pandas as pd

sys.path.insert(0, "/workspace/MicroRhodoDB/pipeline/v150")
import wp3_eval as E

A = "/workspace/v150/review_auditA"
OUT = "/mnt/results/v150_review/audit"
os.makedirs(OUT, exist_ok=True)
DB = "/workspace/MicroRhodoDB/releases/v1.5.0/db/microrhododb_v1.5.0.sqlite"
COLS = "q t pident length qlen slen qstart qend sstart send evalue bits".split()
COV = 0.5
SEED, NBOOT = 150, 2000
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def read_m8(p, self_hits=False):
    m = pd.read_csv(p, sep="\t", header=None, names=COLS)
    m["qcov"] = (m.qend - m.qstart + 1) / m.qlen
    m = m[m.qcov >= COV]
    if not self_hits:
        m = m[m.q != m.t]
    return m


def max_id(m):
    i = m.sort_values("pident", ascending=False).drop_duplicates("q")
    return i.set_index("q")[["t", "pident"]]


# ---------------- 1. per-record identity to every development / reference set -----------------
d = pd.read_csv("/workspace/v150/wp3/ext/out/wp3_external_scores.tsv", sep="\t")
ev = pd.read_sql("select * from external_validation", con)
assert len(d) == 366 and int(d.y.sum()) == 21 and set(d.source_acc) == set(ev.ext_acc)
ids = [l[1:].strip() for l in open(f"{A}/ext_v2.faa") if l.startswith(">")]
assert set(ids) == set(d.source_acc)
for R in ("seeds", "bench", "corpus", "tips"):
    mi = max_id(read_m8(f"{A}/ext_vs_{R}.m8", self_hits=True))
    d[f"id_{R}"] = d.source_acc.map(mi.pident).fillna(0.0)
    d[f"nn_{R}"] = d.source_acc.map(mi.t)
d["id_any"] = d[[f"id_{R}" for R in ("seeds", "bench", "corpus", "tips")]].max(axis=1)
d["id_dev"] = d[["id_seeds", "id_bench", "id_tips"]].max(axis=1)  # sets used to build/tune the scorer & tree
d = d.merge(ev[["ext_acc", "protein_label", "negative_class", "max_identity_to_corpus", "nearest_corpus_acc"]],
            left_on="source_acc", right_on="ext_acc", how="left")
mem = pd.read_sql("select source_acc, membership_status from membership", con).set_index("source_acc").membership_status
d["nn_corpus_status_v150"] = d.nn_corpus.map(mem)

bins = [-1, 0, 50, 70, 90, 101]
lab = ["no_hit", "<50", "50-70", "70-90", ">=90"]
rows = []
for R in ("seeds", "bench", "corpus", "tips", "dev", "any"):
    for y in (1, 0):
        c = pd.cut(d.loc[d.y == y, f"id_{R}"], bins, labels=lab, right=False).value_counts().reindex(lab).fillna(0)
        rows.append(dict(reference=R, cls="positive" if y else "negative", n=int((d.y == y).sum()), **c.astype(int).to_dict()))
idtab = pd.DataFrame(rows)
idtab.to_csv(f"{OUT}/auditA_identity_to_reference_sets.tsv", sep="\t", index=False)

keep = ["source_acc", "y", "stratum", "full_gated", "id_seeds", "nn_seeds", "id_bench", "nn_bench", "id_corpus",
        "nn_corpus", "nn_corpus_status_v150", "id_tips", "nn_tips", "id_dev", "id_any"]
d[keep].to_csv(f"{OUT}/auditA_per_record_identity.tsv", sep="\t", index=False)

# ---------------- 2. negatives close to the corpus ------------------------------------------------
negc = d[(d.y == 0) & (d.id_corpus >= 50)][keep].sort_values("id_corpus", ascending=False)
negc.to_csv(f"{OUT}/auditA_negatives_near_corpus.tsv", sep="\t", index=False)

# ---------------- 3. re-estimate metrics after identity filtering ---------------------------------
filt = {"none": d}
for t in (90, 70, 50):
    filt[f"any<{t}"] = d[d.id_any < t]
    filt[f"dev<{t}"] = d[d.id_dev < t]
# difficulty strata: homolog-class negatives only (negatives that share the 7TM retinal-protein fold)
HOM = {"heliorhodopsin", "animal_typeII_opsin", "fungal_Hsp30_opsin_related", "retinal_site_lacking_PF01036_homolog"}
homneg = set(d.loc[d.y == 0, "stratum"].unique()) & {s for s in d.stratum.unique()
                                                    if any(k in s for k in ("helio", "opsin", "Hsp30", "hsp30", "retinal"))}
filt["homolog_negatives_only"] = d[(d.y == 1) | d.stratum.isin(homneg)]
mrows, orows = [], []
for name, P in filt.items():
    P = P.reset_index(drop=True)
    if P.y.sum() < 2:
        continue
    rng = np.random.default_rng(SEED)
    mm = E.metrics(P, rng, NBOOT)
    mm.insert(0, "filter", name)
    mrows.append(mm)
    op = E.operating_points(P)
    op.insert(0, "filter", name)
    orows.append(op)
M = pd.concat(mrows)
O = pd.concat(orows)
M.to_csv(f"{OUT}/auditA_identity_filtered_metrics.tsv", sep="\t", index=False)
O.to_csv(f"{OUT}/auditA_identity_filtered_operating_points.tsv", sep="\t", index=False)

# negatives that receive a non-zero gated score (the only negatives that can affect ranking)
nz = d[(d.y == 0) & (d.full_gated > 0)][keep]
nz.to_csv(f"{OUT}/auditA_negatives_nonzero_score.tsv", sep="\t", index=False)

# ---------------- 4. holdout fold contamination (WP3 benchmark_v2) --------------------------------
bench = pd.read_sql("select * from benchmark_v2", con)
seeds = pd.read_sql("select * from seed", con)
pos = set(bench.loc[bench.is_positive == 1, "source_acc"])
if not os.path.exists(f"{A}/bench_vs_seeds.m8"):
    subprocess.run(f"export PATH=/workspace/.conda/mrdb/bin:$PATH; cd {A}; diamond blastp -q bench.faa -d seeds "
                   f"-o bench_vs_seeds.m8 --ultra-sensitive -k 25 -e 1e-3 --quiet --outfmt 6 {' '.join(['qseqid','sseqid','pident','length','qlen','slen','qstart','qend','sstart','send','evalue','bitscore'])}",
                   shell=True, check=True)
bs = read_m8(f"{A}/bench_vs_seeds.m8", self_hits=True)
bb = read_m8(f"{A}/bench_vs_bench.m8")
h = pd.read_sql("select * from holdout_assignment", con)
hp = h[h.role == "held_out_positive"].copy()
hp["excl"] = hp.excluded_seeds.apply(lambda s: set(json.loads(s)) if s else set())
crow = []
for _, r in hp.iterrows():
    fold_hold = set(hp[(hp.regime == r.regime) & (hp.fold_id == r.fold_id)].source_acc)
    s_av = bs[(bs.q == r.source_acc) & ~bs.t.isin(r.excl)]
    tr = bb[(bb.q == r.source_acc) & bb.t.isin(pos - fold_hold)]
    crow.append(dict(regime=r.regime, fold_id=r.fold_id, source_acc=r.source_acc, is_seed=r.source_acc in set(seeds.acc),
                     n_excluded_seeds=len(r.excl),
                     max_id_available_seed=s_av.pident.max() if len(s_av) else 0.0,
                     nn_available_seed=s_av.sort_values("pident").t.iloc[-1] if len(s_av) else None,
                     max_id_training_positive=tr.pident.max() if len(tr) else 0.0,
                     score_full=r.score_full, score_fold=r.score_fold, e_hom_full=r.e_hom_full, e_hom_fold=r.e_hom_fold))
C = pd.DataFrame(crow)
C.to_csv(f"{OUT}/auditA_holdout_contamination_per_record.tsv", sep="\t", index=False)
summ = []
for reg, g in C.groupby("regime"):
    row = dict(regime=reg, n_heldout=len(g), seeds_in_heldout=int(g.is_seed.sum()),
               score_changed=int((g.score_full.round(4) != g.score_fold.round(4)).sum()))
    for t in (90, 70, 50):
        row[f"seed_id>={t}"] = int((g.max_id_available_seed >= t).sum())
        row[f"trainpos_id>={t}"] = int((g.max_id_training_positive >= t).sum())
    row["median_id_available_seed"] = g.max_id_available_seed.median()
    row["median_id_training_positive"] = g.max_id_training_positive.median()
    summ.append(row)
CS = pd.DataFrame(summ)
CS.to_csv(f"{OUT}/auditA_holdout_contamination_summary.tsv", sep="\t", index=False)

# ---------------- 5. circularity: E1 anchors vs seeds / benchmark / tips --------------------------
e1 = set(pd.read_csv("/mnt/shared-workspace/v150/review/E1_set.tsv", sep="\t").source_acc)
tips = {l[1:].strip() for l in open(f"{A}/tips.faa") if l.startswith(">")}
ctips = set(pd.read_sql("select source_acc from clade_tip", con).source_acc)
circ = dict(E1=len(e1), seeds=len(set(seeds.acc)), bench_pos=len(pos), tips_faa=len(tips), clade_tip_table=len(ctips),
            E1_and_seeds=len(e1 & set(seeds.acc)), E1_and_benchpos=len(e1 & pos), E1_and_tips=len(e1 & tips),
            E1_and_seeds_and_tips=len(e1 & set(seeds.acc) & tips), seeds_in_benchpos=len(set(seeds.acc) & pos),
            seeds_in_tips=len(set(seeds.acc) & tips), benchpos_in_tips=len(pos & tips),
            E1_and_benchpos_and_tips=len(e1 & pos & tips))
pd.Series(circ).to_csv(f"{OUT}/auditA_circularity_overlaps.tsv", sep="\t", header=["n"])

# ---------------- print summary ---------------------------------------------------------------------
pd.set_option("display.width", 220)
print(idtab.to_string(index=False))
print("\nnegatives with >=50% id to corpus:", len(negc))
print(negc[["source_acc", "stratum", "id_corpus", "nn_corpus", "nn_corpus_status_v150", "full_gated"]].to_string(index=False))
print("\nnegatives with non-zero gated score:", len(nz))
print(nz[["source_acc", "stratum", "full_gated", "id_corpus", "nn_corpus_status_v150"]].to_string(index=False))
print("\nhomolog negative strata used:", sorted(homneg))
print(M[M.method.isin(["full_gated", "full_raw", "B2b_margin", "B3_nn_bits", "abl_e_retinal", "abl_e_homology"])]
      [["filter", "method", "n_pos", "n_neg", "auprc", "auprc_lo", "auprc_hi", "roc_auc"]].round(3).to_string(index=False))
print(O[(O.method == "full_gated") & O.metric.isin(["sensitivity", "specificity"])]
      [["filter", "threshold", "metric", "k", "n", "value", "ci_lo", "ci_hi"]].round(3).to_string(index=False))
print(CS.round(1).to_string(index=False))
print(circ)
