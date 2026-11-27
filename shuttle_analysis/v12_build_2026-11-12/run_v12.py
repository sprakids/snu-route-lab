"""Owned finite V12 weekday grid, full original invariant audits, no publisher."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import csv,math,subprocess,sys
from artifacts import ROOT,read,save,sha,check_baseline,START,END
from run_case import code_manifest
import analyze_followup as independent
from validation_metrics import diagnostics

def guard():
    creation=read(ROOT/'creation_manifest.json');latest=ROOT.parent/'simulation_viewer_2026-11-07/public/routing-model/latest.json'
    assert sha(latest)==creation['production_latest_sha256'];check_baseline()
    for name,digest in creation['parent_source_sha256'].items():assert sha(Path(creation['parent'])/name)==digest
    assert sha(ROOT/'frozen/empirical_evidence.json')==creation['new_evidence_payload_sha256']
    assert sha(ROOT/'frozen/operations_v12_empirical.json')==creation['operations_sha256']

def main():
    marker=ROOT/'validation-started.json';assert not marker.exists(),'Preserve owned/consumed execution.'
    lock=read(ROOT/'experiment_lock.json');cases=lock['pilot_cases'];assert len(cases)==10
    guard();save(marker,{'status':'STARTED','runtime_sha256':code_manifest(),'cases':cases,'production_writes':False})
    frozen=read(ROOT/'frozen/prepared_capacity44_pair.json.gz');r10=read(ROOT.parent/'prototype_validation_261110194553/validation.json')
    def worker(case):
        folder=ROOT/'runs'/case['case']/'attempt_01';assert not folder.exists()
        with (ROOT/(case['case']+'.log')).open('x',encoding='utf8') as stream:
            result=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'run_case.py'),case['case']],cwd=ROOT,
                stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert result.returncode==0,(case['case'],str(folder));guard()
        row=independent.verify(case,folder,frozen);did=independent.base.DAYS[case['day']]
        audit=read(folder/f'audit-{case["scenario"]}-{did}.json.gz')
        for scope in row['scope'].values():
            for key in list(scope['metrics']):
                if key.endswith('_seconds'):scope['metrics'][key[:-8]+'_min']=scope['metrics'].pop(key)
            scope['metrics']['fare_won']['baseline']=None
        row['extended_diagnostics']=diagnostics(audit,START,END)
        data=read(folder/'result.json');row['unserved_trip_weight']=data['report']['unserved_trip_weight']
        row['late_finished_weight']=data['report']['late_arrival_weight'];row['source_directory']=str(folder)
        refs=[x for x in r10['results'] if x['case']['day']==case['day'] and x['case']['scenario']==case['scenario']
              and x['case']['seed']==case['seed'] and x['case']['operations']=='distribution_v8']
        assert len(refs)==1;ref=refs[0]
        row['r10_reference']={'source_directory':ref['source_directory'],'audit_sha256':ref['audit_sha256'],
            'scope':ref['scope'],'maximum_continuous_wait_min':ref['maximum_continuous_wait_min'],
            'over20_weight':ref['over20_weight'],'extended_diagnostics':ref['extended_diagnostics']}
        save(folder/'validation_cell.json',row)
        print('V12_CELL_AUDITED',case['case'],row['maximum_continuous_wait_min'],row['over20_weight'],flush=True)
        return row
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,cases))
    guard();passed=all(r['over20_weight']<1e-7 and r['unserved_trip_weight']<1e-7 for r in results)
    stops=[{'case':r['case']['case'],'weekday':r['case']['day'],'scenario':r['case']['scenario'],**stop} for r in results for stop in r['stop_waits']]
    with (ROOT/'all_stops_waits.csv').open('x',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,list(stops[0]));w.writeheader();w.writerows(stops)
    summary={'status':'PASS_INTERNAL_GRID' if passed else 'NEEDS_FURTHER_REPAIR','invariant_audits':'PASS','cases':10,'results':results,
      'version_family':'V12','release_id':lock['release_id'],'maximum_continuous_wait_min':max(r['maximum_continuous_wait_min'] for r in results),
      'over20_episode_weight':math.fsum(r['over20_weight'] for r in results),'unserved_trip_weight':math.fsum(r['unserved_trip_weight'] for r in results),
      'runtime_code_sha256':code_manifest(),'queue_empirical_accuracy':'NOT_EVALUABLE','pristine_holdout_dates':[],
      'production_writes':False,'production_replacement_allowed':False,'no20_clip_or_forced_abandonment':True}
    save(ROOT/'validation.json',summary);print('V12_GRID_DONE',summary['status'],flush=True)

if __name__=='__main__':main()
