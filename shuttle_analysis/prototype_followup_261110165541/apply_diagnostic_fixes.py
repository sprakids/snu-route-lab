"""Apply diagnosed corrections before the first follow-up run; never edit a running case."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parent
def patch(name,a,b,count=1):
    p=ROOT/name;s=p.read_text(encoding='utf8');assert s.count(a)>=count,(name,a[:70]);p.write_text(s.replace(a,b,count),encoding='utf8')
def main():
    assert not (ROOT/'runs').exists()
    cfg=json.loads((ROOT/'config.json').read_text(encoding='utf8'))
    cfg.update(learn_past_residual_seats=True,seat_history_count=3,seat_history_seconds=1800,
        review_full_stress_rate_per_second=1/150,review_age_stress_rate_per_second=1/300,
        review_full_saturation=0.4,review_age_stress_power=3)
    (ROOT/'config.json').write_text(json.dumps(cfg,indent=2),encoding='utf8')
    helper='''def forecast_available(vehicle,k,now,available):
    # A future bus is not assumed empty at a downstream stop merely because
    # it has not departed yet. Only PAST model passages are consulted here.
    history=vehicle.get('seat_history',{}).get((vehicle['rid'],k),[])
    if vehicle.get('times',[float('inf')]*(k+1))[k]<=now+EPS:return available
    recent=[free for at,free in history if 0<=now-at<=vehicle.get('seat_history_seconds',1800)]
    recent=recent[-vehicle.get('seat_history_count',3):]
    # Conservative lower-seat scenario, not a measured occupancy estimate.
    return min(available,min(recent)) if len(recent)>=2 else available


'''
    patch('engine.py','def indexed_boardable(',helper+'def indexed_boardable(')
    a="        available=vehicle['cap']-sum(s['w'] for target,s in vehicle['onboard'] if target>k)"
    patch('engine.py',a,a+"\n        available=forecast_available(vehicle,k,now,available)",2)
    patch('engine.py',"    vehicles=[];finished=[];waits=[];wait_audit=[];events=[];decisions=[];gate_boardings=[];queue_ticket=0", "    seat_history={}\n    vehicles=[];finished=[];waits=[];wait_audit=[];events=[];decisions=[];gate_boardings=[];queue_ticket=0")
    patch('engine.py',"'t0':t0,'times':times,'onboard':[]", "'t0':t0,'times':times,'seat_history':seat_history if config.get('learn_past_residual_seats') and config['behavior']!='v9_frozen' else {},\n                     'seat_history_count':config.get('seat_history_count',3),'seat_history_seconds':config.get('seat_history_seconds',1800),'onboard':[]")
    patch('engine.py',"            queue=queues[node];available=seats(vehicle['cap'],vehicle['load']);voluntary=set()", "            queue=queues[node];available=seats(vehicle['cap'],vehicle['load']);voluntary=set()\n            history=seat_history.setdefault((rid,k),[]);history.append((t,available))\n            history[:]=history[-config.get('seat_history_count',3):]")
    h='''"""Continuous causal reconsideration: ordinary repeat aversion and stress are separate."""
from dataclasses import dataclass
import math
from preferences import uniform

def integrated(a,b,changes,full,response,config):
    dt=b-a;scale=config['review_age_scale_seconds']
    ordinary=config['review_base_rate_per_second']*config['repeat_multiplier']**changes
    stress=config.get('review_full_stress_rate_per_second',0.)*(-math.expm1(-config.get('review_full_saturation',.4)*full))
    age_rate=config.get('review_age_stress_rate_per_second',0.)
    # Polynomial difference factored to retain precision for nearby events.
    fourth=dt*(b*b*b+b*b*a+b*a*a+a*a*a)
    return response*(ordinary*(dt+dt*(b+a)/(2*scale))+stress*dt+age_rate*fourth/(4*scale**3))

def delay(age,remaining,changes,full,response,config):
    if remaining<=0:return 0.
    if config.get('review_age_stress_rate_per_second',0.)<=0 and config['review_base_rate_per_second']<=0 and config.get('review_full_stress_rate_per_second',0.)<=0:return math.inf
    low=0.;high=60.
    while integrated(age,age+high,changes,full,response,config)<remaining:
        high*=2
        if high>1e12:return math.inf
    for _ in range(36):
        mid=(low+high)/2
        if integrated(age,age+mid,changes,full,response,config)<remaining:low=mid
        else:high=mid
    return (low+high)/2

@dataclass
class ReviewClock:
    last:float
    stop_entry:float
    remaining:float
    count:int
    full:int
    ordinal:int
    identity:object
    response:float
    @classmethod
    def start(cls,at,stop_entry,count,full,identity,response,config,ordinal=0):
        e=-math.log(max(1e-15,uniform(config['seed'],identity,'hazard',stop_entry,ordinal)))
        return cls(at,stop_entry,e,count,full,ordinal,identity,response)
    def update(self,at,count,full,config):
        assert at>=self.last-1e-7
        self.remaining=max(0.,self.remaining-integrated(self.last-self.stop_entry,at-self.stop_entry,self.count,self.full,self.response,config))
        self.last=at;self.count=count;self.full=full
    def due(self,config):return self.last+delay(self.last-self.stop_entry,self.remaining,self.count,self.full,self.response,config)

def interval_probability(a,b,count,full,response,config):
    return -math.expm1(-integrated(a,b,count,full,response,config))
'''
    (ROOT/'hazard.py').write_text(h,encoding='utf8')
    # Preserve targeted decision traces for root-cause audits without exporting
    # synthetic identities or exhaustive individual costs to the public site.
    patch('policy.py',"self.counts=Counter();self.boarding_choices=[];self.initial_choices=0", "self.counts=Counter();self.boarding_choices=[];self.initial_choices=0;self.review_diagnostics=[]")
    marker="            selected=choose(candidates,identity,('reroute',state['visit'],state['review_ordinal']),config)"
    patch('policy.py',marker,marker+'''\n            if at-state['stop_entry']>=600 and len(self.review_diagnostics)<20000:
                self.review_diagnostics.append({'time':at,'uid':identity,'node':node,'age':at-state['stop_entry'],
                    'changes':count,'full_passes':state['full_passes'],'current_eta':current.eta if current else None,
                    'candidate_count':len(candidates),'selected':selected['key'] if selected else None,
                    'best_costs':sorted([(str(c['key']),c['cost'],c['prediction'].eta) for c in candidates],key=lambda r:r[1])[:4]})''')
    patch('engine.py',"'parent_ids':bundle['parent_ids'],", "'review_diagnostics':policy.review_diagnostics,\n            'parent_ids':bundle['parent_ids'],")
    plan=ROOT/'PLAN.md';plan.write_text(plan.read_text(encoding='utf8').replace('後속','후속')+'''

추가 원인과 사전 수정: 과거14시 상태 재구성에서 앞줄1.315명·예측7.53분 대기였으나 상류에서 차가 채워져 이후31개가 만차였다. 운행 전 차량의 차내0명을 하류 여석으로 쓰지 않고 최근3회/30분 이내 통과의 보수 여석 시나리오를 미래 예측에만 적용한다. 실제 승하차·정원은 바꾸지 않는다. 이 추정은 실제 여석 실측이 아니다.

기존 위험률은0.3^변경횟수가 만차 스트레스까지 줄였다. 반복회수는 기본 성향에만 적용하고, 개인 만차와 연속 대기 나이에 따른 연속 위험률을 별도 더한다. 계수는 이름 붙인 미보정 시나리오이다.20분에서 강제 전환하거나 위험률을 불연속 변경하지 않는다. 같은 물리적 줄의 자격 확장도 횟수·시간을 초기화하지 않는다.
''',encoding='utf8')
    manifest={'status':'DIAGNOSED_FIXES_BEFORE_FIRST_RUN','source_diagnostic':'../prototype_model_2026-11-10/long_wait_reconstruction.json',
        'observations_used_for_preference_fitting':0,'actual_supply_or_demand_changed':False,'forced20_exit':False,
        'fixes':['complete same-stop multi-stage strategies','causal rolling lower-seat forecast','stress separate from ordinary repeat propensity'],
        'config':cfg,'new_source_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ('engine.py','policy.py','hazard.py','operations.py')}}
    (ROOT/'diagnostic_fixes.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print('Applied diagnosed fixes before any follow-up run',flush=True)

if __name__=='__main__':main()
