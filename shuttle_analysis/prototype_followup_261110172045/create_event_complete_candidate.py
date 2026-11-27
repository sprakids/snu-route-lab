"""Complete the walking/connection decision after a bus was rejected or full."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json,hashlib,shutil
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    pointer=ROOT/'event_complete_candidate.json';assert not pointer.exists()
    stamp=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%y%m%d%H%M%S');work=ROOT.parent/('prototype_followup_'+stamp);work.mkdir()
    names=['artifacts.py','config.json','preferences.py','hazard.py','capacity.py','physics.py','fares.py','prepare.py','policy.py','metrics.py','engine.py','operations.py','run_case.py','fixtures.py','test_prototype.py','dwell.py','input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md']
    for name in names:shutil.copy2(ROOT/name,work/name)
    shutil.copytree(ROOT/'frozen',work/'frozen')
    for p in ROOT.glob('physical_paths_*.json.gz'):shutil.copy2(p,work/p.name)
    lock=read(ROOT/'experiment_lock.json');lock.update(experiment_id=stamp,parent_followup=str(ROOT),
        hypothesis='Only residual21.26min case voluntarily rejected three spacious buses because onward options were unattractive. Boarding compared board/wait but never walking alternatives. Review connection/walk alternatives after each rejected/full service event.',
        full_and_voluntary_declines_are_separate=True,same_clock_batch_reviews_deduplicated=True)
    save(work/'experiment_lock.json',lock)
    p=work/'engine.py';s=p.read_text(encoding='utf8')
    a="        if kind=='patience':";assert a in s
    s=s.replace(a,'''        if kind=='service_review':
            state,visit=payload
            if state['done'] or state['visit']!=visit or not state['queued']:continue
            if not maybe_switch(state,t,'service_rejected_or_full'):reschedule(state,t)
            continue
'''+a,1)
    a="                    voluntary.add(state['sid']);continue";assert a in s
    s=s.replace(a,'''                    voluntary.add(state['sid'])
                    if state.get('service_review_pending_clock')!=t:
                        state['service_review_pending_clock']=t
                        push(t+.001,2,'service_review',(state,state['visit']))
                    continue''',1)
    a="                reschedule(state,t if config['behavior']!='v9_frozen' else t+.001)";assert a in s
    s=s.replace(a,a+'''
                if config['behavior']!='v9_frozen' and state.get('service_review_pending_clock')!=t:
                    state['service_review_pending_clock']=t
                    push(t+.001,2,'service_review',(state,state['visit']))''',1);p.write_text(s,encoding='utf8')
    save(work/'creation_manifest.json',{'experiment_id':stamp,'parent':str(ROOT),'source_code':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names},
        'production_latest_sha256':hashlib.sha256((ROOT.parent/'simulation_viewer_2026-11-07/public/routing-model/latest.json').read_bytes()).hexdigest(),
        'no20_time_trigger':True,'actual_supply_demand_capacity_unchanged':True,'approval_required_before_production':True})
    (work/'PLAN.md').write_text('''# 차량 사건 뒤 연결·도보 선택 완성

이전 후보의 연속 대기20분 초과는0.210069명 상당·회 한 사례였다. 그 합성 통행은 순환셔틀의 여석60/59.42/60명 차량 세 대를 자발적으로 보내면서 기다렸다. 승차 선택이 현재 탑승/다음차 대기만 비교하고 실제 다른 정류장·도보 대안을 그 순간에는 비교하지 않은 누락을 고친다.

만차 탑승 실패 또는 자발적 승차 보류를 관측하면 차량 처리 직후0.001초에 연결·도보 대안을 재판단한다. 같은 시각 두 차량 뒤에는 한 번만 재판단하며, 그 사이 두 번째 차량에 탔다면 취소한다. 계속 대기도 실제 선택지이며 강제 변경은 없다. 같은 물리적 줄의 시각/FIFO/횟수는 초기화하지 않는다.20분이나 정원·수요·배차는 바꾸지 않는다.

월요일 baseline부터 전체 수지·대기를 검산한다. 통과하면 고정된 운행 보정 축과 나머지요일/배차로 확장한다. 독립실측 부족은NOT_EVALUABLE로 남기고 사용자 승인 전 운영V11을 바꾸지 않는다.
''',encoding='utf8')
    save(pointer,{'experiment_id':stamp,'directory':str(work),'approval_required_before_production':True});print(work)

if __name__=='__main__':main()
