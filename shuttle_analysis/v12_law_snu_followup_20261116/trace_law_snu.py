"""Trace completed law/SNU transfer cohorts without opening new field outcomes."""
from pathlib import Path
from collections import Counter,defaultdict
import csv,gzip,hashlib,json,math,gc
ROOT=Path(__file__).resolve().parent;A=ROOT.parent
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
f=read(A/'261116122336/frozen/prepared_capacity44_pair.json.gz');common=f['prepared']['common']
source={p[0]:p for ps in f['prepared']['plans'].values() for p in ps};dest=f['destination_keys']
nodes=common['nodes'];profiles=list(csv.DictReader((A/'v12_current_pressure_20261116/afternoon-law-before-after.csv').open(encoding='utf-8-sig')))
focus=defaultdict(float);cases=[]
for model,fn in [('261116122336','pilot-validation.json'),('261116112731','pilot-validation.json'),('261116105704','grid-validation.json'),('261116010854','grid-validation.json')]:
    validation=read(A/model/fn)
    r=next(r for r in validation['results'] if r['case']['day']=='화' and r['case']['scenario']=='regular' and not r['case']['case'].startswith('ablation'))
    path=Path(r['source_directory'])/'audit-regular-tue.json.gz';assert sha(path)==r['audit_sha256'];a=read(path)
    vehicles={v['id']:v for v in a['vehicles']}
    # Use each model's own 15-20 peak where available; otherwise the latest
    # candidate's peak clock for diagnostic comparison, explicitly labelled.
    pr=next((p for p in profiles if p['model']==model and p['weekday']=='화' and p['node']=='60'),None)
    at=float(pr['peak_seconds']) if pr else 61260.29786368151
    groups=defaultdict(Counter);examples=[];all_law=0.;all_snu_law=0.;all_snu_transfer=0.;selected={}
    for t in a['legs']:
        if dest[str(t['parent_id'])]!='snu':continue
        uid=t['id'];weight=t['weight']
        for ix,l in enumerate(t['legs']):
            if l[0]!=1 or l[4]!=60 or not l[1]<=at<l[2]:continue
            all_snu_law+=weight
            prior=[v for v in t['legs'][:ix] if v[0]==3]
            if not prior:continue
            all_snu_transfer+=weight
            parent=source[t['parent_id']];before=[h for h in t.get('history',[]) if h[0]<=l[1]+1e-6]
            vr=vehicles[prior[-1][6]];first=next(z for z in t['legs'] if z[0]==3)
            next_ride=next((z for z in t['legs'][ix+1:] if z[0]==3),None)
            out=vehicles[next_ride[6]]['rid'] if next_ride else 'no_next_ride'
            for k,v in [('building',parent[1]),('approach_route',vr['rid']),('approach_board_node',prior[-1][4]),
                        ('first_board_node',first[4]),('changes_before_law',len(before)),('next_route',out),
                        ('source_first_route',parent[6][0]['rid'] if parent[6] else 'walk')]:groups[k][str(v)]+=weight
            if model=='261116122336':focus[uid]+=weight
            selected[uid]=selected.get(uid,0.)+weight
            if len(examples)<35:
                examples.append({'uid':uid,'parent':t['parent_id'],'weight':weight,'building':parent[1],
                    'source_initial_stages':parent[6],'prefix_history':before,'history':t.get('history'),
                    'prefix_legs':t['legs'][:ix+1], 'next_ride':next_ride,
                    'approach_route':vr['rid'],'next_route':out})
    cases.append({'model':model,'case':r['case']['case'],'at':at,'clock_scope':'own afternoon maximum' if pr else 'latest candidate peak clock',
        'snu_law_queue_weight':all_snu_law,'snu_law_after_prior_bus_weight':all_snu_transfer,
        'groups':{k:dict(v.most_common()) for k,v in groups.items()},'examples':examples,'audit_sha256':r['audit_sha256']})
    del a;gc.collect()
metadata={'routes':{},'nodes':nodes,'route_info_keys':list(common['route_info'][0]) if isinstance(common['route_info'],list) else list(common['route_info'])[:3]}
for rid in ['100100250','100100251','100100253']:
    route=f['prepared']['routes'].get(rid);metadata['routes'][rid]=route
out=ROOT/'law-snu-cohort-trace.json';assert not out.exists()
out.write_text(json.dumps({'scope':'Existing completed weighted fragments only; focused peak cohorts are not matched individual causal trajectories.',
    'cases':cases,'latest_focus_uid_weights':dict(focus),'route_metadata':metadata,'production_writes':False},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps([{k:v for k,v in c.items() if k not in ('examples','audit_sha256')} for c in cases],ensure_ascii=False),flush=True)
