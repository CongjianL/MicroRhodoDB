#!/usr/bin/env python
"""Freeze the v1.6.0 round-2 (referee follow-up) inputs into curation/v160/.

Inputs (produced once, outside the build):
  --audit-calls     blind re-annotation calls (120 rows; audit_blind_calls.tsv)
  --flag-corpus     tools/family_flag.py output on the corpus FASTA (one row per source_acc)
  --foldseek-dir    Foldseek web-search outputs (foldseek_queries/funnel.tsv)
  --foldseek-scored candidate table scored with tools/mrdb_search.py and tiered (cand_tiered.tsv)
Outputs (curation/v160/):
  audit_blind_calls_v160.tsv, novel_family_flag_v160.tsv, foldseek_hits_v160.tsv, foldseek_queries_v160.tsv,
  foldseek_funnel_v160.tsv, novel_family_candidates_v160.tsv (watchlist rows; schema unchanged)
Watchlist tiers: structure_only_no_PF01036 (no PF01036 hmmsearch hit at E<=10), underrepresented_family (best family
HMM is viral/schizo/MerMAID/bestrhodopsin), pfam_detectable_sampling_gap (all others; not added to the watchlist).
"""
import argparse, os, re
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--audit-calls", required=True)
ap.add_argument("--flag-corpus", required=True)
ap.add_argument("--foldseek-dir", required=True)
ap.add_argument("--foldseek-scored", required=True)
ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "..", "curation", "v160"))
A = ap.parse_args()
O = os.path.abspath(A.out)

a = pd.read_csv(A.audit_calls, sep="\t", dtype=str)
assert len(a) == 120 and a.audit_id.is_unique
a.to_csv(f"{O}/audit_blind_calls_v160.tsv", sep="\t", index=False)

f = pd.read_csv(A.flag_corpus, sep="\t", dtype={"source_acc": str})
f = f.drop_duplicates("source_acc")
assert len(f) == 5466, len(f)
f["novel_family_hit"] = f.novel_family_hit.fillna("")
f[["source_acc", "novel_family_hit", "novel_family_evalue", "novel_family_bits", "pf01036_bits"]].rename(
    columns={"novel_family_evalue": "family_evalue", "novel_family_bits": "family_bits"}).to_csv(
    f"{O}/novel_family_flag_v160.tsv", sep="\t", index=False)

for x in ("foldseek_queries", "foldseek_funnel"):
    pd.read_csv(f"{A.foldseek_dir}/{x}.tsv", sep="\t").to_csv(f"{O}/{x}_v160.tsv", sep="\t", index=False)

c = pd.read_csv(A.foldseek_scored, sep="\t", low_memory=False)
assert len(c) == 786 and c.target_id.is_unique
keep = {"target_id": "target_id", "source_db": "source_db", "length": "length", "architecture": "architecture",
        "best_query": "best_query", "best_query_family": "best_query_family", "best_bits": "best_bits",
        "best_evalue": "best_evalue", "best_prob": "best_prob", "HeR_bits": "her_bits",
        "nearest_corpus": "nearest_corpus_acc", "nearest_corpus_pid": "nearest_corpus_pid",
        "nearest_corpus_qcov": "nearest_corpus_qcov", "helixC_D85_T89_D96_seqaln": "helixC_motif_pairwise_BR",
        "retinal_K_seqaln": "retinal_K_pairwise_BR_unverified", "PF01036_hmmsearch_E": "pf01036_hmmsearch_evalue",
        "taxonomy": "taxonomy", "membership_score": "scorer_membership_score",
        "provisional_status": "scorer_provisional_status", "typeI_detected_070": "scorer_typeI_detected_070",
        "has_retinal_lysine": "scorer_has_retinal_lysine", "novel_family_hit": "family_flag",
        "novel_family_bits": "family_flag_bits", "pf01036_bits": "scorer_pf01036_bits",
        "nn_source_acc": "scorer_nn_source_acc", "nn_identity": "scorer_nn_identity", "nn_clade_id": "scorer_nn_clade_id",
        "watchlist_tier": "watchlist_tier", "seq": "sequence"}
h = c[list(keep)].rename(columns=keep)
h["to_watchlist"] = (h.watchlist_tier != "pfam_detectable_sampling_gap").astype(int)
h.to_csv(f"{O}/foldseek_hits_v160.tsv", sep="\t", index=False)

w = h[h.to_watchlist == 1]
sp = w.taxonomy.fillna("").str.split("|").str[0].str.strip()
nfc = pd.DataFrame(dict(
    family=[x if isinstance(x, str) and x else "structure_only" for x in w.family_flag],
    source_db="foldseek_web:" + w.source_db,
    query_accession=w.best_query,
    resolved_accession=w.target_id.str.replace(r"^(AF|MG):", "", regex=True),
    identifier=w.target_id,
    description=w.watchlist_tier,
    species=[s if s and not s.startswith("NA:") else None for s in sp],
    taxonomy_id=None,
    architecture=w.architecture,
    score=w.best_bits,
    evalue=w.best_evalue,
    seq_length=w.length,
    has_retinalK=w.scorer_has_retinal_lysine.astype(int),
    mapali_window=None))
nfc.to_csv(f"{O}/novel_family_candidates_v160.tsv", sep="\t", index=False)
print("audit", len(a), "| flags", len(f), "flagged", int((f.novel_family_hit != "").sum()),
      "| foldseek hits", len(h), "watchlist", len(nfc), nfc.description.value_counts().to_dict())
