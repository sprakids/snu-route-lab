"""Independent full-flow reconciliation of capacity-only and paired branches."""
from pathlib import Path
from collections import Counter
import argparse,json,math,csv
import capacity_model as base
from prepare_walk_choices import read
from prepare_city import planned_departures
import analyze_walk_choices as analysis
import verify_walk_choice_core as core
from aggregate_half_hour import aggregate,BINS,INTERVAL

SIM=Path(__file__).resolve().parent
H=SIM/'crowding_walk_choices_2026-11-10/initial_refit_H'

def expected_roster(bundle,scenario,paired):
    result=[];batch=Counter()
    for rid,info in bundle['prepared']['common']['route_info'].items():
        clocks=planned_departures(info['plan']) if info.get('city') else base.dispatches(rid,scenario)
        for clock in clocks:
            count=2 if paired and rid=='shuttle-41841' and 54000<=clock<68400 else 1
            for _ in range(count):
                start=clock+info.get('origin_to_modeled_first_stop_seconds',0)-info['offsets'][info['anchor']]
                if start>base.END or start+info['offsets'][-1]<0:continue
                cap=(44 if clock<75600 else 60) if rid=='shuttle-41841' else info.get('capacity',25 if rid=='shuttle-41914' else 60)
                result.append((rid,start,cap,clock));batch[rid,clock]+=1
        if rid=='shuttle-41841':
            original_multiplicity=Counter(clocks)
            for clock,multiplicity in original_multiplicity.items():
                assert batch[rid,clock]==multiplicity*(2 if paired and 54000<=clock<68400 else 1)
    return result

def minute(rows,a,target):
    b=a+60;prior=next((q for t,q,*_ in reversed(rows) if t<=a),0.)
    pts=[(a,prior)]+[(t,q) for t,q,*_ in rows if a<t<b]+[(b,0.)]
    return {'uniform_minute_mean':math.fsum((end-t)*q for (t,q),(end,_) in zip(pts,pts[1:]))/60,
      'minute_range':[min(q for t,q in pts[:-1]),max(q for t,q in pts[:-1])],
      'expected_absolute_count_error':math.fsum((end-t)*abs(q-target) for (t,q),(end,_) in zip(pts,pts[1:]))/60}

def verify(work,paired,resume_exports=False):
    bundle=read(work/'prepared.json.gz');common=bundle['prepared']['common'];base.OUT=work/'public_data'
    if resume_exports:
        previous=read(work/'independent_verification.json')
        assert previous['status']=='PASS' and previous['simulation_runs']==10
        assert previous['prepared_sha256']==base.sha(work/'prepared.json.gz')
        assert previous['model_sha256']==base.sha(work/'engine.py')
    analysis.WORK=work;analysis.OLD=H;analysis.prepare=lambda:bundle;core.WORK=work;core.OUT=work/'public_data'
    rows=[];results=[];charts={};half={};capacity_events=0
    for scenario in ('regular','peak'):
        charts[scenario]={};half[scenario]={}
        roster=expected_roster(bundle,scenario,paired)
        for day,did in base.DAYS.items():
            receipt=read(work/f'run-{scenario}-{did}.json');assert receipt['status']=='PASS' and receipt['model_sha256']==base.sha(work/'engine.py')
            data=read(work/'public_data'/f'{scenario}-{did}.json');audit=read(work/f'audit-{scenario}-{did}.json.gz')
            for t,node,vid,cap,before,off,on,after,left,new,physical,rid,k in audit['events']:
                want_rid,start,want_cap,clock=roster[vid]
                assert (rid,cap)==(want_rid,want_cap)
                assert abs(start+common['route_info'][rid]['offsets'][k]-t)<1e-6
                assert abs(before-off+on-after)<1e-6 and -1e-6<=after<=cap+1e-6
                capacity_events+=1
            assert len(roster)==data['report']['vehicles']
            assert all(not r['forced'] for r in audit['behavior_decisions'])
            if resume_exports:
                result=read(work/f'analysis-{scenario}-{did}.json')
                assert result['core']['status']=='PASS' and result['core']['particle_mass_max_error']<1e-6
                assert data['report']==audit['report']
            else:result=analysis.analyze(day,scenario)
            results.append(result)
            charts[scenario][did]={k:data[k] for k in ('hourly','daily','report')}
            half[scenario][did]=aggregate(audit['waits'],len(common['nodes']))
            for i,node in enumerate(common['nodes']):
                stats=result['all_stops'].get(str(i),{'waiting_episode_weight':0,'mean_continuous_wait_min':None,'p90_continuous_wait_min':None,
                        'max_continuous_wait_min':0,'over_20_minute_weight':0,'over_20_minute_partition_rows':0})
                rows.append({'scenario':scenario,'weekday':did,'node':i,'stop':node['name'],'ars':node.get('ars',''),**stats,
                             'max_queue':max((r[1] for r in data['queue_timeline'][i]),default=0.)})
            print('CORRECTION_VERIFIED',scenario,did,result['quality_gates'],flush=True)
    scientific={'status':'PASS','simulation_runs':10,'model_sha256':base.sha(work/'engine.py'),'prepared_sha256':base.sha(work/'prepared.json.gz'),
      'capacity_policy_sha256':base.sha(work/'capacity_policy.py'),'all_cases_conservation_fifo_capacity_pass':True,
      'capacity_events_checked':capacity_events,'vehicle_capacities_fixed_by_terminal_dispatch':True,'distinct_44_person_peak_vehicles':paired,
      'all_stop_review':{'over_20_minute_weight':sum(r['over_20_minute_weight'] for r in results),
                         'maximum_continuous_wait_min':max(r['maximum_continuous_wait_min'] for r in results),
                         'named_stops_above40':[{'scenario':r['scenario'],'weekday':r['weekday'],'targets':r['targets']} for r in results if not r['quality_gates']['named_stops_at_most_40']]},
      'only_capacity_and_declared_batch_inputs_changed':True,'behavior_coefficients_refitted':False,'independent_empirical_validation':False,
      'old_three_reports_are_diagnostic_not_selection_gates':True,
      'run_summaries':[{k:r[k] for k in ('scenario','weekday','maximum_continuous_wait_min','over_20_minute_weight','paired_metrics','targets','quality_gates')} for r in results]}
    base.save(work/'independent_verification.json',scientific)
    base.save(work/'all_stops_waits.json',{'rows':rows,'summary':scientific})
    with (work/'all_stops_waits.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,list(rows[0]));writer.writeheader();writer.writerows(rows)
    common['capacity_correction']['engine_sha256']=base.sha(work/'engine.py')
    common['source_note']='동일한 가중 수요·행동계수를 유지한 정원 정정 및 명시한 피크 묶음운행 시나리오. 실측 개인이동/GPS 재생 아님.'
    base.public('common.json',common)
    base.public('charts.json',{'scenarios':charts,'legacy_wait_charts':read(SIM/'public/data/capacity_v9/charts.json')['legacy_wait_charts'],'adaptive':True,'city_capacity_applied':True})
    base.public('half_hour.json',{'schema_version':1,'interval_seconds':INTERVAL,'start_second':base.START,'end_second':base.END,'bin_starts':BINS,
                                'grouping':'stop arrival, half-open bins','mean_denominator':'boarded weighted flows; switchers/unserved separate',
                                'original_dataset':'capacity_v11' if paired else 'capacity_v10','scenarios':half})
    diagnostics=[]
    for parent,label in [(H,'v9_60_single'),(SIM/'capacity44_correction_2026-11-10','capacity44_single'),(SIM/'peak_pair_correction_2026-11-10','capacity44_pair')]:
        for scenario in ('regular','peak'):
            p=parent/'public_data'/f'{scenario}-tue.json'
            if p.exists():diagnostics.append({'model':label,'scenario':scenario,**minute(read(p)['queue_timeline'][1],15*3600+23*60,67)})
    base.save(work/'new_field_diagnostic.json',{'observation_id':'20261110-1523-admin-snu-queue-wait-01',
          'status':'DIAGNOSTIC_NOT_INDEPENDENT_ACCURACY','outside_queue_including_observer':67,'people_ahead':66,'join_minute':'15:23',
          'reported_pure_queue_wait_seconds':189,'reported_join_to_departure_seconds':219,'same_batch_second_vehicle':True,
          'vehicle_arrival_time':'after joining; maybe after15:24 is uncertain recollection, not exact or strict lower bound',
          'one_observation_not_two_photos_or67_individual_wait_samples':True,'coefficient_tuning_performed':False,
          'single_event_model_cannot_match_arrival_boarding_departure_separately':True,
          'do_not_infer_denials_or_headway_from67_div44':True,'queue_minute_comparison':diagnostics})
    base.save(work/'export_completion.json',{'status':'PASS','resumed_after_csv_codec_fix':resume_exports,
         'full_numeric_core_results_preserved_and_reused':resume_exports,'capacity_clock_and_load_checks_repeated':True,
         'rows':len(rows),'prepared_sha256':base.sha(work/'prepared.json.gz'),
         'audit_sha256':{f'{s}-{d}':base.sha(work/f'audit-{s}-{d}.json.gz') for s in ('regular','peak') for d in base.DAYS.values()}})
    print('ALL_CORRECTION_CASES_VERIFIED',json.dumps({'directory':work.name,'runs':10,'capacity_events':capacity_events,'status':'PASS'}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory');p.add_argument('--paired',action='store_true');p.add_argument('--resume-exports',action='store_true');a=p.parse_args();verify(SIM/a.directory,a.paired,a.resume_exports)
