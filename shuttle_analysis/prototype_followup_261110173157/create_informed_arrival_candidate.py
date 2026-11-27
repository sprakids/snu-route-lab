"""Review material queue/timetable information on physical arrival, without a20min cutoff."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json,hashlib,shutil
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    pointer=ROOT/'informed_arrival_candidate.json';assert not pointer.exists()
    stamp=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%y%m%d%H%M%S');work=ROOT.parent/('prototype_followup_'+stamp);work.mkdir()
    names=['artifacts.py','config.json','preferences.py','hazard.py','capacity.py','physics.py','fares.py','prepare.py','policy.py','metrics.py','engine.py','operations.py','run_case.py','fixtures.py','test_prototype.py','dwell.py','input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md','analyze_followup.py','create_weekday_validation.py']
    for name in names:shutil.copy2(ROOT/name,work/name)
    shutil.copytree(ROOT/'frozen',work/'frozen')
    for p in ROOT.glob('physical_paths_*.json.gz'):shutil.copy2(p,work/p.name)
    cfg=read(work/'config.json');cfg['arrival_information_wait_scale_seconds']=300;save(work/'config.json',cfg)
    lock=read(ROOT/'experiment_lock.json');lock.update(experiment_id=stamp,parent_followup=str(ROOT),
        hypothesis='V8 residual20.05775min episode arrived3.465s before a20min reverse-shuttle service but was not ready after the preserved20s preparation. Material next-service gap/queue should raise the probability of reviewing alternatives at arrival, rather than keeping the fixed25percent ordinary rate.',
        ordinary_repeat_decay_preserved=True,preparation_semantics_and_physical_wait_definition_preserved=True)
    lock['pilot_cases']=sorted(lock['pilot_cases'],key=lambda c:{'distribution_v8':0,'gate_reference':1,'baseline':2}[c['operations']])
    save(work/'experiment_lock.json',lock)
    p=work/'policy.py';s=p.read_text(encoding='utf8');a="                p=config['arrival_review_probability']*config['repeat_multiplier']**count";assert a in s
    s=s.replace(a,a+'''
                # Published/model schedule and the currently visible queue only.
                # This is a REVIEW chance, not forced rerouting or shorter ETA.
                stage=current_stage(state)
                next_row=next((row for row in schedule[node] if row[0]>=state['ready_time']-EPS
                    and vehicles[row[1]]['last_stop']<row[2] and stage_choice(stage,vehicles[row[1]]['rid'],row[2]) is not None),None)
                gap=max(0.,next_row[0]-at) if next_row else math.inf
                capacity=vehicles[next_row[1]]['cap'] if next_row else 1.
                visible=qmass[node]+premass[node]
                stress=-math.expm1(-(gap/config.get('arrival_information_wait_scale_seconds',300.))**2-(visible/max(1.,capacity))**2)
                p=p+(1-p)*stress''',1)
    s=s.replace("from engine import first_boardable,scaled_stages,stage_choice","from engine import first_boardable,scaled_stages,stage_choice",1)
    p.write_text(s,encoding='utf8')
    save(work/'creation_manifest.json',{'experiment_id':stamp,'parent':str(ROOT),'parent_source_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names},
        'production_latest_sha256':hashlib.sha256((ROOT.parent/'simulation_viewer_2026-11-07/public/routing-model/latest.json').read_bytes()).hexdigest(),
        'no20_force_or_clipping':True,'actual_supply_demand_and_prep_unchanged':True,'production_approval_required':True})
    (work/'PLAN.md').write_text('''# 도착 시 새 정보에 따른 재판단 보완

이전V8결합 후보에서 역순환셔틀의20분 간격과 준비20초가 맞물려 한 통행이20분3.465초 기다렸다. 준비시간을 빼거나 대기 정의·수요·배차를 바꾸지 않는다.20분에 강제로 나가게 하지 않는다.

정류장에 실제 도착해 긴 다음차 공백 또는 큰 줄을 확인하면 대안 검토 확률을 부드럽게 높인다. 기본25%×0.3^변경횟수는 유지하고, 공개/모형 시각표의 대기공백과 현재 줄만으로 추가 정보 강도를 계산한다.5분은 이름 붙인 미보정 검토 민감도이며 학교 실측값이 아니다. 검토 후 계속 대기도 실제 선택지이다. 지도/조회 갱신 횟수는 이 판단에 영향을 주지 않는다.

주 운행보정V8/별도 도킹참조/기존시계의 월요일부터 확인한다. 통과 시 동일 코드를 평일·배차·난수 확장 검증한다. 독립실측 부족은NOT_EVALUABLE로 유지하며 사용자 명시 승인 전 운영V11을 바꾸지 않는다.
''',encoding='utf8')
    old_validation=read(ROOT/'weekday_validation.json')
    save(Path(old_validation['directory'])/'not_started_parent_gate_failed.json',{'status':'NOT_STARTED_PARENT_GATE_FAILED','parent_max_wait_min':20.05775390643636,'over20_weight':.48407215847191526,'reason':'Do not round3.465seconds away or silently change20minute definition'})
    save(pointer,{'experiment_id':stamp,'directory':str(work),'approval_required_before_production':True});print(work)

if __name__=='__main__':main()
