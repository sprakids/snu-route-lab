"""A separately locked candidate: bounded forecast horizon and marginal wait aversion."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json,hashlib,shutil
ROOT=Path(__file__).resolve().parent
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    pointer=ROOT/'balanced_candidate.json';assert not pointer.exists()
    stamp=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%y%m%d%H%M%S');work=ROOT.parent/('prototype_followup_'+stamp);work.mkdir()
    names=['artifacts.py','config.json','preferences.py','hazard.py','capacity.py','physics.py','fares.py','prepare.py','policy.py','metrics.py','engine.py','operations.py','run_case.py','fixtures.py','test_prototype.py','dwell.py','input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md']
    for name in names:shutil.copy2(ROOT/name,work/name)
    shutil.copytree(ROOT/'frozen',work/'frozen')
    for p in ROOT.glob('physical_paths_*.json.gz'):shutil.copy2(p,work/p.name)
    config=json.loads((work/'config.json').read_text(encoding='utf8'))
    config.update(seat_forecast_horizon_seconds=1800,waiting_discomfort_age_scale_seconds=600,waiting_discomfort_full_sensitivity=.5,
        waiting_discomfort_is_marginal_remaining_wait_not_elapsed_eta=True)
    save(work/'config.json',config)
    lock=json.loads((ROOT/'experiment_lock.json').read_text(encoding='utf8'));lock.update(experiment_id=stamp,
        parent_followup=str(ROOT),hypothesis='Do not extrapolate three observed full model buses to zero seats for the entire remaining day. Bound the historical-seat scenario to30minutes and increase aversion to ADDITIONAL waiting after experienced delay/full passes.',
        prior_candidate_results_used_for_this_hypothesis=False,old_behavior_controls_reference=str(ROOT),
        control_equivalence='Changes are guarded by sequential behavior, so prior physics-mode controls use identical code paths and clocks; reference source hashes stay separate.')
    lock['pilot_cases']=[{'case':f'{op}-combined-regular-mon','mode':'combined','day':'월','scenario':'regular','seed':0,'operations':op} for op in ('baseline','distribution_v8','gate_reference')]
    save(work/'experiment_lock.json',lock)
    p=work/'engine.py';s=p.read_text(encoding='utf8');a="    if vehicle.get('times',[float('inf')]*(k+1))[k]<=now+EPS:return available";assert a in s
    s=s.replace(a,a+"\n    if vehicle.get('times',[float('inf')]*(k+1))[k]-now>vehicle.get('seat_forecast_horizon_seconds',1800):return available",1)
    a="'seat_history_count':config.get('seat_history_count',3),";assert a in s
    s=s.replace(a,"'seat_forecast_horizon_seconds':config.get('seat_forecast_horizon_seconds',1800),"+a,1);p.write_text(s,encoding='utf8')
    p=work/'policy.py';s=p.read_text(encoding='utf8')
    a="            return cost(pred,state['traits'],len(state['history']),changing,config['fare_in_choice'])";assert a in s
    s=s.replace(a,'''            base=cost(pred,state['traits'],len(state['history']),changing,config['fare_in_choice'])
            # State-dependent dislike of MORE standing in the CURRENT queue.
            # Elapsed waiting is never re-added to physical ETA or total time.
            if not changing and pred.wait>0:
                clock=pred.eta-(pred.walk+pred.wait+pred.ride+pred.prep)
                age=max(0.,clock-state['stop_entry'])
                extra=config.get('waiting_discomfort_full_sensitivity',0.)*state['full_passes']+(age/config.get('waiting_discomfort_age_scale_seconds',600.))**2
                base+=state['traits'].wait*(pred.wait+pred.prep)/60*extra
            return base''',1);p.write_text(s,encoding='utf8')
    save(work/'creation_manifest.json',{'experiment_id':stamp,'parent':str(ROOT),'source_code':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names},
        'production_latest_sha256':hashlib.sha256((ROOT.parent/'simulation_viewer_2026-11-07/public/routing-model/latest.json').read_bytes()).hexdigest(),
        'forced20_exit':False,'actual_supply_demand_capacity_unchanged':True,'production_replacement_requires_user_approval':True})
    (work/'PLAN.md').write_text('''# 후속 균형 예측 후보

운영V11은 명시 승인 전 교체하지 않는다. 이전9파일럿과 첫 후속 후보의 실행·실패는 보존한다.

과거3회 여석0을 하루 끝까지 그대로 연장하는 것은 가용 정보 범위를 넘을 수 있다.30분 이내의 보수 예측 시나리오로 한정하고 그 밖 미래는 기존 공급 가정으로 되돌린다. 실제 정원·승하차·배차를 바꾸지 않는다.

오래 기다리거나 만차를 겪으면 현재 줄에서 추가로 기다리는 것을 더 싫어하도록 잔여 대기의 선호비용을 높인다. 이미 지난 대기를 ETA에 더하지 않는다. 대안으로 실제 이동한 후의 걷기·줄·환승은 그대로 계산한다.20분 강제 이탈이나 대기·인원 자르기를 사용하지 않는다.

이름 붙인 미보정 행동 시나리오이며 실측 계수 추정이 아니다. 같은 수요·물리시간·seed·44/피크2대에서 세 종류 시계의 월요일 파일럿을 먼저 확인하고,20분 초과 원인에 따라 후속 개선·다른 요일 검증으로 확장한다.
''',encoding='utf8')
    save(pointer,{'experiment_id':stamp,'directory':str(work),'required_user_approval_before_production_replacement':True});print(work,flush=True)

if __name__=='__main__':main()
