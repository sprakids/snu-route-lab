"""Exactly two private cases and full invariant audits; no deployment writer."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import subprocess,sys,math
from artifacts import ROOT,read,save,sha,check_baseline,START,END
from run_case import code_manifest
import analyze_followup as independent
from validation_metrics import diagnostics

def guard():
    creation=read(ROOT/'creation_manifest.json');latest=ROOT.parent/'simulation_viewer_2026-11-07/public/routing-model/latest.json'
    assert sha(latest)==creation['production_latest_sha256'];check_baseline()
    for name,digest in creation['parent_source_sha256'].items():
        assert sha(Path(creation['parent'])/name)==digest
    assert sha(ROOT/creation['only_new_runtime_input'])==creation['operations_sha256']

def main():
    marker=ROOT/'pilots-started.json';assert not marker.exists(),'Preserve an owned or consumed pilot.'
    lock=read(ROOT/'experiment_lock.json');cases=lock['pilot_cases'];assert len(cases)==2
    guard();save(marker,{'status':'STARTED','runtime_sha256':code_manifest(),'cases':cases,'production_writes':False})
    frozen=read(ROOT/'frozen/prepared_capacity44_pair.json.gz')
    baseline_validation=read(ROOT.parent/'prototype_validation_261110194553/validation.json')
    def worker(case):
        folder=ROOT/'runs'/case['case']/'attempt_01';assert not folder.exists()
        with (ROOT/(case['case']+'.log')).open('x',encoding='utf8') as f:
            result=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'run_case.py'),case['case']],cwd=ROOT,
              stdout=f,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert result.returncode==0,(case['case'],str(folder));guard()
        audited=independent.verify(case,folder,frozen)
        audit=read(folder/f'audit-{case["scenario"]}-wed.json.gz')
        for scope in audited['scope'].values():
            for key in list(scope['metrics']):
                if key.endswith('_seconds'):scope['metrics'][key[:-8]+'_min']=scope['metrics'].pop(key)
            scope['metrics']['fare_won']['baseline']=None
        audited['extended_diagnostics']=diagnostics(audit,START,END)
        audited['unserved_trip_weight']=read(folder/'result.json')['report']['unserved_trip_weight']
        ref=next(r for r in baseline_validation['results'] if r['case']['day']=='수' and r['case']['scenario']==case['scenario'])
        audited['r10_reference']={'source_directory':ref['source_directory'],'audit_sha256':ref['audit_sha256'],
            'scope':ref['scope'],'maximum_continuous_wait_min':ref['maximum_continuous_wait_min'],
            'over20_weight':ref['over20_weight'],'extended_diagnostics':ref['extended_diagnostics']}
        assert sha(Path(ref['source_directory'])/f'audit-{case["scenario"]}-wed.json.gz')==ref['audit_sha256']
        save(folder/'validation_cell.json',audited)
        print('OBSERVED_INPUT_PILOT_AUDITED',case['case'],audited['maximum_continuous_wait_min'],audited['over20_weight'],flush=True)
        return audited
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,cases))
    guard();passed=all(r['over20_weight']<1e-7 and r['unserved_trip_weight']<1e-7 for r in results)
    summary={'status':'PASS_TWO_PRIVATE_CONDITIONS' if passed else 'NEEDS_FURTHER_REPAIR',
       'invariant_audits':'PASS','cases':len(results),'results':results,
       'maximum_continuous_wait_min':max(r['maximum_continuous_wait_min'] for r in results),
       'over20_episode_weight':math.fsum(r['over20_weight'] for r in results),
       'unserved_trip_weight':math.fsum(r['unserved_trip_weight'] for r in results),
       'queue_empirical_accuracy':'NOT_EVALUABLE','production_writes':False,'production_replacement_allowed':False,
       'all_weekdays_validated':False,'behavior_code_unchanged_from_R10':True}
    save(ROOT/'pilot_validation.json',summary);print('PRIVATE_PILOTS_DONE',summary['status'],flush=True)

if __name__=='__main__':main()
