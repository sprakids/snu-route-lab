"""Historical R replay of one arriving shuttle. The passenger count is evaluation-only."""
import argparse
from bisect import bisect_left
import contextlib
import math
from pathlib import Path
import runpy
import sys

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'261124160531'
sys.path[:0]=[str(BASE),str(BASE/'report'),str(HERE.parent/'return_dwell_review_2026-11-24')]
from timing_inputs import inputs, ref
from verify_candidate import check
import return_engine as engine
report=runpy.run_path(str(BASE/'report'/'compare.py'))
Curve,read,save_json,seconds=(report[k] for k in ('Curve','read','save_json','seconds'))


def run(service, bound, paired):
    field=read(HERE/'boarding_admin_snu_1600.json')
    source=read(HERE/'arrival_trace.json')
    assert field['observation_date']==source['day']=='2026-11-25' and len(source['matches'])==1
    trace=source['matches'][0]
    stamp=seconds(field['reported_time'])
    lo,hi=trace['arrival']
    opened={'mid':(lo+hi)/2,'early':lo,'late':hi}[bound]
    baseline=read(BASE/'viewer-data'/f'{service}-wed.json.gz')
    common=read(BASE/'viewer-data/common.json.gz')
    node=common['hot_nodes'][field['simulation_stop_key']]
    slots=sorted({dep for n,_,_,dep,_ in baseline['door_windows'] if n==node})
    if trace['departure']:
        dep=sum(trace['departure'])/2
        slot=min(slots,key=lambda t:abs(t-dep))
        timing='departure_bracket_midpoint'
    else:
        last=trace['points'][-1][0]
        assert last>=stamp+60
        slot=next(t for t in slots if t>last)
        dep=slot
        timing='provisional_next_planned_slot_after_last_positive_poll'
    assert dep>opened
    bundle,_,donors,_=inputs('수',service)
    bundle['snu_return_visits']={slot:dict(arrival=opened,departure=dep,vehicle='observed_approach')}
    if paired:
        bundle['snu_paired_departures']={slot:dep}
    out=HERE/'runs'/(f'{service}-{bound}-paired' if paired else f'{service}-{bound}')
    out.mkdir(parents=True,exist_ok=True)
    engine.WORK=engine.OUT=engine.base.OUT=out
    with (out/'run.log').open('w',encoding='utf8') as log, contextlib.redirect_stdout(log):
        data=engine.simulate(bundle,'수',service)
    verified=check(bundle,service,'수','wed',out,donors)
    assert verified['status']=='PASS' and len(data['observed_return_vehicles'])==1
    vid=next(iter(data['observed_return_vehicles']))
    windows=lambda d:{v:(o,t,cap) for n,v,o,t,cap in d['door_windows'] if n==node}
    old,new=windows(baseline),windows(data)
    mates=[v for v in old if v!=vid and old[v][1]==slot]
    assert len(mates)==1
    mate=mates[0]
    changed={vid,mate} if paired else {vid}
    assert old.keys()==new.keys() and all(new[v]==old[v] for v in old if v not in changed)
    if paired:
        assert new[mate][1:]==(dep,44) and math.isclose(new[mate][0]-old[mate][0],dep-slot,abs_tol=1e-6)
    assert old[vid][1]==slot and math.isclose(new[vid][0],opened,abs_tol=1e-6) and new[vid][1:]==(dep,44)
    key=lambda e:(e[1],e[2],e[11],e[12])
    before={key(e):e for e in baseline['events']}
    after={key(e):e for e in data['events']}
    assert len(before)==len(baseline['events'])==len(data['events']) and before.keys()==after.keys()
    for k,e in before.items():
        assert after[k][3]==e[3]
        if e[2] not in changed:
            assert e[0]==after[k][0]
        elif paired and e[2]==mate:
            assert math.isclose(after[k][0],e[0]+dep-slot,abs_tol=1e-6)
    q=Curve(data['queue_timeline'][node])
    bq=Curve(baseline['queue_timeline'][node])
    prior_idx=bisect_left(q.times,round(opened,3))-1
    audit=ref.load(out/f'audit-{service}-wed.json.gz')
    pre=sum(w['weight'] for w in audit['wait_audit'] if w['node']==node and w['arrival']<opened<=w['end'])
    assert math.isclose(pre,q.levels[prior_idx] if prior_idx>=0 else 0,abs_tol=.005)
    board=sum(e[3] for e in data['preboard_events'] if e[2]==vid and math.isclose(e[0],opened,abs_tol=1e-7,rel_tol=0))
    count=field['outside_queue_before_boarding']
    r=data['report']
    assert r['input_weight']==baseline['report']['input_weight'] and r['unserved_trip_weight']==r['capacity_violations']==0
    save_json(out/'comparison.json',dict(model='R261124160531 with dated arrival',day=source['day'],service=service,
        door_time_variant=bound,opening=opened,scheduled_anchor=slot,departure_used=dep,departure_basis=timing,
        window=[stamp,stamp+60],measured_before_boarding=count,
        baseline_outside_minute=bq.stats(stamp,stamp+60),replay_outside_minute=q.stats(stamp,stamp+60),
        outside_just_before_open=pre,boarded_at_open=board,observer_exact_wait_s=field['exact_wait_seconds'],
        paired=paired,mate_departure=new[mate][1],mate_capacity=new[mate][2],
        tracked_vehicle_count=1,demand=r['input_weight'],unserved=r['unserved_trip_weight'],
        capacity_violations=r['capacity_violations'],fifo_checks=verified['checks']['terminal_fifo_tickets'],
        max_outside_wait_min=max((w['end']-w['physical_stop_entry'])/60 for w in audit['wait_audit'])))
    print(service,bound,round(pre,2),round(board,2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('service',choices=('peak','regular'))
    p.add_argument('bound',choices=('mid','early','late'))
    p.add_argument('--paired',action='store_true')
    args=p.parse_args()
    run(args.service,args.bound,args.paired)
