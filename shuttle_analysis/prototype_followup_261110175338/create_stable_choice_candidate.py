"""Separate the decision to reroute from route-menu enumeration."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json,hashlib,shutil
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    pointer=ROOT/'stable_choice_candidate.json';assert not pointer.exists()
    stamp=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%y%m%d%H%M%S');work=ROOT.parent/('prototype_followup_'+stamp);work.mkdir()
    names=['artifacts.py','config.json','preferences.py','hazard.py','capacity.py','physics.py','fares.py','prepare.py','policy.py','metrics.py','engine.py','operations.py','run_case.py','fixtures.py','test_prototype.py','dwell.py','input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md','analyze_followup.py','create_weekday_validation.py']
    for name in names:shutil.copy2(ROOT/name,work/name)
    shutil.copytree(ROOT/'frozen',work/'frozen')
    for p in ROOT.glob('physical_paths_*.json.gz'):shutil.copy2(p,work/p.name)
    cfg=read(work/'config.json');cfg.update(switch_stress_time_scale_seconds=600,switch_full_stress_coefficient=.25,
        route_menu_normalized_within_same_access=True,known_information='Fixed exogenous scenario clocks known to agents, current simulated queues/onboard states and past residual seats; not a validated real-time forecast. Inferred/V8 clocks are not official published dispatches.')
    save(work/'config.json',cfg);lock=read(ROOT/'experiment_lock.json');lock.update(experiment_id=stamp,parent_followup=str(ROOT),
        hypothesis='A flat MNL with one stay action and many overlapping transfer strategies inflates rerouting and can create high-change-count detours. Decide stay/change using best utility gain and count/stress, then choose a route conditional on changing. Split prior mass between strategies with the same walk access.',
        supply_clock_perfect_information_scenario=True,not_a_realtime_supply_forecast_validation=True)
    save(work/'experiment_lock.json',lock)
    p=work/'policy.py';s=p.read_text(encoding='utf8');marker='def signature(stages):';assert marker in s
    helper='''def adoption_probability(stay_score,best_score,count,age,full,future_wait,config):
    temperature=config['choice_temperature_minutes']
    gain=max(-50.,min(50.,(stay_score-best_score)/temperature))
    worthwhile=1./(1.+math.exp(-gain))
    ordinary=config['repeat_multiplier']**count
    scale=config.get('switch_stress_time_scale_seconds',600.)
    stress=-math.expm1(-(max(0.,age)/scale)**3-(max(0.,future_wait)/scale)**3-config.get('switch_full_stress_coefficient',.25)*full)
    return worthwhile*(ordinary+(1-ordinary)*stress)


'''
    s=s.replace(marker,helper+marker,1)
    a="            selected=choose(candidates,identity,('reroute',state['visit'],state['review_ordinal']),config)";assert a in s
    b='''            alternatives=[c for c in candidates if c['option'] is not None]
            staying=next((c for c in candidates if c['option'] is None),None)
            selected=staying
            if alternatives:
                temperature=config['choice_temperature_minutes']
                best=min(c['cost']-temperature*math.log(max(1e-300,c.get('prior',1.))) for c in alternatives)
                chance=1. if staying is None else adoption_probability(staying['cost'],best,count,at-state['stop_entry'],state['full_passes'],current.first_wait,config)
                if uniform(config['seed'],identity,'adopt-reroute',state['visit'],state['review_ordinal'])<chance:
                    groups=Counter(c['option']['walk'][0] for c in alternatives)
                    conditional=[{**c,'prior':c.get('prior',1.)/groups[c['option']['walk'][0]]} for c in alternatives]
                    selected=choose(conditional,identity,('reroute',state['visit'],state['review_ordinal']),config)'''
    s=s.replace(a,b,1);p.write_text(s,encoding='utf8')
    save(work/'creation_manifest.json',{'experiment_id':stamp,'parent':str(ROOT),'parent_source_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names},
        'production_latest_sha256':hashlib.sha256((ROOT.parent/'simulation_viewer_2026-11-07/public/routing-model/latest.json').read_bytes()).hexdigest(),
        'no20_force_or_clipping':True,'actual_supply_demand_prep_unchanged':True,'production_approval_required':True})
    (work/'PLAN.md').write_text('''# 경로 메뉴 크기와 실제 변경 결정을 분리

직전 후보에는20분초과 두 분할통행이 남았고 각각이전변경4/7회였다. 많은 비슷한 환승경로를 각각 독립 선택지로 두면 ‘계속대기’ 한 개에 비해 ‘변경’ 묶음의 확률이 부풀 수 있다. 변경여부는 최선의 대안과 현재 전략의 효용 차이로 따로 결정하고, 변경할 때 그 안의 경로를 선택한다. 같은 도보 접근 경로를 공유하는 전략에는 접근 고려도의 총량을 나누어 준다.

기본 변경성향의0.3^횟수 감소와, 이미 기다린 시간/개인만차/예상 추가대기의 스트레스를 분리한다. 횟수 예산·소진·최댓값은 없다. 실제 ETA·수요·정원·배차·준비20초는 유지한다.20분 지점의 강제이탈·대기 자르기는 없다.

고정 외생 공급 시계를 여행자도 아는 조건부 시나리오이다. V8추정 시계는 공식 공개 배차표가 아니며 실제·인지 공급시계를 분리한 실시간 예측 검증은 아니다. 승차는 board/wait 뒤 거절·만차일 때 도보 연결을 다시 보는 두 단계로, 완전한 동시3지선다/조기하차 선택은 미구현이다. 한계를 숨기지 않고 독립실측 부족은NOT_EVALUABLE로 남긴다. 사용자 명시승인 전 운영V11을 바꾸지 않는다.
''',encoding='utf8')
    save(pointer,{'experiment_id':stamp,'directory':str(work),'approval_required_before_production':True});print(work)

if __name__=='__main__':main()
