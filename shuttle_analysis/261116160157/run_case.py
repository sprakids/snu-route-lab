"""One bounded private run from the pre-registered experiment table."""
import argparse,time,sys,platform,shutil
from pathlib import Path
from artifacts import ROOT,DAYS,read,save,sha,model_id,check_baseline
from prepare import prepare
import engine

def code_manifest():
    return {name:sha(ROOT/name) for name in ('artifacts.py','preferences.py','hazard.py','capacity.py','physics.py','fares.py','prepare.py','policy.py','metrics.py','engine.py','operations.py','empirical_v12.py','time_profiles.py','behavioral_policy.py','walking_opportunities.py','perception.py','direct_restoration.py','primary_opportunity.py','run_case.py')}
def run(case_id,attempt=1):
    check_baseline();lock=read(ROOT/'experiment_lock.json');case=next(c for c in lock['pilot_cases'] if c['case']==case_id)
    work=ROOT/'runs'/case_id/f'attempt_{attempt:02d}';assert not work.exists(),f'Preserve and inspect the existing run: {work}'
    work.mkdir(parents=True)
    config=read(ROOT/'config.json');config['seed']=case['seed'];config['operations']=case.get('operations','baseline');config.update(case.get('config_overrides',{}))
    if case['mode'] in ('physics','combined','fare_scenario'):config['physics']='path_local_4p8'
    if case['mode'] in ('behavior','combined','fare_scenario'):
        config.update(behavior='sequential',boarding_choice=True)
    if case['mode'] in ('combined','fare_scenario'):config['origin_choice']=True
    if case['mode']=='fare_scenario':config['fare_in_choice']=True
    if config.get('initial_assignment_policy')=='preserve_source_mixture':config['origin_choice']=False
    receipt={'status':'STARTED','private_prototype_id':model_id(),'case':case,'config':config,
             'code_sha256':code_manifest(),'experiment_lock_sha256':sha(ROOT/'experiment_lock.json'),
             'input_manifest_sha256':sha(ROOT/'input_manifest.json'),'python':platform.python_version(),
             'no_production_writes':True}
    save(work/'started.json',receipt);started=time.perf_counter()
    snapshot=work/'source_snapshot';snapshot.mkdir()
    for name in receipt['code_sha256']:shutil.copy2(ROOT/name,snapshot/name)
    try:
        bundle=prepare(case,config)
        save(work/'input_summary.json',{'original_parent_mass':sum(bundle['source_parent_mass'].values()),
            'synthetic_mass':sum(p[3] for p in bundle['prepared']['plans'][case['day']]),
            'parents':len(bundle['source_parent_mass']),'synthetic_packets':len(bundle['prepared']['plans'][case['day']]),
            'maximum_packet_weight':max(p[3] for p in bundle['prepared']['plans'][case['day']]),
            'scenario':case['scenario'],'day':case['day'],'initial_catalog_groups':len(bundle['origin_catalog']),
            'route_info_unchanged':bundle['prepared']['common']['route_info']==read(ROOT/'frozen/prepared.json.gz')['prepared']['common']['route_info']})
        engine.WORK=work;data=engine.simulate(bundle,case['day'],case['scenario'])
        assert code_manifest()==receipt['code_sha256'],'Code changed during this run'
        check_baseline();receipt.update(status='COMPUTED_NOT_EMPIRICALLY_VALIDATED',elapsed_seconds=time.perf_counter()-started,report=data['report'],policy_report=data['policy_report'])
        save(work/'result.json',receipt);print('PROTOTYPE_CASE_DONE',case_id,receipt['elapsed_seconds'],flush=True)
    except Exception as exc:
        save(work/'failure.json',{'error':type(exc).__name__,'message':str(exc),'elapsed_seconds':time.perf_counter()-started,'production_changed':False});raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('case');p.add_argument('--attempt',type=int,default=1);args=p.parse_args();run(args.case,args.attempt)
