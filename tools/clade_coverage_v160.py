"""Clade coverage of Type-I members and candidates (R-C1).
Usage: python tools/clade_coverage_v160.py <db.sqlite> <out.tsv>"""
import sys, sqlite3, pandas as pd, numpy as np
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
d=pd.read_sql("select source_acc,membership_status,is_engineered,clade_id,placement_call,tentative_clade_id from v_master where membership_status like 'typeI_member%' or membership_status like 'typeI_candidate%'",con)
override={'A0A1I3DJQ0','L1K1K8','A0A3G1I4H9','A0ABF7PQ82'}
d['group']=np.where(d.membership_status.str.startswith('typeI_member')|d.source_acc.isin(override),'member','candidate')
conf=d.clade_id.fillna('')!=''
def cat(r,c):
    if c: return 'confident_clade'
    if isinstance(r.tentative_clade_id, str) and r.tentative_clade_id != '':
        return 'tentative_MR_CLD3_017' if r.tentative_clade_id=='MR_CLD3_017' else 'tentative_other'
    pc = r.placement_call if isinstance(r.placement_call, str) and r.placement_call else 'no_placement'
    return 'unplaced_' + pc
d['coverage_category']=[cat(r,c) for r,c in zip(d.itertuples(),conf)]
rows=[]
for scope,sub in [('all_records',d),('counted_non_engineered',d[d.is_engineered==0])]:
    for grp in ['member','candidate','member+candidate']:
        s=sub if grp=='member+candidate' else sub[sub.group==grp]
        for k,v in s.coverage_category.value_counts().items():
            rows.append(dict(scope=scope,group=grp,coverage_category=k,n=v,n_group=len(s),pct=round(100*v/len(s),2)))
t=pd.DataFrame(rows).sort_values(['scope','group','coverage_category'])
t.to_csv(sys.argv[2], sep='\t', index=False)
print(t.to_string(index=False))
