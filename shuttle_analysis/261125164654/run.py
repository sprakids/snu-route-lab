"""Run a matched research R and collect the same observation metrics for each treatment."""
import argparse
import contextlib
import json
import math
import msvcrt
import os
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / '261124160531'
sys.path.insert(0,str(BASE))
import timing_inputs as timing
from run_integrated import physical_waits, distribution
from policy import signature, spread_release, TEMPLATE
import terminal_engine
from verify_terminal import check
sys.path.insert(0,str(BASE/'report'))
import compare as field

DAYS = dict(zip(('mon','tue','wed','thu','fri'),'월화수목금'))
CONDS = ('baseline','supply','release','combined')

def cohort(data, audit, node, minute):
    t = field.seconds(minute)
    events = sorted((e for e in data['events'] if e[1]==node),key=lambda e:(e[0],e[2]))
    departures = {e[2]:e[0] for e in events}
    ready = [(r['physical_stop_entry'],r['vehicle'],r['weight']) for r in audit['wait_audit']
             if r['node']==node and t<=r['physical_stop_entry']<t+60 and r['outcome']=='boarded']
    # Count actual joiners who later board and catch the next scheduled departure
    # group (includes boarding a vehicle that is already waiting with open doors).
    first = sum(w for entry,vid,w in ready
                if departures[vid]==next(e[0] for e in events if e[0]>=entry))
    return dict(boarded_cohort=sum(w for _,_,w in ready),next_departure_group=first,
                **field.riders(audit,data['events'],node,t))

def metrics(data,audit,common,did):
    records=field.field_records()
    hot=common['hot_nodes']
    outside={k:field.Curve(data['queue_timeline'][n]) for k,n in hot.items()}
    items={}
    for oid,day,k,minute,kind,span in records['records']:
        if day!=did:
            continue
        t=field.seconds(minute)
        n=hot[k]
        if kind=='outside':
            stats=outside[k].stats(t,t+60,span)
            field.audit_counts(audit,data,n,kind,t,t+60,stats['mean'])
        else:
            # Field record is a snapshot on a single bus. With overlapping
            # windows an operator/patient identifier would be needed.
            vehicles=[v for node,v,op,dep,_ in data['door_windows']
                      if node==n and op<t+60 and dep>t]
            if len(vehicles)!=1:
                items[oid]=dict(kind=kind,stop=k,minute=minute,observed=span,
                                matched=False,overlapping_vehicles=len(vehicles))
                continue
            stats=field.onboard_series(data,n).stats(t,t+60,span)
            assert any(e[2]==vehicles[0] and e[1]==n and abs(e[4]-e[5])<1e-6 for e in data['events'])
            field.audit_counts(audit,data,n,kind,t,t+60,stats['mean'])
        items[oid]=dict(kind=kind,stop=k,minute=minute,observed=span,matched=True,**stats)
    windows=[]
    if did=='tue':
        for k in ('admin_snu','admin_daehak'):
            n=hot[k]
            for lo in range(field.seconds('14:48'),field.seconds('15:48'),300):
                hi=lo+300
                arrivals=math.fsum(r['weight'] for r in audit['wait_audit'] if r['node']==n and lo<=r['arrival']<hi)
                windows.append(dict(stop=k,time=field.hhmm(lo),arrivals=arrivals,
                     outside=outside[k].stats(lo,hi)['mean'],
                     aboard=field.onboard_series(data,n).stats(lo,hi)['mean']))
    extras={}
    for day,minute in [('mon','12:20'),('tue','15:23'),('wed','16:00')]:
        if day==did:
            n=hot['admin_snu']
            info=cohort(data,audit,n,minute)
            info['doors_opened_within_minute']=sum(1 for node,_,op,_,_ in data['door_windows']
                    if node==n and field.seconds(minute)<=op<field.seconds(minute)+60)
            extras[minute]=info
    if did=='mon':
        k='admin_daehak'
        extras['16:59']=field.boarding_detail(data,audit,'residual',hot[k],outside[k],field.seconds('16:59'))
    return dict(observations=items,windows=windows,episodes=extras)

def run(did,service,treatments):
    day=DAYS[did]
    name=f'{service}-{did}'
    b,_,donors,_=timing.inputs(day,service)
    common=b['prepared']['common']
    daily=b['prepared']['expected'][day]
    olddir=BASE/'runs'/name/'attempt-01'
    baseline=field.read(olddir/f'{name}.json.gz')
    baseline_supply={(e[1],e[2],e[11],e[12]):e[3] for e in baseline['events']}
    original=b['prepared']['plans'][day]
    frozen=signature(b,day,False)
    for condition in treatments:
        dest=HERE/'runs'/condition/name
        dest.mkdir(parents=True,exist_ok=True)
        path=dest/'summary.json'
        if path.exists():
            continue
        b['prepared']['plans'][day]=original.copy()
        changed=spread_release(b,day,donors,timing) if condition in ('release','combined') else 0
        assert signature(b,day,False)==frozen
        treatment=condition in ('supply','combined')
        b['terminal_service_treatment']=treatment
        if condition=='baseline':
            data=baseline
            audit=field.read(olddir/f'audit-{name}.json.gz')
            old=field.read(olddir/'result.json')
            quality={k:old[k] for k in ('max_continuous_wait','over20_weight','unserved','capacity_violations')}
        else:
            common['candidate_id']=common['data_version']='R'+HERE.name
            terminal_engine.WORK=terminal_engine.OUT=terminal_engine.base.OUT=dest
            with (dest/'run.log').open('w',encoding='utf8') as log, contextlib.redirect_stdout(log):
                data=terminal_engine.simulate(b,day,service)
            valid=check(b,service,day,did,dest,donors)
            assert valid['status']=='PASS'
            audit=field.read(dest/f'audit-{name}.json.gz')
            dist=distribution(physical_waits(audit))
            field.save_json(dest/'all_stop_waits.json',dist)
            quality=dict(max_continuous_wait=max(r['max_continuous_wait_min'] for r in dist.values()),
                         over20_weight=math.fsum(r['over_20_minute_weight'] for r in dist.values()),
                         unserved=data['report']['unserved_trip_weight'],capacity_violations=data['report']['capacity_violations'],
                         checks=valid['checks'])
        supply={(e[1],e[2],e[11],e[12]):e[3] for e in data['events']}
        assert supply==baseline_supply and len(supply)==len(data['events'])
        assert math.isclose(data['report']['input_weight'],daily,abs_tol=1e-6)
        assert math.isclose(data['report']['final_weight'],daily,abs_tol=1e-6)
        assigned=data.get('return_template_assignments',[])
        out=dict(model='R'+(BASE.name if condition=='baseline' else HERE.name),condition=condition,
                 day=did,service=service,daily=daily,identity=frozen,departure_identity=signature(b,day,True),
                 changed_sections=changed,mapped_dwells=dict(Counter(r[1] for r in assigned if r[-1])),
                 source_day=TEMPLATE[day] if treatment else None,
                 time_limited_departures=len(data.get('time_limited_departures',[])),
                 **quality,**metrics(data,audit,common,did))
        field.save_json(path.with_suffix('.tmp'),out)
        os.replace(path.with_suffix('.tmp'),path)
        print(name,condition,'verified',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('day',choices=DAYS)
    p.add_argument('service',choices=('peak','regular'))
    p.add_argument('treatments',nargs='+',choices=CONDS)
    a=p.parse_args()
    lockdir=HERE/'runs'/'locks'
    lockdir.mkdir(parents=True,exist_ok=True)
    with (lockdir/f'{a.service}-{a.day}.lock').open('a+b') as lock:
        if lock.tell()==0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        while True:
            try:
                msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
                break
            except OSError:
                time.sleep(2)
        if not all((HERE/'runs'/c/f'{a.service}-{a.day}'/'summary.json').exists() for c in a.treatments):
            run(a.day,a.service,a.treatments)
