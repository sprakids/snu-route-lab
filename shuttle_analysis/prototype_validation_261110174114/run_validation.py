"""Finite validation grid with one hash-checked, already validated parent cell."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from collections import defaultdict
import csv,json,math,subprocess,sys
from artifacts import ROOT,read,save,sha,check_baseline,START,END
from run_case import code_manifest
import analyze_followup as independent

def normalize(result):
    for scope in result['scope'].values():
        metrics=scope['metrics']
        for key in list(metrics):
            if key.endswith('_seconds'):metrics[key[:-8]+'_min']=metrics.pop(key)
        metrics['fare_won']['baseline']=None
    return result

def extra_rows(result,folder,case,common):
    did=independent.base.DAYS[case['day']];scenario=case['scenario']
    data=read(folder/f'{scenario}-{did}.json.gz');audit=read(folder/f'audit-{scenario}-{did}.json.gz')
    bins=defaultdict(list)
    for trip in audit['legs']:
        pending=None
        def take(episode):
            if episode is None:return
            n,a,b=episode;b=min(b,END)
            if a<END and b>START and b-a>1e-7:bins[n,int(a//1800)*1800].append(((b-a)/60,trip['weight'],a,b))
        for leg in trip['legs']:
            if leg[0]==1:
                if pending and pending[0]==leg[4] and abs(pending[2]-leg[1])<1e-5:pending[2]=leg[2]
                else:take(pending);pending=[leg[4],leg[1],leg[2]]
            else:take(pending);pending=None
        take(pending)
    for row in result['stop_waits']:
        timeline=data['queue_timeline'][row['node']];peak=max(timeline,key=lambda x:x[1],default=[None,0.])
        row.update(stop_id=common['nodes'][row['node']].get('stop_id'),max_queue=peak[1],queue_peak_at_second=peak[0])
    cells=[]
    for (node,start),episodes in sorted(bins.items()):
        weight=math.fsum(r[1] for r in episodes)
        cells.append({'case':case['case'],'day':case['day'],'scenario':scenario,'node':node,'stop':common['nodes'][node]['name'],
            'bin_start_second':start,'bin_end_second':start+1800,'arrival_episode_weight':weight,
            'mean_continuous_wait_min':math.fsum(t*w for t,w,*_ in episodes)/weight,
            'max_continuous_wait_min':max(r[0] for r in episodes),'over20_episode_weight':math.fsum(w for t,w,*_ in episodes if t>20+1e-7),
            'grouping':'physical queue-entry half-hour; includes boarded and walk-away episodes'})
    result.update(unserved_trip_weight=data['report']['unserved_trip_weight'],late_finished_weight=data['report']['late_arrival_weight'],
        source_directory=str(folder),half_hour_rows=cells)
    return result

def guard():
    latest=ROOT.parent/'simulation_viewer_2026-11-07/public/routing-model/latest.json'
    assert sha(latest)==read(ROOT/'creation_manifest.json')['production_latest_sha256']
    assert read(latest)['model_id']=='261110162302';check_baseline()

def main():
    lock=read(ROOT/'experiment_lock.json');parent=Path(lock['parent_candidate']);reference=Path(lock['reused_case']['directory'])
    ref=read(reference/'independent_analysis.json');receipt=read(reference/'result.json');expected=code_manifest()
    assert ref['status']=='PASS_INTERNAL_INVARIANTS' and ref['over20_weight']==0
    assert receipt['code_sha256']==expected
    for n,digest in expected.items():assert sha(parent/n)==digest
    assert sha(ROOT/'config.json')==sha(parent/'config.json')
    assert sha(ROOT/'frozen/prepared_capacity44_pair.json.gz')==sha(parent/'frozen/prepared_capacity44_pair.json.gz')
    assert ref['audit_sha256']==sha(reference/'audit-regular-mon.json.gz')
    guard();marker=ROOT/'validation-started.json';assert not marker.exists(),'Preserve run ownership and partial results'
    save(marker,{'status':'STARTED','runtime_sha256':expected,'config_sha256':sha(ROOT/'config.json'),'jobs':lock['pilot_cases'],
        'reference_case':lock['reused_case'],'operational_replacement_allowed':False})
    frozen=read(ROOT/'frozen/prepared_capacity44_pair.json.gz');common=frozen['prepared']['common']
    results=[extra_rows(normalize(ref),reference,lock['reused_case']['case'],common)]
    def worker(case):
        folder=ROOT/'runs'/case['case']/'attempt_01';assert not folder.exists()
        with (ROOT/(case['case']+'.log')).open('x',encoding='utf8') as stream:
            done=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'run_case.py'),case['case']],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert done.returncode==0,(case['case'],str(folder));guard()
        row=independent.verify(case,folder,frozen);row=extra_rows(normalize(row),folder,case,common)
        save(folder/'validation_cell.json',row);print('VALIDATION_CELL',case['case'],row['maximum_continuous_wait_min'],row['over20_weight'],flush=True)
        return row
    with ThreadPoolExecutor(max_workers=2) as pool:
        for row in pool.map(worker,lock['pilot_cases']):results.append(row)
    guard();main_names={c['case'] for c in lock['all_weekday_main_cases']};primary=[r for r in results if r['case']['case'] in main_names]
    assert len(primary)==10 and len(results)==12
    stops=[{'case':r['case']['case'],'day':r['case']['day'],'scenario':r['case']['scenario'],**s} for r in primary for s in r['stop_waits']]
    half=[s for r in primary for s in r['half_hour_rows']];comparisons=[]
    for r in results:
        for scope,v in r['scope'].items():
            row={'case':r['case']['case'],'scope':scope,'weight':v['weight'],'max_continuous_wait_min':r['maximum_continuous_wait_min'],
                'over20_episode_weight':r['over20_weight'],'unserved_trip_weight':r['unserved_trip_weight']}
            for key,pair in v['metrics'].items():
                for which,value in pair.items():row[which+'_'+key]=value
            comparisons.append(row)
    for name,rows in [('all_stops_waits.csv',stops),('half_hour_waits.csv',half),('comparison.csv',comparisons)]:
        with (ROOT/name).open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,list(rows[0]));writer.writeheader();writer.writerows(rows)
    result={'status':'PASS_INTERNAL' if all(r['over20_weight']<1e-7 and r['unserved_trip_weight']<1e-7 for r in results) else 'NEEDS_FURTHER_REPAIR',
        'empirical_status':'NOT_EVALUABLE','requires_explicit_user_approval_before_production_replacement':True,'new_algorithm_promoted':False,
        'cases':len(results),'main_grid':len(primary),'reused_cases':1,'computed_new_cases':len(results)-1,
        'main_stop_rows':len(stops),'half_hour_rows':len(half),'runtime_code_sha256':expected,
        'maximum_continuous_wait_min':max(r['maximum_continuous_wait_min'] for r in results),
        'over20_episode_weight':math.fsum(r['over20_weight'] for r in results),'unserved_trip_weight':math.fsum(r['unserved_trip_weight'] for r in results),
        'results':results,'production_model_unchanged':'261110162302','ops_source':'Monday distribution transferred to weekdays, not observed weekday-by-date clocks',
        'no20_clip_or_forced_abandonment':True,'source_demand_mass_preserved':True,'metric_units':'weighted mean minutes except changes/count and fare/scenario won'}
    save(ROOT/'validation.json',result);print('ALL_VALIDATION_CELLS_DONE',result['status'],result['maximum_continuous_wait_min'],result['over20_episode_weight'],flush=True)

if __name__=='__main__':main()
