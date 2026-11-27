"""Verify source preservation, owned run snapshots, frozen future plan and V11 HTTP readback."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import argparse,hashlib,importlib.util,json
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');args=p.parse_args();work=Path(args.candidate).resolve()
    target=work/'final_verification.json';assert not target.exists()
    manifest=read(work/'repair_manifest.json');checks=0
    for path,digest in manifest['protected'].items():assert sha(Path(path))==digest,path;checks+=1
    for path,digest in manifest['frozen_payloads'].items():assert sha(work/path)==digest,path;checks+=1
    future=read(work/'future_evaluation_plan.json')
    for path,digest in future['frozen_sha256'].items():assert sha(work/path)==digest,path;checks+=1
    lock=read(work/'experiment_lock.json')
    for key,name in [('stage2_protocol_sha256','stage2_protocol.json'),('fine_protocol_sha256','final_midpoint_protocol.json')]:
        if lock.get(key):assert sha(ROOT/name)==lock[key],name;checks+=1
    validation=read(work/'grid-validation.json');cases=validation['results'];assert len(cases)==10
    for row in cases:
        folder=Path(row['source_directory']);started=read(folder/'started.json')
        assert started['case']==row['case']
        for path,digest in started['code_sha256'].items():
            assert sha(work/path)==digest==sha(folder/'source_snapshot'/path),(folder,path);checks+=1
        assert sha(work/'experiment_lock.json')==started['experiment_lock_sha256']
        did={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}[row['case']['day']]
        assert sha(folder/f"audit-{row['case']['scenario']}-{did}.json.gz")==row['audit_sha256'];checks+=1
        if read(work/'config.json').get('initial_assignment_policy')=='preserve_source_mixture':
            assert started['config']['origin_choice'] is False
            assert read(folder/'result.json')['policy_report']['initial_plan_changes']==0
            checks+=2
    spec=importlib.util.spec_from_file_location('old_readback',work.parent/'261112111627/verify_production_unchanged_v2.py')
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    lab='https://snu-shuttle-simulation.vercel.app/';release=f'routing-model/releases/{old.MODEL}.json'
    jobs=[('lab_latest',lab+'routing-model/latest.json'),('lab_payload',lab+release),
      ('data_payload','https://snu-shuttle-v9-data.vercel.app/'+release),('route_api','https://snu-route-lab.vercel.app/api/queue-model')]
    jobs +=[(name,lab+name) for name in ('index.html','viewer-v5.js','mobile-lab.js','mobile-lab.css')]
    with ThreadPoolExecutor(max_workers=4) as pool:responses=list(pool.map(old.fetch,jobs))
    output={'status':'PASS' if all(r['check']=='PASS' for r in responses) else 'PUBLIC_READBACK_FAILURE',
      'release_id':work.name,'checked_at':datetime.now(timezone.utc).isoformat(),'local_source_hash_checks':checks,
      'cases_verified':len(cases),'future_hashes_verified':len(future['frozen_sha256']),
      'production_model_id':old.MODEL,'public_readback':responses,'production_writes':False,
      'quality_gate_is_separate_from_integrity_verification':True}
    target.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')
    assert output['status']=='PASS',output
    print('VERIFIED',work.name,checks,'source checks',len(responses),'HTTP readbacks',flush=True)
if __name__=='__main__':main()
