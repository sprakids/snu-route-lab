"""Independent release comparison and a conditional FIFO replay of the uncertain prior bus."""
import bisect
import csv
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent/'261125164654'
sys.path.insert(0,str(HERE.parent/'261124160531/report'))
from compare import Curve,read,save_json,seconds

DAYS=('mon','tue','wed','thu','fri')
SERVICES=('regular','peak')
def table(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def gap_bounds():
    """Replay the one disputed prior pickup while keeping arrivals/other paths fixed.

    Transfers to the observed next vehicle retain their FIFO priority by ready
    time. The no-pickup endpoint assumes all of this small cohort stay. It is
    a sensitivity endpoint, not an assertion of a cancellation or a probability.
    """
    k='peak-tue'
    folder=HERE/'runs/nov24'/k
    audit=read(folder/f'audit-{k}.json.gz')
    data=read(folder/f'{k}.json.gz')
    n=read(PRIOR/'viewer-data/common.json.gz')['hot_nodes']['admin_daehak']
    t=seconds('15:18')
    visits=read(PRIOR/'validation_samples.json')['2026-11-24']['visits']
    match=[v for v in visits if v['route']=='41843' and v['arrival'][1]<=t<v['departure'][0]]
    assert len(match)==1
    dep=sum(match[0]['departure'])/2
    target=[(v,o,d) for node,v,o,d,cap in data['door_windows'] if node==n and abs(d-dep)<.01]
    assert len(target)==1
    v,op,dep=target[0]
    prior=sorted((d,vid) for node,vid,o,d,_ in data['door_windows'] if node==n and d<dep)[-1]
    source=read(HERE/'terminal_transitions.json')['2026-11-24']['routes']['41843']['events']
    earlier=[e for e in source if e['type']=='exit' and sum(e['interval'])/2 < op]
    prior_trace=max(earlier,key=lambda e:sum(e['interval']))
    assert prior_trace['interval'][1]<prior[0]<op
    # Use exact rows from the original FIFO ledger; split weights can share an ID.
    ev=[w for w in audit['wait_audit'] if w['node']==n and w['outcome']=='boarded'
        and w['vehicle'] in (v,prior[1])]
    counts={}
    for include in (False,True):
        rows=sorted((w['ready'],w['ticket'],w['weight']) for w in ev if include or w['vehicle']==v)
        i=0;remaining=0.;loaded=0.;now=op;series=[]
        while (i<len(rows) or remaining>1e-7) and loaded<44-1e-7:
            if remaining<1e-7:
                now=max(now,rows[i][0])
            now+=2
            if now>=dep:break
            while i<len(rows) and rows[i][0]<=now:
                remaining+=rows[i][2];i+=1
            gain=min(remaining,1.,44-loaded)
            loaded+=gain;remaining-=gain
            series.append((now,loaded))
        counts['retain_previous_riders' if include else 'as_scheduled']=Curve(series).stats(t,t+60)
    actual=Curve([[s,load] for s,_,vid,_,load,_ in data['preboard_events'] if vid==v]).stats(t,t+60)
    assert abs(actual['mean']-counts['as_scheduled']['mean'])<.01,(actual,counts)
    return dict(assumed_all_stay=True,prior_vehicle_weight=sum(w['weight'] for w in ev if w['vehicle']==prior[1]),
        observed_prior_exit=prior_trace['interval'],uncertain_scheduled_departure=prior[0],
        measured_vehicle_id_unknown=True,observed_next_departure=match[0]['departure'],
        next_vehicle_arrival_area=match[0]['arrival'],open=op,modeled_departure=dep,minute=counts)

def card_recheck():
    c=read(HERE/'card_phase.json')
    scope=read(HERE.parent/'seoul_boardings_2026-11-10/stop_scope.json')
    inside={s['stop_id'] for s in scope['stops'] if s['zone'] in ('campus_core','campus_annex')}
    nodes=read(PRIOR/'viewer-data/common.json.gz')['nodes']
    ids=set(c['stops'])
    folder=HERE/'runs/candidate/regular-thu'
    data=read(folder/'regular-thu.json.gz')
    audit=read(folder/'audit-regular-thu.json.gz')
    ev={(e[2],e[0]):e for e in data['events']}
    new=[0.]*288
    for r in audit['legs']:
        for mode,start,end,path,node,_,v,*_ in r['legs']:
            if mode!=3 or not nodes[node].get('city') or nodes[node]['stop_id'] not in ids:continue
            event=ev.get((v,end))
            if event is not None and nodes[event[1]]['stop_id'] not in inside:
                new[int(start//300)]+=r['weight']
    out={}
    for k in ('train_hours','validation_hours'):
        def score(ys):
            gaps=[]
            for h in c[k]:
                x=[sum(c['measured'][12*h+i:12*h+i+3]) for i in (0,3,6,9)]
                y=[sum(ys[12*h+i:12*h+i+3]) for i in (0,3,6,9)]
                if sum(x) and sum(y):gaps.extend(abs(a/sum(x)-b/sum(y)) for a,b in zip(x,y))
            return statistics.mean(gaps)
        out[k]={'old':score(c['modeled']),'candidate':score(new)}
    return out


def dated_pair(variant):
    key='peak-tue'
    folder=HERE/'runs'/variant/key
    data=read(folder/f'{key}.json.gz')
    audit=read(folder/f'audit-{key}.json.gz')
    node=read(PRIOR/'viewer-data/common.json.gz')['hot_nodes']['admin_snu']
    stamp=seconds('15:23')
    # Minute midpoint plus the reported relative durations.
    dep=stamp+30+189+30
    pair=sorted(v for n,v,area,op,d,clock in data['terminal_presence'] if n==node and abs(d-dep)<.01)
    assert len(pair)==2
    rows=[w for w in audit['wait_audit'] if w['node']==node and w['outcome']=='boarded'
          and stamp<=w['physical_stop_entry']<stamp+60]
    boarded=[w for w in rows if w['vehicle']==pair[1]]
    wait=[w['end']-w['physical_stop_entry'] for w in boarded]
    return dict(cohort_boarded_here=sum(w['weight'] for w in rows),
                first_vehicle=sum(w['weight'] for w in rows if w['vehicle']==pair[0]),
                second_vehicle=sum(w['weight'] for w in boarded),
                second_vehicle_outside_s=[min(wait),max(wait)] if wait else [],
                second_vehicle_aboard_s=[min(dep-w['end'] for w in boarded),max(dep-w['end'] for w in boarded)] if wait else [])

def main():
    rows=[]; checks=[]; windows=[]; residuals=[];events=[];cohorts=[]
    for d in DAYS:
        for s in SERVICES:
            k=f'{s}-{d}'
            for label,folder in [('release',PRIOR/'runs/release'),('combined',PRIOR/'runs/combined'),('candidate',HERE/'runs/candidate')]:
                obj=read(folder/k/'summary.json')
                checks.append({key:obj[key] for key in ('day','service','condition','daily','over20_weight','max_continuous_wait','unserved','capacity_violations')})
                for key,r in obj['observations'].items():
                    rows.append(dict(source=key,day=d,service=s,condition=label,kind=r['kind'],minute=r['minute'],stop=r['stop'],
                       measured='~'.join(map(str,dict.fromkeys(r['observed']))),mean=r.get('mean'),low=r.get('minimum'),high=r.get('maximum'),
                       abs_error=r.get('expected_abs_error')))
                windows.extend(dict(service=s,condition=label,**x) for x in obj['windows'])
                if d=='mon':
                    residuals.extend(dict(service=s,condition=label,**x) for x in obj['episodes']['16:59'])
                for t,ep in obj['episodes'].items():
                    if isinstance(ep,dict):
                        cohorts.append(dict(day=d,service=s,condition=label,time=t,boarded=ep['boarded_cohort'],
                            first_departure=ep['next_departure_group'],same_minute=ep['same_minute_boards_mass'],
                            median_wait_seconds=(ep.get('outside_s') or {}).get('median')))
                if label=='candidate' and d in ('mon','tue','wed'):
                    data=read(folder/k/f'{k}.json.gz')
                    hot=read(PRIOR/'viewer-data/common.json.gz')['hot_nodes']
                    minutes={'mon':['16:53'],'tue':['15:18','15:23'],'wed':['16:00']}[d]
                    for minute in minutes:
                        stamp=seconds(minute); n=hot['admin_snu']
                        relevant=[(vid,a,op,dep) for node,vid,a,op,dep,_ in data['terminal_presence']
                                  if node==n and a<stamp+60 and dep>stamp]
                        def maximum(pos):
                            times=[stamp,*[r[pos] for r in relevant if stamp<r[pos]<stamp+60]]
                            return max(sum(r[pos]<=t<r[3] for r in relevant) for t in times)
                        events.append(dict(day=d,service=s,minute=minute,area_max=maximum(1),boarding_max=maximum(2)))
    table(HERE/'현장비교.csv',rows);table(HERE/'평일검증.csv',checks);table(HERE/'5분별_유입과_대기.csv',windows)
    table(HERE/'앞배차_출발후_잔여.csv',residuals);table(HERE/'개인승차_비교.csv',cohorts)
    scores={s:{c:statistics.mean(r['abs_error'] for r in rows if r['condition']==c and r['service']==s and r['kind']=='outside')
              for c in ('release','combined','candidate')} for s in SERVICES}
    dated={}
    for v in ('berth_only','parallel','nov10','nov10_early','nov10_late','nov24'):
        r=read(HERE/'runs'/v/'peak-tue/summary.json')
        dated[v]={k:r[k] for k in ('episodes','observations','town_vehicle_ranges','daily','over20_weight','unserved','capacity_violations')}
        if v.startswith('nov10'):
            dated[v]['observed_pair_joiners']=dated_pair(v)
    save_json(HERE/'검증결과.json',dict(scores=scores,card=card_recheck(),berths=events,
              prior_bus=gap_bounds(),scenarios=dated))
    print(scores)

if __name__=='__main__':main()
