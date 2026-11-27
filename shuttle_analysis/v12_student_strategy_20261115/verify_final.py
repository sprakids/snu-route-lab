"""Verify the frozen candidate, single owned attempts, and active V11 readback."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import argparse,hashlib,importlib.util,json,re
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('--group',default='grid');a=p.parse_args();w=Path(a.candidate).resolve();out=w/(a.group+'-final-verification.json');assert not out.exists()
    manifest=read(w/'repair_manifest.json');future=read(w/'future_evaluation_plan.json');checks=0
    for path,digest in manifest['protected'].items():assert sha(Path(path))==digest,path;checks+=1
    for path,digest in manifest['frozen_payloads'].items():assert sha(w/path)==digest,path;checks+=1
    for path,digest in future['frozen_sha256'].items():assert sha(w/path)==digest,path;checks+=1
    for path in w.glob('physical_paths_*.json.gz'):assert sha(path)==sha(w.parent/'261112220847'/path.name);checks+=1
    v=read(w/(a.group+'-validation.json'));behavior=read(w/(a.group+'-behavior-validation.json'));rec=read(w/(a.group+'-recommendation.json'))
    assert behavior['status']=='PASS_STUDENT_BEHAVIOR_GATES'
    for r in v['results']:
        assert r['status']=='PASS_INTERNAL_INVARIANTS';folder=Path(r['source_directory']);started=read(folder/'started.json')
        for path,digest in started['code_sha256'].items():assert sha(w/path)==digest==sha(folder/'source_snapshot'/path),path;checks+=1
        if 'reused_run' in r:
            proof=r['reused_run'];assert proof['effective_config_equal_except_inert_labels'] and proof['new_execution'] is False
            assert sha(folder/'started.json')==proof['started_sha256'] and r['audit_sha256']==proof['audit_sha256']
            assert sha(folder.parents[2]/'experiment_lock.json')==started['experiment_lock_sha256']
            cfg=read(w/'config.json');cfg.update(seed=r['case']['seed'],operations=r['case'].get('operations','baseline'),physics='path_local_4p8',behavior='sequential',boarding_choice=True,origin_choice=True)
            inert=set(proof['inert_labels']);assert {k:v for k,v in cfg.items() if k not in inert}=={k:v for k,v in started['config'].items() if k not in inert}
            for label in inert:
                for name in v['source_sha256']:assert label not in (w/name).read_text(encoding='utf8'),(label,name,'reused-label must be absent from runtime source')
        else:assert sha(w/'experiment_lock.json')==started['experiment_lock_sha256']
        assert started['config']['origin_choice'] is True and started['config']['student_strategy'] is True
    assert len(list((w/'runs').glob('*/attempt_*')))==sum('reused_run' not in r for r in v['results'])
    report=w/(a.group+'-RESULTS.md');assert sha(report)==rec['report_sha256'];links=[]
    for href in re.findall(r'\]\(([^)]+)\)',report.read_text(encoding='utf8')):
        if href.startswith(('http://','https://','#')):continue
        assert (w/href).resolve().exists(),href;links.append(href)
    days={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'};baseline=w.parent/'261112111627/verify_production_unchanged_v2.py'
    spec=importlib.util.spec_from_file_location('readback_only',baseline);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    lab='https://snu-shuttle-simulation.vercel.app/';release=f'routing-model/releases/{old.MODEL}.json'
    jobs=[('lab_latest',lab+'routing-model/latest.json'),('lab_payload',lab+release),('data_payload','https://snu-shuttle-v9-data.vercel.app/'+release),('route_api','https://snu-route-lab.vercel.app/api/queue-model')]
    jobs +=[(name,lab+name) for name in ('index.html','viewer-v5.js','mobile-lab.js','mobile-lab.css')]
    with ThreadPoolExecutor(max_workers=4) as pool:responses=list(pool.map(old.fetch,jobs))
    unit_counts={}
    for name,label in [('enabled-final.log','enabled_strategy_and_enroute'),('legacy-final.log','legacy_components_strategy_disabled')]:
        log=(w/name).read_text(encoding='utf8');matches=re.findall(r'Ran (\d+) tests?',log);assert len(matches)==1 and re.search(r'^OK\s*$',log,re.M),name
        unit_counts[label]=int(matches[0])
    unit_counts['total']=sum(unit_counts.values())
    result={'status':'PASS' if all(r['check']=='PASS' for r in responses) else 'PUBLIC_READBACK_FAILURE','release_id':w.name,'group':a.group,
      'checked_at':datetime.now(timezone.utc).isoformat(),'local_hash_checks':checks,'runtime_modules':len(v['source_sha256']),'future_hash_count':len(future['frozen_sha256']),
      'cases':len(v['results']),'reused_equivalent_completed_runs':sum('reused_run' in r for r in v['results']),'unit_tests':unit_counts,
      'behavior_gate':behavior['status'],'old_strict_twenty_minute_gate_passed':rec['old_strict_twenty_minute_gate_passed'],
      'max_all_recorded_wait_min':rec['max_all_recorded_wait_min'],'over20_episode_weight':rec['over20_episode_weight'],'unserved_weight':rec['unserved_weight'],
      'local_report_links_verified':len(links),'production_model_id':old.MODEL,'public_readback':responses,'production_writes':False,'new_day_accuracy':'NOT_EVALUATED'}
    result['verification_scope']='Artifact consistency, behavior invariants and active-production preservation; not deployment readiness or field accuracy'
    result['operating_adoption_recommended']=rec['operating_adoption_recommended']
    result['adoption_blockers']=rec['blockers']
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');assert result['status']=='PASS'
    print('VERIFIED',w.name,len(v['results']),checks,'hash checks',len(responses),'HTTP',flush=True)
if __name__=='__main__':main()
