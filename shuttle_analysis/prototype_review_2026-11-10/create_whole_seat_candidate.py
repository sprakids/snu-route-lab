"""Test a whole-person, indivisible forecast without changing physical mass flow."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent/'prototype_followup_261110181553'
def read(p):return json.loads(p.read_text(encoding='utf8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    pointer=ROOT/'whole_seat_candidate.json';assert not pointer.exists()
    stamp=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%y%m%d%H%M%S');work=ROOT.parent/('prototype_followup_'+stamp);work.mkdir()
    names=['artifacts.py','config.json','preferences.py','hazard.py','capacity.py','physics.py','fares.py','prepare.py','policy.py','metrics.py','engine.py','operations.py','run_case.py','fixtures.py','test_prototype.py','dwell.py','input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md','analyze_followup.py','create_weekday_validation.py']
    for n in names:shutil.copy2(PARENT/n,work/n)
    shutil.copytree(PARENT/'frozen',work/'frozen')
    for p in PARENT.glob('physical_paths_*.json.gz'):shutil.copy2(p,work/p.name)
    cfg=read(work/'config.json');cfg.update(forecast_person_requires_whole_seat=True,
        forecast_seat_interpretation='Conservative choice scenario: each weighted traveler requests one indivisible seat; round fractional future residual estimates down, not actual current capacity or physical boardings. Not an estimated boarding probability or validated ETA.')
    save(work/'config.json',cfg)
    lock=read(PARENT/'experiment_lock.json');lock.update(experiment_id=stamp,parent_followup=str(PARENT),
        hypothesis='R7 Thupeak traveler weight0.0548 considered a predicted0.137 residual seat sufficient. Replay found zero people ahead, so ghost clearance is not the focal cause. Forecast choice for an individual uses one indivisible seat and a whole-seat conservative future-residual estimate; actual weighted mass, capacity and boarding remain unchanged.',
        pilot_cases=[{'case':'distribution_v8-combined-peak-thu','mode':'combined','day':'목','scenario':'peak','seed':0,'operations':'distribution_v8'},
                     {'case':'baseline-combined-regular-mon','mode':'combined','day':'월','scenario':'regular','seed':0,'operations':'baseline'},
                     {'case':'gate_reference-combined-regular-mon','mode':'combined','day':'월','scenario':'regular','seed':0,'operations':'gate_reference'}])
    save(work/'experiment_lock.json',lock)
    p=work/'engine.py';s=p.read_text(encoding='utf8')
    def sub(old,new):
        nonlocal s
        assert s.count(old)==1,(old,s.count(old));s=s.replace(old,new,1)
    start=s.index('def forecast_available(');end=s.index('\ndef indexed_boardable(',start)
    s=s[:start]+'''def forecast_available(vehicle,k,now,available):
    when=vehicle.get('times',[float('inf')]*(k+1))[k]
    if when<=now+EPS:return available  # Known current physical state unchanged.
    result=available
    if when-now<=vehicle.get('seat_forecast_horizon_seconds',1800):
        history=vehicle.get('seat_history',{}).get((vehicle['rid'],k),[])
        recent=[free for at,free in history if 0<=now-at<=vehicle.get('seat_history_seconds',1800)]
        recent=recent[-vehicle.get('seat_history_count',3):]
        if len(recent)>=2:result=min(result,min(recent))
    # This is a conservative future choice estimate, not fewer actual seats.
    return float(math.floor(max(0.,result)+EPS)) if vehicle.get('whole_seat_forecast',False) else result

''' + s[end:]
    sub('def indexed_boardable(rows,vehicles,ready,now,stage,weight,view):','def indexed_boardable(rows,vehicles,ready,now,stage,weight,view,indivisible=False):')
    sub('                need-=available','                if not indivisible:need-=available')
    sub('def first_boardable(rows,vehicles,ready,now,stage,weight,waiting):','def first_boardable(rows,vehicles,ready,now,stage,weight,waiting,indivisible=False):')
    sub('return indexed_boardable(rows,vehicles,ready,now,stage,weight,waiting)','return indexed_boardable(rows,vehicles,ready,now,stage,weight,waiting,indivisible)')
    sub('        need-=available','        if not indivisible:need-=available')
    sub("            vehicle={'id':vid,'rid':rid,'cap':", "            vehicle={'whole_seat_forecast':bool(config.get('forecast_person_requires_whole_seat',False) and config['behavior']!='v9_frozen'),'id':vid,'rid':rid,'cap':")
    p.write_text(s,encoding='utf8')
    p=work/'policy.py';s=p.read_text(encoding='utf8')
    old="                    choice=first_boardable(rows,vehicles,ready,now,stage,state['w'],view)";assert old in s
    s=s.replace(old,"                    whole=config.get('forecast_person_requires_whole_seat',False)\n                    request=max(1.,state['w']) if whole else state['w']\n                    choice=first_boardable(rows,vehicles,ready,now,stage,request,view,indivisible=whole)",1)
    p.write_text(s,encoding='utf8')
    p=work/'test_prototype.py';s=p.read_text(encoding='utf8');marker='    def test_duplicate_options_do_not_amplify_choice(self):';assert marker in s
    tests='''    def test_fractional_future_estimate_is_not_a_guaranteed_seat_for_a_small_weight(self):
        v=vehicle(cap=24);v.update(times=[100.,160.],seat_history={('A',0):[(0.,.137),(10.,.137)]},whole_seat_forecast=True)
        self.assertEqual(engine.forecast_available(v,0,20,24),0)
        self.assertEqual(v['cap'],24)
        self.assertEqual(engine.forecast_available(v,0,100,24),24)
    def test_individual_does_not_accumulate_fractional_seats_across_buses(self):
        rows=[(100.,0,0),(200.,1,0)]
        fleet=[vehicle(cap=1,onboard=[(1,{'w':.4})]),vehicle(cap=1,onboard=[(1,{'w':.4})])]
        self.assertEqual(engine.first_boardable(rows,fleet,0,0,leg(),1,[])[0],200)
        self.assertIsNone(engine.first_boardable(rows,fleet,0,0,leg(),1,[],indivisible=True))
        cache={'types':[],'type_at':[],'services':{}}
        view=engine.QueueView(cache,-1)
        self.assertIsNone(engine.first_boardable(rows,fleet,0,0,leg(),1,view,indivisible=True))
        self.assertEqual([v['onboard'][0][1]['w'] for v in fleet],[.4,.4])
'''
    p.write_text(s.replace(marker,tests+marker,1),encoding='utf8')
    p=work/'create_weekday_validation.py';s=p.read_text(encoding='utf8')
    s=s.replace("jobs=[c for c in full if c['case']!='distribution_v8-combined-regular-mon']","jobs=[c for c in full if c['case']!='distribution_v8-combined-peak-thu']",1)
    s=s.replace("reused_case={'case':full[0],'directory':str(ROOT/'runs/distribution_v8-combined-regular-mon/attempt_01')}","reused_case={'case':next(c for c in full if c['case']=='distribution_v8-combined-peak-thu'),'directory':str(ROOT/'runs/distribution_v8-combined-peak-thu/attempt_01')}",1)
    s=s.replace('부모 월요일regular seed0','부모 목요일peak seed0');p.write_text(s,encoding='utf8')
    (work/'PLAN.md').write_text('''# 가중 통행과 한 사람의 예측 좌석 구분

R7은12조건 중 목요일peak에서21.0731분/0.0548006가중통행 한 건이 실패했다. 해당17:12시점 재구성에서 앞줄은0이어서 앞사람의5513거절에 따른 유령청산은 이 사례의 직접 원인으로 확인되지 않았다. 과거 최소여석0.137명상당을 다음02-2에 확실히 있는 것으로 놓아0.0548가중통행은 탈 수 있다고 예측했지만, 실제 모형의 그 차는 만차였다.

새 후보는 가중치가 작은 대표 통행도 개인의 선택 예측에서는 한 좌석이 필요하며 여러 차량의0.x좌석을 모아 탈 수 없다고 보는 보수 시나리오다. 미래 여석 추정치를 정수 방향으로 내리고 개인의 예측 요청량은 최소1, 차량 간 분할 누적은 하지 않는다. 실제 정원44/피크2대·가중 수요·FIFO·분할 승차·운행 시각·준비20초·선호·변경 확률은 그대로다. 현재 차량의 알려진 실제 여석도 차감하지 않는다. 실제 승차 기회를 막거나20분에 강제로 이동시키는 규칙이 아니다.

이는 분수 여석 추정의 불확실성을 회피하는 이름 붙인 선택 시나리오이며 서울대에서 추정한 탑승확률이나 정확한 ETA가 아니다. 실제/인지 공급시계 공유·두 단계 승차 선택·경로 유사성·교외 승객과 체류시간의 미확인 한계는 유지한다. 일반 구조의 의향/적격 혼동 문제는 별도로 기록하고 이 실패의 입증된 원인으로 단정하지 않는다. 운영V11은 새 사용자 명시 승인 전 교체하지 않는다.

실패했던 목요일peak를 먼저 같은 입력/seed0으로 재검산한다. 통과하면 그 부모 조건을 재사용하고 다른11조건을 새로 계산한다. 같은 실패의 값/난수만 바꾸어 통과를 고르지 않는다.
''',encoding='utf8')
    save(work/'creation_manifest.json',{'experiment_id':stamp,'parent':str(PARENT),'parent_source_sha256':{n:hashlib.sha256((PARENT/n).read_bytes()).hexdigest() for n in names},
        'production_latest_sha256':hashlib.sha256((ROOT.parent/'simulation_viewer_2026-11-07/public/routing-model/latest.json').read_bytes()).hexdigest(),
        'physical_capacity_and_mass_unchanged':True,'forecast_only_conservative_whole_person_scenario':True,'production_approval_required':True})
    save(pointer,{'directory':str(work),'experiment_id':stamp,'production_approval_required':True});print(work)
if __name__=='__main__':main()
