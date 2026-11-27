"""Remove extra rounding before FIFO; retain the individual indivisible request."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf8'))
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def main():
    pointer=ROOT/'individual_request_candidate.json';assert not pointer.exists()
    parent=Path(read(ROOT/'whole_seat_candidate.json')['directory']);reference=ROOT.parent/'prototype_followup_261110181553'
    stamp=datetime.now(ZoneInfo('Asia/Seoul')).strftime('%y%m%d%H%M%S');work=ROOT.parent/('prototype_followup_'+stamp);work.mkdir()
    names=['artifacts.py','config.json','preferences.py','hazard.py','capacity.py','physics.py','fares.py','prepare.py','policy.py','metrics.py','engine.py','operations.py','run_case.py','fixtures.py','test_prototype.py','dwell.py','input_manifest.json','capacity44_amendment.json','pair_amendment.json','USER_DIRECTIVE.md','analyze_followup.py','create_weekday_validation.py']
    for n in names:shutil.copy2(parent/n,work/n)
    shutil.copytree(parent/'frozen',work/'frozen')
    for p in parent.glob('physical_paths_*.json.gz'):shutil.copy2(p,work/p.name)
    cfg=read(work/'config.json');cfg['forecast_seat_interpretation']='One indivisible marginal person is queried AFTER the ordinary weighted FIFO forecast of people ahead. No rounding of pre-queue seats; no accumulation of fractions across departures. Physical weighted demand, capacity and actual boarding unchanged. Not a probability guarantee.'
    save(work/'config.json',cfg)
    lock=read(parent/'experiment_lock.json');lock.update(experiment_id=stamp,parent_followup=str(parent),
        hypothesis='Retain individual request>=1 and no across-vehicle accumulation; remove pre-FIFO flooring, which otherwise rejects2.1free minus1.05ahead even though1.05remains. Methodological correction chosen before opening the floor-variant outcomes.',
        pre_fifo_rounding_removed=True)
    save(work/'experiment_lock.json',lock)
    p=work/'engine.py';s=p.read_text(encoding='utf8');a=s.index('def forecast_available(');b=s.index('\ndef indexed_boardable(',a)
    old=(reference/'engine.py').read_text(encoding='utf8');x=old.index('def forecast_available(');y=old.index('\ndef indexed_boardable(',x)
    s=s[:a]+old[x:y]+s[b:]
    field="'whole_seat_forecast':bool(config.get('forecast_person_requires_whole_seat',False) and config['behavior']!='v9_frozen'),";assert field in s
    s=s.replace(field,'',1);p.write_text(s,encoding='utf8')
    p=work/'test_prototype.py';s=p.read_text(encoding='utf8');a=s.index('    def test_fractional_future_estimate_is_not_a_guaranteed_seat_for_a_small_weight(self):');b=s.index('    def test_individual_does_not_accumulate_fractional_seats_across_buses(self):',a)
    tests='''    def test_small_packet_does_not_define_an_individual_seat_requirement(self):
        v=vehicle(cap=24);v.update(times=[100.,160.],seat_history={('A',0):[(0.,.137),(10.,.137)]})
        self.assertAlmostEqual(engine.forecast_available(v,0,20,24),.137)
        self.assertEqual(engine.first_boardable([(100.,0,0)],[v],20,20,leg(),.0548,[])[0],100)
        self.assertIsNone(engine.first_boardable([(100.,0,0)],[v],20,20,leg(),1,[],indivisible=True))
        self.assertEqual(v['cap'],24);self.assertEqual(engine.forecast_available(v,0,100,24),24)
    def test_one_seat_after_fifo_not_rounded_before_people_ahead(self):
        v=vehicle(cap=3,onboard=[(1,{'w':.9})]);v['times']=[100.,160.]
        rows=[(100.,0,0)];ahead=[waiter(1.05)]
        self.assertEqual(engine.first_boardable(rows,[v],0,0,leg(),1,ahead,indivisible=True)[0],100)
        cache={'types':[{'indices':[0],'prefix':[0.,1.05]}],'type_at':[0],'services':{('A',0):[0]}}
        self.assertEqual(engine.first_boardable(rows,[v],0,0,leg(),1,engine.QueueView(cache,0),indivisible=True)[0],100)
        self.assertEqual(v['onboard'][0][1]['w'],.9)
'''
    p.write_text(s[:a]+tests+s[b:],encoding='utf8')
    (work/'PLAN.md').write_text('''# 앞줄 처리 후 한 사람의 비분할 좌석 예측

R7의 목요일peak21.0731분 실패를 고친다. R8의 한사람최소1석/차량간좌석조각누적금지는 유지하되, 앞줄을빼기전floor는제거한다.2.1석예측−앞줄1.05=1.05석이면한사람이가능해야한다는독립검토반례를수용한최소수정이다. 이수정은R8결과를열기전방법상선택했으며R8원본·부분실행·결과는보존한다.

선택예측은일반가중FIFO로앞줄을처리한후대표개인요청량을최소1로비교하며여러차량의소수여석을모아승차한것으로보지않는다. 실제정원·수요질량·승차시분할·FIFO·준비20초·대기시계·운행시각·선호/위험률/무제한변경은그대로다. 과거소수여석으로다음차여석을확실히알수없다는불확실성은남으며실측탑승확률이나정확한ETA를입증한것은아니다.

실패했던목요일peak같은seed0을먼저검산하고통과하면그조건을재사용해나머지11조건을계산한다. 운영V11및latest는새사용자명시승인전변경하지않는다. 독립실측부족은NOT_EVALUABLE이다.
''',encoding='utf8')
    save(work/'creation_manifest.json',{'experiment_id':stamp,'parent':str(parent),'parent_source_sha256':{n:hashlib.sha256((parent/n).read_bytes()).hexdigest() for n in names},
        'production_latest_sha256':hashlib.sha256((ROOT.parent/'simulation_viewer_2026-11-07/public/routing-model/latest.json').read_bytes()).hexdigest(),
        'no_pre_fifo_floor':True,'physical_supply_and_demand_unchanged':True,'production_approval_required':True})
    save(pointer,{'directory':str(work),'experiment_id':stamp,'production_approval_required':True});print(work)
if __name__=='__main__':main()
