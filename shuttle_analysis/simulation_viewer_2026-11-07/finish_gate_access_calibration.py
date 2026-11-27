"""Finish the selected initial-gate candidate and independently reconcile it."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from collections import Counter,defaultdict
import csv, gzip, json, math, subprocess, sys, time

import gate_access_calibration as trial
import capacity_model as base
import verify_city as independent
from aggregate_half_hour import aggregate, BINS, INTERVAL


def run_remaining():
    screen=trial.read(trial.WORK/'screening_results.json');assert screen['status']=='PASS'
    alpha=screen['selected_alpha'];work=trial.folder(alpha)
    jobs=[(scenario,day,did) for scenario in base.SCENARIOS for day,did in base.DAYS.items()]
    def worker(job):
        scenario,day,did=job;receipt=work/f'run-{scenario}-{did}.json'
        if receipt.exists():
            assert trial.read(receipt)['status']=='PASS'
            assert (work/f'public_data/{scenario}-{did}.json').exists()
            assert (work/f'audit-{scenario}-{did}.json.gz').exists()
            print('REUSED',scenario,did,flush=True);return
        log=work/f'full-{scenario}-{did}.log'
        assert not log.exists(),f'Preserve and inspect previous incomplete log: {log}'
        with log.open('w',encoding='utf-8') as f:
            result=subprocess.run([sys.executable,str(trial.ROOT/'gate_access_calibration.py'),'--run',str(alpha),
                                   '--scenario',scenario,'--day',day],stdout=f,stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert result.returncode==0,(scenario,day,str(log))
        print('COMPLETE',scenario,did,flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(worker,jobs))
    verify(alpha)


def verify(alpha):
    work=trial.folder(alpha);out=work/'public_data';bundle=trial.read(work/'prepared.json.gz')
    independent.WORK=work;independent.OUT=out;base.OUT=out
    charts={};halves={};checks=[];diff=[]
    common=bundle['prepared']['common']
    # Preserve the route-stop descriptions used by the existing map.
    frozen_common=trial.read(trial.ROOT/'public/data/capacity_v5/common.json')
    common['city_route_stops']=frozen_common['city_route_stops']
    base.public('common.json',common)
    for scenario in base.SCENARIOS:
        charts[scenario]={};halves[scenario]={}
        for day,did in base.DAYS.items():
            receipt=trial.read(work/f'run-{scenario}-{did}.json');assert receipt['status']=='PASS'
            check=independent.check(bundle,scenario,day,did);checks.append(check)
            data=trial.read(out/f'{scenario}-{did}.json');audit=trial.read(work/f'audit-{scenario}-{did}.json.gz')
            charts[scenario][did]={k:data[k] for k in ('hourly','daily','report')}
            halves[scenario][did]=aggregate(audit['waits'],len(data['daily']))
            for node,hours in data['hourly'].items():
                for hour,row in hours.items():
                    parts=[halves[scenario][did][node][str(t)] for t in BINS if t//3600==int(hour)]
                    for field in ('arrival_weight','served_weight','switched_weight','unserved_weight','denied_weight'):
                        assert abs(math.fsum(p[field] for p in parts)-row.get(field,0))<1e-5
            old=trial.read(trial.ROOT/f'public/data/capacity_v5/{scenario}-{did}.json')
            for node in sorted(set(common['hot_nodes'].values())):
                before=old['daily'][str(node)];after=data['daily'][str(node)]
                diff.append({'scenario':scenario,'weekday':did,'node':node,'stop':common['nodes'][node]['name'],
                             'old_arrival_weight':before['arrival_weight'],'new_arrival_weight':after['arrival_weight'],
                             'old_mean_wait_min':before['mean_wait_min'],'new_mean_wait_min':after['mean_wait_min'],
                             'old_queue_exposure_min':before['mean_queue_exposure_min'],'new_queue_exposure_min':after['mean_queue_exposure_min'],
                             'old_served_weight':before['served_weight'],'new_served_weight':after['served_weight'],
                             'cohort_can_change':True,'real_world_waiting_time_validated':False})
            print('VERIFIED',scenario,did,flush=True)
    oldcharts=trial.read(trial.ROOT/'public/data/capacity_v5/charts.json')
    base.public('charts.json',{'scenarios':charts,'legacy_wait_charts':oldcharts['legacy_wait_charts'],'adaptive':True,'city_capacity_applied':True})
    base.public('half_hour.json',{'schema_version':1,'interval_seconds':INTERVAL,'start_second':base.START,'end_second':base.END,
                                'bin_starts':BINS,'grouping':'stop arrival, half-open bins [start,end)',
                                'mean_denominator':'boarded weighted flows; switchers and unserved are separate',
                                'original_dataset':bundle['gate_access_calibration']['model_id'],'scenarios':halves})
    with (work/'wait_before_after_by_stop_day.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,list(diff[0]));writer.writeheader();writer.writerows(diff)
    before=trial.read(trial.WORK/'protected_source_hashes.json')
    assert before==trial.protected(),'protected original artifacts changed'
    summary={'status':'PASS','model_id':bundle['gate_access_calibration']['model_id'],'alpha':alpha,'simulation_runs':len(checks),
             'runs':checks,'maximum_particle_mass_error':max(r['particle_mass_max_error'] for r in checks),
             'original_artifacts_preserved':len(before),'original_hashes_unchanged':True,
             'same_demand_ids_weights_origins_destinations_departures':True,
             'observations_used_for_selection':3,'independent_empirical_validation':False,
             'waiting_time_or_boarding_probability_validated':False,
             'current_routing_release_retained':True,'collector_unchanged':True}
    trial.save(work/'independent_verification.json',summary)
    trial.save(trial.WORK/'selected_candidate.json',{'status':'PASS','alpha':alpha,'model_id':summary['model_id'],
               'directory':work.relative_to(trial.WORK).as_posix(),'algorithm_id':'provisional_initial_gate_access_v1',
               'empirical_validation_status':'in_sample_fit_only','public_dataset':'capacity_v7','current_default_changed':False})
    print('ALL_VERIFIED',summary['model_id'],flush=True)


if __name__=='__main__':
    run_remaining()
