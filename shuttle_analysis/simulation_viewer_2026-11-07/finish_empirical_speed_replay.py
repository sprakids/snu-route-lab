"""Reconcile ten completed empirical speed-reference runs and chart cohorts."""
from pathlib import Path
import csv,gzip,hashlib,json,math,time
import empirical_speed_replay as empirical
import capacity_model as base
import verify_city as independent
from aggregate_half_hour import aggregate,BINS,INTERVAL


def main():
    work,out=empirical.WORK,empirical.OUT
    needed=[work/'run-regular-mon.json',work/'batch-regular_remaining.json',work/'batch-peak_all.json']
    started=time.monotonic()
    while not all(p.exists() for p in needed):
        if time.monotonic()-started>2400:raise TimeoutError('Not all finite replay batches completed')
        time.sleep(5)
    for p in needed:assert json.loads(p.read_text(encoding='utf-8'))['status']=='PASS'
    bundle=empirical.prepare_variant();independent.WORK=work;independent.OUT=out
    checks=[];charts={};halves={};differences=[];sources=[]
    for scenario in base.SCENARIOS:
        charts[scenario]={};halves[scenario]={}
        for day,did in base.DAYS.items():
            result=independent.check(bundle,scenario,day,did);checks.append(result)
            data=independent.read(out/f'{scenario}-{did}.json')
            audit_path=work/f'audit-{scenario}-{did}.json.gz';audit=independent.read(audit_path)
            charts[scenario][did]={k:data[k] for k in ('hourly','daily','report')}
            half=aggregate(audit['waits'],len(data['daily']));halves[scenario][did]=half
            for node,hours in data['hourly'].items():
                for h,row in hours.items():
                    parts=[half[node][str(t)] for t in BINS if t//3600==int(h)]
                    for field in ['arrival_weight','served_weight','switched_weight','unserved_weight','denied_weight']:
                        assert abs(sum(p[field] for p in parts)-row.get(field,0))<1e-5
            old=independent.read(empirical.ROOT/f'public/data/capacity_v5/{scenario}-{did}.json')
            for node,new in data['daily'].items():
                before=old['daily'][node]
                differences.append(dict(scenario=scenario,weekday=did,node=int(node),stop=bundle['prepared']['common']['nodes'][int(node)]['name'],
                    old_arrival_weight=before['arrival_weight'],new_arrival_weight=new['arrival_weight'],
                    old_served_weight=before['served_weight'],new_served_weight=new['served_weight'],
                    old_mean_wait_min=before['mean_wait_min'],new_mean_wait_min=new['mean_wait_min'],
                    mean_wait_delta_min=(new['mean_wait_min']-before['mean_wait_min']) if before['mean_wait_min'] is not None and new['mean_wait_min'] is not None else None,
                    old_queue_exposure_min=before['mean_queue_exposure_min'],new_queue_exposure_min=new['mean_queue_exposure_min'],
                    boarded_denominator_can_change=True,real_world_improvement_validated=False))
            sources.append({'path':audit_path.name,'sha256':empirical.digest(audit_path)})
            print('VERIFIED',scenario,did,flush=True)
    oldcharts=base.read(empirical.ROOT/'public/data/capacity_v5/charts.json')
    base.OUT=out
    base.public('charts.json',{'scenarios':charts,'legacy_wait_charts':oldcharts['legacy_wait_charts'],'adaptive':True,'city_capacity_applied':True})
    base.public('half_hour.json',dict(schema_version=1,interval_seconds=INTERVAL,start_second=base.START,end_second=base.END,
        bin_starts=BINS,grouping='stop arrival, half-open bins [start,end)',mean_denominator='boarded weighted flows; switchers and unserved are separate',
        original_dataset='empirical_road_reference_20261109_v1',scenarios=halves,audit_sources=sources))
    with (work/'wait_before_after_by_stop_day.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,list(differences[0]));writer.writeheader();writer.writerows(differences)
    summary=dict(status='PASS',revision=empirical.REVISION,runs=checks,simulation_runs=10,
        total_input_weight=sum(r['report']['input_weight'] for days in charts.values() for r in days.values()),
        maximum_particle_mass_error=max(r['particle_mass_max_error'] for r in checks),
        original_v5_prepared_unchanged=empirical.digest(empirical.ROOT/'city_bus_model_2026-11-08/prepared.json.gz')==bundle['empirical_input_hashes']['original_prepared'],
        reference_speed_is_empirical=True,weekday_predictive_accuracy_validated=False,
        external_background_passengers_included=False,public_site_updated=False,
        new_clock_requires_queue_release_adapter=True,prefix_clock_changed=False)
    (work/'independent_verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (work/'run_verification.json').write_text(json.dumps({'status':'PASS','runs':[r['report'] for d in charts.values() for r in d.values()]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='runs'}),flush=True)


if __name__=='__main__':main()
