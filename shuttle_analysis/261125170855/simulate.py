"""Replay the corrected engine against fixed weekday demand and service inventories."""
import argparse
import contextlib
import importlib.util
from pathlib import Path
import sys
import math
import os

HERE=Path(__file__).resolve().parent
PREVIOUS=HERE.parent/'261125164654'
sys.path.insert(0,str(PREVIOUS))
spec=importlib.util.spec_from_file_location('prior_matched_experiment',PREVIOUS/'run.py')
prior=importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
from policy import spread_release, signature
import berth_engine as engine
from verify_berth import check
from operating import apply_stays
field=prior.field

def run(day,service,variant,run_root='runs'):
    key=f'{service}-{day}'
    out=HERE/run_root/variant/key
    out.mkdir(parents=True,exist_ok=True)
    if (out/'summary.json').exists(): return
    weekday=prior.DAYS[day]
    b,_,donors,_=prior.timing.inputs(weekday,service)
    spread_release(b,weekday,donors,prior.timing)
    old=field.read(PREVIOUS/'runs/release'/key/'summary.json')
    assert signature(b,weekday,True)==old['departure_identity']
    card=field.read(HERE/'card_phase.json')
    lag=0 if variant=='berth_only' else card['selected_minutes']
    changed=apply_stays(b,weekday,donors,prior.timing,lag) if lag else 0
    assert signature(b,weekday,False)==old['identity']
    b.update(terminal_service_treatment=True,transitions=field.read(HERE/'terminal_transitions.json'),
             single_line=variant!='parallel')
    if variant.startswith('nov10'):
        assert day=='tue'
        b['dated']='nov10'
        b['arrival_fraction']={'nov10_early':.25,'nov10':.5,'nov10_late':.75}[variant]
        b['pair_observation']=field.read(HERE.parent/'field_observations_2026-11-10/queue_admin_snu_1523.json')
    if variant=='nov24':
        assert day=='tue'
        b['dated']='nov24'
    model='R'+HERE.name
    common=b['prepared']['common']
    common['candidate_id']=common['data_version']=model
    engine.WORK=engine.OUT=engine.base.OUT=out
    with (out/'run.log').open('w',encoding='utf8') as log,contextlib.redirect_stdout(log):
        data=engine.simulate(b,weekday,service)
    valid=check(b,service,weekday,day,out,donors)
    assert valid['status']=='PASS'
    audit=field.read(out/f'audit-{key}.json.gz')
    dist=prior.distribution(prior.physical_waits(audit))
    field.save_json(out/'all_stop_waits.json',dist)
    base=field.read(PREVIOUS/'runs/release'/key/f'{key}.json.gz')
    def inventory(data):
        return {(e[1],e[2],e[11],e[12]):e[3] for e in data['events']}
    assert inventory(base)==inventory(data) and len(base['events'])==len(data['events'])
    for n in (common['hot_nodes']['admin_snu'],common['hot_nodes']['admin_daehak']):
        slots={}
        for node,vid,area,op,dep,clock in data['terminal_presence']:
            if node==n and 15*3600<=clock<19*3600:
                slots.setdefault(clock,[]).append((vid,dep))
        for vids in slots.values():
            assert len(vids)==(2 if n==common['hot_nodes']['admin_snu'] else 1)
            assert len({d for _,d in vids})==1
    rep=data['report']
    assert all(math.isclose(rep[k],old['daily'],abs_tol=1e-6) for k in ('final_weight','input_weight'))
    outdata=dict(model=model,condition=variant,day=day,service=service,daily=old['daily'],
                 identity=old['identity'],departure_identity=signature(b,weekday,True),
                 stay_additional_minutes=lag,stay_affected_weight=changed,checks=valid['checks'],
                 over20_weight=sum(r['over_20_minute_weight'] for r in dist.values()),
                 max_continuous_wait=max(r['max_continuous_wait_min'] for r in dist.values()),
                 unserved=rep['unserved_trip_weight'],capacity_violations=rep['capacity_violations'],
                 terminal_staging_events=sum(op>area for _,_,area,op,_,_ in data['terminal_presence']),
                 **prior.metrics(data,audit,common,day))
    # Where more than one bus intersects a minute, report vehicle-specific
    # loads instead of equating the sum with the reported single bus.
    if day=='tue':
        n=common['hot_nodes']['admin_daehak']; t=field.seconds('15:18')
        outdata['town_vehicle_ranges']=[]
        for node,vid,area,op,dep,clock in data['terminal_presence']:
            if node!=n or not(op<t+60 and dep>t): continue
            events=[[s,total] for s,nd,v,w,total,end in data['preboard_events'] if v==vid]
            curve=field.Curve(events)
            outdata['town_vehicle_ranges'].append(dict(vehicle=vid,op=op,departure=dep,
                     **curve.stats(max(op,t),min(dep,t+60))))
    tmp=out/'summary.tmp'
    field.save_json(tmp,outdata)
    os.replace(tmp,out/'summary.json')
    print(key,variant,outdata['max_continuous_wait'],outdata['unserved'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('day',choices=prior.DAYS)
    p.add_argument('service',choices=('peak','regular'))
    p.add_argument('variant',choices=('candidate','berth_only','parallel','nov10','nov10_early','nov10_late','nov24'))
    a=p.parse_args()
    run(a.day,a.service,a.variant,os.environ.get('SNU_REPLAY_OUTPUT','runs'))
