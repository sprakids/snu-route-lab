"""Full recorded queue profiles, grouping simultaneous changes before measuring peaks."""
from pathlib import Path
from collections import defaultdict,Counter
import json,gzip,csv,hashlib,sys,math
w=Path(sys.argv[1]).resolve();out=w/'grid-stop-queue-exposure.csv';assert not out.exists()
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
f=read(w/'frozen/prepared_capacity44_pair.json.gz');nodes=f['prepared']['common']['nodes'];rows=[]
days={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}
for r in read(w/'grid-validation.json')['results']:
    c=r['case'];path=Path(r['source_directory'])/f"audit-{c['scenario']}-{days[c['day']]}.json.gz"
    assert hashlib.sha256(path.read_bytes()).hexdigest()==r['audit_sha256'];a=read(path);events=defaultdict(Counter)
    for v in a['wait_audit']:
        events[v['node']][v['arrival']]+=v['weight'];events[v['node']][v['end']]-=v['weight']
    for node,n in enumerate(nodes):
        changes=sorted(events[node].items());q=mx=at=above=run=longest=area=0.
        for i,(t,delta) in enumerate(changes):
            q+=delta;end=changes[i+1][0] if i+1<len(changes) else t
            assert q>=-1e-5
            if end-t<=1e-7:continue
            if q>mx:mx=q;at=t
            area+=q*(end-t)
            if q>40+1e-7:above+=end-t;run+=end-t;longest=max(run,longest)
            else:run=0.
        assert abs(q)<1e-5,(node,q)
        rows.append({'case':c['case'],'weekday':c['day'],'scenario':c['scenario'],'node':node,'stop':n['name'],'ars':n.get('ars',''),
            'maximum_queue':mx,'peak_seconds':at,'peak_kst':f'{int(at//3600):02}:{int(at%3600//60):02}:{at%60:06.3f}',
            'minutes_above40_recollection_reference':above/60,'longest_spell_above40_minutes':longest/60,
            'queue_person_minutes':area/60,'scope':'all recorded arrivals and exits;40 reference is a recollection, not a capacity or field cap'})
    print('FULL_QUEUE_PROFILE',c['case'],flush=True)
assert len(rows)==990
with out.open('x',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,list(rows[0]));writer.writeheader();writer.writerows(rows)
