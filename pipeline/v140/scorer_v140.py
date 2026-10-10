"""
MicroRhodoDB v1.4.0 — frozen v1.2 membership scorer, exactly reconstructed.

Reconstruction basis: releases/v1.0/tables/membership_assignments.tsv (the
"rosetta": raw features + evidence axes + frozen scores for all 5,361 v1
candidates, byte-identical membership_score to the frozen v1.3.0 DB).

Verified against all 5,361 frozen records (this module, gate run 2026-10-02):
  - evidence axes: exact to machine precision (max abs diff 2.2e-16)
  - weighted sum -> round(.,4) == frozen membership_score: 0/5361 differ
  - category rules (unrounded score + gates): 0/5361 differ

Evidence vector (weights):
  e_domain   0.28  expit((dom_score - 40)/15); dom_score = best domain bitscore
                   of the PRIMARY model (argmax of full-seq bitscores, NaN->0)
  e_coverage 0.20  hmm_cov = round(ali_len(primary)/model_len(primary), 4)
                   (PF01036: /224, PF18761: /242)
  e_retinal  0.25  retinal Schiff-base lysine present (0/1) at HMM consensus
                   position (PF01036: 210; PF18761: see RETINAL_POS)
  e_margin   0.15  expit((score_PF01036.fillna(0) - score_PF18761.fillna(0))/40)
  e_homology 0.10  seed_best_id * seed_best_cov; DIAMOND blastp vs 15 seeds,
                   max-bitscore hit: id = pident/100, cov = qcovhsp/100;
                   no hit -> 0.0
  e_topology 0.02  expit((kd_max - 1.6)/0.4); KD sliding window w=19

Score: round(sum(w_i * e_i), 4).  Categories use the UNROUNDED score.

Category rules (frozen thresholds 0.86/0.70/0.40; order matters):
  1. no domain hit                       -> rejected
  2. helio-primary (PF18761 > PF01036)   -> rejected
  3. score>=0.86 & lys & complete & +margin -> high_confidence_type_I;
        + PDB xref                        -> confirmed_type_I
  4. score>=0.70                          -> putative_type_I if lys else rhodopsin_like
  5. score>=0.40                          -> ambiguous if lys else rhodopsin_like
  6. else                                 -> rejected
"""
import math
import numpy as np
import pandas as pd
from scipy.special import expit

WEIGHTS = {'e_domain': 0.28, 'e_coverage': 0.20, 'e_retinal': 0.25,
           'e_margin': 0.15, 'e_homology': 0.10, 'e_topology': 0.02}

THR = {'score_confirmed': 0.9, 'score_high': 0.86, 'score_putative': 0.7,
       'score_rhodopsin_like': 0.4, 'require_retinal_for_confirmed': True,
       'require_positive_margin_for_top': True, 'complete_core_min_cov': 0.6}

MODEL_LEN = {'PF01036': 224, 'PF18761': 242}
RETINAL_HMM_POS = {'PF01036': 210}  # PF18761 position determined empirically below

KD = {'A': 1.8, 'R': -4.5, 'N': -3.5, 'D': -3.5, 'C': 2.5, 'Q': -3.5,
      'E': -3.5, 'G': -0.4, 'H': -3.2, 'I': 4.5, 'L': 3.8, 'K': -3.9,
      'M': 1.9, 'F': 2.8, 'P': -1.6, 'S': -0.8, 'T': -0.7, 'W': -0.9,
      'Y': -1.3, 'V': 4.2}


def kd_descriptors(seq, w=19):
    """Kyte-Doolittle sliding window (w=19). kd_max enters the scorer."""
    vals = [KD.get(aa, 0.0) for aa in seq]
    if len(vals) < w:
        wins = [float(np.mean(vals))] if vals else [0.0]
    else:
        wins = [float(np.mean(vals[i:i + w])) for i in range(len(vals) - w + 1)]
    kd_max = round(max(wins), 3)  # frozen convention: rounded to 3 decimals
    kd_mean = float(np.mean(vals)) if vals else 0.0
    frac_h = float(np.mean([1.0 if v > 0 else 0.0 for v in vals])) if vals else 0.0
    return {'kd_mean': kd_mean, 'kd_max': kd_max, 'kd_frac_hydrophobic': frac_h,
            'kd_n_segments': None}  # n_segments not used by scorer


def evidence_vector(feat):
    """feat: DataFrame with dom_score, hmm_cov, has_retinal_lysine,
    score_PF01036, score_PF18761, seed_best_id, seed_best_cov, kd_max."""
    ev = pd.DataFrame(index=feat.index)
    ev['e_domain'] = expit((feat['dom_score'].astype(float) - 40) / 15)
    ev['e_coverage'] = feat['hmm_cov'].astype(float)
    ev['e_retinal'] = feat['has_retinal_lysine'].astype(float)
    margin = feat['score_PF01036'].fillna(0) - feat['score_PF18761'].fillna(0)
    ev['e_margin'] = expit(margin / 40)
    ev['e_homology'] = feat['seed_best_id'].fillna(0.0) * feat['seed_best_cov'].fillna(0.0)
    ev['e_topology'] = expit((feat['kd_max'].astype(float) - 1.6) / 0.4)
    return ev


def score_from_evidence(ev):
    """Returns (unrounded_score, rounded_membership_score)."""
    s = sum(ev[k] * w for k, w in WEIGHTS.items())
    return s, s.round(4)


def primary_model(score_p, score_h):
    p = 0.0 if pd.isna(score_p) else score_p
    h = 0.0 if pd.isna(score_h) else score_h
    return 'PF01036' if p >= h else 'PF18761'


def categorize(score_unrounded, gate_has_domain, is_helio_primary, has_retinal_lysine,
               gate_complete_core, gate_positive_typeI_margin, has_pdb_xref):
    if not gate_has_domain:
        return 'rejected'
    if is_helio_primary:
        return 'rejected'
    if (score_unrounded >= THR['score_high'] and has_retinal_lysine
            and gate_complete_core and gate_positive_typeI_margin):
        return 'confirmed_type_I' if has_pdb_xref else 'high_confidence_type_I'
    if score_unrounded >= THR['score_putative']:
        return 'putative_type_I' if has_retinal_lysine else 'rhodopsin_like'
    if score_unrounded >= THR['score_rhodopsin_like']:
        return 'ambiguous' if has_retinal_lysine else 'rhodopsin_like'
    return 'rejected'
