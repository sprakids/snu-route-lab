"""Address residual long queues before entry, without forcing a late walk-away."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json,hashlib,shutil
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    pointer=ROOT/'preemptive_candidate.json';assert not pointer.exists()
    stamp=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%y%m%d%H%M%S');work=ROOT.parent/('prototype_followup_'+stamp);work.mkdir()
    names=['artifacts.py','config.json','preferences.py','hazard.py','capacity.py','physics.py','fares.py','prepare.py','policy.py','metrics.py','engine.py','operations.py','run_case.py','fixtures.py','test_prototype.py','dwell.py','input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md']
    for name in names:shutil.copy2(ROOT/name,work/name)
    shutil.copytree(ROOT/'frozen',work/'frozen')
    for p in ROOT.glob('physical_paths_*.json.gz'):shutil.copy2(p,work/p.name)
    config=read(work/'config.json');config.update(predicted_queue_curvature_scale_seconds=600,predicted_queue_curvature_coefficient=1.)
    save(work/'config.json',config);lock=read(ROOT/'experiment_lock.json')
    lock.update(experiment_id=stamp,parent_followup=str(ROOT),
        hypothesis='Residual21.90min case reconsidered often and rationally stayed when the next bus was already close. Address entry into long predicted queues via a smooth convex wait preference from zero, not a20min forced exit.',
        baseline_gate_before_extending_cases=True,control_comparison_is_current_V11_and_same_physical_old_behavior=True)
    save(work/'experiment_lock.json',lock)
    p=work/'preferences.py';s=p.read_text(encoding='utf8');assert '    first_wait:float=0.' in s;s=s.replace('    first_wait:float=0.','    first_wait:float=0.\n    wait_squared:float=0.',1);p.write_text(s,encoding='utf8')
    p=work/'policy.py';s=p.read_text(encoding='utf8')
    a='first_wait=0.;chain=list(stages);count=0';assert a in s;s=s.replace(a,'first_wait=wait_squared=0.;chain=list(stages);count=0',1)
    a='                if count==0:first_wait=max(0.,when-ready)+max(0.,ready-cursor)';assert a in s
    s=s.replace(a,a+'\n                wait_squared+=max(0.,when-cursor)**2',1)
    a='return Prediction(cursor,walk,wait,ride,prep,transfers,fee,crowd,fatigue,first_wait)';assert a in s
    s=s.replace(a,'return Prediction(cursor,walk,wait,ride,prep,transfers,fee,crowd,fatigue,first_wait,wait_squared)',1)
    a="            base=cost(pred,state['traits'],len(state['history']),changing,config['fare_in_choice'])";assert a in s
    s=s.replace(a,a+"\n            base+=state['traits'].wait*config.get('predicted_queue_curvature_coefficient',0.)*pred.wait_squared/(60*config.get('predicted_queue_curvature_scale_seconds',600.))",1);p.write_text(s,encoding='utf8')
    save(work/'creation_manifest.json',{'experiment_id':stamp,'parent':str(ROOT),'source_code':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names},
        'production_latest_sha256':hashlib.sha256((ROOT.parent/'simulation_viewer_2026-11-07/public/routing-model/latest.json').read_bytes()).hexdigest(),
        'no_time_clipping_or_forced_exit':True,'same_actual_supply_demand':True,'new_explicit_user_approval_required_for_production':True})
    (work/'PLAN.md').write_text('''# 대기열 진입 전 판단 보완 후보

이전 후보는 최대21.90분/20분초과 약14.09 가중사건이 남았다. 최장 사례는19.9분에도13개 대안을 비교했으나 곧 오는 셔틀이 더 싸고 빨라 계속 기다렸다.20분 직전에 강제로 걷게 만드는 수정은 하지 않는다.

대신 출발·환승·재판단 단계 모두에서 예상 정류장별 대기가 길수록 매끄럽게 불편이 커지는 선호비용 W²/(600초)을 추가한다.600초는 이름 붙인 미보정 선호 시나리오이며 실제 학교 추정값이 아니다. 분 단위 비용이고 실제 ETA·차량시각·누적실제대기에는 가산하지 않는다.20분 지점에 분기나 강제 이탈을 만들지 않는다.

같은4.8km/h·수요·seed·44명/피크2대의 월요일 baseline 파일럿에서 먼저 전체 수지와 연속 대기를 검사한다. 기준 미달이면 원인을 추적해 별도 다음 후보로 계속한다. 통과하면 관측 운행 보정/정문 도킹참조와 다른요일·배차로 확장한다. 운영V11은 사용자 명시 승인 전 교체하지 않는다.
''',encoding='utf8')
    save(pointer,{'experiment_id':stamp,'directory':str(work),'production_approval_required':True});print(work)

if __name__=='__main__':main()
