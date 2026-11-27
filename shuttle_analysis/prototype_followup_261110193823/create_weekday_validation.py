"""Pre-register twelve cases and reuse exactly the validated debug parent."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    pointer=ROOT/'weekday_validation.json';assert not pointer.exists()
    stamp=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%y%m%d%H%M%S');work=ROOT.parent/('prototype_validation_'+stamp);work.mkdir()
    names=['artifacts.py','config.json','preferences.py','hazard.py','capacity.py','physics.py','fares.py','prepare.py','policy.py','metrics.py','engine.py','operations.py','run_case.py','fixtures.py','test_prototype.py','test_prediction_integration.py','dwell.py','input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md','analyze_followup.py']
    for n in names:shutil.copy2(ROOT/n,work/n)
    shutil.copytree(ROOT/'frozen',work/'frozen')
    for p in ROOT.glob('physical_paths_*.json.gz'):shutil.copy2(p,work/p.name)
    days={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}
    maincases=[{'case':f'distribution_v8-combined-{s}-{did}','mode':'combined','day':day,'scenario':s,'seed':0,'operations':'distribution_v8'} for s in ('regular','peak') for day,did in days.items()]
    seeds=[{'case':f'distribution_v8-combined-regular-mon-seed{seed}','mode':'combined','day':'월','scenario':'regular','seed':seed,'operations':'distribution_v8'} for seed in (1,2)]
    lock=read(ROOT/'experiment_lock.json');ref=lock['pilot_cases'][0]
    assert ref in maincases+seeds
    jobs=[c for c in maincases+seeds if c['case']!=ref['case']];assert len(jobs)==11
    lock.update(experiment_id=stamp,parent_candidate=str(ROOT),same_runtime_code_required=True,primary_operations='distribution_v8',
        operations_choice_reason='V8 distribution/entry-time profiles remain the requested primary input, registered before the outcomes; gate-reference clocks are a separate sensitivity.',
        pilot_cases=jobs,all_weekday_main_cases=maincases,reused_case={'case':ref,'directory':str(ROOT/'runs'/ref['case']/'attempt_01')},
        start_only_after_parent_passes=True,empirical_status='NOT_EVALUABLE',source_seeds_not_independent_field_observations=True)
    save(work/'experiment_lock.json',lock)
    save(work/'creation_manifest.json',{'parent':str(ROOT),'experiment_id':stamp,'source_code':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names},
        'production_latest_sha256':hashlib.sha256((ROOT.parent/'simulation_viewer_2026-11-07/public/routing-model/latest.json').read_bytes()).hexdigest(),
        'new_cases':11,'main_grid_cells':10,'additional_seed_cells':2,'new_user_approval_required_for_production':True})
    (work/'PLAN.md').write_text('''# 동일 코드의 평일·배차·난수 전수 검사

원래 수요·출발·목적지·44명/피크2대 공급·도로/보행망·운행시계·선호scale·무제한변경을 동결한다. 실패했던 월요일regular seed1을 고친 부모를 해시 검증 후 재사용하며 나머지11조건을 새로 실행한다. 주10조건은 월~금×regular/peak, 추가조건은 월regular seed1/2이다. 디버그에 사용한 seed는 독립실측이 아니다. 과거 시내 운행자료의 다른요일 전이는 가정이다.

20분은 모든 연속 정류장 대기의 검토 기준이고 강제 이탈·줄/수요/시간 삭제 규칙이 아니다. 전수 수지·FIFO·정원·준비 전 이탈·시간 연결·차량시각을 검산하고 도보·누적대기·총시간·변경횟수·미완료/창뒤완료를 함께 확인한다. 실패면 원인을 남기고 새 후보로 검토한다. 실측 정확도는NOT_EVALUABLE, 사용자 새 명시 승인 전 운영V11교체금지다.
''',encoding='utf8')
    save(pointer,{'directory':str(work),'experiment_id':stamp,'new_cells':11,'main_grid_cells':10,'production_approval_required':True});print(work)
if __name__=='__main__':main()
