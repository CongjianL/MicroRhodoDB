"""MicroRhodoDB v1.5.0 - end-to-end membership feature extraction + frozen scorer.

Wraps pipeline/v140/features_v140.py (feature conventions) and scorer_v140.py (frozen
weights/thresholds) into one callable used by the Snakemake workflow, the external
validation, and the baselines.  Toolchain is pinned by workflow/envs/mrdb.lock.yml
(pyhmmer 0.12.3, HMMER 3.4 CLI hmmalign, DIAMOND 2.1.10).

CLI: python score_v150.py <query.faa> <seeds.faa> <seed_meta.tsv> <PF01036.hmm> <PF18761.hmm> <workdir> <out.tsv>
Output columns: all features + evidence axes + membership_score (rounded 4) + score_unrounded + membership_category.
"""
import os, sys, shutil
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'v140'))
import features_v140 as fx  # noqa: E402
import scorer_v140 as sv    # noqa: E402

HMMER_BIN = os.environ.get('HMMER_BIN', os.path.dirname(shutil.which('hmmalign') or '/workspace/.conda/mrdb/bin/hmmalign'))
DIAMOND = os.environ.get('DIAMOND_BIN', shutil.which('diamond') or '/workspace/.conda/mrdb/bin/diamond')


def read_fasta(p):
    seqs, k = {}, None
    for line in open(p):
        line = line.strip()
        if not line: continue
        if line[0] == '>': k = line[1:].split()[0]; seqs[k] = []
        else: seqs[k].append(line)
    return {a: ''.join(v).upper().replace('*', '') for a, v in seqs.items()}


def compute(query_faa, seeds_faa, seed_meta_tsv, hmm01036, hmm18761, workdir):
    os.makedirs(workdir, exist_ok=True)
    seqs = read_fasta(query_faa)
    seeds = read_fasta(seeds_faa)
    meta = pd.read_csv(seed_meta_tsv, sep='\t').set_index('acc')
    hmms = fx.load_hmms([hmm01036, hmm18761])
    hits = fx.scan_domains(seqs, hmms)
    feat = pd.DataFrame([fx.domain_features(a, s, hits) for a, s in seqs.items()]).set_index('source_acc')
    # retinal lysine: hmmalign query+seeds against each model; column = 100%-K seed column
    lys = {}
    for model, path in (('PF01036', hmm01036), ('PF18761', hmm18761)):
        sub = {a: s for a, s in seqs.items() if feat.at[a, 'primary_model'] == model and not pd.isna(feat.at[a, 'dom_score'])}
        seed_set = [a for a in seeds if (meta.at[a, 'subfamily'] == 'heliorhodopsin') == (model == 'PF18761')]
        both = {**{f'{a}|seed': seeds[a] for a in seed_set}, **sub}
        if not sub: continue
        sto, ref = fx.run_hmmalign(HMMER_BIN, path, both, workdir, f'aln_{model}')
        col = fx.lysine_column(sto, ref, set(seed_set))
        for a, (res, pos) in fx.read_lysine({k: v for k, v in sto.items() if not k.endswith('|seed')}, col).items():
            lys[a] = (res, pos)
    feat['has_retinal_lysine'] = [int(lys.get(a, (None, None))[0] == 'K') for a in feat.index]
    feat['retinal_pos'] = [lys.get(a, (None, None))[1] for a in feat.index]
    with open(os.path.join(workdir, 'seeds.faa'), 'w') as fh:
        for a, s in seeds.items(): fh.write(f'>{a}\n{s}\n')
    hom = fx.seed_homology(DIAMOND, query_faa, os.path.join(workdir, 'seeds.faa'), workdir, meta).set_index('source_acc')
    feat = feat.join(hom)
    for c in ('seed_best_id', 'seed_best_cov'): feat[c] = feat[c].fillna(0.0)
    feat['kd_max'] = [sv.kd_descriptors(seqs[a])['kd_max'] for a in feat.index]
    ev = sv.evidence_vector(feat)
    s_un, s_r = sv.score_from_evidence(ev)
    out = feat.join(ev)
    out['score_unrounded'], out['membership_score'] = s_un, s_r
    out['gate_has_domain'] = ~out.dom_score.isna()
    out['is_helio_primary'] = out.primary_model == 'PF18761'
    out['gate_complete_core'] = out.hmm_cov.fillna(0) >= sv.THR['complete_core_min_cov']
    out['gate_positive_typeI_margin'] = out.score_PF01036.fillna(0) > out.score_PF18761.fillna(0)
    out['membership_category'] = [sv.categorize(r.score_unrounded, r.gate_has_domain, r.is_helio_primary, bool(r.has_retinal_lysine),
                                                r.gate_complete_core, r.gate_positive_typeI_margin, False) for r in out.itertuples()]
    return out.reset_index()


if __name__ == '__main__':
    q, sf, sm, h1, h2, wd, o = sys.argv[1:8]
    compute(q, sf, sm, h1, h2, wd).to_csv(o, sep='\t', index=False)
