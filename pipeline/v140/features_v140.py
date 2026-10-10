"""
MicroRhodoDB v1.4.0 — feature extraction for the frozen membership scorer.

Pinned toolchain (recorded in build_provenance):
  - pyhmmer 0.12.3 / HMMER 3.4, DEFAULT pipeline thresholds (E=10, bias on)
    for domain scores  [== v1 `hmmsearch -E 10` domtbl path]
  - HMMER 3.4 CLI hmmalign for the retinal-lysine column read
    [== v1 `qc.run_hmmalign` path; pyhmmer.hmmalign is NOT equivalent]
  - DIAMOND 2.2.8 blastp vs 15 seeds for seed homology
  - HMMs: PF01036.25 (preserved) + PF18761.8 (InterPro/Pfam,
    sha256 41f5a13c0eb54a040893d29937c5644d0d1e2b8ff74e3d5ad2100f5ac56a84ef)

Conventions (reverse-engineered from the v1 rosetta; verification on all 5,361
frozen records 2026-10-02):
  score_PF01036 / score_PF18761 : round(best-domain bitscore vs HMM, 1);
                                  NaN if no reported hit   [exact: 5361/5361]
  primary_model                 : argmax(score_PF01036.fillna(0), score_PF18761.fillna(0))  [exact]
  dom_score                     : round(best-domain bitscore of primary model, 1)  [exact]
  hmm_cov                       : round(union of ali HMM coords over domains with
                                  bitscore >= 2 / model_len(primary), 4);
                                  model_len PF01036=224, PF18761=242   [exact: 5361/5361]
  seq_cov                       : same union over env coords / length  [5359-5360/5361; descriptive only]
  has_retinal_lysine            : hmmalign vs primary model; residue at match-state
                                  column 210 (PF01036) / 230 (PF18761) == 'K';
                                  column located empirically as the 100%-K seed column  [exact: 5361/5361]
  retinal_pos                   : 1-based sequence ordinal of that residue  [exact: 5361/5361]
  seed_best_id/cov/bits/subfam  : DIAMOND blastp --outfmt 6 qseqid sseqid pident length
                                  qlen slen qstart qend evalue bitscore --max-target-seqs 15;
                                  max-bitscore hit; id=pident/100,
                                  cov=round((qend-qstart+1)/qlen, 4); no hit -> 0.0
                                  [5360/5361; single bitscore-tie edge case]
  kd_max                        : round(max Kyte-Doolittle window mean (w=19), 3)  [exact]

End-to-end gate (recomputed features -> frozen scorer -> frozen scores):
  5360/5361 membership_score exact (max diff 0.0002: DIAMOND tie-break on
  A0ABR3CQ64); 5361/5361 membership_category exact.
"""
import subprocess
import numpy as np
import pandas as pd
import pyhmmer
from pyhmmer.easel import Alphabet, DigitalSequenceBlock, TextSequence
from pyhmmer.plan7 import Pipeline

MODEL_LEN = {'PF01036': 224, 'PF18761': 242}
RETINAL_MATCH_STATE = {'PF01036': 210, 'PF18761': 230}
DOM_SCORE_MIN = 2.0  # domains with bitscore >= 2 enter the coverage union


def _b2s(x):
    return x.decode() if isinstance(x, (bytes, bytearray)) else str(x)


def load_hmms(paths):
    hmms = {}
    for p in paths:
        with pyhmmer.plan7.HMMFile(p) as hf:
            h = hf.read()
        hmms[_b2s(h.accession).split('.')[0]] = h
    return hmms


def scan_domains(seqs, hmms, alphabet=None):
    """Default-threshold hmmsearch per HMM. Returns {model: {acc: hit-dict}}."""
    alphabet = alphabet or Alphabet.amino()
    pipe = Pipeline(alphabet)
    block = DigitalSequenceBlock(
        alphabet, [TextSequence(name=a.encode(), sequence=s).digitize(alphabet)
                   for a, s in seqs.items()])
    out = {}
    for name, h in hmms.items():
        res = pipe.search_hmm(h, block)
        d = {}
        for hit in res:
            doms = []
            for dom in hit.domains:
                ali = dom.alignment
                doms.append({'score': float(dom.score),
                             'ali_hmm': (ali.hmm_from, ali.hmm_to),
                             'env': (dom.env_from, dom.env_to)})
            d[_b2s(hit.name)] = {'score': float(hit.score), 'evalue': float(hit.evalue),
                                 'doms': doms,
                                 'best_dom_score': float(hit.best_domain.score)}
        out[name] = d
    return out


def domain_features(acc, seq, hits_by_model):
    row = {'source_acc': acc, 'length': len(seq)}
    for name in ('PF01036', 'PF18761'):
        hit = hits_by_model[name].get(acc)
        row[f'score_{name}'] = round(hit['best_dom_score'], 1) if hit else np.nan
        row[f'evalue_{name}'] = hit['evalue'] if hit else np.nan
    p = row['score_PF01036'] if not pd.isna(row['score_PF01036']) else 0.0
    h_ = row['score_PF18761'] if not pd.isna(row['score_PF18761']) else 0.0
    primary = 'PF01036' if p >= h_ else 'PF18761'
    row['primary_model'] = primary
    hit = hits_by_model[primary].get(acc)
    if hit is None:
        row.update(dom_score=np.nan, hmm_cov=np.nan, seq_cov=np.nan, seq_evalue=np.nan)
    else:
        row['dom_score'] = round(hit['best_dom_score'], 1)
        cov, env = set(), set()
        for d in hit['doms']:
            if d['score'] >= DOM_SCORE_MIN:
                cov.update(range(d['ali_hmm'][0], d['ali_hmm'][1] + 1))
                env.update(range(d['env'][0], d['env'][1] + 1))
        row['hmm_cov'] = round(len(cov) / MODEL_LEN[primary], 4)
        row['seq_cov'] = round(len(env) / len(seq), 4)
        row['seq_evalue'] = hit['evalue']
    return row


# ---------------- retinal lysine via CLI hmmalign ----------------

def run_hmmalign(hmmer_bin, hmm_path, seqs_dict, workdir, tag):
    """Run CLI hmmalign, return dict acc -> aligned string + RF line."""
    import os
    fa = os.path.join(workdir, f'{tag}.faa')
    with open(fa, 'w') as fh:
        for a, s in seqs_dict.items():
            fh.write(f'>{a}\n{s}\n')
    r = subprocess.run([f'{hmmer_bin}/hmmalign', hmm_path, fa],
                       capture_output=True, text=True, check=True)
    seqs, ref = {}, None
    for line in r.stdout.splitlines():
        if line.startswith('#=GC RF'):
            ref = (ref or '') + line.split(None, 2)[2].strip()
        elif line.startswith('#') or line.startswith('//'):
            continue
        elif line.strip():
            parts = line.split()
            if len(parts) == 2:
                seqs[parts[0]] = seqs.get(parts[0], '') + parts[1]
    return seqs, ref


def lysine_column(sto, ref, seed_accs):
    """Match-state column where seed rows carry K (v1: find_lysine_match_column)."""
    rows = {k.split('|')[0]: v for k, v in sto.items() if k.split('|')[0] in seed_accs}
    best, best_frac = None, -1.0
    for i, rc in enumerate(ref):
        if rc != 'x':
            continue
        frac = sum(1 for v in rows.values() if v[i] == 'K') / len(rows)
        if frac > best_frac:
            best_frac, best_col = frac, i
    return best_col


def read_lysine(sto, col):
    """residue + 1-based sequence ordinal at alignment column (v1: read_lysine_from_alignment)."""
    out = {}
    for k, v in sto.items():
        acc = k.split('|')[0]
        c = v[col]
        if c.isalpha():
            out[acc] = (c, sum(1 for ch in v[:col + 1] if ch.isalpha()))
        else:
            out[acc] = (None, None)
    return out


# ---------------- seed homology via DIAMOND ----------------

def seed_homology(diamond_bin, query_faa, seed_faa, workdir, seed_meta):
    """DIAMOND blastp vs seeds; max-bitscore hit per query.
    Returns DataFrame source_acc, seed_best_id, seed_best_cov, seed_best_bits,
    seed_best_subfamily. Queries without a hit get 0.0/None downstream."""
    import os
    db = os.path.join(workdir, 'seeds_dmnd')
    subprocess.run([diamond_bin, 'makedb', '--in', seed_faa, '-d', db, '--quiet'],
                   check=True, capture_output=True)
    out = os.path.join(workdir, 'query_vs_seeds.tsv')
    subprocess.run([diamond_bin, 'blastp', '-q', query_faa, '-d', db, '-o', out,
                    '--outfmt', '6', 'qseqid', 'sseqid', 'pident', 'length', 'qlen',
                    'slen', 'qstart', 'qend', 'evalue', 'bitscore',
                    '--max-target-seqs', '15', '--quiet'], check=True, capture_output=True)
    cols = ['qry', 'seed', 'pident', 'alnlen', 'qlen', 'slen', 'qstart', 'qend', 'evalue', 'bits']
    try:
        csh = pd.read_csv(out, sep='\t', names=cols)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=['source_acc', 'seed_best_id', 'seed_best_cov',
                                     'seed_best_bits', 'seed_best_subfamily'])
    csh['seed_acc'] = csh['seed'].str.split('|').str[0]
    best = csh.loc[csh.groupby('qry')['bits'].idxmax()]
    rows = []
    for v in best.itertuples():
        rows.append({'source_acc': v.qry,
                     'seed_best_id': v.pident / 100,
                     'seed_best_cov': round((v.qend - v.qstart + 1) / v.qlen, 4),
                     'seed_best_bits': v.bits,
                     'seed_best_subfamily': seed_meta.loc[v.seed_acc, 'subfamily']
                     if v.seed_acc in seed_meta.index else None})
    return pd.DataFrame(rows)
