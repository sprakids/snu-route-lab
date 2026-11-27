"""Lock weekday/scenario/seed validation before opening new outcomes."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json,hashlib,shutil
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    pointer=ROOT/'weekday_validation.json';assert not pointer.exists()
    stamp=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%y%m%d%H%M%S');work=ROOT.parent/('prototype_validation_'+stamp);work.mkdir()
    names=['artifacts.py','config.json','preferences.py','hazard.py','capacity.py','physics.py','fares.py','prepare.py','policy.py','metrics.py','engine.py','operations.py','run_case.py','fixtures.py','test_prototype.py','dwell.py','input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md','analyze_followup.py']
    for name in names:shutil.copy2(ROOT/name,work/name)
    shutil.copytree(ROOT/'frozen',work/'frozen')
    for p in ROOT.glob('physical_paths_*.json.gz'):shutil.copy2(p,work/p.name)
    days={'월':'mon','화':'tue','수':'wed','목':'thu','금':'fri'}
    full=[{'case':f'distribution_v8-combined-{scenario}-{did}','mode':'combined','day':day,'scenario':scenario,'seed':0,'operations':'distribution_v8'} for scenario in ('regular','peak') for day,did in days.items()]
    jobs=[c for c in full if c['case']!='distribution_v8-combined-regular-mon']
    jobs += [{'case':f'distribution_v8-combined-regular-mon-seed{seed}','mode':'combined','day':'월','scenario':'regular','seed':seed,'operations':'distribution_v8'} for seed in (1,2)]
    lock=read(ROOT/'experiment_lock.json');lock.update(experiment_id=stamp,parent_candidate=str(ROOT),
        same_runtime_code_required=True,primary_operations='distribution_v8',
        operations_choice_reason='V8 distribution/entry-time profiles are the explicitly requested primary correction; absolute gate-reference clocks remain a separate diagnostic alternative, not a selected accuracy winner.',
        pilot_cases=jobs,all_weekday_main_cases=full,reused_case={'case':full[0],'directory':str(ROOT/'runs/distribution_v8-combined-regular-mon/attempt_01')},
        start_only_after_parent_distribution_baseline_passes=True)
    save(work/'experiment_lock.json',lock)
    save(work/'creation_manifest.json',{'parent':str(ROOT),'experiment_id':stamp,'source_code':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names},
        'production_latest_sha256':hashlib.sha256((ROOT.parent/'simulation_viewer_2026-11-07/public/routing-model/latest.json').read_bytes()).hexdigest(),
        'new_cases':len(jobs),'main_grid_cells':10,'additional_seed_cells':2,'new_user_approval_required_for_production':True})
    (work/'PLAN.md').write_text('''# 평일·배차·난수 검증 확장

후속후보의 런타임·설정·수요·지형·44명/피크2대 공급을 그대로 동결한다. V8의 월요일 관측 분포/진입시각별 구간시간을 주 운행시계로 사용한다. 정문 절대 도킹참조는 별도 비교이며 배차분포와 동일한 것으로 표시하지 않는다. 다른요일 전이는 여전히 가정이다.

월~금×regular/peak10조건과 월요일regular seed1/2를 검증한다. 부모 월요일regular seed0은 완전감사·독립검산을 재사용하고 나머지11조건을 실제 계산한다. 부모의20분/수지 기준을 통과하기 전에는 실행하지 않는다. 같은seed라도 서로 다른 알고리즘의 난수호출까지 동일하다는 뜻은 아니다. 같은 원래 수요와 출발·목적지는 부모별로 짝지어 보존한다.

전 정류장 연속 대기·미완료/검열·준비 전 취소·도보·누적대기·총시간·정원·적격FIFO·승하차·차량시각을 검산한다. 실패하면 해당 조건의 원인을 추적하고 새 후보로 개선한다.20분에서 강제로 떠나게 하거나 수요/줄/시간을 자르지 않는다. 독립실측 부족은NOT_EVALUABLE이며 사용자 명시 승인 전 운영V11은 유지한다.
''',encoding='utf8')
    save(pointer,{'directory':str(work),'experiment_id':stamp,'new_cells':len(jobs),'main_grid_cells':10,'production_approval_required':True});print(work)

if __name__=='__main__':main()
