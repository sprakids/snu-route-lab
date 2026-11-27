"""Copy preserved R10 and connect only a verified private operations input."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,shutil

ROOT=Path(__file__).resolve().parent
ANALYSIS=ROOT.parent
PARENT=ANALYSIS/'prototype_followup_261110193823'
def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    assert not p.exists()
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')

def main():
    pointer=ROOT/'private_candidate.json';assert not pointer.exists()
    check=read(ROOT/'assessment.json');assert check['model_input_connection_eligible']
    profile=ROOT/'operations_observed_train_v1.json'
    assert sha(profile)==check['outputs'][profile.name]
    stamp=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%y%m%d%H%M%S')
    work=ANALYSIS/('prototype_observed_'+stamp);work.mkdir()
    names=['artifacts.py','config.json','preferences.py','hazard.py','capacity.py','physics.py','fares.py','prepare.py',
           'policy.py','metrics.py','engine.py','operations.py','run_case.py','fixtures.py','test_prototype.py',
           'test_prediction_integration.py','dwell.py','input_manifest.json','capacity44_amendment.json',
           'pair_amendment.json','USER_DIRECTIVE.md','analyze_followup.py']
    parent_hashes={n:sha(PARENT/n) for n in names}
    for name in names:shutil.copy2(PARENT/name,work/name)
    shutil.copytree(PARENT/'frozen',work/'frozen')
    for p in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(p,work/p.name)
    shutil.copy2(ANALYSIS/'prototype_validation_261110194553/validation_metrics.py',work/'validation_metrics.py')
    shutil.copy2(ROOT/'run_private_pilots.py',work/'run_private_pilots.py')
    extra='frozen/operations_observed_train_v1.json';shutil.copy2(profile,work/extra)
    manifest=read(work/'input_manifest.json');manifest['frozen'].append({'path':extra,'sha256':sha(work/extra)})
    (work/'input_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    cases=[{'case':f'observed_train_v1-combined-{scenario}-wed','mode':'combined','day':'수',
            'scenario':scenario,'seed':0,'operations':'observed_train_v1'} for scenario in ('regular','peak')]
    lock={'status':'PREREGISTERED_TWO_PRIVATE_CASES_BEFORE_RUN','experiment_id':stamp,'parent_candidate':str(PARENT),
          'pilot_cases':cases,'hypothesis':'Connect supported Tuesday detected-stop segment medians only; departure grids, demand, capacities and behavior unchanged.',
          'source_assessment_sha256':sha(ROOT/'assessment.json'),'training_dates':check['training_dates'],
          'detected_interval_check_dates':check['heldout_diagnostic_dates'],
          'queue_empirical_accuracy':'NOT_EVALUABLE','operational_replacement_allowed':False,
          'do_not_rerun_consumed_cases':True,'maximum_route_changes':None}
    save(work/'experiment_lock.json',lock)
    latest=ANALYSIS/'simulation_viewer_2026-11-07/public/routing-model/latest.json'
    save(work/'creation_manifest.json',{'parent':str(PARENT),'parent_source_sha256':parent_hashes,
        'code_unchanged_from_r10':True,'only_new_runtime_input':extra,'source_assessment':str(ROOT/'assessment.json'),
        'operations_sha256':sha(work/extra),'production_latest_sha256':sha(latest),
        'new_numerical_behavior_tuning':False,'requires_new_user_approval_for_production':True})
    (work/'PLAN.md').write_text((ROOT/'PLAN.md').read_text(encoding='utf8')+'\n\n이번 후보의 실행 범위는 수요일 regular/peak 두 조건이다. 모든 평일을 통과했다고 주장하지 않는다.\n',encoding='utf8')
    assert all(sha(PARENT/n)==digest for n,digest in parent_hashes.items())
    save(pointer,{'directory':str(work),'experiment_id':stamp,'cases':cases,'production_replacement_allowed':False})
    print('PRIVATE_CANDIDATE_CREATED',work,flush=True)

if __name__=='__main__':main()
