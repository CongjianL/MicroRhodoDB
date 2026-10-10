import pandas as pd, json, sys
sys.path.insert(0,'.')
from lit import *
I='/mnt/shared-workspace/v160/curation_inputs/'
l=pd.read_csv(I+'auditC_landmarks_uniprot.tsv',sep='\t')
w=pd.read_csv(I+'e1_without_publication_link.tsv',sep='\t')
e=pd.read_csv(I+'external_positives_new.tsv',sep='\t')
extra=['A0A0D1E071','A0A0D1EC87','A0A0D1DV72','A0A5B2VFD4','A0A411LJN5','Q9UW81','A0ABF7PQ82','A0ABF7PQ84','L1K1K8','A0A1I3DJQ0','A0ABF7PQA2','A0A3G1I4H9']
accs=list(dict.fromkeys(list(l.Entry)+list(w.source_acc)+list(e.nearest_corpus_acc)+extra))
summ={}
for a in accs:
    u=uniprot(a)
    summ[a]={'name':(u or {}).get('proteinDescription',{}),'function':uniprot_function(u),'refs':uniprot_refs(u),
             'entryType':(u or {}).get('entryType'),'pe':(u or {}).get('proteinExistence'),
             'xrefs':[x for x in (u or {}).get('uniProtKBCrossReferences',[]) if x['database'] in ('EMBL','PDB')]}
json.dump(summ,open('cache/uniprot_summary.json','w'),indent=1)
print(len(summ), sum(1 for v in summ.values() if v['entryType']))
