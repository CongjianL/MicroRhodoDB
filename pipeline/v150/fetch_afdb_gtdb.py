"""MicroRhodoDB v1.5.0 - retrieve AlphaFold DB model metadata + per-residue pLDDT and GTDB metadata.

Usage: python fetch_afdb_gtdb.py <db.sqlite> <outdir>
Outputs:
  afdb_models.tsv     source_acc, model_id, version, global_plddt, seq_match, model_url
  afdb_plddt/<acc>.tsv.gz  per-residue pLDDT (resnum, aa, plddt) from the model CIF/PDB B-factor
  gtdb/VERSION.txt, gtdb/{bac120,ar53}_metadata.tsv.gz
"""
import sys, os, gzip, json, sqlite3, time, hashlib, concurrent.futures as cf
import requests, pandas as pd

db, out = sys.argv[1], sys.argv[2]
os.makedirs(f'{out}/afdb_plddt', exist_ok=True); os.makedirs(f'{out}/gtdb', exist_ok=True)
con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
prot = pd.read_sql("select p.source_acc, p.sequence from protein p join sequence_source s using(source_acc) "
                   "where s.source_database like 'UniProt%'", con)
S = requests.Session()


def get(url, tries=4, stream=False):
    for k in range(tries):
        try:
            r = S.get(url, timeout=60, stream=stream)
            if r.status_code == 404: return None
            r.raise_for_status(); return r
        except Exception:
            time.sleep(2 * (k + 1))
    return None


def one(acc, seq):
    pth = f'{out}/afdb_plddt/{acc}.tsv.gz'
    r = get(f'https://alphafold.ebi.ac.uk/api/prediction/{acc}')
    if r is None: return dict(source_acc=acc, model_id=None, status='no_model')
    js = [m for m in r.json() if m.get('uniprotAccession') == acc] or r.json()
    if not js: return dict(source_acc=acc, model_id=None, status='no_model')
    m = js[0]
    rec = dict(source_acc=acc, model_id=m.get('modelEntityId'), version=m.get('latestVersion'),
               global_plddt=m.get('globalMetricValue'), seq_match=(m.get('sequence') == seq),
               seq_start=m.get('sequenceStart'), seq_end=m.get('sequenceEnd'), model_url=m.get('pdbUrl'),
               model_created=m.get('modelCreatedDate'), status='ok')
    if not os.path.exists(pth) and m.get('pdbUrl'):
        p = get(m['pdbUrl'])
        if p is not None:
            rows, seen = [], set()
            for line in p.text.splitlines():
                if line.startswith('ATOM') and line[12:16].strip() == 'CA':
                    rn = int(line[22:26])
                    if rn in seen: continue
                    seen.add(rn); rows.append((rn, line[17:20], float(line[60:66])))
            with gzip.open(pth, 'wt') as fh:
                fh.write('resnum\tres3\tplddt\n')
                for t in rows: fh.write('%d\t%s\t%.2f\n' % t)
        else:
            rec['status'] = 'model_download_failed'
    return rec


recs = []
with cf.ThreadPoolExecutor(12) as ex:
    futs = [ex.submit(one, a, s) for a, s in zip(prot.source_acc, prot.sequence)]
    for i, f in enumerate(cf.as_completed(futs)):
        recs.append(f.result())
        if i % 500 == 0: print('afdb', i, flush=True)
pd.DataFrame(recs).to_csv(f'{out}/afdb_models.tsv', sep='\t', index=False)
print('afdb done', len(recs), flush=True)

base = 'https://data.gtdb.ecogenomic.org/releases/latest/'
open(f'{out}/gtdb/VERSION.txt', 'w').write(get(base + 'VERSION.txt').text)
for fn in ['ar53_metadata.tsv.gz', 'bac120_metadata.tsv.gz']:
    r = get(base + fn, stream=True)
    with open(f'{out}/gtdb/{fn}', 'wb') as fh:
        for ch in r.iter_content(1 << 20): fh.write(ch)
    print('gtdb', fn, os.path.getsize(f'{out}/gtdb/{fn}'), flush=True)
