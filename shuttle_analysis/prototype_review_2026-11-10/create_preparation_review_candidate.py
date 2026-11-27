"""Preserve failed candidates and test a general missed-service information event."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json,hashlib,shutil
ROOT=Path(__file__).resolve().parent
PARENT=ROOT.parent/'prototype_followup_261110173157'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    pointer=ROOT/'preparation_review_candidate.json';assert not pointer.exists()
    stamp=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%y%m%d%H%M%S')
    work=ROOT.parent/('prototype_followup_'+stamp);work.mkdir()
    names=['artifacts.py','config.json','preferences.py','hazard.py','capacity.py','physics.py','fares.py','prepare.py','policy.py','metrics.py','engine.py','operations.py','run_case.py','fixtures.py','test_prototype.py','dwell.py','input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md','analyze_followup.py','create_weekday_validation.py']
    for n in names:shutil.copy2(PARENT/n,work/n)
    shutil.copytree(PARENT/'frozen',work/'frozen')
    for p in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(p,work/p.name)
    cfg=read(work/'config.json');cfg.update(review_service_missed_during_preparation=True,
        known_information='Fixed exogenous scenario clocks known to agents, current simulated queues/onboard states and past residual seats; not a validated real-time forecast. V8 clocks are inferred, not official published timetables.')
    save(work/'config.json',cfg)
    lock=read(PARENT/'experiment_lock.json');lock.update(experiment_id=stamp,parent_followup=str(PARENT),
        hypothesis='A compatible vehicle passing during the unchanged twenty-second preparation was absent from the information-event stream. Reconsider once ready after that observed missed service, including short missed headways; do not force a change.',
        supply_clock_perfect_information_scenario=True,not_a_realtime_supply_forecast_validation=True)
    lock['pilot_cases']=sorted(lock['pilot_cases'],key=lambda c:({'distribution_v8':0,'baseline':1,'gate_reference':2}[c['operations']]))
    save(work/'experiment_lock.json',lock)
    p=work/'engine.py';s=p.read_text(encoding='utf8')
    def sub(old,new):
        nonlocal s
        assert s.count(old)==1,(old,s.count(old));s=s.replace(old,new,1)
    sub('    premass=[0.]*len(nodes)','    premass=[0.]*len(nodes)\n    preparing_states=[{} for _ in nodes]')
    sub("            state['preparing']=True;premass[state['node']]+=state['w']", "            state['preparing']=True;premass[state['node']]+=state['w']\n            state['missed_during_preparation']=False\n            preparing_states[state['node']][state['sid']]=state")
    sub("        if kind=='service_review':", "        if kind in ('service_review','preparation_review'):")
    sub("            if not maybe_switch(state,t,'service_rejected_or_full'):reschedule(state,t)", "            reason='service_missed_during_preparation' if kind=='preparation_review' else 'service_rejected_or_full'\n            if not maybe_switch(state,t,reason):reschedule(state,t)")
    sub("            if state['done'] or not state.get('preparing'):continue", "            preparing_states[state['node']].pop(state['sid'],None)\n            if state['done'] or not state.get('preparing'):continue")
    sub("            reschedule(state,t if config['behavior']!='v9_frozen' else t+settings['recheck_seconds']);continue", "            reschedule(state,t if config['behavior']!='v9_frozen' else t+settings['recheck_seconds'])\n            if config['behavior']!='v9_frozen' and state.get('missed_during_preparation'):\n                push(t+.001,2,'preparation_review',(state,state['visit']))\n            continue")
    sub("            queue=queues[node];available=seats(vehicle['cap'],vehicle['load']);voluntary=set()", "            if config['behavior']!='v9_frozen' and config.get('review_service_missed_during_preparation',False):\n                for sid,waiting in list(preparing_states[node].items()):\n                    if not waiting.get('preparing') or waiting['node']!=node:\n                        preparing_states[node].pop(sid,None);continue\n                    if t<waiting['ready_time']-EPS and stage_choice(current_stage(waiting),rid,k) is not None:\n                        waiting['missed_during_preparation']=True\n            queue=queues[node];available=seats(vehicle['cap'],vehicle['load']);voluntary=set()")
    p.write_text(s,encoding='utf8')
    p=work/'test_prototype.py';s=p.read_text(encoding='utf8');marker='    def test_unserved_and_long_waits_are_preserved_without_forcing(self):'
    assert marker in s
    tests='''    def test_missed_preparation_service_triggers_review_without_changing_ready_clock(self):
        cfg={'behavior':'sequential','arrival_review_probability':0,'review_base_rate_per_second':0,
             'review_age_stress_rate_per_second':0,'review_full_stress_rate_per_second':0}
        b=fixture([('A',10,10)],cfg);b['supply']['regular']['A']=[START+10,START+1300]
        b['alternatives']['0|snu']=[{'kind':'walk','name':'walk','walk':[0,600.],'walk_meters':500.,'stages':[]}]
        def pick(candidates,*args):return next((c for c in candidates if c.get('option')),candidates[0] if candidates else None)
        with patch('policy.choose',side_effect=pick):data,audit=self.run_case(b)
        row=audit['wait_audit'][0]
        self.assertEqual(row['ready_at'],START+21);self.assertAlmostEqual(row['leave_at'],START+21.001)
        self.assertEqual(row['full_passes_seen'],0)
        self.assertEqual(audit['behavior_decisions'][0]['reason'],'service_missed_during_preparation')
        self.assertFalse(audit['behavior_decisions'][0]['forced']);self.assertEqual(data['report']['final_weight'],10)
    def test_preparation_information_does_not_force_change_or_remove_long_wait(self):
        cfg={'behavior':'sequential','arrival_review_probability':0,'review_base_rate_per_second':0,
             'review_age_stress_rate_per_second':0,'review_full_stress_rate_per_second':0}
        b=fixture([('A',10,10)],cfg);b['supply']['regular']['A']=[START+10,START+1300]
        data,audit=self.run_case(b)
        self.assertAlmostEqual(audit['wait_audit'][0]['end']-audit['wait_audit'][0]['arrival'],1299)
        self.assertEqual(audit['behavior_decisions'],[]);self.assertEqual(data['report']['unserved_trip_weight'],0)
'''
    p.write_text(s.replace(marker,tests+marker,1),encoding='utf8')
    (work/'PLAN.md').write_text('''# 준비 중 놓친 차량을 정보 사건으로 반영

R4는 월요일 V8 조건에서 단 한 분할통행이 20분 3.465초를 기다렸다. 정류장 도착 3.465초 뒤의 차량을 20초 준비가 끝나지 않아 놓쳤지만, 대안 검토는 적격 대기열의 만차·승차 거절에만 연결되어 있었다. 준비 중 실제로 지나간 호환 차량을 보고 준비 완료 직후 한 번 대안을 검토하도록 보완한다. 도착·준비·FIFO·배차·정원·수요는 그대로이며 변경은 확률적 선택이고 의무가 아니다. 이 관측 사건은 모든 노선·정류장·요일에 동일하게 적용한다.

R5의 광범위 도착 검토 강화와 R6의 별도 변경 채택 규칙은 일부 장기대기를 더 만들었으므로 그대로 보존한 뒤, R4의 더 작은 누락만 보완하는 별도 후보를 만든다. 개선은 비단조적이며 여러 난수의 실패가 있을 수 있다. 횟수 상한·소진은 없고 기본 검토율은 0.3^변경횟수로 감소하되 시간·만차 스트레스는 별도다.

고정 외생 공급시계를 여행자가 아는 조건부 시뮬레이션이며 실시간 예측 검증은 아니다. 승차/계속대기 후 도보를 재검토하는 두 단계 선택, 겹친 경로 메뉴, 네트워크 전체 승하차 체류 미통합, 미실측 교외 승객 등의 한계가 남는다. 독립실측 부족은 NOT_EVALUABLE이며 사용자 명시 승인 전 V11을 교체하지 않는다.
''',encoding='utf8')
    save(work/'creation_manifest.json',{'experiment_id':stamp,'parent':str(PARENT),'parent_source_sha256':{n:hashlib.sha256((PARENT/n).read_bytes()).hexdigest() for n in names},
        'production_latest_sha256':hashlib.sha256((ROOT.parent/'simulation_viewer_2026-11-07/public/routing-model/latest.json').read_bytes()).hexdigest(),
        'actual_supply_demand_preparation_unchanged':True,'no20_force_or_clipping':True,'production_approval_required':True})
    save(pointer,{'experiment_id':stamp,'directory':str(work),'approval_required_before_production':True});print(work)
if __name__=='__main__':main()
