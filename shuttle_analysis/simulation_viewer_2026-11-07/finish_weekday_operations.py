"""Independently verify the new clocks, then derive complete weekday charts."""
from collections import defaultdict
from pathlib import Path
import csv, gzip, importlib.util, json, math
import capacity_model as base
import weekday_operations as operations
from aggregate_half_hour import aggregate, BINS, INTERVAL

WORK, OUT = operations.WORK, operations.OUT


def checker():
    source=(operations.ROOT/'verify_city.py').read_text(encoding='utf-8')
    old="""            index=info['segments'].index(legs[0][2])
            clock=legs[0][0]-info['offsets'][index]+info['offsets'][info['anchor']]-info['origin_to_modeled_first_stop_seconds']
            assert min(abs(clock-t) for t in planned_departures(info['plan']))<1e-5
            checks['planned_city_departures']+=1"""
    new="""            route=common['city_operations']['routes'][rid]
            day_index=list(base.DAYS).index(day)
            assert min(abs(legs[0][0]-t) for t in route['departures'][str(day_index)])<1e-5
            # Recompute the complete clock independently from the numeric contract.
            times=[legs[0][0]]
            import bisect as clock_bisect
            profiles=route['segment_profiles'][str(day_index)]
            boundaries=[p[0] for p in profiles]
            for k in range(len(route['stops'])-1):
                j=max(0,min(len(profiles)-1,clock_bisect.bisect_right(boundaries,times[-1])-1))
                times.append(times[-1]+profiles[j][2][k])
            for k,(a,b,pid,load) in enumerate(legs):
                assert pid==info['segments'][k]
                assert abs(a-times[k])<1e-5 and abs(b-times[k+1])<1e-5
            checks['audited_city_departures']+=1"""
    assert old in source;source=source.replace(old,new,1)
    target=WORK/'verification_engine.py'
    if target.exists():assert target.read_text(encoding='utf-8')==source
    else:target.write_text(source,encoding='utf-8')
    spec=importlib.util.spec_from_file_location('weekday_operations_verification',target)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.WORK=WORK;module.OUT=OUT;return module


def csvout(name, rows):
    with (WORK/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)


def checked_run(independent,bundle,scenario,day,did):
    inputs={p.name:operations.sha(p) for p in [WORK/'prepared.json.gz',WORK/'verification_engine.py',
            WORK/f'audit-{scenario}-{did}.json.gz',OUT/f'{scenario}-{did}.json']}
    target=WORK/f'verified-{scenario}-{did}.json'
    if target.exists():
        previous=operations.read(target);assert previous['inputs']==inputs
        return previous['check']
    result=independent.check(bundle,scenario,day,did)
    operations.save(target,{'inputs':inputs,'check':result})
    return result


def main():
    read=operations.read;bundle=operations.prepare();common=bundle['prepared']['common'];base.OUT=OUT
    oldbundle=read(operations.SOURCE)
    assert bundle['prepared']['plans']==oldbundle['prepared']['plans']
    assert bundle['alternatives']==oldbundle['alternatives']
    assert bundle['walk_scales']==oldbundle['walk_scales']
    for rid,info in common['route_info'].items():
        old=oldbundle['prepared']['common']['route_info'][rid]
        if not info.get('city'):assert info==old
        else:assert info['capacity']==old['capacity']
    independent=checker();checks=[];charts={};halves={};stop_comparison=[];daily_comparison=[];sources=[]
    previous=read(operations.ROOT/'gate_access_calibration_2026-11-09/candidates/alpha_075/independent_verification.json')
    previous_summaries={(r['scenario'],r['weekday'],s['scope']):s for r in previous['runs'] for s in r['summaries']}
    # Supplement UI metadata without altering the model's clocks.
    frozen=read(operations.ROOT/'public/data/capacity_v7/common.json')
    common['city_services']=[{**next(x for x in frozen['city_services'] if x['route_id']==r['route_id']),**r} for r in common['city_services']]
    base.public('common.json',common)
    for scenario in base.SCENARIOS:
        charts[scenario]={};halves[scenario]={}
        for day,did in base.DAYS.items():
            assert read(WORK/f'run-{scenario}-{did}.json')['status']=='PASS'
            check=checked_run(independent,bundle,scenario,day,did);checks.append(check)
            data=read(OUT/f'{scenario}-{did}.json'); audit=read(WORK/f'audit-{scenario}-{did}.json.gz')
            charts[scenario][did]={k:data[k] for k in ('hourly','daily','report')}
            half=aggregate(audit['waits'],len(common['nodes']));halves[scenario][did]=half
            for node,hours in data['hourly'].items():
                for hour,row in hours.items():
                    pieces=[half[node][str(t)] for t in BINS if t//3600==int(hour)]
                    for field in ('arrival_weight','served_weight','switched_weight','unserved_weight','denied_weight'):
                        assert abs(math.fsum(p[field] for p in pieces)-row.get(field,0))<1e-5
            for s in check['summaries']:
                old=previous_summaries[scenario,day,s['scope']]
                assert abs(old['weight']-s['weight'])<1e-5
                daily_comparison.append({'scenario':scenario,'weekday':day,'scope':s['scope'],'fixed_cohort_weight':s['weight'],
                    'old_cumulative_wait_min':old['mean_cumulative_wait_min'],'new_cumulative_wait_min':s['mean_cumulative_wait_min'],
                    'wait_delta_min':s['mean_cumulative_wait_min']-old['mean_cumulative_wait_min'],
                    'old_total_time_completed_min':old['mean_class_end_total_min_completed'],
                    'new_total_time_completed_min':s['mean_class_end_total_min_completed'],
                    'old_completed_weight':old['completed_weight'],'new_completed_weight':s['completed_weight'],
                    'old_unserved_weight':old['unserved_weight'],'new_unserved_weight':s['unserved_weight'],
                    'real_wait_accuracy_validated':False})
            old=read(operations.ROOT/f'public/data/capacity_v7/{scenario}-{did}.json')
            for key in ('admin_snu','engineering_302','city_gate','city_120000195'):
                if key not in common['hot_nodes']:continue
                node=str(common['hot_nodes'][key]);before=old['daily'][node];after=data['daily'][node]
                stop_comparison.append({'scenario':scenario,'weekday':day,'stop_key':key,
                    'old_arrival_weight':before['arrival_weight'],'new_arrival_weight':after['arrival_weight'],
                    'old_boarded_wait_min':before['mean_wait_min'],'new_boarded_wait_min':after['mean_wait_min'],
                    'old_all_queue_exposure_min':before['mean_queue_exposure_min'],'new_all_queue_exposure_min':after['mean_queue_exposure_min'],
                    'old_served_weight':before['served_weight'],'new_served_weight':after['served_weight'],
                    'stop_cohort_can_change':True})
            sources.append({'path':f'audit-{scenario}-{did}.json.gz','sha256':operations.sha(WORK/f'audit-{scenario}-{did}.json.gz')})
            print('VERIFIED',scenario,did,flush=True)
    oldcharts=read(operations.ROOT/'public/data/capacity_v7/charts.json')
    base.public('charts.json',{'scenarios':charts,'legacy_wait_charts':oldcharts['legacy_wait_charts'],
        'adaptive':True,'city_capacity_applied':True,'operations_revision':operations.REVISION})
    base.public('half_hour.json',{'schema_version':1,'interval_seconds':INTERVAL,'start_second':base.START,'end_second':base.END,
        'bin_starts':BINS,'grouping':'stop arrival, half-open bins [start,end)',
        'mean_denominator':'boarded weighted flows; switchers and unserved are separate',
        'original_dataset':'capacity_v8','scenarios':halves,'audit_sources':sources})
    csvout('daily_before_after.csv',daily_comparison);csvout('stops_before_after.csv',stop_comparison)
    assert operations.protect()==read(WORK/'protected_hashes.json')
    summary={'status':'PASS','revision':operations.REVISION,'simulation_runs':10,'runs':checks,
        'same_demand_ids_weights_origins_destinations_departures':True,'shuttle_clocks_preserved':True,
        'capacities_preserved':True,'gate_access_calibration_preserved':True,
        'maximum_particle_mass_error':max(x['particle_mass_max_error'] for x in checks),
        'original_artifacts_unchanged':True,'half_hour_mass_reconciled':True,
        'actual_weekday_wait_accuracy_validated':False,'source_days':['2026-11-09'],
        'all_weekdays_are_transfer_estimates':True,'external_background_passengers_included':False}
    save=operations.save;save(WORK/'independent_verification.json',summary)
    save(WORK/'run_verification.json',{'status':'PASS','run_count':10,'runs':[x['report'] for d in charts.values() for x in d.values()]})
    print('ALL_VERIFIED',operations.REVISION,flush=True)


if __name__=='__main__':main()
