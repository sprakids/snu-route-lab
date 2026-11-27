"""Read only the frozen predecessor ledgers; no simulation imports or new dates."""
from pathlib import Path
from collections import Counter,defaultdict
import gzip,json,hashlib,math

ROOT=Path(__file__).resolve().parent
BASE=ROOT.parent/'261116010854'
def read(p):
    b=p.read_bytes()
    return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists(),p
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def hh(t):return f'{int(t//3600):02}:{int(t%3600//60):02}:{int(t%60):02}'
def sorted_counts(c,n=20):return [{'key':str(k),'weight':v} for k,v in c.most_common(n)]

f=read(BASE/'frozen/prepared_capacity44_pair.json.gz')
nodes=f['prepared']['common']['nodes'];dest=f['destination_keys']
original={p[0]:p for rows in f['prepared']['plans'].values() for p in rows}
report={'comparison_parent':BASE.name,'nodes':nodes,'cases':[],
        'scope':'Existing model ledgers only; weighted visits, not independent observations or unique students.'}
for path in sorted((BASE/'runs').glob('queuefit-combined-*/attempt_01/audit-*.json.gz')):
    a=read(path);case=path.parents[1].name
    groups=defaultdict(Counter);examples=defaultdict(list)
    personal={r['id']:r['student_patience_seconds'] for r in a['legs']}
    for r in a['wait_audit']:
        w=r['weight'];seconds=r['end']-r['arrival'];uid=r['id'];parent=r['parent_id']
        if seconds<=1200+1e-6:continue
        d=dest[str(parent)];mode='shuttle' if all(x[0].startswith('shuttle') for x in r['eligibility']) else 'city'
        for key,value in [('node',r['node']),('destination',d),('eligibility',tuple(tuple(x) for x in r['eligibility'])),('node_destination',(r['node'],d)),('mode',mode),('full_passes',r['full_passes_seen']),('changes',r['realized_change_count']),('outcome',r['outcome'])]:groups[key][value]+=w
        if uid in personal:groups['within_personal'][seconds<=personal[uid]+1e-6]+=w
        if r['entry_forecast']:
            pred=r['entry_forecast']['first_wait_seconds']
            groups['forecast_error_bin'][math.floor((seconds-pred)/300)*5]+=w
        examples[r['node']].append({**r,'duration_minutes':seconds/60,'destination':d,
            'source_initial_mode':'walk' if not original[parent][6] else ('shuttle' if original[parent][6][0]['rid'].startswith('shuttle') else 'city'),
            'personal_seconds':personal.get(uid)})
    row={'case':case,'source':str(path),'sha256':sha(path),'over20_groups':{k:sorted_counts(v) for k,v in groups.items()},
         'over20_node_examples':{str(k):sorted(v,key=lambda x:x['duration_minutes'],reverse=True)[:5] for k,v in examples.items()}}
    # Find largest physical-stop queue at each law direction, then profile its occupants.
    law=[i for i,n in enumerate(nodes) if str(n.get('arsId',n.get('ars_id',''))) in ('21298','21270') or '법대' in n.get('name','')]
    row['law_peaks']=[]
    for node in law:
        ws=[r for r in a['wait_audit'] if r['node']==node]
        events=[]
        for r in ws:events.extend([(r['arrival'],r['weight']),(r['end'],-r['weight'])])
        q=mx=at=0.
        for t,v in sorted(events,key=lambda z:(z[0],z[1])):
            q+=v
            if q>mx:mx=q;at=t
        present=[r for r in ws if r['arrival']<=at<r['end']]
        counts=defaultdict(Counter)
        for r in present:
            parent=r['parent_id'];source=original[parent];d=dest[str(parent)];w=r['weight']
            initial='walk' if not source[6] else ('shuttle' if source[6][0]['rid'].startswith('shuttle') else 'city')
            for k,v in [('destination',d),('initial_mode',initial),('changes',r['realized_change_count']),('building',source[1]),('eligibility',tuple(tuple(x) for x in r['eligibility'])),('full_passes_at_exit',r['full_passes_seen'])]:counts[k][v]+=w
        row['law_peaks'].append({'node':node,'maximum_queue':mx,'at':at,'clock':hh(at),
            'occupants':{k:sorted_counts(v,12) for k,v in counts.items()},
            'sample':sorted(present,key=lambda r:r['weight'],reverse=True)[:5]})
    report['cases'].append(row)
    print(case,'over20',round(sum(groups['node'].values()),3),'nodes',groups['node'].most_common(4),'law',[(r['node'],round(r['maximum_queue'],2),r['clock']) for r in row['law_peaks']],flush=True)
save(ROOT/'baseline-remaining-diagnosis.json',report)
