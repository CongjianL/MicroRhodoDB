import sys,json; sys.path.insert(0,'.')
from lit import *
from lit import _get
out={}
for p in ['8YEJ','8YEK','8YEL','9CDC','9CDD','9CDE','8ZAO','8ZAP','8ZAQ','8R0K','8XX8','8ANQ','6EDQ']:
    e=rcsb_entry(p)
    ents=[]
    for eid in (e or {}).get('rcsb_entry_container_identifiers',{}).get('polymer_entity_ids',[]):
        pe=_get(f'https://data.rcsb.org/rest/v1/core/polymer_entity/{p}/{eid}')
        ents.append({'desc':pe.get('rcsb_polymer_entity',{}).get('pdbx_description'),'mutation':pe.get('rcsb_polymer_entity',{}).get('pdbx_mutation'),
                     'uniprot':pe.get('rcsb_polymer_entity_container_identifiers',{}).get('uniprot_ids'),
                     'seq':pe.get('entity_poly',{}).get('pdbx_seq_one_letter_code_can'),'src':[s.get('ncbi_scientific_name') for s in pe.get('rcsb_entity_source_organism',[])]})
    out[p]={'title':(e or {}).get('struct',{}).get('title'),'doi':(e or {}).get('rcsb_primary_citation',{}).get('pdbx_database_id_doi'),
            'pmid':(e or {}).get('rcsb_primary_citation',{}).get('pdbx_database_id_pub_med'),'entities':ents}
    print(p,out[p]['title'],out[p]['pmid'],[(x['desc'],x['mutation'],x['uniprot']) for x in ents])
json.dump(out,open('cache/rcsb_summary.json','w'),indent=1)
