"""Find queue/destination changes behind the small over20 regression."""
from pathlib import Path
from collections import Counter,defaultdict
import csv,gc,gzip,hashlib,json,math
ROOT=Path(__file__).resolve().parent;A=ROOT.parent;G=Path(json.loads((ROOT/'candidate.json').read_bytes())['path']);F=A/'261116122336'
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
def rows(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
allrows={w.name:[r for r in rows(w/'pilot-all-recorded-stops.csv') if not r['case'].startswith('ablation')] for w in [F,G]}
old={(r['weekday'],r['scenario'],r['node']):r for r in allrows[F.name]}
deltas=[]
for r in allrows[G.name]:
    o=old[(r['weekday'],r['scenario'],r['node'])]
    delta=float(r['over20_episode_weight'])-float(o['over20_episode_weight'])
    if abs(delta)>1e-7:deltas.append({'day':r['weekday'],'node':int(r['node']),'stop':r['stop'],
        'over20_before':float(o['over20_episode_weight']),'over20_after':float(r['over20_episode_weight']),'delta':delta})
dest=read(G/'frozen/prepared_capacity44_pair.json.gz')['destination_keys'];groups=[]
for w in [F,G]:
    for r in read(w/'pilot-validation.json')['results']:
        c=r['case']
        if c['case'].startswith('ablation'):continue
        p=Path(r['source_directory'])/f"audit-regular-{'mon' if c['day']=='월' else 'tue'}.json.gz"
        a=read(p);assert hashlib.sha256(p.read_bytes()).hexdigest()==r['audit_sha256']
        counter=Counter();examples=defaultdict(list)
        for v in a['wait_audit']:
            seconds=v['end']-v['arrival']
            if seconds<=1200+1e-7:continue
            d=dest[str(v['parent_id'])];key=(v['node'],d)
            counter[key]+=v['weight']
            if len(examples[key])<4:examples[key].append({k:v.get(k) for k in ['id','parent_id','node','arrival','end','weight','full_passes_seen','entry_forecast','eligibility','student_flexible','student_first_release']})
        groups.append({'model':w.name,'day':c['day'],'raw_visit_scope':'Raw over20 visits; canonical continuous-stop mass is kept in the separate deltas table.',
            'node_destination':[{'node':k[0],'destination':k[1],'weight':v,'examples':examples[k]} for k,v in counter.most_common()]})
        del a;gc.collect()
out=ROOT/'over20-change-diagnosis.json';assert not out.exists()
out.write_text(json.dumps({'canonical_node_deltas':sorted(deltas,key=lambda r:r['delta'],reverse=True),'raw_visit_node_destination':groups,
    'scope':'Completed models only. Diagnosis, not tuning or new field observations.','production_writes':False},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('CANONICAL_NODE_CHANGES',json.dumps(sorted(deltas,key=lambda r:r['delta'],reverse=True)[:20],ensure_ascii=False),flush=True)
print('RAW_DESTINATIONS',json.dumps([{'model':g['model'],'day':g['day'],'groups':[{k:v for k,v in r.items() if k!='examples'} for r in g['node_destination']]} for g in groups],ensure_ascii=False)[:5000],flush=True)
