"""Run and validate every weekday/scenario before any v9 export or activation."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess,sys,json,math,csv,time
import capacity_model as base
from prepare_walk_choices import prepare,read,WORK,ROOT,RULE
import walk_choice_model as model
from analyze_walk_choices import analyze
from aggregate_half_hour import aggregate,BINS,INTERVAL
from gate_access_calibration import minute_summary

def run_all():
    bundle=prepare();expected_sha=base.sha(Path(model.__file__))
    jobs=[(scenario,day,did) for scenario in ('peak','regular') for day,did in base.DAYS.items()]
    def worker(case):
        scenario,day,did=case;receipt=WORK/f'run-{scenario}-{did}.json'
        if receipt.exists():
            saved=read(receipt);assert saved['status']=='PASS' and saved['model_sha256']==expected_sha
            print('REUSED',scenario,did,flush=True);return
        log=WORK/f'full-{scenario}-{did}.log';assert not log.exists(),f'Inspect incomplete log: {log}'
        with log.open('w',encoding='utf8') as stream:
            run=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'run_walk_choices.py'),'--day',day,'--scenario',scenario],
                                stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert run.returncode==0,(case,str(log));assert read(receipt)['model_sha256']==expected_sha
        print('COMPLETED',scenario,did,flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(worker,jobs))
    verify_all(bundle,expected_sha)

def verify_all(bundle,expected_sha):
    out=WORK/'public_data';base.OUT=out;checks=[];charts={};halves={};rows=[]
    common=bundle['prepared']['common'];old=ROOT/'gate_access_calibration_2026-11-09/candidates/alpha_075/public_data'
    baseline_fit=minute_summary(read(old/'peak-mon.json'),read(old/'common.json'))
    for scenario in ('peak','regular'):
        charts[scenario]={};halves[scenario]={}
        for day,did in base.DAYS.items():
            receipt=read(WORK/f'run-{scenario}-{did}.json');assert receipt['model_sha256']==expected_sha
            result=analyze(day,scenario);checks.append(result)
            data=read(out/f'{scenario}-{did}.json');audit=read(WORK/f'audit-{scenario}-{did}.json.gz')
            assert all(not d['forced'] for d in audit['behavior_decisions'])
            charts[scenario][did]={k:data[k] for k in ('hourly','daily','report')}
            halves[scenario][did]=aggregate(audit['waits'],len(common['nodes']))
            for node,hours in data['hourly'].items():
                for hour,r in hours.items():
                    parts=[halves[scenario][did][node][str(t)] for t in BINS if t//3600==int(hour)]
                    for field in ('arrival_weight','served_weight','switched_weight','unserved_weight','denied_weight'):
                        assert abs(math.fsum(p[field] for p in parts)-r.get(field,0))<1e-5
            for i,node in enumerate(common['nodes']):
                values=result['all_stops'].get(str(i),{'waiting_episode_weight':0,'mean_continuous_wait_min':None,
                          'p90_continuous_wait_min':None,'max_continuous_wait_min':0,'over_20_minute_weight':0,'over_20_minute_partition_rows':0})
                before=result['baseline_all_stops'].get(str(i),{})
                rows.append({'scenario':scenario,'weekday':did,'node':i,'stop':node['name'],'ars':node.get('ars',''),
                             **values,'before_max_wait_min':before.get('max_continuous_wait_min',0),
                             'before_over_20_minute_weight':before.get('over_20_minute_weight',0),
                             'max_queue':max(r[1] for r in data['queue_timeline'][i])})
            print('VERIFIED',scenario,did,result['quality_gates'],flush=True)
    fit=checks[0]['field_fit'];fit_checks=[]
    for before,after in zip(baseline_fit,fit):
        assert before['id']==after['id']
        fit_checks.append({'id':after['id'],'before':before,'after':after,
                          'passes':after['expected_absolute_distance_to_report_interval']<=before['expected_absolute_distance_to_report_interval']+.5})
    original=read(ROOT/'crowding_walk_choices_2026-11-10/protected_hashes.json')
    assert all(base.sha(ROOT/name)==value for name,value in original.items())
    all_gates=all(all(c['quality_gates'].values()) for c in checks) and all(f['passes'] for f in fit_checks)
    summary={'status':'PASS' if all_gates else 'QUALITY_REVIEW_REQUIRED','simulation_runs':len(checks),
             'model_sha256':expected_sha,'source_simulation':'capacity_v7','dataset':'capacity_v9',
             'all_stop_quality':{'status':'PASS' if all_gates else 'FAIL','wait_limit_minutes':20,'named_queue_reference':40,
                                 'all_cases_pass':all(all(c['quality_gates'].values()) for c in checks),'field_fit':fit_checks},
             'maximum_particle_mass_error':max(c['core']['particle_mass_max_error'] for c in checks),
             'original_hashes_unchanged':True,'protected_files':len(original),'run_summaries':[
                 {k:c[k] for k in ('scenario','weekday','quality_gates','maximum_continuous_wait_min','over_20_minute_weight','baseline_over_20_minute_weight','paired_metrics','targets')} for c in checks],
             'independent_empirical_validation':False,'no_forced_queue_or_wait_clipping':True,'change_limit':None,
             'rule':RULE}
    base.save(WORK/'independent_verification.json',summary)
    with (WORK/'all_stops_waits.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,list(rows[0]));writer.writeheader();writer.writerows(rows)
    base.save(WORK/'all_stops_waits.json',{'definitions':'continuous physical stop waits, adjacent same-stop waits merged; END censored, 20-minute excess must overlap display window',
                                        'rows':rows,'summary':summary})
    assert all_gates,'Do not export or activate a candidate that fails all-stop or field-fit checks'
    base.public('common.json',common)
    legacy=read(ROOT/'public/data/capacity_v7/charts.json')['legacy_wait_charts']
    base.public('charts.json',{'scenarios':charts,'legacy_wait_charts':legacy,'adaptive':True,'city_capacity_applied':True})
    base.public('half_hour.json',{'schema_version':1,'interval_seconds':INTERVAL,'start_second':base.START,'end_second':base.END,
                                'bin_starts':BINS,'grouping':'stop arrival, half-open bins','mean_denominator':'boarded weighted flows; switchers and unserved separate',
                                'original_dataset':'capacity_v9','scenarios':halves})
    print('ALL_CASES_VERIFIED',json.dumps({'runs':len(checks),'source':str(WORK),'status':'PASS'}),flush=True)

if __name__=='__main__':run_all()
