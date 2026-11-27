"""Full recorded queue profiles, grouping simultaneous changes before measuring peaks."""
from pathlib import Path
from collections import defaultdict,Counter
import json,gzip,csv,hashlib,sys,math
w=Path(sys.argv[1]).resolve();out=w/'grid-stop-queue-exposure.csv';assert not out.exists()
def read(p):return json.loads(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
f=read(w/'frozen/prepared_capacity44_pair.json.gz');nodes=f['prepared']['common']['nodes'];rows=[];prediction_audits=[]
days={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}
for r in read(w/'grid-validation.json')['results']:
    c=r['case'];path=Path(r['source_directory'])/f"audit-{c['scenario']}-{days[c['day']]}.json.gz"
    assert hashlib.sha256(path.read_bytes()).hexdigest()==r['audit_sha256'];a=read(path);events=defaultdict(Counter)
    for v in a['wait_audit']:
        events[v['node']][v['arrival']]+=v['weight'];events[v['node']][v['end']]-=v['weight']
    model_predictions=unknown=decision_mass=0.;checked=0
    for decision in a['behavior_decisions']:
        p=decision['perceived_prediction'];physical=decision['physical_prediction'];at=decision['time']
        assert abs(p['eta']-at-sum(p[k] for k in ['walk','wait','ride','prep']))<1e-5
        if physical is None:
            assert decision['new_eta'] is None;unknown+=decision['weight']
        else:
            assert abs(physical['eta']-at-sum(physical[k] for k in ['walk','wait','ride','prep']))<1e-5
            assert physical['eta']==decision['new_eta'];model_predictions+=decision['weight']
        decision_mass+=decision['weight'];checked+=1
    prediction_audits.append({'case':c['case'],'change_records_checked':checked,'change_visit_weight':decision_mass,
        'full_operational_forecast_weight':model_predictions,'unknown_operational_forecast_weight':unknown,
        'perceived_eta_never_substituted_for_unknown_operational_eta':True})
    begin=len(rows)
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
    queue_area=math.fsum(x['queue_person_minutes'] for x in rows[begin:])
    q=r['extended_diagnostics']['finished_trip_quantiles']['cumulative_wait_min']['mean'];mass=r['scope']['all']['weight']
    assert abs(queue_area-q*mass)<1e-4,(c['case'],queue_area,q*mass)
    print('FULL_QUEUE_PROFILE',c['case'],flush=True)
assert len(rows)==990
with out.open('x',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,list(rows[0]));writer.writeheader();writer.writerows(rows)
audit=w/'prediction-information-audit.json';assert not audit.exists()
audit.write_text(json.dumps({'status':'PASS','cases':prediction_audits,'scope':'Choice perception vs operational forecast vs actual physical queue area are separate; no independent field validation.'},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
